// Arena FC - deterministic 3D football simulation. Pure C#: no Godot, no Unity.
// 11v11 / 7v7 / 5v5, AI, ball physics with spin, passing, shooting, tackling,
// goalkeepers, offside, fouls, set pieces, match clock, stats and commentary feed.
using System;
using System.Collections.Generic;
using System.Linq;
using System.Numerics;

namespace ArenaFC.Core;

public enum Phase { Kickoff, Play, Goal, HalfTime, FullTime, ThrowIn, Corner, GoalKick, FreeKick, Penalty, Paused }
public enum EventKind { Info, Pass, Shot, Save, Goal, Tackle, Foul, Offside, Out, Card, Whistle, Corner }

/// <summary>Phase 2.9 gameplay preset (FC 26-style Authentic/Competitive).
/// Authentic = measured tempo, realistic tackle accuracy, weather on.
/// Competitive = faster pace, more forgiving tackles, arcade feel.</summary>
public enum MatchPreset { Authentic, Competitive }

/// <summary>Phase 3.7 quality preset: Low/Med/High + auto-detect.
/// Controls post FX, shadows, crowd density and shader detail.</summary>
public enum QualityPreset { Low, Medium, High, Auto }

public sealed class MatchOptions
{
    public int TeamSize = 11;                 // 5, 7 or 11 per side
    public float HalfMinutes = 45f;          // *game* minutes
    public float TimeSpeed = 15f;            // game seconds per real second
    public int Difficulty = 1;               // 0 easy .. 3 legendary
    public int Seed = 2026;
    public bool Offside = true;
    public bool Fouls = true;
    public int HomeClub = 0;
    public int AwayClub = 1;
    public string HomeFormation = "4-4-2";
    public string AwayFormation = "4-3-3";
    /// <summary>Optional short labels ("ENG", "BRA"). Clubs fall back to Clubs.All.</summary>
    public string HomeLabel = "";
    public string AwayLabel = "";
    /// <summary>Substitutes available per side (0 disables the bench).</summary>
    public int Bench = 7;
    /// <summary>In-match tactics per side (A5).  Balanced defaults keep the
    /// tuned simulation numbers unchanged.</summary>
    public Tactics HomeTactics = new();
    public Tactics AwayTactics = new();
    public List<CharacterSpec>? CustomHome;
    /// <summary>True when a remote human controls the away side (2-player online).</summary>
    public bool AwayHuman;
    public int CameraMode;
    public float CameraZoom = .68f;
    /// <summary>Phase 2.9: gameplay preset.  Scales pace, tackle accuracy,
    /// stamina effect and first-touch quality.</summary>
    public MatchPreset Preset = MatchPreset.Competitive;
    /// <summary>Phase 3.7: quality preset.  Auto-detects from device.</summary>
    public QualityPreset Quality = QualityPreset.Auto;
    /// <summary>Game mode: 0=Kickoff, 1=Tournament, 2=Training, 3=Shootout.</summary>
    public int Mode;
    /// <summary>Phase 3: player switching mode (0=assisted, 1=manual, 2=directional).</summary>
    public int SwitchMode = 0;
    /// <summary>Phase 3: timed finishing enabled.</summary>
    public bool TimedFinishing = true;
    /// <summary>Phase 3: weak foot penalty enabled.</summary>
    public bool WeakFoot = true;
}

public struct PlayerCommand
{
    public Vector2 Move;
    public bool Sprint, Pass, Shoot, Through, Tackle, Switch, Lob;
    /// <summary>Sprint + tackle = committed slide tackle (longer reach, higher foul risk).</summary>
    public bool Slide;
    /// <summary>Hold to shield the ball / use strength to hold off a challenger.</summary>
    public bool Shield;
    /// <summary>Hold for close-control dribbling: quicker touches, tighter ball, more evade.</summary>
    public bool Dribble;
    /// <summary>M10: Skill move trigger (stick gesture detected).</summary>
    public SkillMove Skill;
    /// <summary>Phase 3: Call for ball (trigger teammate run).</summary>
    public bool CallForBall;
    public float Charge;
    public static PlayerCommand None => default;
}

public sealed class MatchEvent
{
    public EventKind Kind;
    public string Text = "";
    public float Clock;
    public int Side;
    public override string ToString() => $"[{Clock:000.0}] {Text}";
}

public sealed class PlayerState
{
    public CharacterSpec Spec = new();
    public int Index, Team, Slot;
    public Role Role;
    public Vector3 Pos, Vel, Facing, Home, Target;
    public float Stamina = 1f, AnimPhase, ActionTimer, DecisionTimer, PossessionLock, TackleLock;
    /// <summary>Restart taker (free kick / throw-in / corner / goal kick) must play
    /// the ball immediately — no dribbling away with it.</summary>
    public bool MustPlayBall;
    public string Action = "idle";
    /// <summary>Phase 0 event sync: total duration of the current one-shot and the
    /// elapsed seconds at which ball contact occurs (ball_contact_frac * duration).
    /// The sim releases/captures the ball at that moment; the animation layer
    /// speeds the clip so visual contact aligns. See BallState pending fields.</summary>
    public float ActionDuration, ActionContactAt;
    public bool ActionReleased = true;
    public bool IsKeeper;
    /// <summary>Actively closing down an opponent who has the ball (extra pace + acceleration).</summary>
    public bool Pressing;
    /// <summary>Holding off a challenger: reduces their tackle success, costs stamina.</summary>
    public bool Shielding;
    /// <summary>Close-control dribbling: ball stays at the feet and is harder to tackle.</summary>
    public bool Dribbling, Sprinting;
    public int Cards;                          // yellow cards shown to this player
    /// <summary>Sent off: stays on the touchline and takes no further part.
    /// Before this existed a booking had no consequence at all - a player could
    /// collect ten yellows and keep playing.</summary>
    public bool SentOff;
    public float MaxSpeed => (3.6f + Spec.Pace * 3.5f) * (IsKeeper ? .94f : 1f);
    // Phase 2.1 first-touch: quality of the current touch (0..1).  Low quality
    // = heavy touch (ball runs away), high = tight control.  Set by
    // TryPossession based on pressure, stamina and skill.
    public float FirstTouchQuality = 1f;
    // Phase 2.2 dribble: touch interval timer, burst cooldown, momentum.
    public float DribbleTouchTimer, DribbleBurstCd, DribbleMomentum;
    // Phase 2.5 defending: jockey state (0=idle, 1=jockeying, 2=contain).
    public int JockeyState;
    // Phase 2.7 off-ball: run type (0=none, 1=overlap, 2=underlap, 3=decoy, 4=third-man).
    public int RunType;
    // M9 shielding: visible body lean/rotation when protecting ball.
    public float ShieldLeanX, ShieldLeanZ, ShieldRotY;
    // M10 skill moves: current skill move and timer.
    public SkillMove CurrentSkill = SkillMove.None;
    public float SkillTimer;
    // A5 tactics: AI modifiers from in-match tactics. 1 = the balanced default;
    // MatchEngine refreshes them from Options.HomeTactics / AwayTactics every tick.
    public float TacticsPressMult = 1f, TacticsRunMult = 1f, TacticsPassMult = 1f;
    public float TacticsWidthMult = 1f;
    // Phase 3: weak foot (0=left, 1=right, 2=both), timed finishing, call for ball.
    public int PreferredFoot = 1;
    public float ShotTimingQuality = 1f; // 0..1, 1 = perfect timing
    public bool CalledForBall;
    public float CallForBallTimer;
    // Phase 7: AI depth — personality, morale, injury.
    public Personality Personality = Personality.Balanced;
    public float Morale = 75f;
    public bool IsInjured;
    public int InjurySeverity;
}

public sealed class BallState
{
    public Vector3 Pos, Vel, Spin, PassTarget;
    public int Owner = -1;
    public int LastTouch = -1, LastTouchSide = -1, PassFrom = -1, PassReceiver = -1;
    public Vector3 LastTouchPos;
    public float FreeTime, NoPickup;
    /// <summary>Phase 0 pending ball action (event-synced release or capture).
    /// Kind 1 = release (pass/shoot wind-up), Kind 2 = capture (first-touch trap).
    /// While HasPending, the ball stays with its current owner (release) or
    /// loose (capture) until the actor's ActionContactAt elapses.</summary>
    public bool HasPending;
    public int PendingKind, PendingFrom = -1;
    public Vector3 PendingVel, PendingSpin, PendingPos, PendingTarget;
    public float PendingNoPickup;
    public int PendingReceiver = -1;
}

public sealed class MatchState
{
    public Phase Phase = Phase.Kickoff;
    public float PhaseTimer, Clock;
    public int Half = 1;
    public int[] Score = new int[2];
    public int[] Shots = new int[2], ShotsOnTarget = new int[2], Passes = new int[2], Fouls = new int[2], Corners = new int[2];
    public int[] YellowCards = new int[2], RedCards = new int[2];
    /// <summary>Stoppage time for the current half, in game seconds. Accrued from
    /// goals, cards, treatments and substitutions - the clock used to stop dead on
    /// 45:00 / 90:00, sometimes mid-attack.</summary>
    public float AddedTime;
    public float[] PossessionTime = new float[2];
    /// <summary>Accumulated expected goals per side - shown full-time and in the HUD.</summary>
    public float[] Xg = new float[2];
    public PlayerState[] Players = Array.Empty<PlayerState>();
    public BallState Ball = new();
    public int Controlled = -1, ControlledAway = -1, KickoffSide = 0, RestartSide = 0, AttackSign = 1;
    /// <summary>Grace period after TAB switching before auto-select may move control again.</summary>
    public float ControlLock;
    public Vector3 RestartPos;
    public string Commentary = "Kick off!";
    public int GoalScorer = -1;
    // Penalty shootout state (Mode == 3).
    public int ShootoutKicksHome, ShootoutKicksAway;
    public int ShootoutTakerSide;
    public bool ShootoutShotTaken;
    public float ShootoutTimer;
    /// <summary>Player taking the current shootout kick.</summary>
    public int ShootoutTaker = -1;
    /// <summary>Kick-by-kick shootout results (true = scored) for the HUD tally.</summary>
    public readonly List<bool> ShootoutHome = new(), ShootoutAway = new();
}

public sealed partial class MatchEngine
{
    public const float Dt = 1f / 60f;
    public readonly MatchOptions Options;
    public readonly MatchState State = new();
    public readonly List<MatchEvent> Events = new();
    public readonly Rng Rng;
    // Phase 7: AI depth
    public readonly AIDepth AI = new();
    private float _acc;
    private float _globalTime;
    private int _tick;
    private readonly (float x, float z, Role role)[] _slots;

    public MatchEngine(MatchOptions? options = null)
    {
        Options = options ?? new MatchOptions();
        Options.TeamSize = new[] { 5, 7, 11 }.Contains(Options.TeamSize) ? Options.TeamSize : 11;
        Rng = new Rng(Options.Seed);
        _slots = Clubs.Slots(Options.TeamSize == 5 ? "1-2-1 (5s)" : Options.TeamSize == 7 ? "2-3-1 (7s)" : Options.HomeFormation, Options.TeamSize);
        var home = Options.CustomHome ?? Clubs.CreateRoster(Options.HomeClub, Options.TeamSize, Options.Seed);
        var away = Clubs.CreateRoster(Options.AwayClub, Options.TeamSize, Options.Seed + 313);
        State.Players = new PlayerState[Options.TeamSize * 2];
        for (int s = 0; s < 2; s++)
        {
            var roster = s == 0 ? home : away;
            for (int i = 0; i < Options.TeamSize; i++)
            {
                var spec = (i < roster.Count ? roster[i] : new CharacterSpec()).Clone();
                spec.Sanitize();
                int idx = s * Options.TeamSize + i;
                State.Players[idx] = new PlayerState
                {
                    Spec = spec, Index = idx, Team = s, Slot = i,
                    Role = i == 0 ? Role.Goalkeeper : _slots[Math.Min(i, _slots.Length - 1)].role,
                    IsKeeper = i == 0, Stamina = 1f, Facing = new Vector3(s == 0 ? 1 : -1, 0, 0),
                    AnimPhase = Gait.InitialPhase(idx),
                };
                if (i == 0) State.Players[idx].Spec.Role = Role.Goalkeeper;
            }
        }
        State.AttackSign = 1;
        // LinkUpPlays: a named combination per adjacent pair, so a carrier has a
        // runner waiting on a pattern instead of every team-mate freelancing.
        for (int side = 0; side < 2; side++)
        {
            for (int i = 1; i + 1 < Options.TeamSize; i++)
            {
                _linkUps.AddPlay(new LinkUpPlay
                {
                    Name = $"link-{side}-{i}",
                    PasserIndex = side * Options.TeamSize + i,
                    RunnerIndex = side * Options.TeamSize + i + 1,
                    Type = i % 2 == 0 ? "overlap" : "third_man",
                    TriggerDistance = 22f,
                });
            }
        }
        ResetPositions(true);
        if (Options.Mode == 3) // Shootout: start with a penalty
        {
            State.ShootoutTakerSide = 0;
            SetupShootoutKick();
            State.Phase = Phase.Penalty;
            State.PhaseTimer = 1.5f;
            Add(EventKind.Info, "Penalty shootout — take your first penalty!");
        }
        else if (Options.Mode == ModeTraining)
        {
            SetupDrill(TrainingDrill.Attack);
            Add(EventKind.Info, "Training ground — follow the coach.");
        }
        else
        {
            State.Phase = Phase.Kickoff;
            State.PhaseTimer = 1.2f;
            Add(EventKind.Info, "Welcome to Arena FC — kick off!");
        }
    }

    public void Add(EventKind kind, string text)
    {
        Events.Add(new MatchEvent { Kind = kind, Text = text, Clock = State.Clock / 60f, Side = State.Ball.LastTouchSide });
        if (Events.Count > 250) Events.RemoveAt(0);
        State.Commentary = text;
    }

