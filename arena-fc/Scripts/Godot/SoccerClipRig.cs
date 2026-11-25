// Arena FC - Sprite Forge soccer player (sculpted mesh + 18-bone skeleton + 71 clips).
//
// Tools/build_soccer_player.py builds Data/models/soccer_player.glb from the
// latest Sprite Forge pipeline (sforge.footballer + sforge.gamemesh, retargeted
// soccer clips) plus Data/soccer_player_manifest.json (clip list, loop flags,
// action aliases, material order).  This loader plays those clips from the
// match engine's PlayerState, tinting the flat kit materials per CharacterSpec
// exactly like the procedural rig.  When the GLB is absent the game falls back
// to the procedural CharacterRig untouched.
//
// Phase 1 (AME core):
//   1.1 blend space: speed x turnRate x ballState -> clip + phase + weight
//   1.2 foot-planting IK: two-bone analytic IK (port of footlock._ik)
//   1.3 archetypes: Explosive/Lengthy/Controlled style biases
//   1.5 look-at (head tracks ball) + reach (arm extends toward ball)
//   1.6 phase sync: on clip switch, start the new clip at the matching phase
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using ArenaFC.Core;
using ArenaFC.Core.Animation;
using Godot;

namespace ArenaFC.GodotGame;

public sealed partial class SoccerClipRig : Node3D
{
    public const string GlbPath = "res://Data/models/soccer_player.glb";
    public const string ManifestPath = "res://Data/soccer_player_manifest.json";

    public static bool Available => Godot.FileAccess.FileExists(GlbPath);

    public AnimationPlayer? Player;
    public Skeleton3D? Skel;
    public MeshInstance3D? Mesh;
    // Realistic GLB: one mesh node per body part per identity ("v0_body", "v5_hair" ...).
    private readonly List<MeshInstance3D> _meshes = new();
    private static GltfDocument? _gltfDoc;
    private static GltfState? _gltfState;

    private readonly Dictionary<string, string> _aliases = new();
    private readonly HashSet<string> _loops = new();
    private readonly Dictionary<string, float> _clipDuration = new();
    private readonly Dictionary<string, float> _contactFrac = new();
    private readonly List<string> _materialOrder = new();
    private float _height = 1.77f;
    private string _current = "";
    private bool _oneShotDone = true;
    private MotionState? _motionState;

    /// <summary>Presentation-only motion input; never written back to PlayerState.</summary>
    public void ApplyMotion(MotionState? motion) => _motionState = motion;

    // FIFA-style locomotion state.
    private Node3D? _sceneRoot;
    private float _speedScale = 1f;
    private float _lean, _roll;
    private float _styleStride = 1f, _styleLean = 1f;
    private System.Numerics.Vector3 _prevVel = System.Numerics.Vector3.Zero;
    private System.Numerics.Vector3 _prevFacing = new(0, 0, 1);
    private float _turnCooldown;

    // Phase 1 blend-space state.
    private float _speed;        // smoothed ground speed (m/s)
    private float _turnRate;     // smoothed yaw rate (rad/s)
    private float _phase;        // 0..1 cycle phase of the current clip
    private bool _hasBall;
    private float _blend;        // 0..1 crossfade progress on clip switch
    private Vector3 _prevPos;
    private float _prevYaw;
    private bool _primed;

    // Phase 1.3 archetype biases.
    private float _archetypeLean = .12f;
    private float _archetypeCadence = 1f;
    private float _archetypeStride = 1f;
    private float _archetypeRoll = .04f;

    // Phase 1.5 look-at / reach state.
    private float _lookYaw;
    private float _lookPitch;
    private float _reach;

    // Phase 1.2 foot-planting IK state.
    private readonly Dictionary<string, BoneData> _bones = new();
    private Vector3 _prevFootWorldL, _prevFootWorldR;
    private bool _hasPrevFootL, _hasPrevFootR;
    private Vector3 _prevPelvisPos;
    private bool _hasPrevPelvisPos;
    private Vector3 _groundNormalL = Vector3.Up;
    private Vector3 _groundNormalR = Vector3.Up;
    private float _lastIkCorrectionL;
    private float _lastIkCorrectionR;
    private float _lastInertialEnergy;
    private Label? _debugLabel;
    private bool _debugOverlayEnabled = !string.IsNullOrEmpty(System.Environment.GetEnvironmentVariable("ARENA_FC_DEBUG_OVERLAY"));

    // Hypermotion-style inertialization (presentation-only).
    private readonly Dictionary<int, Transform3D> _prevBonePoses = new();
    private readonly Dictionary<int, Transform3D> _inertialPrevFramePoses = new();
    private readonly List<(int bone, Vector3 posOff, Quaternion rotOff, Vector3 posVel, Vector3 angVel, float halfLife)> _inertialBones = new();
    private bool _inertialActive;
    private float _inertialTime;
    private float _inertialPrevDt = 1f / 60f;
    private Vector3 _prevPelvisWorld;
    private bool _hasPrevPelvis;

    private sealed class BoneData
    {
        public int Thigh, Shin, Foot, Spine, Neck, Head, UpperArmL, LowerArmL, UpperArmR, LowerArmR;
        public Vector3 ThighRest, ShinRest, FootRest, SpineRest, NeckRest, HeadRest;
        public Vector3 UpperArmRestL, LowerArmRestL, UpperArmRestR, LowerArmRestR;
    }

    // Foot travel per 1 s clip cycle, measured from the GLB (metres).  At
    // SpeedScale 1.0 the feet move at this rate, so SpeedScale =
    // ground speed / natural rate keeps foot speed ~= ground speed.
    private static readonly Dictionary<string, float> NaturalRate = new()
    {
        ["soccer_walk"] = 0.74f, ["soccer_jog"] = 1.01f, ["soccer_run"] = 1.01f,
        ["soccer_sprint"] = 1.22f, ["soccer_dribble"] = 0.60f,
        ["soccer_run_ball"] = 0.98f, ["soccer_shield"] = 0.30f,
        ["soccer_turn"] = 0.62f, ["soccer_strafe_l"] = 0.55f,
        ["soccer_strafe_r"] = 0.55f, ["soccer_backpedal"] = 0.58f,
        ["soccer_jockey"] = 0.66f,
    };

    private static readonly Dictionary<string, float> MaxRate = new()
    {
        ["soccer_walk"] = 2.2f, ["soccer_jog"] = 2.6f, ["soccer_run"] = 2.6f,
        ["soccer_sprint"] = 2.8f, ["soccer_dribble"] = 1.8f,
        ["soccer_run_ball"] = 2.6f, ["soccer_shield"] = 1.2f,
        ["soccer_turn"] = 1.6f, ["soccer_strafe_l"] = 1.6f,
        ["soccer_strafe_r"] = 1.6f, ["soccer_backpedal"] = 1.6f,
        ["soccer_jockey"] = 1.8f,
    };

    private static readonly Dictionary<string, string> FallbackAliases = new()
    {
        ["idle"] = "soccer_idle", ["run"] = "soccer_run", ["kick"] = "soccer_kick_place",
        ["tackle"] = "soccer_tackle", ["slide"] = "soccer_slide_tackle", ["dive"] = "soccer_keeper_dive_left",
        ["catch"] = "soccer_keeper_catch", ["foul"] = "soccer_trip", ["celebrate"] = "soccer_celebrate",
        ["thigh_control"] = "soccer_thigh_control", ["chest_control"] = "soccer_chest_control", ["volley"] = "soccer_volley",
        ["header"] = "soccer_header",
        ["punch"] = "soccer_punch", ["headbutt"] = "soccer_headbutt", ["knocked_down"] = "soccer_knocked_down",
        ["chip_shot"] = "soccer_chip_shot", ["trivela"] = "soccer_trivela", ["bicycle"] = "soccer_bicycle_kick",
    };

