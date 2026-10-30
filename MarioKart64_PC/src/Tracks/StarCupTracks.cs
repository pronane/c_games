using System;
using MarioKart64.Audio;
using MarioKart64.Core;

namespace MarioKart64.Tracks
{
    public static class StarCupTracks
    {
        public static TrackData CreateWarioStadium(bool mirror)
        {
            TrackData t = new TrackData();
            t.Id = CourseId.WarioStadium;
            t.Name = "WARIO STADIUM";
            t.CupName = "STAR CUP";
            t.Music = MusicTrackId.DesertAndHighway;
            t.IsNightSky = true;
            t.SkyTopColor = Color4.FromBytes(16, 12, 36);
            t.SkyHorizonColor = Color4.FromBytes(72, 48, 98);
            t.GroundPlaneColor = Color4.FromBytes(106, 72, 42);
            t.CurbColorA = Color4.FromBytes(252, 214, 26); // Wario Gold & Purple!
            t.CurbColorB = Color4.FromBytes(136, 38, 192);
            t.WallColor = Color4.FromBytes(102, 95, 112);
            t.FogColor = Color4.FromBytes(44, 32, 62);
            t.FogStart = 280f;
            t.FogEnd = 740f;

            // Authentic MarioWiki Wario Stadium (1591m!):
            // Counterclockwise outer stadium wall (LEFT turns!) -> Mogul Bumps -> Multi-hairpin infield S-bends ->
            // Giant Boost-Ramp Motocross Jump -> Final Hairpin to Finish!
            ControlNode[] nodes = new ControlNode[]
            {
                new ControlNode(   0f,  0.0f,   0f, 18.5f,  0f, EdgeBehavior.SolidWall, EdgeBehavior.SolidWall, SegmentFlags.CheckerFinish),
                new ControlNode(   0f,  2.8f, 118f, 18.5f,  0f, EdgeBehavior.SolidWall, EdgeBehavior.SolidWall, SegmentFlags.MogulBumps),
                new ControlNode( -64f,  1.4f, 224f, 19.0f,  7f, EdgeBehavior.SolidWall, EdgeBehavior.SolidWall, SegmentFlags.None),
                new ControlNode(-176f,  0.8f, 226f, 19.0f,  7f, EdgeBehavior.SolidWall, EdgeBehavior.SolidWall, SegmentFlags.MogulBumps),
                new ControlNode(-198f,  3.5f, 126f, 18.0f,  5f, EdgeBehavior.SolidWall, EdgeBehavior.SolidWall, SegmentFlags.None),
                new ControlNode(-104f,  4.2f,  86f, 17.5f, -7f, EdgeBehavior.SolidWall, EdgeBehavior.SolidWall, SegmentFlags.None),
                new ControlNode( -78f,  2.0f,  16f, 17.5f,  7f, EdgeBehavior.SolidWall, EdgeBehavior.SolidWall, SegmentFlags.MogulBumps),
                new ControlNode(-178f,  1.6f, -12f, 18.5f, -6f, EdgeBehavior.SolidWall, EdgeBehavior.SolidWall, SegmentFlags.None),
                new ControlNode(-268f,  6.5f, -56f, 18.5f,  7f, EdgeBehavior.SolidWall, EdgeBehavior.SolidWall, SegmentFlags.None),
                new ControlNode(-246f, 14.0f,-156f, 18.0f,  0f, EdgeBehavior.SolidWall, EdgeBehavior.SolidWall, SegmentFlags.BoostPad | SegmentFlags.JumpRamp), // Giant Motocross Jump!
                new ControlNode(-148f,  3.2f,-184f, 19.0f,  5f, EdgeBehavior.SolidWall, EdgeBehavior.SolidWall, SegmentFlags.None),
                new ControlNode( -96f,  2.2f,-122f, 18.0f, -6f, EdgeBehavior.SolidWall, EdgeBehavior.SolidWall, SegmentFlags.MogulBumps),
                new ControlNode( -38f,  3.2f,-198f, 18.5f,  7f, EdgeBehavior.SolidWall, EdgeBehavior.SolidWall, SegmentFlags.None),
                new ControlNode(   4f,  0.5f,-112f, 18.5f,  0f, EdgeBehavior.SolidWall, EdgeBehavior.SolidWall, SegmentFlags.None)
            };

            t.BuildClosedSpline(nodes, 26, SurfaceType.Dirt, SurfaceType.OffRoadMud, mirror);

            t.AddItemBoxRow(34, 5);
            t.AddItemBoxRow(132, 5);
            t.AddItemBoxRow(224, 5);
            t.AddItemBoxRow(312, 5);

            t.AddPropAtSegment(15, 0f, 0f, PropKind.LuigiJumbotron, 1.55f, Color4.FromBytes(250, 210, 30));
            for (int s = 18; s < t.Segments.Length; s += 24)
            {
                t.AddPropAtSegment(s, -20.0f, 0f, PropKind.StreetLight, 1.45f, Color4.FromBytes(255, 245, 200));
                t.AddPropAtSegment(s,  20.0f, 0f, PropKind.StreetLight, 1.45f, Color4.FromBytes(255, 245, 200), MathUtil.PI);
            }

            return t;
        }

