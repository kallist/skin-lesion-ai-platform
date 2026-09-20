@echo off
rem ===========================================================================
rem  STOP.bat - shut down ONLY the backend/frontend started by START.bat.
rem
rem  Thin wrapper around scripts\stop.ps1 (PID-verified process trees only).
rem ===========================================================================
setlocal enableextensions
chcp 65001 >nul 2>&1

set "REPO_ROOT=%~dp0"
set "STOP_PS=%REPO_ROOT%scripts\stop.ps1"

if not exist "%STOP_PS%" (
    echo [ERROR] scripts\stop.ps1 was not found next to this file.
    pause
    exit /b 1
)

title Skin Lesion AI Platform - STOP

"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" ^
    -NoProfile -NoLogo -ExecutionPolicy Bypass -File "%STOP_PS%" %*
set "RC=%ERRORLEVEL%"

if not "%RC%"=="0" (
    echo.
    echo [ERROR] STOP reported exit code %RC%. See logs\launcher.log
    pause
)

endlocal & exit /b %RC%
