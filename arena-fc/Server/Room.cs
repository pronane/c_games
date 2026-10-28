// Arena FC - one authoritative match room (v2).
//
// v2 additions
//  * Secure per-client resume tokens keep a disconnected player's slot, team,
//    controlled player and host claims for ReconnectGraceSeconds.
//  * Host migration moves the room-owner role to the next connected client
//    WITHOUT stopping the match, and hands that client a complete engine
//    checkpoint.
//  * Optional peer-authority mode (--peer-host) actually transfers the running
//    simulation to the new host; the server becomes a relay.  Without it the
//    server stays the authority and migration is a role change only.
//  * Each tick's accepted inputs are kept in a trailing log and each snapshot
//    carries the RNG word, so clients can rewind and re-simulate (rollback).
using System.Numerics;
using ArenaFC.Core;
using ArenaFC.Core.Net;

namespace ArenaFC.Server;

public sealed class Client
{
    public WsConnection Conn = null!;
    public Room Room = null!;
    public string Name = "Player";
    public string TokenHash = "";
    public int Slot = -1;
    public int Team;
    public int PlayerIndex = -1;
    public bool Ready;
    public bool Online = true;
    public long DisconnectedAtMs;
    public int PingMs = -1;
    public int Caps = NetProtocol.CapFullDesktop;
    public long PingSentMs;
    public PlayerCommand LastMove;
    public readonly Queue<PlayerCommand> Inputs = new();
    public override string ToString() => $"{Name}#{Slot}(t{Team})";
}

public sealed class Room
{
    public readonly string Code;
    public readonly long CreatedMs = Environment.TickCount64;
    /// <summary>Connected clients AND offline slot reservations.</summary>
    public readonly List<Client> Clients = new();
    public MatchOptions Template = new();
    public MatchEngine? Engine;
    public bool Started;
    public int Tick;
    public int LastSnapTick = -1;
    public int Host;                       // explicit owner; survives reconnect
    public int Authority = NetProtocol.AuthorityServer;
    public int PeerSlot = -1;
    public long LastSnapMs;
    public long LastPingMs;
    public Replay? Recorder;
    public string LastResult = "";
    /// <summary>Trailing authoritative input log, used by rollback clients.</summary>
    public readonly List<InputFrameDto> InputLog = new();
    /// <summary>Most recent commands keyed by player index, for peer hosts.</summary>
    public readonly Dictionary<int, PlayerCommand> PeerCommands = new();
    private readonly List<InputFrameDto> _pendingPeerFrames = new();
    private int _peerTick;

    private readonly Action<string> _log;

    public Room(string code, MatchOptions template, Action<string> log)
    {
        Code = code;
        Template = template;
        _log = log;
    }

    public IEnumerable<Client> Online => Clients.Where(c => c.Online);
    public int HostSlot => Online.Any() ? Host : -1;
    public bool Empty => Clients.Count == 0;
    public bool AllOffline => !Online.Any();
    public bool IsHost(Client c) => c.Online && c.Slot == Host;

    public int FreeSlot()
    {
        for (int i = 0; i < NetProtocol.MaxPlayersPerRoom; i++)
            if (Clients.All(c => c.Slot != i)) return i;
        return -1;
    }

    public Client? BySlot(int slot) => Clients.FirstOrDefault(c => c.Slot == slot);

    public Client? ByTokenHash(string hash) =>
        Clients.FirstOrDefault(c => NetProtocol.TokenHashEquals(c.TokenHash, hash));

    public void Add(Client c)
    {
        c.Room = this;
        c.Slot = FreeSlot();
        c.Team = c.Slot % 2;   // 0,2 = home; 1,3 = away
        c.Online = true;
        Clients.Add(c);
        if (!Online.Any(x => x.Slot == Host)) Host = c.Slot;
        _log($"[room {Code}] {c} joined ({Online.Count()} online/{Clients.Count} reserved)");
    }

    public void MarkOffline(Client c, long now)
    {
        if (!c.Online) return;
        c.Online = false;
        c.DisconnectedAtMs = now;
        c.Inputs.Clear();
        c.PingMs = -1;
        _log($"[room {Code}] {c} disconnected - slot reserved for {NetProtocol.ReconnectGraceSeconds}s");
    }

    public void Remove(Client c)
    {
        Clients.Remove(c);
        _log($"[room {Code}] {c} slot released ({Clients.Count} remain)");
        if (AllOffline && Started) { Started = false; Engine = null; }
    }

