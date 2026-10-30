// See netplay.h. Protocol: shared/netplay/README.md.
#include "netplay.h"
#include "netplay_ws.h"

#include <math.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#if defined(__EMSCRIPTEN__)
#include <emscripten.h>
static double now_ms(void) { return emscripten_get_now(); }
#elif defined(_WIN32)
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
static double now_ms(void)
{
    static LARGE_INTEGER freq;
    LARGE_INTEGER t;
    if (!freq.QuadPart) QueryPerformanceFrequency(&freq);
    QueryPerformanceCounter(&t);
    return (double)t.QuadPart * 1000.0 / (double)freq.QuadPart;
}
#else
#include <time.h>
static double now_ms(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec * 1000.0 + ts.tv_nsec / 1e6;
}
#endif

#define FRAME_MS (1000.0 / 60.0)
#define RESYNC_BEHIND 6
#define TAIL_FRAMES 32
#define SEND_EVERY_MS 50.0
#define HB_EVERY_MS 250.0
#define PING_EVERY_MS 500.0
#define SLOW_MS 1000.0
#define LOST_MS 9000.0
#define WAKE_MS 90000.0
#define OUTBOX 16
#define EVQ 32
#define HASH_SLOTS (NP_MAX_FRAMES / NP_HASH_EVERY + 1)

struct Netplay {
    char url[512];
    char userId[65];
    NpWs *ws;
    bool wantOnline;          // keep (re)connecting
    double connectStart, nextTry, backoff;
    char *outbox[OUTBOX];
    int outCount;

    NpState st;
    NpEvent ev[EVQ];
    int evHead, evCount;

    int epoch;
    int readySeq;
    char startId[40];
    uint32_t seed;
    double lastPing;
    int samples;
    double serverOffset;      // server ms - local ms

    // match
    bool match, over, resuming;
    double origin;            // local ms of sim frame 0
    int resumeTarget;
    uint32_t resumeHash;
    uint16_t *bits[2];
    unsigned char *have[2];
    int localMax, peerAck, remoteContig, remoteMax;
    uint32_t lastHash;
    uint32_t hashMine[HASH_SLOTS], hashTheirs[HASH_SLOTS];
    unsigned char hashFlags[HASH_SLOTS];   // 1 mine, 2 theirs
    double lastSend, lastHb, lastPeerRx, waitSince, holdUntil, lastNackAt;
    int lastNackFrom;
};

// ---------------------------------------------------------------------------
//  Tiny JSON reader: enough for the relay's flat messages
// ---------------------------------------------------------------------------
static const char *ws_skip(const char *p) { while (*p == ' ' || *p == '\t' || *p == '\n' || *p == '\r') p++; return p; }

static const char *skip_value(const char *p)
{
    p = ws_skip(p);
    if (*p == '"') {
        for (p++; *p && *p != '"'; p++) if (*p == '\\' && p[1]) p++;
        return *p ? p + 1 : p;
    }
    if (*p == '{' || *p == '[') {
        int depth = 0;
        for (; *p; p++) {
            if (*p == '"') { p = skip_value(p) - 1; continue; }
            if (*p == '{' || *p == '[') depth++;
            else if ((*p == '}' || *p == ']') && --depth == 0) return p + 1;
        }
        return p;
    }
    while (*p && *p != ',' && *p != '}' && *p != ']') p++;
    return p;
}

// value of a top-level key of the object at `obj`, or NULL
static const char *jfind(const char *obj, const char *key)
{
    if (!obj) return NULL;
    const char *p = ws_skip(obj);
    if (*p != '{') return NULL;
    p++;
    size_t klen = strlen(key);
    for (;;) {
        p = ws_skip(p);
        if (*p != '"') return NULL;
        const char *k = p + 1;
        const char *kend = skip_value(p) - 1;
        p = ws_skip(kend + 1);
        if (*p != ':') return NULL;
        p = ws_skip(p + 1);
        if ((size_t)(kend - k) == klen && memcmp(k, key, klen) == 0) return p;
        p = ws_skip(skip_value(p));
        if (*p != ',') return NULL;
        p++;
    }
}

static bool jnum(const char *obj, const char *key, double *out)
{
    const char *v = jfind(obj, key);
    if (!v || !(*v == '-' || (*v >= '0' && *v <= '9'))) return false;
    *out = strtod(v, NULL);
    return true;
}

static double jnumd(const char *obj, const char *key, double def)
{
    double d;
    return jnum(obj, key, &d) ? d : def;
}

