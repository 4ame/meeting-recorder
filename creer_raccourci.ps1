$pythonw = "D:\Utilitaires\Python\pythonw.exe"
$script  = "C:\Users\arnau\Documents\Projets perso\meeting-recorder\src\tray.py"
$workdir = "C:\Users\arnau\Documents\Projets perso\meeting-recorder"
$dest    = "$env:USERPROFILE\Desktop\Meeting Recorder.lnk"

$shell     = New-Object -ComObject WScript.Shell
$shortcut  = $shell.CreateShortcut($dest)
$shortcut.TargetPath       = $pythonw
$shortcut.Arguments        = "`"$script`""
$shortcut.WorkingDirectory = $workdir
$shortcut.IconLocation     = "C:\Users\arnau\Documents\Projets perso\meeting-recorder\icon.ico,0"
$shortcut.Description      = "Lancer Meeting Recorder"
$shortcut.Save()

Write-Host "Raccourci créé : $dest"
Write-Host "Tu peux maintenant l'épingler à la barre des tâches (clic droit → Épingler)"
