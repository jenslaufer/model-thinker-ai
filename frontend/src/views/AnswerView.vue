<script setup lang="ts">
import AnalysisGate from '../components/AnalysisGate.vue'
import OriginBadge from '../components/OriginBadge.vue'
import type { Answer, Confidence, Finding } from '../api'
import { rough, verdictClass } from '../format'

const TRUST: Record<Answer['reliability'], { label: string; cls: string }> = {
  illustrative: { label: 'Example values only', cls: 'border-assumption/40 bg-assumption/10' },
  estimated: { label: 'Mostly AI estimates', cls: 'border-ai/30 bg-ai/5' },
  rough: { label: 'Rough guide', cls: 'border-assumption/30 bg-assumption/5' },
  grounded: { label: 'Based on your numbers', cls: 'border-accent/30 bg-accent-soft' },
}
const SOURCE_CLS: Record<Finding['data_source'], string> = {
  'example values': 'text-assumption', 'AI estimates': 'text-ai', 'partly your numbers': 'text-user', 'your numbers': 'text-user',
}
const CONF_CLS: Record<Confidence, string> = { high: 'text-user', medium: 'text-ai', low: 'text-assumption', unknown: 'text-muted' }
const ORIGIN_TEXT: Record<string, string> = { ai_estimate: 'AI estimate', default_assumption: 'example value' }
const range = (lo: number | null, hi: number | null) => (lo === null || hi === null ? '—' : `${rough(lo)}–${rough(hi)}`)
const card = (id: number, instance: string) => ({ path: '/analysis', query: { analysis: id }, hash: `#${instance}` })
const lab = (id: number, instance: string) => ({ path: '/scenarios', query: { analysis: id, model: instance } })
</script>

