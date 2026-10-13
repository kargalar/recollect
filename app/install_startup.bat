@echo off
set "SCRIPT_DIR=%~dp0"
set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT_PATH=%STARTUP_FOLDER%\Recollect.lnk"
set "TARGET_PATH=%SCRIPT_DIR%venv\Scripts\pythonw.exe"
set "WORKING_DIR=%SCRIPT_DIR%"

echo Creating startup shortcut...
powershell -Command "$wshell = New-Object -ComObject WScript.Shell; $shortcut = $wshell.CreateShortcut('%SHORTCUT_PATH%'); $shortcut.TargetPath = '%TARGET_PATH%'; $shortcut.Arguments = 'tray.py'; $shortcut.WorkingDirectory = '%WORKING_DIR%'; $shortcut.WindowStyle = 7; $shortcut.Save()"

echo Startup shortcut created at: %SHORTCUT_PATH%
echo The application will now start automatically in the background when you log in.
pause
