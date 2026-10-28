#include "audio.h"

#include <math.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#define AUDIO_RATE 22050
#define RIFF_HEADER_SIZE 44

static void write_u16(unsigned char *buffer, int offset, uint16_t value)
{
    buffer[offset] = (unsigned char)(value & 0xff);
    buffer[offset + 1] = (unsigned char)((value >> 8) & 0xff);
}

static void write_u32(unsigned char *buffer, int offset, uint32_t value)
{
    buffer[offset] = (unsigned char)(value & 0xff);
    buffer[offset + 1] = (unsigned char)((value >> 8) & 0xff);
    buffer[offset + 2] = (unsigned char)((value >> 16) & 0xff);
    buffer[offset + 3] = (unsigned char)((value >> 24) & 0xff);
}

static void write_wave_header(unsigned char *buffer, int frames)
{
    int data_size = frames * 2;
    memcpy(buffer, "RIFF", 4);
    write_u32(buffer, 4, (uint32_t)(36 + data_size));
    memcpy(buffer + 8, "WAVEfmt ", 8);
    write_u32(buffer, 16, 16);
    write_u16(buffer, 20, 1);
    write_u16(buffer, 22, 1);
    write_u32(buffer, 24, AUDIO_RATE);
    write_u32(buffer, 28, AUDIO_RATE * 2);
    write_u16(buffer, 32, 2);
    write_u16(buffer, 34, 16);
    memcpy(buffer + 36, "data", 4);
    write_u32(buffer, 40, (uint32_t)data_size);
}

static uint32_t random_next(uint32_t *state)
{
    *state = *state * 1664525u + 1013904223u;
    return *state;
}

static void add_note(float *mix, int frames, float start, float duration,
                     float frequency, float volume, int square)
{
    int begin = (int)(start * AUDIO_RATE);
    int count = (int)(duration * AUDIO_RATE);
    float phase = 0.0f;
    int i;

    for (i = 0; i < count && begin + i < frames; i++) {
        float t = (float)i / (float)count;
        float envelope = t < 0.06f ? t / 0.06f : 1.0f - t;
        float value;
        phase += frequency / (float)AUDIO_RATE;
        if (phase >= 1.0f) phase -= 1.0f;
        value = square ? (phase < 0.5f ? 1.0f : -1.0f) :
                         (phase < 0.5f ? phase * 4.0f - 1.0f :
                          3.0f - phase * 4.0f);
        mix[begin + i] += value * envelope * volume;
    }
}

static unsigned char *make_music_wave(int *byte_count)
{
    static const int melody[32] = {
        74, 0, 78, 81, 0, 78, 74, 0, 76, 0, 79, 83, 0, 79, 76, 0,
        74, 0, 78, 81, 0, 86, 83, 0, 81, 0, 79, 76, 74, 0, 0, 0
    };
    static const int bass[4] = {50, 45, 47, 43};
    const int frames = AUDIO_RATE * 8;
    float *mix = (float *)calloc((size_t)frames, sizeof(float));
    unsigned char *wave;
    uint32_t noise_state = 0x4c414e44u;
    int i;

    if (!mix) return NULL;

    for (i = 0; i < 32; i++) {
        int midi = melody[i];
        float start = (float)i * 0.25f;
        if (midi > 0) {
            float frequency = 440.0f * powf(2.0f, (float)(midi - 69) / 12.0f);
            add_note(mix, frames, start, 0.19f, frequency, 0.17f, 1);
        }
        if ((i % 2) == 0) {
            int bass_note = bass[(i / 8) % 4];
            float frequency = 440.0f * powf(2.0f, (float)(bass_note - 69) / 12.0f);
            add_note(mix, frames, start, 0.23f, frequency, 0.12f, 0);
        }
    }

    for (i = 0; i < 16; i++) {
        int begin = (int)((float)i * 0.5f * AUDIO_RATE);
        int j;
        for (j = 0; j < AUDIO_RATE / 8 && begin + j < frames; j++) {
            float t = (float)j / (float)(AUDIO_RATE / 8);
            float envelope = (1.0f - t) * (1.0f - t);
            float kick = sinf(2.0f * 3.14159265f *
                             (72.0f - 42.0f * t) * (float)j / AUDIO_RATE);
            float snare = ((int)(random_next(&noise_state) >> 24) - 128) / 128.0f;
            mix[begin + j] += kick * envelope * 0.22f;
            if (i % 4 == 1)
                mix[begin + j] += snare * envelope * 0.07f;
        }
    }

    *byte_count = RIFF_HEADER_SIZE + frames * 2;
    wave = (unsigned char *)malloc((size_t)*byte_count);
    if (!wave) {
        free(mix);
        return NULL;
    }

    write_wave_header(wave, frames);
    for (i = 0; i < frames; i++) {
        float sample = mix[i] * 0.68f;
        int value;
        if (sample > 0.95f) sample = 0.95f;
        if (sample < -0.95f) sample = -0.95f;
        value = (int)(sample * 32767.0f);
        write_u16(wave, RIFF_HEADER_SIZE + i * 2, (uint16_t)(int16_t)value);
    }

    free(mix);
    return wave;
}

