<#
  Guitar Lab - Windows installer.

  Installs what is missing (Python 3.12, Node.js LTS, optionally ffmpeg) with winget, sets up the
  analysis engine in guitar-lab\.venv, downloads and checks the instrument-separation model,
  builds the studio, and adds "Guitar Lab" shortcuts to the desktop and Start menu.
  Safe to run again: finished steps are skipped or refreshed.

  Usually started by double-clicking install.bat. Options:
    -Gpu auto|cpu|cuda   PyTorch build. auto = NVIDIA build when an NVIDIA card is found.
    -SkipFfmpeg          don't install ffmpeg (only needed for M4A/AAC songs)
    -Update              refresh an existing install (used by update.bat)
    -NoShortcuts         don't create shortcuts
#>
param(
  [ValidateSet('auto', 'cpu', 'cuda')][string]$Gpu = 'auto',
  [switch]$SkipFfmpeg,
  [switch]$Update,
  [switch]$NoShortcuts
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$Here = $PSScriptRoot
$Root = Split-Path -Parent $Here                       # the guitar-lab folder
$OnWindows = $env:OS -eq 'Windows_NT'
$Venv = Join-Path $Root '.venv'
if ($OnWindows) { $Py = Join-Path $Venv 'Scripts\python.exe' } else { $Py = Join-Path $Venv 'bin/python' }
$Log = Join-Path $Here 'install.log'
try { Start-Transcript -Path $Log -Append | Out-Null } catch {}

function Step([string]$Message) { Write-Host ''; Write-Host "==> $Message" -ForegroundColor Cyan }
function Done([string]$Message) { Write-Host "    $Message" -ForegroundColor Green }
function Note([string]$Message) { Write-Host "    $Message" -ForegroundColor Yellow }
function Fail([string]$Message) {
  Write-Host ''
  Write-Host "Install stopped: $Message" -ForegroundColor Red
  Write-Host "The full log is in $Log"
  try { Stop-Transcript | Out-Null } catch {}
  exit 1
}
function Has([string]$Command) { [bool](Get-Command $Command -ErrorAction SilentlyContinue) }
function Run([string]$What, [string]$Exe, [string[]]$Arguments) {
  & $Exe @Arguments
  if ($LASTEXITCODE -ne 0) { Fail "$What failed (exit code $LASTEXITCODE)." }
}
function Refresh-Path {
  if ($OnWindows) {
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
  }
}
function Winget-Install([string]$Id, [string]$Name, [string]$Manual) {
  if (-not (Has 'winget')) {
    Fail "$Name is not installed and winget (the Windows package manager) isn't available. Install $Name from $Manual, then run install.bat again."
  }
  Write-Host "    Installing $Name with winget (a Windows prompt may ask for permission)..."
  winget install --id $Id -e --silent --accept-package-agreements --accept-source-agreements
  if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne -1978335189) {   # -1978335189: already installed
    Fail "winget could not install $Name. Install it from $Manual, then run install.bat again."
  }
  Refresh-Path
}

Write-Host 'Guitar Lab installer' -ForegroundColor White
Write-Host "Folder: $Root"
if (-not (Test-Path (Join-Path $Root 'server\app.py')) -and -not (Test-Path (Join-Path $Root 'server/app.py'))) {
  Fail 'This script must stay in the guitar-lab\windows folder of the downloaded code.'
}

# A running copy holds its files open; stop it before replacing them.
. (Join-Path $Here 'common.ps1')
if (Stop-GuitarLab) { Write-Host 'Stopped the running Guitar Lab so it can be updated.' }

# ---------------------------------------------------------------- Python 3.11-3.13
function Find-Python {
  $candidates = @(
    @{ Exe = 'py'; Args = @('-3.12') }, @{ Exe = 'py'; Args = @('-3.13') }, @{ Exe = 'py'; Args = @('-3.11') },
    @{ Exe = 'python'; Args = @() }, @{ Exe = 'python3'; Args = @() }
  )
  foreach ($c in $candidates) {
    if (-not (Has $c.Exe)) { continue }
    try { $v = & $c.Exe @($c.Args + @('--version')) 2>&1 | Out-String } catch { continue }
    # The Microsoft Store "python" stub prints nothing useful; only accept a real 3.11-3.13.
    if ($v -match 'Python 3\.(11|12|13)\.') { return $c }
  }
  return $null
}
Step 'Checking Python'
if (Test-Path $Py) {
  Done 'Engine environment already exists.'
} else {
  $python = Find-Python
  if (-not $python) {
    Winget-Install 'Python.Python.3.12' 'Python 3.12' 'https://www.python.org/downloads/'
    $python = Find-Python
    if (-not $python) { Fail 'Python was installed but cannot be found yet. Close this window, open a new one and run install.bat again.' }
  }
  Done ("Using " + (& $python.Exe @($python.Args + @('--version')) 2>&1 | Out-String).Trim())
  Step 'Creating the engine environment (.venv)'
  Run 'Creating the Python environment' $python.Exe ($python.Args + @('-m', 'venv', $Venv))
}

