using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text.Json;

namespace ArenaFC.Core.Animation;

public sealed class MotionFeatureRow
{
    public string ClipId { get; }
    public int FrameIndex { get; }
    public float Phase { get; }
    public ClipCategory Category { get; }
    public BallState Ball { get; }
    public string StyleTag { get; }
    private readonly float[] _features;
    public ReadOnlyMemory<float> Features => _features;
    internal ReadOnlySpan<float> FeatureSpan => _features;

    internal MotionFeatureRow(string clipId, int frameIndex, float phase,
        ClipCategory category, BallState ball, string styleTag, float[] features)
    {
        ClipId = clipId; FrameIndex = frameIndex; Phase = phase;
        Category = category; Ball = ball; StyleTag = styleTag;
        _features = (float[])features.Clone();
    }
}

public readonly struct MotionMatch
{
    public MotionFeatureRow Row { get; }
    public int RowIndex { get; }
    public float Cost { get; }

    internal MotionMatch(MotionFeatureRow row, int rowIndex, float cost)
    { Row = row; RowIndex = rowIndex; Cost = cost; }
}

/// <summary>Immutable, pure-Core motion feature table. Search is exact, tag-filtered,
/// deterministic brute force; one-shot action queries are deliberately ineligible.</summary>
public sealed class MotionDatabase
{
    public const int CurrentVersion = 2;
    private readonly MotionFeatureRow[] _rows;
    private readonly IReadOnlyList<MotionFeatureRow> _rowView;
    private readonly float[] _mean, _stdDev, _weights;

    public int Count => _rows.Length;
    public int Dimensions => MotionFeatureLayout.Dimensions;
    public IReadOnlyList<MotionFeatureRow> Rows => _rowView;

    private MotionDatabase(MotionFeatureRow[] rows, float[] mean, float[] stdDev, float[] weights)
    {
        _rows = rows;
        _rowView = Array.AsReadOnly(rows);
        _mean = mean; _stdDev = stdDev; _weights = weights;
    }

    public MotionFeatureRow GetRow(int index) => _rows[index];

    public static MotionDatabase Parse(string json)
    {
        using var doc = JsonDocument.Parse(json);
        var root = doc.RootElement;
        if (root.ValueKind != JsonValueKind.Object)
            throw new FormatException("Motion feature database root must be an object.");
        if (ReadInt(root, "version") != CurrentVersion)
            throw new FormatException($"Unsupported motion database version; expected {CurrentVersion}.");
        if (ReadInt(root, "featureSchemaVersion") != MotionFeatureLayout.SchemaVersion)
            throw new FormatException("Motion feature schema version does not match Core.");
        if (ReadInt(root, "dimensions") != MotionFeatureLayout.Dimensions)
            throw new FormatException($"Motion database must have {MotionFeatureLayout.Dimensions} dimensions.");
        if (!string.Equals(OptionalString(root, "space", ""), "facing_root_xz", StringComparison.Ordinal))
            throw new FormatException("Motion database coordinate space differs from Core.");

        var layout = ReadStrings(root, "layout");
        if (!MotionFeatureLayout.Matches(layout))
            throw new FormatException("Motion database feature layout/order differs from Core.");
        if (!root.TryGetProperty("normalization", out var norm) || norm.ValueKind != JsonValueKind.Object
            || !string.Equals(OptionalString(norm, "method", ""), "zscore", StringComparison.Ordinal))
            throw new FormatException("Motion database normalization must use the versioned zscore format.");
        float[] trajectoryTimes = ReadFloats(root, "trajectoryTimes", MotionFeatureLayout.TrajectoryTimes.Length);
        for (int i = 0; i < trajectoryTimes.Length; i++)
            if (MathF.Abs(trajectoryTimes[i] - MotionFeatureLayout.TrajectoryTimes[i]) > 1e-5f)
                throw new FormatException("Motion database trajectory sample times differ from Core.");
        float[] mean = ReadFloats(norm, "mean", MotionFeatureLayout.Dimensions);
        float[] stdDev = ReadFloats(norm, "stdDev", MotionFeatureLayout.Dimensions);
        float[] weights = ReadFloats(root, "weights", MotionFeatureLayout.Dimensions);
        for (int i = 0; i < MotionFeatureLayout.Dimensions; i++)
        {
            if (stdDev[i] <= 0f) throw new FormatException($"Motion database stdDev[{i}] must be positive.");
            if (weights[i] < 0f) throw new FormatException($"Motion database weights[{i}] cannot be negative.");
        }
        if (!root.TryGetProperty("rows", out var rowsElement) || rowsElement.ValueKind != JsonValueKind.Array)
            throw new FormatException("Motion database rows must be an array.");

        var rows = new List<MotionFeatureRow>();
        var seenPayloads = new HashSet<string>(StringComparer.Ordinal);
        foreach (var item in rowsElement.EnumerateArray())
        {
            if (item.ValueKind != JsonValueKind.Object)
                throw new FormatException("Motion feature row must be an object.");
            string clipId = ReadString(item, "clipId");
            int frame = ReadInt(item, "frameIndex");
            float phase = ReadSingle(item, "phase");
            if (frame < 0 || phase < 0f || phase >= 1f)
                throw new FormatException($"Motion row '{clipId}' has invalid frameIndex or normalized phase.");
            // v2: every category.  One-shot clips contribute their entry frames
            // (up to the contact) so an action can start at the matching pose/timing.
            if (!Enum.TryParse(ReadString(item, "category"), true, out ClipCategory category)
                || !Enum.IsDefined(typeof(ClipCategory), category))
                throw new FormatException($"Motion row '{clipId}' has an unknown category.");
            if (!Enum.TryParse(ReadString(item, "ballState"), true, out BallState ball)
                || !Enum.IsDefined(typeof(BallState), ball))
                throw new FormatException($"Motion row '{clipId}' has an unknown ballState.");
            string styleTag = OptionalString(item, "styleTag", "");
            float[] features = ReadFloats(item, "features", MotionFeatureLayout.Dimensions);
            for (int i = 0; i < features.Length; i++)
                if (!float.IsFinite(features[i]))
                    throw new FormatException($"Motion row '{clipId}' feature {i} is not finite.");
            string payloadKey = clipId + "\u001f" + frame.ToString(CultureInfo.InvariantCulture);
            if (!seenPayloads.Add(payloadKey))
                throw new FormatException($"Duplicate motion payload '{clipId}' frame {frame}.");
            rows.Add(new MotionFeatureRow(clipId, frame, phase, category, ball, styleTag, features));
        }
        if (rows.Count == 0) throw new FormatException("Motion database must contain at least one row.");
        rows.Sort((a, b) =>
        {
            int c = string.CompareOrdinal(a.ClipId, b.ClipId);
            return c != 0 ? c : a.FrameIndex.CompareTo(b.FrameIndex);
        });
        return new MotionDatabase(rows.ToArray(), mean, stdDev, weights);
    }

