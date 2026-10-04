"""Das Gefaengnis: was *innen* passiert.

Dieses Modul laeuft im Kindprozess **nach** dem ``fork`` - also bereits in den
neuen Namespaces. Es baut die Sicht des Agenten auf: eigenes Dateisystem,
eigener Prozessbaum, eigenes (leeres) Netz, keine Rechte, keine Ressourcen
ohne Limit.

Schichten (jede einzelne wird protokolliert, keine wird stillschweigend
uebersprungen):

1. Policy          - was erlaubt ist (agoris/policy.py)
2. Namespaces      - user | mount | pid | net | ipc | uts
3. Dateisystem     - chroot in tmpfs, minimale Laufzeitumgebung (nur Python)
4. Rechte          - no_new_privs, UID-Zuordnung, Capabilities verworfen
5. Ressourcen      - CPU, Speicher, Dateigroesse, Prozesse, Deskriptoren
6. seccomp-BPF     - Syscall-Sperrliste auf Kernel-Ebene (falls erlaubt)
7. Netz            - nur Loopback, Egress nur ueber den Richtlinien-Proxy
"""

from __future__ import annotations

import ctypes
import fcntl
import os
import shutil
import socket
import struct
import sys
from typing import Any, Dict, List, Optional, Tuple

from . import limits as limits_mod
from . import seccomp as seccomp_mod

libc = ctypes.CDLL("libc.so.6", use_errno=True)

# Namespace-Flags (Linux, x86_64/aarch64 identisch)
CLONE_NEWNS = 0x00020000
CLONE_NEWUTS = 0x04000000
CLONE_NEWIPC = 0x08000000
CLONE_NEWUSER = 0x10000000
CLONE_NEWPID = 0x20000000
CLONE_NEWNET = 0x40000000

MS_RDONLY = 1
MS_NOSUID = 2
MS_NODEV = 4
MS_NOEXEC = 8
MS_REMOUNT = 32
MS_BIND = 4096
MS_REC = 16384
MS_PRIVATE = 1 << 18

PR_CAPBSET_DROP = 24
SYS_capset = {"x86_64": 126, "aarch64": 91}.get(os.uname().machine, 126)
UNPRIVILEGED_UID = 65534
UNPRIVILEGED_GID = 65534

SIOCGIFFLAGS = 0x8913
SIOCSIFFLAGS = 0x8914
IFF_UP = 0x1

NAMESPACE_FLAGS = {
    "mount": CLONE_NEWNS,
    "uts": CLONE_NEWUTS,
    "ipc": CLONE_NEWIPC,
    "user": CLONE_NEWUSER,
    "pid": CLONE_NEWPID,
    "net": CLONE_NEWNET,
}

JAIL_LAYOUT = (
    "work",
    "tmp",
    "dev",
    "proc",
    "etc",
    "opt/agoris",
    "run/agoris",
    "home",
    "usr/bin",
    "usr/lib",
    "lib64",
)


class JailError(RuntimeError):
    pass


# --------------------------------------------------------------------- libc
def _libc_setup() -> None:
    libc.unshare.restype = ctypes.c_int
    libc.unshare.argtypes = [ctypes.c_int]
    libc.mount.restype = ctypes.c_int
    libc.mount.argtypes = [
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_ulong,
        ctypes.c_char_p,
    ]
    libc.chroot.restype = ctypes.c_int
    libc.chroot.argtypes = [ctypes.c_char_p]
    libc.prctl.restype = ctypes.c_int
    libc.prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong]
    libc.syscall.restype = ctypes.c_long


_libc_setup()


def _errno() -> int:
    return ctypes.get_errno()


# ------------------------------------------------------- Pfade der Laufzeit
def python_lib_dir() -> str:
    """Wo liegt die Standardbibliothek des Wirt-Python?"""
    return f"/usr/lib/python{sys.version_info.major}.{sys.version_info.minor}"


