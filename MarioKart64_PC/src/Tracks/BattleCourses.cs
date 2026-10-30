using System;
using MarioKart64.Audio;
using MarioKart64.Core;

namespace MarioKart64.Tracks
{
    public static class BattleCourses
    {
        private static void AddFloor(TrackData t, float x1, float z1, float x2, float z2, float y, Color4 col, SurfaceType surf = SurfaceType.Asphalt)
        {
            ArenaPlatform p = new ArenaPlatform();
            p.Min = new Vec3(Math.Min(x1, x2), y - 2.0f, Math.Min(z1, z2));
            p.Max = new Vec3(Math.Max(x1, x2), y, Math.Max(z1, z2));
            p.Color = col;
            p.Surface = surf;
            p.IsSolidWall = false;
            p.IsHazardFloor = false;
            t.ArenaPlatforms.Add(p);
        }

        private static void AddWallBlock(TrackData t, float x1, float y1, float z1, float x2, float y2, float z2, Color4 col)
        {
            ArenaPlatform p = new ArenaPlatform();
            p.Min = new Vec3(Math.Min(x1, x2), Math.Min(y1, y2), Math.Min(z1, z2));
            p.Max = new Vec3(Math.Max(x1, x2), Math.Max(y1, y2), Math.Max(z1, z2));
            p.Color = col;
            p.Surface = SurfaceType.Asphalt;
            p.IsSolidWall = true;
            t.ArenaPlatforms.Add(p);
        }

        private static void AddRamp(TrackData t, Vec3 start, Vec3 end, float halfWidth, Color4 col)
        {
            ArenaRamp r = new ArenaRamp();
            r.StartCenter = start;
            r.EndCenter = end;
            r.HalfWidth = halfWidth;
            r.Color = col;
            t.ArenaRamps.Add(r);
        }

        private static void AddBox(TrackData t, float x, float y, float z)
        {
            ItemBoxSpawn b = new ItemBoxSpawn();
            b.Position = new Vec3(x, y + 1.55f, z);
            b.Active = true;
            t.ItemBoxes.Add(b);
        }

        private static void AddPerimeterWalls(TrackData t, float halfSize, float wallTopY, Color4 col)
        {
            float th = 3.0f;
            AddWallBlock(t, -halfSize - th, -4f, -halfSize - th,  halfSize + th, wallTopY, -halfSize, col);
            AddWallBlock(t, -halfSize - th, -4f,  halfSize,       halfSize + th, wallTopY,  halfSize + th, col);
            AddWallBlock(t, -halfSize - th, -4f, -halfSize,      -halfSize,      wallTopY,  halfSize, col);
            AddWallBlock(t,  halfSize,      -4f, -halfSize,       halfSize + th, wallTopY,  halfSize, col);
        }

        public static TrackData CreateBigDonut()
        {
            TrackData t = new TrackData();
            t.Id = CourseId.BigDonut;
            t.Name = "BIG DONUT";
            t.CupName = "BATTLE MODE";
            t.IsBattleArena = true;
            t.Music = MusicTrackId.BattleArena;
            t.HasLavaPlane = true;
            t.LiquidPlaneY = -2.5f;
            t.SkyTopColor = Color4.FromBytes(48, 16, 14);
            t.SkyHorizonColor = Color4.FromBytes(175, 58, 22);
            t.GroundPlaneColor = Color4.FromBytes(235, 72, 16);

            Color4 stone = Color4.FromBytes(152, 145, 138);
            // Outer ring slabs surrounding a boiling central lava hole (-26..+26)
            AddFloor(t, -72f, -72f,  72f, -26f, 0f, stone, SurfaceType.CastleStone);
            AddFloor(t, -72f,  26f,  72f,  72f, 0f, stone, SurfaceType.CastleStone);
            AddFloor(t, -72f, -26f, -26f,  26f, 0f, stone, SurfaceType.CastleStone);
            AddFloor(t,  26f, -26f,  72f,  26f, 0f, stone, SurfaceType.CastleStone);

            AddPerimeterWalls(t, 72f, 6.5f, Color4.FromBytes(98, 92, 95));

            // 4 low inner guard blocks around the lava pit
            Color4 guardCol = Color4.FromBytes(185, 175, 162);
            AddWallBlock(t, -12f, 0f, -27.5f, 12f, 2.2f, -25.5f, guardCol);
            AddWallBlock(t, -12f, 0f,  25.5f, 12f, 2.2f,  27.5f, guardCol);
            AddWallBlock(t, -27.5f, 0f, -12f,-25.5f, 2.2f, 12f, guardCol);
            AddWallBlock(t,  25.5f, 0f, -12f, 27.5f, 2.2f, 12f, guardCol);

            AddBox(t,   0f, 0f, -49f); AddBox(t,   0f, 0f,  49f);
            AddBox(t, -49f, 0f,   0f); AddBox(t,  49f, 0f,   0f);
            AddBox(t, -42f, 0f, -42f); AddBox(t,  42f, 0f, -42f);
            AddBox(t, -42f, 0f,  42f); AddBox(t,  42f, 0f,  42f);

            t.BattleSpawnPositions = new Vec3[]
            {
                new Vec3(  0f, 0.5f, -52f),
                new Vec3(  0f, 0.5f,  52f),
                new Vec3(-52f, 0.5f,   0f),
                new Vec3( 52f, 0.5f,   0f)
            };
            t.BattleSpawnYaws = new float[] { 1.57f, -1.57f, 0f, 3.14f };
            return t;
        }

