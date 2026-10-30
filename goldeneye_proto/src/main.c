/*
 * FACILITY 64 - a small late-90s console-FPS inspired prototype (C99 + raylib)
 *
 * Everything is generated in code: textures (gfx_textures.c), meshes and
 * characters (gfx_models.c), lighting (baked per-vertex + a GLSL 330 shader with
 * dynamic muzzle lights and fog), sounds.  Generated textures can be exported to
 * assets/textures/NAME.png with  --export-textures  and are loaded from there if present.
 *
 * Mission mode : one bunker level, Bond-style objectives, patrolling guards
 *                that react to gunfire noise and line of sight.
 * Deathmatch   : 2-4 player split screen (join-in lobby), first to 5 kills, Golden Gun pickup.
 * Controllers  : up to 4 gamepads, styles/remap/options/debug, controls.cfg (input_pad.c).
 *
 * Unity build: this file #includes the other .c files, so only main.c is compiled.
 */
#include "raylib.h"
#include "raymath.h"
#include "rlgl.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>

/* depth-only clear for the first-person weapon (rlgl has no wrapper for it) */
#if defined(_WIN32)
__declspec(dllimport) void __stdcall glClear(unsigned int mask);
#else
extern void glClear(unsigned int mask);
#endif
#define GL_DEPTH_BUFFER_BIT_ 0x00000100

#include "gfx_textures.c"
#include "gfx_models.c"

/* ------------------------------------------------------------------ */
/* Constants                                                           */
/* ------------------------------------------------------------------ */
#define SCREEN_W 1280
#define SCREEN_H 720

#define MAP_W 28
#define MAP_H 16
#define TILE 2.0f
#define WALL_H 3.0f
#define EYE_H 1.6f
#define PLAYER_R 0.3f
#define ENEMY_R 0.3f

#define MAX_ENEMIES 32
#define MAX_PICKUPS 64
#define MAX_SPAWNS 16
#define MAX_PROPS 64
#define MAX_LIGHTS 48
#define MAX_PARTICLES 600
#define MAX_DECALS 160

#define QUIET_RESET_TIME 2.5f   /* seconds of silence before the noise radius resets */
#define KILL_LIMIT 5

/*
 * Level legend
 *   #  wall          D  door            L  locked door (shoot the lock)
 *   W  interior window, O exterior window (player sees through, guards cannot, bullet-proof)
 *   P  player start  S  deathmatch spawn
 *   < > ^ v  guard, initial patrol direction
 *   A  ammo   H  body armour   K  data disk   X  extraction
 *   G  golden gun (deathmatch only)
 */
static const char *LEVEL[MAP_H] = {
    "#########O#O#####O#O####O###",
    "#.....#.......#......#....X#",
    "#..S..#...<...#..A...#.....#",
    "#.....D.......W......D...<.#",
    "#.....#.......W...v..#..S..#",
    "##D####.......#......###D###",
    "#.....####D#######D###.....#",
    "#..H..#..............#.....O",
    "O.....D..>...G.......D..^..#",
    "#..S..#..............#..A..#",
    "##D######D###D#W########D###",
    "#.....#....#.v..#....#.....#",
    "#.....#.A..#....#....#..H..#",
    "O..P..D....D....L..K.#..S..#",
    "#.....#....#....#....#.....#",
    "############################",
};

/* ------------------------------------------------------------------ */
/* Types                                                               */
/* ------------------------------------------------------------------ */
typedef enum { T_FLOOR, T_WALL, T_DOOR, T_LOCKED, T_WINDOW } TileType;
typedef enum { GS_TITLE, GS_MISSION, GS_DM, GS_LOBBY } GameState;
#define MAX_PLAYERS 4
typedef enum { W_PP7, W_KF7, W_GOLDEN, W_COUNT } WeaponId;
typedef enum { E_PATROL, E_ALERT, E_ATTACK, E_DEAD } EnemyState;
typedef enum { PK_AMMO, PK_HEALTH, PK_DISK, PK_GOLDEN, PK_KF7 } PickupType;
typedef enum { HIT_NONE, HIT_WORLD, HIT_LOCK, HIT_ENEMY, HIT_PLAYER } HitKind;

typedef struct {
    const char *name;
    int magSize;
    float fireDelay;
    float damage;
    float noise;        /* base alert radius in world units */
    bool automatic;
    float reloadTime;
    float spread;
} WeaponDef;

static const WeaponDef WEAPONS[W_COUNT] = {
    { "PP7",        7,  0.28f, 34.0f,   12.0f, false, 1.2f, 0.006f },
    { "KF7 SOVIET", 30, 0.10f, 22.0f,   18.0f, true,  1.8f, 0.025f },
    { "GOLDEN GUN", 1,  0.40f, 1000.0f, 12.0f, false, 1.5f, 0.0f   },
};
#define PP7_SILENCED_NOISE 3.0f

typedef struct {
    Vector3 pos;
    float yaw, pitch;
    float health;
    bool alive;
    int weapon;
    bool has[W_COUNT];
    int mag[W_COUNT];
    int reserve[W_COUNT];
    bool silencer;
    float fireCooldown, reloadTimer, muzzle, hurtFlash, bob, respawnTimer;
    float kick, raise, moveAmt, spreadVis, flashRot, deathT;
    int kills, shots, hits, headshots;
    char msg[96];
    float msgTimer;
    Color suit;
    int variant;
    float aimZoom;
} Player;

typedef struct {
    float move, strafe, turn, look;
    bool fire, firePressed, reload, nextWeapon, use, silencer, aim;
    int selectWeapon; /* -1 none */
} PlayerInput;

typedef struct {
    Vector3 pos;
    float yaw;
    float pdx, pdz;     /* patrol direction */
    EnemyState state;
    float hp;
    Vector3 target;     /* last known / investigated position */
    float shootTimer, alertTimer, hurtFlash, deathT, muzzle;
    float walk, speed, aim, deathDir;
    int variant;
} Enemy;

typedef struct {
    Vector3 pos;
    PickupType type;
    bool active;
    bool respawns;
    float respawnTimer;
    float yaw;
} Pickup;

typedef struct {
    float dist;
    HitKind kind;
    int index;
    int tx, tz;
    bool head;
    Vector3 point, normal;
} Hit;

typedef struct { const char *text; bool done; } Objective;

/* graphics-side types */
typedef enum { PR_CRATE, PR_CRATESTACK, PR_BARREL, PR_DESK, PR_RACK, PR_PILLAR } PropType;
typedef struct { PropType type; Vector3 pos; float rot; BoundingBox box; } Prop;
typedef struct { Vector3 pos; Vector3 col; float radius; bool fixture; } Light;
typedef enum { P_SPARK, P_DUST, P_SMOKE, P_SHELL, P_CHIP, P_GLINT } PartType;
typedef struct { PartType type; Vector3 pos, vel; float life, maxLife, size, rot; Color col; } Particle;
typedef struct { Vector3 pos, n, light; float life, size, rot; } Decal;
typedef struct { int wall, floor, ceil; } Theme;

/* ------------------------------------------------------------------ */
/* Globals                                                             */
/* ------------------------------------------------------------------ */
static int tiles[MAP_H][MAP_W];
static float doorOpen[MAP_H][MAP_W];   /* 0 closed .. 1 open */
static float doorTimer[MAP_H][MAP_W];  /* time left before auto close */
static bool doorOpening[MAP_H][MAP_W];
static bool axisX[MAP_H][MAP_W];       /* passage through tile runs along X */
static bool propBlock[MAP_H][MAP_W];   /* tile has a prop: avoided by guard pathing */
static int bfsDist[MAP_H][MAP_W];

static GameState gState = GS_TITLE;
static bool gPaused = false;
static int gMissionResult = 0;      /* 0 playing, 1 complete, 2 failed */
static float gMissionTime = 0.0f;
static int gDmWinner = -1;
static float gTime = 0.0f;

static Player players[MAX_PLAYERS];
static void PadRumbleSlot(int slot, float lo, float hi, float dur);   /* input_pad.c */
static bool PlayerUsesPad(const Player *p);
static int numPlayers = 1;
static Enemy enemies[MAX_ENEMIES];
static int numEnemies = 0;
static Pickup pickups[MAX_PICKUPS];
static int numPickups = 0;
static int goldenPickup = -1;
static Vector3 spawns[MAX_SPAWNS];
static int numSpawns = 0;
static Vector3 missionStart;
static int exitX = -1, exitZ = -1;

static Prop props[MAX_PROPS];
static int numProps = 0;
static Light lights[MAX_LIGHTS];
static int numLights = 0;
static Particle parts[MAX_PARTICLES];
static int partNext = 0;
static Decal decals[MAX_DECALS];
static int decalNext = 0;

static Objective objs[3] = {
    { "Destroy the lock on the armoury door", false },
    { "Recover the GoldenEye data disk", false },
    { "Reach the extraction point", false },
};

static int shotHeat = 0;
static float lastShotTime = -100.0f;
static float noiseRadius = 0.0f;
static float noiseShow = 0.0f;
static int missionKills = 0;

/* sounds */
static bool audioOk = false;
static Sound sfxShot, sfxSilenced, sfxEnemyShot, sfxClick, sfxPickup, sfxDoor, sfxHurt, sfxReload, sfxRicochet;

/* ------------------------------------------------------------------ */
/* Small helpers                                                       */
/* ------------------------------------------------------------------ */
static float Frand(void) { return (float)rand() / (float)RAND_MAX; }
static float Frand2(void) { return Frand()*2.0f - 1.0f; }
static float WrapPi(float a) { while (a > PI) a -= 2*PI; while (a < -PI) a += 2*PI; return a; }
static int ToTile(float v) { return (int)floorf(v / TILE); }
static bool InMap(int x, int z) { return x >= 0 && z >= 0 && x < MAP_W && z < MAP_H; }
static Vector3 TileCenter(int x, int z) { return (Vector3){ x*TILE + TILE*0.5f, 0.0f, z*TILE + TILE*0.5f }; }
static float Dist2D(Vector3 a, Vector3 b) { float dx = a.x-b.x, dz = a.z-b.z; return sqrtf(dx*dx + dz*dz); }
static float Smooth01(float e0, float e1, float x) { float t = Clamp((x - e0)/(e1 - e0), 0, 1); return t*t*(3 - 2*t); }
static char LevelChar(int x, int z) { return InMap(x, z) ? LEVEL[z][x] : '#'; }

static void Sfx(Sound s) { if (audioOk) PlaySound(s); }

static void SetMsg(Player *p, const char *text)
{
    strncpy(p->msg, text, sizeof(p->msg) - 1);
    p->msg[sizeof(p->msg) - 1] = 0;
    p->msgTimer = 2.5f;
}

static bool TileBlocksMove(int x, int z)
{
    if (!InMap(x, z)) return true;
    int t = tiles[z][x];
    if (t == T_WALL || t == T_WINDOW || t == T_LOCKED) return true;
    if (t == T_DOOR) return doorOpen[z][x] < 0.9f;
    return false;
}

static bool TileBlocksSight(int x, int z)
{
    if (!InMap(x, z)) return true;
    int t = tiles[z][x];
    if (t == T_WALL || t == T_WINDOW || t == T_LOCKED) return true; /* guards can't see through windows */
    if (t == T_DOOR) return doorOpen[z][x] < 0.7f;
    return false;
}

static bool LineOfSight(Vector3 a, Vector3 b)
{
    float dx = b.x - a.x, dz = b.z - a.z;
    float d = sqrtf(dx*dx + dz*dz);
    int steps = (int)(d / 0.2f) + 1;
    for (int i = 1; i < steps; i++) {
        float t = (float)i / (float)steps;
        if (TileBlocksSight(ToTile(a.x + dx*t), ToTile(a.z + dz*t))) return false;
    }
    return true;
}

/* ------------------------------------------------------------------ */
/* Sound generation (no asset files)                                   */
/* ------------------------------------------------------------------ */
static Sound MakeNoiseSfx(float dur, float decay, float lowpass, float vol, float toneHz)
{
    int rate = 22050;
    int n = (int)(dur * rate);
    short *data = (short *)MemAlloc(n * sizeof(short));
    float prev = 0.0f;
    for (int i = 0; i < n; i++) {
        float t = (float)i / rate;
        float env = expf(-t * decay);
        float r = Frand()*2.0f - 1.0f;
        prev += lowpass * (r - prev);
        float s = prev;
        if (toneHz > 0.0f) s = 0.6f*sinf(2*PI*toneHz*t) + 0.4f*prev;
        float v = s * env * vol;
        if (v > 1) v = 1;
        if (v < -1) v = -1;
        data[i] = (short)(v * 32000.0f);
    }
    Wave w = { 0 };
    w.frameCount = (unsigned int)n;
    w.sampleRate = (unsigned int)rate;
    w.sampleSize = 16;
    w.channels = 1;
    w.data = data;
    Sound s = LoadSoundFromWave(w);
    UnloadWave(w);
    return s;
}

static void InitSounds(void)
{
    InitAudioDevice();
    audioOk = IsAudioDeviceReady();
    if (!audioOk) return;
    sfxShot      = MakeNoiseSfx(0.35f, 14.0f, 0.9f, 1.0f, 0.0f);
    sfxSilenced  = MakeNoiseSfx(0.15f, 30.0f, 0.15f, 1.2f, 0.0f);
    sfxEnemyShot = MakeNoiseSfx(0.30f, 16.0f, 0.6f, 0.7f, 0.0f);
    sfxClick     = MakeNoiseSfx(0.05f, 80.0f, 1.0f, 0.5f, 1800.0f);
    sfxPickup    = MakeNoiseSfx(0.20f, 10.0f, 0.1f, 0.5f, 880.0f);
    sfxDoor      = MakeNoiseSfx(0.60f, 4.0f, 0.05f, 0.9f, 70.0f);
    sfxHurt      = MakeNoiseSfx(0.20f, 12.0f, 0.3f, 0.8f, 160.0f);
    sfxReload    = MakeNoiseSfx(0.10f, 40.0f, 0.8f, 0.5f, 600.0f);
    sfxRicochet  = MakeNoiseSfx(0.18f, 22.0f, 0.5f, 0.35f, 2400.0f);
}

static void UnloadSounds(void)
{
    if (!audioOk) return;
    UnloadSound(sfxShot); UnloadSound(sfxSilenced); UnloadSound(sfxEnemyShot); UnloadSound(sfxClick);
    UnloadSound(sfxPickup); UnloadSound(sfxDoor); UnloadSound(sfxHurt); UnloadSound(sfxReload); UnloadSound(sfxRicochet);
    CloseAudioDevice();
}

/* ------------------------------------------------------------------ */
/* Props (shared by collision, bullets, rendering)                     */
/* ------------------------------------------------------------------ */
static void AddProp(PropType type, float tx, float tz, float ox, float oz, float rot)
{
    if (numProps >= MAX_PROPS) return;
    Prop *p = &props[numProps++];
    p->type = type; p->rot = rot;
    p->pos = (Vector3){ (tx + 0.5f)*TILE + ox, 0, (tz + 0.5f)*TILE + oz };
    float sx = 1.1f, sy = 1.1f, sz = 1.1f;
    switch (type) {
        case PR_CRATE:      sx = sz = 1.1f; sy = 1.1f; break;
        case PR_CRATESTACK: sx = sz = 1.2f; sy = 2.05f; break;
        case PR_BARREL:     sx = sz = 0.78f; sy = 1.15f; break;
        case PR_DESK:       sx = 1.7f; sz = 0.85f; sy = 0.78f; break;
        case PR_RACK:       sx = 1.1f; sz = 0.8f; sy = 2.2f; break;
        case PR_PILLAR:     sx = sz = 0.9f; sy = WALL_H; break;
    }
    if (fabsf(sinf(rot)) > 0.7f) { float t = sx; sx = sz; sz = t; }
    p->box = (BoundingBox){ { p->pos.x - sx*0.5f, 0, p->pos.z - sz*0.5f }, { p->pos.x + sx*0.5f, sy, p->pos.z + sz*0.5f } };
    propBlock[(int)tz][(int)tx] = true;
}

static void SetupProps(void)
{
    numProps = 0;
    memset(propBlock, 0, sizeof(propBlock));
    /* R1 */ AddProp(PR_CRATESTACK, 1, 1, -0.3f, -0.3f, 0); AddProp(PR_DESK, 4, 1, 0, -0.45f, 0); AddProp(PR_BARREL, 5, 4, 0.3f, 0.2f, 0);
    /* R2 */ AddProp(PR_DESK, 8, 1, 0, -0.45f, 0); AddProp(PR_DESK, 12, 1, 0, -0.45f, 0); AddProp(PR_CRATE, 7, 5, -0.3f, 0.3f, 0.3f);
    /* R3 */ AddProp(PR_DESK, 16, 1, 0, -0.45f, 0); AddProp(PR_RACK, 20, 1, 0.25f, -0.3f, 0); AddProp(PR_BARREL, 20, 5, 0.4f, 0.4f, 0);
    /* R4 */ AddProp(PR_CRATESTACK, 22, 1, -0.3f, -0.3f, 0); AddProp(PR_BARREL, 22, 4, -0.4f, 0.4f, 0);
    /* R5 */ AddProp(PR_CRATE, 1, 6, -0.3f, -0.3f, 0.2f); AddProp(PR_CRATE, 5, 6, 0.3f, -0.3f, 0); AddProp(PR_BARREL, 1, 9, -0.4f, 0.4f, 0);
    /* hall pillars */ AddProp(PR_PILLAR, 11, 7, 0, -0.55f, 0); AddProp(PR_PILLAR, 11, 9, 0, 0.55f, 0); AddProp(PR_PILLAR, 16, 7, 0, -0.55f, 0); AddProp(PR_PILLAR, 16, 9, 0, 0.55f, 0);
    /* R7 */ AddProp(PR_BARREL, 26, 6, 0.4f, -0.4f, 0); AddProp(PR_BARREL, 22, 6, -0.4f, -0.4f, 0); AddProp(PR_CRATE, 22, 9, -0.3f, 0.3f, 0.15f);
    /* R8 */ AddProp(PR_CRATE, 1, 11, -0.3f, -0.3f, 0); AddProp(PR_CRATESTACK, 5, 14, 0.3f, 0.3f, 0);
    /* R9 */ AddProp(PR_CRATESTACK, 7, 11, -0.3f, -0.3f, 0); AddProp(PR_CRATE, 10, 11, 0.3f, -0.3f, 0.4f); AddProp(PR_CRATE, 7, 14, -0.3f, 0.3f, 0); AddProp(PR_CRATESTACK, 10, 14, 0.3f, 0.3f, 0);
    /* R10 */ AddProp(PR_RACK, 12, 11, -0.3f, -0.35f, 0); AddProp(PR_RACK, 12, 14, -0.3f, 0.35f, 0); AddProp(PR_RACK, 15, 14, 0.3f, 0.35f, 0);
    /* R11 */ AddProp(PR_CRATE, 17, 11, -0.3f, -0.3f, 0); AddProp(PR_CRATE, 20, 11, 0.3f, -0.3f, 0.25f); AddProp(PR_CRATE, 20, 14, 0.3f, 0.3f, 0);
    /* R12 */ AddProp(PR_BARREL, 26, 11, 0.4f, -0.4f, 0); AddProp(PR_CRATESTACK, 22, 14, -0.3f, 0.3f, 0); AddProp(PR_CRATESTACK, 26, 14, 0.3f, 0.3f, 0);
}

/* ------------------------------------------------------------------ */
/* Level                                                               */
/* ------------------------------------------------------------------ */
static void AddPickup(Vector3 pos, PickupType type, bool respawns)
{
    if (numPickups >= MAX_PICKUPS) return;
    Pickup *p = &pickups[numPickups++];
    p->pos = pos; p->type = type; p->active = true; p->respawns = respawns; p->respawnTimer = 0;
    p->yaw = Frand()*2*PI;
}

static void AddEnemy(Vector3 pos, float dx, float dz)
{
    if (numEnemies >= MAX_ENEMIES) return;
    Enemy *e = &enemies[numEnemies];
    memset(e, 0, sizeof(*e));
    e->pos = pos; e->pdx = dx; e->pdz = dz;
    e->yaw = atan2f(dz, dx);
    e->state = E_PATROL;
    e->hp = 60.0f;
    e->variant = numEnemies % 3;
    e->walk = Frand()*6.0f;
    numEnemies++;
}

static void LoadLevel(bool dm)
{
    numEnemies = 0; numPickups = 0; numSpawns = 0; goldenPickup = -1;
    memset(decals, 0, sizeof(decals));
    memset(parts, 0, sizeof(parts));
    for (int z = 0; z < MAP_H; z++) {
        for (int x = 0; x < MAP_W; x++) {
            char c = LEVEL[z][x];
            Vector3 p = TileCenter(x, z);
            doorOpen[z][x] = 0; doorTimer[z][x] = 0; doorOpening[z][x] = false;
            switch (c) {
                case '#': tiles[z][x] = T_WALL; break;
                case 'D': tiles[z][x] = T_DOOR; break;
                case 'L': tiles[z][x] = dm ? T_DOOR : T_LOCKED; break;
                case 'W': case 'O': tiles[z][x] = T_WINDOW; break;
                default:  tiles[z][x] = T_FLOOR; break;
            }
            if (c == 'P') { missionStart = p; if (numSpawns < MAX_SPAWNS) spawns[numSpawns++] = p; }
            if (c == 'S' && numSpawns < MAX_SPAWNS) spawns[numSpawns++] = p;
            if (!dm) {
                if (c == '>') AddEnemy(p, 1, 0);
                if (c == '<') AddEnemy(p, -1, 0);
                if (c == 'v') AddEnemy(p, 0, 1);
                if (c == '^') AddEnemy(p, 0, -1);
                if (c == 'K') AddPickup((Vector3){ p.x, 0.0f, p.z }, PK_DISK, false);
            } else if (c == 'G') {
                goldenPickup = numPickups;
                AddPickup(p, PK_GOLDEN, false);
            }
            if (c == 'A') AddPickup(p, PK_AMMO, true);
            if (c == 'H') AddPickup(p, PK_HEALTH, true);
            if (c == 'X') { exitX = x; exitZ = z; }
        }
    }
    for (int z = 0; z < MAP_H; z++)
        for (int x = 0; x < MAP_W; x++) {
            bool l = InMap(x-1, z) && tiles[z][x-1] != T_WALL;
            bool r = InMap(x+1, z) && tiles[z][x+1] != T_WALL;
            axisX[z][x] = l || r;
        }
    SetupProps();
}

static bool CircleOverlapsTile(float x, float z, float r, int tx, int tz)
{
    float cx = Clamp(x, tx*TILE, tx*TILE + TILE);
    float cz = Clamp(z, tz*TILE, tz*TILE + TILE);
    float dx = x - cx, dz = z - cz;
    return dx*dx + dz*dz < r*r;
}

static bool CircleOverlapsBox(float x, float z, float r, BoundingBox b)
{
    float cx = Clamp(x, b.min.x, b.max.x), cz = Clamp(z, b.min.z, b.max.z);
    float dx = x - cx, dz = z - cz;
    return dx*dx + dz*dz < r*r;
}

static bool AnyActorInTile(int tx, int tz)
{
    for (int i = 0; i < numPlayers; i++)
        if (players[i].alive && CircleOverlapsTile(players[i].pos.x, players[i].pos.z, PLAYER_R + 0.05f, tx, tz)) return true;
    for (int i = 0; i < numEnemies; i++)
        if (enemies[i].state != E_DEAD && CircleOverlapsTile(enemies[i].pos.x, enemies[i].pos.z, ENEMY_R + 0.05f, tx, tz)) return true;
    return false;
}

