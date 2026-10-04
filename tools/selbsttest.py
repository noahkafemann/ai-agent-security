#!/usr/bin/env python3
"""Prueft die Werkzeuge unter ``tools/`` - ohne Abhaengigkeiten.

Warum das existiert: Die Werkzeuge erzeugen und pruefen die veroeffentlichte
Seite. Wenn sie stillschweigend etwas falsch machen, faellt das erst auf,
wenn die Seite schon laeuft - und dann sieht es niemand mehr. Zwei Fehler
sind genau so entstanden:

* Die Trennzeile einer Markdown-Tabelle (``|---|---|``) wurde als Zeile mit
  Inhalt ausgegeben. Die Tabelle sah aus, als haette sie eine Zeile mit
  ``---``.
* Der Vergleich der eingecheckten Dokumentation zeigte auf einen fest im
  Skript hinterlegten Pfad statt auf das uebergebene Verzeichnis. Aufruf
  gegen ein anderes Verzeichnis: "OK" - ohne dass irgendetwas geprueft
  wurde.

    python3 tools/selbsttest.py
"""

from __future__ import annotations

import importlib.util
import pathlib
import shutil
import sys
import tempfile
import traceback
from typing import Callable, List, Tuple

WURZEL = pathlib.Path(__file__).resolve().parent.parent


def _lade(name: str):
    """Laedt ein Skript aus ``tools/`` als Modul."""
    pfad = WURZEL / "tools" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"agoris_tools_{name}", pfad)
    modul = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(modul)
    return modul


md2html = _lade("md2html")
check_links = _lade("check_links")


def _wandle(markdown: str) -> str:
    return md2html.konvertiere(markdown)


def _tabelle_ohne_trennzeile() -> None:
    """Die Trennzeile ist Syntax und darf nicht als Zeile erscheinen."""
    html = _wandle(
        "| A | B |\n"
        "|---|---|\n"
        "| 1 | 2 |\n"
    )
    if "<td>---</td>" in html or "---" in html.replace("<hr", ""):
        raise AssertionError(f"Trennzeile steht noch im Ergebnis:\n{html}")
    zellen = html.count("<td>")
    if zellen != 2:
        raise AssertionError(f"erwartet 2 Zellen, gefunden {zellen}:\n{html}")
    if "<th>A</th>" not in html:
        raise AssertionError(f"Kopfzeile fehlt:\n{html}")


def _tabellen_mit_auszeichnung() -> None:
    """Markdown-Auszeichnung in Zellen bleibt erhalten, Pipes werden getrennt."""
    html = _wandle(
        "| Pfad | Bedeutung |\n"
        "|---|---|\n"
        "| `/usr/bin/python3` | **wichtig** |\n"
        "| | *kursiv* |\n"
    )
    if "<code>/usr/bin/python3</code>" not in html:
        raise AssertionError(f"`...` wurde nicht umgesetzt:\n{html}")
    if "<strong>wichtig</strong>" not in html:
        raise AssertionError(f"fette Zelle ging verloren:\n{html}")
    if "<em>kursiv</em>" not in html:
        raise AssertionError(f"kursive Zelle ging verloren:\n{html}")
    if html.count("<tr>") != 3:
        raise AssertionError(f"erwartet 3 Zeilen, gefunden {html.count('<tr>')}:\n{html}")


def _rohes_html_wird_maskiert() -> None:
    """Rohes HTML in der Quelle wird zu Text, nicht zu Markup.

    Absicht: die Dokumente duerfen nichts einschleusen, was im Browser
    laeuft. Wer in der Markdown-Datei ``<b>`` schreibt, sieht es als Text.
    """
    html = _wandle("| a |\n|---|\n| <b>x</b> |\n")
    if "&lt;b&gt;" not in html or "<b>x</b>" in html:
        raise AssertionError(f"rohes HTML wurde nicht maskiert:\n{html}")


def _ueberschriften() -> None:
    html = _wandle("# Titel\n\n## Teil\n\n### Unter\n")
    for erwartet in ("<h1>Titel</h1>", "<h2>Teil</h2>", "<h3>Unter</h3>"):
        if erwartet not in html:
            raise AssertionError(f"{erwartet} fehlt:\n{html}")


def _codeblock_bleibt_unberuehrt() -> None:
    """Innerhalb eines Codeblocks wird nichts als HTML gelesen."""
    html = _wandle(
        "Beispiel:\n\n"
        "```\n"
        "<b>kein HTML</b> & | *kein Sternchen*\n"
        "```\n"
    )
    if "&lt;b&gt;kein HTML&lt;/b&gt;" not in html:
        raise AssertionError(f"Codeblock wurde als HTML interpretiert:\n{html}")
    if "<b>kein HTML</b>" in html:
        raise AssertionError("Tags aus dem Codeblock sind durchgekommen")


