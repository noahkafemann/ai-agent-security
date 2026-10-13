# Sandbox-Performance messen (Benchmark)

AGORIS enthält ab Version 1.1 einen eingebauten Benchmark-Befehl, der misst,
wie stark die Sandbox-Schichten (Namespaces, chroot, seccomp, Ressourcenlimits,
Proxy) die Ausführungsgeschwindigkeit des Agenten beeinflussen.

## Warum ein Benchmark?

Eine Sandbox kostet Leistung. Jede Sicherheitsschicht braucht Zeit beim Aufbau
und fügt Overhead hinzu. Der Benchmark beantwortet die Frage:

> **Wie viel Kapazität (CPU-Zeit) verlangt die Sandbox vom Agenten?**

Das ist wichtig für:
- **Planung**: Wie lange darf ein Agent rechnen, wenn die Sandbox 15% Overhead hat?
- **Policy-Design**: Lohnt sich `seccomp: false` für Performance?
- **Vergleich**: Welche Schicht kostet wie viel?

## Befehl

```bash
# Standard-Benchmark (Policy minimal, 5 Iterationen, 1 Warmup)
python3 agoris.py benchmark

# Mit eigener Policy
python3 agoris.py benchmark -p research

# Mehr Wiederholungen für genauere Werte
python3 agoris.py benchmark -i 10 -w 2

# Eigener Benchmark-Code
python3 agoris.py benchmark -c "import math; sum(math.sin(i) for i in range(1000000))"

# Verbose: Zeigt den Benchmark-Code an
python3 agoris.py benchmark -v
```

## Parameter

| Parameter | Kurz | Standard | Beschreibung |
|---|---|---|---|
| `--policy` | `-p` | `minimal` | Policy für den Sandbox-Lauf |
| `--iterations` | `-i` | `5` | Messwiederholungen pro Modus (nativ + Sandbox) |
| `--warmup` | `-w` | `1` | Warmup-Läufe (werden nicht gewertet) |
| `--code` | `-c` | (siehe unten) | Eigener Benchmark-Code als String |
| `--verbose` | `-v` | `false` | Benchmark-Code anzeigen |

## Standard-Benchmark-Code

Falls kein `-c` angegeben wird, nutzt AGORIS diesen CPU-lastigen Code:

```python
import time, math
start = time.time()
x = 0.0
for i in range(500000):
    x += math.sin(i) * math.cos(i)
print(f'Loops: 500000, Result: {x:.6f}, Time: {time.time()-start:.3f}s')
```

Der Code ist bewusst **rechenlastig** (kein I/O, kein Netz), um den reinen
CPU-Overhead der Sandbox zu messen. I/O-lastige Aufgaben würden andere
Engpässe zeigen.

## Ausgabe verstehen

```
AGORIS - sichere Umgebung fuer unzuverlaessige KI-Agenten
Sandbox-Benchmark (Policy 'minimal')
Wiederholungen: 5  |  Warmup: 1
Ordner: runs/20261013-123456-benchmark-minimal
------------------------------------------------------------
Nativ (keine Sandbox):     0.234s  (min: 0.228s, max: 0.241s)
Im Sandbox:                0.258s  (min: 0.251s, max: 0.267s)
Overhead:                  10.3%
------------------------------------------------------------
Aktive Schichten:   namespaces, id_maps, filesystem, loopback, chroot,
                    privileges, capabilities, rlimits
Inaktive Schichten: seccomp
------------------------------------------------------------
Interpretation:
  Moderater Overhead (5-20%) - Für die meisten Aufgaben vernachlässigbar.

Hinweis: Der Overhead besteht aus:
  - Namespace-Aufbau (unshare, ID-Mapping)
  - Dateisystem-Aufbau (tmpfs, Mounts, chroot)
  - Rechte-Entzug (Capabilities, no_new_privs)
  - Ressourcen-Limits (setrlimit)
  - seccomp-Filter (BPF-Programm, falls aktiv)
  - Proxy-Start (falls Netz-Policy aktiv)
```

### Werte lesen

- **Nativ**: Code läuft direkt im Host-Prozess (fork aber ohne Namespaces/chroot)
- **Im Sandbox**: Voller AGORIS-Durchlauf mit allen aktiven Schichten
- **Overhead**: `(Sandbox - Nativ) / Nativ * 100`
- **Min/Max**: Streuung über die Iterationen (Jitter messen)

