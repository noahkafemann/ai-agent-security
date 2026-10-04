# Architektur

Dieses Dokument beschreibt, *warum* AGORIS so gebaut ist, wie es ist. Für die
Bedienung siehe [ANWENDUNG.md](ANWENDUNG.md), für die Messwerte
[VERSUCHSPROTOKOLL.md](VERSUCHSPROTOKOLL.md).

## Leitentscheidung

**Der Wirt entscheidet, nicht der Agent.**

Ein Sprachmodell bekommt Instruktionen als Text. Jede Zusicherung, die wir ihm
geben ("ignoriere das nicht", "nutze keine anderen Werkzeuge"), ist eine
Bitte. AGORIS setzt dagegen Grenzen, die keine Bitte beantworten müssen: Der
Prozess bekommt ein Dateisystem, das keine Wirtsdatei enthält; ein
Netz-Interface, das es nicht gibt; ein CPU-Konto, das endet.

Der Konflikt zwischen „der Agent ist unzuverlässig" und „der Agent muss arbeiten
können" löst sich dadurch, dass beides gleichzeitig wahr ist: Der Agent bekommt
genau das, was seine Aufgabe braucht — und nichts, was danach noch nützlich
wäre.

## Zwei Prozesse, ein Kanal

```
   WIRT                                    GEFÄNGNIS
   ┌──────────────────────────────┐        ┌────────────────────────┐
   │ Policy, Limits, Proxy,      │        │ PID 1: runtime/worker  │
   │ Modell-Broker, Audit        │        │   ├─ tools.py (5 Werkz.)│
   │                             │        │   └─ protocol.py       │
   │   fork()                    │        │                        │
   │      │                      │        │                        │
   │      ├── stdin  ◄───────────┼────────┤ schreibt               │
   │      └── stdout ───────────►┼────────┤ liest                  │
   └──────────────────────────────┘        └────────────────────────┘
```

Der Kanal ist ein Newline-JSON-Protokoll über zwei Pipes. Bemerkenswert: es
gibt *keinen* zweiten Weg in das Gefängnis. Kein Unix-Socket für Steuerbefehle,
kein gemeinsames Verzeichnis, keine Signal-Schnittstelle für Daten. Das ist
Absicht — jeder zusätzliche Kanal wäre eine zusätzliche Angriffsfläche.

### Warum der Modell-Broker im Wirt liegt

Der Agent muss das Modell befragen. Er darf aber den API-Schlüssel weder lesen
noch ausgeben. Deshalb schickt der Agent seine Konversation an den Wirt, der
daraus einen echten API-Aufruf macht:

```
Agent  → {"event": "llm_request", "messages": [...], "tools": [...]}
Wirt   → {"op": "llm_result", "response": {"text": "..."}}
```

Damit ist der Schlüssel eine Eigenschaft des Wirts, nicht eine Sache, die man
im Gefängnis „verstecken" könnte. Ein Angriff auf den Schlüssel ist kein
Angriff auf eine Datei, sondern ein Angriff auf einen Prozess, der ihn nie
ausgibt. Der Test `key_leak` prüft genau das: Er sucht die Umgebung des Agenten
ab und meldet jede Variable mit `KEY`, `TOKEN`, `SECRET` oder `PASSWORD`.

## Die Schichten

### 1. Namespaces

`unshare()` mit `CLONE_NEWUSER | CLONE_NEWNS | CLONE_NEWPID | CLONE_NEWNET |
CLONE_NEWIPC | CLONE_NEWUTS`.

Danach schreibt der Kindprozess seine ID-Zuordnung:

```
/proc/self/setgroups  = "deny"
/proc/self/uid_map     = "0 <uid> <n>"
/proc/self/gid_map     = "0 <gid> <n>"
```

Das ist der heikelste Moment. Eine breite Zuordnung (`65536` IDs) ist nur
erlaubt, wenn der Prozess im übergeordneten Namespace die Rechte dafür hat; sonst
`EPERM`. Deshalb versucht AGORIS zuerst breit, fällt auf eine einzelne ID
zurück und **protokolliert**, was geklappt hat. Eine stillschweigend
schmalere Zuordnung wäre eine falsche Sicherheitsaussage.

