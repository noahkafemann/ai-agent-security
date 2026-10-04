"""Plattformpruefung - sagt klar, warum es hier nicht geht.

AGORIS nutzt Funktionen, die es nur unter Linux gibt: Namespaces (``unshare``),
``chroot``, ``setrlimit`` und ``seccomp``. Unter Windows gibt es davon keine einzige.

Ohne diese Pruefung behauptet Python beim Import ``ModuleNotFoundError: No module
named 'fcntl'`` - ein Fehler, der nichts erklaert und schon bei der Installation
irritiert. Deshalb wird ganz am Anfang freundlich und konkret abgebrochen.

Die Module selbst bleiben trotzdem importierbar: Wer die Dateien liest oder auf
einem anderen Betriebssystem nur nachschaut, soll keinen Importfehler bekommen.
Darum sind ``fcntl`` und ``resource`` hier optional.
"""

from __future__ import annotations

import sys
from typing import List, Optional

IS_LINUX = sys.platform.startswith("linux")

#: Wofuer AGORIS den Kernel braucht - fuer die Fehlermeldung aufgeloest.
KERNELFUNKTIONEN: List[str] = [
    ("unshare()", "eigene Prozesse, Dateien und Netze fuer den Agenten (Namespaces)"),
    ("chroot()", "eigenes Dateisystem - der Agent sieht keine Wirtsdatei"),
    ("setrlimit()", "Grenzen fuer Rechenzeit, Speicher, Dateigroesse, Prozesse"),
    ("seccomp", "Syscall-Sperrliste: verbietet ptrace, mount, kexec_load, ..."),
    ("mount()", "bindet Dateien nur lesbar ein"),
]

PLATFORMNAME = {
    "win32": "Windows",
    "darwin": "macOS",
    "cygwin": "Cygwin",
}


def plattformname() -> str:
    roh = sys.platform
    if IS_LINUX:
        return "Linux"
    return PLATFORMNAME.get(roh, roh)


def pruefe() -> Optional[str]:
    """``None``, wenn alles gut ist - sonst eine fertige Fehlermeldung."""
    if IS_LINUX:
        return None
    return (
        "AGORIS laeuft nicht unter {plattform}.\n"
        "\n"
        "Gefunden wurde: {roh}\n"
        "\n"
        "AGORIS braucht Linux-Funktionen des Kernels. Unter Windows gibt es sie\n"
        "nicht - das ist keine Einstellungsfrage, sondern eine Eigenschaft des\n"
        "Betriebssystems. Was fehlen wuerde:\n"
        "\n"
        "{liste}\n"
        "\n"
        "Was du tun kannst:\n"
        "\n"
        "  1. Windows-Subsystem fuer Linux (WSL2), in PowerShell:\n"
        "         wsl --install\n"
        "     Danach im Linux-Terminal:\n"
        "         python3 agoris.py doctor\n"
        "\n"
        "  2. Linux in einer Virtualmaschine (z. B. VirtualBox + Ubuntu)\n"
        "\n"
        "  3. Ein Linux-Server in der Schulumgebung\n"
        "\n"
        "  4. Ein anderer Rechner mit Linux\n"
        "\n"
        "In jedem Fall gilt: 'python3 agoris.py doctor' sagt dir, was dort\n"
        "tatsaechlich funktioniert und was nicht.\n"
        "\n"
        "Zum Nachlesen: README.md, Abschnitt 'Voraussetzungen'."
    ).format(
        plattform=plattformname(),
        roh=sys.platform,
        liste="".join(f"  {name:<14} {zweck}\n" for name, zweck in KERNELFUNKTIONEN),
    )


def require_linux() -> None:
    """Bricht mit einer verstaendlichen Meldung ab, wenn es nicht Linux ist."""
    problem = pruefe()
    if problem:
        print(problem, file=sys.stderr)
        print("", file=sys.stderr)
        sys.exit(3)


def verfuegbare_optionale_module() -> dict:
    """Was an plattformabhaengigen Modulen da ist - fuer die Eigen-Diagnose."""
    zustand = {}
    for name in ("fcntl", "resource", "pwd", "termios"):
        try:
            __import__(name)
            zustand[name] = True
        except ImportError:
            zustand[name] = False
    zustand["linux"] = IS_LINUX
    return zustand