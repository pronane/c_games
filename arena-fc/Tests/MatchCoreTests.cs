// Regression suite for the pure-C# match simulation.
//
// Bug this guards: Tick() used to release the ball whenever the *owner's*
// PossessionLock was greater than zero.  Both TryPossession() and
// AttemptTackle() set that lock when possession is gained, so the ball was
// dropped on the very next tick.  A 60-second unattended 11v11 match produced
// 653 ownership changes, an endless midfield scrum, and no goals.  This is
// what the 02.11.2026 screen recording showed (0-0, "X wins the ball!"
// repeating, the ball never leaving the centre circle for long).
//
// Run: dotnet run --project Tests/MatchCoreTests.csproj -c Release
using System.Numerics;
using System.Reflection;
using System.Text.Json;
using ArenaFC.Core;
using ArenaFC.Core.Animation;

int passed = 0, failed = 0;
void Check(string name, bool ok, string? detail = null)
{
    if (ok) { passed++; Console.WriteLine($"  PASS  {name}"); }
    else { failed++; Console.WriteLine($"  FAIL  {name} {detail}"); }
}
void Section(string s) => Console.WriteLine($"\n== {s} ==");

Section("Possession stability (60 real seconds, 11v11, seed 2026)");
var pos = new MatchEngine(new MatchOptions { Seed = 2026, TimeSpeed = 15f });
int flips = 0, prevOwner = pos.State.Ball.Owner, longestHold = 0, hold = 0;
int tackles = 0, nearTicks = 0, fouls = 0, nearBallTotal = 0;
string prevComment = pos.State.Commentary;
for (int i = 0; i < 3600; i++)
{
    pos.Step(1f / 60f, PlayerCommand.None);
    int o = pos.State.Ball.Owner;
    if (o != prevOwner) { flips++; prevOwner = o; hold = 0; }
    else if (o >= 0) { hold++; longestHold = Math.Max(longestHold, hold); }
    if (pos.State.Commentary != prevComment)
    {
        // A won tackle is either a clean pick-up or a poke loose.
        if (pos.State.Commentary.Contains("wins the ball!") || pos.State.Commentary.Contains("pokes it away!")) tackles++;
        if (pos.State.Commentary.StartsWith("Foul!")) fouls++;
        prevComment = pos.State.Commentary;
    }
    if (o >= 0)
    {
        var carrier = pos.State.Players[o];
        float nearest = 1e9f;
        foreach (var q in pos.State.Players)
            if (q.Team != carrier.Team && !q.IsKeeper)
                nearest = MathF.Min(nearest, Mx.FlatDist(q.Pos, carrier.Pos));
        if (nearest < 2f) nearTicks++;
    }
    foreach (var p in pos.State.Players)
        if (Mx.FlatDist(p.Pos, pos.State.Ball.Pos) < 4f) nearBallTotal++;
}
float avgNearBall = nearBallTotal / 3600f;
// Before the possession fix: flips=653, longestHold=376.
// Before the pressing fix: tackles=7, nearTicks=579.
// Before the spacing/foul fix: avgNearBall=2.62, fouls=4 with no visible contact.
// Phase 0 first-touch delay (ball loose ~0.25 s during trap) draws players in
// slightly, so the baseline moved 2.55 -> 2.58; 2.60 stays below the 2.62 bad mark.
Check("ball does not flip owner every few ticks", flips < 100, $"flips={flips}");
Check("a carrier can dribble for several seconds", longestHold > 180,
      $"longest={longestHold} ticks");
Check("opposition closes down the carrier", nearTicks > 400, $"nearTicks={nearTicks}");
// Real football is ~25-60 won tackles a match (4-10 per 15 game minutes).  The
// old floor of 10 encoded the every-defender-lunges scrum (~120 a match).
// One minute of one seed is too noisy for a rate (a seed can see 1 or 8), so
// average four seeds.
int tackleTotal = tackles;
for (int ts = 2027; ts <= 2029; ts++)
{
    var tm = new MatchEngine(new MatchOptions { Seed = ts, TimeSpeed = 15f });
    string pc = "";
    for (int i = 0; i < 3600; i++)
    {
        tm.Step(1f / 60f, PlayerCommand.None);
        if (tm.State.Commentary != pc && (tm.State.Commentary.Contains("wins the ball!") || tm.State.Commentary.Contains("pokes it away!"))) tackleTotal++;
        pc = tm.State.Commentary;
    }
}
Check("opposition wins the ball back", tackleTotal / 4f >= 3f, $"avg tackles={tackleTotal / 4f:0.0} (seed 2026: {tackles})");
Check("free kicks are not handed out for invisible fouls", fouls <= 3, $"fouls={fouls}");
Check("players keep personal space around the ball", avgNearBall < 2.60f,
      $"avgWithin4m={avgNearBall:F3}");

Section("Action pose timing");
float passStartPose = ActionTiming.ContactEnvelope(0f, .34f, .17f);
float passContactPose = ActionTiming.ContactEnvelope(.17f, .34f, .17f);
float passEndPose = ActionTiming.ContactEnvelope(.34f, .34f, .17f);
float earlyContactPose = ActionTiming.ContactEnvelope(.2f, .5f, .2f);
float midpointPose = ActionTiming.ContactEnvelope(.25f, .5f, .2f);
float passPlaybackScale = ActionTiming.ContactAlignedPlaybackScale(25f / 30f, .5f, .17f);
float passEventTime = .5f * (25f / 30f) / passPlaybackScale;
Check("action pose starts and ends neutral and peaks at contact",
      passStartPose < .001f && passContactPose > .999f && passEndPose < .001f,
      $"start={passStartPose:F3} contact={passContactPose:F3} end={passEndPose:F3}");
Check("action pose peak follows a non-midpoint contact time",
      earlyContactPose > .999f && earlyContactPose > midpointPose,
      $"contact={earlyContactPose:F3} midpoint={midpointPose:F3}");
Check("one-shot clip contact lands on the scheduled simulation time",
      MathF.Abs(passEventTime - .17f) < .001f && passPlaybackScale > 1.8f,
      $"event={passEventTime:F3}s speed={passPlaybackScale:F2}x");

Section("Gait joint sign convention");
// A leg bone points down; +X rotation sends it BEHIND the player (-Z).  Forward
// thigh swing must be negative, knee flexion positive.  See Scripts/Core/Gait.cs.
var runPose = Gait.Compute(6f, MathF.PI * .5f, 0f);
var idlePose = Gait.Compute(0f, 1f, 0f);
Check("the leading thigh swings forward (negative X)", runPose.HipL < -.3f,
      $"hipL={runPose.HipL:F3}");
Check("the trailing thigh swings back", runPose.HipR > .3f, $"hipR={runPose.HipR:F3}");
Check("both knees bend (positive X)", runPose.KneeL > .3f && runPose.KneeR > .05f,
      $"knees={runPose.KneeL:F3}/{runPose.KneeR:F3}");
Check("ankles counter-rotate so boots stay flat", runPose.FootL < 0f,
      $"footL={runPose.FootL:F3}");
Check("knees remain slightly bent when walking/standing", idlePose.KneeL > .05f,
      $"idleKnee={idlePose.KneeL:F3}");

Section("A collected loose ball stays collected");
var stick = new MatchEngine(new MatchOptions { Seed = 7 });
stick.State.Phase = Phase.Play;
stick.State.PhaseTimer = 0f;
stick.State.Ball.Owner = -1;
stick.State.Ball.Vel = Vector3.Zero;
stick.State.Ball.Spin = Vector3.Zero;
stick.State.Ball.FreeTime = .2f;
stick.State.Ball.NoPickup = 0f;
var near = stick.State.Players[5];
stick.State.Ball.Pos = new Vector3(near.Pos.X + .4f, Mx.BallRadius, near.Pos.Z);
int firstOwner = -1, heldTicks = 0;
for (int i = 0; i < 30; i++)
{
    stick.Step(1f / 60f, PlayerCommand.None);
    if (i == 0) firstOwner = stick.State.Ball.Owner;
    if (firstOwner >= 0 && stick.State.Ball.Owner == firstOwner) heldTicks++;
}
// Before the fix: held=4/30.  After: held=30/30.
Check("the player who collected the ball keeps it", heldTicks >= 25,
      $"owner={firstOwner} held={heldTicks}/30");