**Reihenfolge:** `uid_map` kann man erst schreiben, wenn der User-Namespace
existiert. Und `setuid` auf `nobody` muss *nach* dem Dateisystemaufbau
passieren, denn bis dahin braucht man Rechte, um zu mounten.

### 2. Dateisystem

Ein `tmpfs` als neue Wurzel, `chroot` hinein, `cwd = /work`.

Entscheidend ist, was *nicht* eingebunden wird. Der Modus `minimal` legt nur
drei Dinge hinein:

| Im Gefängnis | Im Wirt |
|---|---|
| `/usr/bin/python3` | Kopie des Interpreters |
| `/usr/lib/python3.x` | read-only Bind |
| `/usr/lib/x86_64-linux-gnu` | read-only Bind |
| `/lib64/ld-linux-x86-64.so.2` | read-only Bind |
| `/etc/*` | selbst erzeugt: passwd, group, hosts, nsswitch |
| `/dev/{null,zero,random,urandom}` | read-only Binds |
| `/proc`, `/tmp` | frische tmpfs-Mounts |
| `/opt/agoris` | Runtime, read-only |

Keine Shell. Kein `ls`. Kein `curl`. Das ist der Unterschied zu einem
Gefängnis, in dem das halbe Wirtssystem eingebunden ist: Hier kann der Agent
nicht einmal *fragen*, ob er etwas benutzen möchte — es ist nicht da.

Nach dem Aufbau wird die **Wurzel des Gefängnisses auf nur-lesbar gesetzt**
(`MS_REMOUNT|MS_RDONLY`). `/work` und `/tmp` sind eigene tmpfs-Mounts und bleiben
deshalb beschreibbar. Ohne diesen Schritt könnte der Agent sein eigenes
`/usr/bin/python3` austauschen — der Angriff `eigenes_python_ersetzen` prüft das.

Das `/etc` wird selbst erzeugt, statt den Wirt zu spiegeln. Es enthält keine
`passwd`-Einträge außer `root` und `nobody`, keine Namensauflösung und
ausdrücklich kein DNS.

`/proc` ist optional: In vielen Container-Umgebungen verbietet der Kernel das
Mounten eines frischen procfs (`EPERM`). Ohne procfs sieht der Agent nichts
Schlimmes — der PID-Namespace sorgt dafür, dass es dort ohnehin keine fremden
Prozesse zu sehen gibt.

### 3. Rechte

Drei Schritte, in dieser Reihenfolge:

1. `prctl(PR_SET_NO_NEW_PRIVS, 1)` — kein `execve` kann mehr Rechte aufstocken.
2. Alle Capabilities aus dem Bounding-Set werfen (`PR_CAPBSET_DROP`, 0..40).
3. `capset` mit leeren Mengen — die aktiven Capabilities ebenfalls leeren.

Schritt 2 und 3 sind getrennt nötig. Der Bounding-Set bestimmt, was ein
`execve` *erwerben* kann; die aktiven Capabilities bestimmen, was *jetzt* gilt.
Erst nach einem `execve` ist die Permitted-Menge kleiner als der Bounding-Set —
deshalb schließt sich die Lücke beim Start des Agenten automatisch.

**Der uid-0-Fall:** Läuft der Wirt als root, ist der Prozess im neuen
Namespace uid 0 (bei schmaler Zuordnung). uid 0 ohne Capabilities kann nichts,
was normale Benutzer nicht können — aber `RLIMIT_NPROC` gilt für uid 0 nicht.
Das ist eine echte Lücke und steht als `gap` in der Angriffsbatterie, wenn sie
sich zeigt.

### 4. Ressourcen

