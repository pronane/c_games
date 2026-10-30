using System;
using MarioKart64.Audio;
using MarioKart64.Core;

namespace MarioKart64.Tracks
{
    public static class SpecialCupTracks
    {
        public static TrackData CreateDKsJungleParkway(bool mirror)
        {
            TrackData t = new TrackData();
            t.Id = CourseId.DKsJungleParkway;
            t.Name = "D.K.'S JUNGLE PARKWAY";
            t.CupName = "SPECIAL CUP";
            t.Music = MusicTrackId.CastleAndSpooky;
            t.HasWaterPlane = true;
            t.LiquidPlaneY = -3.2f;
            t.SkyTopColor = Color4.FromBytes(38, 132, 92);
            t.SkyHorizonColor = Color4.FromBytes(245, 196, 98);
            t.GroundPlaneColor = Color4.FromBytes(40, 122, 38);
            t.CurbColorA = Color4.FromBytes(152, 96, 42);
            t.CurbColorB = Color4.FromBytes(88, 172, 50);
            t.WallColor = Color4.FromBytes(98, 72, 42);
            t.FogColor = Color4.FromBytes(202, 174, 102);
            t.FogStart = 210f;
            t.FogEnd = 580f;

            // Authentic MK64 DK's Jungle Parkway:
            // Wide Jungle River Curves -> Giant Booster Cannon Jump over Golden River ->
            // Jungle Island Hairpins -> Wooden Suspension Bridge -> Torch-Lit Rock Cave to Finish!
            ControlNode[] nodes = new ControlNode[]
            {
                new ControlNode(   0f,  1.0f,   0f, 18.0f,  0f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.WaterDrop,       SegmentFlags.CheckerFinish),
                new ControlNode(  12f,  2.0f,  94f, 18.5f, -4f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.WaterDrop,       SegmentFlags.None),
                new ControlNode(  72f,  4.2f, 176f, 18.5f, -6f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.OffRoadShoulder, SegmentFlags.None),
                new ControlNode( 168f,  7.2f, 162f, 16.0f,  0f, EdgeBehavior.Guardrail,       EdgeBehavior.Guardrail,       SegmentFlags.BoostPad | SegmentFlags.JumpRamp), // Giant River Cannon Jump!
                new ControlNode( 242f,  2.5f,  86f, 19.5f, -4f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.WaterDrop,       SegmentFlags.None),
                new ControlNode( 192f,  3.2f,  18f, 18.5f,  5f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.OffRoadShoulder, SegmentFlags.None),
                new ControlNode( 238f,  4.8f, -52f, 13.5f,  0f, EdgeBehavior.WaterDrop,       EdgeBehavior.WaterDrop,       SegmentFlags.Bridge), // Wooden Suspension Bridge!
                new ControlNode( 186f,  6.8f,-138f, 17.0f, -5f, EdgeBehavior.SolidWall,       EdgeBehavior.SolidWall,       SegmentFlags.Tunnel), // Torch-Lit Cave!
                new ControlNode(  88f,  8.6f,-162f, 17.0f, -6f, EdgeBehavior.SolidWall,       EdgeBehavior.SolidWall,       SegmentFlags.Tunnel),
                new ControlNode(  18f,  4.5f,-118f, 18.0f, -4f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.WaterDrop,       SegmentFlags.None),
                new ControlNode(  -2f,  1.8f, -62f, 18.0f,  0f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.WaterDrop,       SegmentFlags.None)
            };

            t.BuildClosedSpline(nodes, 28, SurfaceType.Dirt, SurfaceType.OffRoadGrass, mirror);

            t.AddItemBoxRow(34, 5);
            t.AddItemBoxRow(132, 5);
            t.AddItemBoxRow(228, 4);

            for (int s = 10; s < t.Segments.Length; s += 14)
            {
                if ((t.Segments[s].Flags & SegmentFlags.Tunnel) != 0)
                {
                    t.AddPropAtSegment(s, -17.5f, 0f, PropKind.TorchPillar, 1.1f, Color4.FromBytes(255, 145, 35));
                }
                else if ((t.Segments[s].Flags & SegmentFlags.Bridge) == 0)
                {
                    t.AddPropAtSegment(s, -25.0f, 0f, PropKind.TreePalm, 1.45f, Color4.FromBytes(38, 165, 52));
                }
            }

            HazardSpawnSpec fish = new HazardSpawnSpec();
            fish.Kind = HazardKind.LeapingCheepCheep;
            fish.SegmentIndex = 168;
            fish.BasePos = t.Segments[168].Center;
            fish.PatrolRadius = 16f;
            fish.Speed = 2.2f;
            t.HazardSpecs.Add(fish);

            return t;
        }