def multiarch_lib_dir() -> str:
    """Architektur-Spezifische Bibliotheken (libc, libm, der Loader)."""
    import glob

    for pattern in ("/usr/lib/*-linux-gnu", "/usr/lib/*-linux-gnu-gnu", "/lib/*-linux-gnu"):
        hits = sorted(glob.glob(pattern))
        if hits:
            return hits[0]
    return ""


def loader_path() -> str:
    for candidate in ("/lib64/ld-linux-x86-64.so.2", "/lib/ld-linux-aarch64.so.1", "/lib64/ld64.so.2"):
        if os.path.exists(candidate):
            return candidate
    return ""


# ------------------------------------------------------------------ Schritt 1
def unshare_all(namespaces: List[str]) -> Dict[str, Any]:
    flags = 0
    for name in namespaces:
        flags |= NAMESPACE_FLAGS.get(name, 0)
    if not flags:
        return {"active": False, "reason": "keine Namespaces angefordert"}
    ctypes.set_errno(0)
    rc = libc.unshare(flags)
    if rc != 0:
        err = _errno()
        return {
            "active": False,
            "reason": f"unshare fehlgeschlagen: {err} ({os.strerror(err)})",
            "requested": namespaces,
        }
    return {"active": True, "reason": "ok", "requested": namespaces}


# ------------------------------------------------------------------ Schritt 2
def write_id_maps(real_uid: int, real_gid: int) -> Dict[str, Any]:
    """Ordnet IDs im neuen User-Namespace zu.

    Versucht wird zuerst ein breiter Bereich (``0 <uid> 65536``), damit der
    Agent auf ``nobody`` fallen kann. Das gelingt nur mit entsprechenden Rechten
    im Wirt; sonst wird auf eine einzige ID zurueckgefallen - und das wird
    protokolliert, statt es zu verschweigen.
    """
    notes: List[str] = []
    try:
        with open("/proc/self/setgroups", "w") as fh:
            fh.write("deny")
    except OSError:
        notes.append("setgroups nicht schreibbar")
    wide = False
    zuordnungen = (
        (f"0 {real_uid} 65536\n", f"0 {real_uid} 1\n", "uid_map"),
        (f"0 {real_gid} 65536\n", f"0 {real_gid} 1\n", "gid_map"),
    )
    for breit, eng, target in zuordnungen:
        try:
            with open(f"/proc/self/{target}", "w") as fh:
                fh.write(breit)
            wide = True
        except OSError as exc:
            notes.append(f"{target} breit nicht moeglich ({exc.errno})")
            try:
                with open(f"/proc/self/{target}", "w") as fh:
                    fh.write(eng)
            except OSError as exc2:
                notes.append(f"{target} auch eng nicht moeglich ({exc2.errno})")
    return {"active": True, "wide_mapping": wide, "mapping": f"0 -> {real_uid}", "notes": notes}


# ------------------------------------------------------------------ Schritt 3
def mount(source: Optional[str], target: str, fstype: Optional[str], flags: int, data: Optional[str] = None) -> None:
    rc = libc.mount(
        source.encode() if source else None,
        target.encode(),
        fstype.encode() if fstype else None,
        ctypes.c_ulong(flags),
        data.encode() if data else None,
    )
    if rc != 0:
        err = _errno()
        raise OSError(err, f"mount({source} -> {target}): {os.strerror(err)}")


def _mkdirs(root: str, dirs: Tuple[str, ...], owner: int = -1) -> None:
    for name in dirs:
        path = os.path.join(root, name)
        os.makedirs(path, exist_ok=True)
        if owner >= 0:
            try:
                os.chown(path, owner, owner)
            except OSError:
                pass


