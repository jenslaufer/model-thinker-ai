"""Plain-language layer: what each model asks, what its numbers mean, and one sentence on its result.

Text only rephrases computed metrics and the parameters used; it never adds numbers.
Every implemented model needs an entry (enforced by tests/test_answer.py).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .base import fmt

Params = dict[str, Any]
Metrics = dict[str, Any]


@dataclass(frozen=True)
class Plain:
    question: str
    text: Callable[[Params, Metrics], str]
    # Metric key -> meaning. A key ending in "*" matches every metric with that prefix.
    help: dict[str, str] = field(default_factory=dict)


def _n(x: Any) -> str:
    return fmt(float(x)) if isinstance(x, int | float) and not isinstance(x, bool) else str(x)


def _pct(x: Any) -> str:
    if x is None:
        return "unknown"
    x = float(x)
    if 0 < x < 0.01:
        return "under 1%"
    if 0.99 < x < 1:
        return "over 99%"
    return f"{x:.0%}"


def _known(x: Any) -> bool:
    return x is not None and (not isinstance(x, float) or math.isfinite(x))


def _when(x: Any, then: str) -> str:
    return then.format(_n(x)) if _known(x) else ""


def _normal(p: Params, m: Metrics) -> str:
    return (f"The typical outcome is about {_n(p['mu'])}; in 9 of 10 cases it lands between {_n(m['q05'])} and "
            f"{_n(m['q95'])}. The chance of ending above {_n(p['threshold'])} is {_pct(m['p_above'])}, "
            f"below it {_pct(m['p_below'])}.")


def _power_law(p: Params, m: Metrics) -> str:
    return (f"A few big cases dominate: the largest {_pct(p['top_fraction'])} make up {_pct(m['top_share'])} of the "
            f"total. A case 10 times the smallest one has a {_pct(m['p_exceed_10x'])} chance, 100 times "
            f"{_pct(m['p_exceed_100x'])}.")


def _linear(p: Params, m: Metrics) -> str:
    text = (f"Each period changes the value by about {_n(m['slope'])}. If the trend holds, after {_n(p['horizon'])} "
            f"more periods it is about {_n(m['forecast'])}")
    if _known(m.get("forecast_lo")) and _known(m.get("forecast_hi")):
        text += f" (likely between {_n(m['forecast_lo'])} and {_n(m['forecast_hi'])})"
    text += "."
    r2 = m.get("r2")
    if r2 is not None and r2 < 0.5:
        text += " The straight line fits the data poorly, so treat this with caution."
    return text


def _network(p: Params, m: Metrics) -> str:
    hubs = " A few well-connected hubs carry most links." if m["top10_degree_share"] > 0.25 else ""
    return (f"{_pct(m['giant_component_share'])} of the {_n(p['n'])} actors can reach each other"
            f"{_when(m.get('avg_path_length'), ', on average in {} steps')}. The best-connected 10% hold "
            f"{_pct(m['top10_degree_share'])} of all contacts.{hubs}")


def _diffusion(p: Params, m: Metrics) -> str:
    driver = ("Word of mouth drives growth more than advertising." if m["q_over_p"] > 1
              else "Advertising drives growth more than word of mouth.")
    return (f"Of {_n(p['market_size'])} potential adopters, {_n(m['adopters_at_horizon'])} "
            f"({_pct(m['share_at_horizon'])}) have adopted after {_n(p['periods'])} periods."
            f"{_when(m.get('peak_time'), ' New adoptions peak around period {}.')} {driver}")


def _entropy(p: Params, m: Metrics) -> str:
    spread = "fairly evenly spread" if m["normalized_entropy"] >= 0.8 else "a few categories dominate"
    return (f"The {len(p['probabilities'])} categories behave like {_n(m['effective_categories'])} equally sized "
            f"ones — {spread}. The largest holds {_pct(m['max_share'])} of the total.")


def _random_walk(p: Params, m: Metrics) -> str:
    start, thr = p["start"], p["threshold"]
    crossing = "drops to {} or below" if thr < start else "reaches {}"
    return (f"Starting at {_n(start)}, after {_n(p['steps'])} periods the value ends between {_n(m['q05_final'])} "
            f"and {_n(m['q95_final'])} in 9 of 10 simulated futures (on average {_n(m['mean_final'])}). In "
            f"{_pct(m['p_hit_threshold'])} of them it {crossing.format(_n(thr))} at some point.")


def _markov(p: Params, m: Metrics) -> str:
    states = p["states"]
    target = states[p["target_state"]]
    others = ", ".join(f"'{s}' {_pct(m.get(f'stationary_{s}'))}" for s in states if s != target)
    count = (f" — about {_n(m['final_target_count'])} of {_n(p['population'])}"
             if _known(m.get("final_target_count")) else "")
    return (f"In the long run {_pct(m['stationary_target'])} end up in '{target}' (after {_n(p['steps'])} periods: "
            f"{_pct(m['final_target'])}{count}). The rest settle in {others}."
            f"{_when(m.get('mixing_steps'), ' This balance is reached after about {} periods.')}")


def _system_dynamics(p: Params, m: Metrics) -> str:
    start = ("Early on, growth feeds more growth." if m["dominant_loop_at_start"] == "reinforcing"
             else "Limits hold growth back from the start.")
    if not _known(m.get("equilibrium")):
        return (f"The quantity moves from {_n(p['initial_stock'])} to {_n(m['final_stock'])} after "
                f"{_n(p['horizon'])} periods and has no balance point: it keeps changing. {start}")
    return (f"The quantity moves from {_n(p['initial_stock'])} toward a balance of about {_n(m['equilibrium'])} and "
            f"stands at {_n(m['final_stock'])} after {_n(p['horizon'])} periods."
            f"{_when(m.get('time_to_90pct_eq'), ' It gets 90% of the way there after {} periods.')} {start}")


def _threshold(p: Params, m: Metrics) -> str:
    outcome = "it tips over" if m["tipped"] else "it stalls"
    text = (f"Starting with {_pct(p['initial_share'])} on board, {outcome}: {_pct(m['final_share'])} join in after "
            f"{_n(m['rounds'])} rounds.")
    if m.get("critical_initial_share") is not None:
        text += f" About {_pct(m['critical_initial_share'])} early adopters are enough to tip the group."
    return text


def _game_theory(p: Params, m: Metrics) -> str:
    if not m["pure_nash_count"]:
        return "There is no stable choice: each side keeps switching to counter the other."
    trap = (" Both sides would do better with a different choice — a trap neither escapes alone."
            if m.get("equilibrium_pareto_dominated") else "")
    return f"When each side picks its best response, it settles at {m['equilibrium']}.{trap}"


def _cooperation(p: Params, m: Metrics) -> str:
    verdict = ("Cooperation can last" if m["cooperation_sustainable"] else "Cooperation breaks down")
    return (f"{verdict}: the chance of meeting again ({_pct(p['delta'])}) is "
            f"{'above' if m['cooperation_sustainable'] else 'below'} the {_pct(m['critical_delta'])} needed for "
            f"cooperation to pay off. On average the sides meet {_n(m['expected_rounds'])} times.")


def _collective_action(p: Params, m: Metrics) -> str:
    free = ", so for each individual free-riding pays" if m["free_riding_dominant"] else ""
    return (f"Each unit someone contributes gives {_n(m['mpcr'])} back to them but {_n(p['multiplier'])} to the "
            f"group{free}. The group reaches {_pct(m['efficiency'])} of what it would get if everyone contributed.")


STRATEGY = {"thompson": "learn as you go (Thompson sampling)", "ucb1": "try the most promising unknown (UCB1)",
            "epsilon_greedy": "mostly the best so far, sometimes explore (ε-greedy)", "random": "pick at random"}


def _bandit(p: Params, m: Metrics) -> str:
    best = m["best_strategy"]
    return (f"Best way to split {_n(p['horizon'])} tries: {STRATEGY.get(best, best)}. It gives up about "
            f"{_n(m[f'regret_{best}'])} successes for not knowing the best option in advance, versus "
            f"{_n(m['regret_random'])} when picking at random. Option {m['best_arm'] + 1} looks best.")


_REGRET = "Successes lost by not knowing the best option in advance, with this strategy"

PLAIN: dict[str, Plain] = {
    "normal": Plain("What range of outcomes is normal, and how often is a critical line crossed?", _normal, {
        "p_above": "Chance the outcome ends above the critical threshold",
        "p_below": "Chance the outcome ends below the critical threshold",
        "z_threshold": "Distance of the threshold from the average, in standard deviations (beyond 2 is rare)",
        "q05": "Only 5% of outcomes are lower than this", "q50": "Middle outcome: half are higher, half lower",
        "q95": "Only 5% of outcomes are higher than this"}),
    "power_law": Plain("Do a few big cases dominate the total?", _power_law, {
        "top_share": "Share of the total held by the largest cases",
        "mean": "Average size — pulled up by rare giants", "median": "Typical size: half are smaller",
        "p_exceed_10x": "Chance a case is at least 10 times the smallest",
        "p_exceed_100x": "Chance a case is at least 100 times the smallest"}),
    "linear": Plain("If the current trend continues, where will it be?", _linear, {
        "intercept": "Level of the trend line at the start", "slope": "Change per period",
        "r2": "How well a straight line fits the data (1 = perfectly, 0 = not at all)",
        "forecast": "Projected value at the end of the horizon",
        "forecast_lo": "Low end of the likely range", "forecast_hi": "High end of the likely range"}),
    "network": Plain("How connected are the people involved, and through whom does everything flow?", _network, {
        "avg_degree": "Average number of contacts per actor", "max_degree": "Contacts of the best-connected actor",
        "avg_clustering": "How often an actor's contacts also know each other (0–1)",
        "avg_path_length": "Average number of steps between two actors",
        "giant_component_share": "Share of actors connected to the main group",
        "top10_degree_share": "Share of all contacts held by the best-connected 10%"}),
    "diffusion": Plain("How fast does something spread through a market?", _diffusion, {
        "adopters_at_horizon": "People who have adopted by the end",
        "share_at_horizon": "Share of the market that has adopted by the end",
        "peak_time": "Period with the most new adopters", "time_to_50pct": "Period by which half have adopted",
        "q_over_p": "Word of mouth vs. advertising (above 1: word of mouth is stronger)"}),
    "entropy": Plain("How evenly is something spread across categories?", _entropy, {
        "entropy_bits": "Evenness measured in bits (higher = more even)",
        "max_entropy": "Evenness if all categories were equal",
        "normalized_entropy": "Evenness from 0 (all in one category) to 1 (perfectly even)",
        "hhi": "Concentration index (1 = everything in one category)",
        "effective_categories": "Number of equal-sized categories that would give the same spread",
        "max_share": "Share of the largest category"}),
    "random_walk": Plain("Starting from today, how far can things drift, and how likely is a critical level?",
                         _random_walk, {
        "mean_final": "Average value at the end", "sd_final": "Typical spread of the end value",
        "q05_final": "Only 5% of futures end lower than this", "q95_final": "Only 5% of futures end higher than this",
        "p_hit_threshold": "Chance of touching the critical level at least once",
        "p_final_below_start": "Chance of ending below the starting value",
        "analytic_mean": "Average end value by formula (cross-check of the simulation)",
        "analytic_sd": "Spread of the end value by formula (cross-check)"}),
    "markov": Plain("Where do things settle when they keep switching between states?", _markov, {
        "stationary_*": "Long-run share in this state", "final_*": "Share in this state at the end of the horizon",
        "final_target": "Share in the state of interest at the end of the horizon",
        "stationary_target": "Long-run share in the state of interest",
        "final_target_count": "Number in the state of interest at the end of the horizon",
        "stationary_target_count": "Long-run number in the state of interest",
        "mixing_steps": "Periods until the long-run balance is reached"}),
    "system_dynamics": Plain("How does a quantity grow or shrink when it feeds back on itself?", _system_dynamics, {
        "final_stock": "Level at the end of the horizon", "equilibrium": "Level where inflow and outflow balance",
        "peak_stock": "Highest level reached", "time_to_90pct_eq": "Periods to get 90% of the way to the balance",
        "dominant_loop_at_start": "Which force wins at first: growth feeding growth, or limits",
        "net_growth_rate": "Growth rate after outflows"}),
    "threshold": Plain("Does a small start tip everyone over, or does it fizzle out?", _threshold, {
        "final_share": "Share that has joined in the end", "rounds": "Rounds until nothing changes any more",
        "tipped": "Whether the group tipped over", "critical_initial_share": "Smallest start that tips the group"}),
    "game_theory": Plain("When each side picks its best move, where does it end up?", _game_theory, {
        "pure_nash_count": "Number of stable outcomes where no side wants to switch",
        "equilibrium": "The stable outcome", "dominant_row": "Row player's best choice whatever the other does",
        "dominant_col": "Column player's best choice whatever the other does",
        "mixed_row_p_first": "How often the row player picks the first option when mixing",
        "mixed_col_q_first": "How often the column player picks the first option when mixing",
        "equilibrium_pareto_dominated": "Whether both would be better off with another outcome",
        "equilibrium_welfare": "Combined payoff at the stable outcome"}),
    "cooperation": Plain("Will both sides keep cooperating when they meet again and again?", _cooperation, {
        "critical_delta": "Minimum chance of meeting again for cooperation to pay off",
        "cooperation_sustainable": "Whether cooperation can last",
        "cooperation_margin": "How far the chance of meeting again exceeds the minimum",
        "best_strategy": "Strategy that scored best in a simulated tournament",
        "expected_rounds": "Average number of encounters"}),
    "collective_action": Plain("Will people chip in for a shared good, or free-ride?", _collective_action, {
        "mpcr": "What one unit contributed returns to the contributor",
        "free_riding_dominant": "Whether not contributing pays for each individual",
        "social_dilemma": "Whether individual and group interest clash",
        "optimum_payoff": "Payoff per person if everyone contributes",
        "nash_payoff": "Payoff per person if nobody contributes", "average_payoff": "Average payoff now",
        "contributor_payoff": "Payoff of someone who contributes", "free_rider_payoff": "Payoff of a free-rider",
        "efficiency": "Share of the best possible group result that is reached"}),
    "bandit": Plain("How should you split tries between options you are still learning about?", _bandit, {
        "regret_*": _REGRET, "best_strategy": "Strategy that loses the least",
        "best_arm": "The option that is actually best (counted from 0)",
        "regret_saved_vs_random": "Successes the best strategy saves compared with picking at random"}),
}


def plain_text(key: str, params: Params, metrics: Metrics) -> str:
    return PLAIN[key].text(params, metrics)


def explain_metric(key: str, metric: str) -> str:
    entry = PLAIN.get(key)
    if entry is None:
        return ""
    if metric in entry.help:
        return entry.help[metric]
    return next((v for k, v in entry.help.items() if k.endswith("*") and metric.startswith(k[:-1])), "")
