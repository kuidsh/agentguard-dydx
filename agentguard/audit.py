"""Append-only, hash-chained audit log (JSON Lines).

Each record stores the SHA-256 of the previous record, so editing or deleting any
line breaks verification. In AWS the same lines go to an S3 bucket with Object Lock
(see infra/template.yaml) for tamper-evident retention.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path
from typing import Iterator

GENESIS = "0" * 64


def _canon(obj: dict) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()


class AuditLog:
    def __init__(self, path: str | Path, clock=time.time):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._clock = clock
        self._last = self._tail_hash()

    def _tail_hash(self) -> str:
        if not self.path.exists() or self.path.stat().st_size == 0:
            return GENESIS
        last = None
        with self.path.open("rb") as f:
            for line in f:
                if line.strip():
                    last = line
        return json.loads(last)["hash"] if last else GENESIS

    def append(self, event: str, data: dict) -> dict:
        with self._lock:
            body = {"ts": round(self._clock(), 3), "event": event, "data": data, "prev": self._last}
            rec = dict(body, hash=hashlib.sha256(_canon(body)).hexdigest())
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, sort_keys=True, default=str) + "\n")
            self._last = rec["hash"]
            return rec

    def records(self) -> Iterator[dict]:
        if not self.path.exists():
            return
        with self.path.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    yield json.loads(line)

    def tail(self, n: int = 20) -> list[dict]:
        return list(self.records())[-n:]


def verify(path: str | Path) -> tuple[bool, int, str]:
    """Return (ok, records_checked, message)."""
    prev = GENESIS
    n = 0
    for n, rec in enumerate(AuditLog(path).records(), start=1):
        body = {k: rec[k] for k in ("ts", "event", "data", "prev")}
        if rec["prev"] != prev:
            return False, n, f"record {n}: prev hash mismatch"
        if hashlib.sha256(_canon(body)).hexdigest() != rec["hash"]:
            return False, n, f"record {n}: content was modified"
        prev = rec["hash"]
    return True, n, "chain intact"
