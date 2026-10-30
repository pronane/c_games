// See netplay_ws.h. Three backends share the message queue at the top.
#include "netplay_ws.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// ---------------------------------------------------------------------------
//  Received-message queue (the Windows backend fills it from its reader thread)
// ---------------------------------------------------------------------------
#define NPWS_QUEUE 256

typedef struct { char *text; int len; } NpWsMsg;

typedef struct {
    NpWsMsg items[NPWS_QUEUE];
    int head, count;
} NpWsQueue;

static void q_push(NpWsQueue *q, const char *text, int len)
{
    if (q->count == NPWS_QUEUE) {            // full: drop the oldest (lockstep NACKs recover it)
        free(q->items[q->head].text);
        q->head = (q->head + 1) % NPWS_QUEUE;
        q->count--;
    }
    char *copy = (char *)malloc((size_t)len + 1);
    if (!copy) return;
    memcpy(copy, text, (size_t)len);
    copy[len] = 0;
    int tail = (q->head + q->count) % NPWS_QUEUE;
    q->items[tail].text = copy;
    q->items[tail].len = len;
    q->count++;
}

static int q_pop(NpWsQueue *q, char **msg)
{
    if (!q->count) return 0;
    NpWsMsg m = q->items[q->head];
    q->head = (q->head + 1) % NPWS_QUEUE;
    q->count--;
    *msg = m.text;
    return m.len;
}

static void q_free(NpWsQueue *q)
{
    char *m;
    while (q_pop(q, &m)) free(m);
}

typedef struct {
    bool secure;
    char host[256];
    int port;
    char path[512];
} NpUrl;

static bool parse_url(const char *url, NpUrl *u)
{
    memset(u, 0, sizeof(*u));
    const char *p;
    if (strncmp(url, "wss://", 6) == 0) { u->secure = true; p = url + 6; u->port = 443; }
    else if (strncmp(url, "ws://", 5) == 0) { p = url + 5; u->port = 80; }
    else if (strncmp(url, "https://", 8) == 0) { u->secure = true; p = url + 8; u->port = 443; }
    else if (strncmp(url, "http://", 7) == 0) { p = url + 7; u->port = 80; }
    else return false;
    const char *slash = strchr(p, '/');
    size_t hostLen = slash ? (size_t)(slash - p) : strlen(p);
    const char *colon = memchr(p, ':', hostLen);
    size_t nameLen = colon ? (size_t)(colon - p) : hostLen;
    if (nameLen == 0 || nameLen >= sizeof(u->host)) return false;
    memcpy(u->host, p, nameLen);
    if (colon) u->port = atoi(colon + 1);
    snprintf(u->path, sizeof(u->path), "%s", slash ? slash : "/");
    return u->port > 0;
}

#if defined(__EMSCRIPTEN__)
// ===========================================================================
//  Emscripten: the browser WebSocket
// ===========================================================================
#include <emscripten/websocket.h>

struct NpWs {
    EMSCRIPTEN_WEBSOCKET_T sock;
    NpWsState state;
    NpWsQueue q;
    char error[128];
};

static EM_BOOL on_open(int type, const EmscriptenWebSocketOpenEvent *e, void *ud)
{
    (void)type; (void)e;
    ((NpWs *)ud)->state = NPWS_OPEN;
    return EM_TRUE;
}

static EM_BOOL on_message(int type, const EmscriptenWebSocketMessageEvent *e, void *ud)
{
    (void)type;
    if (e->isText && e->numBytes > 0) q_push(&((NpWs *)ud)->q, (const char *)e->data, (int)e->numBytes - 1);
    return EM_TRUE;
}

static EM_BOOL on_close(int type, const EmscriptenWebSocketCloseEvent *e, void *ud)
{
    (void)type;
    NpWs *ws = (NpWs *)ud;
    if (ws->state != NPWS_CLOSED && !ws->error[0]) snprintf(ws->error, sizeof(ws->error), "closed (%d)", e->code);
    ws->state = NPWS_CLOSED;
    return EM_TRUE;
}

static EM_BOOL on_error(int type, const EmscriptenWebSocketErrorEvent *e, void *ud)
{
    (void)type; (void)e;
    NpWs *ws = (NpWs *)ud;
    snprintf(ws->error, sizeof(ws->error), "connection failed");
    ws->state = NPWS_CLOSED;
    return EM_TRUE;
}

