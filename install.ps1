# install.ps1 — AGORIS einfache Installation unter Windows (PowerShell)
#
# Dieses Skript umgeht die "Unbekannter Herausgeber"-Warnung, indem es
# direkt mit -ExecutionPolicy Bypass ausgeführt wird. Nutzer können es
# einfach mit Doppelklick über install.bat starten oder direkt so aufrufen:
#
#   powershell -ExecutionPolicy Bypass -File install.ps1
#
# Ohne Argument baut es das Image und startet das interaktive Menü.

param(
    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$CliArgs
)

$ErrorActionPreference = "Stop"
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Definition
$IMAGE_NAME = "agoris"

Write-Host "╔═══════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║  AGORIS — Einfache Installation unter Windows          ║" -ForegroundColor Cyan
Write-Host "║  (Docker Desktop + Sandbox)                            ║" -ForegroundColor Cyan
Write-Host "╚═══════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

function Test-DockerAvailable {
    # Fehlt docker ganz, ist der Aufruf ein Fehler und keine Fehlermeldung.
    # Ohne try/catch bricht das Skript mit einem Stapelabbruch ab, statt die
    # eigene Anleitung zu zeigen.
    try {
        $null = docker --version 2>$null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

function Test-DockerRunning {
    try {
        $null = docker version 2>$null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

function Show-Help {
    Write-Host "Verwendung: powershell -ExecutionPolicy Bypass -File install.ps1 [befehl]" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Befehle:"
    Write-Host "  (ohne)   - Baut Image und startet interaktives Menü"
    Write-Host "  doctor   - Prüft die Umgebung im Container"
    Write-Host "  test     - Vollständiger Test aller Agenten"
    Write-Host "  attacks  - 14 Ausbruchversuche"
    Write-Host "  run      - Demo-Agentenlauf"
    Write-Host "  benchmark- Sandbox-Performance messen"
    Write-Host "  help     - Diese Hilfe"
    Write-Host ""
    Write-Host "Beispiel (um SmartScreen zu umgehen):" -ForegroundColor Yellow
    Write-Host "  powershell -ExecutionPolicy Bypass -File install.ps1" -ForegroundColor Gray
    Write-Host ""
}

# Ohne Argument: Image bauen und das Menü starten - das ist der Weg, den
# install.bat (Doppelklick) nimmt. Nur ausdrückliche Hilfe-Anfragen zeigen
# nur die Hilfe.
$command = "start"
$remainingArgs = @()

if ($CliArgs.Count -gt 0) {
    $first = $CliArgs[0]
    if ($first -eq "help") {
        Show-Help
        exit 0
    }
    $command = $first
    if ($CliArgs.Count -gt 1) {
        $remainingArgs = $CliArgs[1..($CliArgs.Count - 1)]
    }
}

if (-not (Test-DockerAvailable)) {
    Write-Host "FEHLER: Docker ist nicht installiert oder nicht im PATH." -ForegroundColor Red
    Write-Host ""
    Write-Host "So behebst du das:" -ForegroundColor Yellow
    Write-Host "  1. Lade Docker Desktop für Windows herunter:" -ForegroundColor Gray
    Write-Host "     https://www.docker.com/products/docker-desktop" -ForegroundColor Cyan
    Write-Host "  2. Installiere Docker Desktop und starte WSL2 Integration." -ForegroundColor Gray
    exit 1
}

if (-not (Test-DockerRunning)) {
    Write-Host "FEHLER: Docker Desktop läuft nicht." -ForegroundColor Red
    Write-Host ""
    Write-Host "Bitte starte Docker Desktop und warte bis es läuft." -ForegroundColor Yellow
    exit 1
}

Write-Host "Docker Desktop ist verfügbar." -ForegroundColor Green
Write-Host ""

Write-Host "Prüfe AGORIS Docker Image..." -ForegroundColor Gray
$imageCheck = docker image inspect $IMAGE_NAME 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Image nicht gefunden. Baue AGORIS Image..." -ForegroundColor Yellow
    docker build -t $IMAGE_NAME -f Dockerfile $SCRIPT_DIR
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FEHLER beim Bauen des Docker Images." -ForegroundColor Red
        exit 1
    }
    Write-Host "Image erfolgreich gebaut." -ForegroundColor Green
} else {
    Write-Host "Image bereits vorhanden." -ForegroundColor Green
}

$runsDir = Join-Path $SCRIPT_DIR "runs"
if (-not (Test-Path $runsDir)) {
    New-Item -ItemType Directory -Path $runsDir | Out-Null
}

Write-Host ""
Write-Host "Starte AGORIS in Docker Desktop..." -ForegroundColor Cyan

$cmdArgs = @("python3", "agoris.py", $command) + $remainingArgs
$dockerArgs = @("run", "--rm", "--privileged", "-it",
    "-v", "$($SCRIPT_DIR):/agoris",
    "-v", "$($runsDir):/agoris/runs",
    "-w", "/agoris",
    $IMAGE_NAME) + $cmdArgs

docker @dockerArgs
exit $LASTEXITCODE
