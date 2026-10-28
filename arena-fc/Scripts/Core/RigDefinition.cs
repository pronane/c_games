// Arena FC - procedural humanoid rig: real bone hierarchy, real per-vertex skin
// weights, real multi-material mesh. Runs on any .NET host (used by Godot + tests).
using System;
using System.Collections.Generic;
using System.Linq;
using System.Numerics;

namespace ArenaFC.Core;

public enum RigMat { Skin, Shirt, ShirtTrim, Shorts, Socks, Boots, Hair, Gloves, Detail }

public sealed class BoneDef
{
    public string Name = "";
    public string ParentName = "";
    public int Parent = -1;
    public Vector3 Head;
    public Vector3 Tail;
}

public sealed class RigGeometry
{
    public BoneDef[] Bones = Array.Empty<BoneDef>();
    public Vector3[] Positions = Array.Empty<Vector3>();
    public Vector3[] Normals = Array.Empty<Vector3>();
    public Vector2[] Uvs = Array.Empty<Vector2>();
    public int[] BoneIndices = Array.Empty<int>();   // 4 per vertex
    public float[] Weights = Array.Empty<float>();   // 4 per vertex
    public int[][] Indices = Array.Empty<int[]>();   // per RigMat
    public int[] SurfaceMaterials = Array.Empty<int>();
    public Vector3 BoundsMin, BoundsMax;
    public int VertexCount => Positions.Length;
    public int TriangleCount => Indices.Sum(a => a.Length / 3);
    public string[] BoneNames => Bones.Select(b => b.Name).ToArray();
}

public static class RigBuilder
{
    // Rest skeleton, 18 bones, in metres for a 1.80 m reference player.
    // Local forward = +Z, up = +Y, left = -X.
    private static readonly (string name, string parent, float[] head, float[] tail)[] Rest =
    {
        ("Hips",       "",            new[]{0f,.98f,0f},     new[]{0f,1.12f,0f}),
        ("Spine",      "Hips",        new[]{0f,1.12f,0f},    new[]{0f,1.32f,0f}),
        ("Chest",      "Spine",       new[]{0f,1.32f,0f},    new[]{0f,1.50f,0f}),
        ("Neck",       "Chest",       new[]{0f,1.50f,0f},    new[]{0f,1.60f,0f}),
        ("Head",       "Neck",        new[]{0f,1.60f,0f},    new[]{0f,1.80f,0f}),
        ("Face",       "Head",        new[]{0f,1.70f,.08f},  new[]{0f,1.72f,.15f}),
        ("LUpperArm",  "Chest",       new[]{-.20f,1.47f,0f}, new[]{-.23f,1.20f,0f}),
        ("LForearm",   "LUpperArm",   new[]{-.23f,1.20f,0f}, new[]{-.25f,.96f,0f}),
        ("LHand",      "LForearm",    new[]{-.25f,.96f,0f},  new[]{-.25f,.86f,0f}),
        ("RUpperArm",  "Chest",       new[]{ .20f,1.47f,0f}, new[]{ .23f,1.20f,0f}),
        ("RForearm",   "RUpperArm",   new[]{ .23f,1.20f,0f}, new[]{ .25f,.96f,0f}),
        ("RHand",      "RForearm",    new[]{ .25f,.96f,0f},  new[]{ .25f,.86f,0f}),
        ("LThigh",     "Hips",        new[]{-.11f,.98f,0f},  new[]{-.12f,.55f,0f}),
        ("LShin",      "LThigh",      new[]{-.12f,.55f,0f},  new[]{-.12f,.13f,0f}),
        ("LFoot",      "LShin",       new[]{-.12f,.13f,0f},  new[]{-.12f,.05f,.16f}),
        ("RThigh",     "Hips",        new[]{ .11f,.98f,0f},  new[]{ .12f,.55f,0f}),
        ("RShin",      "RThigh",      new[]{ .12f,.55f,0f},  new[]{ .12f,.13f,0f}),
        ("RFoot",      "RShin",       new[]{ .12f,.13f,0f},  new[]{ .12f,.05f,.16f}),
    };

