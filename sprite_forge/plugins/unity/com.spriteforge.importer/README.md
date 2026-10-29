# Sprite Forge importer for Unity (v9) - UPM package

Install: Window > Package Manager > + > *Add package from disk...* > `com.spriteforge.importer/package.json`
(or copy the folder into your project's `Packages/`). Unity 2021.3 LTS or newer.

1. Copy a Sprite Forge build folder (with `atlas.json`, or a `forge.py atlas` pack with `pack.json`) under `Assets/`.
2. **Tools > Sprite Forge > Import Build Folder...** and pick it.

You get: sprites sliced with the pivot at the feet (`maps/atlas_normal.png` becomes the `_NormalMap` secondary
texture, so URP 2D lights light it), `<name>_data.asset` (moves, fps, loop, frame data), `Anim/*.anim` +
`<name>.controller`, and `<name>.prefab` with `SpriteForgeCharacter` (plays moves, moves hurt / hit
BoxCollider2D triggers frame by frame, `HitActive` event, gizmos). Batch mode:
`Unity -batchmode -quit -projectPath P -executeMethod SpriteForge.Editor.SpriteForgeImporter.ImportFromCommandLine -sfFolder Assets/chars/hero`

Frame data and normal maps are ESTIMATED from the 2D sprites. This package was compiled against stub Unity APIs
only; it has not been run inside the Unity editor by the Sprite Forge tests.
