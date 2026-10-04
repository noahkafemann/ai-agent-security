"""Die Werkzeuge des Agenten - und die Grenzen, die der *Wirt* setzt.

Zwei Dinge sind hier wichtig:

1. Jedes Werkzeug loest Pfade gegen ``/work`` auf. Es gibt kein ``..``, keinen
   absoluten Pfad, keine Symlink-Ausnahme: ``realpath`` muss innerhalb von
   ``/work`` bleiben, sonst wird der Zugriff abgelehnt.
2. Was hier nicht steht, existiert nicht. Der Agent hat kein ``subprocess``
   gegen den Wirt, keine Shell, keinen Socket ausser dem Proxy-Socket.

Der Werkzeugaufruf wird immer ueber den Kanal *gemeldet* - das Audit-Log
enthaelt damit auch jeden blockierten Versuch.
"""

from __future__ import annotations

import os
import socket
import subprocess
import time
from typing import Any, Callable, Dict, Optional

WORK_ROOT = "/work"
MAX_READ_BYTES = 100 * 1024
MAX_WRITE_BYTES = 64 * 1024
PYTHON_TIMEOUT = 10


class ToolError(Exception):
    pass


def _resolve(path: str) -> str:
    """Wandelt jeden Pfad in einen sicheren absoluten Pfad unterhalb von /work."""
    candidate = path if path.startswith("/") else os.path.join(WORK_ROOT, path)
    real = os.path.realpath(candidate)
    if real != WORK_ROOT and not real.startswith(WORK_ROOT + os.sep):
        raise ToolError(f"Pfad '{path}' verlaesst das Arbeitsverzeichnis - abgelehnt")
    return real