    public static string[] BoneNames => Rest.Select(r => r.name).ToArray();

    public static RigGeometry Build(CharacterSpec spec)
    {
        spec.Sanitize();
        float h = spec.Height / 1.80f;
        float leg = spec.LegLength, arm = spec.ArmLength, bulk = spec.Bulk;
        float hipY = 0.98f * h * leg;
        float shoulderY = hipY + (1.47f - 0.98f) * h;
        float xs = h * (1f + (bulk - 1f) * 0.30f);
        float armXs = xs * spec.ShoulderWidth;

        var bones = new BoneDef[Rest.Length];
        for (int i = 0; i < Rest.Length; i++)
        {
            var r = Rest[i];
            var head = new Vector3(r.head[0], r.head[1], r.head[2]);
            var tail = new Vector3(r.tail[0], r.tail[1], r.tail[2]);
            bool isLeg = r.name is "Hips" or "LThigh" or "LShin" or "LFoot" or "RThigh" or "RShin" or "RFoot";
            bool isArm = r.name.Contains("Arm") || r.name.Contains("Forearm") || r.name.Contains("Hand");
            float hx = head.X * (isArm ? armXs : xs);
            float tx = tail.X * (isArm ? armXs : xs);
            float hz = head.Z * h, tz = tail.Z * h;
            float hy, ty;
            if (isLeg) { hy = head.Y * h * leg; ty = tail.Y * h * leg; }
            else if (isArm)
            {
                hy = shoulderY + (head.Y - 1.47f) * h * arm;
                ty = shoulderY + (tail.Y - 1.47f) * h * arm;
            }
            else { hy = hipY + (head.Y - 0.98f) * h; ty = hipY + (tail.Y - 0.98f) * h; }

            var b = new BoneDef
            {
                Name = r.name,
                ParentName = r.parent,
                Parent = r.parent.Length == 0 ? -1 : Array.FindIndex(bones, 0, i, x => x.Name == r.parent),
                Head = new Vector3(hx, hy, hz),
                Tail = new Vector3(tx, ty, tz),
            };
            bones[i] = b;
        }

        int Bone(string n) => Array.FindIndex(bones, b => b.Name == n);
        int ChildOf(int i) { for (int j = i + 1; j < bones.Length; j++) if (bones[j].Parent == i) return j; return -1; }

        var g = new MeshGen(bones, ChildOf);

        // Torso: overlapping primitives, each rigidly skinned to one bone with soft joints.
        g.Box("Hips", new Vector3(0, hipY + 0.035f * h, 0), new Vector3(.175f * xs * bulk, .105f * h, .115f * xs * bulk), RigMat.Shorts);
        g.Cyl("Spine", 0f, 1f, .165f * xs * bulk, .185f * xs * bulk, RigMat.Shirt);
        g.Cyl("Chest", 0f, 1f, .185f * xs * bulk, .205f * xs * bulk, RigMat.Shirt);
        g.Box("Chest", new Vector3(0, bones[Bone("Chest")].Tail.Y - .035f * h, 0),
              new Vector3(.205f * xs * bulk, .035f * h, .12f * xs * bulk), RigMat.ShirtTrim); // collar
        g.Cyl("Neck", 0f, 1f, .062f * h, .062f * h, RigMat.Skin);

        // Head + hair + face details.
        var headB = bones[Bone("Head")];
        Vector3 headC = (headB.Head + headB.Tail) * 0.5f + new Vector3(0, 0, .012f * h);
        float hr = .112f * h * spec.HeadScale;
        g.Sphere("Head", headC, hr, RigMat.Skin, 10, 14, false);
        if (spec.HairStyle != 3)
        {
            float extra = spec.HairStyle switch { 2 => .022f, 4 => .012f, 1 => .008f, _ => .004f };
            g.Sphere("Head", headC + new Vector3(0, .012f * h, 0), hr + extra * h, RigMat.Hair, 10, 14, true, 0.56f);
            if (spec.HairStyle == 4)
                g.Sphere("Head", headC + new Vector3(0, -.05f * h, -.075f * h), hr * .88f, RigMat.Hair, 8, 10, false);
        }
        g.Sphere("Face", headC + new Vector3(-.042f * h, .018f * h, hr * .90f), .012f * h, RigMat.Detail, 6, 8, false);
        g.Sphere("Face", headC + new Vector3(.042f * h, .018f * h, hr * .90f), .012f * h, RigMat.Detail, 6, 8, false);
        g.Sphere("Face", headC + new Vector3(0, -.02f * h, hr * 1.02f), .013f * h, RigMat.Skin, 6, 8, false);

        // Arms: sleeves -> bare arms -> gloves/hands.
        foreach (string s in new[] { "L", "R" })
        {
            string up = s + "UpperArm", fo = s + "Forearm", ha = s + "Hand";
            float sleeveEnd = spec.LongSleeves ? .92f : .40f;
            g.Cyl(up, 0f, sleeveEnd, .066f * xs * bulk, .058f * xs * bulk, RigMat.Shirt, 10);
            g.Cyl(up, sleeveEnd, 1f, .051f * xs * bulk, .047f * xs * bulk, RigMat.Skin, 10);
            g.Cyl(fo, 0f, 1f, .047f * xs * bulk, .038f * xs * bulk, RigMat.Skin, 10);
            g.Sphere(ha, bones[Bone(ha)].Head + (bones[Bone(ha)].Tail - bones[Bone(ha)].Head) * .55f,
                     .052f * xs, spec.IsKeeper ? RigMat.Gloves : RigMat.Skin, 8, 10, false);
            // sleeve trim
            g.Cyl(up, sleeveEnd - .06f, sleeveEnd, .070f * xs * bulk, .069f * xs * bulk, RigMat.ShirtTrim, 10);
        }

        // Legs: shorts -> skin -> socks -> boots.
        foreach (string s in new[] { "L", "R" })
        {
            string th = s + "Thigh", sh = s + "Shin", ft = s + "Foot";
            g.Cyl(th, 0f, .55f, .092f * xs * bulk, .082f * xs * bulk, RigMat.Shorts, 10);
            g.Cyl(th, .55f, 1f, .078f * xs * bulk, .068f * xs * bulk, RigMat.Skin, 10);
            g.Cyl(sh, 0f, .62f, .068f * xs * bulk, .052f * xs * bulk, RigMat.Skin, 10);
            g.Cyl(sh, .62f, 1f, .056f * xs * bulk, .050f * xs * bulk, RigMat.Socks, 10);
            var foot = bones[Bone(ft)];
            Vector3 fc = (foot.Head + foot.Tail) * .5f + new Vector3(0, -.045f * h, .035f * h);
            g.Box(ft, fc, new Vector3(.058f * xs, .048f * h, .135f * h), RigMat.Boots);
        }

        var geo = g.Finish();
        geo.Bones = bones;
        geo.BoundsMin = g.Min;
        geo.BoundsMax = g.Max;
        return geo;
    }

