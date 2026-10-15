"""Kommandozeile fuer AGORIS.

    python3 agoris.py doctor              Umgebung pruefen
    python3 agoris.py policies            verfuegbare Policies zeigen
    python3 agoris.py show research       eine Policy im Detail
    python3 agoris.py run "Aufgabe" -p research
    python3 agoris.py attacks             Angriffsbatterie ausfuehren
    python3 agoris.py test                Sandbox gegen verschiedene Agenten testen
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
from . import style
from .audit import AuditLog
from .launcher import run_agent, run_snippet, run_benchmark
from .policy import Policy, _deep_merge

RESULTS_DIR = "runs"
BANNER = "AGORIS - sichere Umgebung fuer unzuverlaessige KI-Agenten"


# --------------------------------------------------------------------- doctor
def doctor(args: argparse.Namespace = None) -> int:
    print(style.header(BANNER))
    print(style.dim_text("=" * len(BANNER)))
    print(style.info(f"Python           {platform.python_version()} ({sys.executable})"))
    print(style.info(f"Plattform        {platform.system()} {platform.release()} / {platform.machine()}"))
    uid_line = f"Benutzer         uid={os.getuid()} gid={os.getgid()}{'  (root!)' if os.getuid() == 0 else ''}"
    print(style.info(uid_line))

    names = Policy.available()
    print(style.info(f"Policies         {', '.join(names) if names else '(keine gefunden)'}"))

    benoetigt = ["user", "mount", "pid", "net"]
    try:
        with open("/proc/self/uid_map") as fh:
            uid_map = fh.read().strip()
        print(style.info(f"uid_map          {uid_map}"))
    except OSError as exc:
        uid_map = f"nicht lesbar ({exc})"
        print(style.warning(f"uid_map          {uid_map}"))
    with open("/proc/sys/user/max_user_namespaces") as fh:
        print(style.info(f"max_user_ns      {fh.read().strip()}"))
    for pfad in ("/usr/bin/python3", "/lib64", "/usr/lib"):
        zustand = "vorhanden" if os.path.exists(pfad) else "FEHLT"
        color = style.info if zustand == "vorhanden" else style.error
        print(color(f"{pfad:<18}{zustand}"))
    
    print()
    print(style.header("Namespaces:"))
    flags = {
        "user": 0x10000000, "mount": 0x00020000, "pid": 0x20000000,
        "net": 0x40000000, "ipc": 0x08000000, "uts": 0x04000000,
    }
    import ctypes

    libc = ctypes.CDLL("libc.so.6", use_errno=True)
    libc.unshare.restype = ctypes.c_int
    libc.unshare.argtypes = [ctypes.c_int]
    ns_ok = True
    for name in benoetigt:
        pid = os.fork()
        if pid == 0:
            ctypes.set_errno(0)
            rc = libc.unshare(flags[name])
            err = ctypes.get_errno()
            os._exit(0 if rc == 0 else min(err, 120))
        _pid, status = os.waitpid(pid, 0)
        code = os.WEXITSTATUS(status)
        ok = code == 0
        if not ok:
            ns_ok = False
        if ok:
            print(f"  {name:<8}{style.success('moeglich')}")
        else:
            print(f"  {name:<8}{style.error(f'nein (errno {code})')}")

    print()
    print(style.header("seccomp:"))
    versuch = seccomp_mod.build_program(seccomp_mod.blocked_syscalls(), seccomp_mod.audit_arch())
    print(f"  Filterprogramm    {style.info(str(len(versuch)))} Bytes, {style.info(str(len(seccomp_mod.blocked_syscalls())))} gesperrte Syscalls")
    print(f"  Gesperrt          {style.info(', '.join(seccomp_mod.describe()))}")
    if not seccomp_mod.set_no_new_privs():
        print(style.warning("  Hinweis           PR_SET_NO_NEW_PRIVS nicht moeglich - Filter wird voraussichtlich abgelehnt"))
    else:
        print(style.success("  no_new_privs      setzbar"))

    print()
    print(style.header("Werkzeuge im Wirt (nur zur Info, AGORIS braucht sie nicht):"))
    for werkzeug, kommando in (("ip", "ip"), ("ss", "ss"), ("docker", "docker"), ("gcc", "gcc")):
        vorhanden = os.path.exists(f'/usr/bin/{kommando}') or os.path.exists(f'/usr/sbin/{kommando}')
        text = f"  {werkzeug:<8}{'vorhanden' if vorhanden else 'fehlt (wird nicht gebraucht)'}"
        print(style.info(text) if vorhanden else style.warning(text))

    print()
    print(style.warning("Hinweis: Ohne root sind die Namespaces ueblicherweise nicht zugaenglich."))
    print(style.warning("AGORIS laeuft dann zwar, aber ohne wirksame Isolation - bitte nicht"))
    print(style.warning("als Beleg fuer Sicherheit werten."))
    print()

    if not ns_ok:
        print(style.error("Achtung: Mindestens ein Namespace ist nicht verfuegbar."))
        print(style.error("Die Messung kann auf diesem Rechner nicht belastbar ausfallen."))
        print(style.info("Tipp: Nutze WSL2 (Windows) oder eine Linux-VM mit User-Namespaces."))
        print()
    else:
        print(style.success("Alle Namespaces verfuegbar - weiter gehts mit:"))
        print(style.info("  python3 agoris.py inspect    # Innenansicht"))
        print(style.info("  python3 agoris.py attacks    # 14 Ausbruchversuche"))
        print(style.info("  python3 agoris.py test       # Komplettcheck aller Agenten"))
    return 0


# ------------------------------------------------------------------- policies
def cmd_policies(args: argparse.Namespace) -> int:
    print(style.header("Verfügbare Policies:"))
    for name in Policy.available():
        policy = Policy.load(name)
        beschreibung = policy.description or "(ohne Beschreibung)"
        name_formatted = f"{name:<12}"
        mode_formatted = f"{policy.network['mode']:<6}"
        print(f"  {style.bold(name_formatted)} v{style.info(policy.version)}  {style.info(mode_formatted)} {beschreibung}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    policy = Policy.load(args.policy)
    if args.json:
        print(json.dumps(policy.summary(), indent=2, ensure_ascii=False))
        return 0
    print(style.header(f"Policy '{policy.name}' v{policy.version}"))
    print(style.info(f"  aus           {policy.source}"))
    print(style.info(f"  Beschreibung  {policy.description or '-'}"))
    print(style.info("  Dateisystem"))
    print(f"    {style.bold('schreibbar')}    {policy.filesystem['writable']}")
    print(f"    {style.bold('nur lesbar')}    {policy.filesystem['read_only_mounts']}")
    print(f"    {style.bold('verboten')}      {len(policy.filesystem['forbidden'])} Pfade")
    print(f"    {style.bold('max. Datei')}     {policy.filesystem['max_file_bytes']} B")
    print(f"    {style.bold('max. Arbeits')}   {policy.filesystem['max_workspace_bytes']} B")
    print(style.info("  Prozess"))
    for key in ("cpu_seconds", "wall_seconds", "memory_mb", "max_processes", "max_open_files"):
        key_formatted = f"{key:<14}"
        print(f"    {style.bold(key_formatted)} {policy.process[key]}")
    print(style.info("  Netz"))
    print(f"    {style.bold('Modus')}          {policy.network['mode']}")
    erlaubt = policy.network['allowed_domains'] or '-'
    print(f"    {style.bold('erlaubt')}        {erlaubt}")
    print(f"    {style.bold('gesperrte Ports')} {policy.network['deny_ports']}")
    print(style.info("  System"))
    print(f"    {style.bold('Namespaces')}    {policy.system['namespaces']}")
    laufzeit = policy.system.get('jail_runtime', 'minimal')
    print(f"    {style.bold('Laufzeit')}      {laufzeit}")
    print(f"    {style.bold('seccomp')}       {policy.system['seccomp']}")
    print(style.info("  Werkzeuge"))
    enabled = policy.tools.get('enabled', {})
    if isinstance(enabled, dict):
        enabled_str = ', '.join(enabled.keys()) if enabled else '-'
    else:
        enabled_str = str(enabled)
    print(f"    {enabled_str}")
    print(style.info("  Modell"))
    provider = policy.model.get('provider', '-')
    max_steps = policy.model.get('max_steps', '-')
    print(f"    {style.bold('Anbieter')}     {provider}")
    print(f"    {style.bold('Max Schritte')} {max_steps}")
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
                print(style.error(f"Ergänzung abgelehnt: {exc}"), file=sys.stderr)
                return 2

    run_dir = _new_run_dir(policy.name)
    print(style.header(BANNER))
    print(style.info(f"Policy   {policy.name} v{policy.version}"))
    print(style.info(f"Aufgabe  {aufgabe[:120]}{'...' if len(aufgabe) > 120 else ''}"))
    print(style.info(f"Ordner   {run_dir}"))
    print(style.dim_text("-" * 64))

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

    print(style.dim_text("-" * 64))
    stopped_style = style.success if result.stopped == "finish" else style.error
    print(f"Ende: {stopped_style(result.stopped)}  |  {style.info(f'{result.seconds}s')}  |  {style.info(str(len(result.tool_calls)))} Werkzeugaufrufe")
    active = result.jail_report.get('active_layers', [])
    if active:
        print(f"Schichten aktiv:   {style.success(', '.join(active))}")
    else:
        print(f"Schichten aktiv:   {style.warning('-')}")
    inaktiv = result.jail_report.get("inactive_layers", [])
    if inaktiv:
        print(f"Schichten INAKTIV: {style.error(', '.join(inaktiv))}  <-- Lauf ist eingeschraenkt!")
    verified_style = style.success if verified else style.error
    entries = verification.get('entries', 0)
    problems = verification.get('problems', [])
    problems_str = ', '.join(problems) if problems else 'keine Probleme'
    print(
        f"{verified_style('Audit-Hashkette gueltig:')} {verified} "
        f"({style.info(str(entries))} Eintraege, "
        f"{style.info(problems_str)})"
    )
    answer_preview = result.answer[:300] or '(leer)'
    print(f"Antwort: {style.info(answer_preview)}")
    if result.files:
        print(style.info(f"Dateien des Agenten ({len(result.files)}) in {os.path.join(run_dir, 'ausgabe')}"))
        for datei in result.files:
            rel = os.path.relpath(datei, run_dir)
            size = os.path.getsize(datei)
            print(f"  {style.info(rel)}  ({style.info(str(size))} B)")

    daten = report_mod.run_report(result, policy, audit.path, verified)
    report_mod.write(os.path.join(run_dir, "bericht.md"), report_mod.to_markdown(daten, verified))
    report_mod.write_json(os.path.join(run_dir, "bericht.json"), daten)
    print(style.info(f"Bericht: {os.path.join(run_dir, 'bericht.md')}"))
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
    print(style.header(BANNER))
    print(style.info(f"Innenansicht des Gefaengnisses (Policy '{policy.name}')"))
    print(style.info("Dieser Code laeuft im Gefaengnis, nicht auf deinem Rechner."))
    print(style.dim_text("-" * 64))
    result = run_snippet(
        _inspektions_skript(),
        policy,
        run_dir,
        timeout=30,
        label="inspect",
    )
    stdout = result.stdout.rstrip()
    if stdout:
        print(stdout)
    else:
        print(style.warning("(keine Ausgabe)"))
    if result.stderr.strip():
        print(style.dim_text("-" * 64))
        stderr = result.stderr.strip()[-800:]
        print(stderr)
    print(style.dim_text("-" * 64))
    print(f"Beendet nach {style.info(str(result.seconds))}s, Exit {style.info(str(result.exit_code))}, Signal {style.info(str(result.signal))}")
    inaktiv = sorted(result.jail_report.get("inactive_layers", []))
    if inaktiv:
        print(f"Schichten INAKTIV: {style.error(', '.join(inaktiv))}")
    if result.exit_code not in (0, None) or not result.stdout.strip():
        return 1
    return 0


# ------------------------------------------------------------------- attacks
def cmd_attacks(args: argparse.Namespace) -> int:
    policy = Policy.load(args.policy)
    run_dir = _new_run_dir(f"attacks-{policy.name}")
    print(style.header(BANNER))
    print(style.info(f"Policy {policy.name} - {len(attacks_mod.ATTACKS)} Ausbruchversuche"))
    print(style.info(f"Ordner {run_dir}"))
    print(style.dim_text("-" * 64))
    daten = attacks_mod.run_all(
        run_dir,
        policy,
        timeout=args.timeout,
        only=args.only.split(",") if args.only else None,
    )
    print(style.dim_text("-" * 64))
    for eintrag in daten["ergebnisse"]:
        status = eintrag['status'].upper()
        if status == "BLOCKED":
            status_style = style.success(status)
        elif status == "LEAKED":
            status_style = style.error(status)
        elif status == "GAP":
            status_style = style.warning(status)
        else:
            status_style = style.info(status)
        print(f"{status_style:<8} {eintrag['attack']:<16} {eintrag['title']}")
    print(
        f"\n{style.success('gehalten')} {style.info(str(daten['blocked']))}/{style.info(str(daten['total']))}  |  "
        f"{style.error('durchgekommen')} {style.info(str(daten['leaked']))}  "
        f"|  {style.warning('Luecken')} {style.info(str(daten.get('gaps', 0)))}  "
        f"|  {style.info('unentschieden')} {style.info(str(daten['errors']))}"
    )
    if daten.get("gap_list"):
        print(f"{style.warning('Luecken im Detail:')} {', '.join(daten['gap_list'])}")
    inaktiv = daten.get("inactive_layers") or []
    if inaktiv:
        print(f"{style.warning('Schichten inaktiv:')} {', '.join(inaktiv)} - Lauf ist eingeschraenkt")
    report_mod.write(os.path.join(run_dir, "angriffe.md"), report_mod.to_markdown(daten))
    report_mod.write_json(os.path.join(run_dir, "angriffe.json"), report_mod.attack_report(daten))
    print(style.info(f"Bericht: {os.path.join(run_dir, 'angriffe.md')}"))
    return 0 if daten["leaked"] == 0 and daten.get("errors", 0) == 0 else 2


# -------------------------------------------------------------------- test
def cmd_test(args: argparse.Namespace) -> int:
    """Fuehrt den Test-Harness aus, der die Sandbox gegen verschiedene
    Agenten-Konfigurationen prueft (Policy x Provider).

    Der Harness liegt unter ``tools/test_sandbox.py`` und kann auch direkt
    gestartet werden. Er prueft: doctor, inspect, Agenten-Laeufe mit
    verschiedenen Providern und die Angriffsbatterie.
    """
    print(style.header("Test-Harness starten"))
    import importlib.util
    import subprocess

    tools_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
    script = os.path.join(tools_dir, "test_sandbox.py")
    if not os.path.exists(script):
        print(style.error(f"Test-Harness nicht gefunden: {script}"), file=sys.stderr)
        return 2

    cmd = [sys.executable, script]
    if args.provider:
        cmd += ["--provider", args.provider]
        print(style.info(f"Provider: {args.provider}"))
    if args.policy:
        cmd += ["--policy", args.policy]
        print(style.info(f"Policy: {args.policy}"))
    if args.only:
        cmd += ["--only", args.only]
        print(style.info(f"Only: {args.only}"))

    print(style.info(f"Ausführung: {' '.join(cmd)}"))
    try:
        proc = subprocess.run(cmd, cwd=os.path.dirname(tools_dir) or ".")
        return proc.returncode
    except KeyboardInterrupt:
        print(style.error("\nAbgebrochen."), file=sys.stderr)
        return 130


# -------------------------------------------------------------------- verify
def cmd_verify(args: argparse.Namespace) -> int:
    schlechter: List[str] = []
    print(style.header("Audit-Hashkette prüfen"))
    for ziel in args.run_dir:
        pfad = os.path.join(ziel, "audit.jsonl") if os.path.isdir(ziel) else ziel
        if not os.path.exists(pfad):
            print(style.error(f"Audit-Log nicht gefunden: {pfad}"), file=sys.stderr)
            schlechter.append(pfad)
            continue
        log = AuditLog(pfad, echo=False)
        eintraege = log.read_all()
        ergebnis = log.verify()
        log.close()
        if ergebnis.get("valid"):
            print(
                f"{style.success('OK')}   {pfad}: {style.info(str(len(eintraege)))} Eintraege gelesen, "
                f"{style.info(str(ergebnis.get('entries', 0)))} geprueft, keine Probleme"
            )
            print(f"     Kopf: {style.info(str(ergebnis.get('head', '-')))}")
        else:
            print(style.error(f"FEHL {pfad}: {len(eintraege)} Eintraege gelesen, Kette gebrochen"), file=sys.stderr)
            for problem in ergebnis.get("problems", []):
                print(f"       {problem}", file=sys.stderr)
            schlechter.append(pfad)
    return 1 if schlechter else 0


# ------------------------------------------------------------------- benchmark
def cmd_benchmark(args: argparse.Namespace) -> int:
    """Misst den Performance-Overhead der Sandbox.

    Führt den gleichen Code mehrfach nativ (ohne Isolation) und im Sandbox aus
    und vergleicht die Ausführungszeiten. Zeigt an, wie viel Kapazität die
    Sandbox-Schichten (Namespaces, chroot, seccomp, Ressourcenlimits) kosten.
    """
    print(style.header("Sandbox-Benchmark starten"))
    policy = Policy.load(args.policy)
    run_dir = _new_run_dir(f"benchmark-{policy.name}")

    print(style.info(f"Sandbox-Benchmark (Policy '{policy.name}')"))
    print(style.info(f"Wiederholungen: {args.iterations}  |  Warmup: {args.warmup}"))
    print(style.info(f"Ordner: {run_dir}"))
    print(style.dim_text("-" * 64))

    # Benchmark-Code: CPU-lastig, misst reinen Overhead
    benchmark_code = args.code or (
        "import time, math\n"
        "start = time.time()\n"
        "x = 0.0\n"
        "for i in range(500000):\n"
        "    x += math.sin(i) * math.cos(i)\n"
        "print(f'Loops: 500000, Result: {x:.6f}, Time: {time.time()-start:.3f}s')"
    )

    if args.verbose:
        print(style.header("Benchmark-Code:"))
        print(benchmark_code)
        print(style.dim_text("-" * 64))

    result = run_benchmark(
        benchmark_code,
        policy,
        run_dir,
        iterations=args.iterations,
        warmup=args.warmup,
    )

    print(style.info(f"Nativ (keine Sandbox):     {result.native_time:.3f}s  "
          f"(min: {result.details['native_min']:.3f}s, max: {result.details['native_max']:.3f}s)"))
    print(style.info(f"Im Sandbox:                {result.sandbox_time:.3f}s  "
          f"(min: {result.details['sandbox_min']:.3f}s, max: {result.details['sandbox_max']:.3f}s)"))
    overhead_style = style.success if result.overhead_percent < 5 else style.warning if result.overhead_percent < 20 else style.error if result.overhead_percent < 50 else style.error
    print(style.info(f"Overhead:                  {result.overhead_percent:.1f}%"))
    print(style.dim_text("-" * 64))

    if result.details.get("active_layers"):
        print(style.info(f"Aktive Schichten:   {', '.join(result.details['active_layers'])}"))
    if result.details.get("inactive_layers"):
        print(style.info(f"Inaktive Schichten: {', '.join(result.details['inactive_layers'])}"))

    print(style.dim_text("-" * 64))
    print(style.header("Interpretation:"))
    if result.overhead_percent < 5:
        print(style.success("  Geringer Overhead (< 5%) - Sandbox kostet kaum Leistung."))
    elif result.overhead_percent < 20:
        print(style.success("  Moderater Overhead (5-20%) - Für die meisten Aufgaben vernachlässigbar."))
    elif result.overhead_percent < 50:
        print(style.warning("  Deutlicher Overhead (20-50%) - Bei CPU-lastigen Aufgaben spürbar."))
    else:
        print(style.error("  Hoher Overhead (> 50%) - Prüfe, ob alle Schichten nötig sind."))
        print(style.info("  Tipp: 'seccomp: false' in Policy reduziert Overhead stark."))

    print()
    print(style.header("Hinweis: Der Overhead besteht aus:"))
    print(style.info("  - Namespace-Aufbau (unshare, ID-Mapping)"))
    print(style.info("  - Dateisystem-Aufbau (tmpfs, Mounts, chroot)"))
    print(style.info("  - Rechte-Entzug (Capabilities, no_new_privs)"))
    print(style.info("  - Ressourcen-Limits (setrlimit)"))
    print(style.info("  - seccomp-Filter (BPF-Programm, falls aktiv)"))
    print(style.info("  - Proxy-Start (falls Netz-Policy aktiv)"))
    print()
    print(style.info(f"Details in: {run_dir}"))

    return 0


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

    test = sub.add_parser("test", help="Sandbox gegen verschiedene Agenten testen")
    test.add_argument("--provider", default="simulated,echo",
                      help="Komma-getrennte Provider (Standard: simulated,echo)")
    test.add_argument("--policy", default="minimal,research",
                      help="Komma-getrennte Policies (Standard: minimal,research)")
    test.add_argument("--only", help="nur bestimmte Angriffe (kommagetrennt)")
    test.set_defaults(func=cmd_test)

    pruef = sub.add_parser("verify", help="Audit-Hashkette pruefen (mehrere Pfade moeglich)")
    pruef.add_argument("run_dir", nargs="+", help="Laufordner oder audit.jsonl")
    pruef.set_defaults(func=cmd_verify)

    bench = sub.add_parser("benchmark", help="Sandbox-Performance messen (Overhead nativ vs. Sandbox)")
    bench.add_argument("-p", "--policy", default="minimal", help="Policy für den Sandbox-Lauf")
    bench.add_argument("-i", "--iterations", type=int, default=5, help="Messwiederholungen pro Modus (Standard: 5)")
    bench.add_argument("-w", "--warmup", type=int, default=1, help="Warmup-Läufe (Standard: 1)")
    bench.add_argument("-c", "--code", help="Eigener Benchmark-Code als String")
    bench.add_argument("-v", "--verbose", action="store_true", help="Benchmark-Code anzeigen")
    bench.set_defaults(func=cmd_benchmark)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        args = parser.parse_args(["run"] + (argv or []))
    return args.func(args)