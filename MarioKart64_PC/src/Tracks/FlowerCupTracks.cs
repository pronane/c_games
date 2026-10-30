using System;
using MarioKart64.Audio;
using MarioKart64.Core;

namespace MarioKart64.Tracks
{
    public static class FlowerCupTracks
    {
        public static TrackData CreateToadsTurnpike(bool mirror)
        {
            TrackData t = new TrackData();
            t.Id = CourseId.ToadsTurnpike;
            t.Name = "TOAD'S TURNPIKE";
            t.CupName = "FLOWER CUP";
            t.Music = MusicTrackId.DesertAndHighway;
            t.IsNightSky = true;
            // Authentic MK64 Dusk/Twilight Indigo-to-Violet-Peach Sky + Lush Green Grass Verges (characters--3.png!)
            t.SkyTopColor = Color4.FromBytes(32, 28, 92);
            t.SkyHorizonColor = Color4.FromBytes(178, 126, 168);
            t.GroundPlaneColor = Color4.FromBytes(36, 128, 46);
            t.CurbColorA = Color4.FromBytes(244, 246, 252);
            t.CurbColorB = Color4.FromBytes(215, 222, 232);
            t.WallColor = Color4.FromBytes(236, 240, 248);
            t.FogColor = Color4.FromBytes(98, 78, 126);
            t.FogStart = 280f;
            t.FogEnd = 740f;

            // Authentic MK64 Figure-8 3-Lane Highway Overpass (matches MarioWiki + characters--3.png!):
            // Start North -> Sweeping 270-deg LEFT Loop -> High Overpass Bridge heading East/SE ->
            // Sweeping 270-deg RIGHT Loop -> Underpass heading North back to Finish!
            ControlNode[] nodes = new ControlNode[]
            {
                new ControlNode(   0f,  0.0f,   0f, 19.5f,  0f, EdgeBehavior.Guardrail, EdgeBehavior.Guardrail, SegmentFlags.CheckerFinish),
                new ControlNode(   0f,  0.5f, 118f, 19.5f,  0f, EdgeBehavior.Guardrail, EdgeBehavior.Guardrail, SegmentFlags.None),
                new ControlNode( -58f,  3.2f, 218f, 19.5f,  5f, EdgeBehavior.Guardrail, EdgeBehavior.Guardrail, SegmentFlags.None),
                new ControlNode(-158f,  7.8f, 226f, 19.5f,  6f, EdgeBehavior.Guardrail, EdgeBehavior.Guardrail, SegmentFlags.None),
                new ControlNode(-188f, 13.5f, 126f, 19.0f,  5f, EdgeBehavior.Guardrail, EdgeBehavior.Guardrail, SegmentFlags.Bridge),
                new ControlNode( -92f, 18.0f,  38f, 18.5f,  0f, EdgeBehavior.Guardrail, EdgeBehavior.Guardrail, SegmentFlags.Bridge),
                new ControlNode(   0f, 19.5f,  -8f, 18.5f,  0f, EdgeBehavior.Guardrail, EdgeBehavior.Guardrail, SegmentFlags.Bridge), // High Overpass!
                new ControlNode( 104f, 15.0f, -56f, 19.0f, -4f, EdgeBehavior.Guardrail, EdgeBehavior.Guardrail, SegmentFlags.Bridge),
                new ControlNode( 196f,  7.5f,-136f, 19.5f, -6f, EdgeBehavior.Guardrail, EdgeBehavior.Guardrail, SegmentFlags.None),
                new ControlNode( 168f,  1.5f,-236f, 19.5f, -6f, EdgeBehavior.Guardrail, EdgeBehavior.Guardrail, SegmentFlags.None),
                new ControlNode(  56f,  0.0f,-228f, 19.5f, -5f, EdgeBehavior.Guardrail, EdgeBehavior.Guardrail, SegmentFlags.None),
                new ControlNode(   0f,  0.0f,-124f, 19.5f,  0f, EdgeBehavior.Guardrail, EdgeBehavior.Guardrail, SegmentFlags.None),
                new ControlNode(   0f,  0.0f, -48f, 19.5f,  0f, EdgeBehavior.Guardrail, EdgeBehavior.Guardrail, SegmentFlags.None)    // Underpass below!
            };

            t.BuildClosedSpline(nodes, 28, SurfaceType.Asphalt, SurfaceType.OffRoadGrass, mirror);

            t.AddItemBoxRow(34, 5);
            t.AddItemBoxRow(152, 5);
            t.AddItemBoxRow(278, 5);

            for (int s = 10; s < t.Segments.Length; s += 16)
            {
                t.AddPropAtSegment(s, -20.8f, 0f, PropKind.StreetLight, 1.25f, Color4.FromBytes(255, 232, 145));
                t.AddPropAtSegment(s,  20.8f, 0f, PropKind.StreetLight, 1.25f, Color4.FromBytes(255, 232, 145), MathUtil.PI);
            }

            HazardKind[] vehicleTypes = { HazardKind.HighwayTruck, HazardKind.HighwayBus, HazardKind.HighwayCar };
            int vehicleCount = 16;
            for (int v = 0; v < vehicleCount; v++)
            {
                HazardSpawnSpec hs = new HazardSpawnSpec();
                hs.Kind = vehicleTypes[v % 3];
                hs.SegmentIndex = (v * (t.Segments.Length / vehicleCount)) % t.Segments.Length;
                bool oncoming = mirror && (v % 2 == 1);
                hs.Speed = oncoming ? -26.0f : (24.0f + (v % 3) * 3.5f);
                hs.PatrolRadius = ((v % 3) - 1) * 9.5f;
                hs.PhaseOffset = v * 0.37f;
                t.HazardSpecs.Add(hs);
            }

            return t;
        }