| Grenze | Wert (`minimal`) | Wirkung |
|---|---|---|
| `RLIMIT_CPU` | 5 s | SIGXCPU, dann SIGKILL |
| `RLIMIT_AS` | 128 MB | Adressraum begrenzt |
| `RLIMIT_DATA` | 128 MB | Daten-Segment begrenzt |
| `RLIMIT_FSIZE` | 256 KiB | keine großen Dateien |
| `RLIMIT_NPROC` | 16 | keine Prozess-Flut |
| `RLIMIT_NOFILE` | 64 | keine Datei-Flut |
| `RLIMIT_CORE` | 0 | kein Core-Dump im Wirts-Dateisystem |

Gesetzt werden sie **vor** dem `execve`. Sonst könnte der Agent beim Start
seine eigenen Grenzen aufheben.

Fallstrick: `RLIM_INFINITY` ist `-1`. `min(grenzwert, RLIM_INFINITY)` ergibt
`-1` — man hebt die Grenze also auf, statt sie zu setzen. Deshalb wird
zuerst geprüft, ob die harte Grenze `RLIM_INFINITY` ist.

`RLIMIT_CPU` und `RLIMIT_NPROC` sind nicht das gleiche wie eine Wanduhr: Der
Agent kann hängen, ohne CPU zu verbrauchen (z. B. `select` auf einem Socket).
Dafür gibt es im Wirt zusätzlich die `wall_seconds` der Policy.

### 5. seccomp-BPF

Ein klassisches BPF-Programm, per `prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER)`
eingereicht:

1. Architektur prüfen (`AUDIT_ARCH_X86_64` / `AARCH64`), sonst `KILL`.
2. `A = Syscall-Nummer`
3. `clone` mit `CLONE_NEW*`-Flaggen → `EPERM`
4. Sperrliste → `EPERM` (`clone3` → `ENOSYS`)
5. alles andere → `ALLOW`

Zwei Details mit Absicht:

- **`clone3` gibt `ENOSYS`, nicht `EPERM`.** Die glibc fällt bei `ENOSYS` auf
  `clone` zurück. Mit `EPERM` wäre jeder `subprocess`-Aufruf tot — die
  Anlage wäre sicher, aber kaputt. Sicherheit durch Unbrauchbarkeit ist kein
  Ergebnis.
- **`prctl` steht auf der Liste.** Damit kann der Agent `PR_SET_SECCOMP`,
  `PR_SET_PTRACER` und die Capability-Manipulation nicht selbst aufrufen.

**Wenn seccomp nicht verfügbar ist**, gibt `prctl` hier `EINVAL` (22). In
Container-Umgebungen ist das häufig (z. B. wenn `seccomp` in `/proc` nicht
aktiv ist). AGORIS protokolliert dann Grund und Schicht als inaktiv und wertet
den Lauf als eingeschränkt. Eine Sicherheitsschicht, die stillschweigend
fehlt, wäre schlimmer als eine, die fehlt.

### 6. Netz

Der Netz-Namespace startet mit genau einem Interface: `lo`, ausgeschaltet.
AGORIS schaltet es hoch (`SIOCSIFFLAGS`) — ohne das scheitern manche
Socket-Operationen mit `ENOTCONN`, was die Fehlersuche unnötig erschwert.
Für eine Verbindung nach draußen reicht das nicht; dafür ist ein geroutetes
Interface nötig, und davon gibt es keins.

Der einzige Weg draußen ist der Unix-Socket `/run/agoris/proxy.sock`, read-only
aus dem Wirt eingebunden. Der Proxy entscheidet:

| Prüfung | Beispiel |
|---|---|
| Methode | nur `GET` |
| Schema | nur `http://` |
| Host | Positivliste der Policy |
| Port | nicht auf der Sperrliste |
| Größe | `max_bytes_per_task` |

Wichtig: Der Proxy prüft das **unabhängig** vom Werkzeugcode. Selbst wenn ein
manipulierter Agent `fetch_url` umgeht, kann der Proxy nichts weiterreichen, was
nicht auf der Positivliste steht. Zwei Schichten, eine Wahrheit.

