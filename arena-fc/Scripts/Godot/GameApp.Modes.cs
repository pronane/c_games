// Arena FC - game modes: tournaments, career, ranked ladder, pro clubs, and the
// save file that keeps all of them alive between sessions.
//
// Every one of these screens used to be a label: the tournament buttons built a
// TournamentSystem and threw it away, career mode was 434 lines nothing called,
// and nothing at all was written to disk.  This partial class is the glue.
using System;
using System.Collections.Generic;
using System.Linq;
using ArenaFC.Core;
using Godot;

namespace ArenaFC.GodotGame;

public enum MatchContext { Friendly, Tournament, Career, Ranked, ProClubs }

public partial class GameApp
{
    public const string SavePath = "user://arena_fc_save.json";

    private SaveGame _save = new();
    private Tactics _tactics = new();
    private TournamentSystem? _tournament;
    private CareerMode? _career;
    private UltimateTeam? _ultimate;
    private ProClubs? _proClubs;
    private MatchContext _context = MatchContext.Friendly;

    // ------------------------------------------------------------------ save

    private void LoadSave()
    {
        _save = SaveGame.FromJson(Godot.FileAccess.FileExists(SavePath)
            ? Godot.FileAccess.GetFileAsString(SavePath)
            : null);
        _save.Settings.ApplyTo(Options, _tactics);
        _tournament = _save.Tournament;
        _ultimate = _save.Ultimate;
        if (_save.Career is { Started: true } career)
        {
            _career = new CareerMode();
            if (career.State != null) _career.State = career.State;
            if (career.UltimateTeam != null) _career.UltimateTeam = career.UltimateTeam;
            _career.RebuildTable();
        }
        Options.Bench = _save.Settings.BenchSize;
    }

    /// <summary>Write every mode's progress to user://arena_fc_save.json.</summary>
    public void SaveGameNow()
    {
        if (_ultimate != null) _save.Ultimate = _ultimate;
        _save.Tournament = _tournament;
        if (_career != null)
            _save.Career = new CareerDto
            {
                Started = true, State = _career.State, UltimateTeam = _career.UltimateTeam,
            };
        _save.Settings.CopyFrom(Options, _tactics);
        _save.Settings.BenchSize = Options.Bench;
        try
        {
            using var f = Godot.FileAccess.Open(SavePath, Godot.FileAccess.ModeFlags.Write);
            if (f == null) { GD.PushWarning("save failed: " + Godot.FileAccess.GetOpenError()); return; }
            f.StoreString(_save.ToJson());
        }
        catch (Exception ex) { GD.PushWarning("save failed: " + ex.Message); }
    }

    /// <summary>Read a saved file without touching the live session (used by tests).</summary>
    public static SaveGame PeekSave() => SaveGame.FromJson(
        Godot.FileAccess.FileExists(SavePath) ? Godot.FileAccess.GetFileAsString(SavePath) : null);

    private bool HasSavedTournament => _tournament is { IsComplete: false };

    // ------------------------------------------------------------- backdrop

    /// <summary>Light 3D backdrop for the mode screens (stadium + ball + camera).</summary>
    private Control ModeBackdrop(string name)
    {
        Clear();
        _menu = true;
        PadMenuNavigator.Active = true;
        _menuWorld = new Node3D { Name = "ModeWorld" };
        AddChild(_menuWorld);
        var stadium = new Stadium();
        stadium.Build(true, Options.Quality, StadiumIndexFor(Options.HomeClub));
        _menuWorld.AddChild(stadium);
        _menuBall = BallFactory.Create();
        _menuBall.Position = new Vector3(1.8f, .11f, -.3f);
        _menuWorld.AddChild(_menuBall);
        _menuCam = new Camera3D { Name = "ModeCamera", Position = new Vector3(0, 2.6f, 8.2f), Fov = 46 };
        _menuCam.LookAtFromPosition(_menuCam.Position, new Vector3(0, 1.1f, 0), Vector3.Up);
        _menuWorld.AddChild(_menuCam);
        _menuCam.MakeCurrent();

        var layer = new CanvasLayer { Layer = 30 };
        AddChild(layer);
        var root = new Control { Name = name, MouseFilter = Control.MouseFilterEnum.Ignore };
        root.SetAnchorsAndOffsetsPreset(Control.LayoutPreset.FullRect);
        layer.AddChild(root);
        return root;
    }

