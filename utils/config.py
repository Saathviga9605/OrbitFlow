"""Single config loader so every script reads the same seeded settings."""
from __future__ import annotations

import os

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REAL_TRACE = os.path.join(ROOT, "data", "raw", "open_ntn_traffic_dataset.csv")     # 58 cells x 100 slots, OpenNTN traffic export
SIONNA_TRACE = os.path.join(ROOT, "data", "raw", "sionna_channel_dataset.csv")     # same cells and slots, Sionna channel export


def load_config(path: str | None = None) -> dict:
    with open(path or os.path.join(ROOT, "config.yaml")) as f:
        return yaml.safe_load(f)
