// Arena FC - editable character definition. Shared by the game, the in-game editor,
// the GLB exporter and the headless tests. Pure C#, serialises to JSON.
using System;
using System.Collections.Generic;
using System.Linq;
using System.Numerics;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace ArenaFC.Core;

public enum Role { Goalkeeper, Defender, Midfielder, Forward }

public sealed class CharacterSpec
{
    public string Id { get; set; } = Guid.NewGuid().ToString("N")[..10];
    public string Name { get; set; } = "A. Player";
    public string DisplayName { get; set; } = "A. PLAYER";
    public int Number { get; set; } = 10;
    public Role Role { get; set; } = Role.Midfielder;

    // --- Rig proportions (all editable in-game, live on the skinned mesh) ---
    public float Height { get; set; } = 1.82f;       // metres
    public float Bulk { get; set; } = 1.00f;         // 0.75 .. 1.35
    public float LegLength { get; set; } = 1.00f;    // 0.85 .. 1.18
    public float ArmLength { get; set; } = 1.00f;    // 0.85 .. 1.18
    public float HeadScale { get; set; } = 1.00f;    // 0.85 .. 1.20
    public float ShoulderWidth { get; set; } = 1.00f;

    // --- Appearance ---
    public int SkinTone { get; set; } = 2;           // index into SkinPalette
    public int HairStyle { get; set; } = 0;         // 0 crop,1 short,2 curly,3 bald,4 long
    public string HairColor { get; set; } = "#241811";
    public string KitPrimary { get; set; } = "#d7263d";
    public string KitSecondary { get; set; } = "#f7f7f2";
    public string ShortsColor { get; set; } = "#14213d";
    public string SocksColor { get; set; } = "#f7f7f2";
    public string BootsColor { get; set; } = "#ffd166";
    public string GlovesColor { get; set; } = "#2b2d42";
    public bool LongSleeves { get; set; } = false;

    // --- Attributes (0..1), also editable ---
    public float Pace { get; set; } = 0.72f;
    public float Shooting { get; set; } = 0.70f;
    public float Passing { get; set; } = 0.72f;
    public float Defending { get; set; } = 0.55f;
    public float Goalkeeping { get; set; } = 0.10f;
    public float StaminaMax { get; set; } = 0.85f;

    /// <summary>Per-bone rest-pose offset in degrees (name => XYZ euler). Editable in the Skeleton tab.</summary>
    public Dictionary<string, float[]> BoneRotations { get; set; } = new();

    [JsonIgnore] public bool IsKeeper => Role == Role.Goalkeeper;

    public static readonly string[] SkinPalette =
    {
        "#f6d5bd", "#eab998", "#d69a72", "#b8754d", "#8c5433", "#5e3520", "#3b2116"
    };

    public string SkinHex => SkinPalette[Math.Clamp(SkinTone, 0, SkinPalette.Length - 1)];

    public CharacterSpec Clone() => JsonSerializer.Deserialize<CharacterSpec>(ToJson(), JsonOpts) ?? new CharacterSpec();

    public string ToJson() => JsonSerializer.Serialize(this, JsonOpts);

    public static CharacterSpec FromJson(string json)
    {
        try { return JsonSerializer.Deserialize<CharacterSpec>(json, JsonOpts) ?? new CharacterSpec(); }
        catch { return new CharacterSpec(); }
    }

    public void Sanitize()
    {
        Height = Mx.Clamp(Height, 1.50f, 2.10f);
        Bulk = Mx.Clamp(Bulk, 0.70f, 1.40f);
        LegLength = Mx.Clamp(LegLength, 0.82f, 1.20f);
        ArmLength = Mx.Clamp(ArmLength, 0.82f, 1.20f);
        HeadScale = Mx.Clamp(HeadScale, 0.80f, 1.25f);
        ShoulderWidth = Mx.Clamp(ShoulderWidth, 0.80f, 1.25f);
        Number = Math.Clamp(Number, 1, 99);
        SkinTone = Math.Clamp(SkinTone, 0, SkinPalette.Length - 1);
        HairStyle = Math.Clamp(HairStyle, 0, 4);
        Pace = Mx.Clamp(Pace, 0.1f, 1f);
        Shooting = Mx.Clamp(Shooting, 0.1f, 1f);
        Passing = Mx.Clamp(Passing, 0.1f, 1f);
        Defending = Mx.Clamp(Defending, 0.1f, 1f);
        Goalkeeping = Mx.Clamp(Goalkeeping, 0.1f, 1f);
        StaminaMax = Mx.Clamp(StaminaMax, 0.4f, 1f);
        DisplayName = string.IsNullOrWhiteSpace(DisplayName) ? Name.ToUpperInvariant() : DisplayName;
        if (BoneRotations == null) BoneRotations = new Dictionary<string, float[]>();
        foreach (var k in BoneRotations.Keys.ToList())
        {
            var v = BoneRotations[k];
            if (v == null || v.Length != 3) { BoneRotations.Remove(k); continue; }
            for (int i = 0; i < 3; i++) v[i] = Mx.Clamp(v[i], -170f, 170f);
        }
    }

    public float[] GetBoneRotation(string bone)
        => BoneRotations.TryGetValue(bone, out var v) && v.Length == 3 ? v : new float[3];

    public void SetBoneRotation(string bone, float x, float y, float z)
    {
        BoneRotations[bone] = new[] { x, y, z };
        if (MathF.Abs(x) + MathF.Abs(y) + MathF.Abs(z) < 0.01f) BoneRotations.Remove(bone);
    }

    public static readonly JsonSerializerOptions JsonOpts = new()
    {
        WriteIndented = true,
        IncludeFields = false,
        PropertyNameCaseInsensitive = true,
        Converters = { new JsonStringEnumConverter() }
    };
}

public static class CharacterIo
{
    /// <summary>Portable JSON roster file. Used by the in-game editor and the build tools.</summary>
    public static string SerializeRoster(IEnumerable<CharacterSpec> roster, string teamName)
        => JsonSerializer.Serialize(new RosterFile { TeamName = teamName, Players = roster.ToList() }, CharacterSpec.JsonOpts);

    public static List<CharacterSpec> DeserializeRoster(string json, out string teamName)
    {
        try
        {
            var f = JsonSerializer.Deserialize<RosterFile>(json, CharacterSpec.JsonOpts);
            if (f?.Players?.Count > 0) { teamName = f.TeamName ?? "CUSTOM"; return f.Players; }
        }
        catch { }
        teamName = "CUSTOM";
        return new List<CharacterSpec>();
    }

    public sealed class RosterFile
    {
        public string TeamName { get; set; } = "CUSTOM";
        public int Version { get; set; } = 1;
        public List<CharacterSpec> Players { get; set; } = new();
    }
}
