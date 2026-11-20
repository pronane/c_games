// Arena FC - Training ground coach: one lesson per move, with what to press on
// an Xbox-layout pad (EasySMX and other XInput pads use the same labels) and
// on the keyboard, a plain-English tip, and automatic completion detection.
//
// Prompt text uses tokens the HUD turns into button icons:
//   [A] [B] [X] [Y] [LB] [RB] [LT] [RT] [LS] [RS] [VIEW] [MENU]   pad buttons
//   <E> <Space> <Shift> ...                                          keyboard keys
using System;
using System.Collections.Generic;
using System.Numerics;

namespace ArenaFC.Core;

public enum LessonGoal
{
    MoveDistance, SprintTime, CloseControlTime,
    ShortPass, ThroughBall, LongBall, TeammateRun,
    Shots, Goals, Skill,
    Switch, TackleWin, Slide,
    FreePlay,
}

public sealed class TrainingLesson
{
    public string Title = "";
    public string Section = "";
    public string Pad = "";
    public string Keys = "";
    public string Tip = "";
    public TrainingDrill Drill = TrainingDrill.Attack;
    public LessonGoal Goal;
    public SkillMove Skill = SkillMove.None;
    /// <summary>Repetitions (or metres / seconds for the continuous goals).</summary>
    public float Target = 1f;
}

public sealed class TrainingCoach
{
    public readonly List<TrainingLesson> Lessons = BuildLessons();
    public int Index { get; private set; }
    public float Progress { get; private set; }
    /// <summary>Seconds left on the "well done" flash after a lesson completes.</summary>
    public float CelebrateTimer { get; private set; }
    public string LastFeedback { get; private set; } = "";
    public TrainingLesson Current => Lessons[Math.Clamp(Index, 0, Lessons.Count - 1)];
    public bool AllDone => Index >= Lessons.Count - 1;

    private int _passes, _shots, _goals, _controlled = -1, _owner = -1;
    private MatchEvent? _lastEvent;
    private string _recentButton = "";
    private float _recentButtonTimer;
    private bool _switchPressed;
    private float _advanceTimer = -1f;
    private bool _started;
    private bool _wasSliding;

