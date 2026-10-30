using System;
using System.Collections.Generic;
using MarioKart64.Audio;
using MarioKart64.Core;

namespace MarioKart64.Tracks
{
    public enum CourseId
    {
        // Mushroom Cup (0..3)
        LuigiRaceway = 0,
        MooMooFarm = 1,
        KoopaTroopaBeach = 2,
        KalimariDesert = 3,

        // Flower Cup (4..7)
        ToadsTurnpike = 4,
        FrappeSnowland = 5,
        ChocoMountain = 6,
        MarioRaceway = 7,

        // Star Cup (8..11)
        WarioStadium = 8,
        SherbetLand = 9,
        RoyalRaceway = 10,
        BowsersCastle = 11,

        // Special Cup (12..15)
        DKsJungleParkway = 12,
        YoshiValley = 13,
        BansheeBoardwalk = 14,
        RainbowRoad = 15,

        // Battle Courses (16..19)
        BigDonut = 16,
        BlockFort = 17,
        DoubleDeck = 18,
        Skyscraper = 19
    }

    public enum SurfaceType
    {
        Asphalt = 0,
        Dirt = 1,
        Sand = 2,
        Snow = 3,
        Ice = 4,
        WoodPlanks = 5,
        CastleStone = 6,
        RainbowNeon = 7,
        OffRoadGrass = 8,
        OffRoadSand = 9,
        OffRoadSnow = 10,
        OffRoadMud = 11,
        BoostPad = 12
    }

    public enum EdgeBehavior
    {
        OffRoadShoulder = 0, // Curb -> Offroad grass/sand/snow -> outer perimeter wall
        Guardrail = 1,       // Low rail right at road edge
        SolidWall = 2,       // High rock/brick/fortress wall at road edge
        WaterDrop = 3,       // Plunge into water below
        LavaDrop = 4,        // Plunge into lava below
        AbyssDrop = 5,       // Plunge into void/canyon
        CliffToLower = 6     // Drop off ledge (falls naturally onto lower road if below, or Lakitu if below floor)
    }

    [Flags]
    public enum SegmentFlags
    {
        None = 0,
        Tunnel = 1,
        Bridge = 2,
        BoostPad = 4,
        JumpRamp = 8,
        CheckerFinish = 16,
        MogulBumps = 32
    }

    public struct ControlNode
    {
        public Vec3 Pos;
        public float HalfWidth;
        public float BankDeg;
        public EdgeBehavior LeftEdge;
        public EdgeBehavior RightEdge;
        public SegmentFlags Flags;

        public ControlNode(float x, float y, float z, float halfWidth, float bankDeg, EdgeBehavior left, EdgeBehavior right, SegmentFlags flags)
        {
            Pos = new Vec3(x, y, z);
            HalfWidth = halfWidth;
            BankDeg = bankDeg;
            LeftEdge = left;
            RightEdge = right;
            Flags = flags;
        }

        public ControlNode(float x, float y, float z, float halfWidth)
        {
            Pos = new Vec3(x, y, z);
            HalfWidth = halfWidth;
            BankDeg = 0f;
            LeftEdge = EdgeBehavior.OffRoadShoulder;
            RightEdge = EdgeBehavior.OffRoadShoulder;
            Flags = SegmentFlags.None;
        }
    }

    public struct TrackSegment
    {
        public int Index;
        public Vec3 Center;
        public Vec3 Forward;
        public Vec3 Right;
        public Vec3 Up;
        public float HalfWidth;
        public float BankRad;
        public float CumulativeDist;
        public float SegmentLength;
        public SurfaceType RoadSurface;
        public SurfaceType OffRoadSurface;
        public EdgeBehavior LeftEdge;
        public EdgeBehavior RightEdge;
        public SegmentFlags Flags;
    }

    public class BranchSpline
    {
        public string Name;
        public int StartMainSegment;
        public int EndMainSegment;
        public SurfaceType Surface = SurfaceType.Dirt;
        public TrackSegment[] Segments;
        public bool IsShortcut;
    }