    private sealed class MeshGen
    {
        private readonly BoneDef[] _bones;
        private readonly Func<int, int> _childOf;
        private readonly List<Vector3> _p = new(), _n = new();
        private readonly List<Vector2> _uv = new();
        private readonly List<int> _bi = new();
        private readonly List<float> _w = new();
        private readonly List<int>[] _idx;
        public Vector3 Min = new(float.MaxValue), Max = new(float.MinValue);

        public MeshGen(BoneDef[] bones, Func<int, int> childOf)
        {
            _bones = bones; _childOf = childOf;
            _idx = new List<int>[Enum.GetValues<RigMat>().Length];
            for (int i = 0; i < _idx.Length; i++) _idx[i] = new List<int>();
        }

        private int B(string n) => Array.FindIndex(_bones, b => b.Name == n);

        private void V(Vector3 pos, Vector3 norm, Vector2 uv, int bone, float t, RigMat mat)
        {
            int parent = _bones[bone].Parent;
            int child = _childOf(bone);
            int[] bi = { bone, parent >= 0 ? parent : bone, child >= 0 ? child : bone, bone };
            float[] w = { 1f, 0f, 0f, 0f };
            if (parent >= 0 && t < .22f) { float f = (.22f - t) / .22f * .48f; w[0] = 1f - f; w[1] = f; }
            else if (child >= 0 && t > .82f) { float f = (t - .82f) / .18f * .48f; w[0] = 1f - f; w[2] = f; }

            _p.Add(pos); _n.Add(norm); _uv.Add(uv);
            for (int k = 0; k < 4; k++) { _bi.Add(bi[k]); _w.Add(w[k]); }
            Min = Vector3.Min(Min, pos); Max = Vector3.Max(Max, pos);
            _ = mat;
        }

