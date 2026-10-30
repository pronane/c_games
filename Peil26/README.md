# PEIL 26

A 3D Gaelic football game for Windows 10 and 11. Players are skinned meshes in a GLB, with a skeleton and clips for idle, run, kick, solo, hand-pass, catch and block. The match runs in WebGL, so it is a real 3D scene rather than a software drawing, and it is aimed at 60 frames per second on a normal PC GPU.

Counties, players, Peil Park, commentary and sponsors are fictional. This is not a GAA, EA or FIFA product. No real-player likenesses and no licensed audio.

The exhibition uses the 2026 men's rules: goal 3, point 1, two-pointer from on or outside the 40-metre arc, four steps, solo, bounce, marks, kick-out, 45, the 4-and-3 shape, the black-card sin bin, and the hooter. Third-level trial rules are not used.

## Play

Double-click `build_release.bat`. It needs Node.js from https://nodejs.org/. The script installs Electron, builds `dist\Peil26.exe`, and launches it. The first build downloads Electron, about 100 MB. Later builds are faster.

You can also open `public/index.html` through any static server, but the Windows app is the intended build. Do not open the HTML file by double-click; the browser will block the modules.

## Controllers

A USB pad, or an EasySMX pad on its USB cable or 2.4G receiver, is read through the gamepad API.

- XInput mode uses the Xbox layout. On many EasySMX pads that is LED 1 and LED 4. Hold the mode or Turbo button if the manual says that switches XInput and D-Input.
- D-Input and other generic USB pads use the EasySMX button order.
- Back and Start together swap Xbox and Nintendo face buttons, for pads whose A and B are printed the other way around.

Left stick or D-pad moves. A or RT kicks. Hold, then release, for power. LT is a driven goal; otherwise a kick at the posts goes over the bar. X hand-passes, Y solos, B bounces, LB tackles, RB sprints. The right stick aims. Start pauses.

## PlayStation 3

A PS3 build is not included. The console needs Sony's CELL SDK and a licensed kit, which are not public. There is no homebrew or jailbreak path in this project.

## What changed

The first build drew the pitch in software with pygame. That cannot be a modern 3D game, and it could not hold a broadcast frame rate. This version replaces that renderer. The old Python rules experiments are still in `peil26/` and `tests/` if you want them; they are not the game you launch.
