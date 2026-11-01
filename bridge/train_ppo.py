"""Stage 1 behaviour cloning, stage 2 PPO. Trains on synthetic train-split episodes only.

    python -m bridge.train_ppo [--fast] [--no-forecast]
Writes models/bridge_{bc,ppo}[_noforecast].pt and results/bridge_training[_noforecast].json.
The raw proposal is penalised and carries the log-prob; the repaired action is what executes.
"""
from __future__ import annotations

import argparse
import json
import os
import time

import numpy as np
import torch

from bam.validator import BamGuard
from bridge.policy import (FORECAST_FEATURES, BridgeNet, HeuristicPredictive, build_features, plackett_luce_logprob,
                           power_logprob, sample_topk, to_watts)
from digital_twin.channel import LinkModel
from digital_twin.environment import NTNTwin
from traffic.dataset import load_trace
from traffic.forecaster import Forecaster, prepare_forecast
from traffic.generator import make_trace
from traffic.splits import create_splits
from utils.config import REAL_TRACE, ROOT, load_config


def slot_reward(rec: dict, ok: bool, jain_ema: float, cfg: dict, K: int) -> float:
    r = cfg["reward"]
    arr = float(rec["arrived_kb"].sum()) + 1e-6
    return (r["w_throughput"] * min(float(rec["served_kb"].sum()) / arr, 2.0)
            - r["w_delay"] * min(rec["delay_ms"] / 100.0, 5.0)
            - r["w_loss"] * float(rec["dropped_kb"].sum()) / arr
            - r["w_rt_violation"] * rec["rt_violation"]
            + r["w_fairness"] * jain_ema
            - r["w_guard_violation"] * (0.0 if ok else 1.0)
            - 0.05 * rec["switches"] / K)


class Episode:
    """One twin + guard with the running fairness statistics the reward needs."""

    def __init__(self, trace, cfg, guard, link, use_forecast):
        self.twin, self.cfg, self.guard, self.link = NTNTwin(trace, cfg), cfg, guard, link
        self.use_forecast = use_forecast
        self.obs = self.twin.reset()
        self.arr, self.srv = np.zeros(trace.N), np.zeros(trace.N)
        self.jain = 0.8

    def features(self):
        return build_features(self.obs, self.cfg, self.guard, self.link, self.twin.T, self.use_forecast)

    def step(self, lit, power, priority):
        o = self.obs
        before = self.guard.check(lit, power, o["guard"], o["ssb"], o["sib"])
        ok = all(c["status"] == "PASS" for c in before.values())
        res = self.guard.repair(lit, power, o["guard"], o["ssb"], o["sib"], priority=priority)
        rec = self.twin.step(res.lit, res.power)
        self.arr += rec["arrived_kb"]
        self.srv += rec["served_kb"]
        ratio = self.srv / np.maximum(self.arr, 1e-9)
        j = float(ratio.sum() ** 2 / (len(ratio) * (ratio ** 2).sum() + 1e-12))
        self.jain = 0.9 * self.jain + 0.1 * j
        r = slot_reward(rec, ok, self.jain, self.cfg, self.twin.K)
        self.obs = self.twin.obs()
        return r


def behaviour_clone(net, cfg, traces, guard, link, use_forecast, log):
    teacher = HeuristicPredictive(cfg, use_forecast)
    K, F_, O, W = cfg["scenario"]["k_beams"], [], [], []
    for tr in traces:
        ep = Episode(tr, cfg, guard, link, use_forecast)
        while not ep.twin.done:
            a = teacher.act(ep.obs)
            F_.append(a.info["f"])
            O.append(a.info["order"])
            W.append(0.9 * a.info["w"] + 0.1 / K)
            ep.step(a.lit, a.power, a.priority)
    F_, O, W = (torch.from_numpy(np.array(x)) for x in (F_, O, W))
    F_, W = F_.float(), W.float()
    opt = torch.optim.Adam(net.parameters(), lr=1e-3)
    for e in range(cfg["bridge"]["bc_epochs"]):
        perm, tot = torch.randperm(len(F_)), 0.0
        for i in range(0, len(F_), 512):
            b = perm[i:i + 512]
            z, alpha, _ = net(F_[b])
            lp, _ = power_logprob(alpha, O[b], W[b])
            loss = -(plackett_luce_logprob(z, O[b]) + lp).mean()
            opt.zero_grad()
            loss.backward()
            opt.step()
            tot += loss.item() * len(b)
        log.append({"epoch": e + 1, "loss": tot / len(F_)})
        print(f"BC {e+1} loss {tot/len(F_):.3f}", flush=True)