static bool jstr(const char *obj, const char *key, char *out, int cap)
{
    const char *v = jfind(obj, key);
    if (!v || *v != '"') { if (cap) out[0] = 0; return false; }
    int n = 0;
    for (v++; *v && *v != '"'; v++) {
        char c = *v;
        if (c == '\\' && v[1]) { v++; c = *v == 'n' ? ' ' : *v; if (*v == 'u') { v += 4; c = '?'; } }
        if (n < cap - 1) out[n++] = c;
    }
    out[n] = 0;
    return true;
}

static bool jtrue(const char *obj, const char *key)
{
    const char *v = jfind(obj, key);
    return v && strncmp(v, "true", 4) == 0;
}

// ---------------------------------------------------------------------------
//  Plumbing
// ---------------------------------------------------------------------------
static NpEvent *push_event(Netplay *np, NpEventType type)
{
    if (np->evCount == EVQ) { np->evHead = (np->evHead + 1) % EVQ; np->evCount--; }
    NpEvent *e = &np->ev[(np->evHead + np->evCount++) % EVQ];
    memset(e, 0, sizeof(*e));
    e->type = type;
    e->slot = np->st.slot;
    e->winner = -1;
    e->seed = np->seed;
    e->delay = np->st.delay;
    snprintf(e->room, sizeof(e->room), "%s", np->st.room);
    memcpy(e->picks, np->st.picks, sizeof(e->picks));
    return e;
}

static void status(Netplay *np, const char *fmt, ...)
{
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(np->st.status, sizeof(np->st.status), fmt, ap);
    va_end(ap);
}

static void clean_token(char *dst, int cap, const char *src)
{
    int n = 0;
    for (; src && *src && n < cap - 1; src++) {
        char c = *src;
        if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') ||
            c == '-' || c == '_' || c == ':' || c == '.') dst[n++] = c;
    }
    dst[n] = 0;
}

static bool is_open(Netplay *np) { return np->ws && NpWs_Poll(np->ws) == NPWS_OPEN; }

// NETPLAY_DEBUG=1 prints lobby traffic, =2 also inputs / hashes
static int debug_level(void)
{
    static int level = -1;
    if (level < 0) level = getenv("NETPLAY_DEBUG") ? atoi(getenv("NETPLAY_DEBUG")) : 0;
    return level;
}

static void trace(const char *dir, const char *msg)
{
    int lv = debug_level();
    if (!lv) return;
    bool chatty = strstr(msg, "\"input\"") || strstr(msg, "\"hash\"") || strstr(msg, "\"hb\"") ||
                  strstr(msg, "\"ping\"") || strstr(msg, "\"pong\"");
    if (chatty && lv < 2) return;
    fprintf(stderr, "[netplay] %s %.300s\n", dir, msg);
}

// Lobby commands wait in the outbox while the socket (re)opens; game data does not.
static void sendf(Netplay *np, bool queueIfClosed, const char *fmt, ...)
{
    char buf[4096];
    va_list ap;
    va_start(ap, fmt);
    int n = vsnprintf(buf, sizeof(buf), fmt, ap);
    va_end(ap);
    if (n <= 0 || n >= (int)sizeof(buf)) return;
    if (is_open(np)) {
        trace(">", buf);
        NpWs_Send(np->ws, buf, n);
        return;
    }
    if (!queueIfClosed) return;
    if (np->outCount == OUTBOX) { free(np->outbox[0]); memmove(np->outbox, np->outbox + 1, sizeof(char *) * (OUTBOX - 1)); np->outCount--; }
    np->outbox[np->outCount++] = strdup(buf);
}

static void read_room_fields(Netplay *np, const char *m)
{
    char room[16];
    if (jstr(m, "room", room, sizeof(room))) clean_token(np->st.room, sizeof(np->st.room), room);
    double d;
    if (jnum(m, "slot", &d) && (d == 0 || d == 1)) np->st.slot = (int)d;
    if (jnum(m, "epoch", &d)) np->epoch = (int)d;
    const char *picks = jfind(m, "picks");
    if (picks && *picks == '{') {
        jstr(picks, "0", np->st.picks[0], sizeof(np->st.picks[0]));
        jstr(picks, "1", np->st.picks[1], sizeof(np->st.picks[1]));
    }
    const char *ready = jfind(m, "ready");
    if (ready && *ready == '{') { np->st.ready[0] = jtrue(ready, "0"); np->st.ready[1] = jtrue(ready, "1"); }
    const char *occ = jfind(m, "occupied");
    if (occ && *occ == '{') { np->st.occupied[0] = jtrue(occ, "0"); np->st.occupied[1] = jtrue(occ, "1"); }
}

static void free_match(Netplay *np)
{
    for (int s = 0; s < 2; s++) {
        free(np->bits[s]); np->bits[s] = NULL;
        free(np->have[s]); np->have[s] = NULL;
    }
    np->match = false;
    np->resuming = false;
    np->st.peerHeld = false;
}

