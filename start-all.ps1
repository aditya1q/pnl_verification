# Starts MongoDB (27020), backend (8000) and frontend (5173) in the background.
# They keep running after this window closes. Logs: backend\data\logs\
# Usage:  powershell -ExecutionPolicy Bypass -File .\start-all.ps1
$ErrorActionPreference = "Stop"
$root  = $PSScriptRoot
$logs  = Join-Path $root "backend\data\logs"
$mongo = Join-Path $root "backend\data\mongo27020"
New-Item -ItemType Directory -Force $logs, "$mongo\db" | Out-Null

function Test-Port($port) { [bool](Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue) }

# 1. MongoDB on 27020
if (Test-Port 27020) { "MongoDB  27020 already running" } else {
    Start-Process "C:\Program Files\MongoDB\Server\8.0\bin\mongod.exe" -WindowStyle Hidden -ArgumentList `
        "--port 27020 --bind_ip 127.0.0.1 --dbpath `"$mongo\db`" --logpath `"$mongo\mongod.log`" --logappend"
    "MongoDB  27020 started"
}

# 2. Backend on 8000
if (Test-Port 8000) { "Backend  8000  already running" } else {
    Start-Process "$root\backend\.venv\Scripts\python.exe" -WorkingDirectory "$root\backend" -WindowStyle Hidden `
        -ArgumentList "-m uvicorn app.main:app --host 0.0.0.0 --port 8000" `
        -RedirectStandardOutput "$logs\backend.out.log" -RedirectStandardError "$logs\backend.log"
    "Backend  8000  started"
}

# 3. Frontend on 5173 (proxies /api to the backend on 8000)
if (Test-Port 5173) { "Frontend 5173  already running" } else {
    $env:API_URL = "http://127.0.0.1:8000"
    Start-Process "cmd.exe" -WorkingDirectory "$root\frontend" -WindowStyle Hidden `
        -ArgumentList "/c npm run dev -- --port 5173 > `"$logs\frontend.log`" 2>&1"
    "Frontend 5173  started"
}

Start-Sleep 6
foreach ($p in 27020, 8000, 5173) { "{0,-6} {1}" -f $p, $(if (Test-Port $p) { "LISTENING" } else { "NOT UP - check $logs" }) }
$ip = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } | Select-Object -First 1).IPAddress
"Open: http://${ip}:5173   (on this machine: http://localhost:5173)"