        private void Tri(int a, int b, int c, RigMat mat) { _idx[(int)mat].Add(a); _idx[(int)mat].Add(b); _idx[(int)mat].Add(c); }

        public void Cyl(string bone, float from, float to, float r0, float r1, RigMat mat, int seg = 10)
        {
            int b = B(bone);
            var head = _bones[b].Head; var tail = _bones[b].Tail;
            Vector3 ax = Mx.Norm(tail - head);
            if (ax.LengthSquared() < .5f) ax = Vector3.UnitY;
            Vector3 reference = MathF.Abs(ax.Y) > .9f ? Vector3.UnitX : Vector3.UnitY;
            Vector3 u = Mx.Norm(Vector3.Cross(reference, ax));
            Vector3 v = Vector3.Cross(ax, u);
            Vector3 p0 = head + (tail - head) * from, p1 = head + (tail - head) * to;
            int start = _p.Count;
            int rings = 3;
            for (int j = 0; j <= rings; j++)
            {
                float s = j / (float)rings;
                float t = Mx.Lerp(from, to, s);
                Vector3 c = Mx.Lerp(p0, p1, s);
                float rr = Mx.Lerp(r0, r1, s);
                for (int i = 0; i <= seg; i++)
                {
                    float a = i / (float)seg * MathF.PI * 2f;
                    Vector3 dir = u * MathF.Cos(a) + v * MathF.Sin(a);
                    V(c + dir * rr, dir, new Vector2(i / (float)seg, t), b, t, mat);
                }
            }
            for (int j = 0; j < rings; j++)
                for (int i = 0; i < seg; i++)
                {
                    int a = start + j * (seg + 1) + i, c = a + 1, d = a + (seg + 1), e = d + 1;
                    Tri(a, d, c, mat); Tri(c, d, e, mat);
                }
            // rounded-ish end caps keep limbs looking connected at joints
            foreach (var (center, t, normal) in new[] { (p0, from, -ax), (p1, to, ax) })
            {
                int ci = _p.Count;
                V(center, normal, new Vector2(.5f, .5f), b, t, mat);
                int ring = _p.Count;
                float rr = t <= from ? r0 : r1;
                for (int i = 0; i <= seg; i++)
                {
                    float a = i / (float)seg * MathF.PI * 2f;
                    Vector3 dir = u * MathF.Cos(a) + v * MathF.Sin(a);
                    V(center + dir * rr, normal, new Vector2(.5f + MathF.Cos(a) * .5f, .5f + MathF.Sin(a) * .5f), b, t, mat);
                }
                for (int i = 0; i < seg; i++)
                    if (t <= from) Tri(ci, ring + i + 1, ring + i, mat);
                    else Tri(ci, ring + i, ring + i + 1, mat);
            }
        }

