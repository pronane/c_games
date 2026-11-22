// Arena FC - the referee, assistant referees and fourth official on the pitch (presentation only).
// Positions and calls come from Core/OfficialsDirector (reads the match, never writes it); bodies are the
// same Sprite Forge player GLB in an official kit, signals are the sforge.officials clips, and the flag,
// cards and board are Sprite Forge props (Data/models/officials_props.glb) hung off the right hand.
using System.Collections.Generic;
using System.Linq;
using ArenaFC.Core;
using Godot;

namespace ArenaFC.GodotGame;

public sealed partial class OfficialsView : Node3D
{
    public const string PropsPath = "res://Data/models/officials_props.glb";
    public OfficialsDirector Director = null!;
    public readonly CharacterRig[] Rigs = new CharacterRig[OfficialsDirector.Count];
    private readonly Dictionary<string, Node3D>[] _props = new Dictionary<string, Node3D>[OfficialsDirector.Count];
    private readonly string[] _shown = new string[OfficialsDirector.Count];

    public void Init(MatchEngine engine)
    {
        Name = "Officials";
        var home = engine.State.Players.Length > 0 ? engine.State.Players[0].Spec.KitPrimary : "#d7263d";
        string away = "#1d4ed8";
        foreach (var p in engine.State.Players) if (p.Team == 1 && !p.IsKeeper) { away = p.Spec.KitPrimary; break; }
        foreach (var p in engine.State.Players) if (p.Team == 0 && !p.IsKeeper) { home = p.Spec.KitPrimary; break; }
        var kit = OfficialsDirector.KitFor(home, away);
        Director = new OfficialsDirector(kit.primary, kit.trim, kit.shorts, kit.pattern);
        for (int i = 0; i < OfficialsDirector.Count; i++)
        {
            var rig = RigFactory.Create(Director.Officials[i].Spec);
            rig.Name = "Official_" + (OfficialRole)i;
            if (rig.NameLabel != null) rig.NameLabel.Visible = false;
            AddChild(rig);
            Rigs[i] = rig;
            _props[i] = new Dictionary<string, Node3D>();
            _shown[i] = "";
            AttachProps(i, rig);
        }
    }

    private static GltfDocument? _doc;
    private static GltfState? _state;

    private void AttachProps(int i, CharacterRig rig)
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
        var hand = new BoneAttachment3D { Name = "RightHandProps" };
        skel.AddChild(hand);
        int bone = FindBoneLoose(skel, "RHand");
        if (bone < 0) return;
        hand.BoneName = skel.GetBoneName(bone);
        hand.BoneIdx = bone;
        foreach (var child in scene.GetChildren())
        {
            if (child is not Node3D n) continue;
            string key = n.Name.ToString();
            scene.RemoveChild(n);
            n.Owner = null;
            hand.AddChild(n);
            // grip in the palm: the prop's +Y runs along the closed hand, the face turned outwards
            n.Position = new Vector3(0, -.06f, .02f);
            n.RotationDegrees = key == "flag" ? new Vector3(180, 0, 0) : new Vector3(180, 90, 0);
            n.Visible = false;
            if (n is MeshInstance3D mi) mi.MaterialOverride = PropMaterial();
            foreach (var c in n.FindChildren("*", "MeshInstance3D", true, false))
                if (c is MeshInstance3D m2) m2.MaterialOverride = PropMaterial();
            _props[i][key] = n;
        }
        scene.QueueFree();
    }

    /// <summary>Bone by name, tolerating the "_2" suffixes Godot adds each time one GltfState generates
    /// another scene (every squad player and official shares the parsed GLB).</summary>
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

    private static StandardMaterial3D? _propMat;
    private static StandardMaterial3D PropMaterial() => _propMat ??= new StandardMaterial3D
    {
        VertexColorUseAsAlbedo = true, Roughness = .55f, CullMode = BaseMaterial3D.CullModeEnum.Disabled,
    };

    public void Sync(MatchEngine engine, float dt, float time)
    {
        Director.Update(engine, dt);
        var ball = engine.State.Ball.Pos;
        for (int i = 0; i < OfficialsDirector.Count; i++)
        {
            var o = Director.Officials[i];
            var rig = Rigs[i];
            rig.Position = new Vector3(o.Pos.X, 0, o.Pos.Z);
            rig.Rotation = new Vector3(0, Mathf.Atan2(o.Facing.X, o.Facing.Z), 0);
            RigAnimator.Pose(rig, o, dt, time, ball);
            string want = Director.Prop[i];
            if (want != _shown[i])
            {
                foreach (var kv in _props[i]) kv.Value.Visible = kv.Key == want;
                _shown[i] = want;
            }
        }
    }
}
