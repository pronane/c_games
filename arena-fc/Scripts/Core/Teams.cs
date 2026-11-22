// Arena FC - fictional clubs, formations and roster generation (no licensed assets).
using System;
using System.Collections.Generic;
using System.Linq;
using System.Numerics;

namespace ArenaFC.Core;

public sealed class ClubInfo
{
    public string Name = "";
    public string Short = "";
    public string Primary = "#d7263d";
    public string Secondary = "#ffffff";
    public string Shorts = "#14213d";
    public string Socks = "#ffffff";
    public float Strength = .70f;
    // Phase 6: Home/away/third kits, stadium, league
    public string AwayPrimary = "";
    public string AwaySecondary = "";
    public string ThirdPrimary = "";
    public string Stadium = "Arena Stadium";
    public int LeagueId;
    public string Style = "Balanced"; // Attacking, Defensive, Possession, Counter
    /// <summary>Shirt design (CharacterSpec.KitPatterns) and trim; set from the club index in Clubs.</summary>
    public string Pattern = "plain";
    public string Trim = "";
}

public static class Clubs
{
    public static readonly ClubInfo[] All =
    {
        new() { Name="Harrow Lions",       Short="HAR", Primary="#d7263d", Secondary="#ffffff", Shorts="#14213d", Socks="#ffffff", Strength=.78f, AwayPrimary="#ffffff", AwaySecondary="#d7263d", ThirdPrimary="#14213d", Stadium="Lions Den", LeagueId=0, Style="Attacking" },
        new() { Name="Northgate United",   Short="NOR", Primary="#1d4ed8", Secondary="#f8fafc", Shorts="#1e3a8a", Socks="#f8fafc", Strength=.82f, AwayPrimary="#f8fafc", AwaySecondary="#1d4ed8", ThirdPrimary="#dc2626", Stadium="Northgate Arena", LeagueId=0, Style="Possession" },
        new() { Name="Riverport City",     Short="RIV", Primary="#38bdf8", Secondary="#0f172a", Shorts="#e2e8f0", Socks="#0ea5e9", Strength=.76f, AwayPrimary="#0f172a", AwaySecondary="#38bdf8", ThirdPrimary="#f59e0b", Stadium="Riverport Stadium", LeagueId=0, Style="Balanced" },
        new() { Name="Kingsford FC",       Short="KIN", Primary="#7f1d3a", Secondary="#60a5fa", Shorts="#f8fafc", Socks="#1e3a8a", Strength=.74f, AwayPrimary="#60a5fa", AwaySecondary="#7f1d3a", ThirdPrimary="#ffffff", Stadium="Kingsford Park", LeagueId=0, Style="Defensive" },
        new() { Name="Val Verde Athletic", Short="VVA", Primary="#15803d", Secondary="#111827", Shorts="#111827", Socks="#166534", Strength=.72f, AwayPrimary="#111827", AwaySecondary="#15803d", ThirdPrimary="#fbbf24", Stadium="Estadio Verde", LeagueId=1, Style="Counter" },
        new() { Name="Aurora SC",          Short="AUR", Primary="#6d28d9", Secondary="#fbbf24", Shorts="#1f2937", Socks="#fbbf24", Strength=.80f, AwayPrimary="#fbbf24", AwaySecondary="#6d28d9", ThirdPrimary="#111827", Stadium="Aurora Dome", LeagueId=1, Style="Attacking" },
        new() { Name="Ironbridge Town",    Short="IRN", Primary="#ea580c", Secondary="#18181b", Shorts="#18181b", Socks="#ea580c", Strength=.70f, AwayPrimary="#18181b", AwaySecondary="#ea580c", ThirdPrimary="#ffffff", Stadium="Ironbridge Ground", LeagueId=1, Style="Defensive" },
        new() { Name="Meridian Rovers",    Short="MER", Primary="#f1f5f9", Secondary="#0f172a", Shorts="#0f172a", Socks="#f1f5f9", Strength=.75f, AwayPrimary="#0f172a", AwaySecondary="#f1f5f9", ThirdPrimary="#dc2626", Stadium="Meridian Stadium", LeagueId=1, Style="Balanced" },
        // Phase 6: 12 more clubs (20 total)
        new() { Name="Coastal FC",         Short="COS", Primary="#0891b2", Secondary="#ffffff", Shorts="#164e63", Socks="#0891b2", Strength=.73f, AwayPrimary="#ffffff", AwaySecondary="#0891b2", ThirdPrimary="#f59e0b", Stadium="Coastal Arena", LeagueId=2, Style="Possession" },
        new() { Name="Summit United",      Short="SUM", Primary="#7c3aed", Secondary="#ffffff", Shorts="#4c1d95", Socks="#7c3aed", Strength=.77f, AwayPrimary="#ffffff", AwaySecondary="#7c3aed", ThirdPrimary="#06b6d4", Stadium="Summit Stadium", LeagueId=2, Style="Attacking" },
        new() { Name="Harbor City",        Short="HBC", Primary="#0e7490", Secondary="#f0fdfa", Shorts="#155e75", Socks="#0e7490", Strength=.71f, AwayPrimary="#f0fdfa", AwaySecondary="#0e7490", ThirdPrimary="#f97316", Stadium="Harbor Ground", LeagueId=2, Style="Counter" },
        new() { Name="Pinnacle SC",        Short="PIN", Primary="#b45309", Secondary="#fef3c7", Shorts="#78350f", Socks="#b45309", Strength=.79f, AwayPrimary="#fef3c7", AwaySecondary="#b45309", ThirdPrimary="#1e40af", Stadium="Pinnacle Dome", LeagueId=2, Style="Balanced" },
        new() { Name="Emberton FC",        Short="EMB", Primary="#dc2626", Secondary="#111827", Shorts="#111827", Socks="#dc2626", Strength=.74f, AwayPrimary="#111827", AwaySecondary="#dc2626", ThirdPrimary="#f59e0b", Stadium="Emberton Park", LeagueId=3, Style="Attacking" },
        new() { Name="Frostbite United",   Short="FRO", Primary="#e0f2fe", Secondary="#0369a1", Shorts="#0369a1", Socks="#e0f2fe", Strength=.72f, AwayPrimary="#0369a1", AwaySecondary="#e0f2fe", ThirdPrimary="#dc2626", Stadium="Frostbite Arena", LeagueId=3, Style="Defensive" },
        new() { Name="Golden Gate FC",     Short="GGG", Primary="#f59e0b", Secondary="#111827", Shorts="#111827", Socks="#f59e0b", Strength=.81f, AwayPrimary="#111827", AwaySecondary="#f59e0b", ThirdPrimary="#dc2626", Stadium="Golden Gate Stadium", LeagueId=3, Style="Possession" },
        new() { Name="Silverton Rovers",   Short="SIL", Primary="#94a3b8", Secondary="#1e293b", Shorts="#1e293b", Socks="#94a3b8", Strength=.70f, AwayPrimary="#1e293b", AwaySecondary="#94a3b8", ThirdPrimary="#f59e0b", Stadium="Silverton Ground", LeagueId=3, Style="Balanced" },
        new() { Name="Crimson City",       Short="CRI", Primary="#991b1b", Secondary="#fef2f2", Shorts="#450a0a", Socks="#991b1b", Strength=.76f, AwayPrimary="#fef2f2", AwaySecondary="#991b1b", ThirdPrimary="#111827", Stadium="Crimson Stadium", LeagueId=4, Style="Counter" },
        new() { Name="Azure United",       Short="AZU", Primary="#2563eb", Secondary="#dbeafe", Shorts="#1e40af", Socks="#2563eb", Strength=.78f, AwayPrimary="#dbeafe", AwaySecondary="#2563eb", ThirdPrimary="#f59e0b", Stadium="Azure Arena", LeagueId=4, Style="Attacking" },
        new() { Name="Verdant FC",         Short="VER", Primary="#16a34a", Secondary="#f0fdf4", Shorts="#14532d", Socks="#16a34a", Strength=.73f, AwayPrimary="#f0fdf4", AwaySecondary="#16a34a", ThirdPrimary="#dc2626", Stadium="Verdant Park", LeagueId=4, Style="Possession" },
        new() { Name="Obsidian SC",        Short="OBS", Primary="#111827", Secondary="#f9fafb", Shorts="#f9fafb", Socks="#111827", Strength=.75f, AwayPrimary="#f9fafb", AwaySecondary="#111827", ThirdPrimary="#7c3aed", Stadium="Obsidian Dome", LeagueId=4, Style="Defensive" },
    };