def _ro_bind(source: str, target_path: str, jail_root: str, note: List[str]) -> None:
    full = os.path.join(jail_root, target_path.lstrip("/"))
    os.makedirs(os.path.dirname(full), exist_ok=True)
    if os.path.isdir(source):
        os.makedirs(full, exist_ok=True)
    else:
        # Bind-Ziel fuer eine einzelne Datei muss selbst eine Datei sein,
        # sonst schlaegt das Mount mit ENOTDIR fehl.
        with open(full, "w"):
            pass
    mount(source, full, "none", MS_BIND | MS_REC)
    mount("none", full, "none", MS_REMOUNT | MS_BIND | MS_RDONLY | MS_NOSUID | MS_NODEV)
    note.append(f"{source} -> {target_path} (nur lesbar)")


def _install_minimal_runtime(jail_root: str, events: List[str]) -> List[str]:
    """Baut eine *abgemagerte* Laufzeitumgebung: nur Python, sonst nichts.

    Das ist der entscheidende Unterschied zu einem Gefaengnis, in dem einfach
    das halbe Wirtssystem eingebunden ist: Es gibt keine Shell, keine
    Standardprogramme, keine Netzwerk-Werkzeuge. Was nicht mitgeliefert wird,
    kann der Agent auch nicht aufrufen - unabhaengig davon, was er sich wuenscht.
    """
    note: List[str] = []
    interpreter = os.path.realpath("/usr/bin/python3") if os.path.exists("/usr/bin/python3") else sys.executable
    target_interpreter = os.path.join(jail_root, "usr", "bin", "python3")
    os.makedirs(os.path.dirname(target_interpreter), exist_ok=True)
    shutil.copy2(interpreter, target_interpreter)
    os.chmod(target_interpreter, 0o755)
    note.append(f"Python-Interpreter als Kopie: {interpreter} -> /usr/bin/python3")

    stdlib = python_lib_dir()
    if os.path.isdir(stdlib):
        _ro_bind(stdlib, stdlib, jail_root, note)
    else:
        events.append(f"Standardbibliothek {stdlib} nicht gefunden")
    multilib = multiarch_lib_dir()
    if multilib:
        _ro_bind(multilib, multilib, jail_root, note)
    loader = loader_path()
    if loader:
        _ro_bind(loader, loader, jail_root, note)
    else:
        events.append("dynamischer Loader nicht gefunden")

    link = os.path.join(jail_root, "lib")
    if not os.path.exists(link):
        try:
            os.symlink("usr/lib", link)
        except OSError:
            pass
    events.append(
        "Minimale Laufzeit: nur /usr/bin/python3, /usr/lib/python* und die Systembibliotheken - "
        "keine Shell, keine Standardprogramme"
    )
    return note


def _build_minimal_etc(jail_root: str, events: List[str]) -> None:
    etc = os.path.join(jail_root, "etc")
    files = {
        "passwd": "root:x:0:0:root:/:/sbin/nologin\nnobody:x:65534:65534:nobody:/:/sbin/nologin\n",
        "group": "root:x:0:\nnogroup:x:65534:\n",
        "hosts": "127.0.0.1 localhost\n",
        "hostname": "agoris-jail\n",
        "nsswitch.conf": "passwd: files\ngroup: files\nhosts: files\n",
        "resolv.conf": "# kein DNS im Gefaengnis - Egress laeuft ueber den Proxy\n",
    }
    for name, content in files.items():
        with open(os.path.join(etc, name), "w", encoding="utf-8") as fh:
            fh.write(content)
    try:
        with open("/etc/ld.so.cache", "rb") as src:
            data = src.read()
        with open(os.path.join(etc, "ld.so.cache"), "wb") as dst:
            dst.write(data)
    except OSError:
        pass
    events.append("minimales /etc erzeugt (keine Wirts-Geheimnisse, kein DNS)")


def _build_minimal_dev(jail_root: str, events: List[str]) -> None:
    dev = os.path.join(jail_root, "dev")
    mount("tmpfs", dev, "tmpfs", MS_NOSUID, "size=1m,mode=0755")
    for node in ("null", "zero", "random", "urandom"):
        path = os.path.join(dev, node)
        with open(path, "w"):
            pass
        try:
            mount(f"/dev/{node}", path, "none", MS_BIND)
        except OSError as exc:
            events.append(f"/dev/{node} nicht bindbar ({exc.errno})")
    events.append("/dev: nur null, zero, random, urandom")


