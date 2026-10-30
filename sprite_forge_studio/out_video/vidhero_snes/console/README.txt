Sprite Forge Studio - console export: SNES / Super Famicom

4bpp planar (SNES format) tiles, 15 colours + transparent per palette (8 OBJ palettes), BGR555. 32 sprites / 34 tiles per line.
APPROXIMATIONS: 64x64 character size; 512 sprite tiles in VRAM at once (16 KB name tables)

frame size : 48x64 px   pivot_x 24   ground_y 63   (sprites face RIGHT; mirror to face left)
files      :
  frames/<move>_<NN>.png   every frame at console size (indexed PNG, index 0 = transparent)
  sheet.png                all frames, one row per move (like atlas.png)
  vidhero_snes_snes.h      C arrays: palette, tiles/rects, frames, anims
  palette.pal / .png / .bin  JASC palette (Aseprite/GIMP), swatch, native console values (entry 0 = transparent)
  tiles_bankN.png / .chr|.2bpp|.4bpp   unique 8x8 tiles (indexed PNG + raw native tile data)
  banks: [504, 34] tiles each (limit 512 per bank)
WARNING: 538 tiles do not fit one 512-tile bank -> 2 banks (swap/stream banks per move: CHR bank switching / VRAM DMA)
