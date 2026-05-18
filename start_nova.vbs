Dim objShell, strDir, strCmd

strDir = "C:\Users\user\Desktop\AI assistant project"

Set objShell = CreateObject("WScript.Shell")

' PowerShell bilan oynasiz ishga tushirish
strCmd = "powershell.exe -WindowStyle Hidden -NoProfile -Command " & _
         Chr(34) & "Set-Location '" & strDir & "'; " & _
         "& '" & strDir & "\.venv\Scripts\python.exe' -m core.api.main" & Chr(34)

objShell.Run strCmd, 0, False
Set objShell = Nothing
