#!/bin/bash
# docker-run.sh - AGORIS einfach in Docker starten
#
# Voraussetzung: Docker installiert und läuft
#
# Verwendung:
#   ./docker-run.sh        (startet interaktives Menü)
#   ./docker-run.sh doctor (führt doctor aus)
#   ./docker-run.sh menu   (startet interaktives Menü)

set -euo pipefail

echo "AGORIS - Einfache Docker-Ausführung"
echo "====================================="

# Überprüfe ob Docker läuft
if ! docker version >/dev/null 2>&1; then
    echo "Fehler: Docker scheint nicht zu laufen."
    echo ""
    if [[ "$(uname -s)" == "Darwin" ]]; then
        echo "Starte Docker Desktop für macOS."
    else
        echo "Bitte starte Docker."
    fi
    echo "Download: https://www.docker.com/products/docker-desktop"
    exit 1
fi

# Setze Kommando
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Erstelle Docker Image falls nicht vorhanden
if ! docker image inspect agoris >/dev/null 2>&1; then
    echo "Baue AGORIS Docker Image..."
    # Build-Kontext ist das Verzeichnis dieses Skripts - sonst wird der
    # falsche Ordner gebaut, wenn das Skript von woanders aufgerufen wird.
    if ! docker build -t agoris "$SCRIPT_DIR"; then
        echo "Fehler beim Bauen des Images."
        exit 1
    fi
    echo "Image erfolgreich gebaut."
fi

ARG="${1:-start}"
if [[ "$ARG" == "menu" || "$ARG" == "interaktiv" ]]; then
    ARG="start"
fi

# Füge weitere Argumente hinzu
if [[ $# -gt 0 ]]; then
    shift
    exec docker run --rm --privileged -it -v "$SCRIPT_DIR:/agoris" -w /agoris agoris python3 agoris.py "$ARG" "$@"
else
    exec docker run --rm --privileged -it -v "$SCRIPT_DIR:/agoris" -w /agoris agoris python3 agoris.py "$ARG"
fi