    /// <summary>Phase 0: start a one-shot action with event-synced contact.
    /// contactFrac is the clip's ball_contact fraction (see soccer_motions.CLIP_EVENTS).
    /// The ball is released/captured when elapsed time reaches ActionContactAt.</summary>
    private static void SetAction(PlayerState p, string action, float duration, float contactFrac = 0.5f)
    {
        p.Action = action;
        p.ActionTimer = duration;
        p.ActionDuration = duration;
        p.ActionContactAt = duration * Mx.Clamp(contactFrac, 0f, 1f);
        p.ActionReleased = false;
    }

    /// <summary>Fire a pending ball release/capture whose contact time has elapsed.</summary>
    private void FirePending()
    {
        var b = State.Ball;
        if (!b.HasPending || b.PendingFrom < 0 || b.PendingFrom >= State.Players.Length) { b.HasPending = false; return; }
        var actor = State.Players[b.PendingFrom];
        float elapsed = actor.ActionDuration - actor.ActionTimer;
        if (elapsed < actor.ActionContactAt) return;
        if (b.PendingKind == 1)
        {
            // Release: ball leaves the foot now (pass/shoot contact).
            b.Owner = -1;
            b.Vel = b.PendingVel;
            b.Spin = b.PendingSpin;
            b.Pos = b.PendingPos;
            b.FreeTime = 0;
            b.NoPickup = b.PendingNoPickup;
            b.LastTouch = b.PendingFrom;
            b.LastTouchSide = actor.Team;
            b.LastTouchPos = b.Pos;
            b.PassFrom = b.PendingFrom;
            b.PassReceiver = b.PendingReceiver;
            b.PassTarget = b.PendingTarget;
        }
        else if (b.PendingKind == 2)
        {
            // Capture: first touch completes (trap/chest/header).
            b.Owner = b.PendingFrom;
            b.Vel = Vector3.Zero;
            b.Spin = Vector3.Zero;
            b.FreeTime = 0;
            actor.PossessionLock = .12f;
            b.LastTouch = b.PendingFrom;
            b.LastTouchSide = actor.Team;
            b.LastTouchPos = b.Pos;
            if (actor.Team == 0) State.Controlled = b.PendingFrom;
            if (b.PassFrom >= 0 && b.PassReceiver == b.PendingFrom && b.PassFrom / Options.TeamSize == actor.Team)
                b.PassFrom = -1;
        }
        actor.ActionReleased = true;
        b.HasPending = false;
        b.PendingKind = 0;
        b.PendingFrom = -1;
    }

    public int SideSign(int side) => (side == 0 ? 1 : -1) * (State.Half == 1 ? 1 : -1);
    public Vector3 GoalPos(int side) => new(SideSign(side) * Mx.HalfLength, 0, 0); // goal being attacked by side
    public Vector3 OwnGoalPos(int side) => new(-SideSign(side) * Mx.HalfLength, 0, 0);

    public void ResetPositions(bool kickoff)
    {
        State.Ball.Pos = new Vector3(0, Mx.BallRadius, 0);
        State.Ball.Vel = Vector3.Zero;
        State.Ball.Spin = Vector3.Zero;
        State.Ball.Owner = -1;
        State.Ball.HasPending = false; State.Ball.PendingKind = 0; State.Ball.PendingFrom = -1;
        State.Ball.FreeTime = 0;
        State.Ball.NoPickup = 0;
        for (int s = 0; s < 2; s++)
        {
            int sign = SideSign(s);
            var slots = Clubs.Slots(Options.TeamSize == 5 ? "1-2-1 (5s)" : Options.TeamSize == 7 ? "2-3-1 (7s)" : (s == 0 ? Options.HomeFormation : Options.AwayFormation), Options.TeamSize);
            for (int i = 0; i < Options.TeamSize; i++)
            {
                var p = State.Players[s * Options.TeamSize + i];
                var slot = slots[Math.Min(i, slots.Length - 1)];
                p.Home = Clubs.SlotToWorld(slot.x, slot.z, sign);
                p.Pos = p.Home;
                p.Target = p.Home;
                p.Vel = Vector3.Zero;
                p.Facing = Mx.FlatDir(p.Pos, GoalPos(s));
                p.Action = "idle";
                p.DecisionTimer = Rng.Range(0f, .15f);
                if (p.SentOff)
                {
                    p.Pos = TouchlinePos(p);
                    p.Target = p.Pos;
                    p.Vel = Vector3.Zero;
                    p.Action = "sentoff";
                }
            }
        }
        if (kickoff)
        {
            int taker = State.KickoffSide * Options.TeamSize + Math.Min(_slots.Length - 1, Options.TeamSize - 1);
            State.Ball.Owner = taker;
            State.Ball.LastTouch = taker;
            State.Ball.LastTouchSide = State.KickoffSide;
            State.Players[taker].Pos = new Vector3(-SideSign(State.KickoffSide) * .4f, 0, 0);
            int second = State.KickoffSide * Options.TeamSize + Math.Min(Options.TeamSize - 1, 4);
            if (second != taker) State.Players[second].Pos = new Vector3(-SideSign(State.KickoffSide) * 2.4f, 0, 2.2f);
            State.Controlled = FindNearestHome(State.Ball.Pos, true);
            State.ControlledAway = Options.AwayHuman && Options.TeamSize > 1
                ? Options.TeamSize + 1 : -1;
        }
    }

    private int FindNearestHome(Vector3 pos, bool excludeKeeper)
    {
        int best = -1; float bd = float.MaxValue;
        for (int i = 0; i < Options.TeamSize; i++)
        {
            var p = State.Players[i];
            if (excludeKeeper && p.IsKeeper) continue;
            float d = Mx.FlatDist2(p.Pos, pos);
            if (d < bd) { bd = d; best = p.Index; }
        }
        return best;
    }

    /// <summary>Phase 3: Directional switching — find player in stick direction.</summary>
    private int FindDirectionalSwitch(int current, Vector2 aimDir)
    {
        if (aimDir.LengthSquared() < 0.1f)
            return FindNearestHome(State.Ball.Pos, true);
        var from = State.Players[current];
        int best = current;
        float bestScore = -1f;
        for (int i = 0; i < Options.TeamSize; i++)
        {
            var p = State.Players[i];
            if (p.Index == current || p.IsKeeper) continue;
            Vector3 to = p.Pos - from.Pos;
            float dist = to.Length();
            if (dist < 0.5f) continue;
            Vector2 dir2 = Vector2.Normalize(new Vector2(to.X, to.Z));
            float alignment = Vector2.Dot(Vector2.Normalize(aimDir), dir2);
            float score = alignment * 10f - dist * 0.1f;
            if (score > bestScore)
            {
                bestScore = score;
                best = p.Index;
            }
        }
        return best;
    }

    /// <summary>Phase 3: Manual switching — cycle to next player.</summary>
    private int FindNextHome(int current)
    {
        for (int i = 1; i <= Options.TeamSize; i++)
        {
            int idx = (current + i) % Options.TeamSize;
            var p = State.Players[idx];
            if (!p.IsKeeper) return p.Index;
        }
        return current;
    }

    /// <summary>Phase 3: Call for ball — nearest teammate makes a run toward goal.</summary>
    private void CallForBall(int callerIndex)
    {
        var caller = State.Players[callerIndex];
        // Find nearest teammate (not keeper, not caller)
        int best = -1;
        float bd = float.MaxValue;
        for (int i = 0; i < Options.TeamSize; i++)
        {
            var p = State.Players[i];
            if (p.Index == callerIndex || p.IsKeeper) continue;
            float d = Mx.FlatDist(p.Pos, caller.Pos);
            if (d < bd) { bd = d; best = p.Index; }
        }
        if (best >= 0)
        {
            var runner = State.Players[best];
            runner.CalledForBall = true;
            runner.CallForBallTimer = 3f;
            // Set target toward opponent goal
            int attack = SideSign(runner.Team);
            runner.Target = new Vector3(attack * Mx.HalfLength * 0.7f, 0, runner.Pos.Z * 0.5f);
            Add(EventKind.Info, $"{runner.Spec.DisplayName} makes a run!");
        }
    }

    public void Step(float dt, PlayerCommand cmd)
    {
        _acc += Math.Clamp(dt, 0f, .12f);
        bool first = true;
        while (_acc >= Dt)
        {
            Tick(Dt, first ? cmd : PlayerCommand.None);
            _acc -= Dt;
            first = false;
            if (State.Phase == Phase.FullTime) break;
        }
    }

