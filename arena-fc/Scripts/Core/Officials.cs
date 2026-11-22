// Arena FC - match officials on the pitch (presentation only).
//
// The rules engine always refereed the game, but nobody was on the field to give the calls.  This places a
// referee, two assistant referees and a fourth official the way real officials work (Sprite Forge
// sforge.officials ROLES, v11.31) and turns the match's own event stream into their signals: whistle,
// cards, advantage, penalty, free kicks, the assistants' flags, the fourth official's board.
//
// It only READS the MatchState and the event list.  The officials are separate PlayerStates that are never
// added to State.Players, so the simulation, the network snapshot and every replay stay exactly as they were.
using System;
using System.Collections.Generic;
using System.Numerics;

namespace ArenaFC.Core;

public enum OfficialRole { Referee = 0, AssistantA = 1, AssistantB = 2, Fourth = 3 }

public sealed class OfficialsDirector
{
    public const int Count = 4;
    public readonly PlayerState[] Officials = new PlayerState[Count];
    /// <summary>Prop each official shows this frame ("flag", "card_yellow", "card_red", "board", "").</summary>
    public readonly string[] Prop = new string[Count];
    /// <summary>Calls given so far, oldest first (for tests and the replay of decisions).</summary>
    public readonly List<(OfficialRole who, string action)> Calls = new();

    // per official: signals still to give, each with the pause before it (s)
    private readonly List<(string action, float delay)>[] _queue = new List<(string, float)>[Count];
    private MatchEvent? _lastSeen;

    // Real officials' pace: a referee covers ~11 km a match, sprinting ~7 m/s at most.
    private const float RefMaxSpeed = 6.8f, AssistantMaxSpeed = 6.4f, Accel = 4.5f;
    private const float TouchlineOffset = 1.2f;
    /// <summary>Between the technical areas, in front of the dugouts (sforge.stadium puts them 3.2 m back).</summary>
    private const float FourthOffset = 2.3f;

    public OfficialsDirector(string kitPrimary, string kitTrim, string kitShorts, string kitPattern)
    {
        for (int i = 0; i < Count; i++)
        {
            _queue[i] = new List<(string, float)>();
            Prop[i] = "";
            Officials[i] = new PlayerState
            {
                Index = 1000 + i, Team = -1, Role = Role.Midfielder, Facing = new Vector3(0, 0, 1),
                Spec = new CharacterSpec
                {
                    Name = ((OfficialRole)i).ToString(), DisplayName = "", Number = 0,
                    KitPrimary = kitPrimary, KitSecondary = kitPrimary, KitTrim = kitTrim, KitPattern = kitPattern,
                    ShortsColor = kitShorts, SocksColor = kitShorts, BootsColor = "#111318",
                    SkinTone = (i * 2 + 1) % CharacterSpec.SkinPalette.Length, HairStyle = (i + 3) % 5,
                    Height = 1.78f + i * .02f, Pace = .6f,
                },
            };
        }
        var r = Officials[(int)OfficialRole.Referee];
        r.Pos = new Vector3(-6f, 0, -10f);
        Officials[(int)OfficialRole.AssistantA].Pos = new Vector3(Mx.HalfLength * .5f, 0, Mx.HalfWidth + TouchlineOffset);
        Officials[(int)OfficialRole.AssistantB].Pos = new Vector3(-Mx.HalfLength * .5f, 0, -Mx.HalfWidth - TouchlineOffset);
        Officials[(int)OfficialRole.Fourth].Pos = new Vector3(0, 0, -Mx.HalfWidth - FourthOffset);
        Prop[(int)OfficialRole.AssistantA] = Prop[(int)OfficialRole.AssistantB] = "flag";
    }

    /// <summary>The official kit that clashes with neither team (sforge.officials.kit_for).</summary>
    public static (string primary, string trim, string shorts, string pattern) KitFor(string home, string away)
    {
        var kits = new (string p, string t, string s, string pat)[]
        {
            ("#111318", "#e9eaee", "#111318", "plain"),     // classic
            ("#d9f99d", "#111318", "#111318", "pinstripes"), // volt
            ("#b91c1c", "#111318", "#111318", "band"),      // crimson
            ("#0f766e", "#e9eaee", "#111318", "chevron"),   // teal
            ("#1e3a8a", "#facc15", "#111318", "plain"),     // royal
        };
        foreach (var k in kits)
            if (Clubs.ColourDistance(k.p, home) > .3f && Clubs.ColourDistance(k.p, away) > .3f) return k;
        return kits[1];
    }

    /// <summary>Which half an assistant owns: A the +X half on the +Z touchline, B the -X half on -Z.</summary>
    public static float AssistantHalf(OfficialRole r) => r == OfficialRole.AssistantA ? 1f : -1f;