    public enum PropKind
    {
        TreeRound = 0,
        TreePine = 1,
        TreePalm = 2,
        Cactus = 3,
        MooMooCow = 4,
        RedBarn = 5,
        LuigiJumbotron = 6,
        HotAirBalloon = 7,
        KoopaRock = 8,
        GiantMushroom = 9,
        WarpPipeArch = 10,
        SnowMarioStatue = 11,
        PeachCastle = 12,
        BowserStatue = 13,
        HauntedHouse = 14,
        NeonConstellation = 15,
        Grandstand = 16,
        StreetLight = 17,
        RailCrossingGate = 18,
        TorchPillar = 19
    }

    public struct TrackProp
    {
        public PropKind Kind;
        public Vec3 Position;
        public float YawRad;
        public float Scale;
        public Color4 Tint;

        public TrackProp(PropKind kind, Vec3 pos, float yawRad, float scale, Color4 tint)
        {
            Kind = kind;
            Position = pos;
            YawRad = yawRad;
            Scale = scale;
            Tint = tint;
        }
    }

    public struct ItemBoxSpawn
    {
        public Vec3 Position;
        public float RespawnTimer;
        public bool Active;
        public bool AttachedToBalloon;
    }

    public enum HazardKind
    {
        KalimariTrain = 0,
        HighwayTruck = 1,
        HighwayBus = 2,
        HighwayCar = 3,
        MontyMole = 4,
        SnowmanMine = 5,
        FallingBoulder = 6,
        SlidingPenguin = 7,
        StompingThwomp = 8,
        GiantYoshiEgg = 9,
        SwoopingBat = 10,
        ChainChomp = 11,
        LeapingCheepCheep = 12
    }

    public struct HazardSpawnSpec
    {
        public HazardKind Kind;
        public Vec3 BasePos;
        public int SegmentIndex;
        public float Speed;
        public float PhaseOffset;
        public float PatrolRadius;
        public Vec3[] CustomLoop;
    }

    // Multi-level Battle Arena geometry primitives
    public struct ArenaPlatform
    {
        public Vec3 Min;
        public Vec3 Max;
        public Color4 Color;
        public SurfaceType Surface;
        public bool IsSolidWall;
        public bool IsHazardFloor; // Lava / Water / Abyss
    }

    public struct ArenaRamp
    {
        public Vec3 StartCenter;
        public Vec3 EndCenter;
        public float HalfWidth;
        public Color4 Color;
    }

    public struct SurfaceQueryResult
    {
        public bool FoundRoad;
        public int SegmentIndex;
        public int BranchIndex; // -1 = main spline, >=0 = branch
        public float GroundY;
        public Vec3 RoadNormal;
        public Vec3 RoadForward;
        public float LateralOffset; // Signed distance from road center (+Right, -Left)
        public float RoadHalfWidth;
        public SurfaceType Surface;
        public EdgeBehavior TriggeredEdge;
        public SegmentFlags Flags;
        public bool HitSolidWall;
        public Vec3 WallPushNormal;
        public float WallPenetration;
        public bool FellInLiquidOrVoid;
        public bool LiquidIsLava;
        public bool LiquidIsIceWater;
    }

    public class TrackData
    {
        public CourseId Id;
        public string Name;
        public string CupName;
        public bool IsBattleArena;
        public bool IsMirrored;
        public bool HideRankingsQuestionMark; // Authentic Yoshi Valley "?" feature!
        public int LapCount = 3;

        // Visual Atmosphere
        public Color4 SkyTopColor = Color4.FromBytes(45, 125, 235);
        public Color4 SkyHorizonColor = Color4.FromBytes(165, 215, 255);
        public Color4 GroundPlaneColor = Color4.FromBytes(48, 148, 52);
        public Color4 CurbColorA = Color4.FromBytes(230, 35, 35);
        public Color4 CurbColorB = Color4.FromBytes(245, 245, 245);
        public Color4 WallColor = Color4.FromBytes(130, 125, 120);
        public Color4 FogColor = Color4.FromBytes(175, 215, 250);
        public float FogStart = 180f;
        public float FogEnd = 520f;
        public bool HasWaterPlane = false;
        public bool HasLavaPlane = false;
        public bool HasVoidAbyss = false;
        public bool IsNightSky = false;
        public bool IsSnowing = false;
        public bool IsIceWater = false;
        public float LiquidPlaneY = -4.5f;
        public MusicTrackId Music = MusicTrackId.RacewayCircuit;