        public static TrackData CreateFrappeSnowland(bool mirror)
        {
            TrackData t = new TrackData();
            t.Id = CourseId.FrappeSnowland;
            t.Name = "FRAPPE SNOWLAND";
            t.CupName = "FLOWER CUP";
            t.Music = MusicTrackId.SnowAndIce;
            t.IsSnowing = true;
            t.SkyTopColor = Color4.FromBytes(98, 162, 238);
            t.SkyHorizonColor = Color4.FromBytes(232, 244, 255);
            t.GroundPlaneColor = Color4.FromBytes(238, 246, 255);
            t.CurbColorA = Color4.FromBytes(138, 198, 252);
            t.CurbColorB = Color4.FromBytes(250, 252, 255);
            t.WallColor = Color4.FromBytes(210, 232, 252);
            t.FogColor = Color4.FromBytes(228, 240, 255);
            t.FogStart = 210f;
            t.FogEnd = 580f;

            // Authentic MarioWiki Frappe Snowland:
            // Right then Left -> slight Right past Giant Snow Statue -> Left U-turn -> Right-Left ->
            // Bridge over icy river -> Left into Wide Snowman Field -> High White Snow Canyon Walls to Finish!
            ControlNode[] nodes = new ControlNode[]
            {
                new ControlNode(   0f, 0.0f,   0f, 18.0f,  0f, EdgeBehavior.SolidWall,       EdgeBehavior.SolidWall,       SegmentFlags.CheckerFinish),
                new ControlNode(  24f, 0.8f,  86f, 18.5f, -3f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.OffRoadShoulder, SegmentFlags.None),
                new ControlNode(   4f, 1.6f, 168f, 18.5f,  3f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.OffRoadShoulder, SegmentFlags.None),
                new ControlNode(  38f, 2.2f, 242f, 19.0f, -3f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.OffRoadShoulder, SegmentFlags.None), // Snow Statue!
                new ControlNode( -42f, 2.8f, 286f, 18.5f,  5f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.OffRoadShoulder, SegmentFlags.None),
                new ControlNode(-128f, 2.0f, 236f, 18.5f,  5f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.OffRoadShoulder, SegmentFlags.None),
                new ControlNode(-104f, 1.2f, 152f, 18.0f, -4f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.OffRoadShoulder, SegmentFlags.None),
                new ControlNode(-148f, 1.0f,  74f, 14.5f,  0f, EdgeBehavior.Guardrail,       EdgeBehavior.Guardrail,       SegmentFlags.Bridge), // River Bridge!
                new ControlNode(-158f, 0.4f, -24f, 22.0f,  3f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.OffRoadShoulder, SegmentFlags.None), // Wide Snowman Field!
                new ControlNode(-112f, 0.2f,-118f, 21.5f,  4f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.OffRoadShoulder, SegmentFlags.None),
                new ControlNode( -34f, 0.2f,-148f, 18.0f,  4f, EdgeBehavior.SolidWall,       EdgeBehavior.SolidWall,       SegmentFlags.None), // Snow Canyon!
                new ControlNode(   0f, 0.0f, -76f, 18.0f,  0f, EdgeBehavior.SolidWall,       EdgeBehavior.SolidWall,       SegmentFlags.None)
            };

            t.BuildClosedSpline(nodes, 26, SurfaceType.Snow, SurfaceType.OffRoadSnow, mirror);

            t.AddItemBoxRow(32, 5);
            t.AddItemBoxRow(134, 5);
            t.AddItemBoxRow(218, 5);

            // Giant Snow Mario Sculpture + Dense Snowy Pine Forest!
            t.AddPropAtSegment(74, 27f, 0f, PropKind.SnowMarioStatue, 1.85f, Color4.FromBytes(242, 248, 255));
            t.AddPropAtSegment(232, -28f, 0f, PropKind.SnowMarioStatue, 1.65f, Color4.FromBytes(242, 248, 255));
            for (int s = 14; s < t.Segments.Length; s += 16)
            {
                if (t.Segments[s].LeftEdge == EdgeBehavior.SolidWall) continue;
                t.AddPropAtSegment(s, -26f, 0f, PropKind.TreePine, 1.35f, Color4.FromBytes(45, 132, 78));
                if (s % 32 == 0)
                    t.AddPropAtSegment(s, 26.5f, 0f, PropKind.TreePine, 1.25f, Color4.FromBytes(45, 132, 78));
            }

            int[] snowSegs = { 198, 206, 214, 222, 230, 238, 246, 254, 262, 270 };
            for (int i = 0; i < snowSegs.Length; i++)
            {
                TrackSegment seg = t.Segments[snowSegs[i] % t.Segments.Length];
                float lat = ((i % 3) - 1) * 7.5f + ((i % 2 == 0) ? 3.2f : -3.2f);
                HazardSpawnSpec hs = new HazardSpawnSpec();
                hs.Kind = HazardKind.SnowmanMine;
                hs.BasePos = seg.Center + seg.Right * lat;
                hs.SegmentIndex = seg.Index;
                hs.PhaseOffset = i * 0.5f;
                t.HazardSpecs.Add(hs);
            }

            return t;
        }

