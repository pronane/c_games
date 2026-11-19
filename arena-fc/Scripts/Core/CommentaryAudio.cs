// Arena FC — commentary audio system (Phase 1: Commentary & Audio).
// Rich commentary with 30+ event types, context-aware lines (score, time,
// momentum), two-commentator style (main + co-commentator), and TTS hooks.
// Falls back to text feed when audio is unavailable.
using System;
using System.Collections.Generic;

namespace ArenaFC.Core;

/// <summary>Commentary event types (30+).</summary>
public enum CommentaryEvent
{
    Goal,
    Shot,
    Save,
    Miss,
    Post,
    Foul,
    FreeKick,
    Penalty,
    Corner,
    ThrowIn,
    GoalKick,
    Offside,
    Kickoff,
    HalfTime,
    FullTime,
    Highlight,
    Substitution,
    YellowCard,
    RedCard,
    Injury,
    Dribble,
    Tackle,
    Cross,
    ThroughBall,
    OneOnOne,
    CounterAttack,
    Comeback,
    LateGoal,
    Equalizer,
    LeadChange,
    VAR,
    Woodwork,
    GreatSave,
    TeamTalk,
    Atmosphere,
}

/// <summary>Match context for context-aware commentary.</summary>
public class CommentaryContext
{
    public string HomeTeam = "Home";
    public string AwayTeam = "Away";
    public int HomeScore;
    public int AwayScore;
    public int Minute;
    public bool IsSecondHalf;
    public float Momentum; // -1 (away) to +1 (home)
    public int ShotsHome;
    public int ShotsAway;
    public string LastScorer = "";
    public string LastScorerTeam = "";
}

/// <summary>
/// Commentary system with procedural audio hooks.
/// Generates commentary text with context awareness and two-commentator style.
/// </summary>
public class CommentaryAudio
{
    private readonly Random _rng = new(999);
    private readonly List<string> _recentLines = new();
    private bool _audioEnabled = true;
    private bool _useCoCommentator = true;
    private int _commentatorTurn; // 0 = main, 1 = co

    public bool AudioEnabled
    {
        get => _audioEnabled;
        set => _audioEnabled = value;
    }

    public bool UseCoCommentator
    {
        get => _useCoCommentator;
        set => _useCoCommentator = value;
    }