        // Compiled Geometry
        public TrackSegment[] Segments;
        public float TotalLength;
        public List<BranchSpline> Branches = new List<BranchSpline>();
        public List<ItemBoxSpawn> ItemBoxes = new List<ItemBoxSpawn>();
        public List<TrackProp> Props = new List<TrackProp>();
        public List<HazardSpawnSpec> HazardSpecs = new List<HazardSpawnSpec>();

        // Battle Arena Geometry & Spawns
        public List<ArenaPlatform> ArenaPlatforms = new List<ArenaPlatform>();
        public List<ArenaRamp> ArenaRamps = new List<ArenaRamp>();
        public Vec3[] BattleSpawnPositions;
        public float[] BattleSpawnYaws;

        public void BuildClosedSpline(
            ControlNode[] nodes,
            int subdivisionsPerNode,
            SurfaceType mainSurface,
            SurfaceType offRoadSurface,
            bool mirror)
        {
            IsMirrored = mirror;
            // In OpenGL right-handed world space (+Z = North/Forward, +Y = Up), East/Right is -X!
            // Negating map X in Normal mode ensures ControlNode(+X, Y, +Z) places +X on the driver's RIGHT!
            float mSign = mirror ? 1f : -1f;
            float bankSign = mirror ? -1f : 1f;
            int n = nodes.Length;
            int totalSegs = n * subdivisionsPerNode;
            Segments = new TrackSegment[totalSegs];

            Vec3[] rawCenters = new Vec3[totalSegs];
            float[] rawHalfW = new float[totalSegs];
            float[] rawBank = new float[totalSegs];
            EdgeBehavior[] rawLeft = new EdgeBehavior[totalSegs];
            EdgeBehavior[] rawRight = new EdgeBehavior[totalSegs];
            SegmentFlags[] rawFlags = new SegmentFlags[totalSegs];

            int idx = 0;
            for (int i = 0; i < n; i++)
            {
                ControlNode n0 = nodes[(i - 1 + n) % n];
                ControlNode n1 = nodes[i];
                ControlNode n2 = nodes[(i + 1) % n];
                ControlNode n3 = nodes[(i + 2) % n];

                Vec3 p0 = new Vec3(n0.Pos.X * mSign, n0.Pos.Y, n0.Pos.Z);
                Vec3 p1 = new Vec3(n1.Pos.X * mSign, n1.Pos.Y, n1.Pos.Z);
                Vec3 p2 = new Vec3(n2.Pos.X * mSign, n2.Pos.Y, n2.Pos.Z);
                Vec3 p3 = new Vec3(n3.Pos.X * mSign, n3.Pos.Y, n3.Pos.Z);

                for (int s = 0; s < subdivisionsPerNode; s++)
                {
                    float t = s / (float)subdivisionsPerNode;
                    rawCenters[idx] = Vec3.CatmullRom(p0, p1, p2, p3, t);
                    rawHalfW[idx] = MathUtil.CatmullRomScalar(n0.HalfWidth, n1.HalfWidth, n2.HalfWidth, n3.HalfWidth, t);
                    if (rawHalfW[idx] < 4.5f) rawHalfW[idx] = 4.5f;

                    float bankDeg = MathUtil.Lerp(n1.BankDeg, n2.BankDeg, t) * bankSign;
                    rawBank[idx] = bankDeg * MathUtil.DEG2RAD;

                    ControlNode refNode = (t < 0.5f) ? n1 : n2;
                    rawLeft[idx] = mirror ? refNode.RightEdge : refNode.LeftEdge;
                    rawRight[idx] = mirror ? refNode.LeftEdge : refNode.RightEdge;
                    rawFlags[idx] = n1.Flags;
                    if (i == 0 && s < 3) rawFlags[idx] |= SegmentFlags.CheckerFinish;

                    // Optional Wario Stadium style mogul waves
                    if ((rawFlags[idx] & SegmentFlags.MogulBumps) != 0)
                    {
                        rawCenters[idx].Y += (float)Math.Sin(t * MathUtil.TWO_PI * 2.0f) * 1.45f;
                    }

                    idx++;
                }
            }

            float cumDist = 0f;
            for (int i = 0; i < totalSegs; i++)
            {
                Vec3 prev = rawCenters[(i - 1 + totalSegs) % totalSegs];
                Vec3 curr = rawCenters[i];
                Vec3 next = rawCenters[(i + 1) % totalSegs];

                Vec3 fwd = (next - prev).Normalized();
                if (fwd.LengthSq < 1e-6f) fwd = Vec3.Forward;

                Vec3 flatRight = Vec3.Cross(Vec3.Up, fwd).Normalized();
                if (flatRight.LengthSq < 1e-6f) flatRight = Vec3.Right;

                // Note: In right-handed OpenGL (X right, Y up, Z out-of-screen/-Z forward):
                // Let's keep consistent Right vector: Cross(fwd, Up) points to the driver's RIGHT side!
                Vec3 right = Vec3.Cross(fwd, Vec3.Up).Normalized();
                if (right.LengthSq < 1e-6f) right = Vec3.Right;
                Vec3 baseUp = Vec3.Cross(right, fwd).Normalized();

                float b = rawBank[i];
                float cb = (float)Math.Cos(b);
                float sb = (float)Math.Sin(b);
                Vec3 bankedRight = (right * cb + baseUp * sb).Normalized();
                Vec3 bankedUp = Vec3.Cross(bankedRight, fwd).Normalized();

                float segLen = (next - curr).Length;
                TrackSegment seg = new TrackSegment();
                seg.Index = i;
                seg.Center = curr;
                seg.Forward = fwd;
                seg.Right = bankedRight;
                seg.Up = bankedUp;
                seg.HalfWidth = rawHalfW[i];
                seg.BankRad = b;
                seg.CumulativeDist = cumDist;
                seg.SegmentLength = Math.Max(0.1f, segLen);
                seg.RoadSurface = ((rawFlags[i] & SegmentFlags.BoostPad) != 0) ? SurfaceType.BoostPad : mainSurface;
                seg.OffRoadSurface = offRoadSurface;
                seg.LeftEdge = rawLeft[i];
                seg.RightEdge = rawRight[i];
                seg.Flags = rawFlags[i];

                Segments[i] = seg;
                cumDist += seg.SegmentLength;
            }
            TotalLength = cumDist;
        }

