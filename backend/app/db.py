"""Database entities. SQLite by default, PostgreSQL via DATABASE_URL.

Every analysis re-run creates a new revision; old executions, parameters, results,
scenarios and simulations stay untouched (traceable history).
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import JSON, ForeignKey, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker


def now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    type_annotation_map = {dict: JSON, list: JSON}  # noqa: RUF012


class Workspace(Base):
    __tablename__ = "workspace"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(200))


class User(Base):
    __tablename__ = "user_account"
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspace.id"))
    email: Mapped[str] = mapped_column(String(320))
    role: Mapped[str] = mapped_column(String(20), default="owner")  # owner | analyst | viewer


class Project(Base):
    __tablename__ = "project"
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspace.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(default=now)


class Analysis(Base):
    __tablename__ = "analysis"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    revision: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(default=now)
    updated_at: Mapped[datetime] = mapped_column(default=now)
    project: Mapped[Project] = relationship()
    revisions: Mapped[list[AnalysisRevision]] = relationship(order_by="AnalysisRevision.revision")


class AnalysisRevision(Base):
    """One run of the pipeline: settings plus comparison/synthesis snapshot."""

    __tablename__ = "analysis_revision"
    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("analysis.id"), index=True)
    revision: Mapped[int]
    band: Mapped[float]
    seed: Mapped[int]
    provider: Mapped[str] = mapped_column(String(50))
    settings: Mapped[dict]  # selected, overrides, what_if
    selection: Mapped[dict]
    comparison: Mapped[dict]
    synthesis: Mapped[list]
    created_at: Mapped[datetime] = mapped_column(default=now)


class ProblemDefinition(Base):
    __tablename__ = "problem_definition"
    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("analysis.id"), index=True)
    revision: Mapped[int]
    input: Mapped[dict]
    structure: Mapped[dict]


class Actor(Base):
    __tablename__ = "actor"
    id: Mapped[int] = mapped_column(primary_key=True)
    problem_id: Mapped[int] = mapped_column(ForeignKey("problem_definition.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(200), default="")


class Variable(Base):
    __tablename__ = "variable"
    id: Mapped[int] = mapped_column(primary_key=True)
    problem_id: Mapped[int] = mapped_column(ForeignKey("problem_definition.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(20))
    origin: Mapped[str] = mapped_column(String(20))


class Hypothesis(Base):
    __tablename__ = "hypothesis"
    id: Mapped[int] = mapped_column(primary_key=True)
    problem_id: Mapped[int] = mapped_column(ForeignKey("problem_definition.id"), index=True)
    source: Mapped[str] = mapped_column(String(200))
    target: Mapped[str] = mapped_column(String(200))
    relation: Mapped[str] = mapped_column(String(20))
    polarity: Mapped[str] = mapped_column(String(1))
    status: Mapped[str] = mapped_column(String(20))


class Evidence(Base):
    __tablename__ = "evidence"
    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("analysis.id"), index=True)
    hypothesis_id: Mapped[int | None] = mapped_column(ForeignKey("hypothesis.id"))
    description: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(300), default="")
    value: Mapped[dict | None] = mapped_column(JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(default=now)


class Model(Base):
    __tablename__ = "model"
    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    number: Mapped[int]
    name: Mapped[str] = mapped_column(String(200))
    family: Mapped[str] = mapped_column(String(1))
    implemented: Mapped[bool]


class ModelVersion(Base):
    __tablename__ = "model_version"
    id: Mapped[int] = mapped_column(primary_key=True)
    model_key: Mapped[str] = mapped_column(ForeignKey("model.key"), index=True)
    version: Mapped[str] = mapped_column(String(20))
    spec: Mapped[dict]


class ModelExecution(Base):
    __tablename__ = "model_execution"
    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("analysis.id"), index=True)
    revision: Mapped[int]
    position: Mapped[int]
    model_key: Mapped[str] = mapped_column(ForeignKey("model.key"))
    model_version_id: Mapped[int] = mapped_column(ForeignKey("model_version.id"))
    status: Mapped[str] = mapped_column(String(10))
    error: Mapped[str | None] = mapped_column(Text)
    fit_score: Mapped[int]
    input_hash: Mapped[str] = mapped_column(String(32))
    uncertainty: Mapped[dict]
    created_at: Mapped[datetime] = mapped_column(default=now)
    model_version: Mapped[ModelVersion] = relationship()
    parameters: Mapped[list[ModelParameter]] = relationship(order_by="ModelParameter.id")
    result: Mapped[ModelResult | None] = relationship()
    scenarios: Mapped[list[Scenario]] = relationship(order_by="Scenario.id")
    simulations: Mapped[list[Simulation]] = relationship(order_by="Simulation.id")


class ModelParameter(Base):
    __tablename__ = "model_parameter"
    id: Mapped[int] = mapped_column(primary_key=True)
    execution_id: Mapped[int] = mapped_column(ForeignKey("model_execution.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    value: Mapped[dict]  # {"v": value}
    origin: Mapped[str] = mapped_column(String(30))
    rationale: Mapped[str] = mapped_column(Text, default="")


class ModelResult(Base):
    __tablename__ = "model_result"
    id: Mapped[int] = mapped_column(primary_key=True)
    execution_id: Mapped[int] = mapped_column(ForeignKey("model_execution.id"), unique=True)
    output: Mapped[dict]


class Scenario(Base):
    __tablename__ = "scenario"
    id: Mapped[int] = mapped_column(primary_key=True)
    execution_id: Mapped[int] = mapped_column(ForeignKey("model_execution.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    payload: Mapped[dict]


class Simulation(Base):
    __tablename__ = "simulation"
    id: Mapped[int] = mapped_column(primary_key=True)
    execution_id: Mapped[int | None] = mapped_column(ForeignKey("model_execution.id"), index=True)
    workspace_id: Mapped[int | None] = mapped_column(ForeignKey("workspace.id"))
    model_key: Mapped[str] = mapped_column(String(50))
    kind: Mapped[str] = mapped_column(String(20))  # sensitivity | monte_carlo | simulate
    result: Mapped[dict]
    created_at: Mapped[datetime] = mapped_column(default=now)


class Recommendation(Base):
    __tablename__ = "recommendation"
    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("analysis.id"), index=True)
    revision: Mapped[int]
    key: Mapped[str] = mapped_column(String(100))
    priority: Mapped[float]
    payload: Mapped[dict]
    decision_status: Mapped[str] = mapped_column(String(10), default="open")  # open|accepted|rejected|deferred
    note: Mapped[str] = mapped_column(Text, default="")
    decided_at: Mapped[datetime | None] = mapped_column(default=None)


class Report(Base):
    __tablename__ = "report"
    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("analysis.id"), index=True)
    revision: Mapped[int]
    format: Mapped[str] = mapped_column(String(10), default="markdown")
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=now)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspace.id"), index=True)
    at: Mapped[datetime] = mapped_column(default=now)
    actor: Mapped[str] = mapped_column(String(320))
    action: Mapped[str] = mapped_column(String(50))
    entity: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[int | None]
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


def make_session_factory(url: str | None = None):
    url = url or os.environ.get("DATABASE_URL", "sqlite:///./data/model_thinking.db")
    if url.startswith("sqlite:///./"):
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, connect_args=args)
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)