    /// <summary>netCmds is non-null for authoritative/networked ticks: every key is a
    /// human-controlled player with its own command.  Offline play keeps the single
    /// cmd + State.Controlled behaviour unchanged.</summary>
    private void Tick(float dt, PlayerCommand cmd, Dictionary<int, PlayerCommand>? netCmds = null)
    {
        _tick++;
        _globalTime += dt;
        var S = State;
        if (S.Phase == Phase.FullTime || S.Phase == Phase.Paused) return;

        // Training and shootouts have no match clock (it used to run on into
        // half-time and full-time in the middle of a shootout).
        if (!IsTraining && !IsShootout) S.Clock += dt * Options.TimeSpeed;
        if (IsTraining) TrainingTick(dt);
        if (_tick % 30 == 0) Heat.AddPosition(S.Ball.Pos.X, S.Ball.Pos.Z);
        // Phase 7: AI substitutions (tired players after 60')
        int minute = (int)(S.Clock / 60f);
        if (minute >= 60 && _tick % 600 == 0) // check every 10 seconds
        {
            // Only a computer-managed side: home is the user's, away is human when AwayHuman (incl. online).
            if (!Options.AwayHuman && !OnlineLocked && Options.Bench > 0)
            {
                foreach (var p in S.Players)
                {
                    if (p.Team != 1 || p.IsKeeper || p.SentOff || SubsLeft(1) <= 0) continue;
                    if (!AI.ShouldSubstitute(p.Index, p.Stamina, minute)) continue;
                    // Fresh players first: each sub swaps the tired man onto the bench at
                    // the same index, so the next unused bench slot is SubsUsed.
                    int benchIndex = SubsUsed[1];
                    if (benchIndex >= BenchOf(1).Count) break;
                    int slot = p.Index - Options.TeamSize;
                    string outName = p.Spec.DisplayName;
                    if (Substitute(1, slot, benchIndex))
                        AI.RecordSubstitution(p.Index, p.Index, minute, "Tired: " + outName);
                }
            }
        }
        float halfSeconds = Options.HalfMinutes * 60f;
        // Stoppage time: the half runs until the added minutes are used up.
        float halfEnd = halfSeconds + (Options.Mode == 3 ? 0f : S.AddedTime);
        if (S.Phase == Phase.Play && S.Half == 1 && S.Clock >= halfEnd)
        {
            S.Clock = halfEnd;
            S.Phase = Phase.HalfTime;
            S.PhaseTimer = 3.0f;
            Add(EventKind.Whistle, S.AddedTime > 0f
                ? $"Half time! (+{MathF.Round(S.AddedTime / 60f * 10f) / 10f:0.#} min added)"
                : "Half time!");
            S.AddedTime = 0f;
            return;
        }
        if (S.Phase == Phase.Play && S.Half == 2 && S.Clock >= halfSeconds * 2f + (Options.Mode == 3 ? 0f : S.AddedTime))
        {
            S.Clock = halfSeconds * 2f + S.AddedTime;
            S.Phase = Phase.FullTime;
            Add(EventKind.Whistle, $"Full time! {ScoreText()}");
            foreach (var p in S.Players) p.Action = S.Score[p.Team] > S.Score[1 - p.Team] ? "celebrate" : "idle";
            return;
        }

        if (S.Phase != Phase.Play)
        {
            S.PhaseTimer -= dt;
            if (S.PhaseTimer > 0) { AnimateOnly(dt); return; }
            // Training: a goal or the ball going out just resets the drill.
            if (IsTraining) { SetupDrill(Drill); return; }
            switch (S.Phase)
            {
                case Phase.Kickoff:
                    S.Phase = Phase.Play;
                    if (S.Ball.Owner >= 0) KickoffPass(S.Ball.Owner);
                    break;
                case Phase.Goal:
                    if (Options.Mode == 3) { ShootoutNext(true); break; }
                    ResetPositions(true);
                    S.Phase = Phase.Kickoff;
                    S.PhaseTimer = 1.1f;
                    break;
                case Phase.HalfTime:
                    S.Half = 2;
                    S.AddedTime = 0f;
                    S.KickoffSide = 1;
                    ResetPositions(true);
                    S.Phase = Phase.Kickoff;
                    S.PhaseTimer = 1.1f;
                    Add(EventKind.Info, "Second half under way — ends have been switched.");
                    break;
                case Phase.ThrowIn: case Phase.Corner: case Phase.GoalKick: case Phase.FreeKick: case Phase.Penalty:
                    if (Options.Mode == 3 && S.ShootoutShotTaken && S.Phase != Phase.Penalty) { ShootoutNext(false); break; }
                    Restart(S.RestartSide, S.RestartPos, S.Phase == Phase.Penalty);
                    break;
            }
            return;
        }

        // Shootout: a saved or dead penalty counts as a miss.
        if (Options.Mode == 3 && S.ShootoutShotTaken && S.Phase == Phase.Play)
        {
            S.ShootoutTimer += dt;
            var b = S.Ball;
            bool keeperSave = b.Owner >= 0 && S.Players[b.Owner].IsKeeper
                              && S.Players[b.Owner].Team != S.ShootoutTakerSide;
            bool deadBall = (b.Owner < 0 && b.Vel.LengthSquared() < 0.05f && S.ShootoutTimer > 1.5f)
                            || S.ShootoutTimer > 5f; // parried and rolling about: it's a miss
            if (keeperSave || deadBall) ShootoutNext(false);
        }

        // ---- Human control ----
        S.ControlLock = MathF.Max(0f, S.ControlLock - dt);
        if (netCmds == null)
        {
            if (IsShootout) cmd.Switch = false;      // you always take your own kick
            if (cmd.Switch && S.Controlled >= 0 && S.Ball.Owner == S.Controlled)
            {
                // With the ball, LB / Tab asks a team-mate to make a run instead.
                CallForBall(S.Controlled);
                cmd.Switch = false;
            }
            if (cmd.Switch && S.Controlled >= 0)
            {
                // Phase 3: switching modes.
                if (Options.SwitchMode == 2) // Directional: switch in stick direction
                {
                    S.Controlled = FindDirectionalSwitch(S.Controlled, cmd.Move);
                }
                else if (Options.SwitchMode == 1) // Manual: cycle through players
                {
                    S.Controlled = FindNextHome(S.Controlled);
                }
                else // Assisted (default): nearest to ball
                {
                    S.Controlled = FindNearestHome(S.Ball.Pos, true);
                }
                S.ControlLock = 1.2f;                 // respect a manual switch briefly
            }
            // Phase 3: Call for ball — nearest teammate makes a run.
            if (cmd.CallForBall && S.Controlled >= 0)
            {
                CallForBall(S.Controlled);
            }
            // Auto-select: the ring must be on a player who can actually affect the ball.
            // Without this, the controlled player stayed on whoever last touched it while
            // the opposition walked past, so pass/tackle buttons appeared dead.
            if (!IsShootout && S.ControlLock <= 0f && S.Controlled >= 0 && S.Controlled < S.Players.Length)
            {
                int best = S.Ball.Owner >= 0 && S.Players[S.Ball.Owner].Team == 0
                    ? S.Ball.Owner                                    // attacking: control the carrier
                    : FindNearestHome(S.Ball.Pos, true);             // defending/loose: closest outfielder
                if (best >= 0 && best != S.Controlled)
                {
                    float dCur = Mx.FlatDist(S.Players[S.Controlled].Pos, S.Ball.Pos);
                    float dBest = Mx.FlatDist(S.Players[best].Pos, S.Ball.Pos);
                    if (S.Ball.Owner >= 0 && S.Players[S.Ball.Owner].Team == 0) S.Controlled = best;
                    else if (dBest + 1.6f < dCur) S.Controlled = best;   // hysteresis: no flicker
                }
            }
        }
        else
        {
            // Each networked human may request a player switch on its own team.
            foreach (var kv in netCmds)
                if (kv.Value.Switch && kv.Key >= 0 && kv.Key < S.Players.Length)
                {
                    int next = FindNearestForTeam(S.Players[kv.Key].Team, S.Ball.Pos, true);
                    if (next < 0) continue;
                    if (S.Players[kv.Key].Team == 0) S.Controlled = next;
                    else S.ControlledAway = next;
                }
        }
        var humans = new HashSet<int>();
        if (netCmds != null)
        {
            foreach (int idx in netCmds.Keys)
                if (idx >= 0 && idx < S.Players.Length) humans.Add(idx);
        }
        else if (S.Controlled >= 0 && S.Controlled < S.Players.Length
                 && !(IsShootout && S.ShootoutTakerSide == 1)) humans.Add(S.Controlled);

        PlayerCommand For(int idx)
        {
            if (!humans.Contains(idx)) return PlayerCommand.None;
            if (netCmds != null) return netCmds.TryGetValue(idx, out var c) ? c : PlayerCommand.None;
            return cmd;
        }

        // ---- In-match tactics (A5) ----
        // Wire Tactics into the live engine: mentality, pressing, width and tempo
        // scale the AI.  Everything is normalised so the BALANCED default is
        // exactly 1.0 and the tuned regression suite keeps its numbers.
        var hm = Options.HomeTactics.GetModifiers();
        var am = Options.AwayTactics.GetModifiers();

        // ---- Human intent + AI decisions ----
        foreach (var p in S.Players)
        {
            var mod = p.Team == 0 ? hm : am;
            p.TacticsPressMult = mod.pressMultiplier / 0.9f;
            p.TacticsRunMult = mod.runAggression / 0.85f;
            p.TacticsPassMult = mod.passLength / 1.05f;
            p.TacticsWidthMult = mod.widthMultiplier;
            p.DecisionTimer -= dt;
            p.ActionTimer = MathF.Max(0, p.ActionTimer - dt);
            p.PossessionLock = MathF.Max(0, p.PossessionLock - dt);
            p.TackleLock = MathF.Max(0, p.TackleLock - dt);
            // Was never counted down: one skill move per player per match.
            p.SkillTimer = MathF.Max(0, p.SkillTimer - dt);
            if (p.MustPlayBall && S.Ball.Owner != p.Index) p.MustPlayBall = false;
            p.Dribbling = false;
            p.Sprinting = false;
            if (p.SentOff)
            {
                // Off the pitch, frozen on the touchline: no AI, no human input.
                p.Action = "sentoff";
                p.Pressing = false; p.Shielding = false;
                continue;
            }
            if (!IsActive(p)) { HoldStill(p); continue; }
            PlayerCommand pc = For(p.Index);
            bool human = humans.Contains(p.Index);
            // A pad / key press lasts one fixed tick.  It must NOT wait for the
            // 0.08-0.18 s AI decision timer: that used to silently discard most
            // pass / shoot / tackle presses and made the controller look dead.
            if (human) HumanActions(p, pc);
            if (p.DecisionTimer <= 0)
            {
                p.DecisionTimer = Rng.Range(.08f, .18f);
                Decide(p, pc, human);
            }
        }

        // ---- Movement ----
        foreach (var p in S.Players)
        {
            if (p.SentOff || !IsActive(p)) continue;
            MovePlayer(p, dt, For(p.Index), humans.Contains(p.Index));
        }

        // ---- Ball ----
        S.Ball.NoPickup = MathF.Max(0, S.Ball.NoPickup - dt);
        // Phase 0: fire event-synced release/capture at ball_contact time.
        FirePending();
        if (S.Ball.Owner >= 0 && S.Ball.Owner < S.Players.Length)
        {
            var owner = S.Players[S.Ball.Owner];
            // PossessionLock means "this player may not pick the ball up again for a moment"
            // (see TryPossession / AttemptTackle / PassTo / Shoot).  It must NOT release the
            // ball: TryPossession and AttemptTackle both set it when possession is *gained*,
            // so the old `owner.PossessionLock > 0` check dropped the ball on the very next
            // tick and produced an endless "X wins the ball!" scrum with no dribbling,
            // shots or goals.
            if (Mx.FlatDist(owner.Pos, S.Ball.Pos) > 2.2f && !S.Ball.HasPending)
            {
                S.Ball.Owner = -1;
            }
            else
            {
                Vector3 f = Mx.Norm(Mx.Flat(owner.Facing));
                if (f.LengthSquared() < .1f) f = new Vector3(1, 0, 0);
                float bob = MathF.Sin(_globalTime * 13f) * .012f;
                // Phase 0.3 dribble touch interval: lead grows with speed
                // (0.15m close control -> 0.60m sprint) with alternating touches.
                // Sprinting adds a knock-on (ball pushed ahead faster than the runner).
                float planar = Mx.Flat(owner.Vel).Length();
                float speedT = Mx.Clamp(planar / 6f, 0f, 1f);
                float touch = MathF.Sin(owner.AnimPhase * 2f) * (0.03f + speedT * 0.05f);
                float lead = owner.Dribbling
                    ? Mx.Lerp(0.12f, 0.35f, speedT) + touch * 0.6f
                    : Mx.Lerp(0.15f, 0.60f, speedT) + touch;
                if (owner.Sprinting && planar > 4.5f) lead += 0.08f; // knock-on
                Vector3 side = owner.Dribbling
                    ? new Vector3(-f.Z, 0, f.X) * MathF.Sin(owner.AnimPhase) * .14f
                    : Vector3.Zero;
                S.Ball.Pos = owner.Pos + f * lead + side + new Vector3(0, Mx.BallRadius + bob, 0);
                // Knock-on: sprinting pushes the ball slightly ahead of the runner.
                S.Ball.Vel = owner.Sprinting && planar > 4.5f ? owner.Vel * 1.12f : owner.Vel;
                S.Ball.Spin = Vector3.Zero;
                S.Ball.LastTouch = owner.Index;
                S.Ball.LastTouchSide = owner.Team;
                S.Ball.LastTouchPos = S.Ball.Pos;
                S.PossessionTime[owner.Team] += dt;
            }
        }
        if (S.Ball.Owner < 0) BallPhysics(dt);
        // While a first-touch capture is pending, nobody else may steal the ball.
        if (!S.Ball.HasPending) TryPossession(dt);
        ClampAll();
    }

    private void AnimateOnly(float dt)
    {
        foreach (var p in State.Players)
        {
            p.AnimPhase += dt * (p.Action == "run" ? 8f : 2f);
            p.Vel *= .9f;
        }
    }

    private string ScoreText() => $"{ShortFor(0)} {State.Score[0]} - {State.Score[1]} {ShortFor(1)}";

    private void KickoffPass(int from)
    {
        int team = from / Options.TeamSize;
        int mate = FindBestPassTarget(State.Players[from], false);
        if (mate < 0) return;
        PassTo(State.Players[from], State.Players[mate], 10f, false);
    }

    /// <summary>One-shot human actions, evaluated EVERY fixed tick.  Keeping these
    /// inside Decide() meant they were sampled only every 0.08-0.18 s, so a normal
    /// button tap was usually lost.  Continuous states live here too so shield /
    /// dribble do not flicker with the AI decision clock.</summary>
    private void HumanActions(PlayerState p, PlayerCommand cmd)
    {
        var S = State;
        var ball = S.Ball;
        bool owner = ball.Owner == p.Index;
        // Close control must be reachable even if the pad's LT/L3 is awkward:
        // a carrier moving the stick gently is automatically in close control,
        // while an explicit dribble/shield button still forces it at any speed.
        // This is the "safety / protect the ball" behaviour in the target clip.
        float moveMag = MathF.Sqrt(cmd.Move.X * cmd.Move.X + cmd.Move.Y * cmd.Move.Y);
        bool assistedCloseControl = owner && moveMag > .05f && moveMag < .60f && p.Stamina > .12f;
        bool closeControl = cmd.Dribble || cmd.Shield || assistedCloseControl;
        p.Shielding = owner && closeControl && p.Stamina > .12f;
        p.Dribbling = owner && closeControl && p.Stamina > .08f;
        if (owner)
        {
            // M10: Skill moves — stick gesture triggers animation + evade.
            if (cmd.Skill != SkillMove.None && p.SkillTimer <= 0f)
            {
                var nearestOpp = NearestOpponent(p, out float oppDist);
                float chance = SkillMoves.SuccessChance(cmd.Skill, p.Spec.Pace, oppDist);
                if (IsTraining) chance = 1f; // the training ground teaches the input, not the odds
                if (Rng.Next() < chance)
                {
                    p.CurrentSkill = cmd.Skill;
                    p.SkillTimer = SkillMoves.Duration(cmd.Skill);
                    SetAction(p, SkillMoves.ClipName(cmd.Skill), p.SkillTimer, 0.5f);
                    // Evade: burst away from opponent
                    if (nearestOpp != null)
                    {
                        Vector3 away = Mx.Flat(p.Pos - nearestOpp.Pos);
                        p.Vel += Mx.Norm(away) * 2.5f;
                    }
                    Add(EventKind.Info, $"{p.Spec.DisplayName} pulls off a {SkillMoves.DisplayName(cmd.Skill)}!");
                }
                else
                {
                    p.SkillTimer = .35f;
                    Add(EventKind.Info, $"{p.Spec.DisplayName} fluffs the {SkillMoves.DisplayName(cmd.Skill)}.");
                }
                return;
            }
            if (cmd.Shoot) { Shoot(p, MathF.Max(.25f, cmd.Charge)); return; }
            if (cmd.Pass) { int t = FindBestPassTarget(p, false, false, cmd.Move); if (t >= 0) PassTo(p, S.Players[t], 13f, false); return; }
            // Phase 3: Through ball weight — charge affects power (hold longer = heavier through ball).
            if (cmd.Through)
            {
                int t = FindBestPassTarget(p, true, false, cmd.Move);
                if (t >= 0)
                {
                    float throughPower = Mx.Lerp(12f, 22f, MathF.Max(0.2f, cmd.Charge));
                    PassTo(p, S.Players[t], throughPower, true);
                }
                return;
            }
            if (cmd.Lob) { int t = FindBestPassTarget(p, true, true, cmd.Move); if (t >= 0) PassTo(p, S.Players[t], 20f, true, true); return; }
        }
        else
        {
            if (cmd.Slide && p.TackleLock <= 0f) { AttemptSlide(p); return; }
            if (cmd.Tackle && p.TackleLock <= 0f) { AttemptTackle(p, false, cmd.Sprint); return; }
        }
        // First touch: pass / shoot a loose ball before possession is registered.
        if (ball.Owner < 0 && Mx.FlatDist(p.Pos, ball.Pos) < 1.6f && ball.Pos.Y < 1.6f)
        {
            if (cmd.Shoot) { Shoot(p, MathF.Max(.25f, cmd.Charge), true); return; }
            if (cmd.Pass) { int t = FindBestPassTarget(p, false, false, cmd.Move); if (t >= 0) PassTo(p, S.Players[t], 13f, false); return; }
            if (cmd.Through) { int t = FindBestPassTarget(p, true, false, cmd.Move); if (t >= 0) PassTo(p, S.Players[t], 17f, true); return; }
            if (cmd.Lob) { int t = FindBestPassTarget(p, true, true, cmd.Move); if (t >= 0) PassTo(p, S.Players[t], 20f, true, true); return; }
        }
        // Phase 3: Header clearance — defender heads aerial ball.
        if (ball.Pos.Y > 0.8f && ball.Pos.Y < 2.5f && ball.Owner < 0
            && Mx.FlatDist(p.Pos, ball.Pos) < 1.5f && p.TackleLock <= 0f
            && !p.IsKeeper && p.Spec.Defending > 0.5f)
        {
            HeaderClearance(p);
            return;
        }
        // Shoulder charge: sprinting into a carrier without pressing tackle still
        // contests possession, so "use your power to dispossess" has an effect.
        if (cmd.Sprint && !cmd.Tackle && !cmd.Slide && ball.Owner >= 0
            && ball.Owner < S.Players.Length && p.TackleLock <= 0f && p.Stamina > .2f)
        {
            var carrier = S.Players[ball.Owner];
            if (carrier.Team != p.Team && Mx.FlatDist(p.Pos, carrier.Pos) < 1.7f)
                AttemptTackle(p, false, true);
        }
    }