static void reset_match(Netplay *np, int delay)
{
    free_match(np);
    for (int s = 0; s < 2; s++) {
        np->bits[s] = (uint16_t *)calloc(NP_MAX_FRAMES, sizeof(uint16_t));
        np->have[s] = (unsigned char *)calloc(NP_MAX_FRAMES, 1);
    }
    memset(np->hashFlags, 0, sizeof(np->hashFlags));
    np->match = true;
    np->over = false;
    np->resumeTarget = 0;
    np->st.delay = delay < 1 ? 1 : delay;
    np->st.frame = 0;
    np->st.waiting = np->st.slow = false;
    np->localMax = np->st.delay - 1;
    np->peerAck = -1;
    np->remoteContig = np->st.delay - 1;   // frames below the delay are neutral on both sides
    np->remoteMax = np->remoteContig;
    np->lastPeerRx = np->lastSend = np->lastHb = now_ms();
    np->waitSince = 0;
    np->lastNackFrom = -1;
}

static void end_match(Netplay *np, int winner, const char *text)
{
    bool was = np->match && !np->over;
    np->over = true;
    np->st.phase = np->st.room[0] ? NP_LOBBY : NP_IDLE;
    np->st.ready[0] = np->st.ready[1] = false;
    if (!was) return;
    NpEvent *e = push_event(np, NP_EV_MATCH_END);
    e->winner = winner;
    snprintf(e->text, sizeof(e->text), "%s", text ? text : "");
}

// ---------------------------------------------------------------------------
//  Inputs on the wire: {"t":"input","ack":A,"base":B,"bits":[...]}
// ---------------------------------------------------------------------------
static void send_range(Netplay *np, int from, int to)
{
    int me = np->st.slot;
    if (from < np->st.delay) from = np->st.delay;
    if (to > np->localMax) to = np->localMax;
    if (to - from + 1 > 90) from = to - 89;
    if (from > to || !is_open(np)) return;
    char buf[1200];
    int n = snprintf(buf, sizeof(buf), "{\"t\":\"input\",\"ack\":%d,\"epoch\":%d,\"base\":%d,\"bits\":[",
                     np->remoteContig, np->epoch, from);
    for (int f = from; f <= to; f++)
        n += snprintf(buf + n, sizeof(buf) - n, "%s%u", f > from ? "," : "", (unsigned)np->bits[me][f]);
    n += snprintf(buf + n, sizeof(buf) - n, "]}");
    NpWs_Send(np->ws, buf, n);
    np->lastSend = now_ms();
}

static void send_tail(Netplay *np)
{
    int from = np->peerAck + 1;
    if (np->localMax - from + 1 > TAIL_FRAMES) from = np->localMax - TAIL_FRAMES + 1;
    send_range(np, from, np->localMax);
}

static void store_remote(Netplay *np, int from, int frame, uint16_t bits)
{
    if (frame < 0 || frame >= NP_MAX_FRAMES || from == np->st.slot) return;
    if (!np->have[from][frame]) { np->have[from][frame] = 1; np->bits[from][frame] = bits; }
    if (frame > np->remoteMax) np->remoteMax = frame;
}

static void on_input(Netplay *np, const char *m)
{
    if (!np->match || np->over) return;
    double d;
    if (jnum(m, "epoch", &d) && (int)d != np->epoch) return;
    int from = np->st.slot ^ 1;
    if (jnum(m, "from", &d) && (d == 0 || d == 1)) from = (int)d;
    if (from == np->st.slot) return;
    np->lastPeerRx = now_ms();
    if (jnum(m, "ack", &d) && (int)d > np->peerAck) np->peerAck = (int)d;
    int lowest = -1;
    if (jnum(m, "base", &d)) {
        int base = (int)d;
        const char *a = jfind(m, "bits");
        if (a && *a == '[') {
            int i = 0;
            for (const char *p = ws_skip(a + 1); *p && *p != ']'; i++) {
                store_remote(np, from, base + i, (uint16_t)strtoul(p, NULL, 10));
                p = ws_skip(skip_value(p));
                if (*p == ',') p = ws_skip(p + 1);
            }
            if (i) lowest = base;
        }
    }
    const char *batch = jfind(m, "batch");
    if (batch && *batch == '[') {
        for (const char *p = ws_skip(batch + 1); *p == '{'; ) {
            double f, b;
            if (jnum(p, "frame", &f) && jnum(p, "b", &b)) {
                store_remote(np, from, (int)f, (uint16_t)b);
                if (lowest < 0 || (int)f < lowest) lowest = (int)f;
            }
            p = ws_skip(skip_value(p));
            if (*p == ',') p = ws_skip(p + 1);
        }
    }
    // a hole before what just arrived: ask for it now instead of waiting for the next tail
    int gapFrom = np->remoteContig + 1;
    if (lowest > gapFrom) {
        double t = now_ms();
        if (gapFrom != np->lastNackFrom || t - np->lastNackAt > 80) {
            np->lastNackFrom = gapFrom;
            np->lastNackAt = t;
            int to = lowest - 1 < gapFrom + 40 ? lowest - 1 : gapFrom + 40;
            sendf(np, false, "{\"t\":\"nack\",\"fromFrame\":%d,\"toFrame\":%d}", gapFrom, to);
        }
    }
    while (np->remoteContig + 1 < NP_MAX_FRAMES && np->have[from][np->remoteContig + 1]) np->remoteContig++;
}

