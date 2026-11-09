"""Deterministic offline provider: keyword structuring, default parameters, no narrative."""

from app.engine.goal import heuristic_frame
from app.engine.structure import structure_problem


class HeuristicProvider:
    name = "heuristic"

    def structure(self, inp):
        return structure_problem(inp)

    def frame(self, inp, structure):
        return heuristic_frame(inp, structure)

    def choose(self, structure, frame, specs):
        return [], []

    def parameterize(self, structure, spec, frame=None):
        return {}

    def narrate(self, structure, executions):
        return []
