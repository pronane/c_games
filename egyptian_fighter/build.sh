#!/bin/bash
mkdir -p bin
gcc -std=c99 -O2 -Wall \
  src/main.c src/player.c src/game.c \
  -I/ucrt64/include -L/ucrt64/lib \
  -lraylib -lopengl32 -lgdi32 -lwinmm \
  -o bin/egyptian_fighter.exe

echo "Build done. Running..."
./bin/egyptian_fighter.exe