        public static TrackData CreateChocoMountain(bool mirror)
        {
            TrackData t = new TrackData();
            t.Id = CourseId.ChocoMountain;
            t.Name = "CHOCO MOUNTAIN";
            t.CupName = "FLOWER CUP";
            t.Music = MusicTrackId.DesertAndHighway;
            t.SkyTopColor = Color4.FromBytes(142, 108, 82);
            t.SkyHorizonColor = Color4.FromBytes(212, 182, 154);
            t.GroundPlaneColor = Color4.FromBytes(118, 76, 44);
            t.CurbColorA = Color4.FromBytes(165, 112, 66);
            t.CurbColorB = Color4.FromBytes(228, 202, 172);
            t.WallColor = Color4.FromBytes(126, 82, 48);
            t.FogColor = Color4.FromBytes(198, 168, 142);
            t.FogStart = 110f;
            t.FogEnd = 410f;

            // Authentic MarioWiki Choco Mountain:
            // Foggy brown cliffs -> Right then slight Left -> Right U-turn into mountain rock tunnel ->
            // Two Left turns + hill climb -> Unguarded Left U-turn (CliffToLower!) with Falling Boulders ->
            // Three mogul bumps -> sprint to Finish!
            ControlNode[] nodes = new ControlNode[]
            {
                new ControlNode(   0f,  0.0f,   0f, 17.0f,  0f, EdgeBehavior.SolidWall,    EdgeBehavior.SolidWall,    SegmentFlags.CheckerFinish),
                new ControlNode(  26f,  3.2f,  86f, 17.0f, -4f, EdgeBehavior.SolidWall,    EdgeBehavior.Guardrail,    SegmentFlags.None),
                new ControlNode(  14f,  6.8f, 164f, 17.0f,  3f, EdgeBehavior.SolidWall,    EdgeBehavior.Guardrail,    SegmentFlags.None),
                new ControlNode(  88f, 10.5f, 212f, 16.5f, -6f, EdgeBehavior.SolidWall,    EdgeBehavior.SolidWall,    SegmentFlags.Tunnel),
                new ControlNode( 168f, 13.5f, 152f, 16.5f, -5f, EdgeBehavior.SolidWall,    EdgeBehavior.SolidWall,    SegmentFlags.Tunnel),
                new ControlNode( 148f, 17.5f,  64f, 17.0f,  5f, EdgeBehavior.SolidWall,    EdgeBehavior.Guardrail,    SegmentFlags.None),
                new ControlNode(  84f, 21.5f,   8f, 17.0f,  5f, EdgeBehavior.CliffToLower, EdgeBehavior.SolidWall,    SegmentFlags.None),
                new ControlNode( 126f, 18.0f, -76f, 17.0f,  6f, EdgeBehavior.CliffToLower, EdgeBehavior.SolidWall,    SegmentFlags.None), // Falling Boulders!
                new ControlNode(  82f,  9.5f,-154f, 17.5f,  5f, EdgeBehavior.Guardrail,    EdgeBehavior.SolidWall,    SegmentFlags.MogulBumps),
                new ControlNode(   8f,  2.8f,-148f, 17.5f,  4f, EdgeBehavior.SolidWall,    EdgeBehavior.SolidWall,    SegmentFlags.MogulBumps),
                new ControlNode(   0f,  0.5f, -76f, 17.0f,  0f, EdgeBehavior.SolidWall,    EdgeBehavior.SolidWall,    SegmentFlags.None)
            };

            t.BuildClosedSpline(nodes, 26, SurfaceType.Dirt, SurfaceType.OffRoadMud, mirror);

            t.AddItemBoxRow(34, 5);
            t.AddItemBoxRow(132, 4);
            t.AddItemBoxRow(224, 5);

            int[] boulderSegs = { 174, 182, 190, 198, 206, 214 };
            for (int i = 0; i < boulderSegs.Length; i++)
            {
                TrackSegment seg = t.Segments[boulderSegs[i] % t.Segments.Length];
                HazardSpawnSpec hs = new HazardSpawnSpec();
                hs.Kind = HazardKind.FallingBoulder;
                hs.BasePos = seg.Center;
                hs.SegmentIndex = seg.Index;
                hs.Speed = 14.5f;
                hs.PatrolRadius = seg.HalfWidth * 0.90f;
                hs.PhaseOffset = i * 1.15f;
                t.HazardSpecs.Add(hs);
            }

            return t;
        }