# ---------------------------------------------------------------- engine packages
Push-Location $Root
try {
  Step 'Installing the analysis engine (a few minutes the first time)'
  Run 'Updating pip' $Py @('-m', 'pip', 'install', '--disable-pip-version-check', '-q', '--upgrade', 'pip')
  Run 'Installing engine packages' $Py @('-m', 'pip', 'install', '--disable-pip-version-check', '-q', '-r', 'server/requirements-transcription.txt')
  # Basic Pitch without its TensorFlow extras; the bundled ONNX model is used.
  Run 'Installing Basic Pitch' $Py @('-m', 'pip', 'install', '--disable-pip-version-check', '-q', '--no-deps', 'basic-pitch==0.4.0')
  Done 'Transcription engine installed.'

  Step 'Installing PyTorch and Demucs (instrument separation)'
  $flavour = $Gpu
  if ($flavour -eq 'auto') {
    if (Has 'nvidia-smi') { $flavour = 'cuda' } else { $flavour = 'cpu' }
  }
  $installed = $false
  if ($flavour -eq 'cuda') {
    Write-Host '    NVIDIA graphics card found: installing the GPU build of PyTorch (about 2.5 GB).'
    foreach ($tag in @('cu130', 'cu129', 'cu128', 'cu126')) {
      & $Py -m pip install --disable-pip-version-check -q torch torchaudio --index-url "https://download.pytorch.org/whl/$tag"
      if ($LASTEXITCODE -eq 0) { $installed = $true; Done "PyTorch $tag installed."; break }
    }
    if (-not $installed) { Note 'The GPU build could not be installed; using the CPU build instead.' }
  }
  if (-not $installed) {
    Run 'Installing PyTorch (CPU)' $Py @('-m', 'pip', 'install', '--disable-pip-version-check', '-q', 'torch', 'torchaudio', '--index-url', 'https://download.pytorch.org/whl/cpu')
    Done 'PyTorch (CPU) installed.'
  }
  Run 'Installing Demucs' $Py @('-m', 'pip', 'install', '--disable-pip-version-check', '-q', 'demucs==4.1.0')
  Done 'Demucs installed.'

  Step 'Getting the instrument-separation model (55 MB, checked against its fingerprint)'
  & $Py -m server.model_store --check | Out-Null
  if ($LASTEXITCODE -eq 0) {
    Done 'Model already installed and verified.'
  } else {
    Run 'Downloading the model' $Py @('-m', 'server.model_store')
    Done 'Model installed.'
  }

  Step 'Checking the engine starts'
  Run 'Engine self-check' $Py @('-c', 'from server import app, models; c = models.capabilities(); assert c["transcription"]["configured"], "transcription"; assert c["separation"]["configured"], "separation"; print("    separation and transcription ready; GPU:", c["gpu"]["available"])')

  # ---------------------------------------------------------------- the studio (web page)
  Step 'Checking Node.js'
  $nodeOk = $false
  if (Has 'node') {
    $nv = (& node --version) -replace '^v', ''
    if ([int]($nv.Split('.')[0]) -ge 20) { $nodeOk = $true; Done "Node.js $nv" }
  }
  if (-not $nodeOk) {
    Winget-Install 'OpenJS.NodeJS.LTS' 'Node.js LTS' 'https://nodejs.org/'
    if (-not (Has 'node')) { Fail 'Node.js was installed but cannot be found yet. Close this window, open a new one and run install.bat again.' }
  }
  if ($OnWindows) { $Npm = 'npm.cmd' } else { $Npm = 'npm' }
  Step 'Building the studio'
  Run 'Installing studio packages' $Npm @('ci', '--no-audit', '--no-fund', '--loglevel=error')
  Run 'Building the studio' $Npm @('run', 'build')
  Done 'Studio built.'
} finally {
  Pop-Location
}

# ---------------------------------------------------------------- optional: ffmpeg
if (-not $SkipFfmpeg -and -not (Has 'ffmpeg')) {
  Step 'Installing ffmpeg (lets the engine read M4A/AAC songs)'
  if ($OnWindows -and (Has 'winget')) {
    winget install --id Gyan.FFmpeg -e --silent --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -eq 0 -or $LASTEXITCODE -eq -1978335189) { Refresh-Path; Done 'ffmpeg installed.' }
    else { Note 'ffmpeg could not be installed. MP3, WAV, FLAC and OGG songs still work.' }
  } else {
    Note 'Skipped. MP3, WAV, FLAC and OGG songs work without it.'
  }
}

# ---------------------------------------------------------------- shortcuts
if ($OnWindows -and -not $NoShortcuts) {
  Step 'Adding Guitar Lab to the desktop and Start menu'
  $shell = New-Object -ComObject WScript.Shell
  $places = @([Environment]::GetFolderPath('Desktop'), (Join-Path ([Environment]::GetFolderPath('Programs')) ''))
  foreach ($place in $places) {
    $link = $shell.CreateShortcut((Join-Path $place 'Guitar Lab.lnk'))
    $link.TargetPath = Join-Path $Here 'start.bat'
    $link.WorkingDirectory = $Here
    $link.Description = 'Start Guitar Lab and open it in your browser'
    $link.IconLocation = "$env:SystemRoot\System32\imageres.dll,103"
    $link.Save()
  }
  Done 'Shortcuts added.'
}

Write-Host ''
Write-Host 'Guitar Lab is installed.' -ForegroundColor Green
if ($OnWindows -and -not $NoShortcuts) {
  Write-Host 'Double-click "Guitar Lab" on your desktop (or in the Start menu) to start it.'
} else {
  Write-Host 'Run windows\start.bat to start it.'
}
try { Stop-Transcript | Out-Null } catch {}
exit 0