        private static readonly Vector3[] FaceN = { Vector3.UnitX, -Vector3.UnitX, Vector3.UnitY, -Vector3.UnitY, Vector3.UnitZ, -Vector3.UnitZ };
        private static readonly Vector3[][] FaceU =
        {
            new[]{ Vector3.UnitZ, Vector3.UnitY }, new[]{ -Vector3.UnitZ, Vector3.UnitY },
            new[]{ Vector3.UnitX, -Vector3.UnitZ }, new[]{ Vector3.UnitX, Vector3.UnitZ },
            new[]{ Vector3.UnitX, -Vector3.UnitY }, new[]{ -Vector3.UnitX, -Vector3.UnitY },
        };

        public void Box(string bone, Vector3 center, Vector3 half, RigMat mat)
        {
            int b = B(bone);
            for (int f = 0; f < 6; f++)
            {
                Vector3 nrm = FaceN[f], u = FaceU[f][0], v = FaceU[f][1];
                Vector3 c = center + nrm * (MathF.Abs(nrm.X) * half.X + MathF.Abs(nrm.Y) * half.Y + MathF.Abs(nrm.Z) * half.Z);
                Vector3 du = u * (MathF.Abs(u.X) * half.X + MathF.Abs(u.Y) * half.Y + MathF.Abs(u.Z) * half.Z);
                Vector3 dv = v * (MathF.Abs(v.X) * half.X + MathF.Abs(v.Y) * half.Y + MathF.Abs(v.Z) * half.Z);
                int s = _p.Count;
                float t = Mx.Clamp((c.Y - _bones[b].Head.Y) / MathF.Max(.01f, (_bones[b].Tail - _bones[b].Head).Length()), 0f, 1f);
                V(c - du - dv, nrm, new Vector2(0, 0), b, t, mat);
                V(c + du - dv, nrm, new Vector2(1, 0), b, t, mat);
                V(c + du + dv, nrm, new Vector2(1, 1), b, t, mat);
                V(c - du + dv, nrm, new Vector2(0, 1), b, t, mat);
                Tri(s, s + 1, s + 2, mat); Tri(s, s + 2, s + 3, mat);
            }
        }

        public void Sphere(string bone, Vector3 center, float radius, RigMat mat, int lat = 10, int lon = 14,
                           bool upperOnly = false, float upperFraction = .55f)
        {
            int b = B(bone);
            int rings = Math.Max(3, upperOnly ? (int)(lat * upperFraction) + 1 : lat);
            float maxPhi = upperOnly ? MathF.PI * .5f * (1f + (1f - upperFraction)) : MathF.PI;
            int start = _p.Count;
            for (int j = 0; j <= rings; j++)
            {
                float phi = j / (float)rings * maxPhi;
                for (int i = 0; i <= lon; i++)
                {
                    float theta = i / (float)lon * MathF.PI * 2f;
                    Vector3 n = new(MathF.Sin(phi) * MathF.Cos(theta), MathF.Cos(phi), MathF.Sin(phi) * MathF.Sin(theta));
                    float t = Mx.Clamp(.5f + n.Y * .5f, 0f, 1f);
                    V(center + n * radius, n, new Vector2(i / (float)lon, j / (float)rings), b, t, mat);
                }
            }
            for (int j = 0; j < rings; j++)
                for (int i = 0; i < lon; i++)
                {
                    int a = start + j * (lon + 1) + i, c = a + 1, d = a + (lon + 1), e = d + 1;
                    Tri(a, d, c, mat); Tri(c, d, e, mat);
                }
        }

        public RigGeometry Finish()
        {
            var geo = new RigGeometry
            {
                Positions = _p.ToArray(), Normals = _n.ToArray(), Uvs = _uv.ToArray(),
                BoneIndices = _bi.ToArray(), Weights = _w.ToArray(),
                Indices = new int[_idx.Length][]
            };
            var order = new List<int>();
            for (int i = 0; i < _idx.Length; i++)
            {
                geo.Indices[i] = _idx[i].ToArray();
                if (geo.Indices[i].Length > 0) order.Add(i);
            }
            geo.SurfaceMaterials = order.ToArray();
            return geo;
        }
    }
}
