Option Explicit

Dim shell, fileSystem, projectDirectory, pythonwPath, command

Set shell = CreateObject("WScript.Shell")
Set fileSystem = CreateObject("Scripting.FileSystemObject")

projectDirectory = fileSystem.GetParentFolderName(WScript.ScriptFullName)
pythonwPath = projectDirectory & "\.venv\Scripts\pythonw.exe"

If Not fileSystem.FileExists(pythonwPath) Then
    pythonwPath = "pythonw.exe"
End If

command = Chr(34) & pythonwPath & Chr(34) & " " & _
    Chr(34) & projectDirectory & "\indicator.py" & Chr(34)

shell.CurrentDirectory = projectDirectory
shell.Run command, 0, False
