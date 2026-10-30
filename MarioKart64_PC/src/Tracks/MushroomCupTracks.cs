using System;
using MarioKart64.Audio;
using MarioKart64.Core;

namespace MarioKart64.Tracks
{
    public static class MushroomCupTracks
    {
        public static TrackData CreateLuigiRaceway(bool mirror)
        {
            TrackData t = new TrackData();
            t.Id = CourseId.LuigiRaceway;
            t.Name = "LUIGI RACEWAY";
            t.CupName = "MUSHROOM CUP";
            t.Music = MusicTrackId.RacewayCircuit;
            t.SkyTopColor = Color4.FromBytes(42, 128, 250);
            t.SkyHorizonColor = Color4.FromBytes(175, 224, 255);
            t.GroundPlaneColor = Color4.FromBytes(48, 178, 52);
            t.CurbColorA = Color4.FromBytes(38, 68, 224);
            t.CurbColorB = Color4.FromBytes(58, 228, 52);
            t.WallColor = Color4.FromBytes(182, 148, 108);
            t.FogColor = Color4.FromBytes(186, 228, 255);
            t.FogStart = 320f;
            t.FogEnd = 780f;

            // Authentic N64 Luigi Raceway Overpass-Tunnel Loop (matches MarioWiki + lu-1.jpg & lu-2.jpg!):
            // Top-Down Map Space (+X = East/Right, -X = West/Left, +Z = North/Up):
            // 1. Wide Start/Finish Straight heading North (+Z) over bridge past Green Luigi-Cap Grandstand on Left!
            // 2. Sweeping 180-deg BANKED LEFT Curve (mapX: 0 -> -115 -> -228) with Blue/Green Checkered Barrier on outer Right!
            // 3. Diagonal SE Straight (slight Right bend) diving into the Tan Brick Tunnel + Giant Overhead Luigi Jumbotron!
            // 4. Tunnel passes cleanly UNDERNEATH the elevated front straight (Y = -5.5 vs bridge Y = +5.2)!
            // 5. Sweeping 180-deg BANKED LEFT Curve (mapX: +72 -> +148 -> +68 -> 0) back onto the Start/Finish straight!
            ControlNode[] nodes = new ControlNode[]
            {
                new ControlNode(   0f, 11.8f,   0f, 18.5f,  0f, EdgeBehavior.Guardrail,       EdgeBehavior.Guardrail,       SegmentFlags.CheckerFinish | SegmentFlags.Bridge),
                new ControlNode(   0f, 12.2f,  92f, 18.5f,  0f, EdgeBehavior.Guardrail,       EdgeBehavior.Guardrail,       SegmentFlags.Bridge),
                new ControlNode(   0f,  7.5f, 184f, 18.5f,  2f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.Guardrail,       SegmentFlags.None),
                new ControlNode( -48f,  3.2f, 264f, 19.5f,  7f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.Guardrail,       SegmentFlags.None),
                new ControlNode(-138f,  1.8f, 288f, 19.5f,  8f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.Guardrail,       SegmentFlags.None),
                new ControlNode(-218f,  1.2f, 232f, 19.0f,  6f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.Guardrail,       SegmentFlags.None),
                new ControlNode(-212f,  0.6f, 142f, 18.5f,  0f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.OffRoadShoulder, SegmentFlags.None),
                new ControlNode(-136f,  0.4f,  72f, 18.0f, -3f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.OffRoadShoulder, SegmentFlags.None),
                new ControlNode( -48f,  0.2f,  18f, 17.5f,  0f, EdgeBehavior.SolidWall,       EdgeBehavior.SolidWall,       SegmentFlags.Tunnel),
                new ControlNode(  28f,  0.2f, -28f, 17.5f,  0f, EdgeBehavior.SolidWall,       EdgeBehavior.SolidWall,       SegmentFlags.Tunnel),
                new ControlNode( 104f,  0.6f, -88f, 18.5f,  4f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.Guardrail,       SegmentFlags.None),
                new ControlNode( 152f,  1.6f,-168f, 19.5f,  7f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.Guardrail,       SegmentFlags.None),
                new ControlNode( 118f,  3.2f,-248f, 19.5f,  8f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.Guardrail,       SegmentFlags.None),
                new ControlNode(  36f,  5.6f,-242f, 19.0f,  6f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.Guardrail,       SegmentFlags.None),
                new ControlNode(  -2f,  8.6f,-156f, 18.5f,  2f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.OffRoadShoulder, SegmentFlags.None),
                new ControlNode(   0f, 11.2f, -76f, 18.5f,  0f, EdgeBehavior.Guardrail,       EdgeBehavior.Guardrail,       SegmentFlags.Bridge)
            };

            t.BuildClosedSpline(nodes, 22, SurfaceType.Asphalt, SurfaceType.OffRoadGrass, mirror);

            // Inner Turn 1 Tan Sand Trap (matches lu-2.jpg!)
            for (int s = 56; s <= 118 && s < t.Segments.Length; s++)
            {
                t.Segments[s].OffRoadSurface = SurfaceType.OffRoadSand;
            }

            t.AddItemBoxRow(34, 5);
            t.AddItemBoxRow(148, 5);
            t.AddItemBoxRow(268, 5);

            // Signature Luigi Raceway Hot-Air Balloon floating in the infield with suspended Spiny-Shell Item Box!
            float mSign = mirror ? 1f : -1f;
            Vec3 balloonPos = new Vec3(-88f * mSign, 20.5f, 155f);
            t.Props.Add(new TrackProp(PropKind.HotAirBalloon, balloonPos, 0f, 1.45f, Color4.FromBytes(40, 208, 62)));
            ItemBoxSpawn balloonBox = new ItemBoxSpawn();
            balloonBox.Position = new Vec3(-128f * mSign, 3.2f, 82f);
            balloonBox.Active = true;
            balloonBox.AttachedToBalloon = true;
            t.ItemBoxes.Add(balloonBox);

            // Iconic Grandstand on the Left topped with Giant 3D Green Luigi Cap + Lush 3-Tier Topiary Trees!
            t.AddPropAtSegment(14, -27f, 0f, PropKind.Grandstand, 1.35f, Color4.FromBytes(38, 196, 52));
            t.AddPropAtSegment(334, -27f, 0f, PropKind.Grandstand, 1.25f, Color4.FromBytes(38, 196, 52));

            for (int s = 18; s < t.Segments.Length; s += 16)
            {
                if ((t.Segments[s].Flags & (SegmentFlags.Tunnel | SegmentFlags.Bridge)) != 0) continue;
                t.AddPropAtSegment(s, 25.5f, 0f, PropKind.TreeRound, 1.25f, Color4.FromBytes(48, 185, 58));
                if (s % 32 == 0)
                    t.AddPropAtSegment(s, -25.5f, 0f, PropKind.TreeRound, 1.15f, Color4.FromBytes(58, 195, 65));
            }
            return t;
        }

