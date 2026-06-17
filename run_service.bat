@echo off
setlocal

REM Run from this BAT file directory.
cd /d "%~dp0"

set "PYTHON_EXE=C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe"
set "PORT=8009"
set "LOG_DIR=%~dp0logs"
set "CONSOLE_LOG=%LOG_DIR%\service_console.log"

if not exist "%PYTHON_EXE%" (
  echo ERROR: Python interpreter not found:
  echo %PYTHON_EXE%
  exit /b 1
)

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":%PORT% .*LISTENING"') do set "EXISTING_PID=%%P"
if defined EXISTING_PID (
  echo Service already appears to be running on port %PORT% with PID %EXISTING_PID%.
  exit /b 0
)

start "NH_HESDER_API" /B "%PYTHON_EXE%" -m uvicorn app:app --host 0.0.0.0 --port %PORT% >> "%CONSOLE_LOG%" 2>&1

timeout /t 2 /nobreak >nul

set "NEW_PID="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":%PORT% .*LISTENING"') do set "NEW_PID=%%P"

if not defined NEW_PID (
  echo ERROR: Service did not start on port %PORT%.
  echo Check log file: %CONSOLE_LOG%
  exit /b 1
)

echo Service started on port %PORT% with PID %NEW_PID%.
echo Console output is being written to %CONSOLE_LOG%
exit /b 0