Section("A human who plays can shoot");
var human = new MatchEngine(new MatchOptions { Seed = 2026, TimeSpeed = 15f });
for (int i = 0; i < 3600; i++)
{
    var cmd = PlayerCommand.None;
    int ctrl = human.State.Controlled;
    if (ctrl >= 0)
    {
        var p = human.State.Players[ctrl];
        if (human.State.Ball.Owner == ctrl)
        {
            float distGoal = Mx.FlatDist(p.Pos, human.GoalPos(p.Team));
            if (distGoal < 24f) { cmd.Shoot = true; cmd.Charge = .8f; }
            else
            {
                var d = Mx.FlatDir(p.Pos, human.GoalPos(p.Team));
                cmd.Move = new Vector2(d.X, d.Z);
                cmd.Sprint = true;
            }
        }
        else
        {
            var d = Mx.FlatDir(p.Pos, human.State.Ball.Pos);
            cmd.Move = new Vector2(d.X, d.Z);
            cmd.Tackle = true;
        }
    }
    human.Step(1f / 60f, cmd);
}
Check("controlled player produces shots", human.State.Shots[0] + human.State.Shots[1] > 0,
      $"shots={human.State.Shots[0] + human.State.Shots[1]}");

Section("New defensive actions (slide / shield / first-touch pass)");
var actions = new MatchEngine(new MatchOptions { Seed = 33, TimeSpeed = 15f });
for (int i = 0; i < 600; i++)
{
    var c = new PlayerCommand
    {
        Move = new Vector2(MathF.Sin(i * .05f), MathF.Cos(i * .05f)),
        Slide = i % 90 == 0,
        Shield = i % 3 == 0,
        Pass = i % 120 == 0,
        Tackle = i % 150 == 0,
        Sprint = i % 4 == 0,
    };
    actions.Step(1f / 60f, c);
}
Check("slide/shield/tackle commands keep the match finite",
      Mx.IsFinite(actions.State.Ball.Pos) && Mx.IsFinite(actions.State.Ball.Vel)
      && actions.State.Players.All(p => Mx.IsFinite(p.Pos)));
Check("new commands do not corrupt the scoreboard",
      actions.State.Score.All(s => s >= 0 && s < 100));


Section("06.11.2026: one-shot human actions survive a fixed tick");
// The old engine only sampled human button edges on an AI decision tick (every
// 0.08-0.18 s).  DecisionTimer=10 proves these actions now fire immediately.
MatchEngine Playable(int owner = 0, float mateDistance = 8f)
{
    var e = new MatchEngine(new MatchOptions { Seed = 2026, TimeSpeed = 15f });
    e.State.Phase = Phase.Play;
    e.State.PhaseTimer = 0f;
    e.State.ControlLock = 10f;          // no auto-switch while testing one player
    e.State.Controlled = 0;
    var me = e.State.Players[0];
    me.DecisionTimer = 10f;
    me.PossessionLock = 0f;
    me.TackleLock = 0f;
    me.Stamina = 1f;
    me.Facing = new Vector3(1f, 0f, 0f);
    me.Target = me.Pos;
    var mate = e.State.Players[1];
    mate.Pos = me.Pos + new Vector3(mateDistance, 0f, 2f);
    var b = e.State.Ball;
    b.Owner = owner;
    b.Vel = Vector3.Zero; b.Spin = Vector3.Zero;
    b.FreeTime = .2f; b.NoPickup = 0f;
    b.PassFrom = -1; b.PassReceiver = -1;
    b.Pos = new Vector3(me.Pos.X + .4f, Mx.BallRadius, me.Pos.Z);
    return e;
}

var pass = Playable();
pass.Step(1f / 60f, new PlayerCommand { Pass = true });
// The kick starts (wind-up) on the first tick; the pass is counted when the
// ball leaves the foot.
Check("short pass fires on the first tick outside the AI decision clock",
      pass.State.Ball.HasPending && pass.State.Ball.PendingKind == 1 && pass.State.Ball.PendingReceiver >= 0,
      $"pending={pass.State.Ball.HasPending}");
for (int i = 0; i < 40 && pass.State.Passes[0] == 0; i++) pass.Step(1f / 60f, PlayerCommand.None);
Check("...and is counted when the ball leaves the foot", pass.State.Passes[0] == 1, $"passes={pass.State.Passes[0]}");

var through = Playable();
through.Step(1f / 60f, new PlayerCommand { Through = true });
Check("through ball fires on the first tick", through.State.Ball.HasPending && through.State.Ball.PendingKind == 1,
      $"pending={through.State.Ball.HasPending}");

var longBall = Playable(0, 18f);
longBall.Step(1f / 60f, new PlayerCommand { Lob = true });
// Phase 0: the ball is released at the clip's ball_contact frame, not instantly.
for (int i = 0; i < 15; i++) longBall.Step(1f / 60f, PlayerCommand.None);
Check("long ball is an aerial pass to a distant target",
      longBall.State.Passes[0] > 0 && longBall.State.Ball.Vel.Y > 1f,
      $"passes={longBall.State.Passes[0]} vy={longBall.State.Ball.Vel.Y:F2}");

var shot = Playable();
shot.Step(1f / 60f, new PlayerCommand { Shoot = true, Charge = .8f });
Check("charged shot fires on the first tick", shot.State.Shots[0] > 0,
      $"shots={shot.State.Shots[0]}");

MatchEngine Defending()
{
    var e = Playable(-1);
    int away = e.Options.TeamSize;
    var me = e.State.Players[0];
    var opp = e.State.Players[away];
    opp.Pos = me.Pos + new Vector3(1.2f, 0f, 0f);
    opp.Facing = new Vector3(1f, 0f, 0f);
    e.State.Ball.Owner = away;
    e.State.Ball.Pos = new Vector3(opp.Pos.X + .4f, Mx.BallRadius, opp.Pos.Z);
    return e;
}

var tackle = Defending();
tackle.Step(1f / 60f, new PlayerCommand { Tackle = true });
Check("standing tackle / dispossess fires on the first tick",
      tackle.State.Players[0].TackleLock > 0f && tackle.State.Players[0].Action == "tackle",
      $"action={tackle.State.Players[0].Action} lock={tackle.State.Players[0].TackleLock:F2}");

var slide = Defending();
slide.Step(1f / 60f, new PlayerCommand { Slide = true });
Check("slide tackle fires on the first tick",
      slide.State.Players[0].TackleLock > 0f && slide.State.Players[0].Action == "slide",
      $"action={slide.State.Players[0].Action} lock={slide.State.Players[0].TackleLock:F2}");

var charge = Defending();
charge.Step(1f / 60f, new PlayerCommand { Sprint = true, Move = new Vector2(1f, 0f) });
Check("sprinting into a carrier contests possession with a shoulder charge",
      charge.State.Players[0].TackleLock > 0f,
      $"lock={charge.State.Players[0].TackleLock:F2}");

var dribble = Playable();
dribble.Step(1f / 60f, new PlayerCommand { Dribble = true, Shield = true });
float dribbleTouch = Mx.FlatDist(dribble.State.Ball.Pos, dribble.State.Players[0].Pos);
Check("close-control dribble keeps the ball under the boot",
      dribble.State.Players[0].Dribbling && dribbleTouch < .42f,
      $"touch={dribbleTouch:F3}");

Section("Sprint is visibly faster and released stick stops auto-running");
MatchEngine SprintRun(bool sprint)
{
    var e = new MatchEngine(new MatchOptions { Seed = 91 });
    e.State.Phase = Phase.Play;
    e.State.PhaseTimer = 0f;
    e.State.ControlLock = 10f;
    e.State.Controlled = 0;
    var me = e.State.Players[0];
    me.DecisionTimer = 10f;
    me.Stamina = 1f;
    e.State.Ball.Owner = -1;
    e.State.Ball.Pos = new Vector3(30f, Mx.BallRadius, 20f);
    e.State.Ball.Vel = Vector3.Zero;
    e.State.Ball.NoPickup = 10f;
    float x0 = me.Pos.X;
    for (int i = 0; i < 60; i++)
        e.Step(1f / 60f, new PlayerCommand { Move = new Vector2(1f, 0f), Sprint = sprint });
    return e;
}
var walked = SprintRun(false);
var sprinted = SprintRun(true);
float walkDist = MathF.Abs(walked.State.Players[0].Pos.X - new MatchEngine(new MatchOptions { Seed = 91 }).State.Players[0].Pos.X);
float sprintDist = MathF.Abs(sprinted.State.Players[0].Pos.X - new MatchEngine(new MatchOptions { Seed = 91 }).State.Players[0].Pos.X);
Check("sprint covers at least 20% more ground in one second",
      sprintDist > walkDist * 1.2f, $"walk={walkDist:F2} sprint={sprintDist:F2}");

