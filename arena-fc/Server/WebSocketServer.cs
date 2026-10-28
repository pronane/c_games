// Arena FC - tiny dependency-free RFC 6455 WebSocket server.
// Why not ASP.NET? The relay must run on a Raspberry Pi, a free VPS or a friend's
// laptop with nothing but the .NET 9 runtime installed. No NuGet packages, no
// ASP.NET shared framework requirement, no native dependencies.
using System.Net;
using System.Net.Sockets;
using System.Security.Cryptography;
using System.Text;

namespace ArenaFC.Server;

public sealed class WsConnection
{
    public const string GuidMagic = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";

    public readonly TcpClient Tcp;
    public readonly NetworkStream Stream;
    public readonly SemaphoreSlim SendLock = new(1, 1);
    public readonly string Id;
    public readonly string Peer;
    public volatile bool Closed;
    public long LastSeenMs;

    public Action<WsConnection, string>? OnMessage;
    public Action<WsConnection>? OnClose;
    public object Tag = new();

    public WsConnection(TcpClient tcp, string id)
    {
        Tcp = tcp;
        Stream = tcp.GetStream();
        Id = id;
        Peer = tcp.Client.RemoteEndPoint?.ToString() ?? "?";
        LastSeenMs = Environment.TickCount64;
    }

    public async Task SendTextAsync(string text) => await SendFrameAsync(0x1, Encoding.UTF8.GetBytes(text));
    public async Task SendBinaryAsync(byte[] data) => await SendFrameAsync(0x2, data);

    private async Task SendFrameAsync(byte opcode, byte[] payload)
    {
        if (Closed) return;
        int len = payload.Length;
        byte[] header;
        if (len < 126) { header = new byte[2]; header[1] = (byte)len; }
        else if (len <= ushort.MaxValue)
        {
            header = new byte[4]; header[1] = 126;
            header[2] = (byte)(len >> 8); header[3] = (byte)len;
        }
        else
        {
            header = new byte[10]; header[1] = 127;
            for (int i = 0; i < 8; i++) header[9 - i] = (byte)((long)len >> (8 * i));
        }
        header[0] = (byte)(0x80 | opcode);
        await SendLock.WaitAsync();
        try
        {
            await Stream.WriteAsync(header);
            if (len > 0) await Stream.WriteAsync(payload);
            await Stream.FlushAsync();
        }
        catch { Close(); }
        finally { SendLock.Release(); }
    }

    public async Task RunReadLoopAsync(CancellationToken ct)
    {
        var buf = new byte[8192];
        var frag = new List<byte>();
        byte fragOpcode = 0;
        try
        {
            while (!ct.IsCancellationRequested && !Closed)
            {
                int first = await Stream.ReadAsync(buf, 0, 2, ct);
                if (first < 2) break;
                byte b0 = buf[0], b1 = buf[1];
                bool fin = (b0 & 0x80) != 0;
                byte opcode = (byte)(b0 & 0x0F);
                bool masked = (b1 & 0x80) != 0;
                long len = b1 & 0x7F;
                if (len == 126)
                {
                    if (!await ReadExactAsync(buf, 2, ct)) break;
                    len = (buf[0] << 8) | buf[1];
                }
                else if (len == 127)
                {
                    if (!await ReadExactAsync(buf, 8, ct)) break;
                    len = 0;
                    for (int i = 0; i < 8; i++) len = (len << 8) | buf[i];
                }
                if (len > 4 * 1024 * 1024) break; // sanity: reject absurd frames
                byte[] mask = new byte[4];
                if (masked && !await ReadExactAsync(mask, 4, ct)) break;
                var payload = new byte[len];
                if (len > 0 && !await ReadExactAsync(payload, (int)len, ct)) break;
                if (masked)
                    for (int i = 0; i < payload.Length; i++) payload[i] ^= mask[i & 3];

                LastSeenMs = Environment.TickCount64;
                if (opcode == 0x8) { break; }                       // close
                if (opcode == 0x9) { await SendFrameAsync(0xA, payload); continue; } // ping -> pong
                if (opcode == 0xA) continue;                        // pong
                if (opcode == 0x0) { frag.AddRange(payload); }      // continuation
                else { frag.Clear(); fragOpcode = opcode; frag.AddRange(payload); }
                if (!fin) continue;
                if (fragOpcode == 0x1 || fragOpcode == 0x2)
                {
                    string text = Encoding.UTF8.GetString(frag.ToArray());
                    try { OnMessage?.Invoke(this, text); } catch (Exception ex) { Console.Error.WriteLine($"msg: {ex.Message}"); }
                }
                frag.Clear(); fragOpcode = 0;
            }
        }
        catch (OperationCanceledException) { }
        catch (IOException) { }
        catch (ObjectDisposedException) { }
        finally { Close(); OnClose?.Invoke(this); }
    }

    private async Task<bool> ReadExactAsync(byte[] buf, int count, CancellationToken ct)
    {
        int got = 0;
        while (got < count)
        {
            int n = await Stream.ReadAsync(buf, got, count - got, ct);
            if (n <= 0) return false;
            got += n;
        }
        return true;
    }

