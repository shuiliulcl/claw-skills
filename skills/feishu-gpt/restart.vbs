Dim shell, dir
Set shell = CreateObject("WScript.Shell")
dir = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\"))
shell.Run "cmd.exe /k """ & dir & "restart.bat""", 1, False
Set shell = Nothing
