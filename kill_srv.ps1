for ($i = 0; $i -lt 6; $i++) {
  $procs = Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and ($_.CommandLine -match 'mup-web|spawn_main|server:app|server\.py|multiprocessing') }
  if (-not $procs) { Write-Output "clean"; break }
  foreach ($p in $procs) { Write-Output ("kill PID=" + $p.ProcessId); taskkill /F /T /PID $p.ProcessId 2>$null | Out-Null }
  Start-Sleep -Milliseconds 700
}
Start-Sleep -Milliseconds 500
$left = Get-NetTCPConnection -LocalPort 8000 -State Listen -EA SilentlyContinue
if ($left) { Write-Output ("PORT 8000 still LISTEN by " + ($left.OwningProcess -join ',')) } else { Write-Output "PORT 8000 free" }