## Interpretation der Overhead-Werte

| Overhead | Bedeutung |
|---|---|
| **< 5%** | Gering. Sandbox kostet kaum Leistung. |
| **5–20%** | Moderat. Für die meisten Aufgaben vernachlässigbar. |
| **20–50%** | Deutlich. Bei CPU-lastigen Aufgaben spürbar. |
| **> 50%** | Hoch. Prüfen, ob alle Schichten nötig sind. Tipp: `seccomp: false` reduziert Overhead stark. |

## Was der Overhead wirklich kostet

Der Benchmark misst **Gesamt-Overhead** = Summe aller Schichten. Zum Aufschlüsseln:

```bash
# 1. Nur Namespaces + chroot (kein seccomp, keine Limits)
python3 agoris.py benchmark -p minimal -f '{"system":{"seccomp":false,"namespaces":["user","mount","pid","net"]}}'

# 2. Mit seccomp
python3 agoris.py benchmark -p minimal

# 3. research-Policy (mit Proxy)
python3 agoris.py benchmark -p research
```

Typische Aufschlüsselung (Linux 6.x, x86_64, Policy `minimal`):

| Schicht | Ca. Overhead |
|---|---|
| Namespaces + ID-Mapping | 2–5% |
| Dateisystem (tmpfs, mounts, chroot) | 3–8% |
| Rechte (Capabilities, no_new_privs) | 1–3% |
| Ressourcen-Limits (setrlimit) | < 1% |
| **seccomp (falls aktiv)** | **5–15%** |
| Proxy (Policy `research`) | 1–3% |

> **Hinweis:** Die Werte hängen stark vom Kernel, der Hardware und der
> Last auf dem Host ab. Der Benchmark misst *deinen* Rechner, nicht
> Durchschnittswerte.

## In der Policy steuern

Die Policy steuert, welche Schichten aktiv sind — und damit den Overhead:

```json
{
  "system": {
    "seccomp": false,
    "namespaces": ["user", "mount", "pid", "net"]
  }
}
```

- `seccomp: false` — spart 5–15% Overhead, verliert aber die
  Syscall-Sperrliste (Angriffe 10, 11, 12 in der Batterie werden zu `gap`)
- Weniger Namespaces — spart wenig, schwächt Isolation massiv
- `research`-Policy — Proxy fügt ~2% hinzu, ermöglicht aber Netzzugriff

## Für die Dokumentation / den Bericht

Der Benchmark schreibt Details in den Lauf-Ordner:

```
runs/20261013-123456-benchmark-minimal/
├── audit.jsonl           # Benchmark-Einträge mit Hashkette
├── benchmark.json        # Maschinenlesbares Ergebnis
└── benchmark.md          # Lesbarer Bericht
```

`benchmark.json` enthält:
```json
{
  "name": "sandbox_overhead",
  "native_time": 0.234,
  "sandbox_time": 0.258,
  "overhead_percent": 10.3,
  "details": {
    "iterations": 5,
    "native_times": [0.228, 0.231, 0.234, 0.238, 0.241],
    "sandbox_times": [0.251, 0.255, 0.258, 0.262, 0.267],
    "active_layers": ["namespaces", "id_maps", ...],
    "inactive_layers": ["seccomp"]
  }
}
```

## In Makefile / Skripten

```bash
make benchmark           # lokal auf Linux
make docker-benchmark    # im Docker-Container
.\run.ps1 benchmark      # Windows (WSL2/Docker)
```

## Zusammenfassung

| Frage | Antwort |
|---|---|
| Was misst der Benchmark? | CPU-Overhead der Sandbox-Schichten |
| Was ist der Vergleich? | Gleicher Code: nativ (Host) vs. im Sandbox |
| Wie oft wird gemessen? | Standard: 5x pro Modus + 1 Warmup |
| Wo steht das Ergebnis? | Konsole + `runs/*/benchmark.json` |
| Kann ich eigenen Code testen? | Ja, mit `-c "code"` |
| Was tun bei hohem Overhead? | `seccomp: false` in Policy, oder Hardware prüfen |

Der Benchmark ist **Teil der Sicherheitsbewertung**: Er zeigt, ob die Isolation
akzeptablen Performance-Preis hat — oder ob man Schichten abwägen muss.