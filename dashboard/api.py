"""OrbitFlow server: serves the built story and runs the real pipeline on request.

    python -m uvicorn dashboard.api:app --port 8000
The UI itself is static and needs no server; /api/simulate is for runs outside the precomputed grid.
"""
from __future__ import annotations

import json
import math
import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from agents.supervisor import Supervisor
from bridge.policy import BridgePolicy
from rag.retriever import KnowledgeBase, answer
from scenarios.flood_relief import build
from traffic.dataset import load_trace
from traffic.forecaster import Forecaster, prepare_forecast
from utils.config import REAL_TRACE, ROOT, load_config

app = FastAPI(title="OrbitFlow API")
_state: dict = {}


def _load() -> dict:
    if "cfg" not in _state:
        cfg = load_config()
        m = os.path.join(ROOT, "models")
        _state.update(cfg=cfg, base=load_trace(REAL_TRACE), kb=_state.get("kb") or KnowledgeBase(cfg),
                      forecaster=Forecaster.load(cfg, os.path.join(m, "traffic_predictor.pt")),
                      ckpt=os.path.join(m, "bridge_ppo.pt"))
    return _state


def _finite(d: dict) -> dict:
    return {k: (None if isinstance(v, float) and math.isnan(v) else v) for k, v in d.items()}


@app.get("/api/health")
def health():
    m = os.path.join(ROOT, "models")
    return {"status": "ok", "forecaster": os.path.exists(os.path.join(m, "traffic_predictor.pt")),
            "bridge": os.path.exists(os.path.join(m, "bridge_ppo.pt"))}


@app.get("/api/results/{name}")
def result(name: str):
    if not name.replace("_", "").isalnum():
        raise HTTPException(400, "bad name")
    path = os.path.join(ROOT, "results", name + ".json")
    if not os.path.exists(path):
        raise HTTPException(404, f"{name} not found: run scripts/run_eval.py")
    return JSONResponse(json.load(open(path)))


@app.post("/api/simulate")
def simulate(cap_w: float = 22.0, fade_db: float = 6.0, seed: int = 42, agents: bool = True):
    """Run flood-relief through forecaster, BRIDGE, agents, guard and twin. Takes about a second."""
    if not 2.0 <= cap_w <= 100.0 or not 0.0 <= fade_db <= 20.0:
        raise HTTPException(422, "cap_w must be in [2, 100] and fade_db in [0, 20]")
    s = _load()
    trace, feed = build(s["base"], {"border_cap_w": cap_w, "fade_db": fade_db}, seed)
    trace.forecast = prepare_forecast(s["forecaster"], trace, s["cfg"])
    r = Supervisor(s["cfg"], BridgePolicy(s["cfg"], s["ckpt"]), feed, s["kb"], agents_on=agents).run(trace)
    return {"experiment_id": f"live:cap{cap_w:g}:fade{fade_db:g}:seed{seed}:agents{int(agents)}", "kind": "newly executed simulation",
            "params": {"cap_w": cap_w, "fade_db": fade_db, "seed": seed, "agents": agents},
            "kpis": _finite({k: v for k, v in r["kpis"].items()}), "human_review": r["human_review"][:5]}


@app.post("/api/ask")
def ask(q: str):
    """Extractive, source-grounded answer from the real corpus. Quotations only; says so when unsupported."""
    if not q.strip() or len(q) > 500:
        raise HTTPException(422, "q must be 1 to 500 characters")
    a = answer(_load()["kb"], q)
    return {"query": a.query, "supported": a.supported, "statement": a.statement, "quotes": a.quotes}


_dist = os.path.join(ROOT, "dashboard", "frontend", "dist")
if os.path.isdir(_dist):
    app.mount("/", StaticFiles(directory=_dist, html=True), name="ui")
