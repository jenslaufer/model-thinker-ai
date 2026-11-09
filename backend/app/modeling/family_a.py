"""Family A: distributions and mathematical models."""

import numpy as np
from scipy import stats

from .base import Claim, Model, ModelOutput, ModelSpec, ParamError, ParamSpec, Recommendation, Series, Statement, fmt


class NormalModel(Model):
    spec = ModelSpec(
        key="normal", number=1, name="Normal Distribution", family="A",
        summary="Outcomes as the sum of many small independent effects.",
        description="Estimates how likely an outcome crosses a critical threshold when it results from "
                    "many small, independent, additive influences (Central Limit Theorem).",
        math=r"f(x)=\frac{1}{\sigma\sqrt{2\pi}}e^{-\frac{(x-\mu)^2}{2\sigma^2}},\quad P(X>t)=1-\Phi\left(\frac{t-\mu}{\sigma}\right)",
        assumptions=["Outcome is a sum of many independent, comparably small effects",
                     "Mean and standard deviation are known or estimated", "Tails are thin (no extreme events)"],
        prerequisites=["Estimate of mean and spread of the outcome"],
        limits=["Underestimates extreme events when effects interact or multiply",
                "Unsuitable for bounded or strongly skewed quantities"],
        examples=["Delivery time of a process", "Measurement error", "Quarterly demand of a mature product"],
        use_cases=["Service-level planning", "Quality control", "Risk of missing a target"],
        params=[
            ParamSpec(name="mu", label="Mean", default=100.0, uncertain=True),
            ParamSpec(name="sigma", label="Standard deviation", default=15.0, min=1e-9, uncertain=True),
            ParamSpec(name="threshold", label="Critical threshold", default=120.0,
                      description="Value whose exceedance matters"),
        ],
        primary_metric="p_above", primary_goal="minimize",
        tags={"uncertainty": 0.8, "risk": 0.7, "distribution": 0.9, "forecast": 0.4},
        needs_time=False, data_need="medium", perspective="statistical",
    )

    def compute(self, p, rng):
        mu, sigma, t = p["mu"], p["sigma"], p["threshold"]
        z = (t - mu) / sigma
        p_above = float(stats.norm.sf(z))
        xs = np.linspace(mu - 4 * sigma, mu + 4 * sigma, 121)
        q = {k: float(stats.norm.ppf(v, mu, sigma)) for k, v in (("q05", 0.05), ("q50", 0.5), ("q95", 0.95))}
        risk = 1 if p_above > 0.2 else (-1 if p_above < 0.05 else 0)
        return ModelOutput(
            metrics={"p_above": p_above, "p_below": 1 - p_above, "z_threshold": z, **q},
            series=[Series(name="Density", x=xs.tolist(), y=stats.norm.pdf(xs, mu, sigma).tolist(),
                           kind="area", x_label="Outcome", y_label="Density")],
            claims=[Claim(dimension="risk_level", direction=risk,
                          statement=f"P(outcome > {fmt(t)}) = {p_above:.1%}"),
                    Claim(dimension="predictability", direction=1,
                          statement="Thin tails: 90% of outcomes lie in a narrow, computable band")],
            interpretation=[Statement(text=f"The threshold lies {z:.2f} standard deviations from the mean; "
                                           f"90% of outcomes fall between {fmt(q['q05'])} and {fmt(q['q95'])}.")],
            recommendations=[Recommendation(
                title="Size buffers to the 95% quantile", rationale=f"q95 = {fmt(q['q95'])} under normality.",
                expected_impact=f"Limits threshold breaches to about 5% (currently {p_above:.1%}).",
                prerequisites=["Verify thin tails with historical data"],
                risks=["Fat-tailed reality makes the buffer too small"], uncertainty="medium", horizon="short",
                actions=["Collect 30+ historical observations", "Compare empirical q95 with model q95"])],
            log=[f"z = ({fmt(t)} - {fmt(mu)}) / {fmt(sigma)} = {z:.4f}", f"P(X>t) = 1 - Phi(z) = {p_above:.6f}"],
        )


