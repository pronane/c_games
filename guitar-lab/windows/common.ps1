# Shared by install.ps1 (when updating) and uninstall.ps1.

function Stop-GuitarLab {
  # Ask any running Guitar Lab on this computer to stop, then wait for it to go.
  $stopped = $false
  foreach ($p in 8000..8020) {
    try {
      $h = Invoke-RestMethod -Uri "http://127.0.0.1:$p/api/health" -TimeoutSec 1
    } catch { continue }
    if ($h.service -ne 'Fretwork Python engine') { continue }
    try {
      Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:$p/api/shutdown" -Headers @{ 'X-Fretwork-Client' = 'studio' } -TimeoutSec 3 | Out-Null
    } catch {
      Write-Host "    Guitar Lab on port $p did not accept the stop request; close its window, then try again." -ForegroundColor Yellow
      continue
    }
    for ($i = 0; $i -lt 40; $i++) {
      Start-Sleep -Milliseconds 250
      try { Invoke-RestMethod -Uri "http://127.0.0.1:$p/api/health" -TimeoutSec 1 | Out-Null } catch { $stopped = $true; break }
    }
  }
  return $stopped
}