    /// <summary>Drop reservations whose grace period has expired.</summary>
    public bool ExpireReservations(long now)
    {
        bool changed = false;
        foreach (var c in Clients.Where(c => !c.Online &&
                 now - c.DisconnectedAtMs > NetProtocol.ReconnectGraceSeconds * 1000L).ToArray())
        {
            Remove(c);
            changed = true;
        }
        return changed;
    }

    public void Broadcast(Packet p)
    {
        string json = NetProtocol.Encode(p);
        foreach (var c in Online.ToArray())
            if (!c.Conn.Closed) _ = c.Conn.SendTextAsync(json);
    }

    public void BroadcastExcept(Client except, Packet p)
    {
        string json = NetProtocol.Encode(p);
        foreach (var c in Online.ToArray())
            if (c != except && !c.Conn.Closed) _ = c.Conn.SendTextAsync(json);
    }

    public void Send(Client c, Packet p) => _ = c.Conn.SendTextAsync(NetProtocol.Encode(p));

    public Packet LobbyPacket() => new()
    {
        T = NetProtocol.Lobby, Room = Code, Host = Host, Authority = Authority,
        Max = NetProtocol.MaxPlayersPerRoom, Started = Started,
        Mode = Template.TeamSize + "v" + Template.TeamSize,
        Seed = Template.Seed, Size = Template.TeamSize, Tick = Tick,
        Names = Clients.OrderBy(c => c.Slot).Select(c => c.Name).ToArray(),
        Slots = Clients.OrderBy(c => c.Slot).Select(c => c.Slot).ToArray(),
        Teams = Clients.OrderBy(c => c.Slot).Select(c => c.Team).ToArray(),
        Pings = Clients.OrderBy(c => c.Slot).Select(c => c.PingMs).ToArray(),
        Readys = Clients.OrderBy(c => c.Slot).Select(c => c.Ready).ToArray(),
        Onlines = Clients.OrderBy(c => c.Slot).Select(c => c.Online).ToArray(),
    };

    public void BroadcastLobby() => Broadcast(LobbyPacket());

    /// <summary>Promote the lowest still-connected slot when the owner leaves.
    /// The running simulation is never restarted.</summary>
    public Room MigrateHost(int oldSlot, bool peerHostEnabled)
    {
        if (Online.Any(c => c.Slot == Host)) return this;
        int next = Online.Any() ? Online.Min(c => c.Slot) : -1;
        if (next < 0) { Host = -1; return this; }
        int previous = Host;
        Host = next;
        _log($"[room {Code}] HOST MIGRATION slot {previous} -> {Host} (match {(Started ? "continues" : "lobby")})");

        if (peerHostEnabled && Started && Engine != null)
        {
            // Only a client that declared CapPeerHost can run the simulation.
            // Browser/WebGL clients cannot, so the server stays authoritative.
            var capable = Online.Where(c => (c.Caps & NetProtocol.CapPeerHost) != 0)
                                .OrderBy(c => c.Slot).FirstOrDefault();
            if (capable == null)
            {
                // Nobody left can run the simulation: fall back to the server's
                // cached (last submitted) engine and keep ticking locally.
                Authority = NetProtocol.AuthorityServer;
                PeerSlot = -1;
                _log($"[room {Code}] no peer-host-capable client - server resumes the simulation");
            }
            else
            {
                Authority = NetProtocol.AuthorityPeer;
                PeerSlot = capable.Slot;
                _peerTick = Tick;
                Send(capable, AuthorityPacket(capable));
                _log($"[room {Code}] simulation authority transferred to peer slot {PeerSlot}");
            }
        }

        Broadcast(new Packet
        {
            T = NetProtocol.Host, Room = Code, Host = Host, Slot = previous,
            Authority = Authority, Tick = Tick, Started = Started,
            Reason = $"Host disconnected - {(BySlot(Host)?.Name ?? "next player")} is now host.",
        });
        BroadcastLobby();
        return this;
    }

