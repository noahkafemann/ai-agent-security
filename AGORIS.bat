@echo off
REM AGORIS.bat - Doppelklick zum Starten unter Windows
cd /d "%~dp0"
where python3 >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    python3 agoris_docker.py %*
) else (
    python agoris_docker.py %*
)
pause