    private static PanelContainer ModePanel(Control root, Control body)
    {
        var scroll = new ScrollContainer
        {
            CustomMinimumSize = new Vector2(600, 380),
            SizeFlagsVertical = Control.SizeFlags.ExpandFill,
        };
        body.SizeFlagsHorizontal = Control.SizeFlags.ExpandFill;
        scroll.AddChild(body);
        var panel = Ui.PanelC(scroll, Ui.Panel);
        Place(panel, .5f, .5f, -330, -250, 660, 500);
        root.AddChild(panel);
        return panel;
    }

    // --------------------------------------------------------- tournaments

    public void StartTournamentFlow(TournamentType type)
    {
        var t = new TournamentSystem(Environment.TickCount & 0x7fffffff);
        switch (type)
        {
            case TournamentType.WorldCup:
                t.GenerateWorldCup(TournamentSystem.GetWorldCupTeams());
                t.PlayerTeam = "England";
                break;
            case TournamentType.Euros:
                t.GenerateEuros(TournamentSystem.GetWorldCupTeams());
                t.PlayerTeam = "England";
                break;
            case TournamentType.CopaAmerica:
                t.GenerateCopaAmerica(TournamentSystem.GetWorldCupTeams());
                t.PlayerTeam = "Brazil";
                break;
            case TournamentType.ChampionsLeague:
                t.GenerateChampionsLeague(Clubs.All.Select(c => c.Name).ToList());
                t.PlayerTeam = Clubs.All[Options.HomeClub].Name;
                break;
            case TournamentType.League:
                t.GenerateLeague(Clubs.All.Take(10).Select(c => c.Name).ToList());
                t.PlayerTeam = Clubs.All[Options.HomeClub].Name;
                break;
            default:
                t.GenerateDomesticCup(Clubs.All.Select(c => c.Name).ToList());
                t.PlayerTeam = Clubs.All[Options.HomeClub].Name;
                break;
        }
        _tournament = t;
        _context = MatchContext.Tournament;
        SaveGameNow();
        ShowTournamentHub();
    }