    /// <summary>The 8 foot position/velocity features of the row nearest a clip phase
    /// (the pose the player is in now, for the next query).</summary>
    public bool TryGetPoseFeatures(string clipId, float phase, Span<float> pose8)
    {
        if (pose8.Length < 8) throw new ArgumentException("Need 8 slots.", nameof(pose8));
        int best = -1; float bestD = float.MaxValue;
        for (int i = 0; i < _rows.Length; i++)
        {
            var r = _rows[i];
            if (!string.Equals(r.ClipId, clipId, StringComparison.Ordinal)) continue;
            float d = MathF.Abs(r.Phase - phase);
            if (d < bestD) { bestD = d; best = i; }
        }
        if (best < 0) return false;
        _rows[best].FeatureSpan.Slice(0, 8).CopyTo(pose8);
        return true;
    }

    public bool TrySearch(MotionQuery query, out MotionMatch match)
    {
        if (query == null) throw new ArgumentNullException(nameof(query));
        match = default;
        bool forced = query.ForcedClipId.Length > 0;
        bool locomotion = query.Category == ClipCategory.Locomotion;
        // A locomotion search needs a locomotion intent: an event-driven action must
        // name its own category (or clip), never borrow a running cycle.
        if (!forced && locomotion && !IsLocomotionIntent(query.Intent)) return false;
        if (!forced && !locomotion) return TrySearchAction(query, out match);
        if (forced) return TrySearchForced(query, out match);

        bool exactBall = false, neutralBall = false;
        foreach (var row in _rows)
        {
            if (row.Category != query.Category) continue;
            exactBall |= row.Ball == query.Ball;
            neutralBall |= row.Ball == BallState.None;
        }
        bool exactStyle = false;
        if (!string.IsNullOrEmpty(query.StyleTag))
        {
            foreach (var row in _rows)
                if (EligibleBall(row, query, exactBall, neutralBall)
                    && string.Equals(row.StyleTag, query.StyleTag, StringComparison.OrdinalIgnoreCase))
                { exactStyle = true; break; }
        }

        float bestCost = float.PositiveInfinity;
        int bestIndex = -1;
        ReadOnlySpan<float> q = query.Features;
        for (int rowIndex = 0; rowIndex < _rows.Length; rowIndex++)
        {
            var row = _rows[rowIndex];
            if (!EligibleBall(row, query, exactBall, neutralBall)) continue;
            if (exactStyle && !string.Equals(row.StyleTag, query.StyleTag, StringComparison.OrdinalIgnoreCase)) continue;

            float cost = 0f;
            for (int d = 0; d < MotionFeatureLayout.Dimensions; d++)
            {
                float queryNormalized = (q[d] - _mean[d]) / _stdDev[d];
                float rowNormalized = (row.FeatureSpan[d] - _mean[d]) / _stdDev[d];
                float normalizedDelta = queryNormalized - rowNormalized;
                cost += normalizedDelta * normalizedDelta * _weights[d];
            }
            if (query.CurrentClipId.Length > 0)
            {
                if (!string.Equals(query.CurrentClipId, row.ClipId, StringComparison.Ordinal))
                    cost += query.SwitchPenalty;
                else
                    cost += query.TemporalPenalty * CircularDistance(query.CurrentPhase, row.Phase);
            }
            if (cost < bestCost)
            {
                bestCost = cost;
                bestIndex = rowIndex;
            }
        }
        if (bestIndex < 0) return false;
        match = new MotionMatch(_rows[bestIndex], bestIndex, bestCost);
        return true;
    }

