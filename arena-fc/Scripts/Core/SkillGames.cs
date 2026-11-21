// Arena FC - Skill Games (roadmap 2.4).
//
// The menu's SKILL GAMES used to start a plain friendly.  These are five short,
// scored challenges on the training ground, FC-style, run by the match engine
// itself (so the real ball, shooting, passing and keeper code is what you are
// scored on):
//   * Shooting   - 60 s: shots from around the box against the keeper.  Corner
//                  finishes (outer third of the goal) score 3, anything else 1.
//   * Passing    - 60 s: one team-mate is lit up; a completed pass to him scores
//                  1 (2 if over 20 m).  Mannequins stand in the lanes.
//   * Dribbling  - 60 s: weave through a slalom of mannequins; each one passed on
//                  the correct side scores 1, finishing in the empty net 3.
//   * Crossing   - 60 s: from the wing; a team-mate's goal from your cross scores
//                  3, your own goal 1.  Their keeper and two defenders defend.
//   * Free kicks - six attempts from 18-28 m over a four-man wall: corner 3,
//                  otherwise 1.
// Each attempt resets when it is over (goal, save, out, lost, or a dead ball).
// The session ends with a whistle; Score[0] holds the points.
using System;
using System.Collections.Generic;
using System.Numerics;

namespace ArenaFC.Core;

public sealed partial class MatchEngine
{
    public const int ModeSkill = 4;
    public bool IsSkill => Options.Mode == ModeSkill;

    public SkillGame Skill => Options.SkillGame;
    public int SkillScore { get; private set; }
    public float SkillTimeLeft { get; private set; }
    public int SkillAttemptsLeft { get; private set; }
    public int SkillAttempts { get; private set; }
    /// <summary>Passing: the lit-up team-mate.  -1 otherwise.</summary>
    public int SkillTarget { get; private set; } = -1;
    /// <summary>Dribbling: mannequins still to pass, in order.</summary>
    public readonly List<int> SkillSlalom = new();
    public string SkillMessage { get; private set; } = "";

    private const float SkillDuration = 60f;
    private const int SkillFreeKicks = 6;
    private float _skillResetTimer = -1f, _skillLoose;
    private int _skillPrevOwner = -1, _skillCrosser = -1;
    private bool _skillCrossLive;
    private int _skillFkIndex;
    private bool _skillStarted;

    private static readonly (float back, float z)[] FreeKickSpots =
        { (20f, -6f), (22f, 8f), (25f, 0f), (19f, 11f), (27f, -9f), (23f, -2f) };

    public static string SkillTitle(SkillGame g) => g switch
    {
        SkillGame.Shooting => "SHOOTING",
        SkillGame.Passing => "PASSING",
        SkillGame.Dribbling => "DRIBBLING",
        SkillGame.Crossing => "CROSSING",
        SkillGame.FreeKicks => "FREE KICKS",
        _ => g.ToString().ToUpperInvariant(),
    };

    public static string SkillRules(SkillGame g) => g switch
    {
        SkillGame.Shooting => "60 s. Corner finishes 3, any goal 1.",
        SkillGame.Passing => "60 s. Pass to the lit-up team-mate: 1 point, 2 over 20 m.",
        SkillGame.Dribbling => "60 s. Weave the mannequins (1 each), finish in the net (3).",
        SkillGame.Crossing => "60 s. A team-mate scores from your cross: 3. Your own goal: 1.",
        SkillGame.FreeKicks => "6 free kicks over the wall. Corner 3, any goal 1.",
        _ => "",
    };

    /// <summary>Is this player part of the current skill game?</summary>
    private bool SkillActive(PlayerState p)
    {
        var S = State;
        switch (Skill)
        {
            case SkillGame.Shooting:
            case SkillGame.FreeKicks:
                return p.Index == S.Controlled || (p.IsKeeper && p.Team == 1);
            case SkillGame.Passing:
                return p.Team == 0 && !p.IsKeeper;
            case SkillGame.Dribbling:
                return p.Index == S.Controlled;
            case SkillGame.Crossing:
                if (p.Team == 0) return p.Index == S.Controlled || p.Index == SkillStriker(0) || p.Index == SkillStriker(1);
                return p.IsKeeper || p.Index == Options.TeamSize + 1 || p.Index == Options.TeamSize + 2;
        }
        return false;
    }

    private int SkillStriker(int k) => Options.TeamSize - 1 - k;

