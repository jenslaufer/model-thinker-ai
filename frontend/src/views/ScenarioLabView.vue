<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, type ModelSpec, type SimulateResult } from '../api'
import AnalysisGate from '../components/AnalysisGate.vue'
import OriginBadge from '../components/OriginBadge.vue'
import ParamEditor from '../components/ParamEditor.vue'
import PlotChart from '../components/PlotChart.vue'
import { current, setCurrent } from '../current'
import { clone, fmt, humanize, executionId } from '../format'

const route = useRoute()
const router = useRouter()
const modelKey = ref('')
const spec = ref<ModelSpec | null>(null)
const baseline = ref<Record<string, unknown>>({})
const edited = ref<Record<string, unknown>>({})
const band = ref(0.2)
const sim = ref<SimulateResult | null>(null)
const busy = ref(false)
const err = ref('')
let timer: ReturnType<typeof setTimeout> | undefined

// modelKey holds the execution id (instance), so one model run twice gets two tabs.
const execution = computed(() => current.value?.result.executions.find((e) => executionId(e) === modelKey.value))
const whatIf = computed(() => Object.fromEntries(Object.entries(edited.value)
  .filter(([k, v]) => JSON.stringify(v) !== JSON.stringify(baseline.value[k]))))

watch(current, (a) => {
  if (!a) return
  const ok = a.result.executions.filter((e) => e.status === 'ok')
  const q = String(route.query.model ?? '')
  modelKey.value = ok.some((e) => executionId(e) === q) ? q : (ok[0] ? executionId(ok[0]) : '')
  band.value = a.result.band
}, { immediate: true })

watch(modelKey, async (k) => {
  if (!k || !execution.value) return
  spec.value = await api.model(execution.value.model_key)
  baseline.value = Object.fromEntries(Object.entries(execution.value.params).map(([n, p]) => [n, p.value]))
  edited.value = clone(baseline.value)
  if (route.query.model !== k) router.replace({ query: { ...route.query, model: k } })
}, { immediate: true })

watch([edited, band, baseline], () => { clearTimeout(timer); timer = setTimeout(simulate, 350) }, { deep: true })

function reset() { edited.value = clone(baseline.value) }

async function simulate() {
  if (!modelKey.value || !Object.keys(baseline.value).length) return
  busy.value = true; err.value = ''
  try {
    sim.value = await api.simulate(execution.value?.model_key ?? modelKey.value, { params: baseline.value, band: band.value,
      what_if: Object.keys(whatIf.value).length ? whatIf.value : undefined })
  } catch (e) { err.value = (e as Error).message }
  busy.value = false
}

async function save(asBaseline: boolean) {
  if (!current.value) return
  busy.value = true
  const overrides = Object.fromEntries(current.value.result.executions.map((e) => [executionId(e),
    Object.fromEntries(Object.entries(e.params).filter(([, p]) => p.origin === 'user_input').map(([n, p]) => [n, p.value]))]))
  const body = asBaseline
    ? { overrides: { ...overrides, [modelKey.value]: { ...overrides[modelKey.value], ...whatIf.value } }, band: band.value }
    : { overrides, what_if: { [modelKey.value]: whatIf.value }, band: band.value }
  try { setCurrent(await api.rerun(current.value.id, body)) } catch (e) { err.value = (e as Error).message }
  busy.value = false
}

const KIND_COLOR: Record<string, string> = { baseline: '#4a5568', best: '#0f5e5a', worst: '#a8321f', alternative: '#1f5fa8', stress: '#7a1f12', what_if: '#c0782a' }
const scenarioTraces = computed(() => sim.value ? [{
  type: 'bar' as const, x: sim.value.scenarios.map((s) => s.name), y: sim.value.scenarios.map((s) => s.primary ?? 0),
  marker: { color: sim.value.scenarios.map((s) => KIND_COLOR[s.kind]) },
  text: sim.value.scenarios.map((s) => fmt(s.primary)), textposition: 'outside' as const,
}] : [])
const tornadoTraces = computed(() => {
  if (!sim.value?.sensitivity.length) return []
  const base = sim.value.scenarios.find((s) => s.kind === 'baseline')?.primary ?? 0
  const items = [...sim.value.sensitivity].reverse()
  return [
    { type: 'bar' as const, orientation: 'h' as const, name: `−${Math.round(band.value * 100)}%`, y: items.map((i) => i.param), x: items.map((i) => i.metric_low - base), base, marker: { color: '#a8321f' } },
    { type: 'bar' as const, orientation: 'h' as const, name: `+${Math.round(band.value * 100)}%`, y: items.map((i) => i.param), x: items.map((i) => i.metric_high - base), base, marker: { color: '#0f5e5a' } },
  ]
})
</script>

