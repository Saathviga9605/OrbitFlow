"""Train the residual GRU, fit a GBM baseline, and report per-scenario skill honestly.

    python -m traffic.train_forecaster [--fast]
Writes models/traffic_predictor.pt and results/predictor_metrics.json.
"""
from __future__ import annotations

import argparse
import json
import os

import numpy as np
import torch
from sklearn.ensemble import HistGradientBoostingRegressor

from traffic.dataset import load_trace
from traffic.forecaster import RATE_SCALE, Forecaster, persistence_trace, window_features
from traffic.generator import make_trace
from traffic.splits import create_splits
from utils.config import REAL_TRACE, ROOT, load_config

LAG = 1


def samples(traces, W, H):
    """Inputs at observed slot o, targets rate[o+1 .. o+H] (the timing contract with lag=1)."""
    xs, ys, ls = [], [], []
    for tr in traces:
        f = window_features(tr.rate, W)
        for o in range(0, tr.T - H):
            xs.append(f[o])
            ys.append(tr.rate[o + 1:o + 1 + H].T)
            ls.append(tr.rate[o])
    return np.concatenate(xs), np.concatenate(ys), np.concatenate(ls)


def fit_gru(fc: Forecaster, cfg, tr, va, epochs, log):
    p = cfg["predictor"]
    x, y, l = samples(tr, fc.window, fc.horizon)
    xv, yv, lv = samples(va, fc.window, fc.horizon)
    X = torch.from_numpy(x)
    R = torch.from_numpy(((y - l[:, None]) / RATE_SCALE).astype(np.float32))
    weight = torch.from_numpy(np.where(np.abs(y - l[:, None]) > p["jump_mbps"], p["jump_weight"], 1.0).astype(np.float32))
    Xv, Rv = torch.from_numpy(xv), torch.from_numpy(((yv - lv[:, None]) / RATE_SCALE).astype(np.float32))
    opt = torch.optim.Adam(fc.net.parameters(), lr=p["lr"])
    loss_fn = torch.nn.HuberLoss(reduction="none", delta=0.1)
    best, best_state, stale = 1e9, None, 0
    g = torch.Generator().manual_seed(cfg["seed"])
    for ep in range(epochs):
        fc.net.train()
        perm = torch.randperm(len(X), generator=g)
        for i in range(0, len(X), p["batch"]):
            b = perm[i:i + p["batch"]]
            loss = (loss_fn(fc.net(X[b]), R[b]) * weight[b]).mean()
            opt.zero_grad()
            loss.backward()
            opt.step()
        fc.net.eval()
        with torch.no_grad():
            v = float(loss_fn(fc.net(Xv), Rv).mean())
        log.append({"epoch": ep + 1, "val_huber": v})
        print(f"epoch {ep+1} val {v:.6f}", flush=True)
        if v < best - 1e-7:
            best, best_state, stale = v, {k: t.clone() for k, t in fc.net.state_dict().items()}, 0
        else:
            stale += 1
            if stale >= 5:
                break
    fc.net.load_state_dict(best_state)
    fc.net.eval()


def fit_gbm(tr, W, H, seed):
    x, y, l = samples(tr, W, H)
    idx = np.random.default_rng(seed).choice(len(x), min(60000, len(x)), replace=False)
    Xf = x[idx][:, -6:, :2].reshape(len(idx), -1)
    return [HistGradientBoostingRegressor(max_iter=80, max_depth=5, random_state=seed)
            .fit(Xf, (y[idx, h] - l[idx]) / RATE_SCALE) for h in range(H)]


def gbm_trace(models, trace, W, H):
    T, N = trace.rate.shape
    o = np.maximum(np.arange(T) - LAG, 0)
    f = window_features(trace.rate, W)[o]
    Xf = f[:, :, -6:, :2].reshape(T * N, -1)
    d = np.stack([m.predict(Xf) for m in models], axis=-1).reshape(T, N, H)
    return np.maximum(trace.rate[o][..., None] + RATE_SCALE * d, 0.0)


def score(preds, traces, jump):
    """Pool all (t, cell, h) targets; jumps are targets far from the last value the controller saw."""
    P, Y, L = [], [], []
    for p, tr in zip(preds, traces):
        T, H = tr.T, p.shape[2]
        o = np.maximum(np.arange(T) - LAG, 0)
        for h in range(H):
            valid = np.arange(T - h)
            P.append(p[valid, :, h].ravel())
            Y.append(tr.rate[valid + h].ravel())
            L.append(tr.rate[o[valid]].ravel())
    P, Y, L = map(np.concatenate, (P, Y, L))
    e = np.abs(P - Y)
    m = np.abs(Y - L) > jump
    ss = float(((Y - Y.mean()) ** 2).sum())
    return {"mae": float(e.mean()), "rmse": float(np.sqrt(((P - Y) ** 2).mean())),
            "r2": float(1 - ((P - Y) ** 2).sum() / max(ss, 1e-9)),
            "jump_mae": float(e[m].mean()) if m.any() else None, "n_jump": int(m.sum())}


def main(fast=False):
    cfg = load_config()
    torch.manual_seed(cfg["seed"])
    np.random.seed(cfg["seed"])
    base = load_trace(REAL_TRACE)
    mf = create_splits(n_per_kind=12 if fast else 120, random_seed=cfg["seed"])
    build = lambda eps: [make_trace(e["kind"], base, e["seed"]) for e in eps]
    train, val, test = build(mf.train_episodes), build(mf.val_episodes), build(mf.test_episodes)
    fc = Forecaster(cfg)
    log: list = []
    fit_gru(fc, cfg, train, val, 2 if fast else cfg["predictor"]["epochs"], log)
    gbm = fit_gbm(train, fc.window, fc.horizon, cfg["seed"])
    os.makedirs(os.path.join(ROOT, "models"), exist_ok=True)
    torch.save(fc.net.state_dict(), os.path.join(ROOT, "models", "traffic_predictor.pt"))

    jump = cfg["predictor"]["jump_mbps"]
    groups = {k: [t for t in test if t.meta["kind"] == k] for k in mf.scenario_kinds}
    groups["real_trace"] = [base]
    out = {"split": {"train": len(train), "val": len(val), "test": len(test)}, "training": log, "scenarios": {}}
    for name, ts in groups.items():
        row = {"persistence": score([persistence_trace(t, LAG) for t in ts], ts, jump),
               "gbm": score([gbm_trace(gbm, t, fc.window, fc.horizon) for t in ts], ts, jump),
               "gru": score([fc.predict_trace(t, LAG) for t in ts], ts, jump)}
        pj, gj = row["persistence"]["jump_mae"], row["gru"]["jump_mae"]
        row["gru_jump_skill"] = None if not pj else 1 - gj / pj
        row["gru_mae_skill"] = 1 - row["gru"]["mae"] / row["persistence"]["mae"]
        out["scenarios"][name] = row
        print(name, {k: round(row[k]["mae"], 3) for k in ("persistence", "gbm", "gru")}, "jump skill", row["gru_jump_skill"], flush=True)
    os.makedirs(os.path.join(ROOT, "results"), exist_ok=True)
    json.dump(out, open(os.path.join(ROOT, "results", "predictor_metrics.json"), "w"), indent=1)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true")
    main(ap.parse_args().fast)
