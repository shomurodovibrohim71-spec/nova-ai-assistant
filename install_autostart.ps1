param([switch]$Uninstall)

# Self-elevate to admin if not already
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    $args = if ($Uninstall) { "-Uninstall" } else { "" }
    Start-Process powershell -Verb RunAs -ArgumentList "-ExecutionPolicy Bypass -File `"$PSCommandPath`" $args" -Wait
    exit
}

$taskName         = "JarvesAI"
$launcherTaskName = "JarvesLauncher"
$projectDir = $PSScriptRoot
$python     = Join-Path $projectDir ".venv\Scripts\python.exe"   # python.exe (not pythonw) for reliability
$logFile    = Join-Path $projectDir "data\jarves.log"

New-Item -ItemType Directory -Force -Path (Join-Path $projectDir "data") | Out-Null

if ($Uninstall) {
    Stop-ScheduledTask  -TaskName $taskName         -ErrorAction SilentlyContinue
    Stop-ScheduledTask  -TaskName $launcherTaskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $taskName         -Confirm:$false -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $launcherTaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Jarves tasks ochildi." -ForegroundColor Yellow
    exit
}

if (-not (Test-Path $python)) {
    Write-Host "XATO: $python topilmadi. Avval setup.ps1 ni ishga tushiring." -ForegroundColor Red
    exit 1
}

# Use a .bat launcher — simplest, no quoting issues, pythonw output redirected inside bat
$batFile = Join-Path $projectDir "jarves_service.bat"
$action  = New-ScheduledTaskAction -Execute $batFile -WorkingDirectory $projectDir
$trigger   = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest
$settings  = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -StartWhenAvailable -MultipleInstances IgnoreNew

Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description "Jarves AI Assistant" -Force | Out-Null

# ── JarvesLauncher task ─────────────────────────────────────────────────────
# Triggered on-demand by Jarves (schtasks /run /tn JarvesLauncher).
# Runs as RunLevel Highest so it can open admin-required games without a UAC prompt.
$launcherBat      = Join-Path $projectDir "launcher_helper.bat"
$launcherAction   = New-ScheduledTaskAction -Execute $launcherBat -WorkingDirectory $projectDir
$launcherTrigger  = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME   # required placeholder; real runs are manual
$launcherPrincipal= New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest
$launcherSettings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 1) -StartWhenAvailable -MultipleInstances Queue

Unregister-ScheduledTask -TaskName $launcherTaskName -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName $launcherTaskName -Action $launcherAction -Trigger $launcherTrigger -Principal $launcherPrincipal -Settings $launcherSettings -Description "Jarves elevated app launcher" -Force | Out-Null

Write-Host ""
Write-Host "Jarves Task Scheduler ga ornatildi!" -ForegroundColor Green
Write-Host ""
Write-Host "  Windows ishga tushganda avtomatik boshlanadi" -ForegroundColor White
Write-Host "  Konsol oynasi koriinmaydi" -ForegroundColor White
Write-Host "  Admin huquqida ishlaydi (uyinlar UAC suramasdan ochiladi)" -ForegroundColor White
Write-Host "  Crash bolsa 1 daqiqada qayta boshlanadi" -ForegroundColor White
Write-Host ""
Write-Host "Boshqarish:" -ForegroundColor Cyan
Write-Host "  Ishga tushirish : Start-ScheduledTask -TaskName JarvesAI" -ForegroundColor Yellow
Write-Host "  Toxtatish       : Stop-ScheduledTask -TaskName JarvesAI" -ForegroundColor Yellow
Write-Host "  Ochirish        : .\install_autostart.ps1 -Uninstall" -ForegroundColor Yellow
Write-Host ""
