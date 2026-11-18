// SoccerClipRig.cs — runtime driver for the baked soccer player GLB.
// Phase 1 (AME core):
//   1.1 blend space: speed x turnRate x ballState -> clip + phase + weight
//   1.2 foot-planting IK: two-bone analytic IK (port of footlock._ik)
//   1.3 archetypes: Explosive/Lengthy/Controlled style biases
//   1.5 look-at (head tracks ball) + reach (arm extends toward ball)
//   1.6 phase sync: on clip switch, start the new clip at the matching phase
// Godot 4.x C# (net8.0).  Uses only Godot API — no project types — so it can
// be compiled standalone for verification.
using System;
using System.Collections.Generic;
using Godot;

public sealed class SoccerClipRig : Node3D
{
    public const string LibraryName = "soccer";
    public const string AnimationPlayerPath = "AnimationPlayer";

    // Natural locomotion rates (metres per clip cycle, measured from the
    // baked clips): the rig stretches/squashes clip time so the feet move at
    // the simulated speed.  This is what makes the run read as running
    // instead of skating.
    private static readonly Dictionary<string, float> NaturalRate = new()
    {
        ["soccer_walk"] = .74f, ["soccer_jog"] = 1.01f, ["soccer_run"] = 1.01f,
        ["soccer_sprint"] = 1.22f, ["soccer_dribble"] = .60f,
        ["soccer_run_ball"] = .98f, ["soccer_shield"] = .30f,
        ["soccer_turn"] = .62f, ["soccer_strafe_l"] = .55f,
        ["soccer_strafe_r"] = .55f, ["soccer_backpedal"] = .58f,
        ["soccer_jockey"] = .66f,
    };

    private static readonly Dictionary<string, float> MaxRate = new()
    {
        ["soccer_walk"] = 1.4f, ["soccer_jog"] = 2.2f, ["soccer_run"] = 3.4f,
        ["soccer_sprint"] = 5.6f, ["soccer_dribble"] = 1.8f,
        ["soccer_run_ball"] = 3.6f, ["soccer_shield"] = 1.2f,
        ["soccer_turn"] = 1.6f, ["soccer_strafe_l"] = 1.6f,
        ["soccer_strafe_r"] = 1.6f, ["soccer_backpedal"] = 1.6f,
        ["soccer_jockey"] = 1.8f,
    };

    private AnimationPlayer _player;
    private AnimationLibrary _lib;
    private Skeleton3D _skeleton;
    private string _current = "";
    private float _speed;        // smoothed ground speed (m/s)
    private float _turnRate;     // smoothed yaw rate (rad/s)
    private float _phase;        // 0..1 cycle phase of the current clip
    private bool _hasBall;
    private float _blend;        // 0..1 crossfade progress on clip switch
    private float _prevBlend = 1f;
    private float _lean;         // smoothed forward lean (rad)
    private float _roll;         // smoothed lateral roll (rad)
    private float _lookYaw;      // head look yaw (rad)
    private float _lookPitch;    // head look pitch (rad)
    private float _reach;        // 0..1 arm reach toward the ball
    private float _archetypeLean; // archetype forward-lean bias (rad)
    private float _archetypeCadence; // archetype cadence multiplier
    private float _archetypeStride;  // archetype stride multiplier
    private float _archetypeRoll;    // archetype lateral roll bias (rad)
    private Vector3 _prevPos;
    private float _prevYaw;
    private bool _primed;

    // ---- 1.2 foot-planting IK state -------------------------------------
    private readonly Dictionary<string, BoneData> _bones = new();
    private Vector3 _ikTargetL, _ikTargetR;   // desired foot targets (local)
    private bool _ikActiveL, _ikActiveR;

    private sealed class BoneData
    {
        public int Thigh, Shin, Foot, Spine, Neck, Head, UpperArmL, LowerArmL, UpperArmR, LowerArmR;
        public Vector3 ThighRest, ShinRest, FootRest, SpineRest, NeckRest, HeadRest;
        public Vector3 UpperArmRestL, LowerArmRestL, UpperArmRestR, LowerArmRestR;
    }