    // Shirt designs and trims per club (index-aligned with All).  Original designs; set here rather
    // than drawn from the roster RNG so squads, attributes and match results are unchanged.
    private static readonly string[] ClubPatterns =
    {
        "band", "plain", "hoops", "halves", "stripes", "chevron", "fade", "sash", "pinstripes", "quarters",
        "plain", "stripes", "hoops", "fade", "pinstripes", "band", "sash", "plain", "stripes", "chevron",
    };

    // Goalkeeper kits: a colour no outfield kit of either club wears, with contrasting gloves.
    private static readonly (string shirt, string shorts, string socks, string gloves, string pattern)[] KeeperKits =
    {
        ("#a3e635", "#1a2e05", "#a3e635", "#f97316", "chevron"),
        ("#f97316", "#1c1917", "#f97316", "#38bdf8", "fade"),
        ("#facc15", "#1f2937", "#facc15", "#111827", "band"),
        ("#18181b", "#18181b", "#18181b", "#a3e635", "pinstripes"),
        ("#ec4899", "#3b0764", "#ec4899", "#f8fafc", "fade"),
        ("#14b8a6", "#042f2e", "#14b8a6", "#fde047", "chevron"),
    };

    static Clubs()
    {
        for (int i = 0; i < All.Length; i++)
        {
            All[i].Pattern = ClubPatterns[i % ClubPatterns.Length];
            if (All[i].Trim == "") All[i].Trim = All[i].Shorts == All[i].Primary ? All[i].Secondary : All[i].Shorts;
        }
    }

