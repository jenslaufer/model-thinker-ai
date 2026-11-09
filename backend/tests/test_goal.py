import math

import pytest

from app.engine.goal import GoalFrame, analyse, differences, drivers, goal_seek, set_entry
from app.engine.orchestrator import ParamValue, execute_model, with_goal
from app.engine.structure import ProblemInput, structure_problem
from app.llm.heuristic import HeuristicProvider
from app.modeling.base import Model, ModelOutput, ModelSpec, ParamSpec
from app.modeling.registry import get_model


def test_reach_target_without_target_is_missing():
    assert GoalFrame(kind="reach_target", quantity="paying users").missing() == ["target"]


def test_maximise_under_risk_needs_a_risk_limit():
    assert GoalFrame(kind="maximise_under_risk").missing() == ["quantity", "risk_limit"]
    assert GoalFrame(kind="explain").missing() == []


def test_user_answers_win_over_frame():
    inp = ProblemInput(description="Grow my extension", target_quantity="paying users", target_value=1000)
    f = HeuristicProvider().frame(inp, structure_problem(inp))
    assert (f.kind, f.target, f.quantity, f.origin) == ("reach_target", 1000, "paying users", "user_input")


def test_heuristic_without_goal_fields_explains():
    inp = ProblemInput(description="Grow my extension", time_horizon="12 months")
    f = HeuristicProvider().frame(inp, structure_problem(inp))
    assert (f.kind, f.horizon, f.origin) == ("explain", "12 months", "heuristic")


EXT_MATRIX = [[0.95, 0.03, 0.02], [0.0, 0.92, 0.08], [0.0, 0.05, 0.95]]
EXT_FRAME = GoalFrame(kind="reach_target", quantity="paying users", target=1000)


def ext_markov():
    est = {"transition_matrix": {"value": EXT_MATRIX, "rationale": "typical for small tools", "confidence": "low"}}
    return execute_model("markov", {"states": ["Free", "Paying", "Churned"], "initial": [0.97, 0.03, 0.0],
                                    "steps": 12, "target_state": 1, "population": 4000}, est, 50, 0.2, 42)


def test_goal_seek_matches_closed_form():
    # system_dynamics is a continuous ODE: with r=0, u=0 the stock decays as S0*exp(-d*T)
    model = get_model("system_dynamics")
    params = model.validate({"initial_stock": 1000, "growth_rate": 0, "external_inflow": 0, "horizon": 20})
    s = goal_seek(model, params, "outflow_rate", "final_stock", 1000 * math.exp(-0.05 * 20), seed=42)
    assert s.status == "solved" and s.value == pytest.approx(0.05, rel=1e-3)


def test_unreachable_target_is_reported():
    model = get_model("system_dynamics")
    params = model.validate({"initial_stock": 1000, "growth_rate": 0, "external_inflow": 0, "horizon": 20})
    assert goal_seek(model, params, "outflow_rate", "final_stock", 10**12, seed=42).status == "not_reachable"


class Hump(Model):
    spec = ModelSpec(key="hump", number=99, name="Hump", family="A", summary="test",
                     params=[ParamSpec(name="x", label="x", default=0.2, min=0, max=1),
                             ParamSpec(name="c", label="c", default=1.0, min=0, max=2)])

    def compute(self, p, rng):
        return ModelOutput(metrics={"y": -(p["x"] - 0.5) ** 2, "flat": 1.0})


def test_non_monotonic_and_flat_metrics():
    m = Hump()
    p = m.validate({})
    s = goal_seek(m, p, "x", "y", -0.01, seed=42)
    assert s.status == "not_monotonic" and s.value is None
    assert goal_seek(m, p, "c", "flat", 2.0, seed=42).status == "not_reachable"


def test_set_entry_keeps_rows_stochastic():
    m = set_entry(EXT_MATRIX, 0, 1, 0.01)
    assert sum(m[0]) == pytest.approx(1) and m[0][1] == 0.01 and m[1] == EXT_MATRIX[1]


def test_markov_drivers_rank_matrix_entries():
    g = analyse(ext_markov(), EXT_FRAME, "final_target_count", 0.2, 42)
    assert g.value is not None and g.value < 1000
    top = g.drivers[0]
    assert top.entry is not None and "→" in top.label and top.confidence == "low"
    assert any(s.status == "solved" for s in g.seeks)


