/*  sfx.c - procedural crowd, roars, whistles, kicks and text commentary.
 *  #included from main.c. Everything is synthesised at start-up (no audio
 *  files) and mixed in software into one raylib AudioStream; the same mixer
 *  can render offline (for the intro video's soundtrack).
 *
 *  Spoken commentary later: set gf_commentary_hook to a function that takes
 *  the line text and the GameEvent that caused it (e.g. a TTS engine or a
 *  table of recorded clips keyed by event). It is called once per line.
 */
#define SFX_RATE 44100
#define SFX_BLOCK 1024
#define SFX_VOICES 16

typedef void (*CommentaryHook)(const char *line, int event, void *user);
static CommentaryHook gf_commentary_hook = NULL;
static void *gf_commentary_user = NULL;

enum { SND_WHISTLE, SND_WHISTLE_LONG, SND_WHISTLE_DOUBLE, SND_ROAR, SND_CHEER, SND_GROAN, SND_KICK, SND_HANDPASS, SND_THUD, SND_OOH, SND_COUNT };
typedef struct { float *data; int len; } SfxBuf;
static SfxBuf sfxBuf[SND_COUNT];
typedef struct { int snd, pos; float gain; } Voice;
static Voice voices[SFX_VOICES];
static AudioStream sfxStream;
static int sfxOn;
static float crowdLevel = 0.25f, crowdTarget = 0.25f, crowdHold = 0;
static unsigned int sfxSeed = 12345;
static float lp1, lp2, lp3, bp1, bp2, chantPhase, murmurT;

static float frand(void) { sfxSeed = sfxSeed * 1664525u + 1013904223u; return ((sfxSeed >> 9) & 0x7FFFFF) / (float)0x7FFFFF * 2.0f - 1.0f; }

static SfxBuf sfxAlloc(float seconds) { SfxBuf b; b.len = (int)(seconds * SFX_RATE); b.data = RL_CALLOC(b.len, sizeof(float)); return b; }

/* pea whistle: ~2.9 kHz tone, warbled by the pea at ~35 Hz */
static SfxBuf synthWhistle(float dur, int bursts)
{
    SfxBuf b = sfxAlloc(dur);
    float ph = 0;
    for (int i = 0; i < b.len; i++) {
        float t = (float)i / SFX_RATE;
        float seg = dur / bursts, ts = fmodf(t, seg), on = ts < seg * 0.78f ? 1.0f : 0.0f;
        float env = on * fminf(1.0f, ts * 60.0f) * fminf(1.0f, (seg * 0.78f - ts) * 40.0f);
        float f = 2850.0f + 160.0f * sinf(2 * PI * 34.0f * t);
        ph += 2 * PI * f / SFX_RATE;
        float am = 0.75f + 0.25f * sinf(2 * PI * 34.0f * t + 1.0f);
        b.data[i] = env * am * (0.55f * sinf(ph) + 0.12f * sinf(2 * ph) + 0.05f * frand());
    }
    return b;
}

/* crowd swell: band-limited noise with a slow attack and long release */
static SfxBuf synthCrowd(float dur, float attack, float bright, float pitchy)
{
    SfxBuf b = sfxAlloc(dur);
    float a1 = 0, a2 = 0, a3 = 0;
    for (int i = 0; i < b.len; i++) {
        float t = (float)i / SFX_RATE;
        float env = fminf(1.0f, t / attack) * expf(-fmaxf(0.0f, t - attack) * (2.2f / dur));
        float n = frand();
        a1 += (n - a1) * (0.08f + 0.25f * bright);
        a2 += (a1 - a2) * 0.18f;
        a3 += (a2 - a3) * 0.02f;
        float voice = pitchy * sinf(2 * PI * (220.0f + 40.0f * sinf(t * 3.1f)) * t) * (0.5f + 0.5f * frand());
        b.data[i] = env * ((a2 - a3) * 2.4f + voice * 0.08f);
    }
    return b;
}

static SfxBuf synthThump(float f0, float dur, float noise)
{
    SfxBuf b = sfxAlloc(dur);
    float ph = 0;
    for (int i = 0; i < b.len; i++) {
        float t = (float)i / SFX_RATE;
        float f = f0 * (1.0f + 1.5f * expf(-t * 60.0f));
        ph += 2 * PI * f / SFX_RATE;
        b.data[i] = expf(-t * 28.0f) * (0.8f * sinf(ph) + noise * frand() * expf(-t * 120.0f));
    }
    return b;
}

static void sfxPlay(int snd, float gain)
{
    if (!sfxBuf[snd].data) return;
    for (int v = 0; v < SFX_VOICES; v++)
        if (voices[v].snd < 0) { voices[v].snd = snd; voices[v].pos = 0; voices[v].gain = gain; return; }
}

