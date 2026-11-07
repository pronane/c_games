// Arena FC - wire protocol v2. Godot-free, so the .NET server, the core tests and
// the desktop client all share exactly the same packet format.
//
// Rebuilt from the format that IS checked in: Web/NetClient.gd (client messages),
// Tools/net_smoketest.py + net_v2_smoketest.py (assertions on the JSON), ONLINE.md
// (message table) and shared/netplay/server/arena/*.js (the Node reference server).
// Nothing here depends on a NuGet package; System.Text.Json ships with .NET.
using System;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;
using ArenaFC.Core;

namespace ArenaFC.Core.Net;

public static class NetProtocol
{
    public const int Version = 2;
    public const int DefaultPort = 7777;
    public const float SnapshotHz = 20f;
    public const int MaxPlayersPerRoom = 4;
    /// <summary>Maximum number of unconfirmed ticks a client will re-simulate.</summary>
    public const int MaxRollbackTicks = 24;
    /// <summary>Mutable: the server can shorten/lengthen it with --grace-seconds.</summary>
    public static int ReconnectGraceSeconds = 180;

    // Capability bits advertised in hello.caps
    public const int CapReconnect = 1;
    public const int CapRollback = 2;
    public const int CapPeerHost = 4;
    public const int CapFullDesktop = CapReconnect | CapRollback | CapPeerHost;

    // Who owns the authoritative simulation
    public const int AuthorityServer = 0;
    public const int AuthorityPeer = 1;

    // Message names (lowercase on the wire, matching Web/NetClient.gd and the Node hub)
    public const string Hello = "hello";
    public const string Welcome = "welcome";
    public const string Lobby = "lobby";
    public const string Ready = "ready";
    public const string Start = "start";
    public const string Begin = "begin";
    public const string Input = "input";
    public const string Snap = "snap";
    public const string Resume = "resume";
    public const string Host = "host";
    public const string Authority = "authority";
    public const string End = "end";
    public const string Error = "error";
    public const string Chat = "chat";
    public const string Ping = "ping";
    public const string Pong = "pong";
    public const string Leave = "leave";
    public const string Kick = "kick";
    public const string Submit = "submit";
    public const string PeerInput = "peerinput";
    /// <summary>Message name for state-hash reports.  The C# method Hash(MatchState) keeps that name.</summary>
    public const string HashMessage = "hash";

    private const string RoomAlphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";

    internal static readonly JsonSerializerOptions Json = new()
    {
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
        WriteIndented = false,
        PropertyNameCaseInsensitive = true,
    };

    public static string Encode(Packet p) => JsonSerializer.Serialize(p, Json);

    public static Packet? Decode(string text)
    {
        if (string.IsNullOrWhiteSpace(text)) return null;
        try { return JsonSerializer.Deserialize<Packet>(text, Json); }
        catch (JsonException) { return null; }
        catch (NotSupportedException) { return null; }
    }

    public static string NewRoomCode()
    {
        var chars = new char[6];
        for (int i = 0; i < chars.Length; i++) chars[i] = RoomAlphabet[RandomNumberGenerator.GetInt32(RoomAlphabet.Length)];
        return new string(chars);
    }

    /// <summary>32 random bytes, base64url, no padding => exactly 43 URL-safe chars.</summary>
    public static string NewResumeToken() => ToBase64Url(RandomNumberGenerator.GetBytes(32));

    private static string ToBase64Url(byte[] bytes) =>
        Convert.ToBase64String(bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_');

    public static string HashToken(string token)
    {
        byte[] hash = SHA256.HashData(Encoding.UTF8.GetBytes(token ?? string.Empty));
        return Convert.ToHexString(hash).ToLowerInvariant();
    }

    /// <summary>Length-safe, content-independent comparison so a token hash cannot be timed.</summary>
    public static bool TokenHashEquals(string? a, string? b)
    {
        if (a is null || b is null || a.Length != b.Length) return false;
        int diff = 0;
        for (int i = 0; i < a.Length; i++) diff |= a[i] ^ b[i];
        return diff == 0;
    }

    public static string NormalizeRoom(string? room)
    {
        string s = (room ?? string.Empty).ToUpperInvariant();
        var sb = new StringBuilder(s.Length);
        foreach (char c in s) if (char.IsAsciiLetterOrDigit(c)) sb.Append(c);
        return sb.Length > 12 ? sb.ToString(0, 12) : sb.ToString();
    }

    public static string NormalizeName(string? name)
    {
        string s = Regex.Replace(name ?? string.Empty, @"[^\p{L}\p{N} _.\-]", string.Empty).Trim();
        if (s.Length > 16) s = s[..16];
        return s.Length == 0 ? "Player" : s;
    }

    public static string NormalizeUrl(string? url)
    {
        string s = (url ?? string.Empty).Trim().TrimEnd('/');
        if (s.Length == 0) return $"ws://127.0.0.1:{DefaultPort}";
        if (s.StartsWith("https://", StringComparison.OrdinalIgnoreCase)) return "wss://" + s[8..];
        if (s.StartsWith("http://", StringComparison.OrdinalIgnoreCase)) return "ws://" + s[7..];
        if (s.StartsWith("ws://", StringComparison.OrdinalIgnoreCase) ||
            s.StartsWith("wss://", StringComparison.OrdinalIgnoreCase)) return s;
        return "ws://" + s;
    }

    /// <summary>FNV-1a over the pitch state, quantised to millimetres so a 3-decimal
    /// snapshot and a full-precision engine hash identically (same as the Node hub).</summary>
    public static uint Hash(MatchState s)
    {
        uint h = 2166136261u;
        void Mix(float v)
        {
            h ^= unchecked((uint)(int)MathF.Round(v * 1000f));
            h *= 16777619u;
        }
        foreach (var p in s.Players) { Mix(p.Pos.X); Mix(p.Pos.Z); }
        Mix(s.Ball.Pos.X); Mix(s.Ball.Pos.Y); Mix(s.Ball.Pos.Z);
        h ^= (uint)(s.Score[0] * 7 + s.Score[1]);
        h *= 16777619u;
        return h;
    }
}
