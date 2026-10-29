#!/bin/bash
# Quick dev build + run.  Works in the MSYS2 UCRT64 shell (Windows) and on Linux.
set -e
cd "$(dirname "$0")"
mkdir -p bin
SRC="src/main.c src/player.c src/game.c src/demo.c src/pad.c src/gfx.c"
if [[ "$OSTYPE" == msys* || "$OSTYPE" == cygwin* ]]; then
  # MSYS2's raylib links against the separate glfw3 package; fall back if it isn't needed
  gcc -std=c99 -O2 -Wall $SRC -lraylib -lglfw3 -lopengl32 -lgdi32 -lwinmm -o bin/egyptian_fighter.exe 2>/dev/null ||
  gcc -std=c99 -O2 -Wall $SRC -lraylib -lopengl32 -lgdi32 -lwinmm -o bin/egyptian_fighter.exe
  EXE=./bin/egyptian_fighter.exe
else
  RAYLIB=${RAYLIB:-/usr/local}
  gcc -std=c99 -O2 -Wall $SRC -I"$RAYLIB/include" -I"$RAYLIB/src" -L"$RAYLIB/lib" -L"$RAYLIB/src" \
      -lraylib -lGL -lm -lpthread -ldl -lrt -lX11 -o bin/egyptian_fighter
  EXE=./bin/egyptian_fighter
fi
echo "Build done. Running..."   # assets/ is read relative to the working directory
"$EXE" "$@"