        public static TrackData CreateBlockFort()
        {
            TrackData t = new TrackData();
            t.Id = CourseId.BlockFort;
            t.Name = "BLOCK FORT";
            t.CupName = "BATTLE MODE";
            t.IsBattleArena = true;
            t.Music = MusicTrackId.BattleArena;
            t.SkyTopColor = Color4.FromBytes(42, 125, 238);
            t.SkyHorizonColor = Color4.FromBytes(185, 226, 255);
            t.GroundPlaneColor = Color4.FromBytes(115, 118, 125);

            // Ground street grid
            AddFloor(t, -78f, -78f, 78f, 78f, 0f, Color4.FromBytes(118, 122, 130));
            AddPerimeterWalls(t, 78f, 14f, Color4.FromBytes(145, 148, 158));

            // 4 Iconic Colored Two-Story Forts: Red, Blue, Green, Yellow!
            Color4 red    = Color4.FromBytes(220, 52, 48);
            Color4 blue   = Color4.FromBytes(48, 102, 225);
            Color4 green  = Color4.FromBytes(48, 185, 68);
            Color4 yellow = Color4.FromBytes(238, 198, 38);

            AddWallBlock(t, -62f, 0f, -62f, -22f, 7.0f, -22f, red);
            AddWallBlock(t,  22f, 0f, -62f,  62f, 7.0f, -22f, blue);
            AddWallBlock(t, -62f, 0f,  22f, -22f, 7.0f,  62f, green);
            AddWallBlock(t,  22f, 0f,  22f,  62f, 7.0f,  62f, yellow);

            // 4 Narrow Upper Skybridges connecting the 4 Forts at Y = 7.0!
            Color4 bridgeCol = Color4.FromBytes(198, 202, 210);
            AddFloor(t, -22f, -46f,  22f, -38f, 7.0f, bridgeCol);
            AddFloor(t, -22f,  38f,  22f,  46f, 7.0f, bridgeCol);
            AddFloor(t, -46f, -22f, -38f,  22f, 7.0f, bridgeCol);
            AddFloor(t,  38f, -22f,  46f,  22f, 7.0f, bridgeCol);

            // Ramps climbing from ground street level (Y=0) up to each Fort roof (Y=7.0)!
            AddRamp(t, new Vec3(-70f, 0f, -15f), new Vec3(-52f, 7.0f, -22f), 5.5f, red);
            AddRamp(t, new Vec3( 70f, 0f, -15f), new Vec3( 52f, 7.0f, -22f), 5.5f, blue);
            AddRamp(t, new Vec3(-70f, 0f,  15f), new Vec3(-52f, 7.0f,  22f), 5.5f, green);
            AddRamp(t, new Vec3( 70f, 0f,  15f), new Vec3( 52f, 7.0f,  22f), 5.5f, yellow);

            // Street & Skybridge Item Boxes
            AddBox(t,  0f, 0f,   0f);
            AddBox(t,  0f, 0f, -42f); AddBox(t,  0f, 0f, 42f);
            AddBox(t, -42f,0f,   0f); AddBox(t, 42f, 0f,  0f);
            AddBox(t,  0f, 7f, -42f); AddBox(t,  0f, 7f, 42f);
            AddBox(t, -42f,7f,   0f); AddBox(t, 42f, 7f,  0f);

            t.BattleSpawnPositions = new Vec3[]
            {
                new Vec3(-42f, 7.5f, -42f),
                new Vec3( 42f, 7.5f, -42f),
                new Vec3(-42f, 7.5f,  42f),
                new Vec3( 42f, 7.5f,  42f)
            };
            t.BattleSpawnYaws = new float[] { 0.78f, -0.78f, 2.35f, -2.35f };
            return t;
        }

