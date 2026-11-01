"""Dataset splitting with reproducibility, stratification, and leakage detection.

The dataset consists of:
- Real trace (external test set only, never trained on)
- Synthetic traces: 5 kinds × 120 episodes each

Split strategy:
- 70% train / 15% val / 15% test
- Stratified by scenario kind
- Deterministic (seeded)
- By-episode (never split a single episode across sets)

Temporal integrity:
- All timestamps within an episode are either all train, all val, or all test
- No lookahead: validation set cannot see training episodes' future data
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

import numpy as np


@dataclass
class SplitManifest:
    """Metadata about a dataset split."""
    
    train_episodes: list[dict]  # [{kind, seed}, ...]
    val_episodes: list[dict]
    test_episodes: list[dict]
    real_trace_path: str | None
    test_set_uses_real: bool
    scenario_kinds: list[str]
    total_episodes: int
    random_seed: int
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    def train_seeds(self) -> list[int]:
        """Extract seeds for training episodes."""
        return [ep["seed"] for ep in self.train_episodes]
    
    def val_seeds(self) -> list[int]:
        """Extract seeds for validation episodes."""
        return [ep["seed"] for ep in self.val_episodes]
    
    def test_seeds(self) -> list[int]:
        """Extract seeds for test episodes (synthetic only, excludes real trace)."""
        return [ep["seed"] for ep in self.test_episodes if ep.get("synthetic", True)]


def compute_episode_hash(kind: str, seed: int) -> str:
    """Compute a reproducible hash for an episode (kind, seed pair)."""
    s = f"{kind}:{seed}".encode("utf-8")
    return hashlib.sha256(s).hexdigest()[:8]


def create_splits(
    scenario_kinds: list[str] = None,
    n_per_kind: int = 120,
    train_ratio: float = 0.70,
    val_ratio: float = 0.15,
    seed0: int = 1000,
    random_seed: int = 42,
    real_trace_in_test: bool = True,
) -> SplitManifest:
    """
    Create deterministic train/val/test splits.
    
    Args:
        scenario_kinds: Scenario kinds to include (default: all 5)
        n_per_kind: Episodes per kind
        train_ratio: Fraction for training
        val_ratio: Fraction for validation
        seed0: Base seed for episode generation
        random_seed: Seed for split randomization (applied uniformly across kinds)
        real_trace_in_test: If True, mark real trace as part of test set
    
    Returns:
        SplitManifest with split information
    """
    if scenario_kinds is None:
        scenario_kinds = ["normal", "block", "event_surge", "bursty", "mixed"]
    
    # Verify ratios sum to 1.0
    test_ratio = 1.0 - train_ratio - val_ratio
    assert 0 < train_ratio < 1 and 0 < val_ratio < 1 and test_ratio > 0, "Invalid split ratios"
    
    # Create all episodes
    all_episodes = []
    for kind_idx, kind in enumerate(scenario_kinds):
        for j in range(n_per_kind):
            seed = seed0 + 1000 * kind_idx + j
            all_episodes.append({
                "kind": kind,
                "seed": seed,
                "synthetic": True,
                "hash": compute_episode_hash(kind, seed),
            })
    
    # Shuffle deterministically, stratified by kind
    rng = np.random.default_rng(random_seed)
    
    train_eps, val_eps, test_eps = [], [], []
    for kind in scenario_kinds:
        kind_episodes = [ep for ep in all_episodes if ep["kind"] == kind]
        n = len(kind_episodes)
        
        # Shuffle this kind deterministically
        indices = rng.permutation(n)
        kind_episodes = [kind_episodes[i] for i in indices]
        
        # Split this kind
        n_train = int(n * train_ratio)
        n_val = int(n * val_ratio)
        
        train_eps.extend(kind_episodes[:n_train])
        val_eps.extend(kind_episodes[n_train:n_train+n_val])
        test_eps.extend(kind_episodes[n_train+n_val:])
    
    # Add real trace to test set as metadata (never actually trained on)
    manifest = SplitManifest(
        train_episodes=train_eps,
        val_episodes=val_eps,
        test_episodes=test_eps,
        real_trace_path="data/raw/open_ntn_l2_output.csv" if real_trace_in_test else None,
        test_set_uses_real=real_trace_in_test,
        scenario_kinds=scenario_kinds,
        total_episodes=len(all_episodes),
        random_seed=random_seed,
    )
    
    return manifest


def validate_no_leakage(manifest: SplitManifest) -> bool:
    """
    Verify that train/val/test sets are disjoint (no seed overlap).
    
    Returns:
        True if valid (no leakage), False otherwise
    """
    train_seeds = set(manifest.train_seeds())
    val_seeds = set(manifest.val_seeds())
    test_seeds = set(manifest.test_seeds())
    
    # Check for overlaps
    train_val_overlap = train_seeds & val_seeds
    train_test_overlap = train_seeds & test_seeds
    val_test_overlap = val_seeds & test_seeds
    
    if train_val_overlap or train_test_overlap or val_test_overlap:
        print(f"❌ Leakage detected!")
        if train_val_overlap:
            print(f"   Train-Val overlap: {train_val_overlap}")
        if train_test_overlap:
            print(f"   Train-Test overlap: {train_test_overlap}")
        if val_test_overlap:
            print(f"   Val-Test overlap: {val_test_overlap}")
        return False
    
    print(f"✅ No leakage: {len(train_seeds)} train, {len(val_seeds)} val, {len(test_seeds)} test (disjoint)")
    return True


def save_manifest(manifest: SplitManifest, path: str) -> None:
    """Save manifest to JSON."""
    with open(path, "w") as f:
        json.dump(manifest.to_dict(), f, indent=2)
    print(f"✅ Saved split manifest to {path}")


def load_manifest(path: str) -> SplitManifest:
    """Load manifest from JSON."""
    with open(path) as f:
        data = json.load(f)
    return SplitManifest(**data)
