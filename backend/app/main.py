"""FastAPI application: model library, simulation, analyses, decisions, reports."""

from __future__ import annotations

import hashlib
import os
from collections import Counter
from contextlib import asynccontextmanager
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import db, repo
from app.auth import AuthConfig, AuthError, TokenVerifier
from app.engine.answer import build_answer
from app.engine.graph import build_graph
from app.engine.orchestrator import Setup, parse_instance, run_analysis
from app.engine.scenarios import monte_carlo, scenario_set, sensitivity
from app.engine.selection import select_models
from app.engine.structure import ProblemInput
from app.llm.factory import get_provider
from app.modeling.base import ParamError
from app.modeling.plain import PLAIN
from app.modeling.registry import REGISTRY, get_model
from app.report import render

# --- request bodies ----------------------------------------------------------

class RunBody(BaseModel):
    params: dict[str, Any] = {}
    seed: int = 42


class SimulateBody(RunBody):
    band: float = Field(0.2, gt=0, le=0.9)
    draws: int | None = Field(None, ge=10, le=2000)
    what_if: dict[str, Any] | None = None


class ProjectBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field("", max_length=2000)


class AnalysisBody(BaseModel):
    problem: ProblemInput
    title: str = Field("", max_length=200)
    project_id: int | None = None
    selected: list[str] | None = Field(None, max_length=10)
    overrides: dict[str, dict[str, Any]] = {}
    band: float = Field(0.2, gt=0, le=0.9)
    seed: int = 42


class RerunBody(BaseModel):
    selected: list[str] | None = Field(None, max_length=10)
    overrides: dict[str, dict[str, Any]] | None = None
    what_if: dict[str, dict[str, Any]] = {}
    band: float | None = Field(None, gt=0, le=0.9)


class DecisionBody(BaseModel):
    decision_status: Literal["open", "accepted", "rejected", "deferred"]
    note: str = Field("", max_length=2000)


class EvidenceBody(BaseModel):
    description: str = Field(min_length=1, max_length=5000)
    source: str = Field("", max_length=300)
    hypothesis_id: int | None = None
    value: dict[str, Any] | None = None


# --- dependencies ------------------------------------------------------------

def session(request: Request):
    with request.app.state.Session() as s:
        yield s


SessionDep = Annotated[Session, Depends(session)]


class Ctx(BaseModel):
    workspace_id: int
    user: str
    role: str


def _workspace(s: Session, slug: str, email: str, role: str) -> db.Workspace:
    ws = s.scalar(select(db.Workspace).filter_by(slug=slug))
    if ws is None:
        ws = db.Workspace(slug=slug, name=email or slug)
        s.add(ws)
        s.flush()
    user = s.scalar(select(db.User).filter_by(workspace_id=ws.id))
    if user is None:
        s.add(db.User(workspace_id=ws.id, email=email, role=role))
    elif (user.email, user.role) != (email, role):
        user.email, user.role = email, role
    s.commit()
    return ws


def context(request: Request, s: SessionDep,
            x_workspace: Annotated[str, Header(pattern=r"^[a-z0-9-]{1,64}$")] = "default") -> Ctx:
    """OIDC mode: personal workspace per token subject. Dev mode: workspace from X-Workspace header."""
    verifier: TokenVerifier | None = request.app.state.verifier
    if verifier is None:
        ws = _workspace(s, x_workspace, f"local@{x_workspace}", "admin")
        return Ctx(workspace_id=ws.id, user=f"local@{x_workspace}", role="admin")
    try:
        ident = verifier.verify(request.headers.get("authorization"))
    except AuthError as e:
        raise HTTPException(e.status, str(e), headers={"WWW-Authenticate": "Bearer"} if e.status == 401 else None) from e
    slug = f"u:{ident.sub}" if len(ident.sub) <= 62 else "u:" + hashlib.sha256(ident.sub.encode()).hexdigest()[:40]
    ws = _workspace(s, slug, ident.email, ident.role)
    return Ctx(workspace_id=ws.id, user=ident.email or ident.sub, role=ident.role)


CtxDep = Annotated[Ctx, Depends(context)]


