"""Append-only JSONL audit log with a tiny reader for the dashboard."""
from __future__ import annotations

import json
import os

import numpy as np

from audit.schemas import AuditRecord


def _clean(o):
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, np.ndarray):
        return _clean(o.tolist())
    if isinstance(o, (np.floating,)):
        return round(float(o), 4)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, float):
        return round(o, 4)
    return o


class AuditLogger:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    def write(self, record: AuditRecord) -> None:
        with open(self.path, "a") as f:
            f.write(json.dumps(_clean(record.to_dict())) + "\n")

    def read(self) -> list[dict]:
        if not os.path.exists(self.path):
            return []
        with open(self.path) as f:
            return [json.loads(line) for line in f if line.strip()]

    def clear(self) -> None:
        if os.path.exists(self.path):
            os.remove(self.path)
