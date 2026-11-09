"""The user's goal and the computations that answer it.

The goal (quantity, target, risk limit) comes from the user or from their text, never from an estimate.
Every number derived here comes from running models.
"""

from __future__ import annotations

import itertools
import math
import statistics
from typing import Literal

from pydantic import BaseModel

from app.modeling.base import bounds, fmt

GoalKind = Literal["reach_target", "maximise_under_risk", "compare_options", "explain"]


class GoalFrame(BaseModel):
    quantity: str = ""
    unit: str = ""
    kind: GoalKind = "explain"
    direction: Literal["at_least", "at_most"] = "at_least"
    target: float | None = None
    risk_limits: list[float] = []
    horizon: str = ""
    lever: str = ""
    origin: Literal["ai", "user_input", "heuristic"] = "heuristic"

    def missing(self) -> list[Literal["quantity", "target", "risk_limit"]]:
        out = []
        if self.kind in ("reach_target", "maximise_under_risk") and not self.quantity:
            out.append("quantity")
        if self.kind == "reach_target" and self.target is None:
            out.append("target")
        if self.kind == "maximise_under_risk" and not self.risk_limits:
            out.append("risk_limit")
        return out


class ModelChoice(BaseModel):
    key: str
    instance: str
    reason: str
    goal_metric: str | None = None


def heuristic_frame(inp, structure) -> GoalFrame:
    """Frame from the explicit goal fields only; without them the question is explained, not judged."""
    user = inp.target_value is not None or inp.risk_limit is not None
    kind = "reach_target" if inp.target_value is not None else "maximise_under_risk" if inp.risk_limit else "explain"
    return GoalFrame(quantity=inp.target_quantity, kind=kind, target=inp.target_value,
                     risk_limits=[inp.risk_limit] if inp.risk_limit else [], horizon=inp.time_horizon,
                     origin="user_input" if user else "heuristic")


def apply_user_goal(frame: GoalFrame, inp) -> GoalFrame:
    """The user's answers to the goal question always win over a framed goal."""
    upd = {}
    if inp.target_quantity:
        upd["quantity"] = inp.target_quantity
    if inp.target_value is not None:
        upd |= {"target": inp.target_value, "kind": "reach_target"}
    if inp.risk_limit is not None:
        upd |= {"risk_limits": [inp.risk_limit], "kind": "maximise_under_risk"}
    return frame.model_copy(update=upd | {"origin": "user_input"}) if upd else frame




# --- computations (all numbers come from running models) -------------------------------------------------------

NON_USER = ("ai_estimate", "default_assumption")  # values the user did not enter: the unknowns


class Driver(BaseModel):
    param: str
    entry: list[int] | None = None  # [row, col] for a transition-matrix entry
    label: str
    value: float
    low: float
    high: float
    metric_low: float
    metric_high: float
    swing: float
    origin: str = ""
    confidence: str | None = None
    rationale: str = ""


class Seek(BaseModel):
    param: str
    entry: list[int] | None = None
    label: str
    current: float
    target: float
    given: str = ""  # condition this solve assumes, e.g. "Return = 2.8"
    value: float | None = None
    status: Literal["solved", "not_reachable", "not_monotonic"]


class GoalAnalysis(BaseModel):
    metric: str
    value: float | None
    p05: float | None = None
    p95: float | None = None
    drivers: list[Driver] = []
    seeks: list[Seek] = []


def _num(v) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) else None


def _metric(model, params: dict, metric: str, seed: int) -> float | None:
    try:
        return _num(model.run(params, seed).metrics.get(metric))
    except (ValueError, ArithmeticError, IndexError):  # invalid or degenerate input at the edge of a range
        return None


def set_entry(matrix: list[list[float]], i: int, j: int, v: float) -> list[list[float]]:
    """Set P[i][j] and rescale the row's other entries so the row still sums to 1."""
    v = min(1.0, max(0.0, v))
    row = matrix[i]
    rest = sum(x for k, x in enumerate(row) if k != j)
    new = [v if k == j else (x * (1 - v) / rest if rest else (1 - v) / (len(row) - 1)) for k, x in enumerate(row)]
    return [new if k == i else list(r) for k, r in enumerate(matrix)]