    /// <summary>One-shot entry search: rows of the query's category (dedicated clips
    /// excluded), cost = pose + trajectory + contact timing.</summary>
    private bool TrySearchAction(MotionQuery query, out MotionMatch match)
    {
        match = default;
        float bestCost = float.PositiveInfinity; int bestIndex = -1;
        for (int i = 0; i < _rows.Length; i++)
        {
            var row = _rows[i];
            if (row.Category != query.Category || row.StyleTag == "dedicated") continue;
            float cost = Cost(query.Features, row);
            if (cost < bestCost) { bestCost = cost; bestIndex = i; }
        }
        if (bestIndex < 0) return false;
        match = new MotionMatch(_rows[bestIndex], bestIndex, bestCost);
        return true;
    }

    private bool TrySearchForced(MotionQuery query, out MotionMatch match)
    {
        match = default;
        float bestCost = float.PositiveInfinity; int bestIndex = -1;
        for (int i = 0; i < _rows.Length; i++)
        {
            var row = _rows[i];
            if (!string.Equals(row.ClipId, query.ForcedClipId, StringComparison.Ordinal)) continue;
            float cost = Cost(query.Features, row);
            if (cost < bestCost) { bestCost = cost; bestIndex = i; }
        }
        if (bestIndex < 0) return false;
        match = new MotionMatch(_rows[bestIndex], bestIndex, bestCost);
        return true;
    }

    private float Cost(ReadOnlySpan<float> q, MotionFeatureRow row)
    {
        float cost = 0f;
        for (int d = 0; d < MotionFeatureLayout.Dimensions; d++)
        {
            float delta = (q[d] - row.FeatureSpan[d]) / _stdDev[d];
            cost += delta * delta * _weights[d];
        }
        return cost;
    }

    private static bool EligibleBall(MotionFeatureRow row, MotionQuery query,
        bool exactBall, bool neutralBall) => row.Category == query.Category
            && (exactBall ? row.Ball == query.Ball
                : neutralBall ? row.Ball == BallState.None : true);

    private static bool IsLocomotionIntent(PlayerIntent intent) => intent is PlayerIntent.None
        or PlayerIntent.Move or PlayerIntent.Sprint or PlayerIntent.Shield;

    private static float CircularDistance(float a, float b)
    {
        float d = MathF.Abs(CircularDifference(a, b));
        return d > .5f ? 1f - d : d;
    }

    private static float CircularDifference(float a, float b)
    {
        float d = (a - b) % 1f;
        if (d > .5f) d -= 1f;
        if (d < -.5f) d += 1f;
        return d;
    }

    private static int ReadInt(JsonElement e, string name) =>
        e.TryGetProperty(name, out var value) && value.TryGetInt32(out int result)
            ? result : throw new FormatException($"Motion database field '{name}' must be an integer.");
    private static float ReadSingle(JsonElement e, string name) =>
        e.TryGetProperty(name, out var value) && value.TryGetSingle(out float result)
            ? result : throw new FormatException($"Motion database field '{name}' must be numeric.");
    private static string ReadString(JsonElement e, string name) =>
        e.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String
            && !string.IsNullOrWhiteSpace(value.GetString())
            ? value.GetString()! : throw new FormatException($"Motion database field '{name}' must be a non-empty string.");
    private static string OptionalString(JsonElement e, string name, string fallback) =>
        e.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String
            ? value.GetString() ?? fallback : fallback;

    private static string[] ReadStrings(JsonElement e, string name)
    {
        if (!e.TryGetProperty(name, out var value) || value.ValueKind != JsonValueKind.Array)
            throw new FormatException($"Motion database field '{name}' must be an array.");
        var result = new List<string>();
        foreach (var item in value.EnumerateArray())
        {
            if (item.ValueKind != JsonValueKind.String)
                throw new FormatException($"Motion database field '{name}' must contain strings.");
            result.Add(item.GetString() ?? "");
        }
        return result.ToArray();
    }

    private static float[] ReadFloats(JsonElement e, string name, int expectedLength)
    {
        if (!e.TryGetProperty(name, out var value) || value.ValueKind != JsonValueKind.Array
            || value.GetArrayLength() != expectedLength)
            throw new FormatException($"Motion database field '{name}' must contain {expectedLength} numbers.");
        var result = new float[expectedLength];
        int i = 0;
        foreach (var item in value.EnumerateArray())
        {
            if (!item.TryGetSingle(out float number) || !float.IsFinite(number))
                throw new FormatException($"Motion database field '{name}' contains an invalid number.");
            result[i++] = number;
        }
        return result;
    }
}
