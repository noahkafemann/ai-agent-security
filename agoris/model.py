"""Modell-Broker: der Agent redet mit dem Modell, der *Schluessel* nicht.

Der API-Schluessel liegt ausschliesslich im Wirtprozess. Der Agent schickt
seine Konversation ueber den Kanal an den Wirt, der daraus eine echte
Modellanfrage macht und die Antwort zurueckgibt. Der Agent kann den Schluessel
also weder lesen noch ausgeben - unabhaengig davon, was er versucht.

Anbieter:

* ``simulated``  - deterministisch, ohne Netz, fuer reproduzierbare Laeufe
* ``echo``       - Minimalanbieter fuer Verbindungstests
* ``anthropic``  - echte API, nur mit ``urllib`` und Standardbibliothek
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, List, Optional

ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MAX_TOKENS = 1024

# Werkzeug-Schemata. Der Agent kann ausschliesslich diese Werkzeuge aufrufen -
# eine Liste, die der Wirt ihm gibt. Was nicht in dieser Liste steht, existiert
# fuer ihn nicht, unabhaengig davon, was ein Modell erfindet.
TOOL_SCHEMA: List[Dict[str, Any]] = [
    {
        "name": "read_file",
        "description": "Liest eine Datei aus dem Arbeitsverzeichnis (max. 100 KiB).",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Pfad relativ zu /work"}},
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Schreibt eine Datei in das Arbeitsverzeichnis.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "list_dir",
        "description": "Listet ein Verzeichnis auf.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "run_python",
        "description": "Fuehrt Python-Code in einer Subprozess-Debatte aus (ohne Netz).",
        "input_schema": {
            "type": "object",
            "properties": {"code": {"type": "string"}},
            "required": ["code"],
        },
    },
    {
        "name": "fetch_url",
        "description": "Liest eine Seite ueber den Richtlinien-Proxy (nur erlaubte Domains).",
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
    {
        "name": "finish",
        "description": "Beendet den Lauf mit einem Ergebnis. Pflicht als letzter Schritt.",
        "input_schema": {
            "type": "object",
            "properties": {"answer": {"type": "string"}},
            "required": ["answer"],
        },
    },
]

SYSTEM_PROMPT = (
    "Du bist ein Research-Agent in einer isolierten Sandbox. "
    "Arbeite schrittweise: Werkzeuge aufrufen, Zwischenergebnisse notieren, "
    "dann mit 'finish' abschliessen. Es gibt keinen Internetzugang ausser ueber "
    "einen Proxy, der nur freigegebene Domains durchlaesst."
)


class BrokerError(RuntimeError):
    pass


# ------------------------------------------------------------------ Protokoll
def _tool_choice_prompt(tools: List[Dict[str, Any]]) -> str:
    lines = [SYSTEM_PROMPT, "", "Du kannst ausschliesslich diese Werkzeuge aufrufen:"]
    for tool in tools:
        schema = tool["input_schema"]
        required = ", ".join(schema.get("required", [])) or "-"
        lines.append(f"- {tool['name']}: {tool['description']} (Pflichtfelder: {required})")
    lines += [
        "",
        "Antworte ausschliesslich mit einem JSON-Objekt in einer der beiden Formen:",
        '{"thought": "...", "tool": "name", "args": {...}}',
        '{"thought": "...", "tool": "finish", "args": {"answer": "..."}}',
    ]
    return "\n".join(lines)


def _parse_reply(text: str) -> Dict[str, Any]:
    """Ein Modell antwortet nicht immer sauber - das ist Normalfall, nicht Fehler."""
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.split("\n", 1)[-1] if "\n" in cleaned else cleaned
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError:
            pass
    return {"thought": cleaned[:400], "tool": "finish", "args": {"answer": cleaned}}


# ------------------------------------------------------------------- Anbieter
def _simulated(messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Deterministischer Anbieter ohne Netz - damit Laeufe vergleichbar bleiben."""
    step = sum(1 for message in messages if message.get("role") == "assistant")
    aufgabe = messages[0]["content"] if messages and messages[0].get("role") == "user" else ""
    namen = [tool["name"] for tool in tools]
    if step == 0:
        return {
            "text": json.dumps(
                {
                    "thought": "Zuerst schaue ich mir das Arbeitsverzeichnis an.",
                    "tool": "list_dir" if "list_dir" in namen else "finish",
                    "args": {"path": "."},
                },
                ensure_ascii=False,
            ),
        }
    if step == 1:
        ergebnis = "Datei not_found" if "read_file" not in namen else "gelesen"
        return {
            "text": json.dumps(
                {
                    "thought": "Jetzt schreibe ich das Ergebnis in eine Datei, damit es erhalten bleibt.",
                    "tool": "write_file" if "write_file" in namen else "finish",
                    "args": {"path": "ergebnis.txt", "content": f"Aufgabe: {aufgabe}\n{ergebnis}\n"},
                },
                ensure_ascii=False,
            )
        }
    return {
        "text": json.dumps(
            {
                "thought": "Die Aufgabe ist bearbeitet, ich schliesse ab.",
                "tool": "finish",
                "args": {"answer": f"[simulierter Anbieter] {len(aufgabe)} Zeichen Aufgabe verarbeitet, {step} Schritte."},
            },
            ensure_ascii=False,
        )
    }


def _echo(messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "text": json.dumps(
            {
                "thought": "Echo-Anbieter: kein echtes Modell.",
                "tool": "finish",
                "args": {"answer": "echo: " + json.dumps(messages[-1:], ensure_ascii=False)[:300]},
            },
            ensure_ascii=False,
        )
    }


def _anthropic(messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> Dict[str, Any]:
    key = os.environ.get("AGORIS_API_KEY", "")
    if not key:
        raise BrokerError("AGORIS_API_KEY fehlt im Wirt")
    model = os.environ.get("AGORIS_MODEL", "claude-sonnet-4-20250514")
    url = os.environ.get("AGORIS_API_URL", DEFAULT_ANTHROPIC_URL)
    payload = {
        "model": model,
        "max_tokens": DEFAULT_MAX_TOKENS,
        "system": _tool_choice_prompt(tools),
        "messages": [{"role": m["role"], "content": m["content"]} for m in messages if m.get("role") in ("user", "assistant")],
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "content-type": "application/json",
            "x-api-key": key,
            "anthropic-version": ANTHROPIC_VERSION,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise BrokerError(f"HTTP {exc.code}: {exc.read()[:200].decode('utf-8', 'replace')}") from exc
    except Exception as exc:
        raise BrokerError(str(exc)) from exc
    text = "".join(block.get("text", "") for block in data.get("content", []) if block.get("type") == "text")
    return {"text": text, "usage": data.get("usage", {})}


PROVIDERS: Dict[str, Callable[[List[Dict[str, Any]], List[Dict[str, Any]]], Dict[str, Any]]] = {
    "simulated": _simulated,
    "echo": _echo,
    "anthropic": _anthropic,
}


class ModelBroker:
    """Haelt den Zugang zum Modell - der Agent kommt hier nie ran."""

    def __init__(self, provider: str, key_visible: bool = False) -> None:
        if provider not in PROVIDERS:
            raise BrokerError(f"Unbekannter Anbieter '{provider}' (bekannt: {', '.join(sorted(PROVIDERS))})")
        self.provider = provider
        self.calls = 0
        self.key_visible = key_visible

    def complete(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> Dict[str, Any]:
        self.calls += 1
        reply = PROVIDERS[self.provider](messages, tools or TOOL_SCHEMA)
        reply.setdefault("text", "")
        return reply


def build_model(provider: str) -> ModelBroker:
    return ModelBroker(provider)