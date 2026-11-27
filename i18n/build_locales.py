"""Merge the story-UI strings (app_strings_*.py) into i18n/locales/*.json and copy them to the web bundle.

    python -m i18n.build_locales
Fails if a language misses a key or changes a {placeholder}.
"""
from __future__ import annotations

import json
import os
import re
import shutil

from i18n.app_strings_ar import AR
from i18n.app_strings_en import EN
from i18n.app_strings_hi import HI
from i18n.app_strings_ta import TA

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(os.path.dirname(HERE), "dashboard", "frontend", "public", "data")
PH = re.compile(r"{(\w+)}")
UNIT = re.compile(r"(\{\w+\}\s?(?:W|ms|dBi|dB|Mbps|s)(?![A-Za-z]))")


def check(lang: str, table: dict) -> list[str]:
    errs = [f"{lang}: missing {k}" for k in EN if k not in table]
    errs += [f"{lang}: unknown {k}" for k in table if k not in EN]
    errs += [f"{lang}: placeholders differ in {k}" for k in EN if k in table and set(PH.findall(EN[k])) != set(PH.findall(table[k]))]
    return errs


def main():
    tables = {"en": EN, "ar": AR, "hi": HI, "ta": TA}
    errs = [e for lang, tb in tables.items() if lang != "en" for e in check(lang, tb)]
    if errs:
        raise SystemExit("\n".join(errs))
    # In right-to-left text, keep "{value} unit" (e.g. "100 W") in left-to-right order with a Unicode isolate
    tables["ar"] = {k: UNIT.sub("⁦\\1⁩", v) for k, v in AR.items()}   # LRI ... PDI
    for lang, tb in tables.items():
        p = os.path.join(HERE, "locales", f"{lang}.json")
        d = json.load(open(p, encoding="utf8"))
        d["app"] = dict(tb)
        json.dump(d, open(p, "w", encoding="utf8"), ensure_ascii=False, indent=2)
        if os.path.isdir(WEB):
            shutil.copy(p, os.path.join(WEB, f"i18n_{lang}.json"))
    print(f"{len(EN)} app strings x {len(tables)} languages merged")


if __name__ == "__main__":
    main()