static void OpenDoor(int x, int z)
{
    if (!InMap(x, z) || tiles[z][x] != T_DOOR) return;
    if (!doorOpening[z][x] && doorOpen[z][x] < 0.5f) Sfx(sfxDoor);
    doorOpening[z][x] = true;
    doorTimer[z][x] = 5.0f;
}

static void UpdateDoors(float dt)
{
    for (int z = 0; z < MAP_H; z++)
        for (int x = 0; x < MAP_W; x++) {
            if (tiles[z][x] != T_DOOR) continue;
            if (doorOpening[z][x]) {
                doorOpen[z][x] = fminf(1.0f, doorOpen[z][x] + dt*1.6f);
                doorTimer[z][x] -= dt;
                if (doorTimer[z][x] <= 0.0f) {
                    if (AnyActorInTile(x, z)) doorTimer[z][x] = 1.0f;
                    else doorOpening[z][x] = false;
                }
            } else if (doorOpen[z][x] > 0.0f) {
                if (AnyActorInTile(x, z)) { doorOpening[z][x] = true; doorTimer[z][x] = 1.0f; }
                else doorOpen[z][x] = fmaxf(0.0f, doorOpen[z][x] - dt*1.2f);
            }
        }
}

/* returns true if blocked; records a bumped door / locked door */
static bool CircleHitsSolid(float x, float z, float r, int *doorX, int *doorZ, bool *bumpLocked)
{
    int x0 = ToTile(x - r), x1 = ToTile(x + r), z0 = ToTile(z - r), z1 = ToTile(z + r);
    bool hit = false;
    for (int tz = z0; tz <= z1; tz++)
        for (int tx = x0; tx <= x1; tx++) {
            if (!TileBlocksMove(tx, tz)) continue;
            if (!CircleOverlapsTile(x, z, r, tx, tz)) continue;
            hit = true;
            if (InMap(tx, tz) && tiles[tz][tx] == T_DOOR) { *doorX = tx; *doorZ = tz; }
            if (InMap(tx, tz) && tiles[tz][tx] == T_LOCKED && bumpLocked) *bumpLocked = true;
        }
    for (int i = 0; i < numProps && !hit; i++)
        if (CircleOverlapsBox(x, z, r, props[i].box)) hit = true;
    return hit;
}

static bool MoveActor(Vector3 *pos, float dx, float dz, float r, bool canOpenDoors, bool *bumpLocked)
{
    int doorX = -1, doorZ = -1;
    bool blocked = false;
    if (!CircleHitsSolid(pos->x + dx, pos->z, r, &doorX, &doorZ, bumpLocked)) pos->x += dx; else blocked = true;
    if (!CircleHitsSolid(pos->x, pos->z + dz, r, &doorX, &doorZ, bumpLocked)) pos->z += dz; else blocked = true;
    if (canOpenDoors && doorX >= 0) OpenDoor(doorX, doorZ);
    return blocked;
}

/* Breadth-first search flow field toward a goal tile; doors count as passable, prop tiles are avoided */
static void BuildFlow(int gx, int gz)
{
    static int qx[MAP_W*MAP_H], qz[MAP_W*MAP_H];
    for (int z = 0; z < MAP_H; z++) for (int x = 0; x < MAP_W; x++) bfsDist[z][x] = -1;
    if (!InMap(gx, gz)) return;
    int head = 0, tail = 0;
    bfsDist[gz][gx] = 0; qx[tail] = gx; qz[tail] = gz; tail++;
    const int dx[4] = { 1, -1, 0, 0 }, dz[4] = { 0, 0, 1, -1 };
    while (head < tail) {
        int cx = qx[head], cz = qz[head]; head++;
        for (int k = 0; k < 4; k++) {
            int nx = cx + dx[k], nz = cz + dz[k];
            if (!InMap(nx, nz) || bfsDist[nz][nx] >= 0) continue;
            int t = tiles[nz][nx];
            if (t == T_WALL || t == T_WINDOW || t == T_LOCKED || propBlock[nz][nx]) continue;
            bfsDist[nz][nx] = bfsDist[cz][cx] + 1;
            qx[tail] = nx; qz[tail] = nz; tail++;
        }
    }
}

static Vector3 NextStepToward(Vector3 from, Vector3 goal)
{
    int gx = ToTile(goal.x), gz = ToTile(goal.z);
    int fx = ToTile(from.x), fz = ToTile(from.z);
    if (gx == fx && gz == fz) return goal;
    BuildFlow(gx, gz);
    if (!InMap(fx, fz) || bfsDist[fz][fx] < 0) {
        /* standing on a prop tile or goal unreachable: step to any neighbour that has a path */
        const int ddx[4] = { 1, -1, 0, 0 }, ddz[4] = { 0, 0, 1, -1 };
        for (int k = 0; k < 4; k++) {
            int nx = fx + ddx[k], nz = fz + ddz[k];
            if (InMap(nx, nz) && bfsDist[nz][nx] >= 0) return TileCenter(nx, nz);
        }
        return goal;
    }
    const int dx[4] = { 1, -1, 0, 0 }, dz[4] = { 0, 0, 1, -1 };
    int best = bfsDist[fz][fx], bx = -1, bz = -1;
    for (int k = 0; k < 4; k++) {
        int nx = fx + dx[k], nz = fz + dz[k];
        if (!InMap(nx, nz) || bfsDist[nz][nx] < 0) continue;
        if (bfsDist[nz][nx] < best) { best = bfsDist[nz][nx]; bx = nx; bz = nz; }
    }
    if (bx < 0) return goal;
    if (best == 0) return goal;
    return TileCenter(bx, bz);
}

/* ------------------------------------------------------------------ */
/* Particles & decals (simulation side)                                */
/* ------------------------------------------------------------------ */
static void SpawnPart(PartType type, Vector3 pos, Vector3 vel, float life, float size, Color col)
{
    Particle *p = &parts[partNext];
    partNext = (partNext + 1) % MAX_PARTICLES;
    p->type = type; p->pos = pos; p->vel = vel; p->life = p->maxLife = life; p->size = size; p->col = col;
    p->rot = Frand()*2*PI;
}

static Vector3 ComputeLight(Vector3 p, Vector3 n);
static void AddDecal(Vector3 pos, Vector3 n, float size)
{
    Decal *d = &decals[decalNext];
    decalNext = (decalNext + 1) % MAX_DECALS;
    d->pos = pos; d->n = n; d->life = 30.0f; d->size = size; d->rot = Frand()*2*PI;
    d->light = ComputeLight(Vector3Add(pos, Vector3Scale(n, 0.1f)), n);
}

/* bullet hits a surface: hole decal, sparks, dust puff, chips */
static void ImpactFx(Vector3 p, Vector3 n, bool metal)
{
    AddDecal(p, n, 0.11f + Frand()*0.05f);
    int ns = metal ? 9 : 5;
    for (int i = 0; i < ns; i++) {
        Vector3 v = Vector3Add(Vector3Scale(n, 2.0f + Frand()*3.0f), (Vector3){ Frand2()*2.5f, Frand2()*2.5f + 1.0f, Frand2()*2.5f });
        SpawnPart(P_SPARK, Vector3Add(p, Vector3Scale(n, 0.02f)), v, 0.18f + Frand()*0.2f, 0.05f, (Color){ 255, 210, 120, 255 });
    }
    for (int i = 0; i < 3; i++) {
        Vector3 v = Vector3Add(Vector3Scale(n, 0.4f + Frand()*0.6f), (Vector3){ Frand2()*0.3f, Frand()*0.3f, Frand2()*0.3f });
        SpawnPart(P_DUST, Vector3Add(p, Vector3Scale(n, 0.05f)), v, 0.9f + Frand()*0.6f, 0.22f + Frand()*0.15f, (Color){ 170, 160, 145, 140 });
    }
    for (int i = 0; i < 4; i++) {
        Vector3 v = Vector3Add(Vector3Scale(n, 1.5f + Frand()*2.0f), (Vector3){ Frand2()*1.5f, Frand()*2.0f, Frand2()*1.5f });
        SpawnPart(P_CHIP, Vector3Add(p, Vector3Scale(n, 0.03f)), v, 1.2f, 0.025f, (Color){ 70, 66, 60, 255 });
    }
}

static void UpdateParticles(float dt)
{
    for (int i = 0; i < MAX_PARTICLES; i++) {
        Particle *p = &parts[i];
        if (p->life <= 0) continue;
        p->life -= dt;
        switch (p->type) {
            case P_SPARK: p->vel.y -= 9.0f*dt; break;
            case P_DUST: case P_SMOKE: p->vel = Vector3Scale(p->vel, 1.0f - 1.8f*dt); p->vel.y += 0.15f*dt; p->size += dt*0.35f; break;
            case P_SHELL: case P_CHIP: p->vel.y -= 9.8f*dt; p->rot += dt*18.0f; break;
            case P_GLINT: break;
        }
        p->pos = Vector3Add(p->pos, Vector3Scale(p->vel, dt));
        if ((p->type == P_SHELL || p->type == P_CHIP || p->type == P_SPARK) && p->pos.y < p->size) {
            p->pos.y = p->size;
            if (p->vel.y < 0) p->vel.y = -p->vel.y*0.35f;
            p->vel.x *= 0.6f; p->vel.z *= 0.6f;
        }
    }
    for (int i = 0; i < MAX_DECALS; i++) if (decals[i].life > 0) decals[i].life -= dt;
}

/* ------------------------------------------------------------------ */
/* Players                                                             */
/* ------------------------------------------------------------------ */
static void ResetPlayerLoadout(Player *p, bool dm)
{
    for (int i = 0; i < W_COUNT; i++) { p->has[i] = false; p->mag[i] = 0; p->reserve[i] = 0; }
    p->has[W_PP7] = true; p->mag[W_PP7] = 7; p->reserve[W_PP7] = dm ? 35 : 21;
    if (dm) { p->has[W_KF7] = true; p->mag[W_KF7] = 30; p->reserve[W_KF7] = 60; }
    p->weapon = W_PP7;
    p->silencer = !dm;  /* Bond starts the mission with the silencer fitted */
    p->health = 100.0f;
    p->alive = true;
    p->fireCooldown = p->reloadTimer = p->muzzle = p->hurtFlash = 0;
    p->kick = 0; p->raise = 0; p->deathT = 0;
}

static void SpawnDmPlayer(int i)
{
    Player *p = &players[i];
    int best = 0; float bestD = -1;
    for (int s = 0; s < numSpawns; s++) {
        /* farthest from the nearest living opponent */
        float d = 1e9f;
        for (int j = 0; j < numPlayers; j++)
            if (j != i && players[j].alive) d = fminf(d, Dist2D(spawns[s], players[j].pos));
        if (d > 1e8f) d = Frand()*10.0f;
        d += Frand()*2.0f;
        if (d > bestD) { bestD = d; best = s; }
    }
    p->pos = spawns[best];
    p->yaw = Frand()*2*PI; p->pitch = 0;
    ResetPlayerLoadout(p, true);
}

static void DamagePlayer(int victim, float dmg, int attacker)
{
    Player *p = &players[victim];
    if (!p->alive) return;
    p->health -= dmg;
    p->hurtFlash = 0.45f;
    Sfx(sfxHurt);
    PadRumbleSlot(victim, 0.75f, 0.45f, p->health > 0 ? 0.22f : 0.6f);
    if (p->health > 0) return;
    p->health = 0;
    p->alive = false;
    p->deathT = 0;
    if (gState == GS_MISSION) { gMissionResult = 2; return; }
    /* deathmatch */
    p->respawnTimer = 2.5f;
    if (p->has[W_GOLDEN] && goldenPickup >= 0) pickups[goldenPickup].active = true;
    p->has[W_GOLDEN] = false;
    char buf[64];
    if (attacker >= 0 && attacker != victim) {
        players[attacker].kills++;
        snprintf(buf, sizeof(buf), "YOU KILLED PLAYER %d", victim + 1); SetMsg(&players[attacker], buf);
        snprintf(buf, sizeof(buf), "KILLED BY PLAYER %d", attacker + 1); SetMsg(p, buf);
        if (players[attacker].kills >= KILL_LIMIT) gDmWinner = attacker;
    }
}

/* ------------------------------------------------------------------ */
/* Noise / alerts                                                      */
/* ------------------------------------------------------------------ */
static void MakeNoise(Vector3 at, float radius, Vector3 investigate)
{
    for (int i = 0; i < numEnemies; i++) {
        Enemy *e = &enemies[i];
        if (e->state == E_DEAD || e->state == E_ATTACK) continue;
        if (Dist2D(e->pos, at) <= radius) {
            e->state = E_ALERT;
            e->target = investigate;
            e->alertTimer = 10.0f;
        }
    }
}

/* ------------------------------------------------------------------ */
/* Shooting                                                            */
/* ------------------------------------------------------------------ */
static BoundingBox BoxAt(Vector3 c, float sx, float sy, float sz)
{
    return (BoundingBox){ { c.x - sx*0.5f, c.y - sy*0.5f, c.z - sz*0.5f }, { c.x + sx*0.5f, c.y + sy*0.5f, c.z + sz*0.5f } };
}

/* thin panel in the middle of a door/window tile, from y0 to y1 */
static BoundingBox PanelBox(int x, int z, float y0, float y1, float thick)
{
    Vector3 c = TileCenter(x, z);
    c.y = (y0 + y1) * 0.5f;
    if (axisX[z][x]) return BoxAt(c, thick, y1 - y0, TILE);
    return BoxAt(c, TILE, y1 - y0, thick);
}

static BoundingBox LockBox(int x, int z)
{
    Vector3 c = TileCenter(x, z); c.y = 1.15f;
    if (axisX[z][x]) return BoxAt(c, 0.62f, 0.5f, 0.42f);
    return BoxAt(c, 0.42f, 0.5f, 0.62f);
}

static void TestBox(Ray ray, BoundingBox b, Hit *best, HitKind kind, int index, int tx, int tz, bool head)
{
    RayCollision rc = GetRayCollisionBox(ray, b);
    if (rc.hit && rc.distance < best->dist && rc.distance > 0.0f) {
        best->dist = rc.distance; best->kind = kind; best->index = index;
        best->tx = tx; best->tz = tz; best->head = head; best->point = rc.point; best->normal = rc.normal;
    }
}

static BoundingBox EnemyBodyBox(Vector3 p) { return BoxAt((Vector3){ p.x, 0.78f, p.z }, 0.62f, 1.56f, 0.62f); }
static BoundingBox EnemyHeadBox(Vector3 p) { return BoxAt((Vector3){ p.x, 1.755f, p.z }, 0.36f, 0.39f, 0.36f); }

static Hit CastShot(Ray ray, int shooter, int skipEnemy)
{
    Hit best = { 0 };
    best.dist = 200.0f; best.kind = HIT_NONE;
    if (ray.direction.y < -0.0001f) {
        float t = -ray.position.y / ray.direction.y;
        if (t < best.dist) { best.dist = t; best.kind = HIT_WORLD; best.point = Vector3Add(ray.position, Vector3Scale(ray.direction, t)); best.normal = (Vector3){ 0, 1, 0 }; }
    } else if (ray.direction.y > 0.0001f) {
        float t = (WALL_H - ray.position.y) / ray.direction.y;
        if (t < best.dist) { best.dist = t; best.kind = HIT_WORLD; best.point = Vector3Add(ray.position, Vector3Scale(ray.direction, t)); best.normal = (Vector3){ 0, -1, 0 }; }
    }
    for (int z = 0; z < MAP_H; z++)
        for (int x = 0; x < MAP_W; x++) {
            int t = tiles[z][x];
            Vector3 c = TileCenter(x, z);
            if (t == T_WALL) {
                c.y = WALL_H*0.5f;
                TestBox(ray, BoxAt(c, TILE, WALL_H, TILE), &best, HIT_WORLD, -1, x, z, false);
            } else if (t == T_WINDOW) {
                c.y = 0.45f; TestBox(ray, BoxAt(c, TILE, 0.9f, TILE), &best, HIT_WORLD, -1, x, z, false);
                c.y = 2.7f;  TestBox(ray, BoxAt(c, TILE, 0.6f, TILE), &best, HIT_WORLD, -1, x, z, false);
                TestBox(ray, PanelBox(x, z, 0.9f, 2.4f, 0.1f), &best, HIT_WORLD, -1, x, z, false);
            } else if (t == T_DOOR) {
                if (doorOpen[z][x] < 0.98f)
                    TestBox(ray, PanelBox(x, z, doorOpen[z][x]*WALL_H, WALL_H, 0.22f), &best, HIT_WORLD, -1, x, z, false);
            } else if (t == T_LOCKED) {
                TestBox(ray, PanelBox(x, z, 0.0f, WALL_H, 0.22f), &best, HIT_WORLD, -1, x, z, false);
                TestBox(ray, LockBox(x, z), &best, HIT_LOCK, -1, x, z, false);
            }
        }
    for (int i = 0; i < numProps; i++) TestBox(ray, props[i].box, &best, HIT_WORLD, -2 - i, 0, 0, false);
    if (gState == GS_MISSION) {
        for (int i = 0; i < numEnemies; i++) {
            Enemy *e = &enemies[i];
            if (e->state == E_DEAD || i == skipEnemy) continue;
            TestBox(ray, EnemyBodyBox(e->pos), &best, HIT_ENEMY, i, 0, 0, false);
            TestBox(ray, EnemyHeadBox(e->pos), &best, HIT_ENEMY, i, 0, 0, true);
        }
    } else {
        for (int i = 0; i < numPlayers; i++) {
            if (i == shooter || !players[i].alive) continue;
            Vector3 p = players[i].pos;
            TestBox(ray, EnemyBodyBox(p), &best, HIT_PLAYER, i, 0, 0, false);
            TestBox(ray, EnemyHeadBox(p), &best, HIT_PLAYER, i, 0, 0, true);
        }
    }
    return best;
}

static void DamageEnemy(int idx, float dmg, bool head, Player *shooter)
{
    Enemy *e = &enemies[idx];
    e->hp -= dmg * (head ? 3.0f : 1.0f);
    e->hurtFlash = 0.15f;
    if (e->hp <= 0.0f) {
        e->state = E_DEAD;
        e->deathT = 0;
        e->deathDir = Frand() < 0.5f ? 1.0f : -1.0f;
        missionKills++;
        if (head) shooter->headshots++;
        /* guards drop their KF7 */
        AddPickup((Vector3){ e->pos.x + 0.4f*cosf(e->yaw + 1.2f), 0.0f, e->pos.z + 0.4f*sinf(e->yaw + 1.2f) }, PK_KF7, false);
        pickups[numPickups - 1].yaw = e->yaw + 0.9f;
        return;
    }
    e->target = shooter->pos;
    e->alertTimer = 10.0f;
    if (LineOfSight(e->pos, shooter->pos)) {
        if (e->state != E_ATTACK) e->shootTimer = 0.5f;
        e->state = E_ATTACK;
    } else if (e->state != E_ATTACK) e->state = E_ALERT;
}

static Vector3 PlayerForward(Player *p)
{
    return (Vector3){ cosf(p->pitch)*cosf(p->yaw), sinf(p->pitch), cosf(p->pitch)*sinf(p->yaw) };
}

static bool PlayerSilenced(Player *p) { return p->weapon == W_PP7 && p->silencer && gState == GS_MISSION; }

static void FireWeapon(int i)
{
    Player *p = &players[i];
    const WeaponDef *w = &WEAPONS[p->weapon];
    bool silenced = PlayerSilenced(p);
    p->mag[p->weapon]--;
    p->fireCooldown = w->fireDelay;
    p->muzzle = silenced ? 0.035f : 0.06f;
    p->kick = 1.0f;
    p->flashRot = Frand()*2*PI;
    p->shots++;
    Sfx(silenced ? sfxSilenced : sfxShot);
    if (p->weapon == W_GOLDEN) PadRumbleSlot(i, 0.9f, 0.8f, 0.18f);
    else if (p->weapon == W_KF7) PadRumbleSlot(i, 0.15f, 0.45f, 0.06f);
    else PadRumbleSlot(i, silenced ? 0.1f : 0.25f, silenced ? 0.25f : 0.55f, 0.08f);

    Vector3 fwd = PlayerForward(p);
    Vector3 dir = fwd;
    float spread = w->spread * (1.0f + p->moveAmt*1.5f);
    dir.x += Frand2() * spread;
    dir.y += Frand2() * spread;
    dir.z += Frand2() * spread;
    Ray ray = { { p->pos.x, EYE_H, p->pos.z }, Vector3Normalize(dir) };
    Hit h = CastShot(ray, i, -1);

    /* brass ejects to the right */
    Vector3 right = Vector3Normalize(Vector3CrossProduct(fwd, (Vector3){ 0, 1, 0 }));
    Vector3 sp = Vector3Add(ray.position, Vector3Add(Vector3Scale(fwd, 0.35f), Vector3Add(Vector3Scale(right, 0.14f), (Vector3){ 0, -0.12f, 0 })));
    Vector3 sv = Vector3Add(Vector3Scale(right, 2.2f + Frand()), (Vector3){ Frand2()*0.4f, 1.8f + Frand(), Frand2()*0.4f });
    SpawnPart(P_SHELL, sp, sv, 2.5f, 0.012f, p->weapon == W_GOLDEN ? (Color){ 255, 210, 60, 255 } : (Color){ 210, 160, 60, 255 });
    if (!silenced) SpawnPart(P_SMOKE, Vector3Add(ray.position, Vector3Add(Vector3Scale(fwd, 0.7f), Vector3Scale(right, 0.15f))), Vector3Scale(fwd, 0.6f), 0.6f, 0.12f, (Color){ 200, 200, 200, 90 });

    switch (h.kind) {
        case HIT_WORLD: ImpactFx(h.point, h.normal, h.index <= -2 || (InMap(h.tx, h.tz) && tiles[h.tz][h.tx] != T_WALL)); if (Frand() < 0.3f) Sfx(sfxRicochet); break;
        case HIT_LOCK:
            tiles[h.tz][h.tx] = T_DOOR;
            doorOpen[h.tz][h.tx] = 0;
            for (int k = 0; k < 24; k++)
                SpawnPart(P_SPARK, h.point, (Vector3){ Frand2()*4, Frand()*4, Frand2()*4 }, 0.4f + Frand()*0.4f, 0.06f, (Color){ 255, 220, 100, 255 });
            for (int k = 0; k < 6; k++)
                SpawnPart(P_SHELL, h.point, (Vector3){ Frand2()*2, Frand()*2, Frand2()*2 }, 4.0f, 0.035f, (Color){ 230, 180, 40, 255 });
            if (!objs[0].done) { objs[0].done = true; SetMsg(p, "LOCK DESTROYED - OBJECTIVE A COMPLETE"); }
            break;
        case HIT_ENEMY:
            p->hits++;
            for (int k = 0; k < 5; k++) SpawnPart(P_DUST, h.point, (Vector3){ Frand2()*0.6f, Frand()*0.6f, Frand2()*0.6f }, 0.5f, 0.12f, (Color){ 120, 110, 90, 150 });
            DamageEnemy(h.index, w->damage, h.head, p);
            break;
        case HIT_PLAYER:
            p->hits++;
            for (int k = 0; k < 5; k++) SpawnPart(P_DUST, h.point, (Vector3){ Frand2()*0.6f, Frand()*0.6f, Frand2()*0.6f }, 0.5f, 0.12f, (Color){ 120, 110, 90, 150 });
            DamagePlayer(h.index, w->damage * (h.head ? 1.5f : 1.0f), i);
            break;
        default: break;
    }

    if (gState == GS_MISSION) {
        /* Gunfire noise: repeated shots in a short window widen the alert radius.
           Staying quiet for QUIET_RESET_TIME resets it. */
        if (gMissionTime - lastShotTime > QUIET_RESET_TIME) shotHeat = 0;
        shotHeat++;
        lastShotTime = gMissionTime;
        float base = silenced ? PP7_SILENCED_NOISE : w->noise;
        int heat = shotHeat > 6 ? 6 : shotHeat;
        float radius = base * (1.0f + 0.5f * (float)(heat - 1));
        noiseRadius = radius;
        noiseShow = 1.0f;
        MakeNoise(p->pos, radius, p->pos);
    }
}