<template>
  <AnalysisGate title="Answer" subtitle="Your question answered from the computed model results. The numbers behind it are on the other pages.">
    <template #default="{ analysis }">
      <div v-if="analysis.answer" class="max-w-3xl space-y-6">
        <section>
          <div class="text-xs font-semibold uppercase tracking-[0.08em] text-muted">Your question</div>
          <p class="mt-1 text-xl font-medium leading-snug">{{ analysis.answer.question }}</p>
          <p v-if="analysis.answer.frame?.target !== null && analysis.answer.frame?.target !== undefined" class="mt-1 text-sm text-muted">
            Success means {{ analysis.answer.frame.direction === 'at_most' ? 'at most' : 'at least' }}
            {{ rough(analysis.answer.frame.target) }} {{ analysis.answer.frame.quantity }}<template v-if="analysis.answer.frame.horizon"> within {{ analysis.answer.frame.horizon }}</template>.</p>
        </section>

        <section :class="['rounded border px-4 py-3', verdictClass(analysis.answer.verdict.status)]">
          <div class="flex flex-col-reverse items-start gap-2 sm:flex-row sm:justify-between sm:gap-3">
            <p class="text-lg font-medium leading-snug">{{ analysis.answer.verdict.text }}</p>
            <OriginBadge origin="rule_interpretation" />
          </div>
        </section>

        <section :class="['rounded border px-4 py-3', TRUST[analysis.answer.reliability].cls]">
          <div class="text-sm font-semibold">How far to trust this: {{ TRUST[analysis.answer.reliability].label }}</div>
          <p class="mt-1 text-sm leading-relaxed text-ink/80">{{ analysis.answer.reliability_text }}</p>
        </section>

        <section v-if="analysis.answer.goal_results.length">
          <div class="mb-2 flex items-center justify-between gap-2">
            <h2 class="h-section !mb-0">What each model computes</h2><OriginBadge origin="computed" />
          </div>
          <p class="mb-2 text-sm text-muted">Side by side, never averaged: each model measures in its own way.</p>
          <div class="overflow-x-auto">
            <table class="w-full text-sm">
              <thead><tr class="text-left text-muted"><th class="py-1 pr-3 font-medium">Model</th><th class="py-1 pr-3 font-medium">Measures</th>
                <th class="py-1 pr-3 text-right font-medium">Result</th><th class="py-1 text-right font-medium">Likely range</th></tr></thead>
              <tbody>
                <tr v-for="g in analysis.answer.goal_results" :key="g.instance" class="border-t border-line">
                  <td class="py-1.5 pr-3"><RouterLink :to="card(analysis.id, g.instance)" class="hover:text-accent">{{ g.model_name }}</RouterLink></td>
                  <td class="py-1.5 pr-3 text-muted">{{ g.measures }}</td>
                  <td class="num py-1.5 pr-3 text-right">{{ rough(g.value) }}</td>
                  <td class="num py-1.5 text-right">{{ range(g.p05, g.p95) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section v-if="analysis.answer.differences.length">
          <div class="mb-2 flex items-center justify-between gap-2"><h2 class="h-section !mb-0">Why the models differ</h2><OriginBadge origin="rule_interpretation" /></div>
          <ul class="list-disc space-y-1 pl-5 text-sm"><li v-for="d in analysis.answer.differences" :key="d">{{ d }}</li></ul>
        </section>

        <section v-if="analysis.answer.unknowns.length">
          <h2 class="h-section">Biggest unknowns</h2>
          <ul class="space-y-2">
            <li v-for="u in analysis.answer.unknowns" :key="u.instance + u.label" class="rounded border border-line px-3 py-2 text-sm">
              <div class="font-medium">{{ u.label }} <span class="font-normal text-muted">— {{ u.model_name }}</span></div>
              <p class="mt-0.5">Now {{ u.value_text }} ({{ ORIGIN_TEXT[u.origin] ?? u.origin }}<template v-if="u.confidence">,
                <span :class="CONF_CLS[u.confidence]">confidence {{ u.confidence }}</span></template>) — {{ u.effect_text }}.</p>
              <p v-if="u.rationale" class="mt-0.5 text-muted">Why this value: {{ u.rationale }}</p>
              <RouterLink :to="lab(analysis.id, u.instance)" class="mt-1 inline-block text-xs text-accent hover:underline">Enter your own value →</RouterLink>
            </li>
          </ul>
        </section>

        <section v-if="analysis.answer.what_it_takes.length">
          <div class="mb-2 flex items-center justify-between gap-2"><h2 class="h-section !mb-0">What it would take</h2><OriginBadge origin="computed" /></div>
          <p class="mb-1 text-sm text-muted">The single change in each model that reaches your target, everything else unchanged.</p>
          <ul class="list-disc space-y-1 pl-5 text-sm"><li v-for="w in analysis.answer.what_it_takes" :key="w">{{ w }}</li></ul>
        </section>

        <section v-if="analysis.answer.other_angles.length">
          <div class="mb-2 flex items-center justify-between gap-2"><h2 class="h-section !mb-0">Other angles</h2><OriginBadge origin="rule_interpretation" /></div>
          <ul class="space-y-3">
            <li v-for="f in analysis.answer.other_angles" :key="f.instance" class="panel">
              <div class="text-sm text-muted">{{ f.question }}</div>
              <p class="mt-1 leading-relaxed">{{ f.text }}</p>
              <div class="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
                <RouterLink :to="card(analysis.id, f.instance)" class="hover:text-accent">{{ f.model_name }}</RouterLink>
                <span :class="SOURCE_CLS[f.data_source]">based on {{ f.data_source }}</span>
                <RouterLink :to="lab(analysis.id, f.instance)" class="hover:text-accent">Try your own numbers →</RouterLink>
              </div>
            </li>
          </ul>
        </section>

        <details class="rounded border border-line px-4 py-3">
          <summary class="cursor-pointer text-sm font-semibold">How this was set up</summary>
          <div class="mt-3 space-y-4 text-sm">
            <div v-if="analysis.answer.setup.choices.length">
              <div class="font-medium">Models chosen <OriginBadge origin="ai_interpretation" /></div>
              <ul class="mt-1 list-disc space-y-0.5 pl-5"><li v-for="c in analysis.answer.setup.choices" :key="c.instance">
                <span class="font-medium">{{ c.key }}</span> — {{ c.reason }}</li></ul>
            </div>
            <div v-if="analysis.answer.setup.uncovered.length">
              <div class="font-medium">Not covered by any model</div>
              <ul class="mt-1 list-disc pl-5"><li v-for="u in analysis.answer.setup.uncovered" :key="u">{{ u }}</li></ul>
            </div>
            <div v-if="analysis.answer.setup.estimates.length">
              <div class="font-medium">Values you did not enter</div>
              <div class="mt-1 overflow-x-auto">
                <table class="w-full">
                  <thead><tr class="text-left text-muted"><th class="py-1 pr-3 font-medium">Model</th><th class="py-1 pr-3 font-medium">Value</th>
                    <th class="py-1 pr-3 font-medium">Source</th><th class="py-1 font-medium">Why</th></tr></thead>
                  <tbody>
                    <tr v-for="x in analysis.answer.setup.estimates" :key="x.instance + x.param" class="border-t border-line align-top">
                      <td class="py-1 pr-3 text-muted">{{ x.model_name }}</td>
                      <td class="py-1 pr-3">{{ x.param_label }}: <span class="num break-all">{{ x.value_text }}</span></td>
                      <td class="py-1 pr-3 whitespace-nowrap">{{ ORIGIN_TEXT[x.origin] ?? x.origin }}<span v-if="x.confidence" :class="['block text-xs', CONF_CLS[x.confidence]]">{{ x.confidence }}</span></td>
                      <td class="py-1 text-muted">{{ x.rationale }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </details>

        <p class="text-sm text-muted">
          Want the numbers behind this? See the
          <RouterLink :to="{ path: '/analysis', query: { analysis: analysis.id } }" class="text-accent hover:underline">model results</RouterLink>
          or the <RouterLink :to="{ path: '/reports', query: { analysis: analysis.id } }" class="text-accent hover:underline">full report</RouterLink>.
        </p>
      </div>
    </template>
  </AnalysisGate>
</template>
