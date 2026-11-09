"""Phase 1–2 (UNDERSTAND, DECOMPOSE): turn a natural-language problem into a structure.

The heuristic structurer is deterministic and works offline. An LLM provider can replace it
(see app/llm); its output is validated against the same schema.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Origin = Literal["heuristic", "ai", "user_input"]


class ProblemInput(BaseModel):
    description: str = Field(max_length=10_000)
    objective: str = Field(default="", max_length=2000)
    time_horizon: str = Field(default="", max_length=200)
    system_boundaries: str = Field(default="", max_length=2000)
    available_data: str = Field(default="", max_length=5000)
    actors: list[str] = Field(default=[], max_length=30)
    decision_scope: str = Field(default="", max_length=2000)
    # Answers to "what number by when counts as success?" — the goal is never estimated.
    target_quantity: str = Field(default="", max_length=200)
    target_value: float | None = None
    risk_limit: float | None = Field(default=None, gt=0, lt=1)

    @field_validator("description")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("description must not be empty")
        return v.strip()

    @field_validator("actors")
    @classmethod
    def clean_actors(cls, v: list[str]) -> list[str]:
        return [a.strip()[:100] for a in v if a.strip()]


class Actor(BaseModel):
    name: str
    role: str = ""
    origin: Origin = "user_input"


class Variable(BaseModel):
    name: str
    kind: Literal["outcome", "driver", "stock", "parameter", "data"] = "driver"
    origin: Origin = "heuristic"


class Relation(BaseModel):
    source: str
    target: str
    relation: Literal["causes", "influences", "correlates", "feedback"]
    polarity: Literal["+", "-", "?"] = "+"
    # Every heuristic relation is a hypothesis until evidence supports it.
    status: Literal["hypothesis", "evidenced", "correlational"] = "hypothesis"


class ProblemStructure(BaseModel):
    restated_problem: str
    objective: str
    problem_types: dict[str, float]
    subproblems: list[str]
    actors: list[Actor]
    variables: list[Variable]
    relations: list[Relation]
    criteria: dict[str, float]
    data_gaps: list[str] = []
    origin: Origin = "heuristic"


# tag -> keyword stems (English + German), matched on lowercase text
KEYWORDS: dict[str, list[str]] = {
    "adoption": ["adopt", "launch", "new product", "signup", "sign-up", "user growth", "einführ", "nutzer", "neukunden"],
    "diffusion": ["word of mouth", "viral", "spread", "referral", "diffus", "verbreit", "mundpropaganda", "empfehl",
                  "contagion", "ansteck"],
    "marketing": ["marketing", " ads", "advertis", "campaign", "werbung", "kampagne", "reach", "reichweite"],
    "growth": ["grow", "wachs", "scale", "skalier"],
    "strategy": ["strateg", "competitor", "rival", "react", "wettbewerb", "konkurrent", "reagier", "opponent"],
    "competition": ["compet", "rival", "price war", "price cut", "wettbewerb", "konkurren", "preiskampf"],
    "pricing": ["price", "pricing", "preis"],
    "negotiation": ["negotiat", "verhandl", "bargain"],
    "cooperation": ["cooperat", "collaborat", "kooper", "zusammenarbeit", "alliance", "allianz"],
    "trust": ["trust", "vertrau", "reputation"],
    "partnership": ["partner", "supplier", "lieferant"],
    "repeated": ["long-term relationship", "repeated", "wiederholt", "relationship", "beziehung"],
    "collective": ["collective", "community", "gemeinschaft", "kollektiv", "gesellschaft", "society", "everyone"],
    "public_good": ["public good", "shared ", "commons", "gemeingut", "infrastruct", "infrastruktur", "climate", "klima"],
    "free_riding": ["free rid", "free-rid", "trittbrett"],
    "policy": ["policy", "regulat", "politik", "regulier", "gesetz"],
    "states": ["state", "zustand", "stage", "active", "inactive", "aktiv"],
    "churn": ["churn", "abwander", "kündig", "cancel", "attrition", "wechseln", "switch"],
    "retention": ["retention", "kundenbindung", "loyal", "retain"],
    "long_run": ["long run", "long-run", "langfristig", "steady state"],
    "dynamics": ["over time", "dynamic", "dynamik", "entwickel", "entwickl", "evolve"],
    "feedback": ["feedback", "rückkopplung", "loop", "vicious", "teufelskreis", "self-reinforc", "selbstverstärk"],
    "capacity": ["capacity", "kapazit", "saturat", "sättig", "ceiling", "carrying"],
    "resources": ["resource", "ressourc", "inventory", "lagerbestand", "workforce", "personal"],
    "tipping": ["tipping", "kipp", "critical mass", "kritische masse", "cascade", "kaskade"],
    "critical_mass": ["critical mass", "kritische masse", "threshold", "schwelle"],
    "network": ["network", "netzwerk", "connection", "social", "sozial", "platform", "plattform"],
    "influence": ["influenc", "einfluss", "hub"],
    "dependency": ["dependen", "abhängig", "supply chain", "lieferkette"],
    "uncertainty": ["uncertain", "unsicher", "unclear", "unklar", "volatil", "unknown", "ungewiss", " may ", "might",
                    "könnte"],
    "risk": ["risk", "risik", "downside", "failure", "ausfall", "worst"],
    "distribution": ["distribution", "verteilung", "variation", "schwank", "average", "durchschnitt"],
    "forecast": ["forecast", "predict", "prognos", "vorhersag", "projection"],
    "trend": ["trend", "per month", "pro monat", "increase", "steig", "decline", "sinkt", "rückgang"],
    "finance": ["cash", "liquid", "budget", "finanz", "stock price", "aktie", "revenue", "umsatz"],
    "inequality": ["inequal", "ungleich", "80/20", "pareto", "top customers", "top-kunden", "long tail", "few customers",
                   "wenige kunden"],
    "concentration": ["concentrat", "konzentr", "market share", "marktanteil", "few customers", "wenige kunden"],
    "information": ["information", "signal", "entropy", "entropie"],
    "diversity": ["divers", "portfolio", "streuung"],
    "exploration": ["explor", "try ", "ausprobier", "alternative", "experiment"],
    "experiment": ["a/b", "experiment", "pilot", "test "],
    "learning": ["learn", "lern", "adapt"],
    "options": ["which option", "choose between", "which of", "welche", "variant", "wählen", "or ads", " oder "],
    "incentives": ["incentive", "anreiz", "bonus", "auction", "auktion"],
    "signaling": ["signal", "zertifikat", "certificat", "credential"],
    "innovation": ["innovat", "r&d", "forschung"],
    "coordination": ["coordinat", "koordin", "standard"],
    "lock_in": ["lock-in", "lock in", "path depend", "pfadabh"],
    "power": ["power", "macht", "coalition", "koalition"],
}

VARIABLES: dict[str, tuple[str, str]] = {
    "adoption": ("Adoption rate", "outcome"), "diffusion": ("Word-of-mouth intensity", "driver"),
    "marketing": ("Marketing reach", "driver"), "growth": ("Growth rate", "driver"),
    "competition": ("Competitor response", "driver"), "pricing": ("Price level", "driver"),
    "cooperation": ("Cooperation level", "outcome"), "trust": ("Trust", "stock"),
    "churn": ("Churn rate", "driver"), "retention": ("Retention rate", "driver"), "states": ("State shares", "outcome"),
    "capacity": ("Capacity limit", "parameter"), "resources": ("Resource stock", "stock"),
    "tipping": ("Critical mass", "parameter"), "network": ("Network connectivity", "parameter"),
    "uncertainty": ("Outcome volatility", "parameter"), "risk": ("Downside risk", "outcome"),
    "concentration": ("Concentration share", "outcome"), "finance": ("Cash / revenue", "stock"),
    "public_good": ("Contribution level", "outcome"), "exploration": ("Option performance", "parameter"),
}

# Hypothesised causal links between tag variables: (source tag, target tag, relation, polarity)
LINKS = [
    ("marketing", "adoption", "causes", "+"), ("diffusion", "adoption", "causes", "+"),
    ("adoption", "diffusion", "feedback", "+"), ("competition", "adoption", "influences", "-"),
    ("pricing", "adoption", "influences", "-"), ("churn", "states", "causes", "-"),
    ("retention", "states", "causes", "+"), ("capacity", "growth", "feedback", "-"),
    ("growth", "resources", "causes", "+"), ("trust", "cooperation", "causes", "+"),
    ("cooperation", "trust", "feedback", "+"), ("network", "diffusion", "influences", "+"),
    ("tipping", "adoption", "influences", "+"), ("uncertainty", "risk", "causes", "+"),
]

SUBPROBLEMS: dict[str, str] = {
    "adoption": "How fast and how far will adoption spread?",
    "strategy": "How will other actors respond to our moves?",
    "competition": "Which competitive outcome is stable?",
    "cooperation": "Can cooperation between actors be sustained?",
    "collective": "Will enough actors contribute to the shared goal?",
    "churn": "Which states do actors move between, and where does it settle?",
    "growth": "What limits growth and where is the steady state?",
    "feedback": "Which feedback loops dominate?",
    "tipping": "Is there a critical mass, and are we above it?",
    "uncertainty": "How wide is the range of outcomes?",
    "risk": "How likely is a critical downside?",
    "network": "How does the structure of connections shape the outcome?",
    "concentration": "How concentrated are value and dependency?",
    "exploration": "Which option is best, and how much to experiment?",
    "trend": "What does the observed trend imply?",
}

NUMBER = re.compile(r"\d")


def _hits(text: str, stems: list[str]) -> int:
    return sum(text.count(s) for s in stems)


def structure_problem(inp: ProblemInput) -> ProblemStructure:
    text = " " + f"{inp.description} {inp.objective} {inp.decision_scope} {inp.system_boundaries}".lower() + " "
    types = {}
    for tag, stems in KEYWORDS.items():
        n = _hits(text, stems)
        if n:
            types[tag] = round(min(1.0, 0.6 + 0.2 * (n - 1)), 2)
    types = dict(sorted(types.items(), key=lambda kv: -kv[1]))

    actors = [Actor(name=a) for a in inp.actors]
    variables = []
    if inp.objective:
        variables.append(Variable(name=f"Objective: {inp.objective[:80]}", kind="outcome", origin="user_input"))
    for tag in types:
        if tag in VARIABLES:
            name, kind = VARIABLES[tag]
            variables.append(Variable(name=name, kind=kind))
    if inp.available_data:
        variables.append(Variable(name=f"Data: {inp.available_data[:80]}", kind="data", origin="user_input"))
    names = {v.name for v in variables}
    relations = [Relation(source=VARIABLES[s][0], target=VARIABLES[t][0], relation=r, polarity=pol)
                 for s, t, r, pol in LINKS if VARIABLES[s][0] in names and VARIABLES[t][0] in names]
    data_vars = [v for v in variables if v.kind == "data"]
    outcomes = [v for v in variables if v.kind == "outcome"]
    if data_vars and outcomes:
        relations.append(Relation(source=data_vars[0].name, target=outcomes[0].name, relation="correlates",
                                  polarity="?", status="correlational"))

    subproblems = [q for tag, q in SUBPROBLEMS.items() if tag in types][:6] or [
        "What drives the outcome, and which levers do we control?"]
    criteria = _criteria(inp, text, types, actors, relations)
    gaps = []
    if criteria["data_availability"] < 0.4:
        gaps.append("No quantitative data provided — all model parameters are assumptions.")
    if not inp.objective:
        gaps.append("No explicit objective — recommendations cannot be ranked against a goal.")
    if not inp.actors:
        gaps.append("No actors named — strategic models use generic players.")
    return ProblemStructure(
        restated_problem=inp.description[:500], objective=inp.objective or "not specified",
        problem_types=types, subproblems=subproblems, actors=actors, variables=variables, relations=relations,
        criteria=criteria, data_gaps=gaps,
    )


def _criteria(inp, text, types, actors, relations) -> dict[str, float]:
    def tag(*names):
        return max((types.get(n, 0.0) for n in names), default=0.0)

    data = inp.available_data.lower()
    data_score = 0.1
    if data:
        data_score = 0.4 + (0.3 if NUMBER.search(data) else 0) + (
            0.2 if re.search(r"month|monat|year|jahr|week|woche|history|histor|csv|series|reihe|daily|täglich", data) else 0)
    temporal = 0.2 + (0.5 if inp.time_horizon else 0) + (0.3 if tag("dynamics", "growth", "adoption", "churn", "trend") else 0)
    decision = 0.2 + (0.5 if inp.decision_scope else 0) + (
        0.3 if re.search(r"should|which|whether|sollen|sollten|entscheid|choose|wählen|welche", text) else 0)
    n_act = len(actors)
    return {
        "problem_type": tag(*types) if types else 0.0,
        "complexity": round(min(1.0, (len(types) + n_act + len(relations)) / 15), 2),
        "data_availability": round(min(1.0, data_score), 2),
        "actors": round(min(1.0, n_act / 4), 2),
        "temporal_dynamics": round(min(1.0, temporal), 2),
        "uncertainty": round(max(0.3, tag("uncertainty", "risk")), 2),
        "interactions": round(min(1.0, 0.15 * n_act + 0.5 * tag("strategy", "network", "competition", "cooperation",
                                                                  "collective", "feedback")), 2),
        "decision_relevance": round(min(1.0, decision), 2),
    }
