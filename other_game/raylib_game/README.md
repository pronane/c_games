# New Raylib Game

This is a clean C/raylib starter project for an original game. It contains no
code or assets extracted from the N64 ROM in the parent directory. The ROM is
left untouched and remains separate from this desktop application.

## Layout

- `src/` — application entry point and game lifecycle
- `assets/` — original textures, models, fonts, and other visual assets
- `audio/` — original music and sound effects
- `levels/` — original level data

Keep source assets organized by type and use descriptive names. Only add assets
you created or are authorized to use.

## Build

Install raylib and CMake, then configure and build from this directory:

```sh
cmake -S . -B build
cmake --build build
```

The executable opens a placeholder window. Replace the prototype with original
gameplay and assets as you develop the project.