        public static TrackData CreateSherbetLand(bool mirror)
        {
            TrackData t = new TrackData();
            t.Id = CourseId.SherbetLand;
            t.Name = "SHERBET LAND";
            t.CupName = "STAR CUP";
            t.Music = MusicTrackId.SnowAndIce;
            t.HasWaterPlane = true;
            t.IsIceWater = true;
            t.LiquidPlaneY = -2.0f;
            t.SkyTopColor = Color4.FromBytes(38, 126, 244);
            t.SkyHorizonColor = Color4.FromBytes(205, 242, 255);
            t.GroundPlaneColor = Color4.FromBytes(185, 232, 255);
            t.CurbColorA = Color4.FromBytes(88, 194, 252);
            t.CurbColorB = Color4.FromBytes(245, 252, 255);
            t.WallColor = Color4.FromBytes(165, 222, 252);

            // Authentic MarioWiki + characters--2.png Sherbet Land:
            // Wide shimmering ice coast + Giant Pillared Glacier Penguin Cave + Freezing Water Coves!
            ControlNode[] nodes = new ControlNode[]
            {
                new ControlNode(   0f, 0.5f,   0f, 19.5f,  0f, EdgeBehavior.WaterDrop, EdgeBehavior.WaterDrop, SegmentFlags.CheckerFinish),
                new ControlNode(  12f, 0.5f,  96f, 20.0f,  0f, EdgeBehavior.WaterDrop, EdgeBehavior.WaterDrop, SegmentFlags.None),
                new ControlNode( -48f, 1.0f, 182f, 20.5f,  3f, EdgeBehavior.WaterDrop, EdgeBehavior.WaterDrop, SegmentFlags.None),
                new ControlNode(-148f, 1.5f, 196f, 20.5f,  0f, EdgeBehavior.SolidWall, EdgeBehavior.SolidWall, SegmentFlags.Tunnel), // Pillared Ice Cave!
                new ControlNode(-224f, 1.2f, 118f, 20.5f,  0f, EdgeBehavior.SolidWall, EdgeBehavior.SolidWall, SegmentFlags.Tunnel), // Pillared Ice Cave!
                new ControlNode(-196f, 0.6f,  28f, 20.0f, -3f, EdgeBehavior.WaterDrop, EdgeBehavior.WaterDrop, SegmentFlags.None),
                new ControlNode(-228f, 0.5f, -56f, 21.0f,  3f, EdgeBehavior.WaterDrop, EdgeBehavior.WaterDrop, SegmentFlags.None),
                new ControlNode(-168f, 0.5f,-142f, 21.5f,  3f, EdgeBehavior.WaterDrop, EdgeBehavior.WaterDrop, SegmentFlags.None),
                new ControlNode( -68f, 0.5f,-156f, 20.0f,  3f, EdgeBehavior.WaterDrop, EdgeBehavior.WaterDrop, SegmentFlags.None),
                new ControlNode(   2f, 0.5f, -84f, 19.5f,  0f, EdgeBehavior.WaterDrop, EdgeBehavior.WaterDrop, SegmentFlags.None)
            };

            t.BuildClosedSpline(nodes, 28, SurfaceType.Ice, SurfaceType.OffRoadSnow, mirror);

            t.AddItemBoxRow(34, 5);
            t.AddItemBoxRow(112, 5);
            t.AddItemBoxRow(204, 5);

            int[] penguinSegs = { 65, 88, 102, 114, 126, 138, 168, 192, 218, 236 };
            for (int i = 0; i < penguinSegs.Length; i++)
            {
                TrackSegment seg = t.Segments[penguinSegs[i] % t.Segments.Length];
                HazardSpawnSpec hs = new HazardSpawnSpec();
                hs.Kind = HazardKind.SlidingPenguin;
                hs.BasePos = seg.Center;
                hs.SegmentIndex = seg.Index;
                hs.PatrolRadius = seg.HalfWidth * 0.72f;
                hs.Speed = 3.2f + (i % 3) * 0.8f;
                hs.PhaseOffset = i * 0.9f;
                t.HazardSpecs.Add(hs);
            }

            return t;
        }