        public BranchSpline AddBranchSpline(
            string name,
            int startMainSeg,
            int endMainSeg,
            ControlNode[] branchNodes,
            int subdivisions,
            SurfaceType surface,
            bool isShortcut)
        {
            float mSign = IsMirrored ? 1f : -1f;
            int n = branchNodes.Length;
            int total = (n - 1) * subdivisions + 1;
            TrackSegment[] segs = new TrackSegment[total];

            Vec3[] pts = new Vec3[total];
            float[] hw = new float[total];
            EdgeBehavior[] lEdge = new EdgeBehavior[total];
            EdgeBehavior[] rEdge = new EdgeBehavior[total];
            SegmentFlags[] flg = new SegmentFlags[total];

            int k = 0;
            for (int i = 0; i < n - 1; i++)
            {
                ControlNode n0 = branchNodes[Math.Max(0, i - 1)];
                ControlNode n1 = branchNodes[i];
                ControlNode n2 = branchNodes[i + 1];
                ControlNode n3 = branchNodes[Math.Min(n - 1, i + 2)];

                Vec3 p0 = new Vec3(n0.Pos.X * mSign, n0.Pos.Y, n0.Pos.Z);
                Vec3 p1 = new Vec3(n1.Pos.X * mSign, n1.Pos.Y, n1.Pos.Z);
                Vec3 p2 = new Vec3(n2.Pos.X * mSign, n2.Pos.Y, n2.Pos.Z);
                Vec3 p3 = new Vec3(n3.Pos.X * mSign, n3.Pos.Y, n3.Pos.Z);

                int steps = (i == n - 2) ? subdivisions + 1 : subdivisions;
                for (int s = 0; s < steps; s++)
                {
                    float t = s / (float)subdivisions;
                    pts[k] = Vec3.CatmullRom(p0, p1, p2, p3, t);
                    hw[k] = Math.Max(4.5f, MathUtil.Lerp(n1.HalfWidth, n2.HalfWidth, t));
                    lEdge[k] = IsMirrored ? n1.RightEdge : n1.LeftEdge;
                    rEdge[k] = IsMirrored ? n1.LeftEdge : n1.RightEdge;
                    flg[k] = n1.Flags;
                    k++;
                }
            }

            float dist = 0f;
            for (int i = 0; i < total; i++)
            {
                Vec3 prev = pts[Math.Max(0, i - 1)];
                Vec3 next = pts[Math.Min(total - 1, i + 1)];
                Vec3 fwd = (next - prev).Normalized();
                if (fwd.LengthSq < 1e-6f) fwd = Vec3.Forward;
                Vec3 right = Vec3.Cross(fwd, Vec3.Up).Normalized();
                if (right.LengthSq < 1e-6f) right = Vec3.Right;
                Vec3 up = Vec3.Cross(right, fwd).Normalized();

                float sLen = (i < total - 1) ? (pts[i + 1] - pts[i]).Length : 1.0f;
                TrackSegment seg = new TrackSegment();
                seg.Index = i;
                seg.Center = pts[i];
                seg.Forward = fwd;
                seg.Right = right;
                seg.Up = up;
                seg.HalfWidth = hw[i];
                seg.CumulativeDist = dist;
                seg.SegmentLength = Math.Max(0.1f, sLen);
                seg.RoadSurface = ((flg[i] & SegmentFlags.BoostPad) != 0) ? SurfaceType.BoostPad : surface;
                seg.OffRoadSurface = SurfaceType.OffRoadGrass;
                seg.LeftEdge = lEdge[i];
                seg.RightEdge = rEdge[i];
                seg.Flags = flg[i];
                segs[i] = seg;
                dist += seg.SegmentLength;
            }

            BranchSpline branch = new BranchSpline();
            branch.Name = name;
            branch.StartMainSegment = MathUtil.ClampInt(startMainSeg, 0, Segments.Length - 1);
            branch.EndMainSegment = MathUtil.ClampInt(endMainSeg, 0, Segments.Length - 1);
            branch.Surface = surface;
            branch.Segments = segs;
            branch.IsShortcut = isShortcut;
            Branches.Add(branch);
            return branch;
        }

