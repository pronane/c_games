# Mario Kart 64 PC — N64 Clean-Room Edition (EasySMX USB Ready)

A complete, standalone 3D Windows PC clean-room recreation of **Mario Kart 64** written in pure hardware-accelerated OpenGL (`opengl32.dll`), Windows Multimedia 16-bit Stereo PCM Synth (`winmm.dll`), and a dual-stack **EasySMX USB Controller Engine** (`XInput` + `WinMM DirectInput`).

> **Note:** This project is a 100% original clean-room codebase using procedural 3D geometry, procedural N64 textures, and real-time synthesized music/SFX. It contains zero proprietary Nintendo ROM binaries or ripped assets, and requires **zero external installs or downloads** to compile and run on Windows 10 or Windows 11.

---

## Quick Start (Build & Run in One Click)

1. Extract the `.zip` archive to any folder on Windows 10 or Windows 11.
2. Plug in your **EasySMX USB Controller** (up to **4 controllers** supported simultaneously for 1P–4P split-screen, or use Keyboard).
3. Double-click **`release.bat`** (or run `release.bat` from Command Prompt / PowerShell).

`release.bat` automatically locates the C# compiler pre-installed in Windows (`C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe`, with fallback to `dotnet`), compiles all source modules into **`release\MarioKart64.exe`**, verifies all 16 racing courses + 4 battle arenas, and launches the game!

* Subsequent launches: run **`release\MarioKart64.exe`** directly or double-click **`run_game.bat`**.
* Build without auto-launching: `release.bat --build-only`
* Run automated physics/track/audio verification suite: `release\MarioKart64.exe --self-test`

---

## Language, Graphics Pipeline & Build Architecture

* **Language:** **100% C#** (strict C# 5 syntax targeting `.NET Framework 4.x`, pre-installed on every Windows 10 and Windows 11 PC — zero external SDKs, NuGet packages, or third-party engines required).
* **How `release.bat` Compiles & Builds:**
  1. `release.bat` locates the built-in Windows C# compiler (`%SystemRoot%\Microsoft.NET\Framework64\v4.0.30319\csc.exe`, with automatic fallback to 32-bit `csc.exe` or `dotnet build MarioKart64.csproj`).
  2. It compiles all 23 `.cs` modules across `src\Core`, `src\Input`, `src\Audio`, `src\Entities`, `src\Tracks`, `src\Rendering`, and `src\Game` with `/optimize+ /target:winexe /win32icon:assets\mk64.ico` into a single native-windowed executable: **`release\MarioKart64.exe`**.
  3. It stages `easysmx_config.ini` and `mk64.ico`, runs `release\MarioKart64.exe --verify` to validate all 20 tracks, audio synthesis, and controller subsystems, and launches the game.
* **Authentic N64 + SGI Hybrid 3D Rendering (`opengl32.dll` + `SgiSpriteGenerator.cs`):**
  * Just like Nintendo's 1996 *Mario Kart 64* (which combined real-time 3D polygon courses with smooth Silicon Graphics raytraced billboard sprites for characters, karts, items, and trees), `SgiSpriteGenerator.cs` runs a multi-threaded **analytic 3D Phong + soft-shadow raytracer** at startup to generate **160 multi-angle + steering-lean SGI kart sprites** across all 8 drivers, high-res character portraits, all 14 item sprites, and 3D-shaded trees/hazards, composited into real-time 3D OpenGL display-list courses!
* **Direct Hardware P/Invoke Subsystems:**
  * **3D Graphics:** `opengl32.dll` + `gdi32.dll` hardware WGL context (`NativeGl.cs`, `SceneRenderer.cs`, `HudRenderer.cs`).
  * **Audio:** `winmm.dll` double-buffered 44.1 kHz 16-bit stereo waveOut PCM synthesizer (`NativeWaveOut.cs`, `N64AudioSynth.cs`).
  * **USB Gamepads:** Dual-stack `xinput1_4.dll` + `winmm.dll` DirectInput (`NativeInput.cs`, `EasySmxControllerManager.cs`).

---

## EasySMX USB Controller Support (Plug-and-Play)

Compatible out-of-the-box with all EasySMX wired USB and 2.4GHz USB-dongle controllers (including **ESM-9100, ESM-9101, ESM-9013, ESM-4108, Bayard 9124, X05, X10, X15, X20**):

* **XInput Mode (Default Windows Mode — LED 1+2):**
  * Automatically detected via `xinput1_4.dll` / `xinput1_3.dll` / `xinput9_1_0.dll`.
  * Supports full 360° analog steering with N64 response curve, analog `LT`/`RT` triggers, and **Dual-Motor Force-Feedback Rumble** on drifts, boosts, shell hits, walls, and off-road!
* **DirectInput / D-Input Mode (LED 1+3 or LED 1+4 — toggled by holding EasySMX HOME for 5s):**
  * Automatically detected via `winmm.dll` (`joyGetPosEx` / `joyGetDevCapsW`), including automatic XInput shadow-device deduplication so one pad never registers twice.
* **In-Game EasySMX Controller Studio (`F1` or Title Menu):**
  * View live connected USB slots (`P1`–`P4`), live 2D analog stick crosshair, trigger meters, button bitmasks, adjust Stick Deadzone & Steering Sensitivity, test Rumble motors, and **rebind any button with a single press** (saved to `easysmx_config.ini`).

### Default Controls

