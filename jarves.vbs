' Jarves background launcher.
' Double-click to start Jarves silently (no console window).

Dim fso, dir, pythonw, logOut, logErr, ps, shell
Set fso   = CreateObject("Scripting.FileSystemObject")
dir       = fso.GetParentFolderName(fso.GetAbsolutePathName(WScript.ScriptFullName))
pythonw   = dir & "\.venv\Scripts\pythonw.exe"
logOut    = dir & "\data\jarves.log"
logErr    = dir & "\data\jarves_err.log"

If Not fso.FolderExists(dir & "\data") Then fso.CreateFolder(dir & "\data")

ps = "powershell.exe -NonInteractive -WindowStyle Hidden -Command " & _
     """Start-Process -FilePath '" & pythonw & "'" & _
     " -ArgumentList '-m','core.api.main'" & _
     " -WorkingDirectory '" & dir & "'" & _
     " -WindowStyle Hidden" & _
     " -RedirectStandardOutput '" & logOut & "'" & _
     " -RedirectStandardError '" & logErr & "'"""

Set shell = CreateObject("WScript.Shell")
shell.Run ps, 0, False
