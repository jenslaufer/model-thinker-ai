import re

import pytest

from app.engine.answer import build_answer
from app.engine.goal import GoalFrame
from app.engine.orchestrator import run_analysis
from app.engine.structure import ProblemInput
from app.modeling.plain import PLAIN, explain_metric, plain_text
from app.modeling.registry import REGISTRY, get_model

IMPLEMENTED = sorted(REGISTRY.models)
SNAKE = re.compile(r"\b[a-z]+_[a-z_]+\b")  # raw metric keys like p_hit_threshold must not leak into plain text


@pytest.mark.parametrize("key", IMPLEMENTED)
def test_every_model_explains_itself_in_plain_words(key):
    model = get_model(key)
    params = model.validate({})
    out = model.run(params)
    entry = PLAIN[key]
    assert entry.question.endswith("?")
    text = plain_text(key, params, out.metrics)
    assert text and "nan" not in text.lower() and "None" not in text
    assert not SNAKE.search(text), text
    for metric in out.metrics:
        assert explain_metric(key, metric), f"{key}.{metric} has no plain explanation"


def test_plain_text_uses_the_numbers():
    text = plain_text("random_walk", get_model("random_walk").validate({"start": 1000, "threshold": 0, "steps": 30}),
                      {"q05_final": 120.0, "q95_final": 2400.0, "mean_final": 1100.0, "p_hit_threshold": 0.08})
    assert "1,000" in text and "30 periods" in text and "8%" in text and "drops to 0" in text


PROBLEM = ProblemInput(description="Customers churn between active and dormant states. Should we invest in retention?",
                       objective="Keep more customers active", time_horizon="24 months", actors=["Company", "Customers"])


def test_answer_says_plainly_when_no_user_numbers_were_used():
    a = build_answer(run_analysis(PROBLEM, selected=["markov", "normal", "entropy"]))
    assert a.question == "Keep more customers active"
    assert a.reliability == "illustrative"
    assert "example values" in a.reliability_text
    assert a.verdict.status == "no_target"
    assert a.other_angles and all(f.data_source == "example values" for f in a.other_angles)


def test_other_angles_are_ordered_by_fit_and_marked():
    result = run_analysis(PROBLEM, selected=["markov", "normal", "entropy"],
                          overrides={"normal": {"mu": 5, "sigma": 2}})
    for e, fit in zip(result.executions, (30, 70, 55), strict=True):
        e.fit_score = fit
    a = build_answer(result)
    assert a.reliability == "rough"
    assert [f.fit for f in a.other_angles] == [70, 55, 30]
    assert {f.model_key: f.data_source for f in a.other_angles}["normal"] == "partly your numbers"


def test_unknowns_name_parameters_by_label():
    a = build_answer(run_analysis(PROBLEM, selected=["normal", "random_walk", "entropy"]))
    assert a.unknowns
    assert not any(SNAKE.search(u.label) for u in a.unknowns), a.unknowns


@pytest.mark.parametrize(("key", "params"), [
    ("linear", {"data_x": [], "data_y": []}),              # assumed projection: no prediction interval
    ("linear", {"data_x": [1, 2], "data_y": [1, 2]}),      # two points: no interval either
    ("system_dynamics", {"growth_rate": 0, "outflow_rate": 0}),  # no balance point (infinite equilibrium)
])
def test_plain_text_survives_missing_or_infinite_metrics(key, params):
    model = get_model(key)
    p = model.validate(params)
    text = plain_text(key, p, model.run(p).metrics)
    assert "None" not in text and "inf" not in text.lower().replace("infinite", ""), text


def test_ai_estimates_are_not_user_numbers():
    result = run_analysis(PROBLEM, selected=["markov", "normal", "entropy"])
    for e in result.executions:
        for p in e.params.values():
            p.origin, p.confidence = "ai_estimate", "medium"
    a = build_answer(result)
    assert a.reliability == "estimated" and "AI estimates" in a.reliability_text
    assert all(f.data_source == "AI estimates" for f in a.other_angles)


def test_one_broken_finding_does_not_break_the_answer():
    result = run_analysis(PROBLEM, selected=["markov", "normal", "entropy"])
    result.executions[0].output.metrics.clear()  # e.g. an old revision with a different metric set
    assert len(build_answer(result).other_angles) == 2


def test_entropy_sentence_reads_the_computed_largest_share():
    model = get_model("entropy")
    p = model.validate({"probabilities": [2, 1, 1]})
    m = model.run(p).metrics
    assert m["max_share"] == pytest.approx(0.5)
    assert "50%" in plain_text("entropy", p, m)


# --- question-first answer for the extension case ----------------------------------------------------------------
TOO_PRECISE = re.compile(r"0\.0*[1-9]\d{2,}|[1-9]\d*\.\d{2,}|\d{2,}\.\d")  # 3+ significant figures
EXT = ProblemInput(description="Chrome extension, 4,000 installs, 120 paying users, 8% cancel each month.",
                   objective="Reach 1,000 paying users", time_horizon="12 months",
                   target_quantity="paying users", target_value=1000)