static void compare_hash(Netplay *np, int frame)
{
    int i = frame / NP_HASH_EVERY;
    if (i <= 0 || i >= HASH_SLOTS || np->hashFlags[i] != 3) return;
    if (np->hashMine[i] != np->hashTheirs[i]) {
        sendf(np, false, "{\"t\":\"give_up\"}");
        char text[96];
        snprintf(text, sizeof(text), "Desync at frame %d - no contest", frame);
        end_match(np, -1, text);
    }
}

static void decode_hist(Netplay *np, int slot, const char *b64, int count)
{
    static const char *tbl = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    unsigned acc = 0;
    int bitsHeld = 0, byteIx = 0;
    unsigned char lo = 0;
    for (const char *p = b64; *p && *p != '"'; p++) {
        const char *c = strchr(tbl, *p);
        if (!c || *p == '=') continue;
        acc = (acc << 6) | (unsigned)(c - tbl);
        bitsHeld += 6;
        if (bitsHeld >= 8) {
            bitsHeld -= 8;
            unsigned char byte = (unsigned char)(acc >> bitsHeld);
            if (byteIx & 1) {
                int f = byteIx >> 1;
                if (f < count && f < NP_MAX_FRAMES) { np->bits[slot][f] = (uint16_t)(lo | (byte << 8)); np->have[slot][f] = 1; }
            } else lo = byte;
            byteIx++;
        }
    }
}

static void begin_match(Netplay *np, const char *m, bool resume)
{
    double d;
    int delay = (int)jnumd(m, "delay", 3);
    reset_match(np, delay);
    read_room_fields(np, m);
    if (jnum(m, "seed", &d)) np->seed = (uint32_t)d;
    jstr(m, "startId", np->startId, sizeof(np->startId));
    double t = now_ms();
    if (resume) {
        int frame = (int)jnumd(m, "frame", 0);
        int end = (int)jnumd(m, "end", 0);
        int len[2] = { end, end };
        const char *have = jfind(m, "have");
        if (have && *have == '[') {          // frames really present per slot (the rest are not known yet)
            const char *p = ws_skip(have + 1);
            len[0] = (int)strtol(p, NULL, 10);
            p = strchr(p, ',');
            if (p) len[1] = (int)strtol(p + 1, NULL, 10);
        }
        char key[3] = "p0";
        for (int s = 0; s < 2; s++) {
            key[1] = (char)('0' + s);
            const char *v = jfind(m, key);
            if (v && *v == '"') decode_hist(np, s, v + 1, len[s]);
        }
        int me = np->st.slot;
        for (int f = np->st.delay; f < NP_MAX_FRAMES && np->have[me][f]; f++) np->localMax = f;
        while (np->remoteContig + 1 < NP_MAX_FRAMES && np->have[me ^ 1][np->remoteContig + 1]) np->remoteContig++;
        np->peerAck = np->localMax;          // the server already relayed these
        np->resumeTarget = frame;
        np->resumeHash = (uint32_t)jnumd(m, "hash", 0);
        np->origin = t;
    } else {
        double startAt = jnumd(m, "startAt", 0), serverNow = jnumd(m, "now", 0);
        double lead = (serverNow > 0 && startAt > serverNow) ? startAt - serverNow - np->st.rttMs * 0.5 : 250.0;
        if (lead < 0) lead = 0;
        if (lead > 5000) lead = 5000;
        np->origin = t + lead;
    }
    np->resuming = false;
    np->st.phase = NP_PLAYING;
    NpEvent *e = push_event(np, NP_EV_START);
    e->resumeFrame = np->resumeTarget;
    status(np, resume ? "Rejoined - catching up" : "Fight!");
}