def setup_filesystem(
    jail_root: str,
    read_only_mounts: List[str],
    socket_dir: Optional[str],
    wide_ids: bool,
    workspace_mb: int = 32,
    extra_binds: Optional[List[Tuple[str, str]]] = None,
    runtime_mode: Optional[str] = None,
) -> Dict[str, Any]:
    """Baut das Dateisystem des Gefaengnisses auf."""
    events: List[str] = []
    root_uid = UNPRIVILEGED_UID if wide_ids else 0
    root_gid = UNPRIVILEGED_GID if wide_ids else 0

    mount("none", "/", "none", MS_REC | MS_PRIVATE)  # nichts mehr nach aussen propagieren
    events.append("/ privat (MS_REC|MS_PRIVATE)")

    os.makedirs(jail_root, exist_ok=True)
    # Achtung: tmpfs versteht nur size/mode/uid/gid - "nosuid,nodev" gehoeren
    # in die Flags, sonst schlaegt der Mount mit EINVAL fehl.
    mount(
        "tmpfs",
        jail_root,
        "tmpfs",
        MS_NOSUID | MS_NODEV,
        f"size={workspace_mb}m,mode=0755",
    )
    events.append(f"tmpfs auf {jail_root} ({workspace_mb} MiB, nosuid, nodev)")

    _mkdirs(jail_root, JAIL_LAYOUT)

    bound: List[str] = []
    if (runtime_mode or "minimal") == "minimal":
        bound += _install_minimal_runtime(jail_root, events)
    else:
        for host_path in read_only_mounts:
            if not os.path.exists(host_path):
                events.append(f"{host_path} fehlt im Wirt - uebersprungen")
                continue
            _ro_bind(host_path, host_path, jail_root, bound)
            bound.append(host_path)

    for source, target_path in extra_binds or []:
        if not os.path.exists(source):
            events.append(f"Extra-Bind {source} fehlt - uebersprungen")
            continue
        _ro_bind(source, target_path, jail_root, bound)
        bound.append(f"{source} -> {target_path}")

    events.append("nur lesbar eingebunden: " + ", ".join(bound))

    _build_minimal_etc(jail_root, events)

    # /proc ist optional: in vielen Container-Umgebungen verbietet der Kernel
    # das Mounten eines frischen procfs. Ohne /proc sieht der Agent ohnehin
    # keine fremden Prozesse (pid-Namespace!).
    try:
        mount("proc", os.path.join(jail_root, "proc"), "proc", MS_NOSUID | MS_NODEV | MS_NOEXEC)
        events.append("procfs eingebunden (PID 1 = Agent)")
    except OSError as exc:
        events.append(f"procfs nicht eingebunden ({exc.errno}) - unkritisch, pid-Namespace aktiv")

    _build_minimal_dev(jail_root, events)

    mount(
        "tmpfs",
        os.path.join(jail_root, "tmp"),
        "tmpfs",
        MS_NOSUID | MS_NODEV,
        "size=8m,mode=1777",
    )
    events.append("tmpfs auf /tmp (8 MiB, nosuid, nodev)")

    if socket_dir:
        # Quelle ist ein Pfad *auf dem Wirt*, Ziel immer /run/agoris im Gefaengnis.
        target = os.path.join(jail_root, "run", "agoris")
        os.makedirs(target, exist_ok=True)
        mount(socket_dir, target, "none", MS_BIND | MS_REC)
        mount("none", target, "none", MS_REMOUNT | MS_BIND | MS_RDONLY)
        events.append(f"Proxy-Socket aus {socket_dir} nach /run/agoris eingebunden (nur lesbar)")

    work = os.path.join(jail_root, "work")
    try:
        os.chown(work, root_uid, root_gid)
        os.chmod(work, 0o700 if root_uid else 0o755)
    except OSError:
        pass
    return {"active": True, "events": events, "root_uid": root_uid}


