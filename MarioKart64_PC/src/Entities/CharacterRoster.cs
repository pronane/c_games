using System;
using MarioKart64.Core;

namespace MarioKart64.Entities
{
    public enum CharacterId
    {
        Mario = 0,
        Luigi = 1,
        Peach = 2,
        Toad = 3,
        Yoshi = 4,
        DonkeyKong = 5,
        Wario = 6,
        Bowser = 7
    }

    public enum WeightClass
    {
        Light = 0,
        Medium = 1,
        Heavy = 2
    }

    public class CharacterSpec
    {
        public CharacterId Id;
        public string Name;
        public string ShortName;
        public char EmblemChar;
        public WeightClass WeightClass;

        // Authentic MK64 Physics Multipliers
        public float TopSpeed;          // Base m/s at 100cc (Light & Heavy slightly edge Medium in MK64, Toad/Peach/Yoshi fastest nimble)
        public float Acceleration;      // Light = fastest 0..max, Heavy = slowest 0..max
        public float TurnRate;          // Rad/s base steering responsiveness
        public float DriftGrip;         // Lateral traction while drifting
        public float OffRoadRetention;  // Speed multiplier off-road
        public float Mass;              // Used in kart-to-kart collisions (Bowser > DK/Wario > Mario/Luigi > Yoshi/Peach/Toad)

        // Visual Colors for 3D Kart + Driver Head/Hat/Outfit + Minimap Icon
        public Color4 PrimaryColor;
        public Color4 SecondaryColor;
        public Color4 HatOrHeadColor;
        public Color4 SkinOrSnoutColor;
        public Color4 AccentColor;
    }

    public static class CharacterRoster
    {
        public const int Count = 8;

