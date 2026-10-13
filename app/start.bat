@echo off
cd /d "%~dp0"
echo Stopping existing Recollect processes from this folder...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$all = Get-CimInstance Win32_Process; " ^
  "$tray = $all | Where-Object { $_.Name -match '^pythonw?\.exe$' -and $_.CommandLine -match 'tray\.py' }; " ^
  "$queue = New-Object System.Collections.Generic.Queue[object]; " ^
  "$seen = New-Object 'System.Collections.Generic.HashSet[int]'; " ^
  "$tray | ForEach-Object { $queue.Enqueue($_) | Out-Null }; " ^
  "while ($queue.Count -gt 0) { " ^
  "  $proc = $queue.Dequeue(); " ^
  "  if (-not $seen.Add([int]$proc.ProcessId)) { continue } " ^
  "  $children = $all | Where-Object { $_.ParentProcessId -eq $proc.ProcessId }; " ^
  "  $children | ForEach-Object { $queue.Enqueue($_) | Out-Null }; " ^
  "} " ^
  "$seen | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }"
ping 127.0.0.1 -n 3 >nul
echo Starting Recollect for Windows with System Tray...
start "" ".\venv\Scripts\pythonw.exe" tray.py
echo Tray application started. Check the system tray for the icon.