        public static TrackData CreateMooMooFarm(bool mirror)
        {
            TrackData t = new TrackData();
            t.Id = CourseId.MooMooFarm;
            t.Name = "MOO MOO FARM";
            t.CupName = "MUSHROOM CUP";
            t.Music = MusicTrackId.FarmAndBeach;
            t.SkyTopColor = Color4.FromBytes(48, 138, 248);
            t.SkyHorizonColor = Color4.FromBytes(198, 234, 255);
            t.GroundPlaneColor = Color4.FromBytes(58, 182, 46);
            t.CurbColorA = Color4.FromBytes(162, 108, 56);
            t.CurbColorB = Color4.FromBytes(232, 202, 152);
            t.WallColor = Color4.FromBytes(148, 98, 48);

            // Authentic Clockwise Wide Dirt Country Loop (matches MarioWiki + characters--4.png!):
            // Wide HalfWidth = 18.5..20.0, White 2-Rail Ranch Fences on BOTH sides, uphill Right Turn 1,
            // rolling back pasture with slight Left/Right bends & popping Monty Moles, sweeping Right return!
            ControlNode[] nodes = new ControlNode[]
            {
                new ControlNode(   0f,  0.2f,   0f, 18.5f,  0f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.OffRoadShoulder, SegmentFlags.CheckerFinish),
                new ControlNode(   2f,  2.2f,  78f, 18.5f,  0f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.OffRoadShoulder, SegmentFlags.None),
                new ControlNode(  46f,  6.4f, 152f, 19.5f, -5f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.OffRoadShoulder, SegmentFlags.None),
                new ControlNode( 128f,  7.2f, 182f, 20.0f, -5f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.OffRoadShoulder, SegmentFlags.None),
                new ControlNode( 204f,  4.0f, 146f, 20.0f, -4f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.OffRoadShoulder, SegmentFlags.None),
                new ControlNode( 226f,  1.4f,  68f, 19.5f,  0f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.OffRoadShoulder, SegmentFlags.None),
                new ControlNode( 192f,  0.5f,  -4f, 19.0f,  4f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.OffRoadShoulder, SegmentFlags.None),
                new ControlNode( 218f,  1.8f, -82f, 20.0f, -4f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.OffRoadShoulder, SegmentFlags.None),
                new ControlNode( 192f,  3.6f,-158f, 20.0f, -6f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.OffRoadShoulder, SegmentFlags.None),
                new ControlNode( 116f,  2.2f,-188f, 19.5f, -5f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.OffRoadShoulder, SegmentFlags.None),
                new ControlNode(  38f,  1.0f,-154f, 18.5f, -4f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.OffRoadShoulder, SegmentFlags.None),
                new ControlNode(  -2f,  0.3f, -78f, 18.5f,  0f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.OffRoadShoulder, SegmentFlags.None)
            };

            t.BuildClosedSpline(nodes, 24, SurfaceType.Dirt, SurfaceType.OffRoadGrass, mirror);

            t.AddItemBoxRow(32, 5);
            t.AddItemBoxRow(126, 5);
            t.AddItemBoxRow(220, 5);

            // Red Barn + Silo, Grazing SGI Moo Moo Cows in fenced pastures, & 3-Tier Topiary Trees!
            t.AddPropAtSegment(16, -34f, 0f, PropKind.RedBarn, 1.55f, Color4.FromBytes(212, 38, 36));
            t.AddPropAtSegment(98,  36f, 0f, PropKind.RedBarn, 1.35f, Color4.FromBytes(202, 44, 38));
            for (int s = 10; s < t.Segments.Length; s += 12)
            {
                t.AddPropAtSegment(s, (s % 24 == 0) ? 26.5f : -26.5f, 0f, PropKind.MooMooCow, 1.15f, Color4.FromBytes(250, 250, 250), 1.57f);
            }
            for (int s = 18; s < t.Segments.Length; s += 24)
            {
                t.AddPropAtSegment(s, 32f, 0f, PropKind.TreeRound, 1.25f, Color4.FromBytes(58, 182, 52));
            }

            // Monty Moles (Chubbies) popping out of the inner & outer dirt bends (rendered with SGI TexMontyMole!)
            int[] moleSegs = { 108, 120, 132, 146, 176, 188, 200, 214, 228 };
            for (int i = 0; i < moleSegs.Length; i++)
            {
                TrackSegment seg = t.Segments[moleSegs[i] % t.Segments.Length];
                float lat = ((i % 2 == 0) ? 0.52f : -0.38f) * seg.HalfWidth;
                HazardSpawnSpec hs = new HazardSpawnSpec();
                hs.Kind = HazardKind.MontyMole;
                hs.BasePos = seg.Center + seg.Right * lat;
                hs.SegmentIndex = seg.Index;
                hs.PhaseOffset = i * 0.78f;
                hs.Speed = 2.4f;
                t.HazardSpecs.Add(hs);
            }

            return t;
        }

