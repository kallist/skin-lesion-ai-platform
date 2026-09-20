@echo off
rem ===========================================================================
rem  STATUS.bat - show whether backend / frontend / model / database are healthy.
rem
rem  Thin wrapper around scripts\status.ps1 (read-only, nothing is changed).
rem ===========================================================================
setlocal enableextensions
chcp 65001 >nul 2>&1

set "REPO_ROOT=%~dp0"
set "STATUS_PS=%REPO_ROOT%scripts\status.ps1"

if not exist "%STATUS_PS%" (
    echo [ERROR] scripts\status.ps1 was not found next to this file.
    pause
    exit /b 1
)

title Skin Lesion AI Platform - STATUS

"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" ^
    -NoProfile -NoLogo -ExecutionPolicy Bypass -File "%STATUS_PS%" %*
set "RC=%ERRORLEVEL%"

if not "%RC%"=="0" (
    echo.
    echo [ERROR] STATUS reported exit code %RC%. See logs\launcher.log
    pause
)

endlocal & exit /b %RC%