def audit(s: Session, ctx: Ctx, action: str, entity: str, entity_id: int | None, **detail):
    s.add(db.AuditLog(workspace_id=ctx.workspace_id, actor=ctx.user, action=action, entity=entity,
                      entity_id=entity_id, detail=detail))


def _model(key: str):
    if key not in REGISTRY.models and key not in REGISTRY.planned:
        raise HTTPException(404, f"unknown model '{key}'")
    if key in REGISTRY.planned:
        raise HTTPException(409, f"model '{key}' is planned but not implemented")
    return get_model(key)


def _check_keys(ids: list[str] | None):
    if ids and len(set(ids)) != len(ids):
        raise HTTPException(422, "duplicate model instances")
    for i in ids or []:
        try:
            k, _ = parse_instance(i)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        if k not in REGISTRY.models:
            raise HTTPException(422, f"model '{k}' is not implemented")


def _analysis(s: Session, ctx: Ctx, aid: int) -> db.Analysis:
    a = s.get(db.Analysis, aid)
    if a is None or a.project.workspace_id != ctx.workspace_id:
        raise HTTPException(404, "analysis not found")
    return a


def _detail(s: Session, a: db.Analysis, revision: int | None = None) -> dict:
    try:
        result, recs = repo.load_revision(s, a, revision)
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    return {"id": a.id, "title": a.title, "project_id": a.project_id, "revision": revision or a.revision,
            "latest_revision": a.revision, "created_at": a.created_at, "updated_at": a.updated_at,
            "result": result.model_dump(mode="json"), "answer": build_answer(result).model_dump(mode="json"),
            "recommendations": [r.payload | {"db_id": r.id, "decision_status": r.decision_status, "note": r.note}
                                for r in recs]}


def _default_project(s: Session, ctx: Ctx) -> db.Project:
    p = s.scalar(select(db.Project).filter_by(workspace_id=ctx.workspace_id).order_by(db.Project.id))
    if p is None:
        p = db.Project(workspace_id=ctx.workspace_id, name="Default project")
        s.add(p)
        s.flush()
    return p


# --- app -----------------------------------------------------------------------

