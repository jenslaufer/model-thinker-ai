import pytest
from fastapi.testclient import TestClient

PROBLEM = {
    "description": "Our customers churn between active and dormant states. Should we invest in retention?",
    "objective": "Maximise the long-run share of active customers",
    "time_horizon": "24 months",
    "actors": ["Company", "Customers"],
    "decision_scope": "Retention budget",
}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    monkeypatch.setenv("AUTH_DEV_MODE", "1")
    monkeypatch.delenv("OIDC_ISSUER_URL", raising=False)
    from app.main import create_app

    with TestClient(create_app()) as c:
        yield c


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_model_library(client):
    models = client.get("/api/models").json()
    assert len(models) == 24
    assert sum(m["implemented"] for m in models) >= 5
    detail = client.get("/api/models/diffusion").json()
    assert detail["math"] and detail["params"]
    assert detail["question"].endswith("?") and detail["metric_help"]["peak_time"]
    assert client.get("/api/models/nope").status_code == 404


def test_run_model_and_reject_invalid_params(client):
    r = client.post("/api/models/normal/run", json={"params": {"mu": 0, "sigma": 1, "threshold": 0}})
    assert r.status_code == 200
    assert r.json()["metrics"]["p_above"] == pytest.approx(0.5)
    assert client.post("/api/models/normal/run", json={"params": {"sigma": -1}}).status_code == 422
    assert client.post("/api/models/concavity/run", json={"params": {}}).status_code == 409  # planned only


def test_simulate_endpoint(client):
    r = client.post("/api/models/diffusion/simulate", json={"params": {}, "band": 0.2, "what_if": {"q": 0.5}})
    body = r.json()
    assert {s["kind"] for s in body["scenarios"]} >= {"baseline", "best", "worst", "what_if"}
    assert body["sensitivity"] and body["monte_carlo"]["summary"]


def test_structure_preview(client):
    body = client.post("/api/structure", json=PROBLEM).json()
    assert "churn" in body["structure"]["problem_types"]
    assert "markov" in body["selection"]["selected"]


def test_analysis_lifecycle(client):
    created = client.post("/api/analyses", json={"title": "Churn", "problem": PROBLEM}).json()
    aid = created["id"]
    assert created["revision"] == 1
    assert created["result"]["executions"]
    answer = created["answer"]
    assert answer["question"] == PROBLEM["objective"]
    assert answer["reliability"] == "illustrative"
    assert answer["other_angles"] and answer["verdict"]["status"] == "no_target"

    listed = client.get("/api/analyses").json()
    assert [a["id"] for a in listed] == [aid]

    reopened = client.get(f"/api/analyses/{aid}").json()
    assert reopened["result"]["executions"] == created["result"]["executions"]

    rerun = client.post(f"/api/analyses/{aid}/rerun", json={
        "selected": ["markov", "system_dynamics"],
        "overrides": {"system_dynamics": {"growth_rate": 0.8}},
        "what_if": {"system_dynamics": {"capacity": 9000}},
    }).json()
    assert rerun["revision"] == 2
    ex = {e["model_key"]: e for e in rerun["result"]["executions"]}
    assert set(ex) == {"markov", "system_dynamics"}
    assert ex["system_dynamics"]["params"]["growth_rate"] == {"value": 0.8, "origin": "user_input", "rationale": "",
                                                         "confidence": None}
    assert any(s["kind"] == "what_if" for s in ex["system_dynamics"]["scenarios"])

    revs = client.get(f"/api/analyses/{aid}/revisions").json()
    assert [r["revision"] for r in revs] == [1, 2]
    old = client.get(f"/api/analyses/{aid}", params={"revision": 1}).json()
    assert old["revision"] == 1 and len(old["result"]["executions"]) == len(created["result"]["executions"])

    graph = client.get(f"/api/analyses/{aid}/graph").json()
    assert graph["nodes"] and graph["edges"]

    report = client.get(f"/api/analyses/{aid}/report").json()
    assert "# Churn" in report["content"] and "Computed" in report["content"]
    assert report["content"].index("## The answer") < report["content"].index("## Model selection")
    assert report["content"].index("**Answer:**") < report["content"].index("## Model selection")

    rec = rerun["recommendations"][0]
    patched = client.patch(f"/api/recommendations/{rec['db_id']}", json={"decision_status": "accepted", "note": "go"})
    assert patched.json()["decision_status"] == "accepted"
    assert client.patch(f"/api/recommendations/{rec['db_id']}", json={"decision_status": "maybe"}).status_code == 422

    ev = client.post(f"/api/analyses/{aid}/evidence", json={"description": "Q1 churn was 6%", "source": "CRM"})
    assert ev.status_code == 201

    dash = client.get("/api/dashboard").json()
    assert dash["counts"]["analyses"] == 1
    assert dash["open_decisions"]
    assert dash["recent_simulations"]

    audit = client.get("/api/audit").json()
    actions = {a["action"] for a in audit}
    assert {"analysis.create", "analysis.rerun", "recommendation.decide", "evidence.create"} <= actions


def test_rerun_with_invalid_override_reports_model_error(client):
    aid = client.post("/api/analyses", json={"problem": PROBLEM}).json()["id"]
    r = client.post(f"/api/analyses/{aid}/rerun", json={"selected": ["markov"],
                                                        "overrides": {"markov": {"steps": -5}}}).json()
    assert r["result"]["executions"][0]["status"] == "error"


