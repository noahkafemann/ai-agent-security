#!/usr/bin/env python3
"""Test-Harness: fuehrt die Sandbox gegen verschiedene Agenten-Konfigurationen aus.

Jeder "Agent" ist eine Kombination aus einer Policy (was er darf) und einem
Modell-Provider (wie er antwortet). Das Harness prueft, dass die Isolation
in jeder dieser Konfigurationen haelt.

    python3 tools/test_sandbox.py
    python3 tools/test_sandbox.py --provider simulated,echo
    python3 tools/test_sandbox.py --policy minimal,research
    python3 tools/test_sandbox.py --only key_leak,cpu_bomb

Keine externen Abhaengigkeiten. Alles aus der Standardbibliothek.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional, Tuple

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, WURZEL)

from agoris import attacks as attacks_mod
from agoris.audit import AuditLog
from agoris.compat import require_linux
from agoris.launcher import run_agent, run_snippet
from agoris.policy import Policy

PROVIDER_DEFAULTS = ("simulated", "echo")
POLICY_DEFAULTS = ("minimal", "research")
BANNER = "AGORIS - sichere Umgebung fuer unzuverlaessige KI-Agenten"


class TestResult:
    def __init__(self, name: str) -> None:
        self.name = name
        self.passed: bool = False
        self.details: str = ""
        self.seconds: float = 0.0
        self.metrics: Dict[str, Any] = {}


def _new_test_dir(prefix: str) -> str:
    return tempfile.mkdtemp(prefix=prefix, dir=tempfile.gettempdir())


def _test_doctor() -> TestResult:
    """Prueft, ob das System die Voraussetzungen erfuellt."""
    result = TestResult("doctor")
    started = time.time()
    try:
        from agoris.cli import doctor

        doctor()
        result.passed = True
        result.details = "Umgebung geprueft"
    except SystemExit:
        result.passed = False
        result.details = "doctor hat abgebrochen (SystemExit)"
    except Exception as exc:  # noqa: BLE001
        result.passed = False
        result.details = f"{type(exc).__name__}: {exc}"
    finally:
        result.seconds = round(time.time() - started, 2)
    return result


def _test_inspect(policy_name: str) -> TestResult:
    """Fuehrt die Innenansicht des Kaefigs aus und prueft die Ergebnisse."""
    result = TestResult(f"inspect:{policy_name}")
    started = time.time()
    run_dir = _new_test_dir("agoris-inspect-")
    try:
        from agoris.cli import _inspektions_skript

        policy = Policy.load(policy_name)
        audit = AuditLog(os.path.join(run_dir, "audit.jsonl"), echo=False)
        res = run_snippet(
            _inspektions_skript(), policy, run_dir, audit=audit, timeout=30, label="inspect"
        )
        audit.close()
        stdout = (res.stdout or "").strip()
        try:
            data = json.loads(stdout)
        except (json.JSONDecodeError, ValueError):
            result.passed = False
            result.details = f"Ausgabe nicht parsebar: {stdout[:200]}"
            return result

        checks = []
        usr_bin = data.get("4_inhalt_von_/usr_bin", [])
        if usr_bin != ["python3"]:
            checks.append(f"/usr/bin ≠ [python3]: {usr_bin}")
        geheimnisse = data.get("10_geheimnisse_sichtbar", [])
        if geheimnisse:
            checks.append(f"Geheimnisse: {geheimnisse}")
        netz = data.get("12_internetzugriff", "")
        if "unreachable" not in netz.lower() and "refused" not in netz.lower():
            checks.append(f"Netz nicht gesperrt: {netz}")
        writable = data.get("7_wo_darf_geschrieben_werden", {})
        for path, status in writable.items():
            if path in ("/work/probe.txt", "/tmp/probe.txt"):
                if status != "BESCHREIBBAR":
                    checks.append(f"{path} sollte schreibbar sein: {status}")
            else:
                if "Read-only" not in status and "BESCHREIBBAR" in status:
                    checks.append(f"{path} sollte read-only sein: {status}")

        result.passed = not checks
        result.details = "; ".join(checks) if checks else f"In {data.get('1_arbeitsverzeichnis', '?')}"
    except Exception as exc:  # noqa: BLE001
        result.passed = False
        result.details = f"{type(exc).__name__}: {exc}"
    finally:
        result.seconds = round(time.time() - started, 2)
        shutil.rmtree(run_dir, ignore_errors=True)
    return result


def _test_agent_run(policy_name: str, provider: str, task: str) -> TestResult:
    """Lauf mit einer bestimmten Policy + Provider-Kombination."""
    result = TestResult(f"run:{policy_name}/{provider}")
    started = time.time()
    run_dir = _new_test_dir(f"agoris-run-{policy_name}-{provider}-")
    try:
        policy = Policy.load(policy_name)
        audit = AuditLog(os.path.join(run_dir, "audit.jsonl"), echo=False)
        res = run_agent(task, policy, run_dir, audit=audit, model_provider=provider, wall_timeout=60)
        verification = audit.verify()
        audit.close()

        ok = bool(verification.get("valid"))
        inactive = res.jail_report.get("inactive_layers", [])

        if res.stopped != "finish":
            ok = False
        if not verification.get("valid"):
            ok = False

        result.passed = ok
        result.details = (
            f"{res.steps} Schritte, {res.seconds}s, "
            f"{len(res.tool_calls)} Werkzeugaufrufe, "
            f"inaktiv: {', '.join(inactive) if inactive else 'keine'}"
        )
        result.metrics = {
            "steps": res.steps,
            "seconds": res.seconds,
            "tool_calls": len(res.tool_calls),
            "stopped": res.stopped,
            "active_layers": res.jail_report.get("active_layers", []),
            "inactive_layers": inactive,
            "audit_entries": verification.get("entries", 0),
            "audit_valid": ok,
        }
    except Exception as exc:  # noqa: BLE001
        result.passed = False
        result.details = f"{type(exc).__name__}: {exc}"
    finally:
        result.seconds = round(time.time() - started, 2)
        shutil.rmtree(run_dir, ignore_errors=True)
    return result


def _test_attacks(policy_name: str, only: Optional[List[str]] = None) -> TestResult:
    """Fuehrt die Angriffsbatterie mit einer Policy aus."""
    result = TestResult(f"attacks:{policy_name}")
    started = time.time()
    run_dir = _new_test_dir(f"agoris-attacks-{policy_name}-")
    try:
        policy = Policy.load(policy_name)
        data = attacks_mod.run_all(run_dir, policy, timeout=25.0, echo=False, only=only)
        leaked = data["leaked"]
        blocked = data["blocked"]
        total = data["total"]
        errors = data.get("errors", 0)

        result.passed = (leaked == 0 and errors == 0)
        gap_list = data.get("gap_list", [])
        inactive = data.get("inactive_layers", [])
        parts = [f"{blocked}/{total} gehalten", f"{leaked} durchgegangen"]
        if gap_list:
            parts.append(f"Luecken: {', '.join(gap_list)}")
        if inactive:
            parts.append(f"inaktiv: {', '.join(inactive)}")
        result.details = "; ".join(parts)
        result.metrics = {
            "total": total,
            "blocked": blocked,
            "leaked": leaked,
            "gaps": data.get("gaps", 0),
            "errors": errors,
            "active_layers": data.get("active_layers", []),
            "inactive_layers": inactive,
        }
    except Exception as exc:  # noqa: BLE001
        result.passed = False
        result.details = f"{type(exc).__name__}: {exc}"
    finally:
        result.seconds = round(time.time() - started, 2)
        shutil.rmtree(run_dir, ignore_errors=True)
    return result


def _provider_available(provider: str) -> bool:
    from agoris import model as model_mod

    return provider in model_mod.PROVIDERS


def _print_result(r: TestResult) -> None:
    status = "OK" if r.passed else "FEHLER"
    print(f"  [{status:6}] {r.name:<30} ({r.seconds}s) {r.details}")


def run_tests(
    providers: List[str], policies: List[str], only_attacks: Optional[List[str]] = None
) -> Tuple[List[TestResult], int]:
    results: List[TestResult] = []

    print(f"\n{'=' * 64}")
    print(f"AGORIS Test-Harness: Sandbox gegen verschiedene Agenten")
    print(f"{'=' * 64}")
    print(f"Provider:  {', '.join(providers)}")
    print(f"Policies:  {', '.join(policies)}")
    if only_attacks:
        print(f"Angriffe:  {', '.join(only_attacks)}")
    print(f"{'=' * 64}\n")

    print("[1/4] Systemvoraussetzungen (doctor) ...")
    r = _test_doctor()
    results.append(r)
    _print_result(r)
    print()

    print("[2/4] Innenansicht (inspect) ...")
    for policy_name in policies:
        r = _test_inspect(policy_name)
        results.append(r)
        _print_result(r)
    print()

    print("[3/4] Agenten-Laeufe (run) ...")
    task = "Lies 'aufgabe.md' und schreibe das Ergebnis nach 'ergebnis.txt'."
    for policy_name in policies:
        for provider in providers:
            if not _provider_available(provider):
                r = TestResult(f"run:{policy_name}/{provider}")
                r.passed = False
                r.details = f"Provider '{provider}' nicht verfuegbar"
                results.append(r)
                _print_result(r)
                continue
            r = _test_agent_run(policy_name, provider, task)
            results.append(r)
            _print_result(r)
    print()

    print("[4/4] Angriffsbatterie (attacks) ...")
    for policy_name in policies:
        r = _test_attacks(policy_name, only=only_attacks)
        results.append(r)
        _print_result(r)
    print()

    print("=" * 64)
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    failed = total - passed
    if failed == 0:
        print(f"ALLE {total} TESTS BESTANDEN")
    else:
        print(f"{passed}/{total} Tests bestanden, {failed} FEHLER:")
        for r in results:
            if not r.passed:
                print(f"  - {r.name}: {r.details}")
    print("=" * 64)
    return results, 0 if failed == 0 else 1


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="test_sandbox",
        description="Testet die AGORIS-Sandbox gegen verschiedene Agenten-Konfigurationen",
    )
    parser.add_argument(
        "--provider",
        default=",".join(PROVIDER_DEFAULTS),
        help=f"Komma-getrennte Provider (Standard: {','.join(PROVIDER_DEFAULTS)})",
    )
    parser.add_argument(
        "--policy",
        default=",".join(POLICY_DEFAULTS),
        help=f"Komma-getrennte Policies (Standard: {','.join(POLICY_DEFAULTS)})",
    )
    parser.add_argument(
        "--only",
        default=None,
        help="Nur bestimmte Angriffe (kommagetrennt)",
    )
    args = parser.parse_args(argv)

    providers = [p.strip() for p in args.provider.split(",") if p.strip()]
    policies = [p.strip() for p in args.policy.split(",") if p.strip()]
    only = [a.strip() for a in args.only.split(",") if a.strip()] if args.only else None

    require_linux()
    results, code = run_tests(providers, policies, only_attacks=only)
    return code


if __name__ == "__main__":
    sys.exit(main())
