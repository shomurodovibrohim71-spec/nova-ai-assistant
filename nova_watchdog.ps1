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

function Kill-Port8765 {
    # Kill whatever process is holding port 8765 (no admin/CommandLine needed)
    try {
        $conn = Get-NetTCPConnection -LocalPort 8765 -ErrorAction SilentlyContinue
        if ($conn) {
            foreach ($c in $conn) {
                Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
            }
            Start-Sleep -Seconds 2
        }
    } catch {}
    # Also try killing all python.exe as fallback
    Get-Process -Name "python" -ErrorAction SilentlyContinue |
        Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}

function Port-Free {
    $conn = Get-NetTCPConnection -LocalPort 8765 -ErrorAction SilentlyContinue
    return ($null -eq $conn)
}

function Start-Nova {
    Kill-Port8765

    # Wait until port is actually free (up to 10s)
    $waited = 0
    while (-not (Port-Free) -and $waited -lt 10) {
        Start-Sleep -Seconds 1
        $waited++
    }
    if (-not (Port-Free)) {
        Write-Log "WARNING: port 8765 still busy after ${waited}s - forcing kill"
        Get-Process -Name "python" -ErrorAction SilentlyContinue |
            Stop-Process -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 3
    }

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
Start-Sleep -Seconds 18   # wait for first startup

$checkInterval = 30       # seconds between health checks
$restartDelay  = 15       # seconds to wait after restart before checking

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
