"""Family C: dynamic and strategic models."""

import itertools
import math

import numpy as np
from scipy.integrate import solve_ivp

from .base import Claim, Model, ModelOutput, ModelSpec, ParamError, ParamSpec, Recommendation, Series, Statement, fmt


class MarkovModel(Model):
    spec = ModelSpec(
        key="markov", number=13, name="Markov Models", family="C", version="1.1.0",
        summary="Systems move between states with fixed transition probabilities.",
        description="Computes the state distribution over time and the long-run (stationary) distribution. "
                    "A key insight: if transitions are fixed, history does not matter — only transitions do.",
        math=r"\pi_{t+1}=\pi_t P,\quad \pi^*=\pi^*P,\ \sum_i\pi^*_i=1",
        assumptions=["Finitely many states", "Transition probabilities are constant (no memory)",
                     "Chain is irreducible for a unique long run"],
        prerequisites=["Transition probabilities between states (e.g. from cohort data)"],
        limits=["Interventions that change P change the long run; interventions on the state do not",
                "Memory effects (path dependence) are ignored"],
        examples=["Customer active/dormant/churned", "Employee engagement levels", "Machine up/down"],
        use_cases=["Long-run market share", "Churn and retention planning"],
        params=[
            ParamSpec(name="states", label="State names", type="labels", default=["Active", "Dormant", "Churned"]),
            ParamSpec(name="transition_matrix", label="Transition matrix P (rows sum to 1)", type="matrix",
                      default=[[0.85, 0.10, 0.05], [0.30, 0.50, 0.20], [0.05, 0.05, 0.90]], min=0, max=1,
                      stochastic_rows=True),
            ParamSpec(name="initial", label="Initial distribution", type="vector", default=[1.0, 0.0, 0.0], min=0),
            ParamSpec(name="steps", label="Periods", type="int", default=24, min=1, max=10000),
            ParamSpec(name="target_state", label="State of interest (index)", type="int", default=0, min=0),
            ParamSpec(name="population", label="Population size (0 = shares only)", default=0.0, min=0,
                      description="Number of members, to report counts instead of shares"),
        ],
        primary_metric="final_target", primary_goal="maximize", mc_draws=300,
        goal_metrics={"final_target_count": "count in the state of interest at the horizon"},
        tags={"states": 1.0, "churn": 1.0, "retention": 1.0, "long_run": 0.8, "dynamics": 0.5},
        needs_time=True, data_need="medium", perspective="dynamic",
    )

    def check(self, p):
        P, n = np.array(p["transition_matrix"]), len(p["states"])
        if P.shape != (n, n):
            raise ParamError(f"transition_matrix must be {n}x{n}")
        if not np.allclose(P.sum(axis=1), 1, atol=1e-6):
            raise ParamError("each row of transition_matrix must sum to 1")
        if len(p["initial"]) != n or sum(p["initial"]) <= 0:
            raise ParamError("initial must have one non-negative weight per state")
        if p["target_state"] >= n:
            raise ParamError("target_state out of range")

    def compute(self, p, rng):
        P, labels, k = np.array(p["transition_matrix"]), p["states"], p["target_state"]
        pi = np.array(p["initial"]) / sum(p["initial"])
        vals, vecs = np.linalg.eig(P.T)
        ones = np.isclose(vals, 1, atol=1e-9)
        warnings = []
        if ones.sum() > 1:
            warnings.append("Several stationary distributions: chain is reducible; long run depends on the start.")
        v = np.real(vecs[:, np.argmin(np.abs(vals - 1))])
        stat = v / v.sum()
        hist, mixing = [pi], None
        for t in range(1, p["steps"] + 1):
            pi = pi @ P
            hist.append(pi)
            if mixing is None and 0.5 * np.abs(pi - stat).sum() < 0.01:
                mixing = t
        hist = np.array(hist)
        metrics = {f"stationary_{s}": float(stat[i]) for i, s in enumerate(labels)}
        metrics |= {f"final_{s}": float(hist[-1, i]) for i, s in enumerate(labels)}
        metrics |= {"final_target": float(hist[-1, k]), "stationary_target": float(stat[k]), "mixing_steps": mixing}
        if p["population"] > 0:
            metrics |= {"final_target_count": p["population"] * float(hist[-1, k]),
                        "stationary_target_count": p["population"] * float(stat[k])}
        t = list(range(len(hist)))
        trend = int(np.sign(round(stat[k] - hist[0, k], 6)))
        return ModelOutput(
            metrics=metrics,
            series=[Series(name=s, x=t, y=hist[:, i].tolist(), x_label="Period", y_label="Share")
                    for i, s in enumerate(labels)],
            claims=[Claim(dimension="outcome_trend", direction=trend,
                          statement=f"'{labels[k]}' converges to {stat[k]:.0%} in the long run"),
                    Claim(dimension="leverage", direction=1,
                          statement="Only changing transition probabilities shifts the long run")],
            interpretation=[Statement(text=f"Long-run share of '{labels[k]}': {stat[k]:.1%}"
                                           + (f", reached within 1% after {mixing} periods." if mixing else
                                              "; not converged within the horizon."))],
            recommendations=[Recommendation(
                title=f"Change transitions into and out of '{labels[k]}'",
                rationale="The stationary distribution depends only on P, not on the current state.",
                expected_impact=f"Shifts the long-run share of '{labels[k]}' (now {stat[k]:.0%}).",
                prerequisites=["Measure transition rates per period from cohort data"],
                risks=["One-off campaigns that move the state but not P fade out"], horizon="long",
                actions=["Identify the largest outflow from the target state", "Design interventions on that rate"])],
            warnings=warnings, log=[f"eigenvalues of P^T: {np.round(vals, 4).tolist()}", f"stationary: {np.round(stat, 6).tolist()}"],
        )

    def perturb(self, p, rng, band):
        P = np.array(p["transition_matrix"]) * np.exp(rng.normal(0, band, (len(p["states"]),) * 2))
        return p | {"transition_matrix": (P / P.sum(axis=1, keepdims=True)).tolist()}


