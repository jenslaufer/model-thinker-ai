// Typed client for the FastAPI backend (/api, proxied by Vite in dev, Nginx in prod).
import { login, refresh, session } from './auth'

export type Origin = 'computed' | 'assumption' | 'rule_interpretation' | 'ai_interpretation' | 'user_input'
export type ParamOrigin = 'default_assumption' | 'user_input' | 'ai_estimate'
export type Confidence = 'high' | 'medium' | 'low' | 'unknown'
export type Scalar = number | string | boolean | null

export interface ParamSpec {
  name: string
  label: string
  type: 'float' | 'int' | 'bool' | 'choice' | 'vector' | 'matrix' | 'labels'
  default: unknown
  min: number | null
  max: number | null
  choices: string[] | null
  unit: string
  description: string
  uncertain: boolean
}

export interface ModelSummary {
  key: string
  number: number
  name: string
  family: 'A' | 'B' | 'C'
  implemented: boolean
  summary: string
  perspective: string
  version: string
}

export interface ModelSpec extends ModelSummary {
  description: string
  math: string
  assumptions: string[]
  prerequisites: string[]
  limits: string[]
  examples: string[]
  use_cases: string[]
  params: ParamSpec[]
  primary_metric: string | null
  primary_goal: 'maximize' | 'minimize'
  tags: Record<string, number>
  question: string
  metric_help: Record<string, string>
}

export interface Series {
  name: string
  x: (number | string)[]
  y: number[]
  kind: 'line' | 'bar' | 'area' | 'scatter'
  x_label: string
  y_label: string
}

export interface Statement { text: string; origin: Origin }
export interface Claim { dimension: string; direction: number; statement: string }

export interface Recommendation {
  title: string
  rationale: string
  expected_impact: string
  prerequisites: string[]
  risks: string[]
  uncertainty: 'low' | 'medium' | 'high'
  horizon: 'short' | 'medium' | 'long'
  actions: string[]
  origin: Origin
}

export interface PrioritizedRecommendation extends Recommendation {
  id: string
  priority: number
  source_models: string[]
  evidence: string[]
  db_id?: number
  decision_status?: 'open' | 'accepted' | 'rejected' | 'deferred'
  note?: string
}

export interface ModelOutput {
  metrics: Record<string, Scalar>
  series: Series[]
  tables: Record<string, Record<string, unknown>[]>
  claims: Claim[]
  interpretation: Statement[]
  recommendations: Recommendation[]
  warnings: string[]
  log: string[]
}

export interface SensitivityItem {
  param: string
  low_value: number
  high_value: number
  metric_low: number
  metric_high: number
  swing: number
}

export interface Scenario {
  kind: 'baseline' | 'best' | 'worst' | 'alternative' | 'stress' | 'what_if'
  name: string
  description: string
  params: Record<string, unknown>
  metrics: Record<string, Scalar>
  primary: number | null
}

export interface MonteCarlo {
  draws: number
  band: number
  summary: Record<string, { mean: number; sd: number; p05: number; p50: number; p95: number }>
  categorical: Record<string, { baseline: Scalar; baseline_share: number; frequencies: Record<string, number> }>
  histogram: { edges?: number[]; counts?: number[] }
  note: string
}

export interface Driver {
  param: string; entry: number[] | null; label: string; value: number; low: number; high: number
  metric_low: number; metric_high: number; swing: number; origin: string; confidence: Confidence | null; rationale: string
}

export interface Seek {
  param: string; entry: number[] | null; label: string; current: number; target: number; given: string
  value: number | null; status: 'solved' | 'not_reachable' | 'not_monotonic'
}

export interface GoalAnalysis {
  metric: string; value: number | null; p05: number | null; p95: number | null; drivers: Driver[]; seeks: Seek[]
}

export interface Execution {
  model_key: string
  instance: string
  goal: GoalAnalysis | null
  model_name: string
  model_version: string
  status: 'ok' | 'error'
  error: string | null
  fit_score: number
  params: Record<string, { value: unknown; origin: ParamOrigin; rationale: string; confidence: Confidence | null }>
  assumptions: string[]
  limits: string[]
  output: ModelOutput | null
  scenarios: Scenario[]
  sensitivity: SensitivityItem[] | null
  monte_carlo: MonteCarlo | null
  uncertainty: {
    primary_metric?: string
    interval_p05_p95?: [number, number] | null
    relative_interval_width?: number | null
    share_params_from_user?: number
    most_sensitive?: string | null
    warnings?: number
    empirically_validated?: boolean
  }
}

