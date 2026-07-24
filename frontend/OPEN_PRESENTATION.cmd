@echo off
setlocal
cd /d "%~dp0"
title Smart Construction Presentation
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0presentation-server.ps1"
if errorlevel 1 (
  echo.
  echo The presentation server could not start.
  echo Keep this window open and review the message above.
  pause
)
endlocal
