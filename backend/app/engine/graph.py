"""Knowledge graph: problems, actors, variables, hypotheses, data, models, results, scenarios, recommendations.

Edge `causal` is True only for hypothesised causal links; correlations are never causal.
"""

from __future__ import annotations

from .orchestrator import AnalysisResult


def build_graph(r: AnalysisResult) -> dict:
    nodes, edges = [], []

    def node(id_, type_, label, **data):
        nodes.append({"id": id_, "type": type_, "label": label, "data": data})
        return id_

    def edge(s, t, relation, causal=False, **data):
        edges.append({"id": f"{s}->{t}:{relation}", "source": s, "target": t, "relation": relation,
                      "causal": causal, "data": data})

    s = r.structure
    root = node("problem", "problem", s.restated_problem[:80], objective=s.objective)
    for i, a in enumerate(s.actors):
        edge(node(f"actor:{i}", "actor", a.name), root, "involved_in")
    var_id = {}
    for i, v in enumerate(s.variables):
        var_id[v.name] = node(f"var:{i}", "data_source" if v.kind == "data" else "variable", v.name, kind=v.kind,
                              origin=v.origin)
        if v.kind != "data":
            edge(var_id[v.name], root, "describes")
    for i, rel in enumerate(s.relations):
        h = node(f"hyp:{i}", "hypothesis", f"{rel.source} → {rel.target}", status=rel.status, polarity=rel.polarity)
        src, tgt = var_id.get(rel.source), var_id.get(rel.target)
        if src and tgt:
            causal = rel.relation in ("causes", "influences", "feedback")
            edge(src, tgt, rel.relation, causal=causal, polarity=rel.polarity, status=rel.status, hypothesis=h)
            edge(h, tgt, "hypothesis_about")
    for e in r.executions:
        m = node(f"model:{e.model_key}", "model", e.model_name, fit=e.fit_score, version=e.model_version,
                 status=e.status)
        edge(m, root, "analyses")
        if e.status != "ok":
            continue
        res = node(f"result:{e.model_key}", "result", f"{e.uncertainty.get('primary_metric')} = "
                   f"{_fmt(e.output.metrics.get(e.uncertainty.get('primary_metric')))}", origin="computed")
        edge(m, res, "produces")
        for sc in e.scenarios:
            edge(res, node(f"scenario:{e.model_key}:{sc.kind}", "scenario", f"{sc.name}: {_fmt(sc.primary)}",
                           kind=sc.kind), "scenario")
    for rec in r.recommendations[:8]:
        rid = node(f"rec:{rec.id}", "recommendation", rec.title, priority=rec.priority)
        for k in rec.source_models:
            edge(f"result:{k}", rid, "supports")
        if not rec.source_models:
            edge(root, rid, "requires")
    for c in r.comparison.contradictions:
        cid = node(f"conflict:{c.dimension}", "contradiction", f"Disagreement: {c.dimension}")
        for e in r.executions:
            if e.status == "ok" and any(cl.dimension == c.dimension for cl in e.output.claims):
                edge(f"result:{e.model_key}", cid, "contradicts")
    return {"nodes": nodes, "edges": edges}


def _fmt(v) -> str:
    if isinstance(v, float):
        return f"{v:.3g}"
    return str(v)
