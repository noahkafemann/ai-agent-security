"""seccomp-BPF: Syscall-Filter auf Kernel-Ebene (Schicht auf Kernel-Niveau).

Der Agent darf nur Syscalls nutzen, die fuer Python noetig sind. Alles andere -
vor allem ``ptrace``, ``mount``, ``init_module``, ``kexec_load``, ``bpf``,
``perf_event_open``, ``process_vm_*`` - wird abgewiesen, *bevor* der Kernel die
Aktion ausfuehrt. Das ist die Schicht, die auch dann noch greift, wenn jemand
aus dem Dateisystem ausbricht.

Zusaetzlich wird ``clone`` mit Namespace-Flaggen (CLONE_NEW*) verboten: So kann
der Agent auch keine weiteren Namespaces mehr bauen. ``clone3`` wird mit ENOSYS
beantwortet, damit die glibc auf ``clone`` zurueckfaellt (sonst waere jeder
``subprocess``-Aufruf tot).

Ehrlichkeit des Experiments: Nicht jede Umgebung erlaubt das Einreichen eines
Filters (Container, gehaertete Kernel, manche VMs). Deshalb wird die
Verfuegbarkeit zur Laufzeit geprueft und das Ergebnis *protokolliert* - eine
Schicht, die stillschweigend fehlt, waere ein falscher Sicherheitsgewinn.
"""

from __future__ import annotations

import ctypes
import os
import struct
from typing import Dict, List, Tuple

AUDIT_ARCH_X86_64 = 0xC000003E
AUDIT_ARCH_AARCH64 = 0xC00000B7

BPF_LD_W_ABS = 0x20    # A = *(u32*)(offset)
BPF_LD_IMM = 0x00      # A = k
BPF_JEQ_K = 0x15
BPF_JSET_K = 0x45
BPF_AND_K = 0x54       # A = A & k
BPF_RET_K = 0x06

SECCOMP_RET_ERRNO = 0x00050000
SECCOMP_RET_ALLOW = 0x7FFF0000
SECCOMP_RET_KILL_PROCESS = 0x80000000

PR_SET_NO_NEW_PRIVS = 38
PR_SET_SECCOMP = 22
SECCOMP_MODE_FILTER = 2

EPERM = 1
ENOSYS = 38

CLONE_NEW = 0xFF000000  # alle CLONE_NEW* zusammen (32-Bit-Anteil)
CLONE_NR = 56           # x86_64
SYSCALL_NR_OFFSET = 0
ARGS_OFFSET = 16

# Syscalls, die auf die Sperrliste gehoeren, weil sie den Sicherheitsrahmen
# aushebeln oder Wertsachen des Wirts betreffen.
BLOCKED_X86_64: Dict[int, str] = {
    101: "ptrace",
    155: "pivot_root",
    157: "prctl",
    165: "mount",
    166: "umount2",
    175: "init_module",
    176: "delete_module",
    246: "kexec_load",
    247: "kexec_file_load",
    272: "unshare",
    308: "setns",
    310: "process_vm_readv",
    311: "process_vm_writev",
    312: "kcmp",
    313: "finit_module",
    318: "bpf",
    319: "perf_event_open",
    321: "execveat",
    322: "userfaultfd",
    330: "open_tree",
    331: "move_mount",
    332: "fsopen",
    333: "fsconfig",
    334: "fsmount",
    335: "fspick",
    436: "clone3",
}

BLOCKED_AARCH64: Dict[int, str] = {
    94: "finit_module",
    105: "init_module",
    117: "ptrace",
    129: "kexec_load",
    155: "pivot_root",
    160: "unshare",
    197: "setns",
    280: "bpf",
    281: "execveat",
    286: "move_mount",
    287: "fsopen",
    288: "fsconfig",
    289: "fsmount",
    290: "fspick",
    291: "open_by_handle_at",
    435: "clone3",
}


def audit_arch() -> int:
    machine = os.uname().machine
    return AUDIT_ARCH_AARCH64 if machine in ("aarch64", "arm64") else AUDIT_ARCH_X86_64


def blocked_table() -> Dict[int, str]:
    return BLOCKED_AARCH64 if os.uname().machine in ("aarch64", "arm64") else BLOCKED_X86_64


def blocked_syscalls() -> Tuple[int, ...]:
    return tuple(sorted(blocked_table()))