def ext_result():
    from app.engine.goal import ModelChoice
    from app.engine.orchestrator import Setup
    est = lambda d: {k: {"value": v, "rationale": "typical value", "confidence": "low"} for k, v in d.items()}
    setup = Setup(
        frame=GoalFrame(kind="reach_target", quantity="paying users", target=1000, horizon="12 months",
                        origin="user_input"),
        choices=[ModelChoice(key=k, instance=k, reason="fits", goal_metric=m) for k, m in (
            ("linear", "forecast"), ("random_walk", "mean_final"), ("system_dynamics", "final_stock"),
            ("markov", "final_target_count"), ("entropy", None))],
        estimates={"random_walk": est({"drift": 10, "volatility": 15}),
                   "system_dynamics": est({"growth_rate": 0.15, "capacity": 4000, "outflow_rate": 0.08}),
                   "markov": est({"transition_matrix": [[0.95, 0.03, 0.02], [0.0, 0.92, 0.08], [0.0, 0.05, 0.95]]})})
    overrides = {
        "linear": {"data_x": [1, 2, 3, 4, 5, 6], "data_y": [60, 72, 85, 94, 108, 120], "horizon": 12},
        "random_walk": {"start": 120, "steps": 12, "threshold": 50},
        "system_dynamics": {"initial_stock": 120, "horizon": 12, "external_inflow": 5},
        "markov": {"states": ["Free", "Paying", "Churned"], "initial": [0.97, 0.03, 0.0], "steps": 12,
                   "target_state": 1, "population": 4000}}
    return run_analysis(EXT, overrides=overrides, setup=setup)


def test_extension_answer_is_question_first():
    a = build_answer(ext_result())
    assert a.verdict.status == "unlikely" and "1,000" in a.verdict.text
    assert "3 of 4 models" in a.verdict.text and "every model" not in a.verdict.text
    assert len(a.goal_results) == 4
    assert "Markov" in a.differences[0] and "Free → Paying" in a.differences[0]
    assert a.what_it_takes
    assert any("Free → Paying" in u.label for u in a.unknowns)
    assert [f.model_key for f in a.other_angles] == ["entropy"]
    assert set(a.plain) == {"linear", "random_walk", "system_dynamics", "markov", "entropy"}  # every model card
    assert "(results 220–420)" in a.verdict.text  # estimate-based results: 2 significant figures
    texts = [a.verdict.text, *a.differences, *a.what_it_takes, *[u.effect_text for u in a.unknowns]]
    assert not any(TOO_PRECISE.search(t) for t in texts), texts


def test_rough_keeps_two_significant_figures():
    from app.modeling.base import rough
    assert [rough(x) for x in (224.22, 38412.0, 0.03369, 1249.0, 7.0)] == ["220", "38,000", "0.034", "1,200", "7"]


def test_setup_lists_every_value_the_user_did_not_enter():
    r = ext_result()
    a = build_answer(r)
    rows = {(x.instance, x.param) for x in a.setup.estimates}
    expected = {(e.id, n) for e in r.executions for n, p in e.params.items() if p.origin != "user_input"}
    assert rows == expected
    tm = next(x for x in a.setup.estimates if x.param == "transition_matrix")
    assert (tm.origin, tm.confidence, tm.rationale) == ("ai_estimate", "low", "typical value")
    assert [c.reason for c in a.setup.choices] == ["fits"] * 5


def test_old_revision_without_goal_still_answers():
    r = run_analysis(PROBLEM, selected=["markov", "normal", "entropy"])
    r.selection.frame = None
    a = build_answer(r)
    assert a.verdict.status == "no_goal_metric" and len(a.other_angles) == 3


def test_report_leads_with_the_verdict():
    from app.report import render
    content = render("Extension", 1, ext_result())
    assert content.index("**Answer:** Probably not") < content.index("## Model selection")
    assert "**Why the models differ:**" in content and "| Markov Models |" in content


def test_likely_verdict_reads_cleanly():
    r = ext_result()
    r.selection.frame = r.selection.frame.model_copy(update={"target": 100})
    v = build_answer(r).verdict
    assert v.status == "likely" and "at at" not in v.text and "reaches at least 100" in v.text
    assert build_answer(r).what_it_takes == []  # nothing to change for models that already reach the target


def test_risk_limit_without_risk_metric_says_so():
    problem = PROBLEM.model_copy(update={"target_quantity": "money", "risk_limit": 0.05})
    a = build_answer(run_analysis(problem, selected=["random_walk", "system_dynamics", "normal"]))
    assert a.verdict.status == "no_goal_metric" and "risk" in a.verdict.text
