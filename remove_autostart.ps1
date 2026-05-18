# Jarves ni Windows startupdan o'chirish
$taskName = "JarvesAI"

Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

# Also remove old Startup folder shortcut if exists
$shortcut = Join-Path ([Environment]::GetFolderPath("Startup")) "Jarves.lnk"
if (Test-Path $shortcut) { Remove-Item $shortcut -Force }

Write-Host "Jarves autostart o'chirildi." -ForegroundColor Yellow