    public void Update(MatchEngine engine, float dt)
    {
        if (dt <= 0f) return;
        var s = engine.State;
        ReadEvents(engine);
        var ball = s.Ball.Pos;
        Steer(OfficialRole.Referee, RefereeTarget(ball), ball, RefMaxSpeed, dt);
        foreach (var ar in new[] { OfficialRole.AssistantA, OfficialRole.AssistantB })
        {
            float x = AssistantLineX(engine, AssistantHalf(ar));
            float z = AssistantHalf(ar) * (Mx.HalfWidth + TouchlineOffset);
            // assistants face across the pitch and sidestep along the line
            var face = new Vector3(0, 0, -MathF.Sign(z));
            Steer(ar, new Vector3(x, 0, z), Officials[(int)ar].Pos + face, AssistantMaxSpeed, dt);
        }
        Steer(OfficialRole.Fourth, new Vector3(0, 0, -Mx.HalfWidth - FourthOffset), new Vector3(0, 0, 0), 2f, dt);
        for (int i = 0; i < Count; i++) Advance(i, dt);
    }

    /// <summary>Diagonal system: the referee keeps 12-20 m from the ball, on the near-left / far-right
    /// diagonal (the opposite one to the assistants), on the inside of play.</summary>
    public static Vector3 RefereeTarget(Vector3 ball)
    {
        float diagZ = -ball.X * (Mx.HalfWidth / Mx.HalfLength) * .55f;
        var t = new Vector3(ball.X - MathF.Sign(ball.X == 0 ? 1 : ball.X) * 7f, 0, diagZ * .6f + ball.Z * .4f);
        var d = t - new Vector3(ball.X, 0, ball.Z);
        float len = d.Length();
        if (len < 12f) t = new Vector3(ball.X, 0, ball.Z) + (len < .01f ? new Vector3(-1, 0, 0) : d / len) * 12f;
        if (len > 20f) t = new Vector3(ball.X, 0, ball.Z) + d / len * 20f;
        t.X = Math.Clamp(t.X, -Mx.HalfLength + 2f, Mx.HalfLength - 2f);
        t.Z = Math.Clamp(t.Z, -Mx.HalfWidth + 2f, Mx.HalfWidth - 2f);
        return t;
    }

    /// <summary>Level with the second-last defender of the side defending the goal in this half, or with
    /// the ball when it is nearer the goal line; never past halfway.</summary>
    public static float AssistantLineX(MatchEngine engine, float half)
    {
        var s = engine.State;
        int defending = -1;
        for (int side = 0; side < 2; side++)
            if (MathF.Sign(engine.OwnGoalPos(side).X) == MathF.Sign(half)) defending = side;
        float last = 0f, second = 0f;
        foreach (var p in s.Players)
        {
            if (p.Team != defending || p.SentOff) continue;
            float d = p.Pos.X * half;        // depth towards this goal line
            if (d > last) { second = last; last = d; }
            else if (d > second) second = d;
        }
        float line = MathF.Max(second, s.Ball.Pos.X * half);
        return Math.Clamp(line, 0f, Mx.HalfLength) * half;
    }

    private void Steer(OfficialRole role, Vector3 target, Vector3 look, float maxSpeed, float dt)
    {
        var o = Officials[(int)role];
        var to = new Vector3(target.X - o.Pos.X, 0, target.Z - o.Pos.Z);
        float dist = to.Length();
        // ease off near the spot instead of overshooting; signals are given standing
        float want = o.ActionTimer > 0f ? 0f : Math.Min(maxSpeed, dist * 1.4f);
        var desired = dist > .05f ? to / dist * want : Vector3.Zero;
        var dv = desired - o.Vel;
        float maxDv = Accel * dt;
        if (dv.Length() > maxDv) dv = dv / dv.Length() * maxDv;
        o.Vel += dv;
        o.Pos += o.Vel * dt;
        var f = new Vector3(look.X - o.Pos.X, 0, look.Z - o.Pos.Z);
        if (f.LengthSquared() > .01f)
        {
            f = Vector3.Normalize(f);
            o.Facing = Vector3.Normalize(Vector3.Lerp(o.Facing, f, Math.Min(1f, dt * 6f)));
        }
        o.Sprinting = o.Vel.Length() > 5f;
    }

