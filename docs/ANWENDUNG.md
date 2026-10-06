# Anwendung

## Installation

Es gibt nichts zu installieren. Repository klonen, `python3` aufrufen:

```bash
git clone https://github.com/noahkafemann/ai-agent-security.git
cd ai-agent-security
python3 agoris.py doctor
```

Voraussetzung: Linux mit Python ≥ 3.8. Für die volle Wirkung sollten die
Namespaces verfügbar sein (`doctor` sagt das).

## Erste Schritte

```bash
python3 agoris.py run "Lies 'aufgabe.md' und fasse zusammen."   # Demo
python3 agoris.py show research                                  # Policy ansehen
python3 agoris.py attacks                                        # 14 Versuche
python3 agoris.py verify runs/20261004-093743-minimal            # Log prüfen
```

Ein Lauf landet in `runs/<zeitstempel>-<policy>/`:

| Datei | Inhalt |
|---|---|
| `audit.jsonl` | jedes Ereignis mit Hashkette |
| `bericht.md` | lesbarer Bericht |
| `bericht.json` | dasselbe für Skripte |
| `jail/` | das aufgebaute Gefängnis-Dateisystem |
| `payload/agoris/` | Kopie der Runtime (read-only eingebunden) |

## Eigene Aufgaben

Eine Aufgabe ist eine Textdatei. Für `research` ist `/work` vorbelegt mit
`aufgabe.md`, `frage.md`, `notizen.txt`.

```bash
cat > aufgaben/meine.md <<'EOF'
1. Lies 'daten.csv' aus /work.
2. Berechne den Mittelwert je Spalte.
3. Schreibe das Ergebnis nach 'auswertung.md'.
EOF

python3 agoris.py run -p research -t aufgaben/meine.md
```

## Eigene Policies

Eine Policy ist ein JSON-Fragment — nicht vollständig. Fehlende Werte kommen
aus den Vorgaben in `agoris/policy.py`.

```json
{
  "name": "labor",
  "description": "Rechnen dürfen, Internet nur für zwei Domains",
  "filesystem": { "max_workspace_bytes": 104857600 },
  "process": { "cpu_seconds": 60, "memory_mb": 1024 },
  "network": {
    "mode": "proxy",
    "allowed_domains": ["python.org", "docs.python.org"],
    "deny_ports": [22, 3306, 5432]
  },
  "tools": { "enabled": ["read_file", "write_file", "list_dir", "run_python", "fetch_url", "finish"] },
  "model": { "max_steps": 20 }
}
```

Verwenden:

```bash
python3 agoris.py run "..." -p research -f labor.json    # Ergänzung
cp labor.json agoris/policies/labor.json                # eigene Policy
python3 agoris.py run "..." -p labor
```

### Was die Abschnitte bewirken

| Abschnitt | Schlüssel | Wirkung |
|---|---|---|
| `filesystem` | `writable` | Wurzeln, in die der Agent schreiben darf |
| | `read_only_mounts` | nur im Modus `system` |
| | `forbidden` | zusätzlich zur Fessel hart gesperrt |
| | `max_file_bytes` | `RLIMIT_FSIZE` und Werkzeuglimit |
| | `max_workspace_bytes` | Größe des Arbeits-tmpfs |
| `process` | `cpu_seconds` | `RLIMIT_CPU` |
| | `wall_seconds` | Wanduhr im Wirt |
| | `memory_mb` | `RLIMIT_AS`, `RLIMIT_DATA` |
| | `max_processes` | `RLIMIT_NPROC` |
| `network` | `mode` | `none` oder `proxy` |
| | `allowed_domains` | Positivliste; `*.beispiel.de` erlaubt Subdomains |
| | `deny_ports` | Ports, die der Proxy nie weitergibt |
| `system` | `namespaces` | welche Namespaces benutzt werden |
| | `jail_runtime` | `minimal` (nur Python) oder `system` |
| | `seccomp` | `false` schaltet die Schicht ab |
| `tools` | `enabled` | die Werkzeugliste — das ist eine Sicherheitsgrenze |
| `model` | `provider` | `simulated`, `echo`, `anthropic` |
| | `max_steps` | höchste Zahl von Modellanfragen |

Plausibilitätsprüfung: `user` und `mount` müssen in `namespaces` stehen, `finish`
muss in `enabled` sein, und `mode: proxy` verlangt mindestens eine erlaubte
Domain. Sonst bricht das Laden mit einer Meldung ab, statt still zu arbeiten.

## Eigenes Modell

```bash
export AGORIS_API_KEY="sk-..."
export AGORIS_MODEL="claude-sonnet-4-20250514"
python3 agoris.py run "..." -p research -m anthropic
```

Der Schlüssel bleibt im Wirt. Dass der Agent ihn nicht sieht, ist keine
Konfigurationsfrage, sondern wird im Angriffsbatterie-Ergebnis `key_leak`
geprüft.

Für einen eigenen Anbieter eine Funktion in `agoris/model.py` ergänzen und in
`PROVIDERS` eintragen:

```python
def _mein_anbieter(messages, tools):
    ...
    return {"text": '{"thought": "...", "tool": "finish", "args": {"answer": "..."}}'}

PROVIDERS["mein"] = _mein_anbieter
```