static void TryOpenNearestDoor(Player *p)
{
    float bestD = 3.0f; int bx = -1, bz = -1;
    for (int z = 0; z < MAP_H; z++)
        for (int x = 0; x < MAP_W; x++) {
            if (tiles[z][x] != T_DOOR && tiles[z][x] != T_LOCKED) continue;
            float d = Dist2D(TileCenter(x, z), p->pos);
            if (d < bestD) { bestD = d; bx = x; bz = z; }
        }
    if (bx < 0) return;
    if (tiles[bz][bx] == T_LOCKED) { SetMsg(p, "THE DOOR IS LOCKED - SHOOT THE LOCK"); return; }
    OpenDoor(bx, bz);
}

static void CollectPickups(int i)
{
    Player *p = &players[i];
    for (int k = 0; k < numPickups; k++) {
        Pickup *pk = &pickups[k];
        if (!pk->active || Dist2D(pk->pos, p->pos) > 0.9f) continue;
        bool taken = true;
        switch (pk->type) {
            case PK_AMMO:
                p->reserve[W_PP7] += 14; p->reserve[W_KF7] += 30;
                SetMsg(p, "PICKED UP AMMO");
                break;
            case PK_HEALTH:
                if (p->health >= 100.0f) { taken = false; break; }
                p->health = fminf(100.0f, p->health + 40.0f);
                SetMsg(p, "PICKED UP BODY ARMOUR");
                break;
            case PK_DISK:
                objs[1].done = true;
                SetMsg(p, "DATA DISK RECOVERED - OBJECTIVE B COMPLETE");
                break;
            case PK_KF7:
                if (!p->has[W_KF7]) { p->has[W_KF7] = true; p->mag[W_KF7] = 30; SetMsg(p, PlayerUsesPad(p) ? "PICKED UP KF7 SOVIET (NEXT WEAPON)" : "PICKED UP KF7 SOVIET (PRESS 2)"); }
                else SetMsg(p, "PICKED UP KF7 AMMO");
                p->reserve[W_KF7] += 15;
                break;
            case PK_GOLDEN:
                p->has[W_GOLDEN] = true; p->weapon = W_GOLDEN; p->raise = 0;
                p->mag[W_GOLDEN] = 1; p->reserve[W_GOLDEN] = 99; p->reloadTimer = 0;
                SetMsg(p, "YOU HAVE THE GOLDEN GUN!");
                break;
        }
        if (!taken) continue;
        Sfx(sfxPickup);
        pk->active = false;
        pk->respawnTimer = 15.0f;
    }
}

static void UpdatePlayer(int i, PlayerInput in, float dt)
{
    Player *p = &players[i];
    if (p->msgTimer > 0) p->msgTimer -= dt;
    if (p->hurtFlash > 0) p->hurtFlash -= dt;
    if (!p->alive) {
        p->deathT += dt;
        if (gState == GS_DM && gDmWinner < 0) {
            p->respawnTimer -= dt;
            if (p->respawnTimer <= 0) SpawnDmPlayer(i);
        }
        return;
    }

    p->aimZoom += ((in.aim ? 1.0f : 0.0f) - p->aimZoom)*fminf(1.0f, dt*10.0f);
    p->yaw = WrapPi(p->yaw + in.turn);
    p->pitch = Clamp(p->pitch + in.look, -1.2f, 1.2f);

    float speed = 4.5f;
    Vector3 f = { cosf(p->yaw), 0, sinf(p->yaw) };
    Vector3 r = { -sinf(p->yaw), 0, cosf(p->yaw) };
    float mx = f.x*in.move + r.x*in.strafe;
    float mz = f.z*in.move + r.z*in.strafe;
    float len = sqrtf(mx*mx + mz*mz);
    if (len > 1.0f) { mx /= len; mz /= len; }
    bool bumpLocked = false;
    MoveActor(&p->pos, mx*speed*dt, mz*speed*dt, PLAYER_R, true, &bumpLocked);
    if (bumpLocked && p->msgTimer <= 0) SetMsg(p, "THE DOOR IS LOCKED - SHOOT THE LOCK");
    if (len > 0.1f) p->bob += dt * 9.0f;
    p->moveAmt += (fminf(len, 1.0f) - p->moveAmt) * fminf(1.0f, dt*8.0f);

    if (p->fireCooldown > 0) p->fireCooldown -= dt;
    if (p->muzzle > 0) p->muzzle -= dt;
    p->kick = fmaxf(0.0f, p->kick - dt*7.0f);
    p->raise = fminf(1.0f, p->raise + dt*3.5f);

    const WeaponDef *w = &WEAPONS[p->weapon];
    if (p->reloadTimer > 0) {
        p->reloadTimer -= dt;
        if (p->reloadTimer <= 0) {
            int need = w->magSize - p->mag[p->weapon];
            int take = need < p->reserve[p->weapon] ? need : p->reserve[p->weapon];
            p->mag[p->weapon] += take;
            if (p->weapon != W_GOLDEN) p->reserve[p->weapon] -= take;
            p->reloadTimer = 0;
        }
    }

    int sel = in.selectWeapon;
    if (in.nextWeapon) {
        for (int k = 1; k <= W_COUNT; k++) {
            int c = (p->weapon + k) % W_COUNT;
            if (p->has[c]) { sel = c; break; }
        }
    }
    if (sel >= 0 && sel < W_COUNT && p->has[sel] && sel != p->weapon) {
        p->weapon = sel; p->reloadTimer = 0; p->fireCooldown = 0.25f; p->raise = 0;
        w = &WEAPONS[p->weapon];
    }
    if (in.silencer && gState == GS_MISSION && p->weapon == W_PP7) {
        p->silencer = !p->silencer;
        SetMsg(p, p->silencer ? "SILENCER ATTACHED" : "SILENCER REMOVED");
    }
    if (in.reload && p->reloadTimer <= 0 && p->mag[p->weapon] < w->magSize && p->reserve[p->weapon] > 0) {
        p->reloadTimer = w->reloadTime; Sfx(sfxReload);
    }

    bool wantFire = w->automatic ? in.fire : in.firePressed;
    if (wantFire && p->fireCooldown <= 0 && p->reloadTimer <= 0) {
        if (p->mag[p->weapon] > 0) FireWeapon(i);
        else if (p->reserve[p->weapon] > 0) { p->reloadTimer = w->reloadTime; Sfx(sfxReload); }
        else { Sfx(sfxClick); p->fireCooldown = 0.3f; SetMsg(p, "OUT OF AMMO"); }
    }
    if (p->mag[p->weapon] == 0 && p->reserve[p->weapon] > 0 && p->reloadTimer <= 0 && p->fireCooldown <= 0) {
        p->reloadTimer = w->reloadTime; Sfx(sfxReload);
    }
    float targetSpread = 6.0f + p->moveAmt*10.0f + p->kick*14.0f + (p->weapon == W_KF7 ? 4.0f : 0.0f);
    p->spreadVis += (targetSpread - p->spreadVis) * fminf(1.0f, dt*12.0f);

    if (in.use) TryOpenNearestDoor(p);
    CollectPickups(i);

    if (gState == GS_MISSION && ToTile(p->pos.x) == exitX && ToTile(p->pos.z) == exitZ) {
        if (objs[0].done && objs[1].done) { objs[2].done = true; gMissionResult = 1; }
        else if (p->msgTimer <= 0) SetMsg(p, "OBJECTIVES INCOMPLETE - CANNOT EXTRACT YET");
    }
}

/* ------------------------------------------------------------------ */
/* Enemy AI                                                            */
/* ------------------------------------------------------------------ */
static void EnemyMoveToward(Enemy *e, Vector3 goal, float speed, float dt)
{
    Vector3 step = NextStepToward(e->pos, goal);
    float dx = step.x - e->pos.x, dz = step.z - e->pos.z;
    float d = sqrtf(dx*dx + dz*dz);
    if (d < 0.05f) return;
    float s = fminf(speed*dt, d);
    MoveActor(&e->pos, dx/d*s, dz/d*s, ENEMY_R, true, NULL);
    float targetYaw = atan2f(dz, dx);
    e->yaw += WrapPi(targetYaw - e->yaw) * fminf(1.0f, dt*8.0f);
}

static Vector3 EnemyMuzzlePos(Enemy *e)
{
    return (Vector3){ e->pos.x + cosf(e->yaw)*0.95f - sinf(e->yaw)*0.12f, 1.42f, e->pos.z + sinf(e->yaw)*0.95f + cosf(e->yaw)*0.12f };
}

static void EnemyShoot(Enemy *e, float dist)
{
    Player *p = &players[0];
    int idx = (int)(e - enemies);
    Sfx(sfxEnemyShot);
    e->muzzle = 0.08f;
    MakeNoise(e->pos, 12.0f, p->pos);
    float chance = 0.55f - dist*0.03f;
    if (chance < 0.12f) chance = 0.12f;
    Vector3 from = EnemyMuzzlePos(e);
    Vector3 to = { p->pos.x, EYE_H - 0.3f, p->pos.z };
    bool hit = Frand() < chance;
    /* bullets are real rays: props, doors and other guards block them */
    Vector3 dir = Vector3Normalize(Vector3Subtract(to, from));
    if (!hit) dir = Vector3Normalize(Vector3Add(dir, (Vector3){ Frand2()*0.08f, Frand2()*0.06f, Frand2()*0.08f }));
    Ray ray = { from, dir };
    Hit h = CastShot(ray, -1, idx);
    float pd = Vector3Distance(from, to);
    if (hit && (h.kind == HIT_NONE || h.dist > pd - 0.35f)) DamagePlayer(0, 5.0f + (float)(rand() % 5), -1);
    else if (h.kind == HIT_WORLD && h.dist < 60.0f) ImpactFx(h.point, h.normal, h.index <= -2);
    else if (h.kind == HIT_ENEMY && h.dist < pd) enemies[h.index].hurtFlash = 0.1f;
}

static void UpdateEnemy(Enemy *e, float dt)
{
    if (e->hurtFlash > 0) e->hurtFlash -= dt;
    if (e->muzzle > 0) e->muzzle -= dt;
    if (e->state == E_DEAD) { e->deathT += dt; e->speed = 0; return; }
    Vector3 before = e->pos;

    Player *p = &players[0];
    float dx = p->pos.x - e->pos.x, dz = p->pos.z - e->pos.z;
    float dist = sqrtf(dx*dx + dz*dz);
    bool canSee = false;
    if (p->alive && dist < 30.0f && LineOfSight(e->pos, p->pos)) {
        float diff = fabsf(WrapPi(atan2f(dz, dx) - e->yaw));
        if (e->state == E_ATTACK) canSee = true;
        else if (e->state == E_ALERT) canSee = (diff < 1.7f && dist < 22.0f) || dist < 3.0f;
        else canSee = (diff < 0.9f && dist < 16.0f) || dist < 2.0f;
    }

    if (canSee) {
        if (e->state != E_ATTACK) {
            e->state = E_ATTACK;
            e->shootTimer = 0.7f;               /* reaction time */
            MakeNoise(e->pos, 8.0f, p->pos);    /* shouts to nearby guards */
        }
        e->target = p->pos;
        e->alertTimer = 10.0f;
    }

    /* keep guards from stacking on each other or walking into the player */
    for (int i = 0; i < numEnemies; i++) {
        Enemy *o = &enemies[i];
        if (o == e || o->state == E_DEAD) continue;
        float ox = e->pos.x - o->pos.x, oz = e->pos.z - o->pos.z, od = sqrtf(ox*ox + oz*oz);
        if (od > 0.001f && od < 0.7f) MoveActor(&e->pos, ox/od*(0.7f - od)*0.5f, oz/od*(0.7f - od)*0.5f, ENEMY_R, false, NULL);
    }
    if (p->alive && dist > 0.001f && dist < 0.75f) MoveActor(&e->pos, -dx/dist*(0.75f - dist), -dz/dist*(0.75f - dist), ENEMY_R, false, NULL);

    switch (e->state) {
        case E_PATROL: {
            float ax = e->pos.x + e->pdx*0.9f, az = e->pos.z + e->pdz*0.9f;
            int tx = ToTile(ax), tz = ToTile(az);
            if (!InMap(tx, tz) || tiles[tz][tx] != T_FLOOR || propBlock[tz][tx]) { e->pdx = -e->pdx; e->pdz = -e->pdz; }
            if (MoveActor(&e->pos, e->pdx*1.3f*dt, e->pdz*1.3f*dt, ENEMY_R, false, NULL)) { e->pdx = -e->pdx; e->pdz = -e->pdz; }
            float targetYaw = atan2f(e->pdz, e->pdx);
            e->yaw += WrapPi(targetYaw - e->yaw) * fminf(1.0f, dt*5.0f);
        } break;
        case E_ALERT:
            if (Dist2D(e->pos, e->target) > 0.8f) EnemyMoveToward(e, e->target, 2.6f, dt);
            else e->yaw = WrapPi(e->yaw + dt*1.8f);  /* look around */
            e->alertTimer -= dt;
            if (e->alertTimer <= 0) e->state = E_PATROL;
            break;
        case E_ATTACK:
            if (!canSee) { e->state = E_ALERT; e->alertTimer = 10.0f; break; }
            e->yaw += WrapPi(atan2f(dz, dx) - e->yaw) * fminf(1.0f, dt*10.0f);
            if (dist > 8.0f) EnemyMoveToward(e, p->pos, 2.2f, dt);
            e->shootTimer -= dt;
            if (e->shootTimer <= 0) {
                e->shootTimer = 0.7f + Frand()*0.6f;
                EnemyShoot(e, dist);
            }
            break;
        default: break;
    }
    /* animation drivers */
    float moved = dt > 0 ? Dist2D(before, e->pos)/dt : 0;
    e->speed += (moved - e->speed) * fminf(1.0f, dt*10.0f);
    e->walk += dt * e->speed * 3.4f;
    float aimT = (e->state == E_ATTACK || (e->state == E_ALERT && e->speed < 0.5f)) ? 1.0f : 0.0f;
    e->aim += (aimT - e->aim) * fminf(1.0f, dt*6.0f);
}

/* ------------------------------------------------------------------ */
/* Input                                                               */
/* ------------------------------------------------------------------ */
static PlayerInput ReadInputP1(bool dm, float dt)
{
    PlayerInput in = { 0 };
    in.selectWeapon = -1;
    if (IsKeyDown(KEY_W)) in.move += 1;
    if (IsKeyDown(KEY_S)) in.move -= 1;
    if (IsKeyDown(KEY_D)) in.strafe += 1;
    if (IsKeyDown(KEY_A)) in.strafe -= 1;
    Vector2 md = GetMouseDelta();
    in.turn = md.x * 0.0025f;
    in.look = -md.y * 0.0025f;
    float kturn = 2.4f * dt;
    if (dm) {
        if (IsKeyDown(KEY_Q)) in.turn -= kturn;
        if (IsKeyDown(KEY_E)) in.turn += kturn;
    } else {
        if (IsKeyDown(KEY_LEFT)) in.turn -= kturn;
        if (IsKeyDown(KEY_RIGHT)) in.turn += kturn;
        if (IsKeyDown(KEY_UP)) in.look += kturn*0.6f;
        if (IsKeyDown(KEY_DOWN)) in.look -= kturn*0.6f;
        if (IsKeyDown(KEY_PAGE_UP)) in.look += kturn*0.6f;
        if (IsKeyDown(KEY_PAGE_DOWN)) in.look -= kturn*0.6f;
        in.use = IsKeyPressed(KEY_E) || IsMouseButtonPressed(MOUSE_BUTTON_RIGHT);
        in.silencer = IsKeyPressed(KEY_T);
    }
    in.fire = IsMouseButtonDown(MOUSE_BUTTON_LEFT) || IsKeyDown(KEY_SPACE) || IsKeyDown(KEY_LEFT_CONTROL);
    in.firePressed = IsMouseButtonPressed(MOUSE_BUTTON_LEFT) || IsKeyPressed(KEY_SPACE) || IsKeyPressed(KEY_LEFT_CONTROL);
    in.reload = IsKeyPressed(KEY_R);
    if (IsKeyPressed(KEY_ONE)) in.selectWeapon = W_PP7;
    if (IsKeyPressed(KEY_TWO)) in.selectWeapon = W_KF7;
    if (IsKeyPressed(KEY_THREE)) in.selectWeapon = W_GOLDEN;
    float wheel = GetMouseWheelMove();
    if (wheel != 0.0f || IsKeyPressed(KEY_F)) in.nextWeapon = true;
    in.aim = IsKeyDown(KEY_Z);
    return in;
}

static PlayerInput ReadInputP2(float dt)
{
    PlayerInput in = { 0 };
    in.selectWeapon = -1;
    float kturn = 2.4f * dt;
    if (IsKeyDown(KEY_UP)) in.move += 1;
    if (IsKeyDown(KEY_DOWN)) in.move -= 1;
    if (IsKeyDown(KEY_LEFT)) in.turn -= kturn;
    if (IsKeyDown(KEY_RIGHT)) in.turn += kturn;
    if (IsKeyDown(KEY_COMMA)) in.strafe -= 1;
    if (IsKeyDown(KEY_PERIOD)) in.strafe += 1;
    in.fire = IsKeyDown(KEY_RIGHT_CONTROL) || IsKeyDown(KEY_ENTER) || IsKeyDown(KEY_KP_0);
    in.firePressed = IsKeyPressed(KEY_RIGHT_CONTROL) || IsKeyPressed(KEY_ENTER) || IsKeyPressed(KEY_KP_0);
    in.nextWeapon = IsKeyPressed(KEY_RIGHT_SHIFT);
    in.reload = IsKeyPressed(KEY_SLASH);
    return in;
}

/* ================================================================== */
/* GRAPHICS                                                            */
/* ================================================================== */
typedef enum {
    TX_WALL_CONCRETE, TX_WALL_METAL, TX_WALL_BRICK, TX_WALL_LAB, TX_WALL_WOOD,
    TX_FLOOR_CONCRETE, TX_FLOOR_TILE, TX_FLOOR_METAL, TX_FLOOR_WOOD, TX_FLOOR_LAB,
    TX_CEIL_TILE, TX_CEIL_CONCRETE, TX_DOOR, TX_DOOR_ARMORY, TX_HAZARD, TX_GLASS,
    TX_CRATE, TX_BARREL, TX_SCREEN, TX_RACK, TX_DESK, TX_STEEL,
    TX_GUNMETAL, TX_POLYMER, TX_GUNWOOD, TX_GOLD, TX_SKIN, TX_SLEEVE, TX_CUFF, TX_GLOVE,
    TX_LIGHTPANEL, TX_SKY, TX_SNOW, TX_SOFT, TX_SPARK, TX_FLASH, TX_HOLE, TX_VIGNETTE,
    TX_AMMOBOX, TX_DISK, TX_VEST,
    TX_CHAR_SOLDIER, TX_CHAR_GUARD, TX_CHAR_COMMANDO, TX_CHAR_AGENT1, TX_CHAR_AGENT2,
    TX_COUNT
} TexId;

static const char *TEX_NAMES[TX_COUNT] = {
    "wall_concrete", "wall_metal", "wall_brick", "wall_lab", "wall_wood",
    "floor_concrete", "floor_tile", "floor_metal", "floor_wood", "floor_lab",
    "ceil_tile", "ceil_concrete", "door", "door_armoury", "hazard", "glass",
    "crate", "barrel", "screen", "rack", "desk", "steel",
    "gunmetal", "polymer", "gunwood", "gold", "skin", "sleeve", "cuff", "glove",
    "lightpanel", "sky", "snow", "fx_soft", "fx_spark", "fx_flash", "fx_hole", "fx_vignette",
    "ammobox", "disk", "vest",
    "char_soldier", "char_guard", "char_commando", "char_agent1", "char_agent2",
};

static const CharStyle CHAR_STYLES[5] = {
    /* soldier: olive fatigues, helmet, vest */
    { { 92, 100, 62, 255 }, { 80, 88, 56, 255 }, { 112, 104, 74, 255 }, { 74, 86, 54, 255 }, { 222, 180, 150, 255 }, { 70, 50, 30, 255 }, { 32, 30, 28, 255 }, 1, true, false, false, false, false },
    /* facility guard: blue-grey shirt, peaked cap, moustache */
    { { 84, 96, 118, 255 }, { 52, 58, 74, 255 }, { 60, 60, 60, 255 }, { 34, 38, 52, 255 }, { 200, 150, 115, 255 }, { 40, 30, 25, 255 }, { 24, 24, 24, 255 }, 2, false, false, true, false, false },
    /* commando: black kit, balaclava, beanie, gloves */
    { { 44, 46, 50, 255 }, { 38, 40, 44, 255 }, { 68, 70, 66, 255 }, { 30, 30, 32, 255 }, { 225, 185, 160, 255 }, { 30, 30, 30, 255 }, { 20, 20, 20, 255 }, 3, true, true, false, true, false },
    /* agent 1: charcoal suit */
    { { 38, 40, 48, 255 }, { 34, 36, 42, 255 }, { 0, 0, 0, 255 }, { 0, 0, 0, 255 }, { 225, 185, 155, 255 }, { 55, 38, 24, 255 }, { 16, 16, 16, 255 }, 0, false, false, false, false, true },
    /* agent 2: tan suit, fair hair */
    { { 132, 108, 78, 255 }, { 116, 94, 68, 255 }, { 0, 0, 0, 255 }, { 0, 0, 0, 255 }, { 214, 170, 140, 255 }, { 190, 160, 92, 255 }, { 40, 26, 18, 255 }, 0, false, false, false, false, true },
};

static Texture2D tex[TX_COUNT];
static Material mats[TX_COUNT];
static Shader gShader;
static bool shaderOk = false;
static float overbright = 0.5f;   /* vertex light scale; shader multiplies by 2 */
static int locViewPos, locFogColor, locFogDensity, locUnlit, locDynPos, locDynCol, locDynCount;
static const Vector3 FOG_RGB = { 0.085f, 0.09f, 0.105f };
static float gFogDensity = 0.034f;

/* Enhanced-mode hooks (gfx_enhanced.c, F2) */
static bool gEnh;
static void EnhSetupView(Camera3D cam, const float *pos, const float *col, int n);
static void EnhLevelMaterial(int t);
static bool PropTypeEnhanced(int type);
static void EnhDrawProps(void);
static bool EnhDrawPickupWeapon(int type, Vector3 p, float spin, float hover, float yaw, Vector3 L);