        public void AddItemBoxRow(int segmentIndex, int boxCount, float spreadRatio = 0.68f)
        {
            if (Segments == null || Segments.Length == 0) return;
            int idx = ((segmentIndex % Segments.Length) + Segments.Length) % Segments.Length;
            TrackSegment seg = Segments[idx];
            for (int i = 0; i < boxCount; i++)
            {
                float t = (boxCount == 1) ? 0f : (-1f + 2f * i / (float)(boxCount - 1));
                float lat = t * seg.HalfWidth * spreadRatio;
                ItemBoxSpawn box = new ItemBoxSpawn();
                box.Position = seg.Center + seg.Right * lat + new Vec3(0f, 1.55f, 0f);
                box.Active = true;
                box.RespawnTimer = 0f;
                box.AttachedToBalloon = false;
                ItemBoxes.Add(box);
            }
        }

        public void AddBranchItemBoxes(BranchSpline branch, int branchSegIdx, int count)
        {
            if (branch == null || branch.Segments == null || branch.Segments.Length == 0) return;
            int idx = MathUtil.ClampInt(branchSegIdx, 0, branch.Segments.Length - 1);
            TrackSegment seg = branch.Segments[idx];
            for (int i = 0; i < count; i++)
            {
                float t = (count == 1) ? 0f : (-0.6f + 1.2f * i / (float)(count - 1));
                ItemBoxSpawn box = new ItemBoxSpawn();
                box.Position = seg.Center + seg.Right * (t * seg.HalfWidth) + new Vec3(0f, 1.55f, 0f);
                box.Active = true;
                ItemBoxes.Add(box);
            }
        }

