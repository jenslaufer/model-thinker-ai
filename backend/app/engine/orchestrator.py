"""Phases 4–9: parameterize, execute, compare, simulate, synthesize, decide.

Results of incompatible models are never averaged. The comparison lists each model's
own metrics side by side and reports directional agreement and contradiction on shared
claim dimensions.
"""

from __future__ import annotations

import hashlib
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Literal

from pydantic import BaseModel, model_validator

from app.llm.base import Provider
from app.llm.heuristic import HeuristicProvider
from app.modeling.base import ModelOutput, Recommendation, Statement, fmt
from app.modeling.registry import REGISTRY, get_model

from .goal import Difference, GoalAnalysis, GoalFrame, ModelChoice, analyse, differences
from .scenarios import MonteCarlo, Scenario, SensitivityItem, monte_carlo, scenario_set, sensitivity
from .selection import Selection, select_models
from .structure import ProblemInput, ProblemStructure

log = logging.getLogger(__name__)
UNCERTAINTY_WEIGHT = {"low": 1.0, "medium": 0.8, "high": 0.6}


Confidence = Literal["high", "medium", "low", "unknown"]


class ParamValue(BaseModel):
    value: Any
    origin: Literal["default_assumption", "user_input", "ai_estimate"]
    rationale: str = ""
    confidence: Confidence | None = None

    @model_validator(mode="before")
    @classmethod
    def _legacy_proposal(cls, data: Any) -> Any:
        # Revisions stored before 2026-11 call AI values "ai_proposal" and carry no confidence.
        if isinstance(data, dict) and data.get("origin") == "ai_proposal":
            data = {**data, "origin": "ai_estimate", "confidence": data.get("confidence") or "unknown"}
        return data


def parse_instance(entry: str) -> tuple[str, str]:
    """'markov' -> ('markov', 'markov'); 'withdrawal:fat-tails' -> ('withdrawal', 'withdrawal:fat-tails')."""
    key, sep, label = entry.partition(":")
    if not key or (sep and not label.strip()):
        raise ValueError(f"invalid model instance '{entry}'")
    return key, entry


class Execution(BaseModel):
    model_key: str
    instance: str = ""  # set when one analysis runs the same model more than once
    model_name: str
    model_version: str
    status: Literal["ok", "error"]
    error: str | None = None
    fit_score: int = 0
    params: dict[str, ParamValue] = {}
    assumptions: list[str] = []
    limits: list[str] = []
    output: ModelOutput | None = None
    scenarios: list[Scenario] = []
    sensitivity: list[SensitivityItem] | None = None
    monte_carlo: MonteCarlo | None = None
    uncertainty: dict[str, Any] = {}
    input_hash: str = ""
    goal: GoalAnalysis | None = None

    @property
    def id(self) -> str:
        return self.instance or self.model_key


class Contradiction(BaseModel):
    dimension: str
    positive: list[str]
    negative: list[str]
    explanation: str


class Comparison(BaseModel):
    table: list[dict[str, Any]]
    contradictions: list[Contradiction]
    convergences: list[dict[str, Any]]
    differences: list[Difference] = []  # goal results outside the other models' range, with their cause
    note: str = "Metrics of different models measure different things and are not combined into one number."


class PrioritizedRecommendation(Recommendation):
    id: str
    priority: float
    source_models: list[str]
    evidence: list[str]


class AnalysisResult(BaseModel):
    problem: ProblemInput
    structure: ProblemStructure
    selection: Selection
    executions: list[Execution]
    comparison: Comparison
    synthesis: list[Statement]
    recommendations: list[PrioritizedRecommendation]
    band: float
    seed: int
    provider: str


class Setup(BaseModel):
    """A recorded AI setup. Reruns reuse it so results change only when the user changes something."""
    structure: ProblemStructure | None = None
    frame: GoalFrame | None = None
    choices: list[ModelChoice] = []
    uncovered: list[str] = []
    estimates: dict[str, dict[str, dict[str, Any]]] = {}  # instance -> param -> {value, rationale, confidence}

    @classmethod
    def from_result(cls, r: AnalysisResult) -> Setup:
        est = {e.id: {n: {"value": p.value, "rationale": p.rationale, "confidence": p.confidence}
                      for n, p in e.params.items() if p.origin == "ai_estimate"} for e in r.executions}
        return cls(structure=r.structure, frame=r.selection.frame, choices=r.selection.choices,
                   uncovered=r.selection.uncovered, estimates=est)


def _show(v: Any) -> str:
    return fmt(v) if isinstance(v, float) else str(v)


def _hash(obj: Any) -> str:
    return hashlib.sha256(repr(obj).encode()).hexdigest()[:16]


