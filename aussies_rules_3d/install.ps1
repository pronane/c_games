# Aussie Rules 3D — installer for Windows (PowerShell).
#
#   .\install.ps1           full setup (checks Node, installs dependencies)
#   .\install.ps1 -Check    say what is already there, change nothing
#
# If Node 20+ is missing, a private copy is downloaded into %USERPROFILE%\.aussie-rules-3d\node.
param([switch]$Check)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

function Say($msg) { Write-Host $msg }

$minMajor = 20
$nodeDir = Join-Path $env:USERPROFILE ".aussie-rules-3d\node"

function Get-NodeMajor {
  try {
    $v = node -e 'process.stdout.write(String(process.versions.node.split(".")[0]))' 2>$null
    return [int]$v
  } catch {
    return 0
  }
}

if ((Get-NodeMajor) -lt $minMajor) {
  if (Test-Path (Join-Path $nodeDir "node.exe")) {
    $env:Path = "$nodeDir;$env:Path"
  }
}

if ((Get-NodeMajor) -lt $minMajor) {
  Say "-> downloading a private Node.js runtime into $nodeDir (one-time, ~30 MB)"
  New-Item -ItemType Directory -Force -Path $nodeDir | Out-Null
  $arch = if ($env:PROCESSOR_ARCHITECTURE -eq "ARM64") { "arm64" } else { "x64" }
  $version = "v22.11.0"
  try {
    $index = Invoke-RestMethod "https://nodejs.org/dist/index.json"
    $version = $index[0].version
  } catch { }
  $zip = Join-Path $env:TEMP "node-$version-win-$arch.zip"
  Invoke-WebRequest "https://nodejs.org/dist/$version/node-$version-win-$arch.zip" -OutFile $zip
  Expand-Archive $zip -DestinationPath $nodeDir -Force
  Get-ChildItem (Join-Path $nodeDir "node-$version-win-$arch") -Recurse -File | ForEach-Object {
    Move-Item $_.FullName (Join-Path $nodeDir $_.Name) -Force
  }
  Remove-Item $zip
  $env:Path = "$nodeDir;$env:Path"
}

if ((Get-NodeMajor) -lt $minMajor) {
  Write-Error "Node 20+ is required. Install it from https://nodejs.org and re-run."
}

if ($Check) {
  node scripts/install.mjs --check
} else {
  node scripts/install.mjs
}
