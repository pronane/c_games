<#
  Guitar Lab - remove what install.bat added: shortcuts, the engine environment (.venv), studio
  packages and build, and the downloaded model. Your code folder and any files you saved
  elsewhere are left alone. Python, Node.js and ffmpeg stay installed (other programs may use them).
#>
param([switch]$Yes)
$Root = Split-Path -Parent $PSScriptRoot
$OnWindows = $env:OS -eq 'Windows_NT'
if (-not $Yes) {
  $answer = Read-Host 'Remove Guitar Lab shortcuts, engine, studio build and the downloaded model? (y/N)'
  if ($answer -notmatch '^(y|yes)$') { Write-Host 'Nothing was removed.'; exit 0 }
}
# Stop a running Guitar Lab first so its files can be deleted.
. (Join-Path $PSScriptRoot 'common.ps1')
if (Stop-GuitarLab) { Write-Host 'Stopped the running Guitar Lab.' }
if ($OnWindows) {
  foreach ($place in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))) {
    Remove-Item -LiteralPath (Join-Path $place 'Guitar Lab.lnk') -ErrorAction SilentlyContinue
  }
}
foreach ($item in @('.venv', 'node_modules', 'dist', '.cache')) {
  $path = Join-Path $Root $item
  if (Test-Path $path) { Remove-Item -LiteralPath $path -Recurse -Force; Write-Host "Removed $item" }
}
Write-Host 'Guitar Lab has been removed. You can delete the folder too if you like.' -ForegroundColor Green
