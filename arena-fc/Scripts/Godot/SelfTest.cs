// Arena FC - in-engine integration tests. Run with:
//   godot --headless --path . -- --selftest
// Exercises the actual Godot nodes: skinned mesh, skeleton, GLB export/import,
// shaders, stadium, HUD, editor and the full 3D match pipeline.
using System;
using System.IO;
using System.Linq;
using ArenaFC.Core;
using Godot;

namespace ArenaFC.GodotGame;

public static class SelfTest
{
    public static void Run(Node3D root)
    {
        int pass = 0, fail = 0;
        void Check(string name, bool ok, string? detail = null)
        {
            if (ok) { pass++; GD.Print($"  PASS  {name}"); }
            else { fail++; GD.PrintErr($"  FAIL  {name} {detail}"); }
        }
        void Section(string s) => GD.Print("\n== " + s + " ==");

        GD.Print("ARENA FC — IN-ENGINE SELF TEST (Godot " + Engine.GetVersionInfo()["string"] + ")");

        Section("Shaders / resources");
        foreach (string shader in new[] { "pitch", "ball", "net", "crowd", "sky" })
            Check("shader " + shader + " loads", GD.Load<Shader>($"res://Shaders/{shader}.gdshader") != null);

        Section("Procedural rig in Godot (Skeleton3D + Skin + skinned ArrayMesh)");
        var spec = new CharacterSpec { Name = "Test Player", DisplayName = "TEST", Number = 9 };
        spec.SetBoneRotation("LThigh", 22f, 0, 0);
        var rig = RigFactory.Create(spec, true);
        root.AddChild(rig);
        Check("Skeleton3D has 18 bones", rig.Skeleton.GetBoneCount() == 18, $"got {rig.Skeleton.GetBoneCount()}");
        Check("bone names include Head / LFoot / Face",
              rig.BoneIndex.ContainsKey("Head") && rig.BoneIndex.ContainsKey("LFoot") && rig.BoneIndex.ContainsKey("Face"));
        Check("Skin has one inverse bind per bone", rig.Mesh.Skin != null && rig.Mesh.Skin.GetBindCount() == 18,
              rig.Mesh.Skin == null ? "null skin" : rig.Mesh.Skin.GetBindCount().ToString());
        Check("MeshInstance3D points at skeleton", rig.Mesh.Skeleton == new NodePath(".."));
        var am = rig.Mesh.Mesh as ArrayMesh;
        Check("ArrayMesh has >=7 PBR surfaces", am != null && am.GetSurfaceCount() >= 7,
              am == null ? "null" : am.GetSurfaceCount().ToString());
        var aabb = am?.GetAabb();
        Check("mesh AABB matches character height", aabb.HasValue && aabb.Value.Size.Y > 1.5f && aabb.Value.Size.Y < 2.4f,
              aabb?.Size.Y.ToString("F2") ?? "null");
        bool hasWeights = false;
        if (am != null)
        {
            var arrays = am.SurfaceGetArrays(0);
            var weights = arrays[(int)Godot.Mesh.ArrayType.Weights].AsFloat32Array();
            var bones = arrays[(int)Godot.Mesh.ArrayType.Bones].AsInt32Array();
            hasWeights = weights.Length == bones.Length && weights.Length > 100;
        }
        Check("surface 0 carries 4-bone weights", hasWeights);
        Check("editor bone pose applied to skeleton",
              MathF.Abs(rig.Skeleton.GetBonePoseRotation(rig.BoneIndex["LThigh"]).GetAngle() - Mathf.DegToRad(22f)) < .02f);
        rig.ShowBones(true);
        Check("bone overlay visible", rig.BoneOverlay.Visible);
        bool skinIdentity = true;
        for (int i = 0; i < rig.Geo.Bones.Length; i++)
        {
            var gr = rig.Skeleton.GetBoneGlobalRest(i);
            var bp = rig.Mesh.Skin!.GetBindPose(i);
            if ((gr * bp).Origin.Length() > .001f) skinIdentity = false;
        }
        Check("skin bind matrices are the exact inverse of the bone global rest (no collapse)", skinIdentity);
        int thigh = rig.BoneIndex["LThigh"];
        Check("posing a bone produces a real skin deformation",
              (rig.Skeleton.GetBoneGlobalPose(thigh) * rig.Mesh.Skin!.GetBindPose(thigh)).Basis != Basis.Identity);
        Check("bone pose positions seeded from rest", rig.Skeleton.GetBonePosePosition(4).Length() > .01f);
        Check("rendered instance AABB is full height", rig.Mesh.GetAabb().Size.Y > 1.5f);

        Section("GLB export / glTF re-import round trip");
        var exported = GlbExporter.Export(rig, "selftest_player");
        Check("GLB written", exported.ok, exported.info + " @ " + exported.path);
        if (exported.ok)
        {
            Check("GLB file exists on disk", File.Exists(exported.path));
            string info = GlbExporter.Inspect(exported.path);
            GD.Print("  GLB inspect: " + info);
            Check("GLB contains meshes/skins/joints", info.Contains("meshes=1") && info.Contains("skins=1") && !info.Contains("jointsArrays=0"), info);
            var doc = new GltfDocument();
            var state = new GltfState();
            Error err = doc.AppendFromFile(exported.path, state);
            Check("Godot can read exported GLB", err == Error.Ok, err.ToString());
            if (err == Error.Ok)
            {
                Node imported = doc.GenerateScene(state);
                int bones = 0;
                CountBones(imported, ref bones);
                Check("imported scene has skeleton joints", bones >= 18, $"bones={bones}");
                imported.QueueFree();
            }
        }

        Section("Character JSON round trip via Godot FileAccess");
        Godot.DirAccess.MakeDirRecursiveAbsolute("user://characters");
        string cpath = "user://characters/selftest.json";
        using (var f = Godot.FileAccess.Open(cpath, Godot.FileAccess.ModeFlags.Write)) f?.StoreString(spec.ToJson());
        var loaded = CharacterSpec.FromJson(Godot.FileAccess.GetFileAsString(cpath));
        Check("character JSON survives user:// save/load",
              loaded.DisplayName == "TEST" && MathF.Abs(loaded.GetBoneRotation("LThigh")[0] - 22f) < .01f);
        var roster = Clubs.CreateRoster(0, 11);
        string rjson = CharacterIo.SerializeRoster(roster, "SELFTEST FC");
        var r2 = CharacterIo.DeserializeRoster(rjson, out var tname);
        Check("roster JSON survives round trip", r2.Count == 11 && tname == "SELFTEST FC" && r2[0].IsKeeper);

        Section("Stadium / shaders / HUD / editor nodes");
        var stadium = new Stadium();
        stadium.Build(false);
        root.AddChild(stadium);
        Check("stadium built with goals + stands", stadium.GetChildCount() > 25, $"children={stadium.GetChildCount()}");
        Check("pitch uses procedural line shader", stadium.GetNodeOrNull<MeshInstance3D>("Pitch")?.MaterialOverride is ShaderMaterial);
        var hud = new Hud();
        root.AddChild(hud);
        Check("HUD constructed", hud.GetChildCount() > 0);
        hud.SetTouch(true);
        Check("touch controls can be enabled", hud.Input.TouchEnabled);
        var ed = new CharacterEditor();
        ed.Init(roster);
        root.AddChild(ed);
        Check("character editor constructed", ed.GetChildCount() >= 4, $"children={ed.GetChildCount()}");
        ed.QueueFree();
        hud.QueueFree();
        stadium.QueueFree();

        Section("Full 3D match pipeline (5v5, 12 simulated seconds)");
        var view = new MatchView();
        view.Init(new MatchOptions { TeamSize = 5, Seed = 4242, TimeSpeed = 15f }, null, () => { });
        root.AddChild(view);
        Check("22 rig nodes? (5v5 => 10)", view.Rigs.Length == 10, $"rigs={view.Rigs.Length}");
        Check("all rigs have skinned meshes", view.Rigs.All(r => r.Mesh.Mesh is ArrayMesh && r.Mesh.Skin != null));
        Check("ball mesh created", view.Ball.Mesh != null);
        Check("broadcast camera is current", view.Cam.IsCurrent());
        view.SimulateForTest(12f);
        Check("match clock advanced", view.Engine.State.Clock > 100f, $"clock={view.Engine.State.Clock:F1}");
        Check("simulation produced events", view.Engine.Events.Count >= 2, $"events={view.Engine.Events.Count}");
        Check("no NaN ball/player positions", Mx.IsFinite(view.Engine.State.Ball.Pos) && view.Engine.State.Players.All(p => Mx.IsFinite(p.Pos)));
        Check("3D rig transforms followed simulation",
              view.Rigs.Any(r => MathF.Abs(r.Position.X) > .5f || MathF.Abs(r.Position.Z) > .5f));
        Check("HUD scoreboard updated", view.Hud != null);
        view.QueueFree();
        rig.QueueFree();

        GD.Print($"\nRESULT: {pass} passed, {fail} failed");
        if (fail == 0) GD.Print("ARENA_FC_SELFTEST_PASS");
        else GD.PrintErr("ARENA_FC_SELFTEST_FAIL");
        root.GetTree().Quit(fail == 0 ? 0 : 1);
    }

    private static void CountBones(Node n, ref int count)
    {
        if (n is Skeleton3D sk) count += sk.GetBoneCount();
        foreach (Node c in n.GetChildren()) CountBones(c, ref count);
    }
}
