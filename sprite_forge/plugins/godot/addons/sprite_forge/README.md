# Sprite Forge importer for Godot 4 (v9)

1. Copy `addons/sprite_forge` into your project's `addons/` and enable it (Project > Project Settings > Plugins).
2. Copy a Sprite Forge build folder (the one with `atlas.json`, or a `forge.py atlas` pack with `pack.json`) into the project.
3. Project > Tools > **Sprite Forge: import build folder...** and pick that folder.

You get `<name>_frames.tres` (SpriteFrames: every move with its fps and loop flag) and `<name>.tscn`:
a `SpriteForgeCharacter` (AnimatedSprite2D) whose origin is the character's feet, with `Hurtbox` / `Hitbox`
Area2D children that follow `framedata.json` frame by frame (turn on *Show Boxes* to see them) and a
`hit_active(move, frame, rect)` signal. If the build has `maps/atlas_normal.png` the frames use a CanvasTexture
with that normal map, so a `PointLight2D` lights them.

Headless / CI: `godot --headless --path . --script res://addons/sprite_forge/sf_cli.gd -- res://chars/hero`

Frame data and normal maps are ESTIMATED from the 2D sprites by Sprite Forge - tune them in framedata.json.