    /// <summary>The peer authority itself dropped but the lobby host is still
    /// online: elect another capable client without restarting the match.</summary>
    public void ReElectPeer(bool peerHostEnabled)
    {
        if (!Started || Engine == null || Authority != NetProtocol.AuthorityPeer) return;
        if (BySlot(PeerSlot) is { Online: true } still) return;
        if (!peerHostEnabled)
        {
            Authority = NetProtocol.AuthorityServer;
            PeerSlot = -1;
            return;
        }
        var capable = Online.Where(c => (c.Caps & NetProtocol.CapPeerHost) != 0)
                            .OrderBy(c => c.Slot).FirstOrDefault();
        if (capable == null)
        {
            Authority = NetProtocol.AuthorityServer;
            PeerSlot = -1;
            _log($"[room {Code}] peer host lost - server resumes the simulation");
        }
        else
        {
            PeerSlot = capable.Slot;
            _peerTick = Tick;
            Send(capable, AuthorityPacket(capable));
            _log($"[room {Code}] peer authority re-elected to slot {PeerSlot}");
        }
        Broadcast(new Packet
        {
            T = NetProtocol.Host, Room = Code, Host = Host, Slot = PeerSlot,
            Authority = Authority, Tick = Tick, Started = Started,
            Reason = "Match host changed - simulation continues.",
        });
        BroadcastLobby();
    }

    /// <summary>All match parameters a client needs to construct its engine.</summary>
    public Packet MatchInfo(string type) => new()
    {
        T = type, Room = Code, Seed = Template.Seed, Size = Template.TeamSize,
        HalfMinutes = Template.HalfMinutes, TimeSpeed = Template.TimeSpeed,
        Difficulty = Template.Difficulty, HomeClub = Template.HomeClub, AwayClub = Template.AwayClub,
        HomeFormation = Template.HomeFormation, AwayFormation = Template.AwayFormation,
        CameraMode = 0, CameraZoom = .68f, Tick = Tick, Host = Host,
        Authority = Authority, Grace = NetProtocol.ReconnectGraceSeconds,
        Ctrls = ControlArray(), Names = NameArray(), Ver = NetProtocol.Version,
    };

    /// <summary>Complete mid-match state for a reconnecting client.</summary>
    public Packet ResumePacket(Client c)
    {
        var p = MatchInfo(NetProtocol.Resume);
        p.Slot = c.Slot; p.Team = c.Team; p.Name = c.Name;
        p.Com = $"Reconnected into a live match at {FormatClock(Engine?.State.Clock ?? 0f)}";
        if (Engine != null)
        {
            p.Full = StateCodec.BuildFull(Engine, Tick);
            p.Players = Engine.State.Players.Select(PlayerDto.From).ToArray();
            p.Ball = BallDto.From(Engine.State.Ball);
            p.Score = (int[])Engine.State.Score.Clone();
            p.Clock = Engine.State.Clock; p.Phase = (int)Engine.State.Phase; p.Half = Engine.State.Half;
        }
        p.Inputs = InputLog.TakeLast(NetProtocol.MaxRollbackTicks * 3).ToArray();
        return p;
    }

    /// <summary>Complete state handoff to a newly promoted peer authority.</summary>
    public Packet AuthorityPacket(Client c)
    {
        var p = MatchInfo(NetProtocol.Authority);
        p.Slot = c.Slot; p.Team = c.Team; p.Name = c.Name;
        p.Authority = NetProtocol.AuthorityPeer;
        p.Com = "You are now the match host - running the authoritative simulation.";
        if (Engine != null) p.Full = StateCodec.BuildFull(Engine, Tick);
        p.Inputs = InputLog.TakeLast(NetProtocol.MaxRollbackTicks * 3).ToArray();
        return p;
    }

    private static string FormatClock(float clock)
    {
        int m = (int)(clock / 60f), s = (int)(clock % 60f);
        return $"{m:00}:{s:00}";
    }

    public void Start()
    {
        var opt = new MatchOptions
        {
            TeamSize = Template.TeamSize, Seed = Template.Seed,
            TimeSpeed = Template.TimeSpeed, HalfMinutes = Template.HalfMinutes,
            Difficulty = Template.Difficulty, Offside = true, Fouls = true,
            HomeClub = Template.HomeClub, AwayClub = Template.AwayClub,
            HomeFormation = Template.HomeFormation, AwayFormation = Template.AwayFormation,
            CameraMode = 0, CameraZoom = .68f,
            AwayHuman = Online.Any(c => c.Team == 1),
        };
        Engine = new MatchEngine(opt);
        Started = true;
        Tick = 0; LastSnapTick = -1;
        Authority = NetProtocol.AuthorityServer; PeerSlot = -1;
        InputLog.Clear(); PeerCommands.Clear();
        LastResult = "";
        Recorder = new Replay { Seed = opt.Seed, TeamSize = opt.TeamSize, AwayHuman = opt.AwayHuman };

        AssignPlayers();
        Broadcast(MatchInfo(NetProtocol.Begin));
        _log($"[room {Code}] match started seed={opt.Seed} size={opt.TeamSize} humans={Online.Count()}");
        BroadcastSnapshot();
    }

