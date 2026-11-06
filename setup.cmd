@echo off
cd /d "%~dp0"
if not exist runtime\python.exe (
 echo Python 3.11 runtime is missing. Use the prepared application folder.
 pause
 exit /b 1
)
runtime\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
 pause
 exit /b 1
)
echo Setup complete. Run start.cmd.
pause