static void send_hold_frame(Netplay *np)
{
    if (!np->match || np->over) return;
    int me = np->st.slot;
    int from = np->st.frame - 90 < np->st.delay ? np->st.delay : np->st.frame - 90;
    char buf[1400];
    int n = snprintf(buf, sizeof(buf), "{\"t\":\"hold_frame\",\"frame\":%d,\"hash\":%u,\"base\":%d,\"bits\":[",
                     np->st.frame, (unsigned)np->lastHash, from);
    for (int f = from; f <= np->localMax && f - from < 120; f++)
        n += snprintf(buf + n, sizeof(buf) - n, "%s%u", f > from ? "," : "", (unsigned)np->bits[me][f]);
    n += snprintf(buf + n, sizeof(buf) - n, "]}");
    if (is_open(np)) NpWs_Send(np->ws, buf, n);
}

static void handle(Netplay *np, const char *m)
{
    char t[24];
    if (!jstr(m, "t", t, sizeof(t))) return;
    double d;

    if (!strcmp(t, "input")) { on_input(np, m); return; }
    if (!strcmp(t, "hb")) { if (np->match) np->lastPeerRx = now_ms(); return; }
    if (!strcmp(t, "nack")) {
        if (!np->match || np->over) return;
        send_range(np, (int)jnumd(m, "fromFrame", 0), (int)jnumd(m, "toFrame", -1));
        return;
    }
    if (!strcmp(t, "hash")) {
        if (!np->match) return;
        if (jnum(m, "epoch", &d) && (int)d != np->epoch) return;
        np->lastPeerRx = now_ms();
        int frame = (int)jnumd(m, "frame", 0), i = frame / NP_HASH_EVERY;
        if (frame % NP_HASH_EVERY || i <= 0 || i >= HASH_SLOTS) return;
        np->hashTheirs[i] = (uint32_t)jnumd(m, "hash", 0);
        np->hashFlags[i] |= 2;
        compare_hash(np, frame);
        return;
    }
    if (!strcmp(t, "pong")) {
        double rtt = now_ms() - jnumd(m, "ts", now_ms());
        if (rtt < 0 || rtt > 5000) return;
        if (!np->samples) np->st.rttMs = (float)rtt;
        float dev = fabsf((float)rtt - np->st.rttMs);
        np->st.rttMs += ((float)rtt - np->st.rttMs) * 0.25f;
        np->st.jitterMs += (dev - np->st.jitterMs) * 0.25f;
        if (np->samples < 50) np->samples++;
        return;
    }
    if (!strcmp(t, "queued")) { np->st.phase = NP_QUEUED; status(np, "Looking for an opponent..."); return; }
    if (!strcmp(t, "created") || !strcmp(t, "joined") || !strcmp(t, "matched")) {
        read_room_fields(np, m);
        if (np->match && !np->over) {
            char phase[16];
            jstr(m, "phase", phase, sizeof(phase));
            if (!strcmp(phase, "playing")) { np->resuming = true; status(np, "Rejoining the match..."); return; }
            end_match(np, -1, "The match ended while you were away");
        }
        np->st.phase = NP_LOBBY;
        status(np, "Room %s - you are P%d", np->st.room, np->st.slot + 1);
        push_event(np, NP_EV_ROOM);
        return;
    }
    if (!strcmp(t, "room_state") || !strcmp(t, "peer_pick") || !strcmp(t, "peer") || !strcmp(t, "ready_ack")) {
        if (!strcmp(t, "peer_pick")) {
            int s = (int)jnumd(m, "slot", -1);
            if (s == 0 || s == 1) jstr(m, "char", np->st.picks[s], sizeof(np->st.picks[s]));
        } else if (!strcmp(t, "room_state")) {
            int slot = np->st.slot;
            read_room_fields(np, m);
            np->st.slot = slot;                // room_state has no slot; keep ours
        }
        if (np->st.phase != NP_PLAYING) push_event(np, NP_EV_LOBBY);
        return;
    }
    if (!strcmp(t, "countdown")) {
        read_room_fields(np, m);
        if (jnum(m, "seed", &d)) np->seed = (uint32_t)d;
        jstr(m, "startId", np->startId, sizeof(np->startId));
        np->st.phase = NP_COUNTDOWN;
        status(np, "Both ready - loading");
        push_event(np, NP_EV_COUNTDOWN);
        return;
    }
    if (!strcmp(t, "countdown_cancel")) {
        read_room_fields(np, m);
        np->st.phase = NP_LOBBY;
        np->st.ready[0] = np->st.ready[1] = false;
        NpEvent *e = push_event(np, NP_EV_CANCEL);
        jstr(m, "reason", e->text, sizeof(e->text));
        status(np, "Start cancelled (%s)", e->text);
        return;
    }
    if (!strcmp(t, "go")) { begin_match(np, m, false); return; }
    if (!strcmp(t, "resume")) { begin_match(np, m, true); return; }
    if (!strcmp(t, "need_frame")) { send_hold_frame(np); return; }
    if (!strcmp(t, "peer_hold")) {
        np->st.peerHeld = true;
        int ms = (int)jnumd(m, "timeoutMs", 30000);
        np->holdUntil = now_ms() + ms;
        NpEvent *e = push_event(np, NP_EV_PEER_HOLD);
        e->holdMs = ms;
        status(np, "Opponent disconnected - waiting for them");
        return;
    }
    if (!strcmp(t, "peer_back")) {
        np->st.peerHeld = false;
        np->lastPeerRx = now_ms();
        np->waitSince = 0;
        push_event(np, NP_EV_PEER_BACK);
        status(np, "Opponent is back");
        return;
    }
    if (!strcmp(t, "forfeit")) {
        read_room_fields(np, m);
        char notice[96];
        jstr(m, "notice", notice, sizeof(notice));
        int winner = (int)jnumd(m, "winner", -1);
        if (winner != np->st.slot) snprintf(notice, sizeof(notice), "You left - match forfeited");
        end_match(np, winner, notice);
        return;
    }
    if (!strcmp(t, "match_end")) {
        read_room_fields(np, m);
        char notice[96];
        jstr(m, "notice", notice, sizeof(notice));
        end_match(np, -1, notice);
        return;
    }
    if (!strcmp(t, "peer_left")) {
        read_room_fields(np, m);
        np->st.picks[np->st.slot ^ 1][0] = 0;
        np->st.ready[0] = np->st.ready[1] = false;
        end_match(np, np->st.slot, "Opponent left");
        np->st.phase = NP_LOBBY;
        NpEvent *e = push_event(np, NP_EV_PEER_LEFT);
        snprintf(e->text, sizeof(e->text), "Opponent left");
        return;
    }
    if (!strcmp(t, "error")) {
        NpEvent *e = push_event(np, NP_EV_ERROR);
        jstr(m, "msg", e->text, sizeof(e->text));
        status(np, "%s", e->text);
        if (!strcmp(e->text, "Room not found") || !strncmp(e->text, "Room full", 9)) {
            np->st.room[0] = 0;
            np->st.phase = NP_IDLE;
        }
        return;
    }
}