def execute_model(instance: str, overrides: dict | None, proposals: dict | None, fit: int, band: float, seed: int,
                  what_if: dict | None = None) -> Execution:
    key, instance = parse_instance(instance)
    instance = "" if instance == key else instance
    model = get_model(key)
    spec = model.spec
    overrides, proposals = overrides or {}, proposals or {}
    rejected = {n: v["rationale"] for n, v in proposals.items() if v.get("rejected")}
    proposals = {n: v for n, v in proposals.items() if not v.get("rejected")}
    try:
        params = model.validate({**{k: v["value"] for k, v in proposals.items()}, **overrides})
        origins = {
            n: ParamValue(value=v, origin="user_input" if n in overrides else
                          "ai_estimate" if n in proposals else "default_assumption",
                          rationale="" if n in overrides else proposals.get(n, {}).get("rationale", rejected.get(n, "")),
                          confidence=proposals.get(n, {}).get("confidence") if n in proposals and n not in overrides
                          else None)
            for n, v in params.items()}
        out = model.run(params, seed)
        sens = sensitivity(model, params, band, seed)
        mc = monte_carlo(model, params, band, seed=seed)
        scen = scenario_set(model, params, band, what_if=what_if, seed=seed)
    except Exception as e:  # noqa: BLE001 — one failing model must not break the analysis
        return Execution(model_key=key, instance=instance, model_name=spec.name, model_version=spec.version, status="error",
                         error=f"{type(e).__name__}: {e}", fit_score=fit, assumptions=spec.assumptions, limits=spec.limits)
    pm = spec.primary_metric
    s = mc.summary.get(pm or "", {})
    width = (s["p95"] - s["p05"]) / abs(s["p50"]) if s and s["p50"] else None
    user_share = sum(p.origin == "user_input" for p in origins.values()) / max(1, len(origins))
    return Execution(
        model_key=key, instance=instance, model_name=spec.name, model_version=spec.version, status="ok", fit_score=fit,
        params=origins,
        assumptions=spec.assumptions, limits=spec.limits, output=out, scenarios=scen, sensitivity=sens, monte_carlo=mc,
        uncertainty={"primary_metric": pm, "interval_p05_p95": [s.get("p05"), s.get("p95")] if s else None,
                     "relative_interval_width": width, "share_params_from_user": round(user_share, 2),
                     "most_sensitive": sens[0].param if sens else None, "warnings": len(out.warnings),
                     "empirically_validated": False},
        input_hash=_hash((key, spec.version, params, seed, band)),
    )


def goal_metric_for(e: Execution, frame: GoalFrame | None, chosen: dict[str, str | None]) -> str | None:
    """The metric that measures the user's goal quantity: the AI's choice, else the model's first declared one."""
    if e.status != "ok" or frame is None or frame.kind == "explain":
        return None
    spec = get_model(e.model_key).spec
    allowed = spec.risk_metrics if frame.kind == "maximise_under_risk" else spec.goal_metrics
    if e.id in chosen:
        return chosen[e.id] if chosen[e.id] in allowed else None
    return next(iter(allowed), None)


def with_goal(e: Execution, frame: GoalFrame | None, chosen: dict, band: float, seed: int) -> Execution:
    gm = goal_metric_for(e, frame, chosen)
    if not gm:
        return e
    try:
        return e.model_copy(update={"goal": analyse(e, frame, gm, band, seed)})
    except Exception:
        log.exception("goal analysis failed for %s", e.id)
        return e


def compare(executions: list[Execution]) -> Comparison:
    ok = [e for e in executions if e.status == "ok"]
    table, by_dim = [], {}
    for e in ok:
        pm = e.output and e.model_key and get_model(e.model_key).spec.primary_metric
        s = e.monte_carlo.summary.get(pm, {}) if e.monte_carlo and pm else {}
        table.append({"model": e.model_name, "key": e.model_key, "primary_metric": pm,
                      "value": e.output.metrics.get(pm) if pm else None, "p05": s.get("p05"), "p95": s.get("p95"),
                      "most_sensitive": e.uncertainty.get("most_sensitive"),
                      "claims": [c.statement for c in e.output.claims]})
        for c in e.output.claims:
            by_dim.setdefault(c.dimension, []).append((e.model_name, c))
    contradictions, convergences = [], []
    for dim, claims in by_dim.items():
        pos = [f"{m}: {c.statement}" for m, c in claims if c.direction > 0]
        neg = [f"{m}: {c.statement}" for m, c in claims if c.direction < 0]
        if pos and neg:
            contradictions.append(Contradiction(
                dimension=dim, positive=pos, negative=neg,
                explanation="Models rest on different assumptions about mechanism and parameters. "
                            "Check which assumptions match reality instead of averaging."))
        elif len(pos) >= 2 or len(neg) >= 2:
            convergences.append({"dimension": dim, "direction": 1 if pos else -1, "models": pos or neg})
    return Comparison(table=table, contradictions=contradictions, convergences=convergences)


