@echo off
cd /d "%~dp0"
if exist "%LOCALAPPDATA%\Python\bin\python.exe" (
  "%LOCALAPPDATA%\Python\bin\python.exe" server.py
) else (
  py -3 server.py
)
if errorlevel 1 (
  echo FINN did not start. Install Python 3.9 or newer, then run this file again.
  pause
)
