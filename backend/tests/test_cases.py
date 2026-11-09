"""Example set: questions with expected conclusions from outside the app.

Each case records an AI setup, so the offline run needs no key and is deterministic. The live run re-does the
setup with Claude and checks the same conclusions.
"""

import json
import os
from pathlib import Path

import numpy as np
import pytest

from app.engine.answer import build_answer
from app.engine.orchestrator import Setup, run_analysis
from app.engine.structure import ProblemInput

CASES = sorted(Path(__file__).parent.glob("cases/*.json"))


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def check(answer, expect: dict) -> None:
    assert answer.verdict.status == expect["verdict"], answer.verdict.text
    if "difference_instance" in expect:
        assert answer.differences and expect["difference_mentions"] in answer.differences[0]
    assert any(expect["unknown_mentions"] in u.label for u in answer.unknowns), [u.label for u in answer.unknowns]


@pytest.mark.parametrize("path", CASES, ids=lambda p: p.stem)
def test_case_conclusions(path):
    case = load(path)
    result = run_analysis(ProblemInput(**case["problem"]), overrides=case["overrides"],
                          setup=Setup.model_validate(case["setup"]))
    check(build_answer(result), case["expect"])


def test_retention_expectation_matches_the_analytic_long_run():
    P = np.array(load(Path(__file__).parent / "cases/retention.json")["setup"]["estimates"]["markov"]
                 ["transition_matrix"]["value"])
    A = np.vstack([P.T - np.eye(3), np.ones(3)])
    pi = np.linalg.lstsq(A, np.array([0, 0, 0, 1.0]), rcond=None)[0]
    assert pi[0] * 1000 < 700  # the recorded expectation "unlikely" follows from pi P = pi


@pytest.mark.live
@pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="needs ANTHROPIC_API_KEY")
@pytest.mark.parametrize("path", CASES, ids=lambda p: p.stem)
def test_case_conclusions_with_live_ai_setup(path):
    from app.llm.anthropic_provider import AnthropicProvider

    case = load(path)
    result = run_analysis(ProblemInput(**case["problem"]), provider=AnthropicProvider())
    check(build_answer(result), case["expect"])
