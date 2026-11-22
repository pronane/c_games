// Arena FC - the touchline (presentation only): substitutes on the dugout benches, each manager and an
// assistant in the technical areas, ball kids behind the boards and photographers kneeling along the goal
// lines.  Places come from Sprite Forge (sforge.pitchside.placements on the ground's json, written by
// Tools/add_pitchside.py); bodies are the same squad GLB with the role's clothes (tailor keeper / staff
// garments), clips are the sforge.pitchside loops.  Nothing here reads or writes the simulation beyond the
// score events MatchView passes in.
using System;
using System.Collections.Generic;
using System.Text.Json;
using ArenaFC.Core;
using Godot;

namespace ArenaFC.GodotGame;

public sealed partial class PitchsideView : Node3D
{
    private sealed class Person
    {
        public CharacterRig Rig = null!;
        public string Role = "", Clip = "";
        public int Team = -1;
        public bool Seated;
        public float SeatTop, Settle = -1f, OneShot;
        public Vector3 Seat;
    }

    private readonly List<Person> _people = new();
    private static readonly string[] Bibs = { "#d9f99d", "#fb923c", "#f472b6", "#fde047", "#67e8f9" };
    public const string PropsPath = "res://Data/models/pitchside_props.glb";

    public static string SpotsPath(string preset) => $"res://Data/stadiums/stadium_{preset}.pitchside.json";

    /// <summary>How many of each role the tier can carry (every figure is a skinned squad player at its far LOD).</summary>
    private static (int subs, int kids, int photographers, bool assistants) Budget() => RenderProfile.Tier switch
    {
        RenderTier.Ultra => (7, 6, 8, true),
        RenderTier.High => (5, 4, 6, true),
        _ => (3, 2, 4, false),
    };

    public void Init(MatchEngine engine, MatchOptions opts, string preset)
    {
        Name = "Pitchside";
        string path = SpotsPath(preset);
        if (!Godot.FileAccess.FileExists(path) || !SoccerClipRig.Available) return;
        using var doc = JsonDocument.Parse(Godot.FileAccess.GetFileAsString(path));
        var (maxSubs, maxKids, maxPhoto, assistants) = Budget();
        // the two teams' colours today (after the clash rule) and their benches
        var teamKit = new CharacterSpec[2];
        foreach (var p in engine.State.Players)
            if (!p.IsKeeper && teamKit[p.Team] == null) teamKit[p.Team] = p.Spec;
        var bench = new List<CharacterSpec>[2];
        for (int t = 0; t < 2; t++)
        {
            int club = t == 0 ? opts.HomeClub : opts.AwayClub;
            var squad = Clubs.CreateRoster(club, 18, opts.Seed + 911 * (t + 1));
            bench[t] = squad.GetRange(Math.Min(11, squad.Count), Math.Max(0, squad.Count - 11));
        }
        var count = new Dictionary<string, int>();
        var rng = new Random(opts.Seed * 31 + 7);
        foreach (var s in doc.RootElement.GetProperty("spots").EnumerateArray())
        {
            string role = s.GetProperty("role").GetString() ?? "";
            int team = s.GetProperty("team").GetInt32();
            var pos = s.GetProperty("pos");
            // per team for the bench, per end of the ground for ball kids and photographers
            string key = role + (team >= 0 ? team.ToString() : pos[0].GetSingle() < 0 ? "W" : "E");
            int have = count.TryGetValue(key, out int c) ? c : 0;
            int cap = role switch { "sub" => maxSubs, "ballkid" => (maxKids + 1) / 2, "photographer" => maxPhoto / 2, "assistant" => assistants ? 1 : 0, _ => 1 };
            if (have >= cap) continue;
            count[key] = have + 1;
            var kit = team >= 0 ? teamKit[team] : null;
            var spec = SpecFor(role, team, have, kit, team >= 0 && have < bench[team].Count ? bench[team][have] : null, rng);
            var rig = RigFactory.Create(spec);
            rig.Name = $"Pitchside_{key}_{have}";
            if (rig.NameLabel != null) rig.NameLabel.Visible = false;
            AddChild(rig);
            float x = pos[0].GetSingle(), y = pos[1].GetSingle(), z = pos[2].GetSingle();
            bool seated = s.TryGetProperty("seated", out var se) && se.GetBoolean();
            rig.Position = new Vector3(x, seated ? 0f : y, z);
            rig.Rotation = new Vector3(0, s.GetProperty("yaw").GetSingle(), 0);
            var person = new Person { Rig = rig, Role = role, Team = team, Seated = seated, SeatTop = y, Seat = new Vector3(x, y, z),
                                      Clip = s.GetProperty("clip").GetString() ?? "" };
            Dress(person, spec, kit);
            rig.Soccer?.PlayLoop(person.Clip, (float)rng.NextDouble(), .85f + .3f * (float)rng.NextDouble());
            if (seated) person.Settle = .15f;
            if (role == "photographer") AttachCamera(rig);
            _people.Add(person);
        }
    }