    public static List<TrainingLesson> BuildLessons() => new()
    {
        new() { Section = "BASICS", Title = "Move with the ball", Goal = LessonGoal.MoveDistance, Target = 12f,
            Pad = "[LS] Left stick", Keys = "<W> <A> <S> <D> or arrow keys",
            Tip = "Push the left stick to run with the ball. Small pushes keep it close; a full push runs faster." },
        new() { Section = "BASICS", Title = "Sprint", Goal = LessonGoal.SprintTime, Target = 2f,
            Pad = "Hold [RT] (or [RB]) while moving", Keys = "Hold <Shift> while moving",
            Tip = "Sprinting is faster but your touches get bigger and stamina drains. Use it in open space." },
        new() { Section = "BASICS", Title = "Close control and shielding", Goal = LessonGoal.CloseControlTime, Target = 2f,
            Pad = "Hold [LT] (or press in [LS]) while moving", Keys = "Hold <X> while moving",
            Tip = "Keeps the ball glued to your feet and puts your body between the ball and a defender. Best in tight spaces." },
        new() { Section = "PASSING", Title = "Short pass", Goal = LessonGoal.ShortPass, Target = 3f,
            Pad = "Aim with [LS], press [A]", Keys = "Aim with <W><A><S><D>, press <E>",
            Tip = "A ground pass to the team-mate you are aiming at. Point the stick at them first." },
        new() { Section = "PASSING", Title = "Through ball", Goal = LessonGoal.ThroughBall, Target = 2f,
            Pad = "Aim with [LS], press [Y]", Keys = "Aim, then press <Q>",
            Tip = "Plays the ball into space ahead of a running team-mate. Aim where they are going, not where they are." },
        new() { Section = "PASSING", Title = "Long ball / cross", Goal = LessonGoal.LongBall, Target = 2f,
            Pad = "Aim with [LS], press [VIEW] (small left-centre button)", Keys = "Aim, then press <R>",
            Tip = "A lofted ball over defenders. Use it to switch play or cross from the wing." },
        new() { Section = "PASSING", Title = "Call a team-mate's run", Goal = LessonGoal.TeammateRun, Target = 1f,
            Pad = "Press [LB] while you have the ball", Keys = "Press <Tab> while you have the ball",
            Tip = "Your nearest team-mate sprints into space towards goal, ready for a through ball." },
        new() { Section = "SHOOTING", Title = "Shoot", Goal = LessonGoal.Shots, Target = 3f,
            Pad = "Hold [X] to power up, release to shoot. Aim with [LS]", Keys = "Hold <Space>, release to shoot",
            Tip = "Watch the power bar under the pitch. Release in the green zone for a well-timed shot; too much power goes over." },
        new() { Section = "SHOOTING", Title = "Score two goals", Goal = LessonGoal.Goals, Target = 2f,
            Pad = "Get close, hold [LS] towards a post, then [X]", Keys = "Steer at a post, then <Space>",
            Tip = "Shots aimed at the corners beat the keeper far more often than shots down the middle." },
        new() { Section = "SHOOTING", Title = "Fake shot", Goal = LessonGoal.Skill, Skill = SkillMove.FakeShot, Target = 1f,
            Pad = "Hold [X], then tap [A] before you let go", Keys = "Hold <Space> then tap <E>, or press <7>",
            Tip = "Shape to shoot, then drag the ball away instead. Sends defenders and keepers the wrong way." },
        new() { Section = "SKILL MOVES", Title = "Step-over", Goal = LessonGoal.Skill, Skill = SkillMove.StepOver, Target = 1f,
            Pad = "Flick [RS] left or right", Keys = "Press <1>",
            Tip = "A quick foot over the ball to wrong-foot a defender before you go past." },
        new() { Section = "SKILL MOVES", Title = "Drag-back", Goal = LessonGoal.Skill, Skill = SkillMove.HeelToHeel, Target = 1f,
            Pad = "Flick [RS] down (towards you)", Keys = "Press <2>",
            Tip = "Pull the ball back with your sole to escape a tackle and turn." },
        new() { Section = "SKILL MOVES", Title = "Ball roll", Goal = LessonGoal.Skill, Skill = SkillMove.BallRoll, Target = 1f,
            Pad = "Flick [RS] up (away from you)", Keys = "Press <3>",
            Tip = "Roll the ball across your body to move sideways without losing it." },
        new() { Section = "SKILL MOVES", Title = "Elastico", Goal = LessonGoal.Skill, Skill = SkillMove.Elastico, Target = 1f,
            Pad = "Hold [LT] + flick [RS] left or right", Keys = "Press <4>",
            Tip = "Outside of the foot one way, inside the other. Hard to pull off, but beats a defender who commits." },
        new() { Section = "SKILL MOVES", Title = "Roulette", Goal = LessonGoal.Skill, Skill = SkillMove.Roulette, Target = 1f,
            Pad = "Hold [LT] + flick [RS] down", Keys = "Press <5>",
            Tip = "A 360 spin over the ball that rolls you around a defender who is right on you." },
        new() { Section = "SKILL MOVES", Title = "Rainbow flick", Goal = LessonGoal.Skill, Skill = SkillMove.Rainbow, Target = 1f,
            Pad = "Hold [LT] + flick [RS] up", Keys = "Press <6>",
            Tip = "Flick the ball up and over your own head and the defender's. Risky but spectacular." },
        new() { Section = "DEFENDING", Title = "Switch player", Goal = LessonGoal.Switch, Target = 2f, Drill = TrainingDrill.Defend,
            Pad = "Press [LB]", Keys = "Press <Tab>",
            Tip = "Without the ball, LB changes you to the team-mate nearest the ball. Watch the yellow ring move." },
        new() { Section = "DEFENDING", Title = "Standing tackle", Goal = LessonGoal.TackleWin, Target = 2f, Drill = TrainingDrill.Defend,
            Pad = "Get close, then press [B]", Keys = "Get close, then press <F>",
            Tip = "Run at the attacker and tackle when you are right next to him. Tackle too early and he skips past." },
        new() { Section = "DEFENDING", Title = "Slide tackle", Goal = LessonGoal.Slide, Target = 1f, Drill = TrainingDrill.Defend,
            Pad = "Hold [RT] + press [B]", Keys = "Hold <Shift> + press <F>",
            Tip = "A committed slide with a long reach. Miss the ball in a real match and it is a foul." },
        new() { Section = "FREE PLAY", Title = "Free practice", Goal = LessonGoal.FreePlay, Target = 1f,
            Pad = "Try anything. Hold [LB]+[RB] to go to the next drill", Keys = "Try anything. <N> next / <B> back drill",
            Tip = "All lessons done! Practise freely. Use the pause menu ([MENU] / <Esc>) to quit." },
    };

    /// <summary>Jump to a lesson (wraps), resetting its progress and drill.</summary>
    public void GoTo(MatchEngine e, int index)
    {
        Index = ((index % Lessons.Count) + Lessons.Count) % Lessons.Count;
        Progress = 0f;
        _advanceTimer = -1f;
        LastFeedback = "";
        if (e.IsTraining)
        {
            if (Current.Drill != e.Drill) e.SetDrill(Current.Drill);
            else e.ResetDrill();
        }
        Snapshot(e);
    }

    public void Next(MatchEngine e) => GoTo(e, Index + 1);
    public void Previous(MatchEngine e) => GoTo(e, Index - 1);

    private void Snapshot(MatchEngine e)
    {
        var S = e.State;
        _passes = S.Passes[0]; _shots = S.Shots[0]; _goals = S.Score[0];
        _controlled = S.Controlled; _owner = S.Ball.Owner;
        _lastEvent = e.Events.Count > 0 ? e.Events[^1] : null;
    }

