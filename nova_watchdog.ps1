# Nova AI Watchdog — monitors Nova and auto-restarts on crash
# Runs silently in background. Started by start_nova.vbs at login.

$dir    = "C:\Users\user\Desktop\AI assistant project"
$python = "$dir\.venv\Scripts\python.exe"
$logDir = "$dir\logs"
$log    = "$logDir\watchdog.log"

if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }

function Write-Log($msg) {
    $ts = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    Add-Content -Path $log -Value "[$ts] $msg" -Encoding UTF8
}

function Nova-Running {
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:8765/health" `
             -UseBasicParsing -TimeoutSec 4
        return ($r.StatusCode -eq 200)
    } catch { return $false }
}

function Start-Nova {
    # Kill any stale python processes first
    Get-Process -Name "python" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like "*core.api.main*" } |
        Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1

    $proc = Start-Process `
        -FilePath $python `
        -ArgumentList "-m", "core.api.main" `
        -WorkingDirectory $dir `
        -WindowStyle Hidden `
        -PassThru
    Write-Log "Nova started (PID $($proc.Id))"
    return $proc
}

Write-Log "Watchdog started"

# Initial launch
$nova = Start-Nova
Start-Sleep -Seconds 15   # wait for first startup

$checkInterval = 30       # seconds between health checks
$restartDelay  = 12       # seconds to wait after restart before checking

while ($true) {
    Start-Sleep -Seconds $checkInterval

    if (-not (Nova-Running)) {
        Write-Log "Nova not responding - restarting..."
        $nova = Start-Nova
        Start-Sleep -Seconds $restartDelay
    }

    # Keep log file under 500 KB
    try {
        if ((Get-Item $log).Length -gt 500KB) {
            $lines = Get-Content $log
            $lines | Select-Object -Last 200 | Set-Content $log -Encoding UTF8
        }
    } catch {}
}
