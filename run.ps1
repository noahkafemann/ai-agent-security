# run.ps1 — Startet AGORIS auf Windows.
#
#    .\run.ps1 doctor
#    .\run.ps1 attacks
#    .\run.ps1 test
#
# AGORIS braucht Linux-Kernel-Funktionen. Dieses Skript erkennt automatisch,
# ob WSL2, Docker oder Codespaces verfügbar ist.

param(
    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$Args
)

$ErrorActionPreference = "Stop"

function Test-Wsl {
    $r = wsl --status 2>$null
    return $LASTEXITCODE -eq 0
}

function Test-Docker {
    $r = docker version 2>$null
    return $LASTEXITCODE -eq 0
}

Write-Host "AGORIS — Startvorbereitung auf Windows" -ForegroundColor Cyan
Write-Host ""

# Option 1: WSL2
if (Test-Wsl) {
    Write-Host "WSL2 wurde gefunden." -ForegroundColor Green
    Write-Host ""
    $wslArgs = "cd /mnt/c" + (Get-Location).Path.Replace(":", "").Replace("\", "/") + " && python3 agoris.py " + ($Args -join " ")
    Write-Host "Fuehre in WSL2 aus: python3 agoris.py $($Args -join ' ')" -ForegroundColor Gray
    try {
        wsl bash -lc $wslArgs
        exit $LASTEXITCODE
    } catch {
        Write-Host "WSL2-Aufruf fehlgeschlagen: $_" -ForegroundColor Red
    }
}

# Option 2: Docker Desktop
if (Test-Docker) {
    Write-Host "Docker wurde gefunden." -ForegroundColor Green
    Write-Host "Starte Container mit --privileged (benötigt Docker Desktop)..." -ForegroundColor Gray
    $dockerArgs = @("run", "--rm", "--privileged",
        "-v", "$((Get-Location).Path):/agoris",
        "-w", "/agoris",
        "agoris", "python3", "agoris.py") + $Args
    docker @dockerArgs
    exit $LASTEXITCODE
}

# Option 3: Anleitung
Write-Host "" -ForegroundColor Yellow
Write-Host "Keine Linux-Umgebung gefunden. Installiere eine der folgenden Optionen:" -ForegroundColor Yellow
Write-Host ""
Write-Host "  1. WSL2 (Windows-Subsystem für Linux):" -ForegroundColor Cyan
Write-Host "     In PowerShell als Administrator:" -ForegroundColor Gray
Write-Host "       wsl --install" -ForegroundColor Gray
Write-Host "     Dann Repository klonen und starten:" -ForegroundColor Gray
Write-Host "       git clone https://github.com/noahkafemann/ai-agent-security.git" -ForegroundColor Gray
Write-Host "       cd ai-agent-security" -ForegroundColor Gray
Write-Host "       python3 agoris.py doctor" -ForegroundColor Gray
Write-Host ""
Write-Host "  2. Docker Desktop für Windows:" -ForegroundColor Cyan
Write-Host "     https://www.docker.com/products/docker-desktop" -ForegroundColor Gray
Write-Host "     Dann: docker build -t agoris . && docker run --privileged agoris doctor" -ForegroundColor Gray
Write-Host ""
Write-Host "  3. GitHub Codespaces:" -ForegroundColor Cyan
Write-Host "     Öffne das Repository in github.dev oder starte einen CodeSpace." -ForegroundColor Gray
Write-Host ""
exit 1