class PowerLawModel(Model):
    spec = ModelSpec(
        key="power_law", number=2, name="Power Law / Long Tail", family="A",
        summary="Few items capture most of the value; extreme events dominate.",
        description="Pareto distribution for quantities produced by preferential attachment, self-organized "
                    "criticality or multiplicative growth: city sizes, sales, wealth, outages.",
        math=r"P(X>x)=\left(\frac{x_{min}}{x}\right)^{\alpha},\quad \text{share of top } p = p^{1-1/\alpha}",
        assumptions=["Values above x_min follow a Pareto law", "alpha is stable over the observation window"],
        prerequisites=["Tail exponent estimate (log-log slope or MLE)"],
        limits=["alpha <= 1: mean is infinite; alpha <= 2: variance is infinite — averages mislead",
                "Lognormal data can look like a power law"],
        examples=["80/20 revenue concentration", "Viral content reach", "Operational loss severity"],
        use_cases=["Portfolio focus", "Tail-risk assessment", "Capacity for extreme events"],
        params=[
            ParamSpec(name="alpha", label="Tail exponent α", default=1.16, min=0.1, max=10, uncertain=True),
            ParamSpec(name="x_min", label="Minimum value x_min", default=1.0, min=1e-9),
            ParamSpec(name="top_fraction", label="Top fraction p", default=0.2, min=1e-4, max=1),
        ],
        primary_metric="top_share", primary_goal="minimize",
        tags={"inequality": 1.0, "distribution": 0.8, "risk": 0.6, "concentration": 1.0},
        needs_time=False, data_need="medium", perspective="statistical",
    )

    def compute(self, p, rng):
        a, xm, top = p["alpha"], p["x_min"], p["top_fraction"]
        warnings, mean = [], None
        if a > 1:
            mean = a * xm / (a - 1)
            top_share = top ** (1 - 1 / a)
        else:
            top_share = 1.0
            warnings.append("alpha <= 1: the mean is infinite; the top fraction holds (asymptotically) everything.")
        if a <= 2:
            warnings.append("alpha <= 2: variance is infinite; sample averages are unstable.")
        median = xm * 2 ** (1 / a)
        xs = np.logspace(np.log10(xm), np.log10(xm * 1000), 60)
        conc = 1 if top_share > 0.6 else 0
        return ModelOutput(
            metrics={"top_share": top_share, "mean": mean, "median": median, "p_exceed_10x": 10**-a,
                     "p_exceed_100x": 100**-a},
            series=[Series(name="Survival P(X>x)", x=xs.tolist(), y=((xm / xs) ** a).tolist(),
                           x_label="x (log)", y_label="P(X>x)")],
            claims=[Claim(dimension="concentration", direction=conc,
                          statement=f"Top {top:.0%} hold {top_share:.0%} of total value"),
                    Claim(dimension="predictability", direction=-1 if a <= 2 else 0,
                          statement="Heavy tail: single extreme events dominate aggregates")],
            interpretation=[Statement(text=f"With alpha = {a:.2f}, the top {top:.0%} account for {top_share:.0%}. "
                                           f"An event 10x the minimum has probability {10**-a:.1%}.")],
            recommendations=[Recommendation(
                title="Focus resources on the head, insure the tail",
                rationale=f"Top {top:.0%} carry {top_share:.0%} of value.",
                expected_impact="Higher return per unit of effort; explicit protection against extremes.",
                prerequisites=["Rank items by value", "Fit alpha on real data"],
                risks=["Neglecting the long tail may forgo future hits"], uncertainty="medium", horizon="medium",
                actions=["Build a ranked value list", "Define tail-event playbook"])],
            warnings=warnings,
            log=[f"top_share = p^(1-1/alpha) = {top}^(1-1/{a}) = {top_share:.6f}", f"median = x_min*2^(1/alpha) = {median:.4f}"],
        )