NpWs *NpWs_Open(const char *url)
{
    NpUrl u;
    if (!parse_url(url, &u)) return NULL;
    NpWs *ws = (NpWs *)calloc(1, sizeof(NpWs));
    EmscriptenWebSocketCreateAttributes attr;
    emscripten_websocket_init_create_attributes(&attr);
    attr.url = url;
    ws->sock = emscripten_websocket_new(&attr);
    if (ws->sock <= 0) {
        ws->state = NPWS_CLOSED;
        snprintf(ws->error, sizeof(ws->error), "WebSocket not supported");
        return ws;
    }
    emscripten_websocket_set_onopen_callback(ws->sock, ws, on_open);
    emscripten_websocket_set_onmessage_callback(ws->sock, ws, on_message);
    emscripten_websocket_set_onclose_callback(ws->sock, ws, on_close);
    emscripten_websocket_set_onerror_callback(ws->sock, ws, on_error);
    return ws;
}

NpWsState NpWs_Poll(NpWs *ws) { return ws->state; }

bool NpWs_Send(NpWs *ws, const char *text, int len)
{
    (void)len;   // text is NUL-terminated by netplay.c
    if (ws->state != NPWS_OPEN) return false;
    return emscripten_websocket_send_utf8_text(ws->sock, text) == EMSCRIPTEN_RESULT_SUCCESS;
}

int NpWs_Recv(NpWs *ws, char **msg) { return q_pop(&ws->q, msg); }
const char *NpWs_Error(const NpWs *ws) { return ws->error; }

void NpWs_Close(NpWs *ws)
{
    if (!ws) return;
    if (ws->sock > 0) {
        emscripten_websocket_close(ws->sock, 1000, "bye");
        emscripten_websocket_delete(ws->sock);
    }
    q_free(&ws->q);
    free(ws);
}

#elif defined(_WIN32)
// ===========================================================================
//  Windows: WinHTTP's WebSocket client on a reader thread (ws:// and wss://)
// ===========================================================================
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <winhttp.h>

struct NpWs {
    NpUrl url;
    HINTERNET session, connect, sock;
    HANDLE thread;
    CRITICAL_SECTION lock;
    volatile LONG state;     // NpWsState
    volatile LONG closing;
    NpWsQueue q;
    char error[128];
};

static void set_error(NpWs *ws, const char *what)
{
    EnterCriticalSection(&ws->lock);
    if (!ws->error[0]) snprintf(ws->error, sizeof(ws->error), "%s (error %lu)", what, GetLastError());
    LeaveCriticalSection(&ws->lock);
}