class SystemDynamicsModel(Model):
    spec = ModelSpec(
        key="system_dynamics", number=14, name="System Dynamics", family="C",
        summary="Stocks and flows with reinforcing and balancing feedback loops.",
        description="One stock with a reinforcing growth loop limited by capacity (balancing loop), a "
                    "proportional outflow and a constant external inflow, integrated numerically (RK45).",
        math=r"\frac{dS}{dt}=rS\left(1-\frac{S}{K}\right)-dS+u,\quad S^*=\frac{(r-d)+\sqrt{(r-d)^2+4ru/K}}{2r/K}",
        assumptions=["Single aggregated stock", "Constant rates over the horizon", "Continuous flows"],
        prerequisites=["Current stock, growth and loss rates, capacity estimate"],
        limits=["Aggregation hides heterogeneity", "Delays and multiple stocks are not modelled in this version"],
        examples=["Customer base", "Workforce with hiring and attrition", "Resource stock (fish, forest)"],
        use_cases=["Growth limits", "Sustainable steady state", "Policy levers on flows"],
        params=[
            ParamSpec(name="initial_stock", label="Initial stock S₀", default=100.0, min=0),
            ParamSpec(name="growth_rate", label="Reinforcing growth rate r", default=0.4, min=0, max=10, uncertain=True),
            ParamSpec(name="capacity", label="Capacity K", default=5000.0, min=1e-9, uncertain=True),
            ParamSpec(name="outflow_rate", label="Outflow rate d", default=0.1, min=0, max=10, uncertain=True),
            ParamSpec(name="external_inflow", label="External inflow u per period", default=10.0, min=0, uncertain=True),
            ParamSpec(name="horizon", label="Horizon (periods)", type="int", default=36, min=1, max=2000),
        ],
        goal_metrics={"final_stock": "stock at the horizon"},
        levers=["growth_rate", "outflow_rate", "external_inflow"],
        primary_metric="final_stock", primary_goal="maximize", mc_draws=150,
        tags={"growth": 1.0, "feedback": 1.0, "capacity": 1.0, "dynamics": 1.0, "resources": 0.7},
        needs_time=True, data_need="low", perspective="dynamic",
    )

    def compute(self, p, rng):
        s0, r, K, d, u, T = (p[k] for k in ("initial_stock", "growth_rate", "capacity", "outflow_rate",
                                            "external_inflow", "horizon"))
        f = lambda t, s: r * s * (1 - s / K) - d * s + u
        t = np.linspace(0, T, max(2, T * 4 + 1))
        sol = solve_ivp(f, (0, T), [s0], t_eval=t, rtol=1e-8, atol=1e-8)
        s = sol.y[0]
        if r > 0:
            a = r - d
            eq = (a + math.sqrt(a * a + 4 * r * u / K)) / (2 * r / K)
        else:
            eq = u / d if d > 0 else math.inf
        eq = max(0.0, eq)
        reach = np.where(np.abs(s - eq) <= 0.1 * max(abs(eq - s0), 1e-9))[0]
        t90 = float(t[reach[0]]) if len(reach) else None
        loop = "reinforcing" if r > d else "balancing"
        trend = int(np.sign(round(s[-1] - s0, 9)))
        return ModelOutput(
            metrics={"final_stock": float(s[-1]), "equilibrium": eq, "peak_stock": float(s.max()),
                     "time_to_90pct_eq": t90, "dominant_loop_at_start": loop, "net_growth_rate": r - d},
            series=[Series(name="Stock", x=t.tolist(), y=s.tolist(), x_label="Period", y_label="Stock"),
                    Series(name="Equilibrium", x=[0, T], y=[eq, eq])],
            claims=[Claim(dimension="outcome_trend", direction=trend, statement=f"Stock moves to {fmt(eq)}"),
                    Claim(dimension="leverage", direction=1, statement="Capacity and outflow rate set the ceiling")],
            interpretation=[Statement(text=f"The {loop} loop dominates at the start; the stock approaches the "
                                           f"equilibrium {fmt(eq)} (now {fmt(s0)})"
                                           + (f", 90% of the way after {t90:.1f} periods." if t90 is not None else "."))],
            recommendations=[Recommendation(
                title="Raise capacity or cut the outflow rate",
                rationale=f"Equilibrium S* = {fmt(eq)} is set by K, r, d and u — not by the starting stock.",
                expected_impact="Higher sustainable level; growth effort alone saturates at K.",
                prerequisites=["Estimate the real capacity limit"], risks=["Capacity is often overestimated"],
                horizon="long", actions=["Quantify outflow drivers", "Test capacity-expansion options"])],
            log=[f"RK45 integration, {len(t)} points, status={sol.status}", f"analytic equilibrium S* = {eq:.6f}"],
        )


