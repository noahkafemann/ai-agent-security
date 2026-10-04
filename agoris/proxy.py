"""Richtlinien-Proxy: der einzige Weg aus dem Gefaengnis nach draussen.

Im Netz-Namespace des Agenten gibt es *kein* Interface ausser einem
ausgeschalteten Loopback. Damit ist direkter Egress physikalisch unmoeglich -
aber der Weg durch den Proxy bleibt offen, denn der Socket des Proxy wird in
das Gefaengnis eingebunden. Jede Anfrage, die dort ankommt, wird gegen die
Policy geprueft:

* nur GET, nur http (kein https - dafuer waere TLS-Terminierung noetig)
* Host muss auf der Positivliste stehen
* Port darf nicht auf der Sperrliste stehen
* Antwortgroesse ist begrenzt

Der Proxy laeuft im Wirt und schreibt jede Entscheidung ins Audit-Log.
"""

from __future__ import annotations

import os
import socket
import threading
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlsplit


class PolicyProxy:
    def __init__(self, policy, socket_path: str, audit: Optional[Any] = None, echo: bool = True) -> None:
        self.policy = policy
        self.socket_path = socket_path
        self.audit = audit
        self.echo = echo
        self._server: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self.stats = {"requests": 0, "allowed": 0, "denied": 0, "bytes": 0}
        self._lock = threading.Lock()

    # --------------------------------------------------------------- lifecycle
    def start(self) -> None:
        os.makedirs(os.path.dirname(self.socket_path), exist_ok=True)
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(self.socket_path)
        os.chmod(self.socket_path, 0o666)
        server.listen(16)
        server.settimeout(0.5)
        self._server = server
        self._thread = threading.Thread(target=self._serve, name="policy-proxy", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        if self._server:
            self._server.close()
        socket_dir = os.path.dirname(self.socket_path)
        if os.path.isdir(socket_dir):
            try:
                os.rmdir(socket_dir)
            except OSError:
                pass

    def __enter__(self) -> "PolicyProxy":
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()

    # ------------------------------------------------------------------ serve
    def _serve(self) -> None:
        assert self._server is not None
        while not self._stop.is_set():
            try:
                client, _ = self._server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=self._handle, args=(client,), daemon=True).start()

    def _handle(self, client: socket.socket) -> None:
        with client:
            client.settimeout(self.policy.network.get("timeout_seconds", 15))
            try:
                data = b""
                while b"\r\n\r\n" not in data and len(data) < 16384:
                    chunk = client.recv(4096)
                    if not chunk:
                        break
                    data += chunk
                if not data:
                    return
                request_line = data.split(b"\r\n", 1)[0].decode("latin-1", "replace")
                parts = request_line.split()
                if len(parts) < 2:
                    self._respond(client, 400, "Bad Request")
                    return
                method, target = parts[0], parts[1]
                self._log("proxy_request", method=method, target=target)
                status, body = self._forward(method, target)
                self._respond(client, status, body)
            except socket.timeout:
                self._respond(client, 504, "Gateway Timeout")
            except Exception as exc:  # pragma: no cover - defensiv
                self._respond(client, 500, f"Proxy-Fehler: {exc}")

    # ----------------------------------------------------------------- policy
    def _decide(self, method: str, target: str) -> Tuple[bool, str, str]:
        """(erlaubt, Begruendung, absolute URL) - das Herz der Netz-Policy."""
        if method != "GET":
            return False, f"Methode {method} ist nicht freigegeben", ""
        if not target.startswith("http://"):
            scheme = target.split(":", 1)[0] if ":" in target else "?"
            return False, f"nur absolute http://-Ziele (war '{scheme}')", ""
        parts = urlsplit(target)
        if not parts.hostname:
            return False, "Ziel ohne Hostnamen", ""
        host = parts.hostname.lower()
        port = parts.port or 80
        if not self.policy.port_allowed(port):
            return False, f"Port {port} steht auf der Sperrliste", ""
        if not self.policy.domain_allowed(host):
            return False, f"Domain '{host}' steht nicht auf der Positivliste", ""
        return True, f"{host}:{port} erlaubt", target

    def _forward(self, method: str, target: str) -> Tuple[int, str]:
        with self._lock:
            self.stats["requests"] += 1
        allowed, reason, url = self._decide(method, target)
        if not allowed:
            with self._lock:
                self.stats["denied"] += 1
            self._log("proxy_denied", reason=reason, target=target)
            return 403, f"BLOCKIERT von der Sandbox-Policy: {reason}\nZiel: {target}\n"
        limit = int(self.policy.network.get("max_bytes_per_task", 2 << 20))
        request = urllib.request.Request(
            url, headers={"User-Agent": "agoris-proxy/1.0", "Accept": "*/*"}, method="GET"
        )
        try:
            with urllib.request.urlopen(request, timeout=self.policy.network.get("timeout_seconds", 15)) as response:
                payload = response.read(limit)
                status = response.status
        except urllib.error.HTTPError as exc:
            payload = exc.read(limit)
            status = exc.code
        except Exception as exc:
            self._log("proxy_error", url=url, error=str(exc))
            return 502, f"Upstream-Fehler: {exc}\n"
        with self._lock:
            self.stats["allowed"] += 1
            self.stats["bytes"] += len(payload)
        self._log("proxy_allowed", url=url, status=status, bytes=len(payload))
        return status, payload.decode("utf-8", "replace")

    @staticmethod
    def _respond(client: socket.socket, status: int, body: str) -> None:
        reason = {
            200: "OK",
            400: "Bad Request",
            403: "Forbidden",
            502: "Bad Gateway",
            504: "Gateway Timeout",
        }.get(status, "OK")
        head = (
            f"HTTP/1.1 {status} {reason}\r\n"
            "Content-Type: text/plain; charset=utf-8\r\n"
            f"Content-Length: {len(body.encode('utf-8'))}\r\n"
            "Connection: close\r\n\r\n"
        )
        try:
            client.sendall(head.encode("utf-8") + body.encode("utf-8"))
        except OSError:
            pass

    def _log(self, event: str, **data: Any) -> None:
        if self.audit:
            self.audit.record(event, actor="proxy", **data)
        elif self.echo:
            print(f"[proxy] {event} {data}", flush=True)