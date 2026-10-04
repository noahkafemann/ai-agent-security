# AGORIS

**Eine sichere Umgebung für unzuverlässige KI-Agenten.**

> Was ein Agent darf, entscheidet der Wirt — nicht der Agent.

AGORIS ist kein Chatbot und kein Agenten-Framework. Es ist das *Gehäuse*, in
dem ein Agent laufen darf, ohne dem System zu schaden: ohne Wirts-Dateien, ohne
API-Schlüssel, ohne Netzweg, ohne mehr Rechenzeit und Speicher, als die Policy
vorsieht.

Nur Standardbibliothek. Python ≥ 3.8. Kein Docker, kein `pip`, kein `gcc`.

```bash
python3 agoris.py doctor                 # prüfen, was der Rechner kann
python3 agoris.py run "Aufgabe" -p research
python3 agoris.py attacks                # 13 Ausbruchversuche
python3 agoris.py verify runs/<lauf>     # Audit-Hashkette prüfen
```

Ohne Argumente startet ein Demo-Lauf mit der Policy `minimal`.

---

## Die Grundidee

Ein Sprachmodell kann Anweisungen befolgen, die ihm jemand anderes eingibt.
Diese Anweisungen landen als Text im Systemprompt. Damit ist der Agent so
zuverlässig wie sein schlechtester Instruktiongeber — und ein Angreifer, der
Inhalte einspeist (Webseite, PDF, Datenbank), schreibt indirekt mit.

Man kann das mit noch mehr Prompting bekämpfen. Man kann es auch *baulich*
begrenzen:

| | Wirt | Gefängnis |
|---|---|---|
| API-Schlüssel | ✓ | — |
| Netzwerk | nur über den Richtlinien-Proxy | kein Interface |
| Dateisystem | vollständig | eigenes tmpfs, `/work` |
| Prozesse | überwacht | eigener PID-Namespace, PID 1 |
| Rechenzeit | gesetzt vor dem Start | RLIMIT_CPU |
| Was protokolliert wird | alles | nichts davon ist manipulationssicher |

Der Agent bekommt nicht die Erlaubnis, sondern bleibt einfach an einer Stelle:
sein Arbeitsverzeichnis.

---

## Aufbau

```
                    WIRT  (vertrauenswürdig)
   ┌───────────────────────────────────────────────┐
   │  policy.py    was erlaubt ist                  │
   │  limits.py    Ressourcengrenzen                │
   │  proxy.py     einziger Weg nach draußen        │
   │  model.py     hält den API-Schlüssel           │
   │  audit.py     JSONL + SHA-256-Hashkette        │
   │                                               │
   │   fork() ── zwei Pipes, ein Protokoll ────┐   │
   └───────────────────────────────────────────┼───┘
                                               │
   ┌───────────────────────────────────────────┼───┐
   │  GEFÄNGNIS  (der Agent, kompromittiert)   │   │
   │  user | mount | pid | net | ipc | uts     ▼   │
   │  chroot → no_new_privs → rlimits → caps → seccomp
   │  /work   nur beschreibbar                 │
   │  /opt/agoris  nur lesbar (Runtime)        │
   │  /run/agoris/proxy.sock  (Eingang, nicht Ausgang) │
   │  runtime/worker.py  = der Agent-Loop      │
   └───────────────────────────────────────────────┘
```

### Schichten, in dieser Reihenfolge

1. **Namespaces** — `unshare()` für user, mount, pid, net, ipc, uts.
   *Danach* die ID-Zuordnung (`uid_map`/`gid_map`): vorher gibt es keine Datei,
   in die man schreiben könnte. Die Rechteabgabe kommt ans **Ende** — sie wird
   zum Schreiben der Zuordnung und zum Aufbau des Dateisystems gebraucht.
2. **Dateisystem** — eigenes `tmpfs` als Wurzel, `chroot` hinein. Im Modus
   `minimal` wird nur das eingebunden, was der Agent wirklich braucht: Python,
   die Standardbibliothek, der Loader. **Keine Shell, keine Standardprogramme.**
