#!/usr/bin/env python3
"""Prueft eine erzeugte Seite, bevor sie veroeffentlicht wird.

Drei Fehler, die beim Veroeffentlichen sonst unbemerkt durchrutschen:

1. **Tote Verweise.** Ein Link zeigt auf eine Datei, die es nicht gibt. Wer
   klickt, bekommt eine Fehlermeldung statt einer Seite.
2. **Fremde Ressourcen.** Die Seite soll ohne Internet und ohne CDN
   funktionieren. Laedt sie ein Stylesheet oder ein Bild von einem Server
   nach, ist sie offline kaputt - und in China ebenfalls.
3. **Veraltete Dokumentation.** Die HTML-Dateien unter ``website/docs/`` sind
   eingecheckt, damit die Seite auch aus dem Repository heraus funktioniert.
   Aendert sich ``docs/*.md``, muss diese Kopie nachgezogen werden, sonst
   zeigen zwei Dateien Verschiedenes.

    python3 tools/check_links.py website
    python3 tools/check_links.py website --mit-doku-drift

Rueckgabewert 0 heisst: alles in Ordnung. Sonst 1, damit die Pipeline stoppt.
"""

from __future__ import annotations

import argparse
import filecmp
import html
import pathlib
import re
import subprocess
import sys
import tempfile
from typing import List, Tuple

# Verweise auf andere Seiten sind erlaubt - die klickt man absichtlich an.
# Verweise auf *Ressourcen* von fremden Servern sind verboten: die werden
# automatisch geladen, und genau daran scheitert die Seite ohne Internet.
RESSOURCEN = ("img", "script", "iframe", "video", "audio", "source", "embed")
VERWEIS = re.compile(r'(?:href|src)="([^"]+)"')


def _relative_verweise(seite: pathlib.Path, wurzel: pathlib.Path) -> List[str]:
    """Alle Verweise einer Seite, die auf ein Ziel im Repository zeigen."""
    text = seite.read_text(encoding="utf-8")
    tore = []
    for ziel in VERWEIS.findall(text):
        if ziel.startswith(("http://", "https://", "//", "mailto:", "data:", "javascript:")):
            continue
        tore.append(ziel)
    return tore


def _pruefe_verweise(wurzel: pathlib.Path) -> List[str]:
    fehler = []
    for seite in sorted(wurzel.rglob("*.html")):
        text = seite.read_text(encoding="utf-8")
        for ziel in _relative_verweise(seite, wurzel):
            if ziel.startswith("#"):
                if f'id="{ziel[1:]}"' not in text:
                    fehler.append(f"{seite}: Anker {ziel} gibt es auf der Seite nicht")
                continue
            pfad = ziel.split("#")[0]
            if not pfad:
                continue
            if not (seite.parent / html.unescape(pfad)).exists():
                fehler.append(f"{seite}: Link auf '{ziel}' - Datei fehlt")
    return fehler


def _pruefe_fremde_ressourcen(wurzel: pathlib.Path) -> List[str]:
    fehler = []
    muster = "|".join(RESSOURCEN)
    for seite in sorted(wurzel.rglob("*.html")):
        text = seite.read_text(encoding="utf-8")
        for treffer in re.finditer(rf"<({muster})\b[^>]*\ssrc=\"(https?:)?//([^\"]+)\"", text):
            fehler.append(f"{seite}: <{treffer.group(1)}> laedt von {treffer.group(3)}")
        for treffer in re.finditer(r"<link\b[^>]*href=\"(https?:)?//([^\"]+)\"", text):
            fehler.append(f"{seite}: <link> laedt von {treffer.group(2)}")
        for treffer in re.finditer(r"@import\s+(url\()?[\"']?(https?:)?//([^\"')]+)", text):
            fehler.append(f"{seite}: @import zieht {treffer.group(3)} nach")
    for styl in sorted(wurzel.rglob("*.css")):
        text = styl.read_text(encoding="utf-8")
        for treffer in re.finditer(r"url\(\s*[\"']?(https?:)?//([^\"')]+)", text):
            fehler.append(f"{styl}: url() laedt von {treffer.group(2)}")
    return fehler


def _pruefe_doku_drift(wurzel: pathlib.Path) -> List[str]:
    """Vergleicht ``docs/*.md`` mit der HTML-Kopie unterhalb von ``wurzel``.

    Wichtig: geprueft wird das Verzeichnis, das man angegeben hat - nicht ein
    fest im Skript hinterlegter Pfad. Sonst wuerde der Aufruf gegen ein
    anderes Verzeichnis stillschweigend das falsche pruefen und "OK" melden.

    Wozu das ueberhaupt: Die HTML-Dateien unter ``website/docs/`` sind
    eingecheckt, damit die Seite auch aus einem frischen Klon des Repository
    heraus funktioniert. Aendert sich ``docs/*.md``, muss diese Kopie
    nachgezogen werden, sonst zeigen zwei Dateien Verschiedenes.
    """
    repo = pathlib.Path(__file__).resolve().parent.parent
    quelle = sorted((repo / "docs").glob("*.md"))
    if not quelle:
        return ["docs/ enthaelt keine Markdown-Dateien"]
    if not (wurzel / "docs").is_dir():
        return [f"{wurzel}/docs fehlt - die Dokumentation wurde nicht mitgeliefert"]

    fehler = []
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(
            [sys.executable, str(repo / "tools" / "md2html.py"), *map(str, quelle), "-o", tmp],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        for md in quelle:
            erzeugt = pathlib.Path(tmp) / (md.stem + ".html")
            kopie = wurzel / "docs" / erzeugt.name
            befehl = f"python3 tools/md2html.py {md.name} -o {wurzel}/docs"
            if not kopie.exists():
                fehler.append(f"{kopie} fehlt - mit '{befehl}' nachziehen")
            elif not filecmp.cmp(erzeugt, kopie, shallow=False):
                fehler.append(
                    f"{kopie} passt nicht mehr zu {md.name} - mit '{befehl}' nachziehen"
                )
    return fehler


def main() -> int:
    pf = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    pf.add_argument("wurzel", type=pathlib.Path, help="Verzeichnis mit der erzeugten Seite")
    pf.add_argument(
        "--mit-doku-drift",
        action="store_true",
        help="zusaetzlich pruefen, ob website/docs/ zu docs/*.md passt",
    )
    argumente = pf.parse_args()

    if not argumente.wurzel.is_dir():
        print(f"FEHLER: {argumente.wurzel} ist kein Verzeichnis", file=sys.stderr)
        return 2

    befunde: List[Tuple[str, List[str]]] = [
        ("Tote Verweise", _pruefe_verweise(argumente.wurzel)),
        ("Fremde Ressourcen", _pruefe_fremde_ressourcen(argumente.wurzel)),
    ]
    if argumente.mit_doku_drift:
        befunde.append(("Veraltete Dokumentation", _pruefe_doku_drift(argumente.wurzel)))

    fehler_gesamt = 0
    for titel, fehler in befunde:
        if fehler:
            fehler_gesamt += len(fehler)
            print(f"FEHLER - {titel}:")
            for zeile in fehler:
                print(f"    {zeile}")
        else:
            print(f"OK - {titel}")

    if fehler_gesamt:
        print(f"\n{fehler_gesamt} Problem(e). Die Seite so nicht veroeffentlichen.")
        return 1

    print(f"\nSeite in {argumente.wurzel} ist in Ordnung.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
