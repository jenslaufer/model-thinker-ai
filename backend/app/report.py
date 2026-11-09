"""Markdown report. Every section labels its origin: computed, assumption or interpretation."""

from app.engine.answer import build_answer
from app.engine.orchestrator import AnalysisResult
from app.modeling.base import rough

ORIGIN = {"rule_interpretation": "Rule-based interpretation", "ai_interpretation": "AI interpretation",
          "computed": "Computed", "assumption": "Assumption", "user_input": "User input"}


def _v(x):
    if isinstance(x, float):
        return f"{x:.4g}"
    return "—" if x is None else str(x)


def _line(text: str) -> str:
    return " ".join(text.split())  # one line: user and AI text must not open new Markdown blocks


def _answer(r: AnalysisResult) -> list[str]:
    a = build_answer(r)
    out = ["## The answer", "", f"*{ORIGIN['rule_interpretation']} of the computed results below.*", "",
           f"**Your question:** {_line(a.question)}", "", f"**Answer:** {a.verdict.text}", "",
           f"> {a.reliability_text}", ""]
    if a.goal_results:
        out += ["| Model | Measures | Result | Range (p05–p95) |", "|---|---|---|---|"]
        out += [f"| {g.model_name} | {g.measures} | {rough(g.value)} | "
                f"{'–'.join(rough(x) for x in (g.p05, g.p95)) if g.p05 is not None and g.p95 is not None else '—'} |"
                for g in a.goal_results]
        out.append("")
    unknowns = [f"{u.label} ({u.model_name}): {u.value_text}, {u.origin.replace('_', ' ')}"
                f"{f', confidence {u.confidence}' if u.confidence else ''} — {u.effect_text}" for u in a.unknowns]
    for title, items in (("Why the models differ", a.differences), ("Biggest unknowns", unknowns),
                         ("What it would take", a.what_it_takes)):
        if items:
            out += [f"**{title}:**", *[f"- {_line(x)}" for x in items], ""]
    for f in a.other_angles:
        out += [f"**{f.model_name}** — {f.question}", "", f"{f.text} *(based on {f.data_source})*", ""]
    if a.setup.uncovered:
        out += ["**Not covered by any model:** " + "; ".join(_line(x) for x in a.setup.uncovered), ""]
    return out


def render(title: str, revision: int, r: AnalysisResult) -> str:
    s = r.structure
    out = [f"# {title}", "", (f"Revision {revision} · provider `{r.provider}` · seed {r.seed} · "
                              f"uncertainty band ±{r.band:.0%}"), "",
           ("> Legend: **Computed** = deterministic model output · **Assumption** = default or user parameter · "
           "**Interpretation** = rule-based or AI text. The Model Fit Score is a heuristic, not a probability."), "",
           "## Problem", "", r.problem.description, "", f"**Objective:** {s.objective}", ""]
    out += _answer(r)
    if s.subproblems:
        out += ["**Sub-problems:**", *[f"- {q}" for q in s.subproblems], ""]
    if s.data_gaps:
        out += ["**Data gaps:**", *[f"- {g}" for g in s.data_gaps], ""]
    out += ["## Model selection", "", "| Model | Fit score | Reasons |", "|---|---|---|"]
    fits = {f.key: f for f in r.selection.fits}
    for k in r.selection.selected:
        out.append(f"| {fits[k].name} | {fits[k].score} | {'; '.join(fits[k].reasons)} |")
    out.append("")
    for e in r.executions:
        out += [f"## {e.model_name} (v{e.model_version})", ""]
        if e.status != "ok":
            out += [f"**Execution failed:** {e.error}", ""]
            continue
        out += ["**Assumptions (parameters):**", ""]
        out += [f"- `{n}` = {_v(p.value)} — {p.origin.replace('_', ' ')}" for n, p in e.params.items()]
        out += ["", "**Computed results:**", "", "| Metric | Value |", "|---|---|"]
        out += [f"| {k} | {_v(v)} |" for k, v in e.output.metrics.items()]
        out += ["", "**Scenarios (computed):**", "", "| Scenario | Primary metric | Definition |", "|---|---|---|"]
        out += [f"| {sc.name} | {_v(sc.primary)} | {sc.description} |" for sc in e.scenarios]
        if e.monte_carlo:
            out += ["", f"_Monte Carlo ({e.monte_carlo.draws} draws): {e.monte_carlo.note}_"]
        out += ["", f"**{ORIGIN['rule_interpretation']}:** " + " ".join(st.text for st in e.output.interpretation)]
        if e.output.warnings:
            out += ["", "**Warnings:**", *[f"- {w}" for w in e.output.warnings]]
        out += ["", "**Model limits:**", *[f"- {x}" for x in e.limits], ""]
    c = r.comparison
    out += ["## Comparison", "", c.note, ""]
    out += ["| Model | Primary metric | Value | p05 | p95 |", "|---|---|---|---|---|"]
    out += [f"| {row['model']} | {row['primary_metric']} | {_v(row['value'])} | {_v(row['p05'])} | {_v(row['p95'])} |"
            for row in c.table]
    for x in c.contradictions:
        out += ["", f"**Contradiction on {x.dimension}:** {x.explanation}", *[f"- (+) {p}" for p in x.positive],
                *[f"- (−) {n}" for n in x.negative]]
    out += ["", "## Synthesis", ""]
    out += [f"- *{ORIGIN[st.origin]}:* {st.text}" for st in r.synthesis]
    out += ["", "## Recommendations", ""]
    for i, rec in enumerate(r.recommendations, 1):
        out += [f"### {i}. {rec.title} (priority {rec.priority:.0f})", "", rec.rationale, "",
                f"- Expected impact: {rec.expected_impact}", f"- Uncertainty: {rec.uncertainty} · horizon: {rec.horizon}",
                f"- Sources: {', '.join(rec.source_models) or 'cross-model'}",
                *[f"- Evidence: {ev}" for ev in rec.evidence],
                *[f"- Prerequisite: {p}" for p in rec.prerequisites], *[f"- Risk: {x}" for x in rec.risks],
                *[f"- Action: {a}" for a in rec.actions], ""]
    return "\n".join(out)