def test_missing_goal_metric_value_gives_no_crash():
    e = execute_model("linear", {"data_x": [], "data_y": []}, None, 50, 0.2, 42)
    g = analyse(e, GoalFrame(kind="reach_target", quantity="x", target=10), "forecast_lo", 0.2, 42)
    assert g.value is None and g.seeks == [] and g.drivers == []


def test_user_numbers_are_not_drivers():
    model = get_model("normal")
    params = model.validate({})
    origins = {n: ParamValue(value=v, origin="user_input") for n, v in params.items()}
    assert drivers(model, params, origins, "p_above", 0.2, 42) == []


def _est(d):
    return {k: {"value": v, "rationale": "typical value", "confidence": "low"} for k, v in d.items()}


def extension_executions():
    """The extension growth case: four models that report paying users at month 12."""
    runs = [("linear", {"data_x": [1, 2, 3, 4, 5, 6], "data_y": [60, 72, 85, 94, 108, 120], "horizon": 12}, {}),
            ("random_walk", {"start": 120, "steps": 12, "threshold": 50}, _est({"drift": 10, "volatility": 15})),
            ("system_dynamics", {"initial_stock": 120, "horizon": 12, "external_inflow": 5},
             _est({"growth_rate": 0.15, "capacity": 4000, "outflow_rate": 0.08}))]
    out = [with_goal(execute_model(k, ov, est, 50, 0.2, 42), EXT_FRAME, {}, 0.2, 42) for k, ov, est in runs]
    return out + [with_goal(ext_markov(), EXT_FRAME, {}, 0.2, 42)]


def test_markov_is_the_outlier_because_of_free_to_paying():
    found = differences(extension_executions(), 42)
    assert [d.instance for d in found] == ["markov"]
    d = found[0]
    assert "Free → Paying" in d.driver.label
    assert d.agrees_at is not None and d.agrees_at < d.driver.value
    assert d.others_low < d.others_high < 1000


# --- final review fixes ------------------------------------------------------------------------------------------

def test_risk_question_needs_a_risk_metric():
    # C1: no model in this release measures a probability, so a risk limit must not be "solved" on a level metric
    from app.engine.orchestrator import goal_metric_for
    e = execute_model("random_walk", {"start": 0, "drift": 0.005}, None, 50, 0.2, 42)
    frame = GoalFrame(kind="maximise_under_risk", quantity="money", risk_limits=[0.05])
    assert goal_metric_for(e, frame, {}) is None
    assert goal_metric_for(e, frame, {"random_walk": "mean_final"}) is None  # an AI choice of a level metric too


def test_spread_models_are_not_outliers():
    # C2: three models far apart: none may be dropped as an outlier, because the rest do not agree either
    ex = extension_executions()[:3]  # linear, random_walk, system_dynamics
    for e, (v, lo, hi) in zip(ex, [(96, 86, 106), (240, 225, 255), (1439, 1300, 1600)], strict=True):
        e.goal = e.goal.model_copy(update={"value": v, "p05": lo, "p95": hi})
    assert differences(ex, 42) == []


def test_two_models_are_never_outliers_of_each_other():
    ex = [e for e in extension_executions() if e.model_key in ("random_walk", "markov")]
    assert differences(ex, 42) == []


def test_goal_seek_survives_arithmetic_errors():
    class Brittle(Hump):
        def compute(self, p, rng):
            if p["x"] > 0.9:
                raise ZeroDivisionError("edge of range")
            return super().compute(p, rng)
    m = Brittle()
    assert goal_seek(m, m.validate({}), "x", "y", -0.2, seed=42).status == "not_reachable"


def test_failing_goal_analysis_leaves_the_model_without_goal(monkeypatch):
    from app.engine import orchestrator
    def boom(*a, **k):
        raise RuntimeError("unexpected")
    monkeypatch.setattr(orchestrator, "analyse", boom)
    e = orchestrator.with_goal(ext_markov(), EXT_FRAME, {}, 0.2, 42)
    assert e.goal is None and e.status == "ok"
