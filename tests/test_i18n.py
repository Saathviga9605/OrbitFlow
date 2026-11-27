"""Multilingual input and output: locale completeness, language detection, digit handling, explanations."""
import json
import os
import re

import pytest

from i18n.explain import SUPPORTED, explain, locale
from i18n.interpret import detect_language, interpret, normalise

LOC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "i18n", "locales")


def _flat(d, prefix=""):
    for k, v in d.items():
        if isinstance(v, dict):
            yield from _flat(v, f"{prefix}{k}.")
        else:
            yield f"{prefix}{k}", v


@pytest.mark.parametrize("lang", [x for x in SUPPORTED if x != "en"])
def test_every_language_has_every_key_with_the_same_placeholders(lang):
    en = dict(_flat(locale("en")))
    other = dict(_flat(locale(lang)))
    missing = [k for k in en if k not in other and not k.startswith("_meta")]
    assert not missing, missing
    for k, v in en.items():
        if isinstance(v, str) and k in other:
            assert set(re.findall(r"{(\w+)}", v)) == set(re.findall(r"{(\w+)}", other[k])), k


def test_arabic_is_marked_rtl_and_others_ltr():
    assert locale("ar")["_meta"]["dir"] == "rtl"
    assert all(locale(x)["_meta"]["dir"] == "ltr" for x in ("en", "hi", "ta"))


def test_locale_files_are_valid_utf8_json():
    for f in os.listdir(LOC):
        json.load(open(os.path.join(LOC, f), encoding="utf8"))


REQUESTS = {
    "en": "Simulate a flood with a 16 W power cap under the UAE profile",
    "ar": "حاكِ فيضاناً مع حد قدرة 16 واط وفق ملف الإمارات",
    "hi": "यूएई प्रोफ़ाइल के तहत 16 वाट पावर सीमा के साथ बाढ़ का सिमुलेशन करें",
    "ta": "ஐக்கிய அரபு அமீரக சுயவிவரத்தில் 16 வாட் சக்தி வரம்புடன் வெள்ளத்தை உருவகப்படுத்து",
}


def test_the_same_request_in_four_languages_gives_one_intent():
    intents = {}
    for lang, text in REQUESTS.items():
        it = interpret(text)
        assert it["language"] == lang
        intents[lang] = (it["scenario_id"], it["profile_id"], it["params"])
    assert len(set(map(repr, intents.values()))) == 1
    assert intents["en"] == ("custom_flood", "ae-demo", {"cap_w": 16.0})


def test_native_digits_are_understood():
    assert interpret("فيضان مع حد ١٨ واط")["params"]["cap_w"] == 18.0          # Arabic-Indic digits
    assert interpret("बाढ़ १२ वाट")["params"]["cap_w"] == 12.0                     # Devanagari digits
    assert normalise("௧௫") == "15"                                               # Tamil digits


def test_scenario_keywords_and_unknown_text():
    assert interpret("what happens if an agent crash occurs")["scenario_id"] == "S6_agent_failure"
    assert interpret("بيانات مفقودة")["scenario_id"] == "S10_data_failure"
    assert interpret("நெரிசல்")["scenario_id"] == "S3_congestion"
    it = interpret("tell me a joke")
    assert not it["understood"] and it["scenario_id"] is None
    assert detect_language("hello") == "en"
    with pytest.raises(ValueError):
        interpret("   ")


def test_explanations_contain_only_measured_numbers():
    r = {"id": "S6_agent_failure", "seed": 42, "profile": {"profile_id": "baseline-intl"},
         "kpis": {"rt_sla_violation": 0.018, "mean_delay_ms": 19.2, "throughput_mbps": 176.5, "emergency_served_ratio": 0.957},
         "coordination": {"agent_health": {"network": {"failures": 15, "by_kind": {"exception": 10, "malformed": 3, "timeout": 2}}},
                          "failures": [{"fallback": "reactive_greedy"}]},
         "checks": [{"passed": True}, {"passed": False}]}
    for lang in SUPPORTED:
        lines = explain(r, lang)
        text = " ".join(lines)
        assert "{" not in text and "1.8" in text and "15" in text and "95.7" in text
        assert any("1" in ln and "2" in ln for ln in lines)                       # 1 of 2 checks
    assert explain(r, "xx") == explain(r, "en")                                    # unknown language falls back to English