export interface ProblemInput {
  description: string
  objective: string
  time_horizon: string
  system_boundaries: string
  available_data: string
  actors: string[]
  decision_scope: string
  target_quantity?: string
  target_value?: number | null
  risk_limit?: number | null
}

export interface GoalFrame {
  quantity: string
  unit: string
  kind: 'reach_target' | 'maximise_under_risk' | 'compare_options' | 'explain'
  direction: 'at_least' | 'at_most'
  target: number | null
  risk_limits: number[]
  horizon: string
  lever: string
  origin: 'ai' | 'user_input' | 'heuristic'
}

export interface ModelChoice { key: string; instance: string; reason: string; goal_metric: string | null }

export interface ProblemStructure {
  restated_problem: string
  objective: string
  problem_types: Record<string, number>
  subproblems: string[]
  actors: { name: string; role: string; origin: string }[]
  variables: { name: string; kind: string; origin: string }[]
  relations: { source: string; target: string; relation: string; polarity: string; status: string }[]
  criteria: Record<string, number>
  data_gaps: string[]
  origin: 'heuristic' | 'ai' | 'user_input'
}

export interface ModelFit {
  key: string
  name: string
  number: number
  implemented: boolean
  perspective: string
  score: number
  components: Record<string, number>
  reasons: string[]
  blockers: string[]
  missing_data: string[]
}

export interface Selection {
  fits: ModelFit[]
  selected: string[]
  complementary: string[]
  unsuitable: { key: string; name: string; score: number; why: string[] }[]
  note: string
  frame: GoalFrame | null
  choices: ModelChoice[]
  uncovered: string[]
}

export interface Comparison {
  table: { model: string; key: string; primary_metric: string; value: Scalar; p05: number | null; p95: number | null;
    most_sensitive: string | null; claims: string[] }[]
  contradictions: { dimension: string; positive: string[]; negative: string[]; explanation: string }[]
  convergences: { dimension: string; direction: number; models: string[] }[]
  note: string
}

export interface AnalysisResult {
  problem: ProblemInput
  structure: ProblemStructure
  selection: Selection
  executions: Execution[]
  comparison: Comparison
  synthesis: Statement[]
  recommendations: PrioritizedRecommendation[]
  band: number
  seed: number
  provider: string
}

export interface Finding {
  model_key: string
  instance: string
  model_name: string
  question: string
  text: string
  fit: number
  data_source: 'example values' | 'AI estimates' | 'partly your numbers' | 'your numbers'
}

export interface Verdict {
  status: 'likely' | 'unlikely' | 'unclear' | 'solved' | 'no_target' | 'no_goal_metric'
  text: string
}

export interface GoalResult {
  instance: string; model_name: string; measures: string; value: number; p05: number | null; p95: number | null
}

export interface Unknown {
  instance: string; model_name: string; label: string; value_text: string; origin: string
  confidence: Confidence | null; rationale: string; effect_text: string
}

export interface EstimateRow {
  instance: string; model_name: string; param: string; param_label: string; value_text: string; origin: string
  confidence: Confidence | null; rationale: string
}

export interface Answer {
  question: string
  frame: GoalFrame | null
  reliability: 'illustrative' | 'estimated' | 'rough' | 'grounded'
  reliability_text: string
  verdict: Verdict
  goal_results: GoalResult[]
  differences: string[]
  unknowns: Unknown[]
  what_it_takes: string[]
  other_angles: Finding[]
  plain: Record<string, string>
  setup: { choices: ModelChoice[]; uncovered: string[]; estimates: EstimateRow[] }
}

export interface AnalysisDetail {
  id: number
  title: string
  project_id: number
  revision: number
  latest_revision: number
  created_at: string
  updated_at: string
  result: AnalysisResult
  answer: Answer
  recommendations: PrioritizedRecommendation[]
}

export interface AnalysisListItem {
  id: number
  title: string
  project: string
  revision: number
  updated_at: string
  models: string[]
}

export interface GraphData {
  nodes: { id: string; type: string; label: string; data: Record<string, unknown> }[]
  edges: { id: string; source: string; target: string; relation: string; causal: boolean; data: Record<string, unknown> }[]
}

export interface SimulateResult {
  output: ModelOutput
  sensitivity: SensitivityItem[]
  scenarios: Scenario[]
  monte_carlo: MonteCarlo
}