static Sound make_sound(const int16_t *samples, unsigned int frame_count)
{
    Wave wave = {0};
    Sound sound;
    wave.frameCount = frame_count;
    wave.sampleRate = AUDIO_RATE;
    wave.sampleSize = 16;
    wave.channels = 1;
    wave.data = (void *)samples;
    sound = LoadSoundFromWave(wave);
    return sound;
}

static Sound make_crowd_sound(void)
{
    const unsigned int frames = AUDIO_RATE * 5;
    int16_t *samples = (int16_t *)malloc((size_t)frames * sizeof(int16_t));
    uint32_t state = 0x53454354u;
    float low = 0.0f;
    unsigned int i;
    Sound sound = {0};

    if (!samples) return sound;
    for (i = 0; i < frames; i++) {
        float noise = (float)(int32_t)random_next(&state) / 2147483648.0f;
        float breathe = 0.65f + 0.35f * sinf((float)i * 6.2831853f /
                                             (float)AUDIO_RATE * 0.31f);
        low += (noise - low) * 0.018f;
        samples[i] = (int16_t)(low * breathe * 4100.0f);
    }
    sound = make_sound(samples, frames);
    free(samples);
    return sound;
}

static Sound make_kick_sound(void)
{
    const unsigned int frames = AUDIO_RATE / 3;
    int16_t *samples = (int16_t *)malloc((size_t)frames * sizeof(int16_t));
    unsigned int i;
    Sound sound = {0};
    if (!samples) return sound;
    for (i = 0; i < frames; i++) {
        float t = (float)i / (float)AUDIO_RATE;
        float envelope = expf(-t * 20.0f);
        float low = sinf(2.0f * 3.14159265f * (82.0f - 45.0f * t) * t);
        samples[i] = (int16_t)(low * envelope * 18000.0f);
    }
    sound = make_sound(samples, frames);
    free(samples);
    return sound;
}

static Sound make_whistle_sound(void)
{
    const unsigned int frames = AUDIO_RATE * 3 / 4;
    int16_t *samples = (int16_t *)malloc((size_t)frames * sizeof(int16_t));
    unsigned int i;
    Sound sound = {0};
    if (!samples) return sound;
    for (i = 0; i < frames; i++) {
        float t = (float)i / (float)frames;
        float envelope = sinf(t * 3.14159265f);
        float vibrato = 1.0f + 0.012f * sinf(t * 80.0f);
        float value = sinf(t * 6.2831853f * 2100.0f * vibrato) * 0.75f +
                      sinf(t * 6.2831853f * 3150.0f) * 0.25f;
        samples[i] = (int16_t)(value * envelope * 13000.0f);
    }
    sound = make_sound(samples, frames);
    free(samples);
    return sound;
}

static Sound make_cheer_sound(void)
{
    const unsigned int frames = AUDIO_RATE * 2;
    int16_t *samples = (int16_t *)malloc((size_t)frames * sizeof(int16_t));
    uint32_t state = 0x43484545u;
    float low = 0.0f;
    unsigned int i;
    Sound sound = {0};
    if (!samples) return sound;
    for (i = 0; i < frames; i++) {
        float t = (float)i / (float)frames;
        float noise = (float)(int32_t)random_next(&state) / 2147483648.0f;
        float envelope = sinf(t * 3.14159265f);
        low += (noise - low) * 0.12f;
        samples[i] = (int16_t)(low * envelope * 16000.0f);
    }
    sound = make_sound(samples, frames);
    free(samples);
    return sound;
}

