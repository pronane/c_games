/* audio.c : every sound and every song is synthesised in code at startup.
 * - chiptune music per track (pulse lead, pulse arps, triangle bass, noise drums)
 * - engine hum + drift screech per human player (real-time AudioStream callback)
 * - one-shot effects built from oscillators + noise
 */
#include "common.h"

#define SR 22050
#define NUM_SONGS (NUM_TRACKS + 2)
#define SFX_ALIASES 3

static bool audioOk = false;

/* ------------------------------------------------------------------ */
/* small synthesis toolkit                                              */
/* ------------------------------------------------------------------ */
static unsigned int nseed = 22222;
static float Noise(void) { nseed ^= nseed << 13; nseed ^= nseed >> 17; nseed ^= nseed << 5; return (float)(nseed & 0xFFFF)/32768.0f - 1.0f; }

typedef enum { OSC_SQUARE50, OSC_SQUARE25, OSC_SQUARE12, OSC_TRI, OSC_SAW, OSC_SINE, OSC_NOISE } OscType;

static float Osc(OscType t, float ph)
{
    ph -= floorf(ph);
    switch (t) {
    case OSC_SQUARE50: return ph < 0.5f ? 0.8f : -0.8f;
    case OSC_SQUARE25: return ph < 0.25f ? 0.8f : -0.8f;
    case OSC_SQUARE12: return ph < 0.125f ? 0.8f : -0.8f;
    case OSC_TRI: return ph < 0.5f ? (4.0f*ph - 1.0f) : (3.0f - 4.0f*ph);
    case OSC_SAW: return 2.0f*ph - 1.0f;
    case OSC_SINE: return sinf(ph*2.0f*PI);
    case OSC_NOISE: return Noise();
    }
    return 0;
}

static float MidiHz(float m) { return 440.0f*powf(2.0f, (m - 69.0f)/12.0f); }

/* add a note with a simple ADSR envelope into a float buffer */
static void AddNote(float *buf, int len, float start, float dur, float hz, OscType type, float vol,
                    float att, float dec, float sus, float rel, float vib, float slide)
{
    int s0 = (int)(start*SR);
    int n = (int)((dur + rel)*SR);
    float ph = 0;
    for (int i = 0; i < n; i++) {
        int idx = s0 + i;
        if (idx < 0) continue;
        if (idx >= len) idx -= len;            /* wrap so loops stay seamless */
        if (idx < 0 || idx >= len) continue;
        float t = (float)i/SR;
        float env;
        if (t < att) env = t/att;
        else if (t < att + dec) env = 1.0f - (1.0f - sus)*((t - att)/dec);
        else if (t < dur) env = sus;
        else env = sus*(1.0f - (t - dur)/rel);
        if (env < 0) env = 0;
        float f = hz*(1.0f + slide*t);
        if (vib > 0 && t > 0.12f) f *= 1.0f + vib*sinf(t*2*PI*5.5f);
        ph += f/SR;
        float v = (type == OSC_NOISE) ? Noise() : Osc(type, ph);
        buf[idx] += v*env*vol;
    }
}

static void AddKick(float *buf, int len, float start, float vol)
{
    int s0 = (int)(start*SR);
    float ph = 0;
    for (int i = 0; i < SR/6; i++) {
        int idx = (s0 + i) % len;
        float t = (float)i/SR;
        float f = 140.0f*expf(-t*25.0f) + 45.0f;
        ph += f/SR;
        buf[idx] += sinf(ph*2*PI)*expf(-t*14.0f)*vol;
    }
}

static void AddSnare(float *buf, int len, float start, float vol)
{
    int s0 = (int)(start*SR);
    float ph = 0;
    for (int i = 0; i < SR/7; i++) {
        int idx = (s0 + i) % len;
        float t = (float)i/SR;
        ph += 190.0f/SR;
        buf[idx] += (Noise()*0.8f + Osc(OSC_TRI, ph)*0.4f)*expf(-t*22.0f)*vol;
    }
}

static void AddHat(float *buf, int len, float start, float vol)
{
    int s0 = (int)(start*SR);
    float prev = 0;
    for (int i = 0; i < SR/30; i++) {
        int idx = (s0 + i) % len;
        float t = (float)i/SR;
        float nz = Noise();
        float hp = nz - prev; prev = nz;
        buf[idx] += hp*expf(-t*90.0f)*vol;
    }
}

