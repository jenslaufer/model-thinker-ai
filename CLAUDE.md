# Model Thinking AI

Overview, architecture, API and status: [README.md](README.md).

## Commands

- Backend: `cd backend && uv run pytest && uv run ruff check app tests`
- Frontend: `cd frontend && npm test && npm run build` (build runs `vue-tsc`)
- Dev: `AUTH_DEV_MODE=1 uv run uvicorn app.main:app --reload --port 8000` + `npm run dev` (Vite proxies `/api`)

## Rules

- Models compute; the LLM never does. Every number must come from `Model.compute`. Why: the product promise is
  traceable, non-invented results.
- Label every statement's origin (`computed`, `assumption`, `rule_interpretation`, `ai_interpretation`). Why: users
  must tell calculation from interpretation.
- Never average or merge metrics of different models; report contradictions. Why: incompatible models measure
  different things.
- New model = `Model` subclass + `ModelSpec` + analytic reference test + `PLAIN` entry in `modeling/plain.py`.
  The parametrized tests enforce docs, reproducibility, finite output and a plain explanation of every metric.
  If a metric measures a goal quantity (users, money, a risk), declare it in `goal_metrics` and the params a user
  can move in `levers`; mark real-world unknowns `uncertain=True` so they rank as drivers.
- Never estimate the goal (target, quantity, risk limit). Why: a verdict on an invented goal is worthless.
- Example cases (`tests/cases/`) hold anonymised figures only. Why: the repo may be shared outside.
- Format numbers with `fmt` (backend `modeling/base.py`, frontend `format.ts`). Why: no false precision.

## Quirks

- `key` cannot be a Vue prop; the model route param is `modelKey`.
- Use `clone()` from `format.ts`, not `structuredClone` — it throws on Vue reactive proxies.
- Expensive models set `mc_draws` / `mc_params` in their spec to keep Monte Carlo fast.
- Sign-in is optional OIDC + PKCE; without an issuer the app runs without sign-in. Backend tests either set `AUTH_DEV_MODE=1` (X-Workspace header) or patch
  `auth.make_jwks_client` and sign tokens with a test RSA key (`tests/test_auth.py`).
- New API routes go on the `api` router in `main.py`; only routes on `app` are public.