static DWORD WINAPI reader(LPVOID arg)
{
    NpWs *ws = (NpWs *)arg;
    wchar_t host[256], path[512];
    MultiByteToWideChar(CP_UTF8, 0, ws->url.host, -1, host, 256);
    MultiByteToWideChar(CP_UTF8, 0, ws->url.path, -1, path, 512);

    ws->session = WinHttpOpen(L"c_games-netplay/1", WINHTTP_ACCESS_TYPE_DEFAULT_PROXY,
                              WINHTTP_NO_PROXY_NAME, WINHTTP_NO_PROXY_BYPASS, 0);
    if (!ws->session) { set_error(ws, "WinHttpOpen"); goto done; }
    WinHttpSetTimeouts(ws->session, 8000, 8000, 8000, 0);
    ws->connect = WinHttpConnect(ws->session, host, (INTERNET_PORT)ws->url.port, 0);
    if (!ws->connect) { set_error(ws, "can't reach server"); goto done; }
    HINTERNET req = WinHttpOpenRequest(ws->connect, L"GET", path, NULL, WINHTTP_NO_REFERER,
                                       WINHTTP_DEFAULT_ACCEPT_TYPES, ws->url.secure ? WINHTTP_FLAG_SECURE : 0);
    if (!req) { set_error(ws, "WinHttpOpenRequest"); goto done; }
    if (!WinHttpSetOption(req, WINHTTP_OPTION_UPGRADE_TO_WEB_SOCKET, NULL, 0) ||
        !WinHttpSendRequest(req, WINHTTP_NO_ADDITIONAL_HEADERS, 0, NULL, 0, 0, 0) ||
        !WinHttpReceiveResponse(req, NULL)) {
        set_error(ws, "can't reach server");
        WinHttpCloseHandle(req);
        goto done;
    }
    ws->sock = WinHttpWebSocketCompleteUpgrade(req, 0);
    WinHttpCloseHandle(req);
    if (!ws->sock) { set_error(ws, "server refused the WebSocket"); goto done; }
    InterlockedExchange(&ws->state, NPWS_OPEN);

    {
        size_t cap = 16384, len = 0;
        char *buf = (char *)malloc(cap);
        while (!ws->closing) {
            DWORD got = 0;
            WINHTTP_WEB_SOCKET_BUFFER_TYPE type;
            if (len == cap) { cap *= 2; buf = (char *)realloc(buf, cap); }
            DWORD rc = WinHttpWebSocketReceive(ws->sock, buf + len, (DWORD)(cap - len), &got, &type);
            if (rc != NO_ERROR) { SetLastError(rc); set_error(ws, "connection lost"); break; }
            if (type == WINHTTP_WEB_SOCKET_CLOSE_BUFFER_TYPE) { set_error(ws, "server closed"); break; }
            len += got;
            if (type == WINHTTP_WEB_SOCKET_UTF8_MESSAGE_BUFFER_TYPE) {
                EnterCriticalSection(&ws->lock);
                q_push(&ws->q, buf, (int)len);
                LeaveCriticalSection(&ws->lock);
                len = 0;
            } else if (type == WINHTTP_WEB_SOCKET_BINARY_MESSAGE_BUFFER_TYPE) {
                len = 0;                                  // not used by the protocol
            }
            // *_FRAGMENT_BUFFER_TYPE: keep appending
        }
        free(buf);
    }
done:
    InterlockedExchange(&ws->state, NPWS_CLOSED);
    return 0;
}

NpWs *NpWs_Open(const char *url)
{
    NpWs *ws = (NpWs *)calloc(1, sizeof(NpWs));
    if (!parse_url(url, &ws->url)) { free(ws); return NULL; }
    InitializeCriticalSection(&ws->lock);
    ws->state = NPWS_CONNECTING;
    ws->thread = CreateThread(NULL, 0, reader, ws, 0, NULL);
    if (!ws->thread) { ws->state = NPWS_CLOSED; snprintf(ws->error, sizeof(ws->error), "CreateThread failed"); }
    return ws;
}

NpWsState NpWs_Poll(NpWs *ws) { return (NpWsState)ws->state; }

bool NpWs_Send(NpWs *ws, const char *text, int len)
{
    if (ws->state != NPWS_OPEN) return false;
    return WinHttpWebSocketSend(ws->sock, WINHTTP_WEB_SOCKET_UTF8_MESSAGE_BUFFER_TYPE,
                                (PVOID)text, (DWORD)len) == NO_ERROR;
}

int NpWs_Recv(NpWs *ws, char **msg)
{
    EnterCriticalSection(&ws->lock);
    int n = q_pop(&ws->q, msg);
    LeaveCriticalSection(&ws->lock);
    return n;
}

const char *NpWs_Error(const NpWs *ws) { return ws->error; }

void NpWs_Close(NpWs *ws)
{
    if (!ws) return;
    InterlockedExchange(&ws->closing, 1);
    if (ws->sock) WinHttpWebSocketClose(ws->sock, WINHTTP_WEB_SOCKET_SUCCESS_CLOSE_STATUS, NULL, 0);
    // Closing the handles unblocks a pending receive or connect.
    if (ws->sock) WinHttpCloseHandle(ws->sock);
    if (ws->connect) WinHttpCloseHandle(ws->connect);
    if (ws->session) WinHttpCloseHandle(ws->session);
    if (ws->thread) {
        WaitForSingleObject(ws->thread, 3000);
        CloseHandle(ws->thread);
    }
    q_free(&ws->q);
    DeleteCriticalSection(&ws->lock);
    free(ws);
}

