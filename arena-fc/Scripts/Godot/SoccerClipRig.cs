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
        ["catch"] = "soccer_keeper_catch", ["foul"] = "soccer_foul", ["celebrate"] = "soccer_celebrate",
    };

    public bool Load(CharacterSpec spec)
    {
        LoadManifest();
        GD.Print($"[SoccerClipRig] Loading GLB from {GlbPath}, exists={Godot.FileAccess.FileExists(GlbPath)}");
        var doc = new GltfDocument();
        var state = new GltfState();
        var err = doc.AppendFromFile(GlbPath, state);
        if (err != Error.Ok)
        {
            GD.PrintErr($"[SoccerClipRig] AppendFromFile failed: {err}");
            return false;
        }
        var scene = doc.GenerateScene(state) as Node3D;
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
        Mesh = FindFirst<MeshInstance3D>(scene);
        if (Player == null || Skel == null || Mesh == null)
        {
            GD.PrintErr($"[SoccerClipRig] Missing nodes: Player={Player != null}, Skel={Skel != null}, Mesh={Mesh != null}");
            return false;
        }
        GD.Print($"[SoccerClipRig] GLB loaded OK: {Player.GetAnimationList().Count} animations");
        foreach (var name in Player.GetAnimationList())
        {
            var anim = Player.GetAnimation(name);
            if (anim != null)
                anim.LoopMode = _loops.Contains(name.ToString())
                    ? Animation.LoopModeEnum.Linear : Animation.LoopModeEnum.None;
        }
        Tint(spec);
        SetArchetype(spec.Archetype);
        float s = _height > 0.01f ? spec.Height / _height : 1f;
        Scale = new Vector3(s, s, s);
        CacheBones();
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
        if (!Player.HasAnimation(clip)) clip = "soccer_idle";
        if (oneShot && _oneShotDone)
        {
            clip = SelectLocomotion(p, speed);
            oneShot = false;
        }
        if (clip != _current)
        {
            // 1.6 phase sync: start the new clip at the matching cycle phase.
            float startPhase = _phase;
            Player.Play(clip, oneShot ? .08f : .12f);
            Player.Seek(startPhase * Player.GetAnimation(clip).Length, true);
            _current = clip;
            _oneShotDone = false;
            _blend = 0f;
        }
        _blend = Mathf.Min(_blend + dt / .18f, 1f);
        if (oneShot && !Player.IsPlaying()) _oneShotDone = true;

        if (oneShot)
        {
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
                target = Math.Clamp(speed / (nat * _styleStride * _archetypeStride), 0.55f, max);
                target *= _archetypeCadence;
            }
            _speedScale = Math.Abs(target - _speedScale) < 0.001f ? target
                : _speedScale + (target - _speedScale) * Math.Min(1f, dt * 8f);
            Player.SpeedScale = _speedScale;
        }
        float clipLen = (float)Player.GetAnimation(clip).Length;
        _phase = (_phase + dt * Player.SpeedScale / clipLen) % 1f;

        UpdateLean(p, dt, speed);
        UpdateLookAt(worldPos, yaw, hasBall ? worldPos + Vector3.Forward * .4f : Vector3.Zero);
        UpdateReach(worldPos, yaw, hasBall ? worldPos + Vector3.Forward * .4f : Vector3.Zero);
        UpdateFootIk(worldPos, yaw);
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
        if (speed < 0.5f) return p.IsKeeper ? "soccer_keeper_ready" : "soccer_idle";
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
        foreach (var side in new[] { "L", "R" })
        {
            if (!_bones.TryGetValue(side, out var b)) continue;
            var footGlobal = Skel.GetBoneGlobalPose(b.Foot).Origin;
            var target = new Vector3(footGlobal.X, worldPos.Y, footGlobal.Z);
            float height = footGlobal.Y - worldPos.Y;
            if (height < .18f)
                SolveTwoBone(b, target, worldPos, yaw);
        }
        ApplyLookAndReach();
    }

    private void SolveTwoBone(BoneData b, Vector3 targetWorld, Vector3 rootWorld, float yaw)
    {
        var hip = Skel.GetBoneGlobalPose(b.Thigh).Origin;
        float l1 = b.ThighRest.Length();
        float l2 = b.ShinRest.Length();
        var toTarget = targetWorld - hip;
        float dist = Mathf.Clamp(toTarget.Length(), .01f, l1 + l2 - .001f);
        var dir = toTarget.Normalized();
        float cosA = (l1 * l1 + dist * dist - l2 * l2) / (2f * l1 * dist);
        float angA = Mathf.Acos(Mathf.Clamp(cosA, -1f, 1f));
        var fwd = new Vector3(-Mathf.Sin(yaw), 0f, -Mathf.Cos(yaw));
        var axis = dir.Cross(fwd);
        if (axis.LengthSquared() < 1e-6f) axis = Vector3.Up;
        axis = axis.Normalized();
        var kneeDir = dir.Rotated(axis, angA);
        var knee = hip + kneeDir * l1;
        var thighQuat = ShortestArc(b.ThighRest.Normalized(), kneeDir);
        var shinDir = (targetWorld - knee).Normalized();
        var shinQuat = ShortestArc(b.ShinRest.Normalized(), shinDir);
        Skel.SetBonePoseRotation(b.Thigh, thighQuat);
        Skel.SetBonePoseRotation(b.Shin, shinQuat);
    }

    private static Quaternion ShortestArc(Vector3 from, Vector3 to)
    {
        from = from.Normalized(); to = to.Normalized();
        float dot = Mathf.Clamp(from.Dot(to), -1f, 1f);
        if (dot > .999999f) return Quaternion.Identity;
        if (dot < -.999999f)
        {
            var axis = from.Cross(Vector3.Up);
            if (axis.LengthSquared() < 1e-6f) axis = from.Cross(Vector3.Right);
            return new Quaternion(axis.Normalized(), Mathf.Pi);
        }
        var axis2 = from.Cross(to).Normalized();
        float angle = Mathf.Acos(dot);
        return new Quaternion(axis2, angle);
    }

    // ---- Phase 1.5 look-at + reach --------------------------------------

    private void UpdateLookAt(Vector3 worldPos, float yaw, Vector3 ballWorld)
    {
        if (ballWorld == Vector3.Zero || Skel == null) { _lookYaw = 0f; _lookPitch = 0f; return; }
        var toBall = ballWorld - (worldPos + Vector3.Up * 1.6f);
        float dist = toBall.Length();
        if (dist < .01f) return;
        float ballYaw = Mathf.Atan2(-toBall.X, -toBall.Z);
        float yawDiff = Mathf.AngleDifference(ballYaw, yaw);
        _lookYaw = Mathf.Clamp(yawDiff, -.9f, .9f);
        _lookPitch = Mathf.Clamp(Mathf.Atan2(toBall.Y, new Vector2(toBall.X, toBall.Z).Length()), -.5f, .5f);
    }

    private void UpdateReach(Vector3 worldPos, float yaw, Vector3 ballWorld)
    {
        if (ballWorld == Vector3.Zero) { _reach = 0f; return; }
        float dist = (ballWorld - worldPos).Length();
        _reach = Mathf.Clamp(1f - (dist - .4f) / 1.2f, 0f, 1f);
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