static Wave FloatsToWave(float *buf, int len, float gain)
{
    float peak = 0.0001f;
    for (int i = 0; i < len; i++) if (fabsf(buf[i]) > peak) peak = fabsf(buf[i]);
    float g = gain/peak;
    if (g > 1.6f) g = 1.6f;
    Wave w = { 0 };
    w.frameCount = (unsigned int)len;
    w.sampleRate = SR;
    w.sampleSize = 16;
    w.channels = 1;
    short *d = (short *)RL_MALLOC((size_t)len*sizeof(short));
    for (int i = 0; i < len; i++) {
        float v = buf[i]*g;
        v = Clamp(v, -1.0f, 1.0f);
        d[i] = (short)(v*32000.0f);
    }
    w.data = d;
    return w;
}

/* ------------------------------------------------------------------ */
/* Music                                                                */
/* ------------------------------------------------------------------ */
typedef struct { short *data; int len; } SongBuf;
static SongBuf songs[NUM_SONGS];
static AudioStream musicStream;
static volatile int curSong = -1, pendingSong = -2;
static volatile float songRate = 1.0f, musicVolume = 0.5f;
static double songPos = 0;

static const int SCALES[4][7] = {
    { 0, 2, 4, 5, 7, 9, 11 },  /* major */
    { 0, 2, 3, 5, 7, 8, 10 },  /* minor */
    { 0, 2, 4, 5, 7, 9, 10 },  /* mixolydian */
    { 0, 2, 3, 5, 7, 9, 10 },  /* dorian */
};

static int ScaleNote(int scale, int key, int degree)
{
    int oct = degree >= 0 ? degree/7 : -((-degree + 6)/7);
    int d = degree - oct*7;
    return key + oct*12 + SCALES[scale][d];
}

static unsigned int mseed = 1;
static int MRand(int n) { mseed = mseed*1103515245u + 12345u; return (int)((mseed >> 16) % (unsigned)n); }