    /// <summary>The keeper's kit for a club, chosen to stay clear of both teams' outfield colours.</summary>
    public static (string shirt, string shorts, string socks, string gloves, string pattern) KeeperKit(int clubIndex)
    {
        var club = All[Math.Clamp(clubIndex, 0, All.Length - 1)];
        for (int k = 0; k < KeeperKits.Length; k++)
        {
            var kit = KeeperKits[(clubIndex + k) % KeeperKits.Length];
            if (ColourDistance(kit.shirt, club.Primary) > .35f && ColourDistance(kit.shirt, club.Secondary) > .35f) return kit;
        }
        return KeeperKits[clubIndex % KeeperKits.Length];
    }

    public static float ColourDistance(string a, string b)
    {
        Mx.HexToRgb(a, out float ar, out float ag, out float ab);
        Mx.HexToRgb(b, out float br, out float bg, out float bb);
        return MathF.Sqrt(((ar - br) * (ar - br) + (ag - bg) * (ag - bg) + (ab - bb) * (ab - bb)) / 3f);
    }

    public static readonly string[] FirstNames =
    { "Alex","Marco","Nico","Jamie","Rafael","Yuki","Omar","Luca","Elias","Tomas","Kai","Ivan","Samir","Diego","Felix","Noah","Milan","Ruben","Theo","Amir","Hugo","Leon" };
    public static readonly string[] LastNames =
    { "Varela","Okafor","Bianchi","Kovac","Silva","Nakamura","Haddad","Rossi","Lindqvist","Mendes","Adeyemi","Petrov","Costa","Duarte","Novak","Berg","Marino","Fletcher","Sorensen","Aziz","Moreau","Weber" };

    public static readonly string[] Formations = { "4-4-2", "4-3-3", "3-5-2", "2-3-1 (7s)", "1-2-1 (5s)" };

