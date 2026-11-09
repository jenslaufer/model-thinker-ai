"""Question-first answer for non-experts.

Built from a stored AnalysisResult at read time, so older revisions get it too. It only rephrases computed
results (model outputs, goal analysis, differences) and states how much of the input was the user's own data.
"""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel

from app.modeling.base import fmt, rough
from app.modeling.plain import PLAIN, plain_text
from app.modeling.registry import get_model

from .goal import GoalFrame, ModelChoice
from .orchestrator import AnalysisResult, Execution

log = logging.getLogger(__name__)

RELIABILITY = {
    "illustrative": ("The AI setup was not available, so every model ran on built-in example values. The results "
                     "show how each model behaves — not your situation. Enter your own numbers in the Scenario Lab "
                     "to make them yours."),
    "estimated": ("Most inputs are AI estimates based on typical values. Check the marked ones — the answer names "
                  "the estimates it depends on most."),
    "rough": ("Some inputs are yours, the rest are estimates or example values. Read the results as a rough guide "
              "and check which numbers each finding rests on."),
    "grounded": ("Most inputs are your own numbers. The results still rest on each model's simplifications, "
                 "listed under the model's limits."),
}


class Finding(BaseModel):
    model_key: str
    instance: str  # execution id: model key, or "key:label" when a model runs more than once
    model_name: str
    question: str
    text: str
    fit: int
    data_source: Literal["example values", "AI estimates", "partly your numbers", "your numbers"]


class Verdict(BaseModel):
    status: Literal["likely", "unlikely", "unclear", "solved", "no_target", "no_goal_metric"]
    text: str


class GoalResult(BaseModel):
    instance: str
    model_name: str
    measures: str
    value: float
    p05: float | None
    p95: float | None


class Unknown(BaseModel):
    instance: str
    model_name: str
    label: str
    value_text: str
    origin: str
    confidence: str | None
    rationale: str
    effect_text: str


class EstimateRow(BaseModel):
    instance: str
    model_name: str
    param: str
    param_label: str
    value_text: str
    origin: str
    confidence: str | None
    rationale: str


class Setup(BaseModel):
    choices: list[ModelChoice]
    uncovered: list[str]
    estimates: list[EstimateRow]


class Answer(BaseModel):
    question: str
    frame: GoalFrame | None
    reliability: Literal["grounded", "estimated", "rough", "illustrative"]
    reliability_text: str
    verdict: Verdict
    goal_results: list[GoalResult]
    differences: list[str]
    unknowns: list[Unknown]
    what_it_takes: list[str]
    other_angles: list[Finding]
    plain: dict[str, str]  # instance -> plain sentence, for every model card
    setup: Setup


def _counts(executions: list[Execution]) -> tuple[int, int, int]:
    params = [p for e in executions for p in e.params.values()]
    return (sum(p.origin == "user_input" for p in params), sum(p.origin == "ai_estimate" for p in params),
            len(params))


def _source(e: Execution) -> str:
    own, est, total = _counts([e])
    if own:
        return "your numbers" if own == total else "partly your numbers"
    return "AI estimates" if est else "example values"


def _reliability(executions: list[Execution]) -> str:
    own, est, total = _counts(executions)
    if own and own * 2 >= total:
        return "grounded"
    if est and est * 2 >= total - own:
        return "estimated"
    return "rough" if own or est else "illustrative"


def _finding(e: Execution) -> Finding | None:
    try:
        text = plain_text(e.model_key, {k: p.value for k, p in e.params.items()}, e.output.metrics)
    except (KeyError, TypeError, ValueError, IndexError):
        # Read-time summary of stored results: a revision with an older metric set must not break the page.
        log.exception("plain text failed for %s", e.id)
        return None
    return Finding(model_key=e.model_key, instance=e.id, model_name=e.model_name,
                   question=PLAIN[e.model_key].question, text=text, fit=e.fit_score, data_source=_source(e))


def _value(v) -> str:
    if isinstance(v, (bool, str)):
        return str(v)
    if isinstance(v, (int, float)):
        return fmt(float(v))
    if isinstance(v, list):
        return "[" + ", ".join(_value(x) for x in v) + "]"
    return str(v)


def _label(e: Execution, param: str) -> str:
    return next((p.label for p in get_model(e.model_key).spec.params if p.name == param), param)


def _results(goal: list[Execution]) -> list[GoalResult]:
    return [GoalResult(instance=e.id, model_name=e.model_name, value=e.goal.value, p05=e.goal.p05, p95=e.goal.p95,
                       measures=get_model(e.model_key).spec.goal_metrics.get(e.goal.metric, e.goal.metric))
            for e in goal]


