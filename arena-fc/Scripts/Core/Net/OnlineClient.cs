// Arena FC - Godot-free C# client for the protocol v2 WebSocket hub.
//
// Desktop/mobile C# builds use this directly; the headless core suite swaps in a
// LoopbackTransport so the whole handshake can be tested without a socket.
// All methods are synchronous from the caller's point of view: the socket pump
// runs on background tasks and hands complete JSON messages to Poll().
using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Net.WebSockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using ArenaFC.Core;

namespace ArenaFC.Core.Net;

/// <summary>Minimal transport so OnlineClient is testable without a real socket.</summary>
public interface INetTransport : IDisposable
{
    void Connect(string url);
    void Send(string text);
    /// <summary>Returns the next complete message, or false when nothing is queued.</summary>
    bool TryReceive(out string? text);
    bool IsOpen { get; }
    string? Error { get; }
    void Close();
}

/// <summary>Production transport: RFC 6455 over System.Net.WebSockets (desktop / mobile).</summary>
public sealed class WebSocketTransport : INetTransport
{
    private readonly ClientWebSocket _ws = new();
    private readonly ConcurrentQueue<string> _inbox = new();
    private readonly ConcurrentQueue<string> _outbox = new();
    private readonly CancellationTokenSource _cts = new();
    private Task? _pump;
    private string? _error;

    public bool IsOpen => _ws.State == WebSocketState.Open;
    public string? Error => _error;

    public void Connect(string url)
    {
        _ws.Options.AddSubProtocol("arenafc");
        _pump = Task.Run(async () =>
        {
            try
            {
                await _ws.ConnectAsync(new Uri(url), _cts.Token);
                var receive = ReceiveLoop();
                var send = SendLoop();
                await Task.WhenAll(receive, send);
            }
            catch (Exception ex) { _error = ex.Message; }
        });
    }

    private async Task ReceiveLoop()
    {
        var buf = new byte[256 * 1024];
        while (!_cts.IsCancellationRequested && _ws.State == WebSocketState.Open)
        {
            var sb = new StringBuilder();
            WebSocketReceiveResult r;
            do
            {
                r = await _ws.ReceiveAsync(new ArraySegment<byte>(buf), _cts.Token);
                if (r.MessageType == WebSocketMessageType.Close) return;
                sb.Append(Encoding.UTF8.GetString(buf, 0, r.Count));
            } while (!r.EndOfMessage);
            _inbox.Enqueue(sb.ToString());
        }
    }

    private async Task SendLoop()
    {
        while (!_cts.IsCancellationRequested && _ws.State == WebSocketState.Open)
        {
            if (_outbox.TryDequeue(out var text))
            {
                byte[] bytes = Encoding.UTF8.GetBytes(text);
                await _ws.SendAsync(new ArraySegment<byte>(bytes), WebSocketMessageType.Text, true, _cts.Token);
            }
            else await Task.Delay(2, _cts.Token);
        }
    }

    public void Send(string text) => _outbox.Enqueue(text);
    public bool TryReceive(out string? text) => _inbox.TryDequeue(out text);

    public void Close()
    {
        _cts.Cancel();
        try { _ws.Dispose(); } catch { }
        try { _pump?.Wait(200); } catch { }
    }

    public void Dispose() => Close();
}

/// <summary>Deterministic in-memory transport for tests and offline rehearsals.</summary>
public sealed class LoopbackTransport : INetTransport
{
    private readonly ConcurrentQueue<string> _inbox = new();
    public readonly List<string> Sent = new();
    public bool IsOpen { get; private set; } = true;
    public string? Error { get; set; }
    public string Url = "";

    public void Connect(string url) { Url = url; IsOpen = true; }
    public void Send(string text) { Sent.Add(text); }
    public bool TryReceive(out string? text) => _inbox.TryDequeue(out text);
    public void Push(string text) => _inbox.Enqueue(text);
    public void Push(Packet p) => _inbox.Enqueue(NetProtocol.Encode(p));
    public Packet? LastSent() => Sent.Count == 0 ? null : NetProtocol.Decode(Sent[^1]);
    public void Close() { IsOpen = false; }
    public void Dispose() => Close();
}

public sealed class OnlineClient
{
    private INetTransport? _transport;
    private int _seq;

    public string Url = "", Room = "", Name = "", Token = "";
    public int Slot = -1, Team, HostSlot, TeamSize = 5, Authority, Grace;
    public int Seed = 2026, LatestTick;
    public float TimeSpeed = 15f, HalfMinutes = 45f;
    public bool Connected, Started, InMatch;
    public string LastError = "", Status = "Offline";
    public string[] Names = Array.Empty<string>();
    public int[] Slots = Array.Empty<int>(), Teams = Array.Empty<int>(), Pings = Array.Empty<int>(), Ctrls = Array.Empty<int>();
    public bool[] Readys = Array.Empty<bool>(), Onlines = Array.Empty<bool>();

    /// <summary>Fired for every decoded packet, AFTER the built-in state has been updated.</summary>
    public event Action<Packet>? PacketReceived;

    public INetTransport? Transport => _transport;

    /// <summary>Connect and send `hello`.  Pass a transport to run without sockets.</summary>
    public bool Connect(string url, string room, string playerName, string? token = null,
                        bool create = false, INetTransport? transport = null)
    {
        Close();
        Url = NetProtocol.NormalizeUrl(url);
        Room = NetProtocol.NormalizeRoom(room);
        Name = NetProtocol.NormalizeName(playerName);
        Token = token ?? "";
        _transport = transport ?? new WebSocketTransport();
        try
        {
            _transport.Connect(Url);
            var hello = new Packet
            {
                T = NetProtocol.Hello, Ver = NetProtocol.Version, Caps = NetProtocol.CapFullDesktop,
                Name = Name, Room = Room, Create = create,
            };
            if (!string.IsNullOrEmpty(Token)) hello.Token = Token;
            Send(hello);
            Status = "Connecting…";
            Connected = true;
            return true;
        }
        catch (Exception ex)
        {
            LastError = ex.Message;
            Status = "Connection failed: " + LastError;
            return false;
        }
    }