        public void AddPropAtSegment(int segmentIndex, float lateralDist, float yOffset, PropKind kind, float scale, Color4 tint, float yawOffset = 0f)
        {
            if (Segments == null || Segments.Length == 0) return;
            int idx = ((segmentIndex % Segments.Length) + Segments.Length) % Segments.Length;
            TrackSegment seg = Segments[idx];
            float lat = IsMirrored ? -lateralDist : lateralDist;
            Vec3 pos = seg.Center + seg.Right * lat + new Vec3(0f, yOffset, 0f);
            float yaw = (float)Math.Atan2(seg.Forward.X, seg.Forward.Z) + yawOffset;
            Props.Add(new TrackProp(kind, pos, yaw, scale, tint));
        }

        public SurfaceQueryResult SampleSurface(Vec3 pos, int hintSegmentIndex)
        {
            if (IsBattleArena)
            {
                return SampleBattleArena(pos);
            }

            SurfaceQueryResult res = new SurfaceQueryResult();
            res.RoadNormal = Vec3.Up;
            res.RoadForward = Vec3.Forward;
            res.BranchIndex = -1;

            int count = Segments.Length;
            int bestIdx = 0;
            float bestScore = float.MaxValue;

            // 1. Local search around hintSegmentIndex to preserve overpass/underpass continuity
            int searchWindow = 32;
            if (hintSegmentIndex >= 0 && hintSegmentIndex < count)
            {
                for (int d = -searchWindow; d <= searchWindow; d++)
                {
                    int i = ((hintSegmentIndex + d) % count + count) % count;
                    TrackSegment s = Segments[i];
                    float hDistSq = Vec3.DistanceXZSq(pos, s.Center);
                    float dy = pos.Y - s.Center.Y;
                    // Prevent snapping UP onto a high bridge overhead if kart is underneath
                    float vPenalty = (dy < -4.2f) ? 4500f + dy * dy * 40f : dy * dy * 3.2f;
                    float score = hDistSq + vPenalty;
                    if (score < bestScore)
                    {
                        bestScore = score;
                        bestIdx = i;
                    }
                }
            }

            // If far from local window, check full track
            if (bestScore > 1400f || hintSegmentIndex < 0)
            {
                for (int i = 0; i < count; i++)
                {
                    TrackSegment s = Segments[i];
                    float hDistSq = Vec3.DistanceXZSq(pos, s.Center);
                    float dy = pos.Y - s.Center.Y;
                    float vPenalty = (dy < -4.2f) ? 4500f + dy * dy * 40f : dy * dy * 3.2f;
                    float score = hDistSq + vPenalty;
                    if (score < bestScore)
                    {
                        bestScore = score;
                        bestIdx = i;
                    }
                }
            }

            TrackSegment chosen = Segments[bestIdx];
            int chosenBranch = -1;

            // 2. Also check Branch Splines (Yoshi Valley paths, Koopa Beach cave, Royal Raceway castle path)
            for (int b = 0; b < Branches.Count; b++)
            {
                BranchSpline br = Branches[b];
                for (int j = 0; j < br.Segments.Length; j++)
                {
                    TrackSegment bs = br.Segments[j];
                    float hDistSq = Vec3.DistanceXZSq(pos, bs.Center);
                    if (hDistSq > (bs.HalfWidth + 8f) * (bs.HalfWidth + 8f)) continue;
                    float dy = pos.Y - bs.Center.Y;
                    if (dy < -4.2f) continue;
                    float score = hDistSq + dy * dy * 3.0f;
                    if (score < bestScore)
                    {
                        bestScore = score;
                        chosen = bs;
                        chosenBranch = b;
                    }
                }
            }

            res.FoundRoad = true;
            res.SegmentIndex = (chosenBranch == -1) ? chosen.Index : Branches[chosenBranch].StartMainSegment;
            res.BranchIndex = chosenBranch;
            res.RoadForward = chosen.Forward;
            res.RoadNormal = chosen.Up;
            res.RoadHalfWidth = chosen.HalfWidth;
            res.Flags = chosen.Flags;

            Vec3 rel = pos - chosen.Center;
            float along = Vec3.Dot(rel, chosen.Forward);
            float lat = Vec3.Dot(rel, chosen.Right);
            res.LateralOffset = lat;

            // Interpolate surface elevation smoothly along forward & banked right
            float roadY = chosen.Center.Y + chosen.Forward.Y * along + chosen.Right.Y * MathUtil.Clamp(lat, -chosen.HalfWidth, chosen.HalfWidth);
            res.GroundY = roadY;

            float absLat = Math.Abs(lat);
            EdgeBehavior edge = (lat < 0f) ? chosen.LeftEdge : chosen.RightEdge;
            float sign = (lat < 0f) ? -1f : 1f;

            if (absLat <= chosen.HalfWidth + 0.9f)
            {
                res.Surface = chosen.RoadSurface;
                res.TriggeredEdge = EdgeBehavior.OffRoadShoulder;
            }
            else
            {
                res.TriggeredEdge = edge;
                switch (edge)
                {
                    case EdgeBehavior.Guardrail:
                    case EdgeBehavior.SolidWall:
                        // Solid barrier right at curb edge
                        if (pos.Y < roadY + 7.5f)
                        {
                            res.HitSolidWall = true;
                            res.WallPushNormal = -chosen.Right * sign;
                            res.WallPenetration = absLat - (chosen.HalfWidth + 0.7f);
                        }
                        res.Surface = chosen.RoadSurface;
                        break;

                    case EdgeBehavior.OffRoadShoulder:
                        res.Surface = chosen.OffRoadSurface;
                        float outerWallDist = chosen.HalfWidth + 18.0f;
                        // Gentle outer embankment slope
                        res.GroundY = roadY + (absLat - chosen.HalfWidth) * 0.04f;
                        if (absLat > outerWallDist)
                        {
                            res.HitSolidWall = true;
                            res.WallPushNormal = -chosen.Right * sign;
                            res.WallPenetration = absLat - outerWallDist;
                        }
                        break;

                    case EdgeBehavior.WaterDrop:
                        res.Surface = chosen.OffRoadSurface;
                        if (absLat > chosen.HalfWidth + 1.4f)
                        {
                            res.GroundY = LiquidPlaneY - 3.0f;
                            if (pos.Y <= LiquidPlaneY + 0.4f)
                            {
                                res.FellInLiquidOrVoid = true;
                                res.LiquidIsIceWater = IsIceWater;
                            }
                        }
                        break;

                    case EdgeBehavior.LavaDrop:
                        res.Surface = SurfaceType.CastleStone;
                        if (absLat > chosen.HalfWidth + 1.2f)
                        {
                            res.GroundY = LiquidPlaneY - 3.0f;
                            if (pos.Y <= LiquidPlaneY + 0.5f)
                            {
                                res.FellInLiquidOrVoid = true;
                                res.LiquidIsLava = true;
                            }
                        }
                        break;

                    case EdgeBehavior.AbyssDrop:
                        res.Surface = chosen.RoadSurface;
                        if (absLat > chosen.HalfWidth + 1.2f)
                        {
                            res.GroundY = -200.0f;
                            if (pos.Y < chosen.Center.Y - 14.0f)
                            {
                                res.FellInLiquidOrVoid = true;
                            }
                        }
                        break;

                    case EdgeBehavior.CliffToLower:
                        // Choco Mountain cliff: drops down naturally; if lower road catches kart on next frame, kart keeps driving!
                        res.Surface = SurfaceType.Dirt;
                        if (absLat > chosen.HalfWidth + 1.3f)
                        {
                            res.GroundY = -60.0f;
                            if (pos.Y < -22.0f)
                            {
                                res.FellInLiquidOrVoid = true;
                            }
                        }
                        break;
                }
            }

            // Catch global liquid/void plunge
            if ((HasWaterPlane || HasLavaPlane) && pos.Y < LiquidPlaneY - 0.5f)
            {
                res.FellInLiquidOrVoid = true;
                res.LiquidIsLava = HasLavaPlane;
                res.LiquidIsIceWater = IsIceWater;
            }
            if (HasVoidAbyss && pos.Y < -45.0f)
            {
                res.FellInLiquidOrVoid = true;
            }

            return res;
        }

