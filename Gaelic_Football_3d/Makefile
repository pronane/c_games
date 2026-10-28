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

$(TARGET): src/main.c src/game.c src/game.h src/stadium.c src/sfx.c src/pad.c
	$(CC) $(CFLAGS) -Isrc src/main.c src/game.c -o $@ $(LDFLAGS) $(LIBS)

test:
	$(CC) -std=c99 -Isrc tests/core_tests.c src/game.c -lm -o core_tests && ./core_tests

run: $(TARGET)
	./$(TARGET)

shots: $(TARGET)
	./$(TARGET) --screenshots

clean:
	rm -f gaelic_football gaelic_football.exe core_tests core_tests.exe v2_*.png

.PHONY: run shots test clean