/* Mix n mono samples: crowd bed + one-shot voices. */
static void sfxMix(float *out, int n, float dt)
{
    (void)dt;
    for (int i = 0; i < n; i++) {
        crowdLevel += (crowdTarget - crowdLevel) * 0.00004f;
        float w = frand();
        lp1 += (w - lp1) * 0.12f;          /* murmur band ~ 300-1500 Hz */
        lp2 += (lp1 - lp2) * 0.10f;
        lp3 += (lp2 - lp3) * 0.015f;
        float bed = (lp2 - lp3) * 2.6f;
        murmurT += 1.0f / SFX_RATE;
        float swell = 0.8f + 0.2f * sinf(murmurT * 0.7f) * sinf(murmurT * 0.23f + 1.0f);
        /* faint chant pulse when the crowd is up */
        chantPhase += 2 * PI * 1.9f / SFX_RATE;
        float chant = crowdLevel > 0.45f ? (0.5f + 0.5f * sinf(chantPhase)) * (crowdLevel - 0.45f) : 0.0f;
        bp1 += (w - bp1) * 0.3f; bp2 += (bp1 - bp2) * 0.3f;
        float s = bed * crowdLevel * swell * 0.55f + (bp1 - bp2) * chant * 0.25f;
        for (int v = 0; v < SFX_VOICES; v++) {
            Voice *vo = &voices[v];
            if (vo->snd < 0) continue;
            s += sfxBuf[vo->snd].data[vo->pos] * vo->gain;
            if (++vo->pos >= sfxBuf[vo->snd].len) vo->snd = -1;
        }
        out[i] = tanhf(s * 1.2f) * 0.8f;
    }
}

static void sfxInit(int openDevice)
{
    for (int v = 0; v < SFX_VOICES; v++) voices[v].snd = -1;
    sfxBuf[SND_WHISTLE] = synthWhistle(0.38f, 1);
    sfxBuf[SND_WHISTLE_LONG] = synthWhistle(1.3f, 1);
    sfxBuf[SND_WHISTLE_DOUBLE] = synthWhistle(0.7f, 2);
    sfxBuf[SND_ROAR] = synthCrowd(4.5f, 0.25f, 0.9f, 1.0f);
    sfxBuf[SND_CHEER] = synthCrowd(2.8f, 0.15f, 0.7f, 0.6f);
    sfxBuf[SND_GROAN] = synthCrowd(1.8f, 0.3f, 0.2f, 0.3f);
    sfxBuf[SND_OOH] = synthCrowd(1.4f, 0.2f, 0.35f, 0.8f);
    sfxBuf[SND_KICK] = synthThump(95.0f, 0.18f, 0.6f);
    sfxBuf[SND_HANDPASS] = synthThump(180.0f, 0.09f, 0.9f);
    sfxBuf[SND_THUD] = synthThump(70.0f, 0.25f, 0.3f);
    if (!openDevice) return;
    InitAudioDevice();
    if (!IsAudioDeviceReady()) { TraceLog(LOG_WARNING, "GAME: no audio device - running silent"); return; }
    SetAudioStreamBufferSizeDefault(SFX_BLOCK);
    sfxStream = LoadAudioStream(SFX_RATE, 32, 1);
    PlayAudioStream(sfxStream);
    sfxOn = 1;
}

static void sfxUpdate(float dt)
{
    if (crowdHold > 0) { crowdHold -= dt; if (crowdHold <= 0) crowdTarget = 0.25f; }
    if (!sfxOn) return;
    static float buf[SFX_BLOCK];
    while (IsAudioStreamProcessed(sfxStream)) {
        sfxMix(buf, SFX_BLOCK, dt);
        UpdateAudioStream(sfxStream, buf, SFX_BLOCK);
    }
}

static void crowdSurge(float level, float hold) { if (level > crowdTarget) crowdTarget = level; crowdHold = fmaxf(crowdHold, hold); }

static void sfxShutdown(void)
{
    if (sfxOn) { UnloadAudioStream(sfxStream); CloseAudioDevice(); }
    for (int i = 0; i < SND_COUNT; i++) RL_FREE(sfxBuf[i].data);
}

/* ---- text commentary -------------------------------------------------------- */
#define COMM_LINES 3
static char commLine[COMM_LINES][160];
static float commAge[COMM_LINES] = { 99, 99, 99 };

static void commentarySay(int event, const char *fmt, ...)
{
    char line[160];
    va_list ap; va_start(ap, fmt); vsnprintf(line, sizeof line, fmt, ap); va_end(ap);
    for (int i = COMM_LINES - 1; i > 0; i--) { strcpy(commLine[i], commLine[i - 1]); commAge[i] = commAge[i - 1]; }
    strcpy(commLine[0], line); commAge[0] = 0;
    if (gf_commentary_hook) gf_commentary_hook(line, event, gf_commentary_user);
    if (getenv("GF_COMMENTARY")) printf("COMMENTARY: %s\n", line);
}

static __attribute__((unused)) const char *pick(const char **opts, int n) { return opts[GetRandomValue(0, n - 1)]; }