#else
// ===========================================================================
//  POSIX sockets: ws://, plus wss:// when built with NETPLAY_OPENSSL
// ===========================================================================
#include <errno.h>
#include <fcntl.h>
#include <netdb.h>
#include <poll.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <time.h>
#include <unistd.h>
#ifdef NETPLAY_OPENSSL
#include <openssl/err.h>
#include <openssl/ssl.h>
#endif

enum { ST_TCP, ST_TLS, ST_UPGRADE, ST_OPEN, ST_CLOSED };

struct NpWs {
    NpUrl url;
    int fd;
    int st;
    char error[128];
    char *in;            // raw bytes from the socket
    size_t inLen, inCap;
    char *frag;          // continuation frames of a fragmented text message
    size_t fragLen;
    NpWsQueue q;
    double deadline;
#ifdef NETPLAY_OPENSSL
    SSL_CTX *ctx;
    SSL *ssl;
#endif
};

static double now_s(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + ts.tv_nsec / 1e9;
}

static void fail(NpWs *ws, const char *why)
{
    if (!ws->error[0]) snprintf(ws->error, sizeof(ws->error), "%s", why);
    ws->st = ST_CLOSED;
}

// >0 bytes, 0 would block, -1 closed/error
static int raw_read(NpWs *ws, char *buf, int cap)
{
#ifdef NETPLAY_OPENSSL
    if (ws->ssl) {
        int n = SSL_read(ws->ssl, buf, cap);
        if (n > 0) return n;
        int e = SSL_get_error(ws->ssl, n);
        return (e == SSL_ERROR_WANT_READ || e == SSL_ERROR_WANT_WRITE) ? 0 : -1;
    }
#endif
    ssize_t n = recv(ws->fd, buf, (size_t)cap, 0);
    if (n > 0) return (int)n;
    if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR)) return 0;
    return -1;
}

// Writes everything (messages are small); waits for the socket up to 2 s.
static bool raw_write(NpWs *ws, const char *buf, size_t len)
{
    double until = now_s() + 2.0;
    while (len > 0) {
        long n;
#ifdef NETPLAY_OPENSSL
        if (ws->ssl) {
            n = SSL_write(ws->ssl, buf, (int)len);
            if (n <= 0) {
                int e = SSL_get_error(ws->ssl, (int)n);
                if (e != SSL_ERROR_WANT_READ && e != SSL_ERROR_WANT_WRITE) return false;
                n = 0;
            }
        } else
#endif
        {
            n = send(ws->fd, buf, len, MSG_NOSIGNAL);
            if (n < 0) {
                if (errno != EAGAIN && errno != EWOULDBLOCK && errno != EINTR) return false;
                n = 0;
            }
        }
        if (n == 0) {
            if (now_s() > until) return false;
            struct pollfd p = { ws->fd, POLLOUT, 0 };
            poll(&p, 1, 20);
            continue;
        }
        buf += n;
        len -= (size_t)n;
    }
    return true;
}

static void send_frame(NpWs *ws, int opcode, const char *data, size_t len)
{
    unsigned char hdr[14];
    size_t h = 0;
    hdr[h++] = (unsigned char)(0x80 | opcode);
    if (len < 126) hdr[h++] = (unsigned char)(0x80 | len);
    else if (len < 65536) { hdr[h++] = 0x80 | 126; hdr[h++] = (unsigned char)(len >> 8); hdr[h++] = (unsigned char)len; }
    else {
        hdr[h++] = 0x80 | 127;
        for (int i = 7; i >= 0; i--) hdr[h++] = (unsigned char)((unsigned long long)len >> (8 * i));
    }
    unsigned char mask[4];
    for (int i = 0; i < 4; i++) mask[i] = (unsigned char)(rand() & 0xff);
    memcpy(hdr + h, mask, 4);
    h += 4;
    char stackBuf[2048];
    char *out = len + h <= sizeof(stackBuf) ? stackBuf : (char *)malloc(len + h);
    memcpy(out, hdr, h);
    for (size_t i = 0; i < len; i++) out[h + i] = (char)(data[i] ^ mask[i & 3]);
    if (!raw_write(ws, out, len + h)) fail(ws, "connection lost");
    if (out != stackBuf) free(out);
}