    private void AssignPlayers()
    {
        if (Engine == null) return;
        var used = new HashSet<int>();
        foreach (var group in Clients.GroupBy(c => c.Team).OrderBy(g => g.Key))
        {
            bool first = true;
            foreach (var c in group.OrderBy(x => x.Slot))
            {
                int idx = first
                    ? (group.Key == 0 ? Engine.State.Controlled : Engine.State.ControlledAway)
                    : -1;
                if (idx < 0 || used.Contains(idx)) idx = PickFree(Engine, group.Key, used);
                c.PlayerIndex = idx;
                used.Add(idx);
                first = false;
            }
        }
    }

    private static int PickFree(MatchEngine e, int team, HashSet<int> used)
    {
        int start = team * e.Options.TeamSize;
        for (int i = start + 1; i < start + e.Options.TeamSize; i++)
            if (!used.Contains(i)) return i;
        return start;
    }

    /// <summary>Keep human-controlled indices distinct after the engine's
    /// automatic player switching on ball pickup.</summary>
    private void ReassignOverlaps()
    {
        if (Engine == null) return;
        var seen = new HashSet<int>();
        foreach (var c in Clients.OrderBy(x => x.Slot))
        {
            if (c.PlayerIndex < 0 || c.PlayerIndex >= Engine.State.Players.Length ||
                seen.Contains(c.PlayerIndex) || Engine.State.Players[c.PlayerIndex].Team != c.Team)
                c.PlayerIndex = PickFree(Engine, c.Team, seen);
            seen.Add(c.PlayerIndex);
        }
    }

    private void SyncAutoSwitch()
    {
        if (Engine == null) return;
        var home = Clients.Where(c => c.Team == 0).OrderBy(c => c.Slot).FirstOrDefault();
        var away = Clients.Where(c => c.Team == 1).OrderBy(c => c.Slot).FirstOrDefault();
        if (home != null && Engine.State.Controlled >= 0) home.PlayerIndex = Engine.State.Controlled;
        if (away != null && Engine.State.ControlledAway >= 0) away.PlayerIndex = Engine.State.ControlledAway;
        ReassignOverlaps();
    }

    /// <summary>Collect one frame of commands from every connected client.</summary>
    private Dictionary<int, PlayerCommand> CollectCommands()
    {
        var cmds = new Dictionary<int, PlayerCommand>(4);
        foreach (var c in Clients.OrderBy(x => x.Slot))
        {
            PlayerCommand cmd;
            if (!c.Online) cmd = PlayerCommand.None;
            else if (c.Inputs.Count > 0) cmd = c.Inputs.Dequeue();
            else cmd = new PlayerCommand { Move = c.LastMove.Move, Sprint = c.LastMove.Sprint };
            c.LastMove = new PlayerCommand { Move = cmd.Move, Sprint = cmd.Sprint };
            if (cmd.Switch && Engine != null)
            {
                int next = Engine.FindNearestForTeam(c.Team, Engine.State.Ball.Pos, true);
                if (next >= 0) c.PlayerIndex = next;
            }
            if (Engine != null && c.PlayerIndex >= 0 && c.PlayerIndex < Engine.State.Players.Length)
                cmds[c.PlayerIndex] = cmd;
        }
        return cmds;
    }

    public void TickSim()
    {
        if (!Started || Engine == null) return;
        var cmds = CollectCommands();
        var frame = new Dictionary<int, CommandDto>(cmds.Count);
        foreach (var kv in cmds) frame[kv.Key] = CommandDto.From(kv.Value);

        if (Authority == NetProtocol.AuthorityPeer)
        {
            // The peer host simulates.  Forward the latest commands so it can
            // include them in its authoritative ticks.
            _peerTick++;
            foreach (var kv in cmds) PeerCommands[kv.Key] = kv.Value;
            _pendingPeerFrames.Add(new InputFrameDto { T = _peerTick, C = frame });
            // Batch three 60 Hz ticks into one 20 Hz message instead of
            // flooding the peer with 60 tiny WebSocket frames per second.
            if (_pendingPeerFrames.Count < 3) return;
            var host = BySlot(PeerSlot);
            if (host != null && host.Online)
                Send(host, new Packet
                {
                    T = NetProtocol.PeerInput, Tick = _peerTick,
                    Inputs = _pendingPeerFrames.ToArray(),
                });
            _pendingPeerFrames.Clear();
            return;
        }

        ReassignOverlaps();
        Engine.StepNetwork(MatchEngine.Dt, cmds);
        Tick++;
        RecordFrame(frame);
        SyncAutoSwitch();
        if (Engine.State.Phase == Phase.FullTime) Finish();
    }