@torch.no_grad()
def evaluate(net, cfg, traces, guard, link, use_forecast) -> float:
    K, pmax, pmin = cfg["scenario"]["k_beams"], cfg["scenario"]["p_max_w"], cfg["scenario"]["p_min_w"]
    total = 0.0
    for tr in traces:
        ep = Episode(tr, cfg, guard, link, use_forecast)
        while not ep.twin.done:
            z, a, _ = net(torch.from_numpy(ep.features())[None])
            z, a = z[0].numpy(), a[0].numpy()
            o = np.argsort(-z)[:K]
            lit = np.zeros(len(z), bool)
            lit[o] = True
            p = np.zeros(len(z))
            p[o] = to_watts(a[o] / a[o].sum(), pmin, pmax)
            total += ep.step(lit, p, z)
    return total / len(traces)


def ppo(net, cfg, pool, weights, val, guard, link, use_forecast, iters, tag, log):
    b = cfg["bridge"]
    K, pmax, pmin = cfg["scenario"]["k_beams"], cfg["scenario"]["p_max_w"], cfg["scenario"]["p_min_w"]
    B = b["batch_episodes"]
    opt = torch.optim.Adam(net.parameters(), lr=b["lr"])
    rng = np.random.default_rng(cfg["seed"])
    kinds, probs = list(weights), np.array(list(weights.values()))
    best, best_state = evaluate(net, cfg, val, guard, link, use_forecast), {k: v.clone() for k, v in net.state_dict().items()}
    bc_val = best
    log.append({"iter": 0, "val_reward": best})
    print(f"BC val {best:.2f}", flush=True)
    for it in range(1, iters + 1):
        t0 = time.time()
        eps = [Episode(pool[k][rng.integers(len(pool[k]))], cfg, guard, link, use_forecast)
               for k in rng.choice(kinds, B, p=probs / probs.sum())]
        Fs, Os, Ws, LPs, Vs, Rs = [], [], [], [], [], []
        for _ in range(eps[0].twin.T):
            f = torch.from_numpy(np.stack([e.features() for e in eps]))
            with torch.no_grad():
                z, alpha, v = net(f)
                order = sample_topk(z, K)
                w = torch.distributions.Dirichlet(alpha.gather(1, order)).sample()
                lp = plackett_luce_logprob(z, order) + power_logprob(alpha, order, w)[0]
            zn, on, wn = z.numpy(), order.numpy(), w.numpy()
            rs = []
            for i, e in enumerate(eps):
                lit = np.zeros(zn.shape[1], bool)
                lit[on[i]] = True
                p = np.zeros(zn.shape[1])
                p[on[i]] = to_watts(wn[i], pmin, pmax)
                rs.append(e.step(lit, p, zn[i]))
            Fs.append(f); Os.append(order); Ws.append(w); LPs.append(lp); Vs.append(v)
            Rs.append(torch.tensor(rs, dtype=torch.float32))
        R, V = torch.stack(Rs), torch.stack(Vs)
        adv, gae = torch.zeros_like(R), torch.zeros(B)
        for t in reversed(range(len(R))):
            nxt = V[t + 1] if t + 1 < len(R) else torch.zeros(B)
            gae = R[t] + b["gamma"] * nxt - V[t] + b["gamma"] * b["lam"] * gae
            adv[t] = gae
        ret = (adv + V).flatten()
        adv = adv.flatten()
        adv = (adv - adv.mean()) / (adv.std() + 1e-8)
        Fa, Oa, Wa, LPa = torch.cat(Fs), torch.cat(Os), torch.cat(Ws), torch.cat(LPs)
        for _ in range(b["epochs"]):
            perm = torch.randperm(len(Fa))
            for i in range(0, len(Fa), b["minibatch"]):
                m = perm[i:i + b["minibatch"]]
                z, alpha, v = net(Fa[m])
                lpow, ent_pow = power_logprob(alpha, Oa[m], Wa[m])
                lp = plackett_luce_logprob(z, Oa[m]) + lpow
                ratio = torch.exp(lp - LPa[m])
                pg = -torch.min(ratio * adv[m], ratio.clamp(1 - b["clip"], 1 + b["clip"]) * adv[m]).mean()
                pr = torch.softmax(z, -1)
                ent_beam = -(pr * torch.log(pr + 1e-9)).sum(-1).mean()
                loss = pg + b["value_coef"] * ((v - ret[m]) ** 2).mean() - b["entropy_beam"] * ent_beam - b["entropy_power"] * ent_pow.mean()
                opt.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(net.parameters(), b["grad_clip"])
                opt.step()
        row = {"iter": it, "train_reward": float(R.sum(0).mean()), "sec": time.time() - t0}
        if it % b["eval_every"] == 0 or it == iters:
            row["val_reward"] = evaluate(net, cfg, val, guard, link, use_forecast)
            if row["val_reward"] > best:
                best, best_state = row["val_reward"], {k: v.clone() for k, v in net.state_dict().items()}
            print(f"{tag} it {it} train {row['train_reward']:.1f} val {row['val_reward']:.1f} best {best:.1f} ({row['sec']:.1f}s)", flush=True)
        log.append(row)
    net.load_state_dict(best_state)
    return bc_val, best