    public bool Load(CharacterSpec spec)
    {
        LoadManifest();
        GD.Print($"[SoccerClipRig] Loading GLB from {GlbPath}, exists={Godot.FileAccess.FileExists(GlbPath)}");
        // The GLB (several realistic identities, ~15 MB) is parsed once and every player's
        // scene generated from the same state.
        if (_gltfState == null)
        {
            _gltfDoc = new GltfDocument();
            var st = new GltfState();
            var err = _gltfDoc.AppendFromFile(GlbPath, st);
            if (err != Error.Ok)
            {
                GD.PrintErr($"[SoccerClipRig] AppendFromFile failed: {err}");
                return false;
            }
            _gltfState = st;
        }
        var scene = _gltfDoc!.GenerateScene(_gltfState) as Node3D;
        if (scene == null)
        {
            GD.PrintErr("[SoccerClipRig] GenerateScene returned null");
            return false;
        }
        AddChild(scene);
        _sceneRoot = scene;
        int h = 17;
        foreach (char c in (spec.DisplayName ?? "") + (int)spec.Role + spec.Pace.ToString("F2")) h = h * 31 + c;
        _styleStride = 0.93f + (Math.Abs(h) % 100) / 100f * 0.14f;
        _styleLean = 0.8f + (Math.Abs(h / 7) % 100) / 100f * 0.4f;
        Player = FindFirst<AnimationPlayer>(scene);
        Skel = FindFirst<Skeleton3D>(scene);
        _meshes.Clear();
        foreach (var n in scene.FindChildren("*", "MeshInstance3D", true, false))
            if (n is MeshInstance3D mi) _meshes.Add(mi);
        Mesh = _meshes.Count > 0 ? _meshes[0] : null;
        if (Player == null || Skel == null || Mesh == null)
        {
            GD.PrintErr($"[SoccerClipRig] Missing nodes: Player={Player != null}, Skel={Skel != null}, Mesh={Mesh != null}");
            return false;
        }
        GD.Print("[SoccerClipRig] GLB loaded OK");
        foreach (var name in Player.GetAnimationList())
        {
            var anim = Player.GetAnimation(name);
            if (anim != null)
                anim.LoopMode = _loops.Contains(name)
                    ? Animation.LoopModeEnum.Linear : Animation.LoopModeEnum.None;
        }
        ApplyVariant(spec);
        Tint(spec);
        SetArchetype(spec.Archetype);
        float s = _height > 0.01f ? spec.Height / _height : 1f;
        Scale = new Vector3(s, s, s);
        ApplyBuild(spec);
        CacheBones();
        return true;
    }

    /// <summary>Body build (gap A7): the identities share one body, so the squad's builds came from height
    /// alone.  Bulk (0.7..1.4) widens the chest and shoulders and thickens the upper arms - a uniform scale
    /// on the bone with its inverse on the children, so heads and hands keep their size and nothing skews.
    /// Clips animate rotations (and the hips' position) only, so the scale persists.</summary>
    public void ApplyBuild(CharacterSpec spec)
    {
        if (Skel == null) return;
        float bulk = Math.Clamp(spec.Bulk, .7f, 1.4f);
        float chest = 1f + (bulk - 1f) * .22f;                       // .93 .. 1.09
        float arm = 1f + (bulk - 1f) * .3f;
        float shoulders = 1f + (spec.ShoulderWidth - 1f) * .25f;
        void Set(string bone, float k)
        {
            int b = FindBoneLoose(Skel, bone);
            if (b >= 0) Skel.SetBonePoseScale(b, new Vector3(k, k, k));
        }
        Set("Chest", chest * shoulders);
        Set("Neck", 1f / (chest * shoulders));
        foreach (var side in new[] { "L", "R" })
        {
            Set(side + "UpperArm", arm / (chest * shoulders));
            Set(side + "Forearm", 1f / arm);
        }
    }

    /// <summary>Bone by name, tolerating the "_2" suffixes Godot adds each time one GltfState generates
    /// another scene (every player shares the parsed GLB).</summary>
    public static int FindBoneLoose(Skeleton3D skel, string name)
    {
        int b = skel.FindBone(name);
        if (b >= 0) return b;
        for (int i = 0; i < skel.GetBoneCount(); i++)
        {
            string n = skel.GetBoneName(i);
            if (n.StartsWith(name + "_") && n.Substring(name.Length).Replace("_2", "") == "") return i;
        }
        return -1;
    }

    private void LoadManifest()
    {
        foreach (var kv in FallbackAliases) _aliases[kv.Key] = kv.Value;
        _materialOrder.AddRange(new[] { "skin", "jersey", "shorts", "socks", "boots", "hair" });
        try
        {
            string text = Godot.FileAccess.GetFileAsString(ManifestPath);
            if (string.IsNullOrEmpty(text)) return;
            using var doc = JsonDocument.Parse(text);
            var root = doc.RootElement;
            if (root.TryGetProperty("action_aliases", out var aliases))
                foreach (var p in aliases.EnumerateObject()) _aliases[p.Name] = p.Value.GetString() ?? p.Name;
            if (root.TryGetProperty("clips", out var clips))
                foreach (var c in clips.EnumerateArray())
                {
                    if (!c.TryGetProperty("name", out var nm)) continue;
                    string clipName = nm.GetString() ?? "";
                    if (c.TryGetProperty("loop", out var loop) && loop.GetBoolean()) _loops.Add(clipName);
                    if (c.TryGetProperty("fps", out var fps) && c.TryGetProperty("frames", out var frames))
                        _clipDuration[clipName] = frames.GetSingle() / Math.Max(1f, fps.GetSingle());
                    if (c.TryGetProperty("events", out var ev)
                        && ev.TryGetProperty("ball_contact_frac", out var bc) && bc.ValueKind != JsonValueKind.Null)
                        _contactFrac[clipName] = bc.GetSingle();
                }
            if (root.TryGetProperty("materials", out var mats))
            {
                _materialOrder.Clear();
                foreach (var m in mats.EnumerateArray()) _materialOrder.Add(m.GetString() ?? "");
            }
            if (root.TryGetProperty("stats", out var stats) && stats.TryGetProperty("height_m", out var h))
                _height = h.GetSingle();
            if (_lodParts == null && root.TryGetProperty("lod", out var lod))
            {
                var parts = new Dictionary<string, int[]>();
                if (lod.TryGetProperty("parts", out var lp))
                    foreach (var q in lp.EnumerateObject())
                    {
                        var row = new List<int>();
                        foreach (var x in q.Value.EnumerateArray()) row.Add(x.GetInt32());
                        parts[q.Name] = row.ToArray();
                    }
                var dist = new Dictionary<string, float[]>();
                if (lod.TryGetProperty("distances_m", out var dm))
                    foreach (var q in dm.EnumerateObject())
                    {
                        var d = new List<float>();
                        foreach (var x in q.Value.EnumerateArray()) d.Add(x.GetSingle());
                        dist[q.Name] = d.ToArray();
                    }
                _lodDistances = dist;
                _lodParts = parts;
            }
        }
        catch (Exception) { /* fallback aliases above still cover the core actions */ }
    }

    /// <summary>Which identity prefix ("v0_") a player shows: stable per character Id,
    /// so the same player always has the same face.</summary>
    public static string VariantFor(CharacterSpec spec, IReadOnlyList<string> prefixes)
        => VariantFor(spec, prefixes, null);

    /// <summary>The identity a player wears: deterministic from his name and number (the same face every
    /// launch - the GUID Id changed each run), and, when the identities' skin tones are known, among the
    /// three whose skin is closest to his SkinTone.</summary>
    public static string VariantFor(CharacterSpec spec, IReadOnlyList<string> prefixes, IReadOnlyDictionary<string, float>? skinLum)
    {
        if (prefixes.Count == 0) return "";
        int h = 7;
        foreach (char c in (spec.Name ?? "") + "#" + spec.Number) h = unchecked(h * 31 + c);
        var pool = prefixes.ToList();
        if (skinLum != null && skinLum.Count == prefixes.Count && prefixes.Count > 3)
        {
            var c = CharacterRig.C(spec.SkinHex);
            float want = .2126f * c.R + .7152f * c.G + .0722f * c.B;
            pool = prefixes.OrderBy(p => Math.Abs(skinLum[p] - want)).Take(3).OrderBy(p => p, StringComparer.Ordinal).ToList();
        }
        return pool[(int)((uint)h % (uint)pool.Count)];
    }

    // identity -> mean skin luminance (from its skin atlas), measured once
    private static Dictionary<string, float>? _skinLum;

    private Dictionary<string, float>? SkinLuminance(List<string> prefixes)
    {
        if (_skinLum != null && _skinLum.Count == prefixes.Count) return _skinLum;
        var lum = new Dictionary<string, float>();
        foreach (var mi in _meshes)
        {
            string n = mi.Name.ToString();
            if (!n.EndsWith("_body") || n.Length < 4) continue;
            var mat = mi.Mesh?.SurfaceGetMaterial(0) as BaseMaterial3D;
            var img = mat?.AlbedoTexture?.GetImage();
            if (img == null || img.IsEmpty()) continue;
            if (img.IsCompressed()) img.Decompress();
            img.Resize(32, 32, Image.Interpolation.Bilinear);
            float sum = 0; int cnt = 0;
            for (int y = 8; y < 24; y++)
                for (int x = 8; x < 24; x++)
                {
                    var c = img.GetPixel(x, y);
                    if (c.A < .5f) continue;
                    sum += .2126f * c.R + .7152f * c.G + .0722f * c.B; cnt++;
                }
            if (cnt > 0) lum[n[..3]] = sum / cnt;
        }
        _skinLum = lum.Count == prefixes.Count ? lum : null;
        return _skinLum;
    }

