// Arena FC - goals with real nets and corner flags from Sprite Forge (sforge.goalnet, v11.39).
// The net bulges where a goal goes in (goal_net.gdshader); presentation only.
using System;
using ArenaFC.Core;
using Godot;

namespace ArenaFC.GodotGame;

public partial class Stadium
{
    public const string GoalPath = "res://Data/models/goal_soccer.glb";
    private readonly ShaderMaterial?[] _netMats = new ShaderMaterial?[2];
    private readonly Node3D?[] _goalRoots = new Node3D?[2];
    private readonly float[] _netSince = { 10f, 10f };
    private ShaderMaterial? _flagMat;
    private float _wind;

    private static GltfDocument? _goalDoc;
    private static GltfState? _goalState;

    private static Node3D? GoalScene()
    {
        if (!Godot.FileAccess.FileExists(GoalPath)) return null;
        if (_goalState == null)
        {
            _goalDoc = new GltfDocument();
            var st = new GltfState();
            if (_goalDoc.AppendFromFile(GoalPath, st) != Error.Ok) return null;
            _goalState = st;
        }
        return _goalDoc!.GenerateScene(_goalState) as Node3D;
    }

    /// <summary>Both goals and the four corner flags from the Sprite Forge goal GLB; false when it is missing
    /// (World3D then builds its old posts and flat nets).</summary>
    private bool BuildSpriteForgeGoals()
    {
        var probe = GoalScene();
        if (probe == null) return false;
        probe.QueueFree();
        var netShader = GD.Load<Shader>("res://Shaders/goal_net.gdshader");
        for (int k = 0; k < 2; k++)
        {
            int sign = k == 0 ? -1 : 1;
            var g = GoalScene()!;
            g.Name = sign < 0 ? "GoalLeft" : "GoalRight";
            g.Position = new Vector3(sign * Mx.HalfLength, 0, 0);
            g.RotationDegrees = new Vector3(0, sign < 0 ? 180 : 0, 0);
            AddChild(g);
            _goalRoots[k] = g;
            var mat = new ShaderMaterial { Shader = netShader };
            mat.SetShaderParameter("wind", _wind);
            _netMats[k] = mat;
            foreach (var n in g.FindChildren("*", "MeshInstance3D", true, false))
            {
                if (n is not MeshInstance3D mi) continue;
                string name = mi.Name.ToString();
                if (name.StartsWith("flag")) { mi.Visible = false; continue; }
                if (name.StartsWith("net"))
                {
                    mi.MaterialOverride = mat;
                    mi.CastShadow = GeometryInstance3D.ShadowCastingSetting.Off;
                }
                else if (mi.GetActiveMaterial(0) is BaseMaterial3D bm)
                {
                    bm.VertexColorUseAsAlbedo = true;
                    bm.VertexColorIsSrgb = true;
                    bm.Roughness = .32f;
                }
            }
        }
        _flagMat = new ShaderMaterial { Shader = GD.Load<Shader>("res://Shaders/corner_flag.gdshader") };
        _flagMat.SetShaderParameter("wind", Math.Max(.2f, _wind));
        _flagMat.SetShaderParameter("colour", HomeColour);
        int f = 0;
        foreach (float sx in new[] { -1f, 1f })
            foreach (float sz in new[] { -1f, 1f })
            {
                var c = GoalScene()!;
                c.Name = "CornerFlag" + f;
                c.Position = new Vector3(sx * Mx.HalfLength, 0, sz * Mx.HalfWidth);
                c.RotationDegrees = new Vector3(0, 35f + 90f * f, 0);
                AddChild(c);
                var m = (ShaderMaterial)_flagMat.Duplicate();
                m.SetShaderParameter("phase", f * 1.7f);
                foreach (var n in c.FindChildren("*", "MeshInstance3D", true, false))
                {
                    if (n is not MeshInstance3D mi) continue;
                    string name = mi.Name.ToString();
                    if (name == "flag_cloth") mi.MaterialOverride = m;
                    else if (name == "flag_pole" && mi.GetActiveMaterial(0) is BaseMaterial3D bm) { bm.VertexColorUseAsAlbedo = true; bm.VertexColorIsSrgb = true; }
                    else mi.Visible = false;
                }
                f++;
            }
        return true;
    }

    /// <summary>A goal went in: bulge the net where the ball meets it, harder the faster it was going.</summary>
    public void NetImpact(Vector3 ball, Vector3 vel)
    {
        int k = ball.X < 0 ? 0 : 1;
        var g = _goalRoots[k];
        var mat = _netMats[k];
        if (g == null || mat == null) return;
        var local = g.ToLocal(GlobalTransform * ball);
        var dir = (g.GlobalTransform.Basis.Inverse() * vel);
        if (dir.LengthSquared() < .01f) dir = new Vector3(1, 0, 0);
        dir = dir.Normalized();
        if (dir.X < .2f) dir = new Vector3(.2f, dir.Y, dir.Z).Normalized();
        // carry the ball on along its line to the net: the roof (top) or the sloping back
        float y = Math.Clamp(local.Y, .25f, Mx.GoalHeight - .1f);
        float back = 1.0f + (2.0f - 1.0f) * (1f - y / Mx.GoalHeight);
        var hit = new Vector3(back, y, Math.Clamp(local.Z, -Mx.GoalHalfWidth + .3f, Mx.GoalHalfWidth - .3f));
        mat.SetShaderParameter("impact", hit);
        mat.SetShaderParameter("impact_dir", dir);
        mat.SetShaderParameter("strength", Math.Clamp(vel.Length() / 30f, .25f, .7f));
        _netSince[k] = 0f;
    }

    private void UpdateNets(float dt)
    {
        // the match sets the weather after the ground is built: follow its wind
        float wind = Math.Clamp(MathF.Sqrt(Weather.WindX * Weather.WindX + Weather.WindZ * Weather.WindZ) / 14f, 0f, 1f);
        if (Math.Abs(wind - _wind) > .02f)
        {
            _wind = wind;
            foreach (var m in _netMats) m?.SetShaderParameter("wind", wind);
            foreach (var n in FindChildren("CornerFlag*", "Node3D", false, false))
                foreach (var c in ((Node)n).FindChildren("flag_cloth", "MeshInstance3D", true, false))
                    if (c is MeshInstance3D mi && mi.MaterialOverride is ShaderMaterial fm) fm.SetShaderParameter("wind", Math.Max(.2f, wind));
        }
        for (int k = 0; k < 2; k++)
        {
            if (_netMats[k] == null || _netSince[k] > 6f) continue;
            _netSince[k] += dt;
            _netMats[k]!.SetShaderParameter("since", _netSince[k]);
        }
    }
}