    private void Decide(PlayerState p, PlayerCommand cmd, bool human)
    {
        var S = State;
        var ball = S.Ball;
        int attack = SideSign(p.Team);
        bool ourBall = ball.Owner >= 0 && S.Players[ball.Owner].Team == p.Team;
        Vector3 goal = GoalPos(p.Team);
        bool keeper = p.IsKeeper;

        if (human)
        {
            // Active stick input always wins.  With the stick released we no longer
            // auto-run toward goal / formation, BUT when the opposition has the ball
            // the selected defender still shadows the carrier so the game keeps its
            // defensive pressure instead of leaving one player frozen.
            bool humanDefending = ball.Owner >= 0 && ball.Owner < S.Players.Length
                                  && S.Players[ball.Owner].Team != p.Team;
            if (cmd.Move.LengthSquared() > .01f)
            {
                p.Target = p.Pos + new Vector3(cmd.Move.X, 0, cmd.Move.Y) * 3f;
                p.Pressing = humanDefending;
                if (p.ActionTimer <= 0f) p.Action = "run";
            }
            else if (p.ActionTimer > 0f && (p.Action == "tackle" || p.Action == "slide"))
            {
                // A standing/slide challenge sets a short lunge target in
                // AttemptTackle().  Do not immediately cancel it with an idle
                // target: that made B / RB+B look like it did nothing.
                p.Pressing = true;
            }
            else if (humanDefending && S.ControlLock <= 0f)
            {
                var carrier = S.Players[ball.Owner];
                // A5: Tactics-based pressing — mentality and pressing intensity affect AI.
                float pressDist = 1.1f * p.TacticsPressMult;
                p.Target = carrier.Pos + Mx.FlatDir(carrier.Pos, GoalPos(carrier.Team)) * pressDist;
                p.Pressing = true;
                if (p.ActionTimer <= 0f) p.Action = "run";
            }
            else
            {
                p.Target = p.Pos;
                p.Pressing = false;
                if (p.ActionTimer <= 0f) p.Action = "idle";
            }
            return;
        }
        p.Shielding = false;

        // --- Positional target (AI only) ---
        Vector3 slotPos = FormationPosition(p, attack, ball.Pos);
        if (keeper)
        {
            float gx = OwnGoalPos(p.Team).X;
            // Phase 2.6: angle-cutting — position on the line from ball to
            // goal centre, not just tracking ball Z.  Rush when the ball is
            // close and loose (1v1 positioning).
            Vector3 goalCentre = OwnGoalPos(p.Team);
            Vector3 ballToGoal = Mx.FlatDir(ball.Pos, goalCentre);
            float distToGoal = Mx.FlatDist(ball.Pos, goalCentre);
            // Angle-cut: step toward the ball along the ball->goal line.
            float cutDist = Mx.Clamp((distToGoal - 6f) * .12f, 0f, 2.5f);
            Vector3 cutPos = goalCentre - ballToGoal * cutDist;
            float tx = cutPos.X;
            float tz = Mx.Clamp(ball.Pos.Z * .62f, -Mx.GoalHalfWidth * .92f, Mx.GoalHalfWidth * .92f);
            // Rush: if the ball is loose and close, charge it (1v1).
            bool rush = ball.Owner < 0 && distToGoal < 8f && Mx.FlatDist(p.Pos, ball.Pos) < 6f;
            if (rush)
            {
                p.Target = ball.Pos;
                p.Pressing = true;
            }
            else
            {
                p.Target = new Vector3(tx, 0, tz);
                p.Pressing = false;
            }
            if (p.ActionTimer <= 0f) p.Action = "idle";
            float danger = Mx.FlatDist(ball.Pos, OwnGoalPos(p.Team));
            if (danger < 13f && ball.Owner < 0 && ball.Vel.Length() > 12f && p.ActionTimer <= 0)
            {
                SetAction(p, "dive", .65f, .50f);
                p.Target += Mx.FlatDir(p.Pos, ball.Pos) * 1.6f;
            }
            return;
        }

        if (ball.Owner == p.Index)
        {
            // Dribble toward goal, evade the nearest opponent.
            Vector3 dir = Mx.FlatDir(p.Pos, goal);
            var press = NearestOpponent(p, out float pd);
            if (press != null && pd < 4f)
                dir = Mx.Norm(dir * .75f + Mx.FlatDir(press.Pos, p.Pos) * .55f + new Vector3(0, 0, Mx.Clamp(-press.Pos.Z * .04f, -.5f, .5f)));
            p.Target = p.Pos + dir * 4f;
            p.Action = "run";
            if (!human)
            {
                float distGoal = Mx.FlatDist(p.Pos, goal);
                float shotChance = Mx.Clamp((25f - distGoal) / 25f, 0f, 1f) * .06f * (Options.Difficulty * .35f + 1f);
                if (distGoal < 26f && MathF.Abs(p.Pos.Z) < 22f && Rng.Next() < shotChance)
                { Shoot(p, Rng.Range(.55f, 1f)); return; }
                if ((press != null && pd < 2.1f && Rng.Next() < .20f) || Rng.Next() < .012f)
                {
                    int t = FindBestPassTarget(p, Rng.Next() < .25f);
                    if (t >= 0) { PassTo(p, S.Players[t], 14f, false); return; }
                }
            }
            return;
        }

        // Keep challenges coordinated: one defender engages a loose ball; against
        // a carrier, one engages and two stagger across the passing lanes to contain.
        // The cover defenders jockey instead of all diving into the same scrum.
        bool oppOwns = ball.Owner >= 0 && S.Players[ball.Owner].Team != p.Team;
        int chaser1 = ClosestToBall(p.Team, 0), chaser2 = ClosestToBall(p.Team, 1);
        int chaser3 = oppOwns ? ClosestToBall(p.Team, 2) : -1;
        p.Pressing = false;
        if (ourBall)
        {
            // Phase 2.7: off-ball runs — overlap/underlap/decoy/third-man.
            // Fluid Formations: attack shape differs from defence shape.
            Vector3 carrier = ball.Pos;
            Vector3 support = slotPos + Mx.FlatDir(p.Home, carrier) * 1.6f;
            support.X += attack * 3.5f;
            // Fluid Formations: a link-up pattern can override the role run type.
            _posScratch.Clear();
            foreach (var q in S.Players) _posScratch.Add((q.Pos.X, q.Pos.Z));
            var linkUp = _linkUps.CheckTrigger(ball.Owner, ball.Pos.X, ball.Pos.Z, _posScratch);
            if (linkUp != null && linkUp.RunnerIndex == p.Index)
            {
                p.RunType = RunTypeFor(linkUp.Type);
                p.Target = support + new Vector3(attack * 3f, 0, Mx.Clamp(-carrier.Z * .35f, -10f, 10f));
                p.Action = "run";
                return;
            }
            // Assign run types by role and position.
            if (p.Role == Role.Forward)
            {
                // Overlap: run beyond the carrier toward goal.
                p.RunType = 1;
                p.Target = support + new Vector3(attack * 4f, 0, Mx.Clamp(-carrier.Z * .3f, -8f, 8f));
            }
            else if (p.Role == Role.Defender)
            {
                // Underlap: run inside, behind the carrier.
                p.RunType = 2;
                p.Target = support + new Vector3(attack * 1f, 0, -Mx.Clamp(carrier.Z * .2f, -5f, 5f));
            }
            else if (p.Role == Role.Midfielder)
            {
                // Third-man: run into space behind the play.
                p.RunType = 4;
                p.Target = support + new Vector3(-attack * 2f, 0, 0);
            }
            else
            {
                // Decoy: pull a marker away.
                p.RunType = 3;
                p.Target = support + new Vector3(attack * 2f, 0, Mx.Clamp(carrier.Z * .4f, -10f, 10f));
            }
            p.Action = "run";
        }
        else
        {
            bool isChaser = p.Index == chaser1 || p.Index == chaser2 || p.Index == chaser3;
            if (isChaser)
            {
                if (oppOwns)
                {
                    var carrier = S.Players[ball.Owner];
                    Vector3 goalDir = Mx.FlatDir(carrier.Pos, GoalPos(carrier.Team));
                    // The second and third defenders stay goal-side and jockey
                    // separate lanes instead of diving in alongside the challenger.
                    // Only the first presser (chaser1) commits to the tackle.
                    if (p.Index != chaser1)
                    {
                        p.JockeyState = 1; // jockeying
                        float lane = p.Index == chaser2 ? -1.1f : -2.4f;
                        Vector3 side = new Vector3(0, 0, p.Index == chaser2 ? 2.4f : -2.4f);
                        p.Target = carrier.Pos + goalDir * lane + side;
                        // Contain: stay between carrier and goal.
                        if (Mx.FlatDist(p.Pos, carrier.Pos) < 3f)
                            p.JockeyState = 2; // containing
                        p.Pressing = false;
                    }
                    else
                    {
                        p.JockeyState = 0;
                        // High pressing closes the carrier down; a low block
                        // stands off and invites the pass.
                        float lane = .55f / Mx.Clamp(p.TacticsPressMult, .6f, 1.7f);
                        p.Target = carrier.Pos + goalDir * lane + Mx.Flat(carrier.Vel) * .22f;
                        p.Pressing = true;
                    }
                }
                else
                {
                    Vector3 intercept = ball.Pos + Mx.Flat(ball.Vel) * Mx.Clamp(Mx.FlatDist(p.Pos, ball.Pos) / 14f, 0f, .7f);
                    p.Target = intercept;
                }
                p.Action = "run";
            }
            else
            {
                p.Target = slotPos;
                p.Action = "run";
            }
            if (ball.Owner >= 0)
            {
                var carrier = S.Players[ball.Owner];
                float d = Mx.FlatDist(p.Pos, carrier.Pos);
                float aggression = .38f + Options.Difficulty * .08f + (p.Spec.Defending - .5f) * .12f;
                if (p.Team != carrier.Team && d < 2.2f && p.TackleLock <= 0 && Rng.Next() < aggression)
                    AttemptTackle(p);
            }
        }
        // Goal celebration / foul reaction
        if (p.ActionTimer > 0 && p.Action == "celebrate") p.Target = p.Pos;
    }

    private Vector3 FormationPosition(PlayerState p, int attack, Vector3 ballPos)
    {
        var slots = Clubs.Slots(Options.TeamSize == 5 ? "1-2-1 (5s)" : Options.TeamSize == 7 ? "2-3-1 (7s)"
            : (p.Team == 0 ? Options.HomeFormation : Options.AwayFormation), Options.TeamSize);
        var slot = slots[Math.Min(p.Slot, slots.Length - 1)];
        float shift = Mx.Clamp(ballPos.X / (Mx.HalfLength * 2f), -.5f, .5f) * .30f;
        float zShift = Mx.Clamp(ballPos.Z / Mx.HalfWidth, -1f, 1f) * .10f;
        // Tactics width: stretch or squeeze the block (1.0 = default shape).
        float width = Mx.Clamp(p.TacticsWidthMult, .6f, 1.4f);
        return Clubs.SlotToWorld(slot.x + shift, (slot.z + zShift) * width, attack);
    }

    private PlayerState? NearestOpponent(PlayerState p, out float dist)
    {
        dist = float.MaxValue; PlayerState? best = null;
        foreach (var q in State.Players)
        {
            if (q.Team == p.Team || q.SentOff) continue;
            float d = Mx.FlatDist(p.Pos, q.Pos);
            if (d < dist) { dist = d; best = q; }
        }
        return best;
    }

    private int ClosestToBall(int team, int rank)
    {
        var list = State.Players.Where(p => p.Team == team && !p.IsKeeper && !p.SentOff)
            .OrderBy(p => Mx.FlatDist2(p.Pos, State.Ball.Pos)).ToArray();
        return rank < list.Length ? list[rank].Index : (list.Length > 0 ? list[0].Index : -1);
    }

    private int FindBestPassTarget(PlayerState from, bool through, bool longPass = false, Vector2 aimDir = default)
    {
        int best = -1; float bestScore = float.MinValue;
        int attack = SideSign(from.Team);
        // FIFA/PES-style: bias target toward stick aim direction.
        // If stick is centered, use facing direction. Aim alignment is the
        // dominant factor so passes go where the player points.
        bool hasAim = aimDir.LengthSquared() > 0.15f;
        Vector2 aim = hasAim ? Vector2.Normalize(aimDir) : new Vector2(from.Facing.X, from.Facing.Z);
        foreach (var q in State.Players)
        {
            if (q.Team != from.Team || q.Index == from.Index || q.IsKeeper || q.SentOff) continue;
            float d = Mx.FlatDist(from.Pos, q.Pos);
            if (d < 2.5f || d > 42f) continue;
            if (longPass && d < 12f) continue;
            float forward = (q.Pos.X - from.Pos.X) * attack;
            // Aim alignment: dot product of (teammate direction) with aim.
            // 1.0 = directly where aiming, -1.0 = opposite. Weighted heavily.
            Vector2 toMate = new Vector2(q.Pos.X - from.Pos.X, q.Pos.Z - from.Pos.Z);
            float aimAlign = d > 0.01f ? Vector2.Dot(Vector2.Normalize(toMate), aim) : 0f;
            float openness = NearestOpponent(q, out float od) is null ? 8f : MathF.Min(od, 8f);
            bool laneBlocked = false;
            foreach (var o in State.Players)
            {
                if (o.Team == from.Team) continue;
                float proj = Mx.Clamp(Vector3.Dot(Mx.Flat(o.Pos - from.Pos), Mx.Flat(q.Pos - from.Pos)) / MathF.Max(.01f, d * d), 0f, 1f);
                if (Mx.FlatDist(o.Pos, Mx.Lerp(from.Pos, q.Pos, proj)) < 1.5f && proj > .1f && proj < .9f) { laneBlocked = true; break; }
            }
            // Aim alignment dominates (weight 8.0) so stick direction controls
            // the pass. AI factors (forward/openness) break ties.
            float score = aimAlign * 8.0f + forward * .22f + openness * .55f - d * .10f + (through ? forward * .28f : 0f) - (laneBlocked ? 6f : 0f);
            // A long pass wants a distant, advanced target; a short pass prefers
            // the safe nearby option instead of always hitting the furthest man.
            if (longPass) score += MathF.Min(d, 38f) * .16f + forward * .18f;
            else if (through) score += forward * .10f;
            else
            {
                // A genuine SHORT pass keeps the ball with the nearest safe man.
                // The old scoring still picked an advanced receiver 20+ m away,
                // which made E / pad A feel like an uncontrolled long clearance.
                if (d > 18f) score -= 4f + (d - 18f) * .60f;
                else score += MathF.Max(0f, 12f - d) * .35f;
            }
            if (Options.Offside && IsOffside(q, from)) score -= 30f;
            score += Rng.Range(-1.2f, 1.2f);
            if (score > bestScore) { bestScore = score; best = q.Index; }
        }
        return best;
    }

