#!/usr/bin/env python3
"""Startpunkt fuer AGORIS.

    python3 agoris.py doctor
    python3 agoris.py run "Aufgabe" -p research
    python3 agoris.py attacks

Ohne Argumente laeuft ein kleiner Demo-Lauf mit der Policy ``minimal``.
Nur Standardbibliothek, Python >= 3.8.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agoris.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())