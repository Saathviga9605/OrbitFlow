"""Operations API: scenarios, policy profiles, multilingual requests, registry and governance."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client(kb):
    from dashboard import api
    api._state["kb"] = kb
    return TestClient(api.app)


def test_listing_endpoints(client):
    assert len(client.get("/api/scenarios").json()) == 10
    assert {p["profile_id"] for p in client.get("/api/policy/profiles").json()} >= {"baseline-intl", "ae-demo", "in-demo"}
    assert any(a["id"] == "guard" for a in client.get("/api/agents").json())
    assert client.get("/api/i18n/ar").json()["_meta"]["dir"] == "rtl"
    assert client.get("/api/i18n/fr").status_code == 404
    g = client.get("/api/governance").json()
    assert g["standards"]["entries"] and g["readiness"]["factors"] and g["requirements_alignment"]


def test_errors_are_explicit(client):
    assert client.post("/api/scenarios/S99/run").status_code == 404
    assert client.post("/api/scenarios/S1_normal/run?seed=-1").status_code == 422
    assert client.post("/api/policy/run?exemption=maybe").status_code == 422
    assert client.post("/api/policy/run?cap_w=500").status_code == 422
    assert client.get("/api/policy/profiles/xx").status_code == 404
    assert client.post("/api/interpret?text=").status_code == 422
    bad = client.post("/api/policy/validate", json={"profile_id": "x"}).json()
    assert not bad["valid"] and bad["errors"]


def test_arabic_request_runs_and_is_explained_in_arabic(client):
    r = client.post("/api/interpret", params={"text": "حاكِ فيضاناً مع حد قدرة 16 واط وفق ملف الإمارات"}).json()
    assert r["language"] == "ar" and r["interpreted"]["profile_id"] == "ae-demo"
    assert r["result"]["kpis"]["cap_violation_slots"] == 0
    assert any("فترات" in s or "%" in s for s in r["result"]["explanation"]["ar"])


def test_unrecognised_request_does_not_run(client):
    r = client.post("/api/interpret", params={"text": "tell me a joke"}).json()
    assert not r["interpreted"]["understood"] and "result" not in r


def test_policy_run_changes_with_the_profile(client):
    a = client.post("/api/policy/run?profile=baseline-intl").json()
    b = client.post("/api/policy/run?profile=in-demo").json()
    assert a["coordination"]["exempted_slots"] == 0 and b["coordination"]["exempted_slots"] > 0