    private void Advance(int i, float dt)
    {
        var o = Officials[i];
        if (o.ActionTimer > 0f)
        {
            o.ActionTimer -= dt;
            if (o.ActionTimer <= 0f)
            {
                o.Action = "idle";
                if (Prop[i].StartsWith("card") || Prop[i] == "board") Prop[i] = "";
            }
            return;
        }
        var q = _queue[i];
        if (q.Count == 0) return;
        var (action, delay) = q[0];
        if (delay > 0f) { q[0] = (action, delay - dt); return; }
        q.RemoveAt(0);
        // a backlog (several fouls in a burst) is not replayed one by one: keep the latest two
        while (q.Count > 2) q.RemoveAt(0);
        Start(i, action);
    }

    /// <summary>Clip lengths of the sforge.officials pack (seconds) - the action timer holds the call.</summary>
    public static float Duration(string action) => action switch
    {
        "off_ref_whistle" => 1.0f, "off_ref_card" => 1.8f, "off_ref_advantage" => 1.2f, "off_ref_penalty" => 1.6f,
        "off_ref_direct" => 1.4f, "off_ref_indirect" => 1.8f, "off_ref_goal" => 1.4f, "off_ar_flag_up" => 1.6f,
        "off_ar_offside" => 2.4f, "off_ar_flag_corner" => 1.4f, "off_ar_flag_throw" => 1.4f,
        "off_fourth_board" => 2.4f, _ => 1f,
    };

    private void Start(int i, string action)
    {
        var o = Officials[i];
        string prop = "";
        if (action.StartsWith("off_ref_card:"))
        {
            prop = action.EndsWith("red") ? "card_red" : "card_yellow";
            action = "off_ref_card";
        }
        o.Action = action;
        o.ActionDuration = Duration(action);
        o.ActionTimer = o.ActionDuration;
        o.ActionContactAt = 0f;
        if (prop != "") Prop[i] = prop;
        if (action == "off_fourth_board") Prop[i] = "board";
        Calls.Add(((OfficialRole)i, action));
    }

    private void Queue(OfficialRole who, string action, float delay = 0f) => _queue[(int)who].Add((action, delay));

    private void ReadEvents(MatchEngine engine)
    {
        var ev = engine.Events;
        if (ev.Count == 0) return;
        int start = 0;
        if (_lastSeen != null)
        {
            int k = ev.LastIndexOf(_lastSeen);
            // the log keeps the last 250 events; if ours scrolled out, only the newest is still news
            start = k >= 0 ? k + 1 : ev.Count - 1;
        }
        for (int k = start; k < ev.Count; k++) React(engine, ev[k]);
        _lastSeen = ev[^1];
    }

    private OfficialRole NearestAssistant(Vector3 pos) => pos.X >= 0 ? OfficialRole.AssistantA : OfficialRole.AssistantB;

    private void React(MatchEngine engine, MatchEvent e)
    {
        var ball = engine.State.Ball.Pos;
        string t = e.Text ?? "";
        switch (e.Kind)
        {
            case EventKind.Foul:
                Queue(OfficialRole.Referee, "off_ref_whistle");
                Queue(OfficialRole.Referee, t.Contains("Penalty", StringComparison.OrdinalIgnoreCase) ? "off_ref_penalty"
                    : t.Contains("indirect", StringComparison.OrdinalIgnoreCase) ? "off_ref_indirect" : "off_ref_direct");
                break;
            case EventKind.Card:
                if (t.Contains("keeps his place")) break;
                bool red = t.Contains("is off") || t.Contains("Red", StringComparison.OrdinalIgnoreCase);
                Queue(OfficialRole.Referee, "off_ref_card:" + (red ? "red" : "yellow"), .3f);
                break;
            case EventKind.Offside:
                Queue(NearestAssistant(ball), "off_ar_offside");
                Queue(OfficialRole.Referee, "off_ref_whistle", .5f);
                Queue(OfficialRole.Referee, "off_ref_indirect");
                break;
            case EventKind.Goal:
                Queue(OfficialRole.Referee, "off_ref_whistle");
                Queue(OfficialRole.Referee, "off_ref_goal");
                break;
            case EventKind.Corner:
                Queue(NearestAssistant(ball), "off_ar_flag_corner");
                break;
            case EventKind.Out:
                Queue(NearestAssistant(ball), "off_ar_flag_throw");
                break;
            case EventKind.Whistle:
                Queue(OfficialRole.Referee, "off_ref_whistle");
                break;
            case EventKind.Info:
                if (t.StartsWith("Penalty!")) Queue(OfficialRole.Referee, "off_ref_penalty");
                else if (t.StartsWith("Substitution")) Queue(OfficialRole.Fourth, "off_fourth_board");
                else if (t.Contains("advantage", StringComparison.OrdinalIgnoreCase)) Queue(OfficialRole.Referee, "off_ref_advantage");
                break;
        }
    }
}
