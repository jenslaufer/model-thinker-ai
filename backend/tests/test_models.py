"""Model tests against analytic reference solutions, limits and reproducibility."""

import math

import pytest

from app.modeling.base import ParamError
from app.modeling.registry import REGISTRY, get_model, implemented_models


def run(key, seed=42, **params):
    return get_model(key).run(params, seed=seed)


# --- registry -------------------------------------------------------------


def test_catalog_has_all_24_families():
    numbers = sorted(spec.number for spec in REGISTRY.specs())
    assert numbers == list(range(1, 25))


def test_at_least_five_models_implemented():
    assert len(implemented_models()) >= 5


@pytest.mark.parametrize("key", [m.spec.key for m in implemented_models()])
def test_every_model_runs_with_defaults_and_documents_itself(key):
    model = get_model(key)
    spec = model.spec
    assert spec.math and spec.assumptions and spec.limits and spec.examples
    out = model.run()
    assert out.metrics
    assert out.log, "calculation protocol missing"
    if spec.primary_metric:
        assert spec.primary_metric in out.metrics
    for v in out.metrics.values():
        if isinstance(v, float):
            assert math.isfinite(v)


@pytest.mark.parametrize("key", [m.spec.key for m in implemented_models()])
def test_every_model_is_reproducible(key):
    a = get_model(key).run(seed=7)
    b = get_model(key).run(seed=7)
    assert a.metrics == b.metrics


def test_unknown_parameter_rejected():
    with pytest.raises(ParamError):
        run("normal", foo=1)


def test_bounds_enforced():
    with pytest.raises(ParamError):
        run("normal", sigma=-1)


# --- 1 normal ---------------------------------------------------------------


def test_normal_tail_probability():
    out = run("normal", mu=0, sigma=1, threshold=1.959964)
    assert out.metrics["p_above"] == pytest.approx(0.025, abs=1e-5)
    assert out.metrics["q50"] == pytest.approx(0.0)
    assert out.metrics["q95"] == pytest.approx(1.644854, abs=1e-5)


# --- 2 power law ------------------------------------------------------------


def test_power_law_80_20():
    alpha = math.log(5) / math.log(4)  # Pareto index that produces 80/20
    out = run("power_law", alpha=alpha, x_min=1, top_fraction=0.2)
    assert out.metrics["top_share"] == pytest.approx(0.8, abs=1e-6)
    assert out.metrics["median"] == pytest.approx(2 ** (1 / alpha))
    assert out.metrics["p_exceed_10x"] == pytest.approx(10**-alpha)


def test_power_law_infinite_mean_flagged():
    out = run("power_law", alpha=0.9, x_min=1)
    assert out.metrics["mean"] is None
    assert any("mean" in w.lower() for w in out.warnings)


# --- 3 linear ---------------------------------------------------------------


def test_linear_exact_fit():
    out = run("linear", data_x=[0, 1, 2, 3, 4], data_y=[1, 3, 5, 7, 9], horizon=10)
    assert out.metrics["slope"] == pytest.approx(2)
    assert out.metrics["intercept"] == pytest.approx(1)
    assert out.metrics["r2"] == pytest.approx(1)
    assert out.metrics["forecast"] == pytest.approx(2 * 14 + 1)  # 10 periods after last x=4


def test_linear_without_data_is_an_assumption_projection():
    out = run("linear", data_x=[], data_y=[], baseline=100, slope=5, horizon=4)
    assert out.metrics["forecast"] == pytest.approx(120)
    assert out.metrics["r2"] is None
    assert any("assum" in w.lower() for w in out.warnings)


def test_linear_rejects_mismatched_data():
    with pytest.raises(ParamError):
        run("linear", data_x=[1, 2, 3], data_y=[1, 2])


# --- 6 network --------------------------------------------------------------


def test_network_random_graph_degree():
    out = run("network", n=400, avg_degree=6, topology="random")
    assert out.metrics["avg_degree"] == pytest.approx(6, rel=0.15)
    assert 0 < out.metrics["giant_component_share"] <= 1


def test_network_scale_free_has_hubs():
    sf = run("network", n=500, avg_degree=4, topology="scale_free")
    rnd = run("network", n=500, avg_degree=4, topology="random")
    assert sf.metrics["max_degree"] > 2 * rnd.metrics["max_degree"]


# --- 7 diffusion (Bass) -----------------------------------------------------


def test_bass_peak_time_analytic():
    p, q = 0.03, 0.38
    out = run("diffusion", p=p, q=q, market_size=1000, periods=40)
    assert out.metrics["peak_time"] == pytest.approx(math.log(q / p) / (p + q))
    f = lambda t: (1 - math.exp(-(p + q) * t)) / (1 + q / p * math.exp(-(p + q) * t))
    assert out.metrics["adopters_at_horizon"] == pytest.approx(1000 * f(40))


def test_bass_pure_broadcast_has_no_interior_peak():
    out = run("diffusion", p=0.1, q=0.0, market_size=100, periods=10)
    assert out.metrics["peak_time"] == 0


# --- 8 entropy --------------------------------------------------------------


def test_entropy_uniform_and_certain():
    assert run("entropy", probabilities=[1, 1, 1, 1]).metrics["entropy_bits"] == pytest.approx(2)
    assert run("entropy", probabilities=[1, 0, 0]).metrics["entropy_bits"] == pytest.approx(0)


# --- 9 random walk ----------------------------------------------------------


def test_random_walk_moments():
    out = run("random_walk", start=0, drift=0.5, volatility=2, steps=100, paths=4000, threshold=1000)
    assert out.metrics["mean_final"] == pytest.approx(50, abs=1.5)
    assert out.metrics["sd_final"] == pytest.approx(20, rel=0.05)
    assert out.metrics["p_hit_threshold"] == 0


