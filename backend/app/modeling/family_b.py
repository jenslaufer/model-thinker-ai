"""Family B: networks and information models."""

import math

import networkx as nx
import numpy as np

from .base import Claim, Model, ModelOutput, ModelSpec, ParamError, ParamSpec, Recommendation, Series, Statement, fmt


class NetworkModel(Model):
    spec = ModelSpec(
        key="network", number=6, name="Network Models", family="B",
        summary="Structure of connections shapes reach, robustness and influence.",
        description="Generates a network of the given topology and measures degree distribution, clustering, "
                    "path length and connectedness — the structural drivers of spread and resilience.",
        math=r"C_i=\frac{2e_i}{k_i(k_i-1)},\quad L=\frac{1}{n(n-1)}\sum_{i\neq j}d(i,j)",
        assumptions=["Ties are undirected and unweighted", "Topology class approximates the real network"],
        prerequisites=["Number of actors and average number of contacts"],
        limits=["Synthetic topology, not the measured network", "Ignores tie strength and direction"],
        examples=["Customer referral network", "Supplier dependencies", "Team communication"],
        use_cases=["Find hubs and bottlenecks", "Assess spread potential"],
        params=[
            ParamSpec(name="n", label="Actors (nodes)", type="int", default=300, min=10, max=5000),
            ParamSpec(name="avg_degree", label="Average contacts per actor", default=6.0, min=1, max=100, uncertain=True),
            ParamSpec(name="topology", label="Topology", type="choice", default="scale_free",
                      choices=["random", "scale_free", "small_world"]),
        ],
        primary_metric="giant_component_share", primary_goal="maximize", mc_draws=30,
        tags={"network": 1.0, "diffusion": 0.5, "influence": 0.8, "dependency": 0.6},
        min_actors=3, needs_time=False, data_need="medium", perspective="structural",
    )

    def compute(self, p, rng):
        n, k, topo = p["n"], p["avg_degree"], p["topology"]
        seed = int(rng.integers(1 << 31))
        if topo == "random":
            g = nx.gnp_random_graph(n, min(1.0, k / (n - 1)), seed=seed)
        elif topo == "scale_free":
            g = nx.barabasi_albert_graph(n, max(1, round(k / 2)), seed=seed)
        else:
            g = nx.watts_strogatz_graph(n, max(2, round(k)), 0.1, seed=seed)
        degrees = np.array([d for _, d in g.degree()])
        giant = g.subgraph(max(nx.connected_components(g), key=len))
        giant_share = giant.number_of_nodes() / n
        # mean shortest path from up to 100 sampled sources (exact for small giants)
        nodes = list(giant.nodes())
        sources = nodes if len(nodes) <= 100 else rng.choice(nodes, 100, replace=False).tolist()
        dists = [d for src in sources for d in nx.single_source_shortest_path_length(giant, src).values() if d]
        path = float(np.mean(dists)) if dists else None
        clustering = nx.average_clustering(g)
        top = sorted(nx.degree_centrality(g).items(), key=lambda kv: -kv[1])[:5]
        hub_share = degrees[np.argsort(-degrees)[: max(1, n // 10)]].sum() / max(1, degrees.sum())
        counts = np.bincount(degrees)
        return ModelOutput(
            metrics={"avg_degree": float(degrees.mean()), "max_degree": int(degrees.max()),
                     "avg_clustering": clustering, "avg_path_length": path, "giant_component_share": giant_share,
                     "top10_degree_share": float(hub_share)},
            series=[Series(name="Degree distribution", x=list(range(len(counts))), y=counts.tolist(), kind="bar",
                           x_label="Degree", y_label="Actors")],
            tables={"hubs": [{"node": int(nd), "degree_centrality": round(c, 4)} for nd, c in top]},
            claims=[Claim(dimension="concentration", direction=1 if hub_share > 0.3 else 0,
                          statement=f"Top 10% of actors hold {hub_share:.0%} of ties"),
                    Claim(dimension="leverage", direction=1 if hub_share > 0.3 else 0,
                          statement="Hubs offer leverage points" if hub_share > 0.3 else "No dominant hubs")],
            interpretation=[Statement(text=f"{topo.replace('_', ' ')} network: {giant_share:.0%} of actors are "
                                           f"mutually reachable" + (f", average distance {path:.1f} steps." if path else "."))],
            recommendations=[Recommendation(
                title="Target the hubs" if hub_share > 0.3 else "Seed broadly",
                rationale=f"Top 10% of actors hold {hub_share:.0%} of connections.",
                expected_impact="Faster spread per seeded actor" if hub_share > 0.3 else "Robust, even spread",
                prerequisites=["Map real contacts to identify hubs"],
                risks=["Hub failure fragments a scale-free network"], horizon="short",
                actions=["Identify top-degree actors", "Plan redundancy for critical hubs"])],
            log=[f"generated {topo} graph n={n}, edges={g.number_of_edges()}, graph seed={seed}"],
        )


class DiffusionModel(Model):
    spec = ModelSpec(
        key="diffusion", number=7, name="Broadcast, Diffusion and Contagion (Bass)", family="B",
        summary="Adoption via broadcast (innovation p) and word of mouth (imitation q).",
        description="The Bass model combines a broadcast term (external influence) with contagion between "
                    "adopters and non-adopters. Yields the S-curve, peak timing and saturation.",
        math=r"\frac{dF}{dt}=(p+qF)(1-F),\quad F(t)=\frac{1-e^{-(p+q)t}}{1+\frac{q}{p}e^{-(p+q)t}},\quad t^*=\frac{\ln(q/p)}{p+q}",
        assumptions=["Fixed market potential m", "Homogeneous, fully mixed population", "Each actor adopts once"],
        prerequisites=["Market potential estimate", "p and q from analogues (typical p≈0.03, q≈0.38)"],
        limits=["No network structure, no churn, no competition", "p and q are hard to estimate before launch"],
        examples=["Product launch", "Technology adoption", "Spread of a practice"],
        use_cases=["Launch planning", "Marketing mix: broadcast vs. referral"],
        params=[
            ParamSpec(name="p", label="Innovation (broadcast) p", default=0.03, min=1e-6, max=1, uncertain=True),
            ParamSpec(name="q", label="Imitation (contagion) q", default=0.38, min=0, max=5, uncertain=True),
            ParamSpec(name="market_size", label="Market potential m", default=10000.0, min=1, uncertain=True),
            ParamSpec(name="periods", label="Horizon (periods)", type="int", default=24, min=1, max=1000),
        ],
        goal_metrics={"adopters_at_horizon": "adopters at the horizon"},
        levers=["p", "q"],
        primary_metric="adopters_at_horizon", primary_goal="maximize",
        tags={"diffusion": 1.0, "adoption": 1.0, "growth": 0.7, "marketing": 0.8, "network": 0.3},
        needs_time=True, data_need="low", perspective="dynamic",
    )

    @staticmethod
    def F(t, p, q):
        e = np.exp(-(p + q) * t)
        return (1 - e) / (1 + (q / p) * e)

    def compute(self, p, rng):
        pp, q, m, T = p["p"], p["q"], p["market_size"], p["periods"]
        t = np.arange(0, T + 1)
        cum = m * self.F(t, pp, q)
        peak = max(0.0, math.log(q / pp) / (pp + q)) if q > pp else 0
        f_half = 0.5
        t_half = math.log((1 + q / pp * f_half) / (1 - f_half)) / (pp + q)  # inverse of F at 0.5
        at_h = float(m * self.F(T, pp, q))
        share = at_h / m
        return ModelOutput(
            metrics={"adopters_at_horizon": at_h, "share_at_horizon": share, "peak_time": peak,
                     "time_to_50pct": t_half, "q_over_p": q / pp},
            series=[Series(name="Cumulative adopters", x=t.tolist(), y=cum.tolist(), x_label="Period", y_label="Adopters"),
                    Series(name="New adopters", x=t[1:].tolist(), y=np.diff(cum).tolist(), kind="bar")],
            claims=[Claim(dimension="outcome_trend", direction=1 if share > 0.5 else 0,
                          statement=f"{share:.0%} of potential adopted by period {T}"),
                    Claim(dimension="leverage", direction=1 if q > 3 * pp else 0,
                          statement="Word of mouth dominates" if q > 3 * pp else "Broadcast dominates")],
            interpretation=[Statement(text=f"Adoption peaks around period {peak:.1f}; half the market adopts by "
                                           f"period {t_half:.1f}. q/p = {q / pp:.1f} — "
                                           + ("social contagion drives growth." if q > pp else "broadcast drives growth."))],
            recommendations=[Recommendation(
                title="Invest in referral mechanics" if q > 3 * pp else "Invest in reach (broadcast)",
                rationale=f"q/p = {q / pp:.1f}.",
                expected_impact=f"{fmt(at_h)} adopters by period {T} under baseline assumptions.",
                prerequisites=["Calibrate p, q on first months of data"],
                risks=["Market potential overestimated", "Competing products cap adoption"], horizon="medium",
                actions=["Track monthly new adopters", "Refit p and q after 3–6 periods"])],
            log=[f"F(T) = {self.F(T, pp, q):.6f}", f"t* = ln(q/p)/(p+q) = {peak:.4f}"],
        )


class EntropyModel(Model):
    spec = ModelSpec(
        key="entropy", number=8, name="Entropy Models", family="B",
        summary="Measures uncertainty, diversity or information content of a distribution.",
        description="Shannon entropy quantifies how unpredictable an outcome is, or how diverse a portfolio, "
                    "market or team composition is.",
        math=r"H=-\sum_i p_i\log_2 p_i,\quad H_{max}=\log_2 n",
        assumptions=["Categories are exhaustive and mutually exclusive", "Shares reflect probabilities"],
        prerequisites=["Shares or frequencies per category"],
        limits=["Ignores similarity between categories", "Depends on category granularity"],
        examples=["Customer concentration", "Revenue diversity", "Outcome predictability"],
        use_cases=["Diversification check", "Information value of a signal"],
        params=[ParamSpec(name="probabilities", label="Shares per category", type="vector",
                          default=[0.5, 0.2, 0.15, 0.1, 0.05], min=0)],
        primary_metric="normalized_entropy", primary_goal="maximize",
        tags={"uncertainty": 0.6, "information": 1.0, "concentration": 0.7, "diversity": 1.0},
        needs_time=False, data_need="medium", perspective="information",
    )

    def check(self, p):
        if len(p["probabilities"]) < 2 or sum(p["probabilities"]) <= 0:
            raise ParamError("need at least 2 categories with positive total")

    def compute(self, p, rng):
        w = np.array(p["probabilities"], dtype=float)
        pr = w / w.sum()
        nz = pr[pr > 0]
        h = float(-(nz * np.log2(nz)).sum())
        hmax = math.log2(len(pr))
        norm = h / hmax
        hhi = float((pr**2).sum())
        return ModelOutput(
            metrics={"entropy_bits": h, "max_entropy": hmax, "normalized_entropy": norm, "hhi": hhi,
                     "effective_categories": 2**h, "max_share": float(pr.max())},
            series=[Series(name="Shares", x=[f"#{i + 1}" for i in range(len(pr))], y=pr.tolist(), kind="bar")],
            claims=[Claim(dimension="concentration", direction=1 if norm < 0.6 else -1,
                          statement=f"Normalized entropy {norm:.2f}"),
                    Claim(dimension="predictability", direction=1 if norm < 0.5 else -1,
                          statement=f"{2**h:.1f} effective categories")],
            interpretation=[Statement(text=f"The distribution behaves like {2**h:.1f} equally sized categories "
                                           f"(of {len(pr)}); HHI = {hhi:.2f}.")],
            recommendations=[Recommendation(
                title="Diversify concentrated exposure" if norm < 0.6 else "Diversity is adequate",
                rationale=f"Normalized entropy {norm:.2f}.", expected_impact="Lower dependency on single categories",
                risks=["Diversification can dilute focus"], horizon="medium",
                actions=["Set a maximum share per category"])],
            log=[f"H = -sum p log2 p = {h:.6f} bits, Hmax = {hmax:.6f}"],
        )


class RandomWalkModel(Model):
    spec = ModelSpec(
        key="random_walk", number=9, name="Random Walk Models", family="B",
        summary="Outcome drifts with random shocks; spread grows with √time.",
        description="Monte Carlo of a Gaussian random walk with drift. Shows the range of paths and the chance "
                    "of hitting a critical level at any point in time.",
        math=r"X_{t+1}=X_t+\mu+\sigma\varepsilon_t,\ \varepsilon_t\sim N(0,1),\quad E[X_T]=X_0+\mu T,\ SD[X_T]=\sigma\sqrt{T}",
        assumptions=["Shocks are independent and identically distributed", "Drift and volatility are constant"],
        prerequisites=["Drift and volatility per period (e.g. from historical changes)"],
        limits=["No mean reversion, no regime shifts, thin tails"],
        examples=["Cash balance", "Price of a commodity", "Backlog size"],
        use_cases=["Liquidity risk", "Probability of hitting a limit"],
        params=[
            ParamSpec(name="start", label="Start value", default=100.0),
            ParamSpec(name="drift", label="Drift per period", default=0.5, uncertain=True),
            ParamSpec(name="volatility", label="Volatility per period", default=5.0, min=0, uncertain=True),
            ParamSpec(name="steps", label="Periods", type="int", default=52, min=1, max=2000),
            ParamSpec(name="paths", label="Simulated paths", type="int", default=2000, min=10, max=20000),
            ParamSpec(name="threshold", label="Critical level (hit if crossed)", default=80.0),
        ],
        goal_metrics={"mean_final": "average value at the end"},
        levers=["drift"],
        primary_metric="p_hit_threshold", primary_goal="minimize", mc_draws=200, mc_params={"paths": 300},
        tags={"uncertainty": 1.0, "risk": 0.9, "forecast": 0.5, "finance": 0.7},
        needs_time=True, data_need="medium", perspective="stochastic",
    )

    def compute(self, p, rng):
        x0, mu, sd, T, n, thr = p["start"], p["drift"], p["volatility"], p["steps"], p["paths"], p["threshold"]
        steps = mu + sd * rng.standard_normal((n, T))
        paths = x0 + np.cumsum(steps, axis=1)
        final = paths[:, -1]
        below = thr < x0
        hit = (paths.min(axis=1) <= thr) if below else (paths.max(axis=1) >= thr)
        if thr == x0:
            hit = np.ones(n, dtype=bool)
        p_hit = float(hit.mean())
        qs = np.percentile(paths, [5, 50, 95], axis=0)
        t = list(range(1, T + 1))
        return ModelOutput(
            metrics={"mean_final": float(final.mean()), "sd_final": float(final.std(ddof=1)),
                     "q05_final": float(np.percentile(final, 5)), "q95_final": float(np.percentile(final, 95)),
                     "p_hit_threshold": p_hit, "p_final_below_start": float((final < x0).mean()),
                     "analytic_mean": x0 + mu * T, "analytic_sd": sd * math.sqrt(T)},
            series=[Series(name="5th percentile", x=t, y=qs[0].tolist()),
                    Series(name="Median path", x=t, y=qs[1].tolist()),
                    Series(name="95th percentile", x=t, y=qs[2].tolist())],
            claims=[Claim(dimension="risk_level", direction=1 if p_hit > 0.2 else (-1 if p_hit < 0.05 else 0),
                          statement=f"{p_hit:.0%} chance of crossing {fmt(thr)} within {T} periods"),
                    Claim(dimension="predictability", direction=-1 if sd * math.sqrt(T) > abs(mu * T) else 1,
                          statement="Noise dominates drift" if sd * math.sqrt(T) > abs(mu * T) else "Drift dominates noise")],
            interpretation=[Statement(text=f"After {T} periods the 90% range is {fmt(qs[0][-1])} – {fmt(qs[2][-1])}; "
                                           f"probability of touching {fmt(thr)} at least once: {p_hit:.1%}.")],
            recommendations=[Recommendation(
                title="Hold a buffer against path risk",
                rationale=f"{p_hit:.0%} hit probability even with drift {fmt(mu)}.",
                expected_impact="Avoids forced action at the critical level.",
                prerequisites=["Estimate volatility from historical changes"],
                risks=["Fat tails or regime shifts increase real risk"], horizon="short",
                actions=["Set an early-warning level", "Re-estimate volatility quarterly"])],
            log=[f"{n} paths x {T} steps, analytic E[X_T]={x0 + mu * T:.4f}, SD={sd * math.sqrt(T):.4f}"],
        )


MODELS = [NetworkModel(), DiffusionModel(), EntropyModel(), RandomWalkModel()]