static void GenSong(SongBuf *out, int seed, float bpm, int key, int scale, int energy)
{
    mseed = (unsigned)seed*2654435761u + 1u;
    const int progs[6][4] = { {0,4,5,3}, {0,5,3,4}, {0,3,4,4}, {5,3,0,4}, {0,6,5,4}, {3,4,0,0} };
    int progA = MRand(6), progB = MRand(6);
    if (progB == progA) progB = (progA + 2) % 6;
    float beat = 60.0f/bpm;
    float bar = beat*4;
    int bars = 16;
    int len = (int)(bars*bar*SR);
    float *mix = (float *)calloc((size_t)len, sizeof(float));
    float e8 = beat*0.5f, e16 = beat*0.25f;

    /* rhythm templates in 8th notes (sum = 16 => two bars) */
    const int rhythms[6][10] = {
        { 2,1,1,2,2,1,1,2,4,0 }, { 1,1,2,1,1,2,2,2,4,0 }, { 3,1,2,2,3,1,4,0,0,0 },
        { 2,2,1,1,1,1,2,2,4,0 }, { 1,1,1,1,2,2,2,2,4,0 }, { 3,3,2,3,3,2,0,0,0,0 } };
    int motifR[2], motifP[2][10];
    for (int m = 0; m < 2; m++) {
        motifR[m] = MRand(6);
        int deg = 2 + MRand(3);
        for (int i = 0; i < 10; i++) {
            int step = MRand(5) - 2;
            if (MRand(4) == 0) step *= 2;
            deg += step;
            if (deg < -1) deg = 1;
            if (deg > 9) deg = 7;
            motifP[m][i] = deg;
        }
    }

    for (int b = 0; b < bars; b++) {
        int section = b/8;
        const int *prog = section == 0 ? progs[progA] : progs[progB];
        int chord = prog[(b/2) % 4];
        float t0 = b*bar;
        int root = ScaleNote(scale, key - 24, chord);
        int fifth = ScaleNote(scale, key - 24, chord + 4);
        /* bass */
        const int bp[8] = { 0, 0, 12, 0, 7, 0, 12, 7 };
        for (int i = 0; i < 8; i++) {
            int note = (bp[i] == 7) ? fifth : root + bp[i];
            AddNote(mix, len, t0 + i*e8, e8*0.8f, MidiHz((float)note), OSC_TRI, 0.30f, 0.004f, 0.05f, 0.8f, 0.02f, 0, 0);
        }
        /* arpeggio */
        for (int i = 0; i < 16; i++) {
            int tone = (i % 4 == 3) ? 2 : (i % 4);
            int note = ScaleNote(scale, key, chord + tone*2);
            AddNote(mix, len, t0 + i*e16, e16*0.6f, MidiHz((float)note), OSC_SQUARE12, 0.05f + 0.02f*energy, 0.002f, 0.04f, 0.4f, 0.02f, 0, 0);
        }
        /* pad: long chord tones */
        if (energy >= 1) {
            for (int c = 0; c < 3; c++) {
                int note = ScaleNote(scale, key - 12, chord + c*2);
                AddNote(mix, len, t0, bar*0.95f, MidiHz((float)note), OSC_SQUARE50, 0.022f, 0.05f, 0.3f, 0.6f, 0.1f, 0.004f, 0);
            }
        }
        /* drums */
        for (int q = 0; q < 4; q++) {
            float bt = t0 + q*beat;
            if (q == 0 || q == 2) AddKick(mix, len, bt, 0.55f);
            if (q == 1 || q == 3) AddSnare(mix, len, bt, 0.28f);
            AddHat(mix, len, bt, 0.12f);
            AddHat(mix, len, bt + e8, 0.08f);
            if (energy >= 2) { AddHat(mix, len, bt + e16, 0.04f); AddHat(mix, len, bt + 3*e16, 0.04f); }
        }
        if (energy >= 1 && (b % 4 == 2)) AddKick(mix, len, t0 + 2.5f*beat, 0.4f);
        if (b % 8 == 7) { /* fill */
            for (int i = 0; i < 4; i++) AddSnare(mix, len, t0 + 3*beat + i*e16, 0.18f + 0.04f*i);
        }
    }
    /* melody: 2-bar phrases, motif A A' A cadence | B B' B A-cadence */
    for (int ph = 0; ph < 8; ph++) {
        int m = (ph < 4) ? 0 : 1;
        if (ph == 7) m = 0;
        float t = ph*2*bar;
        const int *rh = rhythms[motifR[m]];
        float pos = 0;
        for (int i = 0; i < 10 && rh[i]; i++) {
            float dur = rh[i]*e8;
            int barIdx = ph*2 + (int)(pos/bar);
            int section = barIdx/8;
            const int *prog = section == 0 ? progs[progA] : progs[progB];
            int chord = prog[(barIdx/2) % 4];
            int deg = motifP[m][i];
            if ((ph % 2) == 1 && i >= 5) deg += (ph == 3 || ph == 7) ? -1 : 1;   /* variation */
            bool strong = fmodf(pos, beat*2) < 0.001f;
            if (strong) { /* snap to the nearest chord tone */
                int best = deg, bd = 99;
                for (int c = -7; c <= 14; c += 1) {
                    int rel = ((c - chord) % 7 + 7) % 7;
                    if (rel == 0 || rel == 2 || rel == 4) { int d = abs(c - deg); if (d < bd) { bd = d; best = c; } }
                }
                deg = best;
            }
            bool last = (rh[i + 1] == 0 || i == 9);
            if (last && (ph == 3 || ph == 7)) deg = chord + 7 > 9 ? chord : chord + 7;
            if (!(MRand(9) == 0 && !strong)) {
                int note = ScaleNote(scale, key + 12, deg);
                AddNote(mix, len, t + pos, dur*0.85f, MidiHz((float)note), OSC_SQUARE25, 0.16f, 0.01f, 0.08f, 0.65f, 0.05f, 0.008f, 0);
                /* harmony a third below in the B section */
                if (m == 1) AddNote(mix, len, t + pos, dur*0.85f, MidiHz((float)ScaleNote(scale, key + 12, deg - 2)), OSC_SQUARE50, 0.05f, 0.01f, 0.08f, 0.6f, 0.05f, 0.006f, 0);
            }
            pos += dur;
        }
    }
    /* simple echo for that cartridge-reverb feel */
    int dly = (int)(beat*0.75f*SR);
    float *wet = (float *)calloc((size_t)len, sizeof(float));
    for (int i = 0; i < len; i++) wet[(i + dly) % len] += mix[i]*0.22f;
    for (int i = 0; i < len; i++) mix[i] += wet[i];
    free(wet);

    Wave w = FloatsToWave(mix, len, 0.85f);
    out->data = (short *)w.data;
    out->len = len;
    free(mix);
}