def synthesize(structure: ProblemStructure, executions: list[Execution], comp: Comparison) -> list[Statement]:
    out = []
    ok = [e for e in executions if e.status == "ok"]
    out.append(Statement(text=f"{len(ok)} of {len(executions)} selected models executed from "
                              f"{len({get_model(e.model_key).spec.perspective for e in ok})} distinct perspectives."))
    for c in comp.convergences:
        out.append(Statement(text=f"{len(c['models'])} models agree on '{c['dimension']}' "
                                  f"({'favourable/high' if c['direction'] > 0 else 'unfavourable/low'})."))
    for c in comp.contradictions:
        out.append(Statement(text=f"Disagreement on '{c.dimension}': {len(c.positive)} model(s) positive, "
                                  f"{len(c.negative)} negative — resolve with data, do not average."))
    sens = [(e.model_name, e.sensitivity[0]) for e in ok if e.sensitivity]
    if sens:
        out.append(Statement(text="Most influential assumptions: " +
                                  "; ".join(f"{s.param} ({m})" for m, s in sens[:5]) + "."))
    if ok and all(e.uncertainty.get("share_params_from_user", 0) == 0 for e in ok):
        out.append(Statement(text="No user data entered into any model: all parameters are default assumptions. "
                                  "Treat results as structured scenarios, not forecasts."))
    return out


def prioritize(executions: list[Execution], comp: Comparison, structure: ProblemStructure) -> list[PrioritizedRecommendation]:
    recs = []
    for e in executions:
        if e.status != "ok":
            continue
        pm = get_model(e.model_key).spec.primary_metric
        for i, r in enumerate(e.output.recommendations):
            evidence = [f"{e.model_name}: {pm} = {_show(e.output.metrics.get(pm))}"] if pm else []
            if e.uncertainty.get("interval_p05_p95"):
                lo, hi = e.uncertainty["interval_p05_p95"]
                evidence.append(f"assumption-uncertainty interval p05–p95: {fmt(lo)} – {fmt(hi)}")
            recs.append(PrioritizedRecommendation(
                **r.model_dump(), id=f"{e.model_key}-{i}", source_models=[e.model_key], evidence=evidence,
                priority=round(e.fit_score * UNCERTAINTY_WEIGHT[r.uncertainty], 1)))
    for c in comp.contradictions:
        recs.append(PrioritizedRecommendation(
            id=f"resolve-{c.dimension}", title=f"Resolve model disagreement on '{c.dimension}'",
            rationale="Models with different assumptions point in opposite directions.",
            expected_impact="Prevents acting on the wrong mechanism.", prerequisites=["Access to outcome data"],
            risks=["Delay while collecting data"], uncertainty="high", horizon="short",
            actions=["List the assumption that drives each side", "Collect the data that discriminates between them"],
            priority=55.0, source_models=[], evidence=c.positive + c.negative))
    for g in structure.data_gaps:
        recs.append(PrioritizedRecommendation(
            id=f"gap-{_hash(g)[:6]}", title="Close data gap", rationale=g, expected_impact="Turns assumptions into "
            "estimates and narrows uncertainty.", uncertainty="low", horizon="short",
            actions=["Collect the missing data", "Re-run the analysis"], priority=40.0, source_models=[], evidence=[g]))
    return sorted(recs, key=lambda r: -r.priority)


def run_analysis(inp: ProblemInput, selected: list[str] | None = None, overrides: dict[str, dict] | None = None,
                 what_if: dict[str, dict] | None = None, band: float = 0.2, seed: int = 42,
                 provider: Provider | None = None, setup: Setup | None = None) -> AnalysisResult:
    provider = provider or HeuristicProvider()
    structure = setup.structure if setup and setup.structure else provider.structure(inp)
    selection = select_models(structure)
    if setup:
        selection.frame, choices, selection.uncovered = setup.frame, setup.choices, setup.uncovered
    else:
        selection.frame = provider.frame(inp, structure)
        choices, selection.uncovered = provider.choose(structure, selection.frame, REGISTRY.specs())
    if setup and selected:
        selection.choices = [c for c in choices if c.instance in selected]
    if choices and not selected:
        selection.choices, selection.selected = choices, [c.instance for c in choices]
    ids = selected or selection.selected
    fit = {f.key: f.score for f in selection.fits}
    overrides, what_if = overrides or {}, what_if or {}
    key = lambda i: parse_instance(i)[0]
    proposals = {i: setup.estimates.get(i, {}) if setup else
                 provider.parameterize(structure, get_model(key(i)).spec, selection.frame) for i in ids}
    chosen = {c.instance: c.goal_metric for c in selection.choices}

    def run(i: str) -> Execution:
        e = execute_model(i, overrides.get(i), proposals[i], fit.get(key(i), 0), band, seed, what_if.get(i))
        return with_goal(e, selection.frame, chosen, band, seed)

    with ThreadPoolExecutor(max_workers=4) as pool:
        executions = list(pool.map(run, ids))
    comp = compare(executions)
    comp.differences = differences(executions, seed)
    synthesis = synthesize(structure, executions, comp) + provider.narrate(structure, executions)
    return AnalysisResult(problem=inp, structure=structure, selection=selection, executions=executions,
                          comparison=comp, synthesis=synthesis,
                          recommendations=prioritize(executions, comp, structure), band=band, seed=seed,
                          provider=provider.name)