// ---------------------------------------------------------------------------
//  Public API
// ---------------------------------------------------------------------------
Netplay *Np_New(const char *url, const char *userId)
{
    Netplay *np = (Netplay *)calloc(1, sizeof(Netplay));
    snprintf(np->url, sizeof(np->url), "%s", url);
    clean_token(np->userId, sizeof(np->userId), userId);
    if (!np->userId[0]) snprintf(np->userId, sizeof(np->userId), "u%08x", (unsigned)(now_ms() * 1000.0));
    np->st.slot = -1;
    np->st.delay = 3;
    np->wantOnline = true;
    np->backoff = 300;
    np->connectStart = now_ms();
    np->nextTry = 0;
    np->st.phase = NP_CONNECTING;
    status(np, "Connecting...");
    return np;
}

void Np_Free(Netplay *np)
{
    if (!np) return;
    if (is_open(np) && np->st.room[0]) sendf(np, false, "{\"t\":\"leave\",\"userId\":\"%s\"}", np->userId);
    NpWs_Close(np->ws);
    for (int i = 0; i < np->outCount; i++) free(np->outbox[i]);
    free_match(np);
    free(np);
}

static void on_open(Netplay *np)
{
    np->backoff = 300;
    np->connectStart = 0;
    np->lastPing = 0;
    if (np->st.room[0]) {
        // back after a drop: reclaim our slot (the server resumes a running match)
        for (int i = 0; i < np->outCount; i++) free(np->outbox[i]);
        np->outCount = 0;
        sendf(np, false, "{\"t\":\"join\",\"room\":\"%s\",\"userId\":\"%s\"}", np->st.room, np->userId);
        if (np->match && !np->over) np->resuming = true;
    } else {
        np->st.phase = NP_IDLE;
        status(np, "Connected");
    }
    for (int i = 0; i < np->outCount; i++) {
        trace(">", np->outbox[i]);
        NpWs_Send(np->ws, np->outbox[i], (int)strlen(np->outbox[i]));
        free(np->outbox[i]);
    }
    np->outCount = 0;
}