static void MusicCallback(void *buffer, unsigned int frames)
{
    short *o = (short *)buffer;
    if (pendingSong != -2) { curSong = pendingSong; pendingSong = -2; songPos = 0; }
    int cs = curSong;
    if (cs < 0 || cs >= NUM_SONGS || !songs[cs].data) { memset(o, 0, frames*sizeof(short)); return; }
    const SongBuf *s = &songs[cs];
    float rate = songRate, vol = musicVolume;
    for (unsigned int i = 0; i < frames; i++) {
        int p = (int)songPos;
        float f = (float)(songPos - p);
        int p2 = p + 1; if (p2 >= s->len) p2 = 0;
        float v = s->data[p]*(1.0f - f) + s->data[p2]*f;
        o[i] = (short)(v*vol);
        songPos += rate;
        if (songPos >= s->len) songPos -= s->len;
    }
}

void MusicPlay(int song)
{
    if (!audioOk) return;
    if (song == curSong && pendingSong == -2) return;
    songRate = 1.0f;
    pendingSong = song;
}

void MusicSetTempo(float rate) { songRate = rate; }

/* ------------------------------------------------------------------ */
/* Engine + drift (one stream per human player)                         */
/* ------------------------------------------------------------------ */
typedef struct {
    volatile float targetHz, targetVol, driftVol, driftPitch;
    float hz, vol, dvol, ph, ph2, ph3, lp;
} EngineState;
static EngineState eng[MAX_HUMANS];
static AudioStream engStream[MAX_HUMANS];

static void EngineFill(int p, short *o, unsigned int frames)
{
    EngineState *e = &eng[p];
    for (unsigned int i = 0; i < frames; i++) {
        e->hz += (e->targetHz - e->hz)*0.0015f;
        e->vol += (e->targetVol - e->vol)*0.002f;
        e->dvol += (e->driftVol - e->dvol)*0.004f;
        e->ph += e->hz/SR; if (e->ph > 1) e->ph -= 1;
        e->ph2 += e->hz*0.5f/SR; if (e->ph2 > 1) e->ph2 -= 1;
        float putt = 0.75f + 0.25f*sinf(e->ph2*2*PI*0.5f);
        float v = (Osc(OSC_SQUARE25, e->ph)*0.5f + Osc(OSC_SAW, e->ph2)*0.5f)*putt;
        e->lp += (v - e->lp)*0.25f;
        float out = e->lp*e->vol;
        if (e->dvol > 0.001f) {
            e->ph3 += (e->driftPitch*(1.0f + 0.04f*sinf(e->ph2*12.0f)))/SR; if (e->ph3 > 1) e->ph3 -= 1;
            float sq = Osc(OSC_SQUARE25, e->ph3)*0.35f + Noise()*0.35f;
            out += sq*e->dvol;
        }
        float vol = G.settings.sfxVol;
        float s = out*vol*30000.0f;
        s = Clamp(s, -32000.0f, 32000.0f);
        o[i] = (short)s;
    }
}
static void EngineCb0(void *b, unsigned int f) { EngineFill(0, (short *)b, f); }
static void EngineCb1(void *b, unsigned int f) { EngineFill(1, (short *)b, f); }

void EngineSet(int player, float speedNorm, float vol)
{
    if (!audioOk || player < 0 || player >= MAX_HUMANS) return;
    if (speedNorm < 0) speedNorm = -speedNorm;
    eng[player].targetHz = 48.0f + speedNorm*95.0f;
    eng[player].targetVol = vol;
}

void DriftLoop(int player, bool on, int sparkLevel)
{
    if (!audioOk || player < 0 || player >= MAX_HUMANS) return;
    eng[player].driftVol = on ? 0.16f : 0.0f;
    eng[player].driftPitch = 700.0f + sparkLevel*250.0f;
}

/* ------------------------------------------------------------------ */
/* Sound effects                                                        */
/* ------------------------------------------------------------------ */
static Sound sfx[SFX_COUNT][SFX_ALIASES];
static int sfxNext[SFX_COUNT];
static Sound voice[3][SFX_ALIASES];
static int voiceNext[3];

static float *NewBuf(float sec, int *len) { *len = (int)(sec*SR); return (float *)calloc((size_t)*len, sizeof(float)); }

static void Arp(float *b, int len, const int *notes, int n, float step, float noteLen, OscType t, float vol)
{
    for (int i = 0; i < n; i++)
        AddNote(b, len, i*step, noteLen, MidiHz((float)notes[i]), t, vol, 0.005f, 0.05f, 0.7f, 0.08f, 0.006f, 0);
}

