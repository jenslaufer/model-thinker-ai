<script setup lang="ts">
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import '@vue-flow/controls/dist/style.css'
import { VueFlow, type Edge, type Node } from '@vue-flow/core'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import { computed, ref, watch } from 'vue'
import { api, type GraphData } from '../api'
import AnalysisGate from '../components/AnalysisGate.vue'
import { current } from '../current'

// Column groups, left to right: context | drivers | outcomes & hypotheses | models | results | conflicts & decisions
const COLUMNS = [['actor', 'problem', 'data_source'], ['variable'], ['outcome', 'hypothesis'], ['model'],
  ['result', 'scenario'], ['contradiction', 'recommendation']]
const column = (n: GraphData['nodes'][number]) => (n.type === 'variable' && n.data.kind === 'outcome' ? 'outcome' : n.type)
const s = (background: string, borderColor: string, extra: Record<string, string> = {}) => ({ background, borderColor, ...extra })
const STYLE: Record<string, Record<string, string>> = {
  problem: s('#16201f', '#16201f', { color: '#fff' }), actor: s('#eef3fb', '#1f5fa8'),
  variable: s('#fff', '#9aa5a3'), data_source: s('#fff8e8', '#9a6a00'),
  hypothesis: s('#f6f5f1', '#c9cfcd', { borderStyle: 'dashed' }), model: s('#e2efed', '#0f5e5a'),
  result: s('#fff', '#0f5e5a'), scenario: s('#fff', '#c9cfcd'),
  contradiction: s('#fbeeeb', '#a8321f'), recommendation: s('#f3eef9', '#6b3fa0'),
}
const graph = ref<GraphData | null>(null)
const hidden = ref<string[]>(['scenario', 'hypothesis'])
const selected = ref<GraphData['nodes'][number] | null>(null)

watch(() => current.value && [current.value.id, current.value.revision], async () => {
  if (current.value) graph.value = await api.graph(current.value.id, current.value.revision)
}, { immediate: true })

const types = computed(() => [...new Set(graph.value?.nodes.map((n) => n.type) ?? [])])
const nodes = computed<Node[]>(() => {
  const rows: Record<string, number> = {}
  const shown = (graph.value?.nodes ?? []).filter((n) => !hidden.value.includes(n.type))
  const cols = COLUMNS.filter((g) => shown.some((n) => g.includes(column(n)))) // no gaps for hidden types
  return shown.map((n) => {
    const col = cols.findIndex((g) => g.includes(column(n)))
    const row = (rows[col] = (rows[col] ?? -1) + 1)
    return { id: n.id, position: { x: col * 240, y: row * 66 + (col % 2) * 22 }, label: n.label,
      style: { ...STYLE[n.type], borderWidth: '1px', borderRadius: '4px', fontSize: '11px', width: '190px', padding: '6px 8px' } }
  })
})
const edges = computed<Edge[]>(() => {
  const ids = new Set(nodes.value.map((n) => n.id))
  return (graph.value?.edges ?? []).filter((e) => ids.has(e.source) && ids.has(e.target)).map((e) => {
    const correl = e.relation === 'correlates'
    const color = e.relation === 'feedback' ? '#c0782a' : e.relation === 'contradicts' ? '#a8321f' : e.causal ? '#0f5e5a' : '#b5bcba'
    return { id: e.id, source: e.source, target: e.target, animated: e.relation === 'feedback',
      label: correl ? 'correlation — not causal' : e.causal ? `${e.data.polarity ?? ''} ${e.relation}` : undefined,
      style: { stroke: color, strokeDasharray: correl ? '5 4' : undefined, strokeWidth: e.causal ? 1.6 : 1 },
      labelStyle: { fontSize: '10px', fill: color } }
  })
})
function toggle(t: string) { hidden.value = hidden.value.includes(t) ? hidden.value.filter((x) => x !== t) : [...hidden.value, t] }
function onClick({ node }: { node: Node }) { selected.value = graph.value?.nodes.find((n) => n.id === node.id) ?? null }
</script>

<template>
  <AnalysisGate title="Knowledge graph" subtitle="Problems, actors, variables, hypotheses, models, results, scenarios and decisions. Solid green: hypothesised causal link · orange animated: feedback loop · dashed: correlation, never causal.">
    <div class="mb-3 flex flex-wrap items-center gap-2 text-sm">
      <span class="text-muted">Show:</span>
      <button v-for="t in types" :key="t" :class="['rounded border px-2 py-0.5', hidden.includes(t) ? 'border-line text-muted' : 'border-accent text-accent']"
        @click="toggle(t)">{{ t.replace('_', ' ') }}</button>
    </div>
    <div class="grid gap-4 xl:grid-cols-[minmax(0,1fr)_18rem]">
      <div class="panel !p-0 h-[640px] overflow-hidden">
        <VueFlow v-if="graph" :nodes="nodes" :edges="edges" fit-view-on-init :min-zoom="0.2" @node-click="onClick">
          <Background pattern-color="#dfe3e1" :gap="20" />
          <Controls />
        </VueFlow>
      </div>
      <aside class="panel">
        <h2 class="h-section">Details</h2>
        <p v-if="!selected" class="text-sm text-muted">Click a node.</p>
        <template v-else>
          <div class="text-xs uppercase tracking-wide text-muted">{{ selected.type }}</div>
          <div class="mb-3 font-medium">{{ selected.label }}</div>
          <dl class="space-y-1 text-sm"><div v-for="(v, k) in selected.data" :key="k" class="flex justify-between gap-3">
            <dt class="text-muted">{{ k }}</dt><dd class="num text-right">{{ v }}</dd></div></dl>
          <ul class="mt-4 space-y-1 text-xs text-muted">
            <li v-for="e in graph?.edges.filter((x) => x.source === selected!.id || x.target === selected!.id)" :key="e.id">
              {{ e.source === selected.id ? '→' : '←' }} {{ e.relation }} {{ e.causal ? '' : '(non-causal)' }}
              {{ graph?.nodes.find((n) => n.id === (e.source === selected!.id ? e.target : e.source))?.label }}</li>
          </ul>
        </template>
      </aside>
    </div>
  </AnalysisGate>
</template>
