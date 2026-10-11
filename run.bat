@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title AI Upscale YouTube Downloader

set "VENV_PY=%~dp0.venv\Scripts\python.exe"

if not exist "%VENV_PY%" (
  call :find_python
  if not defined PY (
    echo Python was not found. Install Python 3.11+ from python.org and try again.
    echo Disable the Windows "App execution aliases" for python.exe if those are on.
    pause
    exit /b 1
  )
  echo Creating virtual environment with:
  echo   %PY%
  "%PY%" -m venv .venv
  if errorlevel 1 (
    echo Could not create .venv
    pause
    exit /b 1
  )
)

for /d %%D in ("%LOCALAPPDATA%\Microsoft\WinGet\Packages\DenoLand.Deno*") do (
  if exist "%%~D\deno.exe" set "PATH=%%~D;%PATH%"
)
if exist "%USERPROFILE%\.deno\bin\deno.exe" set "PATH=%USERPROFILE%\.deno\bin;%PATH%"

echo Checking packages...
"%VENV_PY%" -m pip install -q --upgrade pip
"%VENV_PY%" -m pip install -q -r "%~dp0requirements.txt"
if errorlevel 1 (
  echo Package install failed.
  pause
  exit /b 1
)

"%VENV_PY%" -c "import socket; s=socket.socket(); s.settimeout(0.4); raise SystemExit(0 if s.connect_ex(('127.0.0.1',8501))==0 else 1)" 2>nul
if %errorlevel%==0 (
  echo App is already running. Opening http://127.0.0.1:8501
  start "" "http://127.0.0.1:8501"
  exit /b 0
)

echo Starting http://127.0.0.1:8501
"%VENV_PY%" -m streamlit run "%~dp0app.py" --server.port 8501 --server.headless false
if errorlevel 1 (
  echo The app failed to start.
  pause
  exit /b 1
)
exit /b 0

:find_python
set "PY="
for %%P in (
  "%LocalAppData%\Programs\Python\Python313\python.exe"
  "%LocalAppData%\Programs\Python\Python312\python.exe"
  "%LocalAppData%\Programs\Python\Python311\python.exe"
  "%LocalAppData%\Programs\Python\Python310\python.exe"
  "C:\Python313\python.exe"
  "C:\Python312\python.exe"
  "C:\Python311\python.exe"
  "C:\Python310\python.exe"
) do if not defined PY if exist "%%~P" set "PY=%%~P"
if defined PY goto :eof
if exist "%SystemRoot%\py.exe" (
  "%SystemRoot%\py.exe" -3 -c "import sys; print(sys.executable)" >"%TEMP%\ydl_py.txt" 2>nul
  if exist "%TEMP%\ydl_py.txt" set /p PY=<"%TEMP%\ydl_py.txt"
)
if defined PY echo %PY% | find /i "WindowsApps" >nul && set "PY="
goto :eof
