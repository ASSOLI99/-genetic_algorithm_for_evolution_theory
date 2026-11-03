@echo off
setlocal
title Evolution Lab
cd /d "%~dp0"

echo.
echo  ==========================================================
echo     Evolution Lab  -  one-click launcher (Windows)
echo  ==========================================================
echo.

rem --- Find Python 3.13+ (python on PATH, or the "py" launcher) ---
set "PY="
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 13) else 1)" >nul 2>&1 && set "PY=python"
if not defined PY (
    py -3.13 -c "import sys" >nul 2>&1 && set "PY=py -3.13"
)
if not defined PY (
    echo  [!] Python 3.13 or newer was not found.
    echo      Install it from https://www.python.org/downloads/
    echo      and tick "Add python.exe to PATH" during setup, then run this file again.
    echo.
    pause
    exit /b 1
)

rem --- Create the private environment the first time (PowerShell script reuses it) ---
if not exist ".venv\Scripts\python.exe" (
    echo  First run: creating a private Python environment in .venv ...
    %PY% -m venv .venv
    if errorlevel 1 (
        echo  [!] Could not create the environment.
        pause
        exit /b 1
    )
)

echo  Choose what to run:
echo.
echo    1^) Quick demo        - 4 scenarios x 2 replicates, about 1 minute  (recommended first)
echo    2^) Full comparison   - 144 scenarios x 8 replicates, several minutes
echo    3^) Isolated programs - each reproduction program alone
echo    4^) Invasion test     - rare facultative mutants among clones
echo.
set "CHOICE=1"
set /p "CHOICE=  Your choice [1]: "

set "PROFILE=smoke"
if "%CHOICE%"=="2" set "PROFILE=standard"
if "%CHOICE%"=="3" set "PROFILE=isolated"
if "%CHOICE%"=="4" set "PROFILE=invasion"

echo.
echo  Running profile: %PROFILE%
echo  (dependencies are installed and tests run automatically before the experiment)
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-Experiment.ps1" -Profile %PROFILE%
if errorlevel 1 (
    echo.
    echo  [!] The run stopped with an error. Read the message above.
    pause
    exit /b 1
)

echo.
echo  Done. The report REPORT.html was opened in your browser.
echo  All results are saved in the "runs" folder.
pause
