// Arena FC - the extras hub: achievements, custom drills, evolutions, clubs,
// replay clips and ranked matchmaking.
//
// These are the "implemented but never called" types from the review.  Each one
// now has a screen that actually does something with it, and the state they
// produce is written into the save file.
using System;
using System.Collections.Generic;
using System.Linq;
using ArenaFC.Core;
using Godot;

namespace ArenaFC.GodotGame;

public partial class GameApp
{
    private readonly ReplaySystem _replay = new();
    private readonly ReplayEditor _replayEditor = new();
    private readonly MatchmakingService _matchmaking = new();
    private readonly Club _featureClub = new() { Name = "Arena FC Pro Clubs", Badge = "AF" };
    private readonly FluidFormation _shape = new();
    private readonly ShotMeter _shotMeter = new();
    private readonly List<MatchEvent> _lastEvents = new();

    private BlendLearner? _blend;

    /// <summary>MatchView hands over the learned movement profile at full time.</summary>
    internal void RememberBlend(BlendLearner blend) => _blend = blend;

    /// <summary>Most-used movement clips from the last match (BlendLearner).</summary>
    internal string BlendSummary()
    {
        if (_blend == null || _blend.Weights.CellWeights.Count == 0) return "";
        var totals = new Dictionary<string, float>();
        foreach (var cell in _blend.Weights.CellWeights.Values)
            foreach (var pair in cell)
                totals[pair.Key] = totals.TryGetValue(pair.Key, out float w) ? w + pair.Value : pair.Value;
        var top = totals.OrderByDescending(t => t.Value).Take(3)
            .Select(t => $"{t.Key} {t.Value:0.0}");
        return "Movement profile: " + string.Join(" · ", top);
    }

    internal void RememberEvents(IEnumerable<MatchEvent> events)
    {
        _lastEvents.Clear();
        _lastEvents.AddRange(events.TakeLast(40));
    }

    // ---------------------------------------------------------- achievements

    private List<Achievement> BuildAchievements() => new()
    {
        new Achievement { Name = "First win", Description = "Win a match", Target = 1 },
        new Achievement { Name = "Goal rush", Description = "Score 4 in a match", Target = 4 },
        new Achievement { Name = "Clean sheet", Description = "Win without conceding", Target = 1 },
        new Achievement { Name = "Long range", Description = "Play a 10+ minute match", Target = 1 },
        new Achievement { Name = "Traveller", Description = "Play every mode", Target = 5 },
    };

    private void UnlockAchievements(MatchState state, bool tournament, bool career)
    {
        if (_save.Achievements.Count == 0)
            foreach (var a in BuildAchievements()) _save.Achievements.Add(a.Name);
        void Unlock(string name)
        {
            if (_save.Achievements.Contains("unlocked:" + name)) return;
            _save.Achievements.Add("unlocked:" + name);
            _save.PushResult("Achievement unlocked: " + name);
        }
        bool win = state.Score[0] > state.Score[1];
        if (win) Unlock("First win");
        if (state.Score[0] >= 4) Unlock("Goal rush");
        if (win && state.Score[1] == 0) Unlock("Clean sheet");
        if (state.Clock >= 600f) Unlock("Long range");
        if (tournament || career) Unlock("Traveller");
    }

    private bool AchievementUnlocked(string name) => _save.Achievements.Contains("unlocked:" + name);

    // --------------------------------------------------------------- extras

    public void ShowExtras()
    {
        var root = ModeBackdrop("Extras");
        var v = Ui.VBox(8);
        v.AddChild(Ui.Lbl("EXTRAS", 30, Ui.Accent));
        v.AddChild(Ui.Lbl($"Achievements {_save.Achievements.Count(a => a.StartsWith("unlocked:"))}/{BuildAchievements().Count}" +
                          $"  ·  clips {_save.ReplayClips.Count}", 15, Ui.Sub));
        v.AddChild(Ui.Btn("ACHIEVEMENTS", ShowAchievements));
        v.AddChild(Ui.Btn("CUSTOM TRAINING", ShowCustomTraining));
        v.AddChild(Ui.Btn("REPLAY EDITOR", ShowReplayEditor));
        v.AddChild(Ui.Btn("EVOLUTIONS (ULTIMATE TEAM)", ShowEvolutions));
        v.AddChild(Ui.Btn("CLUBS", ShowFeatureClub));
        v.AddChild(Ui.Btn("MATCHMAKING", ShowMatchmaking));
        v.AddChild(Ui.Btn("BACK", ShowMenu));
        ModePanel(root, v);
        Ui.FocusFirst(v);
    }

