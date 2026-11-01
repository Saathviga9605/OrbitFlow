"""Single config loader so every script reads the same seeded settings."""
from __future__ import annotations

import os

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REAL_TRACE = os.path.join(ROOT, "data", "raw", "dynamic_ntn_dataset.csv")


def load_config(path: str | None = None) -> dict:
    with open(path or os.path.join(ROOT, "config.yaml")) as f:
        return yaml.safe_load(f)
