@echo off
REM install.bat — AGORIS einfache Installation unter Windows (cmd.exe)
REM 
REM Dieses Skript umgeht die Windows-SmartScreen/Unverified Publisher-Warnung
REM durch Aufruf mit bypassed ExecutionPolicy über PowerShell

setlocal enabledelayedexpansion

REM Überprüfe ob PowerShell verfügbar ist
powershell -ExecutionPolicy Bypass -NoProfile -Command "Write-Host 'Starte AGORIS Installer...'" >nul 2>&1
if !ERRORLEVEL! NEQ 0 (
    echo Fehler: PowerShell ist nicht verfügbar.
    pause
    exit /b 1
)

REM Hilfe-Anfragen auf "help" abbilden: "-h", "--help" und "/?" würde
REM PowerShell als Parameter lesen und das Skript damit abbrechen.
set "AGORIS_ARGS=%*"
if /i "%~1"=="-h" set "AGORIS_ARGS=help"
if /i "%~1"=="--help" set "AGORIS_ARGS=help"
if /i "%~1"=="/?" set "AGORIS_ARGS=help"

REM Führe das PowerShell-Install-Skript aus
powershell -ExecutionPolicy Bypass -NoProfile -File "%~dp0install.ps1" !AGORIS_ARGS!

exit /b !ERRORLEVEL!
