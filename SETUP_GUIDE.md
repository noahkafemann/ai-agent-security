# AGORIS Setup-Anleitung

Dieses Dokument führt dich Schritt für Schritt zur einfachsten Installation.

## 1. Welches System hast du?

- **Windows 10/11** → Folge Abschnitt A oder B
- **macOS** → Folge Abschnitt C  
- **Linux** → Folge Abschnitt D

## A) Windows mit Docker Desktop (Am einfachsten)

1. Lade [Docker Desktop für Windows](https://www.docker.com/products/docker-desktop) herunter und installiere es
2. Starte Docker Desktop
3. Klicke doppelt auf `AGORIS.bat` (im Repository-Ordner)
4. Das interaktive Menü startet automatisch!

**Dateien hierfür:** `AGORIS.bat`, `docker-run.cmd`, `agoris_docker.py`

## B) Windows mit WSL2

1. Öffne PowerShell als Administrator
2. Führe aus: `wsl --install`
3. Starte neu und richte Ubuntu ein
4. Öffne WSL2-Terminal (Ubuntu)
5. Klone/öffne das Repository in WSL2
6. Führe aus: `python3 agoris.py`

## C) macOS mit Docker Desktop

1. Lade [Docker Desktop für macOS](https://www.docker.com/products/docker-desktop) herunter
2. Installiere und starte Docker Desktop
3. Öffne Terminal im Repository-Ordner
4. Führe aus: `./docker-run.sh`
5. Das Menü startet!

## D) Linux (direkt)

1. Öffne Terminal im Repository-Ordner
2. Führe aus: `python3 agoris.py`
3. Fertig!

# Interaktiver Setup-Assistent

Du kannst auch den Setup-Assistenten starten:
```bash
python3 setup_assistant.py
```

# Eigene KI-Agenten ausführen

Sobald AGORIS läuft, wähle **Option 10** im Menü ("Benutzerdefinierten Agenten ausführen") und gib den Pfad zu deiner `.py` Datei an.

Oder direkt ohne Menü:
```bash
python3 custom_runner.py sample_agent.py
python3 custom_runner.py meine_datei.py minimal 60
```

Beispiel-Agent: `sample_agent.py` zeigt dir, wie's funktioniert.

# Sicherstellen, dass alles funktioniert

Im Menü oder per Kommando:
```bash
python3 agoris.py doctor
```

Sollte alles grün/ok sein, läuft die Sandbox korrekt.