var idle = Playable();
idle.Step(1f / 60f, PlayerCommand.None);
Check("human does not drift toward goal when the stick is released",
      Mx.FlatDist(idle.State.Players[0].Pos, idle.State.Players[0].Target) < .01f,
      $"targetDelta={Mx.FlatDist(idle.State.Players[0].Pos, idle.State.Players[0].Target):F3}");

Section("Stable broadcast camera plan");
var ballPos = new Vector3(12f, Mx.BallRadius, 8f);
var playerPos = new Vector3(-8f, 0f, -6f);
var camA = BroadcastPlan.Compute(0, ballPos, playerPos, new Vector3(1f, 0f, 0f));
var camB = BroadcastPlan.Compute(0, ballPos, playerPos, new Vector3(-1f, 0f, 0f));
Check("broadcast camera never rotates with instantaneous player facing",
      camA.Target == camB.Target && camA.Look == camB.Look && camA.Up == camB.Up);
Check("broadcast camera keeps the play closer in frame",
      Vector3.Distance(camA.Target, camA.Look) < 52f,
      $"distance={Vector3.Distance(camA.Target, camA.Look):F1}");
var tightBroadcast = BroadcastPlan.Compute(0, Vector3.Zero, new Vector3(5f, 0f, 0f), Vector3.UnitX);
var spreadBroadcast = BroadcastPlan.Compute(0, Vector3.Zero, new Vector3(35f, 0f, 0f), Vector3.UnitX);
Check("default camera stays tight in normal play and widens for separated play",
      tightBroadcast.Fov == 45f && spreadBroadcast.Fov > tightBroadcast.Fov
      && spreadBroadcast.Fov <= 59f,
      $"tight={tightBroadcast.Fov:F1} wide={spreadBroadcast.Fov:F1}");
var tactical = BroadcastPlan.Compute(4, ballPos, playerPos, new Vector3(1f, 0f, 0f));
Check("tactical view keeps a stable -Z screen-up vector", tactical.Up == new Vector3(0f, 0f, -1f));
bool bounded = true;
for (int m = 0; m < BroadcastPlan.ModeCount; m++)
{
    var plan = BroadcastPlan.Compute(m, ballPos, playerPos, new Vector3(1f, 0f, 0f));
    if (MathF.Abs(plan.Target.X) > Mx.HalfLength + 15f || MathF.Abs(plan.Target.Z) > Mx.HalfWidth + 23f) bounded = false;
    if (plan.Fov < 45f || plan.Fov > 75f) bounded = false;
}
Check("all camera modes stay inside the stadium bowl with sane FOV", bounded);

Section("Smoother gait");
var hipPose = Gait.Compute(6f, MathF.PI * .5f, 0f);
var footPose = Gait.Compute(6f, 0f, 0f);
var mixed = Gait.Lerp(Gait.Compute(0f, 0f, 0f), Gait.Compute(6f, 1f, 0f), .5f);
var dribblePose = Gait.Compute(1f, 1f, 0f, false, true);
Check("gait adds out-of-plane hip and foot rotation",
      MathF.Abs(hipPose.HipYawL) > 0f && MathF.Abs(footPose.FootRollL) > .05f,
      $"hipYaw={hipPose.HipYawL:F3} footRoll={footPose.FootRollL:F3}");
Check("gait poses can be eased instead of snapping",
      MathF.Abs(mixed.HipL) > 0f && MathF.Abs(mixed.KneeL) > 0f);
Check("dribble lean and stride are stronger than a plain walk",
      dribblePose.TurnLean > 0f && dribblePose.Stride > Gait.Compute(1f, 1f, 0f).Stride);

Section("06.11.2026 second pass: safe passes, close control and camera dead zone");
var passPlan = Playable();
var passer = passPlan.State.Players[0];
MethodInfo? bestPass = typeof(MatchEngine).GetMethod("FindBestPassTarget",
    BindingFlags.Instance | BindingFlags.NonPublic);
Check("pass-target helper is available to the regression suite", bestPass != null);
if (bestPass != null)
{
    int shortIdx = (int)bestPass.Invoke(passPlan, new object[] { passer, false, false, default(Vector2) })!;
    int longIdx = (int)bestPass.Invoke(passPlan, new object[] { passer, true, true, default(Vector2) })!;
    float shortD = shortIdx >= 0 ? Mx.FlatDist(passer.Pos, passPlan.State.Players[shortIdx].Pos) : 999f;
    float longD = longIdx >= 0 ? Mx.FlatDist(passer.Pos, passPlan.State.Players[longIdx].Pos) : 0f;
    Check("short pass prefers a nearer safe receiver than the long ball",
          shortIdx >= 0 && longIdx >= 0 && shortD < longD,
          $"short={shortD:F1} long={longD:F1}");
}
var autoDribble = Playable();
autoDribble.Step(1f / 60f, new PlayerCommand { Move = new Vector2(.2f, 0f) });
Check("a gently moved stick enters close control automatically",
      autoDribble.State.Players[0].Dribbling && autoDribble.State.Players[0].Shielding,
      $"dribble={autoDribble.State.Players[0].Dribbling}");

var focus0 = BroadcastPlan.Focus(ballPos, playerPos);
var jitter = BroadcastPlan.Focus(ballPos + new Vector3(1f, 0f, 0f), playerPos);
var focus1 = BroadcastPlan.AdvanceFocus(focus0, jitter, 1f / 60f, 0);
Check("small ball jitter does not drag the camera", (focus1 - focus0).Length() < 1e-4f,
      $"delta={(focus1 - focus0).Length():F5}");
var breakaway = BroadcastPlan.Focus(ballPos + new Vector3(30f, 0f, 0f), playerPos);
var focus2 = BroadcastPlan.AdvanceFocus(focus0, breakaway, .5f, 0);
Check("a breakaway eases the camera but keeps a framing margin",
      (focus2 - focus0).Length() > 1f
      && (breakaway - focus2).Length() > BroadcastPlan.FocusDeadzone(0) - .1f,
      $"moved={(focus2 - focus0).Length():F2} margin={(breakaway - focus2).Length():F2}");
bool fixedModes = true;
foreach (int mode in new[] { 0, 1, 3, 4 })
{
    var a = BroadcastPlan.Compute(mode, ballPos, playerPos, new Vector3(1f, 0f, 0f));
    var b = BroadcastPlan.Compute(mode, ballPos, playerPos, new Vector3(-1f, 0f, 0f));
    if (a.Target != b.Target || a.Look != b.Look) fixedModes = false;
}
Check("broadcast / ball-follow / sideline / tactical ignore instant facing", fixedModes);
var focusOverride = BroadcastPlan.Compute(0, ballPos, playerPos, new Vector3(1f, 0f, 0f), focus0);
Check("renderer can supply its held focus point", focusOverride.Target == camA.Target
      && focusOverride.Look == camA.Look);

Section("06.11.2026 second pass: desynchronised, ball-aware animation");
var phaseEngine = new MatchEngine(new MatchOptions { Seed = 5 });
Check("match players do not all start on the same stride phase",
      MathF.Abs(phaseEngine.State.Players[0].AnimPhase - phaseEngine.State.Players[1].AnimPhase) > .1f,
      $"p0={phaseEngine.State.Players[0].AnimPhase:F2} p1={phaseEngine.State.Players[1].AnimPhase:F2}");
Check("Gait.InitialPhase separates adjacent players",
      MathF.Abs(Gait.InitialPhase(0) - Gait.InitialPhase(1)) > .1f);
Check("player head turns toward the ball",
      MathF.Abs(Gait.LookYaw(new Vector3(1f, 0f, 0f), new Vector3(0f, 0f, 1f))) > .2f);
var lookPose = Gait.Compute(5f, 1f, 0f, false, false, .4f);
var easedLook = Gait.Lerp(Gait.Compute(0f, 0f, 0f), lookPose, .5f);
Check("head tracking survives pose easing", MathF.Abs(easedLook.HeadYaw) > .1f,
      $"headYaw={easedLook.HeadYaw:F3}");

Section("Arena Motion Engine: shared manifest and phase synchronization");
var manifestClips = ClipManifestLoader.Parse(File.ReadAllText("Data/clips/clip_manifest.json"));
var manifestEngine = new MotionEngine();
manifestEngine.LoadClips(manifestClips);
Check("shared Sprite Forge clip manifest loads all 18-bone clips",
      manifestEngine.ClipCount == 71 && manifestEngine.TryGetClip("soccer_run", out var runMeta)
      && runMeta.BoneCount == 18 && runMeta.Loop && runMeta.FootPlantFrames.Length == 2
      && runMeta.FootPlantSides.Length == 2 && runMeta.FootPlantSides[1] == FootSide.Right,
      $"clips={manifestEngine.ClipCount}");