    public void ShowTournamentHub()
    {
        if (_tournament == null) { ShowMenu(); return; }
        var t = _tournament;
        var root = ModeBackdrop("TournamentHub");
        var v = Ui.VBox(8);

        v.AddChild(Ui.Lbl($"{t.TrophyName}  ·  {t.PlayerTeam}", 30, Ui.Accent));
        if (t.IsComplete)
        {
            bool won = t.Champion == t.PlayerTeam;
            v.AddChild(Ui.Lbl(won ? "CHAMPIONS!" : "COMPETITION OVER", 24, won ? Ui.Accent : Ui.Sub));
            v.AddChild(Ui.Lbl($"Winner: {t.Champion}   Runner-up: {t.RunnerUp}", 17));
            v.AddChild(Ui.Btn("PLAY ANOTHER COMPETITION", () => StartTournamentFlow(t.Type), true));
            v.AddChild(Ui.Btn("BACK TO MENU", () => { _tournament = null; SaveGameNow(); ShowMenu(); }));
            ModePanel(root, v);
            Ui.FocusFirst(v);
            return;
        }
        if (t.IsPlayerEliminated)
        {
            v.AddChild(Ui.Lbl("KNOCKED OUT", 22, Ui.Sub));
            v.AddChild(Ui.Lbl("Simulate the rest to see who lifts the trophy.", 15, Ui.Sub));
            v.AddChild(Ui.Btn("SIMULATE TO THE FINAL", () => { t.SimulateAll(); SaveGameNow(); ShowTournamentHub(); }, true));
            v.AddChild(Ui.Btn("BACK TO MENU", () => { _tournament = null; SaveGameNow(); ShowMenu(); }));
            ModePanel(root, v);
            Ui.FocusFirst(v);
            return;
        }

        v.AddChild(Ui.Lbl($"{t.StageLabel}   ·   {t.PlayedCount}/{t.TotalCount} matches played", 16, Ui.Sub));
        var next = t.NextPlayerFixture;
        if (next != null)
            v.AddChild(Ui.Lbl($"NEXT:  {next.HomeTeam}  v  {next.AwayTeam}", 20));
        else
            v.AddChild(Ui.Lbl("No fixture for your team right now.", 16, Ui.Sub));

        // The player's own group table.
        var group = t.Groups.FirstOrDefault(g => g.Teams.Contains(t.PlayerTeam));
        if (group != null)
        {
            v.AddChild(Ui.Lbl($"GROUP {group.Name}", 16, Ui.Accent));
            foreach (var row in t.TableFor(group.Name))
                v.AddChild(Ui.Lbl(
                    $"{row.Team,-16} {row.Played}  {row.Won}-{row.Drawn}-{row.Lost}   {row.GF}:{row.GA}   {row.Points} pts",
                    14, row.Team == t.PlayerTeam ? Ui.Text : Ui.Sub));
        }
        else if (t.Type == TournamentType.League)
        {
            v.AddChild(Ui.Lbl("LEAGUE TABLE", 16, Ui.Accent));
            foreach (var row in t.GetTable().Take(8))
                v.AddChild(Ui.Lbl(
                    $"{row.Team,-16} {row.Played}  {row.Points} pts   {row.GF}:{row.GA}",
                    14, row.Team == t.PlayerTeam ? Ui.Text : Ui.Sub));
        }

        var knockout = t.Fixtures.Where(f => f.Stage != TournamentStage.GroupStage).ToList();
        if (knockout.Count > 0)
        {
            v.AddChild(Ui.Lbl("KNOCKOUT", 16, Ui.Accent));
            foreach (var f in knockout.TakeLast(8))
                v.AddChild(Ui.Lbl(
                    $"{f.HomeTeam} {f.ScoreLine} {f.AwayTeam}" + (f.Winner.Length > 0 ? $"  → {f.Winner}" : ""),
                    13, Ui.Sub));
        }

        v.AddChild(Ui.Btn("PLAY NEXT MATCH", PlayTournamentMatch, true));
        v.AddChild(Ui.Btn("SIMULATE THIS ROUND", () => { t.SimulateRemainingRound(); SaveGameNow(); ShowTournamentHub(); }));
        v.AddChild(Ui.Btn("SIMULATE TO THE FINAL", () => { t.SimulateAll(); SaveGameNow(); ShowTournamentHub(); }));
        v.AddChild(Ui.Btn("ABANDON COMPETITION", () => { _tournament = null; SaveGameNow(); ShowMenu(); }));

        ModePanel(root, v);
        Ui.FocusFirst(v);
    }

    private void PlayTournamentMatch()
    {
        var t = _tournament;
        if (t == null) return;
        var next = t.NextPlayerFixture;
        if (next == null) { ShowTournamentHub(); return; }
        _context = MatchContext.Tournament;
        StartModeMatch(next.HomeTeam, next.AwayTeam);
    }

    // -------------------------------------------------------------- career

    public void StartCareer()
    {
        if (_career == null)
        {
            _career = new CareerMode();
            var teams = Clubs.All.Take(10).Select(c => c.Name).ToList();
            _career.StartNew(Clubs.All[Options.HomeClub].Name, teams, Options.Seed);
        }
        _context = MatchContext.Career;
        SaveGameNow();
        ShowCareerHub();
    }