class ThresholdModel(Model):
    spec = ModelSpec(
        key="threshold", number=15, name="Threshold and Feedback Models", family="C",
        summary="Actors join once enough others have joined — cascades and tipping points.",
        description="Granovetter threshold model: each actor adopts when the adopting share exceeds their "
                    "personal threshold. Small changes in the initial share can flip the outcome.",
        math=r"s_{t+1}=s_0+(1-s_0)\,F_\theta(s_t),\quad \theta_i\sim N(\mu,\sigma)",
        assumptions=["Actors observe the total adoption share", "Thresholds are fixed",
                     "Adoption is irreversible within the horizon"],
        prerequisites=["Estimate of the distribution of individual thresholds"],
        limits=["Highly sensitive to the threshold distribution — results are scenario-like",
                "No network locality (see Network models)"],
        examples=["Protest participation", "Adoption of a standard", "Bank run"],
        use_cases=["Find the critical mass", "Assess cascade risk"],
        params=[
            ParamSpec(name="population", label="Population", type="int", default=1000, min=10, max=100000),
            ParamSpec(name="mean_threshold", label="Mean threshold", default=0.25, min=0, max=1, uncertain=True),
            ParamSpec(name="sd_threshold", label="Threshold spread", default=0.12, min=0, max=1, uncertain=True),
            ParamSpec(name="initial_share", label="Initial adopter share", default=0.1, min=0, max=1, uncertain=True),
        ],
        primary_metric="final_share", primary_goal="maximize", mc_draws=200,
        tags={"tipping": 1.0, "feedback": 0.8, "adoption": 0.7, "collective": 0.6, "critical_mass": 1.0},
        min_actors=2, needs_time=True, data_need="low", perspective="social",
    )

    @staticmethod
    def cascade(theta, s0):
        s, rounds = s0, 0
        while rounds < 1000:
            new = s0 + (1 - s0) * float((theta <= s + 1e-12).mean())
            rounds += 1
            if abs(new - s) < 1e-12:
                break
            s = new
        return s, rounds

    def compute(self, p, rng):
        theta = np.clip(rng.normal(p["mean_threshold"], p["sd_threshold"], p["population"]), 0, 1)
        final, rounds = self.cascade(theta, p["initial_share"])
        sweep = np.linspace(0, 0.5, 51)
        finals = [self.cascade(theta, s)[0] for s in sweep]
        crit = next((float(s) for s, f in zip(sweep, finals) if f >= 0.9), None)
        tipped = final >= 0.9
        return ModelOutput(
            metrics={"final_share": final, "rounds": rounds, "tipped": tipped, "critical_initial_share": crit},
            series=[Series(name="Final share vs. initial share", x=sweep.tolist(), y=finals,
                           x_label="Initial adopters", y_label="Final adopters")],
            claims=[Claim(dimension="outcome_trend", direction=1 if tipped else -1,
                          statement=f"Cascade {'reaches' if tipped else 'stalls at'} {final:.0%}"),
                    Claim(dimension="predictability", direction=-1,
                          statement="Outcome flips abruptly around the critical mass")],
            interpretation=[Statement(text=f"Starting from {p['initial_share']:.0%} adopters the cascade ends at "
                                           f"{final:.0%} after {rounds} rounds. "
                                           + (f"Critical initial share ≈ {crit:.0%}." if crit is not None else
                                              "No full cascade below 50% initial share."))],
            recommendations=[Recommendation(
                title=f"Secure a committed core of ≥ {crit:.0%}" if crit is not None else "Lower adoption thresholds",
                rationale="Threshold dynamics are non-linear: below critical mass, effort is wasted.",
                expected_impact="Turns a stalled adoption into a self-sustaining cascade.",
                prerequisites=["Survey willingness: 'I join if x% join'"],
                risks=["Threshold distribution misestimated → wrong critical mass"], uncertainty="high",
                horizon="short", actions=["Recruit early committers", "Make adoption visible to raise perceived share"])],
            log=[f"thresholds sampled N({p['mean_threshold']}, {p['sd_threshold']}) clipped to [0,1]",
                 f"fixed point after {rounds} iterations: {final:.6f}"],
        )


