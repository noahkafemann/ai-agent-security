#!/usr/bin/env python3
"""Menü-Skript für AGORIS.

Dieses Skript präsentiert ein einfaches Menü, um verschiedene AGORIS-Funktionen
auszuführen. Es ermöglicht zudem das Ausführen einer benutzerdefinierten Python-
Datei als Agenten in der Sandbox.
"""

import os
import sys

# Sicherstellen, dass wir das AGORIS-Modul importieren können
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agoris import cli
from agoris.cli import BANNER
from agoris.policy import Policy
from agoris.launcher import run_snippet
from agoris.audit import AuditLog
from agoris import style


def frage(text, standard=""):
    """Fragt den Nutzer nach einer Eingabe.

    Ist die Eingabe geschlossen (Eingabeumleitung, Piping), endet das Menü
    sauber - statt mit einem EOFError-Absturz.
    """
    try:
        antwort = input(text).strip()
    except EOFError:
        print()
        raise SystemExit(0)
    return antwort or standard


def policy_vorhanden(name):
    """Prueft die Policy, bevor sie benutzt wird.

    Sonst bricht der Lauf mit einem DateiNotFoundError ab - mitten im Menü,
    ohne Hinweis, was falsch war.
    """
    verfuegbar = Policy.available()
    if name not in verfuegbar:
        print(style.error(f"Policy '{name}' nicht gefunden."))
        print(style.info(f"Verfuegbar: {', '.join(verfuegbar) if verfuegbar else '(keine)'}"))
        return False
    return True


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
    except (FileNotFoundError, ValueError) as e:
        # Unbekannte Policy, kaputte Datei: verständliche Meldung statt
        # eines Stapelabbruchs mitten im Menü.
        print(style.error(f"Befehl fehlgeschlagen: {e}"))
        return 2
    finally:
        sys.argv = old_argv


def run_custom_agent():
    """Führt eine benutzerdefinierte Python-Datei als Snippet in der Sandbox aus."""
    file_path = frage(style.info("Pfad zur Python-Datei eingeben: "))
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
    # Laufordner unter runs/ - kein temporaeres Verzeichnis: sonst ist das
    # Audit-Log im Moment der Ausgabe schon wieder geloescht.
    run_dir = cli._new_run_dir("custom-agent")
    audit_path = os.path.join(run_dir, "audit.jsonl")
    audit = AuditLog(audit_path, echo=False)

    print(style.header(f"Ausführung von {file_path} in der Sandbox (Policy: minimal)"))
    print(style.info(f"Arbeitsverzeichnis: {run_dir}"))
    print(style.dim_text("-" * 60))

    try:
        # Führe den Snippet aus
        result = run_snippet(
            code=code,
            policy=policy,
            run_dir=run_dir,
            audit=audit,
            timeout=30.0,  # Standardtimeout
            label="custom_agent",
        )
    finally:
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
        choice = frage(style.info("Deine Wahl: "))
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
            policy_name = frage(style.info("Policy name (default: minimal): "), "minimal")
            if policy_vorhanden(policy_name):
                run_command(["show", policy_name])
        elif choice == "5":
            task = frage(style.info("Aufgabe (oder leer für Standard): "))
            if not task:
                task = "Lies 'aufgabe.md' und loese die Aufgabe."
            policy = frage(style.info("Policy (default: minimal): "), "minimal")
            if not policy_vorhanden(policy):
                continue
            args = ["run", task, "-p", policy]
            # Zusätzlich könnten wir task-file oder file unterstützen, aber fürs Menü halten wir es einfach
            run_command(args)
        elif choice == "6":
            provider = frage(style.info("Provider (default: simulated,echo): "), "simulated,echo")
            policy = frage(style.info("Policy (default: minimal,research): "), "minimal,research")
            run_command(["test", "--provider", provider, "--policy", policy])
        elif choice == "7":
            policy = frage(style.info("Policy (default: minimal): "), "minimal")
            if not policy_vorhanden(policy):
                continue
            only = frage(style.info("Nur bestimmte Angriffe (kommagetrennt, optional): "))
            args = ["attacks", "-p", policy]
            if only:
                args.extend(["--only", only])
            run_command(args)
        elif choice == "8":
            run_dir = frage(style.info("Pfad zum Laufordner oder audit.jsonl: "))
            if not run_dir:
                print(style.warning("Kein Pfad angegeben."))
                continue
            run_command(["verify", run_dir])
        elif choice == "9":
            policy = frage(style.info("Policy (default: minimal): "), "minimal")
            if not policy_vorhanden(policy):
                continue
            iterations = frage(style.info("Iterationen (default: 5): "), "5")
            warmup = frage(style.info("Warmup (default: 1): "), "1")
            code = frage(style.info("Benutzerdefinierter Benchmark-Code (optional): "))
            args = ["benchmark", "-p", policy, "-i", iterations, "-w", warmup]
            if code:
                args.extend(["-c", code])
            run_command(args)
        elif choice == "10":
            run_custom_agent()
        else:
            print(style.warning("Ungültige Auswahl. Bitte erneut versuchen."))
        frage(style.dim_text("\nDrücke Enter, um zum Menü zurückzukehren..."))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(style.error("\nProgramm abgebrochen."))
        sys.exit(1)