        public static TrackData CreateRoyalRaceway(bool mirror)
        {
            TrackData t = new TrackData();
            t.Id = CourseId.RoyalRaceway;
            t.Name = "ROYAL RACEWAY";
            t.CupName = "STAR CUP";
            t.Music = MusicTrackId.RacewayCircuit;
            t.HasWaterPlane = true;
            t.LiquidPlaneY = -2.8f;
            t.SkyTopColor = Color4.FromBytes(58, 135, 246);
            t.SkyHorizonColor = Color4.FromBytes(255, 210, 236);
            t.GroundPlaneColor = Color4.FromBytes(56, 176, 60);
            t.CurbColorA = Color4.FromBytes(255, 98, 178);
            t.CurbColorB = Color4.FromBytes(252, 252, 255);
            t.WallColor = Color4.FromBytes(235, 215, 225);

            // Authentic MarioWiki Royal Raceway (1025m):
            // Slight Left -> Left U-turn -> Right U-turn -> Lakeside Right bends ->
            // Right U-turn onto Giant Dash-Panel Ramp Jump over Lake -> Left turn (with Right Driveway to Peach's Castle!) ->
            // Chicane -> Left back to Finish!
            ControlNode[] nodes = new ControlNode[]
            {
                new ControlNode(   0f,  0.5f,   0f, 18.5f,  0f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.OffRoadShoulder, SegmentFlags.CheckerFinish),
                new ControlNode( -16f,  0.5f,  98f, 18.5f,  2f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.WaterDrop,       SegmentFlags.None),
                new ControlNode( -88f,  1.8f, 186f, 19.0f,  6f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.WaterDrop,       SegmentFlags.None), // Left U-turn!
                new ControlNode(-168f,  2.5f, 142f, 19.0f, -6f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.OffRoadShoulder, SegmentFlags.None), // Right U-turn!
                new ControlNode(-212f,  3.8f, 226f, 18.5f, -5f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.WaterDrop,       SegmentFlags.None),
                new ControlNode(-286f,  6.2f, 148f, 18.5f, -5f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.WaterDrop,       SegmentFlags.None),
                new ControlNode(-268f, 12.0f,  36f, 17.5f,  0f, EdgeBehavior.Guardrail,       EdgeBehavior.Guardrail,       SegmentFlags.BoostPad | SegmentFlags.JumpRamp), // Giant Lake Jump!
                new ControlNode(-216f,  2.5f, -68f, 19.5f,  4f, EdgeBehavior.WaterDrop,       EdgeBehavior.OffRoadShoulder, SegmentFlags.None), // Driveway Right to Castle!
                new ControlNode(-138f,  1.5f,-156f, 18.5f,  5f, EdgeBehavior.WaterDrop,       EdgeBehavior.OffRoadShoulder, SegmentFlags.None),
                new ControlNode( -48f,  1.0f,-162f, 18.5f,  5f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.OffRoadShoulder, SegmentFlags.None),
                new ControlNode(   4f,  0.5f, -88f, 18.5f,  0f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.OffRoadShoulder, SegmentFlags.None)
            };

            t.BuildClosedSpline(nodes, 28, SurfaceType.Asphalt, SurfaceType.OffRoadGrass, mirror);

            ControlNode[] castleDrive = new ControlNode[]
            {
                new ControlNode(-204f, 2.2f, -72f, 11.0f),
                new ControlNode(-142f, 3.5f, -38f, 12.0f),
                new ControlNode( -96f, 4.0f, -24f, 14.0f),
                new ControlNode( -68f, 2.0f, -92f, 11.0f),
                new ControlNode( -46f, 1.0f,-152f, 11.0f)
            };
            t.AddBranchSpline("PeachCastleGrounds", 200, 258, castleDrive, 10, SurfaceType.Dirt, false);

            float mSign = mirror ? 1f : -1f;
            t.Props.Add(new TrackProp(PropKind.PeachCastle, new Vec3(-92f * mSign, 3.8f, 4f), 3.14f, 2.15f, Color4.FromBytes(252, 232, 238)));
            t.AddPropAtSegment(12, -26f, 0f, PropKind.Grandstand, 1.35f, Color4.FromBytes(255, 105, 180));

            for (int s = 20; s < t.Segments.Length; s += 16)
            {
                t.AddPropAtSegment(s, -25.5f, 0f, PropKind.TreeRound, 1.25f, Color4.FromBytes(255, 152, 205));
            }

            t.AddItemBoxRow(34, 5);
            t.AddItemBoxRow(132, 5);
            t.AddItemBoxRow(224, 5);

            return t;
        }