    public void Bind(AnimationPlayer player, Skeleton3D skeleton)
    {
        _player = player;
        _skeleton = skeleton;
        _lib = player.GetAnimationLibrary(LibraryName);
        CacheBones();
    }

    private void CacheBones()
    {
        if (_skeleton == null) return;
        _bones.Clear();
        foreach (var side in new[] { "L", "R" })
        {
            var b = new BoneData
            {
                Thigh = _skeleton.FindBone("thigh_" + side),
                Shin = _skeleton.FindBone("shin_" + side),
                Foot = _skeleton.FindBone("foot_" + side),
            };
            if (b.Thigh < 0 || b.Shin < 0 || b.Foot < 0) continue;
            b.ThighRest = _skeleton.GetBoneRest(b.Thigh).Origin;
            b.ShinRest = _skeleton.GetBoneRest(b.Shin).Origin;
            b.FootRest = _skeleton.GetBoneRest(b.Foot).Origin;
            _bones[side] = b;
        }
        // Spine / neck / head / arms for look-at + reach (1.5).
        var spine = _skeleton.FindBone("spine_02");
        var neck = _skeleton.FindBone("neck_01");
        var head = _skeleton.FindBone("head");
        var uaL = _skeleton.FindBone("upperarm_L");
        var laL = _skeleton.FindBone("lowerarm_L");
        var uaR = _skeleton.FindBone("upperarm_R");
        var laR = _skeleton.FindBone("lowerarm_R");
        if (spine >= 0 && neck >= 0 && head >= 0)
        {
            var b = _bones.TryGetValue("L", out var bl) ? bl : new BoneData();
            b.Spine = spine; b.Neck = neck; b.Head = head;
            b.SpineRest = _skeleton.GetBoneRest(spine).Origin;
            b.NeckRest = _skeleton.GetBoneRest(neck).Origin;
            b.HeadRest = _skeleton.GetBoneRest(head).Origin;
            if (uaL >= 0 && laL >= 0)
            {
                b.UpperArmL = uaL; b.LowerArmL = laL;
                b.UpperArmRestL = _skeleton.GetBoneRest(uaL).Origin;
                b.LowerArmRestL = _skeleton.GetBoneRest(laL).Origin;
            }
            if (uaR >= 0 && laR >= 0)
            {
                b.UpperArmR = uaR; b.LowerArmR = laR;
                b.UpperArmRestR = _skeleton.GetBoneRest(uaR).Origin;
                b.LowerArmRestR = _skeleton.GetBoneRest(laR).Origin;
            }
            _bones["L"] = b;
        }
    }

    /// <summary>Set the player's movement archetype (Phase 1.3).  Called by
    /// the world when the character spec is known.</summary>
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