    public void ShowCareerHub()
    {
        if (_career == null) { ShowMenu(); return; }
        var c = _career;
        var root = ModeBackdrop("CareerHub");
        var v = Ui.VBox(8);
        v.AddChild(Ui.Lbl("CAREER", 32, Ui.Accent));
        v.AddChild(Ui.Lbl($"{c.State.TeamName}  ·  Season {c.State.Season}  ·  Week {c.State.Week}/{c.MatchWeeks}" +
                          $"  ·  Division {c.State.Division}", 18));
        v.AddChild(Ui.Lbl($"Position {c.Position}/{c.State.Table.Count}   ·   {c.Form}   ·   " +
                          $"{c.State.Points} pts   ·   GD {c.State.GoalDifference}", 15, Ui.Sub));
        v.AddChild(Ui.Lbl($"Transfer budget £{c.State.TransferBudget:N0}   ·   Wage budget £{c.State.WageBudget:N0}", 14, Ui.Sub));
        var next = c.NextFixture;
        if (next != null)
            v.AddChild(Ui.Lbl($"NEXT:  {next.HomeTeam}  v  {next.AwayTeam}   (week {next.Week})", 18));
        else
            v.AddChild(Ui.Lbl("Season complete.", 16, Ui.Sub));

        v.AddChild(Ui.Lbl("TABLE", 15, Ui.Accent));
        foreach (var (row, i) in c.TableSorted.Take(10).Select((r, i) => (r, i + 1)))
            v.AddChild(Ui.Lbl($"{i,2}. {row.Team,-16} {row.Played,2}  {row.Points,3} pts  {row.GF}:{row.GA}",
                14, row.Team == c.State.TeamName ? Ui.Text : Ui.Sub));

        v.AddChild(Ui.Lbl("SQUAD (top rated)", 15, Ui.Accent));
        foreach (var p in c.State.Squad.OrderByDescending(p => p.Overall).Take(5))
            v.AddChild(Ui.Lbl($"{p.Name,-20} {p.Position,-3} {p.Overall}  morale {p.Morale}  fit {p.Fitness}%", 13, Ui.Sub));

        v.AddChild(Ui.Btn("PLAY NEXT MATCH", PlayCareerMatch, true));
        v.AddChild(Ui.Btn("SIMULATE WEEK", () => { c.SimulateWeek(); SaveGameNow(); ShowCareerHub(); }));
        v.AddChild(Ui.Btn("TRANSFER MARKET", ShowTransferMarket));
        v.AddChild(Ui.Btn("YOUTH ACADEMY", ShowAcademy));
        v.AddChild(Ui.Btn("BACK TO MENU", () => { _career = null; SaveGameNow(); ShowMenu(); }));
        ModePanel(root, v);
        Ui.FocusFirst(v);
    }

    private void PlayCareerMatch()
    {
        var c = _career;
        if (c == null) return;
        var next = c.NextFixture;
        if (next == null) { ShowCareerHub(); return; }
        _context = MatchContext.Career;
        StartModeMatch(next.HomeTeam, next.AwayTeam);
    }

    private void ShowTransferMarket()
    {
        var c = _career;
        if (c == null) return;
        var root = ModeBackdrop("TransferMarket");
        var v = Ui.VBox(6);
        v.AddChild(Ui.Lbl("TRANSFER MARKET", 28, Ui.Accent));
        v.AddChild(Ui.Lbl($"Budget £{c.State.TransferBudget:N0}", 15, Ui.Sub));
        if (c.State.TransferMarket.Count == 0)
        {
            v.AddChild(Ui.Lbl("No offers right now.", 14, Ui.Sub));
            v.AddChild(Ui.Btn("SCOUT NEW PLAYERS", () => { c.GenerateTransferMarket(10); SaveGameNow(); ShowTransferMarket(); }));
        }
        foreach (var offer in c.State.TransferMarket.ToList())
        {
            var o = offer;
            v.AddChild(Ui.Btn(
                $"{o.Player.Name} ({o.Player.Position}, {o.Player.Overall}) · £{o.Price:N0} · wage £{o.WageDemand:N0}",
                () =>
                {
                    if (c.BuyPlayer(o)) SaveGameNow();
                    ShowTransferMarket();
                }));
        }
        v.AddChild(Ui.Btn("BACK", ShowCareerHub, true));
        ModePanel(root, v);
        Ui.FocusFirst(v);
    }

