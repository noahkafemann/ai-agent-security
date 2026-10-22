# run.ps1 — Startet AGORIS auf Windows.
#
#    .\run.ps1 doctor
#    .\run.ps1 attacks
#    .\run.ps1 test
#    .\run.ps1 benchmark
#
# AGORIS braucht Linux-Kernel-Funktionen. Dieses Skript erkennt automatisch,
# ob WSL2, Docker oder Codespaces verfügbar ist.
#
# Einfache Installation:
#   1. PowerShell als Administrator: wsl --install
#   2. Neu starten, dann Ubuntu öffnen
#   3. In Ubuntu: git clone ... && cd ... && python3 agoris.py doctor
#
# Ohne Installation: GitHub Codespaces (Browser)
#   https://github.com/noahkafemann/ai-agent-security → Code → Open with Codespaces

param(
    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$CliArgs
)

$ErrorActionPreference = "Stop"

function Test-Wsl {
    # "wsl" gibt es auf manchen Rechnern gar nicht - dann ist der Aufruf ein
    # Fehler und keine Fehlermeldung. Deshalb der try/catch.
    try {
        $null = wsl --status 2>$null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

function Test-Docker {
    try {
        $null = docker version 2>$null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

function Get-WslPath {
    # "C:\Users\kafemann\repo" -> "/mnt/c/Users/kafemann/repo"
    $pfad = (Get-Location).Path
    if ($pfad -match '^([A-Za-z]):[\\/](.*)$') {
        return "/mnt/" + $matches[1].ToLower() + "/" + $matches[2].Replace("\", "/")
    }
    return $pfad.Replace("\", "/")
}

function Show-Help {
    Write-Host "AGORIS auf Windows" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Verwendung: .\run.ps1 <befehl>" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Befehle:"
    Write-Host "  doctor      - Prüft, ob Linux-Umgebung funktioniert"
    Write-Host "  inspect     - Zeigt Innenansicht des Sandbox"
    Write-Host "  attacks     - 14 Ausbruchversuche"
    Write-Host "  test        - Kompletttest aller Agenten"
    Write-Host "  run         - Demo-Agentenlauf"
    Write-Host "  benchmark   - Sandbox-Performance messen"
    Write-Host "  help        - Diese Hilfe"
    Write-Host ""
    Write-Host "Installation (einmalig):"
    Write-Host "  1. PowerShell als Admin: wsl --install"
    Write-Host "  2. PC neu starten, 'Ubuntu' öffnen"
    Write-Host "  3. In Ubuntu: git clone https://github.com/noahkafemann/ai-agent-security.git"
    Write-Host "  4. cd ai-agent-security && python3 agoris.py doctor"
    Write-Host ""
    Write-Host "Ohne Installation: GitHub Codespaces (Browser)"
    Write-Host "  https://github.com/noahkafemann/ai-agent-security → Code → Open with Codespaces"
}

Write-Host "AGORIS — Startvorbereitung auf Windows" -ForegroundColor Cyan
Write-Host ""

# Hilfe anzeigen
if ($CliArgs.Count -eq 0 -or $CliArgs[0] -eq "help") {
    Show-Help
    exit 0
}

$command = $CliArgs[0]
# Ohne weitere Argumente bleibt die Liste leer - sonst greift der Bereich
# 1..0 und liefert einen Null-Wert, der als Argument mitgegeben wird.
$remainingArgs = if ($CliArgs.Count -gt 1) { $CliArgs[1..($CliArgs.Count - 1)] } else { @() }

# Option 1: WSL2
if (Test-Wsl) {
    Write-Host "WSL2 gefunden." -ForegroundColor Green
    $repoPath = Get-WslPath
    $wslArgs = "cd '$repoPath' && python3 agoris.py $command $($remainingArgs -join ' ')"
    Write-Host "Führe in WSL2 aus: python3 agoris.py $command $($remainingArgs -join ' ')" -ForegroundColor Gray
    try {
        wsl bash -lc $wslArgs
        exit $LASTEXITCODE
    } catch {
        Write-Host "WSL2-Aufruf fehlgeschlagen: $_" -ForegroundColor Red
    }
}

# Option 2: Docker Desktop
if (Test-Docker) {
    Write-Host "Docker Desktop gefunden." -ForegroundColor Green
    Write-Host "Starte Container mit --privileged..." -ForegroundColor Gray
    $dockerArgs = @("run", "--rm", "--privileged",
        "-v", "$((Get-Location).Path):/agoris",
        "-w", "/agoris",
        "agoris", "python3", "agoris.py", $command) + $remainingArgs
    docker @dockerArgs
    exit $LASTEXITCODE
}

# Option 3: Anleitung
Write-Host "" -ForegroundColor Yellow
Write-Host "Keine Linux-Umgebung gefunden. Wähle eine Option:" -ForegroundColor Yellow
Write-Host ""
Write-Host "  1. WSL2 (empfohlen):" -ForegroundColor Cyan
Write-Host "     PowerShell als Administrator:" -ForegroundColor Gray
Write-Host "       wsl --install" -ForegroundColor Gray
Write-Host "     Dann Repository klonen und starten:" -ForegroundColor Gray
Write-Host "       git clone https://github.com/noahkafemann/ai-agent-security.git" -ForegroundColor Gray
Write-Host "       cd ai-agent-security" -ForegroundColor Gray
Write-Host "       python3 agoris.py doctor" -ForegroundColor Gray
Write-Host ""
Write-Host "  2. Docker Desktop für Windows:" -ForegroundColor Cyan
Write-Host "     https://www.docker.com/products/docker-desktop" -ForegroundColor Gray
Write-Host "     Dann: docker build -t agoris . && .\run.ps1 doctor" -ForegroundColor Gray
Write-Host ""
Write-Host "  3. GitHub Codespaces (einfach im Browser, keine Installation):" -ForegroundColor Cyan
Write-Host "     Öffne das Repository in github.dev oder starte einen CodeSpace." -ForegroundColor Gray
Write-Host ""
exit 1
