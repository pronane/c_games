# SpriteForge example - MSYS2 UCRT64 (Windows) or Linux.
#   make            build bin/example(.exe)
#   make run        build and run with assets/dec
#   make sprites    rebuild assets/dec from samples_src/dec
#   make verify     check every assets/*/sprites.cfg
#   make raylib     download raylib source with Python (no git/curl) and build it into third_party/raylib/src
#   make clean
CC      ?= gcc
CFLAGS  ?= -std=c99 -O2 -Wall -Wextra
PYTHON  ?= python
CHAR    ?= dec

ifeq ($(OS),Windows_NT)
  EXE     = bin/example.exe
  LDLIBS  = -lraylib -lopengl32 -lgdi32 -lwinmm
else
  EXE     = bin/example
  PYTHON  = python3
  LDLIBS  = $(shell pkg-config --libs raylib 2>/dev/null || echo -lraylib) -lGL -lm -lpthread -ldl -lrt -lX11
endif
# raylib not installed system-wide? make RAYLIB=C:/path/to/raylib/src  (or `make raylib` once - it is then used automatically)
RAYLIB_VER ?= 5.5
ifeq ($(RAYLIB),)
  ifneq ($(wildcard third_party/raylib/src/libraylib.a),)
    RAYLIB = third_party/raylib/src
  endif
endif
ifdef RAYLIB
  CPPFLAGS += -I$(RAYLIB)
  LDLIBS := -L$(RAYLIB) $(LDLIBS)
endif

all: $(EXE)

$(EXE): example/main.c include/spriteforge.h
	@mkdir -p bin
	$(CC) $(CFLAGS) $(CPPFLAGS) example/main.c -Iinclude -o $@ $(LDFLAGS) $(LDLIBS)

run: $(EXE)
	./$(EXE) assets/$(CHAR)

sprites:
	$(PYTHON) tools/spriteforge.py --name $(CHAR) --src samples_src/$(CHAR) --out assets/$(CHAR)

verify:
	$(PYTHON) tools/verify_cfg.py assets/*/

raylib:
	$(PYTHON) tools/fetch_raylib.py $(RAYLIB_VER) third_party
	$(MAKE) -C third_party/raylib/src PLATFORM=PLATFORM_DESKTOP
	@echo "raylib built - now just run: make"

clean:
	rm -f bin/example bin/example.exe

.PHONY: all run sprites verify clean raylib