def test_rerun_rejects_unknown_model(client):
    aid = client.post("/api/analyses", json={"problem": PROBLEM}).json()["id"]
    assert client.post(f"/api/analyses/{aid}/rerun", json={"selected": ["concavity"]}).status_code == 422


def test_tenant_isolation(client):
    aid = client.post("/api/analyses", json={"problem": PROBLEM}).json()["id"]
    other = {"X-Workspace": "other"}
    assert client.get("/api/analyses", headers=other).json() == []
    assert client.get(f"/api/analyses/{aid}", headers=other).status_code == 404


def test_empty_problem_rejected(client):
    assert client.post("/api/analyses", json={"problem": {"description": "  "}}).status_code == 422


def test_instances_round_trip(client):
    body = {"problem": PROBLEM, "selected": ["normal", "normal:wide"], "overrides": {"normal:wide": {"sigma": 30}}}
    created = client.post("/api/analyses", json=body)
    assert created.status_code == 201
    loaded = client.get(f"/api/analyses/{created.json()['id']}").json()
    ex = loaded["result"]["executions"]
    assert [e["instance"] or e["model_key"] for e in ex] == ["normal", "normal:wide"]
    assert ex[1]["params"]["sigma"]["value"] == 30


@pytest.mark.parametrize("selected", [["nope:x"], ["normal", "normal"], ["markov:"]])
def test_bad_instances_are_rejected(client, selected):
    assert client.post("/api/analyses", json={"problem": PROBLEM, "selected": selected}).status_code == 422


def test_stored_ai_proposal_loads_as_estimate(client):
    from app import db
    aid = client.post("/api/analyses", json={"problem": PROBLEM, "selected": ["normal"]}).json()["id"]
    S = db.make_session_factory()
    with S() as s:
        for p in s.query(db.ModelParameter).all():
            p.origin, p.value = "ai_proposal", {"v": p.value["v"]}
        s.commit()
    params = client.get(f"/api/analyses/{aid}").json()["result"]["executions"][0]["params"]
    assert {p["origin"] for p in params.values()} == {"ai_estimate"}
    assert {p["confidence"] for p in params.values()} == {"unknown"}


def test_frame_endpoint_and_stored_frame(client):
    r = client.post("/api/frame", json={"description": "Grow my extension"}).json()
    assert r["frame"]["kind"] == "explain" and r["missing"] == []
    r = client.post("/api/frame", json={"description": "Grow", "target_quantity": "users", "target_value": 10}).json()
    assert r["frame"]["kind"] == "reach_target" and r["frame"]["target"] == 10
    created = client.post("/api/analyses", json={"problem": PROBLEM}).json()
    assert created["result"]["selection"]["frame"]["kind"] == "explain"


def test_revision_without_frame_loads(client):
    from app import db
    aid = client.post("/api/analyses", json={"problem": PROBLEM, "selected": ["normal"]}).json()["id"]
    with db.make_session_factory()() as s:
        rev = s.query(db.AnalysisRevision).one()
        rev.selection = {k: v for k, v in rev.selection.items() if k not in ("frame", "choices", "uncovered")}
        s.commit()
    assert client.get(f"/api/analyses/{aid}").json()["result"]["selection"]["frame"] is None


def test_goal_analysis_round_trips(client):
    problem = PROBLEM | {"target_quantity": "active customers", "target_value": 0.5}
    created = client.post("/api/analyses", json={"problem": problem, "selected": ["system_dynamics"]}).json()
    loaded = client.get(f"/api/analyses/{created['id']}").json()
    assert created["result"]["executions"][0]["goal"]["metric"] == "final_stock"
    assert loaded["result"]["executions"][0]["goal"] == created["result"]["executions"][0]["goal"]


def test_rerun_keeps_the_first_ai_setup_after_a_failed_run(client):
    # Gate RED: the setup was rebuilt from the last revision, so a failed run or a removed override lost it
    from test_llm import FakeClient, est

    from app.llm import anthropic_provider as ap
    matrix = [[0.9, 0.1, 0.0], [0.2, 0.7, 0.1], [0.0, 0.0, 1.0]]
    client.app.state.provider = ap.AnthropicProvider(FakeClient({
        "_Estimates": ap._Estimates(estimates=[est("transition_matrix", matrix, "typical churn", "low")])}))
    aid = client.post("/api/analyses", json={"problem": PROBLEM, "selected": ["markov"]}).json()["id"]
    client.app.state.provider = ap.AnthropicProvider(FakeClient({}))  # AI would now fail: setup must come from storage
    bad = [[0.9, 0.9, 0.0], [0.2, 0.7, 0.1], [0.0, 0.0, 1.0]]
    failed = client.post(f"/api/analyses/{aid}/rerun", json={"overrides": {"markov": {"transition_matrix": bad}}})
    assert failed.json()["result"]["executions"][0]["status"] == "error"
    fixed = client.post(f"/api/analyses/{aid}/rerun", json={"overrides": {}}).json()
    tm = fixed["result"]["executions"][0]["params"]["transition_matrix"]
    assert (tm["value"], tm["origin"], tm["confidence"]) == (matrix, "ai_estimate", "low")