3. **Rechte** — `PR_SET_NO_NEW_PRIVS`, danach werden *alle* Capabilities aus
   dem Bounding-Set geworfen und `capset` geleert. Läuft der Wirt als root,
   ist der Prozess im Namespace zwar uid 0 — aber ohne Capabilities ist uid 0
   harmlos.
4. **Ressourcen** — `RLIMIT_CPU`, `AS`, `DATA`, `FSIZE`, `NPROC`, `NOFILE`, `CORE`.
   Gesetzt **vor** dem Start des Agenten, damit er sich nichts selbst befreien kann.
5. **seccomp-BPF** — Syscall-Sperrliste: `ptrace`, `mount`, `pivot_root`,
   `init_module`, `kexec_load`, `bpf`, `process_vm_*`, `setns`, `unshare` …
   Zusätzlich ist `clone` mit `CLONE_NEW*`-Flaggen verboten, `clone3` gibt
   `ENOSYS` (damit glibc auf `clone` zurückfällt und `subprocess` nicht stirbt).
6. **Netz** — kein Interface außer einem ausgeschalteten Loopback. Der einzige
   Weg draußen ist der Proxy-Socket, und der entscheidet nach Policy.

### Reihenfolge nicht ändern

`unshare` → `uid_map`/`gid_map` → Dateisystem → `chroot` → `no_new_privs` →
`rlimits` → Capabilities → seccomp → `exec`.

Diese Reihenfolge ist keine Geschmackssache. Jede andere ergibt entweder
`EPERM`, eine unsichtbare Zuordnung oder ein Gefängnis, in dem der Agent sich
selbst die Rechte zurückgeben kann.

---

## Policies

Policies sind JSON unter `agoris/policies/`. Jede wird **an zwei Stellen**
durchgesetzt — einmal im Wirt (Ressourcen, Proxy), einmal im Gefängnis
(Pfad-Fessel, Werkzeug-Filter). Fällt eine Schicht aus, trägt die andere.

| Policy | Netz | Rechenzeit | Werkzeuge |
|---|---|---|---|
| `minimal` | keins | 5 s / 128 MB | lesen, schreiben, Python, `finish` |
| `research` | Proxy, Positivliste | 20 s / 512 MB | zusätzlich `fetch_url` |

```bash
python3 agoris.py show research
python3 agoris.py run "Recherchiere X" -p research -f meine_erweiterung.json
```

---

## Werkzeuge des Agenten

| Werkzeug | Grenze |
|---|---|
| `read_file` | unterhalb von `/work`, `realpath` geprüft |
| `write_file` | nur `/work` und `/tmp`, Größenlimit |
| `list_dir` | unterhalb von `/work` |
| `run_python` | Subprozess, kein Netz, unter denselben Limits |
| `fetch_url` | nur über den Proxy, nur Positivliste |
| `finish` | beendet den Lauf |

Alles andere existiert nicht. Die Werkzeugliste wird vom Wirt vorgegeben — ein
Modell kann sie nicht erweitern, auch wenn es das behauptet.

---

## Messen statt behaupten

`python3 agoris.py attacks` führt dreizehn Ausbruchversuche aus. Jeder Versuch
bekommt vom Wirt eine **Kanariendatei** mit geheimem Inhalt: sie liegt im
Arbeitsverzeichnis des Wirts, und wer sie liest, ist wirklich ausgebrochen.
Zusätzlich prüft der Wirt*nach* dem Lauf selbst nach, ob Dateien im Host-Baum
entstanden sind — eine Meldung des Agenten wird nicht geglaubt.

Ergebnis auf einem Linux 6.18 / x86_64, Lauf als root, Policy `minimal`:

```
gehalten 13/13  |  durchgekommen 0  |  Luecken 0
Schichten inaktiv: seccomp
```

Was die Status bedeuten:

- `blocked` — die Schicht hat gehalten. Für die Anlage ist das der Erfolg.
- `leaked` — der Agent kam durch. Ein echter Fund, ein Fehler in der Anlage.
- `gap` — kein Ausbruch, aber eine Schicht griff nicht (z. B. `RLIMIT_NPROC`
  für uid 0). Wird getrennt ausgewiesen, damit die Sicherheit nicht
  überschätzt wird.
- `error` — keine auswertbare Antwort.

Ein geblockter Versuch sieht zum Beispiel so aus:

