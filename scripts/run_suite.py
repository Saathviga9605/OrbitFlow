"""Run the demonstration scenarios and build the governance bundle for the UI and API.

    python scripts/run_suite.py                 # all scenarios, about 1 minute on CPU
    python scripts/run_suite.py --only S6_agent_failure
Writes results/scenario_suite.json and results/governance.json, and copies them plus the
locale files to dashboard/frontend/public/data.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from knowledge.governance import build as build_governance  # noqa: E402
from scenarios.suite import LANGS, load_suite, run_scenario, runtime  # noqa: E402
from utils.config import ROOT  # noqa: E402

RESULTS = os.path.join(ROOT, "results")
WEB = os.path.join(ROOT, "dashboard", "frontend", "public", "data")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", help="scenario ids to run (default: all)")
    args = ap.parse_args()
    rt = runtime()
    out_path = os.path.join(RESULTS, "scenario_suite.json")
    previous = json.load(open(out_path, encoding="utf8")) if args.only and os.path.exists(out_path) else {"scenarios": []}
    done = {s["id"]: s for s in previous["scenarios"]}
    for s in load_suite():
        if args.only and s["id"] not in args.only:
            continue
        t0 = time.perf_counter()
        r = run_scenario(s["id"], rt=rt)
        done[s["id"]] = r
        print(f"{s['id']:<26} {'PASS' if r['passed'] else 'FAIL'}  {sum(c['passed'] for c in r['checks'])}/{len(r['checks'])} checks  {time.perf_counter() - t0:.1f}s")
    order = [s["id"] for s in load_suite()]
    scen = [done[i] for i in order if i in done]
    suite = {"generated_by": "scripts/run_suite.py", "kind": "executed simulation", "checksums": rt["shas"],
             "summary": {"scenarios": len(scen), "passed": sum(s["passed"] for s in scen),
                         "checks": sum(len(s["checks"]) for s in scen), "checks_passed": sum(c["passed"] for s in scen for c in s["checks"])},
             "scenarios": scen}
    json.dump(suite, open(out_path, "w", encoding="utf8"), indent=1, ensure_ascii=False)
    gov = build_governance(rt["cfg"], rt["kb"])
    s6 = next((s for s in scen if s["id"] == "S6_agent_failure"), None)
    gov["health_snapshot"] = {"scenario": "S6_agent_failure", "agent_health": s6["coordination"]["agent_health"]} if s6 else None
    json.dump(gov, open(os.path.join(RESULTS, "governance.json"), "w", encoding="utf8"), indent=1, ensure_ascii=False, default=str)
    os.makedirs(WEB, exist_ok=True)
    for f in ("scenario_suite.json", "governance.json"):
        shutil.copy(os.path.join(RESULTS, f), WEB)
    for lang in LANGS:
        shutil.copy(os.path.join(ROOT, "i18n", "locales", f"{lang}.json"), os.path.join(WEB, f"i18n_{lang}.json"))
    print(f"{suite['summary']['passed']}/{suite['summary']['scenarios']} scenarios, "
          f"{suite['summary']['checks_passed']}/{suite['summary']['checks']} checks; wrote results/scenario_suite.json, results/governance.json")


if __name__ == "__main__":
    main()