# ------------------------------------------------------------------ Schritt 4
def bring_up_loopback() -> Dict[str, Any]:
    """Im Netz-Namespace gibt es ein loopback - es ist nur ausgeschaltet."""
    if not os.path.exists("/sys/class/net/lo"):
        return {"active": False, "reason": "kein Loopback-Geraet"}
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        request = struct.pack("16sh", b"lo", 0)
        response = fcntl.ioctl(sock.fileno(), SIOCGIFFLAGS, request)
        flags = struct.unpack("16sh", response)[1]
        fcntl.ioctl(sock.fileno(), SIOCSIFFLAGS, struct.pack("16sh", b"lo", flags | IFF_UP))
        return {"active": True, "reason": "lo ist aktiv - aber ohne Weg nach draussen"}
    except OSError as exc:
        return {"active": False, "reason": f"ioctl fehlgeschlagen: {exc}"}
    finally:
        sock.close()


def drop_privileges(wide_ids: bool, no_new_privs: bool) -> Dict[str, Any]:
    result: Dict[str, Any] = {"active": True, "uid": os.getuid(), "gid": os.getgid(), "notes": []}
    try:
        os.setgroups([])
    except OSError as exc:
        result["notes"].append(f"setgroups: {exc}")
    if wide_ids:
        # Bei breiter Zuordnung laeuft der Prozess nach dem Schreiben der
        # uid_map bereits als 65534 - ein setuid waere dann ein No-Op (EINVAL).
        if os.getuid() == UNPRIVILEGED_UID and os.getgid() == UNPRIVILEGED_GID:
            result["notes"].append("laeuft bereits als nobody (65534) - Rechteabgabe durch die breite ID-Zuordnung")
        else:
            try:
                os.setgid(UNPRIVILEGED_GID)
                os.setuid(UNPRIVILEGED_UID)
                result["notes"].append("explizit auf nobody (65534) gesetzt")
            except OSError as exc:
                result["notes"].append(f"setuid: {exc}")
        result["uid"] = os.getuid()
        result["gid"] = os.getgid()
    else:
        result["notes"].append(
            f"uid bleibt {os.getuid()} *im neuen Namespace* - Rechte auf den Wirt hat der Prozess trotzdem nicht"
        )
    if no_new_privs and not seccomp_mod.set_no_new_privs():
        result["notes"].append("no_new_privs nicht gesetzt")
    return result


def drop_capabilities() -> Dict[str, Any]:
    """Wirft *alle* Linux-Capabilities weg.

    Warum das noetig ist: Laeuft der Wirt als root, dann ist der Prozess im
    neuen User-Namespace uid 0. uid 0 allein ist harmlos - gefaehrlich ist uid 0
    *mit* Capabilities (CAP_DAC_OVERRIDE, CAP_SYS_ADMIN, ...). Deshalb werden
    vor dem Start des Agenten sowohl die aktiven Capabilities als auch die
    Bounding-Set geleert. Nach dem naechsten exec ist die Permitted-Menge leer.
    """
    dropped = 0
    for cap in range(0, 41):
        ctypes.set_errno(0)
        if libc.prctl(PR_CAPBSET_DROP, cap, 0, 0, 0) == 0:
            dropped += 1
    cleared = False
    try:
        header = (ctypes.c_uint32 * 1)(0x20080522)  # _LINUX_CAPABILITY_VERSION_3
        data = (ctypes.c_uint32 * 6)(*([0] * 6))
        ctypes.set_errno(0)
        cleared = libc.syscall(ctypes.c_long(SYS_capset), header, data) == 0
    except Exception as exc:  # pragma: no cover
        return {"active": dropped > 0, "reason": f"bounding: {dropped}, capset: {exc}"}
    return {
        "active": True,
        "reason": (
            f"{dropped} Capabilities aus dem Bounding-Set entfernt, "
            f"capset={'ok' if cleared else 'fehlgeschlagen'}"
        ),
        "bounding_caps_dropped": dropped,
        "capset_cleared": cleared,
    }


