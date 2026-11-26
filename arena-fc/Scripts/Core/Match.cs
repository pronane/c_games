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
    /// <summary>Kick-off light (presentation only): "day", "dusk" or "night" (floodlit).</summary>
    public string Lighting = "day";
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
    /// <summary>Game mode: 0=Kickoff, 1=Tournament, 2=Training, 3=Shootout, 4=Skill games.</summary>
    public int Mode;
    /// <summary>Which skill game (Mode 4).</summary>
    public SkillGame SkillGame = SkillGame.Shooting;
    /// <summary>Phase 3: player switching mode (0=assisted, 1=manual, 2=directional).</summary>
    public int SwitchMode = 0;
    /// <summary>Phase 3: timed finishing enabled.</summary>
    public bool TimedFinishing = true;
    /// <summary>Phase 3: weak foot penalty enabled.</summary>
    public bool WeakFoot = true;
    /// <summary>Match weather (9.3).  Set on the engine so ball drag/wind and the
    /// rain/snow particles agree; every new match resets it (default Clear).</summary>
    public WeatherType Weather = WeatherType.Clear;
    /// <summary>Wind speed in m/s for Windy/Storm; direction comes from the seed.</summary>
    public float WindSpeed;
}

public struct PlayerCommand
{
    public Vector2 Move;
    public bool Sprint, Pass, Shoot, Through, Tackle, Switch, Lob;
    /// <summary>The shoot button went down this tick (Shoot fires on release, after
    /// charging).  Without the ball it is the FC slide tackle.</summary>
    public bool ShootPress;
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
    /// <summary>Violent conduct (human only): straight red if seen, VAR if not.</summary>
    public bool Punch, Headbutt;
    /// <summary>Shot modifier: finesse (LT+X), chip (LB+X), low driven (double-tap X).</summary>
    public ShotStyle ShotStyle;
    /// <summary>Held without the ball: auto goal-side contain of the carrier (A / E).</summary>
    public bool Contain;
    /// <summary>Right-stick flick without the ball: switch to the team-mate that way.</summary>
    public Vector2 SwitchDir;
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
    /// <summary>Seconds this player has stood over a set piece (human auto-take).</summary>
    public float RestartHold;
    /// <summary>Stick direction / sprint held while a first touch is in progress.</summary>
    public Vector2 TouchDir;
    public bool TouchKnock;
    /// <summary>RestartId at which this player was last cautioned for encroaching.</summary>
    public int EncroachedAt = -1;
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
    /// <summary>2.5: your keeper's dive on the computer's kicks, from the stick held
    /// as the ball is struck (-1 / +1 = world -Z / +Z side, 0 = stay big).</summary>
    public int ShootoutDive;
    /// <summary>Player taking the current shootout kick.</summary>
    public int ShootoutTaker = -1;
    /// <summary>Kick-by-kick shootout results (true = scored) for the HUD tally.</summary>
    public readonly List<bool> ShootoutHome = new(), ShootoutAway = new();
    /// <summary>Set-piece taker being watched for a double touch.</summary>
    public int SetPieceTaker = -1;
    /// <summary>Counts restarts, so an encroacher is cautioned once per restart.</summary>
    public int RestartId;
    public bool SetPieceLeftFoot;
    public float SetPieceTimer;
    /// <summary>Unseen violent conduct waiting for VAR.</summary>
    public int VarOffender = -1, VarVictimTeam = -1;
    public Vector3 VarSpot;
    public float VarTimer;
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
        ArenaFC.Core.Weather.Set(Options.Weather, Options.WindSpeed, (Options.Seed % 628) / 100f);
        _slots = Clubs.Slots(Options.TeamSize == 5 ? "1-2-1 (5s)" : Options.TeamSize == 7 ? "2-3-1 (7s)" : Options.HomeFormation, Options.TeamSize);
        var home = Options.CustomHome ?? Clubs.CreateRoster(Options.HomeClub, Options.TeamSize, Options.Seed);
        var away = Clubs.CreateRoster(Options.AwayClub, Options.TeamSize, Options.Seed + 313);
        // Kit clash (presentation only): the away side changes into its away kit, keepers into one that
        // stands out from both teams.  Colours never feed the simulation.
        away = Clubs.ResolveKitClash(home, away, Options.AwayClub);
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
    private void SetAction(PlayerState p, string action, float duration, float contactFrac = 0.5f, string? intentOverride = null)
    {
        p.Action = action;
        p.ActionTimer = duration;
        p.ActionDuration = duration;
        p.ActionContactAt = duration * Mx.Clamp(contactFrac, 0f, 1f);
        p.ActionReleased = false;
        RecordActionContract(p, action, duration, contactFrac, intentOverride);
    }

    private void RecordActionContract(PlayerState p, string action, float duration, float contactFrac, string? intentOverride = null)
    {
        string intent = intentOverride ?? action switch
        {
            "kick" => "kick",
            "volley" => "shoot",
            "throw_in" => "throw_in",
            "slide" or "shoulder_charge" or "tackle" => "tackle",
            "dive" => "dive",
            _ when action.StartsWith("sc_") => "skill",
            _ => action,
        };
        bool requiresBallContact = intent is "kick" or "shoot" or "pass" or "clear" or "throw_in" or "tackle" or "skill"
            || action is "kick" or "volley" or "throw_in" or "slide" or "tackle";
        LastActionContracts[p.Index] = new ArenaFC.Core.Football.PlayerActionContract
        {
            PlayerIndex = p.Index,
            Intent = intent,
            TargetPosition = p.Target,
            FacingDirection = Mx.FlatDir(p.Pos, State.Ball.Pos),
            BallContactPosition = State.Ball.Pos,
            BallContactTime = duration * Mx.Clamp(contactFrac, 0f, 1f),
            DesiredSpeed = Mx.Flat(p.Vel).Length(),
            SpeedLimit = p.MaxSpeed,
            RequiresBallContact = requiresBallContact,
        };
    }

