' Stop Jarves background process silently.
Dim shell
Set shell = CreateObject("WScript.Shell")
shell.Run "taskkill /F /IM pythonw.exe", 0, True