    public void Close()
    {
        if (Closed) return;
        Closed = true;
        try { Stream.Close(); } catch { }
        try { Tcp.Close(); } catch { }
    }
}

public sealed class WsServer
{
    private readonly string _bind;
    private readonly int _port;
    private long _connectionCounter;

    public Action<WsConnection, string>? OnMessage;
    public Action<WsConnection>? OnClose;
    public Func<string, (string contentType, string body)>? OnHttp;
    public Action<string>? Log;

    public WsServer(string bind, int port) { _bind = bind; _port = port; }

    public async Task RunAsync(CancellationToken ct)
    {
        IPAddress addr = _bind is "0.0.0.0" or "*" ? IPAddress.Any : IPAddress.Parse(_bind);
        var listener = new TcpListener(addr, _port);
        listener.Server.SetSocketOption(SocketOptionLevel.Socket, SocketOptionName.ReuseAddress, true);
        listener.Start(128);
        Log?.Invoke($"listening on ws://{_bind}:{_port}");
        try
        {
            while (!ct.IsCancellationRequested)
            {
                TcpClient tcp;
                try { tcp = await listener.AcceptTcpClientAsync(ct); }
                catch (OperationCanceledException) { break; }
                _ = Task.Run(async () =>
                {
                    string id = $"c{Interlocked.Increment(ref _connectionCounter)}";
                    var conn = new WsConnection(tcp, id);
                    if (!await HandshakeAsync(conn)) { conn.Close(); return; }
                    conn.OnMessage = (c, m) => OnMessage?.Invoke(c, m);
                    conn.OnClose = c => OnClose?.Invoke(c);
                    await conn.RunReadLoopAsync(ct);
                }, ct);
            }
        }
        finally { listener.Stop(); }
    }

    private async Task<bool> HandshakeAsync(WsConnection conn)
    {
        var buf = new byte[16384];
        int total = 0;
        try
        {
            conn.Stream.ReadTimeout = 5000;
            while (total < buf.Length)
            {
                int n = await conn.Stream.ReadAsync(buf, total, Math.Min(1024, buf.Length - total));
                if (n <= 0) return false;
                total += n;
                int end = FindHeaderEnd(buf, total);
                if (end < 0) continue;
                string head = Encoding.UTF8.GetString(buf, 0, end);
                string key = Header(head, "Sec-WebSocket-Key");
                if (key.Length == 0)
                {
                    // Plain HTTP request - status page / health endpoint.
                    string path = head.Split(' ').Length > 1 ? head.Split(' ')[1] : "/";
                    var (ctBody, body) = OnHttp?.Invoke(path) ?? ("text/plain; charset=utf-8", "Arena FC server\n");
                    var data = Encoding.UTF8.GetBytes(body);
                    string resp = $"HTTP/1.1 200 OK\r\nContent-Type: {ctBody}\r\nContent-Length: {data.Length}\r\nAccess-Control-Allow-Origin: *\r\nConnection: close\r\n\r\n";
                    await conn.Stream.WriteAsync(Encoding.UTF8.GetBytes(resp));
                    await conn.Stream.WriteAsync(data);
                    await conn.Stream.FlushAsync();
                    return false;
                }
                string accept = Convert.ToBase64String(SHA1.HashData(Encoding.UTF8.GetBytes(key + WsConnection.GuidMagic)));
                // RFC 6455: only echo a sub-protocol the client actually offered.
                // Godot's WebSocketPeer offers none by default and rejects an
                // unsolicited "Sec-WebSocket-Protocol" header.
                string offered = Header(head, "Sec-WebSocket-Protocol");
                string protocolLine = offered.Contains("arenafc", StringComparison.OrdinalIgnoreCase)
                    ? "Sec-WebSocket-Protocol: arenafc\r\n" : "";
                string upgrade =
                    "HTTP/1.1 101 Switching Protocols\r\n" +
                    "Upgrade: websocket\r\nConnection: Upgrade\r\n" +
                    $"Sec-WebSocket-Accept: {accept}\r\n" +
                    protocolLine + "\r\n";
                conn.Stream.ReadTimeout = System.Threading.Timeout.Infinite;
                await conn.Stream.WriteAsync(Encoding.UTF8.GetBytes(upgrade));
                await conn.Stream.FlushAsync();
                return true;
            }
        }
        catch (Exception ex) { Log?.Invoke($"handshake failed from {conn.Peer}: {ex.Message}"); }
        return false;
    }

    private static int FindHeaderEnd(byte[] b, int count)
    {
        for (int i = 3; i < count; i++)
            if (b[i - 3] == '\r' && b[i - 2] == '\n' && b[i - 1] == '\r' && b[i] == '\n') return i + 1;
        return -1;
    }

    private static string Header(string head, string key)
    {
        foreach (var line in head.Split("\r\n"))
        {
            int c = line.IndexOf(':');
            if (c > 0 && line[..c].Trim().Equals(key, StringComparison.OrdinalIgnoreCase))
                return line[(c + 1)..].Trim();
        }
        return "";
    }
}