    private bool IsOffside(PlayerState receiver, PlayerState passer)
    {
        int attack = SideSign(receiver.Team);
        if (receiver.Pos.X * attack <= 0f) return false;
        var defenders = State.Players.Where(p => p.Team != receiver.Team)
            .Select(p => p.Pos.X * attack).OrderByDescending(x => x).ToArray();
        if (defenders.Length < 2) return false;
        float secondLast = defenders[1];
        return receiver.Pos.X * attack > 0f && receiver.Pos.X * attack > secondLast;
    }

    /// <summary>Phase 2.3 pass type: Driven (fast, low), Lofted (high),
    /// Threaded (through ball), Chip (soft, high, short).</summary>
    private enum PassType { Driven, Lofted, Threaded, Chip }

    private void PassTo(PlayerState from, PlayerState to, float power, bool through, bool lob = false)
    {
        var b = State.Ball;
        if (b.Owner != from.Index && b.Owner >= 0) return;
        if (b.HasPending) return;
        from.PossessionLock = .35f;
        from.MustPlayBall = false;
        // Phase 0.1: wind-up, then release at ball_contact (0.5 * 0.34s).
        SetAction(from, "kick", .34f, .50f);
        Vector3 aim = to.Pos + Mx.Flat(to.Vel) * (through ? .55f : .22f);
        if (through) aim += Mx.FlatDir(from.Pos, GoalPos(from.Team)) * 4f;
        Vector3 dir = Mx.FlatDir(b.Pos, aim);
        float skill = from.Spec.Passing;
        float err = (1f - skill) * 2.2f + (through ? .8f : 0f);
        dir = Mx.Norm(dir + new Vector3(Rng.Signed() * err * .12f, 0, Rng.Signed() * err * .12f));
        float dist = Mx.FlatDist(b.Pos, aim);
        // Phase 2.3: pass type by context — driven for short, lofted for long,
        // threaded for through, chip for short lob.
        PassType passType = lob ? PassType.Chip
            : through ? PassType.Threaded
            : dist > 22f ? PassType.Lofted
            : PassType.Driven;
        // Speed from the distance to the target: ground passes arrive with a
        // weight that grows with the requested power; lofted/chipped balls
        // carry ~80% of the distance in the air and run on to the receiver.
        float arrive = Mx.Clamp(power * .4f, 3.5f, 9f);
        float speed = passType switch
        {
            PassType.Lofted => Mx.Clamp(dist * .8f / 1.12f, 10f, 27f),
            PassType.Chip => Mx.Clamp(dist * .8f / .65f, 6f, 20f),
            _ => Mx.Clamp(GroundSpeedFor(dist, arrive), 6f, 27f),
        };
        float loftY = passType switch
        {
            PassType.Driven => .45f,
            PassType.Lofted => 5.5f,
            PassType.Threaded => .9f,
            PassType.Chip => 3.2f,
            _ => .45f,
        };
        // Curve: spin on the ball (Magnus effect in BallPhysics).
        float curve = Rng.Signed() * (passType == PassType.Threaded ? .8f : .4f) * skill;
        b.HasPending = true; b.PendingKind = 1; b.PendingFrom = from.Index;
        b.PendingVel = dir * speed + new Vector3(0, loftY, 0);
        b.PendingSpin = new Vector3(0, curve, 0);
        b.PendingPos = from.Pos + dir * .55f + new Vector3(0, Mx.BallRadius + .03f, 0);
        b.PendingNoPickup = .10f;
        b.PendingReceiver = to.Index; b.PendingTarget = aim;
        State.Passes[from.Team]++;
        string passLabel = passType switch
        {
            PassType.Driven => "drives it",
            PassType.Lofted => "lofts it long",
            PassType.Threaded => "threads it through",
            PassType.Chip => "chips it",
            _ => "passes",
        };
        Add(EventKind.Pass, $"{from.Spec.DisplayName} {passLabel} → {to.Spec.DisplayName}");
        if (Options.Offside && IsOffside(to, from))
        {
            Add(EventKind.Offside, $"Offside! {to.Spec.DisplayName} was in an offside position.");
            AwardFreeKick(1 - from.Team, b.Pos, false);
        }
    }

    /// <summary>Phase 2.4 shot type: Power (full charge), Placement (low
    /// charge, corners), Control (mid, skill-based), Volley (first-time aerial).</summary>
    private enum ShotType { Power, Placement, Control, Volley, Finesse }

    private void Shoot(PlayerState p, float charge, bool volley = false)
    {
        var b = State.Ball;
        if (b.Owner != p.Index && !volley) return;
        if (volley && Mx.FlatDist(p.Pos, b.Pos) > 1.6f) return;
        if (b.HasPending) return;
        p.PossessionLock = .55f;
        p.MustPlayBall = false;
        if (Options.Mode == 3) { State.ShootoutShotTaken = true; State.ShootoutTimer = 0f; }
        // Phase 0.2: volley plays the volley clip; release at ball_contact.
        // Phase 2.4: Dynamic Volley — first-time aerial (eFootball v6.0).
        bool isVolley = volley || (b.Pos.Y > .5f && b.Owner == p.Index);
        SetAction(p, isVolley ? "volley" : "kick", .40f, .50f);
        int attack = SideSign(p.Team);
        Vector3 target = new(GoalPos(p.Team).X, Rng.Range(.4f, 2.0f), Rng.Range(-Mx.GoalHalfWidth * .78f, Mx.GoalHalfWidth * .78f));
        State.Xg[p.Team] += ShotXg(p, target);
        // Phase 2.4: shot type by charge and context.
        // Phase 3: finesse shots (charge 0.5-0.65 = curved placement).
        ShotType shotType = isVolley ? ShotType.Volley
            : charge > .75f ? ShotType.Power
            : charge >= .5f && charge <= .65f ? ShotType.Finesse
            : charge < .35f ? ShotType.Placement
            : ShotType.Control;
        // Phase 3: timed finishing — perfect timing window (charge 0.7-0.85).
        float timingQuality = 1f;
        if (Options.TimedFinishing)
        {
            float timingCenter = 0.775f;
            float timingDist = MathF.Abs(charge - timingCenter);
            timingQuality = timingDist < 0.075f ? 1f : timingDist < 0.15f ? 0.8f : timingDist < 0.25f ? 0.5f : 0.3f;
            p.ShotTimingQuality = timingQuality;
        }
        // Phase 3: weak foot — if shot is on the "wrong" side, accuracy penalty.
        float weakFootPenalty = 1f;
        if (Options.WeakFoot && p.PreferredFoot != 2)
        {
            // Determine foot based on ball position relative to player facing
            float footSide = (target.Z - b.Pos.Z) * MathF.Sign(p.Facing.X);
            int shotFoot = footSide > 0 ? 1 : 0; // 0=left, 1=right
            if (shotFoot != p.PreferredFoot)
                weakFootPenalty = 1.4f; // 40% more error with weak foot
        }
        // Aim for the corners when skill is high (placement) or power (far post).
        float cornerBias = shotType == ShotType.Placement || shotType == ShotType.Finesse ? .9f : .6f;
        target.Z = MathF.Sign(target.Z) * Mx.Lerp(Mx.GoalHalfWidth * .2f, Mx.GoalHalfWidth * .86f, p.Spec.Shooting * cornerBias * Rng.Next());
        Vector3 dir = Mx.FlatDir(b.Pos, target);
        float dist = Mx.FlatDist(b.Pos, target);
        float err = (1f - p.Spec.Shooting) * 3.4f + (isVolley ? 1.2f : 0f) + MathF.Max(0f, dist - 20f) * .08f;
        // Placement/finesse shots are more accurate; power shots less so.
        if (shotType == ShotType.Placement) err *= .6f;
        if (shotType == ShotType.Finesse) err *= .5f;
        if (shotType == ShotType.Power) err *= 1.3f;
        err *= weakFootPenalty;
        err *= (2f - timingQuality); // poor timing = more error
        dir = Mx.Norm(dir + new Vector3(0, 0, Rng.Signed() * err * .16f));
        float power = Mx.Lerp(17f, 31f, charge) * Mx.Lerp(.82f, 1.12f, p.Spec.Shooting);
        if (shotType == ShotType.Placement) power *= .75f;
        if (shotType == ShotType.Finesse) power *= .8f;
        if (shotType == ShotType.Volley) power *= 1.05f;
        power *= (0.7f + timingQuality * 0.3f); // perfect timing = full power
        float loft = Mx.Lerp(.08f, .30f, charge) + (dist > 20f ? .06f : 0f);
        if (shotType == ShotType.Placement) loft *= .5f;
        if (shotType == ShotType.Finesse) loft *= .6f;
        if (shotType == ShotType.Volley) loft = .35f;
        b.HasPending = true; b.PendingKind = 1; b.PendingFrom = p.Index;
        b.PendingVel = dir * power + new Vector3(0, power * loft, 0);
        if (IsOnTarget(b.Pos, b.PendingVel, GoalPos(p.Team))) State.ShotsOnTarget[p.Team]++;
        // Finesse shots have more curve (spin).
        float spinAmount = shotType == ShotType.Finesse ? 3.5f : 1f + p.Spec.Shooting * 2.2f;
        b.PendingSpin = new Vector3(0, Rng.Signed() * spinAmount, 0);
        b.PendingPos = b.Pos + new Vector3(0, .05f, 0);
        b.PendingNoPickup = .22f;
        b.PendingReceiver = -1; b.PendingTarget = target;
        State.Shots[p.Team]++;
        string shotLabel = shotType switch
        {
            ShotType.Power => "smashes it",
            ShotType.Placement => "places it",
            ShotType.Finesse => "curls it",
            ShotType.Control => "shoots",
            ShotType.Volley => "volleys it",
            _ => "shoots",
        };
        // Timed finishing feedback
        if (Options.TimedFinishing)
        {
            string timingLabel = timingQuality >= 1f ? " (perfect timing!)"
                : timingQuality >= 0.8f ? " (good timing)"
                : timingQuality >= 0.5f ? " (early/late)"
                : " (poor timing)";
            shotLabel += timingLabel;
        }
        Add(EventKind.Shot, $"{p.Spec.DisplayName} {shotLabel}!");
    }

