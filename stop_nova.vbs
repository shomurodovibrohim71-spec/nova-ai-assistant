Dim objShell
Set objShell = CreateObject("WScript.Shell")

' Stop watchdog (PowerShell running nova_watchdog.ps1)
objShell.Run "powershell.exe -WindowStyle Hidden -NoProfile -Command ""Get-Process powershell | Where-Object {$_.CommandLine -like '*nova_watchdog*'} | Stop-Process -Force""", 0, True

' Stop Nova (python process)
objShell.Run "taskkill /F /FI ""IMAGENAME eq python.exe"" /T", 0, True

Set objShell = Nothing
