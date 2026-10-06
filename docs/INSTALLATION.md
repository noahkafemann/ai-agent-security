# Installation & Plattform-Guide

AGORIS nutzt Linux-Kernel-Funktionen, die es auf Windows und macOS nicht gibt.
Dieses Dokument zeigt, wie du AGORIS auf **jedem** Betriebssystem zum Laufen
bekommst — mit konkreten Befehlen für jede Plattform.

## Warum das wichtig ist

| Funktion | Windows | macOS | Linux |
|---|---|---|---|
| `unshare()` (Namespaces) | nein | nein | ja |
| `chroot()` | nein | nein | ja |
| `setrlimit()` | nein | ja (teilweise) | ja |
| `seccomp` (BPF-Filter) | nein | nein | ja |
| `mount()` (bind, read-only) | nein | nein | ja |

**Fazit:** AGORIS braucht Linux. Auf den anderen Systemen musst du eine
Linux-Umgebung schaffen — entweder eine VM, einen Container oder eine
Cloud-Entwicklungsumgebung.

---

## Plattform-spezifische Anleitung

### 1. Linux (direkt)

Das ist der Standardfall. Alles geht davon aus.

```bash
git clone https://github.com/noahkafemann/ai-agent-security.git
cd ai-agent-security
python3 agoris.py doctor       # prüft deine Namespaces
python3 agoris.py test         # kompletter Check
```

**Voraussetzungen:**
- Python ≥ 3.8 (System liefert meist 3.10+)
- Kernel ≥ 3.8 (User-Namespaces)
- `unshare -Ur true` sollte funktionieren

Falls `python3` nicht gefunden wird, probiere `python`:

```bash
python --version   # manche Systeme nennen es 'python' statt 'python3'
```

### 2. Windows

**Empfehlung: WSL2** (Windows-Subsystem für Linux, Version 2)

In PowerShell **als Administrator**:

```powershell
wsl --install
```

Starte den Rechner neu, wenn Windows danach fragt. Dann öffnest du das
neue "Ubuntu"-Fenster und dort:

```bash
sudo apt update && sudo apt install -y git python3
git clone https://github.com/noahkafemann/ai-agent-security.git
cd ai-agent-security
python3 agoris.py doctor
```

**Hinweis:** In WSL2 funktionieren Namespaces meistens, aber `seccomp`
kann eingeschränkt sein. Verlasse dich auf `doctor`, nicht auf Annahmen.

**Alternative: Docker Desktop**

```powershell
# Docker Desktop installieren: https://www.docker.com/products/docker-desktop
docker build -t agoris https://github.com/noahkafemann/ai-agent-security.git
docker run --rm --privileged agoris python3 agoris.py doctor
```

**Alternative: GitHub Codespaces**

Öffne das Repository in `github.dev` oder starte einen CodeSpace — das
startet automatisch eine Linux-VM mit allen Kernel-Funktionen.

### 3. macOS

**Empfehlung: GitHub Codespaces**

Öffne das Repository in `github.dev` oder starte einen CodeSpace über
die GitHub-Website. Codespaces startet eine Linux-VM mit allen Kernel-
Funktionen automatisch — keine lokale Installation nötig.

**Alternative: Docker Desktop für Mac**

```bash
# Docker Desktop installieren: https://www.docker.com/products/docker-desktop
docker build -t agoris .
docker run --rm --privileged agoris python3 agoris.py doctor
```

> Wichtig: Der Container braucht `--privileged`, sonst schlägt
> `unshare()` mit `EPERM` fehl und die Namespaces sind inaktiv.

**Alternative: Linux-VM**

Installiere VirtualBox, UTM oder Parallels und eine Ubuntu-ISO:

```bash
# In der VM:
sudo apt update && sudo apt install -y git python3
git clone https://github.com/noahkafemann/ai-agent-security.git
cd ai-agent-security
python3 agoris.py doctor
```

### 4. GitHub Codespaces (alles, egal vom Betriebssystem)

Codespaces ist die einfachste Möglichkeit, AGORIS ohne lokale
Installation zu starten. Das `.devcontainer/devcontainer.json` im
Repository stellt sicher, dass alle Kernel-Funktionen verfügbar sind.

1. Gehe zu https://github.com/noahkafemann/ai-agent-security
2. Klicke auf den grünen "Code"-Button → "Open with Codespaces"
3. Der CodeSpace startet automatisch mit allen Voraussetzungen
4. Im integrierten Terminal:

```bash
python3 agoris.py doctor
python3 agoris.py test
```

---

## Fehlersuche

### `python3: command not found`

```bash
# Prüfe, wie Python bei dir heißt
python --version    # statt python3
which python        # Pfad herausfinden
# Dann:
python agoris.py doctor
```

### `git clone` schlägt fehl (Schule)

In vielen Schulen ist der ausgehende HTTPS-Verkehr blockiert.
Alternativ lade das Archiv statt:

```bash
curl -L https://github.com/noahkafemann/ai-agent-security/archive/refs/heads/main.tar.gz \
  | tar xz
cd ai-agent-security-main
```

Falls auch `curl` blockiert ist: Nutze die Schulkopie der Dateien, die
dein Lehrer bereitgestellt hat, oder GitHub Codespaces.

### Namespaces nicht verfügbar (`errno 1` in `doctor`)

Das passiert, wenn:
- Der Kernel User-Namespaces deaktiviert hat
- Du nicht die nötigen Rechte hast

In WSL2: Prüfe `wsl --status` und stelle sicher, dass du WSL2 (nicht WSL1)
nutzt. In Docker: Verwende `--privileged`.

### `seccomp` inaktiv

Das ist **kein Fehler** — es ist eine bekannte Einschränkung. AGORIS
zeigt genau das an: Die Angriffe 10, 11, 12 fallen dann ohne die
stärkste Einzelschicht. Die Übrigen halten weiterhin. Siehe
[`VERSUCHSPROTOKOLL.md`](VERSUCHSPROTOKOLL.md), Abschnitt "Einschränkungen".

---

## Ohne Installation testen

Willst du zuerst nur sehen, wie AGORIS aussieht, ohne etwas zu installieren?

```bash
# Nur der Website-Ordner reicht:
open website/index.html
# oder:
firefox website/index.html
```

Die Seite ist vollständig offline — sie lädt nichts von außen nach.