    /// <summary>Realistic GLB: show one identity per player (all ship in the file; hidden ones cost nothing).</summary>
    private void ApplyVariant(CharacterSpec spec)
    {
        var prefixes = new List<string>();
        foreach (var mi in _meshes)
        {
            string n = mi.Name.ToString();
            if (n.Length > 3 && n[0] == 'v' && char.IsDigit(n[1]) && n[2] == '_' && !prefixes.Contains(n[..3])) prefixes.Add(n[..3]);
        }
        prefixes.Sort(StringComparer.Ordinal);
        string pick = VariantFor(spec, prefixes, SkinLuminance(prefixes));
        if (pick == "") return;
        foreach (var mi in _meshes)
        {
            string n = mi.Name.ToString();
            if (n.Length > 3 && n[0] == 'v' && n[2] == '_')
                mi.Visible = n.StartsWith(pick) && OptionalLayerShown(n, spec.IsKeeper, spec.IsKeeper || spec.LongSleeves, false);
        }
        _pick = pick;
        foreach (var mi in _meshes) if (mi.Visible) { Mesh = mi; break; }
        ApplyLods(pick);
    }

    // ---- Levels of detail (Sprite Forge skinlod v11.38, Tools/add_lods.py) ----
    private static Dictionary<string, int[]>? _lodParts;
    private static Dictionary<string, float[]>? _lodDistances;

    /// <summary>Switch distances (m) for the current quality tier: full detail up close and in replays,
    /// then about 45% and 20% of the triangles.</summary>
    public static float[] LodDistances()
    {
        string tier = RenderProfile.Tier switch { RenderTier.Ultra => "ultra", RenderTier.High => "high", _ => "performance" };
        if (_lodDistances != null && _lodDistances.TryGetValue(tier, out var d) && d.Length >= 2) return d;
        return new[] { 16f, 36f };
    }

    /// <summary>Visibility ranges on the identity's meshes: each part's base mesh, its _lod1 and _lod2 nodes
    /// hand over at the tier's distances (a part dropped from a level just ends there).</summary>
    private void ApplyLods(string pick)
    {
        if (_lodParts == null || pick == "") return;
        var dist = LodDistances();
        float At(int level) => level <= 0 ? 0f : level - 1 < dist.Length ? dist[level - 1] : float.MaxValue;
        foreach (var mi in _meshes)
        {
            string n = mi.Name.ToString();
            if (!n.StartsWith(pick)) continue;
            string rest = n[pick.Length..];
            int level = 0;
            int at = rest.LastIndexOf("_lod", StringComparison.Ordinal);
            if (at > 0 && int.TryParse(rest[(at + 4)..], out int k)) { level = k; rest = rest[..at]; }
            if (!_lodParts.TryGetValue(rest, out var row)) continue;
            int next = -1;
            for (int m = level + 1; m <= row.Length; m++) if (row[m - 1] != 0) { next = m; break; }
            mi.VisibilityRangeBegin = At(level);
            mi.VisibilityRangeBeginMargin = level > 0 ? 1.5f : 0f;
            mi.VisibilityRangeEnd = next > 0 ? At(next) : 0f;          // 0 = no end
            mi.VisibilityRangeEndMargin = next > 0 ? 1.5f : 0f;
        }
        if (!_lodLogged) { _lodLogged = true; GD.Print($"ARENA_FC_LOD tier={RenderProfile.Tier} switch={dist[0]}m/{dist[1]}m parts={_lodParts.Count}"); }
    }
    private static bool _lodLogged;

    /// <summary>Optional garments (Sprite Forge tailor.keeper_garments / staff_garments): the long-sleeved base
    /// layer, gloves and trousers ride along in every identity, hidden unless the role wears them.</summary>
    private static bool OptionalLayerShown(string node, bool gloves, bool sleeves, bool trousers)
        => node.Contains("_gloves") ? gloves : node.Contains("_sleeves") ? sleeves : !node.Contains("_trousers") || trousers;
    private string _pick = "";

    // ---- Touchline figures (Sprite Forge pitchside v11.39): a role's clothes and a looping clip ----
    /// <summary>Show the identity's optional layers for a pitch-side role (base layer, trousers, gloves).</summary>
    public void Wear(bool sleeves, bool trousers, bool gloves = false)
    {
        foreach (var mi in _meshes)
        {
            string n = mi.Name.ToString();
            if (_pick == "" || !n.StartsWith(_pick)) continue;
            if (n.Contains("_sleeves") || n.Contains("_trousers") || n.Contains("_gloves"))
                mi.Visible = OptionalLayerShown(n, gloves, sleeves, trousers);
        }
    }

    /// <summary>Recolour one non-kit layer of this player (e.g. a sub's sleeves in the team colour under his bib).</summary>
    public void SetLayerColor(string layer, Color c)
    {
        foreach (var mi in _meshes)
        {
            if (mi.Mesh == null) continue;
            for (int i = 0; i < mi.Mesh.GetSurfaceCount(); i++)
                if (mi.GetSurfaceOverrideMaterial(i) is StandardMaterial3D m && m.ResourceName == layer) m.AlbedoColor = c;
        }
    }

    /// <summary>Play a looping clip from `phase` (0..1) at `speed`; no locomotion, no match state.</summary>
    public void PlayLoop(string clip, float phase, float speed = 1f)
    {
        if (Player == null || !Player.HasAnimation(clip)) return;
        var anim = Player.GetAnimation(clip);
        anim.LoopMode = Animation.LoopModeEnum.Linear;
        Player.Play(clip, .3f);
        Player.Seek(phase * anim.Length, true);
        Player.SpeedScale = speed;
        _current = clip;
    }

    /// <summary>Play a one-shot clip once; -> its length in seconds (0 when missing).</summary>
    public float PlayOnce(string clip)
    {
        if (Player == null || !Player.HasAnimation(clip)) return 0f;
        Player.Play(clip, .15f);
        Player.Seek(0, true);
        Player.SpeedScale = 1f;
        _current = clip;
        return (float)Player.GetAnimation(clip).Length;
    }

    /// <summary>World position of the hips (for sitting a figure on a seat).</summary>
    public Vector3 HipsWorld()
    {
        if (Skel == null) return Vector3.Zero;
        int b = FindBoneLoose(Skel, "Hips");
        return b < 0 ? Vector3.Zero : (Skel.GlobalTransform * Skel.GetBoneGlobalPose(b)).Origin;
    }

    /// <summary>Club / character colour for a material name, or null to keep it as authored:
    /// kit slots take the club colours, the hair family the player's hair colour, a flat
    /// sculpt "skin" the skin tone; realistic skin and eye atlases stay natural.</summary>
    public static string? TintHexFor(string layer, CharacterSpec spec)
    {
        switch (layer)
        {
            case "jersey": return spec.KitPrimary;
            case "shorts": return spec.ShortsColor;
            case "socks": return spec.SocksColor;
            case "boots": return spec.BootsColor;
            case "hair": case "beard_shell": case "facial_hair": return spec.HairColor;
            case "skin": return spec.SkinHex;
            case "sleeves": return spec.KitPrimary;      // keeper base layer in the shirt colour
            case "trousers": return spec.ShortsColor;    // staff trousers (pitch-side roles)
            case "gloves": return spec.GlovesColor;
        }
        if (layer.StartsWith("hair_") || layer.StartsWith("eyebrows_") || layer.StartsWith("eyelashes_")) return spec.HairColor;
        return null;
    }

    // ---- Kit on the Sprite Forge tailor atlas (sforge.tailor / sforge.kitdesign v11.30) ----
    public const string KitDir = "res://Data/textures/kit/";
    private static Shader? _kitShader;
    private static Texture2D? _kitDetail, _kitGlyphs;
    private static readonly Dictionary<string, Texture2D> _kitPatterns = new();
    private const string Glyphs = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ.-' ";

    /// <summary>True when the GLB carries tailored kit (atlas UVs) and the Sprite Forge masks are present.</summary>
    public static bool KitAtlasAvailable => Godot.FileAccess.FileExists(KitDir + "kit_detail.png")
                                            && Godot.FileAccess.FileExists("res://Shaders/kit.gdshader");

    private static Texture2D? KitTex(string file)
    {
        string path = KitDir + file;
        if (!Godot.FileAccess.FileExists(path)) return null;
        return GD.Load<Texture2D>(path);
    }

