// Arena FC - Play With Friends server (v2: reconnect + host migration + rollback).
//
//   dotnet run --project Server/ArenaFC.Server.csproj -- --port 7777
//   ./ArenaFC.Server --port 7777 --team-size 5 --seed 2026 --peer-host
//
// One process hosts many room-code matches. It is authoritative by default:
// clients send input, the server steps the deterministic core at 60 Hz and
// broadcasts interpolated snapshots at 20 Hz.  With --peer-host, a host
// disconnect migrates the actual simulation to the next client.
using System.Collections.Concurrent;
using System.Diagnostics;
using System.Text;
using System.Text.Json;
using ArenaFC.Core;
using ArenaFC.Core.Net;

namespace ArenaFC.Server;

public static class Program
{
    private sealed class Hub
    {
        public readonly ConcurrentDictionary<string, Room> Rooms = new();
        public readonly ConcurrentDictionary<string, Client> ByConn = new();
        public readonly object Gate = new();
        public readonly MatchOptions Template = new() { TeamSize = 5 };
        public readonly long StartedMs = Environment.TickCount64;
        public int Port = NetProtocol.DefaultPort;
        public bool Verbose;
        public bool PeerHost;
        public int GraceSeconds = NetProtocol.ReconnectGraceSeconds;
        public float SnapHz = NetProtocol.SnapshotHz;
        public int TickHz = 60;
        public int MaxRooms = 200;
        public int Migrations;
        public int Reconnects;
        public int Submits;
        public Action<string> Log = Console.WriteLine;

        public void Info(string s) { if (Verbose) Log(s); }
    }

    private static Hub _hub = new();

    public static int Main(string[] args)
    {
        // Option B: .NET binds to localhost only. The Node edge (Render) is the public face
        // and proxies wss://<host>/ws -> ws://127.0.0.1:7777. --bind can override for LAN.
        string bind = "127.0.0.1";
        int port = NetProtocol.DefaultPort;
        bool verbose = false;
        for (int i = 0; i < args.Length; i++)
        {
            string a = args[i];
            string? Next() => i + 1 < args.Length ? args[++i] : null;
            switch (a)
            {
                case "--port": if (int.TryParse(Next(), out var p)) port = p; break;
                case "--bind": bind = Next() ?? bind; break;
                case "--team-size": if (int.TryParse(Next(), out var ts)) _hub.Template.TeamSize = ts; break;
                case "--seed": if (int.TryParse(Next(), out var sd)) _hub.Template.Seed = sd; break;
                case "--half-minutes": if (float.TryParse(Next(), out var hm)) _hub.Template.HalfMinutes = hm; break;
                case "--time-speed": if (float.TryParse(Next(), out var sp)) _hub.Template.TimeSpeed = sp; break;
                case "--difficulty": if (int.TryParse(Next(), out var d)) _hub.Template.Difficulty = d; break;
                case "--snap-hz": if (float.TryParse(Next(), out var sh)) _hub.SnapHz = sh; break;
                case "--tick-hz": if (int.TryParse(Next(), out var th)) _hub.TickHz = th; break;
                case "--max-rooms": if (int.TryParse(Next(), out var mr)) _hub.MaxRooms = mr; break;
                case "--grace-seconds": if (int.TryParse(Next(), out var gs)) _hub.GraceSeconds = gs; break;
                case "--peer-host": _hub.PeerHost = true; break;
                case "--verbose": case "-v": verbose = true; break;
                case "--help": case "-h": PrintHelp(); return 0;
                default: Console.Error.WriteLine($"unknown option: {a}"); PrintHelp(); return 2;
            }
        }
        _hub.Port = port;
        _hub.Verbose = verbose;
        _hub.Template.TeamSize = new[] { 5, 7, 11 }.Contains(_hub.Template.TeamSize) ? _hub.Template.TeamSize : 5;
        _hub.SnapHz = Math.Clamp(_hub.SnapHz, 5f, 60f);
        _hub.TickHz = Math.Clamp(_hub.TickHz, 30, 120);
        NetProtocol.ReconnectGraceSeconds = Math.Clamp(_hub.GraceSeconds, 5, 3600);

        using var cts = new CancellationTokenSource();
        Console.CancelKeyPress += (_, e) => { e.Cancel = true; cts.Cancel(); };

        var server = new WsServer(bind, port)
        {
            OnMessage = OnMessage,
            OnClose = OnClose,
            OnHttp = OnHttp,
            Log = s => { Console.WriteLine(s); },
        };

        Console.WriteLine("=====================================================");
        Console.WriteLine("  ARENA FC  ·  PLAY WITH FRIENDS SERVER  ·  v2.0");
        Console.WriteLine("=====================================================");
        Console.WriteLine($"  WebSocket   ws://{bind}:{port}  (internal; Node edge proxies /ws)");
        Console.WriteLine($"  Status      http://127.0.0.1:{port}/  (internal)");
        Console.WriteLine($"  Health      http://127.0.0.1:{port}/health  (internal)");
        Console.WriteLine($"  Match       {_hub.Template.TeamSize}v{_hub.Template.TeamSize}  seed={_hub.Template.Seed}  " +
                          $"sim={_hub.TickHz}Hz  snapshots={_hub.SnapHz:0.#}Hz");
        Console.WriteLine($"  Reconnect   {NetProtocol.ReconnectGraceSeconds}s slot reservation + 256-bit token");
        Console.WriteLine($"  Migration   {(_hub.PeerHost ? "peer simulation handoff" : "host role (server keeps simulating)")}");
        Console.WriteLine("  Friends: open Arena FC -> PLAY WITH FRIENDS -> enter the public proxy");
        Console.WriteLine("  address (wss://YOUR-PUBLIC-HOST/ws), then CREATE MATCH and share the 6-letter room code.");
        Console.WriteLine($"  The .NET server listens on {bind}:{port} (LAN-only by default).");
        Console.WriteLine("=====================================================");

        var loop = Task.Run(() => GameLoop(cts.Token));
        try { server.RunAsync(cts.Token).GetAwaiter().GetResult(); }
        catch (OperationCanceledException) { }
        catch (Exception ex) { Console.Error.WriteLine("server error: " + ex); return 1; }
        cts.Cancel();
        try { loop.GetAwaiter().GetResult(); } catch { }
        Console.WriteLine("server stopped.");
        return 0;
    }

