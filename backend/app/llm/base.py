"""Swappable LLM interface. Providers structure problems and propose parameters.

They never compute results: proposals are validated by the model's ParamSpec and
labelled `ai_estimate`; narratives are labelled `ai_interpretation`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from app.modeling.base import ModelSpec, Statement

if TYPE_CHECKING:
    from app.engine.goal import GoalFrame, ModelChoice
    from app.engine.structure import ProblemInput, ProblemStructure


class Provider(Protocol):
    name: str

    def structure(self, inp: ProblemInput) -> ProblemStructure: ...

    def frame(self, inp: ProblemInput, structure: ProblemStructure) -> GoalFrame: ...

    def choose(self, structure: ProblemStructure, frame: GoalFrame,
               specs: list[ModelSpec]) -> tuple[list[ModelChoice], list[str]]:
        """Models for this question with a reason each, and angles no model covers. Empty: use heuristic selection."""
        ...

    def parameterize(self, structure: ProblemStructure, spec: ModelSpec,
                     frame: GoalFrame | None = None) -> dict[str, dict[str, Any]]:
        """Return {param: {"value", "rationale", "confidence"}} or {param: {"rejected": True, "rationale"}}."""
        ...

    def narrate(self, structure: ProblemStructure, executions: list) -> list[Statement]: ...