    private void SkillStart()
    {
        _skillStarted = true;
        SkillScore = 0; SkillAttempts = 0;
        SkillTimeLeft = Skill == SkillGame.FreeKicks ? 0f : SkillDuration;
        SkillAttemptsLeft = Skill == SkillGame.FreeKicks ? SkillFreeKicks : 0;
        _skillFkIndex = 0;
        State.Score[0] = State.Score[1] = 0;
        SkillSetup();
    }

    /// <summary>Lay out one attempt.</summary>
    private void SkillSetup()
    {
        var S = State;
        _skillResetTimer = -1f; _skillLoose = 0f; _skillCrossLive = false; _skillCrosser = -1;
        ResetPositions(true);
        var b = S.Ball;
        b.Owner = -1; b.HasPending = false; b.PendingKind = 0; b.PendingFrom = -1;
        b.Vel = Vector3.Zero; b.Spin = Vector3.Zero; b.NoPickup = 0; b.PassReceiver = -1; b.PassFrom = -1;
        int a = SideSign(0);
        int ts = Options.TeamSize;
        float gx = GoalPos(0).X;
        int spot = 0;
        // Everyone not in the game watches from beside the far touchline.
        foreach (var p in S.Players)
        {
            p.MustPlayBall = false; p.PossessionLock = 0f; p.Stamina = 1f;
            p.Action = "idle"; p.ActionTimer = 0f; p.Vel = Vector3.Zero;
        }
        void Bench(PlayerState q)
        {
            q.Pos = new Vector3(-24f + spot++ * 2.2f, 0, -(Mx.HalfWidth + 1.8f));
            q.Target = q.Pos; q.Facing = Vector3.UnitZ;
        }
        int ctrl;
        switch (Skill)
        {
            case SkillGame.Shooting:
            {
                ctrl = SkillStriker(0);
                foreach (var p in S.Players) if (p.Index != ctrl && !(p.IsKeeper && p.Team == 1)) Bench(p);
                float back = Rng.Range(17f, 26f), z = Rng.Range(-12f, 12f);
                Place(ctrl, new Vector3(gx - a * back, 0, z), Mx.FlatDir(new Vector3(gx - a * back, 0, z), GoalPos(0)));
                Hand(ctrl);
                SkillMessage = "Shoot!  Corners score 3.";
                break;
            }
            case SkillGame.FreeKicks:
            {
                ctrl = SkillStriker(0);
                foreach (var p in S.Players) if (p.Index != ctrl && !(p.IsKeeper && p.Team == 1)) Bench(p);
                var (back, z) = FreeKickSpots[_skillFkIndex % FreeKickSpots.Length];
                Vector3 ball = new(gx - a * back, 0, z);
                Place(ctrl, ball - a * new Vector3(.8f, 0, 0), Mx.FlatDir(ball, GoalPos(0)));
                Hand(ctrl);
                b.Pos = ball + new Vector3(0, Mx.BallRadius, 0);
                S.Players[ctrl].MustPlayBall = true;
                S.RestartPos = ball;
                // A four-man wall 9.15 m out on the line to the goal (inactive: it stands).
                Vector3 toGoal = Mx.FlatDir(ball, GoalPos(0)), side = new(-toGoal.Z, 0, toGoal.X);
                for (int i = 0; i < 4; i++)
                {
                    var w = S.Players[ts + 1 + i];
                    Place(w.Index, ball + toGoal * 9.15f + side * ((i - 1.5f) * .6f + .45f), -toGoal);
                }
                SkillMessage = $"Free kick {SkillFreeKicks - SkillAttemptsLeft + 1} of {SkillFreeKicks}.";
                break;
            }
            case SkillGame.Passing:
            {
                ctrl = ts / 2;
                // Your outfielders in a wide shape; their players are mannequins in the lanes.
                int k = 0;
                foreach (var p in S.Players)
                {
                    if (p.IsKeeper) { Bench(p); continue; }
                    if (p.Team == 1)
                    {
                        float ang = k * 2.4f;
                        Place(p.Index, new Vector3(a * (6f + 14f * MathF.Sin(ang * .7f)), 0, 16f * MathF.Cos(ang)), Vector3.UnitX);
                        k++;
                    }
                }
                Place(ctrl, new Vector3(-a * 8f, 0, 0), new Vector3(a, 0, 0));
                Hand(ctrl);
                SkillPickTarget(ctrl);
                SkillMessage = "Pass to the lit-up team-mate.";
                break;
            }
            case SkillGame.Dribbling:
            {
                ctrl = SkillStriker(0);
                foreach (var p in S.Players) if (p.Index != ctrl && p.Team == 0) Bench(p);
                foreach (var p in S.Players) if (p.IsKeeper && p.Team == 1) Bench(p);
                SkillSlalom.Clear();
                // Mannequins in a line towards goal, alternating sides of the centre.
                for (int i = 0; i < ts - 1; i++)
                {
                    var m = S.Players[ts + 1 + i];
                    if (i >= 7) { Bench(m); continue; }
                    float x = gx - a * (44f - i * 5.5f);
                    Place(m.Index, new Vector3(x, 0, (i % 2 == 0 ? 1f : -1f) * 1.2f), new Vector3(-a, 0, 0));
                    SkillSlalom.Add(m.Index);
                }
                Place(ctrl, new Vector3(gx - a * 52f, 0, 0), new Vector3(a, 0, 0));
                Hand(ctrl);
                SkillMessage = "Weave the mannequins, then finish.";
                break;
            }
            default: // Crossing
            {
                ctrl = 2 <= ts - 3 ? ts - 3 : 1;
                foreach (var p in S.Players)
                    if (!(p.Index == ctrl || p.Index == SkillStriker(0) || p.Index == SkillStriker(1)
                          || (p.IsKeeper && p.Team == 1) || p.Index == ts + 1 || p.Index == ts + 2)) Bench(p);
                float side = Rng.Next() < .5f ? 1f : -1f;
                Place(ctrl, new Vector3(gx - a * 30f, 0, side * (Mx.HalfWidth - 5f)), new Vector3(a, 0, 0));
                Place(SkillStriker(0), new Vector3(gx - a * 22f, 0, side * 3f), new Vector3(a, 0, 0));
                Place(SkillStriker(1), new Vector3(gx - a * 24f, 0, -side * 4f), new Vector3(a, 0, 0));
                Place(ts + 1, new Vector3(gx - a * 10f, 0, side * 2f), new Vector3(-a, 0, 0));
                Place(ts + 2, new Vector3(gx - a * 11f, 0, -side * 3f), new Vector3(-a, 0, 0));
                Hand(ctrl);
                _skillCrosser = ctrl;
                SkillMessage = "Get down the line and cross.";
                break;
            }
        }
        S.Controlled = ctrl;
        _skillPrevOwner = ctrl;
        S.ControlLock = 99f;           // the skill-game player stays selected
        S.Phase = Phase.Play;
        S.PhaseTimer = 0f;

        void Place(int i, Vector3 pos, Vector3 facing)
        {
            var q = S.Players[i];
            q.Pos = pos; q.Target = pos; q.Vel = Vector3.Zero; q.Facing = Mx.Norm(Mx.Flat(facing));
        }
        void Hand(int i)
        {
            var q = S.Players[i];
            b.Pos = q.Pos + q.Facing * .6f + new Vector3(0, Mx.BallRadius, 0);
            b.Owner = i; b.LastTouch = i; b.LastTouchSide = q.Team; b.FreeTime = 0f;
        }
    }