// Only gait cycles may be Locomotion: blocks, appeals, victories and keeper
// stances filed there at speed 0 made standing players hold arms-up poses.
string[] gait = { "soccer_backpedal", "soccer_dribble", "soccer_jockey", "soccer_jog", "soccer_run",
    "soccer_run_ball", "soccer_sidestep", "soccer_sprint", "soccer_strafe_l", "soccer_strafe_r", "soccer_walk" };
var locoIds = manifestClips.Where(c => c.Category == ClipCategory.Locomotion).Select(c => c.Id).OrderBy(x => x).ToArray();
Check("clip manifest: Locomotion holds only gait cycles", locoIds.SequenceEqual(gait),
      string.Join(",", locoIds.Except(gait)));
var standing = manifestEngine.SelectClip(PlayerIntent.Move, ArenaFC.Core.Animation.BallState.None, 0f, 0f);
Check("a standing player plays an idle clip, not an action clip",
      standing != null && standing.Category == ClipCategory.Idle, standing?.Id ?? "null");
var jogging = manifestEngine.SelectClip(PlayerIntent.Move, ArenaFC.Core.Animation.BallState.None, 3.2f, 0f);
Check("a moving player still plays a gait clip", jogging != null && gait.Contains(jogging.Id), jogging?.Id ?? "null");
var walkMeta = new ClipMeta { Id = "walk", Category = ClipCategory.Locomotion, Duration = .8f,
    PreferredSpeed = 2f, BallState = ArenaFC.Core.Animation.BallState.None, Loop = true, BoneCount = 18,
    FootPlantFrames = new[] { .1f, .6f } };
var runMetaToy = new ClipMeta { Id = "run", Category = ClipCategory.Locomotion, Duration = .6f,
    PreferredSpeed = 5f, BallState = ArenaFC.Core.Animation.BallState.None, Loop = true, BoneCount = 18,
    FootPlantFrames = new[] { .2f, .7f } };
var kickMeta = new ClipMeta { Id = "kick", Category = ClipCategory.Kick, Duration = .6f,
    ContactFraction = .5f, PreferredSpeed = .5f, BallState = ArenaFC.Core.Animation.BallState.Possessed, Loop = false, BoneCount = 18 };
var phaseSelector = new MotionEngine();
phaseSelector.LoadClips(new[] { walkMeta, runMetaToy, kickMeta });
Check("locomotion switch aligns the same foot event across different clip phases",
      MathF.Abs(MotionEngine.AlignToNearestFootEvent(walkMeta, runMetaToy, .09f) - .19f) < .001f);
var sideSource = new ClipMeta { Id = "side_source", Category = ClipCategory.Locomotion,
    Duration = 1f, Loop = true, FootPlantFrames = new[] { .10f, .60f },
    FootPlantSides = new[] { FootSide.Left, FootSide.Right } };
var unevenTarget = new ClipMeta { Id = "uneven_target", Category = ClipCategory.Locomotion,
    Duration = 1f, Loop = true, FootPlantFrames = new[] { .08f, .30f, .55f },
    FootPlantSides = new[] { FootSide.Left, FootSide.Left, FootSide.Right } };
Check("uneven plant counts map the nearest right plant to the same side",
      MathF.Abs(MotionEngine.AlignToNearestFootEvent(sideSource, unevenTarget, .58f) - .53f) < .001f);
Check("transition policy applies side-aware alignment to locomotion switches",
      MathF.Abs(MotionEngine.ComputeStartPhase(sideSource, unevenTarget, .58f, PlayerIntent.Move) - .53f) < .001f);
Check("uneven plant counts map the nearest left plant to the same side",
      MathF.Abs(MotionEngine.AlignToNearestFootEvent(sideSource, unevenTarget, .12f) - .10f) < .001f);
var noRightPlant = new ClipMeta { Id = "left_only", Category = ClipCategory.Locomotion,
    Duration = 1f, Loop = true, FootPlantFrames = new[] { .08f },
    FootPlantSides = new[] { FootSide.Left } };
Check("missing same-side target event falls back to inherited phase",
      MathF.Abs(MotionEngine.AlignToNearestFootEvent(sideSource, noRightPlant, .58f) - .58f) < .001f);
var seamSource = new ClipMeta { Id = "seam_source", Category = ClipCategory.Locomotion,
    Duration = 1f, Loop = true, FootPlantFrames = new[] { .95f },
    FootPlantSides = new[] { FootSide.Left } };
var seamTarget = new ClipMeta { Id = "seam_target", Category = ClipCategory.Locomotion,
    Duration = 1f, Loop = true, FootPlantFrames = new[] { .05f },
    FootPlantSides = new[] { FootSide.Left } };
Check("plant alignment preserves signed offset across cycle wrap",
      MathF.Abs(MotionEngine.AlignToNearestFootEvent(seamSource, seamTarget, .98f) - .08f) < .001f);
kickMeta.FootPlantFrames = new[] { .25f, .75f };
kickMeta.FootPlantSides = new[] { FootSide.Left, FootSide.Right };
Check("one-shot actions restart at phase zero despite foot-plant metadata",
      MotionEngine.ComputeStartPhase(runMetaToy, kickMeta, .67f, PlayerIntent.Shoot) == 0f);
var motionA = new MotionState { CurrentClipId = "walk", Phase = .09f };
phaseSelector.Update(motionA, 4.8f, 0f, ArenaFC.Core.Animation.BallState.None, PlayerIntent.Move, 1f / 60f);
Check("speed-context selector queues a running clip without losing source phase",
      motionA.NextClipId == "run" && motionA.CrossfadeRemaining > 0f && motionA.BlendWeight > 0f);
var shotState = new MotionState();
phaseSelector.Update(shotState, .5f, 0f, ArenaFC.Core.Animation.BallState.Possessed, PlayerIntent.Shoot, .08f, .10f);
phaseSelector.Update(shotState, .5f, 0f, ArenaFC.Core.Animation.BallState.Possessed, PlayerIntent.Shoot, .05f, .02f);
Check("contact marker crossing is observable and does not mutate match state",
      shotState.ContactCrossed && shotState.TimeSinceContact == 0f);
var deterministicA = new MotionState { CurrentClipId = "walk", Phase = .31f };
var deterministicB = new MotionState { CurrentClipId = "walk", Phase = .31f };
for (int i = 0; i < 120; i++)
{
    phaseSelector.Update(deterministicA, 3.4f, .2f, ArenaFC.Core.Animation.BallState.None, PlayerIntent.Move, 1f / 60f);
    phaseSelector.Update(deterministicB, 3.4f, .2f, ArenaFC.Core.Animation.BallState.None, PlayerIntent.Move, 1f / 60f);
}
Check("same fixed inputs produce the same clip and normalized phase",
      deterministicA.CurrentClipId == deterministicB.CurrentClipId
      && deterministicA.NextClipId == deterministicB.NextClipId
      && MathF.Abs(deterministicA.RenderPhase - deterministicB.RenderPhase) < 1e-6f);

Section("Motion Matching feature database (Core only; runtime selector unchanged)");
var motionDb = MotionDatabase.Parse(File.ReadAllText("Data/clips/motion_features.json"));
Check("baked motion feature table loads with the versioned 23D layout",
      motionDb.Count == 403 && motionDb.Dimensions == 23);
var poseFeatures = new float[8]; poseFeatures[0] = .12f; poseFeatures[4] = .3f;
var builtQueryA = MotionQuery.BuildFeatures(poseFeatures, 1f, 0f, .1f, 2f, .5f, .8f);
var builtQueryB = MotionQuery.BuildFeatures(poseFeatures, 1f, 0f, .1f, 2f, .5f, .8f);
Check("MotionQuery builds a repeatable facing-root trajectory from current and desired motion",
      builtQueryA.AsSpan().SequenceEqual(builtQueryB)
      && builtQueryA[0] == .12f && builtQueryA[8] == 1f
      && MathF.Abs(builtQueryA[17] - MathF.Sin(.16f)) < 1e-6f
      && MathF.Abs(builtQueryA[18] - MathF.Cos(.16f)) < 1e-6f);
var probeRow = motionDb.GetRow(100);
var probeQuery = new MotionQuery(probeRow.Features.Span.ToArray(), probeRow.Category, probeRow.Ball,
    PlayerIntent.Move, currentClipId: probeRow.ClipId, currentPhase: probeRow.Phase);