def test_random_walk_zero_volatility_is_deterministic():
    out = run("random_walk", start=10, drift=1, volatility=0, steps=5, paths=10, threshold=12)
    assert out.metrics["mean_final"] == 15
    assert out.metrics["p_hit_threshold"] == 1


# --- 13 markov --------------------------------------------------------------


def test_markov_stationary_distribution():
    out = run("markov", states=["A", "B"], transition_matrix=[[0.9, 0.1], [0.5, 0.5]], initial=[0, 1], steps=200)
    assert out.metrics["stationary_A"] == pytest.approx(5 / 6)
    assert out.metrics["final_A"] == pytest.approx(5 / 6, abs=1e-6)


def test_markov_rejects_non_stochastic_matrix():
    with pytest.raises(ParamError):
        run("markov", states=["A", "B"], transition_matrix=[[0.9, 0.2], [0.5, 0.5]], initial=[1, 0])


# --- 14 system dynamics -----------------------------------------------------


def test_system_dynamics_equilibrium():
    out = run("system_dynamics", initial_stock=10, growth_rate=0.5, capacity=1000, outflow_rate=0.1,
              external_inflow=0, horizon=200)
    assert out.metrics["equilibrium"] == pytest.approx(800)
    assert out.metrics["final_stock"] == pytest.approx(800, rel=1e-3)


def test_system_dynamics_collapse_when_outflow_dominates():
    out = run("system_dynamics", initial_stock=100, growth_rate=0.1, capacity=1000, outflow_rate=0.3,
              external_inflow=0, horizon=200)
    assert out.metrics["equilibrium"] == pytest.approx(0)
    assert out.metrics["final_stock"] < 1


# --- 15 threshold -----------------------------------------------------------


def test_threshold_tipping_point():
    tip = run("threshold", population=1000, mean_threshold=0.1, sd_threshold=0, initial_share=0.15)
    stuck = run("threshold", population=1000, mean_threshold=0.1, sd_threshold=0, initial_share=0.05)
    assert tip.metrics["final_share"] == pytest.approx(1)
    assert stuck.metrics["final_share"] == pytest.approx(0.05)


# --- 17 game theory ---------------------------------------------------------


def test_game_prisoners_dilemma():
    out = run("game_theory", row_labels=["C", "D"], col_labels=["C", "D"],
              payoff_row=[[3, 0], [5, 1]], payoff_col=[[3, 5], [0, 1]])
    assert out.metrics["pure_nash_count"] == 1
    assert out.metrics["equilibrium"] == "D/D"
    assert out.metrics["equilibrium_pareto_dominated"] is True


def test_game_matching_pennies_mixed():
    out = run("game_theory", row_labels=["H", "T"], col_labels=["H", "T"],
              payoff_row=[[1, -1], [-1, 1]], payoff_col=[[-1, 1], [1, -1]])
    assert out.metrics["pure_nash_count"] == 0
    assert out.metrics["mixed_row_p_first"] == pytest.approx(0.5)
    assert out.metrics["mixed_col_q_first"] == pytest.approx(0.5)


# --- 18 cooperation ---------------------------------------------------------


def test_cooperation_critical_discount():
    out = run("cooperation", T=5, R=3, P=1, S=0, delta=0.6)
    assert out.metrics["critical_delta"] == pytest.approx(0.5)
    assert out.metrics["cooperation_sustainable"] is True
    assert run("cooperation", T=5, R=3, P=1, S=0, delta=0.4).metrics["cooperation_sustainable"] is False


# --- 19 collective action ---------------------------------------------------


def test_public_goods_free_riding():
    out = run("collective_action", players=10, multiplier=3, endowment=10, contribution_share=0)
    assert out.metrics["mpcr"] == pytest.approx(0.3)
    assert out.metrics["free_riding_dominant"] is True
    assert out.metrics["optimum_payoff"] == pytest.approx(30)
    assert out.metrics["nash_payoff"] == pytest.approx(10)


# --- 23 bandit --------------------------------------------------------------


def test_bandit_learning_beats_random():
    out = run("bandit", arm_means=[0.2, 0.5, 0.55], horizon=2000, epsilon=0.1, runs=20)
    assert out.metrics["regret_thompson"] < out.metrics["regret_random"] / 3
    assert out.metrics["regret_ucb1"] < out.metrics["regret_random"]
    assert out.metrics["best_arm"] == 2


def test_markov_counts_scale_shares():
    m = get_model("markov")
    p = m.validate({"population": 4000})
    out = m.run(p)
    assert out.metrics["final_target_count"] == pytest.approx(4000 * out.metrics["final_target"])
    assert out.metrics["stationary_target_count"] == pytest.approx(4000 * out.metrics["stationary_target"])
    assert "final_target_count" not in m.run(m.validate({})).metrics  # shares only without a population
    assert m.spec.version == "1.1.0"


def test_goal_metrics_and_levers_exist():
    from app.modeling.registry import REGISTRY
    declared = [k for k, m in REGISTRY.models.items() if m.spec.goal_metrics]
    assert {"diffusion", "markov", "system_dynamics", "linear", "random_walk"} <= set(declared)
    for key, m in REGISTRY.models.items():
        metrics = m.run(m.validate({"population": 100} if key == "markov" else {})).metrics
        assert set(m.spec.goal_metrics) <= set(metrics), key
        assert set(m.spec.levers) <= {p.name for p in m.spec.params}, key
    assert next(p for p in get_model("markov").spec.params if p.name == "transition_matrix").stochastic_rows