<template>
  <AnalysisGate title="Scenario lab" subtitle="Change influence parameters and see how the model responds. Best, worst and stress cases shift every uncertain assumption within the band.">
    <template #default="{ analysis }">
      <div class="mb-4 flex flex-wrap gap-2">
        <button v-for="e in analysis.result.executions.filter((x) => x.status === 'ok')" :key="executionId(e)"
          :class="modelKey === executionId(e) ? 'btn !py-1' : 'btn-ghost !py-1'" @click="modelKey = executionId(e)">{{ e.model_name }}<template v-if="e.instance"> ({{ e.instance.split(':')[1] }})</template></button>
      </div>
      <div v-if="spec" class="grid gap-6 xl:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <section class="panel">
          <div class="mb-4 flex items-center justify-between">
            <h2 class="h-section !mb-0">Parameters</h2>
            <button class="btn-ghost !py-1" @click="reset">Reset</button>
          </div>
          <div class="mb-5">
            <label class="label" for="band">Uncertainty band ±{{ Math.round(band * 100) }}%</label>
            <input id="band" v-model.number="band" type="range" min="0.05" max="0.5" step="0.05" class="w-full accent-[#0f5e5a]" />
          </div>
          <ParamEditor v-model="edited" :specs="spec.params" :base="baseline"
            :origins="Object.fromEntries(Object.entries(execution?.params ?? {}).map(([k, p]) => [k, p.origin]))" />
          <div class="mt-5 border-t border-line pt-4">
            <p class="mb-3 text-sm text-muted">{{ Object.keys(whatIf).length ? `What-if changes: ${Object.keys(whatIf).join(', ')}` : 'No changes yet — move a parameter.' }}</p>
            <div class="flex flex-wrap gap-2">
              <button class="btn-ghost" :disabled="busy || !Object.keys(whatIf).length" @click="save(false)">Save what-if as revision</button>
              <button class="btn" :disabled="busy || !Object.keys(whatIf).length" @click="save(true)">Adopt as new baseline</button>
            </div>
          </div>
        </section>
        <div class="space-y-6">
          <p v-if="err" class="text-sm text-danger">{{ err }}</p>
          <section class="panel">
            <div class="mb-1 flex items-center justify-between">
              <h2 class="h-section !mb-0">{{ humanize(spec.primary_metric ?? '') }} by scenario <span class="normal-case">({{ spec.primary_goal }})</span></h2>
              <span class="text-xs text-muted">{{ busy ? 'computing…' : '' }} <OriginBadge origin="computed" /></span>
            </div>
            <PlotChart v-if="sim" :traces="scenarioTraces" :height="260" :y-title="humanize(spec.primary_metric ?? '')" />
            <table v-if="sim" class="data mt-2">
              <tbody><tr v-for="s in sim.scenarios" :key="s.kind">
                <td class="font-medium" :style="{ color: KIND_COLOR[s.kind] }">{{ s.name }}</td>
                <td class="num text-right">{{ fmt(s.primary) }}</td><td class="text-xs text-muted">{{ s.description }}</td>
              </tr></tbody>
            </table>
          </section>
          <section class="panel">
            <h2 class="h-section">Sensitivity (one at a time, ±{{ Math.round(band * 100) }}%)</h2>
            <PlotChart v-if="tornadoTraces.length" :traces="tornadoTraces" :height="60 + 40 * (sim?.sensitivity.length ?? 1)"
              :layout="{ barmode: 'overlay', margin: { l: 110, r: 12, t: 8, b: 40 } }" :x-title="humanize(spec.primary_metric ?? '')" />
            <p v-else class="text-sm text-muted">This model has no continuous uncertain parameters; best/worst cases come from Monte Carlo quantiles of perturbed inputs.</p>
          </section>
          <section v-if="sim?.monte_carlo.histogram.counts" class="panel">
            <h2 class="h-section">Monte Carlo distribution ({{ sim.monte_carlo.draws }} draws)</h2>
            <PlotChart :height="220" :x-title="humanize(spec.primary_metric ?? '')" y-title="Draws" :traces="[{ type: 'bar', marker: { color: '#0f5e5a' },
              x: sim.monte_carlo.histogram.edges!.slice(0, -1).map((e, i) => (e + sim!.monte_carlo.histogram.edges![i + 1]) / 2),
              y: sim.monte_carlo.histogram.counts }]" />
            <p class="mt-2 text-xs text-muted">{{ sim.monte_carlo.note }}</p>
          </section>
        </div>
      </div>
    </template>
  </AnalysisGate>
</template>