class GameTheoryModel(Model):
    spec = ModelSpec(
        key="game_theory", number=17, name="Game Theory", family="C",
        summary="Strategic choices where each payoff depends on the others' choices.",
        description="Two-player normal-form game: dominant strategies, pure Nash equilibria (best-response "
                    "check), mixed equilibrium for 2×2 games, and Pareto efficiency of the outcome.",
        math=r"(s_r^*,s_c^*)\ \text{Nash} \iff u_r(s_r^*,s_c^*)\ge u_r(s_r,s_c^*)\ \forall s_r,\ u_c(s_r^*,s_c^*)\ge u_c(s_r^*,s_c)\ \forall s_c",
        assumptions=["Players are rational and know the payoffs", "Simultaneous, one-shot choice"],
        prerequisites=["Each actor's options and payoffs per outcome (ordinal is enough for pure equilibria)"],
        limits=["Real actors are boundedly rational", "Payoffs are often guesses — check robustness",
                "Repeated interaction changes incentives (see Cooperation)"],
        examples=["Price war", "Market entry", "Negotiation"],
        use_cases=["Anticipate competitor responses", "Find stable outcomes"],
        params=[
            ParamSpec(name="row_labels", label="Row player options", type="labels", default=["High price", "Low price"]),
            ParamSpec(name="col_labels", label="Column player options", type="labels", default=["High price", "Low price"]),
            ParamSpec(name="payoff_row", label="Row player payoffs", type="matrix", default=[[10, 2], [14, 5]]),
            ParamSpec(name="payoff_col", label="Column player payoffs", type="matrix", default=[[10, 14], [2, 5]]),
        ],
        primary_metric="equilibrium_welfare", primary_goal="maximize", mc_draws=300,
        tags={"strategy": 1.0, "competition": 1.0, "negotiation": 0.8, "pricing": 0.6},
        min_actors=2, needs_time=False, data_need="low", perspective="strategic",
    )

    def check(self, p):
        A, B = np.array(p["payoff_row"]), np.array(p["payoff_col"])
        shape = (len(p["row_labels"]), len(p["col_labels"]))
        if A.shape != shape or B.shape != shape:
            raise ParamError(f"payoff matrices must be {shape[0]}x{shape[1]}")

    def compute(self, p, rng):
        A, B, rl, cl = np.array(p["payoff_row"]), np.array(p["payoff_col"]), p["row_labels"], p["col_labels"]
        nash = [(i, j) for i, j in itertools.product(range(A.shape[0]), range(A.shape[1]))
                if A[i, j] >= A[:, j].max() and B[i, j] >= B[i, :].max()]
        dom_r = next((rl[i] for i in range(A.shape[0]) if all((A[i] >= A[k]).all() for k in range(A.shape[0]))), None)
        dom_c = next((cl[j] for j in range(B.shape[1]) if all((B[:, j] >= B[:, k]).all() for k in range(B.shape[1]))), None)

        def dominated(i, j):
            return bool(((A >= A[i, j]) & (B >= B[i, j]) & ((A > A[i, j]) | (B > B[i, j]))).any())

        metrics = {"pure_nash_count": len(nash), "equilibrium": "/".join((rl[nash[0][0]], cl[nash[0][1]])) if nash else "none",
                   "dominant_row": dom_r, "dominant_col": dom_c, "mixed_row_p_first": None, "mixed_col_q_first": None}
        warnings = []
        if nash:
            i, j = nash[0]
            metrics["equilibrium_pareto_dominated"] = dominated(i, j)
            metrics["equilibrium_welfare"] = float(A[i, j] + B[i, j])
            if len(nash) > 1:
                warnings.append("Multiple pure equilibria: coordination problem; outcome depends on expectations.")
        else:
            metrics["equilibrium_pareto_dominated"] = None
            metrics["equilibrium_welfare"] = None
        if A.shape == (2, 2):
            dq = A[0, 0] - A[0, 1] - A[1, 0] + A[1, 1]
            dp = B[0, 0] - B[1, 0] - B[0, 1] + B[1, 1]
            if dq != 0 and dp != 0:
                q = (A[1, 1] - A[0, 1]) / dq
                pr = (B[1, 1] - B[1, 0]) / dp
                if 0 < q < 1 and 0 < pr < 1:
                    metrics["mixed_row_p_first"], metrics["mixed_col_q_first"] = float(pr), float(q)
                    if not nash:
                        probs = np.outer([pr, 1 - pr], [q, 1 - q])
                        metrics["equilibrium_welfare"] = float(((A + B) * probs).sum())
        dilemma = bool(metrics["equilibrium_pareto_dominated"])
        table = [{"row": rl[i], "col": cl[j], "payoff_row": A[i, j], "payoff_col": B[i, j], "nash": (i, j) in nash,
                  "pareto_dominated": dominated(i, j)} for i, j in itertools.product(range(A.shape[0]), range(A.shape[1]))]
        best = max(table, key=lambda r: r["payoff_row"] + r["payoff_col"])
        return ModelOutput(
            metrics=metrics, tables={"outcomes": table},
            series=[Series(name="Welfare per outcome", x=[f"{r['row']}/{r['col']}" for r in table],
                           y=[float(r["payoff_row"] + r["payoff_col"]) for r in table], kind="bar")],
            claims=[Claim(dimension="cooperation", direction=-1 if dilemma else 1,
                          statement="Equilibrium is Pareto-inefficient (social dilemma)" if dilemma else
                          "Equilibrium is efficient or no dilemma"),
                    Claim(dimension="predictability", direction=1 if len(nash) == 1 else -1,
                          statement=f"{len(nash)} pure equilibria")],
            interpretation=[Statement(text=(f"Stable outcome: {metrics['equilibrium']}. " if nash else
                                            "No stable pure outcome; players randomise. ")
                                      + ("Both would be better off at "
                                         f"{best['row']}/{best['col']} — a social dilemma." if dilemma else ""))],
            recommendations=[Recommendation(
                title="Change the game, not the move" if dilemma else "Commit early to your equilibrium strategy",
                rationale="Individually rational choices lead to a collectively worse outcome." if dilemma else
                "The equilibrium is self-enforcing.",
                expected_impact=f"Move toward {best['row']}/{best['col']} (welfare {fmt(best['payoff_row'] + best['payoff_col'])}).",
                prerequisites=["Validate payoffs with the actors' real incentives"],
                risks=["Payoff estimates wrong → equilibrium wrong"], horizon="medium",
                actions=["Look for repeated interaction, contracts or side payments", "Check robustness via Monte Carlo"])],
            warnings=warnings, log=[f"best-response scan over {A.size} outcomes, pure NE={nash}"],
        )

    def perturb(self, p, rng, band):
        A, B = np.array(p["payoff_row"], float), np.array(p["payoff_col"], float)
        scale = max(np.ptp(np.concatenate([A.ravel(), B.ravel()])), 1e-9) * band
        return p | {"payoff_row": (A + rng.normal(0, scale, A.shape)).tolist(),
                    "payoff_col": (B + rng.normal(0, scale, B.shape)).tolist()}


