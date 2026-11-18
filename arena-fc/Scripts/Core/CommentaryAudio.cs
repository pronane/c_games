// Arena FC — commentary audio system (P1 presentation).
// Procedural commentary with text-to-speech hooks.
// Falls back to text feed when audio is unavailable.
using System;
using System.Collections.Generic;

namespace ArenaFC.Core;

/// <summary>Commentary event types.</summary>
public enum CommentaryEvent
{
    Goal,
    Shot,
    Save,
    Foul,
    Corner,
    Offside,
    Kickoff,
    HalfTime,
    FullTime,
    Highlight,
    Substitution,
}

/// <summary>
/// Commentary system with procedural audio hooks.
/// Generates commentary text and optionally speaks it via TTS.
/// </summary>
public class CommentaryAudio
{
    private readonly Random _rng = new(999);
    private readonly List<string> _recentLines = new();
    private bool _audioEnabled = true;

    public bool AudioEnabled
    {
        get => _audioEnabled;
        set => _audioEnabled = value;
    }

    /// <summary>Generate commentary for an event.</summary>
    public string Generate(CommentaryEvent evt, string teamName = "", string playerName = "")
    {
        string line = evt switch
        {
            CommentaryEvent.Goal => Pick(
                $"GOAL! {playerName} scores for {teamName}!",
                $"It's in! {playerName} finds the net!",
                $"GOAL! {teamName} take the lead!"),
            CommentaryEvent.Shot => Pick(
                $"{playerName} shoots... saved!",
                $"What a strike from {playerName}!",
                $"{playerName} goes for it!"),
            CommentaryEvent.Save => Pick(
                "Brilliant save by the keeper!",
                "The keeper gets a strong hand to it!",
                "Denied! Great stop!"),
            CommentaryEvent.Foul => Pick(
                "That's a foul, free kick awarded.",
                "The referee blows for a foul.",
                "Play stopped for a foul."),
            CommentaryEvent.Corner => Pick(
                "Corner kick coming up.",
                "Another corner for the team.",
                "Corner awarded."),
            CommentaryEvent.Offside => Pick(
                "Flag up for offside!",
                "The assistant referee has his flag up.",
                "Offside called."),
            CommentaryEvent.Kickoff => "And we're underway!",
            CommentaryEvent.HalfTime => "Half time here.",
            CommentaryEvent.FullTime => "Full time! What a match!",
            CommentaryEvent.Highlight => Pick(
                "What a moment!",
                "The crowd are on their feet!",
                "Incredible scenes here!"),
            CommentaryEvent.Substitution => "Substitution coming up.",
            _ => "",
        };

        _recentLines.Add(line);
        if (_recentLines.Count > 10) _recentLines.RemoveAt(0);
        return line;
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