    /// <summary>The player's name as glyph indices for the shirt (kit_layout.json "glyphs").</summary>
    public static int[] ShirtGlyphs(string name, out int len)
    {
        var g = new int[14];
        string up = (name ?? "").ToUpperInvariant();
        len = Math.Min(up.Length, 14);
        for (int i = 0; i < 14; i++)
        {
            int k = i < len ? Glyphs.IndexOf(up[i]) : -1;
            g[i] = k < 0 ? Glyphs.Length - 1 : k;
        }
        return g;
    }

    /// <summary>One ShaderMaterial for shirt/shorts/socks/boots: every kit surface samples the same atlas.</summary>
    public static ShaderMaterial? KitMaterial(CharacterSpec spec, float wet = 0f)
    {
        if (!KitAtlasAvailable) return null;
        _kitShader ??= GD.Load<Shader>("res://Shaders/kit.gdshader");
        _kitDetail ??= KitTex("kit_detail.png");
        _kitGlyphs ??= KitTex("kit_glyphs.png");
        string style = string.IsNullOrEmpty(spec.KitPattern) ? "plain" : spec.KitPattern;
        if (!_kitPatterns.TryGetValue(style, out var pat))
        {
            pat = KitTex($"kit_pattern_{style}.png") ?? KitTex("kit_pattern_plain.png")!;
            _kitPatterns[style] = pat;
        }
        var m = new ShaderMaterial { Shader = _kitShader };
        m.SetShaderParameter("pattern_tex", pat);
        m.SetShaderParameter("detail_tex", _kitDetail);
        m.SetShaderParameter("glyph_tex", _kitGlyphs);
        var prim = CharacterRig.C(spec.KitPrimary);
        var sec = CharacterRig.C(spec.KitSecondary);
        m.SetShaderParameter("primary", prim);
        m.SetShaderParameter("secondary", sec);
        string trimHex = string.IsNullOrEmpty(spec.KitTrim) ? spec.ShortsColor : spec.KitTrim;
        var trim = CharacterRig.C(trimHex);
        // a trim that vanishes into the shirt reads as no trim: fall back to the secondary
        if (Lum(trim) - Lum(prim) is > -.06f and < .06f) trim = sec;
        m.SetShaderParameter("trim", trim);
        m.SetShaderParameter("shorts", CharacterRig.C(spec.ShortsColor));
        m.SetShaderParameter("socks", CharacterRig.C(spec.SocksColor));
        m.SetShaderParameter("boots", CharacterRig.C(spec.BootsColor));
        m.SetShaderParameter("boot_detail", Lum(CharacterRig.C(spec.BootsColor)) > .55f ? new Color(.08f, .09f, .12f) : new Color(.93f, .94f, .96f));
        // print in whichever of the kit colours stands out from the shirt, outlined in the other
        bool lightShirt = Lum(prim) > .55f;
        var fill = lightShirt ? (Lum(sec) < .45f ? sec : new Color(.06f, .07f, .1f)) : (Lum(sec) > .55f ? sec : new Color(1, 1, 1));
        if (spec.KitPattern is "stripes" or "hoops" or "halves" or "quarters" or "pinstripes")
            fill = lightShirt && Lum(sec) > .55f ? new Color(.06f, .07f, .1f) : new Color(1, 1, 1);
        var edge = Lum(fill) > .5f ? trim.Darkened(.35f) : new Color(1, 1, 1);
        m.SetShaderParameter("print_fill", fill);
        m.SetShaderParameter("print_edge", edge);
        m.SetShaderParameter("number", Math.Clamp(spec.Number, 0, 99));   // 0: officials, no number
        var glyphs = ShirtGlyphs(spec.DisplayName, out int len);
        m.SetShaderParameter("name_chars", glyphs);
        m.SetShaderParameter("name_len", len);
        m.SetShaderParameter("wet", wet);
        uint seed = (uint)spec.Number * 31u;
        foreach (char ch in spec.DisplayName ?? "") seed = seed * 131u + ch;
        m.SetShaderParameter("flutter_seed", seed % 1000u / 1000f);
        return m;
    }

    /// <summary>A tailored garment's UVs span the kit atlas panels; the old skin-tight kits used
    /// a small corner of the MakeHuman clothes atlas.  Old GLBs keep the flat tint.</summary>
    private static readonly Dictionary<ulong, bool> _atlasUv = new();
    private static bool HasAtlasUv(MeshInstance3D mi, int surface)
    {
        ulong key = mi.Mesh.GetInstanceId() * 8UL + (ulong)surface;
        if (_atlasUv.TryGetValue(key, out bool known)) return known;
        bool r = AtlasUvScan(mi, surface);
        _atlasUv[key] = r;
        return r;
    }

    private static bool AtlasUvScan(MeshInstance3D mi, int surface)
    {
        var arr = mi.Mesh.SurfaceGetArrays(surface);
        if (arr.Count <= (int)Godot.Mesh.ArrayType.TexUV || arr[(int)Godot.Mesh.ArrayType.TexUV].VariantType == Variant.Type.Nil) return false;
        var uv = arr[(int)Godot.Mesh.ArrayType.TexUV].AsVector2Array();
        float maxU = 0, maxV = 0;
        foreach (var p in uv) { if (p.X > maxU) maxU = p.X; if (p.Y > maxV) maxV = p.Y; }
        return maxU > .55f || maxV > .76f;
    }

    private static float Lum(Color c) => .2126f * c.R + .7152f * c.G + .0722f * c.B;

    private ShaderMaterial? _kit;
    private float _flutter, _flutterSent = -1f;

    /// <summary>Sleeve and shorts hems ripple with the player's speed (kit.gdshader, tailor flutter weights).</summary>
    private void UpdateFlutter(float speed, float dt)
    {
        if (_kit == null) return;
        _flutter += (Math.Clamp(speed / 8f, 0f, 1f) - _flutter) * Math.Min(1f, dt * 3f);
        if (Math.Abs(_flutter - _flutterSent) < .03f) return;
        _flutterSent = _flutter;
        _kit.SetShaderParameter("flutter_speed", _flutter);
    }
    /// <summary>The live kit material (weather / dirt are set on it during a match).</summary>
    public ShaderMaterial? KitShader => _kit;

    /// <summary>Retint the GLB materials from the character spec (per club), by material name.</summary>
    public void Tint(CharacterSpec spec)
    {
        _kit = KitMaterial(spec);
        foreach (var mi in _meshes)
        {
            if (mi.Mesh == null) continue;
            for (int i = 0; i < mi.Mesh.GetSurfaceCount(); i++)
            {
                var src = mi.GetSurfaceOverrideMaterial(i) ?? mi.Mesh.SurfaceGetMaterial(i);
                if (src is not BaseMaterial3D && src is not ShaderMaterial) continue;
                string layer = src.ResourceName ?? "";
                if (layer == "" && _materialOrder.Count > i) layer = _materialOrder[i];
                if (_kit != null && layer is "jersey" or "shorts" or "socks" or "boots" && HasAtlasUv(mi, i))
                {
                    mi.SetSurfaceOverrideMaterial(i, _kit);
                    continue;
                }
                if (src is not StandardMaterial3D std) continue;
                if (layer == "" && _materialOrder.Count > i) layer = _materialOrder[i];   // older sculpt GLBs
                if (CloseUpShading(mi, i, std, layer, TintHexFor(layer, spec))) continue;
                string? hex = TintHexFor(layer, spec);
                if (hex == null) continue;
                var mat = (StandardMaterial3D)std.Duplicate();
                mat.AlbedoColor = CharacterRig.C(hex);
                bool kit = layer is "jersey" or "shorts" or "socks";
                mat.Roughness = layer is "boots" ? .34f : kit ? .68f : mat.Roughness;
                mat.MetallicSpecular = .38f;
                mat.RimEnabled = kit || layer == "skin";
                mat.Rim = .22f;
                mat.RimTint = .30f;
                if (kit || layer is "skin" or "boots") mat.CullMode = BaseMaterial3D.CullModeEnum.Disabled;
                mi.SetSurfaceOverrideMaterial(i, mat);
            }
        }
    }

    // ---- Close-up shading (Sprite Forge sforge.skinshade v11.36) ----------------------------------------
    private static Texture2D? _skinDetailN, _skinDetailR;
    private static readonly Dictionary<string, StandardMaterial3D> _shaded = new();

