# raylib viewer for forge.py anim-export output (Linux gcc or MSYS2 UCRT64 on Windows)
#   make RAYLIB=/path/to/raylib/src           build bin/anim_viewer(.exe)
#   ./bin/anim_viewer ../out/<name>/anim idle walk
CC     ?= gcc
CFLAGS ?= -std=c99 -O2 -Wall
ifeq ($(OS),Windows_NT)
  EXE = bin/anim_viewer.exe
  LDLIBS = -lraylib -lopengl32 -lgdi32 -lwinmm
else
  EXE = bin/anim_viewer
  LDLIBS = -lraylib -lGL -lm -lpthread -ldl -lrt -lX11
endif
ifdef RAYLIB
  CPPFLAGS += -I$(RAYLIB)
  LDLIBS := -L$(RAYLIB) $(LDLIBS)
endif
all: $(EXE)
$(EXE): anim_viewer.c
	@mkdir -p bin
	$(CC) $(CFLAGS) $(CPPFLAGS) anim_viewer.c -o $@ $(LDLIBS)
clean:
	rm -f bin/anim_viewer bin/anim_viewer.exe
.PHONY: all clean