var probeOk1 = motionDb.TrySearch(probeQuery, out var probeMatch1);
var probeOk2 = motionDb.TrySearch(probeQuery, out var probeMatch2);
Check("exact search is repeatable and prefers the identical current payload",
      probeOk1 && probeOk2 && probeMatch1.Row.ClipId == probeMatch2.Row.ClipId
      && probeMatch1.Row.FrameIndex == probeMatch2.Row.FrameIndex
      && probeMatch1.Row.ClipId == probeRow.ClipId && probeMatch1.Row.FrameIndex == probeRow.FrameIndex);
var zeroFeatures = new float[MotionFeatureLayout.Dimensions];
var walkFeatures = new float[MotionFeatureLayout.Dimensions];
var runFeatures = new float[MotionFeatureLayout.Dimensions]; runFeatures[0] = .2f;
var fixtureRows = new[]
{
    new { clipId = "walk", frameIndex = 0, phase = .1f, category = "Locomotion", ballState = "None", styleTag = "", features = walkFeatures },
    new { clipId = "run", frameIndex = 0, phase = .1f, category = "Locomotion", ballState = "None", styleTag = "", features = runFeatures },
    new { clipId = "possessed", frameIndex = 0, phase = .1f, category = "Locomotion", ballState = "Possessed", styleTag = "", features = zeroFeatures },
};
var fixtureJson = JsonSerializer.Serialize(new
{
    version = MotionDatabase.CurrentVersion,
    featureSchemaVersion = MotionFeatureLayout.SchemaVersion,
    dimensions = MotionFeatureLayout.Dimensions,
    space = "facing_root_xz",
    layout = MotionFeatureLayout.Names,
    trajectoryTimes = MotionFeatureLayout.TrajectoryTimes,
    normalization = new { method = "zscore", mean = zeroFeatures, stdDev = Enumerable.Repeat(1f, MotionFeatureLayout.Dimensions).ToArray() },
    weights = MotionFeatureLayout.GroupWeights,
    rows = fixtureRows,
});
var fixtureDb = MotionDatabase.Parse(fixtureJson);
var preferWalkQueryFeatures = new float[MotionFeatureLayout.Dimensions]; preferWalkQueryFeatures[0] = .2f;
var continuityQuery = new MotionQuery(preferWalkQueryFeatures, ClipCategory.Locomotion,
    ArenaFC.Core.Animation.BallState.None, currentClipId: "walk", currentPhase: .1f,
    switchPenalty: .5f, temporalPenalty: 0f);
Check("switch penalty can retain the current clip over a slightly closer candidate",
      fixtureDb.TrySearch(continuityQuery, out var continuityMatch) && continuityMatch.Row.ClipId == "walk");
var possessedQuery = new MotionQuery(zeroFeatures, ClipCategory.Locomotion,
    ArenaFC.Core.Animation.BallState.Possessed);
Check("ball-state tags hard-filter impossible motion candidates",
      fixtureDb.TrySearch(possessedQuery, out var possessedMatch) && possessedMatch.Row.ClipId == "possessed");
var shotQuery = new MotionQuery(zeroFeatures, ClipCategory.Locomotion,
    ArenaFC.Core.Animation.BallState.None, PlayerIntent.Shoot);
Check("event-driven one-shots never enter motion database search",
      !fixtureDb.TrySearch(shotQuery, out _));
var dribbleA = new DribbleState { TouchTimer = 0f };
var dribbleB = new DribbleState { TouchTimer = 0f };
var rngA = new Rng(1337); var rngB = new Rng(1337);
var ballA = DribbleSystem.Update(dribbleA, 4, new Vector3(0, Mx.BallRadius, 0), Vector3.Zero,
    Vector3.UnitX, .72f, .8f, .65f, true, 1f / 60f, rngA);
var ballB = DribbleSystem.Update(dribbleB, 4, new Vector3(0, Mx.BallRadius, 0), Vector3.Zero,
    Vector3.UnitX, .72f, .8f, .65f, true, 1f / 60f, rngB);
Check("timed dribble helper is deterministic for equal seeded streams",
      ballA == ballB && dribbleA.TouchTimer == dribbleB.TouchTimer
      && dribbleA.Separation <= DribbleSystem.MaxSeparationShield + .001f);


Section("Penalty shootout is a shootout, not a match (Mode 3)");
Check("shootout: 3-0 after three each is decided", MatchEngine.ShootoutDecided(3, 3, 3, 0));
Check("shootout: 3-1 after 3/2 kicks — away can still reach 3", !MatchEngine.ShootoutDecided(3, 2, 3, 1));
Check("shootout: 4-2 after 4/4 — away can reach at most 3", MatchEngine.ShootoutDecided(4, 4, 4, 2));
Check("shootout: level after five each goes to sudden death", !MatchEngine.ShootoutDecided(5, 5, 4, 4));
Check("shootout: sudden death waits for the pair", !MatchEngine.ShootoutDecided(6, 5, 5, 4));
Check("shootout: sudden death decided after the pair", MatchEngine.ShootoutDecided(6, 6, 5, 4));
var so = new MatchEngine(new MatchOptions { Seed = 11, Mode = MatchEngine.ModeShootout });
int soTicks = 0, strayMoves = 0, playTicks = 0;
var soStart = so.State.Players.Select(p => p.Pos).ToArray();
while (so.State.Phase != Phase.FullTime && soTicks < 60 * 60 * 6)
{
    var S = so.State; var cmdS = PlayerCommand.None;
    // The human shoots as soon as their taker has the ball.
    if (S.ShootoutTakerSide == 0 && S.Phase == Phase.Play && S.Ball.Owner == S.Controlled && !S.ShootoutShotTaken && soTicks % 20 == 0)
    { cmdS.Shoot = true; cmdS.Charge = .7f; cmdS.Move = new Vector2(.3f, soTicks % 40 == 0 ? .5f : -.5f); }
    var inactiveBefore = S.Players.Where(p => S.Phase == Phase.Play && !so.IsActive(p)).Select(p => (p.Index, p.Pos)).ToList();
    int kicksBefore = S.ShootoutKicksHome + S.ShootoutKicksAway;
    so.Step(MatchEngine.Dt, cmdS); soTicks++;
    if (S.Phase == Phase.Play) playTicks++;
    // Players sitting out must not move (the next kick's set-up teleports them, so skip those ticks).
    if (S.ShootoutKicksHome + S.ShootoutKicksAway == kicksBefore)
        foreach (var (idx, before) in inactiveBefore)
            if (Vector3.Distance(S.Players[idx].Pos, before) > .001f) strayMoves++;
}
Check("shootout reaches a result", so.State.Phase == Phase.FullTime, $"ticks={soTicks}");
Check("shootout took at least 3 kicks each", so.State.ShootoutKicksHome >= 3 && so.State.ShootoutKicksAway >= 3,
      $"{so.State.ShootoutKicksHome}/{so.State.ShootoutKicksAway}");
Check("shootout: kicks are recorded for the tally", so.State.ShootoutHome.Count == so.State.ShootoutKicksHome);
Check("shootout: score equals kicks scored", so.State.Score[0] == so.State.ShootoutHome.Count(x => x)
      && so.State.Score[1] == so.State.ShootoutAway.Count(x => x),
      $"score {so.State.Score[0]}-{so.State.Score[1]}");
Check("shootout: nobody else plays during a kick", strayMoves == 0, $"strayMoves={strayMoves}");
Check("shootout: no match clock", so.State.Clock == 0f && so.State.Half == 1);
Check("shootout: no open-play passing", so.State.Passes[0] + so.State.Passes[1] == 0,
      $"passes={so.State.Passes[0] + so.State.Passes[1]}");

Section("Training ground (Mode 2)");
var tr = new MatchEngine(new MatchOptions { Seed = 5, Mode = MatchEngine.ModeTraining });
Check("training starts in play with the ball at your feet",
      tr.State.Phase == Phase.Play && tr.State.Ball.Owner == tr.State.Controlled);
var trAway = Enumerable.Range(1, 10).Select(i => tr.State.Players[11 + i].Pos).ToArray();
for (int i = 0; i < 60 * 20; i++) tr.Step(MatchEngine.Dt, new PlayerCommand { Move = new Vector2(1, 0), Shoot = i % 90 == 0, Charge = .6f });
Check("training: computer outfielders stay off the pitch in the attack drill",
      Enumerable.Range(1, 10).All(i => tr.State.Players[11 + i].Pos == trAway[i - 1]));
