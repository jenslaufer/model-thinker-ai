<script setup lang="ts">
import Plotly from 'plotly.js-dist-min'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { Series } from '../api'

const props = withDefaults(defineProps<{
  series?: Series[]
  traces?: Partial<Plotly.Data>[]
  height?: number
  xTitle?: string
  yTitle?: string
  logX?: boolean
  layout?: Partial<Plotly.Layout>
}>(), { height: 260 })

const el = ref<HTMLDivElement>()
const PALETTE = ['#0f5e5a', '#c0782a', '#4a5568', '#6b3fa0', '#1f5fa8', '#a8321f']

function toTraces(): Partial<Plotly.Data>[] {
  if (props.traces) return props.traces
  return (props.series ?? []).map((s, i) => {
    const color = PALETTE[i % PALETTE.length]
    if (s.kind === 'bar') return { type: 'bar', name: s.name, x: s.x, y: s.y, marker: { color } }
    return {
      type: 'scatter', name: s.name, x: s.x, y: s.y,
      mode: s.kind === 'scatter' ? 'markers' : 'lines',
      fill: s.kind === 'area' ? 'tozeroy' : undefined,
      line: { color, width: 2 }, marker: { color, size: 7 },
    }
  })
}

function draw() {
  if (!el.value) return
  const first = props.series?.[0]
  Plotly.react(el.value, toTraces() as Plotly.Data[], {
    height: props.height,
    margin: { l: 56, r: 12, t: toTraces().length > 1 ? 36 : 8, b: 44 },
    paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
    font: { family: 'IBM Plex Sans, sans-serif', size: 12, color: '#16201f' },
    xaxis: { title: { text: props.xTitle ?? first?.x_label ?? '' }, gridcolor: '#e8ebe9', zeroline: false,
      type: props.logX ? 'log' : undefined, automargin: true },
    yaxis: { title: { text: props.yTitle ?? first?.y_label ?? '' }, gridcolor: '#e8ebe9', zeroline: false, automargin: true },
    legend: { orientation: 'h', x: 0, y: 1, yanchor: 'bottom' },
    showlegend: toTraces().length > 1,
    barmode: 'group',
    ...props.layout,
  }, { displayModeBar: false, responsive: true })
}

onMounted(draw)
watch(() => [props.series, props.traces, props.layout], draw, { deep: true })
onBeforeUnmount(() => el.value && Plotly.purge(el.value))
</script>

<template>
  <div ref="el" class="w-full" />
</template>