    /// <summary>Call once per frame after the engine stepped with <paramref name="cmd"/>.</summary>
    public void Update(MatchEngine e, PlayerCommand cmd, float dt)
    {
        if (!_started) { _started = true; GoTo(e, 0); return; }
        var S = e.State;
        CelebrateTimer = MathF.Max(0f, CelebrateTimer - dt);

        // Remember which pass/shot button was pressed recently, so a counter
        // that moves on the next fixed tick is credited to the right lesson.
        string pressed = cmd.Pass ? "pass" : cmd.Through ? "through" : cmd.Lob ? "lob" : "";
        if (pressed != "") { _recentButton = pressed; _recentButtonTimer = .6f; }
        else _recentButtonTimer = MathF.Max(0f, _recentButtonTimer - dt);
        if (cmd.Switch) _switchPressed = true;

        var lesson = Current;
        var me = S.Controlled >= 0 && S.Controlled < S.Players.Length ? S.Players[S.Controlled] : null;
        bool owner = me != null && S.Ball.Owner == me.Index;
        float moving = cmd.Move.Length();
        float gained = 0f;

        // New events since the last frame.
        var fresh = new List<MatchEvent>();
        for (int i = e.Events.Count - 1; i >= 0 && !ReferenceEquals(e.Events[i], _lastEvent); i--)
            fresh.Insert(0, e.Events[i]);

        switch (lesson.Goal)
        {
            case LessonGoal.MoveDistance:
                if (me != null && moving > .3f) gained = Mx.Flat(me.Vel).Length() * dt;
                break;
            case LessonGoal.SprintTime:
                if (me != null && cmd.Sprint && moving > .4f && Mx.Flat(me.Vel).Length() > 3f) gained = dt;
                break;
            case LessonGoal.CloseControlTime:
                if (owner && (cmd.Dribble || cmd.Shield) && moving > .2f) gained = dt;
                break;
            case LessonGoal.ShortPass:
            case LessonGoal.ThroughBall:
            case LessonGoal.LongBall:
                if (S.Passes[0] > _passes && _recentButtonTimer > 0f)
                {
                    string want = lesson.Goal == LessonGoal.ShortPass ? "pass"
                                : lesson.Goal == LessonGoal.ThroughBall ? "through" : "lob";
                    if (_recentButton == want) gained = S.Passes[0] - _passes;
                    else LastFeedback = "That was a different pass — try the button shown.";
                }
                break;
            case LessonGoal.TeammateRun:
                foreach (var ev in fresh) if (ev.Text.EndsWith("makes a run!")) gained += 1f;
                break;
            case LessonGoal.Shots:
                gained = S.Shots[0] - _shots;
                break;
            case LessonGoal.Goals:
                gained = S.Score[0] - _goals;
                break;
            case LessonGoal.Skill:
                string done = "pulls off a " + SkillMoves.DisplayName(lesson.Skill) + "!";
                foreach (var ev in fresh)
                {
                    if (ev.Text.EndsWith(done)) gained += 1f;
                    else if (ev.Text.Contains(" pulls off a ")) LastFeedback = "Nice move — but not this one. Check the input above.";
                }
                break;
            case LessonGoal.Switch:
                if (_switchPressed && S.Controlled != _controlled && S.Controlled >= 0) gained = 1f;
                break;
            case LessonGoal.TackleWin:
                if (_owner >= 0 && _owner < S.Players.Length && S.Players[_owner].Team == 1
                    && S.Ball.Owner >= 0 && S.Players[S.Ball.Owner].Team == 0)
                    gained = 1f;
                break;
            case LessonGoal.Slide:
                bool sliding = me != null && me.Action == "slide" && me.ActionTimer > 0f;
                if (sliding && !_wasSliding) gained = 1f;
                _wasSliding = sliding;
                break;
        }
        _switchPressed = false;
        Snapshot(e);

        if (lesson.Goal == LessonGoal.FreePlay) return;
        if (_advanceTimer >= 0f)
        {
            _advanceTimer -= dt;
            if (_advanceTimer < 0f) Next(e);
            return;
        }
        if (gained > 0f)
        {
            Progress = MathF.Min(lesson.Target, Progress + gained);
            if (lesson.Goal is not (LessonGoal.MoveDistance or LessonGoal.SprintTime or LessonGoal.CloseControlTime))
                LastFeedback = Progress >= lesson.Target ? "" : "Good! Again…";
            if (Progress >= lesson.Target)
            {
                LastFeedback = "Well done!";
                CelebrateTimer = 1.6f;
                _advanceTimer = 1.6f;
            }
        }
    }

    /// <summary>"2 / 3", "7 / 12 m" or "1.4 / 2.0 s".</summary>
    public string ProgressText()
    {
        var l = Current;
        return l.Goal switch
        {
            LessonGoal.FreePlay => "",
            LessonGoal.MoveDistance => $"{MathF.Floor(Progress)} / {l.Target:0} m",
            LessonGoal.SprintTime or LessonGoal.CloseControlTime => $"{Progress:0.0} / {l.Target:0.0} s",
            _ => $"{(int)Progress} / {(int)l.Target}",
        };
    }
}
