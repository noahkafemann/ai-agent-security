#!/usr/bin/env python3
"""Wandelt eine Markdown-Datei in eine schlichte HTML-Seite.

Warum es das gibt: GitHub Pages liefert ``.md`` als reinen Text aus. Wer auf so
einen Link klickt, sieht eine Wand aus Sternchen, Pipe-Zeichen und Codeblöcken -
keine Seite. Für eine Präsentation ist das unbrauchbar.

Dieses Skript deckt genau das ab, was in ``docs/`` tatsächlich vorkommt:
Überschriften, Codeblöcke, Tabellen, Listen, Zitate, Bilder und die üblichen
Auszeichnungen im Fließtext. Kein Abhängigkeiten, keine Fremdbibliothek - wie
der Rest von AGORIS.

    python3 tools/md2html.py docs/ARCHITEKTUR.md docs/VERSUCHSPROTOKOLL.md -o out/
"""

from __future__ import annotations

import argparse
import html
import os
import re
import sys
from typing import List, Optional, Tuple

RAHMEN = """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{titel}</title>
<link rel="stylesheet" href="{pfad_zum_stil}">
</head>
<body>
<article>
{inhalt}
</article>
<footer><a href="../index.html">&larr; zur&shy;ck zur AGORIS-Seite</a></footer>
</body>
</html>
"""

STIL = """/* Erzeugt von tools/md2html.py - bewusst schlicht und ohne externe Quellen. */
:root { --text:#dce6f2; --muted:#7f8ea6; --dim:#55637a; --line:#172232;
        --panel:#0b111c; --cyan:#35e0e8; --blue:#4d8bff; }
* { box-sizing: border-box; }
body {
  margin: 0; background: #05070c; color: var(--text); line-height: 1.7;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, system-ui, sans-serif;
}
body::before {
  content: ""; position: fixed; inset: 0; pointer-events: none;
  background: radial-gradient(900px 520px at 78% -8%, rgba(77,139,255,.16), transparent 60%),
              radial-gradient(700px 420px at 8% 12%, rgba(157,107,255,.12), transparent 62%);
}
article { position: relative; max-width: 860px; margin: 0 auto; padding: 48px 24px 24px; }
h1, h2, h3, h4 { line-height: 1.2; letter-spacing: -.02em; margin: 1.7em 0 .7em; }
h1 { font-size: 2.1rem; margin-top: 0;
     background: linear-gradient(120deg,#fff 10%,#a8c4e8 60%,#6f88ad);
     -webkit-background-clip: text; background-clip: text; color: transparent; }
h2 { font-size: 1.5rem; padding-bottom: .3em; border-bottom: 1px solid var(--line); }
h3 { font-size: 1.2rem; color: #bcd0e8; }
p { margin: 0 0 1.05em; }
a { color: var(--cyan); }
ul, ol { margin: 0 0 1.1em; padding-left: 1.4em; }
li { margin: .3em 0; }
code {
  font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; font-size: .88em;
  background: rgba(77,139,255,.1); border: 1px solid rgba(77,139,255,.18);
  border-radius: 5px; padding: .1em .42em; color: #b9d0f0;
}
pre {
  background: linear-gradient(180deg, var(--panel) 0%, #080b13 100%);
  border: 1px solid var(--line); border-radius: 12px; padding: 20px 22px;
  overflow-x: auto; font-size: 13.5px; line-height: 1.7; color: #c3d3e6;
}
pre code { background: none; border: none; padding: 0; font-size: inherit; color: inherit; }
table { width: 100%; border-collapse: collapse; margin: 0 0 1.4em; font-size: 14px; }
thead th {
  text-align: left; font-size: 11.5px; letter-spacing: .14em; text-transform: uppercase;
  color: var(--dim); padding: 0 12px 11px; border-bottom: 1px solid #1f2c40;
}
tbody td { padding: 11px 12px; border-bottom: 1px solid rgba(23,34,50,.6); color: var(--muted); vertical-align: top; }
tbody tr:hover { background: rgba(77,139,255,.05); }
tbody td:first-child { color: var(--text); }
blockquote {
  margin: 0 0 1.2em; padding: 2px 18px; border-left: 3px solid var(--cyan);
  color: var(--muted); background: rgba(53,224,232,.04);
}
hr { border: none; border-top: 1px solid var(--line); margin: 2.4em 0; }
img { max-width: 100%; border-radius: 10px; }
footer {
  position: relative; max-width: 860px; margin: 0 auto; padding: 8px 24px 56px;
  font-size: 14px; color: var(--dim);
}
footer a { color: var(--muted); text-decoration: none; }
footer a:hover { color: var(--cyan); }
@media (max-width: 620px) { article { padding: 32px 16px 16px; } pre { padding: 14px; } }
"""