def _codeblock_mit_sprache() -> None:
    html = _wandle("```python\nprint(1)\n```\n")
    if 'class="language-python"' not in html:
        raise AssertionError(f"Sprachklasse fehlt:\n{html}")


def _listen() -> None:
    html = _wandle("- erstens\n- zweitens\n- drittens\n")
    if html.count("<li>") != 3:
        raise AssertionError(f"erwartet 3 Punkte, gefunden {html.count('<li>')}")


def _zitat() -> None:
    html = _wandle("> Wichtig.\n")
    if "<blockquote>" not in html:
        raise AssertionError(f"Zitat fehlt:\n{html}")


def _links_werden_auf_html_umgestellt() -> None:
    """Verweise auf Markdown zielen nach der Umwandlung auf HTML."""
    html = _wandle("Siehe [Anleitung](ANWENDUNG.md) und [Startseite](../index.html).")
    if 'href="ANWENDUNG.html"' not in html:
        raise AssertionError(f"Markdown-Verweis wurde nicht umgestellt:\n{html}")
    if 'href="../index.html"' not in html:
        raise AssertionError(f"HTML-Verweis wurde veraendert:\n{html}")
    if "ANWENDUNG.md" in html:
        raise AssertionError("im Ergebnis steht noch eine Markdown-Datei")


def _fremde_ziele_bleiben() -> None:
    html = _wandle("[GitHub](https://github.com/noahkafemann/ai-agent-security)")
    if 'href="https://github.com/noahkafemann/ai-agent-security"' not in html:
        raise AssertionError(f"externer Verweis ging verloren:\n{html}")


def _maskierung_von_text() -> None:
    html = _wandle("5 < 7 & 8 > 2\n")
    if "&lt;" not in html or "&amp;" not in html:
        raise AssertionError(f"Zeichen wurden nicht maskiert:\n{html}")


def _leerer_text() -> None:
    if _wandle("").strip():
        raise AssertionError("aus leerem Text wurde Inhalt")


# --------------------------------------------------------------------------
# check_links.py
# --------------------------------------------------------------------------


def _seite_mit(*dateien: str) -> pathlib.Path:
    tmp = pathlib.Path(tempfile.mkdtemp())
    (tmp / "index.html").write_text(
        '<!DOCTYPE html><html lang="de"><head>'
        '<link rel="stylesheet" href="style.css"></head>'
        '<body><h1 id="oben">T</h1><a href="#oben">oben</a></body></html>',
        encoding="utf-8",
    )
    (tmp / "style.css").write_text("body { color: #fff; }\n", encoding="utf-8")
    for name in dateien:
        (tmp / name).write_text("<!DOCTYPE html><html></html>\n", encoding="utf-8")
    return tmp


def _gute_seite_besteht() -> None:
    tmp = _seite_mit()
    try:
        fehler = check_links._pruefe_verweise(tmp) + check_links._pruefe_fremde_ressourcen(tmp)
        if fehler:
            raise AssertionError(f"unverdächtige Seite wurde bemängelt: {fehler}")
    finally:
        shutil.rmtree(tmp)


def _toter_verweis_wird_gemeldet() -> None:
    tmp = _seite_mit()
    try:
        (tmp / "index.html").write_text(
            '<a href="gibt/es/nicht.html">x</a>', encoding="utf-8"
        )
        fehler = check_links._pruefe_verweise(tmp)
        if not any("nicht.html" in f for f in fehler):
            raise AssertionError(f"toter Verweis wurde nicht gemeldet: {fehler}")
    finally:
        shutil.rmtree(tmp)


def _fremde_ressourcen_werden_gemeldet() -> None:
    tmp = _seite_mit()
    try:
        (tmp / "index.html").write_text(
            '<link rel="stylesheet" href="https://cdn.example.com/a.css">'
            '<script src="//cdn.example.com/b.js"></script>'
            '<img src="http://pixel.example.net/c.gif">',
            encoding="utf-8",
        )
        (tmp / "style.css").write_text(
            "@import url('https://fonts.example.com/d.css');\n"
            "body { background: url(https://img.example.com/e.png); }\n",
            encoding="utf-8",
        )
        fehler = check_links._pruefe_fremde_ressourcen(tmp)
        if len(fehler) != 5:
            raise AssertionError(f"erwartet 5 Meldungen, gefunden {len(fehler)}: {fehler}")
    finally:
        shutil.rmtree(tmp)


