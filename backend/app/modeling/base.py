"""Core contracts every mathematical model implements.

The AI layer may select and parameterize models; it never produces numbers.
All numbers in a ModelOutput come from `Model.compute`.
"""

from __future__ import annotations

import copy
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, Field

ParamType = Literal["float", "int", "bool", "choice", "vector", "matrix", "labels"]
Origin = Literal["computed", "assumption", "rule_interpretation", "ai_interpretation", "user_input"]


class ParamSpec(BaseModel):
    name: str
    label: str
    type: ParamType = "float"
    default: Any
    min: float | None = None
    max: float | None = None
    choices: list[str] | None = None
    unit: str = ""
    description: str = ""
    # Uncertain scalar params enter sensitivity analysis, scenarios and Monte Carlo.
    uncertain: bool = False
    # Matrix whose rows sum to 1 (transition probabilities); its off-diagonal entries can be goal drivers.
    stochastic_rows: bool = False


class Series(BaseModel):
    name: str
    x: list[float | str]
    y: list[float]
    kind: Literal["line", "bar", "area", "scatter"] = "line"
    x_label: str = ""
    y_label: str = ""


class Claim(BaseModel):
    """A directional statement on a shared dimension, used to detect contradictions.

    direction: +1 favourable/high, -1 unfavourable/low, 0 neutral.
    """

    dimension: Literal["outcome_trend", "risk_level", "leverage", "predictability", "concentration", "cooperation"]
    direction: int = Field(ge=-1, le=1)
    statement: str


class Statement(BaseModel):
    text: str
    origin: Origin = "rule_interpretation"


class Recommendation(BaseModel):
    title: str
    rationale: str
    expected_impact: str
    prerequisites: list[str] = []
    risks: list[str] = []
    uncertainty: Literal["low", "medium", "high"] = "medium"
    horizon: Literal["short", "medium", "long"] = "medium"
    actions: list[str] = []
    origin: Origin = "rule_interpretation"


class ModelOutput(BaseModel):
    metrics: dict[str, float | int | str | bool | None]
    series: list[Series] = []
    tables: dict[str, list[dict[str, Any]]] = {}
    claims: list[Claim] = []
    interpretation: list[Statement] = []
    recommendations: list[Recommendation] = []
    warnings: list[str] = []
    log: list[str] = []  # calculation protocol


class ModelSpec(BaseModel):
    key: str
    number: int
    name: str
    family: Literal["A", "B", "C"]
    version: str = "1.0.0"
    implemented: bool = True
    summary: str
    description: str = ""
    math: str = ""
    assumptions: list[str] = []
    prerequisites: list[str] = []
    limits: list[str] = []
    examples: list[str] = []
    use_cases: list[str] = []
    params: list[ParamSpec] = []
    primary_metric: str | None = None
    primary_goal: Literal["maximize", "minimize"] = "maximize"
    # Metrics that measure a user's goal quantity (metric -> what it measures), and params a goal seek may move.
    goal_metrics: dict[str, str] = {}
    levers: list[str] = []
    # Metrics that are probabilities of a bad outcome (0..1); only these can answer "at most p risk".
    risk_metrics: dict[str, str] = {}
    # Selection profile: problem tags this model addresses (weight 0..1).
    tags: dict[str, float] = {}
    min_actors: int = 0
    needs_time: bool | None = None  # True: dynamic, False: static, None: either
    data_need: Literal["low", "medium", "high"] = "low"
    perspective: str = ""
    mc_draws: int = 500  # Monte Carlo draws; lower for expensive simulations
    mc_params: dict = {}  # cheaper inner-simulation settings used during Monte Carlo only


class ParamError(ValueError):
    pass


