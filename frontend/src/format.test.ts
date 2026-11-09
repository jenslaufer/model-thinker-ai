import { describe, expect, it } from 'vitest'
import { executionId, fmt, parseNumber, humanize, metricHelp, paramOriginLabel, parseList, rough, verdictClass } from './format'

describe('fmt', () => {
  it('avoids false precision', () => {
    expect(fmt(0.123456)).toBe('0.123')
    expect(fmt(12.3456)).toBe('12.35')
    expect(fmt(12345.67)).toBe('12,346')
    expect(fmt(5)).toBe('5')
  })
  it('handles non-numbers', () => {
    expect(fmt(null)).toBe('—')
    expect(fmt(true)).toBe('yes')
    expect(fmt('D/D')).toBe('D/D')
  })
  it('formats percentages', () => {
    expect(fmt(0.256, 'pct')).toBe('25.6%')
  })
})

describe('helpers', () => {
  it('humanizes keys', () => expect(humanize('p_hit_threshold')).toBe('P hit threshold'))
  it('labels origins', () => expect(paramOriginLabel('ai_estimate')).toBe('AI estimate'))
  it('parses comma/newline lists', () => expect(parseList('a, b\nc,, ')).toEqual(['a', 'b', 'c']))
})

describe('metricHelp', () => {
  const help = { peak_time: 'Peak period', 'stationary_*': 'Long-run share' }
  it('finds exact and prefix matches', () => {
    expect(metricHelp(help, 'peak_time')).toBe('Peak period')
    expect(metricHelp(help, 'stationary_Active')).toBe('Long-run share')
    expect(metricHelp(help, 'other')).toBe('')
    expect(metricHelp(undefined, 'x')).toBe('')
  })
})

describe('question-first helpers', () => {
  it('keys executions by instance', () => {
    expect(executionId({ model_key: 'normal', instance: '' })).toBe('normal')
    expect(executionId({ model_key: 'normal', instance: 'normal:wide' })).toBe('normal:wide')
  })
  it('rounds estimate-based results to two significant figures', () =>
    expect([224.22, 38412, 0.03369, 7].map(rough)).toEqual(['220', '38,000', '0.034', '7']))
  it('colours verdicts', () => {
    expect(verdictClass('likely')).toContain('accent')
    expect(verdictClass('unlikely')).toContain('assumption')
    expect(verdictClass('no_target')).toContain('line')
  })
})

describe('parseNumber', () => {
  it('reads thousands separators and decimal commas', () =>
    expect(['1,000', '1.000', '1 000', '2,5', '0.05', '12'].map(parseNumber)).toEqual([1000, 1000, 1000, 2.5, 0.05, 12]))
  it('tells empty from invalid', () => {
    expect(parseNumber('  ')).toBeNull()
    expect(parseNumber('abc')).toBeNaN()
  })
})