        // Exact MK64 Character Select Grid Order:
        // Top Row:    Mario, Luigi, Peach, Toad
        // Bottom Row: Yoshi, D.K.,  Wario, Bowser
        public static readonly CharacterSpec[] All = new CharacterSpec[Count]
        {
            new CharacterSpec
            {
                Id = CharacterId.Mario,
                Name = "MARIO",
                ShortName = "MAR",
                EmblemChar = 'M',
                WeightClass = WeightClass.Medium,
                TopSpeed = 62.5f,
                Acceleration = 33.0f,
                TurnRate = 2.08f,
                DriftGrip = 0.90f,
                OffRoadRetention = 0.62f,
                Mass = 1.00f,
                PrimaryColor = Color4.FromBytes(230, 32, 32),
                SecondaryColor = Color4.FromBytes(32, 85, 220),
                HatOrHeadColor = Color4.FromBytes(235, 30, 30),
                SkinOrSnoutColor = Color4.FromBytes(250, 200, 158),
                AccentColor = Color4.FromBytes(255, 255, 255)
            },
            new CharacterSpec
            {
                Id = CharacterId.Luigi,
                Name = "LUIGI",
                ShortName = "LUI",
                EmblemChar = 'L',
                WeightClass = WeightClass.Medium,
                TopSpeed = 62.7f,
                Acceleration = 32.5f,
                TurnRate = 2.10f,
                DriftGrip = 0.91f,
                OffRoadRetention = 0.63f,
                Mass = 0.98f,
                PrimaryColor = Color4.FromBytes(32, 195, 58),
                SecondaryColor = Color4.FromBytes(32, 80, 210),
                HatOrHeadColor = Color4.FromBytes(32, 200, 58),
                SkinOrSnoutColor = Color4.FromBytes(250, 200, 158),
                AccentColor = Color4.FromBytes(255, 255, 255)
            },
            new CharacterSpec
            {
                Id = CharacterId.Peach,
                Name = "PEACH",
                ShortName = "PEA",
                EmblemChar = 'P',
                WeightClass = WeightClass.Light,
                TopSpeed = 63.6f,
                Acceleration = 41.5f,
                TurnRate = 2.30f,
                DriftGrip = 0.95f,
                OffRoadRetention = 0.70f,
                Mass = 0.76f,
                PrimaryColor = Color4.FromBytes(255, 118, 192),
                SecondaryColor = Color4.FromBytes(220, 48, 135),
                HatOrHeadColor = Color4.FromBytes(255, 225, 65), // Blonde hair + Gold Crown
                SkinOrSnoutColor = Color4.FromBytes(255, 212, 180),
                AccentColor = Color4.FromBytes(60, 180, 255)
            },
            new CharacterSpec
            {
                Id = CharacterId.Toad,
                Name = "TOAD",
                ShortName = "TOA",
                EmblemChar = 'T',
                WeightClass = WeightClass.Light,
                TopSpeed = 63.8f,
                Acceleration = 43.0f,
                TurnRate = 2.36f,
                DriftGrip = 0.96f,
                OffRoadRetention = 0.72f,
                Mass = 0.72f,
                PrimaryColor = Color4.FromBytes(45, 115, 245),
                SecondaryColor = Color4.FromBytes(248, 248, 252),
                HatOrHeadColor = Color4.FromBytes(252, 252, 255), // White mushroom cap with red spots
                SkinOrSnoutColor = Color4.FromBytes(252, 206, 170),
                AccentColor = Color4.FromBytes(235, 32, 32)
            },
            new CharacterSpec
            {
                Id = CharacterId.Yoshi,
                Name = "YOSHI",
                ShortName = "YOS",
                EmblemChar = 'Y',
                WeightClass = WeightClass.Light,
                TopSpeed = 63.7f,
                Acceleration = 42.0f,
                TurnRate = 2.32f,
                DriftGrip = 0.95f,
                OffRoadRetention = 0.71f,
                Mass = 0.78f,
                PrimaryColor = Color4.FromBytes(65, 218, 65),
                SecondaryColor = Color4.FromBytes(245, 245, 245),
                HatOrHeadColor = Color4.FromBytes(68, 220, 68),
                SkinOrSnoutColor = Color4.FromBytes(115, 238, 105),
                AccentColor = Color4.FromBytes(235, 50, 40) // Red saddle/crest
            },
            new CharacterSpec
            {
                Id = CharacterId.DonkeyKong,
                Name = "D.K.",
                ShortName = "D.K",
                EmblemChar = 'D',
                WeightClass = WeightClass.Heavy,
                TopSpeed = 63.3f,
                Acceleration = 25.5f,
                TurnRate = 1.88f,
                DriftGrip = 0.84f,
                OffRoadRetention = 0.56f,
                Mass = 1.28f,
                PrimaryColor = Color4.FromBytes(165, 96, 36),
                SecondaryColor = Color4.FromBytes(242, 198, 35),
                HatOrHeadColor = Color4.FromBytes(132, 72, 25),
                SkinOrSnoutColor = Color4.FromBytes(218, 165, 112),
                AccentColor = Color4.FromBytes(230, 30, 30) // DK Red Tie
            },
            new CharacterSpec
            {
                Id = CharacterId.Wario,
                Name = "WARIO",
                ShortName = "WAR",
                EmblemChar = 'W',
                WeightClass = WeightClass.Heavy,
                TopSpeed = 63.4f,
                Acceleration = 26.0f,
                TurnRate = 1.90f,
                DriftGrip = 0.85f,
                OffRoadRetention = 0.57f,
                Mass = 1.30f,
                PrimaryColor = Color4.FromBytes(250, 218, 25),
                SecondaryColor = Color4.FromBytes(142, 38, 190),
                HatOrHeadColor = Color4.FromBytes(252, 222, 25),
                SkinOrSnoutColor = Color4.FromBytes(245, 192, 155),
                AccentColor = Color4.FromBytes(142, 38, 190)
            },
            new CharacterSpec
            {
                Id = CharacterId.Bowser,
                Name = "BOWSER",
                ShortName = "BOW",
                EmblemChar = 'B',
                WeightClass = WeightClass.Heavy,
                TopSpeed = 63.6f,
                Acceleration = 24.0f,
                TurnRate = 1.84f,
                DriftGrip = 0.83f,
                OffRoadRetention = 0.55f,
                Mass = 1.40f,
                PrimaryColor = Color4.FromBytes(242, 110, 22),
                SecondaryColor = Color4.FromBytes(38, 148, 48),
                HatOrHeadColor = Color4.FromBytes(225, 45, 25), // Fiery red mane + horns
                SkinOrSnoutColor = Color4.FromBytes(242, 188, 52),
                AccentColor = Color4.FromBytes(245, 240, 220) // Shell spikes
            }
        };

        public static CharacterSpec Get(CharacterId id)
        {
            return All[(int)id];
        }

        public static CharacterSpec Get(int index)
        {
            return All[MathUtil.ClampInt(index, 0, Count - 1)];
        }

        // Authentic MK64 Rival Table: each character has designated primary rivals in GP!
        public static CharacterId GetPrimaryRival(CharacterId playerChar)
        {
            switch (playerChar)
            {
                case CharacterId.Mario:      return CharacterId.Bowser;
                case CharacterId.Luigi:      return CharacterId.Wario;
                case CharacterId.Peach:      return CharacterId.Bowser;
                case CharacterId.Toad:       return CharacterId.DonkeyKong;
                case CharacterId.Yoshi:      return CharacterId.Wario;
                case CharacterId.DonkeyKong: return CharacterId.Toad;
                case CharacterId.Wario:      return CharacterId.Mario;
                case CharacterId.Bowser:     return CharacterId.Mario;
                default:                     return CharacterId.Bowser;
            }
        }
    }
}