/* crude formant voice: saw through two resonators, pitch contour */
static void VoiceSyllable(float *b, int len, float start, float dur, float f0a, float f0b, float fa1, float fa2, float fb1, float fb2, float vol)
{
    int s0 = (int)(start*SR), n = (int)(dur*SR);
    float ph = 0, y1a = 0, y2a = 0, y1b = 0, y2b = 0;
    for (int i = 0; i < n; i++) {
        float t = (float)i/n;
        float f0 = f0a + (f0b - f0a)*t;
        f0 *= 1.0f + 0.03f*sinf(i*2*PI*6.0f/SR);
        ph += f0/SR; if (ph > 1) ph -= 1;
        float src = 2*ph - 1;
        float F1 = fa1 + (fb1 - fa1)*t, F2 = fa2 + (fb2 - fa2)*t;
        /* resonator 1 */
        float r = 0.97f, w1 = 2*PI*F1/SR, w2 = 2*PI*F2/SR;
        float a = src + 2*r*cosf(w1)*y1a - r*r*y2a; y2a = y1a; y1a = a;
        float c = src + 2*r*cosf(w2)*y1b - r*r*y2b; y2b = y1b; y1b = c;
        float env = sinf(t*PI); env = sqrtf(env);
        int idx = s0 + i;
        if (idx < len) b[idx] += (a*0.06f + c*0.035f)*env*vol;
    }
}

static Sound MakeSound(float *b, int len, float gain)
{
    Wave w = FloatsToWave(b, len, gain);
    Sound s = LoadSoundFromWave(w);
    UnloadWave(w);
    free(b);
    return s;
}