def _verdict(frame: GoalFrame | None, goal: list[Execution], outliers: set[str]) -> Verdict:
    if frame is None:
        return Verdict(status="no_goal_metric",
                       text="This analysis has no goal to check. Below is what each model shows.")
    q = frame.quantity or "the goal quantity"
    if frame.kind == "maximise_under_risk":
        if not goal:
            return Verdict(status="no_goal_metric",
                           text=f"None of the chosen models measures the risk of {q}, so the risk limit cannot be "
                                "checked. Below is what each model shows.")
        return _risk_verdict(frame, goal)
    if frame.target is None:
        return Verdict(status="no_target", text="No target was given, so there is no yes/no answer. Below is what "
                                                "each model shows and what drives it.")
    if not goal:
        return Verdict(status="no_goal_metric",
                       text=f"None of the models measures {q}, so there is no yes/no answer. Below is what each "
                            "model shows.")
    t = frame.target
    # Models whose result is explained as an outlier are named, not counted: the verdict rests on the rest.
    named = [e.model_name for e in goal if e.id in outliers]
    rest = [e for e in goal if e.id not in outliers]
    total = len(goal)
    if named and len(rest) * 2 > total:
        goal = rest
    else:
        named = []
    note = f" {', '.join(named)} differ{'s' if len(named) == 1 else ''} — see why below." if named else ""
    who = f"{len(goal)} of {total} models that measure {q}" if named else f"every model that measures {q}"
    lows = [e.goal.p05 if e.goal.p05 is not None else e.goal.value for e in goal]
    highs = [e.goal.p95 if e.goal.p95 is not None else e.goal.value for e in goal]
    above = frame.direction == "at_least"
    reach = all(lo >= t for lo in lows) if above else all(hi <= t for hi in highs)
    miss = all(hi < t for hi in highs) if above else all(lo > t for lo in lows)
    span = f"{rough(min(lows))}–{rough(max(highs))}"
    if reach:
        word = "reaches at least" if above else "stays at or below"
        return Verdict(status="likely",
                       text=f"Probably yes: {who} {word} {fmt(t)} "
                            f"(results {span}).{note}")
    if miss:
        miss = f"{who} stay below" if named else f"no model that measures {q} reaches"
        return Verdict(status="unlikely",
                       text=f"Probably not: {miss} {fmt(t)} (results {span}).{note}")
    return Verdict(status="unclear", text=f"Unclear: the models disagree on whether {q} reaches {fmt(t)} "
                                          f"(results {span}). See why below.")


def _risk_verdict(frame: GoalFrame, goal: list[Execution]) -> Verdict:
    lines = []
    for limit in frame.risk_limits:
        for e in goal:
            solved = [s for s in e.goal.seeks if s.target == limit and s.status == "solved"]
            if solved:
                vals = [s.value for s in solved]
                rng = rough(vals[0]) if len(vals) == 1 else f"{rough(min(vals))}–{rough(max(vals))}"
                lines.append(f"At {limit:.0%} risk, {e.model_name}: {solved[0].label} up to {rng}.")
    if not lines:
        return Verdict(status="unclear", text="No model found a value within reach that meets your risk limit.")
    return Verdict(status="solved", text=" ".join(lines))


def _difference(d) -> str:
    text = f"{d.model_name} differs from the others because it assumes {d.driver.label} = {fmt(d.driver.value)}"
    if d.agrees_at is None:
        return text + "; no value within reach brings it into their range."
    return text + (f"; at {rough(d.agrees_at)} it lands in their range ({rough(d.others_low)}–{rough(d.others_high)}). "
                   "Better data on this value settles it — don't pick the convenient model.")


def _unknowns(goal: list[Execution], ok: list[Execution]) -> list[Unknown]:
    if goal:
        items = sorted(((e, d) for e in goal for d in e.goal.drivers), key=lambda x: -x[1].swing)[:3]
        return [Unknown(instance=e.id, model_name=e.model_name, label=d.label, value_text=fmt(d.value),
                        origin=d.origin, confidence=d.confidence, rationale=d.rationale,
                        effect_text=f"moves the result between {rough(d.metric_low)} and {rough(d.metric_high)}")
                for e, d in items]
    out = []
    for e in ok:  # no goal: the most influential non-user value of each model
        if not e.sensitivity:
            continue
        top = max(e.sensitivity, key=lambda i: i.swing)
        p = e.params.get(top.param)
        if p is None or p.origin == "user_input":
            continue
        out.append(Unknown(instance=e.id, model_name=e.model_name, label=_label(e, top.param),
                           value_text=_value(p.value), origin=p.origin, confidence=p.confidence,
                           rationale=p.rationale,
                           effect_text=f"moves the result between {rough(top.metric_low)} and "
                                       f"{rough(top.metric_high)}"))
    return out


def _what_it_takes(goal: list[Execution], frame: GoalFrame | None) -> list[str]:
    if frame is None or frame.kind != "reach_target" or frame.target is None:
        return []
    above = frame.direction == "at_least"
    missing = [e for e in goal if (e.goal.value < frame.target if above else e.goal.value > frame.target)]
    return [f"{e.model_name}: {s.label} from {fmt(s.current)} to {rough(s.value)}"
            for e in missing for s in e.goal.seeks if s.status == "solved"]


def _setup(r: AnalysisResult, ok: list[Execution]) -> Setup:
    rows = [EstimateRow(instance=e.id, model_name=e.model_name, param=n, param_label=_label(e, n),
                        value_text=_value(p.value), origin=p.origin, confidence=p.confidence, rationale=p.rationale)
            for e in ok for n, p in e.params.items() if p.origin != "user_input"]
    return Setup(choices=r.selection.choices, uncovered=r.selection.uncovered, estimates=rows)


def build_answer(r: AnalysisResult) -> Answer:
    ok = [e for e in r.executions if e.status == "ok" and e.output and e.model_key in PLAIN]
    goal = [e for e in ok if e.goal and e.goal.value is not None]
    every = {e.id: f for e in ok if (f := _finding(e))}
    goal_ids = {e.id for e in goal}
    findings = sorted((f for i, f in every.items() if i not in goal_ids), key=lambda f: -f.fit)
    reliability = _reliability(ok)
    frame = r.selection.frame
    return Answer(
        question=r.problem.objective.strip() or r.structure.objective, frame=frame,
        reliability=reliability, reliability_text=RELIABILITY[reliability], verdict=_verdict(frame, goal, {d.instance for d in r.comparison.differences}),
        goal_results=_results(goal), differences=[_difference(d) for d in r.comparison.differences],
        unknowns=_unknowns(goal, ok), what_it_takes=_what_it_takes(goal, frame), other_angles=findings,
        plain={i: f.text for i, f in every.items()}, setup=_setup(r, ok))