| N64 Function | EasySMX USB (XInput Mode) | EasySMX USB (D-Input Mode) | Keyboard (P1) |
| :--- | :--- | :--- | :--- |
| **Steer / Menu** | Left Stick or D-Pad | Left Stick or POV Hat | `Arrow Keys` or `W A S D` |
| **Aim Throw Up/Back** | Left Stick Up / Down | Left Stick Up / Down | `Up/W` or `Down/S` |
| **Accelerate (`A`)** | `A` Button or `RT` Trigger | `Button 1` or `Button 3` | `Up`, `W`, `Z`, or `K` |
| **Brake / Reverse (`B`)** | `B` or `X` Button | `Button 2` or `Button 4` | `Down`, `S`, `X`, or `L` |
| **Hop / Power-Slide (`R`)** | `RB` (Right Bumper) | `R1` (`Btn 6`) or `R2` (`Btn 8`) | `Space`, `Right Shift`, or `J` |
| **Use / Fast-Stop Item (`Z`)** | `LB` or `LT` Trigger | `L1` (`Btn 5`) or `L2` (`Btn 7`) | `E`, `Q`, `Left Shift`, or `Ctrl` |
| **Camera Distance (`C-Up`)** | `Back / Select` or `Y` | `Select` (`Btn 9`) | `C` or `Tab` |
| **Pause (`Start`)** | `Start` Button | `Start` (`Btn 10`) | `Enter`, `P`, or `Esc` |
| **Fullscreen Toggle** | — | — | `F11` or `Alt + Enter` |

---

## Original 8-Character Roster & Physics Classes

* **Lightweights** *(Fastest acceleration, nimble cornering, best off-road speed retention, lowest mass)*:
  * **Peach**, **Toad**, **Yoshi**
* **Middleweights** *(All-around balanced handling, speed, and weight)*:
  * **Mario**, **Luigi**
* **Heavyweights** *(Highest ramming mass — knocks lighter karts aside, strong top-end momentum, wider drift arcs)*:
  * **D.K. (Donkey Kong)**, **Wario**, **Bowser**

---

## All 16 Original Racing Tracks + 4 Battle Courses

### Mushroom Cup
1. **Luigi Raceway** — Sweeping banked stadium oval, brick tunnel, giant Luigi Jumbotron, and floating **Hot Air Balloon** carrying a suspended Item Box!
2. **Moo Moo Farm** — Rolling country dirt track with Red Barn, grazing Moo Moo Cows, and **popping Monty Moles**!
3. **Koopa Troopa Beach** — Tropical island circuit around **Koopa Rock** featuring the **secret Boost-Ramp Cave Shortcut** right through the rock!
4. **Kalimari Desert** — Red canyon desert intersected twice by railroad crossings and a **moving Steam Locomotive Train**!

### Flower Cup
5. **Toad's Turnpike** — Nighttime figure-8 highway overpass with streetlights and **moving Trucks, Buses, & Cars** (including **oncoming traffic in Extra Mirror Mode**)!
6. **Frappe Snowland** — Snowy winter circuit with falling snow, **Giant Snow Mario Statue**, narrow bridge, and **explosive Snowmen**!
7. **Choco Mountain** — Foggy mountain pass with tunnel, unguarded cliff drop to the lower road, and **bouncing Falling Boulders**!
8. **Mario Raceway** — Classic GP circuit with sweeping S-bends, Giant Red Mushroom, and the **Green Warp Pipe Tunnel**!

### Star Cup
9. **Wario Stadium** — Nighttime dirt motocross stadium packed with rhythmic mogul bumps and the **Big Motocross Boost Jump**!
10. **Sherbet Land** — Low-traction glacier ice course with Ice Cave, **sliding Penguins**, and freezing water (rescues you inside an **Ice Cube**)!
11. **Royal Raceway** — Lakeside circuit featuring the **Royal Mega River Jump** and a playable side drive up to **Peach's Castle Courtyard**!
12. **Bowser's Castle** — Lava fortress corridors, narrow stone bridges over boiling lava, Bowser Statue, and **crushing Blue Thwomps**!

### Special Cup
13. **D.K.'s Jungle Parkway** — Tropical river jungle with narrow suspension bridge, **Giant River Cannon Jump**, and Torch-lit Cave!
14. **Yoshi Valley** — Multi-path canyon labyrinth with guardrailless plank bridges, `?` mystery rank display, and the **Giant Spinning Yoshi Egg**!
15. **Banshee Boardwalk** — Haunted nighttime wooden pier with missing guardrail sections, leaping Cheep-Cheep, and **Haunted House swarming with Bats**!
16. **Rainbow Road** — Starry cosmic neon highway featuring the famous plunging start drop, neon constellations, and **oncoming Chain Chomps**!

### Battle Mode Arenas (3-Balloon Rules)
17. **Big Donut** | 18. **Block Fort** | 19. **Double Deck** | 20. **Skyscraper**

---

## Authentic Mario Kart 64 Driving Techniques Included

* **Rocket Start:** Press and hold Accelerate (`A`) just as Lakitu's 2nd red light transitions toward the final countdown beat (avoid revving too early or your engine stalls in burnout smoke!).
* **Power-Slide & Mini-Turbo (`R` / `RB`):** Press & hold `RB` while steering to hop into a Power-Slide. Counter-steer back and forth to turn your tire smoke from **White -> Yellow -> Orange/Red**, then release `RB` for a **Mini-Turbo Boost**!
* **AB Spin Turn:** Hold `A + B` while stationary + steer Left/Right to pivot in place.
* **Banana Braking (`♪`):** Tap `B` (Brake) with neutral steering right as you touch a Banana peel to save yourself from spinning out with a golden musical note `♪`!
* **Ground-Skimming Spiny Shell:** True to MK64, the Blue Spiny Shell races along the track pavement knocking aside anyone in its path on the way to 1st Place!
