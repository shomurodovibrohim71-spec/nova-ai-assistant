# Jarves — first-time setup
# Run once: .\setup.ps1

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

Write-Host "== Jarves Setup ==" -ForegroundColor Cyan

# ── Python venv ───────────────────────────────────────────────────────────────
if (-not (Test-Path "$root\.venv")) {
    Write-Host "[1/5] Creating Python virtual environment..." -ForegroundColor Green
    py -3.12 -m venv "$root\.venv"
} else {
    Write-Host "[1/5] venv already exists." -ForegroundColor DarkGray
}

$python = "$root\.venv\Scripts\python.exe"

# ── Python deps ───────────────────────────────────────────────────────────────
Write-Host "[2/5] Installing Python dependencies..." -ForegroundColor Green
& $python -m pip install --upgrade pip -q
& $python -m pip install -r "$root\requirements.txt" -q
& $python -m pip install -r "$root\requirements-voice.txt" -q

# ── .env ──────────────────────────────────────────────────────────────────────
if (-not (Test-Path "$root\.env")) {
    Write-Host "[3/5] Creating .env from example..." -ForegroundColor Green
    Copy-Item "$root\.env.example" "$root\.env"
    Write-Host "      IMPORTANT: Open .env and fill in your keys!" -ForegroundColor Yellow
} else {
    Write-Host "[3/5] .env already exists." -ForegroundColor DarkGray
}

# ── Node / desktop ────────────────────────────────────────────────────────────
Write-Host "[4/5] Installing desktop UI dependencies..." -ForegroundColor Green
Push-Location "$root\desktop"
npm install --prefer-offline 2>&1 | Out-Null

Write-Host "[5/5] Building desktop UI..." -ForegroundColor Green
npm run build 2>&1 | Out-Null
Pop-Location

# ── smoke test ────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "Running smoke test..." -ForegroundColor Green
& $python "$root\scripts\smoke_test.py" 2>&1 | Select-String -Pattern "^>" | ForEach-Object { Write-Host "  $_" }

Write-Host ""
Write-Host "== Setup complete! ==" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor White
Write-Host "  1. Open .env and set ANTHROPIC_API_KEY  (https://console.anthropic.com/)" -ForegroundColor Yellow
Write-Host "  2. Set TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID  (optional)" -ForegroundColor Yellow
Write-Host "  3. Run:  .\start.ps1              (core + UI)" -ForegroundColor Green
Write-Host "     Run:  .\start.ps1 -Voice       (core + UI + voice push-to-talk)" -ForegroundColor Green
Write-Host "     Run:  .\start.ps1 -CoreOnly    (API server only)" -ForegroundColor Green
