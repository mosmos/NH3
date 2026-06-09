@echo off
setlocal

cd /d "%~dp0"

set "PORT=809"

set "PID="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":%PORT% .*LISTENING"') do set "PID=%%P"

if not defined PID (
  echo No process is listening on port %PORT%. Service may already be stopped.
  exit /b 0
)

taskkill /PID %PID% /T /F >nul 2>&1
if errorlevel 1 (
  echo ERROR: Failed to stop process %PID%.
  exit /b 1
)

echo Service stopped (PID %PID%).
exit /b 0