        public static TrackData CreateYoshiValley(bool mirror)
        {
            TrackData t = new TrackData();
            t.Id = CourseId.YoshiValley;
            t.Name = "YOSHI VALLEY";
            t.CupName = "SPECIAL CUP";
            t.Music = MusicTrackId.CastleAndSpooky;
            t.HideRankingsQuestionMark = true;
            t.HasVoidAbyss = true;
            t.SkyTopColor = Color4.FromBytes(48, 136, 232);
            t.SkyHorizonColor = Color4.FromBytes(198, 232, 185);
            t.GroundPlaneColor = Color4.FromBytes(84, 150, 52);
            t.CurbColorA = Color4.FromBytes(68, 198, 64);
            t.CurbColorB = Color4.FromBytes(245, 242, 225);
            t.WallColor = Color4.FromBytes(148, 112, 72);

            // Authentic MarioWiki Yoshi Valley (772m):
            // Grassy start -> LEFT turn into multi-route canyon maze ->
            // Converging at Giant Spinning Spotted Yoshi Egg Plaza -> Final Canyon Bridge to Finish!
            ControlNode[] nodes = new ControlNode[]
            {
                new ControlNode(   0f,  4.0f,   0f, 16.5f,  0f, EdgeBehavior.Guardrail, EdgeBehavior.Guardrail, SegmentFlags.CheckerFinish | SegmentFlags.Bridge),
                new ControlNode(  -8f,  2.0f,  92f, 15.5f,  2f, EdgeBehavior.AbyssDrop, EdgeBehavior.AbyssDrop, SegmentFlags.Bridge),
                new ControlNode( -68f, -2.0f, 168f, 16.0f,  4f, EdgeBehavior.SolidWall, EdgeBehavior.AbyssDrop, SegmentFlags.None),
                new ControlNode(-158f, -6.0f, 188f, 16.0f,  5f, EdgeBehavior.SolidWall, EdgeBehavior.SolidWall, SegmentFlags.None),
                new ControlNode(-228f, -8.5f, 118f, 14.5f,  0f, EdgeBehavior.AbyssDrop, EdgeBehavior.AbyssDrop, SegmentFlags.Bridge),
                new ControlNode(-196f, -9.5f,  36f, 16.5f, -4f, EdgeBehavior.SolidWall, EdgeBehavior.AbyssDrop, SegmentFlags.None),
                new ControlNode(-228f,-10.5f, -38f, 17.5f,  5f, EdgeBehavior.SolidWall, EdgeBehavior.AbyssDrop, SegmentFlags.None),
                new ControlNode(-152f,-11.0f,-112f, 20.5f,  6f, EdgeBehavior.SolidWall, EdgeBehavior.Guardrail, SegmentFlags.None), // Giant Yoshi Egg Plaza!
                new ControlNode( -62f, -5.0f,-142f, 17.0f,  5f, EdgeBehavior.SolidWall, EdgeBehavior.SolidWall, SegmentFlags.None),
                new ControlNode(   2f,  1.5f, -82f, 16.5f,  0f, EdgeBehavior.Guardrail, EdgeBehavior.Guardrail, SegmentFlags.None)
            };

            t.BuildClosedSpline(nodes, 28, SurfaceType.Dirt, SurfaceType.OffRoadGrass, mirror);

            ControlNode[] branchA = new ControlNode[]
            {
                new ControlNode( -14f,  1.5f, 102f, 12.5f, 0f, EdgeBehavior.AbyssDrop, EdgeBehavior.AbyssDrop, SegmentFlags.Bridge),
                new ControlNode(  28f, -1.0f, 156f, 11.5f, 0f, EdgeBehavior.AbyssDrop, EdgeBehavior.AbyssDrop, SegmentFlags.Bridge),
                new ControlNode( -38f, -4.5f, 208f, 13.0f, 0f, EdgeBehavior.SolidWall, EdgeBehavior.SolidWall, SegmentFlags.None),
                new ControlNode(-142f, -6.0f, 188f, 14.0f, 0f, EdgeBehavior.SolidWall, EdgeBehavior.SolidWall, SegmentFlags.None)
            };
            BranchSpline b1 = t.AddBranchSpline("YoshiLeftBridge", 32, 86, branchA, 12, SurfaceType.WoodPlanks, true);
            t.AddBranchItemBoxes(b1, 16, 2);

            ControlNode[] branchB = new ControlNode[]
            {
                new ControlNode( -74f, -2.2f, 164f, 12.5f, 0f, EdgeBehavior.AbyssDrop, EdgeBehavior.AbyssDrop, SegmentFlags.Bridge),
                new ControlNode(-128f, -5.5f, 112f, 12.0f, 0f, EdgeBehavior.AbyssDrop, EdgeBehavior.AbyssDrop, SegmentFlags.Bridge),
                new ControlNode(-168f, -8.5f,  52f, 13.5f, 0f, EdgeBehavior.SolidWall, EdgeBehavior.AbyssDrop, SegmentFlags.None),
                new ControlNode(-196f, -9.5f,  32f, 15.0f, 0f, EdgeBehavior.SolidWall, EdgeBehavior.AbyssDrop, SegmentFlags.None)
            };
            BranchSpline b2 = t.AddBranchSpline("YoshiCanyonShortcut", 58, 142, branchB, 12, SurfaceType.WoodPlanks, true);
            t.AddBranchItemBoxes(b2, 18, 2);

            t.AddItemBoxRow(40, 4);
            t.AddItemBoxRow(124, 4);
            t.AddItemBoxRow(215, 5);

            TrackSegment eggSeg = t.Segments[196];
            HazardSpawnSpec egg = new HazardSpawnSpec();
            egg.Kind = HazardKind.GiantYoshiEgg;
            egg.BasePos = eggSeg.Center;
            egg.SegmentIndex = 196;
            egg.PatrolRadius = 11.5f;
            egg.Speed = 2.1f;
            t.HazardSpecs.Add(egg);

            for (int s = 50; s < t.Segments.Length; s += 20)
            {
                if ((t.Segments[s].Flags & SegmentFlags.Bridge) == 0)
                    t.AddPropAtSegment(s, -22f, 0f, PropKind.TreePine, 1.25f, Color4.FromBytes(58, 155, 62));
            }

            return t;
        }

