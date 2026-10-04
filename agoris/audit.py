"""Manipulationssicheres Audit-Log (Hash-Kette, JSONL).

Jeder Eintrag enthaelt den SHA-256-Hash seines Vorgaengers. Wer spaeter einen
Eintrag entfernt oder veraendert, bricht die Kette - und genau das ist fuer die
Auswertung eines Experiments der entscheidende Punkt: ein Protokoll, dem man
nicht glauben muss, sondern dem man nachweisen kann, dass es unveraendert ist.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional

GENESIS = "0" * 64


def _canonical(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


@dataclass
class AuditEntry:
    seq: int
    ts: float
    event: str
    actor: str
    data: Dict[str, Any]
    prev: str
    digest: str

    def to_json(self) -> str:
        return _canonical(
            {
                "seq": self.seq,
                "ts": round(self.ts, 6),
                "event": self.event,
                "actor": self.actor,
                "data": self.data,
                "prev": self.prev,
                "digest": self.digest,
            }
        )


@dataclass
class AuditLog:
    """Hash-verkettetes Ereignisprotokoll.

    Der Hash laeuft ueber ``seq | ts | event | actor | data | prev`` und bindet
    damit Zeitstempel, Inhalt *und* Vorgaenger aneinander. Ein nachtraeglicher
    Eingriff in die Mitte der Kette wird beim Verifizieren sichtbar.
    """

    path: str
    _last: str = GENESIS
    _seq: int = 0
    _fh: Optional[Any] = field(default=None, repr=False)
    echo: bool = True

    def __post_init__(self) -> None:
        directory = os.path.dirname(os.path.abspath(self.path))
        if directory:
            os.makedirs(directory, exist_ok=True)
        exists = os.path.exists(self.path) and os.path.getsize(self.path) > 0
        self._fh = open(self.path, "a", encoding="utf-8")
        if exists:
            for entry in self.read_all():
                self._last = entry.digest
                self._seq = entry.seq
        try:
            os.chmod(self.path, 0o444)
        except OSError:
            pass

    # ------------------------------------------------------------------ write
    def record(self, event: str, actor: str = "host", **data: Any) -> AuditEntry:
        self._seq += 1
        ts = time.time()
        prev = self._last
        body = _canonical(
            {"seq": self._seq, "ts": round(ts, 6), "event": event, "actor": actor, "data": data}
        )
        digest = hashlib.sha256(f"{prev}:{body}".encode("utf-8")).hexdigest()
        entry = AuditEntry(self._seq, ts, event, actor, data, prev, digest)
        assert self._fh is not None
        self._fh.write(entry.to_json() + "\n")
        self._fh.flush()
        self._last = digest
        if self.echo:
            print(f"[audit] {event:<22} {actor:<12} {_short(data)}", flush=True)
        return entry

    # ------------------------------------------------------------------- read
    def read_all(self) -> List[AuditEntry]:
        entries: List[AuditEntry] = []
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        entries.append(AuditEntry(**json.loads(line)))
        except FileNotFoundError:
            return []
        return entries

    def verify(self) -> Dict[str, Any]:
        """Prueft die Kette. Liefert einen kurzen Befund fuer Bericht/Website."""
        prev = GENESIS
        problems: List[str] = []
        count = 0
        for entry in self.read_all():
            body = _canonical(
                {
                    "seq": entry.seq,
                    "ts": round(entry.ts, 6),
                    "event": entry.event,
                    "actor": entry.actor,
                    "data": entry.data,
                }
            )
            expected = hashlib.sha256(f"{prev}:{body}".encode("utf-8")).hexdigest()
            if expected != entry.digest:
                problems.append(f"#{entry.seq}: Hash weicht ab (Eintrag veraendert)")
            if entry.prev != prev:
                problems.append(f"#{entry.seq}: prev-Verweis inkonsistent")
            prev = entry.digest
            count += 1
        return {
            "entries": count,
            "valid": not problems,
            "problems": problems,
            "head": prev,
        }

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None


def _short(data: Dict[str, Any], width: int = 68) -> str:
    text = _canonical(data)
    return text if len(text) <= width else text[: width - 1] + "…"


def iter_verified(path: str) -> Iterator[AuditEntry]:
    prev = GENESIS
    for entry in AuditLog(path, echo=False).read_all():
        yield entry
        prev = entry.digest