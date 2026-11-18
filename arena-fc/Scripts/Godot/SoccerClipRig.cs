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
    private readonly Dictionary<string, float> _clipDuration = new();
    private readonly Dictionary<string, float> _contactFrac = new();
    private readonly List<string> _materialOrder = new();
    private float _height = 1.77f;
    private string _current = "";
    private bool _oneShotDone = true;

    // FIFA-style locomotion state (see Update): smoothed cadence, lean/roll,
    // and a stable per-player style (stride +/-7%, lean variation).
    private Node3D? _sceneRoot;
    private float _speedScale = 1f;
    private float _lean, _roll;
    private float _styleStride = 1f, _styleLean = 1f;
    private System.Numerics.Vector3 _prevVel = System.Numerics.Vector3.Zero;
    // Phase 0.4 turn detection: previous facing + cooldown so cuts play once.
    private System.Numerics.Vector3 _prevFacing = new(0, 0, 1);
    private float _turnCooldown;

    // Foot travel per 1 s clip cycle, measured from the GLB (metres).  At
    // SpeedScale 1.0 the feet move at this rate, so SpeedScale =
    // ground speed / natural rate keeps foot speed ~= ground speed.
    private static readonly Dictionary<string, float> NaturalRate = new()
    {
        ["soccer_walk"] = 0.74f, ["soccer_jog"] = 1.01f, ["soccer_run"] = 1.01f,
        ["soccer_sprint"] = 1.22f, ["soccer_dribble"] = 0.60f,
        ["soccer_run_ball"] = 0.98f, ["soccer_shield"] = 0.30f,
    };

    // Cadence caps (cycles/sec): real sprint cadence is ~2.4; above that the
    // legs blur.  High-speed slide remains (clip strides are short) but the
    // treadmill effect at walk/jog/run speeds is gone.
    private static readonly Dictionary<string, float> MaxRate = new()
    {
        ["soccer_walk"] = 2.2f, ["soccer_jog"] = 2.6f, ["soccer_run"] = 2.6f,
        ["soccer_sprint"] = 2.8f, ["soccer_dribble"] = 1.8f,
        ["soccer_run_ball"] = 2.6f, ["soccer_shield"] = 1.2f,
    };

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
        _sceneRoot = scene;
        // Stable per-player style (stride +/-7%, lean variation), seeded from
        // the spec so a player looks the same every match.
        int h = 17;
        foreach (char c in (spec.DisplayName ?? "") + (int)spec.Role + spec.Pace.ToString("F2")) h = h * 31 + c;
        _styleStride = 0.93f + (Math.Abs(h) % 100) / 100f * 0.14f;
        _styleLean = 0.8f + (Math.Abs(h / 7) % 100) / 100f * 0.4f;
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

    /// <summary>Drive the clip player from one match-engine player state.
    /// FIFA-style locomotion: cadence is matched to ground speed per clip
    /// (foot speed ~= ground speed, no treadmill sliding), bands have
    /// hysteresis, one-shots play once, and the body leans with speed,
    /// acceleration and turns.  Phase 0.1: one-shot clips are speed-matched
    /// so the ball_contact frame lands at the sim's contact time (the sim
    /// releases/captures the ball at ActionContactAt, which is derived from
    /// the same clip fraction).  Phase 0.4: sharp turns select the cut /
    /// turn clips by turn rate.</summary>
    public void Update(PlayerState p, float dt)
    {
        if (Player == null) return;
        float speed = Mx.Flat(p.Vel).Length();
        string clip = SelectClip(p, speed, out bool oneShot);
        if (!Player.HasAnimation(clip)) clip = "soccer_idle";
        // One-shots play once; when finished, locomotion takes over.  (The
        // old code replayed them while ActionTimer lingered, which read as
        // stutter/freeze.)
        if (oneShot && _oneShotDone)
        {
            clip = SelectLocomotion(p, speed);
            oneShot = false;
        }
        if (clip != _current)
        {
            Player.Play(clip, oneShot ? 0.08f : 0.12f);
            _current = clip;
            _oneShotDone = false;
        }
        if (oneShot && !Player.IsPlaying()) _oneShotDone = true;
        if (oneShot)
        {
            // Speed-match so contact aligns with the sim: the sim fires at
            // ActionContactAt = duration * frac, the clip hits contact at
            // clipDuration * frac, so SpeedScale = clipDuration / duration
            // puts both on the same frame.  No contact event -> natural play.
            float scale = 1f;
            if (_contactFrac.TryGetValue(clip, out float frac) && frac >= 0f
                && _clipDuration.TryGetValue(clip, out float clipDur)
                && p.ActionDuration > 0.01f)
                scale = Math.Clamp(clipDur / p.ActionDuration, 0.6f, 1.8f);
            Player.SpeedScale = scale;
        }
        else
        {
            float target = 1f;
            if (NaturalRate.TryGetValue(clip, out float nat) && nat > 0.01f)
            {
                float max = MaxRate.TryGetValue(clip, out float mr) ? mr : 2.6f;
                target = Math.Clamp(speed / (nat * _styleStride), 0.55f, max);
            }
            // Smooth cadence changes (no pops when speed changes).
            _speedScale = Math.Abs(target - _speedScale) < 0.001f ? target
                : _speedScale + (target - _speedScale) * Math.Min(1f, dt * 8f);
            Player.SpeedScale = _speedScale;
        }
        UpdateLean(p, dt, speed);
        _prevFacing = Mx.Norm(Mx.Flat(p.Facing));
        if (_prevFacing.LengthSquared() < 0.001f) _prevFacing = new System.Numerics.Vector3(0, 0, 1);
    }

    private string SelectClip(PlayerState p, float speed, out bool oneShot)
    {
        oneShot = false;
        if (p.ActionTimer > 0f && _aliases.TryGetValue(p.Action, out var aliased))
        {
            oneShot = true;
            return aliased;
        }
        // Close control only while actually moving: the dribble clip is a
        // full stride cycle, so playing it standing still looks like
        // running on the spot.
        if (p.Dribbling && speed > 0.8f) return "soccer_dribble";
        if (p.Shielding && speed < 2f) return "soccer_shield";
        return SelectLocomotion(p, speed);
    }

    private string SelectLocomotion(PlayerState p, float speed)
    {
        // Phase 0.4: sharp turns at speed select the cut / turn clips by
        // turn rate (rad/s between previous and current facing).  A 0.6 s
        // cooldown stops the cut replaying every frame of a long turn.
        _turnCooldown = Math.Max(0f, _turnCooldown - 1f / 60f);
        if (speed > 1.2f && _turnCooldown <= 0f)
        {
            var fwd = Mx.Norm(Mx.Flat(p.Facing));
            if (fwd.LengthSquared() > 0.001f)
            {
                float dot = Math.Clamp(_prevFacing.X * fwd.X + _prevFacing.Z * fwd.Z, -1f, 1f);
                float turnRate = Math.Acos(dot) * 60f; // rad/s at 60 Hz
                if (turnRate > 2.2f)
                {
                    _turnCooldown = 0.6f;
                    float cross = _prevFacing.X * fwd.Z - _prevFacing.Z * fwd.X;
                    return cross > 0f ? "soccer_turn_left" : "soccer_turn_right";
                }
            }
        }
        // Hysteresis: stay in the current band until speed clearly leaves
        // it, so hovering at a threshold doesn't flicker clips.
        string cur = _current;
        if (cur == "soccer_walk" && speed < 2f) return "soccer_walk";
        if (cur == "soccer_jog" && speed >= 1.4f && speed < 3.3f) return "soccer_jog";
        if (cur == "soccer_run" && speed >= 2.6f && speed < 4.8f) return "soccer_run";
        if (cur == "soccer_sprint" && speed >= 4f) return "soccer_sprint";
        if (speed < 0.5f) return p.IsKeeper ? "soccer_keeper_ready" : "soccer_idle";
        if (speed < 1.7f) return "soccer_walk";
        if (speed < 2.9f) return "soccer_jog";
        if (speed < 4.3f) return "soccer_run";
        return "soccer_sprint";
    }

    /// <summary>Forward lean grows with speed and acceleration; roll into
    /// turns (lateral acceleration).  Applied to the imported scene root so
    /// it pivots at the feet.</summary>
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
        float leanT = Math.Clamp((0.02f + speed * 0.012f + fwdAccel * 0.015f) * _styleLean, 0f, 0.35f);
        float rollT = Math.Clamp(-latAccel * 0.02f, -0.22f, 0.22f);
        float k = Math.Min(1f, dt * 6f);
        _lean += (leanT - _lean) * k;
        _roll += (rollT - _roll) * k;
        _sceneRoot.Rotation = new Vector3(_lean, 0, _roll);
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
