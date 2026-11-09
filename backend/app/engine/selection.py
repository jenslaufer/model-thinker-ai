"""Phase 3 (SELECT): Model Fit Score.

The score (0–100) is a transparent internal heuristic, not a validated probability.
Components: problem-type match (40), actors (10), time dynamics (15), data (15),
uncertainty (10), interactions/decision relevance (10).
"""

from __future__ import annotations

import math

from pydantic import BaseModel

from app.modeling.base import ModelSpec
from app.modeling.registry import REGISTRY

from .goal import GoalFrame, ModelChoice
from .structure import ProblemStructure

MIN_SCORE = 30
MAX_SELECTED = 5
SAME_PERSPECTIVE_PENALTY = 15


class ModelFit(BaseModel):
    key: str
    name: str
    number: int
    implemented: bool
    perspective: str
    score: int
    components: dict[str, float]
    reasons: list[str]
    blockers: list[str] = []
    missing_data: list[str] = []


class Selection(BaseModel):
    fits: list[ModelFit]
    selected: list[str]
    complementary: list[str]  # why the set works together
    unsuitable: list[dict]
    frame: GoalFrame | None = None
    choices: list[ModelChoice] = []
    uncovered: list[str] = []  # angles no implemented model covers
    note: str = "Model Fit Score is a transparent heuristic (0–100), not a statistically validated probability."


def score_model(spec: ModelSpec, s: ProblemStructure) -> ModelFit:
    c, reasons, blockers, missing = {}, [], [], []
    matches = {t: s.problem_types[t] * w for t, w in spec.tags.items() if t in s.problem_types}
    raw = sum(matches.values())
    c["problem_type"] = round(40 * (1 - math.exp(-raw)), 1)
    if matches:
        top = sorted(matches, key=matches.get, reverse=True)[:3]
        reasons.append(f"Matches problem aspects: {', '.join(top)}")
    else:
        reasons.append("No direct match with detected problem aspects")

    n_act = len(s.actors)
    if spec.min_actors <= max(n_act, 1):
        c["actors"] = 10.0
    elif n_act == 0 and spec.min_actors <= 2:
        c["actors"] = 5.0
        reasons.append("Needs interacting actors — none named, generic players assumed")
    else:
        c["actors"] = 0.0
        blockers.append(f"Requires ≥ {spec.min_actors} actors, {n_act} named")

    temporal = s.criteria["temporal_dynamics"]
    if spec.needs_time is None:
        c["temporal_dynamics"] = 10.0
    elif spec.needs_time:
        c["temporal_dynamics"] = round(15 * temporal, 1)
        reasons.append("Dynamic model" + (" — fits the time horizon" if temporal >= 0.5 else " — problem looks static"))
    else:
        c["temporal_dynamics"] = round(15 * (1 - 0.6 * temporal), 1)

    data = s.criteria["data_availability"]
    need = {"low": 0.0, "medium": 0.4, "high": 0.7}[spec.data_need]
    c["data_availability"] = 15.0 if data >= need else round(15 * data / need * 0.4, 1)
    if data < need:
        missing += spec.prerequisites or [f"{spec.name} needs {spec.data_need} data availability"]
        reasons.append(f"Data need '{spec.data_need}' exceeds available data")

    unc = s.criteria["uncertainty"]
    c["uncertainty"] = round(10 * unc, 1) if spec.perspective in ("stochastic", "statistical", "learning") else 5.0
    inter = max(s.criteria["interactions"], s.criteria["decision_relevance"] * 0.5)
    c["interactions"] = round(10 * inter, 1) if spec.perspective in ("strategic", "social", "structural") else 5.0

    score = round(min(100, sum(c.values())))
    if blockers:
        score = min(score, MIN_SCORE - 1)
    if not spec.implemented:
        reasons.append("Not implemented yet — cannot be executed")
    return ModelFit(key=spec.key, name=spec.name, number=spec.number, implemented=spec.implemented,
                    perspective=spec.perspective, score=score, components=c, reasons=reasons, blockers=blockers,
                    missing_data=missing)


def select_models(s: ProblemStructure, max_selected: int = MAX_SELECTED) -> Selection:
    fits = sorted((score_model(spec, s) for spec in REGISTRY.specs()), key=lambda f: -f.score)
    pool = [f for f in fits if f.implemented and not f.blockers and f.score >= MIN_SCORE]
    selected: list[ModelFit] = []
    while pool and len(selected) < max_selected:
        used = [f.perspective for f in selected]
        best = max(pool, key=lambda f: f.score - SAME_PERSPECTIVE_PENALTY * used.count(f.perspective))
        selected.append(best)
        pool.remove(best)
    if len(selected) < 3:  # ensure a multi-model view even for vague problems
        rest = [f for f in fits if f.implemented and not f.blockers and f not in selected]
        selected += rest[: 3 - len(selected)]
    complementary = [f"{f.name}: {f.perspective} perspective" for f in selected]
    unsuitable = [{"key": f.key, "name": f.name, "score": f.score,
                   "why": f.blockers or (["Not implemented yet"] if not f.implemented else ["Low fit with this problem"])}
                  for f in fits if f not in selected and (f.score < MIN_SCORE or f.blockers or not f.implemented)]
    return Selection(fits=fits, selected=[f.key for f in selected], complementary=complementary, unsuitable=unsuitable)