    /// <summary>Standing tackle, or a committed slide with more reach and more foul risk.
    /// Phase 2.5: jockey/contain state, timing meter, shoulder vs slide,
    /// less-automatic tackles (eFootball v5.4 lesson).</summary>
    private void AttemptTackle(PlayerState p, bool slide = false, bool powered = false)
    {
        p.TackleLock = slide ? 1.35f : .8f;
        // Shoulder charge when close and powered (strength contest, no slide).
        bool shoulder = powered && !slide && Mx.FlatDist(p.Pos, State.Ball.Pos) < 2f;
        SetAction(p, slide ? "slide" : shoulder ? "shoulder_charge" : "tackle",
                  slide ? .60f : shoulder ? .50f : .45f, .40f);
        var b = State.Ball;
        if (b.Owner < 0) return;
        var carrier = State.Players[b.Owner];
        if (carrier.Team == p.Team) return;
        float d = Mx.FlatDist(p.Pos, carrier.Pos);
        float reach = slide ? 4.6f : shoulder ? 2.8f : 3.6f;
        // A HUMAN challenge button should visibly close the last couple of
        // metres.  AI already has three pressers, so lunging every AI tackle
        // would drag the whole defence into the carrier and re-create the
        // "players bunched together" scrum from the recording.
        bool humanChallenge = p.Index == State.Controlled
                              || (Options.AwayHuman && p.Index == State.ControlledAway);
        if (humanChallenge && d > 2.2f && d < 5.2f)
        {
            Vector3 lungeDir = Mx.FlatDir(p.Pos, carrier.Pos);
            p.Target = carrier.Pos - lungeDir * 1.5f;
            p.Vel += lungeDir * 1.6f;
            p.Pressing = true;
        }
        if (d > reach) return;

        // Phase 2.5: timing meter — tackles are less automatic.  The chance
        // is lower than before; positioning (between) and timing matter more.
        // "Use your power to get between the player and the ball": a defender on the
        // goal side / in front of the carrier wins the strength contest more often,
        // while a shielding carrier makes himself harder to dispossess.
        Vector3 f = Mx.Norm(Mx.Flat(carrier.Facing));
        float contestD = MathF.Max(1f, d - 1.0f);
        float between = Mx.Clamp(Vector3.Dot(Mx.Flat(p.Pos - carrier.Pos), f) / MathF.Max(.4f, contestD), -1f, 1f);
        float strength = (p.Spec.Bulk - 1f) * .35f + p.Spec.Defending * .22f;
        // M9: Full shielding integration — body positioning + strength + stamina.
        float shield = 0f;
        if (carrier.Shielding)
        {
            float oppDist = d;
            int strengthAttr = (int)(carrier.Spec.Bulk * 50f + carrier.Spec.Pace * 30f);
            shield = Shielding.Effectiveness(oppDist, strengthAttr, carrier.Stamina);
            // Visible body lean when shielding (M9)
            var (leanX, leanZ, rotY) = Shielding.GetPose(
                (p.Pos.X - carrier.Pos.X) / Math.Max(0.1f, d),
                (p.Pos.Z - carrier.Pos.Z) / Math.Max(0.1f, d),
                oppDist, strengthAttr);
            carrier.ShieldLeanX = leanX;
            carrier.ShieldLeanZ = leanZ;
            carrier.ShieldRotY = rotY;
        }
        float dribble = carrier.Dribbling ? .16f : 0f;
        // Jockeying (staying goal-side, not diving in) improves the chance.
        float jockeyBonus = p.JockeyState == 2 ? .08f : p.JockeyState == 1 ? .04f : 0f;
        // Preset: Authentic has more realistic (lower) tackle accuracy.
        float presetTackle = Options.Preset == MatchPreset.Authentic ? .88f : 1f;
        float chance = (.42f + p.Spec.Defending * .32f + strength + between * .22f - shield - dribble
                       - carrier.Spec.Pace * .12f - (contestD - 1f) * .10f
                       + (slide ? .14f : 0f) + (powered ? .10f : 0f) + jockeyBonus) * presetTackle;
        // Ball already being struck (pass/shot wind-up): only a well-timed block
        // gets there first. Without this ~1 in 4 AI passes was stolen mid-kick.
        if (b.HasPending && b.PendingKind == 1 && b.PendingFrom == carrier.Index) chance *= .30f;
        chance = Mx.Clamp(chance, .03f, .85f);
        if (Rng.Next() < chance)
        {
            // A successful tackle cancels any wind-up the carrier had started.
            b.HasPending = false; b.PendingKind = 0; b.PendingFrom = -1;
            b.Owner = p.Index;
            p.PossessionLock = .12f;
            carrier.PossessionLock = .45f;
            b.Vel = Vector3.Zero;
            p.JockeyState = 0;
            Add(EventKind.Tackle, $"{p.Spec.DisplayName} wins the ball!");
        }
        else if (Options.Fouls && contestD < (slide ? 2.6f : 1.7f)
                 && Rng.Next() < (slide ? .26f : .10f))
        {
            // Only a genuinely close, failed challenge can be a foul now: previously
            // every miss at 2 m had an ~18% chance of a free kick that looked like
            // nothing happened.  Give the victim a visible stumble too.
            State.Fouls[p.Team]++;
            SetAction(carrier, "foul", 1.1f, .40f);
            carrier.Vel *= .2f;
            float ownGoalX = OwnGoalPos(p.Team).X;
            bool inBox = MathF.Abs(b.Pos.X - ownGoalX) < 16.5f && MathF.Abs(b.Pos.Z) < 20.16f;
            // Disciplinary rules.  Cards used to be a decorative counter that
            // incremented with no consequence whatsoever; now a booking is a
            // booking, a second yellow is a red, and a professional foul that
            // denies a clear run on goal can be a straight red.
            bool denial = IsDenyingGoal(carrier, p);
            // RefereeSystem (G9) had advantage, penalties, cards and injury all
            // implemented and nothing calling it.  Decisions now go through it,
            // so the referee is a single authority instead of four RNG rolls.
            var decision = _referee.DecideFoul(inBox, denial, slide, false, slide ? .82f : .45f);
            bool straightRed = decision == RefereeDecision.RedCard;
            bool booked = !straightRed && decision == RefereeDecision.YellowCard;
            bool injury = decision == RefereeDecision.Injury;
            if (injury)
            {
                // A dangerous tackle that hurts: booking plus treatment time.
                booked = true;
                AddStoppage(25f);
                Add(EventKind.Foul, $"{p.Spec.DisplayName} is hurt in the challenge.");
            }
            if (straightRed)
            {
                AddStoppage(45f);
                Add(EventKind.Foul, $"Foul! {p.Spec.DisplayName} denies a clear chance.");
                SendOff(p, "Straight red card");
            }
            else if (booked)
            {
                AddStoppage(20f);
                p.Cards++;
                State.YellowCards[p.Team]++;
                if (p.Cards >= 2) SendOff(p, "Second yellow card");
                else
                {
                    Add(EventKind.Card, $"Yellow card - {p.Spec.DisplayName} ({ClubShort(p.Team)})");
                    Add(EventKind.Foul, "Foul! Free kick.");
                }
            }
            else Add(EventKind.Foul, "Foul! Free kick.");
            if (inBox && Rng.Next() < .55f) AwardFreeKick(1 - p.Team, new Vector3(-SideSign(p.Team) * (Mx.HalfLength - 11f), 0, 0), true);
            else AwardFreeKick(1 - p.Team, b.Pos, false);
        }
    }

    private void AttemptSlide(PlayerState p) => AttemptTackle(p, true);

    public string ClubShort(int team) =>
        Clubs.All[team == 0 ? Options.HomeClub % Clubs.All.Length : Options.AwayClub % Clubs.All.Length].Short;

    /// <summary>True when the fouled player had a clear run on goal and this
    /// defender was the last one able to stop it (a red-card offence).</summary>
    private bool IsDenyingGoal(PlayerState carrier, PlayerState fouler)
    {
        Vector3 goal = GoalPos(carrier.Team);
        if (Mx.FlatDist(carrier.Pos, goal) > 30f) return false;
        foreach (var q in State.Players)
        {
            if (q.Team != fouler.Team || q.Index == fouler.Index || q.SentOff || q.IsKeeper) continue;
            if (Mx.FlatDist(q.Pos, carrier.Pos) < 5f) return false;   // cover is there
        }
        return true;
    }

    /// <summary>Where a sent-off player waits for the rest of the match.</summary>
    private static Vector3 TouchlinePos(PlayerState p) => new(
        Mx.Clamp(p.Pos.X, -Mx.HalfLength + 6f, Mx.HalfLength - 6f), 0f,
        p.Pos.Z >= 0 ? Mx.HalfWidth + 3.5f : -(Mx.HalfWidth + 3.5f));

    /// <summary>Dismiss a player: he leaves the pitch and takes no further part.
    /// Guards against reducing a side below two players so a small-sided match
    /// can always be restarted.</summary>
    private bool SendOff(PlayerState p, string reason)
    {
        if (p.SentOff) return false;
        int active = 0;
        int start = p.Team * Options.TeamSize;
        for (int i = start; i < start + Options.TeamSize && i < State.Players.Length; i++)
            if (!State.Players[i].SentOff) active++;
        if (active <= 2)
        {
            Add(EventKind.Card, $"{p.Spec.DisplayName} keeps his place - too few players left.");
            return false;
        }
        p.SentOff = true;
        State.RedCards[p.Team]++;
        if (State.Ball.Owner == p.Index) State.Ball.Owner = -1;
        if (State.Ball.HasPending && State.Ball.PendingFrom == p.Index)
        {
            State.Ball.HasPending = false; State.Ball.PendingFrom = -1;
            State.Ball.PendingKind = 0; State.Ball.PendingReceiver = -1;
        }
        p.Pos = TouchlinePos(p);
        p.Target = p.Pos;
        p.Vel = Vector3.Zero;
        p.Action = "sentoff";
        p.ActionTimer = 0f;
        p.MustPlayBall = false;
        p.Pressing = false; p.Shielding = false; p.Dribbling = false; p.Sprinting = false;
        Add(EventKind.Card, $"{reason} - {p.Spec.DisplayName} ({ClubShort(p.Team)}) is off. " +
                            $"{active - 1} players left.");
        if (State.Controlled == p.Index) State.Controlled = FindNearestForTeam(p.Team, State.Ball.Pos, true);
        if (State.ControlledAway == p.Index) State.ControlledAway = FindNearestForTeam(p.Team, State.Ball.Pos, true);
        return true;
    }

    /// <summary>Phase 3: Header clearance — defender heads aerial ball away.</summary>
    private void HeaderClearance(PlayerState p)
    {
        var b = State.Ball;
        if (b.Pos.Y < 0.8f || b.Pos.Y > 2.5f) return; // must be head-height
        if (Mx.FlatDist(p.Pos, b.Pos) > 1.5f) return;
        if (b.HasPending) return;

        p.PossessionLock = 0.4f;
        SetAction(p, "header", 0.5f, 0.5f);

        // Clear toward the wings (away from goal)
        int attack = SideSign(p.Team);
        Vector3 target = new(
            p.Pos.X + attack * 15f, // up the pitch, away from own goal
            0,
            p.Pos.Z > 0 ? -20f : 20f // toward opposite wing
        );
        Vector3 dir = Mx.FlatDir(b.Pos, target);
        float power = 14f + p.Spec.Defending * 6f;
        float loft = 0.25f;

        b.HasPending = true;
        b.PendingKind = 0; // clearance (not a shot)
        b.PendingFrom = p.Index;
        b.PendingVel = dir * power + new Vector3(0, power * loft, 0);
        b.PendingSpin = new Vector3(0, Rng.Signed() * 2f, 0);
        b.PendingPos = b.Pos + new Vector3(0, 0.1f, 0);
        b.PendingNoPickup = 0.3f;
        b.PendingReceiver = -1;
        b.PendingTarget = target;

        Add(EventKind.Info, $"{p.Spec.DisplayName} heads it clear!");
    }

    private void AwardFreeKick(int side, Vector3 pos, bool penalty)
    {
        State.Ball.Owner = -1;
        State.Ball.HasPending = false; State.Ball.PendingKind = 0; State.Ball.PendingFrom = -1;
        State.Ball.Vel = Vector3.Zero;
        State.RestartSide = side;
        State.RestartPos = pos;
        State.Phase = penalty ? Phase.Penalty : Phase.FreeKick;
        State.PhaseTimer = 1.5f;
    }

    private void Restart(int side, Vector3 pos, bool penalty)
    {
        State.Ball.Pos = Mx.Clamp(pos.X, -Mx.HalfLength + 1f, Mx.HalfLength - 1f) * Vector3.UnitX
                        + new Vector3(0, Mx.BallRadius, Mx.Clamp(pos.Z, -Mx.HalfWidth + 1f, Mx.HalfWidth - 1f));
        State.Ball.Vel = Vector3.Zero;
        State.Ball.Spin = Vector3.Zero;
        State.Ball.NoPickup = 0;
        int best = -1; float bd = float.MaxValue;
        if (penalty && Options.Mode == 3)
        {
            // Shootout: the taker chosen by SetupShootoutKick (rotates through the outfield).
            best = State.ShootoutTaker >= 0 ? State.ShootoutTaker : ShootoutTakerFor(side);
        }
        else
        {
            for (int i = 0; i < Options.TeamSize; i++)
            {
                var p = State.Players[side * Options.TeamSize + i];
                if (p.SentOff) continue;
                if (p.IsKeeper && !penalty) continue;
                float d = Mx.FlatDist2(p.Pos, State.Ball.Pos);
                if (d < bd) { bd = d; best = p.Index; }
            }
            if (best < 0)
            {
                best = side * Options.TeamSize;
                for (int i = 0; i < Options.TeamSize; i++)
                {
                    int idx = side * Options.TeamSize + i;
                    if (idx < State.Players.Length && !State.Players[idx].SentOff) { best = idx; break; }
                }
            }
        }
        var taker = State.Players[best];
        State.Ball.Owner = best;
        taker.Pos = State.Ball.Pos - new Vector3(SideSign(side) * .8f, 0, 0);
        taker.PossessionLock = 0;
        // Free kick / throw-in / corner / goal kick: taker must play the ball.
        taker.MustPlayBall = State.Phase == Phase.FreeKick || State.Phase == Phase.ThrowIn
                             || State.Phase == Phase.Corner || State.Phase == Phase.GoalKick;
        taker.Facing = Mx.FlatDir(taker.Pos, GoalPos(side));
        // Phase 2.8: set-piece routines.
        bool isCorner = MathF.Abs(State.Ball.Pos.X) > Mx.HalfLength - 3f && MathF.Abs(State.Ball.Pos.Z) > Mx.HalfWidth - 3f;
        bool isThrowIn = State.Phase == Phase.ThrowIn;
        if (isCorner)
        {
            // Corner routine: near-post and far-post runners.
            int nearPost = -1, farPost = -1;
            foreach (var q in State.Players)
            {
                if (q.Team != side || q.Index == best) continue;
                if (q.Role == Role.Forward && nearPost < 0) nearPost = q.Index;
                else if (q.Role == Role.Defender && farPost < 0) farPost = q.Index;
            }
            if (nearPost >= 0)
            {
                var np = State.Players[nearPost];
                np.Target = new Vector3(GoalPos(side).X - SideSign(side) * 3f, 0, 0);
            }
            if (farPost >= 0)
            {
                var fp = State.Players[farPost];
                fp.Target = new Vector3(GoalPos(side).X - SideSign(side) * 5f, 0, Mx.Clamp(-State.Ball.Pos.Z * .3f, -6f, 6f));
            }
        }
        if (isThrowIn)
        {
            // Throw-in: teammates make runs to receive.
            foreach (var q in State.Players)
            {
                if (q.Team != side || q.Index == best) continue;
                if (q.Role == Role.Midfielder)
                    q.Target = State.Ball.Pos + new Vector3(SideSign(side) * 4f, 0, Mx.Clamp(-State.Ball.Pos.Z * .3f, -8f, 8f));
            }
        }
        // Push opponents away from the set piece.
        foreach (var q in State.Players)
            if (q.Team != side && Mx.FlatDist(q.Pos, State.Ball.Pos) < 4f)
                q.Pos += Mx.FlatDir(State.Ball.Pos, q.Pos) * (4f - Mx.FlatDist(q.Pos, State.Ball.Pos));
        State.Phase = Phase.Play;
        if (penalty)
        {
            // Shootout: the human side takes their own penalties; AI shoots at once.
            if (!(Options.Mode == 3 && side == 0)) Shoot(taker, Options.Mode == 3 ? Rng.Range(.45f, .72f) : .9f);
            else Add(EventKind.Info, "Your penalty — aim and shoot!");
        }
        Add(EventKind.Info, penalty ? "Penalty!" : "Back under way.");
    }