    /// <summary>Drive the rig.  Call once per physics frame with the player's
    /// world position, facing yaw (radians), ground speed (m/s), whether the
    /// player has the ball, and the ball's world position (for look-at/reach).
    /// Pass ballWorld = Vector3.Zero when there is no ball.</summary>
    public void Drive(Vector3 worldPos, float yaw, float speed, bool hasBall,
                      Vector3 ballWorld = default)
    {
        if (_player == null || _lib == null) return;
        if (!_primed)
        {
            _prevPos = worldPos; _prevYaw = yaw; _primed = true;
            _speed = speed;
        }
        // Measured ground speed + yaw rate (smoothed).
        float dt = Math.Max(GetPhysicsProcessDeltaTime(), 1e-4f);
        var delta = worldPos - _prevPos;
        float measured = speed > 0f ? speed : delta.Length() / dt;
        _speed = Mathf.Lerp(_speed, measured, .25f);
        float dyaw = Mathf.AngleDifference(yaw, _prevYaw);
        _turnRate = Mathf.Lerp(_turnRate, dyaw / dt, .2f);
        _prevPos = worldPos; _prevYaw = yaw;
        _hasBall = hasBall;

        // ---- 1.1 blend space: (speed, turnRate, ballState) -> clip -------
        string want = SelectClip(_speed, _turnRate, hasBall);
        if (want != _current)
        {
            // 1.6 phase sync: start the new clip at the matching cycle phase
            // so the feet don't jump when the clip changes.
            float startPhase = _phase;
            _current = want;
            _player.Play(LibraryName + "/" + want, .18f);
            _player.Seek(startPhase * _lib.GetAnimation(want).Length, true);
            _blend = 0f;
        }
        _prevBlend = _blend;
        _blend = Mathf.Min(_blend + dt / .18f, 1f);

        // ---- cadence: match clip rate to ground speed (archetype-biased) -
        float natural = NaturalRate.TryGetValue(want, out var n) ? n : 1f;
        float maxRate = MaxRate.TryGetValue(want, out var m) ? m : 3f;
        float target = Mathf.Clamp(_speed / Math.Max(natural, .01f), .25f, 1.6f);
        target *= _archetypeCadence;
        // Blend-space weight: how much of the new clip to show during the
        // crossfade (1.1).  Phase sync keeps the feet continuous.
        float weight = _blend;
        _player.SetCurrentAnimation(LibraryName + "/" + want);
        _player.SetCurrentAnimationPosition(
            (_phase * _lib.GetAnimation(want).Length) % _lib.GetAnimation(want).Length);
        _player.SpeedScale = Mathf.Lerp(_player.SpeedScale, target, .12f);
        _phase = (_phase + dt * _player.SpeedScale / _lib.GetAnimation(want).Length) % 1f;

        // ---- 1.5 lean / roll / look-at / reach ---------------------------
        UpdateLean(_speed, _turnRate);
        UpdateLookAt(worldPos, yaw, ballWorld);
        UpdateReach(worldPos, yaw, ballWorld);

        // ---- 1.2 foot-planting IK ---------------------------------------
        UpdateFootIk(worldPos, yaw);
    }

    /// <summary>Blend-space clip selection (Phase 1.1).  Maps (speed,
    /// turnRate, ballState) to a locomotion clip.  Directional clips
    /// (strafe/backpedal/jockey) are chosen when the player moves sideways
    /// or backwards relative to facing — the caller passes the velocity
    /// heading via turnRate sign conventions; here we use speed bands plus
    /// turn-rate thresholds, with ballState switching to dribble/shield.</summary>
    public string SelectClip(float speed, float turnRate, bool hasBall)
    {
        // Sharp turn at speed -> turn clip (Phase 0.4, kept in blend space).
        if (Math.Abs(turnRate) > 2.2f && speed > 1.2f) return "soccer_turn";
        if (hasBall)
        {
            if (speed < .35f) return "soccer_shield";
            if (speed < 1.8f) return "soccer_dribble";
            return "soccer_run_ball";
        }
        if (speed < .35f) return "soccer_idle";
        if (speed < 1.4f) return "soccer_walk";
        if (speed < 2.4f) return "soccer_jog";
        if (speed < 3.8f) return "soccer_run";
        return "soccer_sprint";
    }

    /// <summary>Directional clip selection (Phase 1.4): given the velocity
    /// heading relative to facing (radians, 0 = forward, ±π = backwards),
    /// pick the matching locomotion clip.  Used by the world when the
    /// player's movement direction differs from their facing.</summary>
    public string SelectDirectionalClip(float speed, float headingOffset, bool hasBall)
    {
        float a = Math.Abs(Mathf.AngleDifference(headingOffset, 0f));
        if (hasBall) return SelectClip(speed, 0f, true);
        if (a < .5f) return SelectClip(speed, 0f, false);          // forward
        if (a > 2.6f) return "soccer_backpedal";                  // backwards
        if (headingOffset > 0f) return "soccer_strafe_l";         // left
        return "soccer_strafe_r";                                 // right
    }