        public static TrackData CreateBansheeBoardwalk(bool mirror)
        {
            TrackData t = new TrackData();
            t.Id = CourseId.BansheeBoardwalk;
            t.Name = "BANSHEE BOARDWALK";
            t.CupName = "SPECIAL CUP";
            t.Music = MusicTrackId.CastleAndSpooky;
            t.IsNightSky = true;
            t.HasWaterPlane = true;
            t.LiquidPlaneY = -3.5f;
            t.SkyTopColor = Color4.FromBytes(6, 6, 18);
            t.SkyHorizonColor = Color4.FromBytes(28, 20, 52);
            t.GroundPlaneColor = Color4.FromBytes(12, 18, 32);
            t.CurbColorA = Color4.FromBytes(112, 78, 48);
            t.CurbColorB = Color4.FromBytes(78, 55, 36);
            t.WallColor = Color4.FromBytes(68, 52, 72);
            t.FogColor = Color4.FromBytes(16, 14, 32);
            t.FogStart = 145f;
            t.FogEnd = 460f;

            // Authentic MarioWiki Banshee Boardwalk (747m):
            // 90-deg LEFT -> 90-deg RIGHT + 45-deg RIGHT -> sharp 135-deg LEFT onto Cheep-Cheep Pier ->
            // S-Chicane + Broken Guardrail Sections -> Bat-Filled Haunted Building -> Finish!
            ControlNode[] nodes = new ControlNode[]
            {
                new ControlNode(   0f, 1.5f,   0f, 15.5f, 0f, EdgeBehavior.Guardrail, EdgeBehavior.Guardrail, SegmentFlags.CheckerFinish | SegmentFlags.Bridge),
                new ControlNode(   0f, 1.5f,  94f, 15.0f, 0f, EdgeBehavior.WaterDrop, EdgeBehavior.Guardrail, SegmentFlags.Bridge),
                new ControlNode( -68f, 2.0f, 148f, 15.0f, 0f, EdgeBehavior.Guardrail, EdgeBehavior.WaterDrop, SegmentFlags.Bridge), // 90-deg Left!
                new ControlNode( -58f, 2.5f, 224f, 15.0f, 0f, EdgeBehavior.WaterDrop, EdgeBehavior.Guardrail, SegmentFlags.Bridge), // 90-deg Right!
                new ControlNode(-158f, 2.0f, 198f, 15.5f, 0f, EdgeBehavior.Guardrail, EdgeBehavior.WaterDrop, SegmentFlags.Bridge), // Cheep-Cheep Pier!
                new ControlNode(-204f, 1.8f,  98f, 15.0f, 0f, EdgeBehavior.WaterDrop, EdgeBehavior.WaterDrop, SegmentFlags.Bridge), // Missing Rails!
                new ControlNode(-168f, 2.8f,   8f, 17.5f, 0f, EdgeBehavior.SolidWall, EdgeBehavior.SolidWall, SegmentFlags.Tunnel), // Haunted Bat Mansion!
                new ControlNode(-124f, 2.8f, -82f, 17.5f, 0f, EdgeBehavior.SolidWall, EdgeBehavior.SolidWall, SegmentFlags.Tunnel),
                new ControlNode( -56f, 1.5f,-148f, 15.0f, 0f, EdgeBehavior.WaterDrop, EdgeBehavior.Guardrail, SegmentFlags.Bridge),
                new ControlNode(   2f, 1.5f, -84f, 15.5f, 0f, EdgeBehavior.Guardrail, EdgeBehavior.Guardrail, SegmentFlags.Bridge)
            };

            t.BuildClosedSpline(nodes, 28, SurfaceType.WoodPlanks, SurfaceType.WoodPlanks, mirror);

            t.AddItemBoxRow(34, 4);
            t.AddItemBoxRow(112, 4);
            t.AddItemBoxRow(205, 4);

            t.AddPropAtSegment(168, 0f, 0f, PropKind.HauntedHouse, 1.85f, Color4.FromBytes(88, 68, 98));
            for (int s = 15; s < t.Segments.Length; s += 24)
            {
                t.AddPropAtSegment(s, -16.2f, 0f, PropKind.TorchPillar, 1.05f, Color4.FromBytes(145, 225, 120));
            }

            int[] batSegs = { 164, 172, 180, 188, 196, 204, 212 };
            for (int i = 0; i < batSegs.Length; i++)
            {
                TrackSegment seg = t.Segments[batSegs[i] % t.Segments.Length];
                HazardSpawnSpec bat = new HazardSpawnSpec();
                bat.Kind = HazardKind.SwoopingBat;
                bat.BasePos = seg.Center;
                bat.SegmentIndex = seg.Index;
                bat.PatrolRadius = 11.5f;
                bat.Speed = 4.2f;
                bat.PhaseOffset = i * 0.8f;
                t.HazardSpecs.Add(bat);
            }

            HazardSpawnSpec bigFish = new HazardSpawnSpec();
            bigFish.Kind = HazardKind.LeapingCheepCheep;
            bigFish.SegmentIndex = 116;
            bigFish.BasePos = t.Segments[116].Center;
            bigFish.PatrolRadius = 16f;
            bigFish.Speed = 1.9f;
            t.HazardSpecs.Add(bigFish);

            return t;
        }