static Cv GenTexture(int id)
{
    switch (id) {
        case TX_WALL_CONCRETE: return TexWallConcrete();
        case TX_WALL_METAL: return TexWallMetal();
        case TX_WALL_BRICK: return TexWallBrick();
        case TX_WALL_LAB: return TexWallLab();
        case TX_WALL_WOOD: return TexWallWood();
        case TX_FLOOR_CONCRETE: return TexFloorConcrete();
        case TX_FLOOR_TILE: return TexFloorTile();
        case TX_FLOOR_METAL: return TexFloorMetal();
        case TX_FLOOR_WOOD: return TexFloorWood();
        case TX_FLOOR_LAB: return TexFloorLab();
        case TX_CEIL_TILE: return TexCeilTile();
        case TX_CEIL_CONCRETE: return TexCeilConcrete();
        case TX_DOOR: return TexDoor();
        case TX_DOOR_ARMORY: return TexDoorArmory();
        case TX_HAZARD: return TexHazard();
        case TX_GLASS: return TexGlass();
        case TX_CRATE: return TexCrate();
        case TX_BARREL: return TexBarrel();
        case TX_SCREEN: return TexScreen();
        case TX_RACK: return TexRack();
        case TX_DESK: return TexDesk();
        case TX_STEEL: return TexSolid((Color){ 120, 124, 128, 255 }, 401, 16, 2, 24);
        case TX_GUNMETAL: return TexSolid((Color){ 74, 77, 86, 255 }, 411, 16, 2, 24);
        case TX_POLYMER: return TexPolymer();
        case TX_GUNWOOD: return TexGunWood();
        case TX_GOLD: return TexSolid((Color){ 214, 168, 52, 255 }, 421, 26, 2, 20);
        case TX_SKIN: return TexSolid((Color){ 214, 168, 136, 255 }, 431, 10, 0, 0);
        case TX_SLEEVE: return TexSolid((Color){ 40, 42, 50, 255 }, 441, 12, 16, 4);
        case TX_CUFF: return TexSolid((Color){ 228, 228, 222, 255 }, 451, 8, 0, 0);
        case TX_GLOVE: return TexSolid((Color){ 30, 30, 32, 255 }, 461, 10, 0, 0);
        case TX_LIGHTPANEL: return TexLightPanel();
        case TX_SKY: return TexSky();
        case TX_SNOW: return TexSnow();
        case TX_SOFT: return TexRadial(64, 2.0f, WHITE);
        case TX_SPARK: return TexRadial(32, 3.0f, (Color){ 255, 230, 170, 255 });
        case TX_FLASH: return TexFlash();
        case TX_HOLE: return TexHole();
        case TX_VIGNETTE: return TexVignette();
        case TX_AMMOBOX: return TexAmmoBox();
        case TX_DISK: return TexDisk();
        case TX_VEST: return TexVest();
        default: return TexCharacter(&CHAR_STYLES[id - TX_CHAR_SOLDIER], 700 + (id - TX_CHAR_SOLDIER)*37);
    }
}

static bool IsSpriteTex(int id) { return id == TX_SOFT || id == TX_SPARK || id == TX_FLASH || id == TX_HOLE || id == TX_VIGNETTE || id == TX_SKY; }

static void LoadAllTextures(bool exportPngs)
{
    char dir[512];
    snprintf(dir, sizeof(dir), "%sassets/textures", GetApplicationDirectory());
    if (exportPngs && !DirectoryExists(dir)) MakeDirectory(dir);
    int loaded = 0, generated = 0;
    for (int i = 0; i < TX_COUNT; i++) {
        char path[640];
        snprintf(path, sizeof(path), "%s/%s.png", dir, TEX_NAMES[i]);
        Image img = { 0 };
        if (!exportPngs && FileExists(path)) img = LoadImage(path);
        if (img.data) loaded++;
        else {
            Cv c = GenTexture(i);
            img = (Image){ c.p, c.w, c.h, 1, PIXELFORMAT_UNCOMPRESSED_R8G8B8A8 };
            generated++;
            if (exportPngs) ExportImage(img, path);
        }
        if (img.format != PIXELFORMAT_UNCOMPRESSED_R8G8B8A8) ImageFormat(&img, PIXELFORMAT_UNCOMPRESSED_R8G8B8A8);
        tex[i] = LoadTextureFromImage(img);
        UnloadImage(img);
        GenTextureMipmaps(&tex[i]);
        SetTextureFilter(tex[i], IsSpriteTex(i) ? TEXTURE_FILTER_BILINEAR : TEXTURE_FILTER_ANISOTROPIC_8X);
        SetTextureWrap(tex[i], IsSpriteTex(i) && i != TX_SKY ? TEXTURE_WRAP_CLAMP : TEXTURE_WRAP_REPEAT);
    }
    TraceLog(LOG_INFO, "FACILITY64: textures loaded from disk %d, generated %d%s", loaded, generated, exportPngs ? " (exported)" : "");
}

/* ---------------- shader ---------------- */
static const char *VS_SRC =
    "#version 330\n"
    "in vec3 vertexPosition; in vec2 vertexTexCoord; in vec3 vertexNormal; in vec4 vertexColor;\n"
    "uniform mat4 mvp; uniform mat4 matModel; uniform mat4 matNormal;\n"
    "out vec3 fragPosition; out vec2 fragTexCoord; out vec4 fragColor; out vec3 fragNormal;\n"
    "void main() {\n"
    "  fragPosition = vec3(matModel*vec4(vertexPosition, 1.0));\n"
    "  fragTexCoord = vertexTexCoord; fragColor = vertexColor;\n"
    "  fragNormal = normalize(vec3(matNormal*vec4(vertexNormal, 1.0)));\n"
    "  gl_Position = mvp*vec4(vertexPosition, 1.0);\n"
    "}\n";
static const char *FS_SRC =
    "#version 330\n"
    "in vec3 fragPosition; in vec2 fragTexCoord; in vec4 fragColor; in vec3 fragNormal;\n"
    "uniform sampler2D texture0; uniform vec4 colDiffuse;\n"
    "uniform vec3 viewPos; uniform vec3 fogColor; uniform float fogDensity; uniform float unlit;\n"
    "uniform vec4 dynPos[4]; uniform vec4 dynCol[4]; uniform int dynCount;\n"
    "out vec4 finalColor;\n"
    "void main() {\n"
    "  vec4 tx = texture(texture0, fragTexCoord);\n"
    "  if (tx.a*colDiffuse.a < 0.05) discard;\n"
    "  vec3 base = tx.rgb*colDiffuse.rgb;\n"
    "  vec3 col;\n"
    "  if (unlit > 0.5) col = base*fragColor.rgb;\n"
    "  else {\n"
    "    vec3 light = fragColor.rgb*2.0;\n"
    "    vec3 n = normalize(fragNormal);\n"
    "    for (int i = 0; i < 4; i++) {\n"
    "      if (i >= dynCount) break;\n"
    "      vec3 d = dynPos[i].xyz - fragPosition; float dist = length(d);\n"
    "      float att = clamp(1.0 - dist/dynPos[i].w, 0.0, 1.0); att *= att;\n"
    "      float ndl = max(dot(n, d/max(dist, 0.001)), 0.0)*0.75 + 0.25;\n"
    "      light += dynCol[i].rgb*att*ndl*(0.5/max(colDiffuse.r + colDiffuse.g + colDiffuse.b, 0.5) + 0.5);\n"
    "    }\n"
    "    col = base*light;\n"
    "  }\n"
    "  float dist = length(viewPos - fragPosition);\n"
    "  float f = 1.0 - exp(-(dist*fogDensity)*(dist*fogDensity));\n"
    "  col = mix(col, fogColor, clamp(f, 0.0, 1.0));\n"
    "  finalColor = vec4(col, tx.a*colDiffuse.a*fragColor.a);\n"
    "}\n";

static void InitShader(void)
{
    gShader = LoadShaderFromMemory(VS_SRC, FS_SRC);
    shaderOk = gShader.id > 0 && gShader.id != rlGetShaderIdDefault();
    if (!shaderOk) {
        TraceLog(LOG_WARNING, "FACILITY64: lighting shader failed, using default shader (no fog/dynamic lights)");
        gShader = LoadShaderFromMemory(NULL, NULL);
        overbright = 1.0f;
        return;
    }
    gShader.locs[SHADER_LOC_MATRIX_MODEL] = GetShaderLocation(gShader, "matModel");
    gShader.locs[SHADER_LOC_MATRIX_NORMAL] = GetShaderLocation(gShader, "matNormal");
    locViewPos = GetShaderLocation(gShader, "viewPos");
    locFogColor = GetShaderLocation(gShader, "fogColor");
    locFogDensity = GetShaderLocation(gShader, "fogDensity");
    locUnlit = GetShaderLocation(gShader, "unlit");
    locDynPos = GetShaderLocation(gShader, "dynPos");
    locDynCol = GetShaderLocation(gShader, "dynCol");
    locDynCount = GetShaderLocation(gShader, "dynCount");
    SetShaderValue(gShader, locFogColor, &FOG_RGB, SHADER_UNIFORM_VEC3);
}

static void SetUnlit(bool u) { if (!shaderOk) return; float v = u ? 1.0f : 0.0f; SetShaderValue(gShader, locUnlit, &v, SHADER_UNIFORM_FLOAT); }
static void SetFog(float d) { if (!shaderOk) return; SetShaderValue(gShader, locFogDensity, &d, SHADER_UNIFORM_FLOAT); }

static void InitMaterials(void)
{
    for (int i = 0; i < TX_COUNT; i++) {
        mats[i] = LoadMaterialDefault();
        mats[i].shader = gShader;
        mats[i].maps[MATERIAL_MAP_DIFFUSE].texture = tex[i];
        mats[i].maps[MATERIAL_MAP_DIFFUSE].color = WHITE;
    }
}

static void DrawMeshTint(Mesh m, int texId, Vector3 light, Matrix xf)
{
    Color c = { ClampB(light.x*overbright*255), ClampB(light.y*overbright*255), ClampB(light.z*overbright*255), 255 };
    mats[texId].maps[MATERIAL_MAP_DIFFUSE].color = c;
    DrawMesh(m, mats[texId], xf);
    mats[texId].maps[MATERIAL_MAP_DIFFUSE].color = WHITE;
}

/* ---------------- rooms, themes, lights ---------------- */
static int roomId[MAP_H][MAP_W];
static Theme roomTheme[32];
static int numRooms = 0;

static bool IsOpenChar(char c) { return c != '#' && c != 'W' && c != 'O' && c != 'D' && c != 'L'; }

static void FloodRooms(void)
{
    static int qx[MAP_W*MAP_H], qz[MAP_W*MAP_H];
    for (int z = 0; z < MAP_H; z++) for (int x = 0; x < MAP_W; x++) roomId[z][x] = -1;
    numRooms = 0;
    for (int z = 0; z < MAP_H; z++) for (int x = 0; x < MAP_W; x++) {
        if (roomId[z][x] >= 0 || !IsOpenChar(LEVEL[z][x]) || numRooms >= 32) continue;
        int id = numRooms++, head = 0, tail = 0;
        roomId[z][x] = id; qx[tail] = x; qz[tail] = z; tail++;
        while (head < tail) {
            int cx = qx[head], cz = qz[head]; head++;
            const int dx[4] = { 1, -1, 0, 0 }, dz[4] = { 0, 0, 1, -1 };
            for (int k = 0; k < 4; k++) {
                int nx = cx + dx[k], nz = cz + dz[k];
                if (!InMap(nx, nz) || roomId[nz][nx] >= 0 || !IsOpenChar(LEVEL[nz][nx])) continue;
                roomId[nz][nx] = id; qx[tail] = nx; qz[tail] = nz; tail++;
            }
        }
        roomTheme[id] = (Theme){ TX_WALL_CONCRETE, TX_FLOOR_CONCRETE, TX_CEIL_CONCRETE };
    }
    struct { int x, z; Theme t; } T[] = {
        { 3, 2,  { TX_WALL_BRICK,    TX_FLOOR_WOOD,     TX_CEIL_TILE } },
        { 10, 3, { TX_WALL_WOOD,     TX_FLOOR_TILE,     TX_CEIL_TILE } },
        { 17, 3, { TX_WALL_LAB,      TX_FLOOR_LAB,      TX_CEIL_TILE } },
        { 24, 2, { TX_WALL_CONCRETE, TX_FLOOR_CONCRETE, TX_CEIL_CONCRETE } },
        { 3, 8,  { TX_WALL_METAL,    TX_FLOOR_METAL,    TX_CEIL_CONCRETE } },
        { 13, 8, { TX_WALL_CONCRETE, TX_FLOOR_TILE,     TX_CEIL_TILE } },
        { 24, 8, { TX_WALL_BRICK,    TX_FLOOR_CONCRETE, TX_CEIL_CONCRETE } },
        { 3, 13, { TX_WALL_CONCRETE, TX_FLOOR_CONCRETE, TX_CEIL_CONCRETE } },
        { 8, 12, { TX_WALL_METAL,    TX_FLOOR_CONCRETE, TX_CEIL_CONCRETE } },
        { 13, 12,{ TX_WALL_METAL,    TX_FLOOR_METAL,    TX_CEIL_TILE } },
        { 18, 12,{ TX_WALL_METAL,    TX_FLOOR_METAL,    TX_CEIL_CONCRETE } },
        { 24, 12,{ TX_WALL_BRICK,    TX_FLOOR_WOOD,     TX_CEIL_TILE } },
    };
    for (int i = 0; i < (int)(sizeof(T)/sizeof(T[0])); i++) {
        int id = roomId[T[i].z][T[i].x];
        if (id >= 0) roomTheme[id] = T[i].t;
    }
}

/* theme for any non-wall tile (doors/windows take a neighbouring room's theme) */
static Theme ThemeAt(int x, int z)
{
    if (InMap(x, z) && roomId[z][x] >= 0) return roomTheme[roomId[z][x]];
    const int dx[4] = { 1, -1, 0, 0 }, dz[4] = { 0, 0, 1, -1 };
    for (int k = 0; k < 4; k++) {
        int nx = x + dx[k], nz = z + dz[k];
        if (InMap(nx, nz) && roomId[nz][nx] >= 0) return roomTheme[roomId[nz][nx]];
    }
    return (Theme){ TX_WALL_CONCRETE, TX_FLOOR_CONCRETE, TX_CEIL_CONCRETE };
}

static void AddLight(float tx, float tz, float y, Vector3 col, float radius, bool fixture)
{
    if (numLights >= MAX_LIGHTS) return;
    lights[numLights++] = (Light){ { (tx + 0.5f)*TILE, y, (tz + 0.5f)*TILE }, col, radius, fixture };
}

static void SetupLights(void)
{
    numLights = 0;
    const float Y = WALL_H - 0.25f;
    AddLight(3, 2.5f, Y, (Vector3){ 1.45f, 1.18f, 0.85f }, 11, true);                  /* R1 warm office */
    AddLight(8.5f, 3, Y, (Vector3){ 1.15f, 1.25f, 1.20f }, 10, true);                 /* R2 fluorescent */
    AddLight(12, 3, Y, (Vector3){ 1.15f, 1.25f, 1.20f }, 10, true);
    AddLight(16.5f, 2.5f, Y, (Vector3){ 1.0f, 1.2f, 1.45f }, 10, true);               /* R3 cool lab */
    AddLight(19, 3, Y, (Vector3){ 1.0f, 1.2f, 1.45f }, 10, true);
    AddLight(24, 2.5f, Y, (Vector3){ 1.25f, 1.2f, 1.05f }, 11, true);                 /* R4 */
    AddLight(3, 7.5f, Y, (Vector3){ 0.95f, 1.30f, 0.95f }, 11, true);                 /* R5 greenish */
    AddLight(8.5f, 8, Y, (Vector3){ 1.2f, 1.18f, 1.05f }, 10, true);                  /* main hall */
    AddLight(12.5f, 8, Y, (Vector3){ 1.2f, 1.18f, 1.05f }, 10, true);
    AddLight(16.5f, 8, Y, (Vector3){ 1.2f, 1.18f, 1.05f }, 10, true);
    AddLight(19.5f, 8, Y, (Vector3){ 1.2f, 1.18f, 1.05f }, 10, true);
    AddLight(24, 7.5f, Y, (Vector3){ 1.5f, 1.0f, 0.6f }, 11, true);                   /* R7 orange */
    AddLight(3, 12.5f, Y, (Vector3){ 1.25f, 0.92f, 0.62f }, 10, true);                /* R8 dim orange */
    AddLight(8.5f, 12.5f, Y, (Vector3){ 1.35f, 1.25f, 0.75f }, 9, true);              /* R9 yellow */
    AddLight(13.5f, 12.5f, Y, (Vector3){ 0.75f, 1.35f, 1.20f }, 9, true);             /* R10 cyan-green */
    AddLight(18.5f, 12.5f, Y, (Vector3){ 1.55f, 0.55f, 0.45f }, 9, true);             /* R11 red alarm */
    AddLight(24, 12.5f, Y, (Vector3){ 1.40f, 1.15f, 0.82f }, 11, true);               /* R12 warm */
    /* daylight spilling in through every exterior window */
    for (int z = 0; z < MAP_H; z++) for (int x = 0; x < MAP_W; x++) {
        if (LEVEL[z][x] != 'O') continue;
        float ix = (float)x, iz = (float)z;
        if (z == 0) iz += 0.9f; else if (x == 0) ix += 0.9f; else if (x == MAP_W - 1) ix -= 0.9f; else iz -= 0.9f;
        AddLight(ix, iz, 1.8f, (Vector3){ 0.55f, 0.68f, 0.95f }, 7.5f, false);
    }
}

static bool IsSolidCharForLight(int x, int z) { return !InMap(x, z) || LEVEL[z][x] == '#'; }

static bool LightVisible(Vector3 a, Vector3 b)
{
    float dx = b.x - a.x, dz = b.z - a.z;
    float d = sqrtf(dx*dx + dz*dz);
    if (d < 0.3f) return true;
    float stop = d - 0.15f;
    int bx = ToTile(b.x), bz = ToTile(b.z);
    for (float s = 0.15f; s < stop; s += 0.2f) {
        float t = s/d;
        int tx = ToTile(a.x + dx*t), tz = ToTile(a.z + dz*t);
        if (tx == bx && tz == bz) continue;
        if (IsSolidCharForLight(tx, tz)) return false;
        char c = LevelChar(tx, tz);
        if ((c == 'D' || c == 'L') ) return false;   /* doors are closed most of the time */
    }
    return true;
}

static const Vector3 AMBIENT = { 0.13f, 0.135f, 0.15f };

/* static light at a point; n = surface normal, or zero vector for an omni probe */
static Vector3 ComputeLight(Vector3 p, Vector3 n)
{
    Vector3 acc = AMBIENT;
    bool probe = n.x == 0 && n.y == 0 && n.z == 0;
    if (!probe && n.y > 0.5f) acc = Vector3Add(acc, (Vector3){ 0.02f, 0.02f, 0.02f });
    for (int i = 0; i < numLights; i++) {
        Light *L = &lights[i];
        Vector3 d = Vector3Subtract(L->pos, p);
        float dist = Vector3Length(d);
        if (dist > L->radius) continue;
        Vector3 sp = probe ? p : Vector3Add(p, Vector3Scale(n, 0.08f));
        if (!LightVisible(L->pos, sp)) continue;
        float att = 1.0f - dist/L->radius; att = att*att;
        float ndl = probe ? 0.8f : Clamp(Vector3DotProduct(n, Vector3Scale(d, 1.0f/fmaxf(dist, 0.001f))), 0, 1)*0.85f + 0.15f;
        acc = Vector3Add(acc, Vector3Scale(L->col, att*ndl));
    }
    return acc;
}

static float DistPointBox2D(float x, float z, float x0, float z0, float x1, float z1)
{
    float dx = fmaxf(fmaxf(x0 - x, 0), x - x1), dz = fmaxf(fmaxf(z0 - z, 0), z - z1);
    return sqrtf(dx*dx + dz*dz);
}

/* distance to the nearest wall or prop footprint, for corner / contact darkening */
static float NearestSolid(float x, float z, bool includeProps)
{
    int tx = ToTile(x), tz = ToTile(z);
    float d = 9.0f;
    for (int dz = -1; dz <= 1; dz++) for (int dx = -1; dx <= 1; dx++) {
        int nx = tx + dx, nz = tz + dz;
        char c = LevelChar(nx, nz);
        if (c != '#' && c != 'W' && c != 'O') continue;
        d = fminf(d, DistPointBox2D(x, z, nx*TILE, nz*TILE, (nx + 1)*TILE, (nz + 1)*TILE));
    }
    if (includeProps)
        for (int i = 0; i < numProps; i++)
            d = fminf(d, DistPointBox2D(x, z, props[i].box.min.x, props[i].box.min.z, props[i].box.max.x, props[i].box.max.z) + 0.05f);
    return d;
}

/* bake lighting + ambient occlusion into vertex colours */
static void BakeMB(MB *b, bool isProp)
{
    for (int i = 0; i < b->count; i++) {
        Vector3 p = { b->v[i*3], b->v[i*3 + 1], b->v[i*3 + 2] };
        Vector3 n = { b->n[i*3], b->n[i*3 + 1], b->n[i*3 + 2] };
        Vector3 L = ComputeLight(p, n);
        float ao = 1.0f;
        if (n.y > 0.5f && p.y < 0.05f) ao = 0.45f + 0.55f*Smooth01(0.0f, 1.0f, NearestSolid(p.x, p.z, true));
        else if (n.y < -0.5f && p.y > WALL_H - 0.05f) ao = 0.6f + 0.4f*Smooth01(0.0f, 0.8f, NearestSolid(p.x, p.z, false));
        else if (fabsf(n.y) < 0.5f) {
            ao = (0.55f + 0.45f*Smooth01(0.0f, 0.6f, p.y)) * (0.78f + 0.22f*Smooth01(0.0f, 0.5f, WALL_H - p.y));
            if (!isProp) {
                /* inner corners: distance along the wall to a perpendicular wall */
                Vector3 q = Vector3Add(p, Vector3Scale(n, 0.6f));
                float d = NearestSolid(q.x, q.z, false);
                ao *= 0.7f + 0.3f*Smooth01(0.0f, 0.6f, d);
            }
        }
        float shade = b->c[i*4]/255.0f;   /* pre-shading from MBBox / white */
        Vector3 c = Vector3Scale(L, ao*shade*overbright);
        b->c[i*4] = ClampB(c.x*255); b->c[i*4 + 1] = ClampB(c.y*255); b->c[i*4 + 2] = ClampB(c.z*255);
    }
}

/* level geometry grouped by texture: lit and emissive */
static Mesh levelMesh[TX_COUNT];
static bool levelHas[TX_COUNT];
static Mesh emisMesh[TX_COUNT];
static bool emisHas[TX_COUNT];
static Mesh skyMesh, snowMesh;
static MB lmb[TX_COUNT], emb[TX_COUNT];
/* props are baked per type so Enhanced mode can swap a type for its 3D model */
#define PROP_TYPES 6
static MB pmb[PROP_TYPES][TX_COUNT], pemb[PROP_TYPES][TX_COUNT];
static Mesh propMesh[PROP_TYPES][TX_COUNT], propEmis[PROP_TYPES][TX_COUNT];
static bool propHas[PROP_TYPES][TX_COUNT], propEmisHas[PROP_TYPES][TX_COUNT];