| Versuch | Beobachtung | Schicht |
|---|---|---|
| `direct_socket` | `connect()` → Fehler | Netz-Namespace |
| `cpu_bomb` | Signal 24 (SIGXCPU) nach 5,0 s | RLIMIT_CPU |
| `memory_bomb` | `MemoryError` | RLIMIT_AS |
| `fork_bomb` | `fork()` → `ENOMEM` nach 3 Kindern | RLIMIT_NPROC |
| `write_readonly` | `EROFS` auf `/opt/agoris` | read-only Mount |
| `ptrace_escape` | `EPERM` | Rechte / seccomp |
| `host_canary` | Kanarie unerreichbar | chroot + Mount-Namespace |

---

## Das Audit-Log

Jede Zeile in `runs/<lauf>/audit.jsonl` enthält den Hash der vorherigen Zeile.
Jede nachträgliche Änderung an der Datei bricht die Kette:

```bash
python3 agoris.py verify runs/20261004-093743-minimal
# Hashkette gueltig: True (12 Eintraege, keine Probleme)
```

Der Wirt protokolliert auch den *gescheiterten* Zugriff. Ein blockierter
Versuch ist eine Information, keine Ausnahme vom Protokoll.

---

## Ehrliche Grenzen

Diese Anlage ist ein **Experiment**, kein zertifizierter Sandbox-Ersatz.

- **Nicht jede Schicht ist überall verfügbar.** In manchen Container-Umgebungen
  lehnt der Kernel `prctl(PR_SET_SECCOMP)` mit `EINVAL` ab. AGORIS schreibt
  das ins Log und wertet den Lauf als *eingeschränkt* — statt die Lücke zu
  verschweigen. Im Testlauf oben war genau das der Fall: 13/13 gehalten,
  seccomp inaktiv.
- **Kein Ersatz für Container oder VM.** Namespaces teilen sich den Kernel.
  Ein Kernel-Bug ist ein Ausbruch aus allem, was hier steht.
- **Der Agent darf als uid 0 laufen**, wenn der Wirt root ist. Die Capabilities
  sind dann weg, aber `RLIMIT_NPROC` gilt für root nicht. Abhilfe: AGORIS als
  eigenen Nicht-Root-Benutzer betreiben.
- **Der Proxy ist HTTP.** Kein TLS, also keine HTTPS-Domains. Wer HTTPS
  braucht, braucht Terminisierung im Wirt.
- **Nur was der Wirt kann, ist sicher.** AGORIS kennt sich selbst nicht — es
  kennt nur die Rechte, die der Wirt übergibt.

---

## Aufbau der Dateien

```
agoris.py               Startpunkt
agoris/
  policy.py             Policy-Engine, Pfad- und Domain-Prüfung
  limits.py             RLIMIT_CPU/AS/FSIZE/NPROC/…
  audit.py              JSONL mit SHA-256-Hashkette
  proxy.py              Richtlinien-Proxy (nur GET, Positivliste)
  model.py              Modell-Broker, hält den API-Schlüssel
  jail.py               Namespaces, chroot, Rechte, Dateisystem
  seccomp.py            BPF-Programm und Sperrliste
  launcher.py           fork, Pipes, Modell-Antworten, Lebensdauer
  attacks.py            13 Ausbruchversuche mit Messprotokoll
  report.py             Markdown- und JSON-Berichte
  cli.py                Kommandozeile
  policies/             minimal.json, research.json
  runtime/              läuft im Gefängnis
    worker.py           der Agent-Loop
    tools.py            Werkzeuge und Pfad-Fessel
    protocol.py         der einzige Kanal nach draußen
docs/                   Architektur und Versuchsprotokoll
website/                statische Seite
```

## Weitere Dokumentation

- [`docs/ARCHITEKTUR.md`](docs/ARCHITEKTUR.md) — Schichten im Detail, Fehler und Grenzen
- [`docs/VERSUCHSPROTOKOLL.md`](docs/VERSUCHSPROTOKOLL.md) — Aufbau, Messwerte, Auswertung
- [`docs/ANWENDUNG.md`](docs/ANWENDUNG.md) — Policies schreiben, eigene Werkzeuge, Auswertung

## Lizenz

MIT