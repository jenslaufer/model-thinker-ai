<script setup lang="ts">
import { onUpdated } from 'vue'
import { useRoute } from 'vue-router'
import AnalysisGate from '../components/AnalysisGate.vue'
import OriginBadge from '../components/OriginBadge.vue'
import PlotChart from '../components/PlotChart.vue'
import { executionId, fmt, humanize } from '../format'
import type { AnalysisDetail, Execution } from '../api'

const primary = (e: Execution) => e.uncertainty.primary_metric ?? ''
const plain = (a: AnalysisDetail, e: Execution) => a.answer?.plain[executionId(e)]
// Answer-page links point at a card (#instance); the cards sit in a horizontal strip and load late.
const route = useRoute()
let shown = ''
onUpdated(() => {
  const id = decodeURIComponent(route.hash.slice(1))
  if (!id || id === shown) return
  const el = document.getElementById(id)
  if (el) { el.scrollIntoView({ block: 'start', inline: 'start', behavior: 'smooth' }); shown = id }
})
const shortParams = (e: Execution) => Object.entries(e.params).filter(([, p]) => typeof p.value !== 'object')
</script>

<template>
  <AnalysisGate title="Model results" subtitle="Phases 5–8: each model computed independently. Results are compared side by side, never averaged.">
    <template #default="{ analysis }">
      <div class="mb-6 grid gap-6 xl:grid-cols-2">
        <section class="panel">
          <h2 class="h-section">Synthesis</h2>
          <ul class="space-y-2 text-sm">
            <li v-for="(s, i) in analysis.result.synthesis" :key="i"><OriginBadge :origin="s.origin" /> {{ s.text }}</li>
          </ul>
        </section>
        <section class="panel">
          <h2 class="h-section">Contradictions & agreement</h2>
          <p v-if="!analysis.result.comparison.contradictions.length && !analysis.result.comparison.convergences.length" class="text-sm text-muted">
            The models make no claims on shared dimensions.</p>
          <div v-for="c in analysis.result.comparison.contradictions" :key="c.dimension" class="mb-4 border-l-2 border-danger pl-3">
            <div class="text-sm font-medium">Disagreement on {{ humanize(c.dimension) }}</div>
            <ul class="mt-1 text-sm"><li v-for="p in c.positive" :key="p"><span class="num text-computed">+</span> {{ p }}</li>
              <li v-for="n in c.negative" :key="n"><span class="num text-danger">−</span> {{ n }}</li></ul>
            <p class="mt-1 text-xs text-muted">{{ c.explanation }}</p>
          </div>
          <div v-for="c in analysis.result.comparison.convergences" :key="c.dimension" class="mb-3 border-l-2 border-accent pl-3">
            <div class="text-sm font-medium">Agreement on {{ humanize(c.dimension) }} ({{ c.direction > 0 ? 'favourable/high' : 'unfavourable/low' }})</div>
            <ul class="mt-1 text-sm text-muted"><li v-for="m in c.models" :key="m">{{ m }}</li></ul>
          </div>
        </section>
      </div>

      <section class="panel mb-6 overflow-x-auto">
        <h2 class="h-section">Comparison</h2>
        <table class="data min-w-[720px]">
          <thead><tr><th>Model</th><th>Primary metric</th><th class="text-right">Value</th><th class="text-right">p05 – p95</th><th>Most sensitive to</th><th>Claims</th></tr></thead>
          <tbody>
            <tr v-for="r in analysis.result.comparison.table" :key="r.key">
              <td class="font-medium">{{ r.model }}</td><td class="text-muted">{{ humanize(r.primary_metric) }}</td>
              <td class="num text-right">{{ fmt(r.value) }}</td>
              <td class="num text-right text-muted">{{ r.p05 !== null ? `${fmt(r.p05)} – ${fmt(r.p95)}` : '—' }}</td>
              <td class="num text-sm">{{ r.most_sensitive ?? '—' }}</td>
              <td class="text-sm text-muted">{{ r.claims.join(' · ') }}</td>
            </tr>
          </tbody>
        </table>
        <p class="mt-2 text-xs text-muted">{{ analysis.result.comparison.note }} Intervals vary assumptions by ±{{ Math.round(analysis.result.band * 100) }}% — assumption uncertainty, not empirical confidence.</p>
      </section>

      <div class="flex snap-x gap-4 overflow-x-auto pb-4">
        <article v-for="e in analysis.result.executions" :id="executionId(e)" :key="executionId(e)" class="panel w-[400px] shrink-0 snap-start scroll-mt-4">
          <div class="flex items-start justify-between gap-2">
            <div>
              <RouterLink :to="`/models/${e.model_key}`" class="font-semibold hover:text-accent">{{ e.model_name }}</RouterLink>
              <div class="text-xs text-muted">v{{ e.model_version }} · fit {{ e.fit_score }}</div>
            </div>
            <RouterLink :to="{ path: '/scenarios', query: { analysis: analysis.id, model: e.model_key } }" class="btn-ghost !px-2 !py-0.5 text-xs">Scenarios</RouterLink>
          </div>
          <p v-if="e.status === 'error'" class="mt-3 text-sm text-danger">Execution failed: {{ e.error }}</p>
          <template v-else-if="e.output">
            <p v-if="plain(analysis, e)" class="mt-3 text-sm leading-relaxed"><OriginBadge origin="rule_interpretation" /> {{ plain(analysis, e) }}</p>
            <div class="mt-4 flex items-baseline justify-between">
              <span class="text-sm text-muted">{{ humanize(primary(e)) }}</span>
              <OriginBadge origin="computed" />
            </div>
            <div class="num text-2xl font-medium">{{ fmt(e.output.metrics[primary(e)]) }}</div>
            <div v-if="e.uncertainty.interval_p05_p95" class="num text-xs text-muted">
              p05–p95: {{ fmt(e.uncertainty.interval_p05_p95[0]) }} – {{ fmt(e.uncertainty.interval_p05_p95[1]) }}</div>
            <PlotChart :series="e.output.series" :height="200" :log-x="e.model_key === 'power_law'" class="mt-2" />
            <div class="mt-3 space-y-1.5 text-sm">
              <p v-for="s in e.output.interpretation" :key="s.text"><OriginBadge :origin="s.origin" /> {{ s.text }}</p>
            </div>
            <ul v-if="e.output.warnings.length" class="mt-2 space-y-0.5 text-xs text-assumption"><li v-for="w in e.output.warnings" :key="w">⚠ {{ w }}</li></ul>
            <h3 class="h-section mt-4">Assumptions</h3>
            <table class="data text-xs"><tbody>
              <tr v-for="[n, p] in shortParams(e)" :key="n">
                <td class="num">{{ n }}</td><td class="num text-right">{{ fmt(p.value) }}</td><td class="text-right"><OriginBadge :origin="p.origin" /></td>
              </tr>
            </tbody></table>
            <ul class="mt-2 list-disc space-y-0.5 pl-4 text-xs text-muted"><li v-for="a in e.assumptions" :key="a">{{ a }}</li></ul>
            <h3 class="h-section mt-4">Recommendation</h3>
            <p v-for="r in e.output.recommendations" :key="r.title" class="text-sm"><span class="font-medium">{{ r.title }}</span> — {{ r.expected_impact }}</p>
            <details class="mt-3 text-xs text-muted"><summary class="cursor-pointer">Limits & calculation protocol</summary>
              <ul class="mt-2 list-disc pl-4"><li v-for="l in e.limits" :key="l">{{ l }}</li></ul>
              <pre class="num mt-2 whitespace-pre-wrap">{{ e.output.log.join('\n') }}</pre></details>
          </template>
        </article>
      </div>
    </template>
  </AnalysisGate>
</template>