static void need_in(NpWs *ws, size_t extra)
{
    if (ws->inLen + extra <= ws->inCap) return;
    while (ws->inLen + extra > ws->inCap) ws->inCap = ws->inCap ? ws->inCap * 2 : 16384;
    ws->in = (char *)realloc(ws->in, ws->inCap);
}

static void consume(NpWs *ws, size_t n)
{
    memmove(ws->in, ws->in + n, ws->inLen - n);
    ws->inLen -= n;
}

static void parse_frames(NpWs *ws)
{
    for (;;) {
        unsigned char *b = (unsigned char *)ws->in;
        if (ws->inLen < 2) return;
        bool fin = b[0] & 0x80;
        int op = b[0] & 0x0f;
        bool masked = b[1] & 0x80;
        unsigned long long len = b[1] & 0x7f;
        size_t h = 2;
        if (len == 126) {
            if (ws->inLen < 4) return;
            len = ((unsigned)b[2] << 8) | b[3];
            h = 4;
        } else if (len == 127) {
            if (ws->inLen < 10) return;
            len = 0;
            for (int i = 0; i < 8; i++) len = (len << 8) | b[2 + i];
            h = 10;
        }
        if (len > (8u << 20)) { fail(ws, "message too big"); return; }
        size_t maskAt = h;
        if (masked) h += 4;
        if (ws->inLen < h + len) return;
        char *payload = ws->in + h;
        if (masked) for (size_t i = 0; i < len; i++) payload[i] ^= ws->in[maskAt + (i & 3)];

        if (op == 0x1 || op == 0x0) {            // text / continuation
            if (op == 0x1 && fin) q_push(&ws->q, payload, (int)len);
            else {
                ws->frag = (char *)realloc(ws->frag, ws->fragLen + len + 1);
                memcpy(ws->frag + ws->fragLen, payload, len);
                ws->fragLen += len;
                if (fin) { q_push(&ws->q, ws->frag, (int)ws->fragLen); ws->fragLen = 0; }
            }
        } else if (op == 0x8) {                  // close
            send_frame(ws, 0x8, payload, len >= 2 ? 2 : 0);
            fail(ws, "server closed");
            return;
        } else if (op == 0x9) {                  // ping -> pong
            send_frame(ws, 0xA, payload, (size_t)len);
        }
        consume(ws, h + (size_t)len);
    }
}

static void pump_read(NpWs *ws)
{
    for (;;) {
        need_in(ws, 16384);
        int n = raw_read(ws, ws->in + ws->inLen, 16384);
        if (n == 0) return;
        if (n < 0) { fail(ws, "connection lost"); return; }
        ws->inLen += (size_t)n;
    }
}