Ein Agent-Provider muss also nie im Gefängnis laufen — er wird vom Wirt
aufgerufen, bekommt die Konversation und gibt eine Antwort als JSON zurück.
Jeder Provider ist ein "Agent" in diesem Sinne.

Antwortformat: ein JSON-Objekt mit `thought`, `tool` und `args`. Was sich nicht
parsen lässt, landet als Text in `finish` — ein kaputtes Modell beendet den
Lauf, statt ihn hängen zu lassen.

## Verschiedene Agenten testen

Ein "Agent" in AGORIS ist die Kombination aus einer Policy (was er darf) und
einem Modell-Provider (wie er antwortet). AGORIS lässt sich damit testen,
ob die Isolation bei **jedem** Agenten hält.

### Schnelltest: alles auf einmal

```bash
python3 agoris.py test
```

Der Test-Harness prüft in vier Phasen:

1. **doctor** — ob dein Rechner die Namespaces und seccomp bereitstellt
2. **inspect** — Innenansicht bei jeder Policy
3. **run** — Agentenlauf mit jedem Provider (Standard: `simulated`, `echo`)
4. **attacks** — die vollständige Angriffsbatterie bei jeder Policy

### Gezielte Tests

```bash
python3 agoris.py test --provider simulated        # nur simulated-Provider
python3 agoris.py test --policy minimal            # nur minimal-Politik
python3 agoris.py test --only key_leak,cpu_bomb    # nur zwei Angriffe
```

Der Harness läuft auch direkt:

```bash
python3 tools/test_sandbox.py --provider simulated,echo --policy minimal
```

Beide Wege verwenden dasselbe Skript — `agoris.py test` ruft
`tools/test_sandbox.py` auf, denn das ist das zentrale Werkzeug für
Replizierbarkeit.

## Eigene Werkzeuge

Ein Werkzeug bekommt zwei Dinge: eine Policy (`tools.enabled`) und eine
Funktion in `agoris/runtime/tools.py`.

```python
def zaehle_zeilen(self, path: str = "", **_) -> Dict[str, Any]:
    real = _resolve(path)                      # Pfad-Fessel, nicht selbst bauen
    if not self.policy.path_readable(real):
        raise ToolError(f"'{path}' ist nicht lesbar")
    with open(real, encoding="utf-8") as fh:
        return {"ok": True, "path": path, "zeilen": sum(1 for _ in fh)}
```

Dann in `ToolBox._table` eintragen, in `agoris/model.py` ein Schema ergänzen
(sonst kennt das Modell das Werkzeug nicht) und in `DEFAULT_PODUCTS` in
`agoris/policy.py` erlauben.

Zwei Regeln:

1. **`_resolve()` benutzen.** Es prüft `realpath` gegen `/work`. Wer stattdessen
   `os.path.join` nimmt, baut ein Loch.
2. **Jeder Aufruf wird protokolliert.** `_table` erledigt das automatisch —
   auch Fehlschläge.

## Auswertung

`bericht.json` lässt sich direkt auswerten:

```python
import json, glob, collections

ergebnisse = []
for pfad in glob.glob("runs/*/angriffe.json"):
    daten = json.load(open(pfad))
    for e in daten["ergebnisse"]:
        eintraege = {"policy": daten["policy"], **e}
        eintraege["quelle"] = pfad
        ergebnisse.append(eintraege)

zusammen = collections.Counter(
    (e["policy"], e["status"]) for e in ergebnisse if e["status"] in ("blocked", "leaked", "gap")
)
for schluessel, anzahl in sorted(zusammen.items()):
    print(schluessel, anzahl)
```

Die Audit-Log-Dateien lassen sich mit `agoris.verify` oder direkt zeilenweise
auswerten — jede Zeile enthält `seq`, `event`, `actor`, `ts` und `hash`.

## Für die Schule

Die Anlage ist als Versuch aufgebaut, nicht als fertiges Produkt. Ein sinnvoller
Ablauf:

1. `doctor` — was kann dieser Rechner?
2. `attacks` — halten die Schichten?
3. Eine Policy verschärfen (`cpu_seconds: 5`) und den Lauf wiederholen.
4. Eine Policy lockern (Netz ohne Positivliste) und den Lauf wiederholen.
5. Den Bericht vergleichen: Was hat sich geändert, welche Schicht war wirksam?

Schritt 5 ist der eigentliche Lernmoment. Der Bericht benennt pro Schicht
`aktiv`/`inaktiv`, damit niemand eine Sicherheitsaussage mit einer Schicht
verbindet, die gar nicht lief.

## Bekannte Stellen

| Stelle | Verhalten | Umgehung |
|---|---|---|
| `seccomp` | `EINVAL` in vielen Containern | Schicht wird als inaktiv protokolliert |
| `RLIMIT_NPROC` | gilt nicht für uid 0 | AGORIS als Nicht-Root betreiben |
| `/proc`-Mount | `EPERM` in vielen Containern | unkritisch, PID-Namespace aktiv |
| HTTPS | nicht unterstützt | TLS-Terminierung im Wirt nötig |
| Kernel-Bugs | umgehen alles hier | das ist der Grund, warum das Ding ein Experiment ist |