def enter_chroot(jail_root: str) -> None:
    if libc.chroot(jail_root.encode()) != 0:
        err = _errno()
        raise OSError(err, f"chroot({jail_root}): {os.strerror(err)}")
    os.chdir("/work")


# ----------------------------------------------------------------- Gesamtablauf
def enter(
    jail_root: str,
    policy,
    handshake_extra: Dict[str, Any],
    extra_binds: Optional[List[Tuple[str, str]]] = None,
) -> Dict[str, Any]:
    """Kompletter Aufbau des Gefaengnisses. Wird im Kindprozess aufgerufen."""
    system = policy.system
    namespaces = list(system.get("namespaces", []))
    process_policy = dict(policy.process)
    fs_policy = dict(policy.filesystem)

    report: Dict[str, Any] = {"layers": {}}

    # Die echten IDs *vor* dem Namespace-Wechsel merken: danach liefert getuid()
    # nur noch die unzugeordnete Notfall-ID (65534).
    real_uid, real_gid = os.getuid(), os.getgid()

    # Reihenfolge ist bedeutsam: erst die Namespaces anlegen, *dann* die
    # ID-Zuordnung schreiben - vorher gibt es kein neues /proc/self/uid_map,
    # in das man schreiben koennte. Die Rechteabgabe kommt ans *Ende*: fuer
    # das Schreiben der Zuordnung und fuer den Dateisystemaufbau braucht man sie.
    report["layers"]["namespaces"] = unshare_all(namespaces)
    if not report["layers"]["namespaces"].get("active"):
        report["layers"]["namespaces"]["hinweis"] = (
            "Ohne aktive Namespaces laeuft der Agent ungeschuetzt - der Lauf wird als"
            " 'ungesichert' gewertet und sollte nicht fuer Auswertungen benutzt werden."
        )
    maps = (
        write_id_maps(real_uid, real_gid)
        if "user" in namespaces
        else {"active": False, "reason": "kein user-Namespace"}
    )
    report["layers"]["id_maps"] = maps
    wide_ids = bool(maps.get("wide_mapping"))

    fs = setup_filesystem(
        jail_root,
        list(fs_policy.get("read_only_mounts", [])),
        handshake_extra.get("host_socket_dir") or handshake_extra.get("socket_dir"),
        wide_ids,
        workspace_mb=max(
            16, int(fs_policy.get("max_workspace_bytes", 32 * 1024 * 1024)) // (1024 * 1024)
        ),
        extra_binds=extra_binds,
        runtime_mode=handshake_extra.get("jail_runtime"),
    )
    report["layers"]["filesystem"] = fs

    if "net" in namespaces:
        report["layers"]["loopback"] = bring_up_loopback()

    enter_chroot(jail_root)
    report["layers"]["chroot"] = {"active": True, "root": jail_root}

    report["layers"]["privileges"] = drop_privileges(
        wide_ids, bool(system.get("no_new_privs", True))
    )
    report["layers"]["capabilities"] = drop_capabilities()
    report["layers"]["rlimits"] = limits_mod.apply(
        {**process_policy, "max_file_bytes": fs_policy.get("max_file_bytes", 1 << 20)}
    )

    if system.get("seccomp", True):
        report["layers"]["seccomp"] = seccomp_mod.install()
    else:
        report["layers"]["seccomp"] = {"active": False, "reason": "in Policy abgeschaltet"}

    report["active_layers"] = [
        name for name, data in report["layers"].items() if isinstance(data, dict) and data.get("active")
    ]
    report["inactive_layers"] = [
        name for name, data in report["layers"].items() if isinstance(data, dict) and not data.get("active")
    ]
    return report