static void WallFace(int dir, int x, int z, float y0, float y1, int texId)
{
    const float T = TILE;
    Vector3 O, U;
    switch (dir) {
        case 0:  O = (Vector3){ (x + 1)*T, y0, (z + 1)*T }; U = (Vector3){ 0, 0, -T }; break;   /* faces +X */
        case 1:  O = (Vector3){ x*T, y0, z*T };             U = (Vector3){ 0, 0, T };  break;   /* faces -X */
        case 2:  O = (Vector3){ x*T, y0, (z + 1)*T };       U = (Vector3){ T, 0, 0 };  break;   /* faces +Z */
        default: O = (Vector3){ (x + 1)*T, y0, z*T };       U = (Vector3){ -T, 0, 0 }; break;   /* faces -Z */
    }
    Vector3 V = { 0, y1 - y0, 0 };
    int nv = (int)ceilf((y1 - y0)/0.5f);
    float u0 = 0, u1 = 1;
    /* break up repetition: alternate tiles use the other half of the texture */
    if (((x*7 + z*13 + dir) & 1) && texId != TX_WALL_LAB) { u0 = 0.5f; u1 = 1.5f; }
    MBGrid(&lmb[texId], O, U, V, 4, nv, u0, u1, 1.0f - y0/WALL_H, 1.0f - y1/WALL_H);
}

static void PropToMB(Prop *p, MB *lm, MB *em)
{
    Matrix xf = MatrixMultiply(MatrixRotateY(p->rot), MatrixTranslate(p->pos.x, 0, p->pos.z));
    Rectangle full128[6], full256x384[6];
    for (int f = 0; f < 6; f++) { full128[f] = (Rectangle){ 0, 0, 128, 128 }; full256x384[f] = (Rectangle){ 0, 0, 256, 384 }; }
    switch (p->type) {
        case PR_CRATE:
            MBBox(&lm[TX_CRATE], (Vector3){ 0, 0.55f, 0 }, (Vector3){ 1.1f, 1.1f, 1.1f }, xf, full128, 128, 128, 0, false, ALLF & ~(1u << 5));
            break;
        case PR_CRATESTACK: {
            MBBox(&lm[TX_CRATE], (Vector3){ 0, 0.6f, 0 }, (Vector3){ 1.2f, 1.2f, 1.2f }, xf, full128, 128, 128, 0, false, ALLF & ~(1u << 5));
            Matrix top = MatrixMultiply(MatrixRotateY(p->rot + 0.45f), MatrixTranslate(p->pos.x + 0.05f, 0, p->pos.z - 0.04f));
            MBBox(&lm[TX_CRATE], (Vector3){ 0, 1.2f + 0.425f, 0 }, (Vector3){ 0.85f, 0.85f, 0.85f }, top, full128, 128, 128, 0, false, ALLF & ~(1u << 5));
        } break;
        case PR_BARREL:
            MBCylinder(&lm[TX_BARREL], (Vector3){ 0, 0, 0 }, (Vector3){ 0, 1, 0 }, 0.39f, 1.15f, 16, 1.15f, false, false, xf);
            MBCylinder(&lm[TX_STEEL], (Vector3){ 0, 1.15f, 0 }, (Vector3){ 0, 1, 0 }, 0.37f, 0.01f, 16, 0.5f, true, false, xf);
            MBCylinder(&lm[TX_STEEL], (Vector3){ 0, 0.38f, 0 }, (Vector3){ 0, 1, 0 }, 0.40f, 0.04f, 16, 0.5f, false, false, xf);
            MBCylinder(&lm[TX_STEEL], (Vector3){ 0, 0.76f, 0 }, (Vector3){ 0, 1, 0 }, 0.40f, 0.04f, 16, 0.5f, false, false, xf);
            break;
        case PR_DESK: {
            Rectangle dk[6]; for (int f = 0; f < 6; f++) dk[f] = (Rectangle){ 0, 0, 128, 128 };
            MBBox(&lm[TX_DESK], (Vector3){ 0, 0.75f, 0 }, (Vector3){ 1.7f, 0.06f, 0.85f }, xf, dk, 128, 128, 0, false, ALLF);
            for (int k = 0; k < 4; k++) {
                float lx = (k & 1) ? 0.78f : -0.78f, lz = (k & 2) ? 0.36f : -0.36f;
                MBBox(&lm[TX_STEEL], (Vector3){ lx, 0.36f, lz }, (Vector3){ 0.06f, 0.72f, 0.06f }, xf, NULL, 0, 0, 0.5f, false, ALLF & ~0x30u);
            }
            MBBox(&lm[TX_DESK], (Vector3){ 0, 0.45f, -0.36f }, (Vector3){ 1.5f, 0.5f, 0.03f }, xf, dk, 128, 128, 0, false, ALLF);
            /* drawer unit */
            MBBox(&lm[TX_STEEL], (Vector3){ 0.5f, 0.38f, 0 }, (Vector3){ 0.45f, 0.70f, 0.7f }, xf, NULL, 0, 0, 0.7f, false, ALLF & ~0x20u);
            /* CRT monitor + keyboard */
            MBBox(&lm[TX_POLYMER], (Vector3){ -0.25f, 0.78f + 0.24f, -0.12f }, (Vector3){ 0.52f, 0.44f, 0.46f }, xf, NULL, 0, 0, 0.3f, false, ALLF & ~0x20u);
            MBBox(&lm[TX_POLYMER], (Vector3){ -0.25f, 0.78f + 0.2f, -0.38f }, (Vector3){ 0.36f, 0.32f, 0.12f }, xf, NULL, 0, 0, 0.3f, false, ALLF & ~0x20u);
            {
                Vector3 O = { -0.25f - 0.21f, 0.78f + 0.07f, 0.111f }, U = { 0.42f, 0, 0 }, V = { 0, 0.32f, 0 };
                Vector3 p0 = Vector3Transform(O, xf), p1 = Vector3Transform(Vector3Add(O, U), xf);
                Vector3 p2 = Vector3Transform(Vector3Add(O, Vector3Add(U, V)), xf), p3 = Vector3Transform(Vector3Add(O, V), xf);
                Vector3 nn = Vector3Normalize(Vector3CrossProduct(Vector3Subtract(p1, p0), Vector3Subtract(p3, p0)));
                MBQuad(&em[TX_SCREEN], p0, p1, p2, p3, (Vector2){ 0, 1 }, (Vector2){ 1, 1 }, (Vector2){ 1, 0 }, (Vector2){ 0, 0 }, nn, (Color){ 210, 255, 220, 255 });
            }
            MBBox(&lm[TX_POLYMER], (Vector3){ -0.2f, 0.795f, 0.28f }, (Vector3){ 0.5f, 0.03f, 0.18f }, xf, NULL, 0, 0, 0.05f, false, ALLF & ~0x20u);
        } break;
        case PR_RACK: {
            MBBox(&lm[TX_STEEL], (Vector3){ 0, 1.1f, 0 }, (Vector3){ 1.1f, 2.2f, 0.8f }, xf, NULL, 0, 0, 0.6f, false, ALLF & ~(1u << 5));
            /* front panel (faces +Z / -Z depending on which wall it sits on) */
            float fz = p->pos.z > (ToTile(p->pos.z) + 0.5f)*TILE ? -0.401f : 0.401f;
            Vector3 O, U, V = { 0, 2.0f, 0 };
            if (fz > 0) { O = (Vector3){ -0.5f, 0.1f, fz }; U = (Vector3){ 1.0f, 0, 0 }; }
            else        { O = (Vector3){ 0.5f, 0.1f, fz };  U = (Vector3){ -1.0f, 0, 0 }; }
            Vector3 p0 = Vector3Transform(O, xf), p1 = Vector3Transform(Vector3Add(O, U), xf);
            Vector3 p2 = Vector3Transform(Vector3Add(O, Vector3Add(U, V)), xf), p3 = Vector3Transform(Vector3Add(O, V), xf);
            Vector3 nn = Vector3Normalize(Vector3CrossProduct(Vector3Subtract(p1, p0), Vector3Subtract(p3, p0)));
            MBQuad(&em[TX_RACK], p0, p1, p2, p3, (Vector2){ 0, 1 }, (Vector2){ 1, 1 }, (Vector2){ 1, 0 }, (Vector2){ 0, 0 }, nn, (Color){ 150, 155, 160, 255 });
        } break;
        case PR_PILLAR:
            MBBox(&lm[TX_WALL_CONCRETE], (Vector3){ 0, WALL_H*0.5f, 0 }, (Vector3){ 0.9f, WALL_H, 0.9f }, xf, full256x384, 256, 384, 0, false, 0x0Fu);
            MBBox(&lm[TX_HAZARD], (Vector3){ 0, 0.15f, 0 }, (Vector3){ 0.94f, 0.3f, 0.94f }, xf, NULL, 0, 0, 0.6f, false, 0x1Fu);
            break;
    }
}

static void BuildLevelMeshes(void)
{
    FloodRooms();
    SetupLights();
    memset(lmb, 0, sizeof(lmb)); memset(emb, 0, sizeof(emb));
    const int dx[4] = { 1, -1, 0, 0 }, dz[4] = { 0, 0, 1, -1 };
    for (int z = 0; z < MAP_H; z++) for (int x = 0; x < MAP_W; x++) {
        char c = LEVEL[z][x];
        if (c == '#') {
            for (int d = 0; d < 4; d++) {
                int nx = x + dx[d], nz = z + dz[d];
                if (!InMap(nx, nz) || LEVEL[nz][nx] == '#') continue;
                WallFace(d, x, z, 0, WALL_H, ThemeAt(nx, nz).wall);
            }
            continue;
        }
        Theme th = ThemeAt(x, z);
        bool isWin = (c == 'W' || c == 'O');
        if (isWin) {
            /* sill and lintel faces toward open neighbours */
            for (int d = 0; d < 4; d++) {
                int nx = x + dx[d], nz = z + dz[d];
                if (!InMap(nx, nz) || LEVEL[nz][nx] == '#') continue;
                /* face of this window block toward the neighbour = wall face of (x,z) in direction d */
                WallFace(d, x, z, 0, 0.9f, th.wall);
                WallFace(d, x, z, 2.4f, WALL_H, th.wall);
            }
            /* sill top / lintel underside + steel frame */
            bool ax = (InMap(x - 1, z) && LEVEL[z][x - 1] != '#') || (InMap(x + 1, z) && LEVEL[z][x + 1] != '#');
            MBGrid(&lmb[TX_STEEL], (Vector3){ x*TILE, 0.9f, (z + 1)*TILE }, (Vector3){ TILE, 0, 0 }, (Vector3){ 0, 0, -TILE }, 2, 2, 0, 2, 0, 2);
            MBGrid(&lmb[TX_STEEL], (Vector3){ x*TILE, 2.4f, z*TILE }, (Vector3){ TILE, 0, 0 }, (Vector3){ 0, 0, TILE }, 2, 2, 0, 2, 0, 2);
            Vector3 cc = TileCenter(x, z);
            Matrix xf = MatrixTranslate(cc.x, 0, cc.z);
            Vector3 bar = ax ? (Vector3){ 0.14f, 0.07f, TILE } : (Vector3){ TILE, 0.07f, 0.14f };
            MBBox(&lmb[TX_STEEL], (Vector3){ 0, 0.935f, 0 }, bar, xf, NULL, 0, 0, 0.5f, false, ALLF);
            MBBox(&lmb[TX_STEEL], (Vector3){ 0, 2.365f, 0 }, bar, xf, NULL, 0, 0, 0.5f, false, ALLF);
            Vector3 mull = ax ? (Vector3){ 0.12f, 1.5f, 0.07f } : (Vector3){ 0.07f, 1.5f, 0.12f };
            MBBox(&lmb[TX_STEEL], (Vector3){ 0, 1.65f, 0 }, mull, xf, NULL, 0, 0, 0.5f, false, ALLF);
            continue;
        }
        /* floor & ceiling */
        int ft = th.floor;
        if (c == 'X') ft = TX_HAZARD;
        if (c == 'D' || c == 'L') ft = TX_FLOOR_METAL;
        MBGrid(&lmb[ft], (Vector3){ x*TILE, 0, (z + 1)*TILE }, (Vector3){ TILE, 0, 0 }, (Vector3){ 0, 0, -TILE }, 4, 4, 0, 1, 0, 1);
        MBGrid(&lmb[th.ceil], (Vector3){ x*TILE, WALL_H, z*TILE }, (Vector3){ TILE, 0, 0 }, (Vector3){ 0, 0, TILE }, 4, 4, 0, 1, 0, 1);
        if (c == 'D' || c == 'L') {
            /* door frame: steel jambs on the two sides of the passage + header */
            bool ax = (InMap(x - 1, z) && LEVEL[z][x - 1] != '#') || (InMap(x + 1, z) && LEVEL[z][x + 1] != '#');
            Vector3 cc = TileCenter(x, z);
            Matrix xf = MatrixTranslate(cc.x, 0, cc.z);
            for (int s = -1; s <= 1; s += 2) {
                Vector3 jc = ax ? (Vector3){ 0, WALL_H*0.5f, s*(TILE*0.5f - 0.07f) } : (Vector3){ s*(TILE*0.5f - 0.07f), WALL_H*0.5f, 0 };
                Vector3 js = ax ? (Vector3){ 0.5f, WALL_H, 0.14f } : (Vector3){ 0.14f, WALL_H, 0.5f };
                MBBox(&lmb[TX_HAZARD], jc, js, xf, NULL, 0, 0, 0.5f, false, ALLF & ~0x30u);
            }
        }
    }
    memset(pmb, 0, sizeof(pmb)); memset(pemb, 0, sizeof(pemb));
    for (int i = 0; i < numProps; i++) {
        int t = props[i].type;
        if (t == PR_PILLAR) PropToMB(&props[i], lmb, emb);
        else PropToMB(&props[i], pmb[t], pemb[t]);
    }
    /* ceiling light fixtures */
    for (int i = 0; i < numLights; i++) {
        if (!lights[i].fixture) continue;
        Vector3 lp = lights[i].pos;
        bool alongX = (int)(lp.x*3) % 2 == 0;
        Vector3 hs = alongX ? (Vector3){ 1.1f, 0.08f, 0.5f } : (Vector3){ 0.5f, 0.08f, 1.1f };
        MBBox(&lmb[TX_STEEL], (Vector3){ lp.x, WALL_H - 0.04f, lp.z }, hs, MatrixIdentity(), NULL, 0, 0, 0.5f, false, ALLF & ~0x30u);
        float hx = hs.x*0.5f - 0.05f, hz = hs.z*0.5f - 0.05f, y = WALL_H - 0.081f;
        Color lc = { ClampB(lights[i].col.x/1.6f*255), ClampB(lights[i].col.y/1.6f*255), ClampB(lights[i].col.z/1.6f*255), 255 };
        MBQuad(&emb[TX_LIGHTPANEL], (Vector3){ lp.x - hx, y, lp.z - hz }, (Vector3){ lp.x + hx, y, lp.z - hz }, (Vector3){ lp.x + hx, y, lp.z + hz }, (Vector3){ lp.x - hx, y, lp.z + hz },
               (Vector2){ 0, 0 }, (Vector2){ 1, 0 }, (Vector2){ 1, 1 }, (Vector2){ 0, 1 }, (Vector3){ 0, -1, 0 }, lc);
    }
    for (int i = 0; i < TX_COUNT; i++) {
        if (lmb[i].count > 0) { BakeMB(&lmb[i], false); levelMesh[i] = MBFinish(&lmb[i]); levelHas[i] = true; }
        if (emb[i].count > 0) { emisMesh[i] = MBFinish(&emb[i]); emisHas[i] = true; }
        for (int t = 0; t < PROP_TYPES; t++) {
            if (pmb[t][i].count > 0) { BakeMB(&pmb[t][i], false); propMesh[t][i] = MBFinish(&pmb[t][i]); propHas[t][i] = true; }
            if (pemb[t][i].count > 0) { propEmis[t][i] = MBFinish(&pemb[t][i]); propEmisHas[t][i] = true; }
        }
    }
    /* sky box (inside faces) and the snow field around the building */
    MB b = { 0 };
    float S = 160.0f, cx = MAP_W*TILE*0.5f, cz = MAP_H*TILE*0.5f, yb = -40.0f, yt = 110.0f;
    Vector3 ns[4] = { { 0, 0, 1 }, { -1, 0, 0 }, { 0, 0, -1 }, { 1, 0, 0 } };
    for (int k = 0; k < 4; k++) {
        Vector3 n = ns[k];
        Vector3 Ud = Vector3CrossProduct((Vector3){ 0, 1, 0 }, n);
        Vector3 O = { cx - n.x*S - Ud.x*S, yb, cz - n.z*S - Ud.z*S };
        MBGrid(&b, O, Vector3Scale(Ud, 2*S), (Vector3){ 0, yt - yb, 0 }, 4, 1, k*0.25f, (k + 1)*0.25f, 1.0f, 0.0f);
    }
    MBGrid(&b, (Vector3){ cx - S, yt, cz + S }, (Vector3){ 2*S, 0, 0 }, (Vector3){ 0, 0, -2*S }, 1, 1, 0, 1, 0.005f, 0.01f);
    /* winding of the top quad points up; flip it to face down (inside) */
    {
        int start = b.count - 6;
        for (int t = start; t < b.count; t += 3) {
            for (int k = 0; k < 3; k++) { float tmp = b.v[(t + 1)*3 + k]; b.v[(t + 1)*3 + k] = b.v[(t + 2)*3 + k]; b.v[(t + 2)*3 + k] = tmp; }
            for (int k = 0; k < 2; k++) { float tmp = b.t[(t + 1)*2 + k]; b.t[(t + 1)*2 + k] = b.t[(t + 2)*2 + k]; b.t[(t + 2)*2 + k] = tmp; }
        }
    }
    skyMesh = MBFinish(&b);
    MBGrid(&b, (Vector3){ cx - S, -0.02f, cz + S }, (Vector3){ 2*S, 0, 0 }, (Vector3){ 0, 0, -2*S }, 16, 16, 0, 2*S/6.0f, 0, 2*S/6.0f);
    for (int i = 0; i < b.count; i++) { unsigned char v = ClampB(255*0.95f*overbright); b.c[i*4] = v; b.c[i*4 + 1] = v; b.c[i*4 + 2] = ClampB(255*1.0f*overbright); }
    snowMesh = MBFinish(&b);
}

/* ---------------- per-view dynamic lights ---------------- */
static void SetupViewLights(Camera3D cam)
{
    if (!shaderOk) return;
    float pos[16] = { 0 }, col[16] = { 0 };
    int n = 0;
    for (int i = 0; i < numPlayers && n < 4; i++) {
        Player *p = &players[i];
        if (!p->alive || p->muzzle <= 0) continue;
        Vector3 f = PlayerForward(p);
        float k = PlayerSilenced(p) ? 0.35f : 1.0f;
        pos[n*4] = p->pos.x + f.x*0.8f; pos[n*4 + 1] = EYE_H + f.y*0.8f; pos[n*4 + 2] = p->pos.z + f.z*0.8f; pos[n*4 + 3] = 8.0f;
        col[n*4] = 2.4f*k; col[n*4 + 1] = 1.7f*k; col[n*4 + 2] = 0.8f*k;
        n++;
    }
    for (int i = 0; i < numEnemies && n < 4 && gState != GS_DM; i++) {
        Enemy *e = &enemies[i];
        if (e->state == E_DEAD || e->muzzle <= 0) continue;
        Vector3 m = EnemyMuzzlePos(e);
        pos[n*4] = m.x; pos[n*4 + 1] = m.y; pos[n*4 + 2] = m.z; pos[n*4 + 3] = 7.0f;
        col[n*4] = 2.2f; col[n*4 + 1] = 1.5f; col[n*4 + 2] = 0.7f;
        n++;
    }
    if (n < 4 && gState == GS_MISSION && exitX >= 0) {
        Vector3 c = TileCenter(exitX, exitZ);
        float pulse = 0.5f + 0.5f*sinf(gTime*4.0f);
        pos[n*4] = c.x; pos[n*4 + 1] = 0.6f; pos[n*4 + 2] = c.z; pos[n*4 + 3] = 4.5f;
        col[n*4] = 0.1f; col[n*4 + 1] = 0.9f*pulse + 0.3f; col[n*4 + 2] = 0.35f;
        n++;
    }
    SetShaderValueV(gShader, locDynPos, pos, SHADER_UNIFORM_VEC4, 4);
    SetShaderValueV(gShader, locDynCol, col, SHADER_UNIFORM_VEC4, 4);
    SetShaderValue(gShader, locDynCount, &n, SHADER_UNIFORM_INT);
    SetShaderValue(gShader, locViewPos, &cam.position, SHADER_UNIFORM_VEC3);
    EnhSetupView(cam, pos, col, n);
}

static Color LightColor(Vector3 L, float a)
{
    return (Color){ ClampB(L.x*0.75f*255), ClampB(L.y*0.75f*255), ClampB(L.z*0.75f*255), ClampB(a*255) };
}

static float FogFactor(Vector3 p, Vector3 cam)
{
    float d = Vector3Distance(p, cam)*gFogDensity;
    return 1.0f - expf(-d*d);
}

/* ---------------- characters ---------------- */
typedef struct {
    Vector3 pos;
    float yaw, walk, speed, aim, death, deathDir, flash, muzzle;
    bool dead, golden;
    int variant;
} CharDraw;

static Matrix MM(Matrix a, Matrix b) { return MatrixMultiply(a, b); }

static void DrawBlobShadow(Vector3 p, float r, float a)
{
    rlSetTexture(tex[TX_SOFT].id);
    rlBegin(RL_QUADS);
    rlColor4ub(0, 0, 0, ClampB(a*255));
    float y = 0.012f;
    rlTexCoord2f(0, 0); rlVertex3f(p.x - r, y, p.z - r);
    rlTexCoord2f(0, 1); rlVertex3f(p.x - r, y, p.z + r);
    rlTexCoord2f(1, 1); rlVertex3f(p.x + r, y, p.z + r);
    rlTexCoord2f(1, 0); rlVertex3f(p.x + r, y, p.z - r);
    rlEnd();
    rlSetTexture(0);
}

