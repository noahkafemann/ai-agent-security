#!/bin/bash
# run.sh — Startet AGORIS auf Linux, macOS (mit Docker) oder leitet zur WSL2-Anleitung.
#
#   ./run.sh [befehl] [argumente...]
#
# Beispiele:
#   ./run.sh doctor
#   ./run.sh attacks
#   ./run.sh test
#   ./run.sh run "Eine Aufgabe" -p minimal

set -euo pipefail

# Wo liegt dieses Skript?
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PLATFORM="$(uname -s)"

case "$PLATFORM" in
    Linux*)
        PYTHON="${PYTHON:-python3}"
        if command -v "$PYTHON" &>/dev/null && "$PYTHON" -c "import sys; sys.exit(0 if sys.platform.startswith('linux') else 1)" 2>/dev/null; then
            exec "$PYTHON" agoris.py "$@"
        fi
        echo "Fehler: python3 auf einem Nicht-Linux-System gefunden, obwohl uname 'Linux' meldet." >&2
        exit 1
        ;;

    Darwin*)
        echo "AGORIS laeuft direkt nicht auf macOS (anderer Kernel)." >&2
        echo "" >&2
        echo "Option 1: GitHub Codespaces (einfachste Moeglichkeit)" >&2
        echo "  Öffne das Repository in github.dev oder starte einen CodeSpace." >&2
        echo "" >&2
        echo "Option 2: Docker Desktop" >&2
        if command -v docker &>/dev/null; then
            echo "  Docker wurde gefunden. Starte Container mit --privileged..." >&2
            exec docker run --rm --privileged \
                -v "$SCRIPT_DIR:/agoris" \
                -w /agoris \
                agoris python3 agoris.py "$@"
        else
            echo "  Docker ist nicht installiert. Installiere Docker Desktop für Mac:" >&2
            echo "  https://www.docker.com/products/docker-desktop" >&2
        fi
        echo "" >&2
        echo "Option 3: Linux-VM (VirtualBox, UTM, Parallels)" >&2
        echo "  Installiere Ubuntu und starte AGORIS dort." >&2
        exit 1
        ;;

    MINGW*|MSYS*|CYGWIN*|Windows*)
        echo "AGORIS laeuft direkt nicht auf Windows (anderer Kernel)." >&2
        echo "" >&2
        echo "Option 1: WSL2 (Windows-Subsystem für Linux)" >&2
        echo "  In PowerShell als Administrator:" >&2
        echo "    wsl --install" >&2
        echo "  Danach im WSL2-Terminal:" >&2
        echo "    python3 $SCRIPT_DIR/agoris.py $*" >&2
        echo "" >&2
        if command -v docker &>/dev/null; then
            echo "Option 2: Docker Desktop für Windows" >&2
            echo "  Docker wurde gefunden. Starte Container mit --privileged..." >&2
            exec docker run --rm --privileged \
                -v "$SCRIPT_DIR:/agoris" \
                -w /agoris \
                agoris python3 agoris.py "$@"
        else
            echo "  Docker ist nicht installiert. Installiere Docker Desktop für Windows:" >&2
            echo "  https://www.docker.com/products/docker-desktop" >&2
        fi
        echo "" >&2
        echo "Option 3: GitHub Codespaces (einfach im Browser)" >&2
        echo "  Öffne das Repository in github.dev oder starte einen CodeSpace." >&2
        exit 1
        ;;

    *)
        echo "Unbekannte Plattform: $PLATFORM" >&2
        echo "AGORIS braucht Linux. Nutze WSL2 (Windows), Docker, oder Codespaces." >&2
        exit 1
        ;;
esac