def _falscher_anker_wird_gemeldet() -> None:
    tmp = _seite_mit()
    try:
        (tmp / "index.html").write_text('<a href="#gibtsnicht">x</a>', encoding="utf-8")
        fehler = check_links._pruefe_verweise(tmp)
        if not any("gibtsnicht" in f for f in fehler):
            raise AssertionError(f"falscher Anker wurde nicht gemeldet: {fehler}")
    finally:
        shutil.rmtree(tmp)


def _dokus_kopien_sind_aktuell() -> None:
    """Die eingecheckte Doku passt zu den Markdown-Dateien - so soll es sein."""
    fehler = check_links._pruefe_doku_drift(WURZEL / "website")
    if fehler:
        raise AssertionError(
            "Die eingecheckte Dokumentation passt nicht zu docs/*.md.\n"
            "Nachziehen mit: python3 tools/md2html.py docs/*.md -o website/docs\n"
            + "\n".join(fehler)
        )


def _veraltete_doku_wird_gemeldet() -> None:
    """Der Vergleich muss das uebergebene Verzeichnis nehmen.

    Genau hier ist der Fehler von vorher entstanden: der Pfad war fest
    eingetragen, also meldete ein Aufruf gegen ein beliebiges anderes
    Verzeichnis "OK", ohne etwas geprueft zu haben.
    """
    tmp = _seite_mit()
    dokudir = tmp / "docs"
    dokudir.mkdir()
    try:
        # Absichtlich eine veraltete Kopie ablegen: nur ein Platzhalter.
        for md in sorted((WURZEL / "docs").glob("*.md")):
            (dokudir / f"{md.stem}.html").write_text("<!-- alt -->\n", encoding="utf-8")
        fehler = check_links._pruefe_doku_drift(tmp)
        if not fehler:
            raise AssertionError(
                "veraltete Dokumentation wurde nicht bemängelt - "
                "der Vergleich prueft offenbar nicht das uebergebene Verzeichnis"
            )
    finally:
        shutil.rmtree(tmp)


def _fehlende_doku_wird_gemeldet() -> None:
    tmp = _seite_mit()
    try:
        fehler = check_links._pruefe_doku_drift(tmp)
        if not any("docs" in f for f in fehler):
            raise AssertionError(f"fehlendes Dokuverzeichnis wurde nicht gemeldet: {fehler}")
    finally:
        shutil.rmtree(tmp)


TESTS: List[Tuple[str, Callable[[], None]]] = [
    ("md2html: Trennzeile wird nicht als Zeile ausgegeben", _tabelle_ohne_trennzeile),
    ("md2html: Auszeichnung in Tabellenzellen bleibt", _tabellen_mit_auszeichnung),
    ("md2html: rohes HTML wird maskiert", _rohes_html_wird_maskiert),
    ("md2html: Ueberschriften", _ueberschriften),
    ("md2html: Codeblock bleibt unberuehrt", _codeblock_bleibt_unberuehrt),
    ("md2html: Sprache im Codeblock", _codeblock_mit_sprache),
    ("md2html: Listen", _listen),
    ("md2html: Zitate", _zitat),
    ("md2html: Markdown-Verweise werden zu HTML", _links_werden_auf_html_umgestellt),
    ("md2html: fremde Verweise bleiben unangetastet", _fremde_ziele_bleiben),
    ("md2html: Zeichen werden maskiert", _maskierung_von_text),
    ("md2html: leerer Text", _leerer_text),
    ("check_links: gute Seite besteht", _gute_seite_besteht),
    ("check_links: toter Verweis", _toter_verweis_wird_gemeldet),
    ("check_links: fremde Ressourcen", _fremde_ressourcen_werden_gemeldet),
    ("check_links: falscher Anker", _falscher_anker_wird_gemeldet),
    ("check_links: eingecheckte Doku ist aktuell", _dokus_kopien_sind_aktuell),
    ("check_links: veraltete Doku wird erkannt", _veraltete_doku_wird_gemeldet),
    ("check_links: fehlende Doku wird erkannt", _fehlende_doku_wird_gemeldet),
]


def main() -> int:
    print("Selbsttest der Werkzeuge unter tools/")
    print("=" * 60)
    fehlgeschlagen = 0
    for name, test in TESTS:
        try:
            test()
        except Exception:  # noqa: BLE001 - hier ist jede Ausnahme ein Befund
            fehlgeschlagen += 1
            print(f"FEHLGESCHLAGEN  {name}")
            for zeile in traceback.format_exc().strip().split("\n")[-3:]:
                print(f"    {zeile}")
        else:
            print(f"ok             {name}")
    print("=" * 60)
    print(f"{len(TESTS) - fehlgeschlagen}/{len(TESTS)} bestanden")
    return 1 if fehlgeschlagen else 0


if __name__ == "__main__":
    sys.exit(main())
