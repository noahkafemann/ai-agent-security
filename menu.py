#!/usr/bin/env python3
"""Menü-Skript für AGORIS.

Dieses Skript präsentiert ein einfaches Menü, um verschiedene AGORIS-Funktionen
auszuführen. Es ermöglicht zudem das Ausführen einer benutzerdefinierten Python-
Datei als Agenten in der Sandbox.
"""

import os
import sys
import subprocess

# Sicherstellen, dass wir das AGORIS-Modul importieren können
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agoris import cli
from agoris.cli import BANNER
from agoris.policy import Policy
from agoris.launcher import run_snippet
from agoris.audit import AuditLog
from agoris import style
import tempfile
import shutil


def print_banner():
    print(style.header(BANNER))
    print(style.dim_text("=" * len(BANNER)))
    print(style.info("AGORIS Menü - Wähle eine Option:"))
    print()


def show_menu():
    print(style.info("1. ") + style.success("Umgebung überprüfen (doctor)"))
    print(style.info("2. ") + style.success("Innenansicht des Gefängnisses zeigen (inspect)"))
    print(style.info("3. ") + style.success("Verfügbare Policies anzeigen"))
    print(style.info("4. ") + style.success("Policy im Detail zeigen"))
    print(style.info("5. ") + style.success("Agentenlauf starten (run)"))
    print(style.info("6. ") + style.success("Sandbox gegen verschiedene Agenten testen (test)"))
    print(style.info("7. ") + style.success("Ausbruchversuche ausführen (attacks)"))
    print(style.info("8. ") + style.success("Audit-Hashkette prüfen (verify)"))
    print(style.info("9. ") + style.success("Sandbox-Performance messen (benchmark)"))
    print(style.info("10. ") + style.success("Benutzerdefinierten Agenten ausführen (Python-Datei in Sandbox)"))
    print(style.info("0. ") + style.error("Beenden"))
    print()


def run_command(cmd_args):
    """Führt einen AGORIS-Befehl über die CLI aus."""
    # Wir verwenden die cli.main Funktion, um die Befehle auszuführen
    old_argv = sys.argv
    try:
        sys.argv = ["agoris"] + cmd_args
        return cli.main()
    except SystemExit as e:
        return e.code
    finally:
        sys.argv = old_argv


def run_custom_agent():
    """Führt eine benutzerdefinierte Python-Datei als Snippet in der Sandbox aus."""
    file_path = input(style.info("Pfad zur Python-Datei eingeben: ")).strip()
    if not file_path:
        print(style.error("Kein Pfad angegeben."))
        return
    if not os.path.isfile(file_path):
        print(style.error(f"Datei nicht gefunden: {file_path}"))
        return

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            code = f.read()
    except Exception as e:
        print(style.error(f"Fehler beim Lesen der Datei: {e}"))
        return

    # Policy laden (minimal)
    policy = Policy.load("minimal")
    # Erstelle ein temporäres Verzeichnis für den Lauf
    with tempfile.TemporaryDirectory(prefix="agoris_menu_") as tmpdir:
        run_dir = os.path.join(tmpdir, "run")
        os.makedirs(run_dir, exist_ok=True)
        # Audit-Log erstellen (optional, aber wir wollen es für die Sauberkeit)
        audit_path = os.path.join(run_dir, "audit.jsonl")
        audit = AuditLog(audit_path, echo=False)

        print(style.header(f"Ausführung von {file_path} in der Sandbox (Policy: minimal)"))
        print(style.info(f"Arbeitsverzeichnis: {run_dir}"))
        print(style.dim_text("-" * 60))

        # Führe den Snippet aus
        from agoris.launcher import run_snippet
        result = run_snippet(
            code=code,
            policy=policy,
            run_dir=run_dir,
            audit=audit,
            timeout=30.0,  # Standardtimeout
            label="custom_agent",
        )
        audit.close()

        print(style.dim_text("-" * 60))
        print(style.info(f"Ausführung beendet nach {result.seconds}s"))
        print(style.info(f"Exit Code: {result.exit_code}"))
        print(style.info(f"Signal: {result.signal}"))
        if result.stdout:
            print(style.header("STDOUT:"))
            print(result.stdout.rstrip())
        if result.stderr:
            print(style.header("STDERR:"))
            print(result.stderr.rstrip()[:1000])  # Begrenze die Ausgabe

        # Zeige ggf. den Audit-Log an
        print(style.info(f"\nAudit-Log gespeichert unter: {audit_path}"))


def main():
    while True:
        print_banner()
        show_menu()
        choice = input(style.info("Deine Wahl: ")).strip()
        if choice == "0":
            print(style.success("Auf Wiedersehen!"))
            break
        elif choice == "1":
            run_command(["doctor"])
        elif choice == "2":
            run_command(["inspect"])
        elif choice == "3":
            run_command(["policies"])
        elif choice == "4":
            policy_name = input(style.info("Policy name (default: minimal): ")).strip() or "minimal"
            run_command(["show", policy_name])
        elif choice == "5":
            task = input(style.info("Aufgabe (oder leer für Standard): ")).strip()
            if not task:
                task = "Lies 'aufgabe.md' und loese die Aufgabe."
            policy = input(style.info("Policy (default: minimal): ")).strip() or "minimal"
            args = ["run", task, "-p", policy]
            # Zusätzlich könnten wir task-file oder file unterstützen, aber fürs Menü halten wir es einfach
            run_command(args)
        elif choice == "6":
            provider = input(style.info("Provider (default: simulated,echo): ")).strip() or "simulated,echo"
            policy = input(style.info("Policy (default: minimal,research): ")).strip() or "minimal,research"
            run_command(["test", "--provider", provider, "--policy", policy])
        elif choice == "7":
            policy = input(style.info("Policy (default: minimal): ")).strip() or "minimal"
            only = input(style.info("Nur bestimmte Angriffe (kommagetrennt, optional): ")).strip()
            args = ["attacks", "-p", policy]
            if only:
                args.extend(["--only", only])
            run_command(args)
        elif choice == "8":
            run_dir = input(style.info("Pfad zum Laufordner oder audit.jsonl: ")).strip()
            if not run_dir:
                print(style.warning("Kein Pfad angegeben."))
                continue
            run_command(["verify", run_dir])
        elif choice == "9":
            policy = input(style.info("Policy (default: minimal): ")).strip() or "minimal"
            iterations = input(style.info("Iterationen (default: 5): ")).strip() or "5"
            warmup = input(style.info("Warmup (default: 1): ")).strip() or "1"
            code = input(style.info("Benutzerdefinierter Benchmark-Code (optional): ")).strip()
            args = ["benchmark", "-p", policy, "-i", iterations, "-w", warmup]
            if code:
                args.extend(["-c", code])
            run_command(args)
        elif choice == "10":
            run_custom_agent()
        else:
            print(style.warning("Ungültige Auswahl. Bitte erneut versuchen."))
        input(style.dim_text("\nDrücke Enter, um zum Menü zurückzukehren..."))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(style.error("\nProgramm abgebrochen."))
        sys.exit(1)