class LinearModel(Model):
    spec = ModelSpec(
        key="linear", number=3, name="Linear Models", family="A",
        summary="Outcome changes by a constant amount per unit of input.",
        description="Ordinary least squares on observed data, or — without data — an explicitly assumed linear "
                    "projection. Gives slope, fit quality and a prediction interval.",
        math=r"y=\beta_0+\beta_1 x+\varepsilon,\quad \hat\beta=(X^TX)^{-1}X^Ty",
        assumptions=["Effect is additive and constant over the range", "Errors are independent with constant variance"],
        prerequisites=["Paired observations (x, y) — at least 3 points for intervals"],
        limits=["Extrapolation beyond the data range is unreliable",
                "Correlation in data is not causation", "Misses saturation and tipping points"],
        examples=["Revenue trend over months", "Cost per unit produced"],
        use_cases=["Trend forecast", "Effect size of a driver"],
        params=[
            ParamSpec(name="data_x", label="Observed x", type="vector", default=[1, 2, 3, 4, 5, 6]),
            ParamSpec(name="data_y", label="Observed y", type="vector", default=[102, 108, 111, 119, 123, 131]),
            ParamSpec(name="horizon", label="Forecast periods after last x", type="int", default=6, min=0, max=1000),
            ParamSpec(name="baseline", label="Baseline (used without data)", default=100.0, uncertain=True),
            ParamSpec(name="slope", label="Slope per period (used without data)", default=5.0, uncertain=True),
        ],
        goal_metrics={"forecast": "value at the horizon"},
        levers=["slope"],
        primary_metric="forecast", primary_goal="maximize",
        tags={"trend": 1.0, "forecast": 0.9, "growth": 0.4},
        needs_time=None, data_need="high", perspective="statistical",
    )

    def check(self, p):
        if len(p["data_x"]) != len(p["data_y"]):
            raise ParamError("data_x and data_y must have equal length")
        if 0 < len(p["data_x"]) < 2:
            raise ParamError("need at least 2 data points (or none for an assumed projection)")

    def compute(self, p, rng):
        x, y, h = np.array(p["data_x"]), np.array(p["data_y"]), p["horizon"]
        warnings, log = [], []
        if len(x) == 0:
            b0, b1, last = p["baseline"], p["slope"], 0.0
            r2 = lo = hi = None
            warnings.append("No data: slope and baseline are assumptions, not estimates.")
            forecast = b0 + b1 * h
            log.append(f"assumed projection: {fmt(b0)} + {fmt(b1)}*{h}")
            xs_fit, ys_fit = [0, h], [b0, forecast]
        else:
            res = stats.linregress(x, y)
            b0, b1, last = float(res.intercept), float(res.slope), float(x.max())
            x_new = last + h
            forecast = b0 + b1 * x_new
            r2 = float(res.rvalue**2) if np.ptp(y) > 0 else 1.0
            n = len(x)
            lo = hi = None
            if n >= 3:
                resid = y - (b0 + b1 * x)
                s = np.sqrt(np.sum(resid**2) / (n - 2))
                se = s * np.sqrt(1 + 1 / n + (x_new - x.mean()) ** 2 / np.sum((x - x.mean()) ** 2))
                tq = stats.t.ppf(0.975, n - 2)
                lo, hi = forecast - tq * se, forecast + tq * se
            if n < 8:
                warnings.append(f"Only {n} observations: estimates are fragile.")
            if h > np.ptp(x):
                warnings.append("Forecast extrapolates beyond the observed range.")
            log.append(f"OLS: intercept={b0:.4f}, slope={b1:.4f}, R2={r2:.4f}")
            xs_fit = np.linspace(x.min(), x_new, 30).tolist()
            ys_fit = (b0 + b1 * np.array(xs_fit)).tolist()
        series = [Series(name="Linear fit / projection", x=list(xs_fit), y=list(ys_fit), x_label="x", y_label="y")]
        if len(x):
            series.insert(0, Series(name="Observed", x=x.tolist(), y=y.tolist(), kind="scatter"))
        trend = 1 if b1 > 0 else (-1 if b1 < 0 else 0)
        return ModelOutput(
            metrics={"intercept": b0, "slope": b1, "r2": r2, "forecast": forecast, "forecast_lo": lo, "forecast_hi": hi},
            series=series,
            claims=[Claim(dimension="outcome_trend", direction=trend, statement=f"Linear trend {fmt(b1)} per period"),
                    Claim(dimension="predictability", direction=1 if (r2 or 0) > 0.8 else 0,
                          statement=f"Linear fit R² = {r2:.2f}" if r2 is not None else "No fit (assumed)")],
            interpretation=[Statement(text=f"Each period changes the outcome by {fmt(b1)}; projected value after "
                                           f"{h} periods: {fmt(forecast)}" +
                                           (f" (95% prediction interval {fmt(lo)} – {fmt(hi)})." if lo is not None else "."))],
            recommendations=[Recommendation(
                title="Plan with the trend, monitor for curvature",
                rationale=f"Slope {fmt(b1)} per period.", expected_impact=f"Forecast {fmt(forecast)}.",
                prerequisites=["Data covers the decision range"],
                risks=["Saturation or feedback breaks linearity"], uncertainty="medium" if r2 else "high",
                horizon="short", actions=["Re-estimate every period", "Compare against nonlinear models"])],
            warnings=warnings, log=log,
        )


MODELS = [NormalModel(), PowerLawModel(), LinearModel()]
