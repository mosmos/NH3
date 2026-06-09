@echo off
setlocal

REM Run from this BAT file's directory so relative imports/files work.
cd /d "%~dp0"

set "PYTHON_EXE=C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe"

if not exist "%PYTHON_EXE%" (
  echo ERROR: Python interpreter not found:
  echo %PYTHON_EXE%
  exit /b 1
)

"%PYTHON_EXE%" "%~dp0run_job.py"
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
  echo ERROR: run_job.py failed with exit code %EXIT_CODE%
  exit /b %EXIT_CODE%
)

echo SUCCESS: run_job.py completed.
exit /b 0
