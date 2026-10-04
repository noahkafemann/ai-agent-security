"""Ressourcen-Grenzen (Schicht 5) - was der Agent maximal verbrauchen darf.

``setrlimit`` wirkt sofort fuer den ganzen Prozess und alle Kinder. Wichtig:
Grenzen werden *vor* dem Start des Agenten gesetzt, damit es sich nicht selbst
freie Hand geben kann. RLIMIT_AS begrenzt den Adressraum, RLIMIT_CPU die
Rechenzeit (der Kernel schickt dann SIGXCPU), RLIMIT_FSIZE die Dateigroesse -
das ist der wichtigste Schutz gegen "die Festplatte zfuellen".
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

try:  # nur unter Unix; unter Windows gibt es kein resource-Modul
    import resource
except ImportError:  # pragma: no cover - Windows
    resource = None

MB = 1024 * 1024


def apply(process_policy: Dict[str, Any]) -> Dict[str, Any]:
    """Setzt alle Grenzen aus dem Policy-Abschnitt ``process``.

    Rueckgabe: ein Protokoll-Dict mit den gesetzten Werten fuer das Audit-Log.
    """
    if resource is None:  # pragma: no cover - Windows
        return {
            "active": False,
            "reason": "resource-Modul fehlt - setrlimit gibt es nur unter Unix",
            "applied": [],
            "not_applied": ["RLIMIT_CPU", "RLIMIT_AS", "RLIMIT_FSIZE", "RLIMIT_NPROC", "RLIMIT_NOFILE", "RLIMIT_CORE"],
        }
    mem_bytes = int(process_policy.get("memory_mb", 256)) * MB
    nofile = int(process_policy.get("max_open_files", 128))
    fsize = int(process_policy.get("max_file_bytes", 1 * MB))
    nproc = int(process_policy.get("max_processes", 64))
    cpu = int(process_policy.get("cpu_seconds", 15))
    core = 1 if process_policy.get("core_dumps", False) else 0

    settings = [
        ("RLIMIT_CPU", cpu),
        ("RLIMIT_AS", mem_bytes),
        ("RLIMIT_DATA", mem_bytes),
        ("RLIMIT_FSIZE", fsize),
        ("RLIMIT_NPROC", nproc),
        ("RLIMIT_NOFILE", nofile),
        ("RLIMIT_CORE", core),
    ]
    applied: List[Tuple[str, int, int]] = []
    for name, value in settings:
        key = getattr(resource, name, None)
        if key is None:
            continue
        try:
            _soft, hard = resource.getrlimit(key)
            if hard == resource.RLIM_INFINITY:
                # Achtung: RLIM_INFINITY ist -1. min(grenzwert, -1) waere -1 und
                # wuerde die Grenze wieder aufheben statt sie zu setzen.
                target_hard = resource.RLIM_INFINITY
                target_soft = value
            else:
                target_hard = min(hard, value)
                target_soft = min(value, target_hard)
            resource.setrlimit(key, (target_soft, target_hard))
            applied.append((name, target_soft, target_hard))
        except (ValueError, OSError) as exc:  # pragma: no cover - plattformabhaengig
            print(f"[limits] {name} nicht setzbar: {exc}", flush=True)
    gesetzt = {name for name, _soft, _hard in applied}
    return {
        "active": bool(applied),
        "applied": [{"limit": name, "soft": soft, "hard": hard} for name, soft, hard in applied],
        "not_applied": [
            name
            for name in (
                "RLIMIT_CPU",
                "RLIMIT_AS",
                "RLIMIT_FSIZE",
                "RLIMIT_NPROC",
                "RLIMIT_NOFILE",
                "RLIMIT_CORE",
            )
            if name not in gesetzt
        ],
    }


def current() -> Dict[str, int]:
    names = [
        "RLIMIT_CPU",
        "RLIMIT_AS",
        "RLIMIT_FSIZE",
        "RLIMIT_NPROC",
        "RLIMIT_NOFILE",
        "RLIMIT_CORE",
    ]
    out: Dict[str, int] = {}
    if resource is None:  # pragma: no cover - Windows
        return out
    for name in names:
        key = getattr(resource, name, None)
        if key is None:
            continue
        out[name] = resource.getrlimit(key)[0]
    return out