class ToolBox:
    def __init__(self, policy, channel) -> None:
        self.policy = policy
        self.channel = channel
        self.calls = 0
        self.blocked = 0
        self.log: list = []
        enabled = set(policy.tools.get("enabled", {}) or {})
        self._table: Dict[str, Callable[..., Dict[str, Any]]] = {
            "read_file": self.read_file,
            "write_file": self.write_file,
            "list_dir": self.list_dir,
            "run_python": self.run_python,
            "fetch_url": self.fetch_url,
            "finish": self.finish,
        }
        self.available = sorted(name for name in self._table if name in enabled or "finish" in enabled and name == "finish")

    # --------------------------------------------------------------- Werkzeuge
    def read_file(self, path: str = "", **_) -> Dict[str, Any]:
        real = _resolve(path)
        if not self.policy.path_readable(real):
            raise ToolError(f"'{path}' ist nicht lesbar (Policy)")
        if not os.path.isfile(real):
            return {"ok": False, "error": "not_found", "path": path}
        size = os.path.getsize(real)
        with open(real, "r", encoding="utf-8", errors="replace") as fh:
            data = fh.read(MAX_READ_BYTES)
        return {
            "ok": True,
            "path": path,
            "bytes": size,
            "truncated": size > MAX_READ_BYTES,
            "content": data,
        }

    def write_file(self, path: str = "", content: str = "", **_) -> Dict[str, Any]:
        real = _resolve(path)
        if not self.policy.path_writable(real):
            raise ToolError(f"'{path}' ist nicht beschreibbar (Policy)")
        data = (content or "").encode("utf-8")
        limit = int(self.policy.filesystem.get("max_file_bytes", 1 << 20))
        if len(data) > min(limit, MAX_WRITE_BYTES):
            raise ToolError(f"Schreibversuch zu gross: {len(data)} Bytes (max {min(limit, MAX_WRITE_BYTES)})")
        os.makedirs(os.path.dirname(real), exist_ok=True)
        with open(real, "w", encoding="utf-8") as fh:
            fh.write(content or "")
        return {"ok": True, "path": path, "bytes": len(data)}

    def list_dir(self, path: str = ".", **_) -> Dict[str, Any]:
        real = _resolve(path)
        if not self.policy.path_readable(real):
            raise ToolError(f"'{path}' ist nicht lesbar (Policy)")
        if not os.path.isdir(real):
            return {"ok": False, "error": "not_dir", "path": path}
        eintraege = sorted(os.listdir(real))
        return {"ok": True, "path": path, "entries": eintraege[:200], "count": len(eintraege)}

    def run_python(self, code: str = "", **_) -> Dict[str, Any]:
        """Python in einer Subprozess-Debatte.

        Auch das ist eine Schranke: rlimit AS und NPROC greifen fuer die
        Subprozesse. Allerdings *innerhalb* derselben Sandbox - das ist keine
        Zusaetzesicherung, sondern verhindert, dass ein fehlerhafter Aufruf den
        Lauf sofort mitnimmt.
        """
        if not code or not str(code).strip():
            raise ToolError("leerer Code")
        try:
            fertig = subprocess.run(
                ["/usr/bin/python3", "-I", "-B", "-c", str(code)],
                capture_output=True,
                text=True,
                timeout=PYTHON_TIMEOUT,
                cwd=WORK_ROOT,
                env={"PATH": "/usr/bin", "HOME": "/tmp"},
            )
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "timeout", "limit_seconds": PYTHON_TIMEOUT}
        return {
            "ok": fertig.returncode == 0,
            "exit_code": fertig.returncode,
            "stdout": fertig.stdout[-8000:],
            "stderr": fertig.stderr[-4000:],
        }

    def fetch_url(self, url: str = "", **_) -> Dict[str, Any]:
        """Der einzige Weg nach draussen - und auch er endet am Proxy.

        Die Pfad-Pruefung passiert *zusaetzlich* zum Wirt, damit der Agent eine
        klare Rueckmeldung bekommt. Die eigentliche Durchsetzung macht der
        Proxy: Selbst wenn dieser Code hier manipuliert wuerde, koennte der
        Proxy nichts weiterreichen, das nicht auf der Positivliste steht.
        """
        socket_path = self.policy.network.get("socket_path_in_jail", "/run/agoris/proxy.sock")
        from urllib.parse import urlsplit

        parts = urlsplit(url or "")
        if parts.scheme != "http":
            return {"ok": False, "error": "scheme_not_allowed", "detail": "nur http://"}
        if not self.policy.domain_allowed(parts.hostname or ""):
            return {"ok": False, "error": "domain_not_allowed", "detail": parts.hostname or ""}
        if not os.path.exists(socket_path):
            return {"ok": False, "error": "no_proxy", "detail": "kein Proxy-Socket im Gefaengnis"}
        anfrage = (
            f"GET {url} HTTP/1.1\r\nHost: {parts.netloc}\r\n"
            "User-Agent: agoris-agent/1.0\r\nAccept: */*\r\nConnection: close\r\n\r\n"
        ).encode("utf-8")
        verbindung = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        verbindung.settimeout(int(self.policy.network.get("timeout_seconds", 15)))
        try:
            verbindung.connect(socket_path)
            verbindung.sendall(anfrage)
            rohdaten = b""
            while len(rohdaten) < (1 << 20):
                stueck = verbindung.recv(65536)
                if not stueck:
                    break
                rohdaten += stueck
        except (socket.timeout, OSError) as exc:
            return {"ok": False, "error": "proxy_unreachable", "detail": str(exc)}
        finally:
            verbindung.close()
        kopf, _, koerper = rohdaten.partition(b"\r\n\r\n")
        zeile = kopf.split(b"\r\n", 1)[0].decode("latin-1", "replace")
        status = int(zeile.split()[1]) if len(zeile.split()) > 1 else 0
        return {
            "ok": status == 200,
            "status": status,
            "url": url,
            "body": koerper.decode("utf-8", "replace")[:8000],
        }

    def finish(self, answer: str = "", **_) -> Dict[str, Any]:
        return {"ok": True, "answer": answer}

    # -------------------------------------------------------------- Ausfuehren
    def call(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        start = time.time()
        self.calls += 1
        if name not in self._table:
            self.blocked += 1
            ergebnis = {"ok": False, "error": "unknown_tool", "detail": name}
        elif name not in self.available:
            self.blocked += 1
            ergebnis = {"ok": False, "error": "tool_not_enabled", "detail": name}
        else:
            try:
                ergebnis = self._table[name](**(args or {}))
            except ToolError as exc:
                self.blocked += 1
                ergebnis = {"ok": False, "error": "policy", "detail": str(exc)}
            except TypeError as exc:
                ergebnis = {"ok": False, "error": "bad_arguments", "detail": str(exc)}
            except Exception as exc:
                ergebnis = {"ok": False, "error": type(exc).__name__, "detail": str(exc)}
        ergebnis["tool"] = name
        ergebnis["args"] = args or {}
        ergebnis["seconds"] = round(time.time() - start, 3)
        ergebnis["blocked"] = not ergebnis.get("ok") and ergebnis.get("error") in (
            "policy",
            "tool_not_enabled",
            "unknown_tool",
        )
        self.log.append(ergebnis)
        return ergebnis