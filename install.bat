@echo off
REM install.bat — AGORIS einfache Installation unter Windows (cmd.exe)
REM
REM Dieses Skript richtet alles ein, was AGORIS unter Windows braucht:
REM 1. Prüft ob Docker Desktop verfügbar ist
REM 2. Baut das Docker Image automatisch
REM 3. Startet AGORIS in Docker mit --privileged
REM
REM WICHTIG: Wenn Windows die Ausführung blockiert
REM ("Der Herausgeber kann nicht verifiziert werden"), dann:
REM
REM   * Rechtsklick auf die Datei → Eigenschaften → "Entsperren" anhaken
REM   * Oder: PowerShell als Administrator, dann:
REM     Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
REM   * Oder starte über: install.ps1 mit -ExecutionPolicy Bypass
REM
REM Oder ganz ohne Skript: docker-compose up

setlocal enabledelayedexpansion

echo.
echo  ============================================================
echo  AGORIS - Einfache Installation unter Windows (Docker Desktop)
echo  ============================================================
echo.

REM Prüfe ob Docker verfügbar ist
docker --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo FEHLER: Docker ist nicht installiert oder nicht im PATH.
    echo.
    echo So behebst du das:
    echo   1. Lade Docker Desktop für Windows herunter:
    echo      https://www.docker.com/products/docker-desktop
    echo   2. Installiere Docker Desktop und starte ggf. neu.
    echo   3. Aktiviere WSL2 als Backend (Docker Desktop → Settings → Resources → WSL Integration).
    echo.
    echo Ohne Docker: GitHub Codespaces (Browser, keine Installation):
    echo      https://github.com/noahkafemann/ai-agent-security → Code → Open with Codespaces
    echo.
    pause
    exit /b 1
)

REM Prüfe ob Docker läuft
docker version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo FEHLER: Docker Desktop läuft nicht.
    echo.
    echo Bitte starte Docker Desktop und warte, bis das Wal-Symbol grün leuchtet.
    echo.
    pause
    exit /b 1
)

echo Docker Desktop ist verfügbar und läuft.

REM Image bauen falls nicht vorhanden
echo.
echo Prüfe AGORIS Docker Image...
docker image inspect agoris >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Image nicht gefunden. Baue AGORIS Image... (dies kann einige Minuten dauern)
    docker build -t agoris -f Dockerfile .
    if %ERRORLEVEL% NEQ 0 (
        echo FEHLER beim Bauen des Docker Images.
        pause
        exit /b 1
    )
    echo Image erfolgreich gebaut.
) else (
    echo Image bereits vorhanden.
)

REM Runs-Verzeichnis anlegen
if not exist "runs" mkdir runs

REM Befehl ermitteln
set "CMD=%1"
if "%CMD%""==""" set "CMD=start"
if /I "%CMD%"=="menu" set "CMD=start"
if /I "%CMD%"=="interaktiv" set "CMD=start"
if /I "%CMD%"=="help" goto :help
if /I "%CMD%"=="--help" goto :help
if /I "%CMD%"=="-h" goto :help

shift
set "ARGS=%*"

echo.
echo Starte AGORIS in Docker Desktop mit Sandbox-Unterstützung...
echo Befehl: docker run --rm --privileged -it -v "%CD%:/agoris" -v "%CD%\runs:/agoris/runs" -w /agoris agoris python3 agoris.py %CMD% %ARGS%
echo.

docker run --rm --privileged -it -v "%CD%:/agoris" -v "%CD%\runs:/agoris/runs" -w /agoris agoris python3 agoris.py %CMD% %ARGS%
exit /b %ERRORLEVEL%

:help
echo.
echo Verwendung: install.bat [befehl] [argumente...]
echo.
echo Befehle:
echo   (ohne)    Baut Image und startet interaktives Menü
echo   doctor    Prüft die Umgebung im Container
echo   test      Vollständiger Test aller Agenten
echo   attacks   14 Ausbruchversuche
echo   run       Demo-Agentenlauf
echo   benchmark Sandbox-Performance messen
echo   help      Diese Hilfe
echo.
echo Beispiele:
echo   install.bat
echo   install.bat doctor
echo   install.bat run "Hallo Welt" -p minimal
echo.
pause
exit /b 0
