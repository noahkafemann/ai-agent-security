@echo off
REM docker-run.cmd - AGORIS einfach in Docker Desktop unter Windows starten
REM
REM Voraussetzung: Docker Desktop installiert und gestartet
REM
REM Verwendung:
REM   docker-run.cmd        (startet interaktives Menü)
REM   docker-run.cmd doctor (führt doctor aus)
REM   docker-run.cmd menu   (startet interaktives Menü)

setlocal

echo AGORIS - Einfache Docker-Ausführung für Windows
echo ================================================

REM Überprüfe ob Docker läuft
docker version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Fehler: Docker Desktop scheint nicht zu laufen.
    echo.
    echo Bitte starte Docker Desktop und versuche es erneut.
    echo Download: https://www.docker.com/products/docker-desktop
    pause
    exit /b 1
)

REM Erstelle Docker Image falls nicht vorhanden
docker image inspect agoris >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Baue AGORIS Docker Image...
    docker build -t agoris .
    if %ERRORLEVEL% NEQ 0 (
        echo Fehler beim Bauen des Images.
        pause
        exit /b 1
    )
    echo Image erfolgreich gebaut.
)

REM Setze Kommando
set "CMD=python3 agoris.py"
set "ARG=%1"
if "%ARG%"=="" set "ARG=menu"
if "%ARG%"=="menu" set "ARG=start"
if "%ARG%"=="interaktiv" set "ARG=start"

REM Füge weitere Argumente hinzu
shift
set "ADDITIONAL=%*"
if "%ADDITIONAL%" NEQ "" set "CMD=%CMD% %ADDITIONAL%"

echo Starte AGORIS in Docker mit --privileged...
echo Kommando: %CMD%
echo.

REM Starte Container
docker run --rm --privileged -it -v "%CD%:/agoris" -w /agoris agoris %CMD%
exit /b %ERRORLEVEL%
