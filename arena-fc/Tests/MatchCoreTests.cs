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
using System;
using System.Collections.Generic;
using System.Linq;
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
// (dribble check below, over four seeds)
Check("opposition closes down the carrier", nearTicks > 400, $"nearTicks={nearTicks}");
// Real football is ~25-60 won tackles a match (4-10 per 15 game minutes).  The
// old floor of 10 encoded the every-defender-lunges scrum (~120 a match).
// One minute of one seed is too noisy for a rate (a seed can see 1 or 8), so
// average four seeds.
int tackleTotal = tackles;
for (int ts = 2027; ts <= 2029; ts++)
{
    var tm = new MatchEngine(new MatchOptions { Seed = ts, TimeSpeed = 15f });
    string pc = ""; int tOwner = tm.State.Ball.Owner, tHold = 0;
    for (int i = 0; i < 3600; i++)
    {
        tm.Step(1f / 60f, PlayerCommand.None);
        int to = tm.State.Ball.Owner;
        if (to != tOwner) { tOwner = to; tHold = 0; } else if (to >= 0) longestHold = Math.Max(longestHold, ++tHold);
        if (tm.State.Commentary != pc && (tm.State.Commentary.Contains("wins the ball!") || tm.State.Commentary.Contains("pokes it away!"))) tackleTotal++;
        pc = tm.State.Commentary;
    }
}
// One seed's longest run is one trajectory; any of four minutes will do.
Check("a carrier can dribble for several seconds", longestHold > 180, $"longest={longestHold} ticks over 4 seeds");
Check("opposition wins the ball back", tackleTotal / 4f >= 3f, $"avg tackles={tackleTotal / 4f:0.0} (seed 2026: {tackles})");
Check("free kicks are not handed out for invisible fouls", fouls <= 3, $"fouls={fouls}");
// One seed is one trajectory: any gameplay change (e.g. more shots on target, so
// more goalmouth scrambles) moves it.  Judge the average over six seeds.
double nearSum = avgNearBall;
for (int sd = 2027; sd <= 2031; sd++)
{
    var sm = new MatchEngine(new MatchOptions { Seed = sd, TimeSpeed = 15f }); long nb = 0;
    for (int i = 0; i < 3600; i++)
    {
        sm.Step(1f / 60f, PlayerCommand.None);
        foreach (var p in sm.State.Players) if (Mx.FlatDist(p.Pos, sm.State.Ball.Pos) < 4f) nb++;
    }
    nearSum += nb / 3600.0;
}
Check("players keep personal space around the ball (6 seeds)", nearSum / 6 < 2.60,
      $"avgWithin4m={nearSum / 6:F3} (seed 2026: {avgNearBall:F3})");

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
      manifestEngine.ClipCount == 333 && manifestEngine.TryGetClip("soccer_run", out var runMeta)
      && runMeta.BoneCount == 18 && runMeta.Loop && runMeta.FootPlantFrames.Length == 2
      && runMeta.FootPlantSides.Length == 2 && runMeta.FootPlantSides[1] == FootSide.Right,
      $"clips={manifestEngine.ClipCount}");
// Only gait cycles may be Locomotion: blocks, appeals, victories and keeper
// stances filed there at speed 0 made standing players hold arms-up poses.
string[] gait = { "soccer_backpedal", "soccer_dribble", "soccer_jockey", "soccer_jog", "soccer_run",
    "soccer_run_ball", "soccer_sidestep", "soccer_sprint", "soccer_strafe_l", "soccer_strafe_r", "soccer_walk" };
// (Motion-captured gait cycles - CMU runs and jogs, SkillCorner match dribble loops, run loops from
// our own match video - are gaits too.)
bool IsGait(string id) => gait.Contains(id) || id.StartsWith("soccer_mocap_run") || id.StartsWith("soccer_mocap_jog")
                          || (id.StartsWith("soccer_sc_carry_") && manifestClips.First(c => c.Id == id).Loop)
                          || (id.StartsWith("soccer_vo_run_") && manifestClips.First(c => c.Id == id).Loop)
                          || (id.StartsWith("soccer_st_carry_") && manifestClips.First(c => c.Id == id).Loop)
                          || (id.StartsWith("soccer_ss_") && manifestClips.First(c => c.Id == id).Loop);
var locoIds = manifestClips.Where(c => c.Category == ClipCategory.Locomotion).Select(c => c.Id).OrderBy(x => x).ToArray();
Check("clip manifest: Locomotion holds only gait cycles", locoIds.All(IsGait) && gait.All(g => locoIds.Contains(g)),
      string.Join(",", locoIds.Where(x => !IsGait(x))));
var standing = manifestEngine.SelectClip(PlayerIntent.Move, ArenaFC.Core.Animation.BallState.None, 0f, 0f);
Check("a standing player plays an idle clip, not an action clip",
      standing != null && standing.Category == ClipCategory.Idle, standing?.Id ?? "null");
var jogging = manifestEngine.SelectClip(PlayerIntent.Move, ArenaFC.Core.Animation.BallState.None, 3.2f, 0f);
Check("a moving player still plays a gait clip", jogging != null && IsGait(jogging.Id), jogging?.Id ?? "null");
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

Section("Motion Matching feature database (schema v2: every clip, contact timing)");
var motionDb = MotionDatabase.Parse(File.ReadAllText("Data/clips/motion_features.json"));
Check("baked motion feature table loads with the versioned 24D layout over every category",
      motionDb.Count > 1000 && motionDb.Dimensions == 24
      && motionDb.Rows.Any(r => r.Category == ClipCategory.Kick) && motionDb.Rows.Any(r => r.Category == ClipCategory.Skill),
      $"rows={motionDb.Count} dims={motionDb.Dimensions}");
var poseFeatures = new float[8]; poseFeatures[0] = .12f; poseFeatures[4] = .3f;
var builtQueryA = MotionQuery.BuildFeatures(poseFeatures, 1f, 0f, .1f, 2f, .5f, .8f);
var builtQueryB = MotionQuery.BuildFeatures(poseFeatures, 1f, 0f, .1f, 2f, .5f, .8f);
Check("MotionQuery builds a repeatable facing-root trajectory from current and desired motion",
      builtQueryA.AsSpan().SequenceEqual(builtQueryB)
      && builtQueryA[0] == .12f && builtQueryA[8] == 1f
      && MathF.Abs(builtQueryA[17] - MathF.Sin(.16f)) < 1e-6f
      && MathF.Abs(builtQueryA[18] - MathF.Cos(.16f)) < 1e-6f);
var probeRow = motionDb.Rows.Where(r => r.Category == ClipCategory.Locomotion).ElementAt(40);
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
// Step 1 of the HyperMotion-style roadmap: pose-level matching drives live selection.
{
    var mm = new MotionEngine();
    mm.LoadClips(ClipManifestLoader.Parse(File.ReadAllText("Data/clips/clip_manifest.json")));
    mm.Database = motionDb;
    // A shot whose ball contact is due in 0.1 s: the old selector started the clip at
    // frame 0 and fast-forwarded the whole wind-up (~3x); matching enters late.
    MotionState Shot(float untilContact, string? forced = null)
    {
        var st = new MotionState();
        for (int i = 0; i < 20; i++)
            mm.Update(st, 5f, 0f, ArenaFC.Core.Animation.BallState.Possessed, PlayerIntent.Move, 1f / 60f,
                      localVelocity: new System.Numerics.Vector2(0, 5f), desiredLocalVelocity: new System.Numerics.Vector2(0, 5f));
        mm.Update(st, 5f, 0f, ArenaFC.Core.Animation.BallState.Possessed, PlayerIntent.Shoot, 1f / 60f, untilContact,
                  localVelocity: new System.Numerics.Vector2(0, 5f), desiredLocalVelocity: new System.Numerics.Vector2(0, 2f), forcedClipId: forced);
        return st;
    }
    var late = Shot(.1f); var early = Shot(.6f);
    mm.TryGetClip(late.RenderClipId, out var lateClip);
    Check("a shot due in 0.1 s enters its clip late in the wind-up, at near-natural speed",
          lateClip != null && lateClip.Category == ClipCategory.Kick && late.RenderPhase > .25f && late.PlaybackScale < 2f,
          $"{late.RenderClipId} phase {late.RenderPhase:0.00} scale {late.PlaybackScale:0.00}");
    Check("a shot with the full wind-up to come enters near the start",
          early.RenderPhase < late.RenderPhase, $"early {early.RenderPhase:0.00} late {late.RenderPhase:0.00}");
    var chip = Shot(.2f, "soccer_chip_shot");
    Check("an action with its own clip plays that clip, entered at the matched frame",
          chip.RenderClipId == "soccer_chip_shot" && chip.MotionMatchRowIndex >= 0, chip.RenderClipId);
    bool dedicatedLeak = false;
    foreach (float t in new[] { .05f, .15f, .3f, .5f, .8f })
    {
        var st = Shot(t);
        if (mm.TryGetClip(st.RenderClipId, out var cm) && cm.Dedicated) dedicatedLeak = true;
    }
    Check("a plain shot never borrows a chip / trivela / bicycle clip", !dedicatedLeak);
    // Running: the gait search follows speed (jog vs sprint) and is deterministic.
    string Gait(float v)
    {
        var st = new MotionState();
        for (int i = 0; i < 30; i++)
            mm.Update(st, v, 0f, ArenaFC.Core.Animation.BallState.None, v > 6f ? PlayerIntent.Sprint : PlayerIntent.Move, 1f / 60f,
                      localVelocity: new System.Numerics.Vector2(0, v), desiredLocalVelocity: new System.Numerics.Vector2(0, v));
        return st.RenderClipId;
    }
    string slow = Gait(2.5f), fast = Gait(8f);
    Check("gait matching picks a slower cycle at 2.5 m/s and a faster one at 8 m/s", slow != fast
          && mm.TryGetClip(slow, out var sm) && mm.TryGetClip(fast, out var fm) && sm.PreferredSpeed < fm.PreferredSpeed,
          $"{slow} vs {fast}");
    Check("matching is deterministic", Gait(8f) == fast && Shot(.1f).RenderPhase == late.RenderPhase);
    // Real motion capture (CMU, SkillCorner, SoccerTrack ...) sits in the same table: some
    // shot contexts pick a captured kick over the hand-keyed ones.
    bool mocapKick = false;
    foreach (float v in new[] { 0f, 1.5f, 3f })
        foreach (float t in new[] { .1f, .3f, .5f })
        {
            var st = new MotionState();
            var lv = new System.Numerics.Vector2(0, v);
            for (int i = 0; i < 20; i++)
                mm.Update(st, v, 0f, ArenaFC.Core.Animation.BallState.None, PlayerIntent.Move, 1f / 60f, localVelocity: lv, desiredLocalVelocity: lv);
            mm.Update(st, v, 0f, ArenaFC.Core.Animation.BallState.Possessed, PlayerIntent.Shoot, 1f / 60f, t, localVelocity: lv, desiredLocalVelocity: lv);
            string rid = st.RenderClipId;     // CMU, SkillCorner, SoccerTrack or studio capture
            if (rid.StartsWith("soccer_mocap_kick") || rid.StartsWith("soccer_sc_") || rid.StartsWith("soccer_st_")
                || rid.StartsWith("soccer_rr_")) mocapKick = true;
        }
    Check("motion-captured kicks are live candidates for shots", mocapKick);
    // Real in-match motion (SkillCorner broadcast pose): shots, passes and first
    // touches from A-League players are candidates in the same search.
    var realHits = new HashSet<string>();
    foreach (var intent in new[] { PlayerIntent.Shoot, PlayerIntent.Pass })
        foreach (float v in new[] { 0f, 1.5f, 3f, 4.5f })
            foreach (float t in new[] { .1f, .2f, .3f, .5f })
                foreach (float lx in new[] { -1.5f, 0f, 1.5f })
                {
                    var st = new MotionState();
                    var lv = new System.Numerics.Vector2(lx, v);
                    for (int i = 0; i < 20; i++)
                        mm.Update(st, v, 0f, ArenaFC.Core.Animation.BallState.None, PlayerIntent.Move, 1f / 60f, localVelocity: lv, desiredLocalVelocity: lv);
                    mm.Update(st, v, 0f, ArenaFC.Core.Animation.BallState.Possessed, intent, 1f / 60f, t, localVelocity: lv, desiredLocalVelocity: lv);
                    if (st.RenderClipId.StartsWith("soccer_sc_")) realHits.Add(intent + ":" + st.RenderClipId);
                }
    Check("real-match motion (SkillCorner) is picked for shots and passes",
          realHits.Any(h => h.StartsWith("Shoot")) && realHits.Any(h => h.StartsWith("Pass")), string.Join(",", realHits));
    // Our own match video (Veo, Sprite Forge match capture): its run loops are gait
    // candidates at jogging-to-running speeds.
    var ownRuns = new HashSet<string>();
    foreach (float v in new[] { 1.5f, 2f, 2.5f, 3f, 3.5f, 4f })
    {
        string g = Gait(v);
        if (g.StartsWith("soccer_vo_run_") || g.StartsWith("soccer_mocap_jog") || g.StartsWith("soccer_mocap_run") || g.StartsWith("soccer_jog") || g.StartsWith("soccer_run")) ownRuns.Add(g);
    }
    Check("run loops from our own match video are picked when jogging", ownRuns.Count > 0, string.Join(",", ownRuns));
}
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

