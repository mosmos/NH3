@echo off
setlocal enabledelayedexpansion

REM Run from this BAT file directory.
cd /d "%~dp0"

set "PYTHON_EXE=C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe"
set "PORT=8009"
set "LOG_DIR=%~dp0logs"
set "CONSOLE_LOG=%LOG_DIR%\service_console.log"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

echo ============================================================
echo  NH_HESDER_3 - Restart Service
echo ============================================================
echo.

echo --- Stopping any process listening on port %PORT% ---
set "OLD_PID="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":%PORT% .*LISTENING"') do set "OLD_PID=%%P"

if defined OLD_PID (
  echo Found process %OLD_PID% listening on port %PORT%. Killing it...
  taskkill /PID %OLD_PID% /T /F >nul 2>&1
  if errorlevel 1 (
    echo WARNING: Failed to stop process %OLD_PID%.
  ) else (
    echo Process %OLD_PID% stopped.
  )
  timeout /t 2 /nobreak >nul
) else (
  echo No process currently listening on port %PORT%.
)

echo.
echo --- Starting service ---
if not exist "%PYTHON_EXE%" (
  echo ERROR: Python interpreter not found:
  echo %PYTHON_EXE%
  goto :end
)

start "NH_HESDER_API" /B "%PYTHON_EXE%" -m uvicorn app:app --host 0.0.0.0 --port %PORT% >> "%CONSOLE_LOG%" 2>&1

timeout /t 2 /nobreak >nul

set "NEW_PID="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":%PORT% .*LISTENING"') do set "NEW_PID=%%P"

if not defined NEW_PID (
  echo ERROR: Service did not start on port %PORT%.
  echo Check log file: %CONSOLE_LOG%
) else (
  echo Service started on port %PORT% with PID %NEW_PID%.
  echo Console output is being written to %CONSOLE_LOG%
)

echo.
echo --- Current python.exe processes ---
tasklist /FI "IMAGENAME eq python.exe" /V

echo.
echo --- Current listeners on port %PORT% ---
netstat -ano | findstr /R /C:":%PORT% .*LISTENING"

:end
echo.
echo ============================================================
pause