    // Phase 6: Stadiums, Leagues, Boots, Faces
    public static readonly StadiumInfo[] Stadiums =
    {
        new() { Name="Lions Den", Capacity=45000, Roof=true, Floodlights=true, LEDBoards=true },
        new() { Name="Northgate Arena", Capacity=60000, Roof=true, Floodlights=true, LEDBoards=true },
        new() { Name="Riverport Stadium", Capacity=35000, Roof=false, Floodlights=true, LEDBoards=false },
        new() { Name="Kingsford Park", Capacity=28000, Roof=false, Floodlights=true, LEDBoards=false },
        new() { Name="Estadio Verde", Capacity=52000, Roof=true, Floodlights=true, LEDBoards=true },
        new() { Name="Aurora Dome", Capacity=70000, Roof=true, Floodlights=true, LEDBoards=true },
        new() { Name="Ironbridge Ground", Capacity=22000, Roof=false, Floodlights=false, LEDBoards=false },
        new() { Name="Meridian Stadium", Capacity=40000, Roof=true, Floodlights=true, LEDBoards=true },
        new() { Name="Coastal Arena", Capacity=32000, Roof=false, Floodlights=true, LEDBoards=false },
        new() { Name="Summit Stadium", Capacity=55000, Roof=true, Floodlights=true, LEDBoards=true },
        new() { Name="Harbor Ground", Capacity=30000, Roof=false, Floodlights=true, LEDBoards=false },
        new() { Name="Pinnacle Dome", Capacity=48000, Roof=true, Floodlights=true, LEDBoards=true },
        new() { Name="Emberton Park", Capacity=26000, Roof=false, Floodlights=true, LEDBoards=false },
        new() { Name="Frostbite Arena", Capacity=38000, Roof=true, Floodlights=true, LEDBoards=true },
        new() { Name="Golden Gate Stadium", Capacity=62000, Roof=true, Floodlights=true, LEDBoards=true },
        new() { Name="Silverton Ground", Capacity=24000, Roof=false, Floodlights=true, LEDBoards=false },
        new() { Name="Crimson Stadium", Capacity=44000, Roof=true, Floodlights=true, LEDBoards=true },
        new() { Name="Azure Arena", Capacity=58000, Roof=true, Floodlights=true, LEDBoards=true },
        new() { Name="Verdant Park", Capacity=34000, Roof=false, Floodlights=true, LEDBoards=false },
        new() { Name="Obsidian Dome", Capacity=50000, Roof=true, Floodlights=true, LEDBoards=true },
    };

    public static readonly LeagueInfo[] Leagues =
    {
        new() { Name="Premier League", Teams=4, PromotionSpots=0, RelegationSpots=0 },
        new() { Name="La Liga", Teams=4, PromotionSpots=0, RelegationSpots=0 },
        new() { Name="Serie A", Teams=4, PromotionSpots=0, RelegationSpots=0 },
        new() { Name="Bundesliga", Teams=4, PromotionSpots=0, RelegationSpots=0 },
        new() { Name="Ligue 1", Teams=4, PromotionSpots=0, RelegationSpots=0 },
    };

    public static readonly BootInfo[] Boots =
    {
        new() { Name="Velocity Pro", Color="#dc2626", Style="Speed" },
        new() { Name="Control Elite", Color="#2563eb", Style="Control" },
        new() { Name="Power Strike", Color="#111827", Style="Power" },
        new() { Name="Phantom X", Color="#f59e0b", Style="Balanced" },
        new() { Name="Aero Glide", Color="#06b6d4", Style="Speed" },
    };

    public static readonly FaceInfo[] Faces =
    {
        new() { SkinTone="#f5d0b0", HairStyle="Short", HairColor="#1f2937" },
        new() { SkinTone="#e8b88a", HairStyle="Curly", HairColor="#78350f" },
        new() { SkinTone="#c68642", HairStyle="Bald", HairColor="#000000" },
        new() { SkinTone="#8d5524", HairStyle="Afro", HairColor="#111827" },
        new() { SkinTone="#ffdbac", HairStyle="Long", HairColor="#fbbf24" },
        new() { SkinTone="#f1c27d", HairStyle="Mohawk", HairColor="#dc2626" },
    };