        public static TrackData CreateDoubleDeck()
        {
            TrackData t = new TrackData();
            t.Id = CourseId.DoubleDeck;
            t.Name = "DOUBLE DECK";
            t.CupName = "BATTLE MODE";
            t.IsBattleArena = true;
            t.Music = MusicTrackId.BattleArena;
            t.SkyTopColor = Color4.FromBytes(28, 38, 72);
            t.SkyHorizonColor = Color4.FromBytes(88, 112, 165);
            t.GroundPlaneColor = Color4.FromBytes(165, 52, 52);

            // Tier 1: Red Base Deck (Y=0)
            AddFloor(t, -80f, -80f, 80f, 80f, 0f, Color4.FromBytes(178, 52, 52));
            AddPerimeterWalls(t, 80f, 16f, Color4.FromBytes(110, 115, 128));

            // Tier 2: Green Middle Deck (Y=5.5)
            AddFloor(t, -52f, -52f, 52f, 52f, 5.5f, Color4.FromBytes(48, 158, 72));
            AddRamp(t, new Vec3( 0f, 0f, -72f), new Vec3( 0f, 5.5f, -52f), 7.5f, Color4.FromBytes(95, 175, 95));
            AddRamp(t, new Vec3( 0f, 0f,  72f), new Vec3( 0f, 5.5f,  52f), 7.5f, Color4.FromBytes(95, 175, 95));

            // Tier 3: White Upper Deck (Y=11.0)
            AddFloor(t, -25f, -25f, 25f, 25f, 11.0f, Color4.FromBytes(225, 228, 238));
            AddRamp(t, new Vec3(-46f, 5.5f, 0f), new Vec3(-25f, 11.0f, 0f), 6.5f, Color4.FromBytes(235, 238, 245));
            AddRamp(t, new Vec3( 46f, 5.5f, 0f), new Vec3( 25f, 11.0f, 0f), 6.5f, Color4.FromBytes(235, 238, 245));

            AddBox(t, -64f, 0f, -64f); AddBox(t, 64f, 0f, -64f);
            AddBox(t, -64f, 0f,  64f); AddBox(t, 64f, 0f,  64f);
            AddBox(t, -36f, 5.5f, -36f); AddBox(t, 36f, 5.5f, 36f);
            AddBox(t,   0f, 11.0f, 0f);

            t.BattleSpawnPositions = new Vec3[]
            {
                new Vec3(-62f, 0.5f,   0f),
                new Vec3( 62f, 0.5f,   0f),
                new Vec3(  0f, 6.0f, -36f),
                new Vec3(  0f, 6.0f,  36f)
            };
            t.BattleSpawnYaws = new float[] { 1.57f, -1.57f, 0f, 3.14f };
            return t;
        }

        public static TrackData CreateSkyscraper()
        {
            TrackData t = new TrackData();
            t.Id = CourseId.Skyscraper;
            t.Name = "SKYSCRAPER";
            t.CupName = "BATTLE MODE";
            t.IsBattleArena = true;
            t.IsNightSky = true;
            t.HasVoidAbyss = true;
            t.Music = MusicTrackId.BattleArena;
            t.SkyTopColor = Color4.FromBytes(8, 10, 28);
            t.SkyHorizonColor = Color4.FromBytes(42, 32, 78);
            t.GroundPlaneColor = Color4.FromBytes(12, 14, 30);

            // High-altitude rooftop with abyss drop-offs around the perimeter & inner shafts!
            Color4 roof = Color4.FromBytes(132, 142, 165);
            Color4 centerCol = Color4.FromBytes(165, 175, 198);

            // Outer ring corridors
            AddFloor(t, -64f, -64f,  64f, -42f, 0f, roof);
            AddFloor(t, -64f,  42f,  64f,  64f, 0f, roof);
            AddFloor(t, -64f, -42f, -42f,  42f, 0f, roof);
            AddFloor(t,  42f, -42f,  64f,  42f, 0f, roof);

            // Central cross & hub (leaving 4 corner abyss shafts inside the roof!)
            AddFloor(t, -42f, -12f,  42f,  12f, 0f, centerCol);
            AddFloor(t, -12f, -42f,  12f,  42f, 0f, centerCol);

            AddBox(t,   0f, 0f,   0f);
            AddBox(t, -52f, 0f, -52f); AddBox(t,  52f, 0f, -52f);
            AddBox(t, -52f, 0f,  52f); AddBox(t,  52f, 0f,  52f);
            AddBox(t,   0f, 0f, -52f); AddBox(t,   0f, 0f,  52f);

            t.BattleSpawnPositions = new Vec3[]
            {
                new Vec3(-52f, 0.5f,   0f),
                new Vec3( 52f, 0.5f,   0f),
                new Vec3(  0f, 0.5f, -52f),
                new Vec3(  0f, 0.5f,  52f)
            };
            t.BattleSpawnYaws = new float[] { 1.57f, -1.57f, 0f, 3.14f };
            return t;
        }
    }
}