void Np_Poll(Netplay *np)
{
    double t = now_ms();
    if (!np->ws && np->wantOnline && t >= np->nextTry) {
        if (!np->connectStart) np->connectStart = t;
        np->ws = NpWs_Open(np->url);
        if (!np->ws) { np->wantOnline = false; np->st.phase = NP_OFFLINE; status(np, "Bad server address: %s", np->url); return; }
        if (np->st.phase == NP_OFFLINE) np->st.phase = NP_CONNECTING;
    }
    if (np->ws) {
        NpWsState s = NpWs_Poll(np->ws);
        if (s == NPWS_OPEN && np->connectStart) on_open(np);
        if (s == NPWS_CONNECTING && np->connectStart && t - np->connectStart > 2500) status(np, "Waking the server...");
        char *msg;
        while (np->ws && NpWs_Recv(np->ws, &msg) > 0) { trace("<", msg); handle(np, msg); free(msg); }
        if (s == NPWS_CLOSED) {
            char why[128];
            snprintf(why, sizeof(why), "%s", NpWs_Error(np->ws));
            NpWs_Close(np->ws);
            np->ws = NULL;
            if (!np->connectStart) {            // it was open: tell the game, then reconnect
                np->connectStart = t;
                NpEvent *e = push_event(np, NP_EV_DISCONNECT);
                snprintf(e->text, sizeof(e->text), "%s", why);
            }
            if (t - np->connectStart > WAKE_MS) {
                np->wantOnline = false;
                np->st.phase = NP_OFFLINE;
                end_match(np, -1, "Connection lost");
                status(np, "Can't reach the server (%s)", why);
            } else {
                np->nextTry = t + np->backoff;
                np->backoff = np->backoff * 1.6 > 3000 ? 3000 : np->backoff * 1.6;
                if (np->st.phase != NP_PLAYING) np->st.phase = NP_CONNECTING;
                status(np, np->st.room[0] ? "Reconnecting..." : "Waking the server...");
            }
        }
    }
    if (!is_open(np)) return;

    if (np->st.phase != NP_PLAYING && t - np->lastPing > PING_EVERY_MS) {
        np->lastPing = t;
        sendf(np, false, "{\"t\":\"ping\",\"ts\":%.3f}", t);
    }
    if (np->match && !np->over && !np->resuming) {
        if (np->localMax > np->peerAck && t - np->lastSend > SEND_EVERY_MS) send_tail(np);
        if (t - np->lastSend > HB_EVERY_MS && t - np->lastHb > HB_EVERY_MS) {
            np->lastHb = t;
            sendf(np, false, "{\"t\":\"hb\"}");
        }
        np->st.slow = np->st.waiting && np->waitSince && t - np->waitSince > SLOW_MS;
        if (np->st.peerHeld) {
            np->st.holdLeftMs = (int)(np->holdUntil - t);
            if (np->st.holdLeftMs < 0) np->st.holdLeftMs = 0;
            status(np, "Opponent disconnected - waiting %ds", (np->st.holdLeftMs + 999) / 1000);
        } else if (np->st.waiting && np->waitSince && t - np->waitSince > LOST_MS && t - np->lastPeerRx > LOST_MS) {
            sendf(np, false, "{\"t\":\"give_up\"}");
            end_match(np, -1, "Connection lost");
        } else if (np->st.slow) {
            status(np, "Connection slow");
        }
    }
}

bool Np_NextEvent(Netplay *np, NpEvent *ev)
{
    if (!np->evCount) return false;
    *ev = np->ev[np->evHead];
    np->evHead = (np->evHead + 1) % EVQ;
    np->evCount--;
    return true;
}

const NpState *Np_State(const Netplay *np) { return &np->st; }

void Np_Create(Netplay *np)
{
    np->st.room[0] = 0;
    sendf(np, true, "{\"t\":\"create\",\"userId\":\"%s\"}", np->userId);
}

void Np_Join(Netplay *np, const char *code)
{
    char room[8];
    clean_token(room, sizeof(room), code);
    for (char *c = room; *c; c++) if (*c >= 'a' && *c <= 'z') *c = (char)(*c - 32);
    np->st.room[0] = 0;
    sendf(np, true, "{\"t\":\"join\",\"room\":\"%s\",\"userId\":\"%s\"}", room, np->userId);
}

void Np_Quick(Netplay *np)
{
    np->st.room[0] = 0;
    sendf(np, true, "{\"t\":\"quick\",\"userId\":\"%s\"}", np->userId);
}

void Np_Pick(Netplay *np, const char *pick)
{
    char p[33];
    clean_token(p, sizeof(p), pick);
    if (np->st.slot == 0 || np->st.slot == 1) snprintf(np->st.picks[np->st.slot], sizeof(np->st.picks[0]), "%s", p);
    sendf(np, true, "{\"t\":\"pick\",\"char\":\"%s\",\"userId\":\"%s\"}", p, np->userId);
}

