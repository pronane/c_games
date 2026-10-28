#ifndef GAELIC_AUDIO_H
#define GAELIC_AUDIO_H

#include "game.h"
#include "raylib.h"

typedef struct GameAudio {
    Music music;
    unsigned char *music_data;
    Sound crowd;
    Sound kick;
    Sound handpass;
    Sound cheer;
    Sound whistle;
    GameEvent previous_event;
    int initialized;
} GameAudio;

void game_audio_init(GameAudio *audio);
void game_audio_update(GameAudio *audio, GameEvent event);
void game_audio_shutdown(GameAudio *audio);

#endif
