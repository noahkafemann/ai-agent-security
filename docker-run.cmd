@echo off
REM docker-run.cmd - AGORIS einfach in Docker Desktop unter Windows starten
REM
REM Voraussetzung: Docker Desktop installiert und gestartet
REM
REM Verwendung:
REM   docker-run.cmd        (startet interaktives Menü)
REM   docker-run.cmd doctor (führt doctor aus)
REM   docker-run.cmd menu   (startet interaktives Menü)

setlocal enabledelayedexpansion

REM In das Verzeichnis des Skripts wechseln: sonst wird beim Bauen und beim
REM Mounten der falsche Ordner benutzt, sobald das Skript von woanders
REM aufgerufen wird.
cd /d "%~dp0"

echo AGORIS - Einfache Docker-Ausführung für Windows
echo ================================================

REM Überprüfe ob Docker läuft
docker version >nul 2>&1
if !ERRORLEVEL! NEQ 0 (
    echo Fehler: Docker Desktop scheint nicht zu laufen.
    echo.
    echo Bitte starte Docker Desktop und versuche es erneut.
    echo Download: https://www.docker.com/products/docker-desktop
    pause
    exit /b 1
)

REM Erstelle Docker Image falls nicht vorhanden
docker image inspect agoris >nul 2>&1
if !ERRORLEVEL! NEQ 0 (
    echo Baue AGORIS Docker Image...
    docker build -t agoris "%~dp0"
    if !ERRORLEVEL! NEQ 0 (
        echo Fehler beim Bauen des Images.
        pause
        exit /b 1
    )
    echo Image erfolgreich gebaut.
)

REM Setze Kommando
set "AGORIS_CMD=python3 agoris.py"
set "ARG=%~1"
if "%ARG%"=="" set "ARG=menu"
if /i "%ARG%"=="menu" set "ARG=start"
if /i "%ARG%"=="interaktiv" set "ARG=start"
set "AGORIS_CMD=!AGORIS_CMD! !ARG!"

REM Weitere Argumente: "%*" bleibt nach SHIFT unverändert, deshalb sammeln
REM ich sie einzeln - sonst wird der Befehl doppelt uebergeben.
shift
:collect_args
if "%1"=="" goto :args_done
set "AGORIS_CMD=!AGORIS_CMD! %1"
shift
goto :collect_args
:args_done

echo Starte AGORIS in Docker mit --privileged...
echo Kommando: !AGORIS_CMD!
echo.

REM Starte Container
docker run --rm --privileged -it -v "%~dp0:/agoris" -w /agoris agoris !AGORIS_CMD!
exit /b !ERRORLEVEL!
