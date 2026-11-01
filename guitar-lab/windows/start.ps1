<#
  Guitar Lab - start the app and open it in the browser.
  The engine and the studio run as one program on this computer only (127.0.0.1); nothing is
  reachable from other machines. Close the window to stop it.
#>
param([int]$Port = 8000, [switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$Root = Split-Path -Parent $PSScriptRoot
$OnWindows = $env:OS -eq 'Windows_NT'
if ($OnWindows) { $Py = Join-Path $Root '.venv\Scripts\python.exe' } else { $Py = Join-Path $Root '.venv/bin/python' }
$Ui = Join-Path $Root 'dist'

function Stop-WithMessage([string]$Message) {
  Write-Host $Message -ForegroundColor Red
  exit 1
}
if (-not (Test-Path $Py)) { Stop-WithMessage 'Guitar Lab is not installed yet. Double-click install.bat in this folder first.' }
if (-not (Test-Path (Join-Path $Ui 'index.html'))) { Stop-WithMessage 'The studio has not been built. Run install.bat again.' }

function Is-GuitarLab([int]$P) {
  try {
    $r = Invoke-RestMethod -Uri "http://127.0.0.1:$P/api/health" -TimeoutSec 2
    return $r.service -eq 'Fretwork Python engine'
  } catch { return $false }
}
function Is-Free([int]$P) {
  try {
    $listener = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, $P)
    $listener.Start(); $listener.Stop(); return $true
  } catch { return $false }
}
function Open-Browser([string]$Url) {
  if ($NoBrowser) { return }
  if ($OnWindows) { Start-Process $Url } elseif (Get-Command xdg-open -ErrorAction SilentlyContinue) { Start-Process xdg-open $Url }
}

# Already running? Just open it.
if (Is-GuitarLab $Port) {
  Write-Host "Guitar Lab is already running at http://localhost:$Port"
  Open-Browser "http://localhost:$Port"
  exit 0
}
while (-not (Is-Free $Port)) { $Port++ }
$Url = "http://localhost:$Port"

try { $Host.UI.RawUI.WindowTitle = 'Guitar Lab - close this window to stop' } catch {}
Write-Host 'Starting Guitar Lab...' -ForegroundColor Cyan
$env:FRETWORK_UI_DIR = $Ui
$env:FRETWORK_LOCAL_APP = '1'   # lets uninstall/update stop it (local requests only)
$proc = Start-Process -FilePath $Py -WorkingDirectory $Root -NoNewWindow -PassThru `
  -ArgumentList @('-m', 'uvicorn', 'server.app:app', '--host', '127.0.0.1', '--port', "$Port", '--log-level', 'warning')

$ready = $false
for ($i = 0; $i -lt 120; $i++) {
  if ($proc.HasExited) { Stop-WithMessage 'Guitar Lab stopped while starting. Run install.bat again; the log is windows\install.log.' }
  if (Is-GuitarLab $Port) { $ready = $true; break }
  Start-Sleep -Milliseconds 500
}
if (-not $ready) { Stop-WithMessage 'Guitar Lab did not start within a minute.' }

Write-Host ''
Write-Host "Guitar Lab is running at $Url" -ForegroundColor Green
Write-Host 'Keep this window open while you use it. Close it to stop Guitar Lab.'
Open-Browser $Url
$proc.WaitForExit()
