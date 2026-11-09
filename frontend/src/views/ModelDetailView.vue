<script setup lang="ts">
import { ref, watch } from 'vue'
import { api, type ModelOutput, type ModelSpec } from '../api'
import MathBlock from '../components/MathBlock.vue'
import MetricTable from '../components/MetricTable.vue'
import OriginBadge from '../components/OriginBadge.vue'
import ParamEditor from '../components/ParamEditor.vue'
import PlotChart from '../components/PlotChart.vue'
import { clone, FAMILY, metricHelp } from '../format'

const props = defineProps<{ modelKey: string }>()
const spec = ref<ModelSpec | null>(null)
const params = ref<Record<string, unknown>>({})
const out = ref<ModelOutput | null>(null)
const err = ref('')
const running = ref(false)

async function run() {
  if (!spec.value?.implemented) return
  running.value = true; err.value = ''
  try { out.value = await api.runModel(spec.value.key, params.value) } catch (e) { err.value = (e as Error).message }
  running.value = false
}

watch(() => props.modelKey, async (k) => {
  out.value = null
  spec.value = await api.model(k)
  params.value = Object.fromEntries(spec.value.params.map((p) => [p.name, clone(p.default)]))
  await run()
}, { immediate: true })

const reset = () => { if (spec.value) { params.value = Object.fromEntries(spec.value.params.map((p) => [p.name, clone(p.default)])); run() } }
</script>

<template>
  <div v-if="spec">
    <RouterLink to="/models" class="text-sm text-muted hover:text-accent">← Model library</RouterLink>
    <div class="mt-2 mb-6">
      <div class="text-xs text-muted">{{ spec.family }} · {{ FAMILY[spec.family] }} · {{ spec.implemented ? `version ${spec.version}` : 'planned' }}</div>
      <h1 class="h-page"><span class="num mr-2 text-muted">{{ String(spec.number).padStart(2, '0') }}</span>{{ spec.name }}</h1>
      <p class="mt-1 max-w-3xl text-muted">{{ spec.summary }}</p>
    </div>
    <div v-if="!spec.implemented" class="panel max-w-2xl">
      <p class="mb-3 text-sm">This model family is catalogued but <strong>not implemented</strong>. It is never selected or executed.</p>
      <MathBlock v-if="spec.math" :tex="spec.math" />
    </div>
    <div v-else class="grid gap-6 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <div class="space-y-6">
        <section class="panel">
          <h2 class="h-section">Explanation</h2>
          <p class="text-sm leading-relaxed">{{ spec.description }}</p>
          <h2 class="h-section mt-5">Mathematical basis</h2>
          <MathBlock :tex="spec.math" />
        </section>
        <section class="panel">
          <div class="mb-2 flex items-center justify-between">
            <h2 class="h-section !mb-0">Visualisation</h2>
            <OriginBadge origin="computed" />
          </div>
          <p v-if="err" class="text-sm text-danger">{{ err }}</p>
          <template v-if="out">
            <PlotChart :series="out.series" :log-x="spec.key === 'power_law'" />
            <p v-for="s in out.interpretation" :key="s.text" class="mt-3 text-sm"><OriginBadge :origin="s.origin" /> {{ s.text }}</p>
            <ul v-if="out.warnings.length" class="mt-3 space-y-1 text-sm text-assumption"><li v-for="w in out.warnings" :key="w">⚠ {{ w }}</li></ul>
          </template>
        </section>
        <section class="grid gap-6 md:grid-cols-2">
          <div class="panel"><h2 class="h-section">Assumptions</h2><ul class="list-disc space-y-1 pl-4 text-sm"><li v-for="a in spec.assumptions" :key="a">{{ a }}</li></ul></div>
          <div class="panel"><h2 class="h-section">Limits and risks</h2><ul class="list-disc space-y-1 pl-4 text-sm"><li v-for="a in spec.limits" :key="a">{{ a }}</li></ul></div>
          <div class="panel"><h2 class="h-section">Examples</h2><ul class="list-disc space-y-1 pl-4 text-sm"><li v-for="a in spec.examples" :key="a">{{ a }}</li></ul></div>
          <div class="panel"><h2 class="h-section">Use cases</h2><ul class="list-disc space-y-1 pl-4 text-sm"><li v-for="a in spec.use_cases" :key="a">{{ a }}</li></ul>
            <h2 class="h-section mt-4">Prerequisites</h2><ul class="list-disc space-y-1 pl-4 text-sm"><li v-for="a in spec.prerequisites" :key="a">{{ a }}</li></ul></div>
        </section>
      </div>
      <div class="space-y-6">
        <section class="panel">
          <div class="mb-4 flex items-center justify-between">
            <h2 class="h-section !mb-0">Input parameters</h2>
            <div class="flex gap-2"><button class="btn-ghost !py-1" @click="reset">Reset</button>
              <button class="btn !py-1" :disabled="running" @click="run">{{ running ? 'Running…' : 'Run' }}</button></div>
          </div>
          <ParamEditor v-model="params" :specs="spec.params" />
        </section>
        <section v-if="out" class="panel">
          <h2 class="h-section">Results</h2>
          <MetricTable :metrics="out.metrics" :highlight="spec.primary_metric" :help="(k) => metricHelp(spec?.metric_help, k)" />
          <details class="mt-4 text-xs text-muted"><summary class="cursor-pointer">Calculation protocol</summary>
            <pre class="num mt-2 whitespace-pre-wrap">{{ out.log.join('\n') }}</pre></details>
        </section>
      </div>
    </div>
  </div>
</template>