# ------------------------------------------------------------------ Inline
_CODE = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_ITALIC = re.compile(r"(?<![*\w])\*([^*\n]+)\*(?!\*)")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)")


def inline(text: str) -> str:
    """Auszeichnungen im Fliesstext - aber zuerst der Code, damit ``*`` in
    ``code`` nicht als Auszeichnung gilt."""
    plaetze: List[str] = []

    def merke(raw: str) -> str:
        plaetze.append(f"<code>{html.escape(raw)}</code>")
        return f"\x00{len(plaetze) - 1}\x00"

    text = _CODE.sub(lambda m: merke(m.group(1)), text)
    text = html.escape(text)
    text = _BOLD.sub(r"<strong>\1</strong>", text)
    text = _ITALIC.sub(r"<em>\1</em>", text)
    text = _IMAGE.sub(
        lambda m: f'<img src="{_ziel(m.group(2))}" alt="{m.group(1)}">', text
    )
    text = _LINK.sub(
        lambda m: f'<a href="{_ziel(m.group(2))}">{m.group(1)}</a>', text
    )
    return re.sub(r"\x00(\d+)\x00", lambda m: plaetze[int(m.group(1))], text)


def _ziel(url: str) -> str:
    """Lokale Markdown-Verweise zeigen auf die HTML-Fassung."""
    if url.endswith(".md") and not url.startswith(("http://", "https://", "#")):
        return url[:-3] + ".html"
    return url


# ------------------------------------------------------------------ Bloecke
def _tabelle(zeilen: List[str]) -> str:
    kopf, *rest = zeilen
    # Die Trennzeile (|---|---|) ist Syntax, keine Zeile mit Inhalt.
    rest = [z for z in rest if not re.match(r"^\s*\|[\s:|-]+\|\s*$", z)]
    spalten = [z.strip() for z in kopf.strip().strip("|").split("|")]
    teile = ["<table><thead><tr>"]
    teile += [f"<th>{inline(z)}</th>" for z in spalten]
    teile.append("</tr></thead><tbody>")
    for zeile in rest:
        zellen = [z.strip() for z in zeile.strip().strip("|").split("|")]
        teile.append("<tr>")
        teile += [f"<td>{inline(z)}</td>" for z in zellen]
        teile.append("</tr>")
    teile.append("</tbody></table>")
    return "".join(teile)


def _liste(zeilen: List[str], geordnet: bool) -> str:
    tag = "ol" if geordnet else "ul"
    teile = [f"<{tag}>"]
    for zeile in zeilen:
        text = re.sub(r"^\s*(?:[-*+]|\d+\.)\s+", "", zeile)
        teile.append(f"<li>{inline(text)}</li>")
    teile.append(f"</{tag}>")
    return "".join(teile)