Check("training: no clock, never reaches half-time", tr.State.Clock == 0f && tr.State.Phase != Phase.HalfTime);
Check("training: stamina never runs out", tr.State.Players.All(p => p.Stamina >= .999f));
tr.SetDrill(TrainingDrill.Defend);
Check("training: defend drill gives the ball to one attacker",
      tr.State.Ball.Owner == tr.TrainingAttacker && tr.State.Players[tr.State.Controlled].Team == 0);

Section("Training coach lessons");
var coachEng = new MatchEngine(new MatchOptions { Seed = 9, Mode = MatchEngine.ModeTraining });
var coach = new TrainingCoach();
coach.Update(coachEng, PlayerCommand.None, MatchEngine.Dt);         // starts lesson 1
Check("coach: has a lesson for every move", coach.Lessons.Count >= 19
      && coach.Lessons.All(l => l.Pad.Length > 0 && l.Keys.Length > 0 && l.Tip.Length > 0));
int passLesson = coach.Lessons.FindIndex(l => l.Goal == LessonGoal.ShortPass);
coach.GoTo(coachEng, passLesson);
for (int i = 0; i < 60 * 30 && coach.Index == passLesson; i++)
{
    var c = new PlayerCommand { Pass = i % 45 == 0 };
    if (i % 45 == 0 && coachEng.State.Ball.Owner != coachEng.State.Controlled) coachEng.ResetDrill();
    coachEng.Step(MatchEngine.Dt, c);
    coach.Update(coachEng, c, MatchEngine.Dt);
}
Check("coach: three short passes complete the passing lesson and move on", coach.Index == passLesson + 1,
      $"index={coach.Index} progress={coach.Progress}");
int stepOver = coach.Lessons.FindIndex(l => l.Skill == SkillMove.StepOver);
coach.GoTo(coachEng, stepOver);
for (int i = 0; i < 60 * 3; i++)
{
    var c = new PlayerCommand { Skill = i == 30 ? SkillMove.StepOver : SkillMove.None };
    coachEng.Step(MatchEngine.Dt, c); coach.Update(coachEng, c, MatchEngine.Dt);
}
Check("coach: a step-over completes the step-over lesson", coach.Index == stepOver + 1 || coach.Progress >= 1f);
Check("skills: RS flicks map to the taught moves",
      SkillMoves.FromFlick(SkillMoves.DetectFlick(.9f, 0f, 0f), false) == SkillMove.StepOver
      && SkillMoves.FromFlick(SkillMoves.DetectFlick(0f, .9f, 0f), false) == SkillMove.HeelToHeel
      && SkillMoves.FromFlick(SkillMoves.DetectFlick(0f, -.9f, 0f), true) == SkillMove.Rainbow
      && SkillMoves.DetectFlick(.9f, 0f, .8f) == SkillMoves.Flick.None);
var sk = new MatchEngine(new MatchOptions { Seed = 3, Mode = MatchEngine.ModeTraining });
int skills = 0;
for (int i = 0; i < 60 * 6; i++)
{
    var c = new PlayerCommand { Skill = i % 60 == 0 ? SkillMove.StepOver : SkillMove.None };
    if (sk.State.Ball.Owner != sk.State.Controlled && i % 60 == 59) sk.ResetDrill();
    int before = sk.Events.Count(ev => ev.Text.Contains("pulls off"));
    sk.Step(MatchEngine.Dt, c);
    if (sk.Events.Count(ev => ev.Text.Contains("pulls off")) > before) skills++;
}
Check("skills: a player can do more than one skill move (timer counts down)", skills >= 3, $"skills={skills}");


Section("Goals, keeper and AI shooting");
{
    // Dribble the ball into an empty net: must be a goal.
    var g = new MatchEngine(new MatchOptions { Seed = 21, Mode = MatchEngine.ModeTraining });
    var S = g.State; var me = S.Players[S.Controlled];
    var keeper = S.Players[11]; keeper.Pos = new Vector3(0, 0, 30f); keeper.Target = keeper.Pos;
    me.Pos = new Vector3(g.GoalPos(0).X - 3f, 0, 0); S.Ball.Owner = me.Index;
    S.Ball.Pos = me.Pos + new Vector3(.5f, Mx.BallRadius, 0); me.Facing = Vector3.UnitX;
    int before = S.Score[0];
    for (int i = 0; i < 120 && S.Score[0] == before; i++)
    { keeper.Pos = new Vector3(0, 0, 30f); g.Step(MatchEngine.Dt, new PlayerCommand { Move = new Vector2(1, 0) }); }
    Check("dribbling the ball into the net is a goal", S.Score[0] == before + 1);

    // 1v1: the keeper leaves his line when a carrier is through on goal.
    var k = new MatchEngine(new MatchOptions { Seed = 22 });
    var K = k.State; foreach (var p in K.Players) { p.Pos = new Vector3(0, 0, p.Index * 2f - 20f); p.Target = p.Pos; }
    var striker = K.Players[21]; var gk = K.Players[0];
    float line = k.OwnGoalPos(0).X;
    gk.Pos = new Vector3(line, 0, 0); striker.Pos = new Vector3(line + k.SideSign(0) * 15f, 0, 0);
    K.Ball.Owner = striker.Index; K.Ball.Pos = striker.Pos + new Vector3(-k.SideSign(0) * .5f, Mx.BallRadius, 0);
    K.Phase = Phase.Play; K.Controlled = -1;
    float maxOut = 0f;
    for (int i = 0; i < 60; i++) { k.Step(MatchEngine.Dt, PlayerCommand.None); maxOut = MathF.Max(maxOut, MathF.Abs(gk.Pos.X - line)); }
    Check("keeper comes off his line in a 1v1", maxOut > 3f, $"maxOut={maxOut:0.0}");

    // AI shoots at a sensible rate (was ~2 per 90 minutes).
    int shots = 0;
    for (int seed = 1; seed <= 6; seed++)
    {
        var m = new MatchEngine(new MatchOptions { Seed = seed, HalfMinutes = 45 });
        while (m.State.Phase != Phase.FullTime) { m.State.Controlled = -1; m.Step(MatchEngine.Dt, PlayerCommand.None); }
        shots += m.State.Shots[0] + m.State.Shots[1];
    }
    Check("AI takes more than 2 shots a match on average", shots / 6f > 2f, $"avg={shots / 6f:0.0}");
}


Section("Laws of the game at restarts (full matches)");
{
    int restarts = 0, tooClose = 0, ranWithBall = 0, throwOffLine = 0, penaltyCrowd = 0;
    for (int seed = 31; seed <= 33; seed++)
    {
        var m = new MatchEngine(new MatchOptions { Seed = seed });
        var S = m.State; Phase prev = S.Phase; int taker = -1; Vector3 start = default;
        while (S.Phase != Phase.FullTime)
        {
            S.Controlled = -1;
            m.Step(MatchEngine.Dt, PlayerCommand.None);
            bool wasSet = prev is Phase.FreeKick or Phase.ThrowIn or Phase.Corner or Phase.GoalKick or Phase.Penalty;
            if (wasSet && S.Phase == Phase.Play && S.Ball.Owner >= 0)
            {
                restarts++;
                taker = S.Ball.Owner; start = S.Players[taker].Pos;
                int side = S.Players[taker].Team;
                float need = prev == Phase.ThrowIn ? 2f : 9.15f;
                foreach (var q in S.Players)
                    if (q.Team != side && !q.SentOff && !(prev == Phase.Penalty && q.IsKeeper)
                        && Mx.FlatDist(q.Pos, S.Ball.Pos) < need - .05f) { tooClose++; break; }
                if (prev == Phase.ThrowIn && MathF.Abs(S.Ball.Pos.Z) < Mx.HalfWidth - .6f) throwOffLine++;
                if (prev == Phase.Penalty)
                {
                    float gx = MathF.Sign(S.Ball.Pos.X) * Mx.HalfLength;
                    foreach (var q in S.Players)
                        if (q.Index != taker && !(q.IsKeeper && q.Team != side) && MathF.Abs(q.Pos.X - gx) < 16.5f && MathF.Abs(q.Pos.Z) < 20.16f) { penaltyCrowd++; break; }
                }
            }
            if (taker >= 0)
            {
                if (S.Ball.Owner == taker && S.Players[taker].MustPlayBall && Mx.FlatDist(S.Players[taker].Pos, start) > 1.0f) { ranWithBall++; taker = -1; }
                else if (S.Ball.Owner != taker) taker = -1;
            }
            prev = S.Phase;
        }
    }
    Check("restarts happen in full matches", restarts > 10, $"restarts={restarts}");
    Check("opponents stand the required distance at restarts (9.15 m / 2 m)", tooClose == 0, $"breaches={tooClose}/{restarts}");
    Check("set-piece takers play the ball, they don't run off with it", ranWithBall == 0, $"ran={ranWithBall}");
    Check("throw-ins are taken from the touchline", throwOffLine == 0, $"off line={throwOffLine}");
    Check("only the taker and keeper are in the area at a penalty", penaltyCrowd == 0, $"crowded={penaltyCrowd}");
}
{
    // A keeper's parry never sends the ball towards his own goal.
    var k = new MatchEngine(new MatchOptions { Seed = 41 });
    var K = k.State; var gk = K.Players[0];
    float line = k.OwnGoalPos(0).X; int sign = k.SideSign(0);
    gk.Pos = new Vector3(line + sign * 2f, 0, 0); gk.Target = gk.Pos;
    K.Phase = Phase.Play; K.Controlled = -1;
    int towardsGoal = 0, parries = 0;
    for (int trial = 0; trial < 40; trial++)
    {
        K.Ball.Owner = -1; K.Ball.HasPending = false;
        K.Ball.Pos = new Vector3(line + sign * 3.2f, 1.0f, 0);
        K.Ball.Vel = new Vector3(-sign * 25f, 0, 0); K.Ball.FreeTime = .5f;
        gk.Pos = new Vector3(line + sign * 2f, 0, 0); gk.Action = "dive"; gk.ActionTimer = .5f;
        string before = K.Commentary;
        k.Step(MatchEngine.Dt, PlayerCommand.None);
        if (K.Commentary.Contains("parries"))
        {
            parries++;
            bool backIntoPlay = K.Ball.Vel.X * sign > 0;
            bool wide = MathF.Abs(K.Ball.Vel.Z) > MathF.Abs(K.Ball.Vel.X) * .8f || K.Ball.Vel.Y > 5f;
            if (!backIntoPlay && !wide) towardsGoal++;
        }
    }
    Check("keeper parries go back into play or wide/over, never into his own net", parries > 0 && towardsGoal == 0, $"parries={parries} towardsGoal={towardsGoal}");
}