    private void PopulateBaselineContracts()
    {
        var b = State.Ball;
        for (int i = 0; i < State.Players.Length; i++)
        {
            var p = State.Players[i];
            if (p.SentOff) continue;
            if (LastActionContracts.TryGetValue(i, out var existing))
            {
                // Preserve active action contracts set by SetAction/FirePending.
                if (existing.Intent is "kick" or "shoot" or "pass" or "clear" or "tackle" or "dive" or "skill" or "throw_in" or "intercept" or "dribble" or "catch" or "parry" or "header" or "block")
                    continue;
            }
            if (b.Owner == i)
            {
                LastActionContracts[i] = new ArenaFC.Core.Football.PlayerActionContract
                {
                    PlayerIndex = i,
                    Intent = p.Shielding ? "shield" : "carry",
                    TargetPosition = p.Target,
                    FacingDirection = p.Facing,
                    DesiredSpeed = Mx.Flat(p.Vel).Length(),
                    SpeedLimit = p.MaxSpeed,
                };
            }
            else if (b.Owner < 0 && b.PassReceiver == i)
            {
                float dist = Mx.FlatDist(p.Pos, b.Pos);
                float spd = MathF.Max(1f, Mx.Flat(b.Vel).Length());
                float ttc = Math.Clamp(dist / spd, 0.05f, 2.0f);
                Vector3 recvPos = b.Pos + Mx.Flat(b.Vel) * ttc;
                LastActionContracts[i] = new ArenaFC.Core.Football.PlayerActionContract
                {
                    PlayerIndex = i,
                    Intent = "receive",
                    TargetPosition = recvPos,
                    FacingDirection = Mx.FlatDir(p.Pos, b.Pos),
                    BallContactPosition = recvPos,
                    BallContactTime = ttc,
                    DesiredSpeed = 7.5f,
                    SpeedLimit = p.MaxSpeed,
                    RequiresBallContact = true,
                };
            }
            else
            {
                LastActionContracts.Remove(i);
            }
        }
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
            bool isPass = b.PendingReceiver >= 0;
            if (isPass) State.Passes[actor.Team]++;
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
            if (LastActionContracts.TryGetValue(actor.Index, out var ac))
                ac.Intent = isPass ? "pass" : "shoot";
            if (isPass && b.PendingReceiver < State.Players.Length)
            {
                var recv = State.Players[b.PendingReceiver];
                float dist = Mx.FlatDist(b.Pos, b.PendingTarget);
                float spd = MathF.Max(1f, Mx.Flat(b.Vel).Length());
                LastActionContracts[recv.Index] = new ArenaFC.Core.Football.PlayerActionContract
                {
                    PlayerIndex = recv.Index, Intent = "receive",
                    TargetPosition = b.PendingTarget, FacingDirection = Mx.FlatDir(recv.Pos, b.Pos),
                    BallContactTime = Mx.Clamp(dist / spd, 0.05f, 2.0f),
                    RequiresBallContact = true, DesiredSpeed = 7.5f,
                };
            }
        }
        else if (b.PendingKind == 2)
        {
            // Capture: first touch completes (trap/thigh/chest/header).  A steered
            // touch knocks it into space; otherwise the ball is killed at his feet.
            if (DirectedTouch(actor)) { actor.ActionReleased = true; b.HasPending = false; b.PendingKind = 0; b.PendingFrom = -1; return; }
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
        LastActionContracts.Clear();
        PopulateBaselineContracts();
        var S = State;
        if (S.Phase == Phase.FullTime || S.Phase == Phase.Paused) return;

        // Training and shootouts have no match clock (it used to run on into
        // half-time and full-time in the middle of a shootout).
        if (!IsTraining && !IsShootout && !IsSkill) S.Clock += dt * Options.TimeSpeed;
        if (IsTraining) TrainingTick(dt);
        if (IsSkill) { SkillTick(dt); if (S.Phase == Phase.FullTime) return; }
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
            UpdateVar(dt);                      // VAR reviews at the stoppage
            if (S.PhaseTimer > 0) { AnimateOnly(dt); return; }
            // Training: a goal or the ball going out just resets the drill.
            if (IsTraining) { SetupDrill(Drill); return; }
            if (IsSkill) { SkillNext(); return; }
            switch (S.Phase)
            {
                case Phase.Kickoff:
                    S.Phase = Phase.Play;
                    if (S.Ball.Owner >= 0)
                    {
                        // A human side takes its own kick-off (FC: tap pass); it used to be
                        // played for you the instant the whistle went.  The computer still
                        // kicks off at once; an idle human's is taken for him after 8 s.
                        var ko = S.Players[S.Ball.Owner];
                        bool humanSide = netCmds != null ? netCmds.ContainsKey(ko.Index)
                                                         : ko.Team == 0 ? S.Controlled >= 0 : Options.AwayHuman;
                        if (humanSide)
                        {
                            if (ko.Team == 0 && netCmds == null) { S.Controlled = ko.Index; S.ControlLock = .5f; }
                            ko.MustPlayBall = true;
                            S.RestartPos = S.Ball.Pos;
                        }
                        else KickoffPass(S.Ball.Owner);
                    }
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

        // Shootout, computer's kick: the human keeper picks a side with the stick
        // during the run-up; the kick is struck after ~1.5 s.
        // 7.3: a computer penalty in a match works the same way.
        bool aiShootoutKick = Options.Mode == 3 && !S.ShootoutShotTaken && S.Phase == Phase.Play && S.ShootoutTakerSide == 1
                              && S.ShootoutTaker >= 0 && S.Ball.Owner == S.ShootoutTaker;
        bool aiMatchPenalty = AiPenaltyPending();
        if (aiShootoutKick || aiMatchPenalty)
        {
            if (netCmds == null)
                S.ShootoutDive = MathF.Abs(cmd.Move.Y) > .45f ? MathF.Sign(cmd.Move.Y) : 0;
            S.ShootoutTimer += dt;
            if (S.ShootoutTimer >= 1.5f)
                Shoot(S.Players[aiShootoutKick ? S.ShootoutTaker : S.Ball.Owner], aiShootoutKick ? Rng.Range(.45f, .72f) : Rng.Range(.55f, .85f));
        }
        else if (Options.Mode != 3 && S.ShootoutShotTaken)
        {
            // Match penalty struck: the keeper's dive applies for the next moment only.
            S.ShootoutTimer += dt;
            if (S.ShootoutTimer > 1.5f) S.ShootoutShotTaken = false;
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
            if (cmd.SwitchDir.LengthSquared() > .3f && S.Controlled >= 0 && S.Ball.Owner != S.Controlled && !IsShootout)
            {
                // Right-stick switch: the team-mate in the flicked direction.
                var cur = S.Players[S.Controlled];
                var want = Vector3.Normalize(new Vector3(cmd.SwitchDir.X, 0, cmd.SwitchDir.Y));
                int pick = -1; float bestScore = .35f;
                foreach (var q in S.Players)
                {
                    if (q.Team != cur.Team || q.Index == cur.Index || q.SentOff || q.IsKeeper) continue;
                    Vector3 rel = Mx.Flat(q.Pos - cur.Pos); float rd = rel.Length();
                    if (rd < 1f) continue;
                    float score = Vector3.Dot(rel / rd, want) - rd / 120f;
                    if (score > bestScore) { bestScore = score; pick = q.Index; }
                }
                if (pick >= 0) { S.Controlled = pick; S.ControlLock = 1.2f; }
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
                    // 6.6: while you are steering your defender, only take him off you
                    // when a team-mate is clearly closer (the ring used to hop every
                    // time someone got 1.6 m nearer, ~18 times a minute).
                    bool steering = cmd.Move.LengthSquared() > .09f;
                    float margin = steering ? MathF.Max(4f, dCur * .4f) : 1.6f;
                    if (S.Ball.Owner >= 0 && S.Players[S.Ball.Owner].Team == 0) S.Controlled = best;
                    else if (dBest + margin < dCur)
                    {
                        S.Controlled = best;                                  // hysteresis: no flicker
                        // A deflection can send the ball back the other way at once:
                        // keep the new man for a moment rather than hop straight back.
                        if (steering) S.ControlLock = MathF.Max(S.ControlLock, .7f);
                    }
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
                 && !(IsShootout && S.ShootoutTakerSide == 1) && !AiPenaltyPending()) humans.Add(S.Controlled);

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
            if (p.MustPlayBall && S.Ball.Owner != p.Index) ReleaseSetPiece(p);
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
            // A human who doesn't take a set piece within 8 s has it taken for him;
            // otherwise an idle player stalls the match (opponents must wait 9.15 m off).
            if (p.MustPlayBall && S.Ball.Owner == p.Index) p.RestartHold += dt; else p.RestartHold = 0f;
            if (human && p.MustPlayBall && p.RestartHold > 8f) human = false;
            // A pad / key press lasts one fixed tick.  It must NOT wait for the
            // 0.08-0.18 s AI decision timer: that used to silently discard most
            // pass / shoot / tackle presses and made the controller look dead.
            if (human) HumanActions(p, pc);
            else if (S.Ball.Owner < 0 && AiAttackHighBall(p)) continue;
            // A player mid first-touch is busy controlling the ball: re-deciding
            // used to send the receiver running off while the ball rolled past him
            // (about half of all failed AI passes).
            bool trapping = S.Ball.HasPending && S.Ball.PendingKind == 2 && S.Ball.PendingFrom == p.Index;
            if (p.DecisionTimer <= 0 && !trapping)
            {
                p.DecisionTimer = Rng.Range(.08f, .18f);
                Decide(p, pc, human);
            }
            RespectRestartDistance(p);          // AI targets, and the human's assist target
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
                // A carried ball that crosses a line is released so BallPhysics can rule
                // on it this tick: dribbling into the net used to be no goal, and
                // dribbling over the touchline was never out of play.
                // A keeper holding the ball only takes it over his line if he goes over
                // himself (a catch on the line put the held ball 0.4 m behind it: own goal).
                Vector3 lineCheck = owner.IsKeeper ? owner.Pos : S.Ball.Pos;
                if (!owner.MustPlayBall // a throw-in taker stands behind the line by law
                    && (MathF.Abs(lineCheck.X) > Mx.HalfLength + .02f || MathF.Abs(lineCheck.Z) > Mx.HalfWidth + .2f))
                {
                    S.Ball.Owner = -1;
                    S.Ball.Vel = owner.Vel;
                    S.Ball.FreeTime = 0f;
                    S.Ball.LastTouch = owner.Index;
                    S.Ball.LastTouchSide = owner.Team;
                }
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
        EnforceRestartLaws(dt);
        UpdateVar(dt);
        PopulateBaselineContracts();
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
        if (cmd.Punch || cmd.Headbutt) { ViolentConduct(p, cmd.Headbutt); return; }
        RecordTouchIntent(p, cmd);
        // First-time header / volley: shoot (at goal) or pass as a high ball
        // arrives - also cancels a control touch that had already started.
        if ((cmd.Shoot || cmd.Pass) && State.Ball.Owner != p.Index)
        {
            var bb = State.Ball;
            bool capturing = bb.HasPending && bb.PendingKind == 2 && bb.PendingFrom == p.Index;
            if (capturing) { bb.HasPending = false; bb.PendingKind = 0; bb.PendingFrom = -1; }
            if (capturing || CanStrikeInAir(p))
            {
                if (bb.Pos.Y > .5f || capturing) { FirstTimeStrike(p, cmd.Shoot, MathF.Max(.3f, cmd.Charge), cmd.Move); return; }
            }
        }
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
            if (cmd.Shoot) { Shoot(p, MathF.Max(.25f, cmd.Charge), false, cmd.ShotStyle, cmd.Move); return; }
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
            if (IsCornerKick(p) && (cmd.Lob || cmd.Through)) { CornerDelivery(p, CornerAim(p, cmd.Move)); return; }
            if (cmd.Lob) { int t = FindBestPassTarget(p, true, true, cmd.Move); if (t >= 0) PassTo(p, S.Players[t], 20f, true, true); return; }
        }
        else
        {
            // FC: the shoot button (X / Square) without the ball is a slide tackle,
            // unless the ball is loose at his feet (then it is a first-time strike).
            bool looseNear = ball.Owner < 0 && (Mx.FlatDist(p.Pos, ball.Pos) < 2.2f || ball.PassReceiver == p.Index
                             || (ball.LastTouchSide == p.Team && Mx.FlatDist(p.Pos, ball.Pos) < 10f));   // our ball coming to him
            if (cmd.ShootPress && !looseNear && p.TackleLock <= 0f && !p.IsKeeper) { AttemptSlide(p); return; }
            if (cmd.Slide && p.TackleLock <= 0f) { AttemptSlide(p); return; }
            if (cmd.Tackle && p.TackleLock <= 0f) { AttemptTackle(p, false, cmd.Sprint); return; }
        }
        // First touch: pass / shoot a loose ball before possession is registered.
        if (ball.Owner < 0 && Mx.FlatDist(p.Pos, ball.Pos) < 1.6f && ball.Pos.Y < 1.6f)
        {
            if (cmd.Shoot) { Shoot(p, MathF.Max(.25f, cmd.Charge), true, cmd.ShotStyle, cmd.Move); return; }
            if (cmd.Pass) { int t = FindBestPassTarget(p, false, false, cmd.Move); if (t >= 0) PassTo(p, S.Players[t], 13f, false); return; }
            if (cmd.Through) { int t = FindBestPassTarget(p, true, false, cmd.Move); if (t >= 0) PassTo(p, S.Players[t], 17f, true); return; }
            if (cmd.Lob) { int t = FindBestPassTarget(p, true, true, cmd.Move); if (t >= 0) PassTo(p, S.Players[t], 20f, true, true); return; }
        }
        // Phase 3: Header clearance — defender heads aerial ball.
        if (ball.Pos.Y > 0.8f && ball.Pos.Y < 2.5f && ball.Owner < 0
            && Mx.FlatDist(p.Pos, ball.Pos) < 1.5f && p.TackleLock <= 0f
            && p.PossessionLock <= 0f && ball.NoPickup <= 0f       // not the ball he has just struck
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
        // Jockey: hold LT (X key) without the ball while they have it - face up
        // the carrier, shorter steps, better-timed tackles (was AI-only).
        p.JockeyState = 0;
        if (ball.Owner >= 0 && ball.Owner < S.Players.Length && S.Players[ball.Owner].Team != p.Team
            && (cmd.Dribble || cmd.Shield))
        {
            var c = S.Players[ball.Owner];
            p.JockeyState = Mx.FlatDist(p.Pos, c.Pos) < 3.5f ? 2 : 1;
            p.Facing = Mx.FlatDir(p.Pos, c.Pos);
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
        if (keeper && ball.Owner == p.Index && !p.MustPlayBall)
        {
            // Ball in hand: step out to the edge of his area and distribute.  He used
            // to keep walking back to his line holding it and carry it over (most AI
            // goals were these own goals).
            Vector3 own = OwnGoalPos(p.Team);
            float outX = own.X + MathF.Sign(-own.X) * 9f;
            p.Target = new Vector3(outX, 0, Mx.Clamp(p.Pos.Z, -12f, 12f));
            p.Pressing = false;
            if (p.ActionTimer <= 0f) p.Action = "run";
            if (p.PossessionLock <= 0f && p.ActionTimer <= 0f && Rng.Next() < .09f)
            {
                bool punt = Rng.Next() < .35f;
                int t = FindBestPassTarget(p, false, longPass: punt);
                if (t < 0) t = FindBestPassTarget(p, false);
                if (t >= 0) PassTo(p, S.Players[t], punt ? 24f : 15f, false);
            }
            return;
        }
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
            // Sweeper-keeper: with the ball far away he stands well off his line
            // behind his defence (real keepers sit ~20 m behind the back line).
            if (distToGoal > 25f) cutDist = MathF.Max(cutDist, Mx.Clamp((distToGoal - 25f) * .40f, 0f, 16f));
            Vector3 cutPos = goalCentre - ballToGoal * cutDist;
            float tx = cutPos.X;
            float tz = Mx.Clamp(ball.Pos.Z * .62f, -Mx.GoalHalfWidth * .92f, Mx.GoalHalfWidth * .92f);
            // 2.5: on the computer's shootout kicks the human picks the dive.
            bool humanKeeper = (IsShootout || !Options.AwayHuman) && S.ShootoutTakerSide == 1 && p.Team == 0 && S.ShootoutShotTaken;
            // He goes as the ball is struck, not during the wind-up (the taker reads an
            // early keeper and puts it the other way).
            if (humanKeeper) { tz = S.ShootoutDive * Mx.GoalHalfWidth * .8f; tx = gx + MathF.Sign(-gx) * .4f; }
            // Rush: if the ball is loose and close, charge it (1v1).
            bool rush = ball.Owner < 0 && distToGoal < 8f && Mx.FlatDist(p.Pos, ball.Pos) < 6f;
            if (humanKeeper) rush = false;   // he has committed to the dive you picked
            // 1v1: an opponent carrying the ball in on goal with no defender left
            // between him and the goal.  The keeper comes off his line to narrow the
            // angle and, once close, goes down at the attacker's feet.
            bool oneOnOne = false;
            // A set piece against him (penalty, free kick): he holds his line - at a
            // penalty the Law says so, and nobody rushes a dead ball.
            bool setPieceAgainst = ball.Owner >= 0 && S.Players[ball.Owner].MustPlayBall && S.Players[ball.Owner].Team != p.Team;
            if (setPieceAgainst && distToGoal < 13f)
            {
                tx = gx + MathF.Sign(-gx) * .3f;
                // Set on the line for a penalty (Sprite Forge keeper_penalty_set clip).
                if (AtPenaltySpot(S.RestartPos) && p.ActionTimer <= 0f) SetAction(p, "keeper_penalty_set", .5f, 1f);
            }
            if (!setPieceAgainst && ball.Owner >= 0 && S.Players[ball.Owner].Team != p.Team && distToGoal < 20f
                && MathF.Abs(ball.Pos.Z) < 18f)
            {
                oneOnOne = true;
                foreach (var q in S.Players)
                {
                    if (q.Team != p.Team || q.IsKeeper || q.SentOff) continue;
                    float qd = Mx.FlatDist(q.Pos, goalCentre);
                    if (qd < distToGoal - 1f && Mx.FlatDist(q.Pos, ball.Pos) < distToGoal) { oneOnOne = false; break; }
                }
            }
            if (oneOnOne)
            {
                var carrier1 = S.Players[ball.Owner];
                float outDist = Mx.Clamp((distToGoal - 2.5f) * .72f, 1.5f, 11f);
                p.Target = goalCentre - ballToGoal * outDist;
                p.Pressing = true;
                if (p.ActionTimer <= 0f) p.Action = "run";
                if (Mx.FlatDist(p.Pos, carrier1.Pos) < 1.9f && p.TackleLock <= 0f && p.ActionTimer <= 0f)
                {
                    p.TackleLock = 1.1f;
                    SetAction(p, "dive", .65f, .45f);
                    float smother = Mx.Clamp(.42f + p.Spec.Defending * .25f - carrier1.Spec.Pace * .10f, .25f, .7f);
                    if (Rng.Next() < smother)
                    {
                        ball.HasPending = false; ball.PendingKind = 0; ball.PendingFrom = -1;
                        ball.Owner = p.Index;
                        ball.Vel = Vector3.Zero;
                        p.PossessionLock = .2f;
                        carrier1.PossessionLock = .5f;
                        Add(EventKind.Save, $"{p.Spec.DisplayName} smothers it at {carrier1.Spec.DisplayName}'s feet!");
                    }
                }
                return;
            }
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
            // Shot stopping: read the ball's line and get across to where it will
            // cross his own line, rather than towards where the ball is now.  Shots
            // from 18 m+ went in 36% of the time (real: ~4-6%) because he only moved
            // once the ball was inside 13 m, and then at the ball, not its path.
            if (!humanKeeper && ball.Owner < 0 && TryClaimPoint(p, out Vector3 claim))
            {
                p.Target = claim; p.Pressing = true; p.Action = "run";
                return;
            }
            if (!humanKeeper && ball.Owner < 0 && !ball.HasPending && TryShotCrossing(p, out Vector3 cross, out float tCross))
            {
                p.Target = new Vector3(cross.X, 0, cross.Z);
                float lateral = MathF.Abs(cross.Z - p.Pos.Z);
                if (tCross < .55f && lateral > .6f && (p.ActionTimer <= 0 || p.Action == "keeper_penalty_set"))
                    SetAction(p, "dive", .65f, .50f);
                return;
            }
            if (danger < 13f && ball.Owner < 0 && ball.Vel.Length() > 12f && (p.ActionTimer <= 0 || p.Action == "keeper_penalty_set"))
            {
                SetAction(p, "dive", .65f, .50f);
                p.Target += humanKeeper ? new Vector3(0, 0, S.ShootoutDive * 2.2f) : Mx.FlatDir(p.Pos, ball.Pos) * 1.6f;
            }
            return;
        }

        if (ball.Owner == p.Index)
        {
            // Dribble toward goal, evade the nearest opponent.
            Vector3 dir = Mx.FlatDir(p.Pos, goal);
            // A wide player in the opposition half goes down the line to cross
            // rather than cutting straight for goal (carriers spent 0.5% of their
            // time in the crossing zone, so there were ~3 crosses a match, real ~35).
            if (!human && MathF.Abs(p.Pos.Z) > Mx.HalfWidth * .42f && p.Pos.X * attack > -5f
                && MathF.Abs(goal.X - p.Pos.X) > 9f)
                dir = Mx.Norm(new Vector3(attack, 0, -MathF.Sign(p.Pos.Z) * .10f));
            var press = NearestOpponent(p, out float pd);
            if (press != null && pd < 4f)
                dir = Mx.Norm(dir * .75f + Mx.FlatDir(press.Pos, p.Pos) * .55f + new Vector3(0, 0, Mx.Clamp(-press.Pos.Z * .04f, -.5f, .5f)));
            if (p.MustPlayBall)
            {
                p.Target = p.Pos;
                if (p.ActionTimer <= 0f) p.Action = "idle";
            }
            else
            {
                p.Target = p.Pos + dir * 4f;
                if (p.ActionTimer <= 0f) p.Action = "run";
            }
            if (!human)
            {
                // Set piece: play it.  A direct free kick in range is a shot; anything
                // else is a pass (long balls allowed), taken within about a second.
                if (p.MustPlayBall)
                {
                    // The shootout (and a computer penalty against you) strikes the kick after the run-up.
                    if (IsShootout || (p.Team == 1 && !Options.AwayHuman && AtPenaltySpot(S.RestartPos))) return;
                    float dg = Mx.FlatDist(p.Pos, goal);
                    bool throwIn = IsThrowInHold(p);
                    // 7.2: a corner is delivered into the box (near post, penalty spot,
                    // far post) or, now and then, played short.
                    if (IsCornerKick(p) && p.RestartHold > .8f && Rng.Next() < .2f)
                    {
                        if (Rng.Next() < .22f)
                        {
                            PlayerState? sh = null; float sd = 14f;
                            foreach (var q in S.Players)
                                if (q.Team == p.Team && q.Index != p.Index && !q.IsKeeper && !q.SentOff && Mx.FlatDist(q.Pos, p.Pos) < sd)
                                { sd = Mx.FlatDist(q.Pos, p.Pos); sh = q; }
                            if (sh != null) { PassTo(p, sh, 10f, false); return; }
                        }
                        float pick = Rng.Next();
                        CornerDelivery(p, pick < .4f ? -1f : pick < .7f ? 0f : 1f);
                        return;
                    }
                    if (IsCornerKick(p)) return;
                    if (!throwIn && dg < 28f && MathF.Abs(p.Pos.Z) < 18f && XgFrom(p.Pos, p.Team, false) > .03f && Rng.Next() < .5f)
                    { Shoot(p, Rng.Range(.62f, .9f)); return; }
                    if (Rng.Next() < .14f)
                    {
                        int t = FindBestPassTarget(p, false, longPass: !throwIn && Rng.Next() < .35f);
                        if (t < 0) t = FindBestPassTarget(p, false);
                        if (t >= 0 && (!throwIn || Mx.FlatDist(p.Pos, S.Players[t].Pos) < 25f))
                        { PassTo(p, S.Players[t], throwIn ? 11f : 14f, false); return; }
                    }
                    // Nobody in range after a few seconds (5-a-side, everyone upfield):
                    // play it to the nearest team-mate rather than stand there forever.
                    if (p.RestartHold > 3f)
                    {
                        PlayerState? near = null; float nd = float.MaxValue;
                        foreach (var q in S.Players)
                        {
                            if (q.Team != p.Team || q.Index == p.Index || q.SentOff) continue;
                            float qd = Mx.FlatDist(p.Pos, q.Pos);
                            if (qd < nd) { nd = qd; near = q; }
                        }
                        if (near != null) { PassTo(p, near, throwIn ? 11f : 14f, false); return; }
                    }
                    return;
                }
                // Wide in the final third with a team-mate in the box: cross it.
                if (AiCross(p)) return;
                // Shoot when the chance is good: xG of this position, a lower bar under
                // pressure, and the odd speculative long shot.  The old rule (2% per
                // decision inside 26 m) produced ~2 shots a match.
                float distGoal = Mx.FlatDist(p.Pos, goal);
                bool pressed = press != null && pd < 2.6f;
                float xgHere = XgFrom(p.Pos, p.Team, press == null || pd > 8f);
                // Real teams shoot at ~0.10 xG on average and take plenty of
                // 0.03-0.06 chances; the old bar (0.085 / 0.055) left 3.7 shots
                // from ~12 final-third entries a match.
                // (bars lowered again once keepers stopped parrying every shot back
                // into play: rebounds had been half the shots - real teams take ~12 a match)
                float bar = (pressed ? .028f : .042f) / (1f + Options.Difficulty * .08f);
                bool chance = distGoal < 32f && xgHere > bar && Rng.Next() < .45f;
                bool speculative = distGoal < 30f && xgHere > .02f && Rng.Next() < .06f;
                if (chance || speculative)
                {
                    float power = distGoal < 12f ? Rng.Range(.42f, .72f) : Rng.Range(.58f, .92f);
                    Shoot(p, power);
                    return;
                }
                // Carriers with open grass ahead run with it; closed down at 2-9 m they move
                // it on after a couple of touches (real median ~2 s on the ball).
                float passRate = press == null || pd > 9f ? .012f : pd < 2.1f ? .20f : pd < 5f ? .07f : .03f;
                if (Rng.Next() < passRate)
                {
                    int t = FindBestPassTarget(p, Rng.Next() < .25f);
                    // A defender closed down near his own goal with no clean ball on
                    // gets rid of it: long and towards the touchline.
                    if (Mx.FlatDist(p.Pos, OwnGoalPos(p.Team)) < 40f && press != null && pd < 2.8f
                        && (t < 0 || LastPassTargetBlocked || Mx.FlatDist(p.Pos, OwnGoalPos(p.Team)) < 20f) && Rng.Next() < .75f)
                    {
                        GroundClearance(p);
                        return;
                    }
                    // No clean lane: keep it (dribble, shield) unless closed down hard.
                    bool forced = press != null && pd < 1.4f;
                    if (t >= 0 && (!LastPassTargetBlocked || (forced && Rng.Next() < .5f))) { PassTo(p, S.Players[t], 14f, false); return; }
                }
            }
            return;
        }

        // Keep challenges coordinated: one defender engages a loose ball; against
        // a carrier, one engages and two stagger across the passing lanes to contain.
        // The cover defenders jockey instead of all diving into the same scrum.
        bool oppOwns = ball.Owner >= 0 && S.Players[ball.Owner].Team != p.Team;
        int chaser1 = PrimaryChaser(p.Team, 0), chaser2 = PrimaryChaser(p.Team, 1);
        int chaser3 = oppOwns ? PrimaryChaser(p.Team, 2) : -1;
        // Their pass in flight: one man goes for the interception, the rest hold shape
        // (the passing side still sends two, so a team-mate can tidy up a loose one).
        if (!oppOwns && PossessionTeam() >= 0 && PossessionTeam() != p.Team) chaser2 = -1;
        p.Pressing = false;
        // The intended receiver of a pass in flight comes to meet it.
        if (ball.Owner < 0 && ball.PassReceiver == p.Index && PossessionTeam() == p.Team)
        {
            p.Target = BallFocus();
            if (p.ActionTimer <= 0f) p.Action = "run";
            return;
        }
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
                if (p.ActionTimer <= 0f) p.Action = "run";
                return;
            }
            // Ball wide in the final third: attack the box (near post, far post,
            // penalty spot) so a cross has someone to find.  The three most advanced
            // forwards / midfielders go; the rest support as usual.
            var cpl = S.Players[ball.Owner];
            Vector3 aGoal = GoalPos(p.Team);
            if ((p.Role == Role.Forward || p.Role == Role.Midfielder) && p.Index != ball.Owner
                && MathF.Abs(cpl.Pos.Z) > Mx.HalfWidth * .35f && Mx.FlatDist(cpl.Pos, aGoal) < 46f)
            {
                float myD = Mx.FlatDist(p.Pos, aGoal); int rank = 0;
                foreach (var q in S.Players)
                    if (q.Team == p.Team && q.Index != p.Index && q.Index != ball.Owner && !q.SentOff
                        && (q.Role == Role.Forward || q.Role == Role.Midfielder) && Mx.FlatDist(q.Pos, aGoal) < myD) rank++;
                if (rank < 3)
                {
                    float near = MathF.Sign(cpl.Pos.Z);
                    Vector3 spot = rank switch
                    {
                        0 => aGoal + new Vector3(-attack * 6f, 0, near * 2.5f),      // near post
                        1 => aGoal + new Vector3(-attack * 8f, 0, -near * 3.5f),     // far post
                        _ => aGoal + new Vector3(-attack * 12f, 0, 0f),              // penalty spot
                    };
                    p.RunType = 5;          // attacking the box
                    p.Target = spot;
                    if (p.ActionTimer <= 0f) p.Action = "run";
                    return;
                }
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
            if (!IsSkill)
            {
                var tacOff = GetTacticalAssignment(p.Index);
                if (tacOff != null && (tacOff.Role == "support" || tacOff.Role == "recycle"))
                    p.Target = Mx.Lerp(p.Target, tacOff.MovementTarget, 0.22f);
            }
            if (p.ActionTimer <= 0f) p.Action = "run";
        }
        else
        {
            var tacAssign = GetTacticalAssignment(p.Index);
            bool isPresser = tacAssign?.Role == "press";
            bool isCoverRole = tacAssign?.Role == "cover";
            bool isChaser = isPresser || isCoverRole || (tacAssign == null && (p.Index == chaser1 || p.Index == chaser2 || p.Index == chaser3));
            if (isChaser)
            {
                if (oppOwns)
                {
                    var carrier = S.Players[ball.Owner];
                    Vector3 goalDir = Mx.FlatDir(carrier.Pos, GoalPos(carrier.Team));
                    // M3: coordinator is authoritative for primary presser/cover.
                    bool primaryPresser = isPresser || (tacAssign == null && p.Index == chaser1);
                    if (!primaryPresser)
                    {
                        p.JockeyState = 1; // jockeying
                        bool nearBox = Mx.FlatDist(carrier.Pos, GoalPos(carrier.Team)) < 30f;
                        if (tacAssign != null && isCoverRole)
                        {
                            p.Target = tacAssign.MovementTarget;
                        }
                        else
                        {
                            float lane = p.Index == chaser2 ? (nearBox ? -3f : -5.5f) : (nearBox ? -5f : -9f);
                            float sz = nearBox ? 3f : 5f;
                            Vector3 side = new Vector3(0, 0, p.Index == chaser2 ? sz : -sz);
                            p.Target = carrier.Pos + goalDir * lane + side;
                        }
                        if (Mx.FlatDist(p.Pos, carrier.Pos) < 3f)
                            p.JockeyState = 2; // containing
                        p.Pressing = false;
                    }
                    else
                    {
                        p.JockeyState = 0;
                        float lane = 2.6f / Mx.Clamp(p.TacticsPressMult, .6f, 1.7f);
                        float gap = Mx.FlatDist(p.Pos, carrier.Pos);
                        bool heavy = Mx.FlatDist(carrier.Pos, ball.Pos) > 1.1f || carrier.FirstTouchQuality < .4f;
                        bool danger = Mx.FlatDist(carrier.Pos, GoalPos(carrier.Team)) < 28f;
                        float phase = (S.Clock / MathF.Max(1f, Options.TimeSpeed) * .5f + p.Index * .37f) % 1f;
                        if (heavy || danger || phase < .12f) lane = .9f;
                        Vector3 pressTarget = carrier.Pos + goalDir * lane + Mx.Flat(carrier.Vel) * .22f;
                        if (tacAssign != null && isPresser)
                            pressTarget = Mx.Lerp(pressTarget, tacAssign.MovementTarget, 0.5f);
                        p.Target = pressTarget;
                        p.Pressing = gap > lane + 1.5f;
                        p.JockeyState = gap <= lane + 1.5f ? 2 : 0;
                    }
                }
                else
                {
                    Vector3 focus = BallFocus();
                    Vector3 intercept = focus != ball.Pos ? focus
                        : ball.Pos + Mx.Flat(ball.Vel) * Mx.Clamp(Mx.FlatDist(p.Pos, ball.Pos) / 14f, 0f, .7f);
                    if (ball.Owner < 0 && !ball.HasPending && !IsSkill)
                    {
                        var pred = _tacticalBallPred ?? BallPred(1.2f);
                        float maxSpd = p.MaxSpeed;
                        float accel = Math.Clamp(9f + p.Spec.Pace * 6f + p.Spec.Defending * 3f, 8f, 18f);
                        if (pred.TryInterceptXZ(p.Pos, maxSpd, accel, out var s, 0f))
                            intercept = new Vector3(s.Position.X, 0f, s.Position.Z);
                    }
                    if (tacAssign != null && isPresser)
                        intercept = Mx.Lerp(intercept, tacAssign.MovementTarget, 0.35f);
                    p.Target = intercept;
                }
                if (p.ActionTimer <= 0f) p.Action = "run";
            }
            else
            {
                p.Target = slotPos;
                // Goal-side marking: a defender or midfielder with an attacker in his
                // zone sits between that man and his own goal, never in front of him.
                if (oppOwns && (p.Role == Role.Defender || p.Role == Role.Midfielder))
                {
                    var ownGoal = OwnGoalPos(p.Team);
                    PlayerState? mark = null; float best = 11f;
                    foreach (var q in S.Players)
                    {
                        if (q.Team == p.Team || q.SentOff || q.IsKeeper || q.Index == ball.Owner) continue;
                        // Near the ball the chasers deal with it; markers pick up runners
                        // away from it (tight marking at the ball crowded it).
                        if (Mx.FlatDist(q.Pos, ball.Pos) < 6f) continue;
                        float dz = Mx.FlatDist(q.Pos, slotPos);
                        if (dz < best) { best = dz; mark = q; }
                    }
                    if (mark != null)
                    {
                        Vector3 goalSide = mark.Pos + Mx.FlatDir(mark.Pos, ownGoal) * 1.6f;
                        p.Target = Mx.Lerp(slotPos, goalSide, .65f);
                    }
                }
                if (!IsSkill)
                {
                    if (tacAssign != null)
                    {
                        if (tacAssign.Role == "cover")
                            p.Target = Mx.Lerp(p.Target, tacAssign.MovementTarget, 0.18f);
                        else if (tacAssign.Role == "recover" && tacAssign.Intent.StartsWith("transition", StringComparison.Ordinal))
                            p.Target = Mx.Lerp(p.Target, tacAssign.MovementTarget, 0.12f);
                    }
                }
                if (p.ActionTimer <= 0f) p.Action = "run";
            }
            if (ball.Owner >= 0)
            {
                var carrier = S.Players[ball.Owner];
                float d = Mx.FlatDist(p.Pos, carrier.Pos);
                // One challenger at a time: only the designated presser commits, and
                // mostly when the carrier's touch is loose.  Every defender within
                // 2.2 m used to lunge ~3 times a second (~120 tackles a match).
                var tac = GetTacticalAssignment(p.Index);
                bool presser = tac != null ? tac.Role == "press" : p.Index == PrimaryChaser(p.Team, 0);
                float looseTouch = Mx.FlatDist(carrier.Pos, ball.Pos) > .45f || carrier.FirstTouchQuality < .5f ? .22f : 0f;
                float aggression = presser
                    ? .22f + Options.Difficulty * .04f + (p.Spec.Defending - .5f) * .08f + looseTouch
                    : (tac?.Role == "cover" ? .04f : .01f);
                if (p.Team != carrier.Team && d < 2.0f && p.TackleLock <= 0 && Rng.Next() < aggression)
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
        // Team shape.  The slots are kick-off shapes (everyone in their own half);
        // the old +-0.15 shift kept forwards within ~7 m of halfway all match, so a
        // carrier was always dribbling on his own.  Now the block moves as a unit:
        //  * in possession it steps up with the ball - back line to halfway when
        //    attacking, forwards into the box, held level with the opposition's
        //    second-last defender so they stay onside;
        //  * out of possession it is compact, shifted across to the ball, and the
        //    defensive line never steps in front of the ball (goal-side).
        float scale = Mx.HalfLength * .94f;
        float bx = Mx.Clamp(ballPos.X * attack / scale, -1f, 1f);        // ball, own frame
        float progress = (bx + 1f) * .5f;                                 // 0 own goal .. 1 their goal
        bool inPossession = PossessionTeam() == p.Team;
        float width = Mx.Clamp(p.TacticsWidthMult, .6f, 1.4f);
        float bz = Mx.Clamp(ballPos.Z / Mx.HalfWidth, -1f, 1f);
        float x, z;
        if (inPossession)
        {
            // Defenders step up less than the rest: real teams in possession are
            // ~34 m long back-to-front (ours were 23 m - the back line pushed up to
            // the forwards).
            float push = p.Role == Role.Defender ? .10f + .45f * progress : .22f + .66f * progress;
            x = slot.x + push;
            // Wide players and full-backs stretch to the touchline in possession
            // (the ball used to never go wider than ~25 m from the centre line).
            float zs = MathF.Abs(slot.z) > .45f ? slot.z * 1.55f : slot.z * 1.25f;
            z = Mx.Clamp((zs + bz * .12f) * width, -.97f, .97f);
            if (p.Role == Role.Forward || p.Role == Role.Midfielder)
            {
                float onside = OffsideLineFrame(p.Team) - .015f;
                x = MathF.Min(x, MathF.Max(onside, bx));
            }
        }
        else
        {
            // Compact block centred a little goal-side of the ball.
            // Real blocks out of possession: ~30 m long, ~33 m wide (ours: 23 / 39).
            float centre = bx * .50f - .16f;
            x = centre + (slot.x + .34f) * .76f;
            z = (slot.z * .66f + bz * .28f) * width;
            if (p.Role == Role.Defender) x = MathF.Min(x, bx - .03f);
            x = MathF.Max(x, -.80f);
        }
        x = Mx.Clamp(x, -.86f, .80f);
        Vector3 world = Clubs.SlotToWorld(x, z, attack);
        // PR C deeper: coordinator shapes cover/recover when out of possession.
        var tac = GetTacticalAssignment(p.Index);
        if (tac != null && !p.IsKeeper)
        {
            if (!inPossession && (tac.Role == "cover" || tac.Role == "recover"))
            {
                float blend = tac.Role == "cover" ? 0.30f : 0.18f;
                world = Mx.Lerp(world, tac.MovementTarget, blend);
            }
            else if (inPossession && tac.Role == "support")
            {
                world = Mx.Lerp(world, tac.MovementTarget, 0.15f);
            }
        }
        return world;
    }

    /// <summary>The opposition's second-last player (offside line), in
    /// <paramref name="team"/>'s attacking frame (-1 own goal .. 1 their goal).</summary>
    private float OffsideLineFrame(int team)
    {
        int attack = SideSign(team);
        float scale = Mx.HalfLength * .94f;
        float deepest = float.MinValue, second = float.MinValue;
        foreach (var q in State.Players)
        {
            if (q.Team == team || q.SentOff) continue;
            float qx = q.Pos.X * attack / scale;
            if (qx > deepest) { second = deepest; deepest = qx; }
            else if (qx > second) second = qx;
        }
        // Never behind halfway (you can't be offside in your own half).
        return MathF.Max(second == float.MinValue ? 0f : second, 0f);
    }

    /// <summary>The team that has the ball - including a pass on its way to a team-mate
    /// (both teams used to drop into their out-of-possession block, and chase, every
    /// time a pass was in the air).  -1 for a genuinely loose ball.</summary>
    private int PossessionTeam()
    {
        var b = State.Ball;
        if (b.Owner >= 0) return State.Players[b.Owner].Team;
        if (b.PassReceiver >= 0 && b.PassReceiver < State.Players.Length && b.FreeTime < 3f && b.LastTouchSide >= 0
            && State.Players[b.PassReceiver].Team == b.LastTouchSide)
            return b.LastTouchSide;
        return -1;
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

    private int PrimaryChaser(int team, int rank)
    {
        // M3: coordinator is authoritative for primary defensive engagement when available.
        // Rank 0 prefers coordinator press, rank 1 prefers cover, rank 2 prefers next defensive role.
        // Fallback to distance/intercept ranking, excluding higher-ranked picks.
        if (rank < 0) rank = 0;
        var exclude = new HashSet<int>();
        for (int r = 0; r <= rank; r++)
        {
            int pick = -1;
            if (r <= 2)
            {
                string? want = r == 0 ? "press" : r == 1 ? "cover" : null;
                if (want != null)
                {
                    foreach (var p in State.Players)
                    {
                        if (p.Team != team || p.IsKeeper || p.SentOff || exclude.Contains(p.Index)) continue;
                        var tac = GetTacticalAssignment(p.Index);
                        if (tac != null && tac.Role == want) { pick = p.Index; break; }
                    }
                }
                else
                {
                    var candidates = new List<(int idx, float score)>();
                    foreach (var p in State.Players)
                    {
                        if (p.Team != team || p.IsKeeper || p.SentOff || exclude.Contains(p.Index)) continue;
                        var tac = GetTacticalAssignment(p.Index);
                        if (tac == null) continue;
                        if (tac.Role == "recover" || tac.Role == "support" || tac.Role == "cover")
                            candidates.Add((p.Index, Mx.FlatDist2(p.Pos, BallFocus())));
                    }
                    if (candidates.Count > 0)
                    {
                        candidates.Sort((a, b) => a.score.CompareTo(b.score));
                        pick = candidates[0].idx;
                    }
                }
            }
            if (pick < 0) pick = ClosestToBall(team, 0, exclude);
            if (pick < 0) return -1;
            if (r == rank) return pick;
            exclude.Add(pick);
        }
        return -1;
    }

    private int ClosestToBall(int team, int rank) => ClosestToBall(team, rank, null);

    private int ClosestToBall(int team, int rank, HashSet<int>? exclude)
    {
        var b = State.Ball;
        var focus = BallFocus();
        bool looseMoving = b.Owner < 0 && !b.HasPending && !IsSkill && Mx.Flat(b.Vel).LengthSquared() > 4f;
        var pred = looseMoving ? BallPred(1.5f) : null;
        var list = State.Players.Where(p => p.Team == team && !p.IsKeeper && !p.SentOff && (exclude == null || !exclude.Contains(p.Index)))
            .Select(p => {
                float score = Mx.FlatDist2(p.Pos, focus);
                if (pred != null)
                {
                    float accel = Math.Clamp(9f + p.Spec.Pace * 6f + p.Spec.Defending * 3f, 8f, 18f);
                    if (pred.TryInterceptXZ(p.Pos, p.MaxSpeed, accel, out var s, 0f))
                        score = s.Time * s.Time * 100f + Mx.FlatDist2(p.Pos, new Vector3(s.Position.X,0,s.Position.Z)) * 0.01f;
                }
                return (p.Index, score);
            })
            .OrderBy(x => x.score).ToArray();
        return rank < list.Length ? list[rank].Index : (list.Length > 0 ? list[0].Index : -1);
    }

    private int FindBestPassTarget(PlayerState from, bool through, bool longPass = false, Vector2 aimDir = default)
    {
        int best = -1; float bestScore = float.MinValue; bool bestBlocked = false;
        int attack = SideSign(from.Team);
        // FIFA/PES-style: bias target toward stick aim direction.
        // If stick is centered, use facing direction. Aim alignment is the
        // dominant factor so passes go where the player points.
        bool hasAim = aimDir.LengthSquared() > 0.15f;
        Vector2 aim = hasAim ? Vector2.Normalize(aimDir) : new Vector2(from.Facing.X, from.Facing.Z);
        float passSpeed = longPass ? 20f : through ? 17f : 13f;
        int oppCount = 0;
        foreach (var o in State.Players) if (o.Team != from.Team && !o.SentOff) oppCount++;
        var oppP = new Vector3[oppCount];
        var oppV = new Vector3[oppCount];
        var oppSpd = new float[oppCount];
        var oppAcc = new float[oppCount];
        int oi = 0;
        foreach (var o in State.Players)
        {
            if (o.Team == from.Team || o.SentOff) continue;
            oppP[oi] = o.Pos; oppV[oi] = o.Vel;
            oppSpd[oi] = o.MaxSpeed;
            oppAcc[oi] = Math.Clamp(9f + o.Spec.Pace * 6f + o.Spec.Defending * 3f, 8f, 18f);
            oi++;
        }
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
            bool laneBlocked = LaneRisk(from, q, d) > 0f;
            float laneSafety = ArenaFC.Core.Football.PlayerPerception.LaneSafety(from.Pos, q.Pos, oppP, oppV, passSpeed, oppSpd, oppAcc);
            float tBall = d / MathF.Max(1f, passSpeed);
            Vector3 recvAim = q.Pos + Mx.Flat(q.Vel) * MathF.Min(tBall, 0.6f) * (through ? 0.8f : 0.45f);
            float recvMax = q.MaxSpeed;
            float recvAcc = Math.Clamp(9f + q.Spec.Pace * 6f + q.Spec.Defending * 3f, 8f, 18f);
            float tRecv = ArenaFC.Core.Football.PlayerPerception.TimeToReach(q.Pos, q.Vel, recvAim, recvMax, recvAcc);
            float recvReachPenalty = MathF.Max(0f, tRecv - tBall - 0.15f) * 3.0f;
            // Aim alignment dominates (weight 8.0) so stick direction controls
            // the pass. AI factors (forward/openness) break ties.
            // An opponent who can step into the lane before the ball passes him
            // turns the pass into an interception (61% of AI passes went past an
            // opponent within 1.5 m of the line; real completion is ~80%).
            float score = aimAlign * 8.0f + forward * .22f + openness * .55f - d * .10f + (through ? forward * .28f : 0f) - (laneBlocked ? (hasAim ? 6f : 14f) : 0f);
            score += (laneSafety - 0.55f) * 3.5f;
            if (laneSafety < 0.20f) score -= 5f;
            score -= recvReachPenalty;
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
            // AI build-up looks for the winger in the final 40 m (to get crosses in).
            if (!hasAim && !laneBlocked && MathF.Abs(q.Pos.Z) > Mx.HalfWidth * .45f
                && MathF.Abs(GoalPos(from.Team).X - q.Pos.X) < 40f) score += 2.5f;
            score += Rng.Range(-1.2f, 1.2f);
            if (score > bestScore) { bestScore = score; best = q.Index; bestBlocked = laneBlocked || laneSafety < 0.25f; }
        }
        LastPassTargetBlocked = bestBlocked;
        return best;
    }

    /// <summary>A shot (or stray ball) that will miss his goal: he lets it go for a goal
    /// kick instead of palming it round the post.  Keepers used to touch 57% of all
    /// shots, wide ones included, so goal kicks barely happened.</summary>
    private bool GoingWide(PlayerState k)
    {
        var b = State.Ball;
        float gx = OwnGoalPos(k.Team).X;
        // Already over the line outside the posts: out of play, leave it.
        if (MathF.Abs(b.Pos.X) >= MathF.Abs(gx) && (MathF.Abs(b.Pos.Z) > Mx.GoalHalfWidth || b.Pos.Y > Mx.GoalHeight)) return true;
        if (MathF.Abs(b.Vel.X) < 8f || MathF.Sign(b.Vel.X) != MathF.Sign(gx - b.Pos.X)) return false;
        float t = MathF.Max(0f, (gx - b.Pos.X) / b.Vel.X);   // already over: judge it where it is
        if (t > 1.2f) return false;
        float z = b.Pos.Z + b.Vel.Z * t;
        float y = b.Pos.Y + b.Vel.Y * t - .5f * 9.81f * t * t;
        return MathF.Abs(z) > Mx.GoalHalfWidth + .35f || y > Mx.GoalHeight + .3f;
    }

    /// <summary>6.5: a high ball dropping into his area that he can get to first -
    /// where it comes down through catching height (2.3 m).</summary>
    private bool TryClaimPoint(PlayerState k, out Vector3 point)
    {
        var b = State.Ball; point = default;
        if (b.Pos.Y < 1.2f && b.Vel.Y <= 0f) return false;
        if (Mx.Flat(b.Vel).Length() < 4f) return false;
        var pred = BallPred(2.2f);
        float t = -1f; Vector3 p = default;
        for (int i = 1; i < pred.Samples.Count; i++)
        {
            var s = pred.Samples[i];
            if (s.Position.Y <= 2.3f && s.Velocity.Y <= 0f)
            { t = s.Time; p = new Vector3(s.Position.X, 0f, s.Position.Z); break; }
        }
        if (t <= 0f) return false;
        Vector3 own = OwnGoalPos(k.Team);
        if (MathF.Abs(p.X - own.X) > 7f || MathF.Abs(p.Z) > 9f || MathF.Abs(p.X) > Mx.HalfLength) return false;
        float mine = Mx.FlatDist(k.Pos, p) / 6.5f;
        if (mine > t + .25f) return false;
        foreach (var q in State.Players)
            if (q.Team != k.Team && !q.SentOff && Mx.FlatDist(q.Pos, p) / 7f < mine - .35f) return false;
        point = p;
        return true;
    }

    /// <summary>A ball travelling at this keeper's goal: where it crosses the plane he
    /// stands in, and how long until it gets there.</summary>
    private bool TryShotCrossing(PlayerState k, out Vector3 cross, out float t)
    {
        var b = State.Ball; cross = default; t = 0f;
        float gx = OwnGoalPos(k.Team).X;
        float vx = b.Vel.X;
        if (MathF.Abs(vx) < 6f || MathF.Sign(vx) != MathF.Sign(gx - b.Pos.X)) return false;
        float planeX = MathF.Abs(k.Pos.X - gx) < 6f ? k.Pos.X : gx - MathF.Sign(gx) * .6f;
        t = (planeX - b.Pos.X) / vx;
        if (t < 0f || t > 1.6f) return false;
        var pred = BallPred(MathF.Min(1.6f, t + 0.1f));
        var s = pred.At(t);
        float z = s.Position.Z;
        float y = s.Position.Y;
        if (MathF.Abs(z) > Mx.GoalHalfWidth + .3f || y > Mx.GoalHeight + .3f) return false;   // going wide: let it go
        cross = new Vector3(planeX, MathF.Max(Mx.BallRadius, y), z);
        return true;
    }

    /// <summary>Set by FindBestPassTarget: the chosen lane can be cut out.</summary>
    private bool LastPassTargetBlocked;

    /// <summary>How far inside an opponent's interception reach the pass lane passes
    /// (0 = clear).  Reach grows with the time the ball takes to get level with him.</summary>
    private float LaneRisk(PlayerState from, PlayerState to, float d)
    {
        float worst = 0f;
        Vector3 line = Mx.Flat(to.Pos - from.Pos);
        foreach (var o in State.Players)
        {
            if (o.Team == from.Team || o.SentOff) continue;
            float proj = Vector3.Dot(Mx.Flat(o.Pos - from.Pos), line) / MathF.Max(.01f, d * d);
            if (proj < .05f || proj > .97f) continue;
            float perp = Mx.FlatDist(o.Pos, Mx.Lerp(from.Pos, to.Pos, proj));
            float tArrive = proj * d / 13f;
            float reach = .9f + 4.5f * tArrive;
            worst = MathF.Max(worst, reach - perp);
        }
        return worst;
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

    private void PassTo(PlayerState from, PlayerState to, float power, bool through, bool lob = false, Vector3? aimAt = null)
    {
        var b = State.Ball;
        if (b.Owner != from.Index && b.Owner >= 0) return;
        if (b.HasPending) return;
        from.PossessionLock = .35f;
        // 7.2: a throw-in is thrown - two hands, from above the head - not kicked.
        bool thrown = IsThrowInHold(from);
        ReleaseSetPiece(from);
        // Phase 0.1: wind-up, then release at ball_contact (0.5 * 0.34s).
        if (thrown)
        {
            SetAction(from, "throw_in", .55f, .55f);
            // In his hands during the wind-up: it was lying over the line, so the
            // out-of-play check gave another throw-in before it was even thrown.
            float zl0 = Mx.HalfWidth - .15f;
            b.Pos = new Vector3(b.Pos.X, b.Pos.Y, Mx.Clamp(b.Pos.Z, -zl0, zl0));
            b.Vel = Vector3.Zero;
        }
        else SetAction(from, "kick", .34f, .50f, "pass");
        Vector3 aim = aimAt ?? to.Pos + Mx.Flat(to.Vel) * (through ? .55f : .22f);
        if (through && aimAt == null) aim += Mx.FlatDir(from.Pos, GoalPos(from.Team)) * 4f;
        float skill = from.Spec.Passing;
        float dist = Mx.FlatDist(b.Pos, aim);
        if (aimAt == null)
        {
            float estSpeed = through ? Mx.Clamp(dist * 0.9f, 10f, 24f) : Mx.Clamp(dist * 1.1f, 8f, 22f);
            float tBall = dist / MathF.Max(1f, estSpeed);
            float leadT = MathF.Min(tBall, through ? 0.85f : 0.35f);
            Vector3 recvLead = to.Pos + Mx.Flat(to.Vel) * leadT;
            if (through)
                recvLead += Mx.FlatDir(from.Pos, GoalPos(from.Team)) * MathF.Min(5f, 2f + tBall * 4f);
            // Only adopt lead if receiver can plausibly reach it around ball arrival.
            float recvMax = to.MaxSpeed;
            float recvAcc = Math.Clamp(9f + to.Spec.Pace * 6f + to.Spec.Defending * 3f, 8f, 18f);
            float tRecv = ArenaFC.Core.Football.PlayerPerception.TimeToReach(to.Pos, to.Vel, recvLead, recvMax, recvAcc);
            if (tRecv <= tBall + 0.30f)
            {
                aim = Vector3.Lerp(aim, recvLead, through ? 0.70f : 0.35f);
                dist = Mx.FlatDist(b.Pos, aim);
            }
        }
        Vector3 dir = Mx.FlatDir(b.Pos, aim);
        // Pass error grows with pressure, distance and difficulty (it was a flat
        // ~4 deg from skill alone, so AI passes almost never strayed - the main
        // source of throw-ins, corners and turnovers in real football).
        NearestOpponent(from, out float pressDist);
        float pressure = Mx.Clamp(1f - pressDist / 3f, 0f, 1f);
        float err = ((1f - skill) * 2.2f + (through ? .8f : 0f) + (lob ? .6f : 0f))
                    * (1f + pressure * .9f) * (1f + MathF.Max(0f, dist - 15f) / 30f);
        dir = Mx.Norm(dir + new Vector3(Rng.Signed() * err * .12f, 0, Rng.Signed() * err * .12f));
        // Weight error: slightly over- or under-hit.
        float weightErr = 1f + Rng.Signed() * ((1f - skill) * .22f + pressure * .10f);
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
        speed = Mx.Clamp(speed * weightErr, 5f, 28f);
        float loftY = passType switch
        {
            PassType.Driven => .45f,
            PassType.Lofted => 5.5f,
            PassType.Threaded => .9f,
            PassType.Chip => 3.2f,
            _ => .45f,
        };
        // 3.3 curled passes: the spin used to be a random sign (pure error).  A
        // through ball or a long pass with an opponent in the lane is now bent
        // round him: launched on the far side of the line and curled back onto
        // the target (Magnus: accel = -spin * |v| * n, n = left of the pass line).
        float curve = 0f;
        if ((passType == PassType.Threaded || passType == PassType.Lofted) && skill > .45f && dist > 10f)
        {
            Vector3 n = new(-dir.Z, 0, dir.X);
            PlayerState? blocker = null; float bestPerp = 1.6f, blockSide = 0f;
            foreach (var q in State.Players)
            {
                if (q.Team == from.Team || q.SentOff || q.IsKeeper) continue;
                Vector3 rel = Mx.Flat(q.Pos - b.Pos);
                float along = Vector3.Dot(rel, dir), perp = Vector3.Dot(rel, n);
                if (along < dist * .15f || along > dist * .85f || MathF.Abs(perp) >= bestPerp) continue;
                bestPerp = MathF.Abs(perp); blocker = q; blockSide = perp >= 0f ? 1f : -1f;
            }
            if (blocker != null)
            {
                float launchSide = -blockSide;                        // go round the far side of him
                float spinMag = (passType == PassType.Threaded ? 4.5f : 3.5f) + 3f * skill;
                float t = dist / MathF.Max(6f, speed);
                float bend = MathF.Min(.5f * .055f * spinMag * speed * t * t * .6f, dist * .3f);
                Vector3 offsetAim = aim + n * (launchSide * bend);
                dir = Mx.Norm(Mx.FlatDir(b.Pos, offsetAim) + (dir - Mx.FlatDir(b.Pos, aim)));
                curve = launchSide * spinMag;
            }
        }
        b.HasPending = true; b.PendingKind = 1; b.PendingFrom = from.Index;
        if (aimAt != null && lob)
        {
            // A cross into an area: a real arc that arrives at head height over the
            // spot (it used to be a 3 m/s "chip" that skidded through the box at 17 m/s).
            float T = Mx.Clamp(dist / 17f, .75f, 1.35f);
            speed = dist / T * weightErr;
            loftY = (1.7f - Mx.BallRadius + .5f * 9.81f * T * T) / T;
        }
        if (thrown)
        {
            // Released from head height on a throwing arc: lands at the man's feet.
            float T = Mx.Clamp(dist / 13f, .45f, 1.2f);
            speed = Mx.Clamp(dist / T, 5f, 16f);
            loftY = (.3f - 2.1f + .5f * 9.81f * T * T) / T;
            curve = 0f;
        }
        b.PendingVel = dir * speed + new Vector3(0, loftY, 0);
        b.PendingSpin = new Vector3(0, curve, 0);
        b.PendingPos = from.Pos + dir * (thrown ? .25f : .55f) + new Vector3(0, thrown ? 2.1f : Mx.BallRadius + .03f, 0);
        if (thrown)
        {
            // Released over the line, not behind it (the taker stands just outside):
            // the throw used to start out of play and go straight back out.
            float zl = Mx.HalfWidth - .15f;
            b.PendingPos = new Vector3(b.PendingPos.X, b.PendingPos.Y, Mx.Clamp(b.PendingPos.Z, -zl, zl));
            b.PendingNoPickup = .30f;
        }
        b.PendingNoPickup = thrown ? .30f : .10f;
        b.PendingReceiver = to.Index; b.PendingTarget = aim;
        // Counted when the ball leaves the foot (FirePending), not at the wind-up:
        // a pass challenged mid-kick and tried again was counted two or three times.
        string passLabel = thrown ? "throws it" : aimAt != null && lob ? "crosses it" : passType switch
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
    private enum ShotType { Power, Placement, Control, Volley, Finesse, Chip, Low, Trivela }

    private void Shoot(PlayerState p, float charge, bool volley = false, ShotStyle style = ShotStyle.Auto, Vector2 aim = default)
    {
        var b = State.Ball;
        if (b.Owner != p.Index && !volley) return;
        if (volley && Mx.FlatDist(p.Pos, b.Pos) > 1.6f) return;
        if (b.HasPending) return;
        p.PossessionLock = .55f;
        // (Checked before ReleaseSetPiece clears MustPlayBall.)
        if (Options.Mode == 3 || (p.MustPlayBall && AtPenaltySpot(State.RestartPos))) { State.ShootoutShotTaken = true; State.ShootoutTimer = 0f; }
        ReleaseSetPiece(p);
        // Phase 0.2: volley plays the volley clip; release at ball_contact.
        // Phase 2.4: Dynamic Volley — first-time aerial (eFootball v6.0).
        bool isVolley = volley || (b.Pos.Y > .5f && b.Owner == p.Index);
        SetAction(p, isVolley ? "volley" : "kick", .40f, .50f, "shoot");
        int attack = SideSign(p.Team);
        Vector3 target = new(GoalPos(p.Team).X, Rng.Range(.4f, 2.0f), Rng.Range(-Mx.GoalHalfWidth * .78f, Mx.GoalHalfWidth * .78f));
        State.Xg[p.Team] += ShotXg(p, target);
        // Shot type: an explicit modifier (finesse LT+X, chip LB+X, low double-tap X),
        // otherwise by power.  Finesse used to be a hidden 50-65% power window.
        ShotType shotType = style == ShotStyle.Finesse ? ShotType.Finesse
            : style == ShotStyle.Trivela ? ShotType.Trivela
            : style == ShotStyle.Chip ? ShotType.Chip
            : style == ShotStyle.Low ? ShotType.Low
            : isVolley ? ShotType.Volley
            : charge > .75f ? ShotType.Power
            : charge < .35f ? ShotType.Placement
            : ShotType.Control;
        // Dedicated Sprite Forge clips for the chip and the trivela (same timing as "kick").
        if (shotType == ShotType.Chip) p.Action = "chip_shot";
        else if (shotType == ShotType.Trivela) p.Action = "trivela";
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
        float cornerBias = shotType == ShotType.Placement || shotType == ShotType.Finesse || shotType == ShotType.Trivela ? .9f : .6f;
        target.Z = MathF.Sign(target.Z) * Mx.Lerp(Mx.GoalHalfWidth * .2f, Mx.GoalHalfWidth * .86f, p.Spec.Shooting * cornerBias * Rng.Next());
        // The stick aims the shot: across the goal = that post (the side used to be
        // random, so "aim with the left stick" did nothing).
        if (aim.LengthSquared() > .1f && MathF.Abs(aim.Y) > .2f)
            target.Z = MathF.Sign(aim.Y) * Mx.Lerp(Mx.GoalHalfWidth * .45f, Mx.GoalHalfWidth * .86f, MathF.Min(1f, MathF.Abs(aim.Y) + p.Spec.Shooting * .3f));
        else if (aim.LengthSquared() > .1f)
            target.Z *= .35f;                                      // stick straight at goal: aim central
        if (shotType == ShotType.Chip) target.Y = Mx.GoalHeight * .8f;
        if (shotType == ShotType.Low) target.Y = .2f;
        Vector3 dir = Mx.FlatDir(b.Pos, target);
        float dist = Mx.FlatDist(b.Pos, target);
        // A defender closing in hurries the strike (shots ignored pressure: 52% were
        // on target against ~33% in real football, and goal kicks were rare).
        NearestOpponent(p, out float shotPress);
        float hurried = Mx.Clamp(1f - (shotPress - .8f) / 2.7f, 0f, 1f);
        float err = (1f - p.Spec.Shooting) * 3.4f + (isVolley ? 1.2f : 0f) + MathF.Max(0f, dist - 18f) * .08f + hurried * 1.0f;
        // Placement/finesse shots are more accurate; power shots less so.
        if (shotType == ShotType.Placement) err *= .6f;
        if (shotType == ShotType.Finesse) err *= .5f;
        if (shotType == ShotType.Trivela) err *= .7f;          // harder to strike cleanly
        if (shotType == ShotType.Power) err *= 1.3f;
        err *= weakFootPenalty;
        err *= (2f - timingQuality); // poor timing = more error
        dir = Mx.Norm(dir + new Vector3(0, 0, Rng.Signed() * err * .16f));
        float power = Mx.Lerp(17f, 31f, charge) * Mx.Lerp(.82f, 1.12f, p.Spec.Shooting);
        if (shotType == ShotType.Placement) power *= .75f;
        if (shotType == ShotType.Finesse) power *= .8f;
        if (shotType == ShotType.Trivela) power *= .9f;
        if (shotType == ShotType.Volley) power *= 1.05f;
        if (shotType == ShotType.Chip) power = Mx.Lerp(10f, 15f, charge) + dist * .12f;
        if (shotType == ShotType.Low) { power *= .95f; err *= .9f; }
        power *= (0.7f + timingQuality * 0.3f); // perfect timing = full power
        float loft = Mx.Lerp(.08f, .30f, charge) + (dist > 20f ? .06f : 0f);
        if (shotType == ShotType.Placement) loft *= .5f;
        if (shotType == ShotType.Finesse) loft *= .6f;
        if (shotType == ShotType.Trivela) loft *= .7f;
        if (shotType == ShotType.Volley) loft = .35f;
        if (shotType == ShotType.Chip) loft = .62f;                // up and over the keeper
        if (shotType == ShotType.Low) loft = .015f;                // skidding along the turf
        if (shotType is ShotType.Power or ShotType.Placement or ShotType.Control or ShotType.Finesse or ShotType.Trivela)
        {
            // 3.4: the shot is struck at a height at the goal line, not with a fixed
            // launch angle.  The old angle meant a well-timed shot from 16 m (charge
            // .78) cleared the bar every time and anything >=.7 from 24 m went over.
            // Aimed height by shot type, then what goes wrong: over-hitting (charge
            // past .85) leans back and lifts it, bad timing scatters it, sprinting
            // through the shot gets under it, the weak foot is less clean.
            float hT = shotType switch
            {
                ShotType.Placement => target.Y * .55f,
                ShotType.Finesse or ShotType.Trivela => Mx.Lerp(.9f, 2.1f, Rng.Next()),
                _ => target.Y,
            };
            float overHit = MathF.Max(0f, charge - .85f) / .15f;
            hT += overHit * Rng.Range(.5f, 2.4f) * (1f + dist / 30f);   // worse from range
            hT += Rng.Signed() * (1f - timingQuality) * 1.1f;
            if (p.Sprinting) hT += .3f;
            hT += Rng.Signed() * (weakFootPenalty - 1f) * .8f;
            hT = MathF.Max(.12f, hT);
            float tFlight = dist / MathF.Max(8f, power) * 1.06f;
            float vy = (hT - b.Pos.Y) / tFlight - .5f * Mx.Gravity * tFlight;
            loft = Mx.Clamp(vy, 0f, power * .5f) / power;
        }
        b.HasPending = true; b.PendingKind = 1; b.PendingFrom = p.Index;
        // On target is judged on the line the shot is meant to finish on (a
        // finesse shot starts outside the post and bends back in).
        bool onTarget = IsOnTarget(b.Pos, dir * power + new Vector3(0, power * loft, 0), GoalPos(p.Team));
        Vector3 spin;
        if (shotType == ShotType.Finesse || shotType == ShotType.Trivela)
        {
            // 3.3: inside-foot curl.  Start the ball outside the far post and let
            // the Magnus force bend it back: a = k * spin * v (BallPhysics), so
            // the bend over the flight is ~0.5 a t^2.  Spin sign makes it curve
            // towards the middle of the goal (Cross(spin, v).Z = -spin * v.X).
            // Trivela (outside of the boot): the opposite shape - it starts on the
            // inside, towards the middle, and swerves out to the aimed post.
            float side = target.Z >= 0f ? 1f : -1f;
            if (shotType == ShotType.Trivela) side = -side;
            float spinMag = 3.2f + p.Spec.Shooting * 2.4f;
            float t = dist / MathF.Max(8f, power);
            float bend = MathF.Min(.5f * .055f * spinMag * power * t * t * .6f, dist * .2f);
            Vector3 outside = new(target.X, target.Y, target.Z + side * bend);
            dir = Mx.Norm(Mx.FlatDir(b.Pos, outside) + (dir - Mx.FlatDir(b.Pos, target)));
            spin = new Vector3(0, side * MathF.Sign(dir.X) * spinMag, 0);
        }
        else spin = new Vector3(0, Rng.Signed() * (1f + p.Spec.Shooting * 2.2f), 0);
        b.PendingVel = dir * power + new Vector3(0, power * loft, 0);
        if (onTarget) State.ShotsOnTarget[p.Team]++;
        b.PendingSpin = spin;
        b.PendingPos = b.Pos + new Vector3(0, .05f, 0);
        b.PendingNoPickup = .22f;
        b.PendingReceiver = -1; b.PendingTarget = target;
        State.Shots[p.Team]++;
        string shotLabel = shotType switch
        {
            ShotType.Power => "smashes it",
            ShotType.Placement => "places it",
            ShotType.Finesse => "curls it",
            ShotType.Trivela => "goes outside of the boot",
            ShotType.Chip => "chips it",
            ShotType.Low => "drills it low",
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
            carrier.PossessionLock = .45f;
            p.JockeyState = 0;
            // Not every won tackle is a clean pick-up: slides and pokes knock it
            // loose (where most real throw-ins and corners come from).
            // Near the touchline a challenge usually puts it out for a throw (real
            // matches have ~40 throw-ins; ours had ~2 once a repeat-throw bug went).
            float toLine = Mx.HalfWidth - MathF.Abs(carrier.Pos.Z);
            bool byLine = toLine < 7f;
            float pokeChance = (slide ? .55f : .30f) + (byLine ? .25f : 0f);
            if (Rng.Next() < pokeChance)
            {
                Vector3 through = Mx.FlatDir(p.Pos, carrier.Pos);
                float ang = Rng.Range(-1.0f, 1.0f);
                Vector3 dir = new(through.X * MathF.Cos(ang) - through.Z * MathF.Sin(ang), 0,
                                  through.X * MathF.Sin(ang) + through.Z * MathF.Cos(ang));
                if (byLine && Rng.Next() < .6f)
                    dir = Mx.Norm(dir * .4f + new Vector3(0, 0, MathF.Sign(carrier.Pos.Z)));
                b.Owner = -1;
                b.Vel = dir * Rng.Range(4f, slide ? 10f : 7f);
                b.LastTouch = p.Index; b.LastTouchSide = p.Team;
                b.NoPickup = .12f; b.FreeTime = 0f;
                p.PossessionLock = .25f;
                Add(EventKind.Tackle, $"{p.Spec.DisplayName} pokes it away!");
            }
            else
            {
                b.Owner = p.Index;
                p.PossessionLock = .12f;
                b.Vel = Vector3.Zero;
                Add(EventKind.Tackle, $"{p.Spec.DisplayName} wins the ball!");
            }
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
        ReleaseSetPiece(p);
        p.Pressing = false; p.Shielding = false; p.Dribbling = false; p.Sprinting = false;
        Add(EventKind.Card, $"{reason} - {p.Spec.DisplayName} ({ClubShort(p.Team)}) is off. " +
                            $"{active - 1} players left.");
        if (State.Controlled == p.Index) State.Controlled = FindNearestForTeam(p.Team, State.Ball.Pos, true);
        if (State.ControlledAway == p.Index) State.ControlledAway = FindNearestForTeam(p.Team, State.Ball.Pos, true);
        return true;
    }

    /// <summary>Phase 3: Header clearance — defender heads aerial ball away.</summary>
    /// <summary>A defender under pressure near his goal hacks it clear: long, lofted,
    /// towards the near touchline (it often goes out - a throw-in is a fine result).</summary>
    private void GroundClearance(PlayerState p)
    {
        var b = State.Ball;
        if (b.Owner != p.Index || b.HasPending) return;
        p.PossessionLock = .35f;
        ReleaseSetPiece(p);
        SetAction(p, "kick", .34f, .50f, "clear");
        int attack = SideSign(p.Team);
        float side = MathF.Abs(p.Pos.Z) > 4f ? MathF.Sign(p.Pos.Z) : (Rng.Next() < .5f ? -1f : 1f);
        Vector3 target = new(p.Pos.X + attack * Rng.Range(22f, 40f), 0, side * Rng.Range(Mx.HalfWidth * .55f, Mx.HalfWidth + 6f));
        Vector3 dir = Mx.FlatDir(b.Pos, target);
        float power = Rng.Range(17f, 25f) + p.Spec.Defending * 3f;
        b.HasPending = true; b.PendingKind = 1; b.PendingFrom = p.Index;
        b.PendingVel = dir * power + new Vector3(0, power * Rng.Range(.25f, .45f), 0);
        b.PendingSpin = new Vector3(0, Rng.Signed() * 2f, 0);
        b.PendingPos = p.Pos + dir * .55f + new Vector3(0, Mx.BallRadius + .03f, 0);
        b.PendingNoPickup = .3f;
        b.PendingReceiver = -1; b.PendingTarget = target;
        Add(EventKind.Info, $"{p.Spec.DisplayName} clears it!");
    }

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
            (p.Pos.Z >= 0 ? 1f : -1f) * (Mx.HalfWidth + 4f) // out towards the near touchline
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

    /// <summary>The set-piece taker has played the ball.  Under the laws he may not
    /// touch it again until another player has (the audit found ~10% double
    /// touches), so he is locked out of possession briefly.</summary>
    private void ReleaseSetPiece(PlayerState p)
    {
        if (p.MustPlayBall)
        {
            // Follow-through only; touching it again before anyone else is an
            // offence the referee punishes (EnforceRestartLaws), not prevented.
            p.PossessionLock = MathF.Max(p.PossessionLock, .35f);
            State.SetPieceTaker = p.Index;
            State.SetPieceLeftFoot = false;
            State.SetPieceTimer = 0f;
        }
        p.MustPlayBall = false;
    }

    /// <summary>On a penalty spot (11 m out, centred).</summary>
    private static bool AtPenaltySpot(Vector3 pos)
        => MathF.Abs(MathF.Abs(pos.X) - (Mx.HalfLength - 11f)) < .4f && MathF.Abs(pos.Z) < .4f;

    /// <summary>A computer penalty in an offline match, waiting to be struck.</summary>
    private bool AiPenaltyPending()
    {
        var S = State;
        if (Options.Mode == 3 || Options.AwayHuman || S.Phase != Phase.Play || S.Ball.Owner < 0 || S.ShootoutShotTaken) return false;
        var o = S.Players[S.Ball.Owner];
        return o.Team == 1 && o.MustPlayBall && AtPenaltySpot(S.RestartPos);
    }

    /// <summary>Is the ball being held for a throw-in (on a touchline)?</summary>
    /// <summary>The taker is standing over a corner kick.</summary>
    private bool IsCornerKick(PlayerState taker)
        => taker.MustPlayBall && MathF.Abs(State.Ball.Pos.X) > Mx.HalfLength - 2.5f
           && MathF.Abs(State.Ball.Pos.Z) > Mx.HalfWidth - 2.5f;

    /// <summary>Stick to corner zone: towards the near post -1, neutral 0 (penalty
    /// spot), across to the far post +1.</summary>
    private float CornerAim(PlayerState p, Vector2 stick)
    {
        if (stick.LengthSquared() < .1f) return 0f;
        float across = -MathF.Sign(State.Ball.Pos.Z) * stick.Y;   // stick.Y is world Z
        return across > .55f ? 1f : across < -.2f ? -1f : 0f;
    }

    /// <summary>7.2: a corner into the box: near post (6 m out), penalty spot (11 m)
    /// or far post (8 m), on a real arc, to the attacker best placed for it.</summary>
    private void CornerDelivery(PlayerState p, float zone)
    {
        var S = State;
        int attack = SideSign(p.Team);
        Vector3 goal = GoalPos(p.Team);
        float near = MathF.Sign(S.Ball.Pos.Z);
        Vector3 spot = zone < 0f ? new Vector3(goal.X - attack * 6f, 0, near * 2.5f)
                     : zone > 0f ? new Vector3(goal.X - attack * 8f, 0, -near * 4f)
                     : new Vector3(goal.X - attack * 11f, 0, near * .5f);
        PlayerState? best = null; float bd = float.MaxValue;
        foreach (var q in S.Players)
        {
            if (q.Team != p.Team || q.Index == p.Index || q.IsKeeper || q.SentOff) continue;
            float d = Mx.FlatDist(q.Pos, spot);
            if (d < bd) { bd = d; best = q; }
        }
        if (best == null) return;
        best.Target = spot;
        PassTo(p, best, 20f, false, true, spot);
    }

    private bool IsThrowInHold(PlayerState taker)
        => taker.MustPlayBall && MathF.Abs(State.Ball.Pos.Z) > Mx.HalfWidth - .6f
           && MathF.Abs(State.Ball.Pos.X) < Mx.HalfLength - 1.5f;

    private void AwardFreeKick(int side, Vector3 pos, bool penalty)
    {
        // Play stops: nobody carries on mid-tackle or mid-celebration through the
        // stoppage.  Only the fouled player (in "foul") keeps his reaction.
        foreach (var q in State.Players)
            if (q.Action != "foul") { q.Action = "idle"; q.ActionTimer = 0f; q.Pressing = false; q.JockeyState = 0; }
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
        // A throw-in is taken from the touchline itself, not a metre inside it.
        float zLimit = State.Phase == Phase.ThrowIn ? Mx.HalfWidth - .1f : Mx.HalfWidth - 1f;
        State.Ball.Pos = Mx.Clamp(pos.X, -Mx.HalfLength + 1f, Mx.HalfLength - 1f) * Vector3.UnitX
                        + new Vector3(0, Mx.BallRadius, Mx.Clamp(pos.Z, -zLimit, zLimit));
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
        State.RestartId++;
        // Your restart: the ring goes to the taker (it could stay on someone else,
        // so the throw / free kick button "did nothing").
        if (taker.Team == 0 && State.Controlled >= 0 && Options.Mode != ModeShootout) { State.Controlled = best; State.ControlLock = .5f; }
        else if (taker.Team == 1 && Options.AwayHuman && State.ControlledAway >= 0) State.ControlledAway = best;
        State.Ball.Owner = best;
        bool throwIn = State.Phase == Phase.ThrowIn;
        taker.Pos = throwIn
            ? new Vector3(State.Ball.Pos.X, 0, MathF.Sign(State.Ball.Pos.Z) * (Mx.HalfWidth + .35f)) // feet behind the line
            : State.Ball.Pos - new Vector3(SideSign(side) * .8f, 0, 0);
        taker.Vel = Vector3.Zero;
        taker.Target = taker.Pos;
        taker.PossessionLock = 0;
        // Free kick / throw-in / corner / goal kick: taker must play the ball.
        // Penalties too: the taker shoots from the spot (and an idle human's kick is
        // taken for him after 8 s instead of the shootout waiting forever).
        taker.MustPlayBall = State.Phase == Phase.FreeKick || State.Phase == Phase.ThrowIn
                             || State.Phase == Phase.Corner || State.Phase == Phase.GoalKick
                             || penalty;
        taker.Facing = throwIn ? new Vector3(0, 0, -MathF.Sign(State.Ball.Pos.Z)) : Mx.FlatDir(taker.Pos, GoalPos(side));
        // Phase 2.8: set-piece routines.
        bool isCorner = MathF.Abs(State.Ball.Pos.X) > Mx.HalfLength - 3f && MathF.Abs(State.Ball.Pos.Z) > Mx.HalfWidth - 3f;
        bool isThrowIn = State.Phase == Phase.ThrowIn;
        if (isCorner)
        {
            // Corner routine: every tall/forward player attacks a zone (near post,
            // penalty spot, far post, edge of the six-yard box); the rest hold.
            {
                int zi = 0; float nearZ = MathF.Sign(State.Ball.Pos.Z); int atk = SideSign(side); float gxa = GoalPos(side).X;
                Vector3[] zones = {
                    new(gxa - atk * 6f, 0, nearZ * 2.5f), new(gxa - atk * 11f, 0, 0f),
                    new(gxa - atk * 8f, 0, -nearZ * 4f), new(gxa - atk * 5.5f, 0, -nearZ * .5f),
                    new(gxa - atk * 15f, 0, nearZ * 5f) };
                foreach (var q in State.Players.Where(q => q.Team == side && q.Index != best && !q.IsKeeper && !q.SentOff)
                                               .OrderByDescending(q => (q.Spec.Height - 1.8f) * 3f + (q.Role == Role.Forward ? .3f : q.Role == Role.Defender ? .15f : 0f)))
                {
                    if (zi >= zones.Length) break;
                    q.Target = zones[zi++];
                }
            }
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
        // Opponents back the required distance: 9.15 m at free kicks, corners and
        // goal kicks (was 4 m), 2 m at a throw-in.  MovePlayer keeps them there
        // until the ball is played.
        float keepOff = throwIn ? 2f : 9.15f;
        foreach (var q in State.Players)
        {
            if (q.Team == side || q.SentOff || (penalty && q.IsKeeper)) continue;
            float qd = Mx.FlatDist(q.Pos, State.Ball.Pos);
            if (qd < keepOff)
            {
                q.Pos = OutsideCircle(State.Ball.Pos, qd > .05f ? q.Pos : OwnGoalPos(q.Team), keepOff + .3f);
                q.Target = q.Pos;
            }
        }
        // Goal kick / defending free kick in its own area: opponents outside the area.
        if (!penalty && !throwIn && taker.MustPlayBall && OwnAreaRestart(taker))
        {
            float ogx = OwnGoalPos(side).X;
            foreach (var q in State.Players)
                if (q.Team != side && !q.SentOff && InArea(q.Pos, ogx, .5f)) { q.Pos = OutsideArea(q.Pos, ogx); q.Target = q.Pos; }
        }
        // Penalty in a match: everyone except the taker and the keeper outside the
        // area and the arc.
        if (penalty && Options.Mode != ModeShootout)
        {
            float gx = MathF.Sign(State.Ball.Pos.X) * Mx.HalfLength;
            foreach (var q in State.Players)
            {
                if (q.Index == best || q.SentOff || (q.IsKeeper && q.Team != side)) continue;
                bool inArea = MathF.Abs(q.Pos.X - gx) < 16.5f + .5f && MathF.Abs(q.Pos.Z) < 20.16f + .5f;
                bool inArc = Mx.FlatDist(q.Pos, State.Ball.Pos) < 9.15f;
                if (inArea || inArc)
                {
                    q.Pos = new Vector3(gx - MathF.Sign(gx) * 18.5f, 0, Mx.Clamp(q.Pos.Z, -20f, 20f));
                    q.Target = q.Pos;
                }
            }
            var gkDef = State.Players[(1 - side) * Options.TeamSize];
            if (!gkDef.SentOff) { gkDef.Pos = new Vector3(gx - MathF.Sign(gx) * .3f, 0, 0); gkDef.Target = gkDef.Pos; }
        }
        State.Phase = Phase.Play;
        if (penalty)
        {
            // Shootout: the human side takes their own penalties; AI shoots at once.
            if (Options.Mode != 3)
            {
                // 7.3: match penalties use the shootout model - you aim and strike your
                // own (auto-taken after 8 s), and dive with your keeper on theirs.
                State.ShootoutTakerSide = side; State.ShootoutShotTaken = false;
                State.ShootoutTimer = 0f; State.ShootoutDive = 0;
                if (side == 0 || Options.AwayHuman)
                {
                    if (side == 0) { State.Controlled = best; State.ControlLock = .4f; }
                    Add(EventKind.Info, "Your penalty — aim with the stick, hold shoot and release.");
                }
                else Add(EventKind.Info, "Their penalty — hold left or right to dive, centre to stay big.");
            }
            else if (side == 0) Add(EventKind.Info, "Your penalty — aim and shoot!");
            else { State.ShootoutDive = 0; Add(EventKind.Info, "Their penalty — hold left or right to dive, centre to stay big."); }
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
            // Calibrated against real tracking (SkillCorner open data, A-League): players
            // averaged 2.1 m/s and sprinted (>7 m/s) 0.6% of the time; ours ran 4.3 m/s
            // and sprinted 11%.  Off the ball a player now walks/jogs to a target that is
            // close, runs to one further away, and sprints only to a far target or a duel.
            float dist = d.Length();
            // (a forward attacking the box for a cross - RunType 5 - also goes hard)
            bool urgent = p.Pressing || State.Ball.Owner == p.Index || (p.RunType == 5 && State.Ball.Owner >= 0)
                          || (State.Ball.Owner < 0 && Mx.FlatDist(p.Target, BallFocus()) < 3f);
            sprint = !human && (dist > (urgent ? 5f : 20f) || p.Pressing) && p.Stamina > .25f;
            if (!urgent && !sprint && wish.LengthSquared() > 0f)
            {
                // Arrival in real units: walk (<2 m away), jog (~2.5-3.5 m/s up to 10 m),
                // run (~5 m/s) to 20 m; sprint beyond (above).
                float want = dist < 2f ? 1.0f + dist * .35f : dist < 10f ? 2.2f + (dist - 2f) * .16f : 3.5f + MathF.Min(1f, (dist - 10f) / 10f) * 1.6f;
                float top = p.MaxSpeed * Mx.Lerp(.72f, 1f, p.Stamina);
                wish *= MathF.Min(1f, want / MathF.Max(1f, top));
            }
        }
        // Restart taker must play the ball, not run off with it.
        // An AI taker stands over the ball until he plays it.  A human is free to
        // move: carrying it away is a free kick against him (EnforceRestartLaws),
        // and opponents are free to encroach and be cautioned for it.
        bool stick = human && cmd.Move.LengthSquared() > .01f;
        // Contain: hold A (E) without the ball - the player moves goal-side of the
        // carrier and stays 2 m off him.  The stick still overrides.
        if (human && !stick && cmd.Contain && State.Ball.Owner >= 0 && State.Players[State.Ball.Owner].Team != p.Team)
        {
            var c = State.Players[State.Ball.Owner];
            Vector3 spot = c.Pos + Mx.FlatDir(c.Pos, OwnGoalPos(p.Team)) * 2f;
            wish = Mx.Flat(spot - p.Pos).Length() > .3f ? Mx.Norm(Mx.Flat(spot - p.Pos)) : Vector3.Zero;
            p.Facing = Mx.FlatDir(p.Pos, c.Pos);
        }
        if (human && p.JockeyState > 0) { sprint = false; }
        if (p.MustPlayBall && !stick) { wish = Vector3.Zero; p.Vel = Vector3.Zero; }   // only the stick moves a taker
        // Shootout: the stick aims the kick; the taker stays on the spot.  Walking
        // off with it turned the shootout into a free kick and open play.
        if (IsShootout && p.MustPlayBall) { wish = Vector3.Zero; p.Vel = Vector3.Zero; }
        if (!stick && State.Ball.Owner >= 0 && State.Ball.Owner != p.Index)
        {
            // AI players (and the assist when a human lets go of the stick) go
            // round the restart circle rather than through it - by choice; a human
            // steering into it is free to, and is cautioned.
            var holder = State.Players[State.Ball.Owner];
            if (holder.MustPlayBall && holder.Team != p.Team && wish.LengthSquared() > 0f)
            {
                // Wide margin: players carry momentum (turns are weight-limited), so
                // they must start steering away well before the 9.15 m line.
                float need = RestartDistance(holder) + 1.6f;
                Vector3 next = p.Pos + wish * 2f;
                if (Mx.FlatDist(next, State.Ball.Pos) < need)
                {
                    Vector3 rim = State.Ball.Pos + Mx.FlatDir(State.Ball.Pos, p.Pos) * need;
                    Vector3 tangent = new(-(rim - State.Ball.Pos).Z, 0, (rim - State.Ball.Pos).X);
                    wish = Mx.Norm(Mx.Flat(rim - p.Pos) + Mx.Norm(tangent) * MathF.Sign(Vector3.Dot(tangent, wish) + 1e-4f));
                }
            }
        }
        p.Sprinting = sprint;
        float fatigue = Mx.Lerp(.72f, 1f, p.Stamina);
        // Phase 2.9 preset: Authentic is slightly slower, Competitive faster.
        float presetPace = Options.Preset == MatchPreset.Authentic ? .94f : 1.03f;
        float speed = p.MaxSpeed * fatigue * presetPace * (sprint ? 1.42f : 1f) * (p.Pressing ? 1.12f : 1f);
        if (p.Action == "tackle") speed *= 1.35f;
        if (human && p.JockeyState > 0) speed *= .72f;           // jockeying: short side-on steps
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
        // Shared authoritative core integration (gravity, Magnus, knuckleball,
        // drag, wind, air/ground friction, bounce). Collisions/outcomes below.
        ArenaFC.Core.Football.BallTrajectory.Step(ref b.Pos, ref b.Vel, ref b.Spin, dt,
            Weather.Raining, Weather.WindX, Weather.WindZ, Rng.Signed);

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
            // Measured from his chest, not his boots: a shot at the bar straight at
            // him (2 m up) used to be out of a standing keeper's reach.
            float d = (p.Pos + new Vector3(0, .9f, 0) - b.Pos).Length();
            float reach = p.Action == "dive" ? 1.70f : 1.20f;
            // A penalty dive you committed to: full stretch the way you went (a keeper
            // covers ~2.5 m sideways), nothing extra the other way.
            if (State.ShootoutShotTaken && State.ShootoutTakerSide == 1 && p.Team == 0 && !Options.AwayHuman && State.ShootoutDive != 0
                && MathF.Sign(b.Pos.Z - p.Pos.Z) == State.ShootoutDive)
                reach = 2.4f;
            if (d < reach && b.Pos.Y < 2.5f && b.FreeTime > .1f && !GoingWide(p))
            {
                float spd = b.Vel.Length();
                bool diving = p.Action == "dive";
                // Hold it when he can: a shot straight at him at a sane pace is caught;
                // a stretching dive or a rocket is pushed away.  (Every shot over
                // 18 m/s used to be parried: 45 of 79 shots.)
                float catchChance = Mx.Clamp(1f - (spd - 15f) / 20f, 0f, 1f) * (diving ? .45f : 1f) * (d < .75f ? 1f : .65f);
                if (spd > 10f && Rng.Next() > catchChance)
                {
                    // Parry: either back out into play or tipped round the post /
                    // over the bar for a corner.  The keeper is the last touch (it
                    // used to stay with the shooter, so a parry out was a goal kick).
                    float sign = SideSign(p.Team);
                    b.LastTouch = p.Index; b.LastTouchSide = p.Team;
                    if (Rng.Next() < .60f)
                    {
                        float side = b.Pos.Z >= p.Pos.Z ? 1f : -1f;
                        bool overBar = b.Pos.Y > 1.6f && Rng.Next() < .5f;
                        // Own goal is at -sign: a tip keeps travelling towards the goal
                        // line, but high (over the bar) or wide (round the post).
                        b.Vel = overBar
                            ? new Vector3(-sign * spd * .30f, 7.0f, Rng.Signed() * 1.5f)
                            : new Vector3(-sign * spd * .18f, 1.2f, side * spd * .45f);
                    }
                    else
                        // Back out into play, away from goal.  This used to be -sign,
                        // i.e. towards his own net ("parries it away!" ... GOAL).
                        b.Vel = new Vector3(sign * spd * .35f, 3.0f,
                            (b.Pos.Z - p.Pos.Z) * 4.0f + Rng.Signed() * 3f);
                    b.NoPickup = .15f;
                    SetAction(p, "parry", .60f, .50f);
                    Add(EventKind.Save, $"{p.Spec.DisplayName} parries it away!");
                    return;
                }
                b.Owner = p.Index;
                b.LastTouch = p.Index; b.LastTouchSide = p.Team;
                p.PossessionLock = .15f;
                SetAction(p, "catch", .40f, .50f);
                Add(EventKind.Save, $"{p.Spec.DisplayName} makes the save!");
                return;
            }
        }

        // --- Out of play ---
        // (Not while a throw-in is being thrown: the ball is in the taker's hands,
        // over the line - it used to give another throw-in before it left them.)
        bool throwing = b.HasPending && b.PendingKind == 1 && b.PendingPos.Y > 1.5f;   // only a throw starts at head height
        if (MathF.Abs(b.Pos.Z) > Mx.HalfWidth + .2f && !throwing)
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
        if (IsSkill) { SkillGoal(side); State.PhaseTimer = 1.4f; }
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
        // High balls (above 1.55 m) used to be unplayable by anyone: now they can be
        // headed up to each player's jumping reach, and contested in the air.
        if (b.FreeTime < .08f || b.NoPickup > 0f || b.Pos.Y > 3.2f) return;   // (3.2: a keeper's hands)
        bool high = b.Pos.Y > 1.55f;
        int best = -1; float bd = 1.05f * 1.05f, bestAir = float.MinValue;
        foreach (var p in State.Players)
        {
            if (!IsActive(p)) continue;
            if (p.PossessionLock > 0f) continue;
            if (b.PassReceiver == p.Index && b.FreeTime < .05f) continue;
            float d = Mx.FlatDist2(p.Pos, b.Pos);
            if (high)
            {
                // 6.5: a keeper in his own area claims high balls with his hands -
                // he used to be excluded from every ball above 1.55 m.
                if (p.IsKeeper)
                {
                    if (!InArea(p.Pos, OwnGoalPos(p.Team).X, 0f) || b.Pos.Y > p.Spec.Height + 1.3f || d > 1.6f * 1.6f) continue;
                    float kAir = AerialScore(p, b.Pos) + 2.5f;
                    if (kAir > bestAir) { bestAir = kAir; best = p.Index; }
                    continue;
                }
                if (b.Pos.Y > HeaderReach(p) || d > 1.4f * 1.4f) continue;
                float air = AerialScore(p, b.Pos);
                if (air > bestAir) { bestAir = air; best = p.Index; }
                continue;
            }
            if (p.IsKeeper && GoingWide(p)) continue;    // he lets a wide one go
            float radius = p.IsKeeper ? 1.5f : 1.0f;
            if (d < radius * radius && d < bd) { bd = d; best = p.Index; }
        }
        if (high && best >= 0 && State.Players[best].IsKeeper)
        {
            var k = State.Players[best];
            // Catch it, or punch it clear when an attacker is challenging him.
            bool challenged = State.Players.Any(q => q.Team != k.Team && !q.SentOff && Mx.FlatDist(q.Pos, b.Pos) < 1.3f);
            if (challenged && Rng.Next() < .45f)
            {
                Vector3 away = Mx.Norm(Mx.Flat(b.Pos - OwnGoalPos(k.Team)) + new Vector3(0, 0, Rng.Signed() * .4f));
                b.Vel = away * Rng.Range(12f, 17f) + new Vector3(0, Rng.Range(4f, 7f), 0);
                b.NoPickup = .25f; b.FreeTime = 0f; b.PassReceiver = -1;
                b.LastTouch = k.Index; b.LastTouchSide = k.Team; b.LastTouchPos = b.Pos;
                SetAction(k, "parry", .5f, .4f);
                Add(EventKind.Save, $"{k.Spec.DisplayName} punches it clear!");
            }
            else
            {
                b.Owner = k.Index; b.Vel = Vector3.Zero; b.HasPending = false; b.PassReceiver = -1;
                b.LastTouch = k.Index; b.LastTouchSide = k.Team;
                k.PossessionLock = .4f;
                SetAction(k, "catch", .6f, .3f);
                Add(EventKind.Save, $"{k.Spec.DisplayName} comes and claims it.");
            }
            return;
        }
        if (high && best >= 0)
        {
            var w = State.Players[best];
            foreach (var q in State.Players)       // the loser of the duel jumps too
                if (q.Index != best && !q.SentOff && q.Team != w.Team && Mx.FlatDist(q.Pos, b.Pos) < 1.6f)
                    SetAction(q, "header", .5f, .5f);
            bool human = w.Index == State.Controlled || (Options.AwayHuman && w.Index == State.ControlledAway);
            if (!human)
            {
                // AI winners don't try to cushion a high ball: attackers go for goal,
                // defenders head it clear, everyone else heads it on.
                if (Mx.FlatDist(w.Pos, GoalPos(w.Team)) < 18f) { FirstTimeStrike(w, true, Rng.Range(.45f, .9f), Vector2.Zero); return; }
                if (Mx.FlatDist(w.Pos, OwnGoalPos(w.Team)) < Mx.HalfLength) { HeaderClearance(w); if (b.HasPending) return; }
                FirstTimeStrike(w, false, .5f, Vector2.Zero);
                return;
            }
        }
        if (best >= 0)
        {
            var p = State.Players[best];
            // Phase 0.2 first touch: aerial/fast balls play a trap/chest/header
            // clip and possession completes at ball_contact. Slow ground balls
            // are collected instantly so the game keeps flowing.
            // Phase 2.1: first-touch quality from pressure, stamina, skill.
            float ballSpeed = b.Vel.Length();
            // A fast ball from the other side (a pass cut out, a shot or clearance
            // blocked) often comes off him rather than sticking: deflections are
            // where most real throw-ins and corners come from (we had ~2 and ~3 a match).
            if (!p.IsKeeper && b.LastTouchSide >= 0 && b.LastTouchSide != p.Team && ballSpeed > 6.5f && !b.HasPending)
            {
                bool strike = b.PassReceiver < 0;            // shot or clearance
                bool crossIn = b.Pos.Y > .6f && Mx.FlatDist(p.Pos, OwnGoalPos(p.Team)) < 20f;
                if (crossIn) strike = true;                  // a cross into his box: block / head it away
                float deflect = Mx.Clamp((ballSpeed - 6.5f) / 12f, 0f, 1f) * (strike ? .85f : .50f) * (1.2f - p.Spec.Defending * .4f);
                if (Rng.Next() < deflect)
                {
                    Vector3 hv = Mx.Flat(b.Vel);
                    // A shot or cross blocked near his own goal mostly carries on, off
                    // line - often behind for a corner; a pass cut out in midfield
                    // squirts sideways.
                    bool nearOwnGoal = Mx.FlatDist(p.Pos, OwnGoalPos(p.Team)) < 25f;
                    float ang = (nearOwnGoal ? Rng.Range(.15f, .8f) : Rng.Range(.45f, 1.4f)) * (Rng.Next() < .5f ? -1f : 1f);
                    float c = MathF.Cos(ang), sn = MathF.Sin(ang);
                    Vector3 nd = Mx.Norm(new Vector3(hv.X * c - hv.Z * sn, 0, hv.X * sn + hv.Z * c));
                    float keep = Rng.Range(.35f, .65f);
                    b.Vel = nd * (ballSpeed * keep) + new Vector3(0, Rng.Range(.8f, 3f), 0);
                    b.NoPickup = .18f; b.FreeTime = 0f;
                    b.LastTouch = p.Index; b.LastTouchSide = p.Team; b.LastTouchPos = b.Pos;
                    b.PassReceiver = -1; b.PassFrom = -1;
                    p.PossessionLock = .2f;
                    if (p.ActionTimer <= 0f) SetAction(p, "block", .4f, .3f);
                    Add(EventKind.Info, strike ? $"Blocked by {p.Spec.DisplayName}!" : $"{p.Spec.DisplayName} gets a touch - it's loose!");
                    return;
                }
            }
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
                // Foot below 0.45 m, thigh/knee to 0.95 m, chest to 1.55 m, head above.
                touchAction = TouchFor(b.Pos.Y, b.Vel.Y);
                contactFrac = touchAction == "trap" ? .60f : .55f;
                SetAction(p, touchAction, .50f, contactFrac);
                p.Target = b.Pos; // plant feet on the spot
                // A ground ball is cushioned by the receiving foot: it slows into his
                // stride instead of rolling on at pass speed while the touch plays.
                if (touchAction == "trap")
                {
                    Vector3 hv = Mx.Flat(b.Vel);
                    float keep = Mx.Lerp(.45f, .20f, quality);
                    b.Vel = new Vector3(hv.X * keep, b.Vel.Y, hv.Z * keep);
                    p.Target = b.Pos + Mx.Flat(b.Vel) * .3f;
                }
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
            bool intercepted = b.LastTouchSide >= 0 && b.LastTouchSide != p.Team;
            b.Owner = best;
            b.Vel = Vector3.Zero;
            b.Spin = Vector3.Zero;
            b.FreeTime = 0;
            p.PossessionLock = .12f;
            b.LastTouch = best; b.LastTouchSide = p.Team; b.LastTouchPos = b.Pos;
            if (p.Team == 0) State.Controlled = best;
            if (intercepted)
            {
                RecordActionContract(p, "intercept", 0.35f, 0.5f, "intercept");
            }
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
    // PR C: tactical coordinator cache + hysteresis
    private readonly ArenaFC.Core.Football.TacticalCoordinator _tactical = new();
    private int _tacticalTick = -1;
    private readonly Dictionary<int, ArenaFC.Core.Football.TacticalCoordinator.Assignment> _tacticalByPlayer = new();
    public int TacticalRoleChanges;
    public int TacticalPressAssignments;
    public int TacticalCoverAssignments;
    public readonly Dictionary<int, ArenaFC.Core.Football.PlayerActionContract> LastActionContracts = new();

    private ArenaFC.Core.Football.BallTrajectory? _tacticalBallPred;
    private ArenaFC.Core.Football.BallTrajectory? _ballPredLong;
    private int _ballPredLongTick = -1;
    private float _ballPredLongHorizon;

    private ArenaFC.Core.Football.BallTrajectory BallPred(float horizonSeconds)
    {
        float h = Math.Clamp(horizonSeconds, 0.1f, 3.0f);
        if (_tacticalTick == _tick && _tacticalBallPred != null && h <= 0.8f) return _tacticalBallPred;
        if (_ballPredLongTick == _tick && _ballPredLong != null && _ballPredLongHorizon >= h - 0.001f)
            return _ballPredLong;
        _ballPredLongHorizon = MathF.Max(h, 2.5f);
        _ballPredLong = ArenaFC.Core.Football.BallTrajectory.Predict(
            State.Ball.Pos, State.Ball.Vel, State.Ball.Spin, _ballPredLongHorizon, Weather.Raining, Weather.WindX, Weather.WindZ);
        _ballPredLongTick = _tick;
        return _ballPredLong;
    }

    private ArenaFC.Core.Football.TacticalCoordinator.Assignment? GetTacticalAssignment(int playerIndex)
    {
        if (_tacticalTick != _tick)
        {
            var prev = new Dictionary<int, string>(_tacticalByPlayer.Count);
            foreach (var kv in _tacticalByPlayer) prev[kv.Key] = kv.Value.Role;
            _tacticalTick = _tick;
            _tacticalByPlayer.Clear();
            // M3: coordinator sees predicted ball trajectory (same physics rules).
            _tacticalBallPred = ArenaFC.Core.Football.BallTrajectory.Predict(
                State.Ball.Pos, State.Ball.Vel, State.Ball.Spin, 0.8f, Weather.Raining, Weather.WindX, Weather.WindZ);
            var t0 = _tactical.BuildAssignments(State, 0, _tacticalBallPred);
            var t1 = _tactical.BuildAssignments(State, 1, _tacticalBallPred);
            void Add(ArenaFC.Core.Football.TacticalCoordinator.Assignment a)
            {
                if (prev.TryGetValue(a.PlayerIndex, out var oldRole) && oldRole != a.Role) TacticalRoleChanges++;
                if (a.Role == "press") TacticalPressAssignments++;
                else if (a.Role == "cover") TacticalCoverAssignments++;
                _tacticalByPlayer[a.PlayerIndex] = a;
            }
            foreach (var a in t0) Add(a);
            foreach (var a in t1) Add(a);
        }
        return _tacticalByPlayer.TryGetValue(playerIndex, out var asn) ? asn : null;
    }

    internal void ResetTacticalCache()
    {
        _tacticalTick = -1;
        _tacticalByPlayer.Clear();
        _tacticalBallPred = null;
        _ballPredLong = null;
        _ballPredLongTick = -1;
        _ballPredLongHorizon = 0f;
        _tactical.ClearState();
        TacticalRoleChanges = 0;
        TacticalPressAssignments = 0;
        TacticalCoverAssignments = 0;
        LastActionContracts.Clear();
    }

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

    /// <summary>xG of a shot from <paramref name="from"/> by <paramref name="team"/>.</summary>
    public float XgFrom(Vector3 from, int team, bool oneOnOne)
    {
        var goal = GoalPos(team);
        float distance = Mx.FlatDist(from, goal);
        float dx = MathF.Max(.1f, MathF.Abs(goal.X - from.X));
        float goalAngle = MathF.Abs(MathF.Atan2(Mx.GoalHalfWidth - from.Z, dx) - MathF.Atan2(-Mx.GoalHalfWidth - from.Z, dx));
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