    /// <summary>Generate commentary for an event with context.</summary>
    public string Generate(CommentaryEvent evt, CommentaryContext ctx)
    {
        string line = evt switch
        {
            CommentaryEvent.Goal => GenerateGoal(ctx),
            CommentaryEvent.Shot => GenerateShot(ctx),
            CommentaryEvent.Save => Pick(
                "Brilliant save by the keeper!",
                "The keeper gets a strong hand to it!",
                "Denied! Great stop!",
                "What a reaction from the goalkeeper!"),
            CommentaryEvent.Miss => Pick(
                "Just wide of the post!",
                "Over the bar! The striker holds his head.",
                "So close! Inches away!",
                "Dragged wide, he'll want that back."),
            CommentaryEvent.Post => Pick(
                "Off the post! So unlucky!",
                "Clatters the woodwork! The crowd gasps!",
                "Hit the post! The keeper was beaten!"),
            CommentaryEvent.Foul => Pick(
                "That's a foul, free kick awarded.",
                "The referee blows for a foul.",
                "Play stopped for a foul.",
                "He's gone in a bit strong there. Free kick."),
            CommentaryEvent.FreeKick => Pick(
                "Free kick in a dangerous position.",
                "The wall is set. Free kick coming up.",
                "Free kick, just outside the box."),
            CommentaryEvent.Penalty => Pick(
                "PENALTY! The referee points to the spot!",
                "Penalty awarded! The crowd erupts!",
                "He's pointed to the spot! Penalty!"),
            CommentaryEvent.Corner => Pick(
                "Corner kick coming up.",
                "Another corner for the team.",
                "Corner awarded. The delivery coming in.",
                "Corner! The crowd senses a chance."),
            CommentaryEvent.ThrowIn => Pick(
                "Throw-in to restart play.",
                "Ball out for a throw-in."),
            CommentaryEvent.GoalKick => Pick(
                "Goal kick to the keeper.",
                "Goal kick, the keeper will take his time."),
            CommentaryEvent.Offside => Pick(
                "Flag up for offside!",
                "The assistant referee has his flag up.",
                "Offside called. The striker was a touch early.",
                "Offside! The linesman's flag is up."),
            CommentaryEvent.Kickoff => ctx.IsSecondHalf
                ? "And we're back underway for the second half!"
                : "And we're underway! The match is on!",
            CommentaryEvent.HalfTime => $"Half time here. {ctx.HomeTeam} {ctx.HomeScore} - {ctx.AwayScore} {ctx.AwayTeam}.",
            CommentaryEvent.FullTime => GenerateFullTime(ctx),
            CommentaryEvent.Highlight => Pick(
                "What a moment!",
                "The crowd are on their feet!",
                "Incredible scenes here!",
                "The fans are loving this!"),
            CommentaryEvent.Substitution => Pick(
                "Substitution coming up.",
                "Fresh legs on the pitch.",
                "The manager makes a change."),
            CommentaryEvent.YellowCard => Pick(
                "Yellow card shown by the referee.",
                "He's in the book for that challenge."),
            CommentaryEvent.RedCard => Pick(
                "RED CARD! He's been sent off!",
                "The referee reaches for red! That's a big moment!"),
            CommentaryEvent.Injury => Pick(
                "He's down and receiving treatment.",
                "Play stopped, looks like an injury."),
            CommentaryEvent.Dribble => Pick(
                "Beautiful skill! He's past his man!",
                "What a touch! The crowd applauds!",
                "He's gliding past players!"),
            CommentaryEvent.Tackle => Pick(
                "Crunching tackle! The crowd loves it!",
                "Won the ball cleanly!",
                "Great defensive work!"),
            CommentaryEvent.Cross => Pick(
                "Cross comes in... headed away!",
                "Whipped in from the flank!",
                "The cross is cleared!"),
            CommentaryEvent.ThroughBall => Pick(
                "Slipped through! He's in behind!",
                "Threaded through beautifully!"),
            CommentaryEvent.OneOnOne => Pick(
                "One on one with the keeper!",
                "He's through! Just the keeper to beat!"),
            CommentaryEvent.CounterAttack => Pick(
                "Counter attack! They're breaking at pace!",
                "They've won it back and they're flying forward!"),
            CommentaryEvent.Comeback => Pick(
                "What a comeback! The momentum has shifted!",
                "They're fighting back! This is incredible!"),
            CommentaryEvent.LateGoal => Pick(
                "LATE DRAMA! A goal in the closing minutes!",
                "Unbelievable! Scored at the death!"),
            CommentaryEvent.Equalizer => Pick(
                "EQUALIZER! They're level again!",
                "Back on level terms! Game on!"),
            CommentaryEvent.LeadChange => Pick(
                "They take the lead! The fans go wild!",
                "In front now! What a turnaround!"),
            CommentaryEvent.VAR => Pick(
                "VAR check in progress...",
                "The referee is checking the monitor."),
            CommentaryEvent.Woodwork => Pick(
                "Off the woodwork again!",
                "The post is rattled!"),
            CommentaryEvent.GreatSave => Pick(
                "WORLD CLASS SAVE! Unbelievable stop!",
                "He's flown to his right! Spectacular!"),
            CommentaryEvent.TeamTalk => Pick(
                "The manager is animated on the touchline.",
                "You can see the passion from the bench."),
            CommentaryEvent.Atmosphere => Pick(
                "The atmosphere is electric here!",
                "The fans are in full voice!",
                "What a noise from the home supporters!",
                "You can feel the passion in the stands!",
                "The away fans are making themselves heard!"),
            _ => "",
        };

        // Add co-commentator color occasionally
        if (_useCoCommentator && _rng.Next(3) == 0)
        {
            line += " " + Pick(
                "What a game we're having here.",
                "The fans are making some noise.",
                "You can feel the tension out there.",
                "This is turning into a classic.");
        }

        _recentLines.Add(line);
        if (_recentLines.Count > 20) _recentLines.RemoveAt(0);
        _commentatorTurn = 1 - _commentatorTurn;
        return line;
    }

