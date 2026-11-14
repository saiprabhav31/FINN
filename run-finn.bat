@echo off
cd /d "%~dp0"
if exist "%LOCALAPPDATA%\Python\bin\python.exe" (
  "%LOCALAPPDATA%\Python\bin\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
  if errorlevel 1 goto install_failed
  "%LOCALAPPDATA%\Python\bin\python.exe" server.py
) else (
  py -3 -m pip install --disable-pip-version-check -r requirements.txt
  if errorlevel 1 goto install_failed
  py -3 server.py
)
if errorlevel 1 (
  echo FINN did not start. Install Python 3.9 or newer, then run this file again.
  pause
)
goto end
:install_failed
echo FINN could not install its document-reading dependency. Install pypdf with: py -3 -m pip install -r requirements.txt
pause
:end
