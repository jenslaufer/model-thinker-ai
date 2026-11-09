"""Model registry: implemented models plus catalog entries for families not yet implemented.

To add a model: subclass `Model`, give it a `ModelSpec`, append it to a family's MODELS list.
"""

from .base import Model, ModelSpec
from .family_a import MODELS as A
from .family_b import MODELS as B
from .family_c import MODELS as C


def _planned(key, number, name, family, summary, math, tags, perspective):
    return ModelSpec(key=key, number=number, name=name, family=family, implemented=False, summary=summary,
                     math=math, tags=tags, perspective=perspective,
                     limits=["Not implemented yet — catalog entry only, never executed."])


PLANNED = [
    _planned("concavity", 4, "Concavity and Convexity", "A", "Diminishing vs. increasing returns; Jensen's inequality.",
             r"f(E[X])\ \gtrless\ E[f(X)]", {"returns": 1.0, "risk": 0.5}, "mathematical"),
    _planned("value_power", 5, "Value and Power Models", "A", "Shapley value: fair attribution of joint value.",
             r"\phi_i=\sum_{S\subseteq N\setminus\{i\}}\frac{|S|!(n-|S|-1)!}{n!}(v(S\cup\{i\})-v(S))",
             {"power": 1.0, "coalition": 0.8, "negotiation": 0.5}, "strategic"),
    _planned("path_dependence", 10, "Path Dependence Models", "B", "Early events shape long-run outcomes (Pólya urn).",
             r"P(\text{red}_{t+1})=\frac{r_t}{r_t+b_t}", {"history": 1.0, "lock_in": 1.0}, "dynamic"),
    _planned("local_interaction", 11, "Local Interaction Models", "B", "Neighbours' choices drive coordination (Schelling, Ising).",
             r"u_i=\sum_{j\in N(i)}\mathbb{1}[s_i=s_j]", {"segregation": 1.0, "coordination": 0.8}, "social"),
    _planned("lyapunov", 12, "Lyapunov and Equilibrium Models", "B", "Whether and how fast a system reaches equilibrium.",
             r"V(x_{t+1})\le V(x_t)-k", {"equilibrium": 1.0, "stability": 1.0}, "mathematical"),
    _planned("spatial_choice", 16, "Spatial and Hedonic Choice Models", "C", "Choice by distance to ideal points in attribute space.",
             r"u_i(x)=-\|x-\theta_i\|", {"preferences": 1.0, "positioning": 1.0}, "economic"),
    _planned("mechanism_design", 20, "Mechanism Design", "C", "Design rules so self-interest yields the desired outcome.",
             r"\max_{M}\ E[W]\ \text{s.t. IC, IR}", {"incentives": 1.0, "auction": 1.0, "policy": 0.6}, "strategic"),
    _planned("signaling", 21, "Signaling Models", "C", "Costly signals separate types under asymmetric information.",
             r"c_H(s)<\Delta w<c_L(s)", {"information": 0.8, "trust": 0.6, "signaling": 1.0}, "strategic"),
    _planned("learning", 22, "Learning Models", "C", "Reinforcement and social learning of behaviour.",
             r"Q_{t+1}(a)=Q_t(a)+\alpha(r_t-Q_t(a))", {"learning": 1.0, "adaptation": 0.8}, "learning"),
    _planned("rugged_landscape", 24, "Rugged Landscape Models", "C", "Search on landscapes with many local optima (NK).",
             r"F=\frac{1}{N}\sum_i f_i(x_i,x_{i_1},\dots,x_{i_K})", {"innovation": 1.0, "search": 1.0, "exploration": 0.5},
             "search"),
]


class Registry:
    def __init__(self, models: list[Model], planned: list[ModelSpec]):
        self.models = {m.spec.key: m for m in models}
        self.planned = {s.key: s for s in planned}

    def specs(self) -> list[ModelSpec]:
        return sorted([m.spec for m in self.models.values()] + list(self.planned.values()), key=lambda s: s.number)

    def spec(self, key: str) -> ModelSpec:
        if key in self.models:
            return self.models[key].spec
        return self.planned[key]


REGISTRY = Registry(A + B + C, PLANNED)


def get_model(key: str) -> Model:
    if key not in REGISTRY.models:
        raise KeyError(f"model '{key}' is not implemented")
    return REGISTRY.models[key]


def implemented_models() -> list[Model]:
    return sorted(REGISTRY.models.values(), key=lambda m: m.spec.number)