class Model:
    spec: ModelSpec

    def validate(self, params: dict[str, Any] | None) -> dict[str, Any]:
        """Merge with defaults, coerce types, enforce bounds. Unknown keys are rejected."""
        params = dict(params or {})
        known = {p.name: p for p in self.spec.params}
        unknown = set(params) - set(known)
        if unknown:
            raise ParamError(f"unknown parameters: {sorted(unknown)}")
        out: dict[str, Any] = {}
        for p in self.spec.params:
            value = params.get(p.name, copy.deepcopy(p.default))
            out[p.name] = _coerce(p, value)
        self.check(out)
        return out

    def check(self, params: dict[str, Any]) -> None:
        """Cross-parameter validation hook."""

    def run(self, params: dict[str, Any] | None = None, seed: int = 42) -> ModelOutput:
        clean = self.validate(params)
        out = self.compute(clean, np.random.default_rng(seed))
        out.log.insert(0, f"{self.spec.name} v{self.spec.version}, seed={seed}, params={_short(clean)}")
        return out

    def compute(self, p: dict[str, Any], rng: np.random.Generator) -> ModelOutput:
        raise NotImplementedError

    def perturb(self, p: dict[str, Any], rng: np.random.Generator, band: float) -> dict[str, Any]:
        """Random draw around p for Monte Carlo. Default: triangular noise on uncertain scalars."""
        q = dict(p)
        for spec in self.spec.params:
            if spec.uncertain and spec.type in ("float", "int"):
                base = p[spec.name]
                lo, hi = _band(spec, base, band)
                value = rng.triangular(lo, base, hi) if hi > lo else base
                q[spec.name] = _coerce(spec, round(value) if spec.type == "int" else value)
        return q


def _band(spec: ParamSpec, base: float, band: float) -> tuple[float, float]:
    width = abs(base) * band if base != 0 else band
    lo, hi = base - width, base + width
    if spec.min is not None:
        lo = max(lo, spec.min)
    if spec.max is not None:
        hi = min(hi, spec.max)
    return lo, hi


def bounds(spec: ParamSpec, base: float, band: float) -> tuple[float, float]:
    return _band(spec, base, band)


def _coerce(p: ParamSpec, value: Any) -> Any:
    try:
        if p.type == "float":
            v = float(value)
        elif p.type == "int":
            v = round(float(value))
        elif p.type == "bool":
            return bool(value)
        elif p.type == "choice":
            if value not in (p.choices or []):
                raise ParamError(f"{p.name}: '{value}' not in {p.choices}")
            return value
        elif p.type == "labels":
            return [str(x) for x in value]
        elif p.type == "vector":
            arr = [float(x) for x in value]
            _bound_all(p, arr)
            return arr
        elif p.type == "matrix":
            m = [[float(x) for x in row] for row in value]
            if len({len(r) for r in m}) > 1:
                raise ParamError(f"{p.name}: rows differ in length")
            _bound_all(p, [x for r in m for x in r])
            return m
    except (TypeError, ValueError) as e:
        if isinstance(e, ParamError):
            raise
        raise ParamError(f"{p.name}: invalid value {value!r}") from e
    if not np.isfinite(v):
        raise ParamError(f"{p.name}: must be finite")
    _bound_all(p, [v])
    return v


def _bound_all(p: ParamSpec, values: list[float]) -> None:
    for v in values:
        if p.min is not None and v < p.min:
            raise ParamError(f"{p.name}: {v} < min {p.min}")
        if p.max is not None and v > p.max:
            raise ParamError(f"{p.name}: {v} > max {p.max}")


def _short(params: dict[str, Any]) -> str:
    s = str(params)
    return s if len(s) < 300 else s[:297] + "..."


def fmt(x: float) -> str:
    """Human number format: no false precision."""
    if abs(x) >= 1000:
        return f"{x:,.0f}"
    if abs(x) >= 1:
        return f"{x:.2f}".rstrip("0").rstrip(".")
    return f"{x:.3g}"


def rough(x: float) -> str:
    """Two significant figures, for results that rest on estimates (220, 38,000, 0.034)."""
    return fmt(float(f"{x:.2g}")) if x else "0"
