# Stops the frontend (5173), backend (8000) and the 27020 MongoDB started by start-all.ps1.
# Usage:  powershell -ExecutionPolicy Bypass -File .\stop-all.ps1          (leaves MongoDB running)
#         powershell -ExecutionPolicy Bypass -File .\stop-all.ps1 -Mongo   (also stops MongoDB 27020)
param([switch]$Mongo)
$ports = @(5173, 8000); if ($Mongo) { $ports += 27020 }
foreach ($port in $ports) {
    $pids = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
    if (-not $pids) { "$port not running"; continue }
    foreach ($id in $pids) { Stop-Process -Id $id -Force; "$port stopped (PID $id)" }
}