        public static TrackData CreateRainbowRoad(bool mirror)
        {
            TrackData t = new TrackData();
            t.Id = CourseId.RainbowRoad;
            t.Name = "RAINBOW ROAD";
            t.CupName = "SPECIAL CUP";
            t.Music = MusicTrackId.RainbowRoad;
            t.IsNightSky = true;
            t.HasVoidAbyss = true;
            t.SkyTopColor = Color4.FromBytes(5, 5, 22);
            t.SkyHorizonColor = Color4.FromBytes(20, 12, 52);
            t.GroundPlaneColor = Color4.FromBytes(6, 6, 22);
            t.CurbColorA = Color4.FromBytes(255, 232, 45);
            t.CurbColorB = Color4.FromBytes(255, 190, 30);
            t.WallColor = Color4.FromBytes(255, 225, 55);
            t.FogColor = Color4.FromBytes(12, 10, 35);
            t.FogStart = 340f;
            t.FogEnd = 900f;

            // Authentic MK64 Rainbow Road:
            // High Start -> Giant Steep Plunging Drop -> Sweeping RIGHT Cosmic Curve ->
            // Star Hairpins -> Rollercoaster Waves -> Lunging Chain Chomps -> Cosmic Finale!
            ControlNode[] nodes = new ControlNode[]
            {
                new ControlNode(   0f, 30.0f,   0f, 18.5f,  0f, EdgeBehavior.Guardrail, EdgeBehavior.Guardrail, SegmentFlags.CheckerFinish | SegmentFlags.Bridge),
                new ControlNode(   0f, 32.0f,  98f, 18.5f,  0f, EdgeBehavior.Guardrail, EdgeBehavior.Guardrail, SegmentFlags.Bridge), // Famous Steep Drop Crest!
                new ControlNode(   8f,  4.0f, 218f, 19.5f,  0f, EdgeBehavior.Guardrail, EdgeBehavior.Guardrail, SegmentFlags.Bridge), // Bottom of plunge!
                new ControlNode(  92f, 14.0f, 292f, 19.0f, -7f, EdgeBehavior.Guardrail, EdgeBehavior.Guardrail, SegmentFlags.Bridge),
                new ControlNode( 204f,  8.0f, 262f, 19.0f, -6f, EdgeBehavior.Guardrail, EdgeBehavior.Guardrail, SegmentFlags.Bridge),
                new ControlNode( 162f, 16.0f, 156f, 18.0f,  6f, EdgeBehavior.Guardrail, EdgeBehavior.Guardrail, SegmentFlags.Bridge), // Star hairpin inward!
                new ControlNode( 264f, 20.0f,  98f, 18.0f, -6f, EdgeBehavior.Guardrail, EdgeBehavior.Guardrail, SegmentFlags.Bridge),
                new ControlNode( 278f,  8.0f,   2f, 18.5f,  0f, EdgeBehavior.Guardrail, EdgeBehavior.Guardrail, SegmentFlags.Bridge), // Rollercoaster waves!
                new ControlNode( 198f, 15.0f, -72f, 18.5f,  5f, EdgeBehavior.Guardrail, EdgeBehavior.Guardrail, SegmentFlags.Bridge),
                new ControlNode( 242f, 22.0f,-168f, 18.5f, -7f, EdgeBehavior.Guardrail, EdgeBehavior.Guardrail, SegmentFlags.Bridge),
                new ControlNode( 138f, 18.0f,-224f, 18.5f, -6f, EdgeBehavior.Guardrail, EdgeBehavior.Guardrail, SegmentFlags.Bridge),
                new ControlNode(  38f, 20.0f,-182f, 18.5f, -6f, EdgeBehavior.Guardrail, EdgeBehavior.Guardrail, SegmentFlags.Bridge),
                new ControlNode(   2f, 25.0f, -98f, 18.5f,  0f, EdgeBehavior.Guardrail, EdgeBehavior.Guardrail, SegmentFlags.Bridge)
            };

            t.BuildClosedSpline(nodes, 28, SurfaceType.RainbowNeon, SurfaceType.RainbowNeon, mirror);

            t.AddItemBoxRow(42, 5);
            t.AddItemBoxRow(138, 5);
            t.AddItemBoxRow(232, 5);
            t.AddItemBoxRow(315, 5);

            Color4[] neonCols = new Color4[]
            {
                Color4.FromBytes(255, 65, 85),
                Color4.FromBytes(75, 255, 110),
                Color4.FromBytes(85, 185, 255),
                Color4.FromBytes(255, 235, 65),
                Color4.FromBytes(255, 115, 235)
            };
            for (int i = 0; i < 8; i++)
            {
                int segIdx = (i * 42 + 20) % t.Segments.Length;
                float side = (i % 2 == 0) ? -48f : 48f;
                t.AddPropAtSegment(segIdx, side, 16f, PropKind.NeonConstellation, 2.4f, neonCols[i % neonCols.Length]);
            }

            // Iconic MK64 Rainbow Road Chain Chomps lunging oncoming along the rainbow track!
            for (int c = 0; c < 4; c++)
            {
                HazardSpawnSpec chomp = new HazardSpawnSpec();
                chomp.Kind = HazardKind.ChainChomp;
                chomp.SegmentIndex = (c * 85 + 65) % t.Segments.Length;
                chomp.Speed = -34.0f;
                chomp.PatrolRadius = (c % 2 == 0) ? -6.5f : 6.5f;
                chomp.PhaseOffset = c * 0.25f;
                t.HazardSpecs.Add(chomp);
            }

            return t;
        }
    }
}