class CooperationModel(Model):
    spec = ModelSpec(
        key="cooperation", number=18, name="Cooperation Models", family="C",
        summary="Repeated interaction can make cooperation self-enforcing.",
        description="Repeated prisoner's dilemma with continuation probability δ: grim-trigger condition and "
                    "a round-robin tournament of classic strategies (Axelrod).",
        math=r"\text{Cooperation sustainable} \iff \delta\ge\frac{T-R}{T-P},\quad T>R>P>S",
        assumptions=["Payoffs follow T > R > P > S", "Players value the future with factor δ", "Moves are observed"],
        prerequisites=["Rough payoff ranking and how likely the relationship continues"],
        limits=["No noise or misperception in this version", "Two-player abstraction"],
        examples=["Supplier relationship", "Cartel stability", "Team collaboration"],
        use_cases=["Design partnerships", "Assess trust stability"],
        params=[
            ParamSpec(name="T", label="Temptation T", default=5.0, uncertain=True),
            ParamSpec(name="R", label="Reward R", default=3.0, uncertain=True),
            ParamSpec(name="P", label="Punishment P", default=1.0, uncertain=True),
            ParamSpec(name="S", label="Sucker S", default=0.0),
            ParamSpec(name="delta", label="Continuation probability δ", default=0.7, min=0, max=0.999, uncertain=True),
        ],
        primary_metric="cooperation_margin", primary_goal="maximize",
        tags={"cooperation": 1.0, "trust": 1.0, "repeated": 1.0, "partnership": 0.9, "strategy": 0.5},
        min_actors=2, needs_time=True, data_need="low", perspective="strategic",
    )
    STRATEGIES = ("Always cooperate", "Always defect", "Tit for tat", "Grim trigger")

    def check(self, p):
        if not p["T"] > p["R"] > p["P"] > p["S"]:
            raise ParamError("payoffs must satisfy T > R > P > S")

    @staticmethod
    def move(name, own, other):
        if name == "Always cooperate":
            return "C"
        if name == "Always defect":
            return "D"
        if name == "Tit for tat":
            return other[-1] if other else "C"
        return "D" if "D" in other else "C"

    def compute(self, p, rng):
        T, R, P, S, d = p["T"], p["R"], p["P"], p["S"], p["delta"]
        pay = {("C", "C"): R, ("C", "D"): S, ("D", "C"): T, ("D", "D"): P}
        crit = (T - R) / (T - P)
        rounds = min(2000, int(math.log(1e-6) / math.log(d)) + 1) if d > 0 else 1
        score = {s: 0.0 for s in self.STRATEGIES}
        for a, b in itertools.product(self.STRATEGIES, repeat=2):
            ha, hb, total = [], [], 0.0
            for t in range(rounds):
                ma, mb = self.move(a, ha, hb), self.move(b, hb, ha)
                total += d**t * pay[(ma, mb)]
                ha.append(ma)
                hb.append(mb)
            score[a] += total / len(self.STRATEGIES)
        ranking = sorted(score.items(), key=lambda kv: -kv[1])
        ok = d >= crit
        return ModelOutput(
            metrics={"critical_delta": crit, "cooperation_sustainable": ok, "cooperation_margin": d - crit,
                     "best_strategy": ranking[0][0], "expected_rounds": 1 / (1 - d)},
            tables={"tournament": [{"strategy": s, "avg_discounted_payoff": round(v, 3)} for s, v in ranking]},
            series=[Series(name="Tournament score", x=[s for s, _ in ranking], y=[v for _, v in ranking], kind="bar")],
            claims=[Claim(dimension="cooperation", direction=1 if ok else -1,
                          statement=f"δ = {d:.2f} {'≥' if ok else '<'} critical {crit:.2f}")],
            interpretation=[Statement(text=f"Cooperation is {'self-enforcing' if ok else 'not stable'}: the "
                                           f"shadow of the future (δ={d:.2f}) {'exceeds' if ok else 'is below'} the "
                                           f"critical value {crit:.2f}. Best tournament strategy: {ranking[0][0]}.")],
            recommendations=[Recommendation(
                title="Lengthen the shadow of the future" if not ok else "Reciprocate: cooperate, retaliate, forgive",
                rationale=f"Critical continuation probability {crit:.2f}.",
                expected_impact="Makes cooperation the rational choice for both sides.",
                prerequisites=["Visible behaviour of both sides"], risks=["Misread signals trigger retaliation spirals"],
                horizon="long", actions=["Use long-term contracts or frequent interactions",
                                         "Reduce the temptation payoff T (e.g. penalties)"])],
            log=[f"critical δ = (T-R)/(T-P) = {crit:.6f}", f"tournament: {rounds} discounted rounds per match"],
        )


