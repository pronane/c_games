# Egyptian Fighter – Character Select + Versus (Raylib + C)

A complete Street Fighter-style prototype with:

- Character select screen
- Two different characters (just called Character 1 & Character 2)
- Human vs CPU **or** Human vs Human
- Full moveset for each character
- **Works even if many (or all) PNG files are missing** – missing assets become colored placeholders + console warnings

## Controls

### Character Select
| Key | Action |
|-----|--------|
| A / D or ← → | Player 1 change character |
| J / Enter | Player 1 Ready |
| ← → | Player 2 change character (Human vs Human only) |
| Z / Numpad 1 | Player 2 Ready |
| Tab | Toggle Human vs CPU ↔ Human vs Human |

### During Fight
**Player 1**
| Key | Action |
|-----|--------|
| WASD / Arrows | Move / Crouch / Jump |
| J | Punch |
| K | Kick |
| U | Special 1 – Pyramid Blast |
| I | Special 2 – Bum Fireball |
| L | Block (hold) |
| O | Throw |
| P | Taunt |

**Player 2** (Human vs Human)
| Key | Action |
|-----|--------|
| Arrow keys | Move / Crouch / Jump |
| Z | Punch |
| X | Kick |
| C | Special 1 |
| V | Special 2 |
| B | Block |
| N | Throw |
| M | Taunt |

| Key | Global |
|-----|--------|
| ESC | Pause / Unpause |
| R / Enter | Return to Character Select (after match) |

---

## Asset Folders

```
assets/
├── char1/
│   ├── idle.png
│   ├── walk.png
│   ├── crouch.png
│   ├── jump.png
│   ├── punch.png
│   ├── kick.png
│   ├── pyramid_blast.png
│   ├── bum_fireball.png
│   ├── block.png
│   ├── hit.png
│   ├── throw.png
│   ├── jump_attack.png
│   ├── taunt.png
│   └── victory.png
└── char2/
    └── (same 14 files)
```

You can put any of the generated male/female sheets into `char1` or `char2`.  
They are treated simply as two different characters.

Each animation PNG should be a single horizontal strip. The game uses these
frame counts: 6 for idle, crouch, punch, kick, both specials, block, hit, throw,
jump attack, taunt, and victory; 8 for walk and jump. Keep transparent padding
around the figures: the game uses it to align their feet and normalize their
on-screen height.

### Missing assets behaviour
- The game **compiles and runs** even if zero PNG files exist.
- Every missing file prints a clear `WARNING: MISSING ASSET: ...` in the console.
- A colored placeholder rectangle is shown instead (different colour per animation state).
- You can add the real PNGs later at any time and they will be used automatically.

---

## How to Build & Run (Windows + VS Code)

1. Install MSYS2 + MinGW + Raylib (easiest):
   ```bash
   pacman -S mingw-w64-x86_64-gcc mingw-w64-x86_64-raylib
   ```
   Add `C:\msys64\mingw64\bin` to your PATH.

2. Open this folder in VS Code.

3. Double-click **`build_release.bat`** (or run it from a terminal).

The script detects the compiler, builds an optimized executable, copies assets, and launches the game.

If Raylib is not auto-detected:
```bat
set RAYLIB_PATH=C:\msys64\mingw64
build_release.bat
```

---

## Project Structure

```
egyptian_fighter/
├── src/
│   ├── main.c
│   ├── common.h
│   ├── player.h / player.c
│   └── game.h / game.c
├── assets/
│   ├── char1/          ← drop Character 1 sprites here
│   └── char2/          ← drop Character 2 sprites here
├── build_release.bat
└── README.md
```

Enjoy!
