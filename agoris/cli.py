"""Kommandozeile fuer AGORIS.

    python3 agoris.py doctor              Umgebung pruefen
    python3 agoris.py policies            verfuegbare Policies zeigen
    python3 agoris.py show research       eine Policy im Detail
    python3 agoris.py run "Aufgabe" -p research
    python3 agoris.py attacks             Angriffsbatterie ausfuehren
    python3 agoris.py verify runs/<name>  Audit-Hashkette pruefen

Ohne Argumente startet ein kleiner Demo-Lauf mit der Policy ``minimal`` - so
sieht man die Anlage funktionieren, ohne sie einrichten zu muessen.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time
from typing import Any, Dict, List, Optional

from . import attacks as attacks_mod
from . import report as report_mod
from . import seccomp as seccomp_mod
from .audit import AuditLog
from .launcher import run_agent, run_snippet
from .policy import Policy, _deep_merge

RESULTS_DIR = "runs"
BANNER = "AGORIS - sichere Umgebung fuer unzuverlaessige KI-Agenten"


# --------------------------------------------------------------------- doctor
def doctor(args: argparse.Namespace = None) -> int:
    print(BANNER)
    print("=" * len(BANNER))
    print(f"Python           {platform.python_version()} ({sys.executable})")
    print(f"Plattform        {platform.system()} {platform.release()} / {platform.machine()}")
    print(f"Benutzer         uid={os.getuid()} gid={os.getgid()}"
          f"{'  (root!)' if os.getuid() == 0 else ''}")

    names = Policy.available()
    print(f"Policies         {', '.join(names) if names else '(keine gefunden)'}")

    benoetigt = ["user", "mount", "pid", "net"]
    try:
        with open("/proc/self/uid_map") as fh:
            uid_map = fh.read().strip()
        print(f"uid_map          {uid_map}")
    except OSError as exc:
        uid_map = f"nicht lesbar ({exc})"
    with open("/proc/sys/user/max_user_namespaces") as fh:
        print(f"max_user_ns      {fh.read().strip()}")
    for pfad in ("/usr/bin/python3", "/lib64", "/usr/lib"):
        zustand = "vorhanden" if os.path.exists(pfad) else "FEHLT"
        print(f"{pfad:<18}{zustand}")

    print()
    print("Namespaces:")
    flags = {
        "user": 0x10000000, "mount": 0x00020000, "pid": 0x20000000,
        "net": 0x40000000, "ipc": 0x08000000, "uts": 0x04000000,
    }
    import ctypes

    libc = ctypes.CDLL("libc.so.6", use_errno=True)
    libc.unshare.restype = ctypes.c_int
    libc.unshare.argtypes = [ctypes.c_int]
    for name in benoetigt:
        pid = os.fork()
        if pid == 0:
            ctypes.set_errno(0)
            rc = libc.unshare(flags[name])
            err = ctypes.get_errno()
            os._exit(0 if rc == 0 else min(err, 120))
        _pid, status = os.waitpid(pid, 0)
        code = os.WEXITSTATUS(status)
        print(f"  {name:<8}{'moeglich' if code == 0 else f'nein (errno {code})'}")

    print()
    print("seccomp:")
    versuch = seccomp_mod.build_program(seccomp_mod.blocked_syscalls(), seccomp_mod.audit_arch())
    print(f"  Filterprogramm    {len(versuch)} Bytes, {len(seccomp_mod.blocked_syscalls())} gesperrte Syscalls")
    print(f"  Gesperrt          {', '.join(seccomp_mod.describe())}")
    if not seccomp_mod.set_no_new_privs():
        print("  Hinweis           PR_SET_NO_NEW_PRIVS nicht moeglich - Filter wird voraussichtlich abgelehnt")
    else:
        print("  no_new_privs      setzbar")

    print()
    print("Werkzeuge im Wirt (nur zur Info, AGORIS braucht sie nicht):")
    for werkzeug, kommando in (("ip", "ip"), ("ss", "ss"), ("docker", "docker"), ("gcc", "gcc")):
        print(f"  {werkzeug:<8}{'vorhanden' if os.path.exists(f'/usr/bin/{kommando}') or os.path.exists(f'/usr/sbin/{kommando}') else 'fehlt (wird nicht gebraucht)'}")

    print()
    print("Hinweis: Ohne root sind die Namespaces ueblicherweise nicht zugaenglich.")
    print("AGORIS laeuft dann zwar, aber ohne wirksame Isolation - bitte nicht")
    print("als Beleg fuer Sicherheit werten.")
    return 0


# ------------------------------------------------------------------- policies
def cmd_policies(args: argparse.Namespace) -> int:
    for name in Policy.available():
        policy = Policy.load(name)
        beschreibung = policy.description or "(ohne Beschreibung)"
        print(f"{name:<12} v{policy.version}  {policy.network['mode']:<6} {beschreibung}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    policy = Policy.load(args.policy)
    if args.json:
        print(json.dumps(policy.summary(), indent=2, ensure_ascii=False))
        return 0
    print(f"Policy '{policy.name}' v{policy.version}")
    print(f"  aus           {policy.source}")
    print(f"  Beschreibung  {policy.description or '-'}")
    print("  Dateisystem")
    print(f"    schreibbar    {policy.filesystem['writable']}")
    print(f"    nur lesbar    {policy.filesystem['read_only_mounts']}")
    print(f"    verboten      {len(policy.filesystem['forbidden'])} Pfade")
    print(f"    max. Datei     {policy.filesystem['max_file_bytes']} B")
    print(f"    max. Arbeits   {policy.filesystem['max_workspace_bytes']} B")
    print("  Prozess")
    for key in ("cpu_seconds", "wall_seconds", "memory_mb", "max_processes", "max_open_files"):
        print(f"    {key:<14} {policy.process[key]}")
    print("  Netz")
    print(f"    Modus          {policy.network['mode']}")
    print(f"    erlaubt        {policy.network['allowed_domains'] or '-'}")
    print(f"    gesperrte Ports {policy.network['deny_ports']}")
    print("  System")
    print(f"    Namespaces    {policy.system['namespaces']}")
    print(f"    Laufzeit      {policy.system.get('jail_runtime', 'minimal')}")
    print(f"    seccomp       {policy.system['seccomp']}")
    print(f"  Werkzeuge      {policy.tools['enabled']}")
    print(f"  Modell         {policy.model['provider']}, max {policy.model['max_steps']} Schritte")
    return 0


# ----------------------------------------------------------------------- run
def _new_run_dir(policy_name: str) -> str:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = os.path.join(RESULTS_DIR, f"{stamp}-{policy_name}")
    suffix = 1
    while os.path.exists(path):
        path = os.path.join(RESULTS_DIR, f"{stamp}-{policy_name}-{suffix}")
        suffix += 1
    os.makedirs(path, exist_ok=True)
    return path


def cmd_run(args: argparse.Namespace) -> int:
    policy = Policy.load(args.policy)
    aufgabe = args.task
    if args.task_file:
        with open(args.task_file, "r", encoding="utf-8") as fh:
            aufgabe = fh.read().strip()
    if args.file:
        with open(args.file, "r", encoding="utf-8") as fh:
            # Tiefen-Merge, nicht {**a, **b}: sonst wuerde ein "network"-Objekt
            # in der Datei den *ganzen* Abschnitt ersetzen und dabei z. B. den
            # Proxy-Modus still auf "none" zuruecksetzen.
            try:
                policy = Policy.from_dict(
                    _deep_merge(policy.raw, json.load(fh)),
                    source=f"{policy.source} + {args.file}",
                )
            except ValueError as exc:
                print(f"Ergänzung abgelehnt: {exc}", file=sys.stderr)
                return 2

    run_dir = _new_run_dir(policy.name)
    print(BANNER)
    print(f"Policy   {policy.name} v{policy.version}")
    print(f"Aufgabe  {aufgabe[:120]}{'...' if len(aufgabe) > 120 else ''}")
    print(f"Ordner   {run_dir}")
    print("-" * 64)

    audit = AuditLog(os.path.join(run_dir, "audit.jsonl"), echo=True)
    result = run_agent(
        aufgabe,
        policy,
        run_dir,
        audit=audit,
        model_provider=args.model,
        wall_timeout=args.timeout,
    )
    audit.close()
    verification = audit.verify()
    verified = bool(verification.get("valid"))

    print("-" * 64)
    print(f"Ende: {result.stopped}  |  {result.seconds}s  |  {len(result.tool_calls)} Werkzeugaufrufe")
    print(f"Schichten aktiv:   {', '.join(result.jail_report.get('active_layers', [])) or '-'}")
    inaktiv = result.jail_report.get("inactive_layers", [])
    if inaktiv:
        print(f"Schichten INAKTIV: {', '.join(inaktiv)}  <-- Lauf ist eingeschraenkt!")
    print(
        f"Audit-Hashkette gueltig: {verified} "
        f"({verification.get('entries', 0)} Eintraege, "
        f"{verification.get('problems', []) or 'keine Probleme'})"
    )
    print(f"Antwort: {result.answer[:300] or '(leer)'}")
    if result.files:
        print(f"Dateien des Agenten ({len(result.files)}) in {os.path.join(run_dir, 'ausgabe')}:")
        for datei in result.files:
            print(f"  {os.path.relpath(datei, run_dir)}  ({os.path.getsize(datei)} B)")

    daten = report_mod.run_report(result, policy, audit.path, verified)
    report_mod.write(os.path.join(run_dir, "bericht.md"), report_mod.to_markdown(daten, verified))
    report_mod.write_json(os.path.join(run_dir, "bericht.json"), daten)
    print(f"Bericht: {os.path.join(run_dir, 'bericht.md')}")
    return 0 if verified else 1


# ------------------------------------------------------------------ inspect
def _inspektions_skript() -> str:
    """Prueft aus der Sicht des Agenten, wie das Gefaengnis wirklich aussieht.

    Der Code laeuft *im* Gefaengnis, nicht im Wirt. Genau deshalb ist die
    Ausgabe ein Beweis und keine Behauptung: Wer sie liest, hat den Blick
    des Agenten.
    """
    return r'''
import json, os, resource, socket

def eintraege(pfad):
    try:
        return sorted(os.listdir(pfad))
    except OSError as exc:
        return "nicht lesbar: %s" % exc.strerror

def schreibtest(ziel):
    try:
        with open(ziel, "w", encoding="utf-8") as fh:
            fh.write("probe")
        os.unlink(ziel)
        return "BESCHREIBBAR"
    except OSError as exc:
        return "%s (%s)" % (exc.strerror, exc.__class__.__name__)

bericht = {}
bericht["1_arbeitsverzeichnis"] = os.getcwd()
bericht["2_benutzer"] = {
    "uid": os.getuid(),
    "gid": os.getgid(),
    "euid": os.geteuid(),
    "prozess_id": os.getpid(),
}
bericht["3_inhalt_von_/"] = eintraege("/")
bericht["4_inhalt_von_/usr_bin"] = eintraege("/usr/bin")
bericht["5_inhalt_von_/etc"] = eintraege("/etc")
bericht["6_inhalt_von_/work"] = eintraege("/work")
bericht["7_wo_darf_geschrieben_werden"] = {
    ziel: schreibtest(ziel)
    for ziel in ("/work/probe.txt", "/tmp/probe.txt", "/usr/bin/probe.txt",
                 "/etc/probe.txt", "/opt/agoris/probe.txt")
}
bericht["8_darf_gelesen_werden"] = {
    ziel: os.path.exists(ziel)
    for ziel in ("/etc/shadow", "/etc/passwd", "/root", "/sys", "/proc", "/dev/mem", "/dev/urandom")
}
bericht["9_umgebungsvariablen"] = sorted(os.environ)
bericht["10_geheimnisse_sichtbar"] = [
    name for name in os.environ
    if any(muster in name.upper() for muster in ("KEY", "TOKEN", "SECRET", "PASSWORD"))
]
grenzen = {}
for name in ("CPU", "AS", "DATA", "FSIZE", "NPROC", "NOFILE", "CORE"):
    wert = getattr(resource, "RLIMIT_" + name, None)
    if wert is not None:
        grenzen[name] = resource.getrlimit(wert)[0]
bericht["11_ressourcengrenzen"] = grenzen
verbindung = socket.socket()
verbindung.settimeout(5)
try:
    verbindung.connect(("1.1.1.1", 80))
    bericht["12_internetzugriff"] = "VERBINDUNG AUFGEBAUT - das sollte nicht passieren!"
except OSError as exc:
    bericht["12_internetzugriff"] = "%s (%s)" % (exc.strerror, exc.__class__.__name__)
finally:
    verbindung.close()
print(json.dumps(bericht, indent=2, ensure_ascii=False))
'''


def cmd_inspect(args: argparse.Namespace) -> int:
    policy = Policy.load(args.policy)
    run_dir = _new_run_dir(f"inspect-{policy.name}")
    print(BANNER)
    print(f"Innenansicht des Gefaengnisses (Policy '{policy.name}')")
    print("Dieser Code laeuft im Gefaengnis, nicht auf deinem Rechner.")
    print("-" * 64)
    result = run_snippet(
        _inspektions_skript(),
        policy,
        run_dir,
        timeout=30,
        label="inspect",
    )
    print(result.stdout.rstrip() or "(keine Ausgabe)")
    if result.stderr.strip():
        print("-" * 64)
        print(result.stderr.strip()[-800:])
    print("-" * 64)
    print(f"Beendet nach {result.seconds}s, Exit {result.exit_code}, Signal {result.signal}")
    inaktiv = sorted(result.jail_report.get("inactive_layers", []))
    if inaktiv:
        print(f"Schichten INAKTIV: {', '.join(inaktiv)}")
    if result.exit_code not in (0, None) or not result.stdout.strip():
        return 1
    return 0


# ------------------------------------------------------------------- attacks
def cmd_attacks(args: argparse.Namespace) -> int:
    policy = Policy.load(args.policy)
    run_dir = _new_run_dir(f"attacks-{policy.name}")
    print(BANNER)
    print(f"Policy {policy.name} - {len(attacks_mod.ATTACKS)} Ausbruchversuche")
    print(f"Ordner {run_dir}")
    print("-" * 64)
    daten = attacks_mod.run_all(
        run_dir,
        policy,
        timeout=args.timeout,
        only=args.only.split(",") if args.only else None,
    )
    print("-" * 64)
    for eintrag in daten["ergebnisse"]:
        print(f"{eintrag['status'].upper():<8} {eintrag['attack']:<16} {eintrag['title']}")
    print(
        f"\ngehalten {daten['blocked']}/{daten['total']}  |  durchgekommen {daten['leaked']}"
        f"  |  Luecken {daten.get('gaps', 0)}  |  unentschieden {daten['errors']}"
    )
    if daten.get("gap_list"):
        print(f"Luecken im Detail: {', '.join(daten['gap_list'])}")
    inaktiv = daten.get("inactive_layers") or []
    if inaktiv:
        print(f"Schichten inaktiv: {', '.join(inaktiv)} - Lauf ist eingeschraenkt")
    report_mod.write(os.path.join(run_dir, "angriffe.md"), report_mod.to_markdown(daten))
    report_mod.write_json(os.path.join(run_dir, "angriffe.json"), report_mod.attack_report(daten))
    print(f"Bericht: {os.path.join(run_dir, 'angriffe.md')}")
    return 0 if daten["leaked"] == 0 and daten.get("errors", 0) == 0 else 2


# -------------------------------------------------------------------- verify
def cmd_verify(args: argparse.Namespace) -> int:
    schlechter: List[str] = []
    for ziel in args.run_dir:
        pfad = os.path.join(ziel, "audit.jsonl") if os.path.isdir(ziel) else ziel
        if not os.path.exists(pfad):
            print(f"Audit-Log nicht gefunden: {pfad}", file=sys.stderr)
            schlechter.append(pfad)
            continue
        log = AuditLog(pfad, echo=False)
        eintraege = log.read_all()
        ergebnis = log.verify()
        log.close()
        if ergebnis.get("valid"):
            print(
                f"OK   {pfad}: {len(eintraege)} Eintraege gelesen, "
                f"{ergebnis.get('entries', 0)} geprueft, keine Probleme"
            )
            print(f"     Kopf: {ergebnis.get('head', '-')}")
        else:
            print(f"FEHL {pfad}: {len(eintraege)} Eintraege gelesen, Kette gebrochen", file=sys.stderr)
            for problem in ergebnis.get("problems", []):
                print(f"       {problem}", file=sys.stderr)
            schlechter.append(pfad)
    return 1 if schlechter else 0


# ----------------------------------------------------------------------- main
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agoris", description=BANNER)
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("doctor", help="Umgebung und Faehigkeiten pruefen").set_defaults(func=doctor)
    sub.add_parser("policies", help="verfuegbare Policies listen").set_defaults(func=cmd_policies)

    show = sub.add_parser("show", help="Policy im Detail zeigen")
    show.add_argument("policy", nargs="?", default="minimal")
    show.add_argument("--json", action="store_true")
    show.set_defaults(func=cmd_show)

    lauf = sub.add_parser("run", help="Agentenlauf starten")
    lauf.add_argument("task", nargs="?", default="Lies 'aufgabe.md' und loese die Aufgabe.")
    lauf.add_argument("-p", "--policy", default="minimal")
    lauf.add_argument("-t", "--task-file", help="Aufgabe aus einer Datei lesen")
    lauf.add_argument("-f", "--file", help="zusaetzliche Policy-Felder aus JSON")
    lauf.add_argument("-m", "--model", help="Modellanbieter (simulated, echo, anthropic)")
    lauf.add_argument("--timeout", type=float, help="Wanduhr-Stopp in Sekunden")
    lauf.set_defaults(func=cmd_run)

    blick = sub.add_parser("inspect", help="Innenansicht des Gefaengnisses zeigen")
    blick.add_argument("-p", "--policy", default="minimal")
    blick.set_defaults(func=cmd_inspect)

    angriff = sub.add_parser("attacks", help="Ausbruchversuche ausfuehren")
    angriff.add_argument("-p", "--policy", default="minimal")
    angriff.add_argument("--timeout", type=float, default=20.0)
    angriff.add_argument("--only", help="nur diese Angriffe (kommagetrennt)")
    angriff.set_defaults(func=cmd_attacks)

    pruef = sub.add_parser("verify", help="Audit-Hashkette pruefen (mehrere Pfade moeglich)")
    pruef.add_argument("run_dir", nargs="+", help="Laufordner oder audit.jsonl")
    pruef.set_defaults(func=cmd_verify)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        args = parser.parse_args(["run"] + (argv or []))
    return args.func(args)