ROMNAME := gaelic_football
PROJECT_NAME := $(ROMNAME)
BUILD_DIR := build-n64
N64_INST ?=
CC_PC ?= gcc
RAYLIB_CFLAGS ?= $(shell pkg-config --cflags raylib 2>/dev/null)
RAYLIB_LIBS ?= $(shell pkg-config --libs raylib 2>/dev/null)
PC_SOURCES := src/main.c src/game.c src/audio.c src/player_model.c
N64_SOURCES := src/main_n64.c src/game.c

.PHONY: all pc n64 clean

all: pc

ifeq ($(OS),Windows_NT)
PC_OUTPUT := $(PROJECT_NAME).exe
PC_LIBS_FALLBACK := -lraylib -lopengl32 -lgdi32 -lwinmm -lm
else
PC_OUTPUT := $(PROJECT_NAME)
PC_LIBS_FALLBACK := -lraylib -lGL -lm -lpthread -ldl -lrt -lX11
endif

pc:
	$(CC_PC) -std=c99 -O2 -Wall -Wextra -DPLATFORM_RAYLIB -Isrc \
		$(RAYLIB_CFLAGS) $(PC_SOURCES) -o $(PC_OUTPUT) \
		$(if $(strip $(RAYLIB_LIBS)),$(RAYLIB_LIBS) -lm,$(PC_LIBS_FALLBACK))

ifeq ($(strip $(N64_INST)),)
n64:
	@echo "ERROR: Set N64_INST to the Libdragon SDK installation directory."
	@exit 1
else
include $(N64_INST)/include/n64.mk

CFLAGS += -std=c99 -DPLATFORM_N64 -Isrc
N64_OBJECTS := $(addprefix $(BUILD_DIR)/,$(N64_SOURCES:.c=.o))

n64: $(ROMNAME).z64

$(BUILD_DIR)/$(ROMNAME).elf: $(N64_OBJECTS)

$(ROMNAME).z64: N64_ROM_TITLE = "GAELIC FOOTBALL"
endif

clean:
	$(RM) -r $(BUILD_DIR)
	$(RM) -f $(PROJECT_NAME) $(PROJECT_NAME).exe $(PROJECT_NAME).z64
