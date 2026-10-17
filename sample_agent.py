#!/usr/bin/env python3
"""Beispiel eines benutzerdefinierten KI-Agenten für AGORIS.

Dieser Agent demonstriert, wie man mit den verfügbaren Werkzeugen
in der AGORIS-Sandbox arbeitet. Er kann:
- Verzeichnisse auflisten
- Dateien lesen/schreiben
- Python-Code ausführen
- Weitere Aktionen gemäß Policy

Läuft er erfolgreich in der Sandbox, sieht man eine Datei
/work/agent_output.txt entstehen.
"""

def main():
    print("Agent gestartet...")
    
    # 1. Arbeitsverzeichnis auflisten
    try:
        import os
        files = os.listdir("/work")
        print(f"Dateien im /work-Verzeichnis: {files}")
    except Exception as e:
        print(f"Fehler beim Auflisten: {e}")
    
    # 2. Eine Datei schreiben
    try:
        with open("/work/agent_output.txt", "w", encoding="utf-8") as f:
            f.write("Dies ist ein Beispiel-Agent.\n")
            f.write("Er hat erfolgreich in der AGORIS-Sandbox ausgeführt.\n")
            f.write("======================================\n\n")
            f.write("Hier können eigene Berechnungen oder Aufgaben stehen.\n")
        print("Erfolgreich geschrieben: /work/agent_output.txt")
    except Exception as e:
        print(f"Fehler beim Schreiben: {e}")
    
    # 3. Die geschriebene Datei lesen
    try:
        with open("/work/agent_output.txt", "r", encoding="utf-8") as f:
            content = f.read()
        print("Dateiinhalt:")
        print(content)
    except Exception as e:
        print(f"Fehler beim Lesen: {e}")
    
    # 4. Einfaches Rechnen mit Python
    try:
        result = sum(i*i for i in range(10))
        print(f"Beispielrechnung (Quadrate 0-9): {result}")
    except Exception as e:
        print(f"Fehler bei Berechnung: {e}")
    
    print("Agent erfolgreich beendet!")

if __name__ == "__main__":
    main()
