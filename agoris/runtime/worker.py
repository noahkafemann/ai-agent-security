"""Der Agent-Loop. Laeuft als PID 1 im PID-Namespace des Gefaengnisses.

Ablauf eines Schrittes:

1. Kontext (``op=config``) vom Wirt entgegennehmen
2. "Systembericht" senden: PID, UID, Rechte, Werkzeuge, Pfade
3. Schleife: an den Wirt eine Modellanfrage schicken, Antwort auswerten,
   Werkzeug aufrufen, Ergebnis zurueckschicken
4. Bei ``finish`` oder bei erreichtem Schritt-/Zeitlimit beenden

Bemerkenswert fuer die Untersuchung: Der Agent hat **keinen** API-Schluessel
und **keinen** Netzwerkzugang. Beides liegt im Wirt. Deshalb kann ein
kompromittiertes Modell die Umgebung auch nicht verlassen - es kann nur die
Werkzeuge benutzen, die der Wirt ihm gegeben hat.
"""

from __future__ import annotations

import os
import resource
import sys
import time
import traceback
from typing import Any, Dict, List

if __package__ in (None, ""):  # pragma: no cover - Direktstart im Gefaengnis
    sys.path.insert(0, "/opt")

from agoris.policy import Policy
from agoris.runtime.protocol import Channel
from agoris.runtime.tools import ToolBox

MAX_STEPS_FALLBACK = 12


def _sysinfo() -> Dict[str, Any]:
    """Was der Agent von sich selbst weiss - und was eben *nicht*."""
    grenzen = {}
    for name in ("cpu", "as", "data", "fsize", "nproc", "nofile", "core"):
        wert = getattr(resource, f"RLIMIT_{name.upper()}", None)
        if wert is not None:
            grenzen[name] = resource.getrlimit(wert)[0]
    return {
        "pid": os.getpid(),
        "uid": os.getuid(),
        "gid": os.getgid(),
        "cwd": os.getcwd(),
        "root": "/",
        "euid_is_root": os.geteuid() == 0,
        "writable_roots": ["/work", "/tmp"],
        "capabilities_effective": [],
        "rlimits": grenzen,
        "env_visible": sorted(os.environ.keys()),
        "api_key_visible": "AGORIS_API_KEY" in os.environ,
        "filesystem": sorted(os.listdir("/")) if os.path.isdir("/") else [],
    }


def _tool_schema_for(tools) -> List[Dict[str, Any]]:
    from agoris import model as model_mod

    return [tool for tool in model_mod.TOOL_SCHEMA if tool["name"] in tools.available]


def main() -> int:
    channel = Channel()
    config = channel.recv()
    if not config or config.get("op") != "config":
        return 2
    policy = Policy.from_dict(config["policy"])
    # Der Proxy-Socket wird vom Wirt benannt; der Agent darf ihn nur benutzen,
    # nicht selbst bestimmen, wohin er zeigt.
    if config.get("proxy_socket"):
        policy.network["socket_path_in_jail"] = config["proxy_socket"]

    box = ToolBox(policy, channel)
    channel.send(
        {
            "event": "ready",
            "pid": os.getpid(),
            "uid": os.getuid(),
            "tools": box.available,
            "info": _sysinfo(),
        }
    )

    aufgabe = config.get("task", "")
    max_schritte = int(policy.model.get("max_steps", MAX_STEPS_FALLBACK))
    nachrichten: List[Dict[str, Any]] = [{"role": "user", "content": aufgabe}]
    channel.send({"event": "log", "step": 0, "message": f"Aufgabe erhalten ({len(aufgabe)} Zeichen)."})
    channel.send({"event": "log", "step": 0, "message": f"Werkzeuge: {', '.join(box.available)}"})

    start = time.time()
    budget = float(policy.process.get("wall_seconds", 300))
    schritte = 0
    antwort = ""
    grund = "step_limit"

    while schritte < max_schritte:
        if time.time() - start > budget:
            grund = "wall_clock_limit"
            break
        schritte += 1
        anfrage_id = f"s{schritte}"
        channel.send(
            {
                "event": "llm_request",
                "id": anfrage_id,
                "messages": nachrichten,
                "tools": box.available,
            }
        )
        antwort_rohdaten = channel.wait_for("llm_result")
        if antwort_rohdaten is None:
            grund = "host_disconnected"
            break
        roh = antwort_rohdaten.get("response", {})
        text = roh.get("text", "")
        from agoris.model import _parse_reply

        entscheidung = _parse_reply(text)
        gedanke = entscheidung.get("thought", "")
        werkzeug = entscheidung.get("tool", "finish")
        argumente = entscheidung.get("args", {}) or {}
        channel.send({"event": "log", "step": schritte, "message": f"{gedanke} -> {werkzeug}"})

        ergebnis = box.call(werkzeug, argumente)
        channel.send({"event": "tool", "call": ergebnis})

        nachrichten.append({"role": "assistant", "content": text[:2000]})
        nachrichten.append(
            {
                "role": "user",
                "content": f"Werkzeug '{werkzeug}' ergab: {str(ergebnis)[:1500]}",
            }
        )

        if werkzeug == "finish" and ergebnis.get("ok"):
            antwort = str(ergebnis.get("answer", ""))
            grund = "finish"
            break
        if werkzeug == "finish":
            grund = "finish_mit_fehler"

    channel.send(
        {
            "event": "result",
            "answer": antwort,
            "stopped": grund,
            "steps": schritte,
            "metrics": {
                "wall_seconds": round(time.time() - start, 2),
                "tool_calls": box.calls,
                "tools_blocked": box.blocked,
                "max_steps": max_schritte,
            },
        }
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BrokenPipeError:
        sys.exit(0)
    except Exception:  # pragma: no cover - letzter Ausweg
        traceback.print_exc()
        sys.exit(1)