static void DrawCharacter(const CharDraw *c, Camera3D cam)
{
    int tid = TX_CHAR_SOLDIER + c->variant;
    Vector3 L = ComputeLight((Vector3){ c->pos.x, 1.2f, c->pos.z }, (Vector3){ 0 });
    if (c->flash > 0) L = Vector3Add(L, (Vector3){ 1.4f, 1.3f, 1.2f });
    float s = Clamp(c->speed/2.6f, 0, 1);
    float ph = c->walk;
    float swing = sinf(ph)*0.55f*s;
    float bob = fabsf(cosf(ph))*0.035f*s;
    float aim = c->aim;

    /* death: knees buckle, then the body topples with a small bounce */
    float fallT = 0, fall = 0, knee = 0, bounce = 0;
    if (c->dead) {
        fallT = Clamp(c->death*1.9f, 0, 1);
        fall = fallT*fallT;
        if (c->death > 0.53f) bounce = sinf((c->death - 0.53f)*14.0f)*expf(-(c->death - 0.53f)*7.0f)*0.12f;
        knee = sinf(fallT*PI)*0.9f + fallT*0.25f;
        swing = 0; bob = 0; aim = 0;
    }
    float dir = c->deathDir == 0 ? 1.0f : c->deathDir;
    Matrix root = MM(MM(MM(MatrixRotateZ(dir*(fall*1.52f - bounce)), MatrixTranslate(-dir*0.2f*fall, 0.05f*fall, 0)),
                        MatrixRotateY(-c->yaw)), MatrixTranslate(c->pos.x, 0, c->pos.z));
    Matrix hips = MM(MatrixTranslate(0, 1.0f + bob - knee*0.12f, 0), root);
    DrawMeshTint(charMesh[CP_HIPS], tid, L, hips);
    for (int side = -1; side <= 1; side += 2) {
        float sw = side > 0 ? swing : -swing;
        float kn = s*fmaxf(0.0f, sinf(ph + (side > 0 ? 1.6f : 1.6f + PI)))*0.9f + knee*1.3f;
        Matrix thigh = MM(MM(MatrixRotateZ(sw + knee*0.6f), MatrixTranslate(0, -0.02f, side*0.105f)), hips);
        DrawMeshTint(charMesh[CP_THIGH], tid, L, thigh);
        Matrix shin = MM(MM(MatrixRotateZ(-kn), MatrixTranslate(0, -0.46f, 0)), thigh);
        DrawMeshTint(charMesh[CP_SHIN], tid, L, shin);
    }
    Matrix torso = MM(MM(MM(MatrixRotateY(0.18f*aim), MatrixRotateZ(-0.07f*aim - 0.05f*s + fallT*0.3f)), MatrixTranslate(0, 0.04f, 0)), hips);
    DrawMeshTint(charMesh[CP_TORSO], tid, L, torso);
    Matrix head = MM(MM(MatrixRotateY(-0.15f*aim), MatrixTranslate(0, 0.56f, 0)), torso);
    DrawMeshTint(charMesh[CP_HEAD], tid, L, head);
    int hat = CHAR_STYLES[c->variant].hatType;
    if (hat == 1) DrawMeshTint(charMesh[CP_HELMET], tid, L, head);
    else if (hat == 2) DrawMeshTint(charMesh[CP_CAP], tid, L, head);
    else if (hat == 3) DrawMeshTint(charMesh[CP_BEANIE], tid, L, head);

    /* arms + rifle, blended between low-ready (patrol) and aiming */
    float armSwing = sinf(ph)*0.18f*s*(1 - aim);
    float ruz = Lerp(0.25f, 1.05f, aim) + armSwing, rux = Lerp(0.45f, 0.32f, aim), rfz = Lerp(1.1f, 0.5f, aim);
    float luz = Lerp(0.70f, 1.35f, aim) - armSwing, lux = Lerp(-0.45f, -0.62f, aim), lfz = Lerp(0.8f, 0.22f, aim);
    if (c->dead) { ruz = 0.2f + fallT*1.6f; rux = 0.2f; rfz = 0.4f; luz = 0.1f + fallT*1.9f; lux = -0.3f; lfz = 0.5f; }
    Matrix ua = MM(MM(MM(MatrixRotateZ(ruz), MatrixRotateX(rux)), MatrixTranslate(0, 0.47f, 0.29f)), torso);
    DrawMeshTint(charMesh[CP_UPPERARM], tid, L, ua);
    DrawMeshTint(charMesh[CP_FOREARM], tid, L, MM(MM(MatrixRotateZ(rfz), MatrixTranslate(0, -0.29f, 0)), ua));
    Matrix la = MM(MM(MM(MatrixRotateZ(luz), MatrixRotateX(lux)), MatrixTranslate(0, 0.47f, -0.29f)), torso);
    DrawMeshTint(charMesh[CP_UPPERARM], tid, L, la);
    DrawMeshTint(charMesh[CP_FOREARM], tid, L, MM(MM(MatrixRotateZ(lfz), MatrixTranslate(0, -0.29f, 0)), la));
    if (!c->dead) {
        Vector3 rp = { Lerp(0.30f, 0.40f, aim), Lerp(0.18f, 0.40f, aim), Lerp(0.05f, 0.12f, aim) };
        Matrix rifle = MM(MM(MM(MatrixRotateZ(Lerp(-0.65f, 0.0f, aim)), MatrixRotateY(Lerp(0.30f, 0.04f, aim))), MatrixTranslate(rp.x, rp.y, rp.z)), torso);
        DrawMeshTint(charMesh[CP_RIFLE], c->golden ? TX_GOLD : tid, c->golden ? Vector3Scale(L, 1.4f) : L, rifle);
        if (c->muzzle > 0) {
            Vector3 mp = Vector3Transform((Vector3){ 0.60f, 0.01f, 0 }, rifle);
            rlDrawRenderBatchActive();
            BeginBlendMode(BLEND_ADDITIVE);
            rlDisableDepthMask();
            DrawBillboard(cam, tex[TX_FLASH], mp, 0.55f, WHITE);
            DrawBillboard(cam, tex[TX_SOFT], mp, 1.4f, (Color){ 255, 170, 60, 120 });
            rlDrawRenderBatchActive();
            rlEnableDepthMask();
            EndBlendMode();
        }
    }
}

static void DrawShadowsFor(Vector3 p, float r, float a)
{
    rlDrawRenderBatchActive();
    rlDisableDepthMask();
    BeginBlendMode(BLEND_ALPHA);
    DrawBlobShadow(p, r, a);
    EndBlendMode();
    rlDrawRenderBatchActive();
    rlEnableDepthMask();
}

#include "gfx_enhanced.c"
#include "input_pad.c"

/* ---------------- world pieces ---------------- */
static void DrawDoors(void)
{
    for (int z = 0; z < MAP_H; z++) for (int x = 0; x < MAP_W; x++) {
        int t = tiles[z][x];
        if (t != T_DOOR && t != T_LOCKED) continue;
        float o = doorOpen[z][x];
        if (o >= 0.99f) continue;
        Vector3 c = TileCenter(x, z);
        Matrix rot = axisX[z][x] ? MatrixIdentity() : MatrixRotateY(PI*0.5f);
        Vector3 L = ComputeLight((Vector3){ c.x, 1.6f, c.z }, (Vector3){ 0 });
        bool armoury = LEVEL[z][x] == 'L';
        DrawMeshTint(pickMesh[PM_DOOR], armoury ? TX_DOOR_ARMORY : TX_DOOR, L, MM(rot, MatrixTranslate(c.x, o*2.95f, c.z)));
        if (t == T_LOCKED) {
            for (int s = -1; s <= 1; s += 2) {
                Vector3 off = axisX[z][x] ? (Vector3){ s*0.17f, 0, 0 } : (Vector3){ 0, 0, s*0.17f };
                DrawMeshTint(pickMesh[PM_PADLOCK], TX_GOLD, Vector3Scale(L, 1.3f), MM(rot, MatrixTranslate(c.x + off.x, 1.1f, c.z + off.z)));
            }
        }
    }
}

static void DrawPickups(Camera3D cam)
{
    for (int i = 0; i < numPickups; i++) {
        Pickup *pk = &pickups[i];
        if (!pk->active) continue;
        Vector3 p = pk->pos;
        float spin = gTime*1.6f + pk->yaw;
        float hover = 0.30f + 0.06f*sinf(gTime*2.5f + i);
        Vector3 L = Vector3Scale(ComputeLight((Vector3){ p.x, 0.8f, p.z }, (Vector3){ 0 }), 1.15f);
        L = Vector3Add(L, (Vector3){ 0.15f, 0.15f, 0.15f });
        Matrix M = MM(MatrixRotateY(spin), MatrixTranslate(p.x, hover, p.z));
        switch (pk->type) {
            case PK_AMMO:   DrawMeshTint(pickMesh[PM_AMMOBOX], TX_AMMOBOX, L, M); break;
            case PK_HEALTH: DrawMeshTint(pickMesh[PM_VEST], TX_VEST, L, MM(MatrixTranslate(0, -0.15f, 0), M)); break;
            case PK_DISK:   DrawMeshTint(pickMesh[PM_DISK], TX_DISK, Vector3Add(L, (Vector3){ 0.3f, 0.3f, 0.4f }), MM(MatrixTranslate(0, 0.45f, 0), M)); break;
            case PK_GOLDEN: {
                if (Frand() < 0.15f) SpawnPart(P_GLINT, (Vector3){ p.x + Frand2()*0.3f, hover + 0.3f + Frand2()*0.2f, p.z + Frand2()*0.3f }, (Vector3){ 0, 0.2f, 0 }, 0.4f, 0.18f, (Color){ 255, 230, 140, 255 });
                if (EnhDrawPickupWeapon(PK_GOLDEN, p, spin, hover, pk->yaw, L)) break;
                Matrix G = MM(MM(MatrixScale(3.0f, 3.0f, 3.0f), MatrixRotateY(spin)), MatrixTranslate(p.x, hover + 0.35f, p.z));
                Vector3 GL = Vector3Add(Vector3Scale(L, 1.3f), (Vector3){ 0.3f, 0.25f, 0.1f });
                DrawMeshTint(vmMesh[VM_PISTOL_SLIDE], TX_GOLD, GL, G);
                DrawMeshTint(vmMesh[VM_PISTOL_FRAME], TX_GOLD, GL, G);
                DrawMeshTint(vmMesh[VM_PISTOL_GRIP], TX_GOLD, GL, G);
            } break;
            case PK_KF7:
                if (EnhDrawPickupWeapon(PK_KF7, p, spin, hover, pk->yaw, L)) break;
                DrawMeshTint(charMesh[CP_RIFLE], TX_CHAR_SOLDIER, L, MM(MM(MatrixRotateX(PI*0.5f), MatrixRotateY(pk->yaw)), MatrixTranslate(p.x, 0.05f, p.z)));
                break;
        }
        DrawShadowsFor((Vector3){ p.x, 0, p.z }, pk->type == PK_KF7 ? 0.45f : 0.38f, pk->type == PK_KF7 ? 0.35f : 0.45f);
        if (pk->type == PK_DISK || pk->type == PK_GOLDEN) {
            rlDrawRenderBatchActive();
            BeginBlendMode(BLEND_ADDITIVE);
            rlDisableDepthMask();
            Color gc = pk->type == PK_DISK ? (Color){ 60, 140, 255, 110 } : (Color){ 255, 190, 60, 110 };
            DrawBillboard(cam, tex[TX_SOFT], (Vector3){ p.x, hover + 0.4f, p.z }, 1.3f + 0.15f*sinf(gTime*5), gc);
            rlDrawRenderBatchActive();
            rlEnableDepthMask();
            EndBlendMode();
        }
    }
}

static void Quad3D(Vector3 c, Vector3 t, Vector3 b, float s, Color col)
{
    Vector3 p0 = Vector3Add(c, Vector3Scale(Vector3Add(Vector3Negate(t), Vector3Negate(b)), s));
    Vector3 p1 = Vector3Add(c, Vector3Scale(Vector3Subtract(t, b), s));
    Vector3 p2 = Vector3Add(c, Vector3Scale(Vector3Add(t, b), s));
    Vector3 p3 = Vector3Add(c, Vector3Scale(Vector3Subtract(b, t), s));
    rlColor4ub(col.r, col.g, col.b, col.a);
    rlTexCoord2f(0, 1); rlVertex3f(p0.x, p0.y, p0.z);
    rlTexCoord2f(1, 1); rlVertex3f(p1.x, p1.y, p1.z);
    rlTexCoord2f(1, 0); rlVertex3f(p2.x, p2.y, p2.z);
    rlTexCoord2f(0, 0); rlVertex3f(p3.x, p3.y, p3.z);
}

static void DrawDecals(Camera3D cam)
{
    rlDrawRenderBatchActive();
    rlDisableDepthMask();
    rlDisableBackfaceCulling();
    BeginBlendMode(BLEND_ALPHA);
    rlSetTexture(tex[TX_HOLE].id);
    rlBegin(RL_QUADS);
    for (int i = 0; i < MAX_DECALS; i++) {
        Decal *d = &decals[i];
        if (d->life <= 0) continue;
        Vector3 n = d->n;
        Vector3 ref = fabsf(n.y) > 0.9f ? (Vector3){ 1, 0, 0 } : (Vector3){ 0, 1, 0 };
        Vector3 t = Vector3Normalize(Vector3CrossProduct(n, ref));
        Vector3 b = Vector3CrossProduct(n, t);
        Vector3 t2 = Vector3Add(Vector3Scale(t, cosf(d->rot)), Vector3Scale(b, sinf(d->rot)));
        Vector3 b2 = Vector3CrossProduct(n, t2);
        float a = Clamp(d->life/3.0f, 0, 1) * (1.0f - FogFactor(d->pos, cam.position));
        Color c = LightColor(d->light, a);
        Quad3D(Vector3Add(d->pos, Vector3Scale(n, 0.008f)), t2, b2, d->size, c);
    }
    rlEnd();
    rlSetTexture(0);
    EndBlendMode();
    rlDrawRenderBatchActive();
    rlEnableBackfaceCulling();
    rlEnableDepthMask();
}

static void DrawGlass(Camera3D cam)
{
    rlDrawRenderBatchActive();
    rlDisableBackfaceCulling();
    rlDisableDepthMask();
    BeginBlendMode(BLEND_ALPHA);
    rlSetTexture(tex[TX_GLASS].id);
    rlBegin(RL_QUADS);
    for (int z = 0; z < MAP_H; z++) for (int x = 0; x < MAP_W; x++) {
        if (tiles[z][x] != T_WINDOW) continue;
        Vector3 c = TileCenter(x, z);
        Vector3 L = ComputeLight((Vector3){ c.x, 1.6f, c.z }, (Vector3){ 0 });
        Color col = LightColor(Vector3Add(L, (Vector3){ 0.35f, 0.4f, 0.5f }), 0.85f);
        float y0 = 0.97f, y1 = 2.33f;
        for (int half = 0; half < 2; half++) {
            float a0 = half ? 0.06f : -TILE*0.5f + 0.02f, a1 = half ? TILE*0.5f - 0.02f : -0.06f;
            rlColor4ub(col.r, col.g, col.b, col.a);
            if (axisX[z][x]) {
                rlTexCoord2f(0, 1); rlVertex3f(c.x, y0, c.z + a0);
                rlTexCoord2f(1, 1); rlVertex3f(c.x, y0, c.z + a1);
                rlTexCoord2f(1, 0); rlVertex3f(c.x, y1, c.z + a1);
                rlTexCoord2f(0, 0); rlVertex3f(c.x, y1, c.z + a0);
            } else {
                rlTexCoord2f(0, 1); rlVertex3f(c.x + a0, y0, c.z);
                rlTexCoord2f(1, 1); rlVertex3f(c.x + a1, y0, c.z);
                rlTexCoord2f(1, 0); rlVertex3f(c.x + a1, y1, c.z);
                rlTexCoord2f(0, 0); rlVertex3f(c.x + a0, y1, c.z);
            }
        }
    }
    rlEnd();
    rlSetTexture(0);
    EndBlendMode();
    rlDrawRenderBatchActive();
    rlEnableDepthMask();
    rlEnableBackfaceCulling();
    (void)cam;
}

static void DrawParticlesAndGlows(Camera3D cam)
{
    /* solid bits: shells and chips */
    for (int i = 0; i < MAX_PARTICLES; i++) {
        Particle *p = &parts[i];
        if (p->life <= 0 || (p->type != P_SHELL && p->type != P_CHIP)) continue;
        if (Vector3Distance(p->pos, cam.position) < 0.7f) continue;   /* don't draw casings in your face */
        float sx = p->type == P_SHELL ? p->size*1.0f : p->size, sy = p->type == P_SHELL ? p->size*1.0f : p->size, sz = p->type == P_SHELL ? p->size*2.4f : p->size;
        float cr = cosf(p->rot), sr = sinf(p->rot);
        sx = fabsf(sx*cr) + fabsf(sz*sr); sz = fabsf(sz*cr) + fabsf(sx*sr);
        DrawCube(p->pos, sx*2, sy*2, sz, p->col);
    }
    rlDrawRenderBatchActive();
    rlDisableDepthMask();
    BeginBlendMode(BLEND_ALPHA);
    for (int i = 0; i < MAX_PARTICLES; i++) {
        Particle *p = &parts[i];
        if (p->life <= 0 || (p->type != P_DUST && p->type != P_SMOKE)) continue;
        float a = (p->life/p->maxLife);
        Color c = p->col; c.a = ClampB(c.a*a);
        DrawBillboard(cam, tex[TX_SOFT], p->pos, p->size*2, c);
    }
    EndBlendMode();
    BeginBlendMode(BLEND_ADDITIVE);
    for (int i = 0; i < MAX_PARTICLES; i++) {
        Particle *p = &parts[i];
        if (p->life <= 0 || (p->type != P_SPARK && p->type != P_GLINT)) continue;
        float a = p->life/p->maxLife;
        Color c = p->col; c.a = ClampB(255*a);
        if (p->type == P_SPARK) {
            /* streak: two overlapping sprites along velocity */
            DrawBillboard(cam, tex[TX_SPARK], p->pos, p->size*2.2f, c);
            DrawBillboard(cam, tex[TX_SPARK], Vector3Subtract(p->pos, Vector3Scale(p->vel, 0.012f)), p->size*1.6f, c);
        } else DrawBillboard(cam, tex[TX_FLASH], p->pos, p->size*(0.6f + a), c);
    }
    /* light fixture glow */
    for (int i = 0; i < numLights; i++) {
        if (!lights[i].fixture) continue;
        Vector3 gp = { lights[i].pos.x, WALL_H - 0.16f, lights[i].pos.z };
        float fade = 1.0f - FogFactor(gp, cam.position);
        Color c = { ClampB(lights[i].col.x*60), ClampB(lights[i].col.y*60), ClampB(lights[i].col.z*60), ClampB(255*fade) };
        DrawBillboard(cam, tex[TX_SOFT], gp, 2.0f, c);
    }
    if (gState == GS_MISSION && exitX >= 0) {
        Vector3 c = TileCenter(exitX, exitZ);
        float pulse = 0.6f + 0.4f*sinf(gTime*4.0f);
        for (int k = 0; k < 4; k++)
            DrawBillboard(cam, tex[TX_SOFT], (Vector3){ c.x, 0.4f + k*0.55f, c.z }, 1.6f - k*0.2f, (Color){ 40, ClampB(200*pulse), 90, 255 });
    }
    rlDrawRenderBatchActive();
    EndBlendMode();
    rlEnableDepthMask();
}

static void DrawStatic(void)
{
    Matrix I = MatrixIdentity();
    for (int i = 0; i < TX_COUNT; i++) if (levelHas[i]) { EnhLevelMaterial(i); DrawMesh(levelMesh[i], mats[i], I); }
    for (int t = 0; t < PROP_TYPES; t++) {
        if (PropTypeEnhanced(t)) continue;
        for (int i = 0; i < TX_COUNT; i++) if (propHas[t][i]) { EnhLevelMaterial(i); DrawMesh(propMesh[t][i], mats[i], I); }
    }
    SetUnlit(true);
    for (int i = 0; i < TX_COUNT; i++) if (emisHas[i]) DrawMesh(emisMesh[i], mats[i], I);
    for (int t = 0; t < PROP_TYPES; t++) {
        if (PropTypeEnhanced(t)) continue;
        for (int i = 0; i < TX_COUNT; i++) if (propEmisHas[t][i]) DrawMesh(propEmis[t][i], mats[i], I);
    }
    SetUnlit(false);
    EnhLevelMaterial(TX_DOOR);
    EnhDrawProps();
}

static void DrawSkyAndSnow(Camera3D cam)
{
    SetUnlit(true);
    SetFog(0.0f);
    rlDisableDepthMask();
    Matrix follow = MatrixTranslate(cam.position.x - MAP_W*TILE*0.5f, 0, cam.position.z - MAP_H*TILE*0.5f);
    DrawMesh(skyMesh, mats[TX_SKY], follow);
    rlEnableDepthMask();
    SetUnlit(false);
    SetFog(0.006f);
    if (shaderOk) { Vector3 haze = { 0.80f, 0.84f, 0.90f }; SetShaderValue(gShader, locFogColor, &haze, SHADER_UNIFORM_VEC3); }
    DrawMesh(snowMesh, mats[TX_SNOW], MatrixIdentity());
    if (shaderOk) SetShaderValue(gShader, locFogColor, &FOG_RGB, SHADER_UNIFORM_VEC3);
    SetFog(gFogDensity);
}

static CharDraw EnemyDraw(Enemy *e)
{
    CharDraw c = { 0 };
    c.pos = e->pos; c.yaw = e->yaw; c.walk = e->walk; c.speed = e->speed; c.aim = e->aim;
    c.dead = e->state == E_DEAD; c.death = e->deathT; c.deathDir = e->deathDir;
    c.flash = e->hurtFlash; c.muzzle = e->muzzle; c.variant = e->variant;
    return c;
}

static CharDraw PlayerCharDraw(Player *p)
{
    CharDraw c = { 0 };
    c.pos = p->pos; c.yaw = p->yaw; c.walk = p->bob*0.75f; c.speed = p->moveAmt*4.5f; c.aim = 1.0f;
    c.dead = !p->alive; c.death = p->deathT; c.deathDir = 1;
    c.flash = p->hurtFlash > 0.3f ? 0.1f : 0; c.muzzle = p->muzzle; c.variant = p->variant; c.golden = p->weapon == W_GOLDEN;
    return c;
}

static void DrawWorld(Camera3D cam, int viewer)
{
    ClearBackground((Color){ 22, 23, 27, 255 });
    BeginMode3D(cam);
    SetupViewLights(cam);
    SetFog(gFogDensity);
    SetUnlit(false);
    DrawSkyAndSnow(cam);
    DrawStatic();
    DrawDoors();
    if (gState != GS_DM) {
        for (int i = 0; i < numEnemies; i++) {
            Enemy *e = &enemies[i];
            if (Vector3Distance(e->pos, cam.position) > 60) continue;
            CharDraw c = EnemyDraw(e);
            if (EnhDrawCharacter(&c, cam, i, W_KF7, false)) continue;
            DrawCharacter(&c, cam);
            DrawShadowsFor(e->pos, e->state == E_DEAD ? 0.9f : 0.55f, 0.5f);
        }
    } else {
        for (int i = 0; i < numPlayers; i++) {
            Player *p = &players[i];
            if (i == viewer) continue;
            if (!p->alive && p->deathT > 2.4f) continue;
            CharDraw c = PlayerCharDraw(p);
            if (EnhDrawCharacter(&c, cam, MAX_ENEMIES + i, p->weapon, PlayerSilenced(p))) continue;
            DrawCharacter(&c, cam);
            DrawShadowsFor(p->pos, 0.55f, 0.5f);
        }
    }
    DrawPickups(cam);
    DrawDecals(cam);
    DrawParticlesAndGlows(cam);
    DrawGlass(cam);
    EndMode3D();
}

static Camera3D PlayerCamera(Player *p)
{
    Camera3D c = { 0 };
    float bob = sinf(p->bob) * 0.035f * p->moveAmt;
    float dy = 0;
    if (!p->alive) dy = -Clamp(p->deathT*1.5f, 0, 1)*1.2f;
    c.position = (Vector3){ p->pos.x, EYE_H + bob + dy, p->pos.z };
    c.target = Vector3Add(c.position, PlayerForward(p));
    c.up = (Vector3){ 0, 1, 0 };
    if (!p->alive) { float r = Clamp(p->deathT*1.5f, 0, 1)*0.5f; c.up = (Vector3){ -sinf(p->yaw)*r, 1, cosf(p->yaw)*r }; }
    c.fovy = 65.0f - 20.0f*p->aimZoom;
    c.projection = CAMERA_PERSPECTIVE;
    return c;
}