static void BuildSfx(void)
{
    int len; float *b;
    Sound base[SFX_COUNT];

    b = NewBuf(0.3f, &len); AddNote(b, len, 0, 0.22f, 440, OSC_SQUARE50, 0.5f, 0.002f, 0.02f, 0.9f, 0.05f, 0, 0); base[SFX_BEEP_LOW] = MakeSound(b, len, 0.7f);
    b = NewBuf(0.7f, &len); AddNote(b, len, 0, 0.55f, 880, OSC_SQUARE50, 0.5f, 0.002f, 0.02f, 0.9f, 0.1f, 0, 0);
    AddNote(b, len, 0, 0.55f, 1320, OSC_SQUARE25, 0.2f, 0.002f, 0.02f, 0.9f, 0.1f, 0, 0); base[SFX_BEEP_HIGH] = MakeSound(b, len, 0.75f);
    /* drift: short screech burst (the continuous one lives in the engine stream) */
    b = NewBuf(0.25f, &len); for (int i = 0; i < len; i++) { float t = (float)i/SR; b[i] = (Noise()*0.5f + Osc(OSC_SQUARE25, t*900))*expf(-t*8); } base[SFX_DRIFT] = MakeSound(b, len, 0.5f);
    /* boost whoosh: rising filtered noise + rumble */
    b = NewBuf(0.9f, &len);
    { float lp = 0; for (int i = 0; i < len; i++) { float t = (float)i/SR; float k = 0.05f + 0.5f*t; lp += (Noise() - lp)*k; float env = (t < 0.08f ? t/0.08f : expf(-(t - 0.08f)*3.2f)); b[i] = (lp*0.9f + Osc(OSC_SAW, t*(80 + 200*t))*0.3f)*env; } }
    base[SFX_BOOST] = MakeSound(b, len, 0.8f);
    /* roulette: rapid random blips */
    b = NewBuf(1.4f, &len);
    { unsigned int s = 5; for (int i = 0; i < 26; i++) { s = s*1103515245u + 12345u; int note = 72 + (int)((s >> 16) % 12); AddNote(b, len, i*0.052f, 0.035f, MidiHz((float)note), OSC_SQUARE25, 0.35f, 0.001f, 0.01f, 0.8f, 0.01f, 0, 0); } }
    base[SFX_ROULETTE] = MakeSound(b, len, 0.6f);
    /* item get: bell ding */
    b = NewBuf(0.8f, &len); AddNote(b, len, 0, 0.05f, 1318, OSC_SINE, 0.6f, 0.001f, 0.6f, 0.0f, 0.1f, 0, 0);
    AddNote(b, len, 0, 0.05f, 2637, OSC_SINE, 0.25f, 0.001f, 0.4f, 0.0f, 0.1f, 0, 0);
    AddNote(b, len, 0.07f, 0.05f, 1760, OSC_SQUARE25, 0.2f, 0.001f, 0.3f, 0.0f, 0.1f, 0, 0); base[SFX_ITEMGET] = MakeSound(b, len, 0.7f);
    /* throw */
    b = NewBuf(0.3f, &len); { float lp = 0; for (int i = 0; i < len; i++) { float t = (float)i/SR; lp += (Noise() - lp)*(0.4f - t); b[i] = lp*sinf(t/0.3f*PI); } } base[SFX_THROW] = MakeSound(b, len, 0.6f);
    /* hit: crash + falling bonk */
    b = NewBuf(0.6f, &len); for (int i = 0; i < len; i++) { float t = (float)i/SR; b[i] = Noise()*expf(-t*9)*0.8f; }
    AddNote(b, len, 0, 0.3f, 600, OSC_SQUARE50, 0.4f, 0.001f, 0.3f, 0.2f, 0.1f, 0, -2.5f); base[SFX_HIT] = MakeSound(b, len, 0.8f);
    /* bump: low thud */
    b = NewBuf(0.25f, &len); AddKick(b, len, 0, 1.0f); for (int i = 0; i < len; i++) b[i] += Noise()*expf(-(float)i/SR*40)*0.3f; base[SFX_BUMP] = MakeSound(b, len, 0.7f);
    /* spin out: descending warble */
    b = NewBuf(0.9f, &len); AddNote(b, len, 0, 0.75f, 900, OSC_SQUARE25, 0.4f, 0.005f, 0.1f, 0.8f, 0.1f, 0.08f, -1.1f); base[SFX_SPIN] = MakeSound(b, len, 0.6f);
    /* lap jingle */
    { int n[] = { 72, 76, 79, 84 }; b = NewBuf(0.9f, &len); Arp(b, len, n, 4, 0.09f, 0.08f, OSC_SQUARE25, 0.4f);
      AddNote(b, len, 0.36f, 0.3f, MidiHz(84), OSC_SQUARE50, 0.2f, 0.005f, 0.1f, 0.7f, 0.15f, 0.01f, 0); base[SFX_LAP] = MakeSound(b, len, 0.7f); }
    /* final lap fanfare */
    { int n[] = { 67, 67, 67, 72, 71, 72, 76, 79 }; float tm[] = { 0, 0.12f, 0.24f, 0.36f, 0.6f, 0.72f, 0.84f, 0.96f };
      b = NewBuf(2.0f, &len);
      for (int i = 0; i < 8; i++) { float d = (i == 7) ? 0.7f : 0.1f; AddNote(b, len, tm[i], d, MidiHz((float)n[i]), OSC_SQUARE25, 0.4f, 0.005f, 0.05f, 0.8f, 0.1f, 0.01f, 0);
        AddNote(b, len, tm[i], d, MidiHz((float)n[i] - 12), OSC_TRI, 0.3f, 0.005f, 0.05f, 0.8f, 0.1f, 0, 0); }
      AddSnare(b, len, 0.96f, 0.3f); AddKick(b, len, 0.96f, 0.5f);
      base[SFX_FINALLAP] = MakeSound(b, len, 0.8f); }
    /* finish fanfare */
    { int n[] = { 72, 76, 79, 84, 79, 84, 88 }; float tm[] = { 0, 0.14f, 0.28f, 0.42f, 0.7f, 0.84f, 1.0f };
      b = NewBuf(2.8f, &len);
      for (int i = 0; i < 7; i++) { float d = (i == 6) ? 1.2f : 0.12f; AddNote(b, len, tm[i], d, MidiHz((float)n[i]), OSC_SQUARE25, 0.4f, 0.005f, 0.05f, 0.8f, 0.2f, 0.012f, 0);
        AddNote(b, len, tm[i], d, MidiHz((float)n[i] - 5), OSC_SQUARE50, 0.12f, 0.005f, 0.05f, 0.8f, 0.2f, 0, 0); }
      AddNote(b, len, 1.0f, 1.2f, MidiHz(48), OSC_TRI, 0.4f, 0.01f, 0.1f, 0.8f, 0.3f, 0, 0);
      for (int i = 0; i < 4; i++) AddSnare(b, len, 0.7f + i*0.075f, 0.2f);
      AddKick(b, len, 1.0f, 0.6f);
      base[SFX_FINISH] = MakeSound(b, len, 0.85f); }
    b = NewBuf(0.08f, &len); AddNote(b, len, 0, 0.04f, 1200, OSC_SQUARE25, 0.4f, 0.001f, 0.02f, 0.6f, 0.02f, 0, 0); base[SFX_MENU_MOVE] = MakeSound(b, len, 0.5f);
    { int n[] = { 76, 84 }; b = NewBuf(0.3f, &len); Arp(b, len, n, 2, 0.07f, 0.07f, OSC_SQUARE25, 0.4f); base[SFX_MENU_OK] = MakeSound(b, len, 0.6f); }
    { int n[] = { 76, 69 }; b = NewBuf(0.3f, &len); Arp(b, len, n, 2, 0.07f, 0.07f, OSC_SQUARE25, 0.4f); base[SFX_MENU_BACK] = MakeSound(b, len, 0.6f); }
    /* peel drop: squishy bloop */
    b = NewBuf(0.3f, &len); AddNote(b, len, 0, 0.2f, 300, OSC_SINE, 0.7f, 0.002f, 0.1f, 0.5f, 0.05f, 0, 3.0f); base[SFX_PEEL] = MakeSound(b, len, 0.6f);
    /* disco: glittery arpeggio */
    { int n[] = { 72, 76, 79, 83, 84, 88, 91, 95, 96 }; b = NewBuf(1.2f, &len); Arp(b, len, n, 9, 0.06f, 0.1f, OSC_SQUARE12, 0.35f); base[SFX_DISCO] = MakeSound(b, len, 0.7f); }
    /* kazoo: buzzy bwaaam + thunder */
    b = NewBuf(1.5f, &len);
    AddNote(b, len, 0, 0.9f, 330, OSC_SAW, 0.45f, 0.02f, 0.1f, 0.9f, 0.2f, 0.03f, -0.35f);
    AddNote(b, len, 0, 0.9f, 333, OSC_SQUARE25, 0.25f, 0.02f, 0.1f, 0.9f, 0.2f, 0.03f, -0.35f);
    { float lp = 0; for (int i = 0; i < len; i++) { float t = (float)i/SR; lp += (Noise() - lp)*0.08f; b[i] += lp*2.0f*expf(-t*2.0f)*(t > 0.3f ? 1 : t/0.3f); } }
    base[SFX_KAZOO] = MakeSound(b, len, 0.8f);
    b = NewBuf(0.2f, &len); AddNote(b, len, 0, 0.12f, 400, OSC_SQUARE25, 0.4f, 0.002f, 0.05f, 0.6f, 0.05f, 0, 2.5f); base[SFX_HOP] = MakeSound(b, len, 0.4f);
    b = NewBuf(0.3f, &len); AddNote(b, len, 0, 0.05f, 1800, OSC_SQUARE12, 0.4f, 0.001f, 0.1f, 0.3f, 0.1f, 0, 1.5f);
    AddNote(b, len, 0.05f, 0.05f, 2400, OSC_SQUARE12, 0.3f, 0.001f, 0.1f, 0.3f, 0.1f, 0, 1.5f); base[SFX_SPARK] = MakeSound(b, len, 0.5f);
    b = NewBuf(0.5f, &len); for (int i = 0; i < len; i++) { float t = (float)i/SR; b[i] = Noise()*expf(-t*18)*0.5f; }
    { int n[] = { 84, 88, 91 }; Arp(b, len, n, 3, 0.04f, 0.05f, OSC_SQUARE12, 0.3f); } base[SFX_BOXBREAK] = MakeSound(b, len, 0.6f);
    b = NewBuf(0.5f, &len); AddNote(b, len, 0, 0.35f, 220, OSC_SQUARE50, 0.5f, 0.005f, 0.1f, 0.6f, 0.1f, 0.1f, -1.4f); base[SFX_SQUISH] = MakeSound(b, len, 0.6f);

    for (int i = 0; i < SFX_COUNT; i++) {
        sfx[i][0] = base[i];
        for (int a = 1; a < SFX_ALIASES; a++) sfx[i][a] = LoadSoundAlias(base[i]);
    }

    /* character voices: woo-hoo, ouch, yay (played back pitched per character) */
    Sound vb[3];
    b = NewBuf(0.75f, &len);
    VoiceSyllable(b, len, 0.0f, 0.22f, 260, 300, 400, 800, 450, 850, 1.0f);    /* "woo" */
    VoiceSyllable(b, len, 0.22f, 0.45f, 330, 420, 600, 1000, 380, 800, 1.0f);  /* "hoo!" */
    vb[0] = MakeSound(b, len, 0.8f);
    b = NewBuf(0.5f, &len);
    VoiceSyllable(b, len, 0.0f, 0.4f, 380, 200, 700, 1200, 350, 700, 1.0f);    /* "owww" */
    vb[1] = MakeSound(b, len, 0.8f);
    b = NewBuf(0.6f, &len);
    VoiceSyllable(b, len, 0.0f, 0.5f, 300, 450, 500, 1900, 750, 1500, 1.0f);   /* "yaay" */
    vb[2] = MakeSound(b, len, 0.8f);
    for (int i = 0; i < 3; i++) {
        voice[i][0] = vb[i];
        for (int a = 1; a < SFX_ALIASES; a++) voice[i][a] = LoadSoundAlias(vb[i]);
    }
}

