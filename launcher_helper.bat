@echo off
cd /d "%~dp0"
set /p TARGET=<"data\launch_target.txt"
echo [%DATE% %TIME%] TARGET=%TARGET% >> "data\launcher.log" 2>&1
if "%TARGET%"=="" exit /b 1

powershell -NonInteractive -WindowStyle Hidden -Command ^
  "Start-Process -FilePath '%TARGET%' -WorkingDirectory (Split-Path '%TARGET%')" ^
  >> "data\launcher.log" 2>&1
echo [%DATE% %TIME%] done, err=%ERRORLEVEL% >> "data\launcher.log"