    private static void PrintHelp()
    {
        Console.WriteLine("""
            Arena FC - Play With Friends server

              dotnet run --project Server/ArenaFC.Server.csproj -- [options]
              ./ArenaFC.Server [options]

            Options:
              --port N           WebSocket + HTTP port (default 7777)
              --bind ADDR        127.0.0.1 (default, internal) or 0.0.0.0 for LAN/public
              --team-size N      5, 7 or 11 players per side (default 5)
              --seed N           deterministic match seed (default 2026)
              --half-minutes N   game minutes per half (default 45)
              --time-speed N     game seconds per real second (default 15)
              --difficulty N     0 easy .. 3 legendary (default 1)
              --snap-hz N        snapshot broadcasts per second (default 20)
              --tick-hz N        simulation ticks per second (default 60)
              --max-rooms N      room cap (default 200)
              --grace-seconds N  reconnect slot reservation (default 180)
              --peer-host        on host loss, transfer the live simulation to
                                 the new host client (server becomes a relay)
              --verbose          log every join / input / match event
            """);
    }

    // ------------------------------------------------------------ messaging

    private static void OnMessage(WsConnection conn, string text)
    {
        var p = NetProtocol.Decode(text);
        if (p == null) { _hub.Info($"bad json from {conn.Id}: {text[..Math.Min(80, text.Length)]}"); return; }
        lock (_hub.Gate)
        {
            switch (p.T)
            {
                case NetProtocol.Hello:
                    HandleHello(conn, p);
                    break;
                case NetProtocol.Input:
                    if (_hub.ByConn.TryGetValue(conn.Id, out var c) && p.Cmd != null)
                    {
                        var cmd = p.Cmd.To();
                        c.Inputs.Enqueue(cmd);
                        while (c.Inputs.Count > 12) c.Inputs.Dequeue();
                        c.LastMove = new PlayerCommand { Move = cmd.Move, Sprint = cmd.Sprint };
                    }
                    break;
                case NetProtocol.Pong:
                    if (_hub.ByConn.TryGetValue(conn.Id, out var pc) && p.Ms.HasValue)
                        pc.PingMs = (int)Math.Clamp((Environment.TickCount64 & 0x7fffffffL) - p.Ms.Value, 0d, 9999d);
                    break;
                case NetProtocol.Start:
                    if (_hub.ByConn.TryGetValue(conn.Id, out var host) &&
                        host.Room.IsHost(host) && !host.Room.Started)
                        host.Room.Start();
                    break;
                case NetProtocol.Ready:
                    if (_hub.ByConn.TryGetValue(conn.Id, out var rc))
                    {
                        rc.Ready = p.Ready ?? !rc.Ready;
                        rc.Room.BroadcastLobby();
                    }
                    break;
                case NetProtocol.Chat:
                    if (_hub.ByConn.TryGetValue(conn.Id, out var cc))
                    {
                        string msg = (p.M ?? "").Trim();
                        if (msg.Length > 0)
                            cc.Room.Broadcast(new Packet
                            {
                                T = NetProtocol.Chat, Name = cc.Name,
                                M = msg.Length > 160 ? msg[..160] : msg, Slot = cc.Slot,
                            });
                    }
                    break;
                case NetProtocol.Submit:
                    if (_hub.ByConn.TryGetValue(conn.Id, out var submitter) &&
                        submitter.Room.ApplySubmit(submitter, p))
                    {
                        _hub.Submits++;
                        submitter.Room.RelaySubmit(submitter, p);
                        submitter.Room.LastSnapMs = Environment.TickCount64;
                    }
                    break;
                case NetProtocol.Kick:
                    if (_hub.ByConn.TryGetValue(conn.Id, out var kicker) &&
                        kicker.Room.IsHost(kicker) && p.KickSlot.HasValue)
                        HandleKick(kicker, p.KickSlot.Value);
                    break;
                case NetProtocol.Leave:
                    conn.Close();
                    break;
                default:
                    _hub.Info($"unknown message '{p.T}' from {conn.Id}");
                    break;
            }
        }
    }