        public static TrackData CreateBowsersCastle(bool mirror)
        {
            TrackData t = new TrackData();
            t.Id = CourseId.BowsersCastle;
            t.Name = "BOWSER'S CASTLE";
            t.CupName = "STAR CUP";
            t.Music = MusicTrackId.CastleAndSpooky;
            t.HasLavaPlane = true;
            t.LiquidPlaneY = -3.5f;
            t.SkyTopColor = Color4.FromBytes(42, 12, 14);
            t.SkyHorizonColor = Color4.FromBytes(156, 46, 18);
            t.GroundPlaneColor = Color4.FromBytes(235, 72, 15);
            t.CurbColorA = Color4.FromBytes(95, 90, 98);
            t.CurbColorB = Color4.FromBytes(235, 88, 22);
            t.WallColor = Color4.FromBytes(78, 72, 82);
            t.FogColor = Color4.FromBytes(102, 34, 18);
            t.FogStart = 195f;
            t.FogEnd = 540f;

            // Authentic 90-Degree Right-Angled MK64 Stone Fortress Layout (MarioWiki 777m):
            // Bridge over Lava -> Courtyard (two 45-deg RIGHT turns) -> Crushing Thwomp Hall ->
            // Narrow Lava Bridge -> Spiral Tower Climb -> Rooftop Lava Jump -> Right-Angled Corridor to Finish!
            ControlNode[] nodes = new ControlNode[]
            {
                new ControlNode(   0f,  2.0f,   0f, 16.5f, 0f, EdgeBehavior.SolidWall, EdgeBehavior.SolidWall, SegmentFlags.CheckerFinish | SegmentFlags.Tunnel),
                new ControlNode(   0f,  2.0f,  98f, 15.0f, 0f, EdgeBehavior.LavaDrop,  EdgeBehavior.LavaDrop,  SegmentFlags.Bridge),
                new ControlNode(  54f,  2.0f, 156f, 16.5f, 0f, EdgeBehavior.SolidWall, EdgeBehavior.SolidWall, SegmentFlags.None), // Courtyard + Thwomp Hall!
                new ControlNode( 148f,  2.2f, 156f, 16.5f, 0f, EdgeBehavior.SolidWall, EdgeBehavior.SolidWall, SegmentFlags.Tunnel),
                new ControlNode( 198f,  2.5f, 108f, 13.5f, 0f, EdgeBehavior.LavaDrop,  EdgeBehavior.LavaDrop,  SegmentFlags.Bridge), // Lava Bridge!
                new ControlNode( 198f,  4.8f,  24f, 16.5f, 0f, EdgeBehavior.SolidWall, EdgeBehavior.SolidWall, SegmentFlags.Tunnel),
                new ControlNode( 132f,  7.8f,   4f, 16.5f, 0f, EdgeBehavior.SolidWall, EdgeBehavior.SolidWall, SegmentFlags.None), // Fire-Breathing Bowser Statue!
                new ControlNode( 132f, 11.2f, -76f, 16.5f, 4f, EdgeBehavior.SolidWall, EdgeBehavior.SolidWall, SegmentFlags.None),
                new ControlNode( 198f, 14.0f,-112f, 16.0f, 4f, EdgeBehavior.SolidWall, EdgeBehavior.SolidWall, SegmentFlags.None), // Spiral Tower Top!
                new ControlNode( 152f, 12.8f,-176f, 14.0f, 0f, EdgeBehavior.LavaDrop,  EdgeBehavior.LavaDrop,  SegmentFlags.Bridge | SegmentFlags.JumpRamp), // Rooftop Lava Jump!
                new ControlNode(  58f,  6.0f,-176f, 16.5f, 3f, EdgeBehavior.SolidWall, EdgeBehavior.SolidWall, SegmentFlags.None),
                new ControlNode(   2f,  2.5f,-108f, 16.5f, 0f, EdgeBehavior.SolidWall, EdgeBehavior.SolidWall, SegmentFlags.Tunnel)
            };

            t.BuildClosedSpline(nodes, 25, SurfaceType.CastleStone, SurfaceType.CastleStone, mirror);

            t.AddItemBoxRow(32, 4);
            t.AddItemBoxRow(125, 4);
            t.AddItemBoxRow(218, 4);

            // Fire-Breathing Bowser Statue & Fortress Torch Pillars!
            t.AddPropAtSegment(156, -21f, 0f, PropKind.BowserStatue, 1.95f, Color4.FromBytes(135, 140, 145));
            for (int s = 10; s < t.Segments.Length; s += 20)
            {
                t.AddPropAtSegment(s, -17.5f, 0f, PropKind.TorchPillar, 1.25f, Color4.FromBytes(255, 130, 28));
                t.AddPropAtSegment(s,  17.5f, 0f, PropKind.TorchPillar, 1.25f, Color4.FromBytes(255, 130, 28));
            }

            // Crushing SGI Spiked Blue Thwomps!
            int[] thwompSegs = { 52, 66, 80, 138, 152, 172, 232, 248 };
            for (int i = 0; i < thwompSegs.Length; i++)
            {
                TrackSegment seg = t.Segments[thwompSegs[i] % t.Segments.Length];
                float lat = ((i % 3) - 1) * 6.2f;
                HazardSpawnSpec hs = new HazardSpawnSpec();
                hs.Kind = HazardKind.StompingThwomp;
                hs.BasePos = seg.Center + seg.Right * lat;
                hs.SegmentIndex = seg.Index;
                hs.Speed = 2.6f;
                hs.PhaseOffset = i * 0.72f;
                t.HazardSpecs.Add(hs);
            }

            return t;
        }
    }
}
