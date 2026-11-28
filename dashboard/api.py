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
from rag.retriever import KnowledgeBase, ask as ask_kb
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
    if not 2.0 <= cap_w <= 300.0 or not 0.0 <= fade_db <= 20.0:
        raise HTTPException(422, "cap_w must be in [2, 300] and fade_db in [0, 20]")
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
    a = ask_kb(_load()["kb"], q)
    return {"query": a.query, "supported": a.supported, "statement": a.statement, "quotes": a.quotes}


# ------------------------------------------------------------ operations layer: scenarios, policy, agents, languages
def _rt():
    from scenarios.suite import runtime
    return runtime(kb=_load()["kb"])


@app.get("/api/scenarios")
def scenarios():
    from scenarios.suite import load_suite
    return [{k: s.get(k) for k in ("id", "title", "description", "expected", "simulated", "limitations", "seed", "profiles", "faults")} for s in load_suite()]


@app.post("/api/scenarios/{sid}/run")
def run_scenario_api(sid: str, seed: int | None = None):
    """Execute one suite scenario through the full pipeline (2-7 s). Returns checks, KPIs, traces and explanations."""
    from scenarios.suite import run_scenario
    if seed is not None and not 0 <= seed <= 100000:
        raise HTTPException(422, "seed must be in [0, 100000]")
    try:
        return JSONResponse(run_scenario(sid, seed=seed, rt=_rt()))
    except KeyError as e:
        raise HTTPException(404, str(e)) from e


@app.get("/api/policy/profiles")
def profiles():
    from policy.engine import list_profiles, load_profile, summary
    return [summary(load_profile(p)) for p in list_profiles()]


@app.get("/api/policy/profiles/{pid}")
def profile(pid: str):
    from policy.engine import load_profile, validate
    try:
        p = load_profile(pid)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    return {"profile": p, "validation": validate(p, _load()["cfg"], _load()["kb"])}


@app.post("/api/policy/validate")
def validate_profile(body: dict):
    """Validate a custom profile (JSON body with the same fields as policy/profiles/*.yaml)."""
    from policy.engine import validate
    return validate(body, _load()["cfg"], _load()["kb"])


@app.post("/api/policy/run")
def policy_run(profile: str = "baseline-intl", cap_w: float | None = None, exemption: str | None = None,
               fade_db: float | None = None, seed: int = 42):
    """Flood scenario under a profile, optionally customised. Same traffic and model; only the policy changes."""
    from policy.engine import EXEMPTION_MODES
    from scenarios.suite import run_custom
    if exemption is not None and exemption not in EXEMPTION_MODES:
        raise HTTPException(422, f"exemption must be one of {EXEMPTION_MODES}")
    if (cap_w is not None and not 2.0 <= cap_w <= 300.0) or (fade_db is not None and not 0.0 <= fade_db <= 20.0) or not 0 <= seed <= 100000:
        raise HTTPException(422, "cap_w in [2, 300], fade_db in [0, 20], seed in [0, 100000]")
    try:
        r = run_custom(_rt(), profile, cap_w, fade_db, seed, exemption, with_baselines=True)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    if "error" in r:
        raise HTTPException(422, r)
    from i18n.explain import explain
    r["explanation"] = {lang: explain(r, lang) for lang in ("en", "ar", "hi", "ta")}
    return JSONResponse(r)


@app.post("/api/interpret")
def interpret_api(text: str, run: bool = True, lang: str | None = None):
    """Multilingual request -> structured intent -> (optionally) a real run, explained in the request's language."""
    from i18n.explain import SUPPORTED, explain
    from i18n.interpret import interpret
    from scenarios.suite import run_custom, run_scenario
    try:
        it = interpret(text)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    out_lang = lang if lang in SUPPORTED else it["language"]
    resp = {"interpreted": it, "language": out_lang}
    if run and it["understood"]:
        p = it["params"]
        if it["scenario_id"] == "custom_flood":
            cap = p.get("cap_w")
            if cap is not None and not 2.0 <= cap <= 300.0:
                raise HTTPException(422, "cap_w must be in [2, 300]")
            r = run_custom(_rt(), it["profile_id"] or "baseline-intl", cap, p.get("fade_db"), p.get("seed", 42), with_baselines=True)
        else:
            r = run_scenario(it["scenario_id"], seed=p.get("seed"), profile_id=it["profile_id"], rt=_rt())
        r["explanation"] = {out_lang: explain(r, out_lang)}
        resp["result"] = r
    return JSONResponse(resp)


@app.get("/api/agents")
def agents():
    from agents.registry import load_registry
    return load_registry()


@app.get("/api/governance")
def governance():
    if "gov" not in _state:
        from knowledge.governance import build
        _state["gov"] = build(_load()["cfg"], _load()["kb"])
    return JSONResponse(json.loads(json.dumps(_state["gov"], default=str)))


@app.get("/api/i18n/{lang}")
def i18n(lang: str):
    from i18n.explain import SUPPORTED, locale
    if lang not in SUPPORTED:
        raise HTTPException(404, f"supported languages: {SUPPORTED}")
    return locale(lang)


_dist = os.path.join(ROOT, "dashboard", "frontend", "dist")
if os.path.isdir(_dist):
    app.mount("/", StaticFiles(directory=_dist, html=True), name="ui")
