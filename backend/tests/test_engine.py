import pytest

from app.engine.graph import build_graph
from app.engine.orchestrator import run_analysis
from app.engine.scenarios import monte_carlo, scenario_set, sensitivity
from app.engine.selection import select_models
from app.engine.structure import ProblemInput, structure_problem
from app.modeling.registry import get_model

LAUNCH = ProblemInput(
    description="We launch a new app. Adoption depends on word of mouth and marketing reach. "
                "Should we invest in referrals or ads? A competitor may react with a price cut.",
    objective="Maximise active users after 24 months",
    time_horizon="24 months",
    actors=["Our company", "Competitor", "Customers"],
    available_data="Monthly signups for 6 months",
    decision_scope="Budget split between referral programme and ads",
)


def test_structure_detects_types_actors_and_criteria():
    s = structure_problem(LAUNCH)
    assert s.origin == "heuristic"
    assert {"adoption", "strategy"} <= set(s.problem_types)
    assert [a.name for a in s.actors] == LAUNCH.actors
    assert set(s.criteria) == {"problem_type", "complexity", "data_availability", "actors", "temporal_dynamics",
                               "uncertainty", "interactions", "decision_relevance"}
    assert s.criteria["temporal_dynamics"] > 0.5
    assert s.criteria["decision_relevance"] > 0.5
    assert s.variables and s.subproblems


def test_structure_handles_german():
    s = structure_problem(ProblemInput(description="Wie entwickelt sich die Kundenabwanderung? "
                                                   "Kunden wechseln zwischen aktiv und inaktiv."))
    assert "churn" in s.problem_types


def test_selection_scores_and_reasons():
    sel = select_models(structure_problem(LAUNCH))
    by_key = {f.key: f for f in sel.fits}
    assert all(0 <= f.score <= 100 for f in sel.fits)
    assert all(f.reasons for f in sel.fits)
    assert by_key["diffusion"].score > by_key["entropy"].score
    assert "diffusion" in sel.selected and "game_theory" in sel.selected
    assert 3 <= len(sel.selected) <= 6
    # planned models are never selected
    assert all(by_key[k].implemented for k in sel.selected)
    assert sel.unsuitable


def test_selection_prefers_diverse_perspectives():
    sel = select_models(structure_problem(LAUNCH))
    perspectives = [next(f.perspective for f in sel.fits if f.key == k) for k in sel.selected]
    assert len(set(perspectives)) >= 3


def test_sensitivity_ranks_parameters():
    model = get_model("diffusion")
    tornado = sensitivity(model, model.validate({}), band=0.2)
    names = [t.param for t in tornado]
    assert set(names) == {"p", "q", "market_size"}
    assert tornado[0].swing >= tornado[-1].swing
    ms = next(t for t in tornado if t.param == "market_size")
    assert ms.metric_high > ms.metric_low  # linear in m


def test_scenarios_best_beats_worst():
    model = get_model("diffusion")
    sc = {s.kind: s for s in scenario_set(model, model.validate({}), band=0.2, what_if={"q": 0.6})}
    assert set(sc) == {"baseline", "best", "worst", "alternative", "stress", "what_if"}
    m = model.spec.primary_metric
    assert sc["best"].metrics[m] > sc["baseline"].metrics[m] > sc["worst"].metrics[m]
    assert sc["stress"].metrics[m] <= sc["worst"].metrics[m]
    assert sc["what_if"].params["q"] == 0.6


def test_scenarios_for_matrix_models_use_monte_carlo_quantiles():
    model = get_model("game_theory")
    sc = {s.kind: s for s in scenario_set(model, model.validate({}), band=0.2)}
    assert {"best", "worst"} <= set(sc)
    assert "quantile" in sc["best"].description


def test_monte_carlo_reproducible_with_intervals():
    model = get_model("diffusion")
    a = monte_carlo(model, model.validate({}), band=0.2, draws=200, seed=1)
    b = monte_carlo(model, model.validate({}), band=0.2, draws=200, seed=1)
    assert a.summary == b.summary
    s = a.summary[model.spec.primary_metric]
    assert s["p05"] <= s["p50"] <= s["p95"]
    assert "assumption" in a.note.lower()