        public static TrackData CreateMarioRaceway(bool mirror)
        {
            TrackData t = new TrackData();
            t.Id = CourseId.MarioRaceway;
            t.Name = "MARIO RACEWAY";
            t.CupName = "FLOWER CUP";
            t.Music = MusicTrackId.RacewayCircuit;
            t.SkyTopColor = Color4.FromBytes(34, 118, 246);
            t.SkyHorizonColor = Color4.FromBytes(172, 224, 255);
            t.GroundPlaneColor = Color4.FromBytes(46, 172, 50);
            t.CurbColorA = Color4.FromBytes(236, 32, 34);
            t.CurbColorB = Color4.FromBytes(252, 232, 24);
            t.WallColor = Color4.FromBytes(185, 188, 195);
            t.FogColor = Color4.FromBytes(182, 226, 255);
            t.FogStart = 310f;
            t.FogEnd = 740f;

            // Authentic MarioWiki + lu-4.png Mario Raceway Layout:
            // Red Mario-Cap Grandstand on Left + "MARIO STAR" & Red/Yellow Checkered Barriers ->
            // Two sweeping RIGHT turns -> Gradual LEFT U-turn around grass hill ->
            // Sharp RIGHT hairpin around Giant Red Spotted Mushroom -> Left-Right S-bend ->
            // Glossy Emerald-Green Warp Pipe Tunnel -> 90-deg RIGHT onto Start/Finish straight!
            ControlNode[] nodes = new ControlNode[]
            {
                new ControlNode(   0f, 0.0f,   0f, 18.5f,  0f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.OffRoadShoulder, SegmentFlags.CheckerFinish),
                new ControlNode(   0f, 0.0f, 106f, 18.5f,  0f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.OffRoadShoulder, SegmentFlags.None),
                new ControlNode(  64f, 2.2f, 196f, 19.0f, -7f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.OffRoadShoulder, SegmentFlags.None),
                new ControlNode( 168f, 2.6f, 188f, 19.0f, -7f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.OffRoadShoulder, SegmentFlags.None),
                new ControlNode( 206f, 4.8f, 102f, 18.5f,  5f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.OffRoadShoulder, SegmentFlags.None), // Left U-turn hill!
                new ControlNode( 138f, 6.2f,  52f, 18.0f,  6f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.OffRoadShoulder, SegmentFlags.None),
                new ControlNode( 186f, 4.2f, -12f, 18.5f, -7f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.OffRoadShoulder, SegmentFlags.None), // Giant Mushroom hairpin!
                new ControlNode( 256f, 2.0f, -68f, 18.5f, -6f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.OffRoadShoulder, SegmentFlags.None),
                new ControlNode( 212f, 0.8f,-136f, 18.0f,  5f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.OffRoadShoulder, SegmentFlags.None), // S-bend!
                new ControlNode( 148f, 0.4f,-118f, 16.5f,  0f, EdgeBehavior.SolidWall,       EdgeBehavior.SolidWall,       SegmentFlags.Tunnel), // Green Warp Pipe!
                new ControlNode(  76f, 0.0f,-116f, 16.5f,  0f, EdgeBehavior.SolidWall,       EdgeBehavior.SolidWall,       SegmentFlags.Tunnel),
                new ControlNode(  24f, 0.0f,-168f, 18.5f, -6f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.OffRoadShoulder, SegmentFlags.None),
                new ControlNode(  -4f, 0.0f, -92f, 18.5f,  0f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.OffRoadShoulder, SegmentFlags.None)
            };

            t.BuildClosedSpline(nodes, 25, SurfaceType.Asphalt, SurfaceType.OffRoadGrass, mirror);

            t.AddItemBoxRow(34, 5);
            t.AddItemBoxRow(138, 5);
            t.AddItemBoxRow(248, 5);

            // Giant Red Spotted SGI Mushroom, Emerald Warp Pipe portals, Red Mario-Cap Grandstand & Topiary Trees!
            t.AddPropAtSegment(156,  25f, 0f, PropKind.GiantMushroom, 2.15f, Color4.FromBytes(238, 32, 34));
            t.AddPropAtSegment(222,   0f, 0f, PropKind.WarpPipeArch,  1.45f, Color4.FromBytes(32, 192, 58));
            t.AddPropAtSegment(255,   0f, 0f, PropKind.WarpPipeArch,  1.45f, Color4.FromBytes(32, 192, 58));
            t.AddPropAtSegment(12,  -27f, 0f, PropKind.Grandstand,    1.35f, Color4.FromBytes(236, 32, 34));
            t.AddPropAtSegment(308, -27f, 0f, PropKind.Grandstand,    1.25f, Color4.FromBytes(236, 32, 34));

            for (int s = 18; s < t.Segments.Length; s += 16)
            {
                if ((t.Segments[s].Flags & SegmentFlags.Tunnel) != 0) continue;
                t.AddPropAtSegment(s, 25.5f, 0f, PropKind.TreeRound, 1.25f, Color4.FromBytes(46, 178, 56));
                if (s % 32 == 0)
                    t.AddPropAtSegment(s, -25.5f, 0f, PropKind.TreeRound, 1.15f, Color4.FromBytes(56, 188, 62));
            }

            return t;
        }
    }
}