    /// <summary>Penalty shootout: record the kick, check the result, set up the next.</summary>
    private void ShootoutNext(bool scored)
    {
        var S = State;
        int side = S.ShootoutTakerSide;
        if (side == 0) { S.ShootoutKicksHome++; S.ShootoutHome.Add(scored); }
        else { S.ShootoutKicksAway++; S.ShootoutAway.Add(scored); }
        Add(EventKind.Info, scored
            ? $"Penalty scored! {S.Score[0]}-{S.Score[1]}"
            : $"Penalty missed! {S.Score[0]}-{S.Score[1]}");
        int kh = S.ShootoutKicksHome, ka = S.ShootoutKicksAway;
        int sh = S.Score[0], sa = S.Score[1];
        bool decided = ShootoutDecided(kh, ka, sh, sa);
        if (decided)
        {
            S.Phase = Phase.FullTime;
            S.PhaseTimer = 2f;
            Add(EventKind.Info, sh > sa ? "Shootout won! Champions!" : "Shootout lost.");
            return;
        }
        S.ShootoutTakerSide = 1 - side;
        SetupShootoutKick();
        S.Phase = Phase.Penalty;
        S.PhaseTimer = 1.5f;
    }

    private void MovePlayer(PlayerState p, float dt, PlayerCommand cmd, bool human)
    {
        Vector3 wish = Vector3.Zero;
        bool sprint = false;
        if (human && cmd.Move.LengthSquared() > .01f)
        {
            wish = new Vector3(cmd.Move.X, 0, cmd.Move.Y);
            if (wish.LengthSquared() > 1f) wish = Vector3.Normalize(wish);
            sprint = cmd.Sprint;
            p.Target = p.Pos + wish * 3f;
        }
        else
        {
            Vector3 d = Mx.Flat(p.Target - p.Pos);
            if (d.Length() > .35f) wish = Mx.Norm(d);
            // Assisted dribble/positioning keeps the match flowing when the human lets
            // go of the stick; active stick input always overrides p.Target above.
            sprint = !human && (Mx.FlatDist(p.Pos, p.Target) > 5f || p.Pressing) && p.Stamina > .25f;
        }
        // Restart taker must play the ball, not run off with it.
        if (p.MustPlayBall) wish = Vector3.Zero;
        p.Sprinting = sprint;
        float fatigue = Mx.Lerp(.72f, 1f, p.Stamina);
        // Phase 2.9 preset: Authentic is slightly slower, Competitive faster.
        float presetPace = Options.Preset == MatchPreset.Authentic ? .94f : 1.03f;
        float speed = p.MaxSpeed * fatigue * presetPace * (sprint ? 1.42f : 1f) * (p.Pressing ? 1.12f : 1f);
        if (p.Action == "tackle") speed *= 1.35f;
        if (p.Dribbling) speed *= .88f;
        // Phase 0.2: plant feet while trapping/controlling (first touch).
        if (p.ActionTimer > 0f && (p.Action == "trap" || p.Action == "chest_control" || p.Action == "header"))
            speed *= .30f;
        // Phase 2.2: explosive burst (FC-style) — short acceleration spike.
        p.DribbleBurstCd = MathF.Max(0f, p.DribbleBurstCd - dt);
        float burst = 0f;
        if (p.Dribbling && p.DribbleBurstCd <= 0f && sprint && p.Stamina > .4f)
        {
            burst = .35f;
            p.DribbleBurstCd = Rng.Range(1.2f, 2.5f);
            p.Stamina = MathF.Max(.1f, p.Stamina - .06f);
        }
        speed *= (1f + burst);
        Vector3 targetVel = wish * speed;
        // Phase 2.2: momentum-limited turns (eFootball weight) — turning
        // against velocity costs speed; Explosive archetype turns faster.
        float turnCost = 1f;
        if (p.Dribbling && wish.LengthSquared() > .01f)
        {
            Vector3 curDir = Mx.Norm(Mx.Flat(p.Vel));
            Vector3 wishDir = Mx.Norm(wish);
            float dot = Vector3.Dot(curDir, wishDir);
            float archetypeTurn = p.Spec.Archetype == Archetype.Explosive ? .85f
                                : p.Spec.Archetype == Archetype.Lengthy ? 1.1f : 1f;
            turnCost = Mx.Clamp(1f - (1f - dot) * .25f * archetypeTurn, .6f, 1f);
            p.DribbleMomentum = Mx.Lerp(p.DribbleMomentum, dot, dt * 4f);
        }
        float accel = (human ? 18f : p.Pressing ? 16f : 12f) * dt;
        if (sprint) accel *= 1.25f;
        if (p.Dribbling) accel *= 1.35f * turnCost;
        p.Vel = Mx.MoveTowards(p.Vel, targetVel, accel);
        p.Pos += p.Vel * dt;
        p.Pos.Y = 0;
        // Engine badge: a bigger tank, so the same sprints cost less.
        float drain = p.Spec.Badges.Contains(Badge.Engine) ? .7f : 1f;
        if (p.Shielding) p.Stamina = MathF.Max(.08f, p.Stamina - dt * .12f * drain);
        else if (sprint) p.Stamina = MathF.Max(.08f, p.Stamina - dt * .055f * drain);
        else p.Stamina = MathF.Min(1f, p.Stamina + dt * .022f);
        float planar = Mx.Flat(p.Vel).Length();
        if (planar > .15f) p.Facing = Mx.Norm(Mx.Lerp(p.Facing, Mx.Flat(p.Vel), MathF.Min(1f, dt * 7f)));
        else if (State.Ball.Owner == p.Index || p.IsKeeper) p.Facing = Mx.Norm(Mx.Lerp(p.Facing, Mx.FlatDir(p.Pos, GoalPos(p.Team)), MathF.Min(1f, dt * 5f)));
        p.AnimPhase += dt * (2.2f + planar * (p.Sprinting ? 1.9f : 1.5f) + (p.Dribbling ? 3.2f : 0f));
        // Phase 2.2: dribble touch interval — ball stays close, periodic
        // touches keep it glued.  Faster when sprinting, slower when jogging.
        if (p.Dribbling && State.Ball.Owner == p.Index)
        {
            p.DribbleTouchTimer -= dt;
            if (p.DribbleTouchTimer <= 0f)
            {
                p.DribbleTouchTimer = sprint ? .28f : .45f;
                // Small touch: nudge the ball forward (visual only, owner stays).
                Vector3 touchDir = Mx.FlatDir(p.Pos, p.Pos + Mx.Flat(p.Facing) * 2f);
                State.Ball.Pos = p.Pos + touchDir * .35f + new Vector3(0, Mx.BallRadius, 0);
            }
        }
        if (p.ActionTimer <= 0) p.Action = planar > 1.2f ? "run" : "idle";
        // Personal space prevents target convergence from turning into a stack.
        // The coordinated press assignment above leaves more players on shape.
        foreach (var q in State.Players)
        {
            if (q.Index == p.Index) continue;
            Vector3 diff = Mx.Flat(p.Pos - q.Pos);
            float dd = diff.Length();
            if (dd > .001f && dd < 1.2f) p.Pos += Mx.Norm(diff) * (1.2f - dd) * .65f;
        }
        // Only the carrier and the nearest presser should be right on top of the ball.
        // IMPORTANT: only while the ball is OWNED.  Around a loose ball everybody
        // must be allowed to converge, or nobody ever reaches pickup range.
        if (State.Ball.Owner >= 0 && p.Index != State.Ball.Owner && !p.Pressing)
        {
            Vector3 away = Mx.Flat(p.Pos - State.Ball.Pos);
            float bd = away.Length();
            if (bd > .001f && bd < 1.8f) p.Pos += Mx.Norm(away) * (1.8f - bd) * .42f;
        }
        p.Pos.X = Mx.Clamp(p.Pos.X, -Mx.HalfLength - 2.5f, Mx.HalfLength + 2.5f);
        p.Pos.Z = Mx.Clamp(p.Pos.Z, -Mx.HalfWidth - 2.5f, Mx.HalfWidth + 2.5f);
    }

    /// <summary>Speed-proportional rolling drag (1/s) on grass.</summary>
    public const float RollDrag = .30f;
    /// <summary>Constant rolling resistance (m/s²) on grass.</summary>
    public const float RollResistance = 1.0f;

    /// <summary>Launch speed for a ground ball to cover <paramref name="dist"/> metres
    /// and still be travelling at <paramref name="arrive"/> m/s when it gets there,
    /// under the rolling model in <see cref="BallPhysics"/>. Deterministic bisection.</summary>
    public static float GroundSpeedFor(float dist, float arrive)
    {
        const float K = RollDrag, A = RollResistance;
        float lo = arrive, hi = 40f;
        for (int i = 0; i < 24; i++)
        {
            float m = (lo + hi) * .5f;
            float d = (m - arrive) / K - A / (K * K) * MathF.Log((K * m + A) / (K * arrive + A));
            if (d < dist) lo = m; else hi = m;
        }
        return lo;
    }

    private void BallPhysics(float dt)
    {
        var b = State.Ball;
        b.FreeTime += dt;
        Vector3 v = b.Vel;
        v.Y += Mx.Gravity * dt;
        // Magnus effect from spin (side curve + dip).
        v += Vector3.Cross(b.Spin, v) * (.055f * dt);
        // Gap 5: Knuckleball wobble for power shots.
        if (b.Spin.LengthSquared() < 0.1f && v.Length() > 20f)
        {
            v.X += Rng.Signed() * 0.5f * dt;
            v.Z += Rng.Signed() * 0.5f * dt;
        }
        // Ball drag: air resistance proportional to velocity squared.
        // Prevents shots from floating; high-speed balls decelerate faster.
        float speed = v.Length();
        float dragCoeff = 0.0035f; // tuned for realistic shot trajectories
        // G6: Weather effects — rain increases drag, wind adds lateral force.
        if (Weather.Raining) dragCoeff *= 1.5f;
        v -= v * (dragCoeff * speed * dt);
        // Wind: lateral force on airborne ball
        if (b.Pos.Y > Mx.BallRadius + 0.5f)
        {
            v.X += Weather.WindX * dt * 0.5f;
            v.Z += Weather.WindZ * dt * 0.5f;
        }
        // Air drag when airborne; rolling friction when on ground (stops gliding).
        bool airborne = v.Y > 0f || b.Pos.Y > Mx.BallRadius + .05f;
        // Rolling resistance lives in the ground branch below; only air drag here.
        if (airborne) v *= 1f - .045f * dt;
        b.Pos += v * dt;

        if (b.Pos.Y < Mx.BallRadius)
        {
            b.Pos.Y = Mx.BallRadius;
            if (v.Y < 0f) v.Y = -v.Y * .48f;
            if (MathF.Abs(v.Y) < .45f) v.Y = 0f;
            if (v.Y == 0f)
            {
                // Rolling on grass: light speed-proportional drag plus constant
                // rolling resistance, so a 15 m/s pass rolls ~30 m (was ~7 m).
                float flat = MathF.Sqrt(v.X * v.X + v.Z * v.Z);
                float next = MathF.Max(0f, flat * (1f - RollDrag * dt) - RollResistance * dt);
                float k = flat > 1e-4f ? next / flat : 0f;
                v.X *= k; v.Z *= k;
            }
            else
            {
                // Bouncing: each contact scrubs some pace.
                v.X *= MathF.Max(0f, 1f - .55f * dt);
                v.Z *= MathF.Max(0f, 1f - .55f * dt);
            }
            b.Spin *= MathF.Max(0f, 1f - 2f * dt);
        }
        b.Vel = v;

        // --- Posts and crossbar ---
        foreach (int side in new[] { -1, 1 })
        {
            float gx = side * Mx.HalfLength;
            if (MathF.Abs(b.Pos.X - gx) < Mx.BallRadius + .09f)
            {
                foreach (float pz in new[] { -Mx.GoalHalfWidth, Mx.GoalHalfWidth })
                    if (MathF.Abs(b.Pos.Z - pz) < Mx.BallRadius + .09f && b.Pos.Y < Mx.GoalHeight + .1f)
                    {
                        b.Pos.X = gx - side * (Mx.BallRadius + .1f);
                        b.Vel.X *= -.45f; b.Vel.Z += Rng.Signed() * 1.5f;
                        Add(EventKind.Info, "Off the post!");
                    }
                if (MathF.Abs(b.Pos.Y - Mx.GoalHeight) < Mx.BallRadius + .08f && MathF.Abs(b.Pos.Z) < Mx.GoalHalfWidth)
                {
                    b.Pos.X = gx - side * (Mx.BallRadius + .1f);
                    b.Vel.X *= -.4f; b.Vel.Y *= -.5f;
                    Add(EventKind.Info, "Off the crossbar!");
                }
            }
        }

        // --- Goal ---
        if (MathF.Abs(b.Pos.X) > Mx.HalfLength + .02f && MathF.Abs(b.Pos.X) < Mx.HalfLength + 2f
            && MathF.Abs(b.Pos.Z) < Mx.GoalHalfWidth - .05f && b.Pos.Y < Mx.GoalHeight)
        {
            int scoringSide = b.Pos.X > 0 ? 0 : 1; // home attacks +X in first half
            if (State.Half == 2) scoringSide = 1 - scoringSide;
            Goal(scoringSide);
            return;
        }

        // --- Goalkeeper save / parry (Phase 0.5) ---
        // Fast shots are parried (deflected), slow ones are caught. Mirrors the
        // browser keeper_saves() threshold so desktop and web agree.
        foreach (var p in State.Players)
        {
            if (!p.IsKeeper) continue;
            float d = (p.Pos - b.Pos).Length();
            if (d < (p.Action == "dive" ? 1.65f : 1.15f) && b.Pos.Y < 2.5f && b.FreeTime > .1f)
            {
                float spd = b.Vel.Length();
                bool diving = p.Action == "dive";
                if (spd > 18f || (diving && spd > 14f))
                {
                    // Parry: deflect away from goal, ball stays loose.
                    float sign = SideSign(p.Team);
                    b.Vel = new Vector3(-sign * spd * .35f, 3.0f,
                        (b.Pos.Z - p.Pos.Z) * 4.0f + Rng.Signed() * 3f);
                    b.NoPickup = .15f;
                    SetAction(p, "parry", .60f, .50f);
                    Add(EventKind.Save, $"{p.Spec.DisplayName} parries it away!");
                    return;
                }
                b.Owner = p.Index;
                p.PossessionLock = .15f;
                SetAction(p, "catch", .40f, .50f);
                Add(EventKind.Save, $"{p.Spec.DisplayName} makes the save!");
                return;
            }
        }

        // --- Out of play ---
        if (MathF.Abs(b.Pos.Z) > Mx.HalfWidth + .2f)
        {
            int side = b.LastTouchSide >= 0 ? 1 - b.LastTouchSide : 0;
            State.RestartSide = side;
            State.RestartPos = new Vector3(Mx.Clamp(b.Pos.X, -Mx.HalfLength + 2f, Mx.HalfLength - 2f), 0,
                                           MathF.Sign(b.Pos.Z) * (Mx.HalfWidth - .5f));
            State.Phase = Phase.ThrowIn; State.PhaseTimer = 1.1f;
            Add(EventKind.Out, "Throw-in.");
            b.Vel = Vector3.Zero;
            return;
        }
        if (MathF.Abs(b.Pos.X) > Mx.HalfLength + .2f)
        {
            int last = b.LastTouchSide >= 0 ? b.LastTouchSide : 0;
            int defending = b.Pos.X > 0 ? (State.Half == 1 ? 1 : 0) : (State.Half == 1 ? 0 : 1);
            if (last == defending)
            {
                State.Corners[1 - defending]++;
                State.RestartSide = 1 - defending;
                State.RestartPos = new Vector3(MathF.Sign(b.Pos.X) * (Mx.HalfLength - .6f), 0,
                                               MathF.Sign(b.Pos.Z) * (Mx.HalfWidth - .6f));
                State.Phase = Phase.Corner; State.PhaseTimer = 1.3f;
                Add(EventKind.Out, "Corner kick.");
            }
            else
            {
                State.RestartSide = defending;
                State.RestartPos = new Vector3(MathF.Sign(b.Pos.X) * (Mx.HalfLength - 5.5f), 0, 0);
                State.Phase = Phase.GoalKick; State.PhaseTimer = 1.2f;
                Add(EventKind.Out, "Goal kick.");
            }
            b.Vel = Vector3.Zero;
        }
    }

