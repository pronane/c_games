# make            -> native build (Linux, or MSYS2 UCRT64 shell on Windows)
# make RAYLIB_DIR=/path/to/raylib   (dir containing include/ and lib/, or raylib/src)
# make test (rules-engine unit tests) / make run / make shots (headless screenshot run; needs a display or Xvfb)
CC ?= gcc
RAYLIB_DIR ?=
CFLAGS := -std=c99 -O2 -Wall -Wextra
ifneq ($(RAYLIB_DIR),)
CFLAGS += -I$(RAYLIB_DIR)/include -I$(RAYLIB_DIR)
LDFLAGS += -L$(RAYLIB_DIR)/lib -L$(RAYLIB_DIR)
endif
ifeq ($(OS),Windows_NT)
TARGET := gaelic_football.exe
LIBS := -lraylib -lglfw3 -lopengl32 -lgdi32 -lwinmm -lm -static-libgcc
else
TARGET := gaelic_football
LIBS := -lraylib -lGL -lm -lpthread -ldl -lrt -lX11
endif

$(TARGET): src/main.c src/game.c src/motion_match.c src/motion_match.h src/motion_cache.c src/motion_cache.h src/action_motion.c src/action_motion.h src/release_visual.c src/release_visual.h ../shared/arena_motion/arena_motion.c ../shared/arena_motion/arena_motion.h src/game.h src/stadium.c src/sfx.c src/pad.c
	$(CC) $(CFLAGS) -Isrc src/main.c src/game.c src/motion_match.c src/motion_cache.c src/action_motion.c src/release_visual.c ../shared/arena_motion/arena_motion.c -o $@ $(LDFLAGS) $(LIBS)

test:
	$(CC) -std=c99 -Isrc tests/core_tests.c src/game.c -lm -o core_tests && ./core_tests
	$(CC) -std=c99 -Wall -Wextra -Isrc tests/motion_tests.c src/motion_match.c ../shared/arena_motion/arena_motion.c -lm -o motion_tests && ./motion_tests
	$(CC) -std=c99 -Wall -Wextra -Isrc tests/motion_cache_tests.c src/motion_cache.c src/motion_match.c src/action_motion.c ../shared/arena_motion/arena_motion.c -lm -o motion_cache_tests
	python3 tests/run_motion_cache_tests.py ./motion_cache_tests
	$(CC) -std=c99 -Wall -Wextra -Isrc tests/action_motion_tests.c src/action_motion.c ../shared/arena_motion/arena_motion.c -lm -o action_motion_tests && ./action_motion_tests
	$(CC) -std=c99 -Wall -Wextra -Isrc tests/release_visual_tests.c src/release_visual.c -lm -o release_visual_tests && ./release_visual_tests
	$(CC) -std=c99 -Wall -Wextra ../shared/arena_motion/tests/arena_motion_tests.c ../shared/arena_motion/arena_motion.c -lm -o arena_motion_tests && ./arena_motion_tests

# Headless raylib 5.5 animation-only tool: GNU ld discards all draw code.
# Uses the vendored raylib source, not an installed renderer; no display needed.
RAYLIB55_SRC := ../TurboTumble64/deps/raylib-5.5/src
motion_headless: tools/motion_headless.c tools/raylib_headless_support.c src/main.c src/game.c src/motion_match.c src/motion_cache.c src/action_motion.c src/release_visual.c $(wildcard src/*.h) src/stadium.c src/sfx.c src/pad.c $(RAYLIB55_SRC)/rmodels.c $(RAYLIB55_SRC)/raylib.h $(RAYLIB55_SRC)/raymath.h ../shared/arena_motion/arena_motion.c ../shared/arena_motion/arena_motion.h
	$(CC) -std=c99 -O2 -Wall -Wextra -Wno-unused-parameter -DEXTERNAL_CONFIG_FLAGS -DSUPPORT_MODULE_RMODELS -DSUPPORT_FILEFORMAT_GLTF -ffunction-sections -fdata-sections -I$(RAYLIB55_SRC) -Isrc tools/motion_headless.c tools/raylib_headless_support.c $(RAYLIB55_SRC)/rmodels.c src/game.c src/motion_match.c src/motion_cache.c src/action_motion.c src/release_visual.c ../shared/arena_motion/arena_motion.c -Wl,--gc-sections -lm -o $@

test-motion-model: motion_headless
	python3 tests/run_motion_model_tests.py ./motion_headless assets/models/gaelic_player.glb

run: $(TARGET)
	./$(TARGET)

shots: $(TARGET)
	./$(TARGET) --screenshots

clean:
	rm -f gaelic_football gaelic_football.exe core_tests core_tests.exe motion_tests motion_tests.exe arena_motion_tests arena_motion_tests.exe motion_cache_tests motion_cache_tests.exe action_motion_tests action_motion_tests.exe release_visual_tests release_visual_tests.exe motion_headless motion_headless.exe v2_*.png

.PHONY: run shots test test-motion-model clean