    private void SkillPickTarget(int from)
    {
        var S = State;
        var opts = new List<int>();
        foreach (var p in S.Players)
            if (p.Team == 0 && !p.IsKeeper && p.Index != from)
            {
                float d = Mx.FlatDist(p.Pos, S.Players[from].Pos);
                if (d > 9f && d < 38f) opts.Add(p.Index);
            }
        SkillTarget = opts.Count == 0 ? -1 : opts[Math.Min(opts.Count - 1, (int)(Rng.Next() * opts.Count))];
    }

    private void SkillAdd(int points, string why)
    {
        SkillScore += points;
        State.Score[0] = SkillScore;
        SkillMessage = $"+{points}  {why}";
        Add(EventKind.Info, $"Skill game: +{points} ({why}) - {SkillScore} points");
    }

    /// <summary>A goal in a skill game: score it, then set up the next attempt.</summary>
    private void SkillGoal(int side)
    {
        var b = State.Ball;
        if (side != 0) return;
        bool corner = MathF.Abs(b.Pos.Z) > Mx.GoalHalfWidth * .62f;
        switch (Skill)
        {
            case SkillGame.Shooting:
            case SkillGame.FreeKicks:
                SkillAdd(corner ? 3 : 1, corner ? "corner finish" : "goal");
                break;
            case SkillGame.Dribbling:
                SkillAdd(3, "finished");
                break;
            case SkillGame.Crossing:
                if (_skillCrossLive && State.GoalScorer >= 0 && State.GoalScorer != _skillCrosser) SkillAdd(3, "scored from your cross");
                else SkillAdd(1, "goal");
                break;
        }
    }