    private static void HandleKick(Client host, int slot)
    {
        if (slot == host.Slot || slot < 0) return;
        var target = host.Room.BySlot(slot);
        if (target == null) return;
        _hub.ByConn.TryRemove(target.Conn.Id, out _);
        host.Room.Remove(target);
        target.Conn.Close();
        if (host.Room.AllOffline) _hub.Rooms.TryRemove(host.Room.Code, out _);
        else host.Room.BroadcastLobby();
        host.Room.MigrateHost(slot, _hub.PeerHost);
    }

    private static void HandleHello(WsConnection conn, Packet p)
    {
        if (_hub.ByConn.ContainsKey(conn.Id)) return;
        if (p.Ver.HasValue && p.Ver.Value > NetProtocol.Version)
        {
            _ = conn.SendTextAsync(NetProtocol.Encode(new Packet
            {
                T = NetProtocol.Error, Reason = $"Protocol mismatch: server={NetProtocol.Version}, client={p.Ver}",
            }));
            conn.Close();
            return;
        }

        // ---- Secure resume: reclaim an offline slot with the bearer token ----
        if (!string.IsNullOrWhiteSpace(p.Token) && p.Token.Length >= 32)
        {
            string hash = NetProtocol.HashToken(p.Token);
            string wantedRoom = NetProtocol.NormalizeRoom(p.Room);
            var candidates = (wantedRoom.Length > 0 && _hub.Rooms.TryGetValue(wantedRoom, out var one)
                ? new[] { one } : _hub.Rooms.Values.ToArray());
            Client? reclaimed = null;
            foreach (var r in candidates)
            {
                var c = r.ByTokenHash(hash);
                if (c != null && !c.Online &&
                    Environment.TickCount64 - c.DisconnectedAtMs <= NetProtocol.ReconnectGraceSeconds * 1000L)
                { reclaimed = c; break; }
                // A stale socket that never fired OnClose: take over the slot.
                if (c != null && c.Conn.Closed) { reclaimed = c; break; }
            }
            if (reclaimed != null)
            {
                Reclaim(conn, reclaimed);
                return;
            }
        }

        string wanted = NetProtocol.NormalizeRoom(p.Room);
        bool create = p.Create ?? false;
        Room room;
        bool exists = wanted.Length > 0 && _hub.Rooms.ContainsKey(wanted);
        if (wanted.Length > 0 && !exists && !create)
        {
            _ = conn.SendTextAsync(NetProtocol.Encode(new Packet
            { T = NetProtocol.Error, Reason = $"Room {wanted} does not exist. Check the 6-letter code.", Room = wanted }));
            return;
        }
        if (wanted.Length > 0 && exists && create)
        {
            _ = conn.SendTextAsync(NetProtocol.Encode(new Packet
            { T = NetProtocol.Error, Reason = $"Room {wanted} already exists - use JOIN.", Room = wanted }));
            return;
        }
        if (wanted.Length > 0 && exists)
        {
            room = _hub.Rooms[wanted];
            if (room.Started)
            {
                _ = conn.SendTextAsync(NetProtocol.Encode(new Packet
                { T = NetProtocol.Error, Reason = $"Match in room {wanted} is already playing.", Room = wanted }));
                return;
            }
            if (room.FreeSlot() < 0)
            {
                _ = conn.SendTextAsync(NetProtocol.Encode(new Packet
                { T = NetProtocol.Error, Reason = $"Room {wanted} is full.", Room = wanted }));
                return;
            }
        }
        else
        {
            if (_hub.Rooms.Count >= _hub.MaxRooms)
            {
                _ = conn.SendTextAsync(NetProtocol.Encode(new Packet
                { T = NetProtocol.Error, Reason = "Server is full. Try again later." }));
                return;
            }
            string code;
            if (wanted.Length >= 3 && wanted.Length <= 12 && wanted.All(char.IsLetterOrDigit))
                code = wanted;
            else
                do { code = NetProtocol.NewRoomCode(); } while (_hub.Rooms.ContainsKey(code));
            room = new Room(code, _hub.Template, s => _hub.Log(s));
            _hub.Rooms[code] = room;
        }

        var client = new Client
        {
            Conn = conn, Room = room,
            Name = NetProtocol.NormalizeName(p.Name),
            Caps = p.Caps ?? NetProtocol.CapFullDesktop,
        };
        int dup = 1;
        string baseName = client.Name;
        while (room.Clients.Any(x => x.Name == client.Name))
            client.Name = $"{baseName[..Math.Min(13, baseName.Length)]}{++dup}";
        string token = NetProtocol.NewResumeToken();
        client.TokenHash = NetProtocol.HashToken(token);
        room.Add(client);
        _hub.ByConn[conn.Id] = client;
        conn.Tag = client;

        SendWelcome(room, client, token);
        room.BroadcastLobby();
    }

