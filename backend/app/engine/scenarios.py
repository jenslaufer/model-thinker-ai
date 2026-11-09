"""Phase 7 (SIMULATE): scenarios, one-at-a-time sensitivity and Monte Carlo.

Uncertainty bands are ±band around the current assumptions — they express assumption
uncertainty, not an empirically estimated distribution.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel

from app.modeling.base import Model, ModelOutput, bounds

ScenarioKind = Literal["baseline", "best", "worst", "alternative", "stress", "what_if"]
BAND_NOTE = ("Draws vary uncertain assumptions within ±{band:.0%} (triangular). Intervals express assumption "
             "uncertainty, not empirical confidence.")


class SensitivityItem(BaseModel):
    param: str
    low_value: float
    high_value: float
    metric_low: float
    metric_high: float
    swing: float


class Scenario(BaseModel):
    kind: ScenarioKind
    name: str
    description: str
    params: dict[str, Any]
    metrics: dict[str, Any]
    primary: float | None


class MonteCarlo(BaseModel):
    draws: int
    band: float
    summary: dict[str, dict[str, float]]
    categorical: dict[str, dict[str, Any]]
    histogram: dict[str, list[float]]
    note: str


def _primary(model: Model, out: ModelOutput) -> float | None:
    v = out.metrics.get(model.spec.primary_metric) if model.spec.primary_metric else None
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _uncertain(model: Model):
    return [p for p in model.spec.params if p.uncertain and p.type in ("float", "int")]


def sensitivity(model: Model, params: dict, band: float = 0.2, seed: int = 42) -> list[SensitivityItem]:
    items = []
    for spec in _uncertain(model):
        lo, hi = bounds(spec, params[spec.name], band)
        if hi <= lo:
            continue
        m_lo = _primary(model, model.run(params | {spec.name: lo}, seed))
        m_hi = _primary(model, model.run(params | {spec.name: hi}, seed))
        if m_lo is None or m_hi is None:
            continue
        items.append(SensitivityItem(param=spec.name, low_value=lo, high_value=hi, metric_low=m_lo, metric_high=m_hi,
                                     swing=abs(m_hi - m_lo)))
    return sorted(items, key=lambda i: -i.swing)


def _run_scenario(model, kind, name, desc, params, seed) -> Scenario:
    out = model.run(params, seed)
    return Scenario(kind=kind, name=name, description=desc, params=model.validate(params), metrics=out.metrics,
                    primary=_primary(model, out))


def _corner(model, params, tornado, band, favourable: bool):
    maximize = model.spec.primary_goal == "maximize"
    q = dict(params)
    for item in tornado:
        lo, hi = bounds(next(p for p in model.spec.params if p.name == item.param), params[item.param], band)
        high_better = (item.metric_high > item.metric_low) == maximize
        q[item.param] = hi if high_better == favourable else lo
    return q


def scenario_set(model: Model, params: dict, band: float = 0.2, what_if: dict | None = None,
                 seed: int = 42) -> list[Scenario]:
    goal = model.spec.primary_goal
    out = [_run_scenario(model, "baseline", "Baseline", "Current assumptions.", params, seed)]
    tornado = sensitivity(model, params, band, seed)
    if tornado:
        best = _corner(model, params, tornado, band, True)
        worst = _corner(model, params, tornado, band, False)
        stress = _corner(model, params, tornado, min(0.9, band * 2), False)
        lever = tornado[0].param
        alt = params | {lever: _corner(model, params, tornado[:1], band, True)[lever]}
        out += [
            _run_scenario(model, "best", "Best case", f"All uncertain assumptions ±{band:.0%} in the favourable "
                          f"direction ({goal} {model.spec.primary_metric}).", best, seed),
            _run_scenario(model, "worst", "Worst case", f"All uncertain assumptions ±{band:.0%} in the unfavourable "
                          "direction.", worst, seed),
            _run_scenario(model, "alternative", "Single lever", f"Only the most influential assumption ('{lever}') "
                          "moves favourably.", alt, seed),
            _run_scenario(model, "stress", "Stress", f"Unfavourable shift of ±{min(0.9, band * 2):.0%} on all "
                          "uncertain assumptions.", stress, seed),
        ]
    else:
        out += _quantile_scenarios(model, params, band, seed)
    if what_if:
        out.append(_run_scenario(model, "what_if", "What-if", f"User overrides: {what_if}", params | what_if, seed))
    return out


def _quantile_scenarios(model, params, band, seed) -> list[Scenario]:
    """Models without uncertain scalars (matrix inputs): pick Monte Carlo draws at quantiles."""
    rng = np.random.default_rng(seed)
    n = min(model.spec.mc_draws, 200)
    draws = []
    for _ in range(n):
        q = model.perturb(params, rng, band)
        try:
            draws.append((q, _primary(model, model.run(q, seed))))
        except ValueError:
            continue
    draws = [(q, v) for q, v in draws if v is not None]
    if not draws:
        return []
    draws.sort(key=lambda d: d[1])
    maximize = model.spec.primary_goal == "maximize"
    pick = lambda f: draws[min(len(draws) - 1, int(f * len(draws)))][0]
    hi, lo, ex = (0.9, 0.1, 0.02) if maximize else (0.1, 0.9, 0.98)
    return [
        _run_scenario(model, "best", "Best case", f"Monte Carlo draw at the {hi:.0%} quantile of "
                      f"{model.spec.primary_metric} (inputs perturbed ±{band:.0%}).", pick(hi), seed),
        _run_scenario(model, "worst", "Worst case", f"Monte Carlo draw at the {lo:.0%} quantile.", pick(lo), seed),
        _run_scenario(model, "stress", "Stress", f"Monte Carlo draw at the {ex:.0%} quantile.", pick(ex), seed),
    ]


def monte_carlo(model: Model, params: dict, band: float = 0.2, draws: int | None = None, seed: int = 42) -> MonteCarlo:
    draws = draws or model.spec.mc_draws
    rng = np.random.default_rng(seed)
    params = params | model.spec.mc_params
    base = model.run(params, seed).metrics
    values: dict[str, list[float]] = {}
    cats: dict[str, list] = {}
    ok = 0
    for i in range(draws):
        try:
            m = model.run(model.perturb(params, rng, band), seed + i + 1).metrics
        except ValueError:
            continue
        ok += 1
        for k, v in m.items():
            if isinstance(v, (bool, str)):
                cats.setdefault(k, []).append(v)
            elif isinstance(v, (int, float)):
                values.setdefault(k, []).append(float(v))
    summary = {k: {"mean": float(np.mean(v)), "sd": float(np.std(v)), "p05": float(np.percentile(v, 5)),
                   "p50": float(np.percentile(v, 50)), "p95": float(np.percentile(v, 95))} for k, v in values.items()}
    categorical = {k: {"baseline": base.get(k), "baseline_share": v.count(base.get(k)) / len(v),
                       "frequencies": dict(Counter(map(str, v)).most_common(5))} for k, v in cats.items()}
    pm = model.spec.primary_metric
    hist = {}
    if pm in values:
        counts, edges = np.histogram(values[pm], bins=20)
        hist = {"edges": edges.tolist(), "counts": counts.astype(float).tolist()}
    note = BAND_NOTE.format(band=band)
    if model.spec.mc_params:
        note += f" Inner simulation reduced for Monte Carlo: {model.spec.mc_params}."
    return MonteCarlo(draws=ok, band=band, summary=summary, categorical=categorical, histogram=hist, note=note)