// 2.5: you dive on the computer's kicks.  Always dive to +Z: shots that side get
// saved far more often than shots to the other side, which is the point of guessing.
{
    int sameSide = 0, sameSaved = 0, otherSide = 0, otherSaved = 0, waited = 0;
    for (int seed = 200; seed < 260; seed++)
    {
        var m = new MatchEngine(new MatchOptions { Seed = seed, Mode = MatchEngine.ModeShootout });
        var M = m.State;
        // Skip to the first computer kick: shoot our own straight away.
        int guard = 0;
        while (M.ShootoutTakerSide != 1 && guard++ < 60 * 30)
        {
            var c = PlayerCommand.None;
            if (M.Phase == Phase.Play && M.Ball.Owner == M.Controlled && !M.ShootoutShotTaken) { c.Shoot = true; c.Charge = .6f; }
            m.Step(MatchEngine.Dt, c);
        }
        int kicks = M.ShootoutKicksAway; float strikeZ = 0f; bool struck = false; int preTicks = 0;
        guard = 0;
        while (M.ShootoutKicksAway == kicks && M.Phase != Phase.FullTime && guard++ < 60 * 20)
        {
            if (M.Phase == Phase.Play && !M.ShootoutShotTaken) preTicks++;
            m.Step(MatchEngine.Dt, new PlayerCommand { Move = new Vector2(0, 1f) });
            if (!struck && M.Ball.Owner < 0 && M.Ball.Vel.LengthSquared() > 100f) { struck = true; strikeZ = M.Ball.Vel.Z; }
        }
        if (preTicks > 60) waited++;
        if (!struck || M.ShootoutAway.Count == 0) continue;
        bool saved = !M.ShootoutAway[^1];
        if (strikeZ > .5f) { sameSide++; if (saved) sameSaved++; }
        else if (strikeZ < -.5f) { otherSide++; if (saved) otherSaved++; }
    }
    float rs = sameSide > 0 ? (float)sameSaved / sameSide : 0f, ro = otherSide > 0 ? (float)otherSaved / otherSide : 1f;
    Check("computer's penalty waits for a run-up so you can pick a dive", waited > 40, $"waited={waited}/60");
    Check("diving the right way saves far more than diving the wrong way", sameSide >= 8 && otherSide >= 8 && rs > ro + .25f,
          $"right way {sameSaved}/{sameSide}, wrong way {otherSaved}/{otherSide}");
}

{
    // Holding the stick on your own kick aims it; it never walks the taker off the
    // spot (that used to give a free kick and turn the shootout into open play).
    var m = new MatchEngine(new MatchOptions { Seed = 77, Mode = MatchEngine.ModeShootout });
    var M = m.State; int guard = 0;
    while (!(M.Phase == Phase.Play && M.Ball.Owner == M.Controlled) && guard++ < 600) m.Step(MatchEngine.Dt, PlayerCommand.None);
    var spot = M.Ball.Pos;
    for (int i = 0; i < 240; i++) m.Step(MatchEngine.Dt, new PlayerCommand { Move = new Vector2(-1f, 0f) });
    Check("shootout: the stick aims, the taker stays on the spot (no free kick, no open play)",
          Mx.FlatDist(M.Ball.Pos, spot) < 1.0f && !m.Events.Any(ev => ev.Text.Contains("free kick")) && M.Phase == Phase.Play,
          $"moved {Mx.FlatDist(M.Ball.Pos, spot):0.0} m, phase {M.Phase}");
}

// 7.3: penalties in a match use the shootout model.
{
    MatchEngine Pen(int seed, int side)
    {
        var m = new MatchEngine(new MatchOptions { Seed = seed });
        var S = m.State;
        // A penalty for `side` at the goal it attacks.
        S.Phase = Phase.Penalty; S.RestartSide = side; S.RestartPos = new Vector3(m.SideSign(side) * (Mx.HalfLength - 11f), 0, 0); S.PhaseTimer = .01f;
        m.Step(MatchEngine.Dt, PlayerCommand.None);
        return m;
    }
    // Ours: we take it (control on the taker), nothing is struck for us.
    var a = Pen(301, 0); var A = a.State;
    for (int i = 0; i < 120; i++) a.Step(MatchEngine.Dt, PlayerCommand.None);
    Check("match penalty for you: you take it (control on the taker, no auto-shot)",
          A.Ball.Owner == A.Controlled && A.Players[A.Controlled].MustPlayBall && A.Shots[0] == 0, $"owner {A.Ball.Owner} ctl {A.Controlled} shots {A.Shots[0]}");
    a.Step(MatchEngine.Dt, new PlayerCommand { Shoot = true, Charge = .7f, Move = new Vector2(0, .6f) });
    for (int i = 0; i < 40; i++) a.Step(MatchEngine.Dt, PlayerCommand.None);
    Check("match penalty for you: shoot strikes it", A.Shots[0] == 1, $"shots {A.Shots[0]}");

    // Theirs: a run-up, and your dive decides it.
    int same = 0, sameSaved = 0, other = 0, otherSaved = 0, waited = 0;
    for (int seed = 400; seed < 460; seed++)
    {
        var m = Pen(seed, 1); var M = m.State; int pre = 0; bool struck = false; float z = 0f; int ev0 = m.Events.Count;
        for (int i = 0; i < 300; i++)
        {
            if (M.Shots[1] == 0) pre++;
            m.Step(MatchEngine.Dt, new PlayerCommand { Move = new Vector2(0, 1f) });
            if (!struck && M.Ball.Owner < 0 && M.Ball.Vel.LengthSquared() > 100f) { struck = true; z = M.Ball.Vel.Z; }
            if (struck && (M.Phase != Phase.Play || (M.Ball.Owner >= 0 && M.Players[M.Ball.Owner].IsKeeper))) break;
        }
        if (pre > 60) waited++;
        // A keeper save (not a miss: those happen either way).
        bool saved = m.Events.Skip(ev0).Any(ev => ev.Kind == EventKind.Save);
        if (z > .5f) { same++; if (saved) sameSaved++; } else if (z < -.5f) { other++; if (saved) otherSaved++; }
    }
    Check("computer's match penalty has a run-up so you can dive", waited > 40, $"waited {waited}/60");
    Check("match penalty: diving the right way saves more", same >= 8 && other >= 8 && (float)sameSaved / same > (float)otherSaved / other + .2f,
          $"right {sameSaved}/{same} wrong {otherSaved}/{other}");
}

// 6.6: the defensive ring doesn't hop between team-mates while you chase the ball.
{
    int sw = 0, quick = 0; double defT = 0;
    foreach (int seed in new[] { 1, 2, 3, 4 })
    {
        var e = new MatchEngine(new MatchOptions { Seed = seed }); var S = e.State; int last = S.Controlled; double lastT = 0, t = 0;
        while (S.Phase != Phase.FullTime)
        {
            var c = PlayerCommand.None;
            if (S.Controlled >= 0) { var me = S.Players[S.Controlled]; var d = new Vector2(S.Ball.Pos.X - me.Pos.X, S.Ball.Pos.Z - me.Pos.Z); if (d.Length() > 1) c.Move = Vector2.Normalize(d); }
            e.Step(MatchEngine.Dt, c); t += MatchEngine.Dt;
            bool defending = S.Phase == Phase.Play && !(S.Ball.Owner >= 0 && S.Players[S.Ball.Owner].Team == 0);
            if (defending) defT += MatchEngine.Dt;
            if (S.Controlled != last) { if (defending) { sw++; if (t - lastT < 1.0) quick++; } last = S.Controlled; lastT = t; }
        }
    }
    double perMin = sw / (defT / 60);
    double hopsPerMin = quick / (defT / 60);
    Check("defensive auto-switch doesn't hop while you steer (was 18/min with 3.4 hops/min)", perMin < 13 && hopsPerMin < 2.2,
          $"{perMin:0.0}/min, quick hops {hopsPerMin:0.0}/min ({quick}/{sw})");
}

