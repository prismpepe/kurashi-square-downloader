@echo off
cd /d "%~dp0"
if not exist "runtime\pythonw.exe" (
 echo Run setup.cmd first.
 pause
 exit /b 1
)
start "" "runtime\pythonw.exe" "launcher.py"