    /// <summary>Skin, hair, eyes, lashes and beards of the realistic identities: pore detail and subsurface
    /// scattering on skin, anisotropic alpha-to-coverage hair, a wet catch-light in the eyes.  Shared per
    /// source material (identities are reused across the squad).  Subsurface / anisotropy / clearcoat
    /// need Forward+; on the GL renderer the same materials just stay simpler.</summary>
    private static bool CloseUpShading(MeshInstance3D mi, int surface, StandardMaterial3D std, string layer, string? tint)
    {
        string kind = layer.StartsWith("skin_") ? "skin" : layer.StartsWith("hair_") ? "hair"
            : layer.StartsWith("eyes_") ? "eyes" : layer.StartsWith("eyelashes") ? "lashes"
            : layer is "beard_shell" or "facial_hair" || layer.StartsWith("eyebrows") ? "beard" : "";
        if (kind == "") return false;
        // shared per source material and tint (hair cards are grey, coloured with each player's hair colour)
        string key = std.GetInstanceId() + "|" + (tint ?? "");
        if (!_shaded.TryGetValue(key, out var mat))
        {
            mat = (StandardMaterial3D)std.Duplicate();
            if (tint != null) mat.AlbedoColor = CharacterRig.C(tint);
            bool fp = RenderProfile.ForwardPlus;
            switch (kind)
            {
                case "skin":
                    mat.Roughness = .52f;
                    mat.MetallicSpecular = .35f;
                    mat.RimEnabled = true; mat.Rim = .18f; mat.RimTint = .5f;
                    _skinDetailN ??= LoadTex("res://Data/textures/skin/skin_detail_normal.png");
                    if (_skinDetailN != null)
                    {
                        // pores: a 4 cm tile projected triplanar in the body's own space (UV2), independent
                        // of the 1-2k colour atlas on UV1
                        mat.DetailEnabled = true;
                        mat.DetailNormal = _skinDetailN;
                        mat.DetailUVLayer = BaseMaterial3D.DetailUV.UV2;
                        mat.UV2Triplanar = true;
                        mat.UV2Scale = new Vector3(25f, 25f, 25f);
                        // the detail layer is a normal map only: multiply leaves the colour atlas untouched
                        mat.DetailBlendMode = BaseMaterial3D.BlendModeEnum.Mul;
                    }
                    if (fp && RenderProfile.Tier >= RenderTier.High)
                    {
                        mat.SubsurfScatterEnabled = true;
                        mat.SubsurfScatterStrength = .28f;
                        mat.SubsurfScatterSkinMode = true;
                    }
                    break;
                case "hair":
                case "beard":
                    mat.Roughness = kind == "hair" ? .38f : .55f;
                    mat.MetallicSpecular = .5f;
                    mat.Transparency = BaseMaterial3D.TransparencyEnum.AlphaScissor;
                    mat.AlphaScissorThreshold = kind == "hair" ? .45f : .35f;
                    mat.AlphaAntialiasingMode = BaseMaterial3D.AlphaAntiAliasing.AlphaToCoverage;
                    mat.CullMode = BaseMaterial3D.CullModeEnum.Disabled;
                    if (fp) { mat.AnisotropyEnabled = true; mat.Anisotropy = kind == "hair" ? .6f : .3f; }
                    break;
                case "eyes":
                    // MakeHuman's brown irises are red-brown; the broadcast grade pushed them to red
                    mat.AlbedoColor = new Color(.84f, .9f, 1f);
                    mat.Roughness = .05f;
                    mat.MetallicSpecular = .8f;
                    if (fp) { mat.ClearcoatEnabled = true; mat.Clearcoat = 1f; mat.ClearcoatRoughness = .02f; }
                    break;
                case "lashes":
                    mat.Roughness = .6f;
                    mat.Transparency = BaseMaterial3D.TransparencyEnum.AlphaScissor;
                    mat.AlphaScissorThreshold = .4f;
                    mat.CullMode = BaseMaterial3D.CullModeEnum.Disabled;
                    break;
            }
            _shaded[key] = mat;
        }
        mi.SetSurfaceOverrideMaterial(surface, mat);
        return true;
    }

    private static Texture2D? LoadTex(string path)
        => ResourceLoader.Exists(path) ? GD.Load<Texture2D>(path) : null;

    /// <summary>Set the player's movement archetype (Phase 1.3).</summary>
    public void SetArchetype(Archetype archetype)
    {
        switch (archetype)
        {
            case Archetype.Explosive:
                _archetypeLean = .16f; _archetypeCadence = 1.12f;
                _archetypeStride = .92f; _archetypeRoll = .05f;
                break;
            case Archetype.Lengthy:
                _archetypeLean = .10f; _archetypeCadence = .88f;
                _archetypeStride = 1.14f; _archetypeRoll = .03f;
                break;
            default: // Controlled
                _archetypeLean = .12f; _archetypeCadence = 1f;
                _archetypeStride = 1f; _archetypeRoll = .04f;
                break;
        }
    }

    /// <summary>Drive the clip player from one match-engine player state.
    /// Phase 1: blend space (speed x turnRate x ballState), phase sync on
    /// clip switch, foot-planting IK, look-at/reach, archetype biases.
    /// Phase 0.1: one-shot clips are speed-matched so the ball_contact frame
    /// lands at the sim's contact time.</summary>
    public void Update(PlayerState p, float dt)
    {
        if (Player == null) return;
        // Paused: freeze animation playback so players don't run on the spot.
        if (dt <= 0f)
        {
            Player.SpeedScale = 0f;
            return;
        }
        Player.SpeedScale = _speedScale;
        float speed = Mx.Flat(p.Vel).Length();
        bool hasBall = p.Dribbling || p.Shielding;

        // Track measured speed + turn rate for the blend space.
        var worldPos = new Vector3(p.Pos.X, p.Pos.Y, p.Pos.Z);
        float yaw = Mathf.Atan2(-p.Facing.X, -p.Facing.Z);
        if (!_primed) { _prevPos = worldPos; _prevYaw = yaw; _primed = true; _speed = speed; }
        float measured = speed > 0f ? speed : (worldPos - _prevPos).Length() / Mathf.Max(dt, 1e-4f);
        _speed = Mathf.Lerp(_speed, measured, .25f);
        float dyaw = Mathf.AngleDifference(yaw, _prevYaw);
        _turnRate = Mathf.Lerp(_turnRate, dyaw / Mathf.Max(dt, 1e-4f), .2f);
        _prevPos = worldPos; _prevYaw = yaw;
        _hasBall = hasBall;

        // One-shots (actions) take priority over locomotion.
        string clip = SelectClip(p, speed, out bool oneShot);
        bool motionDriven = _motionState != null && _motionState.RenderClipId.Length > 0;
        // An engine one-shot with its own clip (foul -> trip, catch, parry, header,
        // throw-in ...) wins over plain locomotion: the motion engine has no intent
        // for these and used to keep the player running through them.
        if (motionDriven && p.ActionTimer > 0f && _aliases.TryGetValue(p.Action, out var own)
            && (_motionState!.LastIntent is PlayerIntent.Move or PlayerIntent.Sprint
                // A dedicated action the motion engine is not already playing (no
                // feature table loaded): play its own clip directly.
                || (Dedicated(p.Action) && _motionState.RenderClipId != own)))
            motionDriven = false;
        if (motionDriven)
        {
            clip = _motionState!.RenderClipId;
            oneShot = _motionState.LastIntent is PlayerIntent.Pass or PlayerIntent.ThroughBall
                or PlayerIntent.Shoot or PlayerIntent.Trap or PlayerIntent.Tackle
                or PlayerIntent.Dive or PlayerIntent.Celebrate or PlayerIntent.Cut;
        }
        if (!Player.HasAnimation(clip)) { motionDriven = false; clip = SelectClip(p, speed, out oneShot); }
        if (!Player.HasAnimation(clip)) clip = "soccer_idle";
        if (!motionDriven && oneShot && _oneShotDone)
        {
            clip = SelectLocomotion(p, speed);
            oneShot = false;
        }
        if (clip != _current)
        {
            CaptureInertialOldPoses();
            // Locomotion clips inherit cycle phase; one-shots must begin at frame zero.
            float startPhase = motionDriven ? _motionState!.RenderPhase : oneShot ? 0f : _phase;
            Player.Play(clip, oneShot ? .08f : .12f);
            Player.Seek(startPhase * Player.GetAnimation(clip).Length, true);
            _current = clip;
            _oneShotDone = false;
            _blend = 0f;
            CaptureInertialTransition();
        }
        _blend = Mathf.Min(_blend + dt / .18f, 1f);
        if (oneShot && !Player.IsPlaying()) _oneShotDone = true;

        if (oneShot)
        {
            float scale = 1f;
            // Align ball actions to their contact frame. Other one-shots, such as
            // slide tackles, should still finish inside the engine action window.
            if (_clipDuration.TryGetValue(clip, out float clipDur)
                && clipDur > 0f && p.ActionDuration > 0.01f)
            {
                if (_contactFrac.TryGetValue(clip, out float frac) && frac > 0f
                    && p.ActionContactAt > 0f)
                    scale = ActionTiming.ContactAlignedPlaybackScale(clipDur, frac, p.ActionContactAt);
                else
                    scale = Math.Clamp(clipDur / p.ActionDuration, 0.6f, 1.8f);
            }
            Player.SpeedScale = scale;
        }
        else
        {
            float target = 1f;
            if (NaturalRate.TryGetValue(clip, out float nat) && nat > 0.01f)
            {
                float max = MaxRate.TryGetValue(clip, out float mr) ? mr : 2.6f;
                target = Math.Clamp(speed / (nat * _styleStride * _archetypeStride), 0.55f, max);
                target *= _archetypeCadence;
            }
            _speedScale = Math.Abs(target - _speedScale) < 0.001f ? target
                : _speedScale + (target - _speedScale) * Math.Min(1f, dt * 8f);
            Player.SpeedScale = _speedScale;
        }
        float clipLen = (float)Player.GetAnimation(clip).Length;
        if (motionDriven)
        {
            // The shared engine owns normalized phase and contact timing. Seeking here
            // is presentation-only and cannot affect authoritative simulation state.
            Player.Seek(_motionState!.RenderPhase * clipLen, true);
            Player.SpeedScale = _motionState.PlaybackScale;
            _phase = _motionState.RenderPhase;
        }
        else _phase = (_phase + dt * Player.SpeedScale / clipLen) % 1f;

        UpdateLean(p, dt, speed);
        UpdateFlutter(speed, dt);
        UpdateLookAt(worldPos, yaw, hasBall ? worldPos + Vector3.Forward * .4f : Vector3.Zero);
        UpdateReach(worldPos, yaw, hasBall ? worldPos + Vector3.Forward * .4f : Vector3.Zero);
        UpdateInertialization(dt);
        UpdateFootIk(worldPos, yaw);
        StoreInertialPrevPoses(dt);
        _prevFacing = Mx.Norm(Mx.Flat(p.Facing));
        if (_prevFacing.LengthSquared() < 0.001f) _prevFacing = new System.Numerics.Vector3(0, 0, 1);
    }

