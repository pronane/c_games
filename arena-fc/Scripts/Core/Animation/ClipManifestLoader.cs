// Strict reader for the shared Sprite Forge clip metadata JSON. No Godot APIs here;
// the desktop adapter reads text via Godot's FileAccess and browser uses ClipManifest.gd.
using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Numerics;

namespace ArenaFC.Core.Animation;

public static class ClipManifestLoader
{
    public const int CurrentVersion = 1;

    public static List<ClipMeta> Parse(string json)
    {
        using var doc = JsonDocument.Parse(json);
        var root = doc.RootElement;
        int version = root.TryGetProperty("version", out var v) ? v.GetInt32() : 0;
        if (version != CurrentVersion)
            throw new FormatException($"Unsupported clip manifest version {version}; expected {CurrentVersion}.");
        if (!root.TryGetProperty("clips", out var clips) || clips.ValueKind != JsonValueKind.Array)
            throw new FormatException("Clip manifest must contain a clips array.");

        var result = new List<ClipMeta>();
        foreach (var item in clips.EnumerateArray())
        {
            string id = RequiredString(item, "id");
            string categoryName = RequiredString(item, "category");
            if (!Enum.TryParse(categoryName, ignoreCase: true, out ClipCategory category))
                throw new FormatException($"Unknown clip category '{categoryName}' for '{id}'.");
            string ballName = OptionalString(item, "ballState", "None");
            if (!Enum.TryParse(ballName, ignoreCase: true, out BallState ballState))
                throw new FormatException($"Unknown ballState '{ballName}' for '{id}'.");
            float duration = RequiredSingle(item, "duration");
            float contact = OptionalSingle(item, "contactFraction", -1f);
            if (duration <= 0f || !float.IsFinite(duration))
                throw new FormatException($"Clip '{id}' must have a finite positive duration.");
            if (contact < -1f || contact > 1f)
                throw new FormatException($"Clip '{id}' has contactFraction outside [-1,1].");

            var feet = ReadFloats(item, "footPlantFrames");
            foreach (float phase in feet)
                if (!float.IsFinite(phase) || phase < 0f || phase > 1f)
                    throw new FormatException($"Clip '{id}' has a foot plant outside [0,1].");
            var footSides = ReadFootSides(item, id, feet.Length);
            var tags = ReadStrings(item, "tags");
            int bones = item.TryGetProperty("boneCount", out var boneValue) ? boneValue.GetInt32() : 18;
            if (bones != 18)
                throw new FormatException($"Clip '{id}' has {bones} bones; expected 18.");
            var meta = new ClipMeta
            {
                Id = id,
                PoseDataKey = OptionalString(item, "poseDataKey", id),
                Category = category,
                Duration = duration,
                ContactFraction = contact,
                FootPlantFrames = feet,
                FootPlantSides = footSides,
                RootVelocityAvg = new Vector3(OptionalSingle(item, "rootVelocityX", 0f), 0f,
                    OptionalSingle(item, "rootVelocityZ", 0f)),
                PreferredSpeed = OptionalSingle(item, "preferredSpeed", 0f),
                PreferredTurnRate = OptionalSingle(item, "preferredTurnRate", 0f),
                BallState = ballState,
                Tags = tags,
                BoneCount = bones,
                Loop = item.TryGetProperty("loop", out var loop) && loop.GetBoolean(),
            };
            if (meta.PreferredSpeed < 0f || !float.IsFinite(meta.PreferredSpeed))
                throw new FormatException($"Clip '{id}' has invalid preferredSpeed.");
            result.Add(meta);
        }
        return result;
    }

    private static string RequiredString(JsonElement e, string name)
    {
        if (!e.TryGetProperty(name, out var value) || value.ValueKind != JsonValueKind.String)
            throw new FormatException($"Clip manifest field '{name}' is required and must be a string.");
        string? text = value.GetString();
        if (string.IsNullOrWhiteSpace(text)) throw new FormatException($"Clip manifest field '{name}' cannot be empty.");
        return text;
    }
    private static string OptionalString(JsonElement e, string name, string fallback) =>
        e.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String
            ? value.GetString() ?? fallback : fallback;
    private static float RequiredSingle(JsonElement e, string name) =>
        e.TryGetProperty(name, out var value) && value.TryGetSingle(out float result)
            ? result : throw new FormatException($"Clip manifest field '{name}' is required and must be numeric.");
    private static float OptionalSingle(JsonElement e, string name, float fallback) =>
        e.TryGetProperty(name, out var value) && value.TryGetSingle(out float result) ? result : fallback;
    private static FootSide[] ReadFootSides(JsonElement e, string id, int plantCount)
    {
        if (!e.TryGetProperty("footPlantSides", out var value))
        {
            var inferred = new FootSide[plantCount];
            for (int i = 0; i < inferred.Length; i++)
                inferred[i] = i % 2 == 0 ? FootSide.Left : FootSide.Right;
            return inferred;
        }
        if (value.ValueKind != JsonValueKind.Array)
            throw new FormatException($"Clip '{id}' footPlantSides must be an array.");
        var sides = new List<FootSide>();
        foreach (var item in value.EnumerateArray())
        {
            if (item.ValueKind != JsonValueKind.String
                || !Enum.TryParse(item.GetString(), ignoreCase: true, out FootSide side)
                || !Enum.IsDefined(typeof(FootSide), side))
                throw new FormatException($"Clip '{id}' has an invalid footPlantSides entry.");
            sides.Add(side);
        }
        if (sides.Count != plantCount)
            throw new FormatException($"Clip '{id}' footPlantSides count must match footPlantFrames.");
        return sides.ToArray();
    }

    private static float[] ReadFloats(JsonElement e, string name)
    {
        if (!e.TryGetProperty(name, out var value) || value.ValueKind != JsonValueKind.Array) return Array.Empty<float>();
        var result = new List<float>();
        foreach (var item in value.EnumerateArray())
        {
            if (!item.TryGetSingle(out float number)) throw new FormatException($"'{name}' must contain only numbers.");
            result.Add(number);
        }
        return result.ToArray();
    }
    private static string[] ReadStrings(JsonElement e, string name)
    {
        if (!e.TryGetProperty(name, out var value) || value.ValueKind != JsonValueKind.Array) return Array.Empty<string>();
        var result = new List<string>();
        foreach (var item in value.EnumerateArray())
        {
            if (item.ValueKind != JsonValueKind.String) throw new FormatException($"'{name}' must contain only strings.");
            result.Add(item.GetString() ?? "");
        }
        return result.ToArray();
    }
}
