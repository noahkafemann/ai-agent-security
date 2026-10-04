"""Der einzige Kanal zwischen Gefaengnis und Wirt.

Zwei Pipes, ein Protokoll: Der Agent kann Nachrichten senden
(``send``) und auf Antworten warten (``recv``). Jede Nachricht ist ein
JSON-Objekt mit ``op``. Das ist die *gesamte* Angriffsflaeche dieses Kanals -
deshalb wird hier nichts zusammen mit den Werkzeugen oder dem Modell vermischt.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Dict, Optional


class Channel:
    def __init__(self, reader=None, writer=None) -> None:
        self._in = reader or sys.stdin
        self._out = writer or sys.stdout
        self._pending: Dict[str, Dict[str, Any]] = {}

    def send(self, message: Dict[str, Any]) -> None:
        self._out.write(json.dumps(message, ensure_ascii=False) + "\n")
        self._out.flush()

    def recv(self, timeout: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """Naechste Nachricht. ``None`` heisst: der Wirt hat die Verbindung
        geschlossen - fuer den Agenten das Ende der Welt."""
        if self._pending:
            key, value = self._pending.popitem()
            return value
        line = self._in.readline()
        if not line:
            return None
        line = line.strip()
        if not line:
            return self.recv(timeout)
        return json.loads(line)

    def wait_for(self, op: str, timeout: Optional[float] = None) -> Optional[Dict[str, Any]]:
        while True:
            message = self.recv(timeout)
            if message is None:
                return None
            if message.get("op") == op:
                return message