# Dockerfile — AGORIS Sandbox für Linux (Docker Desktop, Codespaces, WSL2)
#
# AGORIS braucht Linux-Kernel-Funktionen (Namespaces, chroot, seccomp).
# Dieser Container läuft mit --privileged, damit die Isolation im
# Docker-Desktop-VM (Windows/macOS) funktioniert.
#
# Bauen:
#   docker build -t agoris .
#
# Starten (Windows PowerShell):
#   docker run --rm --privileged -it -v "${PWD}:/agoris" -w /agoris agoris python3 agoris.py doctor
#
# Starten (Windows cmd.exe):
#   docker run --rm --privileged -it -v "%CD%:/agoris" -w /agoris agoris python3 agoris.py doctor

FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONNOUSERSITE=1 \
    AGORIS_SANDBOX=1 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

# System-Pakete: Python3 + minimale Laufzeitumgebung für die Sandbox.
# Keine Shell, keine Netzwerk-Tools im fertigen Image — die laufen ja
# ohnehin im isolierten Käfig. Hier brauchen wir nur den Interpreter
# und die Standardbibliothek.
#
# Wichtig: die Shell wird erst in der allerletzten Schicht entfernt.
# Jede weitere RUN-Zeile wird über "/bin/sh -c" ausgeführt - fehlt die
# Shell da, bricht der Build ab.
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 \
        python3-stdlib \
        ca-certificates \
        tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3 /usr/bin/python

WORKDIR /agoris

# Projektdateien kopieren (wird beim Start vom Wirt überschrieben via -v)
COPY . /agoris/

# Healthcheck für Docker Desktop / Orchestrierung.
# Exec-Form, keine Shell-Form: das fertige Image hat keine Shell mehr.
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD ["python3", "-c", "import sys; sys.exit(0)"]

# Letzte Schicht: Shell entfernen. Das Image startet mit exec-form,
# also braucht es zum Start keine Shell.
RUN rm -f /bin/sh /bin/bash /bin/dash /usr/bin/sh /usr/bin/bash 2>/dev/null || true

CMD ["python3", "agoris.py", "doctor"]
