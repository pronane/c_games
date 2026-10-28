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
}

public static class Clubs
{
    public static readonly ClubInfo[] All =
    {
        new() { Name="Harrow Lions",       Short="HAR", Primary="#d7263d", Secondary="#ffffff", Shorts="#14213d", Socks="#ffffff", Strength=.78f },
        new() { Name="Northgate United",   Short="NOR", Primary="#1d4ed8", Secondary="#f8fafc", Shorts="#1e3a8a", Socks="#f8fafc", Strength=.82f },
        new() { Name="Riverport City",     Short="RIV", Primary="#38bdf8", Secondary="#0f172a", Shorts="#e2e8f0", Socks="#0ea5e9", Strength=.76f },
        new() { Name="Kingsford FC",       Short="KIN", Primary="#7f1d3a", Secondary="#60a5fa", Shorts="#f8fafc", Socks="#1e3a8a", Strength=.74f },
        new() { Name="Val Verde Athletic", Short="VVA", Primary="#15803d", Secondary="#111827", Shorts="#111827", Socks="#166534", Strength=.72f },
        new() { Name="Aurora SC",          Short="AUR", Primary="#6d28d9", Secondary="#fbbf24", Shorts="#1f2937", Socks="#fbbf24", Strength=.80f },
        new() { Name="Ironbridge Town",    Short="IRN", Primary="#ea580c", Secondary="#18181b", Shorts="#18181b", Socks="#ea580c", Strength=.70f },
        new() { Name="Meridian Rovers",    Short="MER", Primary="#f1f5f9", Secondary="#0f172a", Shorts="#0f172a", Socks="#f1f5f9", Strength=.75f },
    };

    public static readonly string[] FirstNames =
    { "Alex","Marco","Nico","Jamie","Rafael","Yuki","Omar","Luca","Elias","Tomas","Kai","Ivan","Samir","Diego","Felix","Noah","Milan","Ruben","Theo","Amir","Hugo","Leon" };
    public static readonly string[] LastNames =
    { "Varela","Okafor","Bianchi","Kovac","Silva","Nakamura","Haddad","Rossi","Lindqvist","Mendes","Adeyemi","Petrov","Costa","Duarte","Novak","Berg","Marino","Fletcher","Sorensen","Aziz","Moreau","Weber" };

    public static readonly string[] Formations = { "4-4-2", "4-3-3", "3-5-2", "2-3-1 (7s)", "1-2-1 (5s)" };

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
            p.Sanitize();
            list.Add(p);
        }
        return list;
    }
}