def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        cfg = AuthConfig.from_env()
        app.state.auth = cfg
        app.state.verifier = TokenVerifier(cfg) if cfg.mode == "oidc" else None
        app.state.Session = db.make_session_factory()
        app.state.provider = get_provider()
        with app.state.Session() as s:
            repo.sync_models(s)
        yield

    app = FastAPI(title="Model Thinking AI", version="0.1.0", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(","),
                       allow_methods=["*"], allow_headers=["*"])

    api = APIRouter(dependencies=[Depends(context)])  # every route below requires an identity

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/auth/config")
    def auth_config(request: Request):
        cfg = request.app.state.auth
        return {"mode": cfg.mode, "issuer": cfg.issuer, "client_id": cfg.client_id} if cfg.mode == "oidc" \
            else {"mode": "dev"}

    @api.get("/api/auth/me")
    def me(ctx: CtxDep):
        return {"email": ctx.user, "role": ctx.role}

    @api.get("/api/settings")
    def settings(request: Request):
        url = os.environ.get("DATABASE_URL", "sqlite")
        return {
            "provider": request.app.state.provider.name, "database": url.split(":")[0],
            "models_implemented": len(REGISTRY.models), "models_total": len(REGISTRY.specs()),
            "features": {
                "model_library": "implemented", "model_selection": "implemented (heuristic score)",
                "orchestration": "implemented", "scenarios_sensitivity_monte_carlo": "implemented",
                "knowledge_graph": "implemented", "decision_center": "implemented", "reports": "implemented (markdown)",
                "llm_analysis": "implemented (optional, set LLM_PROVIDER=anthropic)",
                "authentication": ("OIDC via launch-kit (JWKS-validated bearer tokens)" if
                                   request.app.state.auth.mode == "oidc" else "DEV MODE — no authentication"),
                "rbac": "PARTIAL — launch-kit roles admin/user both get full access to their own workspace",
                "encryption_at_rest": "NOT IMPLEMENTED — delegate to database/disk encryption",
                "redis_background_jobs": "NOT IMPLEMENTED — runs synchronously",
                "evaluate_phase_model_recalibration": "PARTIAL — evidence can be recorded, not yet fed back",
            },
        }

    # models -----------------------------------------------------------------
    @api.get("/api/models")
    def list_models():
        return [s.model_dump(include={"key", "number", "name", "family", "implemented", "summary", "perspective",
                                      "version"}) for s in REGISTRY.specs()]

    @api.get("/api/models/{key}")
    def model_detail(key: str):
        try:
            spec = REGISTRY.spec(key).model_dump(mode="json")
        except KeyError as e:
            raise HTTPException(404, f"unknown model '{key}'") from e
        plain = PLAIN.get(key)
        return spec | {"question": plain.question if plain else "", "metric_help": plain.help if plain else {}}

    @api.post("/api/models/{key}/run")
    def run_model(key: str, body: RunBody):
        model = _model(key)
        try:
            return model.run(body.params, body.seed)
        except ParamError as e:
            raise HTTPException(422, str(e)) from e

    @api.post("/api/models/{key}/simulate")
    def simulate(key: str, body: SimulateBody, s: SessionDep, ctx: CtxDep):
        model = _model(key)
        try:
            params = model.validate(body.params)
            out = {"output": model.run(params, body.seed).model_dump(mode="json"),
                   "sensitivity": [i.model_dump() for i in sensitivity(model, params, body.band, body.seed)],
                   "scenarios": [x.model_dump(mode="json") for x in
                                 scenario_set(model, params, body.band, body.what_if, body.seed)],
                   "monte_carlo": monte_carlo(model, params, body.band, body.draws, body.seed).model_dump(mode="json")}
        except ParamError as e:
            raise HTTPException(422, str(e)) from e
        s.add(db.Simulation(workspace_id=ctx.workspace_id, model_key=key, kind="simulate",
                            result={"params": params, "band": body.band,
                                    "primary": out["output"]["metrics"].get(model.spec.primary_metric)}))
        s.commit()
        return out

    @api.post("/api/structure")
    def structure(problem: ProblemInput, request: Request):
        st = request.app.state.provider.structure(problem)
        return {"structure": st, "selection": select_models(st)}

    # projects ---------------------------------------------------------------
    @api.post("/api/frame")
    def frame(problem: ProblemInput, request: Request):
        provider = request.app.state.provider
        f = provider.frame(problem, provider.structure(problem))
        return {"frame": f.model_dump(mode="json"), "missing": f.missing()}

    @api.get("/api/projects")
    def projects(s: SessionDep, ctx: CtxDep):
        rows = s.scalars(select(db.Project).filter_by(workspace_id=ctx.workspace_id)).all()
        counts = dict(s.execute(select(db.Analysis.project_id, func.count()).group_by(db.Analysis.project_id)).all())
        return [{"id": p.id, "name": p.name, "description": p.description, "created_at": p.created_at,
                 "analyses": counts.get(p.id, 0)} for p in rows]

    @api.post("/api/projects", status_code=201)
    def create_project(body: ProjectBody, s: SessionDep, ctx: CtxDep):
        p = db.Project(workspace_id=ctx.workspace_id, name=body.name, description=body.description)
        s.add(p)
        s.flush()
        audit(s, ctx, "project.create", "project", p.id)
        s.commit()
        return {"id": p.id, "name": p.name}

    # analyses ---------------------------------------------------------------
    @api.get("/api/analyses")
    def analyses(s: SessionDep, ctx: CtxDep):
        rows = s.scalars(select(db.Analysis).join(db.Project).filter(db.Project.workspace_id == ctx.workspace_id)
                         .order_by(db.Analysis.updated_at.desc())).all()
        out = []
        for a in rows:
            ex = s.scalars(select(db.ModelExecution).filter_by(analysis_id=a.id, revision=a.revision)).all()
            out.append({"id": a.id, "title": a.title, "project_id": a.project_id, "project": a.project.name,
                        "revision": a.revision, "updated_at": a.updated_at, "models": [e.model_key for e in ex]})
        return out

    @api.post("/api/analyses", status_code=201)
    def create_analysis(body: AnalysisBody, request: Request, s: SessionDep, ctx: CtxDep):
        _check_keys(body.selected)
        if body.project_id:
            project = s.get(db.Project, body.project_id)
            if project is None or project.workspace_id != ctx.workspace_id:
                raise HTTPException(404, "project not found")
        else:
            project = _default_project(s, ctx)
        result = run_analysis(body.problem, body.selected, body.overrides, band=body.band, seed=body.seed,
                              provider=request.app.state.provider)
        a = db.Analysis(project_id=project.id, title=body.title or body.problem.description[:80])
        s.add(a)
        s.flush()
        # The AI setup is recorded once and carried forward, so later reruns never depend on a failed revision.
        setup = Setup.from_result(result).model_dump(mode="json")
        repo.save_revision(s, a, result, {"selected": body.selected, "overrides": body.overrides, "what_if": {},
                                          "setup": setup})
        audit(s, ctx, "analysis.create", "analysis", a.id, models=[e.model_key for e in result.executions])
        s.commit()
        return _detail(s, a)

    @api.get("/api/analyses/{aid}")
    def get_analysis(aid: int, s: SessionDep, ctx: CtxDep, revision: int | None = None):
        return _detail(s, _analysis(s, ctx, aid), revision)

    @api.get("/api/analyses/{aid}/revisions")
    def revisions(aid: int, s: SessionDep, ctx: CtxDep):
        a = _analysis(s, ctx, aid)
        return [{"revision": r.revision, "created_at": r.created_at, "settings": r.settings, "band": r.band}
                for r in a.revisions]

    @api.post("/api/analyses/{aid}/rerun")
    def rerun(aid: int, body: RerunBody, request: Request, s: SessionDep, ctx: CtxDep):
        a = _analysis(s, ctx, aid)
        _check_keys(body.selected)
        prev = a.revisions[-1]
        problem = ProblemInput.model_validate(
            s.scalar(select(db.ProblemDefinition).filter_by(analysis_id=a.id, revision=a.revision)).input)
        selected = body.selected or prev.settings.get("selected") or \
            [e["model_key"] for e in _detail(s, a)["result"]["executions"]]
        overrides = body.overrides if body.overrides is not None else prev.settings.get("overrides", {})
        band = body.band or prev.band
        # Same AI setup as the first revision: only user changes move results. Older revisions have none stored.
        stored = prev.settings.get("setup")
        setup = Setup.model_validate(stored) if stored else Setup.from_result(repo.load_revision(s, a)[0])
        result = run_analysis(problem, selected, overrides, body.what_if, band=band, seed=prev.seed,
                              provider=request.app.state.provider, setup=setup)
        a.revision += 1
        a.updated_at = db.now()
        repo.save_revision(s, a, result, {"selected": selected, "overrides": overrides, "what_if": body.what_if,
                                          "setup": setup.model_dump(mode="json")})
        audit(s, ctx, "analysis.rerun", "analysis", a.id, revision=a.revision)
        s.commit()
        return _detail(s, a)

    @api.get("/api/analyses/{aid}/graph")
    def graph(aid: int, s: SessionDep, ctx: CtxDep, revision: int | None = None):
        result, _ = repo.load_revision(s, _analysis(s, ctx, aid), revision)
        return build_graph(result)

    @api.get("/api/analyses/{aid}/report")
    def report(aid: int, s: SessionDep, ctx: CtxDep, revision: int | None = None):
        a = _analysis(s, ctx, aid)
        rev = revision or a.revision
        result, _ = repo.load_revision(s, a, rev)
        content = render(a.title, rev, result)
        s.add(db.Report(analysis_id=a.id, revision=rev, content=content))
        s.commit()
        return {"analysis_id": a.id, "revision": rev, "format": "markdown", "content": content}

    @api.post("/api/analyses/{aid}/evidence", status_code=201)
    def add_evidence(aid: int, body: EvidenceBody, s: SessionDep, ctx: CtxDep):
        a = _analysis(s, ctx, aid)
        ev = db.Evidence(analysis_id=a.id, **body.model_dump())
        s.add(ev)
        s.flush()
        audit(s, ctx, "evidence.create", "evidence", ev.id, analysis=a.id)
        s.commit()
        return {"id": ev.id}

    @api.get("/api/analyses/{aid}/evidence")
    def list_evidence(aid: int, s: SessionDep, ctx: CtxDep):
        a = _analysis(s, ctx, aid)
        return s.scalars(select(db.Evidence).filter_by(analysis_id=a.id).order_by(db.Evidence.id)).all()

    @api.patch("/api/recommendations/{rid}")
    def decide(rid: int, body: DecisionBody, s: SessionDep, ctx: CtxDep):
        rec = s.get(db.Recommendation, rid)
        if rec is None:
            raise HTTPException(404, "recommendation not found")
        _analysis(s, ctx, rec.analysis_id)
        rec.decision_status, rec.note, rec.decided_at = body.decision_status, body.note, db.now()
        audit(s, ctx, "recommendation.decide", "recommendation", rid, status=body.decision_status)
        s.commit()
        return {"id": rec.id, "decision_status": rec.decision_status, "note": rec.note}

    # dashboard / audit ----------------------------------------------------------
    @api.get("/api/dashboard")
    def dashboard(s: SessionDep, ctx: CtxDep):
        analyses_ = s.scalars(select(db.Analysis).join(db.Project).filter(db.Project.workspace_id == ctx.workspace_id)
                              .order_by(db.Analysis.updated_at.desc())).all()
        ids = [a.id for a in analyses_]
        latest = {a.id: a.revision for a in analyses_}
        execs = [e for e in s.scalars(select(db.ModelExecution).filter(db.ModelExecution.analysis_id.in_(ids))
                                      .order_by(db.ModelExecution.id.desc())).all()]
        current = [e for e in execs if latest[e.analysis_id] == e.revision]
        recs = [r for r in s.scalars(select(db.Recommendation).filter(db.Recommendation.analysis_id.in_(ids))
                                     .order_by(db.Recommendation.priority.desc())).all()
                if latest[r.analysis_id] == r.revision]
        titles = {a.id: a.title for a in analyses_}
        insights = []
        for a in analyses_[:5]:
            ar = a.revisions[-1]
            insights += [{"analysis_id": a.id, "analysis": a.title, "text": x["text"], "origin": x["origin"]}
                         for x in ar.synthesis[1:3]]
        return {
            "counts": {"analyses": len(analyses_), "projects": s.scalar(select(func.count()).select_from(db.Project)
                                                                         .filter_by(workspace_id=ctx.workspace_id)),
                       "executions": len(execs), "open_decisions": sum(r.decision_status == "open" for r in recs)},
            "active_analyses": [{"id": a.id, "title": a.title, "revision": a.revision, "updated_at": a.updated_at}
                                for a in analyses_[:6]],
            "models_used": Counter(e.model_key for e in current).most_common(),
            "recent_simulations": [{"analysis_id": e.analysis_id, "analysis": titles[e.analysis_id],
                                    "model": e.model_key, "status": e.status, "at": e.created_at,
                                    "primary_metric": e.uncertainty.get("primary_metric"),
                                    "interval": e.uncertainty.get("interval_p05_p95")} for e in execs[:8]],
            "insights": insights[:6],
            "open_decisions": [{"db_id": r.id, "analysis_id": r.analysis_id, "analysis": titles[r.analysis_id],
                                "title": r.payload["title"], "priority": r.priority}
                               for r in recs if r.decision_status == "open"][:8],
        }

    @api.get("/api/audit")
    def audit_log(s: SessionDep, ctx: CtxDep):
        rows = s.scalars(select(db.AuditLog).filter_by(workspace_id=ctx.workspace_id)
                         .order_by(db.AuditLog.id.desc()).limit(200)).all()
        return [{"at": r.at, "actor": r.actor, "action": r.action, "entity": r.entity, "entity_id": r.entity_id,
                 "detail": r.detail} for r in rows]

    app.include_router(api)
    return app


app = create_app()
