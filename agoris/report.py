"""Berichte: Was ist gelaufen, was hat gehalten, was wurde protokolliert.

Zwei Formate:

* Markdown - fuer Menschen, Aufgaben und das Versuchsprotokoll
* JSON     - fuer die Website und eigene Auswertungen

Wichtig fuer die wissenschaftliche Redlichkeit: Der Bericht sagt auch, welche
Schicht *nicht* aktiv war. Ein Lauf, bei dem seccomp nicht verfuegbar war, wird
nicht als "vollstaendig gesichert" verkauft, sondern als eingeschraenkt.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from . import seccomp as seccomp_mod

SICHERHEIT_NOTE = (
    "AGORIS ist kein vollstaendiger Sandbox-Ersatz. Es setzt Schichten, "
    "von denen jede einzelne Fehler haben kann - und manche Umgebungen erlauben "
    "nicht alle Schichten (z. B. seccomp). Der Bericht weist das aus."
)


def run_report(
    result,
    policy,
    audit_path: str,
    audit_ok: Optional[bool] = None,
) -> Dict[str, Any]:
    schichten = result.jail_report.get("layers", {})
    aktiv = sorted(result.jail_report.get("active_layers", []))
    inaktiv = sorted(result.jail_report.get("inactive_layers", []))
    return {
        "policy": policy.summary(),
        "outcome": {
            "stopped": result.stopped,
            "exit_code": result.exit_code,
            "signal": result.signal,
            "seconds": result.seconds,
            "answer": result.answer,
            "steps": result.steps,
        },
        "sandbox": {
            "active_layers": aktiv,
            "inactive_layers": inaktiv,
            "id_mapping": result.jail_report.get("layers", {}).get("id_maps", {}),
            "filesystem_events": result.jail_report.get("layers", {})
            .get("filesystem", {})
            .get("events", []),
            "privileges": result.jail_report.get("layers", {}).get("privileges", {}),
            "capabilities": result.jail_report.get("layers", {}).get("capabilities", {}),
            "rlimits": result.jail_report.get("layers", {}).get("rlimits", {}),
            "seccomp": result.jail_report.get("layers", {}).get("seccomp", {}),
        },
        "agent": {
            "pid_in_jail": result.ready.get("pid"),
            "uid_in_jail": result.ready.get("uid"),
            "tools": result.ready.get("tools", []),
            "api_key_visible": result.ready.get("info", {}).get("api_key_visible"),
            "writable_roots": result.ready.get("info", {}).get("writable_roots", []),
            "tool_calls": len(result.tool_calls),
            "metrics": result.metrics,
        },
        "tool_calls": [
            {"tool": c.get("tool"), "ok": c.get("ok"), "blocked": c.get("blocked"), "seconds": c.get("seconds")}
            for c in result.tool_calls
        ],
        "audit": {"path": audit_path, "chain_ok": audit_ok},
        "caveat": SICHERHEIT_NOTE,
    }


def attack_report(data: Dict[str, Any]) -> Dict[str, Any]:
    zurueck = dict(data)
    for eintrag in zurueck.get("ergebnisse", []):
        eintrag.pop("stdout", None)
        eintrag.pop("stderr", None)
    return zurueck


def to_markdown(daten: Dict[str, Any], audit_verified: Optional[bool] = None) -> str:
    if "ergebnisse" in daten:
        return _attacks_markdown(daten)
    return _run_markdown(daten, audit_verified)


def _run_markdown(daten: Dict[str, Any], audit_verified: Optional[bool]) -> str:
    policy = daten["policy"]
    outcome = daten["outcome"]
    sandbox = daten["sandbox"]
    agent = daten["agent"]
    zeilen = [
        "# AGORIS - Laufbericht",
        "",
        f"- **Policy:** `{policy['name']}` (v{policy['version']})",
        f"- **Ende:** `{outcome['stopped']}` nach {outcome['seconds']} s, Exit-Code {outcome['exit_code']}",
        f"- **Schritte:** {agent['metrics'].get('max_steps', '?')} Limit, {outcome['steps']} ausgefuehrt",
        "",
        "## Schichten",
        "",
        "| Schicht | Status | Hinweis |",
        "| --- | --- | --- |",
    ]
    gruende = {"seccomp": (sandbox.get("seccomp") or {}).get("reason", "")}
    for name in sandbox["active_layers"]:
        zeilen.append(f"| {name} | aktiv | |")
    for name in sandbox["inactive_layers"]:
        zeilen.append(f"| {name} | **inaktiv** | {gruende.get(name, '')} |")
    zeilen += [
        "",
        "## Was der Agent von sich sah",
        "",
        f"- PID im Gefaengnis: `{agent['pid_in_jail']}`",
        f"- UID im Gefaengnis: `{agent['uid_in_jail']}`",
        f"- API-Schluessel sichtbar: **{'ja' if agent['api_key_visible'] else 'nein'}**",
        f"- Werkzeuge: {', '.join(agent['tools']) or '-'}",
        f"- Schreibbare Wurzeln: {', '.join(agent['writable_roots'])}",
        "",
        "## Werkzeugaufrufe",
        "",
        "| Werkzeug | Ergebnis | blockiert | s |",
        "| --- | --- | --- | --- |",
    ]
    for call in daten["tool_calls"]:
        zeilen.append(
            f"| {call['tool']} | {'ok' if call['ok'] else 'fehlgeschlagen'} | "
            f"{'**ja**' if call['blocked'] else 'nein'} | {call['seconds']} |"
        )
    zeilen += [
        "",
        "## Ergebnis des Agenten",
        "",
        "```",
        (outcome["answer"] or "(keine Antwort)")[:1500],
        "```",
        "",
        "## Audit-Log",
        "",
        f"- Datei: `{daten['audit']['path']}`",
        f"- Hashkette gueltig: **{'ja' if (audit_verified if audit_verified is not None else daten['audit'].get('chain_ok')) else 'nein'}**",
        "",
        "## Einschraenkung",
        "",
        SICHERHEIT_NOTE,
        "",
    ]
    return "\n".join(zeilen)


def _attacks_markdown(daten: Dict[str, Any]) -> str:
    zeilen = [
        "# AGORIS - Angriffsbatterie",
        "",
        f"- **Policy:** `{daten['policy']}`",
        f"- **Versuche:** {daten['total']}",
        f"- **Gehalten:** {daten['blocked']}",
        f"- **Durchgekommen:** {daten['leaked']}",
        f"- **Luecken (Grenze griff nicht):** {daten.get('gaps', 0)}"
        + (f" - {', '.join(daten.get('gap_list', []))}" if daten.get("gap_list") else ""),
        f"- **Unentschieden:** {daten['errors']}",
        "",
        f"Schichten aktiv: {', '.join(daten.get('active_layers', [])) or '-'}",
        f"Schichten inaktiv: {', '.join(daten.get('inactive_layers', [])) or '-'}",
        "",
        "| Versuch | Schicht | Ergebnis | Begruendung | Zeit |",
        "| --- | --- | --- | --- | --- |",
    ]
    for eintrag in daten["ergebnisse"]:
        zeilen.append(
            f"| {eintrag['title']} | {eintrag['schicht']} | **{eintrag['status']}** | "
            f"{eintrag.get('begruendung', '')[:80]} | {eintrag['seconds']}s |"
        )
    zeilen += [
        "",
        "## Was die Status bedeuten",
        "",
        "- `blocked` - der Versuch hat die erwartete Sperre ausgeloest. Genau das",
        "  wollten wir beweisen; fuer die Anlage ist das ein Erfolg.",
        "- `leaked` - der Agent kam durch. Das waere ein echter Fund und ein Fehler",
        "  in der Anlage.",
        "- `gap` - kein Ausbruch, aber eine Schicht hat nicht gegriffen. Beispiele:",
        "  `RLIMIT_NPROC` gilt nicht fuer uid 0, oder seccomp fehlt in der Umgebung.",
        "  Wird getrennt ausgewiesen, damit die Sicherheit nicht ueberschaetzt wird.",
        "- `error` - der Versuch lieferte keine auswertbare Antwort.",
        "",
        "## Schichten, die geprueft wurden",
        "",
    ]
    for schicht in daten["schichten"]:
        zeilen.append(f"- {schicht}")
    zeilen += ["", "## Details", ""]
    for eintrag in daten["ergebnisse"]:
        zeilen += [
            f"### {eintrag['title']} (`{eintrag['attack']}`)",
            "",
            f"**Erwartung:** {eintrag['expected']} - **Ergebnis:** {eintrag['status']}",
            "",
            f"*Warum das funktionieren sollte:* {eintrag['why']}",
            "",
            "```",
            (eintrag.get("details") or "(keine Ausgabe)")[:400],
            "```",
            "",
        ]
    return "\n".join(zeilen)


def write(path: str, inhalt: str) -> str:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(inhalt)
    return path


def write_json(path: str, daten: Dict[str, Any]) -> str:
    return write(path, json.dumps(daten, indent=2, ensure_ascii=False, sort_keys=False) + "\n")


def layer_overview() -> Dict[str, Any]:
    """Kurzueberblick fuer die CLI und die Website."""
    return {
        "seccomp_blocked": seccomp_mod.describe(),
        "seccomp_blocked_count": len(seccomp_mod.blocked_syscalls()),
    }