        private SurfaceQueryResult SampleBattleArena(Vec3 pos)
        {
            SurfaceQueryResult res = new SurfaceQueryResult();
            res.FoundRoad = true;
            res.RoadNormal = Vec3.Up;
            res.RoadForward = Vec3.Forward;
            res.Surface = SurfaceType.Asphalt;
            res.GroundY = -120f;

            // Check platforms (highest valid floor at or slightly above kart Y)
            for (int i = 0; i < ArenaPlatforms.Count; i++)
            {
                ArenaPlatform p = ArenaPlatforms[i];
                if (p.IsSolidWall)
                {
                    // Horizontal AABB collision against solid blocks/pillars/outer walls
                    if (pos.Y + 1.5f > p.Min.Y && pos.Y < p.Max.Y)
                    {
                        float expand = 1.35f;
                        if (pos.X > p.Min.X - expand && pos.X < p.Max.X + expand &&
                            pos.Z > p.Min.Z - expand && pos.Z < p.Max.Z + expand)
                        {
                            float dxMin = Math.Abs(pos.X - (p.Min.X - expand));
                            float dxMax = Math.Abs((p.Max.X + expand) - pos.X);
                            float dzMin = Math.Abs(pos.Z - (p.Min.Z - expand));
                            float dzMax = Math.Abs((p.Max.Z + expand) - pos.Z);

                            float minPen = Math.Min(Math.Min(dxMin, dxMax), Math.Min(dzMin, dzMax));
                            res.HitSolidWall = true;
                            res.WallPenetration = minPen;
                            if (minPen == dxMin) res.WallPushNormal = new Vec3(-1f, 0f, 0f);
                            else if (minPen == dxMax) res.WallPushNormal = new Vec3(1f, 0f, 0f);
                            else if (minPen == dzMin) res.WallPushNormal = new Vec3(0f, 0f, -1f);
                            else res.WallPushNormal = new Vec3(0f, 0f, 1f);
                        }
                    }
                    // Also allow driving on top of forts if kart reached top height!
                    if (pos.X >= p.Min.X && pos.X <= p.Max.X && pos.Z >= p.Min.Z && pos.Z <= p.Max.Z)
                    {
                        if (pos.Y >= p.Max.Y - 1.6f && p.Max.Y > res.GroundY)
                        {
                            res.GroundY = p.Max.Y;
                            res.Surface = p.Surface;
                        }
                    }
                    continue;
                }

                if (pos.X >= p.Min.X && pos.X <= p.Max.X && pos.Z >= p.Min.Z && pos.Z <= p.Max.Z)
                {
                    if (p.IsHazardFloor)
                    {
                        if (pos.Y <= p.Max.Y + 0.6f)
                        {
                            res.FellInLiquidOrVoid = true;
                            res.LiquidIsLava = HasLavaPlane;
                        }
                    }
                    else if (pos.Y >= p.Max.Y - 2.4f && p.Max.Y > res.GroundY)
                    {
                        res.GroundY = p.Max.Y;
                        res.Surface = p.Surface;
                    }
                }
            }

            // Check connecting ramps
            for (int i = 0; i < ArenaRamps.Count; i++)
            {
                ArenaRamp r = ArenaRamps[i];
                Vec3 axis = r.EndCenter - r.StartCenter;
                Vec3 axisXZ = new Vec3(axis.X, 0f, axis.Z);
                float lenXZ = axisXZ.Length;
                if (lenXZ < 0.1f) continue;
                Vec3 dirXZ = axisXZ * (1.0f / lenXZ);
                Vec3 rightXZ = new Vec3(dirXZ.Z, 0f, -dirXZ.X);

                Vec3 rel = pos - r.StartCenter;
                float along = rel.X * dirXZ.X + rel.Z * dirXZ.Z;
                float lat = Math.Abs(rel.X * rightXZ.X + rel.Z * rightXZ.Z);
                if (along >= -0.5f && along <= lenXZ + 0.5f && lat <= r.HalfWidth)
                {
                    float t = MathUtil.Clamp(along / lenXZ, 0f, 1f);
                    float rampY = MathUtil.Lerp(r.StartCenter.Y, r.EndCenter.Y, t);
                    if (pos.Y >= rampY - 2.5f && rampY > res.GroundY)
                    {
                        res.GroundY = rampY;
                        res.Surface = SurfaceType.Asphalt;
                    }
                }
            }

            if (pos.Y < -18f)
            {
                res.FellInLiquidOrVoid = true;
                res.LiquidIsLava = HasLavaPlane;
            }

            return res;
        }
    }
}
