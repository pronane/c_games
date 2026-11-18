// Arena FC - Sprite Forge soccer player (sculpted mesh + 18-bone skeleton + 67 clips).
//
// Tools/build_soccer_player.py builds Data/models/soccer_player.glb from the
// latest Sprite Forge pipeline (sforge.footballer + sforge.gamemesh, retargeted
// soccer clips) plus Data/soccer_player_manifest.json (clip list, loop flags,
// action aliases, material order).  This loader plays those clips from the
// match engine's PlayerState, tinting the flat kit materials per CharacterSpec
// exactly like the procedural rig.  When the GLB is absent the game falls back
// to the procedural CharacterRig untouched.
using System;
using System.Collections.Generic;
using System.Text.Json;
using ArenaFC.Core;
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

    private readonly Dictionary<string, string> _aliases = new();
    private readonly HashSet<string> _loops = new();
    private readonly List<string> _materialOrder = new();
    private float _height = 1.77f;
    private string _current = "";
    private bool _oneShotDone = true;

    // Fallback aliases if the manifest is missing (mirrors soccer_player_manifest.json).
    private static readonly Dictionary<string, string> FallbackAliases = new()
    {
        ["idle"] = "soccer_idle", ["run"] = "soccer_run", ["kick"] = "soccer_kick_place",
        ["tackle"] = "soccer_tackle", ["slide"] = "soccer_slide_tackle", ["dive"] = "soccer_keeper_dive_left",
        ["catch"] = "soccer_keeper_catch", ["foul"] = "soccer_foul", ["celebrate"] = "soccer_celebrate",
    };

    public bool Load(CharacterSpec spec)
    {
        LoadManifest();
        var doc = new GltfDocument();
        var state = new GltfState();
        if (doc.AppendFromFile(GlbPath, state) != Error.Ok) return false;
        var scene = doc.GenerateScene(state) as Node3D;
        if (scene == null) return false;
        AddChild(scene);
        Player = FindFirst<AnimationPlayer>(scene);
        Skel = FindFirst<Skeleton3D>(scene);
        Mesh = FindFirst<MeshInstance3D>(scene);
        if (Player == null || Skel == null || Mesh == null) return false;
        foreach (var name in Player.GetAnimationList())
        {
            var anim = Player.GetAnimation(name);
            if (anim != null)
                anim.LoopMode = _loops.Contains(name.ToString())
                    ? Animation.LoopModeEnum.Linear : Animation.LoopModeEnum.None;
        }
        Tint(spec);
        float s = _height > 0.01f ? spec.Height / _height : 1f;
        Scale = new Vector3(s, s, s);
        return true;
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
                    if (c.TryGetProperty("loop", out var loop) && loop.GetBoolean()
                        && c.TryGetProperty("name", out var nm)) _loops.Add(nm.GetString() ?? "");
            if (root.TryGetProperty("materials", out var mats))
            {
                _materialOrder.Clear();
                foreach (var m in mats.EnumerateArray()) _materialOrder.Add(m.GetString() ?? "");
            }
            if (root.TryGetProperty("stats", out var stats) && stats.TryGetProperty("height_m", out var h))
                _height = h.GetSingle();
        }
        catch (Exception) { /* fallback aliases above still cover the core actions */ }
    }

    /// <summary>Retint the GLB kit materials from the character spec (per club).</summary>
    public void Tint(CharacterSpec spec)
    {
        if (Mesh?.Mesh == null) return;
        for (int i = 0; i < Mesh.Mesh.GetSurfaceCount(); i++)
        {
            string layer = i < _materialOrder.Count ? _materialOrder[i] : "";
            string hex = layer switch
            {
                "skin" => spec.SkinHex,
                "jersey" => spec.KitPrimary,
                "shorts" => spec.ShortsColor,
                "socks" => spec.SocksColor,
                "boots" => spec.BootsColor,
                "hair" => spec.HairColor,
                _ => "#888888",
            };
            var src = Mesh.GetSurfaceOverrideMaterial(i) ?? Mesh.Mesh.SurfaceGetMaterial(i);
            if (src is not StandardMaterial3D std) continue;
            var mat = (StandardMaterial3D)std.Duplicate();
            mat.AlbedoColor = CharacterRig.C(hex);
            mat.Roughness = layer is "boots" or "hair" ? .34f : .68f;
            mat.MetallicSpecular = .38f;
            mat.RimEnabled = layer is "skin" or "jersey" or "shorts" or "socks";
            mat.Rim = .22f;
            mat.RimTint = .30f;
            mat.CullMode = BaseMaterial3D.CullModeEnum.Disabled;
            Mesh.SetSurfaceOverrideMaterial(i, mat);
        }
    }

    /// <summary>Drive the clip player from one match-engine player state.</summary>
    public void Update(PlayerState p, float dt)
    {
        if (Player == null) return;
        string clip = SelectClip(p, out bool oneShot);
        if (!Player.HasAnimation(clip)) clip = "soccer_idle";
        if (clip != _current || (oneShot && _oneShotDone))
        {
            Player.Play(clip);
            _current = clip;
            _oneShotDone = false;
        }
        if (oneShot && !Player.IsPlaying()) _oneShotDone = true;
        if (!oneShot)
        {
            float speed = Mx.Flat(p.Vel).Length();
            Player.SpeedScale = Math.Clamp(speed / 6f, .75f, 1.7f);
        }
        else Player.SpeedScale = 1f;
    }

    private string SelectClip(PlayerState p, out bool oneShot)
    {
        oneShot = false;
        if (p.ActionTimer > 0f && _aliases.TryGetValue(p.Action, out var aliased))
        {
            oneShot = true;
            return aliased;
        }
        if (p.Dribbling) return "soccer_dribble";
        if (p.Shielding) return "soccer_shield";
        float speed = Mx.Flat(p.Vel).Length();
        if (speed < .6f) return p.IsKeeper ? "soccer_keeper_ready" : "soccer_idle";
        if (speed < 3f) return "soccer_walk";
        if (p.Sprinting || speed > 5.5f) return "soccer_sprint";
        return "soccer_run";
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