def test_monte_carlo_categorical_robustness():
    model = get_model("game_theory")
    mc = monte_carlo(model, model.validate({}), band=0.05, draws=100, seed=1)
    assert 0 <= mc.categorical["equilibrium"]["baseline_share"] <= 1


def test_run_analysis_full_pipeline():
    result = run_analysis(LAUNCH)
    assert len(result.executions) >= 3
    for ex in result.executions:
        assert ex.status == "ok"
        assert ex.output.metrics
        assert ex.scenarios and ex.sensitivity is not None
        assert ex.model_version
    assert result.recommendations
    assert result.recommendations[0].priority >= result.recommendations[-1].priority
    assert all(r.source_models or r.evidence for r in result.recommendations)
    assert any(r.source_models for r in result.recommendations)
    origins = {s.origin for s in result.synthesis}
    assert "ai_interpretation" not in origins  # heuristic provider never claims AI output


def test_contradictions_are_reported_not_averaged():
    result = run_analysis(LAUNCH, selected=["normal", "random_walk", "diffusion", "threshold"],
                          overrides={"normal": {"threshold": 60}, "threshold": {"initial_share": 0.01}})
    dims = {c.dimension for c in result.comparison.contradictions}
    for c in result.comparison.contradictions:
        assert c.positive and c.negative
    assert result.comparison.table  # side-by-side metrics per model
    assert isinstance(dims, set)


def test_failed_model_does_not_break_analysis():
    result = run_analysis(LAUNCH, selected=["diffusion", "markov"],
                          overrides={"markov": {"transition_matrix": [[2, 0], [0, 1]]}})
    status = {e.model_key: e.status for e in result.executions}
    assert status == {"diffusion": "ok", "markov": "error"}


def test_graph_marks_correlation_as_non_causal():
    result = run_analysis(LAUNCH)
    g = build_graph(result)
    kinds = {n["type"] for n in g["nodes"]}
    assert {"problem", "actor", "variable", "model", "result", "scenario", "recommendation"} <= kinds
    ids = {n["id"] for n in g["nodes"]}
    assert all(e["source"] in ids and e["target"] in ids for e in g["edges"])
    for e in g["edges"]:
        if e["relation"] == "correlates":
            assert e["causal"] is False


@pytest.mark.parametrize("text", ["", "   "])
def test_empty_problem_rejected(text):
    with pytest.raises(ValueError):
        ProblemInput(description=text)


def test_evidence_has_no_false_precision():
    result = run_analysis(LAUNCH, selected=["diffusion"])
    ev = " ".join(e for r in result.recommendations for e in r.evidence)
    assert "e+" not in ev
    decimals = [tok.split(".")[1] for tok in ev.replace(",", "").split() if "." in tok and tok.replace(".", "").isdigit()]
    assert all(len(d) <= 3 for d in decimals)


def test_ai_proposal_reads_as_estimate():
    from app.engine.orchestrator import ParamValue
    p = ParamValue.model_validate({"value": 1.0, "origin": "ai_proposal", "rationale": "x"})
    assert p.origin == "ai_estimate" and p.confidence == "unknown"


def test_one_model_runs_twice_as_instances():
    r = run_analysis(LAUNCH, selected=["normal", "normal:wide"], overrides={"normal:wide": {"sigma": 30}})
    assert [e.id for e in r.executions] == ["normal", "normal:wide"]
    assert r.executions[1].params["sigma"].value == 30 and r.executions[0].params["sigma"].value != 30


def test_parse_instance():
    from app.engine.orchestrator import parse_instance
    assert parse_instance("markov") == ("markov", "markov")
    assert parse_instance("withdrawal:fat-tails") == ("withdrawal", "withdrawal:fat-tails")
    with pytest.raises(ValueError):
        parse_instance("markov:")