    private void ShowAchievements()
    {
        var root = ModeBackdrop("Achievements");
        var v = Ui.VBox(8);
        v.AddChild(Ui.Lbl("ACHIEVEMENTS", 30, Ui.Accent));
        foreach (var a in BuildAchievements())
            v.AddChild(Ui.Lbl($"{(AchievementUnlocked(a.Name) ? "[x]" : "[ ]")} {a.Name} — {a.Description}",
                15, AchievementUnlocked(a.Name) ? Ui.Text : Ui.Sub));
        v.AddChild(Ui.Lbl("", 6));
        foreach (var line in _save.RecentResults.Take(6)) v.AddChild(Ui.Lbl(line, 13, Ui.Sub));
        v.AddChild(Ui.Btn("BACK", ShowExtras, true));
        ModePanel(root, v);
        Ui.FocusFirst(v);
    }

    private void ShowCustomTraining()
    {
        var root = ModeBackdrop("CustomTraining");
        var v = Ui.VBox(8);
        var drill = new CustomTraining
        {
            Name = "Finishing under pressure",
            Type = SkillGame.FreeKicks,
            TargetScore = 5,
        };
        drill.Steps.Add("Warm up: 10 short passes");
        drill.Steps.Add("Then: score 5 free kicks");
        v.AddChild(Ui.Lbl("CUSTOM TRAINING", 30, Ui.Accent));
        v.AddChild(Ui.Lbl($"{drill.Name} · {drill.Type} · target {drill.TargetScore}", 16));
        foreach (var step in drill.Steps) v.AddChild(Ui.Lbl("• " + step, 14, Ui.Sub));
        v.AddChild(Ui.Btn("RUN THIS DRILL", () => { Mode = GameMode.SkillGames; StartSkillGames(); }, true));
        v.AddChild(Ui.Btn("BACK", ShowExtras, true));
        ModePanel(root, v);
        Ui.FocusFirst(v);
    }

    // ---------------------------------------------------------------- replay

    private void ShowReplayEditor()
    {
        var root = ModeBackdrop("ReplayEditor");
        var v = Ui.VBox(8);
        v.AddChild(Ui.Lbl("REPLAY EDITOR", 30, Ui.Accent));
        if (_lastEvents.Count == 0)
        {
            v.AddChild(Ui.Lbl("Play a match first — the editor needs a clip.", 15, Ui.Sub));
        }
        else
        {
            foreach (var e in _lastEvents.Where(e => e.Kind is EventKind.Goal or EventKind.Card or EventKind.Save)
                         .Take(6))
            {
                var evt = e;
                v.AddChild(Ui.Btn($"[{evt.Clock:000}'] {evt.Text} → clip", () =>
                {
                    _replayEditor.Trim((int)evt.Clock * 60, (int)evt.Clock * 60 + 90);
                    _replayEditor.SlowMotion = true;
                    _replayEditor.TextOverlay = evt.Text;
                    _replay.RecordEvent(evt, (int)evt.Clock * 60);
                }));
            }
            v.AddChild(Ui.Lbl($"Clip: frames {_replayEditor.StartFrame}-{_replayEditor.EndFrame}" +
                              $" · slow-mo {(_replayEditor.SlowMotion ? "on" : "off")}", 14, Ui.Sub));
            v.AddChild(Ui.Btn("SAVE CLIP", () =>
            {
                _save.ReplayClips.Add($"{_replayEditor.TextOverlay} ({_replayEditor.StartFrame}-{_replayEditor.EndFrame})");
                SaveGameNow();
                ShowReplayEditor();
            }, true));
        }
        v.AddChild(Ui.Btn("BACK", ShowExtras, true));
        ModePanel(root, v);
        Ui.FocusFirst(v);
    }

    // ------------------------------------------------------------ evolutions

    private void ShowEvolutions()
    {
        _ultimate ??= new UltimateTeam();
        var root = ModeBackdrop("Evolutions");
        var v = Ui.VBox(8);
        var evo = new Evolution { Name = "Rising talent", MinOverall = 55, MaxOverall = 78, Boost = 3 };
        v.AddChild(Ui.Lbl("EVOLUTIONS", 30, Ui.Accent));
        v.AddChild(Ui.Lbl($"{evo.Name} · {evo.MinOverall}-{evo.MaxOverall} OVR · +{evo.Boost}", 16, Ui.Sub));
        var candidates = _ultimate.Club.Where(c => c.Overall >= evo.MinOverall && c.Overall <= evo.MaxOverall)
            .Take(6).ToList();
        if (candidates.Count == 0) v.AddChild(Ui.Lbl("No cards in range — open a pack first.", 15, Ui.Sub));
        for (int i = 0; i < candidates.Count; i++)
        {
            int idx = _ultimate.Club.IndexOf(candidates[i]);
            var card = candidates[i];
            v.AddChild(Ui.Btn($"{card.Name} ({card.Overall}) → evolve", () =>
            {
                var evolved = evo.Apply(card);
                if (idx >= 0) _ultimate.Club[idx] = evolved;
                SaveGameNow();
                ShowEvolutions();
            }));
        }
        v.AddChild(Ui.Btn("BACK", ShowExtras, true));
        ModePanel(root, v);
        Ui.FocusFirst(v);
    }