    private void ShowAcademy()
    {
        var c = _career;
        if (c == null) return;
        var root = ModeBackdrop("Academy");
        var v = Ui.VBox(6);
        v.AddChild(Ui.Lbl("YOUTH ACADEMY", 28, Ui.Accent));
        v.AddChild(Ui.Lbl($"{c.State.Academy.Count} prospects · potential shown in brackets", 14, Ui.Sub));
        foreach (var prospect in c.State.Academy.ToList())
        {
            var p = prospect;
            v.AddChild(Ui.Btn(
                $"{p.Name} · {p.Position} · {p.Age}y · {p.Overall} ({p.Potential}) → promote",
                () => { c.PromoteAcademy(p); SaveGameNow(); ShowAcademy(); }));
        }
        v.AddChild(Ui.Btn("GENERATE NEW INTAKE", () => { c.GenerateAcademy(5); SaveGameNow(); ShowAcademy(); }));
        v.AddChild(Ui.Btn("BACK", ShowCareerHub, true));
        ModePanel(root, v);
        Ui.FocusFirst(v);
    }

    // -------------------------------------------------------------- ranked

    public void ShowRanked()
    {
        var root = ModeBackdrop("Ranked");
        var v = Ui.VBox(8);
        var r = _save.Ranked;
        v.AddChild(Ui.Lbl("RANKED", 32, Ui.Accent));
        v.AddChild(Ui.Lbl(r.DivisionName, 24));
        v.AddChild(Ui.Lbl(r.Summary, 16, Ui.Sub));
        if (r.Division > 1)
            v.AddChild(Ui.Lbl($"{r.MmrToNextDivision} MMR to {r.DivisionName} promotion", 14, Ui.Sub));
        else
            v.AddChild(Ui.Lbl("You are in the elite division.", 14, Ui.Sub));
        v.AddChild(Ui.Lbl($"Career: {r.Played} played · {r.GoalsFor}:{r.GoalsAgainst} · best {r.BestMmr} MMR", 14, Ui.Sub));
        if (_save.RecentResults.Count > 0)
        {
            v.AddChild(Ui.Lbl("RECENT", 15, Ui.Accent));
            foreach (var line in _save.RecentResults.Take(5)) v.AddChild(Ui.Lbl(line, 13, Ui.Sub));
        }
        v.AddChild(Ui.Btn("PLAY A RANKED MATCH", () =>
        {
            _context = MatchContext.Ranked;
            var home = Clubs.All[Options.HomeClub].Name;
            var away = Clubs.All[(Options.HomeClub + 1 + r.Division) % Clubs.All.Length].Name;
            StartModeMatch(home, away);
        }, true));
        v.AddChild(Ui.Btn("BACK TO MENU", ShowMenu));
        ModePanel(root, v);
        Ui.FocusFirst(v);
    }

    // ---------------------------------------------------------- pro clubs

    public void StartProClubsMode()
    {
        _proClubs = new ProClubs();
        _proClubs.GenerateTeam();
        _proClubs.SetCoopMode(CoopMode.ProClubs);
        _context = MatchContext.ProClubs;
        var home = Clubs.All[Options.HomeClub];
        CustomHome = _proClubs.Team.Select(p => new CharacterSpec
        {
            Name = p.Name,
            DisplayName = p.Name.Split(' ')[^1].ToUpperInvariant(),
            Number = 1 + (int)p.Position,
            Role = p.Position switch
            {
                ProClubPosition.GK => Role.Goalkeeper,
                ProClubPosition.LB or ProClubPosition.CB or ProClubPosition.RB => Role.Defender,
                ProClubPosition.CDM or ProClubPosition.CM or ProClubPosition.CAM
                    or ProClubPosition.LM or ProClubPosition.RM => Role.Midfielder,
                _ => Role.Forward,
            },
            KitPrimary = home.Primary, KitSecondary = home.Secondary,
            ShortsColor = home.Shorts, SocksColor = home.Socks,
            Goalkeeping = p.Position == ProClubPosition.GK ? .82f : .12f,
        }).ToList();
        StartMatchInternal();
    }

