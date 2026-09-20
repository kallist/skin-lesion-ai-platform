@echo off
rem ===========================================================================
rem  SETUP.bat - first-time configuration.  Run this ONCE per machine.
rem
rem  Creates the Python virtual environment, installs backend/frontend
rem  dependencies, creates backend\.env with random secrets, checks the model.
rem  It never installs system software, never overwrites an existing .env and
rem  never resets the database.
rem
rem  Thin wrapper around scripts\setup.ps1.
rem ===========================================================================
setlocal enableextensions
chcp 65001 >nul 2>&1

set "REPO_ROOT=%~dp0"
set "SETUP_PS=%REPO_ROOT%scripts\setup.ps1"

if not exist "%SETUP_PS%" (
    echo [ERROR] scripts\setup.ps1 was not found next to this file.
    echo         Expected: "%SETUP_PS%"
    pause
    exit /b 1
)

title Skin Lesion AI Platform - SETUP

"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" ^
    -NoProfile -NoLogo -ExecutionPolicy Bypass -File "%SETUP_PS%" %*
set "RC=%ERRORLEVEL%"

if not "%RC%"=="0" (
    echo.
    echo [ERROR] SETUP failed with exit code %RC%. Read the messages above.
    pause
)

endlocal & exit /b %RC%