    /// <summary>Actions with a clip authored for exactly that action (Sprite Forge
    /// field-sport pack): play it rather than the motion engine's nearest match in
    /// the broad category (every skill move used to come out as a generic cut, a
    /// header as a trap).</summary>
    private static bool Dedicated(string action)
        => action.StartsWith("skill_") || action is "chip_shot" or "trivela" or "bicycle" or "thigh_control"
           or "chest_control" or "header" or "volley" or "punch" or "headbutt" or "keeper_penalty_set";

    private string SelectClip(PlayerState p, float speed, out bool oneShot)
    {
        oneShot = false;
        if (p.ActionTimer > 0f && _aliases.TryGetValue(p.Action, out var aliased))
        {
            oneShot = true;
            return aliased;
        }
        if (p.Dribbling && speed > 0.8f) return "soccer_dribble";
        if (p.Shielding && speed < 2f) return "soccer_shield";
        return SelectLocomotion(p, speed);
    }

    /// <summary>Blend-space locomotion selection (Phase 1.1): speed x
    /// turnRate x ballState -> clip.  Directional clips (strafe/backpedal)
    /// are chosen when the velocity heading differs from facing.</summary>
    public string SelectLocomotion(PlayerState p, float speed)
    {
        // Phase 0.4: sharp turns at speed select the turn clip by turn rate.
        _turnCooldown = Math.Max(0f, _turnCooldown - 1f / 60f);
        if (speed > 1.2f && _turnCooldown <= 0f)
        {
            var fwd = Mx.Norm(Mx.Flat(p.Facing));
            if (fwd.LengthSquared() > 0.001f)
            {
                float dot = Math.Clamp(_prevFacing.X * fwd.X + _prevFacing.Z * fwd.Z, -1f, 1f);
                float turnRate = (float)Math.Acos(dot) * 60f;
                if (turnRate > 2.2f)
                {
                    _turnCooldown = 0.6f;
                    return "soccer_turn";
                }
            }
        }
        // Directional: heading offset from velocity vs facing (Phase 1.4).
        var vel = Mx.Flat(p.Vel);
        var facing = Mx.Norm(Mx.Flat(p.Facing));
        if (vel.Length() > 0.4f && facing.LengthSquared() > 0.001f && !p.Dribbling)
        {
            var vh = Mx.Norm(vel);
            float headingOff = (float)Math.Atan2(vh.X * facing.Z - vh.Z * facing.X,
                                                 vh.X * facing.X + vh.Z * facing.Z);
            float a = Math.Abs(headingOff);
            if (a > 2.6f) return "soccer_backpedal";
            if (a > 0.5f) return headingOff > 0f ? "soccer_strafe_l" : "soccer_strafe_r";
        }
        // Hysteresis bands.
        string cur = _current;
        if (cur == "soccer_walk" && speed < 2f) return "soccer_walk";
        if (cur == "soccer_jog" && speed >= 1.4f && speed < 3.3f) return "soccer_jog";
        if (cur == "soccer_run" && speed >= 2.6f && speed < 4.8f) return "soccer_run";
        if (cur == "soccer_sprint" && speed >= 4f) return "soccer_sprint";
        if (speed < 0.5f) return p.IsKeeper ? "soccer_keeper_ready" : "soccer_idle_ready";
        if (speed < 1.7f) return "soccer_walk";
        if (speed < 2.9f) return "soccer_jog";
        if (speed < 4.3f) return "soccer_run";
        return "soccer_sprint";
    }

    /// <summary>Directional clip selection (Phase 1.4): given the velocity
    /// heading relative to facing, pick the matching locomotion clip.</summary>
    public string SelectDirectionalClip(float speed, float headingOffset, bool hasBall)
    {
        float a = Mathf.Abs(Mathf.AngleDifference(headingOffset, 0f));
        if (hasBall) return SelectLocomotion(new PlayerState(), speed);
        if (a < .5f) return SelectLocomotion(new PlayerState(), speed);
        if (a > 2.6f) return "soccer_backpedal";
        if (headingOffset > 0f) return "soccer_strafe_l";
        return "soccer_strafe_r";
    }

    private void UpdateLean(PlayerState p, float dt, float speed)
    {
        if (_sceneRoot == null || dt <= 0f) return;
        System.Numerics.Vector3 vel = Mx.Flat(p.Vel);
        System.Numerics.Vector3 accel = (vel - _prevVel) / dt;
        _prevVel = vel;
        System.Numerics.Vector3 fwd = Mx.Norm(Mx.Flat(p.Facing));
        if (fwd.LengthSquared() < 0.001f) fwd = new System.Numerics.Vector3(0, 0, 1);
        System.Numerics.Vector3 right = new System.Numerics.Vector3(fwd.Z, 0, -fwd.X);
        float fwdAccel = accel.X * fwd.X + accel.Z * fwd.Z;
        float latAccel = accel.X * right.X + accel.Z * right.Z;
        float leanT = Math.Clamp((0.02f + speed * 0.012f + fwdAccel * 0.015f) * _styleLean, 0f, 0.35f)
                      + _archetypeLean * .5f;
        float rollT = Math.Clamp(-latAccel * 0.02f, -0.22f, 0.22f) + _archetypeRoll * .3f;
        float k = Math.Min(1f, dt * 6f);
        _lean += (leanT - _lean) * k;
        _roll += (rollT - _roll) * k;
        _sceneRoot.Rotation = new Vector3(_lean, 0, _roll);
    }


    // ---- Hypermotion-style inertialization (velocity-aware) -------------

    private static readonly string[] InertialBoneNames =
    {
        "Hips", "spine_01", "spine_02", "neck_01", "head",
        "upperarm_L", "lowerarm_L", "upperarm_R", "lowerarm_R"
    };

    private void CaptureInertialOldPoses()
    {
        _prevBonePoses.Clear();
        if (Skel == null) return;
        foreach (var name in InertialBoneNames)
        {
            int b = FindBoneLoose(Skel, name);
            if (b >= 0) _prevBonePoses[b] = Skel.GetBoneGlobalPose(b);
        }
    }