Section("The referee enforces the Laws (nothing is physically prevented)");
{
    MatchEngine SetPiece(int seed, int side, Vector3 spot, out PlayerState taker)
    {
        var m = new MatchEngine(new MatchOptions { Seed = seed });
        var S = m.State;
        S.Phase = Phase.FreeKick; S.RestartSide = side; S.RestartPos = spot; S.PhaseTimer = .01f;
        m.Step(MatchEngine.Dt, PlayerCommand.None);
        taker = S.Players[S.Ball.Owner];
        return m;
    }
    // A human defender walks into the 10 yards: cautioned and sent back.
    var e1 = SetPiece(51, 1, new Vector3(5f, 0, 0), out var t1);
    var S1 = e1.State;
    int yBefore = S1.YellowCards[0];
    var enc = S1.Players.Where(p => p.Team == 0 && !p.IsKeeper).OrderBy(p => Mx.FlatDist(p.Pos, S1.Ball.Pos)).First();
    S1.Controlled = enc.Index; S1.ControlLock = 99f;
    for (int i = 0; i < 240 && S1.YellowCards[0] == yBefore && S1.Ball.Owner == t1.Index && t1.MustPlayBall; i++)
    {
        var d = Mx.FlatDir(enc.Pos, S1.Ball.Pos);
        t1.DecisionTimer = 1f;                                 // keep the AI taker waiting
        e1.Step(MatchEngine.Dt, new PlayerCommand { Move = new Vector2(d.X, d.Z) });
    }
    Check("a human can walk into the 10 yards (not physically stopped) and is cautioned",
          S1.YellowCards[0] == yBefore + 1, $"yellows {yBefore}->{S1.YellowCards[0]}");
    Check("the encroacher is sent back the full distance", Mx.FlatDist(enc.Pos, S1.Ball.Pos) >= 9.15f || enc.SentOff,
          $"dist {Mx.FlatDist(enc.Pos, S1.Ball.Pos):0.0}");

    // A human taker runs off with a free kick: free kick to the opposition.
    var e2 = SetPiece(52, 0, new Vector3(-5f, 0, 0), out var t2);
    var S2 = e2.State; S2.Controlled = t2.Index; S2.ControlLock = 99f;
    var spot2 = S2.RestartPos;
    for (int i = 0; i < 180 && S2.Phase == Phase.Play; i++)
        e2.Step(MatchEngine.Dt, new PlayerCommand { Move = new Vector2(1, 0) });
    Check("a human taker can carry the ball (not frozen)...", Mx.FlatDist(t2.Pos, spot2) > 1f, $"moved {Mx.FlatDist(t2.Pos, spot2):0.0} m");
    Check("...and it is a free kick to the opposition", S2.Phase == Phase.FreeKick && S2.RestartSide == 1,
          $"phase {S2.Phase} side {S2.RestartSide}");

    // Double touch: the taker plays it, then has it again before anyone else.
    var e3 = SetPiece(53, 0, new Vector3(-5f, 0, 0), out var t3);
    var S3 = e3.State; S3.Controlled = t3.Index; S3.ControlLock = 99f;
    for (int i = 0; i < 60 && S3.SetPieceTaker < 0; i++) e3.Step(MatchEngine.Dt, new PlayerCommand { Pass = i == 1 });
    for (int i = 0; i < 40 && !S3.SetPieceLeftFoot; i++) e3.Step(MatchEngine.Dt, PlayerCommand.None);
    S3.Ball.Owner = t3.Index; S3.Ball.Pos = t3.Pos + new Vector3(.5f, Mx.BallRadius, 0); t3.PossessionLock = 0;
    e3.Step(MatchEngine.Dt, PlayerCommand.None);
    Check("a double touch by the taker is an indirect free kick to the opposition",
          S3.Phase == Phase.FreeKick && S3.RestartSide == 1, $"phase {S3.Phase} side {S3.RestartSide}");

    // Violent conduct: straight red, from the referee or (if he missed it) VAR.
    int sentOff = 0, viaVar = 0, trials = 12;
    for (int k = 0; k < trials; k++)
    {
        var m = new MatchEngine(new MatchOptions { Seed = 60 + k });
        var S = m.State; S.Phase = Phase.Play;
        var me = S.Players[3]; var them = S.Players[S.Players.Length - 2];
        me.Pos = new Vector3(0, 0, k * 2f - 10f); them.Pos = me.Pos + new Vector3(.8f, 0, 0);
        S.Ball.Owner = -1; S.Ball.Pos = me.Pos + new Vector3(0, Mx.BallRadius, 30f - k * 5f);
        S.Controlled = me.Index; S.ControlLock = 99f;
        m.Step(MatchEngine.Dt, new PlayerCommand { Punch = k % 2 == 0, Headbutt = k % 2 == 1 });
        bool immediate = me.SentOff;
        for (int i = 0; i < 60 * 8 && !me.SentOff; i++) { S.Controlled = me.Index; m.Step(MatchEngine.Dt, PlayerCommand.None); }
        if (me.SentOff) sentOff++;
        if (me.SentOff && !immediate) viaVar++;
    }
    Check("punches and headbutts are always a red card (referee or VAR)", sentOff == trials, $"{sentOff}/{trials}, via VAR {viaVar}");
    Check("the referee misses some off the ball, and VAR catches them", viaVar > 0, $"via VAR {viaVar}");

    // Online: skill moves, call-for-ball and the new actions survive the wire.
    var wire = ArenaFC.Core.Net.CommandDto.From(new PlayerCommand { Skill = SkillMove.Roulette, CallForBall = true, Punch = true }).To();
    Check("skill / call-for-ball / punch go over the network", wire.Skill == SkillMove.Roulette && wire.CallForBall && wire.Punch);
}


