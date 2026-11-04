// Arena FC - deterministic 60 Hz input replay.
// Only quantised commands are stored, so a whole match fits in a few hundred KB.
// Replaying them through StepOneTick reproduces the authoritative state exactly.
using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Serialization;
using ArenaFC.Core;

namespace ArenaFC.Core.Net;

public sealed class Replay
{
    public int Seed { get; set; } = 2026;
    public int TeamSize { get; set; } = 11;
    public bool AwayHuman { get; set; }
    public string? Room { get; set; }
    public List<Dictionary<int, CommandDto>> Ticks { get; set; } = new();

    private sealed class ReplayDto
    {
        [JsonPropertyName("v")] public int V { get; set; } = NetProtocol.Version;
        [JsonPropertyName("seed")] public int Seed { get; set; }
        [JsonPropertyName("size")] public int Size { get; set; }
        [JsonPropertyName("away")] public bool Away { get; set; }
        [JsonPropertyName("room")] public string? Room { get; set; }
        [JsonPropertyName("ticks")] public List<Dictionary<int, CommandDto>> Ticks { get; set; } = new();
    }

    public string ToJson()
    {
        var dto = new ReplayDto
        {
            Seed = Seed, Size = TeamSize, Away = AwayHuman, Room = Room, Ticks = Ticks,
        };
        return JsonSerializer.Serialize(dto, NetProtocol.Json);
    }

    public static Replay? FromJson(string json)
    {
        try
        {
            var d = JsonSerializer.Deserialize<ReplayDto>(json, NetProtocol.Json);
            if (d is null) return null;
            return new Replay
            {
                Seed = d.Seed,
                TeamSize = d.Size is 5 or 7 or 11 ? d.Size : 11,
                AwayHuman = d.Away,
                Room = d.Room,
                Ticks = d.Ticks ?? new List<Dictionary<int, CommandDto>>(),
            };
        }
        catch (JsonException) { return null; }
        catch (NotSupportedException) { return null; }
    }

    public MatchEngine CreateEngine() => new(new MatchOptions
    {
        Seed = Seed,
        TeamSize = TeamSize,
        AwayHuman = AwayHuman,
    });

    /// <summary>Re-simulate every recorded tick on the supplied engine.</summary>
    public void Play(MatchEngine e)
    {
        foreach (var frame in Ticks)
        {
            var cmds = new Dictionary<int, PlayerCommand>(frame.Count);
            foreach (var kv in frame) cmds[kv.Key] = kv.Value.To();
            e.StepOneTick(cmds);
        }
    }
}