void Np_Ready(Netplay *np, bool ready)
{
    sendf(np, true, "{\"t\":\"ready\",\"ready\":%s,\"readySeq\":%d,\"userId\":\"%s\"}",
          ready ? "true" : "false", ++np->readySeq, np->userId);
}

void Np_Loaded(Netplay *np)
{
    sendf(np, false, "{\"t\":\"loaded\",\"startId\":\"%s\",\"rtt\":%.1f,\"jitter\":%.1f,\"samples\":%d}",
          np->startId, np->st.rttMs, np->st.jitterMs, np->samples);
}

void Np_Leave(Netplay *np)
{
    sendf(np, false, "{\"t\":\"leave\",\"userId\":\"%s\"}", np->userId);
    end_match(np, -1, "You left");
    free_match(np);
    np->st.room[0] = 0;
    np->st.slot = -1;
    np->st.phase = is_open(np) ? NP_IDLE : NP_CONNECTING;
    memset(np->st.picks, 0, sizeof(np->st.picks));
    np->st.ready[0] = np->st.ready[1] = false;
}

bool Np_InMatch(const Netplay *np) { return np->match && !np->over; }

int Np_StepsDue(Netplay *np)
{
    if (!np->match || np->over || np->resuming || np->st.peerHeld) return 0;
    double t = now_ms();
    if (np->resumeTarget > np->st.frame) {          // replaying after a rejoin
        int left = np->resumeTarget - np->st.frame;
        return left > 600 ? 600 : left;
    }
    double elapsed = t - np->origin;
    if (elapsed < 0) return 0;
    int ideal = (int)floor(elapsed / FRAME_MS);
    int behind = ideal - np->st.frame;
    if (behind > RESYNC_BEHIND) {                   // a stall: restart the clock, don't fast-forward
        np->origin = t - np->st.frame * FRAME_MS;
        return 0;
    }
    if (behind <= 0) return 0;
    return behind == 1 ? 1 : 2;
}

bool Np_SetLocalInput(Netplay *np, uint16_t bits)
{
    if (!np->match || np->over) return false;
    int me = np->st.slot;
    int f = np->st.frame + np->st.delay;
    if (me < 0 || f >= NP_MAX_FRAMES || np->have[me][f]) return false;
    np->bits[me][f] = bits;
    np->have[me][f] = 1;
    if (f > np->localMax) np->localMax = f;
    send_tail(np);
    return true;
}

bool Np_FrameInputs(Netplay *np, uint16_t out[2])
{
    int f = np->st.frame;
    if (!np->match || np->over || f >= NP_MAX_FRAMES) return false;
    if (f < np->st.delay) {
        out[0] = out[1] = 0;
    } else {
        int me = np->st.slot;
        if (!np->have[me][f]) np->have[me][f] = 1;       // never sent (rejoin edge): neutral
        if (!np->have[me ^ 1][f]) {
            if (!np->st.waiting) np->waitSince = now_ms();
            np->st.waiting = true;
            return false;
        }
        out[0] = np->bits[0][f];
        out[1] = np->bits[1][f];
    }
    np->st.waiting = false;
    np->st.slow = false;
    np->waitSince = 0;
    return true;
}

void Np_FrameDone(Netplay *np, uint32_t hash)
{
    if (!np->match) return;
    np->st.frame++;
    np->lastHash = hash;
    int f = np->st.frame;
    if (np->resumeTarget && f == np->resumeTarget) {
        np->resumeTarget = 0;
        np->origin = now_ms() - f * FRAME_MS;
        if (np->resumeHash && np->resumeHash != hash) {
            sendf(np, false, "{\"t\":\"give_up\"}");
            end_match(np, -1, "Desync after rejoin - no contest");
            return;
        }
        status(np, "Back in the match");
    }
    if (f % NP_HASH_EVERY == 0 && f / NP_HASH_EVERY < HASH_SLOTS) {
        int i = f / NP_HASH_EVERY;
        np->hashMine[i] = hash;
        np->hashFlags[i] |= 1;
        sendf(np, false, "{\"t\":\"hash\",\"frame\":%d,\"hash\":%u}", f, (unsigned)hash);
        compare_hash(np, f);
    }
}

void Np_MatchOver(Netplay *np)
{
    if (!np->match || np->over) return;
    np->over = true;
    send_tail(np);                 // the other side may still need our last frames
    np->st.phase = NP_LOBBY;
    np->st.ready[0] = np->st.ready[1] = false;
}

void Np_DebugDrop(Netplay *np)
{
    if (!np->ws) return;
    NpWs_Close(np->ws);
    np->ws = NULL;
    np->connectStart = now_ms();
    np->nextTry = now_ms() + 100;
}
