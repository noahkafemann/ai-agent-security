#!/usr/bin/env python3
"""Startpunkt fuer AGORIS.

    python3 agoris.py doctor
    python3 agoris.py inspect
    python3 agoris.py run "Aufgabe" -p research
    python3 agoris.py attacks
    python3 agoris.py verify runs/<lauf>

Ohne Argumente laeuft ein kleiner Demo-Lauf mit der Policy ``minimal``.
Nur Standardbibliothek, Python >= 3.8, nur Linux.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Vor allem anderen: Sag es klar, wenn das Betriebssystem nicht passt. Sonst
# bricht der Import mit 'No module named fcntl' ab - technisch korrekt, aber
# fuer jemanden, der gerade zum ersten Mal startet, voellig unbrauchbar.
from agoris.compat import require_linux  # noqa: E402

require_linux()

from agoris.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())