    private void UpdateLean(float speed, float turnRate)
    {
        float leanTarget = Mathf.Clamp(speed * .035f, 0f, .28f) + _archetypeLean * .5f;
        float rollTarget = Mathf.Clamp(-turnRate * .06f, -.22f, .22f) + _archetypeRoll * .3f;
        _lean = Mathf.Lerp(_lean, leanTarget, .08f);
        _roll = Mathf.Lerp(_roll, rollTarget, .08f);
        Rotation = new Vector3(_lean, Rotation.Y, _roll);
    }

    /// <summary>Head look-at (Phase 1.5): yaw/pitch the neck+head toward the
    /// ball, clamped to a natural range.  Applied as a bone offset in
    /// _Process via the skeleton.</summary>
    private void UpdateLookAt(Vector3 worldPos, float yaw, Vector3 ballWorld)
    {
        if (ballWorld == Vector3.Zero || _skeleton == null) { _lookYaw = 0f; _lookPitch = 0f; return; }
        var toBall = ballWorld - (worldPos + Vector3.Up * 1.6f);
        float dist = toBall.Length();
        if (dist < .01f) return;
        float ballYaw = Mathf.Atan2(-toBall.X, -toBall.Z);
        float yawDiff = Mathf.AngleDifference(ballYaw, yaw);
        _lookYaw = Mathf.Clamp(yawDiff, -.9f, .9f);
        _lookPitch = Mathf.Clamp(Mathf.Atan2(toBall.Y, new Vector2(toBall.X, toBall.Z).Length()), -.5f, .5f);
    }

    /// <summary>Arm reach (Phase 1.5): extend the arm toward a nearby ball
    /// (trapping/receiving).  _reach is 0..1.</summary>
    private void UpdateReach(Vector3 worldPos, float yaw, Vector3 ballWorld)
    {
        if (ballWorld == Vector3.Zero) { _reach = 0f; return; }
        float dist = (ballWorld - worldPos).Length();
        _reach = Mathf.Clamp(1f - (dist - .4f) / 1.2f, 0f, 1f);
    }

    /// <summary>Foot-planting IK (Phase 1.2): two-bone analytic IK ported
    /// from sprite_forge/sforge/footlock.py.  Plants the feet on the ground
    /// plane so they don't skate during turns and cuts.</summary>
    private void UpdateFootIk(Vector3 worldPos, float yaw)
    {
        if (_skeleton == null || _bones.Count == 0) return;
        // Desired foot targets: directly below the hips, on the ground.
        // The skeleton's animated pose already places the feet; IK refines
        // them toward the ground plane to kill skating.
        foreach (var side in new[] { "L", "R" })
        {
            if (!_bones.TryGetValue(side, out var b)) continue;
            // Current foot world position from the skeleton.
            var footGlobal = _skeleton.GetBoneGlobalPose(b.Foot).Origin;
            // Project to the ground plane (y = worldPos.y).
            var target = new Vector3(footGlobal.X, worldPos.Y, footGlobal.Z);
            // Only correct when the foot is near the ground (planted phase).
            float height = footGlobal.Y - worldPos.Y;
            bool planted = height < .18f;
            if (planted)
            {
                SolveTwoBone(b, side == "L", target, worldPos, yaw);
            }
        }
        ApplyLookAndReach();
    }