/* ---------------- first-person weapon ---------------- */
static void DrawViewModel(Player *p, Camera3D cam)
{
    if (!p->alive) return;
    rlDrawRenderBatchActive();
    glClear(GL_DEPTH_BUFFER_BIT_);
    Vector3 f = Vector3Normalize(Vector3Subtract(cam.target, cam.position));
    Vector3 r = Vector3Normalize(Vector3CrossProduct(f, (Vector3){ 0, 1, 0 }));
    Vector3 u = Vector3CrossProduct(r, f);
    Vector3 e = cam.position;
    Matrix V = { r.x, u.x, -f.x, e.x,  r.y, u.y, -f.y, e.y,  r.z, u.z, -f.z, e.z,  0, 0, 0, 1 };

    const WeaponDef *w = &WEAPONS[p->weapon];
    bool rifle = p->weapon == W_KF7, golden = p->weapon == W_GOLDEN, sil = PlayerSilenced(p);
    float bx = sinf(p->bob*0.5f)*0.011f*p->moveAmt, by = -fabsf(cosf(p->bob*0.5f))*0.010f*p->moveAmt;
    float idle = sinf(gTime*1.3f)*0.002f;
    float dip = 0;
    if (p->reloadTimer > 0) dip = sinf((1.0f - p->reloadTimer/w->reloadTime)*PI);
    float low = (1.0f - p->raise); low = low*low*0.22f;
    Vector3 base = rifle ? (Vector3){ 0.13f, -0.135f, -0.33f } : (Vector3){ 0.15f, -0.115f, -0.40f };
    float kick = p->kick*p->kick;
    Matrix G = MM(MM(MM(MatrixRotateX(kick*(rifle ? 0.06f : 0.22f) - dip*0.35f), MatrixRotateZ(dip*0.6f)), MatrixRotateY(0.05f)),
                  MatrixTranslate(base.x + bx, base.y + by + idle - dip*0.10f - low, base.z + kick*(rifle ? 0.03f : 0.04f)));
    Matrix GV = MM(G, V);
    Vector3 L = ComputeLight(e, (Vector3){ 0 });
    L = Vector3Add(Vector3Scale(L, 0.9f), (Vector3){ 0.12f, 0.12f, 0.12f });
    Vector3 sleeveTint = p->variant == 4 ? (Vector3){ 2.9f, 2.4f, 1.8f } : (Vector3){ 1, 1, 1 };
    int metal = golden ? TX_GOLD : TX_GUNMETAL;
    Vector3 ML = golden ? Vector3Add(Vector3Scale(L, 1.25f), (Vector3){ 0.15f, 0.12f, 0.05f }) : Vector3Scale(L, rifle ? 0.8f : 1.05f);
    Vector3 wrist;
    if (!rifle) {
        float slide = p->muzzle > 0 ? 0.028f : (p->mag[p->weapon] == 0 ? 0.024f : 0.0f);
        DrawMeshTint(vmMesh[VM_PISTOL_SLIDE], metal, ML, MM(MatrixTranslate(0, 0, slide), GV));
        DrawMeshTint(vmMesh[VM_PISTOL_FRAME], metal, ML, GV);
        DrawMeshTint(vmMesh[VM_PISTOL_GRIP], golden ? TX_GOLD : TX_POLYMER, ML, GV);
        if (sil) DrawMeshTint(vmMesh[VM_SILENCER], TX_GUNMETAL, Vector3Scale(L, 0.8f), GV);
        DrawMeshTint(vmMesh[VM_HAND_R], TX_SKIN, L, GV);
        wrist = (Vector3){ 0.006f, -0.088f, 0.04f };
    } else {
        DrawMeshTint(vmMesh[VM_RIFLE_METAL], TX_GUNMETAL, ML, GV);
        DrawMeshTint(vmMesh[VM_RIFLE_WOOD], TX_GUNWOOD, L, GV);
        DrawMeshTint(vmMesh[VM_RIFLE_GRIP], TX_POLYMER, ML, GV);
        DrawMeshTint(vmMesh[VM_HAND_R], TX_SKIN, L, MM(MatrixTranslate(0, -0.02f, 0.045f), GV));
        DrawMeshTint(vmMesh[VM_HAND_L], TX_SKIN, L, MM(MatrixTranslate(0, -0.01f, -0.30f), GV));
        Matrix sl = MM(MM(MM(MatrixRotateX(0.45f), MatrixRotateY(-0.75f)), MatrixTranslate(-0.035f, -0.06f, -0.26f)), GV);
        DrawMeshTint(vmMesh[VM_CUFF_L], TX_CUFF, L, MM(MatrixTranslate(0, 0, -0.02f), sl));
        DrawMeshTint(vmMesh[VM_SLEEVE_L], TX_SLEEVE, Vector3Multiply(L, sleeveTint), sl);
        wrist = (Vector3){ 0.008f, -0.125f, 0.085f };
    }
    Matrix sr = MM(MM(MM(MatrixRotateX(rifle ? 0.35f : 0.2f), MatrixRotateY(rifle ? 0.42f : 0.55f)), MatrixTranslate(wrist.x, wrist.y, wrist.z)), GV);
    DrawMeshTint(vmMesh[VM_CUFF_R], TX_CUFF, L, MM(MatrixTranslate(0, 0, -0.02f), sr));
    DrawMeshTint(vmMesh[VM_SLEEVE_R], TX_SLEEVE, Vector3Multiply(L, sleeveTint), sr);

    if (p->muzzle > 0) {
        Vector3 mp = rifle ? (Vector3){ 0, 0.012f, -0.475f } : sil ? (Vector3){ 0, 0.022f, -0.29f } : (Vector3){ 0, 0.022f, -0.17f };
        Vector3 cv = Vector3Transform(mp, G);  /* in view space */
        float s = rifle ? 0.10f : sil ? 0.03f : 0.075f;
        Vector3 ax = { cosf(p->flashRot), sinf(p->flashRot), 0 }, ay = { -sinf(p->flashRot), cosf(p->flashRot), 0 };
        rlDrawRenderBatchActive();
        BeginBlendMode(BLEND_ADDITIVE);
        rlDisableDepthMask();
        rlDisableBackfaceCulling();
        rlSetTexture(tex[TX_FLASH].id);
        rlBegin(RL_QUADS);
        for (int k = 0; k < 2; k++) {
            float ss = k ? s*1.8f : s;
            Vector3 c0 = Vector3Transform(Vector3Add(cv, Vector3Scale(Vector3Add(Vector3Negate(ax), Vector3Negate(ay)), ss)), V);
            Vector3 c1 = Vector3Transform(Vector3Add(cv, Vector3Scale(Vector3Subtract(ax, ay), ss)), V);
            Vector3 c2 = Vector3Transform(Vector3Add(cv, Vector3Scale(Vector3Add(ax, ay), ss)), V);
            Vector3 c3 = Vector3Transform(Vector3Add(cv, Vector3Scale(Vector3Subtract(ay, ax), ss)), V);
            rlColor4ub(255, 255, 255, k ? 120 : 255);
            rlTexCoord2f(0, 1); rlVertex3f(c0.x, c0.y, c0.z);
            rlTexCoord2f(1, 1); rlVertex3f(c1.x, c1.y, c1.z);
            rlTexCoord2f(1, 0); rlVertex3f(c2.x, c2.y, c2.z);
            rlTexCoord2f(0, 0); rlVertex3f(c3.x, c3.y, c3.z);
        }
        rlEnd();
        rlSetTexture(0);
        rlDrawRenderBatchActive();
        rlEnableBackfaceCulling();
        rlEnableDepthMask();
        EndBlendMode();
    }
}

static void DrawFirstPerson(Player *p, Camera3D cam)
{
    cam.fovy = 58.0f;   /* narrower FOV for the weapon so it doesn't splay out with perspective */
    BeginMode3D(cam);
    SetupViewLights(cam);
    SetFog(gFogDensity);
    if (!EnhDrawViewModel(p, cam, (int)(p - players))) DrawViewModel(p, cam);
    EndMode3D();
}

/* ---------------- HUD ---------------- */
static void DrawTextShadow(const char *t, int x, int y, int fs, Color c)
{
    DrawText(t, x + 2, y + 2, fs, Fade(BLACK, 0.7f*c.a/255.0f));
    DrawText(t, x, y, fs, c);
}

static void DrawHud(Player *p, int w, int h, int idx)
{
    float sc = h/720.0f; if (sc < 0.5f) sc = 0.5f;
    int fs = h >= 600 ? 20 : 16;
    char buf[96];

    /* damage vignette */
    if (p->hurtFlash > 0) {
        float a = Clamp(p->hurtFlash/0.45f, 0, 1);
        DrawTexturePro(tex[TX_VIGNETTE], (Rectangle){ 0, 0, 256, 256 }, (Rectangle){ 0, 0, (float)w, (float)h }, (Vector2){ 0 }, 0, Fade((Color){ 220, 20, 10, 255 }, a));
        DrawRectangle(0, 0, w, h, Fade((Color){ 180, 0, 0, 255 }, a*0.18f));
    }

    /* dynamic crosshair */
    if (p->alive) {
        int cx = w/2, cy = h/2;
        float g = p->spreadVis*sc*0.8f;
        Color ch = Fade(RAYWHITE, 0.85f);
        for (int k = 0; k < 4; k++) {
            int dx = (k == 0) ? 1 : (k == 1) ? -1 : 0, dy = (k == 2) ? 1 : (k == 3) ? -1 : 0;
            Vector2 a = { cx + dx*g, cy + dy*g }, b = { cx + dx*(g + 7*sc), cy + dy*(g + 7*sc) };
            DrawLineEx((Vector2){ a.x + 1, a.y + 1 }, (Vector2){ b.x + 1, b.y + 1 }, 2.0f, Fade(BLACK, 0.6f));
            DrawLineEx(a, b, 2.0f, ch);
        }
        DrawRectangle(cx - 1, cy - 1, 2, 2, ch);
    }

    /* health / armour bar (bottom left) */
    int bw = (int)(260*sc), bh = (int)(14*sc), bx = (int)(24*sc), by = h - (int)(42*sc);
    DrawRectangleRounded((Rectangle){ (float)bx - 6, (float)by - 22*sc, (float)bw + 12, (float)bh + 30*sc }, 0.3f, 6, Fade(BLACK, 0.45f));
    DrawTextShadow("HEALTH", bx, by - (int)(18*sc), (int)(14*sc + 2), Fade(RAYWHITE, 0.9f));
    int segs = 20;
    for (int i = 0; i < segs; i++) {
        float t0 = (float)i/segs;
        bool on = t0 < p->health/100.0f;
        Color c = on ? (p->health > 30 ? ColorLerp((Color){ 200, 40, 30, 255 }, (Color){ 255, 120, 60, 255 }, t0) : (Color){ 255, (unsigned char)(60 + 60*sinf(gTime*10)), 40, 255 }) : (Color){ 60, 20, 20, 160 };
        DrawRectangle(bx + i*bw/segs, by, bw/segs - 2, bh, c);
    }

    /* ammo (bottom right): weapon name, rounds as brass icons, reserve */
    const WeaponDef *wd = &WEAPONS[p->weapon];
    int rx = w - (int)(24*sc);
    DrawTextShadow(wd->name, rx - MeasureText(wd->name, fs), h - (int)(80*sc), fs, p->weapon == W_GOLDEN ? GOLD : RAYWHITE);
    int mag = p->mag[p->weapon];
    int iw = (int)(fmaxf(3, (wd->magSize > 10 ? 6 : 10)*sc)), ih = (int)(18*sc), gap = (int)(fmaxf(2, 3*sc));
    int perRow = wd->magSize > 15 ? 15 : wd->magSize;
    for (int i = 0; i < wd->magSize; i++) {
        int row = i / perRow, col = i % perRow;
        int x = rx - (col + 1)*(iw + gap) - (int)(70*sc);
        int y = h - (int)(50*sc) + row*(ih/2 + 3) - (wd->magSize > 15 ? ih/2 : 0);
        Color c = i < mag ? (p->weapon == W_GOLDEN ? GOLD : (Color){ 220, 175, 70, 255 }) : (Color){ 70, 60, 40, 140 };
        DrawRectangle(x, y + (wd->magSize > 15 ? 0 : 3), iw, wd->magSize > 15 ? ih/2 : ih - 3, c);
        if (i < mag) DrawRectangle(x, y + (wd->magSize > 15 ? 0 : 3), iw, 3, (Color){ 180, 110, 50, 255 });
    }
    if (p->weapon == W_GOLDEN) snprintf(buf, sizeof(buf), "1");
    else snprintf(buf, sizeof(buf), "%d", p->reserve[p->weapon]);
    DrawTextShadow(buf, rx - MeasureText(buf, fs + 12), h - (int)(52*sc), fs + 12, YELLOW);
    if (p->reloadTimer > 0) DrawTextShadow("RELOADING", rx - MeasureText("RELOADING", fs), h - (int)(106*sc), fs, ORANGE);
    else if (PlayerSilenced(p)) DrawTextShadow("SILENCED", rx - MeasureText("SILENCED", fs), h - (int)(106*sc), fs, LIGHTGRAY);

    if (gState == GS_MISSION) {
        DrawRectangleRounded((Rectangle){ 10, 10, 430, 96 }, 0.12f, 6, Fade(BLACK, 0.45f));
        DrawTextShadow(PlayerUsesPad(p) ? TextFormat("OBJECTIVES  (%s: watch)", ActBtn(ACT_PAUSE)) : "OBJECTIVES  (TAB: watch)", 20, 16, 16, GOLD);
        for (int i = 0; i < 3; i++) {
            snprintf(buf, sizeof(buf), "%c. %s", 'A' + i, objs[i].text);
            DrawTextShadow(buf, 20, 40 + i*20, 16, objs[i].done ? (Color){ 110, 230, 110, 255 } : RAYWHITE);
        }
        bool alert = false, attack = false;
        for (int i = 0; i < numEnemies; i++) {
            if (enemies[i].state == E_ALERT) alert = true;
            if (enemies[i].state == E_ATTACK) attack = true;
        }
        const char *st = attack ? "DETECTED" : alert ? "GUARDS ALERTED" : "UNDETECTED";
        Color scl = attack ? RED : alert ? ORANGE : (Color){ 110, 230, 110, 255 };
        DrawTextShadow(st, w - MeasureText(st, 22) - 20, 16, 22, scl);
        if (noiseShow > 0) {
            snprintf(buf, sizeof(buf), "NOISE RADIUS %.0fm  (x%d)", noiseRadius, shotHeat);
            DrawTextShadow(buf, w - MeasureText(buf, 16) - 20, 44, 16, Fade(YELLOW, noiseShow));
        }
    } else {
        snprintf(buf, sizeof(buf), "P%d  KILLS %d / %d", idx + 1, p->kills, KILL_LIMIT);
        static const Color PCOL[MAX_PLAYERS] = { { 102, 191, 255, 255 }, { 255, 170, 120, 255 }, { 130, 230, 120, 255 }, { 250, 220, 90, 255 } };
        DrawTextShadow(buf, 14, 12, fs, PCOL[idx & 3]);
        if (!p->alive) {
            const char *t = "RESPAWNING...";
            DrawTextShadow(t, w/2 - MeasureText(t, 30)/2, h/2 + 40, 30, RED);
        }
    }
    if (p->msgTimer > 0) {
        DrawTextShadow(p->msg, w/2 - MeasureText(p->msg, fs)/2, h - (int)(130*sc), fs, Fade(RAYWHITE, fminf(1.0f, p->msgTimer)));
    }
}

/* radial gradient disc (DrawCircleGradient's signature differs between raylib 5.5 and 6.x) */
static void GradCircle(Vector2 c, float r, Color inner, Color outer)
{
    for (int i = 24; i >= 1; i--) DrawCircleV(c, r*i/24.0f, ColorLerp(inner, outer, i/24.0f));
}

/* the "watch" pause menu */
static void DrawWatchMenu(void)
{
    int w = GetScreenWidth(), h = GetScreenHeight();
    DrawRectangle(0, 0, w, h, Fade(BLACK, 0.6f));
    Vector2 c = { w*0.5f, h*0.5f };
    float r = h*0.43f;
    /* strap */
    DrawRectangleGradientV((int)(c.x - r*0.55f), 0, (int)(r*1.1f), h, (Color){ 40, 30, 22, 255 }, (Color){ 60, 44, 30, 255 });
    for (int y = 0; y < h; y += 18) DrawRectangle((int)(c.x - r*0.55f), y, (int)(r*1.1f), 2, Fade(BLACK, 0.25f));
    /* case & bezel */
    DrawCircleV((Vector2){ c.x + 8, c.y + 10 }, r + 22, Fade(BLACK, 0.5f));
    GradCircle(c, r + 20, (Color){ 230, 232, 236, 255 }, (Color){ 110, 112, 118, 255 });
    DrawRectangle((int)(c.x + r + 8), (int)(c.y - 14), 22, 28, (Color){ 170, 172, 176, 255 });
    DrawRing(c, r + 2, r + 14, 0, 360, 96, (Color){ 20, 30, 60, 255 });
    for (int i = 0; i < 60; i++) {
        float a = i/60.0f*2*PI;
        float r0 = (i % 5 == 0) ? r + 3 : r + 9;
        DrawLineEx((Vector2){ c.x + cosf(a)*r0, c.y + sinf(a)*r0 }, (Vector2){ c.x + cosf(a)*(r + 13), c.y + sinf(a)*(r + 13) }, i % 5 == 0 ? 3 : 1, (Color){ 200, 205, 215, 255 });
    }
    GradCircle(c, r, (Color){ 26, 40, 34, 255 }, (Color){ 8, 14, 12, 255 });
    /* LCD scanlines */
    for (int y = (int)(c.y - r); y < c.y + r; y += 3) {
        float dy = y - c.y, hw = sqrtf(fmaxf(0, r*r - dy*dy));
        DrawLine((int)(c.x - hw), y, (int)(c.x + hw), y, Fade(BLACK, 0.18f));
    }
    int x = (int)(c.x - r*0.70f), y = (int)(c.y - r*0.72f);
    char buf[128];
    Color lcd = { 140, 230, 160, 255 };
    if (gState == GS_MISSION) {
        DrawText("MISSION 1: FACILITY", x, y, 26, GOLD); y += 42;
        for (int i = 0; i < 3; i++) {
            snprintf(buf, sizeof(buf), "%c. %s", 'A' + i, objs[i].text);
            DrawText(buf, x, y, 18, lcd);
            DrawText(objs[i].done ? "COMPLETED" : "INCOMPLETE", x + 20, y + 21, 16, objs[i].done ? (Color){ 120, 255, 120, 255 } : (Color){ 255, 90, 80, 255 });
            y += 48;
        }
        snprintf(buf, sizeof(buf), "TIME %02d:%02d   KILLS %d", (int)gMissionTime/60, (int)gMissionTime%60, missionKills);
        DrawText(buf, x, y + 4, 18, LIGHTGRAY); y += 36;
    } else {
        DrawText(TextFormat("%dP DEATHMATCH", numPlayers), x, y, 26, GOLD); y += 42;
        buf[0] = 0;
        for (int i = 0; i < numPlayers; i++) snprintf(buf + strlen(buf), sizeof(buf) - strlen(buf), "P%d %d   ", i + 1, players[i].kills);
        DrawText(buf, x, y, 20, lcd); y += 26;
        DrawText(TextFormat("first to %d kills", KILL_LIMIT), x, y, 16, LIGHTGRAY); y += 34;
    }
    if (gPadLostSlot >= 0) {
        snprintf(buf, sizeof(buf), "P%d CONTROLLER DISCONNECTED", gPadLostSlot + 1);
        DrawText(buf, x, y, 18, ORANGE); y += 20;
        DrawText("reconnect it, or press A on another pad", x, y, 16, ORANGE); y += 26;
    }
    const char *items[4] = { "RESUME", "RESTART", "OPTIONS / CONTROLLER", "QUIT TO TITLE" };
    for (int i = 0; i < 4; i++) {
        bool sel = gWatchSel == i;
        if (sel) DrawRectangle(x - 8, y - 3, (int)(r*1.25f), 24, Fade(lcd, 0.22f));
        DrawText(TextFormat("%s %s", sel ? ">" : " ", items[i]), x, y, 18, sel ? RAYWHITE : SKYBLUE);
        y += 26;
    }
    DrawText(gUiPadMode ? "A select   B/START resume" : "ENTER select   TAB/ESC resume   Q quit", x, y + 6, 15, LIGHTGRAY);
}

/* ------------------------------------------------------------------ */
/* Game flow                                                           */
/* ------------------------------------------------------------------ */
static void StartMission(void)
{
    gState = GS_MISSION;
    numPlayers = 1;
    LoadLevel(false);
    for (int i = 0; i < 3; i++) objs[i].done = false;
    memset(&players[0], 0, sizeof(Player));
    players[0].pos = missionStart;
    players[0].yaw = -PI/2;     /* facing north */
    players[0].suit = (Color){ 40, 40, 45, 255 };
    players[0].variant = 3;
    ResetPlayerLoadout(&players[0], false);
    SetMsg(&players[0], "INFILTRATE THE FACILITY. STAY QUIET, 007.");
    gMissionResult = 0; gMissionTime = 0; gPaused = false;
    shotHeat = 0; lastShotTime = -100; noiseShow = 0; missionKills = 0;
    gSlotJoined[0] = true; gPadLostSlot = -1; gWatchSel = 0; gUi = UI_NONE;
    if (gSlotPad[0] >= 0 && !gPad[gSlotPad[0]].avail) gSlotPad[0] = -1;
    if (gSlotPad[0] < 0) for (int p = 0; p < MAX_PLAYERS; p++) if (gPad[p].avail) { gSlotPad[0] = p; break; }   /* auto-assign */
    DisableCursor();
}

static void StartDeathmatch(void)
{
    static const Color SUITS[MAX_PLAYERS] = { { 50, 80, 170, 255 }, { 170, 50, 50, 255 }, { 50, 130, 60, 255 }, { 170, 140, 40, 255 } };
    static const int VARIANTS[MAX_PLAYERS] = { 3, 4, 2, 0 };   /* two agents, then the commando and soldier outfits */
    gState = GS_DM;
    numPlayers = gDmPlayers < 2 ? 2 : gDmPlayers > MAX_PLAYERS ? MAX_PLAYERS : gDmPlayers;
    LoadLevel(true);
    for (int i = 0; i < MAX_PLAYERS; i++) {
        memset(&players[i], 0, sizeof(Player));
        players[i].alive = false;
        players[i].suit = SUITS[i];
        players[i].variant = VARIANTS[i];
    }
    for (int i = 0; i < numPlayers; i++) SpawnDmPlayer(i);
    for (int i = 0; i < numPlayers; i++) SetMsg(&players[i], "FIND THE GOLDEN GUN IN THE MAIN HALL");
    gDmWinner = -1; gPaused = false; gPadLostSlot = -1; gWatchSel = 0; gUi = UI_NONE;
    DisableCursor();
}

static void StartTitle(void)
{
    gState = GS_TITLE;
    numPlayers = 1;
    LoadLevel(false);
    memset(&players[0], 0, sizeof(Player));
    players[0].alive = false;
    players[0].pos = (Vector3){ -100, 0, -100 };
    gPaused = false; gPadLostSlot = -1; gUi = UI_NONE;
    gSlotJoined[0] = true; for (int s = 1; s < MAX_PLAYERS; s++) { gSlotJoined[s] = false; gSlotPad[s] = -1; }
    gKb2Slot = -1;
    RumbleStopAll();
    EnableCursor();
}

