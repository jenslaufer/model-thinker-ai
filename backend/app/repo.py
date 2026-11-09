"""Persist and restore analysis revisions."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import db
from app.engine.orchestrator import AnalysisResult, Comparison, Execution, PrioritizedRecommendation
from app.engine.selection import Selection
from app.engine.structure import ProblemInput, ProblemStructure
from app.modeling.base import ModelOutput, Statement
from app.modeling.registry import REGISTRY


def sync_models(s: Session) -> None:
    """Register model catalog and current versions (idempotent)."""
    for spec in REGISTRY.specs():
        if not s.get(db.Model, spec.key):
            s.add(db.Model(key=spec.key, number=spec.number, name=spec.name, family=spec.family,
                           implemented=spec.implemented))
        else:
            s.get(db.Model, spec.key).implemented = spec.implemented
        if spec.implemented and not _version(s, spec.key, spec.version):
            s.add(db.ModelVersion(model_key=spec.key, version=spec.version, spec=spec.model_dump(mode="json")))
    s.commit()


def _version(s: Session, key: str, version: str) -> db.ModelVersion | None:
    return s.scalar(select(db.ModelVersion).filter_by(model_key=key, version=version))


def save_revision(s: Session, analysis: db.Analysis, r: AnalysisResult, settings: dict) -> None:
    rev = analysis.revision
    s.add(db.AnalysisRevision(analysis_id=analysis.id, revision=rev, band=r.band, seed=r.seed, provider=r.provider,
                              settings=settings, selection=r.selection.model_dump(mode="json"),
                              comparison=r.comparison.model_dump(mode="json"),
                              synthesis=[x.model_dump(mode="json") for x in r.synthesis]))
    pd = db.ProblemDefinition(analysis_id=analysis.id, revision=rev, input=r.problem.model_dump(mode="json"),
                              structure=r.structure.model_dump(mode="json"))
    s.add(pd)
    s.flush()
    s.add_all([db.Actor(problem_id=pd.id, name=a.name, role=a.role) for a in r.structure.actors])
    s.add_all([db.Variable(problem_id=pd.id, name=v.name, kind=v.kind, origin=v.origin) for v in r.structure.variables])
    s.add_all([db.Hypothesis(problem_id=pd.id, source=h.source, target=h.target, relation=h.relation,
                             polarity=h.polarity, status=h.status) for h in r.structure.relations])
    for pos, e in enumerate(r.executions):
        spec = REGISTRY.spec(e.model_key)
        ex = db.ModelExecution(analysis_id=analysis.id, revision=rev, position=pos, model_key=e.model_key,
                               model_version_id=_version(s, e.model_key, spec.version).id, status=e.status,
                               error=e.error, fit_score=e.fit_score, input_hash=e.input_hash,
                               uncertainty=e.uncertainty | {"instance": e.instance})
        s.add(ex)
        s.flush()
        s.add_all([db.ModelParameter(execution_id=ex.id, name=n, value={"v": p.value, "c": p.confidence},
                                     origin=p.origin,
                                     rationale=p.rationale) for n, p in e.params.items()])
        if e.output:
            s.add(db.ModelResult(execution_id=ex.id, output=e.output.model_dump(mode="json")))
        s.add_all([db.Scenario(execution_id=ex.id, kind=sc.kind, payload=sc.model_dump(mode="json"))
                   for sc in e.scenarios])
        if e.sensitivity is not None:
            s.add(db.Simulation(execution_id=ex.id, model_key=e.model_key, kind="sensitivity",
                                result={"items": [i.model_dump(mode="json") for i in e.sensitivity]}))
        if e.goal:
            s.add(db.Simulation(execution_id=ex.id, model_key=e.model_key, kind="goal",
                                result=e.goal.model_dump(mode="json")))
        if e.monte_carlo:
            s.add(db.Simulation(execution_id=ex.id, model_key=e.model_key, kind="monte_carlo",
                                result=e.monte_carlo.model_dump(mode="json")))
    s.add_all([db.Recommendation(analysis_id=analysis.id, revision=rev, key=x.id, priority=x.priority,
                                 payload=x.model_dump(mode="json")) for x in r.recommendations])


def load_revision(s: Session, analysis: db.Analysis, revision: int | None = None) -> tuple[AnalysisResult, list]:
    rev = revision or analysis.revision
    ar = s.scalar(select(db.AnalysisRevision).filter_by(analysis_id=analysis.id, revision=rev))
    if ar is None:
        raise LookupError(f"revision {rev} not found")
    pd = s.scalar(select(db.ProblemDefinition).filter_by(analysis_id=analysis.id, revision=rev))
    rows = s.scalars(select(db.ModelExecution).filter_by(analysis_id=analysis.id, revision=rev)
                     .order_by(db.ModelExecution.position)).all()
    executions = []
    for ex in rows:
        spec = ex.model_version.spec
        sims = {sim.kind: sim.result for sim in ex.simulations}
        executions.append(Execution(
            model_key=ex.model_key, instance=ex.uncertainty.get("instance", ""), model_name=spec["name"], model_version=ex.model_version.version, status=ex.status,
            error=ex.error, fit_score=ex.fit_score, assumptions=spec["assumptions"], limits=spec["limits"],
            params={p.name: {"value": p.value["v"], "origin": p.origin, "rationale": p.rationale,
                            "confidence": p.value.get("c")} for p in ex.parameters},
            output=ModelOutput.model_validate(ex.result.output) if ex.result else None,
            scenarios=[sc.payload for sc in ex.scenarios],
            sensitivity=sims["sensitivity"]["items"] if "sensitivity" in sims else None,
            monte_carlo=sims.get("monte_carlo"), goal=sims.get("goal"), uncertainty=ex.uncertainty, input_hash=ex.input_hash))
    recs = s.scalars(select(db.Recommendation).filter_by(analysis_id=analysis.id, revision=rev)
                     .order_by(db.Recommendation.priority.desc(), db.Recommendation.id)).all()
    result = AnalysisResult(
        problem=ProblemInput.model_validate(pd.input), structure=ProblemStructure.model_validate(pd.structure),
        selection=Selection.model_validate(ar.selection), executions=executions,
        comparison=Comparison.model_validate(ar.comparison),
        synthesis=[Statement.model_validate(x) for x in ar.synthesis],
        recommendations=[PrioritizedRecommendation.model_validate(x.payload) for x in recs],
        band=ar.band, seed=ar.seed, provider=ar.provider)
    return result, recs