static void send_upgrade(NpWs *ws)
{
    static const char b64[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    char key[25];
    for (int i = 0; i < 22; i++) key[i] = b64[rand() % 64];
    key[22] = '='; key[23] = '='; key[24] = 0;
    char req[1024];
    int n = snprintf(req, sizeof(req),
                     "GET %s HTTP/1.1\r\nHost: %s:%d\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                     "Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\nUser-Agent: c_games-netplay/1\r\n\r\n",
                     ws->url.path, ws->url.host, ws->url.port, key);
    if (!raw_write(ws, req, (size_t)n)) fail(ws, "connection lost");
    ws->st = ST_UPGRADE;
}

NpWs *NpWs_Open(const char *url)
{
    NpWs *ws = (NpWs *)calloc(1, sizeof(NpWs));
    if (!parse_url(url, &ws->url)) { free(ws); return NULL; }
    ws->fd = -1;
    ws->deadline = now_s() + 10.0;
#ifndef NETPLAY_OPENSSL
    if (ws->url.secure) { fail(ws, "wss:// needs a build with NETPLAY_OPENSSL"); return ws; }
#endif
    char port[16];
    snprintf(port, sizeof(port), "%d", ws->url.port);
    struct addrinfo hints, *res = NULL;
    memset(&hints, 0, sizeof(hints));
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;
    if (getaddrinfo(ws->url.host, port, &hints, &res) != 0 || !res) { fail(ws, "can't find server"); return ws; }
    ws->fd = socket(res->ai_family, res->ai_socktype, res->ai_protocol);
    if (ws->fd < 0) { freeaddrinfo(res); fail(ws, "socket failed"); return ws; }
    fcntl(ws->fd, F_SETFL, fcntl(ws->fd, F_GETFL, 0) | O_NONBLOCK);
    int rc = connect(ws->fd, res->ai_addr, res->ai_addrlen);
    freeaddrinfo(res);
    if (rc != 0 && errno != EINPROGRESS) { fail(ws, "can't reach server"); return ws; }
    ws->st = ST_TCP;
    return ws;
}

NpWsState NpWs_Poll(NpWs *ws)
{
    if (ws->st == ST_CLOSED) return NPWS_CLOSED;
    if (ws->st != ST_OPEN && now_s() > ws->deadline) { fail(ws, "timed out"); return NPWS_CLOSED; }

    if (ws->st == ST_TCP) {
        struct pollfd p = { ws->fd, POLLOUT, 0 };
        if (poll(&p, 1, 0) <= 0) return NPWS_CONNECTING;
        int err = 0;
        socklen_t el = sizeof(err);
        getsockopt(ws->fd, SOL_SOCKET, SO_ERROR, &err, &el);
        if (err) { fail(ws, "can't reach server"); return NPWS_CLOSED; }
#ifdef NETPLAY_OPENSSL
        if (ws->url.secure) {
            ws->ctx = SSL_CTX_new(TLS_client_method());
            SSL_CTX_set_default_verify_paths(ws->ctx);
            SSL_CTX_set_verify(ws->ctx, SSL_VERIFY_PEER, NULL);
            ws->ssl = SSL_new(ws->ctx);
            SSL_set_tlsext_host_name(ws->ssl, ws->url.host);
            SSL_set1_host(ws->ssl, ws->url.host);
            SSL_set_fd(ws->ssl, ws->fd);
            ws->st = ST_TLS;
        } else
#endif
            send_upgrade(ws);
    }
#ifdef NETPLAY_OPENSSL
    if (ws->st == ST_TLS) {
        int r = SSL_connect(ws->ssl);
        if (r == 1) send_upgrade(ws);
        else {
            int e = SSL_get_error(ws->ssl, r);
            if (e != SSL_ERROR_WANT_READ && e != SSL_ERROR_WANT_WRITE) { fail(ws, "TLS handshake failed"); return NPWS_CLOSED; }
            return NPWS_CONNECTING;
        }
    }
#endif
    if (ws->st == ST_UPGRADE) {
        pump_read(ws);
        if (ws->st == ST_CLOSED) return NPWS_CLOSED;
        need_in(ws, 1);
        ws->in[ws->inLen] = 0;
        char *end = strstr(ws->in, "\r\n\r\n");
        if (!end) return NPWS_CONNECTING;
        if (strncmp(ws->in, "HTTP/1.1 101", 12) != 0) { fail(ws, "server refused the WebSocket"); return NPWS_CLOSED; }
        consume(ws, (size_t)(end + 4 - ws->in));
        ws->st = ST_OPEN;
    }
    if (ws->st == ST_OPEN) {
        pump_read(ws);
        parse_frames(ws);
    }
    return ws->st == ST_OPEN ? NPWS_OPEN : ws->st == ST_CLOSED ? NPWS_CLOSED : NPWS_CONNECTING;
}

bool NpWs_Send(NpWs *ws, const char *text, int len)
{
    if (ws->st != ST_OPEN) return false;
    send_frame(ws, 0x1, text, (size_t)len);
    return ws->st == ST_OPEN;
}

int NpWs_Recv(NpWs *ws, char **msg) { return q_pop(&ws->q, msg); }
const char *NpWs_Error(const NpWs *ws) { return ws->error; }

void NpWs_Close(NpWs *ws)
{
    if (!ws) return;
    if (ws->st == ST_OPEN) send_frame(ws, 0x8, "\x03\xe8", 2);
#ifdef NETPLAY_OPENSSL
    if (ws->ssl) SSL_free(ws->ssl);
    if (ws->ctx) SSL_CTX_free(ws->ctx);
#endif
    if (ws->fd >= 0) close(ws->fd);
    q_free(&ws->q);
    free(ws->in);
    free(ws->frag);
    free(ws);
}
#endif
