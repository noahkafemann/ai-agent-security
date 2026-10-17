#!/usr/bin/env python3
"""Interaktiver Setup-Assistent für AGORIS.
Führt den Benutzer Schritt für Schritt durch Installation und Start.
"""

import os
import sys
import shutil
import subprocess
from agoris import style

def clear():
    os.system('cls' if os.name == 'nt' else 'clear')

def check_docker():
    if shutil.which('docker'):
        try:
            r = subprocess.run(['docker', 'version'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
            return 'running' if r.returncode == 0 else 'installed'
        except:
            return 'installed'
    return 'missing'

def check_wsl():
    if os.name == 'nt':
        try:
            r = subprocess.run(['wsl', '--status'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
            return r.returncode == 0
        except:
            return False
    return False

def check_python():
    return shutil.which('python3') or shutil.which('python')

def main():
    clear()
    print(style.header('AGORIS Setup-Assistent'))
    print(style.info('Finde den einfachsten Weg für dein System'))
    print(style.dim_text('=' * 60))
    print()
    
    # System erkennen
    print(style.bold('Dein System:'))
    if os.name == 'nt':
        print('  Windows')
    elif sys.platform == 'darwin':
        print('  macOS')
    else:
        print(f'  Linux ({sys.platform})')
    print()
    
    # Status prüfen
    docker_status = check_docker()
    wsl_ok = check_wsl()
    python_ok = check_python()
    
    print(style.bold('Vorhandene Komponenten:'))
    if docker_status == 'running':
        print(style.success('  ✓ Docker läuft'))
    elif docker_status == 'installed':
        print(style.warning('  ⚠ Docker installiert, aber läuft nicht'))
    else:
        print(style.error('  ✗ Docker nicht gefunden'))
    
    if os.name == 'nt':
        if wsl_ok:
            print(style.success('  ✓ WSL2 verfügbar'))
        else:
            print('  • WSL2: prüfe mit "wsl --install"')
    
    if python_ok:
        print(style.success(f'  ✓ Python: {python_ok}'))
    else:
        print(style.error('  ✗ Python nicht gefunden'))
    print()
    
    print(style.bold('Empfohlener Weg für dein System:'))
    if os.name == 'nt':
        if docker_status == 'running':
            print(style.success('  1) Docker Desktop (am einfachsten)'))
            print('     Starte: AGORIS.bat oder docker-run.cmd')
            print('     Oder: python3 agoris_docker.py')
        elif wsl_ok:
            print(style.success('  1) WSL2'))
            print('     Öffne WSL2-Terminal und führe aus:')
            print('     cd /mnt/c/PATH/TO/ai-agent-security && python3 agoris.py')
        else:
            print('  1) WSL2 einrichten (PowerShell als Admin: wsl --install)')
            print('  2) Nach Neustart Docker Desktop installieren')
    elif sys.platform == 'darwin':
        if docker_status == 'running':
            print(style.success('  1) Docker Desktop'))
            print('     ./docker-run.sh oder python3 agoris_docker.py')
        else:
            print('  1) Docker Desktop für macOS installieren')
    else:  # Linux
        if python_ok:
            print(style.success('  1) Direkt starten (Linux)'))
            print('     python3 agoris.py')
        else:
            print('  1) Python3 installieren (apt install python3)')
    print()
    
    # Datei-Übersicht
    print(style.bold('Vorhandene Start-Skripte:'))
    scripts = ['AGORIS.bat', 'AGORIS.cmd', 'docker-run.cmd', 'docker-run.sh', 'agoris_docker.py', 'agoris.py', 'menu.py']
    for s in scripts:
        if os.path.exists(os.path.join(os.path.dirname(__file__), s)):
            print(style.success(f'  ✓ {s}'))
        else:
            print(f'  • {s}')
    print()
    
    # Menü
    print(style.bold('Nächste Schritte:'))
    print('1. Docker-Start (Windows/Mac mit Docker)')
    print('2. Direkt-Start (Linux mit Python)')
    print('3. Eigenen Agenten testen')
    print('4. Hilfe anzeigen')
    print('0. Beenden')
    print()
    
    try:
        choice = input(style.info('Deine Wahl: '))
        if choice == '0':
            return
        elif choice == '1':
            if docker_status == 'running':
                if os.name == 'nt':
                    print('\nStarte: docker-run.cmd')
                else:
                    print('\nStarte: ./docker-run.sh')
            else:
                print('\nStarte Docker Desktop zuerst, dann:')
                if os.name == 'nt':
                    print('  docker-run.cmd')
                else:
                    print('  ./docker-run.sh')
        elif choice == '2':
            print('\nStarte: python3 agoris.py')
            print('Oder: python3 menu.py')
        elif choice == '3':
            print('\nTest mit Beispiel:')
            print('  python3 custom_runner.py sample_agent.py')
            print('Oder im Menü → Option 10')
        elif choice == '4':
            print('\nDetaillierte Anleitung in README.md')
    except KeyboardInterrupt:
        pass

if __name__ == '__main__':
    main()