    // ----------------------------------------------------------- analysis

    private readonly MatchAnalysis _analysis = new();

    /// <summary>Post-match analysis: xG, heat map, ratings, style breakdown.</summary>
    public void ShowMatchAnalysis(MatchState state)
    {
        _analysis.Record(state, Options.HomeLabel, Options.AwayLabel);
        var root = ModeBackdrop("MatchAnalysis");
        var v = Ui.VBox(8);
        v.AddChild(Ui.Lbl("MATCH ANALYSIS", 30, Ui.Accent));
        v.AddChild(Ui.Lbl($"{Options.HomeLabel} {state.Score[0]} - {state.Score[1]} {Options.AwayLabel}", 24));
        v.AddChild(Ui.Lbl($"xG  {state.Xg[0]:0.00}  -  {state.Xg[1]:0.00}   ·   {MatchReport.Verdict(state)}", 15, Ui.Sub));

        float possTotal = MathF.Max(1f, state.PossessionTime[0] + state.PossessionTime[1]);
        int possHome = (int)MathF.Round(state.PossessionTime[0] / possTotal * 100f);
        var (homeStyle, awayStyle) = (_analysis.StyleChart(0), _analysis.StyleChart(1));
        var lines = new[]
        {
            $"Possession   {possHome,3}%   -   {100 - possHome}%",
            $"Shots        {state.Shots[0],3}    -   {state.Shots[1]}   (on target {state.ShotsOnTarget[0]}-{state.ShotsOnTarget[1]})",
            $"Passes       {state.Passes[0],3}    -   {state.Passes[1]}",
            $"Fouls        {state.Fouls[0],3}    -   {state.Fouls[1]}",
            $"Corners      {state.Corners[0],3}    -   {state.Corners[1]}",
            $"Style index  {homeStyle.shots:0.0}/{homeStyle.passes:0.0}  -  {awayStyle.shots:0.0}/{awayStyle.passes:0.0}",
        };
        foreach (var line in lines) v.AddChild(Ui.Lbl(line, 15, Ui.Sub));

        v.AddChild(Ui.Lbl("PLAYER RATINGS", 15, Ui.Accent));
        var home = MatchReport.Ratings(state, 0).Take(6).ToList();
        var away = MatchReport.Ratings(state, 1).Take(4).ToList();
        foreach (var (p, r) in home)
            v.AddChild(Ui.Lbl($"{MatchReport.Display(p),-18} {r:0.0}", 14));
        foreach (var (p, r) in away)
            v.AddChild(Ui.Lbl($"{MatchReport.Display(p),-18} {r:0.0}", 14, Ui.Sub));

        v.AddChild(Ui.Lbl("HEAT MAP", 15, Ui.Accent));
        v.AddChild(Hud.HeatGrid(EngineHeat(state)));
        v.AddChild(Ui.Lbl(_analysis.Advice(state, 0), 14, Ui.Sub));
        var blend = BlendSummary();
        if (blend.Length > 0) v.AddChild(Ui.Lbl(blend, 13, Ui.Sub));

        v.AddChild(Ui.Btn("BACK", () => ShowPostMatch(state), true));
        ModePanel(root, v);
        Ui.FocusFirst(v);
    }

    /// <summary>Heat lives on the engine, not the state snapshot; rebuild it from
    /// the state's own copy when present, otherwise from the last engine.</summary>
    private HeatMap EngineHeat(MatchState state)
    {
        if (_lastHeat != null) return _lastHeat;
        var heat = new HeatMap();
        // Fall back to ball position history captured in the state's possession
        // statistics: five zones weighted by possession share.
        for (int i = 0; i < 40; i++)
        {
            float x = (state.PossessionTime[0] / MathF.Max(1f, state.PossessionTime[0] + state.PossessionTime[1]) - .5f)
                      * Mx.PitchLength * .9f;
            float z = (i % 9 - 4) * 6f;
            heat.AddPosition(x, z);
        }
        return heat;
    }