    /// <summary>Reconnect into the same slot, team and controlled player.</summary>
    private static void Reclaim(WsConnection conn, Client client)
    {
        var room = client.Room;
        var old = client.Conn;
        client.Conn = conn;
        client.Online = true;
        client.DisconnectedAtMs = 0;
        client.Inputs.Clear();
        conn.Tag = client;
        _hub.ByConn[conn.Id] = client;
        if (old.Id != conn.Id)
        {
            _hub.ByConn.TryRemove(old.Id, out _);
            if (!old.Closed) old.Close();
        }
        _hub.Reconnects++;
        _hub.Log($"[room {room.Code}] RESUME {client} reclaimed slot at tick {room.Tick} " +
                 $"(match {(room.Started ? "running" : "lobby")})");
        SendWelcome(room, client, null);
        if (room.Started)
        {
            // Full mid-match state: the client continues from this exact tick.
            room.Send(client, room.ResumePacket(client));
            room.Send(client, Snapshot.Build(room.Engine!, room.Tick, room.ControlArray(),
                room.PingArray(), room.NameArray(), room.InputLog.TakeLast(8).ToArray(),
                room.Authority, room.Host));
        }
        else room.Send(client, room.LobbyPacket());
        room.BroadcastLobby();
        if (!room.Online.Any(c => c.Slot == room.Host)) room.MigrateHost(-1, _hub.PeerHost);
    }