    /// <summary>Per-tick skill-game upkeep: clock, scoring, attempt resets.</summary>
    private void SkillTick(float dt)
    {
        var S = State;
        if (!_skillStarted) { SkillStart(); return; }
        foreach (var p in S.Players) p.Stamina = 1f;
        if (S.Phase != Phase.Play) return;
        if (Skill != SkillGame.FreeKicks)
        {
            SkillTimeLeft -= dt;
            if (SkillTimeLeft <= 0f) { SkillEnd(); return; }
        }
        var b = S.Ball;
        int owner = b.Owner;
        bool over = false;
        switch (Skill)
        {
            case SkillGame.Passing:
                if (owner >= 0 && owner != _skillPrevOwner && S.Players[owner].Team == 0 && _skillPrevOwner >= 0)
                {
                    if (owner == SkillTarget)
                    {
                        float d = Mx.FlatDist(S.Players[owner].Pos, S.Players[_skillPrevOwner].Pos);
                        SkillAdd(d > 20f ? 2 : 1, d > 20f ? "long pass" : "pass");
                    }
                    SkillPickTarget(owner);
                    S.Controlled = owner;
                }
                break;
            case SkillGame.Dribbling:
                if (owner == S.Controlled && SkillSlalom.Count > 0)
                {
                    var m = S.Players[SkillSlalom[0]];
                    var c = S.Players[owner];
                    int a = SideSign(0);
                    if ((c.Pos.X - m.Pos.X) * a > 0f)
                    {
                        // passed level with it: on the side away from where it stands?
                        bool rightSide = MathF.Sign(c.Pos.Z - m.Pos.Z) == -MathF.Sign(m.Pos.Z);
                        if (rightSide) SkillAdd(1, "mannequin");
                        else SkillMessage = "Wrong side!";
                        SkillSlalom.RemoveAt(0);
                    }
                }
                break;
            case SkillGame.Crossing:
                if (owner < 0 && b.PassFrom == _skillCrosser && b.Pos.Y > .8f) _skillCrossLive = true;
                break;
        }
        if (owner >= 0) _skillPrevOwner = owner;
        // Attempt over: the keeper or a defender has it, or the ball is lying dead.
        if (owner >= 0 && S.Players[owner].Team == 1) over = true;
        if (owner < 0 && b.Vel.LengthSquared() < .04f) _skillLoose += dt; else _skillLoose = 0f;
        if (_skillLoose > 2f) over = true;
        if (Skill == SkillGame.FreeKicks && owner < 0 && !b.HasPending && b.FreeTime > 4f) over = true;
        if (over && _skillResetTimer < 0f) _skillResetTimer = .9f;
        if (_skillResetTimer >= 0f)
        {
            _skillResetTimer -= dt;
            if (_skillResetTimer < 0f) SkillNext();
        }
    }

    /// <summary>After a goal, a save, the ball going out or dying: the next attempt.</summary>
    private void SkillNext()
    {
        SkillAttempts++;
        if (Skill == SkillGame.FreeKicks)
        {
            SkillAttemptsLeft--;
            _skillFkIndex++;
            if (SkillAttemptsLeft <= 0) { SkillEnd(); return; }
        }
        if (Skill == SkillGame.Passing && State.Ball.Owner >= 0 && State.Players[State.Ball.Owner].Team == 0 && State.Phase == Phase.Play)
            return;                   // passing keeps flowing; only a dead or lost ball resets it
        SkillSetup();
    }

    private void SkillEnd()
    {
        var S = State;
        S.Score[0] = SkillScore;
        S.Phase = Phase.FullTime;
        S.PhaseTimer = 0f;
        SkillMessage = $"{SkillTitle(Skill)}: {SkillScore} points";
        Add(EventKind.Whistle, $"Skill game over - {SkillTitle(Skill)}: {SkillScore} points");
    }
}
