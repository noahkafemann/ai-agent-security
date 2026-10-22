#!/usr/bin/env python3
"""
Einfacher Custom-Agent-Runner für AGORIS.
Mit diesem Tool kann man schnell eigene Python-Dateien in der Sandbox testen.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agoris.policy import Policy
from agoris.launcher import run_snippet
from agoris.audit import AuditLog
from agoris import style


def _run_dir() -> str:
    """Laufordner unter runs/ - das Audit-Log soll nach dem Lauf noch da sein."""
    from agoris.cli import _new_run_dir

    return _new_run_dir("custom-agent")


def run_custom(file_path: str, policy_name: str = "minimal", timeout: float = 30.0):
    """Führt eine Python-Datei in der AGORIS-Sandbox aus."""
    if not os.path.exists(file_path):
        print(style.error(f"Datei nicht gefunden: {file_path}"))
        return 1

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            code = f.read()
    except UnicodeDecodeError as exc:
        print(style.error(f"Datei ist kein UTF-8-Text: {exc}"))
        return 1
    except OSError as exc:
        print(style.error(f"Datei nicht lesbar: {exc}"))
        return 1

    # Policy vorab prüfen: sonst bricht der Lauf mit einem DateiNotFoundError ab.
    verfuegbar = Policy.available()
    if policy_name not in verfuegbar:
        print(style.error(f"Policy '{policy_name}' nicht gefunden."))
        print(style.info(f"Verfuegbar: {', '.join(verfuegbar) if verfuegbar else '(keine)'}"))
        return 2

    print(style.header(f"Starte {os.path.basename(file_path)} in Sandbox"))
    print(style.info(f"Policy: {policy_name} | Timeout: {timeout}s"))
    print(style.dim_text("-" * 60))

    policy = Policy.load(policy_name)

    run_dir = _run_dir()
    audit = AuditLog(os.path.join(run_dir, "audit.jsonl"), echo=False)

    try:
        result = run_snippet(code, policy, run_dir, audit=audit,
                              timeout=timeout, label="custom")
    finally:
        audit.close()

    print(result.stdout.rstrip() if result.stdout else style.dim_text("(keine Ausgabe)"))
    if result.stderr:
        print(style.error("STDERR:"))
        print(result.stderr[:2000])

    print(style.dim_text("-" * 60))
    status = style.success("ERFOLG") if result.exit_code == 0 else style.error(f"FEHLER ({result.exit_code})")
    print(f"Status: {status} | Dauer: {result.seconds:.2f}s")
    print(f"Audit: {audit.path}")

    return 0 if result.exit_code in (0, None) else 1


def main():
    if len(sys.argv) < 2:
        print(style.header("Custom-Agent-Runner für AGORIS"))
        print("Verwendung:")
        print("  python3 custom_runner.py mein_agent.py")
        print("  python3 custom_runner.py mein_agent.py research 60")
        print()
        print("Beispiel:")
        print("  python3 custom_runner.py sample_agent.py")
        return 1

    file_path = sys.argv[1]
    policy = sys.argv[2] if len(sys.argv) > 2 else "minimal"

    timeout = 30.0
    if len(sys.argv) > 3:
        try:
            timeout = float(sys.argv[3])
        except ValueError:
            print(style.error(f"Timeout ist keine Zahl: {sys.argv[3]}"))
            print(style.info("Beispiel: python3 custom_runner.py agent.py minimal 60"))
            return 2

    return run_custom(file_path, policy, timeout)


if __name__ == "__main__":
    sys.exit(main())
