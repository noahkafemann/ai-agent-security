"""Der Wirt: startet das Gefaengnis und spricht mit ihm.

Ablauf eines Agentenlaufs:

1. Policy laden und pruefen
2. Arbeitsverzeichnis (``run/<name>``) anlegen, Runtime-Code hineinkopieren
3. Audit-Log (Hash-Kette) oeffnen, ggf. Richtlinien-Proxy starten
4. ``fork`` -> Kind: Namespaces aufbauen, chroot, Rechte, Limits, seccomp,
   dann startet ``runtime/worker.py`` (der Agent) *oder* ein einzelnes
   Testskript (``snippet``) fuer die Angriffsbatterie
5. Eltern: Konfiguration schicken, Modellanfragen beantworten, Ereignisse
   sammeln, auf das Ergebnis warten, Proxy beenden

Wichtig: Der Elternprozess uebergibt *nur* die Pipes. Es gibt keinen zweiten
Kommunikationsweg in das Gefaengnis - das ist Teil des Sicherheitsmodells.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from . import jail as jail_mod
from . import model as model_mod
from .audit import AuditLog
from .policy import Policy
from .proxy import PolicyProxy
from .runtime.protocol import Channel

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE_ROOT = os.path.join(PROJECT_ROOT, "agoris")


class LaunchResult:
    def __init__(self) -> None:
        self.exit_code: Optional[int] = None
        self.signal: Optional[int] = None
        self.answer: str = ""
        self.jail_report: Dict[str, Any] = {}
        self.ready: Dict[str, Any] = {}
        self.steps: List[Dict[str, Any]] = []
        self.tool_calls: List[Dict[str, Any]] = []
        self.metrics: Dict[str, Any] = {}
        self.stopped: str = "?"
        self.steps: int = 0
        self.seconds: float = 0.0
        self.transcript: List[str] = []


class SnippetResult:
    def __init__(self) -> None:
        self.stdout: str = ""
        self.stdout_truncated: bool = False
        self.stderr: str = ""
        self.exit_code: Optional[int] = None
        self.signal: Optional[int] = None
        self.timed_out: bool = False
        self.jail_report: Dict[str, Any] = {}
        self.seconds: float = 0.0


# --------------------------------------------------------------------- Lauf
def run_agent(
    task: str,
    policy: Policy,
    run_dir: str,
    audit: Optional[AuditLog] = None,
    model_provider: Optional[str] = None,
    wall_timeout: Optional[float] = None,
    quiet: bool = False,
) -> LaunchResult:
    """Startet genau einen Agentenlauf und liefert das Ergebnis."""
    result = LaunchResult()
    jail_root = _prepare(run_dir, policy)
    package_copy = prepare_jail_dirs(run_dir, policy)

    audit = audit or AuditLog(os.path.join(run_dir, "audit.jsonl"), echo=False)
    provider = model_provider or policy.model.get("provider", "simulated")
    broker = model_mod.build_model(provider)

    socket_dir, socket_file = _socket_paths(run_dir)
    proxy = PolicyProxy(policy, socket_file, audit=audit, echo=not quiet)
    proxy_active = policy.network.get("mode") == "proxy"
    if proxy_active:
        proxy.start()

    config = {
        "op": "config",
        "task": task,
        "policy": policy.raw,
        "proxy_socket": "/run/agoris/proxy.sock" if proxy_active else None,
        "socket_dir": "/run/agoris" if proxy_active else None,
        "host_pid": os.getpid(),
    }

    audit.record("run_start", actor="host", task=task, policy=policy.name, provider=provider)
    started = time.time()

    # Zwei Pipes statt einer: eine je Richtung. Der Agent bekommt seine
    # Eingabe wirklich auf stdin - ein zweiter Kanal existiert nicht.
    host_to_agent_r, host_to_agent_w = os.pipe()
    agent_to_host_r, agent_to_host_w = os.pipe()
    pid = os.fork()
    if pid == 0:  # ----------------------------------------------------- Kind
        os.close(host_to_agent_w)
        os.close(agent_to_host_r)
        status = _child_agent(
            jail_root, policy, config, host_to_agent_r, agent_to_host_w, package_copy,
            socket_dir if proxy_active else None,
        )
        os._exit(status)

    # ---------------------------------------------------------- Elternteil
    os.close(host_to_agent_r)
    os.close(agent_to_host_w)
    child_out = os.fdopen(agent_to_host_r, "r", encoding="utf-8")
    child_in = os.fdopen(host_to_agent_w, "w", encoding="utf-8")
    channel = Channel(child_out, child_in)
    wall_deadline = started + (wall_timeout or (policy.process["wall_seconds"] + 30))

    try:
        channel.send(config)
        while True:
            if time.time() > wall_deadline:
                audit.record("wall_timeout", actor="host", limit=wall_timeout)
                _terminate(pid)
                result.stopped = "wall_timeout"
                break
            message = channel.recv()
            if message is None:
                break
            event = message.get("event") or message.get("op")
            if event == "ready":
                result.ready = message
                audit.record(
                    "jail_ready",
                    actor="agent",
                    **{k: message[k] for k in ("pid", "uid", "tools") if k in message},
                )
            elif event == "jail_report":
                result.jail_report = message.get("report", {})
                audit.record(
                    "jail_layers",
                    actor="sandbox",
                    active=result.jail_report.get("active_layers", []),
                    inactive=result.jail_report.get("inactive_layers", []),
                )
            elif event == "log":
                line = f"  [Schritt {message.get('step')}] {message.get('message')}"
                result.transcript.append(line)
                print(line, flush=True)
                audit.record(
                    "agent_message", actor="agent", step=message.get("step"), text=message.get("message")
                )
            elif event == "tool":
                call = message.get("call", {})
                result.tool_calls.append(call)
                flag = "BLOCKIERT" if call.get("blocked") else ("ok" if call.get("ok") else "fehlgeschlagen")
                line = f"    -> {call.get('tool')} [{flag}] {call.get('seconds')}s"
                result.transcript.append(line)
                print(line, flush=True)
                audit.record(
                    "tool_call",
                    actor="agent",
                    tool=call.get("tool"),
                    ok=call.get("ok"),
                    blocked=call.get("blocked"),
                    args=call.get("args"),
                )
            elif event == "result":
                result.answer = message.get("answer", "")
                result.steps = message.get("steps", [])
                result.metrics = message.get("metrics", {})
                result.stopped = message.get("stopped", "?")
            elif event == "fatal":
                result.stopped = "fatal"
                result.answer = message.get("error", "")
                audit.record("jail_fatal", actor="sandbox", error=message.get("error"))
            elif event == "llm_request":
                try:
                    reply = broker.complete(
                        message.get("messages", []), _tool_schemas(message.get("tools", []))
                    )
                except model_mod.BrokerError as exc:
                    reply = {"text": f"Modellfehler: {exc}", "tool_calls": []}
                channel.send({"op": "llm_result", "id": message["id"], "response": reply})
    except KeyboardInterrupt:
        _terminate(pid)
        result.stopped = "aborted"
    finally:
        try:
            child_out.close()
        except Exception:
            pass

    result.exit_code, result.signal = _reap(pid)
    result.seconds = round(time.time() - started, 2)
    if proxy_active:
        result.metrics.setdefault("proxy", dict(proxy.stats))
        proxy.stop()

    audit.record(
        "run_end",
        actor="host",
        stopped=result.stopped,
        seconds=result.seconds,
        exit_code=result.exit_code,
        signal=result.signal,
        tools=len(result.tool_calls),
    )
    return result


# ------------------------------------------------------- Angriffs-Testsnippet
def run_snippet(
    code: str,
    policy: Policy,
    run_dir: str,
    audit: Optional[AuditLog] = None,
    timeout: Optional[float] = None,
    label: str = "snippet",
) -> SnippetResult:
    """Fuehrt ein einzelnes Stueck Python im Gefaengnis aus (fuer die Tests)."""
    result = SnippetResult()
    jail_root = _prepare(run_dir, policy)
    package_copy = prepare_jail_dirs(run_dir, policy)
    audit = audit or AuditLog(os.path.join(run_dir, "audit.jsonl"), echo=False)
    timeout = timeout or min(float(policy.process["wall_seconds"]), 20)

    socket_dir, socket_file = _socket_paths(run_dir)
    proxy = PolicyProxy(policy, socket_file, audit=audit, echo=False)
    proxy_active = policy.network.get("mode") == "proxy"
    if proxy_active:
        proxy.start()

    out_r, out_w = os.pipe()
    err_r, err_w = os.pipe()
    report_r, report_w = os.pipe()
    devnull = os.open(os.devnull, os.O_RDONLY)

    audit.record("snippet_start", actor="host", label=label, timeout=timeout)
    started = time.time()
    pid = os.fork()
    if pid == 0:  # ----------------------------------------------------- Kind
        for fd in (out_r, err_r, report_r):
            os.close(fd)
        _child_snippet(
            jail_root,
            policy,
            code,
            package_copy,
            out_w,
            err_w,
            report_w,
            devnull,
            socket_dir if proxy_active else None,
        )
        os._exit(70)

    for fd in (out_w, err_w, report_w, devnull):
        os.close(fd)

    # Die Pipes werden gelesen, *waehrend* das Kind laeuft: sonst blockiert es,
    # sobald der Puffer (64 KiB) voll ist, und der Wirt wartet vergeblich.
    deadline = time.time() + timeout + 2
    buffers: Dict[int, List[Any]] = {}

    def reader(fd: int, limit: int) -> None:
        data, truncated = _read_capped(fd, limit, deadline)
        buffers[fd] = [data, truncated]

    threads = [
        threading.Thread(target=reader, args=(out_r, policy.process["max_output_bytes"]), daemon=True),
        threading.Thread(target=reader, args=(err_r, 16384), daemon=True),
        threading.Thread(target=reader, args=(report_r, 65536), daemon=True),
    ]
    for thread in threads:
        thread.start()

    status: Optional[int] = None
    while time.time() < deadline:
        waited, raw_status = os.waitpid(pid, os.WNOHANG)
        if waited == pid:
            status = raw_status
            break
        time.sleep(0.05)
    if status is None:
        result.timed_out = True
        audit.record("snippet_timeout", actor="host", label=label, timeout=timeout)
        _terminate(pid)
        _reap(pid)
    else:
        result.exit_code = os.WEXITSTATUS(status) if os.WIFEXITED(status) else None
        result.signal = os.WTERMSIG(status) if os.WIFSIGNALED(status) else None

    for thread in threads:
        thread.join(timeout=2)
    result.stdout, result.stdout_truncated = buffers.get(out_r, ["", False])
    result.stderr, _ = buffers.get(err_r, ["", False])
    report_raw, _ = buffers.get(report_r, ["", False])
    try:
        result.jail_report = json.loads(report_raw.strip().splitlines()[-1]) if report_raw.strip() else {}
    except (json.JSONDecodeError, IndexError):
        result.jail_report = {}

    result.seconds = round(time.time() - started, 2)
    if proxy_active:
        proxy.stop()
    audit.record(
        "snippet_end",
        actor="host",
        label=label,
        seconds=result.seconds,
        exit_code=result.exit_code,
        signal=result.signal,
        timed_out=result.timed_out,
    )
    return result


# ------------------------------------------------------------------ Kindseite
def _child_agent(
    jail_root: str,
    policy: Policy,
    config: Dict[str, Any],
    in_fd: int,
    out_fd: int,
    package_copy: str,
    host_socket_dir: Optional[str] = None,
) -> int:
    # Der Kanal des Agenten ist exakt stdin/stdout. stderr bleibt auf dem
    # Terminal - so sieht man Tracebacks auch bei einem abgestuerzten Lauf.
    os.dup2(in_fd, 0)
    os.dup2(out_fd, 1)
    child_out = os.fdopen(os.dup(1), "w", encoding="utf-8")
    child_in = os.fdopen(0, "r", encoding="utf-8")
    channel = Channel(child_in, child_out)
    # Wichtig: Fuer den Aufbau braucht der Kindprozess den *Host*-Pfad des
    # Sockets, fuer den Agenten gehoert der *Jail*-Pfad in die Policy.
    # Vertauscht man beide, versucht das Gefaengnis seinen eigenen Pfad zu
    # mounten - und scheitert mit ENOENT.
    extra = {
        "host_socket_dir": host_socket_dir,
        "jail_runtime": policy.system.get("jail_runtime", "minimal"),
    }
    try:
        report = jail_mod.enter(jail_root, policy, extra, extra_binds=[(package_copy, "/opt")])
        channel.send({"event": "jail_report", "report": report})
        _scoped_environment()
        os.chdir("/work")
        os.execv("/usr/bin/python3", ["/usr/bin/python3", "-I", "-B", "/opt/agoris/runtime/worker.py"])
    except OSError as exc:
        channel.send({"event": "fatal", "error": f"Start des Agenten fehlgeschlagen: {exc}"})
        return 71


def _child_snippet(
    jail_root: str,
    policy: Policy,
    code: str,
    package_copy: str,
    out_w: int,
    err_w: int,
    report_w: int,
    devnull: int,
    host_socket_dir: Optional[str] = None,
) -> None:
    extra = {
        "host_socket_dir": host_socket_dir,
        "jail_runtime": policy.system.get("jail_runtime", "minimal"),
    }
    try:
        report = jail_mod.enter(jail_root, policy, extra, extra_binds=[(package_copy, "/opt")])
        os.write(report_w, (json.dumps(report) + "\n").encode("utf-8"))
        os.close(report_w)
    except Exception as exc:
        try:
            os.write(report_w, (json.dumps({"error": f"{type(exc).__name__}: {exc}"}) + "\n").encode("utf-8"))
            os.close(report_w)
        except OSError:
            pass
        os.write(2, f"Gefaengnis-Aufbau fehlgeschlagen: {type(exc).__name__}: {exc}\n".encode())
        os._exit(72)
    _scoped_environment()
    os.dup2(devnull, 0)
    os.dup2(out_w, 1)
    os.dup2(err_w, 2)
    for fd in (out_w, err_w):
        if fd > 2:
            os.close(fd)
    os.chdir("/work")
    try:
        os.execv("/usr/bin/python3", ["/usr/bin/python3", "-I", "-B", "-c", code])
    except OSError as exc:  # pragma: no cover
        os.write(2, f"Start fehlgeschlagen: {exc}\n".encode())
        os._exit(71)


def _scoped_environment() -> None:
    """Umgebung auf das Minimum beschneiden - kein Schluessel, kein Wirts-PATH."""
    os.environ.clear()
    os.environ.update(
        {
            "PATH": "/usr/bin:/bin",
            "HOME": "/tmp",
            "TMPDIR": "/tmp",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "AGORIS_SANDBOX": "1",
            "LANG": "C.UTF-8",
        }
    )


# ------------------------------------------------------------------- Helfer
def _socket_paths(run_dir: str) -> Tuple[str, str]:
    """Kurzer Socket-Pfad - Unix-Sockets erlauben hoechstens 108 Zeichen.

    Das Arbeitsverzeichnis unter results/ ist deutlich laenger; deshalb liegt
    der Proxy-Socket in einem flachen Verzeichnis des temporaeren Laufwerks.
    """
    import hashlib
    import tempfile

    kennung = hashlib.sha1(run_dir.encode("utf-8")).hexdigest()[:10]
    socket_dir = os.path.join(tempfile.gettempdir(), f"agoris-{os.getpid()}-{kennung}")
    return socket_dir, os.path.join(socket_dir, "proxy.sock")


def _prepare(run_dir: str, policy: Policy) -> str:
    jail_root = os.path.join(run_dir, "jail")
    os.makedirs(os.path.join(jail_root, "work"), exist_ok=True)
    files = policy.raw.get("seed_files")
    if isinstance(files, dict):
        for name, content in files.items():
            path = os.path.join(jail_root, "work", name.lstrip("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(str(content))
    return jail_root


def prepare_jail_dirs(run_dir: str, policy: Policy) -> str:
    """Kopiert den Runtime-Code fuer das Gefaengnis (nur lesbar eingebunden).

    Wichtig: Der Kopier-Zielordner liegt *ausserhalb* von ``run_dir/jail`` und
    heisst ``payload/agoris`` - so entspricht ``payload`` dem Verzeichnis ``/opt``
    im Gefaengnis. Ein Ziel *innerhalb* von ``jail`` waere nach dem tmpfs-Mount
    unsichtbar.
    """
    payload = os.path.join(run_dir, "payload")
    target = os.path.join(payload, "agoris")
    if os.path.islink(target) or os.path.isfile(target):
        os.unlink(target)
    if os.path.isdir(target):
        shutil.rmtree(target)
    shutil.copytree(PACKAGE_ROOT, target, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
    return payload


def _tool_schemas(names: List[str]) -> List[Dict[str, Any]]:
    return [tool for tool in model_mod.TOOL_SCHEMA if tool["name"] in names]


def _reap(pid: int) -> Tuple[Optional[int], Optional[int]]:
    try:
        _pid, status = os.waitpid(pid, 0)
    except ChildProcessError:
        return None, None
    return (
        os.WEXITSTATUS(status) if os.WIFEXITED(status) else None,
        os.WTERMSIG(status) if os.WIFSIGNALED(status) else None,
    )


def _terminate(pid: int) -> None:
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            return
        for _ in range(10):
            time.sleep(0.05)
            try:
                waited, _status = os.waitpid(pid, os.WNOHANG)
                if waited == pid:
                    return
            except ChildProcessError:
                return


def _read_capped(fd: int, limit: int, deadline: float) -> Tuple[str, bool]:
    """Liest eine Pipe bis zum Ende, aber nie laenger als bis ``deadline``.

    Wichtig: nicht "keine Daten in 0,2 s" als Abbruchgrund - das Kind braucht
    nach dem Start gut eine halbe Sekunde. Abbruch ist EOF (Kind beendet) oder
    die Frist.
    """
    import select

    chunks: List[bytes] = []
    kept = 0
    truncated = False
    while time.time() < deadline:
        ready, _, _ = select.select([fd], [], [], 0.2)
        if not ready:
            continue
        try:
            chunk = os.read(fd, 65536)
        except OSError:
            break
        if not chunk:
            break
        if kept < limit:
            take = chunk[: limit - kept]
            chunks.append(take)
            kept += len(take)
        if kept >= limit:
            truncated = True
    try:
        os.close(fd)
    except OSError:
        pass
    return b"".join(chunks).decode("utf-8", "replace"), truncated