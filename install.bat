@echo off
REM install.bat — AGORIS einfache Installation unter Windows (cmd.exe)
REM 
REM Dieses Skript umgeht die Windows-SmartScreen/Unverified Publisher-Warnung
REM durch Aufruf mit bypassed ExecutionPolicy über PowerShell

setlocal

REM Überprüfe ob Python/PowerShell verfügbar ist
powershell -ExecutionPolicy Bypass -NoProfile -Command "Write-Host 'Starte AGORIS Installer...'" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Fehler: PowerShell ist nicht verfügbar.
    pause
    exit /b 1
)

REM Führe das PowerShell-Install-Skript aus
powershell -ExecutionPolicy Bypass -NoProfile -File "%~dp0install.ps1" %*

exit /b %ERRORLEVEL%