    private void RecordFrame(Dictionary<int, CommandDto> frame)
    {
        InputLog.Add(new InputFrameDto { T = Tick, C = frame });
        Recorder?.Ticks.Add(frame.ToDictionary(k => k.Key, v => v.Value));
        if (InputLog.Count > 240) InputLog.RemoveRange(0, InputLog.Count - 240);
    }

    /// <summary>Accept an authoritative submission from the peer host.</summary>
    public bool ApplySubmit(Client c, Packet p)
    {
        if (Authority != NetProtocol.AuthorityPeer || c.Slot != PeerSlot || Engine == null) return false;
        if (p.Full != null)
        {
            StateCodec.ApplyFull(Engine, p.Full);
            Tick = p.Full.Tick;
        }
        else if (p.Tick.HasValue) Tick = p.Tick.Value;
        if (p.Inputs != null)
            foreach (var f in p.Inputs)
            {
                if (InputLog.All(x => x.T != f.T)) InputLog.Add(f);
                Recorder?.Ticks.Add(new Dictionary<int, CommandDto>(f.C));
            }
        while (InputLog.Count > 240) InputLog.RemoveAt(0);
        return true;
    }

    public int[] ControlArray()
    {
        var a = new int[NetProtocol.MaxPlayersPerRoom];
        Array.Fill(a, -1);
        foreach (var c in Clients) if (c.Slot >= 0 && c.Slot < a.Length) a[c.Slot] = c.PlayerIndex;
        return a;
    }

    public string[] NameArray()
    {
        var a = new string[NetProtocol.MaxPlayersPerRoom];
        Array.Fill(a, "");
        foreach (var c in Clients) if (c.Slot >= 0 && c.Slot < a.Length) a[c.Slot] = c.Name;
        return a;
    }

    public int[] PingArray()
    {
        var a = new int[NetProtocol.MaxPlayersPerRoom];
        Array.Fill(a, -1);
        foreach (var c in Clients) if (c.Slot >= 0 && c.Slot < a.Length) a[c.Slot] = c.PingMs;
        return a;
    }

    public void BroadcastSnapshot()
    {
        if (!Started || Engine == null) return;
        var trailing = InputLog.Where(f => f.T > LastSnapTick).ToArray();
        Broadcast(Snapshot.Build(Engine, Tick, ControlArray(), PingArray(), NameArray(),
            trailing, Authority, Host));
        LastSnapTick = Tick;
        LastSnapMs = Environment.TickCount64;
    }

    /// <summary>Relay a peer host's submitted snapshot to the other clients.</summary>
    public void RelaySubmit(Client from, Packet p)
    {
        p.T = NetProtocol.Snap;
        p.Full = null;                 // peers only need the lightweight snapshot
        p.Room = Code;
        p.Host = Host;
        p.Authority = Authority;
        p.Ctrls = ControlArray();
        p.Pings = PingArray();
        p.Names = NameArray();
        BroadcastExcept(from, p);
    }

    public void SendPings(long now)
    {
        LastPingMs = now;
        foreach (var c in Online.ToArray())
        {
            c.PingSentMs = now;
            Send(c, new Packet { T = NetProtocol.Ping, Ms = (int)(now & 0x7fffffffL) });
        }
    }

    private void Finish()
    {
        if (Engine == null) return;
        LastResult = $"{Engine.State.Score[0]} - {Engine.State.Score[1]}";
        try
        {
            var dir = Path.Combine(AppContext.BaseDirectory, "replays");
            Directory.CreateDirectory(dir);
            string file = Path.Combine(dir, $"{Code}-{DateTime.UtcNow:yyyyMMdd-HHmmss}.json");
            File.WriteAllText(file, Recorder?.ToJson() ?? "{}");
            _log($"[room {Code}] replay saved -> {file}");
        }
        catch (Exception ex) { _log($"[room {Code}] replay save failed: {ex.Message}"); }
        BroadcastSnapshot();
        Broadcast(new Packet
        {
            T = NetProtocol.End, Room = Code, Reason = "Full time",
            Score = (int[])Engine.State.Score.Clone(),
            Com = $"FULL TIME  {LastResult}",
        });
        Started = false;
        Engine = null;
        Authority = NetProtocol.AuthorityServer;
        PeerSlot = -1;
        foreach (var c in Clients) { c.Ready = false; c.Inputs.Clear(); }
        BroadcastLobby();
        _log($"[room {Code}] full time {LastResult}");
    }
}