class CollectiveActionModel(Model):
    spec = ModelSpec(
        key="collective_action", number=19, name="Collective Action Problems", family="C",
        summary="Everyone gains from contributions, but each prefers to free-ride.",
        description="Linear public goods game: contributions are multiplied and shared equally. If the "
                    "multiplier is below the group size, free-riding is individually dominant.",
        math=r"\pi_i=e-c_i+\frac{r}{n}\sum_j c_j,\quad \text{MPCR}=\frac{r}{n}<1<r\ \Rightarrow\ \text{dilemma}",
        assumptions=["Contributions are all-or-nothing", "Benefits are shared equally", "Self-interested actors"],
        prerequisites=["Group size, return on pooled contributions"],
        limits=["Ignores social norms, punishment and reputation (they raise contributions in practice)"],
        examples=["Industry standard funding", "Shared infrastructure", "Climate mitigation"],
        use_cases=["Design incentives for joint projects"],
        params=[
            ParamSpec(name="players", label="Group size n", type="int", default=8, min=2, max=100000),
            ParamSpec(name="multiplier", label="Multiplier r", default=2.4, min=0, uncertain=True),
            ParamSpec(name="endowment", label="Endowment per actor", default=100.0, min=0),
            ParamSpec(name="contribution_share", label="Share of contributors", default=0.4, min=0, max=1, uncertain=True),
        ],
        primary_metric="efficiency", primary_goal="maximize",
        tags={"collective": 1.0, "public_good": 1.0, "free_riding": 1.0, "cooperation": 0.7, "policy": 0.6},
        min_actors=2, needs_time=False, data_need="low", perspective="strategic",
    )

    def compute(self, p, rng):
        n, r, e, s = p["players"], p["multiplier"], p["endowment"], p["contribution_share"]
        k = round(n * s)
        pot = r * e * k / n
        contributor, rider = pot, e + pot
        avg = (k * contributor + (n - k) * rider) / n
        optimum = r * e if r > 1 else e
        dilemma = r < n and r > 1
        eff = avg / optimum if optimum else 1.0
        return ModelOutput(
            metrics={"mpcr": r / n, "free_riding_dominant": r < n, "social_dilemma": dilemma, "optimum_payoff": optimum,
                     "nash_payoff": e if r < n else r * e, "average_payoff": avg, "contributor_payoff": contributor,
                     "free_rider_payoff": rider, "efficiency": eff},
            series=[Series(name="Average payoff vs. contributor share", x=[i / 20 for i in range(21)],
                           y=[e + (r - 1) * e * i / 20 for i in range(21)], x_label="Contributor share", y_label="Payoff")],
            claims=[Claim(dimension="cooperation", direction=-1 if dilemma else 1,
                          statement=f"MPCR = {r / n:.2f}: {'free-riding pays individually' if dilemma else 'no dilemma'}")],
            interpretation=[Statement(text=f"Each unit contributed returns {r / n:.2f} to the contributor but {fmt(r)} "
                                           f"to the group. Current efficiency {eff:.0%} of the optimum.")],
            recommendations=[Recommendation(
                title="Add selective incentives or enforcement" if dilemma else "Coordinate contributions",
                rationale=f"Free-riders earn {fmt(rider - contributor)} more than contributors.",
                expected_impact=f"Raises average payoff from {fmt(avg)} towards {fmt(optimum)}.",
                prerequisites=["Contributions are observable"], risks=["Enforcement costs exceed gains"],
                horizon="medium", actions=["Make contributions visible", "Introduce matching or penalties",
                                           "Shrink the group (higher MPCR)"])],
            log=[f"k = {k} contributors, pot share = {pot:.4f}"],
        )


