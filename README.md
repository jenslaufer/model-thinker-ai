# Model Thinking AI — Multi-Model Intelligence Framework

A decision platform built on Scott E. Page's book *The Model Thinker: What You Need to Know to Make Data Work for
You* (Basic Books, 2018). Describe a problem in plain language; the system structures it, scores the book's 24 model
families for fit, executes a complementary set of mathematical models, compares their perspectives (without
averaging them), computes scenarios, sensitivity and Monte Carlo, and derives traceable recommendations.

**Core rule:** an LLM may structure problems and propose parameters. It never produces numbers. Every number comes
from a deterministic, tested model implementation, and the UI labels each statement as *Computed*, *Assumption*,
*Rule-based interpretation* or *AI interpretation*.

## How it was built

After reading the book, I wrote one prompt and let [Claude Code](https://claude.com/claude-code) build the app from
it: [`docs/master-prompt.md`](docs/master-prompt.md) (German, verbatim). Later sessions added the question-first
Answer page and the AI setup with transparent estimates. It is an experiment, not a validated product: with
questions that come without data, the models compute assumptions precisely, and the answers can look more certain
than they are.

## Build and run

You need [Docker](https://docs.docker.com/get-docker/) with Docker Compose. Nothing else.

```bash
git clone <this repository> model-thinking-ai
cd model-thinking-ai
docker compose up --build -d
```

Open http://localhost:8080. There is no sign-in: the app runs as one local workspace and is reachable from your
machine only. The first build takes a few minutes.

- **Without an API key** the app structures problems with a keyword heuristic and runs the models on example
  parameter values. The Answer page says so.
- **With the AI setup** Claude reads the question, frames the goal, picks the models and estimates every parameter
  with a reason and a confidence. You need an [Anthropic API key](https://console.anthropic.com/):

  ```bash
  LLM_PROVIDER=anthropic ANTHROPIC_API_KEY=sk-ant-... docker compose up --build -d
  ```

  One analysis takes one to two minutes and makes a few dozen API calls.

Start with one of the example problems on *New Analysis*. Stop with `docker compose down`
(`docker compose down -v` also deletes the database).

## Development

```bash
# Backend (Python 3.12+, uv) — without sign-in
cd backend && uv sync && AUTH_DEV_MODE=1 uv run uvicorn app.main:app --reload --port 8000

# Frontend (Node 24)
cd frontend && npm install && npm run dev        # http://localhost:5173, proxies /api to :8000

# Tests
cd backend && uv run pytest && uv run ruff check app tests
cd backend && uv run pytest -m live   # example set with the real AI setup (needs ANTHROPIC_API_KEY)
cd frontend && npm test && npm run build
```

Configuration (environment):

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./data/model_thinking.db` | SQLAlchemy URL; Compose uses PostgreSQL |
| `AUTH_DEV_MODE` | Compose: `1` | `1` = no sign-in, one local workspace. Outside Compose the backend refuses to start without it or an issuer |
| `OIDC_ISSUER_URL` | — | OIDC issuer; enables sign-in and takes precedence over `AUTH_DEV_MODE` (see "Sign-in") |
| `OIDC_CLIENT_ID` | — | Public PKCE client; also checked as token audience |
| `OIDC_JWKS_URI` | `{issuer}/auth/jwks` | Override, e.g. an internal Docker URL |
| `LLM_PROVIDER` | `heuristic` | `anthropic` enables Claude via the Messages API: goal frame, model choice, estimates for every parameter, structuring, narrative (needs `ANTHROPIC_API_KEY`) |
| `ANTHROPIC_API_KEY` / `ANTHROPIC_MODEL` | — / `claude-opus-5-5` | Claude credentials and model |
| `PORT` / `BIND` | `8080` / `127.0.0.1` | Compose: published port and address. `BIND=0.0.0.0` opens the app to the network — only with sign-in |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated allowed origins |

## Architecture

```
frontend/  Vue 3 + Vite + TypeScript + Tailwind 4 + Vue Router · Plotly · Vue Flow · KaTeX
backend/
  app/modeling/   Model contract (ParamSpec, ModelOutput, Claim) + 14 implemented models, 10 catalogued
  app/engine/     structure → selection → orchestrator → scenarios → graph (pure Python, no I/O)
  app/llm/        Provider protocol: heuristic (offline, default) | anthropic (Messages API)
  app/db.py       SQLAlchemy entities; repo.py persists/restores revisions; report.py renders Markdown
  app/main.py     FastAPI routes
```

Decisions:

- **Computation separate from AI.** Models implement `Model.compute(params, rng) -> ModelOutput`. The LLM layer only
  returns validated structures (tags from a fixed vocabulary, scalar parameters within `ParamSpec` bounds).
- **Standard result structure.** Every model returns metrics, series, tables, *claims* on shared dimensions
  (`outcome_trend`, `risk_level`, `leverage`, `predictability`, `concentration`, `cooperation`), rule-based
  interpretation, recommendations, warnings and a calculation log.
- **Contradictions, not averages.** The comparison detects opposite claims on the same dimension and reports them
  with the assumptions behind each side. Metrics of different models are never combined.
- **Reproducibility.** Fixed seeds; each execution stores model version, parameters (with origin), an input hash,
  and its results. Re-runs create new revisions; history stays.
- **Synchronous execution.** An analysis takes a few seconds (models run in a thread pool). Redis/background jobs
  are not needed yet.

### Analysis protocol (phases)

| Phase | Implementation |
|---|---|
| 1 Understand / 2 Decompose | `engine/structure.py` (keyword heuristic, DE+EN) or Claude; actors, variables, hypothesised relations, 8 criteria |
| 2b Frame the goal | `engine/goal.py` `GoalFrame`: quantity, target or risk limit, horizon, lever. From the form's target fields or Claude; **never estimated** — without a target the answer explains instead of judging |
| 3 Select | Claude picks 3–6 models with a reason each and names angles no model covers; fallback and cross-check `engine/selection.py`: Model Fit Score 0–100 = problem-type match 40 + actors 10 + time 15 + data 15 + uncertainty 10 + interactions 10; diversity penalty for repeated perspectives |
| 4 Parameterize | User numbers first; otherwise Claude estimates every parameter (scalars, vectors, matrices) with a reason and a confidence, labelled *AI estimate*; invalid estimates fall back to the default and say why. Reruns reuse the recorded setup (`orchestrator.Setup`), so results move only when the user changes an input. One analysis can run a model several times (`key:label` instances) |
| 5 Execute | `engine/orchestrator.py`; one failing model does not stop the analysis |
| 6 Compare | Side-by-side table, contradictions, convergences |
| 7 Simulate | `engine/scenarios.py`: baseline, best, worst, single-lever alternative, stress (2× band), what-if; one-at-a-time sensitivity; Monte Carlo (triangular ±band) |
| 8 Synthesize | Rule-based statements; optional AI narrative labelled as such. `engine/goal.py` computes per model the goal metric (declared in `ModelSpec.goal_metrics`), the drivers (non-user values ranked by their effect on it, incl. transition-matrix entries) and a goal seek (bisection on one lever, ±10× the current value); across models it explains outliers by their top driver. `engine/answer.py` turns this into the question-first answer: verdict, results side by side, why models differ, biggest unknowns, what it would take, other angles, and how it was set up |
| 9 Decide | Priority = fit score × confidence weight; plus items for contradictions and data gaps |
| 10 Evaluate | *Partial:* evidence can be recorded per analysis; not yet fed back into models |

### Model library

| # | Model | Status | Analytic tests |
|---|---|---|---|
| 1 | Normal distribution | ✅ | tail probability, quantiles |
| 2 | Power law / long tail | ✅ | 80/20 at α = ln5/ln4, infinite-mean warning |
| 3 | Linear models (OLS / assumed projection) | ✅ | exact fit, prediction interval, mismatch rejected |
| 4 | Concavity and convexity | catalogued | — |
| 5 | Value and power (Shapley) | catalogued | — |
| 6 | Network models | ✅ | random-graph degree, scale-free hubs |
| 7 | Broadcast, diffusion, contagion (Bass) | ✅ | closed-form F(t), peak time ln(q/p)/(p+q) |
| 8 | Entropy | ✅ | uniform = log₂n, certain = 0 |
| 9 | Random walk | ✅ | E = x₀+μT, SD = σ√T, deterministic limit |
| 10 | Path dependence | catalogued | — |
| 11 | Local interaction | catalogued | — |
| 12 | Lyapunov / equilibrium | catalogued | — |
| 13 | Markov models | ✅ | stationary distribution, stochastic-matrix validation |
| 14 | System dynamics (stock & flow) | ✅ | equilibrium K(1−d/r), collapse when d > r |
| 15 | Threshold and feedback (Granovetter) | ✅ | tipping vs. stall at the threshold |
| 16 | Spatial / hedonic choice | catalogued | — |
| 17 | Game theory (2-player normal form) | ✅ | prisoner's dilemma, matching pennies mixed NE |
| 18 | Cooperation (repeated PD) | ✅ | critical δ = (T−R)/(T−P) |
| 19 | Collective action (public goods) | ✅ | MPCR, free-riding, optimum vs. Nash payoff |
| 20 | Mechanism design | catalogued | — |
| 21 | Signaling | catalogued | — |
| 22 | Learning models | catalogued | — |
| 23 | Multi-armed bandit | ✅ | Thompson/UCB beat uniform allocation |
| 24 | Rugged landscapes (NK) | catalogued | — |

Catalogued models have a detail page but are never selected or executed. To add a model: subclass `Model` in
`app/modeling/family_*.py`, define its `ModelSpec`, append it to `MODELS`, add analytic tests to
`tests/test_models.py`. The parametrized tests enforce documentation, reproducibility and finite outputs.

### Sign-in (optional)

Without an issuer the app has no sign-in and one workspace. To serve it to several people, put it behind HTTPS and
set an OIDC provider that supports the authorization code flow with PKCE for a public client:

```bash
OIDC_ISSUER_URL=https://<issuer> OIDC_CLIENT_ID=<public client id> BIND=0.0.0.0 docker compose up --build -d
```

Register `https://<host>/callback` as redirect URI and `https://<host>/` as post-logout URI on the client. Browsers
allow PKCE only on `https` or `localhost`. The backend validates RS256 access tokens against the issuer's JWKS
(`{issuer}/auth/jwks`, override with `OIDC_JWKS_URI`); each user (`sub`) gets a personal workspace. The frontend
reads issuer and client ID at runtime from `/api/auth/config`, so the same image works everywhere. Tokens live in
`sessionStorage`; on a 401 the client tries the refresh token once, then signs in again.

## Data model

`Workspace` ← `User`, `Project` ← `Analysis` ← `AnalysisRevision` (settings, selection, comparison, synthesis).
Per revision: `ProblemDefinition` (input + structure) ← `Actor`, `Variable`, `Hypothesis`;
`ModelExecution` (→ `Model`, `ModelVersion`) ← `ModelParameter` (value + origin), `ModelResult`, `Scenario`,
`Simulation` (sensitivity, Monte Carlo); `Recommendation` (decision status, note); `Report`; `Evidence`;
`AuditLog`. Tables are created on startup (`create_all`); there are no migrations yet.

## API (all under `/api`)

| Method & path | Purpose |
|---|---|
| `GET /models`, `GET /models/{key}` | Library and model specification |
| `POST /models/{key}/run` | Run one model `{params, seed}` |
| `POST /models/{key}/simulate` | Scenarios, sensitivity, Monte Carlo `{params, band, draws, what_if}` |
| `POST /structure` | Structure a problem and preview the selection |
| `POST /frame` | Goal frame and missing goal fields (`target`, `risk_limit`, `quantity`) for the ask-once step |
| `GET/POST /analyses` | List / create (runs the full pipeline) |
| `GET /analyses/{id}?revision=` · `GET /analyses/{id}/revisions` | Reopen any revision |
| `POST /analyses/{id}/rerun` | New revision `{selected, overrides, what_if, band}` |
| `GET /analyses/{id}/graph` · `GET /analyses/{id}/report` | Knowledge graph · Markdown report |
| `GET/POST /analyses/{id}/evidence` | Evidence log |
| `PATCH /recommendations/{id}` | Decision status `open/accepted/rejected/deferred` |
| `GET /dashboard` · `GET /settings` · `GET /audit` · `GET/POST /projects` | Overview, status, audit log |

## User interface

Dashboard · New Analysis (example problems, structure preview, optional success target; asks once when the AI
finds the target missing) · Answer (the landing page after a run: verdict on the user's question, model results in
the goal's units side by side, why models differ, biggest unknowns, what it would take, other angles, and every
value the user did not enter with its reason and confidence) ·
Problem Explorer · Model Library
(KaTeX formulas, live runs) · Model Selection (scores, components, reasons; re-run a changed set) · Model
Results (synthesis, contradictions, comparison table, one column per model) · Scenario Lab (sliders, scenario
chart, tornado, Monte Carlo; save as what-if revision or new baseline) · Simulation Center (any model, Monte Carlo
summary, categorical robustness) · Knowledge Graph (Vue Flow; causal, feedback and correlational edges styled
apart) · Decision Center (accept/defer/reject, evidence log) · Reports (sanitised Markdown, download) · Settings
(runtime, feature status, audit log).

## Security status

| Requirement | Status |
|---|---|
| Input validation | ✅ Pydantic on every body; model parameters validated against `ParamSpec` (types, bounds, shapes) |
| Prompt-injection protection | ✅ User text passed as delimited data; structured outputs; fixed tag vocabulary; bounds-checked proposals; fallback to heuristic |
| Tenant separation | ✅ Every query scoped by workspace (tested) |
| Audit log | ✅ Create, re-run, decision, evidence, project |
| XSS | ✅ Report HTML sanitised with DOMPurify |
| Authentication | ✅ Optional sign-in via OIDC (code flow + PKCE); off by default (one local workspace). The backend validates RS256 access tokens against the tenant JWKS (issuer, audience, expiry); ID tokens and `client_credentials` tokens are rejected. Each user (`sub`) gets a personal workspace. With sign-in, every route except `/api/health` and `/api/auth/config` requires a token |
| Authorization (RBAC) | ⚠ Partial: the roles `admin` and `user` are accepted and stored; both have full access to their own workspace. Shared team workspaces are not built yet |
| Encryption at rest | ❌ Delegate to database/disk encryption |
| TLS | ❌ Terminate at a reverse proxy in front of Compose |

## Implementation status

| Phase | Status |
|---|---|
| 1 Foundation | ✅ Architecture, data model, UI, library, ≥ 5 models |
| 2 Analytics | ✅ 14 of 24 families executable; selection engine; orchestration |
| 3 Simulation | ✅ Scenarios, Monte Carlo, sensitivity, interactive charts |
| 4 Intelligence | ✅ Optional Claude provider, knowledge graph, decision center, reports · ⚠ evidence not yet fed back |
| 5 Production | ⚠ Tests, Docker Compose, PostgreSQL verified, optional OIDC sign-in · ❌ team workspaces/fine-grained roles, migrations, monitoring, background jobs |

Known limits:

- The keyword structurer is shallow; it detects aspects, not mechanisms. Claude improves structuring but is optional.
- The Model Fit Score is a heuristic. The diversity penalty can pull in a weakly fitting model; adjust in Model Selection.
- Default parameters are generic examples. Results based on them are scenarios, not forecasts — the UI says so.
- Without the Claude provider, numbers in the problem text are not extracted: a form-only run uses example values
  everywhere, and the Answer page says so.
- Verdicts rest on models that declare a goal metric for the user's quantity. Goal seek moves one lever within ±10×
  of its current value; a target further away shows as not reachable.
- The example set (`backend/tests/cases/`) holds anonymised cases only; expected conclusions come from outside the
  app (analytic results or conclusions reviewed by hand).
- Monte Carlo bands express assumption uncertainty (±band), not empirically estimated distributions.
- The frontend bundle includes Plotly (~1.4 MB gzip, lazy-loaded).

## License

MIT, see [LICENSE](LICENSE). The model families and their names follow Scott E. Page, *The Model Thinker*; the book
is not included.
