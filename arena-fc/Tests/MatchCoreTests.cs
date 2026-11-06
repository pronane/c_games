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
using ArenaFC.Core;

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
        if (pos.State.Commentary.Contains("wins the ball!")) tackles++;
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
Check("ball does not flip owner every few ticks", flips < 100, $"flips={flips}");
Check("a carrier can dribble for several seconds", longestHold > 180,
      $"longest={longestHold} ticks");
Check("opposition closes down the carrier", nearTicks > 400, $"nearTicks={nearTicks}");
Check("opposition wins the ball back", tackles >= 10, $"tackles={tackles}");
Check("free kicks are not handed out for invisible fouls", fouls <= 3, $"fouls={fouls}");
Check("players keep personal space around the ball", avgNearBall < 2.55f,
      $"avgWithin4m={avgNearBall:F3}");

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
Check("short pass fires on the first tick outside the AI decision clock",
      pass.State.Passes[0] > 0, $"passes={pass.State.Passes[0]}");

var through = Playable();
through.Step(1f / 60f, new PlayerCommand { Through = true });
Check("through ball fires on the first tick", through.State.Passes[0] > 0,
      $"passes={through.State.Passes[0]}");

var longBall = Playable(0, 18f);
longBall.Step(1f / 60f, new PlayerCommand { Lob = true });
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
    int shortIdx = (int)bestPass.Invoke(passPlan, new object[] { passer, false, false })!;
    int longIdx = (int)bestPass.Invoke(passPlan, new object[] { passer, true, true })!;
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

Console.WriteLine($"\nRESULT: {passed} passed, {failed} failed");
return failed == 0 ? 0 : 1;