void PlaySfx(SfxId id, float vol, float pitch)
{
    if (!audioOk || id < 0 || id >= SFX_COUNT) return;
    float v = vol*G.settings.sfxVol;
    if (v <= 0.01f) return;
    Sound s = sfx[id][sfxNext[id]];
    sfxNext[id] = (sfxNext[id] + 1) % SFX_ALIASES;
    SetSoundVolume(s, v > 1 ? 1 : v);
    SetSoundPitch(s, pitch);
    PlaySound(s);
}

void PlayVoice(int charId, int kind)
{
    if (!audioOk || kind < 0 || kind > 2) return;
    Sound s = voice[kind][voiceNext[kind]];
    voiceNext[kind] = (voiceNext[kind] + 1) % SFX_ALIASES;
    SetSoundVolume(s, 0.8f*G.settings.sfxVol);
    SetSoundPitch(s, CHARACTERS[charId].voicePitch);
    PlaySound(s);
}

void AudioInit(void)
{
    SetAudioStreamBufferSizeDefault(2048);
    InitAudioDevice();
    audioOk = IsAudioDeviceReady();
    if (!audioOk) { TraceLog(LOG_WARNING, "AUDIO: no audio device, running silent"); return; }

    double t0 = GetTime();
    /* songs: 4 tracks, title, results */
    for (int i = 0; i < NUM_TRACKS; i++) {
        const TrackDef *d = &TRACK_DEFS[i];
        GenSong(&songs[i], d->musicSeed, d->bpm, d->musicKey, d->musicScale, 2);
    }
    GenSong(&songs[MUSIC_TITLE], 101, 124, 60, 0, 1);
    GenSong(&songs[MUSIC_RESULTS], 7, 112, 65, 0, 0);
    BuildSfx();
    TraceLog(LOG_INFO, "AUDIO: synthesised music + sfx in %.2fs", GetTime() - t0);

    musicStream = LoadAudioStream(SR, 16, 1);
    SetAudioStreamCallback(musicStream, MusicCallback);
    PlayAudioStream(musicStream);
    for (int p = 0; p < MAX_HUMANS; p++) {
        memset(&eng[p], 0, sizeof(eng[p]));
        eng[p].hz = eng[p].targetHz = 50;
        engStream[p] = LoadAudioStream(SR, 16, 1);
        SetAudioStreamCallback(engStream[p], p == 0 ? EngineCb0 : EngineCb1);
        PlayAudioStream(engStream[p]);
    }
}

void AudioUpdate(void)
{
    if (!audioOk) return;
    musicVolume = G.settings.musicVol;
}

void AudioShutdown(void)
{
    if (!audioOk) return;
    StopAudioStream(musicStream);
    for (int p = 0; p < MAX_HUMANS; p++) StopAudioStream(engStream[p]);
    UnloadAudioStream(musicStream);
    for (int p = 0; p < MAX_HUMANS; p++) UnloadAudioStream(engStream[p]);
    for (int i = 0; i < SFX_COUNT; i++) {
        for (int a = 1; a < SFX_ALIASES; a++) UnloadSoundAlias(sfx[i][a]);
        UnloadSound(sfx[i][0]);
    }
    for (int i = 0; i < 3; i++) {
        for (int a = 1; a < SFX_ALIASES; a++) UnloadSoundAlias(voice[i][a]);
        UnloadSound(voice[i][0]);
    }
    CloseAudioDevice();
    for (int i = 0; i < NUM_SONGS; i++) { RL_FREE(songs[i].data); songs[i].data = NULL; }
}
