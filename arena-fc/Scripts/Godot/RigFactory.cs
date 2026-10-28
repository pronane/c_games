// Arena FC - converts the pure-C# procedural rig into real Godot 3D resources:
// Skeleton3D (bone hierarchy + rest poses), Skin (inverse bind matrices),
// ArrayMesh (per-vertex 4-bone weights, 9 material surfaces), and PBR materials.
using System;
using System.Collections.Generic;
using System.Linq;
using ArenaFC.Core;
using Godot;

namespace ArenaFC.GodotGame;

public partial class CharacterRig : Node3D
{
    public CharacterSpec Spec = new();
    public RigGeometry Geo = new();
    public Skeleton3D Skeleton = null!;
    public MeshInstance3D Mesh = null!;
    public MeshInstance3D BoneOverlay = null!;
    public Label3D NameLabel = null!;
    public StandardMaterial3D[] Materials = new StandardMaterial3D[9];
    public bool EditorMode;
    public readonly Dictionary<string, int> BoneIndex = new();

    public void Rebuild(CharacterSpec spec)
    {
        Spec = spec ?? new CharacterSpec();
        Spec.Sanitize();
        foreach (Node c in GetChildren()) { RemoveChild(c); c.QueueFree(); }
        Geo = RigBuilder.Build(Spec);
        BoneIndex.Clear();

        Skeleton = new Skeleton3D { Name = "Skeleton3D" };
        AddChild(Skeleton);
        for (int i = 0; i < Geo.Bones.Length; i++)
        {
            var b = Geo.Bones[i];
            int idx = Skeleton.AddBone(b.Name);
            BoneIndex[b.Name] = idx;
            if (b.Parent >= 0) Skeleton.SetBoneParent(idx, b.Parent);
            System.Numerics.Vector3 parentHead = b.Parent >= 0 ? Geo.Bones[b.Parent].Head : System.Numerics.Vector3.Zero;
            Vector3 localRest = G(b.Head - parentHead);
            Skeleton.SetBoneRest(idx, new Transform3D(Basis.Identity, localRest));
            // Godot 4.7: the animated global pose is built from pose_position, NOT
            // from rest. Seed each bone's pose position with its rest translation,
            // otherwise every skinned vertex collapses onto the origin.
            Skeleton.SetBonePosePosition(idx, localRest);
        }

        var skin = new Skin();
        for (int i = 0; i < Geo.Bones.Length; i++)
            skin.AddBind(i, new Transform3D(Basis.Identity, G(Geo.Bones[i].Head)).Inverse());

        for (int i = 0; i < Materials.Length; i++) Materials[i] = MakeMaterial((RigMat)i);

        var arrays = new Godot.Collections.Array();
        arrays.Resize((int)Godot.Mesh.ArrayType.Max);
        arrays[(int)Godot.Mesh.ArrayType.Vertex] = ToG(Geo.Positions);
        arrays[(int)Godot.Mesh.ArrayType.Normal] = ToG(Geo.Normals);
        arrays[(int)Godot.Mesh.ArrayType.TexUV] = ToG(Geo.Uvs);
        arrays[(int)Godot.Mesh.ArrayType.Bones] = Geo.BoneIndices;
        arrays[(int)Godot.Mesh.ArrayType.Weights] = Geo.Weights;

        var arrayMesh = new ArrayMesh();
        for (int s = 0; s < Geo.SurfaceMaterials.Length; s++)
        {
            int mat = Geo.SurfaceMaterials[s];
            if (Geo.Indices[mat].Length == 0) continue;
            arrays[(int)Godot.Mesh.ArrayType.Index] = Geo.Indices[mat];
            arrayMesh.AddSurfaceFromArrays(Godot.Mesh.PrimitiveType.Triangles, arrays);
            arrayMesh.SurfaceSetMaterial(s, Materials[mat]);
            arrayMesh.SurfaceSetName(s, ((RigMat)mat).ToString());
        }

        Mesh = new MeshInstance3D { Name = "SkinnedMesh", Mesh = arrayMesh, Skin = skin };
        Skeleton.AddChild(Mesh);
        Mesh.Skeleton = new NodePath("..");
        Mesh.CastShadow = GeometryInstance3D.ShadowCastingSetting.On;

        NameLabel = new Label3D
        {
            Name = "ShirtName",
            Text = $"{Spec.DisplayName}  {Spec.Number}",
            FontSize = 48,
            PixelSize = 0.0032f,
            OutlineSize = 6,
            Modulate = new Color(1, 1, 1, 1),
            Position = new Vector3(0, Geo.Bones[2].Head.Y + .035f, -.225f),
            RotationDegrees = new Vector3(0, 180, 0),
            DoubleSided = false,
        };
        AddChild(NameLabel);

        BuildBoneOverlay();
        ApplyPoseOverrides();
    }