class BanditModel(Model):
    spec = ModelSpec(
        key="bandit", number=23, name="Multi-Armed Bandit Models", family="C",
        summary="Balance exploring uncertain options with exploiting the best known one.",
        description="Bernoulli bandit simulation comparing random choice, ε-greedy, UCB1 and Thompson sampling "
                    "by cumulative regret against always choosing the best option.",
        math=r"\text{Regret}(T)=T\mu^*-\sum_{t=1}^T\mu_{a_t},\quad \text{UCB1: } \bar x_a+\sqrt{2\ln t/n_a}",
        assumptions=["Each option has a fixed success probability", "Feedback after every trial", "Options are independent"],
        prerequisites=["Candidate options and rough prior success rates"],
        limits=["Stationary rewards only", "True success rates are assumptions used to score strategies"],
        examples=["A/B/n testing of offers", "Choosing suppliers", "R&D portfolio"],
        use_cases=["Experiment design", "Allocation under uncertainty"],
        params=[
            ParamSpec(name="arm_means", label="Assumed success rate per option", type="vector",
                      default=[0.04, 0.05, 0.065], min=0, max=1),
            ParamSpec(name="horizon", label="Trials", type="int", default=1000, min=10, max=20000),
            ParamSpec(name="epsilon", label="ε (exploration rate)", default=0.1, min=0, max=1, uncertain=True),
            ParamSpec(name="runs", label="Simulation runs", type="int", default=20, min=1, max=500),
        ],
        primary_metric="regret_thompson", primary_goal="minimize", mc_draws=40,
        mc_params={"runs": 4, "horizon": 500},
        tags={"exploration": 1.0, "learning": 0.8, "experiment": 1.0, "uncertainty": 0.5, "options": 0.8},
        needs_time=True, data_need="low", perspective="learning",
    )

    def check(self, p):
        if len(p["arm_means"]) < 2:
            raise ParamError("need at least 2 options")

    def compute(self, p, rng):
        mu, T, eps, runs = np.array(p["arm_means"]), p["horizon"], p["epsilon"], p["runs"]
        k = len(mu)
        regret = {}
        rows = np.arange(runs)
        for name in ("random", "epsilon_greedy", "ucb1", "thompson"):
            n, wins, reg = np.zeros((runs, k)), np.zeros((runs, k)), np.zeros(T)
            for t in range(T):
                if name == "random":
                    a = rng.integers(k, size=runs)
                elif name == "epsilon_greedy":
                    explore = (rng.random(runs) < eps) | (t < k)
                    a = np.where(explore, rng.integers(k, size=runs), np.argmax(wins / np.maximum(n, 1), axis=1))
                elif name == "ucb1":
                    a = np.full(runs, t) if t < k else np.argmax(wins / n + np.sqrt(2 * math.log(t) / n), axis=1)
                else:
                    a = np.argmax(rng.beta(wins + 1, n - wins + 1), axis=1)
                n[rows, a] += 1
                wins[rows, a] += rng.random(runs) < mu[a]
                reg[t] = (mu.max() - mu[a]).mean()
            regret[name] = reg
        curves = {s: np.cumsum(v) for s, v in regret.items()}
        final = {s: float(c[-1]) for s, c in curves.items()}
        best = min((s for s in final if s != "random"), key=final.get)
        idx = list(range(0, T, max(1, T // 100)))
        return ModelOutput(
            metrics={f"regret_{s}": v for s, v in final.items()} | {"best_strategy": best, "best_arm": int(np.argmax(mu)),
                                                                    "regret_saved_vs_random": final["random"] - final[best]},
            series=[Series(name=s, x=idx, y=[float(c[i]) for i in idx], x_label="Trial", y_label="Cumulative regret")
                    for s, c in curves.items()],
            claims=[Claim(dimension="leverage", direction=1,
                          statement=f"Adaptive allocation saves {final['random'] - final[best]:.1f} successes vs. random")],
            interpretation=[Statement(text=f"Best strategy: {best} with regret {final[best]:.1f} vs. {final['random']:.1f} "
                                           f"for uniform allocation over {T} trials.")],
            recommendations=[Recommendation(
                title=f"Allocate trials adaptively ({best.replace('_', ' ')})",
                rationale="Fixed equal splits waste trials on inferior options.",
                expected_impact=f"≈ {final['random'] - final[best]:.0f} more successes per {T} trials.",
                prerequisites=["Fast, measurable feedback per trial"], risks=["Non-stationary rewards mislead the bandit"],
                horizon="short", actions=["Instrument success per option", "Run Thompson sampling with a small floor of exploration"])],
            log=[f"{runs} runs x {T} trials x 4 strategies"],
        )

    def perturb(self, p, rng, band):
        mu = np.clip(np.array(p["arm_means"]) * np.exp(rng.normal(0, band, len(p["arm_means"]))), 0, 1)
        return super().perturb(p, rng, band) | {"arm_means": mu.tolist()}


MODELS = [MarkovModel(), SystemDynamicsModel(), ThresholdModel(), GameTheoryModel(), CooperationModel(),
          CollectiveActionModel(), BanditModel()]