def _with(params: dict, param: str, entry: list[int] | None, v: float) -> dict:
    return params | {param: set_entry(params[param], *entry, v) if entry else v}


def _state_names(model, params: dict) -> list[str] | None:
    labels = next((p.name for p in model.spec.params if p.type == "labels"), None)
    return params.get(labels) if labels else None


def drivers(model, params: dict, origins: dict, metric: str, band: float, seed: int) -> list[Driver]:
    """Values the user did not enter, ranked by how much they move the goal metric."""
    out = []
    names = _state_names(model, params)
    for spec in model.spec.params:
        o = origins.get(spec.name)
        if o is None or o.origin not in NON_USER:
            continue
        if spec.type in ("float", "int") and spec.uncertain:  # not simulation settings like paths or steps
            candidates = [(None, spec.label, params[spec.name], *bounds(spec, params[spec.name], band))]
        elif spec.type == "matrix" and spec.stochastic_rows:
            P = params[spec.name]
            candidates = [([i, j], f"Chance per period to move {names[i]} → {names[j]}" if names
                           else f"{spec.label} [{i},{j}]",
                           x, max(0.0, x * (1 - band)), min(1.0, x * (1 + band)))
                          for i, row in enumerate(P) for j, x in enumerate(row) if i != j and x > 0]
        else:
            continue
        for entry, label, v, lo, hi in candidates:
            if hi <= lo:
                continue
            m_lo, m_hi = (_metric(model, _with(params, spec.name, entry, x), metric, seed) for x in (lo, hi))
            if m_lo is None or m_hi is None or abs(m_hi - m_lo) <= 1e-9 * max(1.0, abs(m_lo)):
                continue  # unused or without effect on the goal
            out.append(Driver(param=spec.name, entry=entry, label=label, value=v, low=lo, high=hi, metric_low=m_lo,
                              metric_high=m_hi, swing=abs(m_hi - m_lo), origin=o.origin, confidence=o.confidence,
                              rationale=o.rationale))
    return sorted(out, key=lambda d: -d.swing)


def _range(model, param: str, entry: list[int] | None, v: float) -> tuple[float, float]:
    if entry:
        return (v / 10, min(1.0, v * 10)) if v else (0.0, 1.0)
    # Search one order of magnitude around the current value: what it would take, not any value at all.
    # Extreme values also make some models stiff (system dynamics near zero capacity).
    spec = next(p for p in model.spec.params if p.name == param)
    lo, hi = sorted((v / 10, v * 10)) if v else (-1.0, 1.0)
    return max(lo, spec.min) if spec.min is not None else lo, min(hi, spec.max) if spec.max is not None else hi


def goal_seek(model, params: dict, lever: Driver | str, metric: str, target: float, seed: int, steps: int = 30,
              given: str = "") -> Seek:
    """Bisection on one lever for the value where the metric hits the target. Never guesses a value."""
    if isinstance(lever, Driver):
        param, entry, label, current = lever.param, lever.entry, lever.label, lever.value
    else:
        spec = next(p for p in model.spec.params if p.name == lever)
        param, entry, label, current = lever, None, spec.label, float(params[lever])
    seek = Seek(param=param, entry=entry, label=label, current=current, target=target, given=given,
                status="not_reachable")
    lo, hi = _range(model, param, entry, current)
    def f(x):
        return _metric(model, _with(params, param, entry, x), metric, seed)

    xs = [lo + (hi - lo) * k / 4 for k in range(5)]
    ys = [f(x) for x in xs]
    if any(y is None for y in ys):
        return seek
    diffs = [b - a for a, b in itertools.pairwise(ys)]
    tol = 1e-9 * max(1.0, max(abs(y) for y in ys))
    rising, falling = all(d >= -tol for d in diffs), all(d <= tol for d in diffs)
    if rising and falling:
        return seek  # flat: no lever value changes the result
    if not (rising or falling):
        return seek.model_copy(update={"status": "not_monotonic"})
    if not min(ys) <= target <= max(ys):
        return seek
    a, b, ya = lo, hi, ys[0]
    for _ in range(steps):
        mid = (a + b) / 2
        ym = f(mid)
        if ym is None:
            return seek
        if (ym - target) * (ya - target) <= 0:
            b = mid
        else:
            a, ya = mid, ym
    return seek.model_copy(update={"status": "solved", "value": (a + b) / 2})


