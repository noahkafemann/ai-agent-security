"""Richtlinien (Policy-as-Code).

Die Policy beschreibt *durchgaengig*, was ein Agent darf:

* welche Dateien er lesen/schreiben darf (``filesystem``)
* welche Rechenressourcen er verbrauchen darf (``process``)
* wohin er im Netz darf (``network``)
* welche Werkzeuge (Tools) er benutzen darf (``tools``)

Wichtig fuer die Versuchsanlage: Die gleiche Policy wird an *zwei* Stellen
durchgesetzt - einmal im Wirt (Ressourcen, Netz-Proxy) und einmal im Gefaengnis
(Pfad-Fessel, Werkzeug-Filter). Verteidigung in der Tiefe: faellt eine Schicht
aus, traegt die andere.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

POLICY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "policies")

DEFAULTS: Dict[str, Any] = {
    "name": "unnamed",
    "version": 1,
    "description": "",
    "filesystem": {
        "read_only_mounts": ["/usr", "/lib", "/lib64", "/bin", "/sbin"],
        "writable": ["/work", "/tmp"],
        "forbidden": [
            "/proc/kcore",
            "/proc/self/mem",
            "/dev/mem",
            "/dev/kmem",
            "/dev/port",
            "/sys",
            "/etc/shadow",
            "/etc/sudoers",
            "/root",
            "/var/run/docker.sock",
        ],
        "max_file_bytes": 1_048_576,
        "max_workspace_bytes": 16_777_216,
        "max_path_depth": 12,
    },
    "process": {
        "cpu_seconds": 15,
        "wall_seconds": 90,
        "memory_mb": 256,
        "max_processes": 64,
        "max_open_files": 128,
        "max_output_bytes": 65_536,
        "core_dumps": False,
    },
    "network": {
        "mode": "none",  # "none" = kein Interface, "proxy" = nur ueber den Proxy
        "allowed_domains": [],
        "blocked_domains": [],
        "deny_ports": [22, 23, 25, 445, 3306, 5432, 6379],
        "max_bytes_per_task": 2_097_152,
        "timeout_seconds": 15,
    },
    "system": {
        "namespaces": ["user", "mount", "pid", "net", "ipc", "uts"],
        "seccomp": True,
        "drop_privileges": True,
        "no_new_privs": True,
        "readonly_root": True,
        "jail_runtime": "minimal",  # "minimal" = nur Python, "system" = ganzes /usr
    },
    "tools": {
        "enabled": ["read_file", "write_file", "list_dir", "run_python", "http_get", "finish"],
        "args_max_chars": 8_000,
    },
    "model": {
        "provider": "simulated",
        "max_steps": 10,
        "step_timeout_seconds": 60,
    },
}

_NAMESPACES = {"user", "mount", "pid", "net", "ipc", "uts"}


@dataclass
class Policy:
    name: str
    version: int
    description: str
    filesystem: Dict[str, Any]
    process: Dict[str, Any]
    network: Dict[str, Any]
    system: Dict[str, Any]
    tools: Dict[str, Any]
    model: Dict[str, Any]
    source: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    # -------------------------------------------------------------- factories
    @classmethod
    def load(cls, name_or_path: str) -> "Policy":
        path = name_or_path
        if not os.path.sep in name_or_path and not name_or_path.endswith(".json"):
            path = os.path.join(POLICY_DIR, f"{name_or_path}.json")
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"Policy '{name_or_path}' nicht gefunden (gesucht: {path}). "
                f"Verfuegbar: {', '.join(sorted(cls.available()))}"
            )
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return cls.from_dict(data, source=path)

    @classmethod
    def from_dict(cls, data: Dict[str, Any], source: Optional[str] = None) -> "Policy":
        merged = _deep_merge(DEFAULTS, data)
        policy = cls(
            name=merged["name"],
            version=int(merged["version"]),
            description=merged.get("description", ""),
            filesystem=merged["filesystem"],
            process=merged["process"],
            network=merged["network"],
            system=merged["system"],
            tools=merged["tools"],
            model=merged["model"],
            source=source,
            raw=merged,
        )
        errors = policy.validate()
        if errors:
            raise ValueError("Ungueltige Policy:\n  - " + "\n  - ".join(errors))
        return policy

    @staticmethod
    def available() -> List[str]:
        if not os.path.isdir(POLICY_DIR):
            return []
        return sorted(f[:-5] for f in os.listdir(POLICY_DIR) if f.endswith(".json"))

    # ------------------------------------------------------------ validation
    def validate(self) -> List[str]:
        errors: List[str] = []
        for key in ("filesystem", "process", "network", "system", "tools", "model"):
            if not isinstance(getattr(self, key), dict):
                errors.append(f"Abschnitt '{key}' fehlt oder ist kein Objekt")
        net_mode = self.network.get("mode")
        if net_mode not in ("none", "proxy"):
            errors.append("network.mode muss 'none' oder 'proxy' sein")
        if net_mode == "proxy" and not self.network.get("allowed_domains"):
            errors.append("network.mode='proxy' verlangt mindestens eine erlaubte Domain")
        for domain in self.network.get("allowed_domains", []):
            if "/" in domain or ":" in domain:
                errors.append(f"allowed_domains: '{domain}' muss ein reiner Hostname sein")
        for value in ("cpu_seconds", "max_processes", "max_open_files", "max_output_bytes"):
            if int(self.process.get(value, 0)) <= 0:
                errors.append(f"process.{value} muss groesser als 0 sein")
        if int(self.process.get("memory_mb", 0)) <= 0:
            errors.append("process.memory_mb muss groesser als 0 sein")
        if int(self.process.get("wall_seconds", 0)) <= 0:
            errors.append("process.wall_seconds muss groesser als 0 sein")
        for ns in self.system.get("namespaces", []):
            if ns not in _NAMESPACES:
                errors.append(f"unbekannter Namespace '{ns}' (erlaubt: {sorted(_NAMESPACES)})")
        if "user" not in self.system.get("namespaces", []):
            errors.append("user-Namespace ist Pflicht (ohne ihn fehlt die Rechteisolierung)")
        if "mount" not in self.system.get("namespaces", []):
            errors.append("mount-Namespace ist Pflicht (ohne ihn fehlt die Dateisystemisolierung)")
        if self.system.get("jail_runtime", "minimal") not in ("minimal", "system"):
            errors.append("system.jail_runtime muss 'minimal' oder 'system' sein")
        if not self.tools.get("enabled"):
            errors.append("tools.enabled ist leer - der Agent koennte nichts tun")
        if "finish" not in self.tools.get("enabled", []):
            errors.append("tools.enabled muss 'finish' enthalten, sonst endet der Lauf nie")
        return errors

    # --------------------------------------------------------------- queries
    def tool_enabled(self, name: str) -> bool:
        return name in self.tools.get("enabled", [])

    def domain_allowed(self, host: str) -> bool:
        host = host.lower().split(":", 1)[0]
        for blocked in self.network.get("blocked_domains", []):
            if _host_matches(host, blocked.lower()):
                return False
        if self.network.get("mode") != "proxy":
            return False
        for allowed in self.network.get("allowed_domains", []):
            if _host_matches(host, allowed.lower()):
                return True
        return False

    def port_allowed(self, port: int) -> bool:
        return port not in set(self.network.get("deny_ports", []))

    def path_writable(self, abs_path: str) -> bool:
        if any(abs_path == p or abs_path.startswith(p.rstrip("/") + "/") for p in self.filesystem["forbidden"]):
            return False
        return any(abs_path == w or abs_path.startswith(w.rstrip("/") + "/") for w in self.filesystem["writable"])

    def path_readable(self, abs_path: str) -> bool:
        if any(abs_path == p or abs_path.startswith(p.rstrip("/") + "/") for p in self.filesystem["forbidden"]):
            return False
        return True

    def summary(self) -> Dict[str, Any]:
        """Kurzform fuer Berichte, CLI-Ausgabe und die Website."""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "source": self.source,
            "filesystem": {
                "writable": self.filesystem["writable"],
                "read_only_mounts": self.filesystem["read_only_mounts"],
                "forbidden_count": len(self.filesystem["forbidden"]),
                "max_file_bytes": self.filesystem["max_file_bytes"],
                "max_workspace_bytes": self.filesystem["max_workspace_bytes"],
            },
            "process": self.process,
            "network": {
                "mode": self.network["mode"],
                "allowed_domains": self.network["allowed_domains"],
                "deny_ports": self.network["deny_ports"],
            },
            "system": self.system,
            "tools": self.tools["enabled"],
            "model": self.model,
        }


def _host_matches(host: str, pattern: str) -> bool:
    if pattern.startswith("*."):
        return host == pattern[2:] or host.endswith(pattern[1:])
    return host == pattern


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def split_url(url: str):
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise ValueError(f"nur http/https erlaubt, nicht '{parts.scheme}'")
    if not parts.hostname:
        raise ValueError("URL ohne Hostnamen")
    return parts