    private void CaptureInertialTransition()
    {
        if (Skel == null || _prevBonePoses.Count == 0) return;
        _inertialBones.Clear();
        _inertialActive = true;
        _inertialTime = 0f;
        float dt = Mathf.Max(0.0001f, _inertialPrevDt);
        foreach (var kv in _prevBonePoses)
        {
            int b = kv.Key;
            var oldTx = kv.Value;
            var newTx = Skel.GetBoneGlobalPose(b);
            Vector3 posOff = oldTx.Origin - newTx.Origin;
            if (posOff.Length() > .12f) posOff = posOff.Normalized() * .12f;
            Quaternion oldRot = oldTx.Basis.GetRotationQuaternion();
            Quaternion newRot = newTx.Basis.GetRotationQuaternion();
            Quaternion rotOff = (oldRot * newRot.Inverse()).Normalized();

            // Velocity-aware capture: estimate old bone velocity from previous frame.
            Vector3 posVel = Vector3.Zero;
            Vector3 angVel = Vector3.Zero;
            if (_inertialPrevFramePoses.TryGetValue(b, out var prevTx))
            {
                posVel = (oldTx.Origin - prevTx.Origin) / dt;
                Quaternion prevRot = prevTx.Basis.GetRotationQuaternion();
                Quaternion dq = (oldRot * prevRot.Inverse()).Normalized();
                dq.GetAxisAngle(out Vector3 axis, out float angle);
                if (angle > Mathf.Pi) angle -= Mathf.Tau;
                angVel = axis * (angle / dt);
                if (angVel.Length() > 12f) angVel = angVel.Normalized() * 12f;
            }

            _inertialBones.Add((b, posOff, rotOff, posVel, angVel, 0.18f));
        }
    }

    private void UpdateInertialization(float dt)
    {
        if (!_inertialActive || Skel == null) return;
        _inertialTime += dt;
        bool any = false;
        for (int i = 0; i < _inertialBones.Count; i++)
        {
            var ib = _inertialBones[i];
            float lambda = 0.69314718056f / Mathf.Max(0.001f, ib.halfLife);
            float decay = Mathf.Exp(-lambda * dt);
            // Velocity-aware integration then decay (Hypermotion-style continuity).
            ib.posOff += ib.posVel * dt;
            ib.posVel *= decay;
            ib.posOff *= decay;
            if (ib.posOff.Length() > .12f) ib.posOff = ib.posOff.Normalized() * .12f;

            float angLen = ib.angVel.Length();
            if (angLen > 1e-6f)
            {
                Quaternion dq = new Quaternion(ib.angVel / angLen, angLen * dt);
                ib.rotOff = (dq * ib.rotOff).Normalized();
            }
            ib.rotOff = ib.rotOff.Slerp(Quaternion.Identity, 1f - decay).Normalized();
            ib.angVel *= decay;
            _inertialBones[i] = ib;

            if (ib.posOff.Length() > 0.0008f || ib.posVel.Length() > 0.001f || ib.angVel.Length() > 0.01f || Mathf.Abs(ib.rotOff.W) < 0.9995f)
            {
                any = true;
                var cur = Skel.GetBoneGlobalPose(ib.bone);
                Quaternion finalRot = (ib.rotOff * cur.Basis.GetRotationQuaternion()).Normalized();
                Vector3 finalPos = cur.Origin + ib.posOff;
                Skel.SetBoneGlobalPoseOverride(ib.bone, new Transform3D(new Basis(finalRot), finalPos), 1f, true);
            }
        }
        float energy = 0f;
        for (int i = 0; i < _inertialBones.Count; i++) energy += _inertialBones[i].posOff.LengthSquared() + _inertialBones[i].rotOff.GetAngle() * 0.1f;
        _lastInertialEnergy = energy;
        if (!any || _inertialTime > 0.18f * 7f)
        {
            _inertialActive = false;
            foreach (var ib in _inertialBones)
                Skel.ClearBoneGlobalPoseOverride(ib.bone);
            _inertialBones.Clear();
            _lastInertialEnergy = 0f;
        }
    }

    private void StoreInertialPrevPoses(float dt)
    {
        if (Skel == null) return;
        _inertialPrevDt = Mathf.Max(0.0001f, dt);
        _inertialPrevFramePoses.Clear();
        foreach (var name in InertialBoneNames)
        {
            int b = FindBoneLoose(Skel, name);
            if (b >= 0) _inertialPrevFramePoses[b] = Skel.GetBoneGlobalPose(b);
        }
    }

    // ---- Phase 1.2 foot-planting IK -------------------------------------

    private void CacheBones()
    {
        if (Skel == null) return;
        _bones.Clear();
        foreach (var side in new[] { "L", "R" })
        {
            var b = new BoneData
            {
                Thigh = Skel.FindBone("thigh_" + side),
                Shin = Skel.FindBone("shin_" + side),
                Foot = Skel.FindBone("foot_" + side),
            };
            if (b.Thigh < 0 || b.Shin < 0 || b.Foot < 0) continue;
            b.ThighRest = Skel.GetBoneRest(b.Thigh).Origin;
            b.ShinRest = Skel.GetBoneRest(b.Shin).Origin;
            b.FootRest = Skel.GetBoneRest(b.Foot).Origin;
            _bones[side] = b;
        }
        var spine = Skel.FindBone("spine_02");
        var neck = Skel.FindBone("neck_01");
        var head = Skel.FindBone("head");
        var uaL = Skel.FindBone("upperarm_L");
        var laL = Skel.FindBone("lowerarm_L");
        var uaR = Skel.FindBone("upperarm_R");
        var laR = Skel.FindBone("lowerarm_R");
        if (spine >= 0 && neck >= 0 && head >= 0)
        {
            var b = _bones.TryGetValue("L", out var bl) ? bl : new BoneData();
            b.Spine = spine; b.Neck = neck; b.Head = head;
            b.SpineRest = Skel.GetBoneRest(spine).Origin;
            b.NeckRest = Skel.GetBoneRest(neck).Origin;
            b.HeadRest = Skel.GetBoneRest(head).Origin;
            if (uaL >= 0 && laL >= 0)
            {
                b.UpperArmL = uaL; b.LowerArmL = laL;
                b.UpperArmRestL = Skel.GetBoneRest(uaL).Origin;
                b.LowerArmRestL = Skel.GetBoneRest(laL).Origin;
            }
            if (uaR >= 0 && laR >= 0)
            {
                b.UpperArmR = uaR; b.LowerArmR = laR;
                b.UpperArmRestR = Skel.GetBoneRest(uaR).Origin;
                b.LowerArmRestR = Skel.GetBoneRest(laR).Origin;
            }
            _bones["L"] = b;
        }
    }

    private void UpdateFootIk(Vector3 worldPos, float yaw)
    {
        if (Skel == null || _bones.Count == 0) return;
        bool leftPlanted = _motionState?.FootPlantedLeft ?? false;
        bool rightPlanted = _motionState?.FootPlantedRight ?? false;
        _lastIkCorrectionL = 0f; _lastIkCorrectionR = 0f;

        foreach (var side in new[] { "L", "R" })
        {
            if (!_bones.TryGetValue(side, out var b)) continue;
            bool isLeft = side == "L";
            var footGlobal = Skel.GetBoneGlobalPose(b.Foot).Origin;
            float height = footGlobal.Y - worldPos.Y;
            bool planted = (isLeft ? leftPlanted : rightPlanted) || height < .10f;

            var ground = SampleGround(worldPos, footGlobal);
            if (isLeft) _groundNormalL = ground.normal; else _groundNormalR = ground.normal;
            float groundY = ground.hit ? ground.y : worldPos.Y;
            Vector3 target = new Vector3(footGlobal.X, groundY + 0.012f, footGlobal.Z);

            if (planted)
            {
                ref bool hasPrev = ref (isLeft ? ref _hasPrevFootL : ref _hasPrevFootR);
                ref Vector3 prev = ref (isLeft ? ref _prevFootWorldL : ref _prevFootWorldR);
                if (hasPrev)
                {
                    Vector3 locked = new Vector3(prev.X, groundY + 0.012f, prev.Z);
                    float lockW = Mathf.Clamp(1f - height / 0.18f, 0.25f, 0.85f);
                    target = target.Lerp(locked, lockW);
                }
                if (height < .22f)
                {
                    Vector3 before = Skel.GetBoneGlobalPose(b.Foot).Origin;
                    SolveTwoBone(b, target, worldPos, yaw);
                    Vector3 after = Skel.GetBoneGlobalPose(b.Foot).Origin;
                    float corr = before.DistanceTo(after);
                    if (isLeft) _lastIkCorrectionL = corr; else _lastIkCorrectionR = corr;
                }
                ApplyFootGroundOrientation(b, ground.normal, yaw);
                prev = Skel.GetBoneGlobalPose(b.Foot).Origin;
                prev.Y = groundY + 0.012f;
                hasPrev = true;
            }
            else
            {
                if (isLeft) _hasPrevFootL = false; else _hasPrevFootR = false;
                if (height < .18f)
                {
                    Vector3 before = Skel.GetBoneGlobalPose(b.Foot).Origin;
                    SolveTwoBone(b, target, worldPos, yaw);
                    Vector3 after = Skel.GetBoneGlobalPose(b.Foot).Origin;
                    float corr = before.DistanceTo(after);
                    if (isLeft) _lastIkCorrectionL = corr; else _lastIkCorrectionR = corr;
                    ApplyFootGroundOrientation(b, ground.normal, yaw);
                }
            }
        }
        ApplyPelvisStabilization(worldPos, leftPlanted, rightPlanted);
        UpdateDebugOverlay();
        ApplyLookAndReach();
    }