    public static Vector3 G(System.Numerics.Vector3 v) => new(v.X, v.Y, v.Z);

    private static Vector3[] ToG(System.Numerics.Vector3[] v)
    {
        var r = new Vector3[v.Length];
        for (int i = 0; i < v.Length; i++) r[i] = G(v[i]);
        return r;
    }
    private static Vector2[] ToG(System.Numerics.Vector2[] v)
    {
        var r = new Vector2[v.Length];
        for (int i = 0; i < v.Length; i++) r[i] = new Vector2(v[i].X, v[i].Y);
        return r;
    }

    public static Color C(string hex)
    {
        Mx.HexToRgb(hex, out float r, out float g, out float b);
        return new Color(r, g, b);
    }

    private string MaterialHex(RigMat mat) => mat switch
    {
        RigMat.Skin => Spec.SkinHex,
        RigMat.Shirt => Spec.KitPrimary,
        RigMat.ShirtTrim => Spec.KitSecondary,
        RigMat.Shorts => Spec.ShortsColor,
        RigMat.Socks => Spec.SocksColor,
        RigMat.Boots => Spec.BootsColor,
        RigMat.Hair => Spec.HairColor,
        RigMat.Gloves => Spec.GlovesColor,
        _ => "#14151a",
    };

    private StandardMaterial3D MakeMaterial(RigMat mat)
    {
        string hex = MaterialHex(mat);
        return new StandardMaterial3D
        {
            AlbedoColor = C(hex),
            Roughness = mat is RigMat.Boots or RigMat.Hair ? .35f : .72f,
            Metallic = mat == RigMat.Boots ? .18f : 0f,
            CullMode = BaseMaterial3D.CullModeEnum.Disabled,
        };
    }

    public void ApplyAppearance()
    {
        Spec.Sanitize();
        for (int i = 0; i < Materials.Length; i++) if (Materials[i] != null) Materials[i].AlbedoColor = C(MaterialHex((RigMat)i));
        if (NameLabel != null)
        {
            NameLabel.Text = $"{Spec.DisplayName}  {Spec.Number}";
            NameLabel.Position = new Vector3(0, Geo.Bones[2].Head.Y + .035f, -.225f);
            Mx.HexToRgb(Spec.KitPrimary, out float br, out float bg, out float bb);
            NameLabel.Modulate = (br + bg + bb) / 3f < .35f ? new Color(1, 1, 1) : new Color(.08f, .09f, .12f);
        }
        ApplyPoseOverrides();
    }

    public void ApplyPoseOverrides()
    {
        if (Skeleton == null) return;
        for (int i = 0; i < Geo.Bones.Length; i++)
        {
            var v = Spec.GetBoneRotation(Geo.Bones[i].Name);
            // Keep pose position in sync with rest (a ResetBonePoses() anywhere
            // would zero it and collapse the skin otherwise).
            var b = Geo.Bones[i];
            var parentHead = b.Parent >= 0 ? Geo.Bones[b.Parent].Head : System.Numerics.Vector3.Zero;
            Skeleton.SetBonePosePosition(i, G(b.Head - parentHead));
            Skeleton.SetBonePoseRotation(i, Quaternion.FromEuler(new Vector3(
                Mathf.DegToRad(v[0]), Mathf.DegToRad(v[1]), Mathf.DegToRad(v[2]))));
        }
    }

    private void BuildBoneOverlay()
    {
        var im = new ImmediateMesh();
        var m = new StandardMaterial3D
        {
            AlbedoColor = new Color(.15f, 1f, .55f),
            ShadingMode = BaseMaterial3D.ShadingModeEnum.Unshaded,
            DisableReceiveShadows = true,
        };
        im.SurfaceBegin(Godot.Mesh.PrimitiveType.Lines, m);
        foreach (var b in Geo.Bones)
        {
            im.SurfaceAddVertex(new Vector3(b.Head.X, b.Head.Y, b.Head.Z));
            im.SurfaceAddVertex(new Vector3(b.Tail.X, b.Tail.Y, b.Tail.Z));
        }
        im.SurfaceEnd();
        BoneOverlay = new MeshInstance3D { Name = "BoneOverlay", Mesh = im, Visible = false };
        AddChild(BoneOverlay);
    }

    public void ShowBones(bool show)
    {
        if (BoneOverlay != null) BoneOverlay.Visible = show;
    }
}

public static class RigFactory
{
    public static CharacterRig Create(CharacterSpec spec, bool editorMode = false)
    {
        var rig = new CharacterRig { Name = "Rig_" + spec.DisplayName, EditorMode = editorMode };
        rig.Rebuild(spec);
        return rig;
    }
}