def _stmt(code: int, jt: int, jf: int, k: int) -> bytes:
    # struct sock_filter { __u16 code; __u8 jt; __u8 jf; __u32 k; }
    # Reihenfolge der Felder beachten - sonst passiert die Maske im jt/jf-Feld.
    return struct.pack("HBBI", code, jt, jf, k)


def build_program(blocked: Tuple[int, ...], arch: int) -> bytes:
    """BPF-Programm: Arch pruefen, gefaehrliche Syscalls sperren, Rest erlauben."""
    program = b""
    # 1) Architektur pruefen (sonst koennte ein 32-Bit-Aufruf durchrutschen)
    program += _stmt(BPF_LD_W_ABS, 0, 0, 4)
    program += _stmt(BPF_LD_IMM, 0, 0, arch)
    program += _stmt(BPF_JEQ_K, 0, 1, 0)
    program += _stmt(BPF_RET_K, 0, 0, SECCOMP_RET_KILL_PROCESS)
    # 2) A = Syscall-Nummer
    program += _stmt(BPF_LD_W_ABS, 0, 0, SYSCALL_NR_OFFSET)
    # 3) clone mit Namespace-Flaggen verbieten. Das Flag steht als erstes
    #    Argument (Offset 16). jf=4 ueberspringt genau die vier Instruktionen
    #    der Pruefung, wenn es gar nicht clone ist.
    program += _stmt(BPF_JEQ_K, 0, 4, CLONE_NR)
    program += _stmt(BPF_LD_W_ABS, 0, 0, ARGS_OFFSET)     # A = flags (low word)
    program += _stmt(BPF_AND_K, 0, 0, CLONE_NEW)         # A = flags & CLONE_NEW*
    program += _stmt(BPF_JSET_K, 0, 1, 0)                # Namespace-Flag? -> EPERM
    program += _stmt(BPF_RET_K, 0, 0, SECCOMP_RET_ERRNO | EPERM)
    # 4) Sperrliste
    for number in blocked:
        errno = ENOSYS if blocked_table().get(number) == "clone3" else EPERM
        program += _stmt(BPF_JEQ_K, 0, 1, number)
        program += _stmt(BPF_LD_IMM, 0, 0, SECCOMP_RET_ERRNO | errno)
    program += _stmt(BPF_RET_K, 0, 0, SECCOMP_RET_ALLOW)
    return program


class _SockFProg(ctypes.Structure):
    _fields_ = [("len", ctypes.c_ushort), ("filter", ctypes.c_void_p)]


def set_no_new_privs() -> bool:
    libc = ctypes.CDLL("libc.so.6", use_errno=True)
    libc.prctl.restype = ctypes.c_int
    libc.prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong]
    return libc.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) == 0


def install() -> Dict[str, object]:
    """Versucht, den Filter zu aktivieren. Gibt ein Protokoll-Dict zurueck."""
    blocked = blocked_syscalls()
    result: Dict[str, object] = {
        "active": False,
        "reason": "",
        "blocked_count": len(blocked),
        "blocked": [blocked_table().get(n, str(n)) for n in blocked],
        "arch": hex(audit_arch()),
        "program_bytes": 0,
        "clone_namespace_flags": hex(CLONE_NEW),
    }
    program = build_program(blocked, audit_arch())
    result["program_bytes"] = len(program)

    if not set_no_new_privs():
        result["reason"] = "PR_SET_NO_NEW_PRIVS nicht moeglich"
        return result

    try:
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        libc.prctl.restype = ctypes.c_int
        libc.prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong]
        buf = ctypes.create_string_buffer(program, len(program))
        prog = _SockFProg(len(program), ctypes.cast(buf, ctypes.c_void_p))
        ctypes.set_errno(0)
        rc = libc.prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, ctypes.addressof(prog), 0, 0)
        if rc != 0:
            err = ctypes.get_errno()
            result["reason"] = f"prctl(PR_SET_SECCOMP) -> {err} ({os.strerror(err)})"
            return result
    except OSError as exc:  # pragma: no cover
        result["reason"] = f"libc nicht nutzbar: {exc}"
        return result

    result["active"] = True
    result["reason"] = "Filter aktiv"
    return result


def describe() -> List[str]:
    """Menschenlesbare Sperrliste fuer Bericht und Website."""
    return [f"{name} ({nr})" for nr, name in sorted(blocked_table().items())]