export interface RerunBody {
  selected?: string[]
  overrides?: Record<string, Record<string, unknown>>
  what_if?: Record<string, Record<string, unknown>>
  band?: number
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(method: string, path: string, body?: unknown, retried = false): Promise<T> {
  const headers: Record<string, string> = body ? { 'Content-Type': 'application/json' } : {}
  if (session.accessToken) headers.Authorization = `Bearer ${session.accessToken}`
  const res = await fetch(`/api${path}`, { method, headers, body: body ? JSON.stringify(body) : undefined })
  if (res.status === 401 && session.config?.mode === 'oidc') {
    if (!retried && (await refresh())) return request<T>(method, path, body, true)
    await login()
    throw new ApiError(401, 'Session expired — redirecting to sign-in')
  }
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}))
    const msg = typeof detail.detail === 'string' ? detail.detail
      : Array.isArray(detail.detail) ? detail.detail.map((d: { msg: string }) => d.msg).join('; ')
        : res.statusText
    throw new ApiError(res.status, msg)
  }
  return res.json() as Promise<T>
}

export const api = {
  models: () => request<ModelSummary[]>('GET', '/models'),
  model: (key: string) => request<ModelSpec>('GET', `/models/${key}`),
  runModel: (key: string, params: Record<string, unknown>) =>
    request<ModelOutput>('POST', `/models/${key}/run`, { params }),
  simulate: (key: string, body: { params: Record<string, unknown>; band?: number; draws?: number; what_if?: Record<string, unknown> }) =>
    request<SimulateResult>('POST', `/models/${key}/simulate`, body),
  frame: (problem: ProblemInput) =>
    request<{ frame: GoalFrame; missing: ('quantity' | 'target' | 'risk_limit')[] }>('POST', '/frame', problem),
  structure: (problem: ProblemInput) =>
    request<{ structure: ProblemStructure; selection: Selection }>('POST', '/structure', problem),
  analyses: () => request<AnalysisListItem[]>('GET', '/analyses'),
  analysis: (id: number, revision?: number) =>
    request<AnalysisDetail>('GET', `/analyses/${id}${revision ? `?revision=${revision}` : ''}`),
  createAnalysis: (body: { problem: ProblemInput; title?: string; selected?: string[]; band?: number }) =>
    request<AnalysisDetail>('POST', '/analyses', body),
  rerun: (id: number, body: RerunBody) => request<AnalysisDetail>('POST', `/analyses/${id}/rerun`, body),
  revisions: (id: number) =>
    request<{ revision: number; created_at: string; settings: Record<string, unknown>; band: number }[]>(
      'GET', `/analyses/${id}/revisions`),
  graph: (id: number, revision?: number) =>
    request<GraphData>('GET', `/analyses/${id}/graph${revision ? `?revision=${revision}` : ''}`),
  report: (id: number, revision?: number) =>
    request<{ content: string; revision: number }>('GET', `/analyses/${id}/report${revision ? `?revision=${revision}` : ''}`),
  decide: (dbId: number, decision_status: string, note: string) =>
    request<{ decision_status: string }>('PATCH', `/recommendations/${dbId}`, { decision_status, note }),
  addEvidence: (id: number, body: { description: string; source: string }) =>
    request<{ id: number }>('POST', `/analyses/${id}/evidence`, body),
  evidence: (id: number) =>
    request<{ id: number; description: string; source: string; created_at: string }[]>('GET', `/analyses/${id}/evidence`),
  dashboard: () => request<Dashboard>('GET', '/dashboard'),
  settings: () => request<{ provider: string; database: string; models_implemented: number; models_total: number;
    features: Record<string, string> }>('GET', '/settings'),
  audit: () => request<{ at: string; actor: string; action: string; entity: string; entity_id: number | null;
    detail: Record<string, unknown> }[]>('GET', '/audit'),
}

export interface Dashboard {
  counts: { analyses: number; projects: number; executions: number; open_decisions: number }
  active_analyses: { id: number; title: string; revision: number; updated_at: string }[]
  models_used: [string, number][]
  recent_simulations: { analysis_id: number; analysis: string; model: string; status: string; at: string;
    primary_metric: string | null; interval: [number, number] | null }[]
  insights: { analysis_id: number; analysis: string; text: string; origin: Origin }[]
  open_decisions: { db_id: number; analysis_id: number; analysis: string; title: string; priority: number }[]
}