    private static CharacterSpec SpecFor(string role, int team, int k, CharacterSpec? kit, CharacterSpec? sub, Random rng)
    {
        if (role == "sub" && sub != null && kit != null)
        {
            // the bench wears a training bib over the kit, long sleeves in the team colour
            sub.KitPrimary = Bibs[(team * 2 + 1) % Bibs.Length];
            sub.KitSecondary = sub.KitPrimary;
            sub.KitPattern = "plain";
            sub.KitTrim = kit.KitPrimary;
            sub.ShortsColor = kit.ShortsColor;
            sub.SocksColor = kit.SocksColor;
            sub.LongSleeves = true;
            sub.DisplayName = "";
            sub.Number = 0;
            return sub;
        }
        string team1 = kit?.KitPrimary ?? "#1d4ed8";
        string dark = Darker(team1, .42f);
        var (jersey, trim, legs, boots, height, bulk) = role switch
        {
            "manager" => ("#1c1f26", "#2a2f3a", "#22252d", "#0b0b0d", 1.76f + .12f * (float)rng.NextDouble(), 1.08f),
            "assistant" => (dark, team1, "#1f2229", "#0b0b0d", 1.74f + .12f * (float)rng.NextDouble(), 1.0f),
            "ballkid" => ("#0f2b46", "#e9eaee", "#0f2b46", "#e9eaee", 1.42f + .1f * (float)rng.NextDouble(), .82f),
            _ => ("#f97316", "#1f2937", "#2b2f36", "#111111", 1.72f + .14f * (float)rng.NextDouble(), 1.02f),   // photographer
        };
        return new CharacterSpec
        {
            Name = $"{role}#{team}#{k}", DisplayName = "", Number = 0, Role = Role.Midfielder,
            KitPrimary = jersey, KitSecondary = jersey, KitTrim = trim, KitPattern = "plain",
            ShortsColor = legs, SocksColor = legs, BootsColor = boots, LongSleeves = true,
            Height = height, Bulk = bulk, SkinTone = rng.Next(0, 6),
        };
    }

    private static void Dress(Person p, CharacterSpec spec, CharacterSpec? kit)
    {
        var s = p.Rig.Soccer;
        if (s == null) return;
        bool trousers = p.Role != "sub";
        s.Wear(sleeves: true, trousers: trousers);
        if (p.Role == "sub" && kit != null) s.SetLayerColor("sleeves", CharacterRig.C(kit.KitPrimary));
        else if (p.Role == "photographer") s.SetLayerColor("sleeves", CharacterRig.C("#2b2f36"));
    }

    private static string Darker(string hex, float k)
    {
        var c = CharacterRig.C(hex);
        return "#" + new Color(c.R * k, c.G * k, c.B * k).ToHtml(false);
    }

    private static GltfDocument? _doc;
    private static GltfState? _state;

    private static void AttachCamera(CharacterRig rig)
    {
        var skel = rig.Soccer?.Skel;
        if (skel == null || !Godot.FileAccess.FileExists(PropsPath)) return;
        if (_state == null)
        {
            _doc = new GltfDocument();
            var st = new GltfState();
            if (_doc.AppendFromFile(PropsPath, st) != Error.Ok) return;
            _state = st;
        }
        if (_doc!.GenerateScene(_state) is not Node3D scene) return;
        int bone = SoccerClipRig.FindBoneLoose(skel, "RHand");
        if (bone < 0) { scene.QueueFree(); return; }
        var hand = new BoneAttachment3D { Name = "Camera", BoneName = skel.GetBoneName(bone), BoneIdx = bone };
        skel.AddChild(hand);
        hand.AddChild(scene);
        // body in the palm, the lens pointing where the face looks
        scene.Position = new Vector3(-.04f, -.02f, .06f);
        scene.RotationDegrees = new Vector3(-80, 0, 0);
        foreach (var n in scene.FindChildren("*", "MeshInstance3D", true, false))
            if (n is MeshInstance3D mi && mi.GetActiveMaterial(0) is BaseMaterial3D bm)
            {
                bm.VertexColorUseAsAlbedo = true;
                bm.VertexColorIsSrgb = true;
            }
    }

    /// <summary>A goal: the scoring bench jumps up, its manager turns to shout, the other bench sits on.</summary>
    public void OnGoal(int team)
    {
        foreach (var p in _people)
        {
            if (p.Team != team) continue;
            var s = p.Rig.Soccer;
            if (s == null) continue;
            if (p.Role == "sub") p.OneShot = s.PlayOnce("sub_cheer");
            else if (p.Role == "manager") { s.PlayLoop("manager_shout", 0f); p.OneShot = 4.5f; }
        }
    }

    public override void _Process(double delta)
    {
        float dt = (float)delta;
        foreach (var p in _people)
        {
            // sit the bench on its seats once the clip has posed them: hips just above the cushion
            if (p.Settle > 0f)
            {
                p.Settle -= dt;
                if (p.Settle <= 0f && p.Rig.Soccer != null)
                {
                    var hips = p.Rig.Soccer.HipsWorld();
                    if (hips.Y > .05f)
                    {
                        // hips over the cushion (a touch forward of its centre), the hip joint a hand above it
                        var fwd = new Vector3(Mathf.Sin(p.Rig.Rotation.Y), 0, Mathf.Cos(p.Rig.Rotation.Y));
                        var want = p.Seat + fwd * .04f + new Vector3(0, .06f, 0);
                        p.Rig.Position += want - hips;
                    }
                }
            }
            if (p.OneShot > 0f)
            {
                p.OneShot -= dt;
                if (p.OneShot <= 0f) p.Rig.Soccer?.PlayLoop(p.Clip, 0f);
            }
        }
    }

    public int Count => _people.Count;
}
