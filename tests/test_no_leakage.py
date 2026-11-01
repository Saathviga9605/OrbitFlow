"""Test data leakage prevention in train/val/test splits."""
from __future__ import annotations

import pytest

from traffic.splits import create_splits, validate_no_leakage


def test_splits_are_disjoint():
    """Train/val/test splits must have no seed overlap."""
    manifest = create_splits(n_per_kind=50, random_seed=123)
    assert validate_no_leakage(manifest), "Splits should be disjoint"


def test_splits_cover_all_episodes():
    """Every episode should be in exactly one split."""
    n_per_kind = 40
    manifest = create_splits(n_per_kind=n_per_kind, random_seed=456)
    
    n_kinds = len(manifest.scenario_kinds)
    total_expected = n_kinds * n_per_kind
    total_actual = len(manifest.train_episodes) + len(manifest.val_episodes) + len(manifest.test_episodes)
    
    assert total_actual == total_expected, f"Expected {total_expected} episodes, got {total_actual}"


def test_splits_respect_ratios():
    """Train/val/test splits should match requested ratios (within rounding)."""
    manifest = create_splits(
        n_per_kind=100,
        train_ratio=0.70,
        val_ratio=0.15,
        random_seed=789,
    )
    
    total = len(manifest.train_episodes) + len(manifest.val_episodes) + len(manifest.test_episodes)
    
    train_ratio = len(manifest.train_episodes) / total
    val_ratio = len(manifest.val_episodes) / total
    test_ratio = len(manifest.test_episodes) / total
    
    # Allow 2% tolerance for rounding
    assert abs(train_ratio - 0.70) < 0.02, f"Train ratio {train_ratio} ≠ 0.70"
    assert abs(val_ratio - 0.15) < 0.02, f"Val ratio {val_ratio} ≠ 0.15"
    assert abs(test_ratio - 0.15) < 0.02, f"Test ratio {test_ratio} ≠ 0.15"


def test_stratification_preserves_kind_distribution():
    """Each split should have episodes from all scenario kinds (stratified)."""
    manifest = create_splits(n_per_kind=50, random_seed=101)
    
    kinds = set(manifest.scenario_kinds)
    
    train_kinds = set(ep["kind"] for ep in manifest.train_episodes)
    val_kinds = set(ep["kind"] for ep in manifest.val_episodes)
    test_kinds = set(ep["kind"] for ep in manifest.test_episodes)
    
    assert train_kinds == kinds, "Train set missing some kinds"
    assert val_kinds == kinds, "Val set missing some kinds"
    assert test_kinds == kinds, "Test set missing some kinds"


def test_deterministic_seeding():
    """Same seed should produce identical splits."""
    manifest1 = create_splits(n_per_kind=50, random_seed=999)
    manifest2 = create_splits(n_per_kind=50, random_seed=999)
    
    assert manifest1.train_seeds() == manifest2.train_seeds(), "Train seeds differ"
    assert manifest1.val_seeds() == manifest2.val_seeds(), "Val seeds differ"
    assert manifest1.test_seeds() == manifest2.test_seeds(), "Test seeds differ"


def test_different_seed_produces_different_splits():
    """Different random seed should produce different splits."""
    manifest1 = create_splits(n_per_kind=50, random_seed=111)
    manifest2 = create_splits(n_per_kind=50, random_seed=222)
    
    # At least some difference expected (extremely unlikely to be identical)
    assert manifest1.train_seeds() != manifest2.train_seeds(), "Different seeds produced same split"


def test_real_trace_marked_in_test():
    """If real_trace_in_test=True, manifest should reflect it."""
    manifest = create_splits(real_trace_in_test=True)
    assert manifest.test_set_uses_real, "Real trace should be marked for test set"
    assert manifest.real_trace_path == "data/raw/open_ntn_l2_output.csv"
    
    manifest2 = create_splits(real_trace_in_test=False)
    assert not manifest2.test_set_uses_real, "Real trace should not be marked"
    assert manifest2.real_trace_path is None
