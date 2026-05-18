# Jarves — unified launcher
# Usage: .\start.ps1           (core + UI)
#        .\start.ps1 -CoreOnly (core only, no UI)
#        .\start.ps1 -Voice    (core + voice PTT mode)

param(
    [switch]$CoreOnly,
    [switch]$Voice,
    [string]$Mode = "ptt"
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

# ── check venv ────────────────────────────────────────────────────────────────
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "[ERROR] .venv not found. Run setup first:" -ForegroundColor Red
    Write-Host "   py -3.12 -m venv .venv" -ForegroundColor Yellow
    Write-Host "   .\.venv\Scripts\python.exe -m pip install -r requirements.txt" -ForegroundColor Yellow
    exit 1
}

# ── check .env ────────────────────────────────────────────────────────────────
$env_file = Join-Path $root ".env"
if (-not (Test-Path $env_file)) {
    Copy-Item (Join-Path $root ".env.example") $env_file
    Write-Host "[WARN] .env created from .env.example — fill in ANTHROPIC_API_KEY and TELEGRAM keys." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "  ██╗ █████╗ ██████╗ ██╗   ██╗███████╗███████╗" -ForegroundColor Cyan
Write-Host "  ██║██╔══██╗██╔══██╗██║   ██║██╔════╝██╔════╝" -ForegroundColor Cyan
Write-Host "  ██║███████║██████╔╝██║   ██║█████╗  ███████╗" -ForegroundColor Cyan
Write-Host "  ██║██╔══██║██╔══██╗╚██╗ ██╔╝██╔══╝  ╚════██║" -ForegroundColor Cyan
Write-Host "  ██║██║  ██║██║  ██║ ╚████╔╝ ███████╗███████║" -ForegroundColor Cyan
Write-Host "  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚══════╝╚══════╝" -ForegroundColor Cyan
Write-Host ""

# ── start core ────────────────────────────────────────────────────────────────
Write-Host "[1/3] Starting Jarves core (http://127.0.0.1:8765)..." -ForegroundColor Green
$core = Start-Process -FilePath $python `
    -ArgumentList "-m", "core.api.main" `
    -WorkingDirectory $root `
    -PassThru -NoNewWindow

# wait until core is ready
$ready = $false
for ($i = 0; $i -lt 20; $i++) {
    Start-Sleep -Milliseconds 500
    try {
        $null = Invoke-WebRequest "http://127.0.0.1:8765/health" -UseBasicParsing -TimeoutSec 1
        $ready = $true
        break
    } catch {}
}

if (-not $ready) {
    Write-Host "[WARN] Core did not respond in 10s — it may still be starting." -ForegroundColor Yellow
} else {
    Write-Host "       Core online." -ForegroundColor Green
}

# ── voice mode ────────────────────────────────────────────────────────────────
if ($Voice) {
    Write-Host "[2/3] Starting voice pipeline (mode=$Mode)..." -ForegroundColor Green
    $voiceProc = Start-Process -FilePath $python `
        -ArgumentList "-m", "core.voice.run", "--mode", $Mode `
        -WorkingDirectory $root `
        -PassThru -NoNewWindow
    Write-Host "       Voice active. Say 'hello' to test." -ForegroundColor Green
}

# ── desktop UI ────────────────────────────────────────────────────────────────
if (-not $CoreOnly) {
    $electronExe = Join-Path $root "desktop\node_modules\.bin\electron.cmd"
    $distMain    = Join-Path $root "desktop\dist-electron\main.js"

    if ((Test-Path $electronExe) -and (Test-Path $distMain)) {
        Write-Host "[3/3] Launching Jarves UI..." -ForegroundColor Green
        Start-Process -FilePath $electronExe `
            -ArgumentList $distMain `
            -WorkingDirectory (Join-Path $root "desktop") `
            -NoNewWindow
    } else {
        Write-Host "[3/3] UI not built yet. Building now..." -ForegroundColor Yellow
        Push-Location (Join-Path $root "desktop")
        npm run build 2>&1 | Out-Null
        Pop-Location
        Start-Process -FilePath $electronExe `
            -ArgumentList $distMain `
            -WorkingDirectory (Join-Path $root "desktop") `
            -NoNewWindow
    }
    Write-Host "       UI window should appear." -ForegroundColor Green
}

Write-Host ""
Write-Host "  Jarves is running. Press Ctrl+C to stop the core." -ForegroundColor Cyan
Write-Host "  REST:  http://127.0.0.1:8765" -ForegroundColor DarkCyan
Write-Host "  WS:    ws://127.0.0.1:8765/ws" -ForegroundColor DarkCyan
Write-Host ""

# keep script alive so Ctrl+C kills the core process
try {
    Wait-Process -Id $core.Id
} catch {
    $core | Stop-Process -Force -ErrorAction SilentlyContinue
    if ($Voice -and $voiceProc) { $voiceProc | Stop-Process -Force -ErrorAction SilentlyContinue }
}
