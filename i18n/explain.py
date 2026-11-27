"""Localised decision summaries built only from fields of a measured result.

Every sentence is a template filled with numbers taken from the result dict; nothing is generated
freely, so a summary cannot state a number the run did not produce. Missing keys fall back to English.
"""
from __future__ import annotations

import json
import os

LOCALES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "locales")
SUPPORTED = ("en", "ar", "hi", "ta")
_CACHE: dict = {}


def locale(lang: str) -> dict:
    lang = lang if lang in SUPPORTED else "en"
    if lang not in _CACHE:
        with open(os.path.join(LOCALES, f"{lang}.json"), encoding="utf8") as f:
            _CACHE[lang] = json.load(f)
    return _CACHE[lang]


def t(lang: str, section: str, key: str, **kw) -> str:
    s = locale(lang).get(section, {}).get(key) or locale("en")[section].get(key, key)
    return s.format(**kw) if kw else s


def _pct(v):
    return "n/a" if v is None else f"{v * 100:.1f}"


def _num(v, d=1):
    return "n/a" if v is None else f"{v:.{d}f}"


def _terms(lang, keys):
    return ", ".join(t(lang, "terms", k) for k in keys) or t(lang, "explain", "none")


def _kinds_count(lang, d: dict):
    return ", ".join(f"{t(lang, 'terms', k)} ×{v}" for k, v in d.items()) or t(lang, "explain", "none")


def _single(r: dict, lang: str) -> list[str]:
    k, c = r.get("kpis", {}), r.get("coordination", {})
    out = []
    ref = r.get("baselines", {}).get("reactive", {}).get("kpis", {})
    args = dict(late=_pct(k.get("rt_sla_violation")), delay=_num(k.get("mean_delay_ms")), thr=_num(k.get("throughput_mbps")))
    out.append(t(lang, "explain", "delivery", late_ref=_pct(ref.get("rt_sla_violation")), **args) if ref else t(lang, "explain", "delivery_noref", **args))
    if k.get("emergency_served_ratio"):
        out.append(t(lang, "explain", "emergency", em=_pct(k["emergency_served_ratio"])))
    if (r.get("profile") or {}).get("operating_constraints", {}).get("border_power_cap", {}).get("enabled") and r.get("base", {}).get("kind") != "synthetic":
        out.append(t(lang, "explain", "cap", viol=k.get("cap_violation_slots", 0), exempt=c.get("exempted_slots", 0),
                     mode=t(lang, "terms", c.get("exemption_mode", "human_approval"))))
    nh = c.get("agent_health", {}).get("network", {})
    if nh.get("failures"):
        out.append(t(lang, "explain", "fallback", n=nh["failures"], kinds=_kinds_count(lang, nh.get("by_kind", {})), fb=c.get("failures", [{}])[0].get("fallback", "")))
    ph = c.get("agent_health", {}).get("policy", {})
    if ph.get("failures"):
        out.append(t(lang, "explain", "policy_down", n=ph["failures"]))
    if c.get("conflicts_by_type"):
        out.append(t(lang, "explain", "conflicts", n=sum(c["conflicts_by_type"].values()), types=_kinds_count(lang, c["conflicts_by_type"])))
    if c.get("human_review_by_kind"):
        out.append(t(lang, "explain", "human", n=sum(c["human_review_by_kind"].values()), kinds=_kinds_count(lang, c["human_review_by_kind"])))
    dq = c.get("data_quality", {})
    if dq.get("degraded_slots"):
        out.append(t(lang, "explain", "data", n=dq["degraded_slots"], c=dq.get("conservative_slots", 0)))
    f = r.get("forecast")
    if f:
        out.append(t(lang, "explain", "forecast", g=_num(f["gated_mae_mbps"], 2), p=_num(f["persistence_mae_mbps"], 2), share=_num(f["gated_share"] * 100, 1)))
    return out


def explain(r: dict, lang: str = "en") -> list[str]:
    title = locale(lang).get("scenarios", {}).get(r.get("id", ""), r.get("title", ""))
    pid = (r.get("profile") or {}).get("profile_id") or ", ".join(r.get("profiles", {}).keys()) or "baseline-intl"
    out = [t(lang, "explain", "headline", title=title, seed=r.get("seed", "?"), profile=pid)]
    if "profiles" in r:
        ef = r["profile_effect"]
        out.append(t(lang, "explain", "profiles", n=len(r["profiles"]),
                     list="; ".join(f"{row['profile']} {_pct(row['emergency_served_ratio'])}% ({t(lang, 'terms', row['exemption'])}, {row['cap_w']:g} W)" for row in ef["table"])))
        if ef.get("pre_cap_identical"):
            out.append(t(lang, "explain", "pre_cap_same"))
    elif "matrix" in r:
        m = r["matrix"]
        yn = lambda b: t(lang, "explain", "yes" if b else "no")       # noqa: E731
        out.append(t(lang, "explain", "matrix", normal=yn(m["normal_identical_across_profiles"]), flood=yn(m["flood_differs_across_profiles"])))
    elif "multilingual" in r:
        m = r["multilingual"]
        out.append(t(lang, "explain", "multilingual", n=m["n_languages"], same=t(lang, "explain", "yes" if m["same_kpis"] else "no")))
    else:
        out += _single(r, lang)
    if r.get("checks"):
        out.append(t(lang, "explain", "checks", passed=sum(c["passed"] for c in r["checks"]), total=len(r["checks"])))
    out.append(t(lang, "explain", "sim_note"))
    return out
