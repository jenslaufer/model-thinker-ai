import type { Origin, ParamOrigin, Verdict } from './api'

/** Number format without false precision. */
export function fmt(v: unknown, mode: 'num' | 'pct' = 'num'): string {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'boolean') return v ? 'yes' : 'no'
  if (typeof v !== 'number') return String(v)
  if (!Number.isFinite(v)) return '∞'
  if (mode === 'pct') return `${(v * 100).toFixed(1)}%`
  const a = Math.abs(v)
  if (a >= 1000) return v.toLocaleString('en-US', { maximumFractionDigits: 0 })
  if (a >= 1) return String(Number(v.toFixed(2)))
  if (a === 0) return '0'
  return String(Number(v.toPrecision(3)))
}

/** A number as people type it: 1,000 · 1.000 · 1 000 · 2,5. Empty → null, unreadable → NaN. */
export function parseNumber(text: string): number | null {
  const t = text.trim().replace(/\s/g, '')
  if (!t) return null
  if (/^\d{1,3}([.,]\d{3})+$/.test(t)) return Number(t.replace(/[.,]/g, ''))
  return /^-?\d+([.,]\d+)?$/.test(t) ? Number(t.replace(',', '.')) : NaN
}

/** Two significant figures, for results that rest on estimates (220, 38,000, 0.034). */
export const rough = (v: number) => fmt(v ? Number(v.toPrecision(2)) : 0)

/** Execution id: the model key, or "key:label" when one analysis runs a model more than once. */
export const executionId = (e: { model_key: string; instance?: string }) => e.instance || e.model_key

export const verdictClass = (s: Verdict['status']) => ({
  likely: 'border-accent/40 bg-accent-soft',
  solved: 'border-accent/40 bg-accent-soft',
  unlikely: 'border-assumption/40 bg-assumption/10',
  unclear: 'border-assumption/30 bg-assumption/5',
  no_target: 'border-line bg-panel',
  no_goal_metric: 'border-line bg-panel',
})[s]

export const humanize = (key: string) => {
  const s = key.replace(/_/g, ' ')
  return s.charAt(0).toUpperCase() + s.slice(1)
}

export const ORIGIN_LABEL: Record<Origin, string> = {
  computed: 'Computed',
  assumption: 'Assumption',
  rule_interpretation: 'Rule-based interpretation',
  ai_interpretation: 'AI interpretation',
  user_input: 'User input',
}

export const paramOriginLabel = (o: ParamOrigin) =>
  ({ default_assumption: 'Default assumption', user_input: 'User input', ai_estimate: 'AI estimate' })[o]

export const parseList = (text: string) =>
  text.split(/[,\n]/).map((s) => s.trim()).filter(Boolean)

export const FAMILY: Record<string, string> = {
  A: 'Distributions & mathematical models',
  B: 'Networks & information',
  C: 'Dynamic & strategic',
}

/** Deep copy of plain JSON data (works on Vue reactive proxies, unlike structuredClone). */
export const clone = <T>(v: T): T => (v === undefined ? v : JSON.parse(JSON.stringify(v)))

/** Plain meaning of a metric; keys ending in "*" match every metric with that prefix. */
export const metricHelp = (help: Record<string, string> | undefined, key: string) =>
  help?.[key] ?? Object.entries(help ?? {}).find(([k]) => k.endsWith('*') && key.startsWith(k.slice(0, -1)))?.[1] ?? ''
