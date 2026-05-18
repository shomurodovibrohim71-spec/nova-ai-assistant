Dim objShell, strDir, strPS, strCmd

strDir = "C:\Users\user\Desktop\AI assistant project"
strPS  = strDir & "\nova_watchdog.ps1"

Set objShell = CreateObject("WScript.Shell")
objShell.CurrentDirectory = strDir

' Launch watchdog via PowerShell, fully hidden — no window ever appears
strCmd = "powershell.exe -WindowStyle Hidden -NoProfile -ExecutionPolicy Bypass -File """ & strPS & """"

objShell.Run strCmd, 0, False
Set objShell = Nothing
