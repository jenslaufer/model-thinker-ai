<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { api, type ModelSpec, type ModelSummary, type SimulateResult } from '../api'
import MetricTable from '../components/MetricTable.vue'
import OriginBadge from '../components/OriginBadge.vue'
import ParamEditor from '../components/ParamEditor.vue'
import PlotChart from '../components/PlotChart.vue'
import { clone, fmt, humanize, metricHelp } from '../format'

const models = ref<ModelSummary[]>([])
const key = ref('diffusion')
const spec = ref<ModelSpec | null>(null)
const params = ref<Record<string, unknown>>({})
const band = ref(0.2)
const draws = ref<number | null>(null)
const res = ref<SimulateResult | null>(null)
const busy = ref(false)
const err = ref('')

onMounted(async () => { models.value = (await api.models()).filter((m) => m.implemented) })
watch(key, async (k) => {
  res.value = null
  spec.value = await api.model(k)
  params.value = Object.fromEntries(spec.value.params.map((p) => [p.name, clone(p.default)]))
  draws.value = null
}, { immediate: true })

async function run() {
  busy.value = true; err.value = ''
  try { res.value = await api.simulate(key.value, { params: params.value, band: band.value, draws: draws.value ?? undefined }) }
  catch (e) { err.value = (e as Error).message }
  busy.value = false
}
const pm = computed(() => spec.value?.primary_metric ?? '')
</script>

<template>
  <div>
    <h1 class="h-page">Simulation center</h1>
    <p class="mt-1 mb-6 max-w-3xl text-sm text-muted">Run any implemented model on its own: Monte Carlo over uncertain assumptions,
      sensitivity and scenarios. Runs are reproducible (fixed seed) and logged.</p>
    <div class="grid gap-6 xl:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
      <section class="panel space-y-4">
        <div>
          <label class="label" for="model">Model</label>
          <select id="model" v-model="key" class="field"><option v-for="m in models" :key="m.key" :value="m.key">{{ m.name }}</option></select>
        </div>
        <div class="grid grid-cols-2 gap-4">
          <div><label class="label" for="band">Band ±{{ Math.round(band * 100) }}%</label>
            <input id="band" v-model.number="band" type="range" min="0.05" max="0.9" step="0.05" class="w-full accent-[#0f5e5a]" /></div>
          <div><label class="label" for="draws">Draws</label>
            <input id="draws" v-model.number="draws" type="number" min="10" max="2000" class="field num" placeholder="model default" /></div>
        </div>
        <ParamEditor v-if="spec" v-model="params" :specs="spec.params" />
        <button class="btn w-full justify-center" :disabled="busy" @click="run">{{ busy ? 'Simulating…' : 'Run simulation' }}</button>
        <p v-if="err" class="text-sm text-danger">{{ err }}</p>
      </section>
      <div v-if="res && spec" class="space-y-6">
        <section class="panel">
          <div class="mb-2 flex justify-between"><h2 class="h-section !mb-0">Distribution of {{ humanize(pm) }}</h2><OriginBadge origin="computed" /></div>
          <PlotChart v-if="res.monte_carlo.histogram.counts" :height="240" :x-title="humanize(pm)" y-title="Draws"
            :traces="[{ type: 'bar', marker: { color: '#0f5e5a' }, x: res.monte_carlo.histogram.edges!.slice(0, -1).map((e, i) => (e + res!.monte_carlo.histogram.edges![i + 1]) / 2), y: res.monte_carlo.histogram.counts }]" />
          <p class="text-xs text-muted">{{ res.monte_carlo.note }}</p>
        </section>
        <section class="panel overflow-x-auto">
          <h2 class="h-section">Monte Carlo summary ({{ res.monte_carlo.draws }} draws)</h2>
          <table class="data">
            <thead><tr><th>Metric</th><th class="text-right">Mean</th><th class="text-right">SD</th><th class="text-right">p05</th><th class="text-right">p50</th><th class="text-right">p95</th></tr></thead>
            <tbody><tr v-for="(s, k) in res.monte_carlo.summary" :key="k" :class="k === pm && 'bg-accent-soft/60'">
              <td>{{ humanize(String(k)) }}</td>
              <td v-for="f in (['mean', 'sd', 'p05', 'p50', 'p95'] as const)" :key="f" class="num text-right">{{ fmt(s[f]) }}</td>
            </tr></tbody>
          </table>
          <template v-if="Object.keys(res.monte_carlo.categorical).length">
            <h3 class="h-section mt-5">Robustness of categorical results</h3>
            <table class="data"><tbody><tr v-for="(c, k) in res.monte_carlo.categorical" :key="k">
              <td>{{ humanize(String(k)) }}</td><td class="num">{{ fmt(c.baseline) }}</td>
              <td class="num text-right">{{ fmt(c.baseline_share, 'pct') }} of draws unchanged</td></tr></tbody></table>
          </template>
        </section>
        <section class="panel">
          <h2 class="h-section">Baseline run</h2>
          <PlotChart :series="res.output.series" :height="220" :log-x="key === 'power_law'" />
          <MetricTable :metrics="res.output.metrics" :highlight="pm" :help="(k) => metricHelp(spec?.metric_help, k)" class="mt-3" />
        </section>
      </div>
    </div>
  </div>
</template>
