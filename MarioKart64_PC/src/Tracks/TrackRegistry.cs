using System;
using MarioKart64.Core;

namespace MarioKart64.Tracks
{
    public static class TrackRegistry
    {
        public const int RaceTrackCount = 16;
        public const int BattleCourseCount = 4;
        public const int TotalCourseCount = 20;

        public static readonly string[] CupNames = new string[4]
        {
            "MUSHROOM CUP",
            "FLOWER CUP",
            "STAR CUP",
            "SPECIAL CUP"
        };

        public static readonly string[] CourseNames = new string[TotalCourseCount]
        {
            "LUIGI RACEWAY",
            "MOO MOO FARM",
            "KOOPA TROOPA BEACH",
            "KALIMARI DESERT",
            "TOAD'S TURNPIKE",
            "FRAPPE SNOWLAND",
            "CHOCO MOUNTAIN",
            "MARIO RACEWAY",
            "WARIO STADIUM",
            "SHERBET LAND",
            "ROYAL RACEWAY",
            "BOWSER'S CASTLE",
            "D.K.'S JUNGLE PARKWAY",
            "YOSHI VALLEY",
            "BANSHEE BOARDWALK",
            "RAINBOW ROAD",
            "BIG DONUT",
            "BLOCK FORT",
            "DOUBLE DECK",
            "SKYSCRAPER"
        };

        public static CourseId GetCupCourse(CupType cup, int raceIndexInCup)
        {
            int idx = ((int)cup) * 4 + MathUtil.ClampInt(raceIndexInCup, 0, 3);
            return (CourseId)idx;
        }

        public static TrackData Create(CourseId id, bool mirror)
        {
            switch (id)
            {
                case CourseId.LuigiRaceway:     return MushroomCupTracks.CreateLuigiRaceway(mirror);
                case CourseId.MooMooFarm:       return MushroomCupTracks.CreateMooMooFarm(mirror);
                case CourseId.KoopaTroopaBeach: return MushroomCupTracks.CreateKoopaTroopaBeach(mirror);
                case CourseId.KalimariDesert:   return MushroomCupTracks.CreateKalimariDesert(mirror);

                case CourseId.ToadsTurnpike:    return FlowerCupTracks.CreateToadsTurnpike(mirror);
                case CourseId.FrappeSnowland:   return FlowerCupTracks.CreateFrappeSnowland(mirror);
                case CourseId.ChocoMountain:    return FlowerCupTracks.CreateChocoMountain(mirror);
                case CourseId.MarioRaceway:     return FlowerCupTracks.CreateMarioRaceway(mirror);

                case CourseId.WarioStadium:     return StarCupTracks.CreateWarioStadium(mirror);
                case CourseId.SherbetLand:      return StarCupTracks.CreateSherbetLand(mirror);
                case CourseId.RoyalRaceway:     return StarCupTracks.CreateRoyalRaceway(mirror);
                case CourseId.BowsersCastle:    return StarCupTracks.CreateBowsersCastle(mirror);

                case CourseId.DKsJungleParkway: return SpecialCupTracks.CreateDKsJungleParkway(mirror);
                case CourseId.YoshiValley:      return SpecialCupTracks.CreateYoshiValley(mirror);
                case CourseId.BansheeBoardwalk: return SpecialCupTracks.CreateBansheeBoardwalk(mirror);
                case CourseId.RainbowRoad:      return SpecialCupTracks.CreateRainbowRoad(mirror);

                case CourseId.BigDonut:         return BattleCourses.CreateBigDonut();
                case CourseId.BlockFort:        return BattleCourses.CreateBlockFort();
                case CourseId.DoubleDeck:       return BattleCourses.CreateDoubleDeck();
                case CourseId.Skyscraper:       return BattleCourses.CreateSkyscraper();
                default:                        return MushroomCupTracks.CreateLuigiRaceway(mirror);
            }
        }
    }
}
