"""Statistics shared by every experiment. Paired, non-parametric by default: KPI differences are often skewed or tied."""
from __future__ import annotations

import numpy as np
from scipy import stats as st


def summary(v, seed: int = 0, n_boot: int = 2000) -> dict:
    v = np.asarray(v, float)
    v = v[~np.isnan(v)]
    if len(v) == 0:
        return {"n": 0, "mean": None, "sd": None, "median": None, "lo": None, "hi": None}
    if len(v) == 1:
        return {"n": 1, "mean": float(v[0]), "sd": None, "median": float(v[0]), "lo": None, "hi": None}
    m = v[np.random.default_rng(seed).integers(len(v), size=(n_boot, len(v)))].mean(1)
    return {"n": len(v), "mean": float(v.mean()), "sd": float(v.std(ddof=1)), "median": float(np.median(v)),
            "lo": float(np.percentile(m, 2.5)), "hi": float(np.percentile(m, 97.5))}


def paired(a, b, seed: int = 0) -> dict:
    """a vs b on the same episodes. Wilcoxon signed-rank, rank-biserial r, Cohen's dz, mean-difference CI.

    Wilcoxon needs symmetric differences to test the median exactly; without that it still tests for a location shift.
    """
    a, b = np.asarray(a, float), np.asarray(b, float)
    ok = ~(np.isnan(a) | np.isnan(b))
    d = (a - b)[ok]
    nz = d[np.abs(d) > 1e-12]
    out = {"n": int(ok.sum()), "test": "Wilcoxon signed-rank, two-sided", "mean_diff": float(d.mean()) if len(d) else None,
           "wins_a_lower": int((d < -1e-12).sum()), "wins_b_lower": int((d > 1e-12).sum()), "ties": int((np.abs(d) <= 1e-12).sum())}
    if len(d) > 1:
        m = d[np.random.default_rng(seed).integers(len(d), size=(2000, len(d)))].mean(1)
        out.update(diff_lo=float(np.percentile(m, 2.5)), diff_hi=float(np.percentile(m, 97.5)),
                   cohen_dz=float(d.mean() / d.std(ddof=1)) if d.std(ddof=1) > 0 else None)
    if len(nz) >= 6:
        r = st.rankdata(np.abs(nz))
        out["rank_biserial"] = float((r[nz > 0].sum() - r[nz < 0].sum()) / r.sum())
        out["p"] = float(st.wilcoxon(nz).pvalue)
    else:
        out["rank_biserial"], out["p"] = None, None
    return out


def holm(pvalues: dict) -> dict:
    """Holm-Bonferroni adjusted p-values for a family of comparisons."""
    items = sorted(((k, p) for k, p in pvalues.items() if p is not None), key=lambda x: x[1])
    adj, running = {}, 0.0
    for i, (k, p) in enumerate(items):
        running = max(running, min(1.0, p * (len(items) - i)))
        adj[k] = running
    return adj


def effect_label(r) -> str:
    """Conventional size labels for |rank-biserial|; they describe separation, not engineering importance."""
    if r is None:
        return "n/a"
    r = abs(r)
    return "large" if r >= 0.5 else "medium" if r >= 0.3 else "small" if r >= 0.1 else "negligible"