    private static void SendWelcome(Room room, Client client, string? token)
    {
        room.Send(client, new Packet
        {
            T = NetProtocol.Welcome, Room = room.Code, Slot = client.Slot,
            Team = client.Team, Name = client.Name, Ver = NetProtocol.Version,
            Seed = room.Template.Seed, Size = room.Template.TeamSize,
            Max = NetProtocol.MaxPlayersPerRoom, Host = room.Host,
            Authority = room.Authority, Grace = NetProtocol.ReconnectGraceSeconds,
            Started = room.Started, Tick = room.Tick,
            Token = token,                       // only sent on the original handshake
        });
    }

    private static void OnClose(WsConnection conn)
    {
        lock (_hub.Gate)
        {
            if (!_hub.ByConn.TryRemove(conn.Id, out var c)) return;
            // A reclaimed connection may close late; ignore its stale OnClose.
            if (c.Conn.Id != conn.Id) return;
            var room = c.Room;
            int oldHost = room.Host;
            room.MarkOffline(c, Environment.TickCount64);
            if (room.AllOffline)
            {
                // Keep the room alive for the grace period so the token works.
                _hub.Info($"room {room.Code} empty - holding reservations");
            }
            if (c.Slot == oldHost)
            {
                _hub.Migrations++;
                room.MigrateHost(oldHost, _hub.PeerHost);
            }
            else
            {
                room.ReElectPeer(_hub.PeerHost);
                room.BroadcastLobby();
            }
        }
    }

    // ------------------------------------------------------------ game loop

    private static void GameLoop(CancellationToken ct)
    {
        double simStep = 1.0 / _hub.TickHz;
        double snapStep = 1.0 / _hub.SnapHz;
        var sw = Stopwatch.StartNew();
        double lastSim = 0, lastSnap = 0, lastPing = 0, lastGc = 0;
        while (!ct.IsCancellationRequested)
        {
            double now = sw.Elapsed.TotalSeconds;
            if (now - lastSim >= simStep)
            {
                lastSim = now;
                lock (_hub.Gate)
                    foreach (var room in _hub.Rooms.Values) room.TickSim();
            }
            if (now - lastSnap >= snapStep)
            {
                lastSnap = now;
                lock (_hub.Gate)
                    foreach (var room in _hub.Rooms.Values)
                        if (room.Started && room.Authority == NetProtocol.AuthorityServer)
                            room.BroadcastSnapshot();
            }
            if (now - lastPing >= 2.0)
            {
                lastPing = now;
                long ms = Environment.TickCount64;
                lock (_hub.Gate)
                    foreach (var room in _hub.Rooms.Values) room.SendPings(ms);
            }
            if (now - lastGc >= 5.0)
            {
                lastGc = now;
                lock (_hub.Gate)
                {
                    foreach (var r in _hub.Rooms.Values)
                        if (r.ExpireReservations(Environment.TickCount64)) r.BroadcastLobby();
                    foreach (var kv in _hub.Rooms.Where(kv => kv.Value.AllOffline &&
                             Environment.TickCount64 - kv.Value.CreatedMs > 5_000 &&
                             kv.Value.Clients.All(c => Environment.TickCount64 - c.DisconnectedAtMs >
                                 NetProtocol.ReconnectGraceSeconds * 1000L)).ToArray())
                    {
                        _hub.Rooms.TryRemove(kv.Key, out _);
                        _hub.Info($"room {kv.Key} closed after grace period");
                    }
                }
            }
            Thread.Sleep(1);
        }
    }

    // ------------------------------------------------------------ HTTP status