    /// <summary>Legacy: Generate without context (uses defaults).</summary>
    public string Generate(CommentaryEvent evt, string teamName = "", string playerName = "")
    {
        var ctx = new CommentaryContext
        {
            HomeTeam = teamName != "" ? teamName : "Home",
            LastScorer = playerName,
            LastScorerTeam = teamName,
        };
        return Generate(evt, ctx);
    }

    private string GenerateGoal(CommentaryContext ctx)
    {
        string scorer = ctx.LastScorer != "" ? ctx.LastScorer : "The striker";
        string team = ctx.LastScorerTeam != "" ? ctx.LastScorerTeam : ctx.HomeTeam;
        int total = ctx.HomeScore + ctx.AwayScore;
        string scoreLine = $"{ctx.HomeTeam} {ctx.HomeScore} - {ctx.AwayScore} {ctx.AwayTeam}";

        if (total == 1)
            return Pick(
                $"GOAL! {scorer} scores for {team}! {scoreLine}!",
                $"It's in! {scorer} finds the net! {scoreLine}!",
                $"GOAL! {team} take the lead! {scoreLine}!");

        if (ctx.HomeScore == ctx.AwayScore)
            return Pick(
                $"GOAL! {scorer} equalizes! {scoreLine}! Game on!",
                $"It's level! {scorer} brings them back! {scoreLine}!");

        if (ctx.Minute > 80)
            return Pick(
                $"LATE GOAL! {scorer} scores in the dying minutes! {scoreLine}!",
                $"UNBELIEVABLE! {scorer} at the death! {scoreLine}!");

        return Pick(
            $"GOAL! {scorer} scores for {team}! {scoreLine}!",
            $"It's in! {scorer} finds the net! {scoreLine}!",
            $"GOAL! {team} extend their lead! {scoreLine}!");
    }

    private string GenerateShot(CommentaryContext ctx)
    {
        string scorer = ctx.LastScorer != "" ? ctx.LastScorer : "The striker";
        if (ctx.Momentum > 0.5)
            return Pick(
                $"{scorer} shoots... the keeper is equal to it!",
                $"What a strike from {scorer}! Saved!",
                $"{scorer} goes for it! The crowd holds its breath!");
        if (ctx.Momentum < -0.5)
            return Pick(
                $"{scorer} fires one in! Great stop!",
                $"Powerful effort from {scorer}! The keeper parries!",
                $"{scorer} lets fly! Denied by the keeper!");
        return Pick(
            $"{scorer} shoots... saved!",
            $"What a strike from {scorer}!",
            $"{scorer} goes for it!");
    }

    private string GenerateFullTime(CommentaryContext ctx)
    {
        string result = $"{ctx.HomeTeam} {ctx.HomeScore} - {ctx.AwayScore} {ctx.AwayTeam}";
        if (ctx.HomeScore == ctx.AwayScore)
            return $"Full time! {result}. Points shared in an entertaining match!";
        string winner = ctx.HomeScore > ctx.AwayScore ? ctx.HomeTeam : ctx.AwayTeam;
        return $"Full time! {result}. {winner} take all three points!";
    }

    /// <summary>Speak commentary via TTS (if enabled).</summary>
    public void Speak(string text)
    {
        if (!_audioEnabled) return;
        // Hook for TTS engine (e.g., Windows Speech, Web Speech API)
        // In Godot: use DisplayServer.tts_speak()
        // In browser: use speechSynthesis.speak()
    }

    private string Pick(params string[] options)
    {
        return options[_rng.Next(options.Length)];
    }

    public IReadOnlyList<string> RecentLines => _recentLines;
}
