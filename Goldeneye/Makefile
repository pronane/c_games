PROJECT_NAME = glass_harbor
SRC = main.c game.c

CC_PC = gcc
CFLAGS_PC = -std=c99 -Wall -Wextra -O2 -DPLATFORM_RAYLIB

ifeq ($(OS),Windows_NT)
    EXE_PC = MySpy.exe
    LIBS_PC = -lraylib -lopengl32 -lgdi32 -lwinmm
else
    EXE_PC = MySpy
    LIBS_PC = -lraylib -lGL -lm -lpthread -ldl -lrt -lX11
endif

.PHONY: all pc n64 clean

all: pc

pc: $(SRC) game.h
	$(CC_PC) $(CFLAGS_PC) $(SRC) -o $(EXE_PC) $(LIBS_PC)

ifeq ($(strip $(N64_INST)),)
n64:
	@echo "ERROR: Set N64_INST to a Libdragon preview SDK installation with OpenGL enabled."
	@exit 1
else
include $(N64_INST)/include/n64.mk

ROM = $(PROJECT_NAME).z64
ELF = $(PROJECT_NAME).elf
N64_ROM_TITLE = "GLASS HARBOR"
OBJS = main.o game.o
CFLAGS += -std=c99 -DPLATFORM_N64

n64: $(ROM)
endif

clean:
	$(RM) $(EXE_PC) $(PROJECT_NAME).z64 $(PROJECT_NAME).elf $(PROJECT_NAME).bin main.o game.o