    /// <summary>Formation slots in "own-half" coordinates: x -1=own goal, +1=opponent goal; z -1..1 = width.</summary>
    public static (float x, float z, Role role)[] Slots(string formation, int teamSize)
    {
        if (teamSize == 5) formation = "1-2-1 (5s)";
        if (teamSize == 7) formation = "2-3-1 (7s)";
        return formation switch
        {
            "4-3-3" => new[] {
                (-.90f,0f,Role.Goalkeeper),
                (-.64f,-.62f,Role.Defender),(-.68f,-.20f,Role.Defender),(-.68f,.20f,Role.Defender),(-.64f,.62f,Role.Defender),
                (-.28f,-.45f,Role.Midfielder),(-.34f,0f,Role.Midfielder),(-.28f,.45f,Role.Midfielder),
                (.02f,-.55f,Role.Forward),(.06f,0f,Role.Forward),(.02f,.55f,Role.Forward) },
            "3-5-2" => new[] {
                (-.90f,0f,Role.Goalkeeper),
                (-.66f,-.48f,Role.Defender),(-.68f,0f,Role.Defender),(-.66f,.48f,Role.Defender),
                (-.34f,-.70f,Role.Midfielder),(-.38f,-.25f,Role.Midfielder),(-.30f,0f,Role.Midfielder),(-.38f,.25f,Role.Midfielder),(-.34f,.70f,Role.Midfielder),
                (.02f,-.22f,Role.Forward),(.02f,.22f,Role.Forward) },
            "2-3-1 (7s)" => new[] {
                (-.86f,0f,Role.Goalkeeper),
                (-.58f,-.40f,Role.Defender),(-.58f,.40f,Role.Defender),
                (-.20f,-.55f,Role.Midfielder),(-.26f,0f,Role.Midfielder),(-.20f,.55f,Role.Midfielder),
                (.06f,0f,Role.Forward) },
            "1-2-1 (5s)" => new[] {
                (-.86f,0f,Role.Goalkeeper),
                (-.52f,0f,Role.Defender),
                (-.12f,-.48f,Role.Midfielder),(-.12f,.48f,Role.Midfielder),
                (.10f,0f,Role.Forward) },
            _ => new[] { // 4-4-2
                (-.90f,0f,Role.Goalkeeper),
                (-.64f,-.62f,Role.Defender),(-.68f,-.20f,Role.Defender),(-.68f,.20f,Role.Defender),(-.64f,.62f,Role.Defender),
                (-.30f,-.62f,Role.Midfielder),(-.34f,-.20f,Role.Midfielder),(-.34f,.20f,Role.Midfielder),(-.30f,.62f,Role.Midfielder),
                (.02f,-.22f,Role.Forward),(.02f,.22f,Role.Forward) },
        };
    }

    /// <summary>World-space starting/home position. attackSign: home +1, away -1 (flips at half time).</summary>
    /// <summary>Substitutes for a club: extra outfielders (plus a reserve keeper)
    /// generated from the same club identity as the starting eleven.</summary>
    public static List<CharacterSpec> CreateBench(int clubIndex, int count = 7, int seed = 7)
    {
        var list = CreateRoster(clubIndex, Math.Max(1, count), seed + 5000);
        for (int i = 0; i < list.Count; i++)
        {
            list[i].Number = 12 + i;
            var role = i == 0 ? Role.Goalkeeper
                     : i % 3 == 0 ? Role.Defender
                     : i % 3 == 1 ? Role.Midfielder : Role.Forward;
            list[i].Role = role;
            list[i].Goalkeeping = role == Role.Goalkeeper ? MathF.Max(list[i].Goalkeeping, .62f) : .12f;
        }
        AssignBadges(list, seed + 77);
        return list;
    }

    /// <summary>Deterministic trait assignment (Features.cs Badge).  The engine
    /// reads these - see the Engine badge's stamina drain in Match.cs.</summary>
    public static void AssignBadges(List<CharacterSpec> list, int seed = 11)
    {
        var rng = new Random(seed);
        foreach (var p in list)
        {
            var pool = p.Role switch
            {
                Role.Goalkeeper => new[] { Badge.Wall, Badge.Engine },
                Role.Defender => new[] { Badge.Wall, Badge.Engine, Badge.TargetMan },
                Role.Midfielder => new[] { Badge.Playmaker, Badge.Handles, Badge.Engine },
                _ => new[] { Badge.Deadeye, Badge.Trickster, Badge.TargetMan },
            };
            p.Badges.Clear();
            p.Badges.Add(pool[rng.Next(pool.Length)]);
            if (rng.NextDouble() < .35) p.Badges.Add(pool[rng.Next(pool.Length)]);
        }
    }

    public static Vector3 SlotToWorld(float x, float z, int attackSign)
        => new(attackSign * x * Mx.HalfLength * .94f, 0f, z * Mx.HalfWidth * .88f);

