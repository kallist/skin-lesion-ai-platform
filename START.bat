@echo off
rem ===========================================================================
rem  START.bat - double click this file to launch the Skin Lesion AI Platform
rem              (backend + frontend + browser).
rem
rem  Thin wrapper: all logic lives in scripts\start.ps1.
rem  * resolves its own location, so the project can live anywhere
rem    (spaces and non-ASCII characters in the path are supported)
rem  * bypasses the execution policy for this process only
rem  * never needs administrator rights and never changes system settings
rem ===========================================================================
setlocal enableextensions
chcp 65001 >nul 2>&1

set "REPO_ROOT=%~dp0"
set "START_PS=%REPO_ROOT%scripts\start.ps1"

if not exist "%START_PS%" (
    echo [ERROR] scripts\start.ps1 was not found next to this file.
    echo         Expected: "%START_PS%"
    echo         The project folder looks incomplete.
    pause
    exit /b 1
)

title Skin Lesion AI Platform - START

"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" ^
    -NoProfile -NoLogo -ExecutionPolicy Bypass -File "%START_PS%" %*
set "RC=%ERRORLEVEL%"

if not "%RC%"=="0" (
    echo.
    echo [ERROR] Startup failed with exit code %RC%.
    echo         Check the messages above and the logs\ folder.
    echo         If the dependencies are missing, run SETUP.bat first.
    pause
)

endlocal & exit /b %RC%
