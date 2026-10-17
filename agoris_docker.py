#!/usr/bin/env python3
"""Einfache AGORIS Docker-Ausführung.

Dieses Skript ermöglicht es, AGORIS mit einem Klick unter Windows, macOS
oder Linux in Docker zu starten - ohne manuelle Befehle.
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path


def check_docker():
    """Prüft ob Docker installiert und verfügbar ist."""
    return shutil.which("docker") is not None


def is_docker_running():
    """Prüft ob Docker läuft."""
    try:
        result = subprocess.run(["docker", "version"], 
                              stdout=subprocess.PIPE, 
                              stderr=subprocess.PIPE, 
                              timeout=5)
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def build_image(repo_dir):
    """Baut das AGORIS Docker Image falls nicht vorhanden."""
    try:
        # Prüfe ob Image existiert
        result = subprocess.run(["docker", "image", "inspect", "agoris"],
                              stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE,
                              timeout=5)
        if result.returncode == 0:
            return True
    except subprocess.TimeoutExpired:
        return False
    
    print("Baue AGORIS Docker Image...")
    try:
        result = subprocess.run(["docker", "build", "-t", "agoris", "."],
                              cwd=repo_dir,
                              check=True)
        print("Image erfolgreich gebaut.")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Fehler beim Bauen des Images: {e}")
        return False
    except FileNotFoundError:
        print("Docker nicht gefunden.")
        return False


def run_agoris(args, repo_dir):
    """Startet AGORIS in Docker."""
    cmd = ["docker", "run", "--rm", "--privileged", "-it"]
    # Mount Projektverzeichnis
    cmd.extend(["-v", f"{repo_dir}:/agoris", "-w", "/agoris"])
    # Starte AGORIS
    cmd.append("agoris")
    cmd.extend(["python3", "agoris.py"] + args)
    
    try:
        subprocess.run(cmd, cwd=repo_dir, check=True)
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)
    except FileNotFoundError:
        print("Docker nicht gefunden.")


def main():
    args = sys.argv[1:] if len(sys.argv) > 1 else ["start"]
    repo_dir = Path(__file__).parent.absolute()
    
    # Plattform-spezifische Hinweise
    system = os.name
    print("AGORIS - Einfache Docker-Ausführung")
    print("=" * 40)
    print()
    
    if not check_docker():
        print("Fehler: Docker ist nicht installiert oder nicht im PATH.")
        print()
        print("So installierst du Docker:")
        if system == "nt":
            print("1. Lade Docker Desktop für Windows herunter:")
            print("   https://www.docker.com/products/docker-desktop")
            print("2. Installiere und starte Docker Desktop")
        elif sys.platform == "darwin":
            print("1. Lade Docker Desktop für macOS herunter:")
            print("   https://www.docker.com/products/docker-desktop")
            print("2. Installiere und starte Docker Desktop")
        else:
            print("1. Installiere Docker auf Linux:")
            print("   https://docs.docker.com/engine/install/")
        sys.exit(1)
    
    if not is_docker_running():
        print("Fehler: Docker läuft nicht.")
        print()
        print("Bitte starte Docker und versuche es erneut.")
        sys.exit(1)
    
    if not build_image(repo_dir):
        print("Fehler beim Vorbereiten des Docker-Images.")
        sys.exit(1)
    
    print("Starte AGORIS in Docker mit Sandbox-Unterstützung...")
    print()
    run_agoris(args, repo_dir)


if __name__ == "__main__":
    main()