        public static TrackData CreateKoopaTroopaBeach(bool mirror)
        {
            TrackData t = new TrackData();
            t.Id = CourseId.KoopaTroopaBeach;
            t.Name = "KOOPA TROOPA BEACH";
            t.CupName = "MUSHROOM CUP";
            t.Music = MusicTrackId.FarmAndBeach;
            t.SkyTopColor = Color4.FromBytes(28, 152, 248);
            t.SkyHorizonColor = Color4.FromBytes(255, 232, 182);
            t.GroundPlaneColor = Color4.FromBytes(242, 216, 148);
            t.CurbColorA = Color4.FromBytes(245, 212, 130);
            t.CurbColorB = Color4.FromBytes(98, 218, 242);
            t.WallColor = Color4.FromBytes(155, 128, 92);
            t.HasWaterPlane = true;
            t.LiquidPlaneY = -2.1f;

            // Authentic MarioWiki Koopa Troopa Beach:
            // Cliffs on Left, Turquoise Ocean on Right -> slight Right-Left -> long LEFT curve around island ->
            // Rocky Arch / Cave Shortcut -> wide RIGHT bay with Boost Ramps -> gradual LEFT return to finish!
            ControlNode[] nodes = new ControlNode[]
            {
                new ControlNode(   0f, 0.5f,   0f, 19.5f,  0f, EdgeBehavior.SolidWall,       EdgeBehavior.WaterDrop, SegmentFlags.CheckerFinish),
                new ControlNode(  18f, 0.5f,  86f, 20.0f,  0f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.WaterDrop, SegmentFlags.None),
                new ControlNode(  -8f, 0.4f, 168f, 20.5f,  2f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.WaterDrop, SegmentFlags.None),
                new ControlNode( -92f, 0.3f, 224f, 21.0f,  4f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.WaterDrop, SegmentFlags.BoostPad),
                new ControlNode(-196f, 0.6f, 196f, 20.0f,  4f, EdgeBehavior.SolidWall,       EdgeBehavior.WaterDrop, SegmentFlags.None),
                new ControlNode(-258f, 1.2f, 112f, 19.5f, -3f, EdgeBehavior.WaterDrop,       EdgeBehavior.OffRoadShoulder, SegmentFlags.BoostPad),
                new ControlNode(-248f, 1.5f,  16f, 19.5f, -3f, EdgeBehavior.WaterDrop,       EdgeBehavior.OffRoadShoulder, SegmentFlags.None),
                new ControlNode(-196f, 3.2f, -68f, 18.0f,  0f, EdgeBehavior.SolidWall,       EdgeBehavior.SolidWall, SegmentFlags.Tunnel),
                new ControlNode(-124f, 1.6f,-136f, 20.0f,  4f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.WaterDrop, SegmentFlags.None),
                new ControlNode( -42f, 0.6f,-154f, 20.0f,  3f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.WaterDrop, SegmentFlags.None),
                new ControlNode(   2f, 0.5f, -78f, 19.5f,  0f, EdgeBehavior.SolidWall,       EdgeBehavior.WaterDrop, SegmentFlags.None)
            };

            t.BuildClosedSpline(nodes, 26, SurfaceType.Sand, SurfaceType.OffRoadSand, mirror);

            // Famous Koopa Rock Ramp & Cliff Cave Tunnel Shortcut!
            ControlNode[] caveNodes = new ControlNode[]
            {
                new ControlNode( -32f, 0.5f, 178f, 9.5f, 0f, EdgeBehavior.SolidWall, EdgeBehavior.SolidWall, SegmentFlags.BoostPad | SegmentFlags.JumpRamp),
                new ControlNode( -96f, 4.2f, 132f, 9.0f, 0f, EdgeBehavior.SolidWall, EdgeBehavior.SolidWall, SegmentFlags.Tunnel),
                new ControlNode(-168f, 2.4f,  86f, 9.0f, 0f, EdgeBehavior.SolidWall, EdgeBehavior.SolidWall, SegmentFlags.Tunnel),
                new ControlNode(-236f, 1.2f,  44f, 9.5f, 0f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.OffRoadShoulder, SegmentFlags.None)
            };
            BranchSpline shortcut = t.AddBranchSpline("KoopaRockCave", 54, 152, caveNodes, 12, SurfaceType.Sand, true);
            t.AddBranchItemBoxes(shortcut, 18, 1);

            t.AddItemBoxRow(34, 5);
            t.AddItemBoxRow(124, 5);
            t.AddItemBoxRow(228, 5);

            // Giant Koopa Rock centerpiece & SGI Tropical Palm Trees!
            float mSign = mirror ? 1f : -1f;
            t.Props.Add(new TrackProp(PropKind.KoopaRock, new Vec3(-124f * mSign, 0f, 38f), 0.4f, 2.5f, Color4.FromBytes(168, 142, 102)));
            for (int s = 10; s < t.Segments.Length; s += 14)
            {
                if ((t.Segments[s].Flags & SegmentFlags.Tunnel) != 0) continue;
                t.AddPropAtSegment(s, -24.5f, 0f, PropKind.TreePalm, 1.35f, Color4.FromBytes(45, 195, 65));
            }
            return t;
        }