def analyse(execution, frame: GoalFrame, goal_metric: str, band: float, seed: int) -> GoalAnalysis:
    """Goal metric value, its uncertainty band, the drivers behind it and what it would take."""
    from app.modeling.registry import get_model

    model = get_model(execution.model_key)
    out = execution.output
    value = _num(out.metrics.get(goal_metric)) if out else None
    if value is None:
        return GoalAnalysis(metric=goal_metric, value=None)
    summary = execution.monte_carlo.summary.get(goal_metric, {}) if execution.monte_carlo else {}
    # Goal analysis runs the model ~100 times: use the cheaper inner settings Monte Carlo uses.
    params = model.validate({k: p.value for k, p in execution.params.items()}) | model.spec.mc_params
    found = drivers(model, params, execution.params, goal_metric, band, seed)
    lever = frame.lever if frame.lever in model.spec.levers else None
    seeks = []
    if frame.kind == "reach_target" and frame.target is not None:
        for lv in [lever] if lever else found[:2]:
            seeks.append(goal_seek(model, params, lv, goal_metric, frame.target, seed))
    elif (frame.kind == "maximise_under_risk" and goal_metric in model.spec.risk_metrics
          and (lever := lever or (model.spec.levers or [None])[0])):
        top = found[0] if found else None
        for limit in frame.risk_limits:
            seeks.append(goal_seek(model, params, lever, goal_metric, limit, seed))
            if top and top.param != lever:
                for x in (top.low, top.high):
                    seeks.append(goal_seek(model, _with(params, top.param, top.entry, x), lever, goal_metric, limit,
                                           seed, given=f"{top.label} = {fmt(x)}"))
    return GoalAnalysis(metric=goal_metric, value=value, p05=_num(summary.get("p05")), p95=_num(summary.get("p95")),
                        drivers=found, seeks=seeks)


OUTLIER_FACTOR = 1.5  # a model differs when it is this far from the agreeing others and outside their range


class Difference(BaseModel):
    instance: str
    model_name: str
    driver: Driver
    agrees_at: float | None  # driver value at which this model reaches the others' range
    others_low: float
    others_high: float


def differences(executions: list, seed: int) -> list[Difference]:
    """Models whose goal result lies outside every other model's range, explained by their top driver."""
    from app.modeling.registry import get_model

    goal = [e for e in executions if e.goal and e.goal.value is not None]
    span = {e.id: (e.goal.p05 if e.goal.p05 is not None else e.goal.value,
                   e.goal.p95 if e.goal.p95 is not None else e.goal.value) for e in goal}
    out = []
    for e in goal:
        rest = [o for o in goal if o.id != e.id]
        others = [span[o.id] for o in rest]
        # An outlier needs a majority that agrees among itself: at least two other models within the factor.
        values = [o.goal.value for o in rest]
        agree = len(rest) >= 2 and min(values) > 0 and max(values) / min(values) <= OUTLIER_FACTOR
        if not agree or not e.goal.drivers:
            continue
        lo, hi = min(a for a, _ in others), max(b for _, b in others)
        mine = span[e.id]
        median = statistics.median(o.goal.value for o in goal if o.id != e.id)
        far = median and not 1 / OUTLIER_FACTOR <= e.goal.value / median <= OUTLIER_FACTOR
        if (mine[1] >= lo and mine[0] <= hi) or not far:
            continue
        driver = e.goal.drivers[0]
        model = get_model(e.model_key)
        params = model.validate({k: p.value for k, p in e.params.items()})
        edge = hi if mine[0] > hi else lo
        seek = goal_seek(model, params, driver, e.goal.metric, edge, seed)
        out.append(Difference(instance=e.id, model_name=e.model_name, driver=driver, agrees_at=seek.value,
                              others_low=lo, others_high=hi))
    return out