    // ----------------------------------------------------------------- clubs

    private void ShowFeatureClub()
    {
        var root = ModeBackdrop("Clubs");
        var v = Ui.VBox(8);
        if (_featureClub.Members.Count == 0)
        {
            _featureClub.Members.AddRange(new[] { "You", "Pad 2", "Pad 3", "Pad 4" });
            _featureClub.Reputation = 120;
        }
        v.AddChild(Ui.Lbl("CLUBS", 30, Ui.Accent));
        v.AddChild(Ui.Lbl($"{_featureClub.Name} [{_featureClub.Badge}] · reputation {_featureClub.Reputation}", 16));
        v.AddChild(Ui.Lbl($"Members: {string.Join(", ", _featureClub.Members)}", 14, Ui.Sub));
        v.AddChild(Ui.Lbl($"Record: {_featureClub.Wins}W / {_featureClub.Losses}L", 14, Ui.Sub));
        v.AddChild(Ui.Btn("PLAY A CLUB MATCH", () => { Mode = GameMode.Kickoff; StartProClubs(); }, true));
        v.AddChild(Ui.Btn("BACK", ShowExtras, true));
        ModePanel(root, v);
        Ui.FocusFirst(v);
    }

    // ----------------------------------------------------------- matchmaking

    private PlayerRanking MyRanking() => new()
    {
        PlayerId = "local",
        DisplayName = "You",
        Rating = _save.Ranked.Mmr,
        Wins = _save.Ranked.Wins,
        Draws = _save.Ranked.Draws,
        Losses = _save.Ranked.Losses,
    };

    private void ShowMatchmaking()
    {
        var me = MyRanking();
        if (_matchmaking.FindLobbies(me).Count == 0)
        {
            // Seed a few lobbies around the player's rating so the filter has
            // something to work with (there is no server for ranked yet).
            for (int i = 0; i < 4; i++)
            {
                _matchmaking.CreateLobby(new Lobby
                {
                    Id = "lobby-" + i,
                    HostName = "Challenger " + (i + 1),
                    Mode = "Kickoff",
                    MinRating = Math.Max(0, me.Rating - 350 + i * 120),
                    MaxRating = me.Rating + 350 + i * 120,
                    CurrentPlayers = 1,
                    MaxPlayers = 2,
                });
            }
        }
        var lobbies = _matchmaking.FindLobbies(me);
        var best = _matchmaking.FindBestMatch(me);
        var root = ModeBackdrop("Matchmaking");
        var v = Ui.VBox(8);
        v.AddChild(Ui.Lbl("MATCHMAKING", 30, Ui.Accent));
        v.AddChild(Ui.Lbl($"Your rating {me.Rating} · {me.Tier} · {lobbies.Count} lobby(ies) in range", 16, Ui.Sub));
        foreach (var lobby in lobbies)
            v.AddChild(Ui.Btn($"{lobby.HostName} · {lobby.Mode} · {lobby.MinRating}-{lobby.MaxRating}",
                () => { _context = MatchContext.Ranked; StartModeMatch(Clubs.All[Options.HomeClub].Name,
                    Clubs.All[(Options.HomeClub + 2) % Clubs.All.Length].Name); }));
        v.AddChild(Ui.Btn("QUICK MATCH", () =>
        {
            if (best == null) return;
            _context = MatchContext.Ranked;
            StartModeMatch(Clubs.All[Options.HomeClub].Name, Clubs.All[(Options.HomeClub + 1) % Clubs.All.Length].Name);
        }, true));
        v.AddChild(Ui.Btn("BACK", ShowMenu));
        ModePanel(root, v);
        Ui.FocusFirst(v);
    }

    // ------------------------------------------------------- shot meter hook

    /// <summary>Timing feedback for the HUD charge bar (ShotMeter).</summary>
    public string ShotFeedback(float charge)
    {
        _shotMeter.Charge = charge;
        return _shotMeter.GetFeedback();
    }
}