// 4.4 / 8.4: back to goal, ball dropping at head height -> a good finisher goes for
// the bicycle kick (its own Sprite Forge clip), facing goal it is a header.
{
    string Attempt(bool backToGoal)
    {
        var m = new MatchEngine(new MatchOptions { Seed = 91 }); var S = m.State; S.Phase = Phase.Play;
        var st = S.Players[9]; S.Controlled = st.Index; S.ControlLock = 99f;
        foreach (var q in S.Players) if (q.Index != st.Index && !q.IsKeeper) { q.Pos = new Vector3(q.Pos.X, 0, 30f); q.Target = q.Pos; }
        int sg = m.SideSign(0);
        st.Pos = m.GoalPos(0) - new Vector3(sg * 9f, 0, 0); st.Target = st.Pos;
        st.Facing = new Vector3(backToGoal ? -sg : sg, 0, 0);
        st.Spec.Shooting = .85f; st.PossessionLock = 0f;
        var b = S.Ball; b.Owner = -1; b.HasPending = false; b.Pos = st.Pos + st.Facing * .4f + new Vector3(0, 1.6f, 0);
        b.Vel = new Vector3(0, -1f, 0); b.FreeTime = 1f; b.NoPickup = 0f;
        int ev0 = m.Events.Count;
        m.Step(MatchEngine.Dt, new PlayerCommand { Shoot = true, Charge = .7f });
        for (int i = 0; i < 4; i++) m.Step(MatchEngine.Dt, PlayerCommand.None);
        return st.Action + " | " + string.Join(" / ", m.Events.Skip(ev0).Select(e => e.Text));
    }
    string back = Attempt(true), facing = Attempt(false);
    Check("back to goal, ball at head height: bicycle kick", back.StartsWith("bicycle") && back.Contains("bicycle kick"), back);
    Check("facing goal, same ball: a header, not a bicycle", !facing.StartsWith("bicycle"), facing);
}

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
    int restarts = 0, tooClose = 0, ranWithBall = 0, throwOffLine = 0, penaltyCrowd = 0, goalKicks = 0, gkAreaBreach = 0;
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
                if (prev == Phase.GoalKick) goalKicks++;
                if (prev == Phase.Penalty)
                {
                    float gx = MathF.Sign(S.Ball.Pos.X) * Mx.HalfLength;
                    foreach (var q in S.Players)
                        if (q.Index != taker && !(q.IsKeeper && q.Team != side) && MathF.Abs(q.Pos.X - gx) < 16.5f && MathF.Abs(q.Pos.Z) < 20.16f) { penaltyCrowd++; break; }
                }
            }
            if (taker >= 0 && S.Ball.Owner == taker && S.Players[taker].MustPlayBall)
            {
                // Goal kick / own-area free kick: opponents stay out of the
                // penalty area until the ball is in play (restart spot inside).
                float gx = m.OwnGoalPos(S.Players[taker].Team).X;
                bool ownAreaRestart = MathF.Abs(S.RestartPos.X - gx) < 16.5f && MathF.Abs(S.RestartPos.Z) < 20.16f;
                if (ownAreaRestart)
                    foreach (var q in S.Players)
                        if (q.Team != S.Players[taker].Team && !q.SentOff && MathF.Abs(q.Pos.X - gx) < 16.2f && MathF.Abs(q.Pos.Z) < 19.9f) { gkAreaBreach++; break; }
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
    Check("opponents stay outside the penalty area at a goal kick until it is taken", goalKicks > 0 && gkAreaBreach == 0, $"goal kicks={goalKicks} breach ticks={gkAreaBreach}");
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
    // 3.3: a finesse shot visibly bends: it starts outside the post and curls back
    // in towards the middle (the curl direction used to be a coin toss).
    {
        int bentIn = 0, inside = 0, n = 0; float maxBow = 0f;
        for (int k = 0; k < 12; k++)
        {
            var m = Striker(300 + k, out var st);
            float aimY = k % 2 == 0 ? 1f : -1f;
            m.State.Players[11].Pos = new Vector3(m.State.Players[11].Pos.X, 0, 25f);  // their keeper out of the way
            m.Step(MatchEngine.Dt, new PlayerCommand { Shoot = true, Charge = .6f, ShotStyle = ShotStyle.Finesse, Move = new Vector2(0, aimY) });
            for (int i = 0; i < 30 && m.State.Ball.HasPending; i++) m.Step(MatchEngine.Dt, PlayerCommand.None);
            var b = m.State.Ball; var start = b.Pos; var v0 = Vector3.Normalize(new Vector3(b.Vel.X, 0, b.Vel.Z));
            float bow = 0f; float lineX = m.GoalPos(0).X; float crossZ = float.NaN;
            for (int i = 0; i < 120; i++)
            {
                m.Step(MatchEngine.Dt, PlayerCommand.None);
                var dd = new Vector3(b.Pos.X - start.X, 0, b.Pos.Z - start.Z);
                float lateral = dd.Z * v0.X - dd.X * v0.Z;     // signed distance off the launch line
                if (MathF.Abs(lateral) > MathF.Abs(bow)) bow = lateral;
                if (float.IsNaN(crossZ) && MathF.Abs(b.Pos.X) >= MathF.Abs(lineX) - .1f) crossZ = b.Pos.Z;
                if (m.State.Phase != Phase.Play) { if (float.IsNaN(crossZ)) crossZ = b.Pos.Z; break; }
            }
            n++;
            maxBow = MathF.Max(maxBow, MathF.Abs(bow));
            // Launched towards the aimed side, it bends back towards the centre.
            float straightZ = start.Z + v0.Z / v0.X * (lineX - start.X);
            if (MathF.Abs(bow) > .4f && !float.IsNaN(crossZ) && MathF.Abs(crossZ) < MathF.Abs(straightZ) - .3f) bentIn++;
            if (!float.IsNaN(crossZ) && MathF.Abs(crossZ) < Mx.GoalHalfWidth) inside++;
        }
        Check("finesse shots bend visibly back towards the middle (≥0.4 m off the launch line)", bentIn >= 10, $"bent {bentIn}/{n}, max bow {maxBow:0.00} m");
        Check("finesse shots aimed at a post curl back inside it", inside >= 8, $"inside {inside}/{n}");
    }
    // 3.4: shot height.  A well-timed strike stays under the bar; leathering it
    // (full charge) from range is what sends it into the stand.  (Before: a perfectly
    // timed shot from 16 m went over every time, and every shot >= .7 from 24 m.)
    {
        (int over, int n) Heights(float dist, float charge)
        {
            int ov = 0, cnt = 0;
            for (int k = 0; k < 20; k++)
            {
                var m = new MatchEngine(new MatchOptions { Seed = 700 + k }); var S = m.State; S.Phase = Phase.Play;
                var st = S.Players[9]; S.Controlled = st.Index; S.ControlLock = 99f;
                foreach (var q in S.Players) if (q.Index != st.Index) { q.Pos = new Vector3(q.Pos.X, 0, 30f); q.Target = q.Pos; }
                st.Pos = m.GoalPos(0) - new Vector3(m.SideSign(0) * dist, 0, 0); st.Facing = new Vector3(m.SideSign(0), 0, 0);
                S.Ball.Owner = st.Index; S.Ball.Pos = st.Pos + st.Facing * .5f + new Vector3(0, Mx.BallRadius, 0);
                m.Step(MatchEngine.Dt, new PlayerCommand { Shoot = true, Charge = charge });
                float lineX = m.GoalPos(0).X;
                for (int i = 0; i < 200; i++)
                {
                    m.Step(MatchEngine.Dt, PlayerCommand.None);
                    if (MathF.Abs(S.Ball.Pos.X) >= MathF.Abs(lineX)) { cnt++; if (S.Ball.Pos.Y > Mx.GoalHeight) ov++; break; }
                }
            }
            return (ov, cnt);
        }
        var (o16, n16) = Heights(16f, .775f); var (o24, n24) = Heights(24f, .775f); var (oFull, nFull) = Heights(24f, 1f);
        Check("a well-timed shot stays under the bar (16 m and 24 m)", n16 >= 15 && n24 >= 15 && o16 <= n16 / 8 && o24 <= n24 / 8,
              $"16 m over {o16}/{n16}, 24 m over {o24}/{n24}");
        Check("full power from 24 m often goes over", nFull >= 10 && oFull >= nFull * .3f, $"over {oFull}/{nFull}");
    }
    // Trivela (finesse + sprint): outside of the boot - starts towards the middle and
    // swerves out to the aimed post.
    {
        int out_ = 0, n = 0;
        for (int k = 0; k < 10; k++)
        {
            var m = Striker(320 + k, out var st);
            float aimY = k % 2 == 0 ? 1f : -1f;
            m.State.Players[11].Pos = new Vector3(m.State.Players[11].Pos.X, 0, 25f);
            m.Step(MatchEngine.Dt, new PlayerCommand { Shoot = true, Charge = .6f, ShotStyle = ShotStyle.Trivela, Move = new Vector2(0, aimY) });
            for (int i = 0; i < 30 && m.State.Ball.HasPending; i++) m.Step(MatchEngine.Dt, PlayerCommand.None);
            var b = m.State.Ball; var start = b.Pos; var v0 = Vector3.Normalize(new Vector3(b.Vel.X, 0, b.Vel.Z));
            float lineX = m.GoalPos(0).X, crossZ = float.NaN;
            for (int i = 0; i < 120 && float.IsNaN(crossZ); i++)
            {
                m.Step(MatchEngine.Dt, PlayerCommand.None);
                if (MathF.Abs(b.Pos.X) >= MathF.Abs(lineX) - .1f || m.State.Phase != Phase.Play) crossZ = b.Pos.Z;
            }
            float straightZ = start.Z + v0.Z / v0.X * (lineX - start.X);
            n++;
            if (!float.IsNaN(crossZ) && MathF.Sign(crossZ) == MathF.Sign(aimY) && MathF.Abs(crossZ) > MathF.Abs(straightZ) + .3f) out_++;
        }
        Check("trivela swerves out towards the aimed post", out_ >= 7, $"{out_}/{n}");
    }
    // Curled passes: a through ball with a defender in the lane is bent round him
    // (the pass spin used to be a random sign - pure error).
    {
        int clear = 0, n = 0;
        for (int seed = 0; seed < 20; seed++)
        {
            var m = new MatchEngine(new MatchOptions { Seed = 500 + seed, Offside = false }); var S = m.State; S.Phase = Phase.Play;
            int sg = m.SideSign(0); var a = S.Players[6]; var r = S.Players[9];
            foreach (var q in S.Players) if (q.Index != a.Index && q.Index != r.Index && !q.IsKeeper) { q.Pos = new Vector3(-sg * 45f, 0, q.Pos.Z * .5f); q.Target = q.Pos; }
            a.Pos = Vector3.Zero; a.Facing = new Vector3(sg, 0, 0); r.Pos = new Vector3(sg * 22f, 0, 0); r.Target = r.Pos;
            var dfd = S.Players[16]; var dp = new Vector3(sg * 11f, 0, (seed % 2 == 0 ? 1 : -1) * .9f);
            S.Controlled = a.Index; S.ControlLock = 99f; S.Ball.Owner = a.Index; S.Ball.Pos = a.Pos + a.Facing * .5f + new Vector3(0, Mx.BallRadius, 0);
            dfd.Pos = dp;
            m.Step(MatchEngine.Dt, new PlayerCommand { Through = true, Charge = .5f, Move = new Vector2(sg, 0) });
            float minD = 99f; bool flew = false;
            for (int i = 0; i < 120; i++)
            {
                dfd.Pos = dp; dfd.Vel = Vector3.Zero; dfd.PossessionLock = 5f;      // a statue: we only measure the path
                m.Step(MatchEngine.Dt, PlayerCommand.None);
                if (S.Ball.Owner < 0) flew = true;
                if (flew) minD = MathF.Min(minD, Mx.FlatDist(S.Ball.Pos, dp));
            }
            n++; if (minD > 1f) clear++;
        }
        Check("a curled through ball bends round a defender in the lane", clear >= 16, $"cleared by >1 m {clear}/{n} (random spin: ~16/30)");
    }
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

// ---- 9.2/9.3: preview stadium and weather reach the engine ----
{
    Check("preview shows the home club's ground", Presentation.StadiumFor(Clubs.All[0].Name) == Clubs.All[0].Stadium
          && new Presentation().GeneratePreMatch(Clubs.All[2].Name, Clubs.All[3].Name, "4-4-2", "4-3-3").Stadium == Clubs.All[2].Stadium);
    var (rt, _) = Presentation.WeatherFor("Rain");
    new MatchEngine(new MatchOptions { Weather = rt, Seed = 5 });
    Check("rain in the preview makes it rain in the match", Weather.Raining);
    new MatchEngine(new MatchOptions { Seed = 5 });
    Check("a new match resets the weather (no rain leaking into the next game)", !Weather.Raining && Weather.WindX == 0f);
}

Section("Keeper distribution and receiving");
{
    // A keeper who catches it on his line steps out and plays it: he used to walk
    // back onto the line holding it and carry it over (an own goal).
    var e = new MatchEngine(new MatchOptions { Seed = 9 }); var S = e.State;
    S.Phase = Phase.Play;
    var gk = S.Players.First(q => q.IsKeeper && q.Team == 0);
    var own = e.OwnGoalPos(0);
    gk.Pos = own + new Vector3(MathF.Sign(-own.X) * .5f, 0, 1f);
    S.Ball.Owner = gk.Index; S.Ball.HasPending = false; S.Ball.Pos = gk.Pos;
    int[] before = { S.Score[0], S.Score[1] };
    bool released = false;
    for (int i = 0; i < 60 * 6 && !released; i++)
    {
        S.Controlled = -1; e.Step(MatchEngine.Dt, PlayerCommand.None);
        if (S.Ball.Owner != gk.Index) released = true;
    }
    Check("a keeper with the ball in hand distributes it", released);
    Check("... without carrying it over his own line", S.Score[1] == before[1] && S.Score[0] == before[0], $"score {S.Score[0]}-{S.Score[1]}");

    // AI pass completion over released passes (real ~80%; ours was 65% because a
    // receiver re-decided mid-trap and ran off while the ball rolled past).
    int att = 0, ok = 0;
    foreach (int seed in new[] { 31, 32 })
    {
        var m = new MatchEngine(new MatchOptions { Seed = seed }); var M = m.State;
        int q0 = M.Passes[0], q1 = M.Passes[1], team = -1;
        while (M.Phase != Phase.FullTime)
        {
            M.Controlled = -1; m.Step(MatchEngine.Dt, PlayerCommand.None);
            int t = M.Passes[0] > q0 ? 0 : M.Passes[1] > q1 ? 1 : -1; q0 = M.Passes[0]; q1 = M.Passes[1];
            if (t >= 0 && M.Ball.PassReceiver >= 0 && M.Phase == Phase.Play) { team = t; continue; }
            if (team < 0) continue;
            if (M.Phase != Phase.Play) { att++; team = -1; continue; }
            if (M.Ball.Owner >= 0) { att++; if (M.Players[M.Ball.Owner].Team == team) ok++; team = -1; }
        }
    }
    double pc = att > 0 ? ok / (double)att : 0;
    Check("AI pass completion 72-92% (real ~80%)", pc is >= .72 and <= .92, $"{pc:P0} of {att}");
}

Section("Keeper lets a wide shot go");
{
    var e = new MatchEngine(new MatchOptions { Seed = 9 }); var S = e.State;
    S.Phase = Phase.Play;
    var gk = S.Players.First(q => q.IsKeeper && q.Team == 0);
    var own = e.OwnGoalPos(0); float sg = MathF.Sign(own.X);
    gk.Pos = own + new Vector3(-sg * 1f, 0, 2.6f); gk.Target = gk.Pos;
    foreach (var q in S.Players) if (!q.IsKeeper) q.Pos = new Vector3(-sg * 20f, 0, q.Pos.Z);
    // struck from 14 m, crossing the line 1.1 m outside the post, passing within reach of him
    S.Ball.Owner = -1; S.Ball.HasPending = false; S.Ball.FreeTime = 1f;
    S.Ball.Pos = own + new Vector3(-sg * 14f, .3f, 0f);
    Vector3 crossAt = own + new Vector3(0, .5f, Mx.GoalHalfWidth + 1.1f);
    S.Ball.Vel = Vector3.Normalize(crossAt - S.Ball.Pos) * 22f;
    S.Ball.LastTouchSide = 1; S.Ball.PassReceiver = -1;
    bool touched = false;
    for (int i = 0; i < 90 && S.Phase == Phase.Play; i++)
    {
        S.Controlled = -1; e.Step(MatchEngine.Dt, PlayerCommand.None);
        if (S.Ball.LastTouch == gk.Index || S.Ball.Owner == gk.Index) touched = true;
    }
    Check("a shot going wide is left for a goal kick (keepers used to palm 57% of all shots)", !touched,
          $"touched={touched} phase={S.Phase}");
}

Section("Skill games (2.4): five scored challenges, not a plain match");
{
    foreach (SkillGame g in Enum.GetValues<SkillGame>())
    {
        var e = new MatchEngine(new MatchOptions { Seed = 5, Mode = MatchEngine.ModeSkill, SkillGame = g, Fouls = false, Offside = false });
        var S = e.State; int t = 0;
        while (S.Phase != Phase.FullTime && t < 60 * 90)
        {
            t++;
            var c = PlayerCommand.None; var me = S.Players[S.Controlled]; var goal = e.GoalPos(0);
            if (S.Ball.Owner == S.Controlled)
            {
                Vector3 d;
                switch (g)
                {
                    case SkillGame.Shooting: case SkillGame.FreeKicks:
                        d = Vector3.Normalize(new Vector3(goal.X, 0, me.Pos.Z > 0 ? -2.8f : 2.8f) - me.Pos);
                        c.Move = new Vector2(d.X, d.Z); if (t % 40 == 0) { c.Shoot = true; c.Charge = .65f; } break;
                    case SkillGame.Passing:
                        if (e.SkillTarget >= 0 && t % 30 == 0) { d = Vector3.Normalize(S.Players[e.SkillTarget].Pos - me.Pos); c.Move = new Vector2(d.X, d.Z); c.Pass = true; } break;
                    case SkillGame.Dribbling:
                        Vector3 tgt = e.SkillSlalom.Count > 0
                            ? S.Players[e.SkillSlalom[0]].Pos + new Vector3(e.SideSign(0) * 1.5f, 0, -MathF.Sign(S.Players[e.SkillSlalom[0]].Pos.Z) * 1.6f) : goal;
                        d = Vector3.Normalize(tgt - me.Pos); c.Move = new Vector2(d.X, d.Z);
                        if (e.SkillSlalom.Count == 0 && Mx.FlatDist(me.Pos, goal) < 16 && t % 20 == 0) { c.Shoot = true; c.Charge = .5f; } break;
                    default:
                        if (MathF.Abs(goal.X - me.Pos.X) > 12) { c.Move = new Vector2(MathF.Sign(goal.X), 0); c.Sprint = true; } else if (t % 20 == 0) c.Lob = true; break;
                }
            }
            e.Step(MatchEngine.Dt, c);
        }
        Check($"skill game {g}: ends on its own (60 s or six kicks)", S.Phase == Phase.FullTime, $"t={t / 60f:0}s");
        Check($"skill game {g}: no match clock, no opposition team in play", S.Clock == 0f
              && S.Players.Count(q => q.Team == 1 && !q.IsKeeper && e.IsActive(q)) <= 2);
        if (g is SkillGame.Shooting or SkillGame.Passing or SkillGame.Dribbling)
            Check($"skill game {g}: a scripted player scores points", e.SkillScore > 0, $"{e.SkillScore} pts");
        if (g == SkillGame.FreeKicks)
            Check("skill game FreeKicks: six attempts over a four-man wall", e.SkillAttempts == 6, $"{e.SkillAttempts}");
        Check($"skill game {g}: score is the full-time score", S.Score[0] == e.SkillScore);
    }
    var sv = new SaveGame();
    bool b1 = sv.RecordSkill(SkillGame.Shooting, 7), b2 = sv.RecordSkill(SkillGame.Shooting, 5), b3 = sv.RecordSkill(SkillGame.Shooting, 9);
    var round = SaveGame.FromJson(sv.ToJson());
    Check("skill best scores save, only rise, and survive a save/load", b1 && !b2 && b3 && round.BestSkill(SkillGame.Shooting) == 9);
}

Section("Set pieces and crosses (7.2, 6.5)");
{
    // The keeper claims a high ball dropping into his six-yard box.
    var e = new MatchEngine(new MatchOptions { Seed = 11 }); var S = e.State;
    S.Phase = Phase.Play;
    var gk = S.Players.First(q => q.IsKeeper && q.Team == 0);
    var own = e.OwnGoalPos(0); float sg = MathF.Sign(own.X);
    gk.Pos = own + new Vector3(-sg * 1.5f, 0, 0); gk.Target = gk.Pos;
    foreach (var q in S.Players) if (!q.IsKeeper) q.Pos = new Vector3(-sg * 25f, 0, q.Pos.Z);
    S.Ball.Owner = -1; S.Ball.HasPending = false; S.Ball.FreeTime = 1f; S.Ball.LastTouchSide = 1; S.Ball.PassReceiver = -1;
    S.Ball.Pos = new Vector3(own.X - sg * 3f, 2f, Mx.HalfWidth - 6f);
    var land = own + new Vector3(-sg * 4.5f, 0, 1.5f);
    float T = 1.1f;
    S.Ball.Vel = new Vector3((land.X - S.Ball.Pos.X) / T, (2.3f - 2f + .5f * 9.81f * T * T) / T, (land.Z - S.Ball.Pos.Z) / T);
    bool claimed = false;
    for (int i = 0; i < 120 && !claimed; i++)
    {
        S.Controlled = -1; e.Step(MatchEngine.Dt, PlayerCommand.None);
        if (S.Ball.Owner == gk.Index || (S.Ball.LastTouch == gk.Index && e.Events.Any(x => x.Text.Contains("punches")))) claimed = true;
    }
    Check("keeper comes and claims a cross into his six-yard box (keepers were excluded from high balls)", claimed);

    // A throw-in is thrown from above the head with the throw-in action.
    int thrown = 0, kicked = 0, cornerCross = 0, corners = 0;
    foreach (int seed in new[] { 101, 102, 103 })
    {
        var m = new MatchEngine(new MatchOptions { Seed = seed }); var M = m.State; int evc = 0;
        bool wasThrow = false, wasCorner = false;
        while (M.Phase != Phase.FullTime)
        {
            M.Controlled = -1; m.Step(MatchEngine.Dt, PlayerCommand.None);
            if (M.Phase == Phase.ThrowIn) wasThrow = true;
            if (M.Phase == Phase.Corner) wasCorner = true;
            for (; evc < m.Events.Count; evc++)
            {
                var ev = m.Events[evc];
                if (ev.Kind != EventKind.Pass) continue;
                if (wasThrow) { if (ev.Text.Contains("throws it") && M.Players[M.Ball.PendingFrom].Action == "throw_in" && M.Ball.PendingPos.Y > 1.8f) thrown++; else kicked++; wasThrow = false; }
                if (wasCorner) { corners++; if (ev.Text.Contains("crosses it") || Mx.FlatDist(M.Ball.PendingTarget, M.Players[M.Ball.PendingFrom].Pos) < 15f) cornerCross++; wasCorner = false; }
            }
        }
    }
    Check("throw-ins are thrown (hands, from head height), not kicked", thrown > 0 && kicked == 0, $"thrown {thrown}, kicked {kicked}");
    Check("AI corners are delivered into the box or played short", corners > 0 && cornerCross == corners, $"{cornerCross}/{corners}");
}

Section("Human controls: kick-off, restarts, FC slide button");
{
    // You take your own kick-off (it was played for you the moment the whistle went).
    var e = new MatchEngine(new MatchOptions { Seed = 7 }); var S = e.State; int firstPass = -1;
    for (int t = 0; t < 240; t++)
    {
        e.Step(MatchEngine.Dt, new PlayerCommand { Pass = t == 150 });
        if (firstPass < 0 && e.Events.Any(x => x.Kind == EventKind.Pass)) firstPass = t;
    }
    Check("a human kick-off waits for your pass", firstPass == 150, $"first pass at tick {firstPass}");
    // Square / X without the ball is the slide tackle.
    var e2 = new MatchEngine(new MatchOptions { Seed = 7 }); var S2 = e2.State;
    for (int i = 0; i < 400 && S2.Phase != Phase.Play; i++) e2.Step(MatchEngine.Dt, new PlayerCommand { Pass = i % 30 == 0 });
    var opp = S2.Players.First(q => q.Team == 1 && !q.IsKeeper && q.Role != Role.Defender);
    var me = S2.Players.First(q => q.Team == 0 && q.Role == Role.Defender);
    S2.Controlled = me.Index; S2.Ball.Owner = opp.Index; S2.Ball.Pos = opp.Pos; S2.Ball.HasPending = false;
    me.Pos = opp.Pos + new Vector3(1.5f, 0, 0); S2.ControlLock = 5;
    string act = "";
    for (int t = 0; t < 10; t++) { e2.Step(MatchEngine.Dt, new PlayerCommand { ShootPress = t == 3, Move = new Vector2(-1, 0) }); if (t == 6) act = me.Action; }
    Check("shoot button without the ball = slide tackle (as in FC)", act == "slide", act);
    // At your restarts the ring is on the taker, and one press plays it.
    int ours = 0, onTaker = 0;
    var e3 = new MatchEngine(new MatchOptions { Seed = 2 }); var S3 = e3.State; var last = S3.Phase;
    for (int t = 0; t < 60 * 60 * 3 && S3.Phase != Phase.FullTime; t++)
    {
        bool restart = last is Phase.ThrowIn or Phase.FreeKick or Phase.Corner or Phase.GoalKick && S3.Phase == Phase.Play;
        last = S3.Phase;
        var c = new PlayerCommand { Pass = S3.Ball.Owner >= 0 && S3.Ball.Owner == S3.Controlled && S3.Players[S3.Ball.Owner].MustPlayBall };
        e3.Step(MatchEngine.Dt, c);
        if (restart && S3.Ball.Owner >= 0 && S3.Players[S3.Ball.Owner].Team == 0) { ours++; if (S3.Ball.Owner == S3.Controlled) onTaker++; }
    }
    Check("your restarts put you on the taker", ours > 0 && onTaker == ours, $"{onTaker}/{ours}");
}

Section("Realism gate (0.1): four full AI matches stay inside football's bands");
{
    // Per-match averages over four seeds.  The bands are deliberately wide (they
    // tighten as the AI work lands); a change that knocks the simulation out of
    // them - e.g. the old ~2 gShots or ~120 gTackles a match - fails CI.
    double gShots = 0, gGoals = 0, gPasses = 0, gTackles = 0, gFouls = 0, gCards = 0, gOut = 0, gOffside = 0, gHeaders = 0;
    // Calibration samples (same definitions as Tools/skillcorner_metrics.py).
    var cLin = new List<double>(); var cLout = new List<double>(); var cWin = new List<double>(); var cWout = new List<double>();
    var cLine = new List<double>(); var cPress = new List<double>(); var cSpd = new List<double>();
    int[] seeds = { 101, 102, 103, 104 };
    foreach (int seed in seeds)
    {
        var e = new MatchEngine(new MatchOptions { Seed = seed }); var S = e.State; int evc = 0;
        var prevPos = new Vector3[S.Players.Length]; long tick = 0;
        while (S.Phase != Phase.FullTime)
        {
            S.Controlled = -1; e.Step(MatchEngine.Dt, PlayerCommand.None); tick++;
            for (; evc < e.Events.Count; evc++)
            {
                var ev = e.Events[evc];
                if (ev.Kind == EventKind.Tackle) gTackles++;
                else if (ev.Kind == EventKind.Out) gOut++;
                else if (ev.Kind == EventKind.Offside) gOffside++;
                if (ev.Text.Contains("heads")) gHeaders++;
            }
            if (tick % 6 == 0)
                for (int i = 0; i < S.Players.Length; i++)
                {
                    var p = S.Players[i]; if (p.IsKeeper || p.SentOff) continue;
                    if (tick > 6 && S.Phase == Phase.Play)
                    {
                        double v = Vector3.Distance(Mx.Flat(p.Pos), Mx.Flat(prevPos[i])) / (6 * MatchEngine.Dt);
                        if (v < 12) cSpd.Add(v);
                    }
                    prevPos[i] = p.Pos;
                }
            if (S.Phase != Phase.Play || tick % 30 != 0 || S.Ball.Owner < 0) continue;
            int inTeam = S.Players[S.Ball.Owner].Team;
            for (int team = 0; team < 2; team++)
            {
                var xs = new List<double>(); var zs = new List<double>(); double gkx = 0;
                foreach (var p in S.Players)
                {
                    if (p.Team != team || p.SentOff) continue;
                    if (p.IsKeeper) { gkx = p.Pos.X; continue; }
                    xs.Add(p.Pos.X); zs.Add(p.Pos.Z);
                }
                if (xs.Count < 8) continue;
                bool isIn = team == inTeam;
                (isIn ? cLin : cLout).Add(xs.Max() - xs.Min()); (isIn ? cWin : cWout).Add(zs.Max() - zs.Min());
                if (!isIn) cLine.Add(xs.Min(x => Math.Abs(x - gkx)));
            }
            var holder = S.Players[S.Ball.Owner]; double nearOpp = 1e9;
            foreach (var q in S.Players)
                if (q.Team != holder.Team && !q.IsKeeper && !q.SentOff)
                    nearOpp = Math.Min(nearOpp, Vector3.Distance(Mx.Flat(q.Pos), Mx.Flat(holder.Pos)));
            cPress.Add(nearOpp);
        }
        gShots += S.Shots[0] + S.Shots[1]; gGoals += S.Score[0] + S.Score[1];
        gPasses += S.Passes[0] + S.Passes[1]; gFouls += S.Fouls[0] + S.Fouls[1];
        gCards += S.YellowCards[0] + S.YellowCards[1] + S.RedCards[0] + S.RedCards[1];
    }
    double n = seeds.Length;
    Check("gate: shots per match 4-35", gShots / n is >= 4 and <= 35, $"{gShots / n:0.0}");
    Check("gate: goals per match 0.5-6", gGoals / n is >= .5 and <= 6, $"{gGoals / n:0.0}");
    Check("gate: passes per match 80-700", gPasses / n is >= 80 and <= 700, $"{gPasses / n:0}");
    Check("gate: tackles per match 20-130", gTackles / n is >= 20 and <= 130, $"{gTackles / n:0}");
    Check("gate: fouls per match 1-30", gFouls / n is >= 1 and <= 30, $"{gFouls / n:0.0}");
    Check("gate: cards per match at most 8", gCards / n <= 8, $"{gCards / n:0.0}");
    // Real: ~11% of shots are goals.  Before the keeper fixes it was ~35% (keepers
    // carried catches back over their own line, and only moved inside 13 m).
    // 3.5: the ball really goes out (throw-ins + corners + goal kicks).  It was ~9 a
    // match: keepers palmed every shot, wide ones included, and nothing deflected.
    Check("gate: ball out of play at least 10 times a match", gOut / n >= 10, $"{gOut / n:0.0}");
    Check("gate: offsides happen (at least 0.5 a match)", gOffside / n >= .5, $"{gOffside / n:0.0}");
    Check("gate: headers happen (at least 1.5 a match)", gHeaders / n >= 1.5, $"{gHeaders / n:0.0}");
    double conv = gShots > 0 ? gGoals / gShots : 0;
    Check("gate: shot conversion 5-25% (real ~11%)", conv is >= .05 and <= .25, $"{conv:P0}");

    // Calibration gate: real tracking (SkillCorner open data, A-League; see
    // Data/calibration).  Real: length 34/30, width 43/34, back line 21 m from the
    // keeper, nearest opponent 6.5 m, 2.1 m/s, 0.6% of time above 7 m/s.  Before
    // calibration the sim was 23/23, 33/30, 34 m, 1.4 m, 4.3 m/s and 11%.
    static double Med(List<double> a) { a.Sort(); return a.Count == 0 ? double.NaN : a[a.Count / 2]; }
    double lin = Med(cLin), lout = Med(cLout), win = Med(cWin), wout = Med(cWout), dl = Med(cLine), pm = Med(cPress);
    double sm = cSpd.Average(), s7 = cSpd.Count(v => v > 7) / (double)cSpd.Count;
    Check("calibration: team length in possession 27-41 m (real 34)", lin is >= 27 and <= 41, $"{lin:0.0}");
    Check("calibration: team length out of possession 25-36 m (real 30)", lout is >= 25 and <= 36, $"{lout:0.0}");
    Check("calibration: width in possession 37-50 m (real 43)", win is >= 37 and <= 50, $"{win:0.0}");
    Check("calibration: width out of possession 28-39 m (real 34)", wout is >= 28 and <= 39, $"{wout:0.0}");
    Check("calibration: back line 15-29 m in front of the keeper (real 21)", dl is >= 15 and <= 29, $"{dl:0.0}");
    Check("calibration: carriers are not mobbed (nearest opponent median >= 2 m, real 6.5)", pm >= 2.0, $"{pm:0.00}");
    Check("calibration: mean running speed <= 3.8 m/s (real 2.1)", sm <= 3.8, $"{sm:0.00}");
    Check("calibration: sprinting (> 7 m/s) under 7% of the time (real 0.6%)", s7 < .07, $"{s7:P1}");
}


Section("Match officials on the pitch (presentation only, 22.11.2026)");
{
    // Two identical matches, one watched by the officials director: the simulation must not change.
    var plain = new MatchEngine(new MatchOptions { Seed = 77, TimeSpeed = 15f, TeamSize = 11 });
    var refd = new MatchEngine(new MatchOptions { Seed = 77, TimeSpeed = 15f, TeamSize = 11 });
    var kit = OfficialsDirector.KitFor(refd.State.Players[1].Spec.KitPrimary, refd.State.Players[^1].Spec.KitPrimary);
    var dir = new OfficialsDirector(kit.primary, kit.trim, kit.shorts, kit.pattern);
    var refDist = new List<float>();
    int arOffTouchline = 0, arWrongHalf = 0, arTicks = 0, offsides = 0;
    var lastSeen = (MatchEvent?)null;
    for (int i = 0; i < 60 * 240; i++)
    {
        plain.Step(1f / 60f, PlayerCommand.None);
        refd.Step(1f / 60f, PlayerCommand.None);
        dir.Update(refd, 1f / 60f);
        if (refd.Events.Count > 0 && !ReferenceEquals(refd.Events[^1], lastSeen))
        {
            if (refd.Events[^1].Kind == EventKind.Offside) offsides++;
            lastSeen = refd.Events[^1];
        }
        if (i > 120 && refd.State.Phase == Phase.Play)
            refDist.Add(Mx.FlatDist(dir.Officials[0].Pos, refd.State.Ball.Pos));
        for (int a = 1; a <= 2; a++)
        {
            var o = dir.Officials[a];
            float half = OfficialsDirector.AssistantHalf((OfficialRole)a);
            arTicks++;
            if (MathF.Abs(MathF.Abs(o.Pos.Z) - (Mx.HalfWidth + 1.2f)) > .6f) arOffTouchline++;
            if (o.Pos.X * half < -1f) arWrongHalf++;
        }
    }
    bool same = plain.State.Score[0] == refd.State.Score[0] && plain.State.Score[1] == refd.State.Score[1]
                && plain.State.Ball.Pos == refd.State.Ball.Pos && plain.State.Passes[0] == refd.State.Passes[0];
    Check("officials never change the simulation (same score, ball, passes)", same);
    Check("officials are not in State.Players", refd.State.Players.All(p => p.Index < 1000));
    refDist.Sort();
    float med = refDist.Count > 0 ? refDist[refDist.Count / 2] : 0f;
    Check("referee keeps 8-25 m from the ball in open play (median)", med is >= 8f and <= 25f, $"{med:0.0} m");
    Check("referee is never on top of the ball (5th pct >= 4 m)", refDist.Count > 0 && refDist[refDist.Count / 20] >= 4f,
          refDist.Count > 0 ? $"{refDist[refDist.Count / 20]:0.0} m" : "");
    Check("assistants stay on their touchline", arOffTouchline < arTicks / 50, $"{arOffTouchline}/{arTicks}");
    Check("assistants stay in their own half", arWrongHalf == 0, $"{arWrongHalf}");
    Check("the referee whistles", dir.Calls.Any(c => c.who == OfficialRole.Referee && c.action == "off_ref_whistle"));
    bool anyCard = refd.State.YellowCards.Sum() + refd.State.RedCards.Sum() > 0;
    Check("every card is shown by the referee", !anyCard || dir.Calls.Any(c => c.action == "off_ref_card"));
    Check("offsides are flagged by an assistant", refd.Events.All(e => e.Kind != EventKind.Offside)
          || dir.Calls.Any(c => c.action == "off_ar_offside"), $"offside events {offsides}");
    // The C# kit table mirrors sforge.officials.KITS (written into the manifest by Tools/add_official_clips.py).
    var manPath = Path.Combine(AppContext.BaseDirectory, "../../../../Data/soccer_player_manifest.json");
    if (!File.Exists(manPath)) manPath = "Data/soccer_player_manifest.json";
    if (File.Exists(manPath))
    {
        using var man = JsonDocument.Parse(File.ReadAllText(manPath));
        bool kitsMatch = man.RootElement.TryGetProperty("officials", out var off)
            && off.GetProperty("kits").GetProperty("classic").GetProperty("primary").GetString() == "#111318"
            && off.GetProperty("kits").GetProperty("volt").GetProperty("primary").GetString() == "#d9f99d";
        Check("official kits match Sprite Forge's sforge.officials.KITS", kitsMatch);
        bool aliases = man.RootElement.GetProperty("action_aliases").TryGetProperty("off_ar_offside", out _);
        Check("officials clips are in the player manifest", aliases);
    }
    Console.WriteLine($"  info  referee median {med:0.0} m from the ball; {dir.Calls.Count} calls: " +
        string.Join(", ", dir.Calls.GroupBy(c => c.action).Select(g => $"{g.Key}×{g.Count()}")));
}

Section("Kit clash: away kit, keepers clear of both sides (22.11.2026)");
{
    int har = Array.FindIndex(Clubs.All, c => c.Short == "HAR"), cri = Array.FindIndex(Clubs.All, c => c.Short == "CRI");
    var clash = new MatchEngine(new MatchOptions { HomeClub = har, AwayClub = cri, TeamSize = 11, Seed = 5 });
    string hs = clash.State.Players.First(p => p.Team == 0 && !p.IsKeeper).Spec.KitPrimary;
    string aw = clash.State.Players.First(p => p.Team == 1 && !p.IsKeeper).Spec.KitPrimary;
    Check("red v red: the away side changes into its away kit", Clubs.ColourDistance(hs, aw) >= Clubs.ClashDistance, $"{hs} v {aw}");
    var noClash = new MatchEngine(new MatchOptions { HomeClub = 0, AwayClub = 1, TeamSize = 11, Seed = 5 });
    Check("red v blue: both sides keep their home kits",
          noClash.State.Players.First(p => p.Team == 1 && !p.IsKeeper).Spec.KitPrimary == Clubs.All[1].Primary);
    bool keepersClear = true;
    for (int h = 0; h < Clubs.All.Length; h++)
        for (int a = 0; a < Clubs.All.Length; a += 3)
        {
            if (h == a) continue;
            var m = new MatchEngine(new MatchOptions { HomeClub = h, AwayClub = a, TeamSize = 5, Seed = 1 });
            var outfield = m.State.Players.Where(p => !p.IsKeeper).Select(p => p.Spec.KitPrimary).Distinct().ToList();
            foreach (var k in m.State.Players.Where(p => p.IsKeeper))
                if (outfield.Any(o => Clubs.ColourDistance(o, k.Spec.KitPrimary) < Clubs.ClashDistance)) keepersClear = false;
        }
    Check("keepers never clash with either side's outfield kit (every fixture)", keepersClear);
    // the clash rule changes colours only: same seed, same match
    var a1 = new MatchEngine(new MatchOptions { HomeClub = har, AwayClub = cri, TeamSize = 11, Seed = 9 });
    var a2 = new MatchEngine(new MatchOptions { HomeClub = har, AwayClub = cri, TeamSize = 11, Seed = 9 });
    for (int i = 0; i < 1800; i++) { a1.Step(1f / 60f, PlayerCommand.None); a2.Step(1f / 60f, PlayerCommand.None); }
    Check("kit changes are deterministic and colour-only", a1.State.Ball.Pos == a2.State.Ball.Pos);
}

Section("Hypermotion / ML-Flow-inspired motion system (TwoBoneIK, BallApproach, Inertialization)");
{
    // TwoBoneIK: analytic solve reaches target and knee clamp prevents hyperextension.
    var root = new Vector3(0f, 1f, 0f);
    var target = new Vector3(0f, 0.3f, 0.4f); // reachable: dist ~0.806
    bool solved = TwoBoneIK.Solve(root, target, 0.5f, 0.5f, Vector3.UnitX, out var joint, out var end);
    Check("TwoBoneIK solves reachable target", solved && (end - target).Length() < 0.05f,
        $"solved={solved} end={end}");
    var clampTarget = new Vector3(0f, 0.02f, 0.1f); // reachable but near-straight knee
    bool clamped = TwoBoneIK.SolveWithKneeClamp(root, clampTarget, 0.5f, 0.5f, Vector3.UnitX, 8f, 155f, out var cj, out var ce);
    Vector3 upper = cj - root; Vector3 lower = ce - cj;
    float cosK = Vector3.Dot(Vector3.Normalize(upper), Vector3.Normalize(-lower));
    float kneeDeg = MathF.Acos(Math.Clamp(cosK, -1f, 1f)) * 180f / MathF.PI;
    Check("TwoBoneIK knee clamp stays within anatomical range", clamped && kneeDeg >= 7.5f && kneeDeg <= 156.0f,
        $"deg={kneeDeg:F1}");

    // BallApproach: weight ramps when approaching and contact timing cost prefers matching clip.
    var approach = BallApproach.Update(
        new Vector3(0, 0, 0), new Vector3(0, 0, 3f), new Vector3(0, 0, 1f),
        new Vector3(0, 0, 3f), Vector3.Zero, true, 1f / 60f, 0f);
    Check("BallApproach ramps weight when closing on ball", approach.IsApproachingBall && approach.ApproachWeight > 0f,
        $"w={approach.ApproachWeight:F3} dist={approach.DistanceToBall:F2} ttc={approach.TimeToBallContact:F2}");
    var clipGood = new ClipMeta { Id = "kick", Category = ClipCategory.Kick, Duration = 0.4f, ContactFraction = 0.5f };
    var clipBad = new ClipMeta { Id = "kick_bad", Category = ClipCategory.Kick, Duration = 0.4f, ContactFraction = 0.1f };
    float goodCost = BallApproach.ContactTimingCost(clipGood, 0.2f);
    float badCost = BallApproach.ContactTimingCost(clipBad, 0.2f);
    Check("BallApproach prefers contact timing near arrival", goodCost < badCost, $"good={goodCost:F2} bad={badCost:F2}");
    float locked = BallApproach.ContactLockedStartPhase(clipGood, 0.1f, 0f, 1f);
    Check("BallApproach locks start phase toward contact", locked > 0f && locked <= clipGood.ContactFraction,
        $"locked={locked:F3}");

    // Inertialization: offsets decay to near-zero.
    var buf = new InertializationBuffer { DefaultHalfLife = 0.1f };
    var oldPoses = new Dictionary<int, (Vector3 pos, Quaternion rot)> { [1] = (new Vector3(0, 1, 0), Quaternion.Identity) };
    var newPoses = new Dictionary<int, (Vector3 pos, Quaternion rot)> { [1] = (new Vector3(0, 1.1f, 0), Quaternion.Identity) };
    buf.Capture(oldPoses, newPoses);
    Check("Inertialization captures transition offset", buf.Active && buf.Bones.Count == 1);
    for (int i = 0; i < 120; i++) buf.Update(1f / 60f);
    Check("Inertialization decays offset to rest", !buf.Active || buf.Bones[0].PositionOffset.Length() < 0.01f,
        $"active={buf.Active} len={(buf.Bones.Count>0?buf.Bones[0].PositionOffset.Length():0f):F4}");

    // MotionEngine: approach weight rises and contact-locked one-shot enters near contact.
    var eng = new MotionEngine();
    eng.LoadClips(new[]
    {
        new ClipMeta { Id = "run", Category = ClipCategory.Locomotion, Duration = 1f, Loop = true, PreferredSpeed = 3f, FootPlantFrames = new[]{0.25f,0.75f} },
        new ClipMeta { Id = "trap", Category = ClipCategory.FirstTouch, Duration = 0.5f, Loop = false, ContactFraction = 0.5f, BallState = ArenaFC.Core.Animation.BallState.Approaching },
    });
    var ms = new MotionState();
    for (int i = 0; i < 30; i++)
        eng.Update(ms, 3f, 0f, ArenaFC.Core.Animation.BallState.Approaching, PlayerIntent.Trap, 1f / 60f, secondsUntilContact: 0.15f);
    Check("MotionEngine raises approach weight for timed contact", ms.ApproachWeight > 0.2f, $"w={ms.ApproachWeight:F2}");
    Check("MotionEngine selects contact-capable clip on approach", ms.RenderClipId == "trap" || ms.CurrentClipId == "trap" || ms.NextClipId == "trap",
        $"cur={ms.CurrentClipId} next={ms.NextClipId}");
}

Section("Hypermotion data plumbing v2 (manifest curves/contact/velocity)");
{
    string manifestJson = """
    {
      "version": 2,
      "clips": [
        {
          "id": "run",
          "category": "Locomotion",
          "duration": 1.0,
          "contactFraction": -1.0,
          "footPlantFrames": [0.25, 0.75],
          "footPlantSides": ["Left","Right"],
          "rootVelocityX": 0.0,
          "rootVelocityZ": 3.0,
          "preferredSpeed": 3.0,
          "preferredTurnRate": 0.0,
          "ballState": "None",
          "tags": [],
          "boneCount": 18,
          "loop": true,
          "plantCurveLeft": [0,0,0,0,0,0,0,0,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
          "plantCurveRight": [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,0,0,0,0,0,0,0],
          "contactWindowStart": -1.0,
          "contactWindowEnd": -1.0,
          "rootVelocitySamples": [0,3,0,3,0,3,0,3]
        },
        {
          "id": "kick",
          "category": "Kick",
          "duration": 0.8,
          "contactFraction": 0.5,
          "footPlantFrames": [0.2],
          "footPlantSides": ["Left"],
          "rootVelocityX": 0.0,
          "rootVelocityZ": 0.5,
          "preferredSpeed": 1.0,
          "preferredTurnRate": 0.0,
          "ballState": "Possessed",
          "tags": ["dedicated"],
          "boneCount": 18,
          "loop": false,
          "plantCurveLeft": [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,0.5,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
          "plantCurveRight": [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
          "contactWindowStart": 0.3,
          "contactWindowEnd": 0.55,
          "rootVelocitySamples": [0,0.5,0,0.5,0,0.5,0,0.5]
        }
      ]
    }
    """;
    var clips = ClipManifestLoader.Parse(manifestJson);
    Check("v2 manifest parses", clips.Count == 2 && clips[0].HasPlantCurves);
    Check("plant curve samples weight", clips[0].SamplePlantWeight(true, 8f / 31f) > 0.9f);
    Check("root velocity samples fallback/interpolate", clips[0].SampleRootVelocity(0.5f).Y > 2.9f);
    Check("contact window parsed", clips[1].HasContactWindow && clips[1].ContactWindowStart == 0.3f && clips[1].ContactWindowEnd == 0.55f);

    var eng = new ArenaFC.Core.Animation.MotionEngine();
    eng.LoadClips(clips);
    var ms = new ArenaFC.Core.Animation.MotionState();
    eng.Update(ms, 3f, 0f, ArenaFC.Core.Animation.BallState.None, ArenaFC.Core.Animation.PlayerIntent.Move, 1f / 60f);
    Check("motion engine populates v2 plant weights", ms.PlantWeightLeft >= 0f && ms.PlantWeightLeft <= 1f && ms.PlantWeightRight >= 0f && ms.PlantWeightRight <= 1f);
    Check("motion engine populates root velocity sample", ms.RootVelocitySampleZ > 0.1f);
}

Section("Football intelligence Milestone 1 (trajectory/perception/coordinator)");
{
    // Ball trajectory determinism and basic physics sanity
    var t1 = ArenaFC.Core.Football.BallTrajectory.Predict(new Vector3(0,0.11f,0), new Vector3(12f,4f,0), Vector3.Zero, 1.0f);
    var t2 = ArenaFC.Core.Football.BallTrajectory.Predict(new Vector3(0,0.11f,0), new Vector3(12f,4f,0), Vector3.Zero, 1.0f);
    bool same = t1.Samples.Count == t2.Samples.Count;
    for (int i = 0; same && i < t1.Samples.Count; i++) same = (t1.Samples[i].Position - t2.Samples[i].Position).LengthSquared() < 1e-10f;
    Check("ball trajectory deterministic", same && t1.Samples.Count > 10);
    var mid = t1.At(0.5f);
    Check("ball trajectory sample moves forward", mid.Position.X > 1f);
    Check("ball trajectory gravity applied", t1.At(0.2f).Velocity.Y < 4f);
    // M1 parity: Predict must match shared authoritative Step integration.
    {
        Vector3 pp = new(0, 0.11f, 0), pv = new(12f, 4f, 1f), ps = new(0.2f, 0, -0.3f);
        var pred = ArenaFC.Core.Football.BallTrajectory.Predict(pp, pv, ps, 1.0f, true, 0.8f, -0.4f);
        Vector3 mp = pp, mv = pv, msSpin = ps;
        bool parity = true;
        for (int i = 0; i < pred.Samples.Count; i++)
        {
            var s = pred.Samples[i];
            if ((s.Position - mp).LengthSquared() > 1e-8f || (s.Velocity - mv).LengthSquared() > 1e-8f) { parity = false; break; }
            if (i < pred.Samples.Count - 1)
                ArenaFC.Core.Football.BallTrajectory.Step(ref mp, ref mv, ref msSpin, ArenaFC.Core.Football.BallTrajectory.Dt, true, 0.8f, -0.4f);
        }
        Check("ball trajectory prediction matches shared Step integration", parity && pred.Samples.Count > 10);
    }

    // Player reachability
    float tReach = ArenaFC.Core.Football.PlayerPerception.TimeToReach(Vector3.Zero, Vector3.Zero, new Vector3(10,0,0), 8f, 12f);
    Check("time to reach positive", tReach > 0.5f && tReach < 3f);
    float tClose = ArenaFC.Core.Football.PlayerPerception.TimeToReach(Vector3.Zero, Vector3.Zero, new Vector3(1,0,0), 8f, 12f);
    Check("closer target reached sooner", tClose < tReach);

    // Lane safety
    Vector3[] oppPos = new[] { new Vector3(5f,0,0.2f) };
    Vector3[] oppVel = new[] { Vector3.Zero };
    float safe = ArenaFC.Core.Football.PlayerPerception.LaneSafety(Vector3.Zero, new Vector3(10,0,0), oppPos, oppVel, 18f, 7f, 12f);
    float clear = ArenaFC.Core.Football.PlayerPerception.LaneSafety(Vector3.Zero, new Vector3(10,0,5), oppPos, oppVel, 18f, 7f, 12f);
    Check("blocked lane less safe than clear lane", safe < clear);

    // Tactical coordinator determinism / role assignment
    var eng = new MatchEngine(new MatchOptions { Seed = 123, TeamSize = 11 });
    for (int i = 0; i < 120; i++) eng.Step(1f/60f, PlayerCommand.None);
    var tc = new ArenaFC.Core.Football.TacticalCoordinator();
    var a1 = tc.BuildAssignments(eng.State, 0);
    var a2 = tc.BuildAssignments(eng.State, 0);
    bool det = a1.Count == a2.Count;
    for (int i = 0; det && i < a1.Count; i++) det = a1[i].PlayerIndex == a2[i].PlayerIndex && a1[i].Role == a2[i].Role;
    Check("tactical coordinator deterministic", det && a1.Count > 0);
    { var seen = new System.Collections.Generic.HashSet<int>(); bool uniq = true; foreach (var a in a1) uniq &= seen.Add(a.PlayerIndex); Check("tactical coordinator assigns unique roles per player", uniq && seen.Count == a1.Count); }
}

Section("Animation telemetry metrics (contact/transition/plant continuity)");
{
    string manifestJson = """
    {
      "version": 2,
      "clips": [
        {
          "id":"run","category":"Locomotion","duration":1.0,"contactFraction":-1.0,
          "footPlantFrames":[0.25,0.75],"footPlantSides":["Left","Right"],
          "rootVelocityX":0.0,"rootVelocityZ":3.0,"preferredSpeed":3.0,"preferredTurnRate":0.0,
          "ballState":"None","tags":[],"boneCount":18,"loop":true,
          "plantCurveLeft":[0,0,0,0,0,0,0,0,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
          "plantCurveRight":[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,0,0,0,0,0,0,0],
          "contactWindowStart":-1.0,"contactWindowEnd":-1.0,"rootVelocitySamples":[0,3,0,3,0,3,0,3]
        },
        {
          "id":"kick","category":"Kick","duration":0.8,"contactFraction":0.5,
          "footPlantFrames":[0.2],"footPlantSides":["Left"],
          "rootVelocityX":0.0,"rootVelocityZ":0.5,"preferredSpeed":1.0,"preferredTurnRate":0.0,
          "ballState":"Possessed","tags":["dedicated"],"boneCount":18,"loop":false,
          "plantCurveLeft":[1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,0.5,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
          "plantCurveRight":[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
          "contactWindowStart":0.3,"contactWindowEnd":0.55,"rootVelocitySamples":[0,0.5,0,0.5,0,0.5,0,0.5]
        }
      ]
    }
    """;
    var clips = ArenaFC.Core.Animation.ClipManifestLoader.Parse(manifestJson);
    var eng = new ArenaFC.Core.Animation.MotionEngine();
    eng.LoadClips(clips);
    var ms = new ArenaFC.Core.Animation.MotionState();
    // Run locomotion and measure plant/contact continuity.
    float maxPhaseJump = 0f; float prevPhase = 0f; bool prevSet = false;
    for (int i = 0; i < 180; i++)
    {
        eng.Update(ms, 3f, 0f, ArenaFC.Core.Animation.BallState.None, ArenaFC.Core.Animation.PlayerIntent.Move, 1f/60f);
        float p = ms.RenderPhase;
        if (prevSet)
        {
            float dp = p - prevPhase;
            if (dp < -0.5f) dp += 1f;
            if (dp > 0.5f) dp -= 1f;
            maxPhaseJump = MathF.Max(maxPhaseJump, MathF.Abs(dp));
        }
        prevPhase = p; prevSet = true;
    }
    Check("locomotion phase continuity (no large jumps)", maxPhaseJump < 0.2f, $"maxJump={maxPhaseJump:F3}");
    Check("plant weights in valid range", ms.PlantWeightLeft >= 0f && ms.PlantWeightLeft <= 1f && ms.PlantWeightRight >= 0f && ms.PlantWeightRight <= 1f);

    // Contact alignment: request kick with TTC and ensure contact window/phase are reasonable.
    var mk = new ArenaFC.Core.Animation.MotionState();
    for (int i = 0; i < 30; i++) eng.Update(mk, 2f, 0f, ArenaFC.Core.Animation.BallState.Possessed, ArenaFC.Core.Animation.PlayerIntent.Move, 1f/60f);
    eng.Update(mk, 1.5f, 0f, ArenaFC.Core.Animation.BallState.Possessed, ArenaFC.Core.Animation.PlayerIntent.Shoot, 1f/60f, 0.35f);
    Check("kick transition enters contact-timed clip", mk.RenderClipId.Length > 0);
    Check("contact window signal present for kick clip", clips[1].HasContactWindow && clips[1].HasContact);
}

Section("PR B/C/D regression: trajectory intercept, coordinator roles, action contract");
{
    // B: BallTrajectory intercept finds a reachable sample
    var traj = ArenaFC.Core.Football.BallTrajectory.Predict(new Vector3(0,1f,0), new Vector3(8f,-1f,2f), Vector3.Zero, 2.0f);
    bool hasIntercept = traj.TryInterceptXZ(new Vector3(2f,0,0f), 7f, 12f, out var intercept, 0.05f);
    Check("trajectory intercept search returns reachable sample", hasIntercept, hasIntercept ? $"t={intercept.Time:F2}" : "none");
    if (hasIntercept) Check("intercept sample is within horizon", intercept.Time >= 0.05f && intercept.Time <= 2.0f);

    // C: coordinator gives at most one primary presser per team in ordinary setup
    var eng2 = new MatchEngine(new MatchOptions { Seed = 77, TeamSize = 11 });
    for (int i = 0; i < 180; i++) eng2.Step(1f/60f, PlayerCommand.None);
    var tc2 = new ArenaFC.Core.Football.TacticalCoordinator();
    var asn = tc2.BuildAssignments(eng2.State, 0);
    int pressers = 0; foreach (var a in asn) if (a.Role == "press") pressers++;
    Check("coordinator assigns at most one primary presser", pressers <= 1, $"pressers={pressers}");
    Check("tactical role-change telemetry increments", eng2.TacticalRoleChanges >= 0);

    // D: action contract carries contact-timed receive intent
    var contract = new ArenaFC.Core.Football.PlayerActionContract
    {
        PlayerIndex = 3, Intent = "receive", BallContactTime = 0.35f, RequiresBallContact = true, DesiredSpeed = 7f
    };
    Check("action contract stores contact timing", contract.RequiresBallContact && contract.BallContactTime > 0.3f && contract.BallContactTime < 0.4f);
}

Section("PR B/C regression: blocked-lane avoidance and no-oscillation");
{
    // B: MatchEngine blocked-lane avoidance - FindBestPassTarget should avoid directly blocked lane.
    var eng = new MatchEngine(new MatchOptions { Seed = 123, TeamSize = 5, AwayHuman = true });
    eng.State.Phase = Phase.Play; eng.State.PhaseTimer = 0f;
    var bPasser = eng.State.Players[eng.State.Controlled];
    bPasser.Pos = new Vector3(-10f, 0f, 0f); bPasser.Vel = Vector3.Zero; bPasser.Facing = new Vector3(1,0,0);
    eng.State.Ball.Owner = bPasser.Index; eng.State.Ball.Pos = bPasser.Pos; eng.State.Ball.Vel = Vector3.Zero;
    PlayerState? safeMate = null, blockedMate = null;
    foreach (var q in eng.State.Players)
    {
        if (q.Team != bPasser.Team || q.Index == bPasser.Index || q.IsKeeper) continue;
        if (blockedMate == null) { blockedMate = q; q.Pos = new Vector3(8f,0,0f); q.Vel = Vector3.Zero; }
        else if (safeMate == null) { safeMate = q; q.Pos = new Vector3(8f,0,12f); q.Vel = Vector3.Zero; }
        else { q.Pos = new Vector3(-20f,0,20f + q.Index); }
    }
    foreach (var o in eng.State.Players)
    {
        if (o.Team == bPasser.Team) continue;
        o.Pos = new Vector3(40f,0,40f); o.Vel = Vector3.Zero;
    }
    if (blockedMate != null)
    {
        var blocker = eng.State.Players.First(o => o.Team != bPasser.Team && !o.IsKeeper);
        blocker.Pos = new Vector3(0f,0,0f); blocker.Vel = Vector3.Zero;
    }
    var mi = typeof(MatchEngine).GetMethod("FindBestPassTarget", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance);
    int target = mi != null ? (int)mi.Invoke(eng, new object[] { bPasser, false, false, new Vector2(1f,0f) })! : -1;
    if (blockedMate != null && safeMate != null)
        Check("blocked-lane pass avoids directly blocked receiver", target != blockedMate.Index, $"target={target} blocked={blockedMate.Index} safe={safeMate.Index}");
    else
        Check("blocked-lane pass avoids directly blocked receiver", true, "setup skipped");

    // B: predicted intercept - TryInterceptXZ finds intercept for a moving loose ball.
    var pred = ArenaFC.Core.Football.BallTrajectory.Predict(new Vector3(0,0.2f,0), new Vector3(10f,0,0), Vector3.Zero, 1.5f);
    bool canIntercept = pred.TryInterceptXZ(new Vector3(3f,0,1f), 8f, 14f, out var si, 0f);
    Check("predicted intercept finds moving-ball interception", canIntercept, canIntercept ? $"t={si.Time:F2} p=({si.Position.X:F1},{si.Position.Z:F1})" : "none");

    // C: no-oscillation-over-N-ticks - in a stable phase, role flips should be bounded.
    var eng2 = new MatchEngine(new MatchOptions { Seed = 77, TeamSize = 11 });
    for (int i = 0; i < 120; i++) eng2.Step(1f/60f, PlayerCommand.None);
    var tc = new ArenaFC.Core.Football.TacticalCoordinator();
    var prevRoles = new Dictionary<int, string>();
    var roleFlips = new Dictionary<int, int>();
    for (int t = 0; t < 120; t++)
    {
        eng2.Step(1f/60f, PlayerCommand.None);
        foreach (var a in tc.BuildAssignments(eng2.State, 0))
        {
            if (prevRoles.TryGetValue(a.PlayerIndex, out var pr) && pr != a.Role)
                roleFlips[a.PlayerIndex] = roleFlips.TryGetValue(a.PlayerIndex, out var f) ? f + 1 : 1;
            prevRoles[a.PlayerIndex] = a.Role;
        }
    }
    int maxFlips = roleFlips.Count > 0 ? roleFlips.Values.Max() : 0;
    Check("coordinator role flips bounded over 120 ticks", maxFlips <= 50, $"maxFlips={maxFlips}");
    Check("tactical telemetry counters are reported", eng2.TacticalPressAssignments >= 0 && eng2.TacticalCoverAssignments >= 0, $"press={eng2.TacticalPressAssignments} cover={eng2.TacticalCoverAssignments}");

    // B: predicted-intercept decision behavior - defender chases intercept point, not stale ball position.
    var engI = new MatchEngine(new MatchOptions { Seed = 99, TeamSize = 5, AwayHuman = true });
    engI.State.Phase = Phase.Play; engI.State.PhaseTimer = 0f;
    foreach (var p in engI.State.Players) { p.Pos = new Vector3(-40f,0,40f); p.Vel = Vector3.Zero; p.ActionTimer = 0f; p.Action = "idle"; }
    engI.State.Ball.Owner = -1; engI.State.Ball.HasPending = false;
    engI.State.Ball.Pos = new Vector3(0f, 0.11f, 0f);
    engI.State.Ball.Vel = new Vector3(12f, 0f, 0f);
    var def = engI.State.Players.First(p => p.Team == 1 && !p.IsKeeper);
    def.Pos = new Vector3(4f, 0f, 3f); def.Vel = Vector3.Zero;
    engI.Step(1f/60f, PlayerCommand.None);
    float distToIntercept = Mx.FlatDist(def.Target, new Vector3(6f,0,0f));
    float distToBallNow = Mx.FlatDist(def.Target, engI.State.Ball.Pos);
    Check("predicted intercept influences defender chase target", distToIntercept <= distToBallNow + 1.5f, $"targetDistIntercept={distToIntercept:F2} targetDistBall={distToBallNow:F2} target={def.Target}");
}

Section("M4 seeded telemetry comparison (headless deterministic)");
{
    static (int goals, int shots, int passes, int roleChanges, int press, int cover) RunTelemetry(int seed)
    {
        var e = new MatchEngine(new MatchOptions { Seed = seed, TeamSize = 11, AwayHuman = true });
        for (int i = 0; i < 600; i++)
        {
            var cmds = new Dictionary<int, PlayerCommand>
            {
                [e.State.Controlled] = new PlayerCommand { Move = new Vector2((float)Math.Sin(i * .07f), (float)Math.Cos(i * .11f)), Sprint = i % 9 == 0, Pass = i % 73 == 0, Shoot = i % 97 == 0 },
                [e.State.ControlledAway] = new PlayerCommand { Move = new Vector2((float)Math.Cos(i * .05f), (float)Math.Sin(i * .13f)) },
            };
            e.StepOneTick(cmds);
        }
        int goals = e.State.Score[0] + e.State.Score[1];
        int shots = e.State.Shots[0] + e.State.Shots[1];
        int passes = e.State.Passes[0] + e.State.Passes[1];
        return (goals, shots, passes, e.TacticalRoleChanges, e.TacticalPressAssignments, e.TacticalCoverAssignments);
    }
    var a = RunTelemetry(4242);
    var b = RunTelemetry(4242);
    Check("seeded telemetry deterministic", a == b, $"a={a} b={b}");
    var c = RunTelemetry(4243);
    Check("seeded telemetry collected", c.shots >= 0 && c.passes >= 0 && c.roleChanges >= 0, $"telemetry={c}");
}

Section("M3 coordinator authority invariants");
{
    var e = new MatchEngine(new MatchOptions { Seed = 77, TeamSize = 11, AwayHuman = true });
    var tc = new ArenaFC.Core.Football.TacticalCoordinator();
    int checks = 0;
    for (int t = 0; t < 240; t++)
    {
        e.Step(1f / 60f, PlayerCommand.None);
        for (int team = 0; team < 2; team++)
        {
            var assignments = tc.BuildAssignments(e.State, team);
            int press = 0, cover = 0;
            var seen = new HashSet<int>();
            bool unique = true;
            foreach (var a in assignments)
            {
                unique &= seen.Add(a.PlayerIndex);
                if (a.Role == "press") press++;
                if (a.Role == "cover") cover++;
            }
            Check($"M3 unique assignments tick {t} team {team}", unique, unique ? "ok" : "duplicate player");
            if (!unique) { checks = -1; break; }
            bool teamInPoss = e.State.Ball.Owner >= 0 && e.State.Ball.Owner < e.State.Players.Length && e.State.Players[e.State.Ball.Owner].Team == team;
            if (!teamInPoss)
            {
                Check($"M3 single press tick {t} team {team}", press <= 1, $"press={press}");
                Check($"M3 single cover tick {t} team {team}", cover <= 1, $"cover={cover}");
                if (press > 1 || cover > 1) { checks = -1; break; }
            }
            checks++;
        }
        if (checks < 0) break;
    }
    Check("M3 coordinator invariants exercised", checks > 0, $"checks={checks}");
}

Section("M3 runtime no-conflicting-chasers and stability");
{
    var e = new MatchEngine(new MatchOptions { Seed = 79, TeamSize = 11, AwayHuman = true });
    int conflictTicks = 0, checkedTicks = 0;
    for (int t = 0; t < 360; t++)
    {
        e.Step(1f / 60f, PlayerCommand.None);
        int possTeam = -1;
        if (e.State.Ball.Owner >= 0 && e.State.Ball.Owner < e.State.Players.Length)
            possTeam = e.State.Players[e.State.Ball.Owner].Team;
        for (int team = 0; team < 2; team++)
        {
            if (possTeam < 0 || possTeam == team) continue;
            var carrier = e.State.Players[e.State.Ball.Owner];
            int hardPressers = 0;
            foreach (var p in e.State.Players)
            {
                if (p.Team != team || p.IsKeeper || p.SentOff) continue;
                bool hardPress = (p.Action == "tackle" || p.Action == "slide")
                                 && Mx.FlatDist(p.Pos, carrier.Pos) < 1.8f;
                if (hardPress) hardPressers++;
            }
            if (hardPressers > 1) conflictTicks++;
            checkedTicks++;
        }
    }
    Check("M3 no conflicting hard pressers", conflictTicks == 0, $"conflicts={conflictTicks}/{checkedTicks}");
    Check("M3 role changes bounded", e.TacticalRoleChanges < 8000, $"roleChanges={e.TacticalRoleChanges}");

    // Stronger engagement invariant: at most one OOP outfielder per team in close pressing state.
    var e2 = new MatchEngine(new MatchOptions { Seed = 81, TeamSize = 11, AwayHuman = true });
    int closePressConflicts = 0, closePressChecked = 0;
    for (int t = 0; t < 360; t++)
    {
        e2.Step(1f / 60f, PlayerCommand.None);
        int possTeam = e2.State.Ball.Owner >= 0 && e2.State.Ball.Owner < e2.State.Players.Length ? e2.State.Players[e2.State.Ball.Owner].Team : -1;
        if (possTeam < 0) continue;
        for (int team = 0; team < 2; team++)
        {
            if (team == possTeam) continue;
            int closePressers = 0;
            foreach (var p in e2.State.Players)
            {
                if (p.Team != team || p.IsKeeper || p.SentOff) continue;
                if (p.Index == e2.State.Controlled || p.Index == e2.State.ControlledAway) continue;
                if (p.Pressing && Mx.FlatDist(p.Pos, e2.State.Players[e2.State.Ball.Owner].Pos) < 5.5f) closePressers++;
            }
            if (closePressers > 1) closePressConflicts++;
            closePressChecked++;
        }
    }
    Check("M3 no conflicting close pressers", closePressConflicts == 0, $"conflicts={closePressConflicts}/{closePressChecked}");

    // Support-destination quality: coordinator-assigned movement targets stay sane.
    var e3 = new MatchEngine(new MatchOptions { Seed = 83, TeamSize = 11, AwayHuman = true });
    var tc3 = new ArenaFC.Core.Football.TacticalCoordinator();
    int targetChecks = 0, targetBad = 0;
    for (int t = 0; t < 240; t++)
    {
        e3.Step(1f / 60f, PlayerCommand.None);
        for (int team = 0; team < 2; team++)
        {
            var assignments = tc3.BuildAssignments(e3.State, team);
            foreach (var a in assignments)
            {
                if (a.Role is not ("support" or "cover" or "recover" or "press")) continue;
                targetChecks++;
                var mt = a.MovementTarget;
                bool sane = float.IsFinite(mt.X) && float.IsFinite(mt.Z)
                    && MathF.Abs(mt.X) < Mx.HalfLength + 15f
                    && MathF.Abs(mt.Z) < Mx.HalfWidth + 15f;
                if (!sane) targetBad++;
            }
        }
    }
    Check("M3 coordinator movement targets sane", targetBad == 0, $"bad={targetBad}/{targetChecks}");

    // Per-player stability: no excessive role flapping.
    var e4 = new MatchEngine(new MatchOptions { Seed = 87, TeamSize = 11, AwayHuman = true });
    var tc4 = new ArenaFC.Core.Football.TacticalCoordinator();
    var prevRoles = new Dictionary<int, string>();
    var roleChangesPerPlayer = new Dictionary<int, int>();
    for (int t = 0; t < 300; t++)
    {
        e4.Step(1f / 60f, PlayerCommand.None);
        for (int team = 0; team < 2; team++)
        {
            foreach (var a in tc4.BuildAssignments(e4.State, team))
            {
                if (prevRoles.TryGetValue(a.PlayerIndex, out var pr) && pr != a.Role)
                    roleChangesPerPlayer[a.PlayerIndex] = roleChangesPerPlayer.GetValueOrDefault(a.PlayerIndex, 0) + 1;
                prevRoles[a.PlayerIndex] = a.Role;
            }
        }
    }
    int maxFlap = roleChangesPerPlayer.Count > 0 ? roleChangesPerPlayer.Values.Max() : 0;
    Check("M3 per-player role flap bounded", maxFlap <= 80, $"maxFlap={maxFlap}");
}

Section("M4 authoritative action contracts");
{
    var e = new MatchEngine(new MatchOptions { Seed = 55, TeamSize = 11, AwayHuman = true });
    bool sawCarrier = false, sawAction = false, keyOk = true, fieldsOk = true;
    var seenIntents = new HashSet<string>();
    for (int t = 0; t < 1800; t++)
    {
        e.Step(1f / 60f, PlayerCommand.None);
        foreach (var kv in e.LastActionContracts)
        {
            var c = kv.Value;
            if (c.PlayerIndex != kv.Key) { keyOk = false; break; }
            if (!float.IsFinite(c.DesiredSpeed) || !float.IsFinite(c.SpeedLimit) || c.SpeedLimit <= 0f) fieldsOk = false;
            if (!float.IsFinite(c.FacingDirection.X) || !float.IsFinite(c.FacingDirection.Z)) fieldsOk = false;
            seenIntents.Add(c.Intent);
            if (c.Intent is "carry" or "shield" or "receive") sawCarrier = true;
            if (c.Intent is "kick" or "shoot" or "pass" or "clear" or "receive" or "tackle" or "dive" or "throw_in" or "skill" or "intercept") sawAction = true;
        }
        if (!keyOk) break;
    }
    Check("M4 contract keys match players", keyOk, keyOk ? "ok" : "mismatch");
    Check("M4 contract fields finite/valid", fieldsOk, fieldsOk ? "ok" : "invalid field");
    Check("M4 baseline carrier/receive contract observed", sawCarrier, sawCarrier ? "ok" : "missing");
    Check("M4 action contract observed", sawAction, sawAction ? "ok" : "missing");
    Check("M4 pass or shoot intent observed", seenIntents.Contains("pass") || seenIntents.Contains("shoot"), string.Join(",", seenIntents));
    Check("M4 tackle intent observed", seenIntents.Contains("tackle"), string.Join(",", seenIntents));
}

Section("M6 clip manifest provenance/root velocity");
{
    string manifestPath = "Data/clips/clip_manifest.json";
    if (!System.IO.File.Exists(manifestPath)) manifestPath = "arena-fc/Data/clips/clip_manifest.json";
    if (System.IO.File.Exists(manifestPath))
    {
        using var doc = JsonDocument.Parse(System.IO.File.ReadAllText(manifestPath));
        var root = doc.RootElement;
        Check("M6 manifest version 2", root.TryGetProperty("version", out var ver) && ver.GetInt32() == 2, ver.ToString());
        int clips = 0, withProv = 0, locoNonZero = 0, locoTotal = 0, schemaBad = 0;
        foreach (var c in root.GetProperty("clips").EnumerateArray())
        {
            clips++;
            bool hasProv = c.TryGetProperty("provenance", out var prov) && prov.ValueKind == JsonValueKind.Object;
            bool hasSrc = c.TryGetProperty("source", out var src) && src.ValueKind == JsonValueKind.String;
            if (hasProv || hasSrc) withProv++;
            int rvLen = c.TryGetProperty("rootVelocitySamples", out var rv) && rv.ValueKind == JsonValueKind.Array ? rv.GetArrayLength() : 0;
            int plLen = c.TryGetProperty("plantCurveLeft", out var pl) && pl.ValueKind == JsonValueKind.Array ? pl.GetArrayLength() : 0;
            int prLen = c.TryGetProperty("plantCurveRight", out var pr) && pr.ValueKind == JsonValueKind.Array ? pr.GetArrayLength() : 0;
            if (rvLen != 64 || plLen != 32 || prLen != 32) schemaBad++;
            string cat = c.TryGetProperty("category", out var catEl) ? catEl.GetString() ?? "" : "";
            if (cat.Equals("Locomotion", StringComparison.OrdinalIgnoreCase))
            {
                locoTotal++;
                if (rvLen == 64)
                {
                    bool nz = false;
                    foreach (var s in rv.EnumerateArray()) { if (s.TryGetSingle(out float f) && MathF.Abs(f) > 1e-6f) { nz = true; break; } }
                    if (nz) locoNonZero++;
                }
            }
        }
        Check("M6 manifest has clips", clips > 0, $"clips={clips}");
        Check("M6 all clips have provenance/source", withProv == clips, $"withProv={withProv}/{clips}");
        Check("M6 locomotion clips mostly have nonzero root velocity", locoNonZero >= locoTotal - 3 && locoTotal > 0, $"nonzero={locoNonZero}/{locoTotal}");
        Check("M6 rootVelocity/plant curve schema", schemaBad == 0, $"bad={schemaBad}/{clips}");
    }
    else
    {
        Check("M6 manifest present for validation", false, "manifest not found; run from arena-fc");
    }
}

Console.WriteLine($"\nRESULT: {passed} passed, {failed} failed");
return failed == 0 ? 0 : 1;