    private (bool hit, float y, Vector3 normal) SampleGround(Vector3 worldPos, Vector3 footWorld)
    {
        // Default to pitch plane at the player's current base.
        Vector3 normal = Vector3.Up;
        float y = worldPos.Y;
        bool hit = false;
        try
        {
            var space = Skel?.GetWorld3D()?.DirectSpaceState;
            if (space != null)
            {
                var from = new Vector3(footWorld.X, footWorld.Y + 0.6f, footWorld.Z);
                var to = new Vector3(footWorld.X, footWorld.Y - 0.8f, footWorld.Z);
                var q = PhysicsRayQueryParameters3D.Create(from, to);
                q.CollideWithAreas = false;
                q.CollideWithBodies = true;
                var res = space.IntersectRay(q);
                if (res.Count > 0 && res.ContainsKey("position"))
                {
                    var pos = (Vector3)res["position"];
                    var n = res.ContainsKey("normal") ? (Vector3)res["normal"] : Vector3.Up;
                    if (n.LengthSquared() > 1e-6f) normal = n.Normalized();
                    y = pos.Y;
                    hit = true;
                }
            }
        }
        catch { /* headless / no physics: plane fallback */ }
        return (hit, y, normal);
    }

    private void ApplyFootGroundOrientation(BoneData b, Vector3 groundNormal, float yaw)
    {
        if (Skel == null) return;
        if (groundNormal.LengthSquared() < 1e-6f) groundNormal = Vector3.Up;
        groundNormal = groundNormal.Normalized();
        // Only apply when ground is reasonably level to avoid extreme ankle poses.
        if (groundNormal.Dot(Vector3.Up) < 0.65f) return;
        var footTx = Skel.GetBoneGlobalPose(b.Foot);
        Vector3 fwd = new Vector3(Mathf.Sin(yaw), 0f, Mathf.Cos(yaw));
        // Project forward onto ground plane.
        fwd = (fwd - groundNormal * fwd.Dot(groundNormal));
        if (fwd.LengthSquared() < 1e-6f) fwd = footTx.Basis.Z;
        fwd = fwd.Normalized();
        Vector3 right = fwd.Cross(groundNormal);
        if (right.LengthSquared() < 1e-6f) return;
        right = right.Normalized();
        Vector3 up = right.Cross(fwd).Normalized();
        var basis = new Basis(right, up, fwd).Orthonormalized();
        // Blend gently toward ground-aligned orientation.
        footTx.Basis = footTx.Basis.Slerp(basis, 0.35f).Orthonormalized();
        Skel.SetBoneGlobalPoseOverride(b.Foot, footTx, 1f, true);
    }

    private void UpdateDebugOverlay()
    {
        if (!_debugOverlayEnabled) return;
        try
        {
            if (_debugLabel == null || !IsInstanceValid(_debugLabel))
            {
                var canvas = new CanvasLayer { Name = "HypermotionDebugCanvas", Layer = 100 };
                AddChild(canvas);
                _debugLabel = new Label
                {
                    Name = "HypermotionDebugLabel",
                    Position = new Vector2(12, 12),
                    Modulate = new Color(1, 1, 0.6f, 0.95f),
                };
                _debugLabel.AddThemeFontSizeOverride("font_size", 14);
                canvas.AddChild(_debugLabel);
            }
            float approach = _motionState?.ApproachWeight ?? 0f;
            float ttc = _motionState?.TimeToBallContact ?? -1f;
            bool lp = _motionState?.FootPlantedLeft ?? false;
            bool rp = _motionState?.FootPlantedRight ?? false;
            float pwL = _motionState?.PlantWeightLeft ?? 0f;
            float pwR = _motionState?.PlantWeightRight ?? 0f;
            float rvx = _motionState?.RootVelocitySampleX ?? 0f;
            float rvz = _motionState?.RootVelocitySampleZ ?? 0f;
            bool cw = _motionState?.InContactWindow ?? false;
            _debugLabel.Text =
                $"AME dbg\napproach={approach:F2} ttc={ttc:F2} contactWin={cw}\n" +
                $"plant L={lp}({pwL:F2}) R={rp}({pwR:F2})\n" +
                $"rv=({rvx:F2},{rvz:F2})\n" +
                $"ikCorr L={_lastIkCorrectionL:F3} R={_lastIkCorrectionR:F3}\n" +
                $"inertial={(_inertialActive ? _inertialTime : 0f):F2} E={_lastInertialEnergy:F3}";
        }
        catch { /* debug overlay is non-fatal */ }
    }

    private void ApplyPelvisStabilization(Vector3 worldPos, bool leftPlanted, bool rightPlanted)
    {
        if (Skel == null) return;
        int pelvisIdx = Skel.FindBone("Hips");
        if (pelvisIdx < 0) return;
        var pelvisTx = Skel.GetBoneGlobalPose(pelvisIdx);
        Vector3 pelvis = pelvisTx.Origin;

        // Soft midpoint pull when both feet planted.
        if (leftPlanted && rightPlanted && _hasPrevFootL && _hasPrevFootR)
        {
            Vector3 mid = (_prevFootWorldL + _prevFootWorldR) * 0.5f;
            mid.Y = pelvis.Y;
            Vector3 err = mid - pelvis; err.Y = 0;
            if (err.Length() > 0.06f) err = err.Normalized() * 0.06f;
            pelvis += err * 0.35f;
        }

        // Lateral weight shift toward the more planted foot.
        float diff = (leftPlanted ? 1f : 0f) - (rightPlanted ? 1f : 0f);
        if (Mathf.Abs(diff) > 0.1f && _hasPrevFootL && _hasPrevFootR)
        {
            Vector3 lat = _prevFootWorldL - _prevFootWorldR; lat.Y = 0;
            if (lat.LengthSquared() > 1e-6f)
            {
                lat = lat.Normalized();
                pelvis += lat * (diff * 0.025f);
            }
        }

        // Soft vertical clamp to keep pelvis grounded.
        float avgFootY = ((_hasPrevFootL ? _prevFootWorldL.Y : worldPos.Y) + (_hasPrevFootR ? _prevFootWorldR.Y : worldPos.Y)) * 0.5f;
        float targetY = avgFootY + _height * 0.52f;
        float yErr = Mathf.Clamp(targetY - pelvis.Y, -0.04f, 0.04f);
        pelvis.Y += yErr * 0.25f;

        pelvisTx.Origin = pelvis;
        Skel.SetBoneGlobalPoseOverride(pelvisIdx, pelvisTx, 1f, true);
        _prevPelvisPos = pelvis;
        _hasPrevPelvisPos = true;
    }


    private void ApplyLookAndReach()
    {
        if (!_bones.TryGetValue("L", out var b)) return;
        if (b.Neck >= 0 && b.Head >= 0)
        {
            var neckQ = new Quaternion(Vector3.Up, _lookYaw) *
                        new Quaternion(Vector3.Right, _lookPitch);
            Skel.SetBonePoseRotation(b.Neck, neckQ);
            var headQ = new Quaternion(Vector3.Up, _lookYaw * .5f) *
                        new Quaternion(Vector3.Right, _lookPitch * .5f);
            Skel.SetBonePoseRotation(b.Head, headQ);
        }
        if (_reach > .01f)
        {
            var armQ = new Quaternion(Vector3.Right, -_reach * 1.1f);
            if (b.UpperArmR >= 0) Skel.SetBonePoseRotation(b.UpperArmR, armQ);
            if (b.LowerArmR >= 0)
                Skel.SetBonePoseRotation(b.LowerArmR,
                    new Quaternion(Vector3.Right, -_reach * .4f));
        }
    }

    private static T? FindFirst<T>(Node root) where T : Node
    {
        if (root is T t) return t;
        foreach (var c in root.GetChildren())
        {
            var found = FindFirst<T>(c);
            if (found != null) return found;
        }
        return null;
    }
}