void game_audio_init(GameAudio *audio)
{
    unsigned char *music_data;
    int music_size = 0;

    memset(audio, 0, sizeof(*audio));
    InitAudioDevice();
    if (!IsAudioDeviceReady()) {
        TraceLog(LOG_WARNING, "Audio device unavailable; continuing without sound.");
        return;
    }

    music_data = make_music_wave(&music_size);
    if (music_data) {
        audio->music = LoadMusicStreamFromMemory(".wav", music_data, music_size);
        audio->music_data = music_data;
        if (IsMusicValid(audio->music)) {
            audio->music.looping = true;
            SetMusicVolume(audio->music, 0.17f);
            PlayMusicStream(audio->music);
        } else {
            TraceLog(LOG_WARNING, "Could not load the generated match music.");
        }
    } else {
        TraceLog(LOG_WARNING, "Could not allocate generated match music.");
    }

    audio->crowd = make_crowd_sound();
    audio->kick = make_kick_sound();
    audio->handpass = make_kick_sound();
    audio->cheer = make_cheer_sound();
    audio->whistle = make_whistle_sound();
    if (audio->crowd.frameCount > 0) SetSoundVolume(audio->crowd, 0.19f);
    if (audio->kick.frameCount > 0) SetSoundVolume(audio->kick, 0.6f);
    if (audio->handpass.frameCount > 0) SetSoundVolume(audio->handpass, 0.35f);
    if (audio->cheer.frameCount > 0) SetSoundVolume(audio->cheer, 0.55f);
    if (audio->whistle.frameCount > 0) SetSoundVolume(audio->whistle, 0.45f);
    audio->previous_event = GAME_EVENT_NONE;
    audio->initialized = 1;
    if (audio->crowd.frameCount > 0) PlaySound(audio->crowd);
    else TraceLog(LOG_WARNING, "Could not create generated crowd ambience.");
}

void game_audio_update(GameAudio *audio, GameEvent event)
{
    if (!audio->initialized) return;
    if (IsMusicValid(audio->music)) UpdateMusicStream(audio->music);
    if (audio->crowd.frameCount > 0 && !IsSoundPlaying(audio->crowd))
        PlaySound(audio->crowd);

    if (event != audio->previous_event && event != GAME_EVENT_NONE) {
        if (event == GAME_EVENT_GOAL || event == GAME_EVENT_POINT) {
            if (audio->cheer.frameCount > 0) PlaySound(audio->cheer);
        } else if (event == GAME_EVENT_FOUR_STEPS ||
                   event == GAME_EVENT_ILLEGAL_BOUNCE) {
            if (audio->whistle.frameCount > 0) PlaySound(audio->whistle);
        } else if (event == GAME_EVENT_KICKED) {
            if (audio->kick.frameCount > 0) PlaySound(audio->kick);
        } else if (event == GAME_EVENT_HANDPASSED ||
                   event == GAME_EVENT_BOUNCED ||
                   event == GAME_EVENT_HIGH_FIELD) {
            if (audio->handpass.frameCount > 0) PlaySound(audio->handpass);
        }
    }
    audio->previous_event = event;
}

void game_audio_shutdown(GameAudio *audio)
{
    if (!audio->initialized) return;
    if (IsMusicValid(audio->music)) {
        StopMusicStream(audio->music);
        UnloadMusicStream(audio->music);
    }
    free(audio->music_data);
    if (audio->crowd.frameCount > 0) UnloadSound(audio->crowd);
    if (audio->kick.frameCount > 0) UnloadSound(audio->kick);
    if (audio->handpass.frameCount > 0) UnloadSound(audio->handpass);
    if (audio->cheer.frameCount > 0) UnloadSound(audio->cheer);
    if (audio->whistle.frameCount > 0) UnloadSound(audio->whistle);
    CloseAudioDevice();
    audio->initialized = 0;
}