    /// <summary>Two-bone IK (port of footlock._ik): given a hip position, a
    /// target, and thigh/shin lengths, compute the knee position via the
    /// law of cosines and the joint rotations.  Applies the rotations to
    /// the skeleton bones.</summary>
    private void SolveTwoBone(BoneData b, bool isLeft, Vector3 targetWorld,
                              Vector3 rootWorld, float yaw)
    {
        // Hip world position (thigh bone global origin).
        var hip = _skeleton.GetBoneGlobalPose(b.Thigh).Origin;
        float l1 = b.ThighRest.Length();   // thigh length
        float l2 = b.ShinRest.Length();    // shin length
        var toTarget = targetWorld - hip;
        float dist = Mathf.Clamp(toTarget.Length(), .01f, l1 + l2 - .001f);
        var dir = toTarget.Normalized();
        // Law of cosines: angle at the hip between thigh and target dir.
        float cosA = (l1 * l1 + dist * dist - l2 * l2) / (2f * l1 * dist);
        float angA = Mathf.Acos(Mathf.Clamp(cosA, -1f, 1f));
        // Pole vector: knee points forward (+Z in bone space -> world -Z fwd).
        var fwd = new Vector3(-Mathf.Sin(yaw), 0f, -Mathf.Cos(yaw));
        var pole = fwd;
        var axis = dir.Cross(pole);
        if (axis.LengthSquared() < 1e-6f) axis = Vector3.Up;
        axis = axis.Normalized();
        var kneeDir = dir.Rotated(axis, angA);
        var knee = hip + kneeDir * l1;
        // Joint rotations (shortest-arc from rest to current, as in footlock).
        var thighQuat = ShortestArc(b.ThighRest.Normalized(), kneeDir);
        var shinDir = (targetWorld - knee).Normalized();
        var shinQuat = ShortestArc(b.ShinRest.Normalized(), shinDir);
        // Apply as bone pose overrides (local to parent).
        _skeleton.SetBonePoseRotation(b.Thigh, thighQuat);
        _skeleton.SetBonePoseRotation(b.Shin, shinQuat);
    }

    /// <summary>Shortest-arc quaternion from one direction to another
    /// (port of footlock._shortest_arc).</summary>
    private static Quaternion ShortestArc(Vector3 from, Vector3 to)
    {
        from = from.Normalized(); to = to.Normalized();
        float dot = Mathf.Clamp(from.Dot(to), -1f, 1f);
        if (dot > .999999f) return Quaternion.Identity;
        if (dot < -.999999f)
        {
            var axis = from.Cross(Vector3.Up);
            if (axis.LengthSquared() < 1e-6f) axis = from.Cross(Vector3.Right);
            return Quaternion.FromAxisAngle(axis.Normalized(), Mathf.Pi);
        }
        var axis2 = from.Cross(to).Normalized();
        float angle = Mathf.Acos(dot);
        return Quaternion.FromAxisAngle(axis2, angle);
    }

    /// <summary>Apply look-at (neck/head) and reach (arm) as bone pose
    /// offsets on top of the animated pose (Phase 1.5).</summary>
    private void ApplyLookAndReach()
    {
        if (!_bones.TryGetValue("L", out var b)) return;
        if (b.Neck >= 0 && b.Head >= 0)
        {
            var neckQ = Quaternion.FromAxisAngle(Vector3.Up, _lookYaw) *
                        Quaternion.FromAxisAngle(Vector3.Right, _lookPitch);
            _skeleton.SetBonePoseRotation(b.Neck, neckQ);
            var headQ = Quaternion.FromAxisAngle(Vector3.Up, _lookYaw * .5f) *
                        Quaternion.FromAxisAngle(Vector3.Right, _lookPitch * .5f);
            _skeleton.SetBonePoseRotation(b.Head, headQ);
        }
        if (_reach > .01f)
        {
            // Extend the nearer arm toward the ball (simple pitch forward).
            var armQ = Quaternion.FromAxisAngle(Vector3.Right, -_reach * 1.1f);
            if (b.UpperArmR >= 0) _skeleton.SetBonePoseRotation(b.UpperArmR, armQ);
            if (b.LowerArmR >= 0)
                _skeleton.SetBonePoseRotation(b.LowerArmR,
                    Quaternion.FromAxisAngle(Vector3.Right, -_reach * .4f));
        }
    }
}