static void UpdateWorldTimers(float dt)
{
    UpdateDoors(dt);
    UpdateParticles(dt);
    if (noiseShow > 0) noiseShow -= dt*0.5f;
    if (gState == GS_DM) {
        for (int i = 0; i < numPickups; i++) {
            Pickup *pk = &pickups[i];
            if (pk->active || !pk->respawns) continue;
            pk->respawnTimer -= dt;
            if (pk->respawnTimer <= 0) pk->active = true;
        }
    }
}

static Camera3D TitleCamera(void)
{
    /* slow dolly through the main hall and past the windows */
    float t = gTime*0.07f;
    float k = 0.5f + 0.5f*sinf(t);
    Camera3D c = { 0 };
    c.position = (Vector3){ 15.0f + 22.0f*k, 1.75f + 0.15f*sinf(t*2.3f), 17.0f + 0.6f*sinf(t*1.7f) };
    float yaw = sinf(t*1.3f)*0.6f + (cosf(t) > 0 ? 0.0f : PI);
    c.target = Vector3Add(c.position, (Vector3){ cosf(yaw), -0.05f, sinf(yaw)*0.6f });
    c.up = (Vector3){ 0, 1, 0 };
    c.fovy = 62.0f;
    c.projection = CAMERA_PERSPECTIVE;
    return c;
}

static void DrawTitle(void)
{
    int w = GetScreenWidth(), h = GetScreenHeight();
    DrawWorld(TitleCamera(), -1);
    EnhBloom();
    DrawTexturePro(tex[TX_VIGNETTE], (Rectangle){ 0, 0, 256, 256 }, (Rectangle){ 0, 0, (float)w, (float)h }, (Vector2){ 0 }, 0, Fade(BLACK, 0.95f));
    DrawRectangleGradientV(0, 0, w, h/2, Fade(BLACK, 0.55f), Fade(BLACK, 0.0f));
    DrawRectangleGradientV(0, h/2, w, h/2, Fade(BLACK, 0.0f), Fade(BLACK, 0.75f));
    /* gun-barrel rings */
    for (int i = 0; i < 6; i++) {
        float r = 60.0f + i*45.0f + fmodf(gTime*40.0f, 45.0f);
        DrawRing((Vector2){ w*0.5f, h*0.5f - 40 }, r, r + 2, 0, 360, 72, Fade(GOLD, 0.10f));
    }
    if (gState != GS_TITLE) return;
    const char *title = "FACILITY 64";
    int tw = MeasureText(title, 84);
    DrawText(title, w/2 - tw/2 + 4, 104, 84, Fade(BLACK, 0.7f));
    DrawText(title, w/2 - tw/2, 100, 84, (Color){ 240, 196, 70, 255 });
    DrawText(title, w/2 - tw/2, 100, 84, Fade((Color){ 255, 240, 170, 255 }, 0.25f + 0.1f*sinf(gTime*2)));
    const char *sub = "a late-90s console-FPS inspired raylib prototype";
    DrawTextShadow(sub, w/2 - MeasureText(sub, 20)/2, 196, 20, LIGHTGRAY);
    const char *opts[4] = { "[1]  MISSION: FACILITY", "[2]  DEATHMATCH (2-4 players, split screen, Golden Gun)", "[O]  OPTIONS / CONTROLLER", "[ESC]  QUIT" };
    for (int i = 0; i < 4; i++) {
        bool sel = gTitleSel == i;
        DrawRectangleRounded((Rectangle){ w/2 - 340.0f, 300.0f + i*50, 680, 40 }, 0.3f, 6, sel ? Fade((Color){ 90, 70, 20, 255 }, 0.8f) : Fade(BLACK, 0.5f));
        if (sel) DrawRectangleRoundedLinesEx((Rectangle){ w/2 - 340.0f, 300.0f + i*50, 680, 40 }, 0.3f, 6, 2, GOLD);
        DrawTextShadow(opts[i], w/2 - 316, 308 + i*50, 26, sel ? (Color){ 255, 236, 170, 255 } : RAYWHITE);
    }
    int np = 0; for (int p = 0; p < MAX_PLAYERS; p++) np += gPad[p].avail;
    const char *padl = np ? TextFormat("%d controller%s connected  -  style: %s", np, np > 1 ? "s" : "", STYLE_NAME[gCtl.style]) : "no controller connected (keyboard + mouse)";
    DrawTextShadow(padl, w/2 - MeasureText(padl, 18)/2, 510, 18, np ? (Color){ 140, 230, 160, 255 } : GRAY);
    if (gUi != UI_NONE) return;   /* options/remap/debug panel covers the help lines */
    if (gUiPadMode) {
        if (gCtl.style == STYLE_MODERN)
            DrawTextShadow(TextFormat("Pad: left stick move, right stick look, %s fire, %s aim, %s reload, %s weapon, %s door, %s silencer, %s watch",
                           ActBtn(ACT_FIRE), ActBtn(ACT_AIM), ActBtn(ACT_RELOAD), ActBtn(ACT_NEXTWPN), ActBtn(ACT_USE), ActBtn(ACT_SILENCER), ActBtn(ACT_PAUSE)), 40, h - 70, 16, (Color){ 190, 190, 190, 255 });
        else
            DrawTextShadow(TextFormat("Pad (classic): left stick turn+look, right stick/D-pad walk+strafe, %s fire, %s aim, %s door+reload, %s weapon, %s watch",
                           ActBtn(ACT_FIRE), ActBtn(ACT_AIM), ActBtn(ACT_USE), ActBtn(ACT_NEXTWPN), ActBtn(ACT_PAUSE)), 40, h - 70, 16, (Color){ 190, 190, 190, 255 });
        DrawTextShadow("D-pad/stick: choose    A: select    Options: deadzone, sensitivity, invert Y, vibration, remap, debug", 40, h - 44, 16, (Color){ 190, 190, 190, 255 });
    } else {
        DrawTextShadow("Mission: WASD move, mouse/arrows look, LMB/Space fire, Z aim, R reload, 1/2 weapons, T silencer, E door, TAB watch",
                 40, h - 70, 16, (Color){ 190, 190, 190, 255 });
        DrawTextShadow("Deathmatch: P1 WASD+mouse (Q/E turn)  keyboard P2: arrows, ,/. strafe, RCtrl/Enter fire  -  controllers join in the lobby",
                 40, h - 44, 16, (Color){ 190, 190, 190, 255 });
    }
}

/* deathmatch join-in screen (drawn over the title backdrop) */
static void DrawLobby(void)
{
    int w = GetScreenWidth(), h = GetScreenHeight();
    DrawTitle();
    DrawRectangle(0, 0, w, h, Fade(BLACK, 0.55f));
    const char *t = "DEATHMATCH - JOIN IN";
    DrawText(t, w/2 - MeasureText(t, 44)/2, 84, 44, GOLD);
    static const Color PCOL[MAX_PLAYERS] = { { 102, 191, 255, 255 }, { 255, 170, 120, 255 }, { 130, 230, 120, 255 }, { 250, 220, 90, 255 } };
    for (int s = 0; s < MAX_PLAYERS; s++) {
        Rectangle r = { 70.0f + s*290, 150, 270, 310 };
        bool j = gSlotJoined[s];
        DrawRectangleRounded(r, 0.06f, 6, j ? Fade((Color){ 20, 30, 40, 255 }, 0.95f) : Fade((Color){ 20, 20, 22, 255 }, 0.8f));
        DrawRectangleRoundedLinesEx(r, 0.06f, 6, j ? 3 : 1, j ? PCOL[s] : DARKGRAY);
        DrawText(TextFormat("PLAYER %d", s + 1), (int)r.x + 20, (int)r.y + 18, 30, j ? PCOL[s] : GRAY);
        int y = (int)r.y + 70;
        if (!j) {
            float a = 0.5f + 0.5f*sinf(gTime*4 + s);
            DrawText("PRESS A / START", (int)r.x + 20, y, 22, Fade(RAYWHITE, 0.4f + 0.6f*a)); y += 30;
            DrawText("ON A CONTROLLER", (int)r.x + 20, y, 22, Fade(RAYWHITE, 0.4f + 0.6f*a)); y += 40;
            if (s > 0 && gKb2Slot < 0) DrawText("(or K: keyboard arrows)", (int)r.x + 20, y, 16, GRAY);
            continue;
        }
        if (s == 0) { DrawText("KEYBOARD + MOUSE", (int)r.x + 20, y, 20, RAYWHITE); y += 28; }
        if (s == gKb2Slot) { DrawText("KEYBOARD: ARROW KEYS", (int)r.x + 20, y, 20, RAYWHITE); y += 28; }
        int p = gSlotPad[s];
        if (p >= 0) {
            DrawText(TextFormat("%sCONTROLLER %d", s == 0 ? "+ " : "", p + 1), (int)r.x + 20, y, 20, (Color){ 140, 230, 160, 255 }); y += 24;
            DrawTextBoxed(gPad[p].avail ? gPad[p].name : "(disconnected)", (int)r.x + 20, y, 230, 16, LIGHTGRAY); y += 44;
        }
        DrawText("READY", (int)r.x + 20, (int)(r.y + r.height - 44), 26, PCOL[s]);
    }
    int n = LobbyCount();
    const char *l1 = TextFormat("%d player%s   -   split screen: %s", n, n > 1 ? "s" : "", n <= 2 ? "top / bottom" : "4-way");
    DrawText(l1, w/2 - MeasureText(l1, 22)/2, 490, 22, RAYWHITE);
    const char *l2 = "START (joined pad) or ENTER: begin     B: leave     BACK: share P1 with the keyboard     K: keyboard P2     ESC: title";
    DrawText(l2, w/2 - MeasureText(l2, 18)/2, 540, 18, SKYBLUE);
    if (n < 2) {
        const char *l3 = "with one player, ENTER adds a keyboard player 2 (arrow keys)";
        DrawText(l3, w/2 - MeasureText(l3, 16)/2, 570, 16, GRAY);
    }
    const char *l4 = TextFormat("pad assignment: %s (change in OPTIONS)", gCtl.autoJoin ? "AUTO, connection order" : "press to join");
    DrawText(l4, w/2 - MeasureText(l4, 16)/2, 600, 16, GRAY);
}

static void DrawMissionEnd(void)
{
    int w = GetScreenWidth(), h = GetScreenHeight();
    DrawRectangle(0, 0, w, h, Fade(BLACK, 0.72f));
    bool ok = gMissionResult == 1;
    const char *t = ok ? "MISSION COMPLETE" : "MISSION FAILED";
    DrawText(t, w/2 - MeasureText(t, 64)/2 + 3, 123, 64, Fade(BLACK, 0.8f));
    DrawText(t, w/2 - MeasureText(t, 64)/2, 120, 64, ok ? GOLD : (Color){ 230, 50, 40, 255 });
    DrawRectangleRounded((Rectangle){ w/2 - 220.0f, 228, 440, 300 }, 0.08f, 6, Fade((Color){ 20, 26, 30, 255 }, 0.85f));
    DrawRectangleRoundedLinesEx((Rectangle){ w/2 - 220.0f, 228, 440, 300 }, 0.08f, 6, 2, Fade(GOLD, 0.6f));
    char buf[128];
    Player *p = &players[0];
    int y = 250, x = w/2 - 190;
    const char *labels[5] = { "TIME", "KILLS", "SHOTS FIRED", "ACCURACY", "HEADSHOTS" };
    char vals[5][32];
    snprintf(vals[0], 32, "%02d:%02d", (int)gMissionTime/60, (int)gMissionTime%60);
    snprintf(vals[1], 32, "%d / %d", missionKills, numEnemies);
    snprintf(vals[2], 32, "%d", p->shots);
    snprintf(vals[3], 32, "%d%%", p->shots ? (p->hits*100)/p->shots : 0);
    snprintf(vals[4], 32, "%d", p->headshots);
    for (int i = 0; i < 5; i++) {
        DrawText(labels[i], x, y, 24, LIGHTGRAY);
        DrawText(vals[i], x + 380 - MeasureText(vals[i], 24), y, 24, RAYWHITE);
        y += 40;
    }
    snprintf(buf, sizeof(buf), "%s", ok ? "Well done, 007." : "You were killed in action.");
    DrawText(buf, w/2 - MeasureText(buf, 20)/2, y + 6, 20, ok ? (Color){ 140, 230, 140, 255 } : (Color){ 230, 140, 120, 255 });
    const char *pr = Pr("A: retry      B: title", "ENTER: retry      Q: title");
    DrawText(pr, w/2 - MeasureText(pr, 22)/2, 550, 22, SKYBLUE);
}

static void InitGraphics(bool exportTextures)
{
    InitShader();
    LoadAllTextures(exportTextures);
    InitMaterials();
    BuildCharacterMeshes();
    BuildWeaponMeshes();
    BuildMiscMeshes();
    LoadLevel(false);          /* props must exist before the static mesh is built */
    BuildLevelMeshes();
    InitEnhanced();
}

/* split-screen layout: 2 players top/bottom, 3-4 players in quadrants */
static Rectangle DmViewRect(int i)
{
    if (numPlayers <= 2) return (Rectangle){ 0, (float)(i*(SCREEN_H/2)), (float)SCREEN_W, (float)(SCREEN_H/2) };
    return (Rectangle){ (float)((i % 2)*(SCREEN_W/2)), (float)((i/2)*(SCREEN_H/2)), (float)(SCREEN_W/2), (float)(SCREEN_H/2) };
}
static RenderTexture2D *DmTarget(RenderTexture2D *split, int i) { return numPlayers <= 2 ? &split[i] : &split[2 + i]; }

/* one frame of output: 3D views, (Enhanced) bloom, then HUDs and overlays */
static void RenderFrame(RenderTexture2D *split)
{
    if (gState == GS_DM) {
        for (int i = 0; i < numPlayers; i++) {
            BeginTextureMode(*DmTarget(split, i));
            Camera3D cam = PlayerCamera(&players[i]);
            DrawWorld(cam, i);
            DrawFirstPerson(&players[i], cam);
            EndTextureMode();
        }
    }
    BeginDrawing();
    if (gState == GS_TITLE) {
        DrawTitle();
    } else if (gState == GS_LOBBY) {
        DrawLobby();
    } else if (gState == GS_MISSION) {
        Camera3D cam = PlayerCamera(&players[0]);
        DrawWorld(cam, 0);
        DrawFirstPerson(&players[0], cam);
        EnhBloom();
        DrawHud(&players[0], GetScreenWidth(), GetScreenHeight(), 0);
        if (gMissionResult != 0) DrawMissionEnd();
        else if (gPaused && gUi == UI_NONE) DrawWatchMenu();
    } else {
        ClearBackground(BLACK);
        for (int i = 0; i < numPlayers; i++) {
            Rectangle v = DmViewRect(i);
            DrawTextureRec(DmTarget(split, i)->texture, (Rectangle){ 0, 0, v.width, -v.height }, (Vector2){ v.x, v.y }, WHITE);
        }
        EnhBloom();
        /* HUDs are drawn on top of the composited views so they stay crisp (and out of the bloom) */
        for (int i = 0; i < numPlayers; i++) {
            Rectangle v = DmViewRect(i);
            BeginScissorMode((int)v.x, (int)v.y, (int)v.width, (int)v.height);
            rlPushMatrix();
            rlTranslatef(v.x, v.y, 0);
            DrawHud(&players[i], (int)v.width, (int)v.height, i);
            rlDrawRenderBatchActive();
            rlPopMatrix();
            EndScissorMode();
        }
        if (numPlayers == 3) {
            /* spare quadrant: live scoreboard */
            Rectangle v = { SCREEN_W/2.0f, SCREEN_H/2.0f, SCREEN_W/2.0f, SCREEN_H/2.0f };
            DrawRectangleRec(v, (Color){ 12, 14, 18, 255 });
            DrawText("SCORES", (int)v.x + 40, (int)v.y + 40, 36, GOLD);
            for (int i = 0; i < numPlayers; i++)
                DrawText(TextFormat("PLAYER %d   %d / %d", i + 1, players[i].kills, KILL_LIMIT), (int)v.x + 40, (int)v.y + 100 + i*44, 28, RAYWHITE);
            DrawText(players[0].has[W_GOLDEN] || players[1].has[W_GOLDEN] || players[2].has[W_GOLDEN] ? "THE GOLDEN GUN IS TAKEN" : "THE GOLDEN GUN IS IN THE MAIN HALL",
                     (int)v.x + 40, (int)v.y + 250, 18, LIGHTGRAY);
        }
        DrawRectangle(0, SCREEN_H/2 - 2, SCREEN_W, 4, BLACK);
        if (numPlayers > 2) DrawRectangle(SCREEN_W/2 - 2, 0, 4, SCREEN_H, BLACK);
        if (gDmWinner >= 0) {
            DrawRectangle(0, 0, SCREEN_W, SCREEN_H, Fade(BLACK, 0.7f));
            char buf[64];
            snprintf(buf, sizeof(buf), "PLAYER %d WINS!", gDmWinner + 1);
            DrawText(buf, SCREEN_W/2 - MeasureText(buf, 64)/2, SCREEN_H/2 - 60, 64, GOLD);
            const char *t = Pr("A / START: rematch     B: title", "ENTER: rematch     Q: title");
            DrawText(t, SCREEN_W/2 - MeasureText(t, 24)/2, SCREEN_H/2 + 30, 24, SKYBLUE);
        } else if (gPaused && gUi == UI_NONE) DrawWatchMenu();
    }
    DrawUiScreens();
    gToastY = gUi == UI_NONE ? 60 : GetScreenHeight() - (gUi == UI_DEBUG ? 50 : 34);
    DrawToast();
    if (gShotPending[0]) { rlDrawRenderBatchActive(); TakeScreenshot(gShotPending); gShotPending[0] = 0; }
    EndDrawing();
}

static void Restart(void) { if (gState == GS_MISSION) StartMission(); else StartDeathmatch(); }
static void Unpause(void) { gPaused = false; DisableCursor(); GetMouseDelta(); }

/* one frame of game logic; returns true to quit */
static bool GameUpdate(float dt)
{
    PadPoll(dt);
    EnhUpdate(dt);   /* F2 graphics toggle, F3 model reload, skeletal animation */
    UiIn u = UiPoll(dt);
    if (gQuitRequested) return true;

    if (gState == GS_TITLE || gState == GS_LOBBY) {
        UpdateWorldTimers(dt);
        for (int i = 0; i < numEnemies; i++) UpdateEnemy(&enemies[i], dt);
        if (UpdateUiScreens(u, dt)) return false;
        if (gState == GS_LOBBY) { UpdateLobby(u); return false; }
        if (u.src >= 0 && (gSlotPad[0] < 0 || !gPad[gSlotPad[0]].avail)) gSlotPad[0] = u.src;   /* the pad driving the menu is P1's */
        gTitleSel = (gTitleSel + u.dy + 4) % 4;
        int pick = -1;
        if (u.ok || u.start) pick = gTitleSel;
        if (IsKeyPressed(KEY_ONE) || IsKeyPressed(KEY_KP_1)) pick = 0;
        else if (IsKeyPressed(KEY_TWO) || IsKeyPressed(KEY_KP_2)) pick = 1;
        else if (IsKeyPressed(KEY_O) || IsKeyPressed(KEY_ZERO) || IsKeyPressed(KEY_KP_0)) pick = 2;
        else if (IsKeyPressed(KEY_ESCAPE)) pick = 3;
        if (pick == 0) { if (u.src >= 0) gSlotPad[0] = u.src; StartMission(); }
        else if (pick == 1) OpenLobby(u.src);
        else if (pick == 2) OpenOptions();
        else if (pick == 3) return true;
        return false;
    }

    bool over = (gState == GS_MISSION && gMissionResult != 0) || (gState == GS_DM && gDmWinner >= 0);
    if (!over) gOverT = 0;
    if (over) {
        RumbleStopAll();
        if (gState == GS_MISSION) players[0].deathT += dt;
        gOverT += dt;
        if (gOverT < 1.0f) return false;    /* ignore buttons still being mashed when the round ends */
        if (u.ok || u.start) Restart();
        else if (u.back || IsKeyPressed(KEY_Q)) StartTitle();
    } else if (gPaused) {
        RumbleStopAll();
        PadTakeOver();
        if (UpdateUiScreens(u, dt)) return false;
        gWatchSel = (gWatchSel + u.dy + 4) % 4;
        if (IsKeyPressed(KEY_TAB) || IsKeyPressed(KEY_P) || u.back || u.start) Unpause();
        else if (IsKeyPressed(KEY_Q)) StartTitle();
        else if (u.ok) {
            if (gWatchSel == 0) Unpause();
            else if (gWatchSel == 1) Restart();
            else if (gWatchSel == 2) OpenOptions();
            else StartTitle();
        }
    } else {
        if (IsKeyPressed(KEY_TAB) || IsKeyPressed(KEY_ESCAPE) || IsKeyPressed(KEY_P) || AnyPausePressed()) { gPaused = true; gWatchSel = 0; }
        else {
            UpdateWorldTimers(dt);
            if (gState == GS_MISSION) {
                gMissionTime += dt;
                MissionAutoAssign();
                UpdatePlayer(0, ReadSlotInput(0, false, dt), dt);
                for (int i = 0; i < numEnemies; i++) UpdateEnemy(&enemies[i], dt);
            } else {
                PlayerInput in[MAX_PLAYERS];
                for (int i = 0; i < numPlayers; i++) in[i] = ReadSlotInput(i, true, dt);
                for (int i = 0; i < numPlayers; i++) UpdatePlayer(i, in[i], dt);
            }
        }
    }
    return false;
}

int main(int argc, char **argv)
{
    bool exportTextures = false;
    bool quitAfterExport = false;
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--export-textures") == 0) exportTextures = true;
        if (strcmp(argv[i], "--quit-after-export") == 0) quitAfterExport = true;
        if (strcmp(argv[i], "--pad-script") == 0 && i + 1 < argc) LoadPadScript(argv[++i]);
    }
    SetConfigFlags(FLAG_MSAA_4X_HINT | FLAG_VSYNC_HINT);
    InitWindow(SCREEN_W, SCREEN_H, "Facility 64 - GoldenEye-style prototype");
    SetExitKey(KEY_NULL);
    SetTargetFPS(60);
    srand(1234);
    InitSounds();
    InitGraphics(exportTextures);
    if (exportTextures && quitAfterExport) { UnloadSounds(); CloseWindow(); return 0; }
    InitPads();
    StartTitle();

    /* [0..1] 2-player halves, [2..5] 3-4 player quadrants */
    RenderTexture2D split[6];
    for (int i = 0; i < 2; i++) split[i] = LoadRenderTexture(SCREEN_W, SCREEN_H/2);
    for (int i = 2; i < 6; i++) split[i] = LoadRenderTexture(SCREEN_W/2, SCREEN_H/2);

    bool quit = false;
    while (!quit && !WindowShouldClose()) {
        float dt = GetFrameTime();
        if (dt > 0.05f) dt = 0.05f;
        gTime += dt;
        quit = GameUpdate(dt);
        RenderFrame(split);
    }

    RumbleStopAll();
    for (int i = 0; i < 6; i++) UnloadRenderTexture(split[i]);
    UnloadSounds();
    CloseWindow();
    return 0;
}