def val_kpis(net, cfg, traces, guard, link, use_forecast) -> dict:
    """KPIs on validation episodes: the common yardstick when variants use different rewards."""
    K, pmax, pmin = cfg["scenario"]["k_beams"], cfg["scenario"]["p_max_w"], cfg["scenario"]["p_min_w"]
    delay, rt, tp = [], [], []
    with torch.no_grad():
        for tr in traces:
            ep = Episode(tr, cfg, guard, link, use_forecast)
            while not ep.twin.done:
                z, a, _ = net(torch.from_numpy(ep.features())[None])
                z, a = z[0].numpy(), a[0].numpy()
                o = np.argsort(-z)[:K]
                lit = np.zeros(len(z), bool)
                lit[o] = True
                p = np.zeros(len(z))
                p[o] = to_watts(a[o] / a[o].sum(), pmin, pmax)
                ep.step(lit, p, z)
            h = ep.twin.history
            delay.append(np.mean([x["delay_ms"] for x in h]))
            rt.append(np.mean([x["rt_violation"] for x in h]))
            tp.append(np.mean([x["throughput_mbps"] for x in h]))
    return {"delay_ms": float(np.mean(delay)), "rt_miss": float(np.mean(rt)), "throughput": float(np.mean(tp))}


def apply_overrides(cfg: dict, sets: list[str]) -> None:
    for s in sets or []:
        key, val = s.split("=")
        d = cfg
        parts = key.split(".")
        for p in parts[:-1]:
            d = d[p]
        d[parts[-1]] = json.loads(val)


def main(fast=False, no_forecast=False, seed=None, tag=None, sets=None, no_bc=False):
    cfg = load_config()
    apply_overrides(cfg, sets)
    cfg["seed"] = seed if seed is not None else cfg["seed"]
    torch.manual_seed(cfg["seed"])
    np.random.seed(cfg["seed"])
    torch.set_num_threads(1 if tag else 4)
    use_fc = not no_forecast
    suffix = f"_{tag}" if tag else ("_noforecast" if no_forecast else "")
    base = load_trace(REAL_TRACE)
    mf = create_splits(n_per_kind=12 if fast else 120, random_seed=load_config()["seed"])     # same split for every training seed
    fc = Forecaster.load(cfg, os.path.join(ROOT, "models", "traffic_predictor.pt"))

    def build(e):
        t = make_trace(e["kind"], base, e["seed"])
        t.forecast = prepare_forecast(fc, t, cfg)
        return t

    pool: dict = {}
    for e in mf.train_episodes:
        pool.setdefault(e["kind"], []).append(build(e))
    # stratified validation sample: model selection never touches the test split
    val = [build(e) for k in mf.scenario_kinds for e in [x for x in mf.val_episodes if x["kind"] == k][:4 if fast else 12]]
    guard, link = BamGuard(cfg), LinkModel(cfg)
    net = BridgeNet(dirichlet_offset=cfg["bridge"]["dirichlet_offset"])
    log = {"bc": [], "ppo": []}
    flat = [t for v in pool.values() for t in v]
    idx = np.random.default_rng(cfg["seed"]).permutation(len(flat))[: 10 if fast else cfg["bridge"]["bc_episodes"]]
    if not no_bc:
        behaviour_clone(net, cfg, [flat[i] for i in idx], guard, link, use_fc, log["bc"])
    log["bc_val_kpis"] = val_kpis(net, cfg, val, guard, link, use_fc)
    torch.save(net.state_dict(), os.path.join(ROOT, "models", "exp" if tag else "", f"bridge_bc{suffix}.pt"))
    w = cfg["bridge"]["kind_weights"]
    bc_val, best = ppo(net, cfg, pool, w, val, guard, link, use_fc, 3 if fast else cfg["bridge"]["iterations"], "PPO" + suffix, log["ppo"])
    torch.save(net.state_dict(), os.path.join(ROOT, "models", "exp" if tag else "", f"bridge_ppo{suffix}.pt"))
    log["val_kpis"] = val_kpis(net, cfg, val, guard, link, use_fc)
    log["config"] = {"seed": cfg["seed"], "sets": sets or [], "no_bc": no_bc, "no_forecast": no_forecast}
    log.update(bc_val=bc_val, best_val=best, ppo_beats_bc=best > bc_val, n_params=sum(p.numel() for p in net.parameters()))
    out = os.path.join(ROOT, "results", "exp" if tag else "")
    os.makedirs(out, exist_ok=True)
    json.dump(log, open(os.path.join(out, f"bridge_training{suffix}.json"), "w"), indent=1)
    print("done", bc_val, best, flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true")
    ap.add_argument("--no-forecast", action="store_true")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--tag")
    ap.add_argument("--set", action="append", dest="sets")
    ap.add_argument("--no-bc", action="store_true")
    a = ap.parse_args()
    main(a.fast, a.no_forecast, a.seed, a.tag, a.sets, a.no_bc)