Section("The ball in the air");
{
    Check("touch by height: foot / thigh / chest / head",
          MatchEngine.TouchFor(.3f, 0) == "trap" && MatchEngine.TouchFor(.7f, 0) == "thigh_control"
          && MatchEngine.TouchFor(1.2f, 0) == "chest_control" && MatchEngine.TouchFor(1.9f, 0) == "header");
    // Landing point of a lofted ball.
    var lb = new ArenaFC.Core.BallState { Pos = new Vector3(0, .11f, 0), Vel = new Vector3(15f, 7f, 0) };
    var land = MatchEngine.LandingPoint(lb, 1.3f);
    float tLand = (7f + MathF.Sqrt(49f + 2 * 9.81f * (.11f - 1.3f))) / 9.81f;
    Check("landing point of a lofted ball is predicted", MathF.Abs(land.X - 15f * tLand * .93f) < .5f, $"x={land.X:0.0}");

    // A ball dropping at 2 m next to a player is now playable (headed).
    var m = new MatchEngine(new MatchOptions { Seed = 71 });
    var S = m.State; S.Phase = Phase.Play;
    var me = S.Players[5]; S.Controlled = -1;
    foreach (var q in S.Players) if (q.Index != me.Index) { q.Pos = new Vector3(q.Pos.X, 0, q.Pos.Z + 25f); q.Target = q.Pos; }
    me.Pos = new Vector3(0, 0, 0);
    S.Ball.Owner = -1; S.Ball.Pos = new Vector3(.3f, 2.0f, 0); S.Ball.Vel = new Vector3(-1f, -2f, 0); S.Ball.FreeTime = .5f;
    int lt = S.Ball.LastTouch;
    for (int i = 0; i < 12; i++) m.Step(MatchEngine.Dt, PlayerCommand.None);
    Check("a 2 m high ball can be headed (was unplayable above 1.55 m)", S.Ball.LastTouch == me.Index || S.Ball.Owner == me.Index
          || (S.Ball.HasPending && S.Ball.PendingFrom == me.Index), $"last {S.Ball.LastTouch}");

    // A human volleys at goal: it is a shot.
    var v = new MatchEngine(new MatchOptions { Seed = 72 });
    var V = v.State; V.Phase = Phase.Play;
    var st = V.Players[9]; V.Controlled = st.Index; V.ControlLock = 99f;
    var goal = v.GoalPos(0);
    st.Pos = goal - new Vector3(v.SideSign(0) * 12f, 0, 0);
    V.Ball.Owner = -1; V.Ball.Pos = st.Pos + new Vector3(v.SideSign(0) * .6f, .9f, 0); V.Ball.Vel = new Vector3(0, -1f, 2f); V.Ball.FreeTime = .5f;
    int shots0 = V.Shots[0];
    v.Step(MatchEngine.Dt, new PlayerCommand { Shoot = true, Charge = .7f });
    Check("a first-time volley at goal is a shot", V.Shots[0] == shots0 + 1 && V.Ball.Vel.X * v.SideSign(0) > 10f,
          $"shots {shots0}->{V.Shots[0]} vx={V.Ball.Vel.X:0.0}");

    // Directed first touch: stick held at reception knocks it that way.
    var d = new MatchEngine(new MatchOptions { Seed = 73 });
    var D = d.State; D.Phase = Phase.Play;
    var rc = D.Players[6]; D.Controlled = rc.Index; D.ControlLock = 99f;
    foreach (var q in D.Players) if (q.Index != rc.Index) { q.Pos = new Vector3(q.Pos.X, 0, q.Pos.Z + 25f); q.Target = q.Pos; }
    rc.Pos = Vector3.Zero; rc.Vel = Vector3.Zero;
    D.Ball.Owner = -1; D.Ball.Pos = new Vector3(.7f, .6f, 0); D.Ball.Vel = new Vector3(-6f, 0, 0); D.Ball.FreeTime = .5f;
    float maxZ = 0f;
    for (int i = 0; i < 60; i++) { d.Step(MatchEngine.Dt, new PlayerCommand { Move = new Vector2(0, 1) }); maxZ = MathF.Max(maxZ, D.Ball.Pos.Z); }
    Check("a steered first touch goes where the stick points", maxZ > 1.2f, $"ball z reached {maxZ:0.0}");
}


Section("Controls: every move reachable and doing what it says");
{
    MatchEngine Striker(int seed, out PlayerState st)
    {
        var m = new MatchEngine(new MatchOptions { Seed = seed });
        var S = m.State; S.Phase = Phase.Play;
        st = S.Players[9]; S.Controlled = st.Index; S.ControlLock = 99f;
        foreach (var q in S.Players) if (q.Index != st.Index && !q.IsKeeper) { q.Pos = new Vector3(q.Pos.X, 0, 30f); q.Target = q.Pos; }
        st.Pos = m.GoalPos(0) - new Vector3(m.SideSign(0) * 16f, 0, 0);
        st.Facing = new Vector3(m.SideSign(0), 0, 0);
        S.Ball.Owner = st.Index; S.Ball.Pos = st.Pos + st.Facing * .5f + new Vector3(0, Mx.BallRadius, 0);
        return m;
    }
    Vector3 Strike(int seed, ShotStyle style, Vector2 aim, out string label)
    {
        var m = Striker(seed, out var st);
        m.Step(MatchEngine.Dt, new PlayerCommand { Shoot = true, Charge = .6f, ShotStyle = style, Move = aim });
        for (int i = 0; i < 30 && m.State.Ball.HasPending; i++) m.Step(MatchEngine.Dt, PlayerCommand.None);
        label = m.State.Commentary;
        return m.State.Ball.Vel;
    }
    int left = 0, right = 0;
    for (int k = 0; k < 8; k++)
    {
        if (Strike(80 + k, ShotStyle.Auto, new Vector2(0, 1f), out _).Z > 0) right++;
        if (Strike(90 + k, ShotStyle.Auto, new Vector2(0, -1f), out _).Z < 0) left++;
    }
    Check("the stick aims the shot at a post (was random)", left >= 7 && right >= 7, $"right {right}/8 left {left}/8");
    var chip = Strike(101, ShotStyle.Chip, Vector2.Zero, out var chipL);
    var low = Strike(102, ShotStyle.Low, Vector2.Zero, out var lowL);
    Strike(103, ShotStyle.Finesse, Vector2.Zero, out var finL);
    Check("chip shot goes up and over", chip.Y > 6f && chipL.Contains("chips it"), $"vy={chip.Y:0.0} '{chipL}'");
    Check("low driven shot stays down", low.Y < 1.2f && lowL.Contains("drills it low"), $"vy={low.Y:0.0} '{lowL}'");
    Check("finesse shot is a curler", finL.Contains("curls it"), finL);

    // Jockey and contain without the ball.
    var d = new MatchEngine(new MatchOptions { Seed = 110, Mode = MatchEngine.ModeTraining });
    d.SetDrill(TrainingDrill.Defend);
    var D = d.State; var me = D.Players[D.Controlled]; var att = D.Players[d.TrainingAttacker];
    d.Step(MatchEngine.Dt, new PlayerCommand { Dribble = true, Move = new Vector2(0, 1) });
    Check("holding LT off the ball jockeys (faces up the carrier)", me.JockeyState > 0
          && Vector3.Dot(me.Facing, Mx.FlatDir(me.Pos, att.Pos)) > .9f);
    float startGap = Mx.FlatDist(me.Pos, att.Pos);
    for (int i = 0; i < 60; i++) d.Step(MatchEngine.Dt, new PlayerCommand { Contain = true });
    var ownGoal = d.OwnGoalPos(0);
    Check("holding A off the ball contains: goal-side, about 2 m off", Mx.FlatDist(me.Pos, ownGoal) < Mx.FlatDist(att.Pos, ownGoal)
          && Mx.FlatDist(me.Pos, att.Pos) < MathF.Max(4f, startGap), $"gap {Mx.FlatDist(me.Pos, att.Pos):0.0}");

    // Right-stick switch picks the team-mate in that direction.
    var w = new MatchEngine(new MatchOptions { Seed = 111 });
    var W = w.State; W.Phase = Phase.Play; W.Ball.Owner = W.Players[15].Index;
    var cur = W.Players[4]; W.Controlled = cur.Index; W.ControlLock = 0f;
    var wanted = W.Players.Where(q => q.Team == 0 && q.Index != cur.Index && !q.IsKeeper).OrderByDescending(q => q.Pos.Z - cur.Pos.Z).First();
    w.Step(MatchEngine.Dt, new PlayerCommand { SwitchDir = new Vector2(0, 1) });
    Check("right-stick flick switches towards that side of the pitch", W.Players[W.Controlled].Pos.Z > cur.Pos.Z,
          $"picked {W.Controlled} (z {W.Players[W.Controlled].Pos.Z:0.0} vs {cur.Pos.Z:0.0})");
    var wire2 = ArenaFC.Core.Net.CommandDto.From(new PlayerCommand { ShotStyle = ShotStyle.Chip, Contain = true, SwitchDir = new Vector2(.6f, .8f) }).To();
    Check("shot style / contain / switch direction go over the network",
          wire2.ShotStyle == ShotStyle.Chip && wire2.Contain && MathF.Abs(wire2.SwitchDir.Y - .8f) < 1e-4f);
    Check("the coach teaches every control (27 lessons)", new TrainingCoach().Lessons.Count >= 27);
}

Console.WriteLine($"\nRESULT: {passed} passed, {failed} failed");
return failed == 0 ? 0 : 1;