        public static TrackData CreateKalimariDesert(bool mirror)
        {
            TrackData t = new TrackData();
            t.Id = CourseId.KalimariDesert;
            t.Name = "KALIMARI DESERT";
            t.CupName = "MUSHROOM CUP";
            t.Music = MusicTrackId.DesertAndHighway;
            t.SkyTopColor = Color4.FromBytes(48, 132, 235);
            t.SkyHorizonColor = Color4.FromBytes(255, 208, 148);
            t.GroundPlaneColor = Color4.FromBytes(222, 148, 76);
            t.CurbColorA = Color4.FromBytes(205, 82, 36);
            t.CurbColorB = Color4.FromBytes(245, 214, 158);
            t.WallColor = Color4.FromBytes(178, 92, 48);
            t.FogColor = Color4.FromBytes(245, 198, 145);
            t.FogStart = 280f;
            t.FogEnd = 720f;

            // Authentic MarioWiki Kalimari Desert:
            // Red mesa on Left -> gradual LEFT U-turn -> 1st Railroad Crossing -> slight RIGHT bend + Items ->
            // 2nd Railroad Crossing -> long gradual LEFT U-turn -> slight Right-Left to Finish!
            ControlNode[] nodes = new ControlNode[]
            {
                new ControlNode(   0f, 0.0f,   0f, 18.0f,  0f, EdgeBehavior.SolidWall,       EdgeBehavior.OffRoadShoulder, SegmentFlags.CheckerFinish),
                new ControlNode(   0f, 0.3f,  92f, 18.0f,  0f, EdgeBehavior.SolidWall,       EdgeBehavior.OffRoadShoulder, SegmentFlags.None),
                new ControlNode( -48f, 1.6f, 182f, 18.5f,  4f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.OffRoadShoulder, SegmentFlags.None),
                new ControlNode(-145f, 0.0f, 212f, 19.0f,  0f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.OffRoadShoulder, SegmentFlags.None), // Crossing #1!
                new ControlNode(-228f, 1.4f, 168f, 18.5f,  5f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.SolidWall,       SegmentFlags.None),
                new ControlNode(-248f, 2.6f,  78f, 18.5f,  0f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.SolidWall,       SegmentFlags.None),
                new ControlNode(-204f, 1.2f,   4f, 18.5f, -4f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.OffRoadShoulder, SegmentFlags.None),
                new ControlNode(-226f, 0.8f, -78f, 18.5f,  4f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.OffRoadShoulder, SegmentFlags.None),
                new ControlNode(-145f, 0.0f,-138f, 19.0f,  0f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.OffRoadShoulder, SegmentFlags.None), // Crossing #2!
                new ControlNode( -56f, 1.4f,-178f, 18.5f,  5f, EdgeBehavior.OffRoadShoulder, EdgeBehavior.OffRoadShoulder, SegmentFlags.None),
                new ControlNode(   8f, 0.5f, -96f, 18.0f,  0f, EdgeBehavior.SolidWall,       EdgeBehavior.OffRoadShoulder, SegmentFlags.None)
            };

            t.BuildClosedSpline(nodes, 28, SurfaceType.Asphalt, SurfaceType.OffRoadSand, mirror);

            t.AddItemBoxRow(34, 5);
            t.AddItemBoxRow(132, 5);
            t.AddItemBoxRow(232, 5);

            // Crossing Gates at both railroad intersections
            t.AddPropAtSegment(84, -21f, 0f, PropKind.RailCrossingGate, 1.35f, Color4.FromBytes(235, 40, 40));
            t.AddPropAtSegment(84,  21f, 0f, PropKind.RailCrossingGate, 1.35f, Color4.FromBytes(235, 40, 40));
            t.AddPropAtSegment(224,-21f, 0f, PropKind.RailCrossingGate, 1.35f, Color4.FromBytes(235, 40, 40));
            t.AddPropAtSegment(224, 21f, 0f, PropKind.RailCrossingGate, 1.35f, Color4.FromBytes(235, 40, 40));

            // Saguaro SGI Cacti dotting the desert!
            for (int s = 12; s < t.Segments.Length; s += 15)
            {
                t.AddPropAtSegment(s, (s % 30 == 0) ? 26.5f : -26.5f, 0f, PropKind.Cactus, 1.4f, Color4.FromBytes(48, 158, 58));
            }

            // Moving Kalimari Steam Locomotive + 3 Passenger Cars circling the closed railroad loop!
            float mSign = mirror ? 1f : -1f;
            Vec3[] trainLoop = new Vec3[24];
            for (int i = 0; i < 24; i++)
            {
                float ang = (i / 24.0f) * MathUtil.TWO_PI;
                float tx = (-145f + (float)Math.Cos(ang) * 52f) * mSign;
                float tz = 38f + (float)Math.Sin(ang) * 182f;
                trainLoop[i] = new Vec3(tx, 0.3f, tz);
            }
            for (int car = 0; car < 4; car++)
            {
                HazardSpawnSpec trainSpec = new HazardSpawnSpec();
                trainSpec.Kind = HazardKind.KalimariTrain;
                trainSpec.Speed = 34.0f;
                trainSpec.PhaseOffset = car * 0.042f;
                trainSpec.PatrolRadius = car;
                trainSpec.CustomLoop = trainLoop;
                t.HazardSpecs.Add(trainSpec);
            }

            return t;
        }
    }
}
