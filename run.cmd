@echo off
REM run.cmd — Startet AGORIS auf Windows (cmd.exe Version).
REM
REM    run.cmd doctor
REM    run.cmd attacks
REM    run.cmd test
REM    run.cmd benchmark
REM
REM AGORIS braucht Linux-Kernel-Funktionen. Dieses Skript prüft WSL2 und Docker.

if "%1"=="" (
    echo AGORIS auf Windows
    echo.
    echo Verwendung: run.cmd ^<befehl^>
    echo.
    echo Befehle:
    echo   doctor      - Prüft, ob Linux-Umgebung funktioniert
    echo   inspect     - Zeigt Innenansicht des Sandbox
    echo   attacks     - 14 Ausbruchversuche
    echo   test        - Kompletttest aller Agenten
    echo   run         - Demo-Agentenlauf
    echo   benchmark   - Sandbox-Performance messen
    echo   help        - Diese Hilfe
    echo.
    echo Installation (einmalig):
    echo   1. PowerShell als Admin: wsl --install
    echo   2. PC neu starten, 'Ubuntu' öffnen
    echo   3. In Ubuntu: git clone https://github.com/noahkafemann/ai-agent-security.git
    echo   4. cd ai-agent-security && python3 agoris.py doctor
    echo.
    echo Ohne Installation: GitHub Codespaces (Browser)
    echo   https://github.com/noahkafemann/ai-agent-security -^> Code -^> Open with Codespaces
    exit /b 0
)

if "%1"=="help" (
    call :show_help
    exit /b 0
)

set "COMMAND=%1"
shift
set "ARGS=%*"

REM Prüfe WSL2
wsl --status >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo WSL2 gefunden.
    set "REPO_PATH=%CD::=%"
    set "REPO_PATH=%REPO_PATH:\=/%"
    set "WSL_CMD=cd /mnt/c/%REPO_PATH% && python3 agoris.py %COMMAND% %ARGS%"
    echo Fuehre in WSL2 aus: python3 agoris.py %COMMAND% %ARGS%
    wsl bash -lc "%WSL_CMD%"
    exit /b %ERRORLEVEL%
)

REM Prüfe Docker
docker version >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo Docker Desktop gefunden.
    echo Starte Container mit --privileged...
    docker run --rm --privileged -v "%CD%:/agoris" -w /agoris agoris python3 agoris.py %COMMAND% %ARGS%
    exit /b %ERRORLEVEL%
)

REM Keine Linux-Umgebung
echo.
echo Keine Linux-Umgebung gefunden. Waehle eine Option:
echo.
echo   1. WSL2 (empfohlen):
echo      PowerShell als Administrator:
echo        wsl --install
echo      Dann Repository klonen und starten:
echo        git clone https://github.com/noahkafemann/ai-agent-security.git
echo        cd ai-agent-security
echo        python3 agoris.py doctor
echo.
echo   2. Docker Desktop für Windows:
echo      https://www.docker.com/products/docker-desktop
echo      Dann: docker build -t agoris . ^&^& run.cmd doctor
echo.
echo   3. GitHub Codespaces (einfach im Browser, keine Installation):
echo      Oeffne das Repository in github.dev oder starte einen CodeSpace.
echo.
exit /b 1

:show_help
echo AGORIS auf Windows
echo.
echo Verwendung: run.cmd ^<befehl^>
echo.
echo Befehle:
echo   doctor      - Prüft, ob Linux-Umgebung funktioniert
echo   inspect     - Zeigt Innenansicht des Sandbox
echo   attacks     - 14 Ausbruchversuche
echo   test        - Kompletttest aller Agenten
echo   run         - Demo-Agentenlauf
echo   benchmark   - Sandbox-Performance messen
echo   help        - Diese Hilfe
echo.
echo Installation (einmalig):
echo   1. PowerShell als Admin: wsl --install
echo   2. PC neu starten, 'Ubuntu' öffnen
echo   3. In Ubuntu: git clone https://github.com/noahkafemann/ai-agent-security.git
echo   4. cd ai-agent-security && python3 agoris.py doctor
echo.
echo Ohne Installation: GitHub Codespaces (Browser)
echo   https://github.com/noahkafemann/ai-agent-security -^> Code -^> Open with Codespaces
exit /b 0