    private static (string, string) OnHttp(string path)
    {
        if (path.StartsWith("/health"))
        {
            lock (_hub.Gate)
            {
                var payload = new
                {
                    ok = true, game = "Arena FC", protocol = NetProtocol.Version,
                    uptimeSeconds = (Environment.TickCount64 - _hub.StartedMs) / 1000,
                    teamSize = _hub.Template.TeamSize, seed = _hub.Template.Seed,
                    rooms = _hub.Rooms.Count, players = _hub.ByConn.Count,
                    peerHost = _hub.PeerHost,
                    reconnectGraceSeconds = NetProtocol.ReconnectGraceSeconds,
                    migrations = _hub.Migrations, reconnects = _hub.Reconnects, submits = _hub.Submits,
                    matches = _hub.Rooms.Values.Select(r => new
                    {
                        code = r.Code, players = r.Online.Count(), reservations = r.Clients.Count - r.Online.Count(),
                        host = r.Host, authority = r.Authority, started = r.Started,
                        tick = r.Tick, score = r.Engine == null ? null : r.Engine.State.Score,
                    }).ToArray(),
                };
                return ("application/json; charset=utf-8", JsonSerializer.Serialize(payload));
            }
        }
        lock (_hub.Gate)
        {
            var sb = new StringBuilder();
            sb.AppendLine("<!doctype html><html><head><meta charset='utf-8'>");
            sb.AppendLine("<meta http-equiv='refresh' content='5'><title>Arena FC - Play With Friends</title>");
            sb.AppendLine("<style>body{background:#0b1218;color:#e7f2ef;font:15px system-ui,sans-serif;margin:0;padding:32px;max-width:820px;margin:auto}" +
                          "h1{color:#35e8a0}code{background:#15242d;padding:3px 7px;border-radius:5px;color:#7fffc9}" +
                          "table{border-collapse:collapse;width:100%;margin-top:18px}td,th{padding:9px;border-bottom:1px solid #20323b;text-align:left}" +
                          ".box{background:#101e26;border:1px solid #1f3540;border-radius:10px;padding:18px;margin:16px 0}</style></head><body>");
            sb.AppendLine("<h1>ARENA FC · PLAY WITH FRIENDS</h1>");
            sb.AppendLine($"<p>Server online · protocol v{NetProtocol.Version} · {_hub.Template.TeamSize}v{_hub.Template.TeamSize} · " +
                          $"sim {_hub.TickHz} Hz · snapshots {_hub.SnapHz:0.#} Hz · " +
                          $"reconnect grace {NetProtocol.ReconnectGraceSeconds}s · " +
                          $"migration {(_hub.PeerHost ? "peer simulation handoff" : "host role")}</p>");
            sb.AppendLine("<div class='box'><b>How to play</b><br>1. In the game, open <b>PLAY WITH FRIENDS</b>.<br>" +
                          $$"2. Set the server address to <code>wss://YOUR-PUBLIC-HOST/ws</code>.<br>" +
                          "3. One friend clicks <b>CREATE MATCH</b> and shares the 6-letter room code.<br>" +
                          "4. Everyone else enters that code and clicks <b>JOIN</b>.<br>" +
                          "5. The host clicks <b>START MATCH</b>. Play!<br>" +
                          "If you drop, the game reconnects automatically with your team and player intact.</div>");
            sb.AppendLine($"<p><b>Active rooms:</b> {_hub.Rooms.Count} &nbsp; <b>Connected players:</b> {_hub.ByConn.Count} &nbsp; " +
                          $"<b>Migrations:</b> {_hub.Migrations} &nbsp; <b>Reconnects:</b> {_hub.Reconnects}</p>");
            sb.AppendLine("<table><tr><th>Room</th><th>Players</th><th>State</th><th>Host</th><th>Score</th><th>Names</th></tr>");
            foreach (var r in _hub.Rooms.Values.OrderBy(x => x.Code))
                sb.AppendLine($"<tr><td><code>{r.Code}</code></td><td>{r.Online.Count()}/{NetProtocol.MaxPlayersPerRoom}</td>" +
                              $"<td>{(r.Started ? "PLAYING · tick " + r.Tick : "LOBBY")}" +
                              $"{(r.Authority == NetProtocol.AuthorityPeer ? " · peer-host" : "")}</td>" +
                              $"<td>{r.Host}</td>" +
                              $"<td>{(r.Engine == null ? "-" : r.Engine.State.Score[0] + " - " + r.Engine.State.Score[1])}</td>" +
                              $"<td>{string.Join(", ", r.Clients.Select(c => System.Net.WebUtility.HtmlEncode(c.Name) + (c.Online ? "" : " (reconnecting)")))}</td></tr>");
            sb.AppendLine("</table><p style='color:#7d949c;margin-top:26px'>Health endpoint: <a style='color:#7fffc9' href='/health'>/health</a> · " +
                          "Arena FC is original open-source code; no licensed football assets.</p></body></html>");
            return ("text/html; charset=utf-8", sb.ToString());
        }
    }
}