Fehlermeldungen sind absichtlich *aufschlussreich* (`BLOCKIERT von der
Sandbox-Policy: Port 22 steht auf der Sperrliste`): Ein Schüler soll aus einem
blockierten Versuch lernen können, nicht raten müssen.

## Fehler, die beim Bauen passiert sind

Diese Liste ist Teil der Dokumentation, weil sie zeigt, dass die Anlage
getestet und nicht nur entworfen wurde.

| Fehler | Symptom | Ursache |
|---|---|---|
| Breite ID-Zuordnung | `EPERM` beim Schreiben von `uid_map` | Rechte im übergeordneten Namespace fehlen |
| tmpfs-Optionen | `EINVAL` beim Mount | `nosuid,nodev` gehören in die Flags, nicht in `size=…` |
| Bind-Mount Remount | `ENODEV` | `MS_REC` auf einem Bind funktioniert nicht wie erwartet |
| Bind auf Datei | `ENOTDIR` | Ziel muss selbst eine Datei sein, kein Verzeichnis |
| Socket-Pfad | `AF_UNIX path too long` | Unix-Sockets: max. 108 Zeichen |
| Socket-Quelle | `ENOENT` | Jail-Pfad als Mount-Quelle statt Host-Pfad |
| `sock_fprog` | `EINVAL` | `argtypes` auf `c_ulong` setzen, `ctypes.addressof()` übergeben |
| `RLIM_INFINITY` | Grenze aufgehoben statt gesetzt | `-1` ist kleiner als jeder Wert |
| Payload unsichtbar | `ENOENT` nach dem Mount | Ziel lag *innerhalb* des Jail-Roots |
| Pipe-Voll | Wirt wartet endlos | Pipes müssen *während* des Laufs gelesen werden |

Der letzte Punkt ist kein Detail: Der klassische Fehler ist `fork`, dann
`read()` vom Kind blockierend. Ein Kind, das 200 KiB schreibt, läuft in einen
64-KiB-Puffer und wartet — während der Wirt auf das Kind wartet.

## Warum kein Docker und kein gVisor

Eine Container-Lösung wäre weniger Code. Aber:

- **Docker braucht einen Daemon und Rechte**, die hier nicht vorausgesetzt sind.
- **gVisor braucht einen eigenen Kernel** — er löst das Problem, indem er alles
  neu macht. Das ist keine Abhängigkeit, die man in einer Schulumgebung
  einführen sollte.
- **Namespaces direkt aufzurufen** macht jede einzelne Schicht sichtbar. Für
  jemanden, der verstehen will, *warum* etwas sicher ist, ist das der
  Unterschied zwischen Beweis und Behauptung.

Der Preis ist ehrlich: AGORIS ist weniger erprobt als Docker. Genau deshalb
protokolliert es jede Schicht, jede Fehlmeldung und jeden gescheiterten
Angriff.

## Verzeichniszuordnung

| Im Gefängnis | Herkunft |
|---|---|
| `/` | tmpfs, **nach dem Aufbau auf nur-lesbar** |
| `/work` | eigenes tmpfs — einziger beschreibbarer Arbeitsbereich |
| `/tmp` | eigenes tmpfs, 8 MiB |
| `/opt/agoris` | Kopie aus `runs/<lauf>/payload`, read-only |
| `/run/agoris/proxy.sock` | Bind aus `/tmp/agoris-<pid>-<hash>/proxy.sock` |
| `/usr/bin/python3` | Kopie des Wirt-Interpreters |
| `/etc` | selbst erzeugt, kein Wirts-Inhalt |
| `/tmp` | eigene tmpfs, 8 MiB |

`/opt/agoris` ist read-only, weil dort die Werkzeuge liegen. Ein Agent, der
`tools.py` umschreibt, hat sonst das Problem gelöst, seinen eigenen Wächter
abzuschalten — deshalb prüft der Test `write_readonly` zusätzlich **vom Wirt
aus**, ob die Datei im Host-Baum auftaucht.