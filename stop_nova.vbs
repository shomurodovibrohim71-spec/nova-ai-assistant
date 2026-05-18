Dim objShell
Set objShell = CreateObject("WScript.Shell")
' Kill all python processes running Nova
objShell.Run "taskkill /F /FI ""IMAGENAME eq python.exe"" /T", 0, True
Set objShell = Nothing
