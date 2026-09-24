@echo off
setlocal enabledelayedexpansion

set "PORT=8009"

echo ============================================================
echo  NH_HESDER_3 - Kill service PIDs
echo ============================================================
echo.

echo --- Attempting to kill PID(s) listening on port %PORT% ---
set "PIDS="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":%PORT% .*LISTENING"') do (
    set "PIDS=!PIDS! %%P"
)

if not defined PIDS (
    echo   (none - port %PORT% is free)
) else (
    for %%P in (%PIDS%) do (
        echo   Killing PID %%P ...
        taskkill /PID %%P /F >nul 2>&1
    )
)

echo.
echo --- Verifying ---
set "STILL_ALIVE="
for %%P in (%PIDS%) do (
    tasklist /FI "PID eq %%P" 2>nul | findstr /R "^python.exe" >nul
    if not errorlevel 1 (
        echo   STILL ALIVE: PID %%P  -^>  run elevated: taskkill /PID %%P /F
        set "STILL_ALIVE=1"
    ) else (
        echo   Killed: PID %%P
    )
)

if not defined PIDS (
    echo   (nothing to verify)
) else (
    if not defined STILL_ALIVE echo   All target PID(s) killed successfully.
)

echo.
echo ============================================================
pause
