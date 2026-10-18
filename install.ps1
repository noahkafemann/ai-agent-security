# install.ps1 — AGORIS einfache Installation unter Windows (PowerShell)
#
# Dieses Skript richtet alles ein, was AGORIS unter Windows braucht:
# 1. Prüft ob PowerShell im Administratormodus läuft (für WSL2)
# 2. Prüft ob Docker Desktop verfügbar ist
# 3. Baut das Docker Image automatisch
# 4. Startet AGORIS in Docker mit --privileged
#
# WICHTIG: Wenn Windows die Ausführung von Skripten blockiert
# ("Herausgeber kann nicht verifiziert werden"), führe zuerst aus:
#
#   Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
#
# Oder starte dieses Skript mit:
#
#   powershell -ExecutionPolicy Bypass -File install.ps1

param(
    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$Args
)

$ErrorActionPreference = "Continue"
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Definition
$IMAGE_NAME = "agoris"

Write-Host "╔═══════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║  AGORIS — Einfache Installation unter Windows          ║" -ForegroundColor Cyan
Write-Host "║  (Docker Desktop + Sandbox)                            ║" -ForegroundColor Cyan
Write-Host "╚═══════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# ----------------------------------------------------------------- Helfer
function Test-DockerAvailable {
    $r = docker --version 2>$null
    return $LASTEXITCODE -eq 0
}

function Test-DockerRunning {
    try {
        $r = docker version 2>$null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

function Show-Help {
    Write-Host "Verwendung: .\install.ps1 [befehl] [argumente...]" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Befehle:"
    Write-Host "  (ohne)   - Baut Image und startet interaktives Menü"
    Write-Host "  doctor   - Prüft die Umgebung im Container"
    Write-Host "  test     - Vollständiger Test aller Agenten"
    Write-Host "  attacks  - 14 Ausbruchversuche"
    Write-Host "  run      - Demo-Agentenlauf"
    Write-Host "  benchmark- - Sandbox-Performance messen"
    Write-Host "  help     - Diese Hilfe"
    Write-Host ""
    Write-Host "Beispiele:"
    Write-Host "  .\install.ps1"
    Write-Host "  .\install.ps1 doctor"
    Write-Host "  .\install.ps1 run ""Hallo Welt"" -p minimal"
    Write-Host ""
}

# ----------------------------------------------------------------- Hilfe
if ($Args.Count -eq 0 -or $Args[0] -in @("help", "-h", "--help", "/?")) {
    Show-Help
    exit 0
}

$command = $Args[0]
$remainingArgs = @($Args[1..($Args.Count-1)])

# ----------------------------------------------------------------- Docker prüfen
if (-not (Test-DockerAvailable)) {
    Write-Host "FEHLER: Docker ist nicht installiert oder nicht im PATH." -ForegroundColor Red
    Write-Host ""
    Write-Host "So behebst du das:" -ForegroundColor Yellow
    Write-Host "  1. Lade Docker Desktop für Windows herunter:" -ForegroundColor Gray
    Write-Host "     https://www.docker.com/products/docker-desktop" -ForegroundColor Cyan
    Write-Host "  2. Installiere Docker Desktop und starte den Rechner neu (falls gefragt)." -ForegroundColor Gray
    Write-Host "  3. Stelle sicher, dass WSL2 als Backend aktiv ist:" -ForegroundColor Gray
    Write-Host "     Docker Desktop → Settings → Resources → WSL Integration" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Ohne Docker: Nutze GitHub Codespaces (keine Installation):" -ForegroundColor Yellow
    Write-Host "  https://github.com/noahkafemann/ai-agent-security → Code → Open with Codespaces" -ForegroundColor Cyan
    exit 1
}

if (-not (Test-DockerRunning)) {
    Write-Host "FEHLER: Docker Desktop läuft nicht." -ForegroundColor Red
    Write-Host ""
    Write-Host "Bitte starte Docker Desktop und versuche es erneut." -ForegroundColor Yellow
    Write-Host "  Starte: Docker Desktop aus dem Startmenü" -ForegroundColor Gray
    Write-Host "  Warte, bis das Wal-Symbol grün leuchtet." -ForegroundColor Gray
    exit 1
}

Write-Host "Docker Desktop ist verfügbar und läuft." -ForegroundColor Green

# ----------------------------------------------------------------- Image bauen
Write-Host ""
Write-Host "Prüfe AGORIS Docker Image..." -ForegroundColor Gray

$imageCheck = docker image inspect $IMAGE_NAME 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Image nicht gefunden. Baue AGORIS Image... (dies kann einige Minuten dauern)" -ForegroundColor Yellow
    $build = docker build -t $IMAGE_NAME -f Dockerfile $SCRIPT_DIR 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FEHLER beim Bauen des Docker Images:" -ForegroundColor Red
        Write-Host $build -ForegroundColor Gray
        exit 1
    }
    Write-Host "Image erfolgreich gebaut." -ForegroundColor Green
} else {
    Write-Host "Image bereits vorhanden." -ForegroundColor Green
}

# ----------------------------------------------------------------- Volumen für Runs vorbereiten
$runsDir = Join-Path $SCRIPT_DIR "runs"
if (-not (Test-Path $runsDir)) {
    New-Item -ItemType Directory -Path $runsDir | Out-Null
}

# ----------------------------------------------------------------- Container starten
$cmdArgs = @("python3", "agoris.py", $command) + $remainingArgs
$dockerArgs = @("run", "--rm", "--privileged", "-it",
    "-v", "$($SCRIPT_DIR):/agoris",
    "-v", "$($runsDir):/agoris/runs",
    "-w", "/agoris",
    $IMAGE_NAME) + $cmdArgs

Write-Host ""
Write-Host "Starte AGORIS in Docker Desktop mit Sandbox-Unterstützung..." -ForegroundColor Cyan
Write-Host "Befehl: $($dockerArgs -join ' ')" -ForegroundColor Gray
Write-Host ""

try {
    docker @dockerArgs
    exit $LASTEXITCODE
} catch {
    Write-Host "FEHLER beim Starten des Containers: $_" -ForegroundColor Red
    exit 1
}