    public void Send(Packet p) => _transport?.Send(NetProtocol.Encode(p));

    public void SendInput(PlayerCommand cmd) => Send(new Packet
    {
        T = NetProtocol.Input, Seq = ++_seq, Cmd = CommandDto.From(cmd),
    });

    public void SendStart() => Send(new Packet { T = NetProtocol.Start });
    public void SendReady(bool on) => Send(new Packet { T = NetProtocol.Ready, Ready = on });
    public void SendChat(string text) => Send(new Packet { T = NetProtocol.Chat, M = text });
    public void SendKick(int slot) => Send(new Packet { T = NetProtocol.Kick, KickSlot = slot });
    public void SendLeave() => Send(new Packet { T = NetProtocol.Leave });

    /// <summary>Drain the socket queue on the main thread. Call once per frame.</summary>
    public void Poll()
    {
        var t = _transport;
        if (t == null) return;
        if (t.Error != null) { LastError = t.Error; Status = "Connection error: " + t.Error; }
        int guard = 0;
        while (guard++ < 256 && t.TryReceive(out var text))
        {
            if (string.IsNullOrWhiteSpace(text)) continue;
            var p = NetProtocol.Decode(text);
            if (p == null) continue;
            Handle(p);
            PacketReceived?.Invoke(p);
        }
        if (Connected && !t.IsOpen && t.Error != null) Connected = false;
    }

    private void Handle(Packet p)
    {
        switch (p.T)
        {
            case NetProtocol.Welcome:
                if (p.Room != null) Room = p.Room;
                if (p.Slot.HasValue) Slot = p.Slot.Value;
                if (p.Team.HasValue) Team = p.Team.Value;
                if (p.Size.HasValue) TeamSize = p.Size.Value;
                if (p.Seed.HasValue) Seed = p.Seed.Value;
                if (p.Authority.HasValue) Authority = p.Authority.Value;
                if (p.Grace.HasValue) Grace = p.Grace.Value;
                if (p.Host.HasValue) HostSlot = p.Host.Value;
                if (p.Started.HasValue) InMatch = p.Started.Value;
                if (!string.IsNullOrEmpty(p.Token)) Token = p.Token;  // never logged / stored in plaintext on disk here
                Status = $"In room {Room} · slot {Slot} · team {(Team == 0 ? "home" : "away")}";
                break;
            case NetProtocol.Lobby:
                if (p.Host.HasValue) HostSlot = p.Host.Value;
                if (p.Size.HasValue) TeamSize = p.Size.Value;
                if (p.Authority.HasValue) Authority = p.Authority.Value;
                if (p.Started.HasValue) InMatch = p.Started.Value;
                Names = p.Names ?? Names; Slots = p.Slots ?? Slots; Teams = p.Teams ?? Teams;
                Pings = p.Pings ?? Pings; Readys = p.Readys ?? Readys; Onlines = p.Onlines ?? Onlines;
                Status = $"Room {Room} · {Names.Length} player(s) · host slot {HostSlot}";
                break;
            case NetProtocol.Begin:
            case NetProtocol.Resume:
                Started = true; InMatch = true;
                if (p.Seed.HasValue) Seed = p.Seed.Value;
                if (p.Size.HasValue) TeamSize = p.Size.Value;
                if (p.TimeSpeed.HasValue) TimeSpeed = p.TimeSpeed.Value;
                if (p.HalfMinutes.HasValue) HalfMinutes = p.HalfMinutes.Value;
                if (p.Host.HasValue) HostSlot = p.Host.Value;
                if (p.Authority.HasValue) Authority = p.Authority.Value;
                Ctrls = p.Ctrls ?? Ctrls;
                Status = p.T == NetProtocol.Resume ? "Reconnected into a live match" : "Match started";
                break;
            case NetProtocol.Snap:
                if (p.Tick.HasValue) LatestTick = p.Tick.Value;
                if (p.Ctrls != null) Ctrls = p.Ctrls;
                if (p.Host.HasValue) HostSlot = p.Host.Value;
                break;
            case NetProtocol.Ping:
                Send(new Packet { T = NetProtocol.Pong, Ms = p.Ms ?? 0 });
                break;
            case NetProtocol.Host:
                if (p.Host.HasValue) HostSlot = p.Host.Value;
                Status = p.Reason ?? "Host changed";
                break;
            case NetProtocol.Error:
                LastError = p.Reason ?? "Server error";
                Status = "Server error: " + LastError;
                break;
            case NetProtocol.End:
                Started = false; InMatch = false;
                Status = p.Com ?? "Full time";
                break;
            case NetProtocol.Chat:
                Status = (p.Name ?? "?") + ": " + (p.M ?? "");
                break;
        }
    }

    public int LocalPlayerIndex(int fallback)
    {
        if (Slot >= 0 && Slot < Ctrls.Length && Ctrls[Slot] >= 0) return Ctrls[Slot];
        return fallback;
    }

    public bool IsHost => Slot >= 0 && Slot == HostSlot;

    public void Close()
    {
        _transport?.Close();
        _transport = null;
        Connected = false; Started = false; InMatch = false;
        Status = "Offline";
    }
}
