#include "../game.h"

#include <assert.h>
#include <math.h>
#include <stdio.h>

static void TestStartingLoadout(void)
{
    GameState game;
    GameInit(&game);
    assert(game.current_weapon == GAME_SIDEARM);
    assert(game.ammo[GAME_SIDEARM] == 12);
    assert(game.reserve_ammo[GAME_SIDEARM] == 48);
    assert(!game.has_carbine);
}

static void TestPickupAndSwitch(void)
{
    GameState game;
    GameInput input = {0};
    GameInit(&game);
    game.position[0] = GAME_CARBINE_X;
    game.position[2] = GAME_CARBINE_Z;
    input.interact = true;
    GameUpdate(&game, input, 0.0f);

    assert(game.has_carbine);
    assert(game.current_weapon == GAME_CARBINE);
    assert(game.ammo[GAME_CARBINE] == 24);
    assert(game.reserve_ammo[GAME_CARBINE] == 72);
    assert(game.pickup_event);

    input.interact = false;
    input.switch_weapon = true;
    GameUpdate(&game, input, 0.0f);
    assert(game.current_weapon == GAME_SIDEARM);
    assert(!game.pickup_event);
}

static void TestAimedShotAndWallOcclusion(void)
{
    GameState game;
    GameInput input = {0};
    GameInit(&game);
    game.position[0] = 6.0f;
    game.position[1] = 1.65f;
    game.position[2] = -7.0f;
    game.guards[0].x = 9.38f;
    game.guards[0].z = -5.0f;
    game.guards[0].phase = 0.0f;
    game.yaw = atan2f(3.0f, 2.3f);
    game.pitch = atan2f(-0.23f, sqrtf(3.0f * 3.0f + 2.3f * 2.3f));
    input.fire = true;
    GameUpdate(&game, input, 0.0f);
    assert(game.shot_event);
    assert(game.hit_event);
    assert(game.guards[0].health == 45);
    assert(game.ammo[GAME_SIDEARM] == 11);

    GameInit(&game);
    game.position[0] = 0.0f;
    game.position[1] = 1.65f;
    game.position[2] = -1.0f;
    game.guards[0].x = -0.38f;
    game.guards[0].z = 2.7f;
    game.guards[0].phase = 0.0f;
    game.yaw = atan2f(-0.38f, 4.0f);
    game.pitch = atan2f(-0.23f, sqrtf(0.38f * 0.38f + 4.0f * 4.0f));
    input.fire = true;
    GameUpdate(&game, input, 0.0f);
    assert(game.shot_event);
    assert(!game.hit_event);
    assert(game.guards[0].health == 100);
}

static void TestCarbineFireAndAimedMovement(void)
{
    GameState game;
    GameInput input = {0};
    GameInit(&game);
    game.has_carbine = true;
    game.current_weapon = GAME_CARBINE;
    game.ammo[GAME_CARBINE] = 24;
    game.position[0] = 6.0f;
    game.position[1] = 1.65f;
    game.position[2] = -7.0f;
    game.guards[0].x = 9.38f;
    game.guards[0].z = -5.0f;
    game.guards[0].phase = 0.0f;
    game.yaw = atan2f(3.0f, 2.3f);
    game.pitch = atan2f(-0.23f, sqrtf(3.0f * 3.0f + 2.3f * 2.3f));
    input.fire = true;
    GameUpdate(&game, input, 0.0f);
    assert(game.hit_event);
    assert(game.guards[0].health == 66);
    assert(game.ammo[GAME_CARBINE] == 23);

    GameInit(&game);
    input.fire = false;
    game.yaw = 0.0f;
    input.move_y = 1.0f;
    input.aim = true;
    GameUpdate(&game, input, 0.05f);
    assert(game.aiming);
    assert(fabsf(game.position[2] - (8.5f + 3.7f * 0.7f * 0.05f)) < 0.001f);

    GameInit(&game);
    game.position[0] = 0.0f;
    game.position[2] = -1.0f;
    game.guards[0].x = 0.0f;
    game.guards[0].z = 2.7f;
    game.guards[0].phase = 0.0f;
    game.guards[0].attack_cooldown = 0.0f;
    GameUpdate(&game, (GameInput){0}, 0.05f);
    assert(game.health == 100.0f);
}

static void TestReloadAndMissionFlow(void)
{
    GameState game;
    GameInput input = {0};
    GameInit(&game);
    game.ammo[GAME_SIDEARM] = 0;
    game.reserve_ammo[GAME_SIDEARM] = 10;
    input.reload = true;
    GameUpdate(&game, input, 0.0f);
    assert(game.reload_event);

    input.reload = false;
    for (int i = 0; i < 21; ++i) GameUpdate(&game, input, 0.05f);
    assert(game.ammo[GAME_SIDEARM] == 10);
    assert(game.reserve_ammo[GAME_SIDEARM] == 0);

    game.position[0] = 7.0f;
    game.position[2] = -7.0f;
    input.interact = true;
    GameUpdate(&game, input, 0.0f);
    assert(game.has_data_core);
    game.position[0] = 9.0f;
    game.position[2] = -9.0f;
    GameUpdate(&game, input, 0.0f);
    assert(game.mission_complete);
}

int main(void)
{
    TestStartingLoadout();
    TestPickupAndSwitch();
    TestAimedShotAndWallOcclusion();
    TestCarbineFireAndAimedMovement();
    TestReloadAndMissionFlow();
    puts("All game tests passed.");
    return 0;
}
