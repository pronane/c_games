# Guitar Lab on Windows

Runs everything on your own PC. Nothing is uploaded anywhere: the "engine" is a program on this
computer that the studio page talks to.

## Install (once)

1. Get the code: on GitHub, **Code → Download ZIP** and unzip it, or `git clone https://github.com/pronane/c_games`.
2. Open `c_games\guitar-lab\windows` and double-click **install.bat**.
   - Installs Python 3.12, Node.js and ffmpeg with winget if they're missing (Windows may ask for permission).
   - Sets up the engine, downloads the 55 MB instrument-separation model and checks its fingerprint, and builds the studio.
   - With an NVIDIA graphics card it installs the GPU build of PyTorch (about 2.5 GB); otherwise the CPU build.
   - Takes about 5–15 minutes depending on your connection. Progress is saved in `windows\install.log`.
3. A **Guitar Lab** shortcut appears on your desktop and in the Start menu.

## Use

Double-click **Guitar Lab**. A window opens ("close this window to stop") and the app opens in your
browser at `http://localhost:8000`. Use Chrome or Edge. The microphone and USB guitar cables work
because the page runs on this computer.

## Update, uninstall

- **update.bat**: gets the latest code (if you used git) and rebuilds.
- **uninstall.bat**: removes the shortcuts, the engine, the studio build and the model. Python, Node.js and ffmpeg stay.

## If something goes wrong

- *"Python/Node.js was installed but cannot be found yet"*: close the window and run install.bat again.
- *winget is missing* (older Windows 10): install "App Installer" from the Microsoft Store, or install
  Python 3.12 from python.org (tick "Add to PATH") and Node.js LTS from nodejs.org, then run install.bat again.
- *Antivirus blocks the download*: allow `download.pytorch.org` and `github.com`, then run install.bat again.
- Options for install.bat: `-Gpu cpu` forces the CPU build, `-SkipFfmpeg` skips ffmpeg, `-NoShortcuts`.
