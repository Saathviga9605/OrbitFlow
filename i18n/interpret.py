"""Multilingual request interpreter: script-based language detection + keyword/number lexicon.

It maps a request such as "حاكِ فيضاناً مع حد قدرة 16 واط وفق ملف الإمارات" to a structured,
language-independent intent {scenario_id, profile_id, params}. The pipeline then runs on that intent,
so its numbers cannot depend on the input language. This is NOT natural-language understanding:
anything outside the lexicon is reported as unmatched rather than guessed.
"""
from __future__ import annotations

import os
import re
import unicodedata

import yaml

LEXICON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lexicon.yaml")
SCRIPTS = {"ar": (0x0600, 0x06FF), "hi": (0x0900, 0x097F), "ta": (0x0B80, 0x0BFF)}
DIGITS = {**{chr(0x0660 + i): str(i) for i in range(10)}, **{chr(0x06F0 + i): str(i) for i in range(10)},
          **{chr(0x0966 + i): str(i) for i in range(10)}, **{chr(0x0BE6 + i): str(i) for i in range(10)}, "٫": "."}
_LEX = None


def normalise(text: str) -> str:
    t = unicodedata.normalize("NFC", text).casefold()
    t = "".join(DIGITS.get(ch, ch) for ch in t)
    t = re.sub("[ً-ْـ]", "", t)          # Arabic diacritics and tatweel
    t = re.sub("[أإآ]", "ا", t)
    return " ".join(t.split())


def lexicon() -> dict:
    global _LEX
    if _LEX is None:
        with open(LEXICON, encoding="utf8") as f:
            raw = yaml.safe_load(f)
        _LEX = {sec: {k: {lang: [normalise(w) for w in ws] for lang, ws in v.items()} if isinstance(v, dict) else [normalise(w) for w in v]
                      for k, v in raw[sec].items()} for sec in raw}
    return _LEX


def detect_language(text: str) -> str:
    counts = {lang: sum(lo <= ord(ch) <= hi for ch in text) for lang, (lo, hi) in SCRIPTS.items()}
    lang, n = max(counts.items(), key=lambda kv: kv[1])
    return lang if n > 0 else "en"


def _find(norm: str, table: dict) -> tuple[str | None, list[str]]:
    for key, by_lang in table.items():
        hits = [w for ws in by_lang.values() for w in ws if w and w in norm]
        if hits:
            return key, hits
    return None, []


def _number_before(norm: str, units: list[str]) -> float | None:
    alt = "|".join(re.escape(u) for u in sorted(units, key=len, reverse=True))
    m = re.search(rf"(\d+(?:\.\d+)?)\s*(?:{alt})(?![a-z])", norm)
    return float(m.group(1)) if m else None


def interpret(text: str) -> dict:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("empty request")
    if len(text) > 500:
        raise ValueError("request longer than 500 characters")
    lex = lexicon()
    norm = normalise(text)
    sid, s_hits = _find(norm, lex["scenarios"])
    pid, p_hits = _find(norm, lex["profiles"])
    params = {}
    cap = _number_before(norm, lex["units"]["watt"])
    if cap is not None:
        params["cap_w"] = cap
    fade = _number_before(norm, lex["units"]["db"])
    if fade is not None:
        params["fade_db"] = fade
    alt = "|".join(re.escape(u) for u in lex["units"]["seed"])
    m = re.search(rf"(?:{alt})\s*[:=]?\s*(\d+)", norm)
    if m:
        params["seed"] = int(m.group(1))
    if sid is None and (params.get("cap_w") is not None or params.get("fade_db") is not None):
        sid = "custom_flood"                         # a cap or fade only makes sense in the flood storyline
    return {"input": text, "language": detect_language(text), "normalised": norm, "scenario_id": sid, "profile_id": pid,
            "params": params, "matched_terms": s_hits + p_hits, "understood": sid is not None,
            "method": "keyword and number lexicon (i18n/lexicon.yaml); not a language model"}
