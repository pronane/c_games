# Arena FC — Windows Setup Guide

Step-by-step instructions for building, running, and testing Arena FC on Windows.

## Prerequisites

| Software | Version | Download |
|----------|---------|----------|
| Godot Engine | 4.7.2 (Mono/.NET) | https://godotengine.org/download |
| .NET SDK | 9.0 | https://dotnet.microsoft.com/download/dotnet/9.0 |
| Git | Latest | https://git-scm.com/download/win |
| Python | 3.10+ (optional, for tests) | https://python.org/downloads/ |

## Quick Start

### Option A: Automated build script

```cmd
cd arena-fc
build_windows.bat
```

This will:
1. Pull latest changes from GitHub
2. Build the .NET solution
3. Run all tests (.NET + Python)
4. Open the Godot editor

### Option B: Manual steps

#### 1. Clone and navigate

```cmd
git clone https://github.com/pronane/c_games.git
cd c_games\arena-fc
```

#### 2. Build .NET

```cmd
dotnet build ArenaFC.sln -c Release
```

#### 3. Run tests

```cmd
REM .NET tests
dotnet run --project Tests\MatchCoreTests.csproj -c Release

REM Python tests
python Tools\test_soccer_forge.py
python Tools\test_pads.py
```

#### 4. Open in Godot

```cmd
"C:\path\to\Godot_v4.7.2-stable_mono_win64.exe" --path .
```

Or open the Godot editor and import the project from this folder.

#### 5. Run the game

Press **F5** in the Godot editor, or:

```cmd
"C:\path\to\Godot_v4.7.2-stable_mono_win64.exe" --path . --resolution 1280x720
```

## Video Recording

### Using Windows Game Bar (built-in)

1. Press **Win + G** to open Game Bar
2. Press **Win + Alt + R** to start recording
3. Play the game
4. Press **Win + Alt + R** again to stop
5. Video saved to `Videos\Captures\`

### Using OBS (free, better quality)

1. Download OBS: https://obsproject.com/
2. Add a **Window Capture** source, select the Godot window
3. Set recording format to **MP4**
4. Click **Start Recording**, play, then **Stop Recording**

### Recommended recording settings

- Resolution: 1280×720 or higher
- Frame rate: 30 or 60 fps
- Duration: 55 seconds (match the original baseline recording)
- Camera: Side view (default) or broadcast angle

## Controller Testing (EasySMX)

### Setup

1. Plug in the EasySMX controller via USB or Bluetooth
2. Windows should detect it as an Xbox-compatible controller
3. In Godot, go to **Project → Input Map** to verify bindings

### Test checklist

- [ ] Menu navigation with D-pad (up/down/left/right)
- [ ] Menu selection with A button
- [ ] Player movement with left stick
- [ ] Sprint with B button (or right stick click)
- [ ] Pass with X button
- [ ] Shoot with Y button (hold for power)
- [ ] Tackle with A button
- [ ] Slide tackle with B button
- [ ] Camera switch with right stick click
- [ ] Pause with Start button

### Controller database

The game includes a controller database at `Data\input\gamecontrollerdb.txt`.
If your controller isn't recognised, check if it's listed there. You can add
custom mappings in Godot's Input Map.

## Troubleshooting

### "Godot not found"
Pass the full path: `build_windows.bat "C:\Godot\Godot.exe"`

### ".NET SDK not found"
Install .NET 9 SDK from https://dotnet.microsoft.com/download/dotnet/9.0
Restart your terminal after installation.

### "Project version mismatch"
Make sure you're using Godot 4.7.2 Mono. Other versions may not load the project.

### Game runs but no player visible
Check that `Data\models\soccer_player.glb` exists (3.1 MB).
If missing, pull latest: `git pull origin main`

### Controller not working
1. Check Windows Game Controllers: `joy.cpl`
2. Verify the controller appears and responds to input
3. In Godot, check **Project → Input Map** for correct bindings