def konvertiere(markdown: str) -> str:
    zeilen = markdown.replace("\r\n", "\n").split("\n")
    raus: List[str] = []
    i = 0
    while i < len(zeilen):
        zeile = zeilen[i]

        if not zeile.strip():
            i += 1
            continue

        # Codeblock
        if zeile.strip().startswith("```"):
            sprache = zeile.strip()[3:].strip()
            i += 1
            block: List[str] = []
            while i < len(zeilen) and not zeilen[i].strip().startswith("```"):
                block.append(zeilen[i])
                i += 1
            i += 1
            cls = f' class="language-{html.escape(sprache)}"' if sprache else ""
            raus.append(f"<pre><code{cls}>{html.escape(chr(10).join(block))}</code></pre>")
            continue

        # Tabelle: Kopfzeile + Trennzeile
        if zeile.strip().startswith("|") and i + 1 < len(zeilen) and re.match(
            r"^\s*\|[\s:|-]+\|\s*$", zeilen[i + 1]
        ):
            block = []
            while i < len(zeilen) and zeilen[i].strip().startswith("|"):
                block.append(zeilen[i])
                i += 1
            raus.append(_tabelle(block))
            continue

        # Überschrift
        treffer = re.match(r"^(#{1,6})\s+(.*)$", zeile)
        if treffer:
            stufe = len(treffer.group(1))
            raus.append(f"<h{stufe}>{inline(treffer.group(2).strip())}</h{stufe}>")
            i += 1
            continue

        # Zitat
        if zeile.strip().startswith(">"):
            block = []
            while i < len(zeilen) and zeilen[i].strip().startswith(">"):
                block.append(zeilen[i].strip().lstrip(">").strip())
                i += 1
            raus.append(f"<blockquote>{inline(' '.join(block))}</blockquote>")
            continue

        # Trennlinie
        if re.match(r"^\s*(-{3,}|\*{3,})\s*$", zeile):
            raus.append("<hr>")
            i += 1
            continue

        # Listen
        if re.match(r"^\s*[-*+]\s+", zeile) or re.match(r"^\s*\d+\.\s+", zeile):
            geordnet = bool(re.match(r"^\s*\d+\.\s+", zeile))
            block = []
            while i < len(zeilen) and zeilen[i].strip() and (
                re.match(r"^\s*[-*+]\s+", zeilen[i])
                or re.match(r"^\s*\d+\.\s+", zeilen[i])
            ):
                block.append(zeilen[i])
                i += 1
            raus.append(_liste(block, geordnet))
            continue

        # Absatz
        block = []
        while i < len(zeilen) and zeilen[i].strip():
            kandidat = zeilen[i]
            if (
                kandidat.strip().startswith(("```", ">", "#", "|"))
                or re.match(r"^\s*([-*+]|\d+\.)\s+", kandidat)
                or re.match(r"^\s*(-{3,}|\*{3,})\s*$", kandidat)
            ):
                break
            block.append(kandidat.strip())
            i += 1
        if block:
            raus.append(f"<p>{inline(' '.join(block))}</p>")
    return "\n".join(raus)


def seite(markdown: str, stil_pfad: str = "../style.css") -> str:
    erster = re.search(r"^#\s+(.*)$", markdown, re.M)
    titel = erster.group(1).strip() if erster else "Dokumentation"
    return RAHMEN.format(titel=html.escape(titel), pfad_zum_stil=stil_pfad, inhalt=konvertiere(markdown))


def main(argv: Optional[List[str]] = None) -> int:
    parsen = argparse.ArgumentParser(description="Markdown nach HTML, ohne Fremdbibliothek")
    parsen.add_argument("dateien", nargs="+")
    parsen.add_argument("-o", "--ausgabe", default=".", help="Zielordner")
    parsen.add_argument("--stil", default="mit", choices=("mit", "ohne"),
                        help="style.css mitschreiben")
    args = parsen.parse_args(argv)

    os.makedirs(args.ausgabe, exist_ok=True)
    for pfad in args.dateien:
        with open(pfad, "r", encoding="utf-8") as fh:
            markdown = fh.read()
        ziel = os.path.join(args.ausgabe, os.path.basename(pfad)[:-3] + ".html")
        with open(ziel, "w", encoding="utf-8") as fh:
            fh.write(seite(markdown))
        print(f"{pfad} -> {ziel}")
    if args.stil == "mit":
        stil_ziel = os.path.join(args.ausgabe, "doku-style.css")
        with open(stil_ziel, "w", encoding="utf-8") as fh:
            fh.write(STIL)
        print(f"(Stil geschrieben: {stil_ziel})")
    return 0


if __name__ == "__main__":
    sys.exit(main())