    private void Goal(int side)
    {
        AddStoppage(30f);
        State.Score[side]++;
        State.GoalScorer = State.Ball.LastTouch;
        var scorer = State.GoalScorer >= 0 ? State.Players[State.GoalScorer].Spec.DisplayName : "Own goal";
        Add(EventKind.Goal, $"GOAL! {scorer} — {ScoreText()}");
        State.KickoffSide = 1 - side;
        State.Phase = Phase.Goal;
        State.PhaseTimer = 3.4f;
        State.Ball.Vel = Vector3.Zero;
        State.Ball.HasPending = false; State.Ball.PendingKind = 0; State.Ball.PendingFrom = -1;
        foreach (var p in State.Players)
        {
            SetAction(p, p.Team == side ? "celebrate" : "idle", 2.5f, .50f);
        }
    }

    private void TryPossession(float dt)
    {
        var b = State.Ball;
        if (b.Owner >= 0) { b.FreeTime = 0; return; }
        if (b.FreeTime < .08f || b.NoPickup > 0f || b.Pos.Y > 1.55f) return;
        int best = -1; float bd = 1.05f * 1.05f;
        foreach (var p in State.Players)
        {
            if (!IsActive(p)) continue;
            if (p.PossessionLock > 0f) continue;
            if (b.PassReceiver == p.Index && b.FreeTime < .05f) continue;
            float d = Mx.FlatDist2(p.Pos, b.Pos);
            float radius = p.IsKeeper ? 1.5f : 1.0f;
            if (d < radius * radius && d < bd) { bd = d; best = p.Index; }
        }
        if (best >= 0)
        {
            var p = State.Players[best];
            // Phase 0.2 first touch: aerial/fast balls play a trap/chest/header
            // clip and possession completes at ball_contact. Slow ground balls
            // are collected instantly so the game keeps flowing.
            // Phase 2.1: first-touch quality from pressure, stamina, skill.
            float ballSpeed = b.Vel.Length();
            bool needsTouch = !p.IsKeeper && (b.Pos.Y > 0.35f || ballSpeed > 4f);
            // Pressure: nearest opponent distance (closer = more pressure).
            var nearestOpp = NearestOpponent(p, out float oppDist);
            float pressure = Mx.Clamp(1f - oppDist / 6f, 0f, 1f);
            float staminaFactor = Mx.Clamp(p.Stamina * 1.4f, 0f, 1f);
            float skillFactor = p.Spec.Passing * .5f + p.Spec.Pace * .3f + .2f;
            float presetFactor = Options.Preset == MatchPreset.Authentic ? .92f : 1f;
            // Fatigue: tired players (stamina < 0.3) trap significantly worse.
            float fatiguePenalty = p.Stamina < 0.3f ? (0.3f - p.Stamina) * 1.5f : 0f;
            float quality = Mx.Clamp((skillFactor * .5f + staminaFactor * .3f + (1f - pressure) * .2f) * presetFactor - fatiguePenalty, .10f, 1f);
            p.FirstTouchQuality = quality;
            if (needsTouch)
            {
                string touchAction;
                float contactFrac;
                if (b.Pos.Y > 1.05f)
                {
                    if (b.Vel.Y < -1.5f) { touchAction = "header"; contactFrac = .55f; }
                    else { touchAction = "chest_control"; contactFrac = .55f; }
                }
                else { touchAction = "trap"; contactFrac = .60f; }
                SetAction(p, touchAction, .50f, contactFrac);
                p.Target = b.Pos; // plant feet on the spot
                b.HasPending = true; b.PendingKind = 2; b.PendingFrom = best;
                b.PendingReceiver = b.PassReceiver; b.PendingTarget = b.PassTarget;
                return;
            }
            // Heavy touch (low quality): ball runs away slightly (knock-on).
            if (quality < .45f)
            {
                Vector3 knockDir = Mx.FlatDir(p.Pos, b.Pos);
                b.Vel = knockDir * (1f - quality) * 3.5f;
                b.NoPickup = .12f;
                p.PossessionLock = .25f;
                return;
            }
            b.Owner = best;
            b.Vel = Vector3.Zero;
            b.Spin = Vector3.Zero;
            b.FreeTime = 0;
            p.PossessionLock = .12f;
            b.LastTouch = best; b.LastTouchSide = p.Team; b.LastTouchPos = b.Pos;
            if (p.Team == 0) State.Controlled = best;
            if (b.PassFrom >= 0 && b.PassReceiver == best && b.PassFrom / Options.TeamSize == p.Team)
                b.PassFrom = -1;
        }
    }

    private void ClampAll()
    {
        var b = State.Ball;
        if (!Mx.IsFinite(b.Pos) || !Mx.IsFinite(b.Vel))
        {
            b.Pos = new Vector3(0, Mx.BallRadius, 0); b.Vel = Vector3.Zero; b.Owner = -1;
        }
        b.Pos.X = Mx.Clamp(b.Pos.X, -Mx.HalfLength - 3f, Mx.HalfLength + 3f);
        b.Pos.Z = Mx.Clamp(b.Pos.Z, -Mx.HalfWidth - 3f, Mx.HalfWidth + 3f);
        b.Pos.Y = Mx.Clamp(b.Pos.Y, Mx.BallRadius, 25f);
        foreach (var p in State.Players)
            if (!Mx.IsFinite(p.Pos) || !Mx.IsFinite(p.Vel)) { p.Pos = p.Home; p.Vel = Vector3.Zero; }
    }

    // ---- Read-only helpers for the front end ----
    // ---- Substitutions -------------------------------------------------------
    public const int MaxSubstitutions = 5;
    /// <summary>Bench for each side. Built lazily from the club squads so that
    /// headless tests and the server pay nothing unless a sub is actually made.</summary>
    public readonly List<CharacterSpec>[] Bench = { new(), new() };
    public readonly int[] SubsUsed = new int[2];
    /// <summary>Set by the online client: substitutions are local-only until the
    /// protocol carries them, so they are refused rather than desyncing clients.</summary>
    public bool OnlineLocked;

    public int SubsLeft(int side) => MaxSubstitutions - SubsUsed[side];
    public bool HasBench => Bench[0].Count > 0 || Bench[1].Count > 0;
    public List<CharacterSpec> BenchOf(int side) { EnsureBench(side); return Bench[side]; }

    public void EnsureBench(int side, int count = 7)
    {
        if (Bench[side].Count > 0) return;
        int club = side == 0 ? Options.HomeClub : Options.AwayClub;
        Bench[side].AddRange(Clubs.CreateBench(club, Math.Max(1, count), Options.Seed + side * 31));
    }

    /// <summary>Replace an on-pitch player with a substitute.  The outgoing player
    /// swaps onto the bench, keeps his cards with him, and the incoming player
    /// starts fresh (full stamina, no bookings).</summary>
    public bool Substitute(int side, int slot, int benchIndex)
    {
        if (OnlineLocked) return false;
        if (side is < 0 or > 1) return false;
        if (SubsUsed[side] >= MaxSubstitutions) return false;
        slot = Math.Clamp(slot, 0, Options.TeamSize - 1);
        int index = side * Options.TeamSize + slot;
        if (index < 0 || index >= State.Players.Length) return false;
        var p = State.Players[index];
        if (p.SentOff) return false;
        EnsureBench(side, Math.Max(1, Options.Bench));
        if (benchIndex < 0 || benchIndex >= Bench[side].Count) return false;

        var incoming = Bench[side][benchIndex];
        var outgoing = p.Spec;
        Bench[side][benchIndex] = outgoing;

        p.Spec = incoming;
        p.Stamina = 1f;
        p.Cards = 0;
        p.ActionTimer = 0f;
        p.PossessionLock = 0f;
        p.Action = "idle";
        p.IsInjured = false;
        p.FirstTouchQuality = 1f;
        SubsUsed[side]++;
        AddStoppage(15f);
        if (State.Ball.Owner == index) State.Ball.Owner = -1;
        Add(EventKind.Info, $"Substitution ({ClubShort(side)}): {incoming.DisplayName} on for {outgoing.DisplayName}");
        return true;
    }

    /// <summary>Short label for a side: an explicit tournament label, else the club code.</summary>
    public string ShortFor(int side)
    {
        string label = side == 0 ? Options.HomeLabel : Options.AwayLabel;
        if (!string.IsNullOrWhiteSpace(label)) return label;
        int club = side == 0 ? Options.HomeClub : Options.AwayClub;
        return Clubs.All[Math.Clamp(club, 0, Clubs.All.Length - 1)].Short;
    }

    /// <summary>Territory map of the match, sampled 2x/second from the ball.</summary>
    public HeatMap Heat { get; } = new();
    private readonly ExpectedGoals _xgModel = new();

    /// <summary>xG for one shot, from distance, angle and defensive pressure.</summary>
    private readonly RefereeSystem _referee = new();
    // LinkUpPlays (FluidFormations): named combinations between a carrier and a
    // runner.  Built from the naming order so indices are stable for both sides.
    private readonly LinkUpPlays _linkUps = new();
    private readonly List<(float x, float z)> _posScratch = new();

    private static int RunTypeFor(string type) => type switch
    {
        "overlap" => 1, "underlap" => 2, "decoy" => 3, _ => 4,
    };

    private float ShotXg(PlayerState p, Vector3 target)
    {
        var goal = GoalPos(p.Team);
        var ball = State.Ball.Pos;
        float distance = Mx.FlatDist(ball, goal);
        // Visible goal-mouth angle: the angle between the two posts seen from the ball.
        float dx = MathF.Max(.1f, MathF.Abs(goal.X - ball.X));
        float a1 = MathF.Atan2(Mx.GoalHalfWidth - ball.Z, dx);
        float a2 = MathF.Atan2(-Mx.GoalHalfWidth - ball.Z, dx);
        float goalAngle = MathF.Abs(a1 - a2);
        var nearest = NearestOpponent(p, out float oppDist);
        bool oneOnOne = nearest == null || oppDist > 8f;
        return _xgModel.CalculateXG(distance, goalAngle, oneOnOne);
    }

    /// <summary>Shot on target: would the launched ball cross the goal line inside
    /// the frame (straight line in plan, ballistic in height, ignoring curve/drag)?</summary>
    public static bool IsOnTarget(Vector3 pos, Vector3 vel, Vector3 goal)
    {
        float dx = goal.X - pos.X;
        if (MathF.Abs(vel.X) < .5f || MathF.Sign(vel.X) != MathF.Sign(dx)) return false;
        float t = dx / vel.X;
        float z = pos.Z + vel.Z * t;
        float y = pos.Y + vel.Y * t - .5f * 9.81f * t * t;
        return MathF.Abs(z) < Mx.GoalHalfWidth && y < Mx.GoalHeight;
    }

    /// <summary>Accrue stoppage time for the current half (game seconds).</summary>
    public void AddStoppage(float gameSeconds)
    {
        if (Options.Mode == 3) return;
        State.AddedTime = MathF.Min(State.AddedTime + MathF.Max(0f, gameSeconds), 420f);
    }

    /// <summary>Minutes of added time signalled for the current half (rounded up,
    /// as the fourth official would show it).</summary>
    public int AddedMinutesShown => (int)MathF.Ceiling(State.AddedTime / 60f);

    /// <summary>True once the clock is inside the added time of the half.</summary>
    public bool InStoppageTime
    {
        get
        {
            if (Options.Mode == 3 || State.Phase != Phase.Play) return false;
            float halfSeconds = Options.HalfMinutes * 60f;
            return State.Half == 1
                ? State.Clock >= halfSeconds
                : State.Clock >= halfSeconds * 2f;
        }
    }

    public string ClockString()
    {
        float minutes = State.Clock / 60f;
        int m = (int)minutes;
        int s = (int)((minutes - m) * 60f);
        return $"{m:00}:{s:00}";
    }
    public float PossessionPct(int side)
    {
        float total = State.PossessionTime[0] + State.PossessionTime[1];
        return total < .1f ? 50f : State.PossessionTime[side] / total * 100f;
    }
    public int PlayerWithBall => State.Ball.Owner;
    public bool IsHomeAttackingRight => SideSign(0) > 0;
}
