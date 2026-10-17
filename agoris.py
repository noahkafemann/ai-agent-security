#!/usr/bin/env python3
"""AGORIS - Eine sichere Umgebung fuer unzuverlaessige KI-Agenten.

Ohne Argumente startet das interaktive Menü. Für Details siehe agoris.cli.
"""

from agoris.cli import main

if __name__ == "__main__":
    import sys
    sys.exit(main())