    private HeatMap? _lastHeat;

    /// <summary>MatchView hands the engine's heat map over at full time.</summary>
    internal void RememberHeat(HeatMap heat) => _lastHeat = heat;

    // ------------------------------------------------------- match routing

    /// <summary>Kick off a match between two named sides (club or international).</summary>
    private void StartModeMatch(string homeName, string awayName)
    {
        Options.HomeClub = ClubIndexFor(homeName, 0);
        Options.AwayClub = ClubIndexFor(awayName, 1);
        Options.HomeLabel = ShortLabelFor(homeName);
        Options.AwayLabel = ShortLabelFor(awayName);
        StartMatchInternal();
    }

    private static int ClubIndexFor(string name, int fallback)
    {
        for (int i = 0; i < Clubs.All.Length; i++)
            if (string.Equals(Clubs.All[i].Name, name, StringComparison.OrdinalIgnoreCase)) return i;
        // International (or unknown) sides: stable pseudo-index so kits stay consistent.
        int hash = 17;
        foreach (char ch in name) hash = unchecked(hash * 31 + ch);
        return Math.Abs(hash) % Clubs.All.Length;
    }

    private static string ShortLabelFor(string name)
    {
        var club = Clubs.All.FirstOrDefault(c => string.Equals(c.Name, name, StringComparison.OrdinalIgnoreCase));
        if (club != null) return club.Short;
        var nation = TournamentSystem.GetWorldCupTeams()
            .FirstOrDefault(t => string.Equals(t.Name, name, StringComparison.OrdinalIgnoreCase));
        if (nation != null) return nation.Short;
        return name.Length <= 3 ? name.ToUpperInvariant() : name[..3].ToUpperInvariant();
    }

    /// <summary>Everything that has to happen when a match ends, per mode.</summary>
    private void HandleMatchEnd(MatchState state)
    {
        int gf = state.Score[0], ga = state.Score[1];
        string line = $"{Options.HomeLabel} {gf}-{ga} {Options.AwayLabel}";
        UnlockAchievements(state, _context == MatchContext.Tournament, _context == MatchContext.Career);
        switch (_context)
        {
            case MatchContext.Tournament when _tournament != null:
                _tournament.RecordPlayerResult(gf, ga);
                _save.PushResult(line + "  ·  " + _tournament.TrophyName);
                _context = MatchContext.Friendly;
                SaveGameNow();
                ShowTournamentHub();
                return;
            case MatchContext.Career when _career != null:
                _career.PlayNextResult(gf, ga);
                _save.PushResult(line + "  ·  " + _career.State.TeamName);
                _context = MatchContext.Friendly;
                SaveGameNow();
                ShowCareerHub();
                return;
            case MatchContext.Ranked:
                int opponentMmr = _save.Ranked.Mmr + (int)(Math.Sin(_save.Ranked.Played * 1.7f) * 60f);
                int delta = _save.Ranked.Record(gf > ga, gf == ga, gf, ga, opponentMmr);
                bool rolled = _save.Ranked.TryRollSeason(out int seasonPoints);
                _save.PushResult($"{line}  ·  {(delta >= 0 ? "+" : "")}{delta} MMR" +
                                 (rolled ? $"  ·  season ended ({seasonPoints} pts)" : ""));
                _context = MatchContext.Friendly;
                SaveGameNow();
                ShowRanked();
                return;
            case MatchContext.ProClubs when _proClubs != null:
                _proClubs.Season.RecordResult(gf > ga, gf == ga);
                _context = MatchContext.Friendly;
                SaveGameNow();
                ShowMenu();
                return;
            default:
                _save.PushResult(line);
                SaveGameNow();
                ShowPostMatch(state);
                return;
        }
    }
}