    public static List<CharacterSpec> CreateRoster(int clubIndex, int teamSize, int seed = 7)
    {
        var club = All[Math.Clamp(clubIndex, 0, All.Length - 1)];
        var rng = new Rng(seed + clubIndex * 977);
        var slots = Slots(teamSize == 5 ? "1-2-1 (5s)" : teamSize == 7 ? "2-3-1 (7s)" : "4-4-2", teamSize);
        var list = new List<CharacterSpec>();
        for (int i = 0; i < teamSize; i++)
        {
            var slot = slots[Math.Min(i, slots.Length - 1)];
            string first = FirstNames[rng.RangeInt(0, FirstNames.Length - 1)];
            string last = LastNames[rng.RangeInt(0, LastNames.Length - 1)];
            var p = new CharacterSpec
            {
                Name = first + " " + last,
                DisplayName = last.ToUpperInvariant(),
                Number = i == 0 ? 1 : rng.RangeInt(2, 39),
                Role = slot.role,
                Height = rng.Range(1.72f, 1.96f),
                Bulk = rng.Range(.88f, 1.14f),
                LegLength = rng.Range(.94f, 1.08f),
                ArmLength = rng.Range(.94f, 1.06f),
                HeadScale = rng.Range(.94f, 1.07f),
                SkinTone = rng.RangeInt(0, CharacterSpec.SkinPalette.Length - 1),
                HairStyle = rng.RangeInt(0, 4),
                HairColor = new[] { "#241811", "#4a2f1b", "#b06b2c", "#111111", "#7b4a2a" }[rng.RangeInt(0, 4)],
                KitPrimary = club.Primary,
                KitSecondary = club.Secondary,
                ShortsColor = club.Shorts,
                SocksColor = club.Socks,
                BootsColor = new[] { "#ffd166", "#111827", "#f8fafc", "#ef4444", "#22d3ee" }[rng.RangeInt(0, 4)],
                LongSleeves = rng.Next() < .25f,
                Pace = Mx.Clamp(club.Strength + rng.Range(-.14f, .12f), .3f, .98f),
                Shooting = Mx.Clamp(club.Strength + rng.Range(-.16f, .14f), .3f, .98f),
                Passing = Mx.Clamp(club.Strength + rng.Range(-.14f, .14f), .3f, .98f),
                Defending = Mx.Clamp(club.Strength + rng.Range(-.14f, .14f), .3f, .98f),
                Goalkeeping = i == 0 ? Mx.Clamp(club.Strength + .12f, .5f, .99f) : .12f,
                StaminaMax = rng.Range(.76f, .95f),
            };
            // Phase 1.3 archetype: pacy forwards are Explosive, tall defenders
            // are Lengthy, everyone else Controlled (FC 26-style movement types).
            p.Archetype = p.Role switch
            {
                Role.Goalkeeper => Archetype.Controlled,
                Role.Forward => p.Pace > .78f ? Archetype.Explosive : Archetype.Controlled,
                Role.Defender => p.Height > 1.88f ? Archetype.Lengthy : Archetype.Controlled,
                Role.Midfielder => p.Pace > .82f ? Archetype.Explosive : Archetype.Controlled,
                _ => Archetype.Controlled,
            };
            p.KitPattern = club.Pattern;
            p.KitTrim = club.Trim;
            if (slot.role == Role.Goalkeeper)
            {
                var gk = KeeperKit(Array.IndexOf(All, club));
                p.KitPrimary = gk.shirt; p.KitSecondary = gk.shorts; p.ShortsColor = gk.shorts;
                p.SocksColor = gk.socks; p.GlovesColor = gk.gloves; p.KitPattern = gk.pattern; p.KitTrim = gk.shorts;
                p.LongSleeves = true;
            }
            p.Sanitize();
            list.Add(p);
        }
        AssignBadges(list, seed + clubIndex);
        return list;
    }
}

// Phase 6: Content info classes
public sealed class StadiumInfo
{
    public string Name = "";
    public int Capacity;
    public bool Roof;
    public bool Floodlights;
    public bool LEDBoards;
}

public sealed class LeagueInfo
{
    public string Name = "";
    public int Teams;
    public int PromotionSpots;
    public int RelegationSpots;
}

public sealed class BootInfo
{
    public string Name = "";
    public string Color = "";
    public string Style = "";
}

public sealed class FaceInfo
{
    public string SkinTone = "";
    public string HairStyle = "";
    public string HairColor = "";
}
