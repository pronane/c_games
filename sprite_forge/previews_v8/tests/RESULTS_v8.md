# Sprite Forge Studio v8 tests

| result | test | detail | s |
|---|---|---|---|
| PASS | turn_args parses 0/90/180/270 |  |  |
| PASS | GUI turn dropdown -> degrees (+ fine angle override) |  |  |
| PASS | icons: 17 drawn, all non-empty RGBA |  |  |
| PASS | wizard command: 3D tab -> --no-fbx --anim-export, retro tab -> --console snes |  |  |
| PASS | wizard command: photo source -> no 3D / console flags |  |  |
| PASS | forge.py cutout: transparent RGBA cut-out, clear border, sprite + HD sprite + landmarks | QA verdict FAIL (see cutout_report.txt) | 1.69 |
| PASS | forge.py export-ef: sprites.cfg + one strip per move for all 14 fighter moves | missing: none | 0.55 |
| PASS | forge.py turn --yaw 0 | turn: 0 deg (template) in 1.3s -> /tmp/sfs_v8test_4t48p_14/turn | 1.68 |
| PASS | forge.py turn --yaw 90 | turn: 90 deg (template) in 1.3s -> /tmp/sfs_v8test_4t48p_14/turn | 1.67 |
| PASS | forge.py turn --yaw 180 | turn: 180 deg (template) in 1.3s -> /tmp/sfs_v8test_4t48p_14/turn | 1.71 |
| PASS | forge.py turn --yaw 270 | turn: 270 deg (template) in 1.3s -> /tmp/sfs_v8test_4t48p_14/turn | 1.73 |
| PASS | forge.py turn --yaw 60 | turn: 60 deg (template) in 1.3s -> /tmp/sfs_v8test_4t48p_14/turn | 1.71 |
| PASS | build --turn 90 final (thread pool) |  | 5.75 |
| PASS | build --turn 90 final, SFS_THREADS=1 (serial) |  | 10.49 |
| PASS | thread pool output == serial output (atlas.png) | speed-up x1.8 |  |
| PASS | rebuild unchanged (cache) |  | 0.79 |
| PASS | build --turn 90 --quality draft (Quick preview) | x2.7 faster than final | 2.17 |
| PASS | build report labels turned moves honestly |  |  |
| PASS | Start-tab wizard: photo -> turn 90 -> EF target -> Quick preview build |  | 3.93 |
| PASS | wizard's 'Same as typing' command == wizard build |  | 2.1 |
