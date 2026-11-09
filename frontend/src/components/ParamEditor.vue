<script setup lang="ts">
// Edits model parameters according to their ParamSpec. Sliders for bounded or uncertain scalars.
import type { ParamSpec } from '../api'
import OriginBadge from './OriginBadge.vue'
import type { ParamOrigin } from '../api'

const props = defineProps<{
  specs: ParamSpec[]
  base?: Record<string, unknown> // reference values for slider ranges
  origins?: Record<string, ParamOrigin>
  scalarsOnly?: boolean
}>()
const model = defineModel<Record<string, unknown>>({ required: true })

function range(p: ParamSpec): [number, number, number] {
  const b = Number(props.base?.[p.name] ?? p.default)
  // Slider spans base ±200%, clipped to the spec bounds; the number field accepts any valid value.
  const w = b === 0 ? 1 : 2 * Math.abs(b)
  const lo = Math.max(p.min ?? -Infinity, b - w)
  const hi = Math.min(p.max ?? Infinity, b + w)
  const step = p.type === 'int' ? 1 : Number(((hi - lo) / 200).toPrecision(2))
  return [lo, hi, step]
}

const set = (name: string, v: unknown) => { model.value = { ...model.value, [name]: v } }
const num = (e: Event) => Number((e.target as HTMLInputElement).value)
const toText = (v: unknown) => Array.isArray(v) ? (Array.isArray(v[0]) ? (v as unknown[][]).map((r) => r.join(', ')).join('\n') : v.join(', ')) : String(v ?? '')
function fromText(p: ParamSpec, t: string) {
  if (p.type === 'labels') return t.split(',').map((s) => s.trim()).filter(Boolean)
  if (p.type === 'vector') return t.split(',').map((s) => s.trim()).filter(Boolean).map(Number)
  return t.split('\n').filter((r) => r.trim()).map((r) => r.split(',').map((s) => Number(s.trim())))
}
const visible = () => props.specs.filter((p) => !props.scalarsOnly || p.type === 'float' || p.type === 'int' || p.type === 'choice')
</script>

<template>
  <div class="space-y-4">
    <div v-for="p in visible()" :key="p.name">
      <div class="mb-1 flex items-baseline justify-between gap-2">
        <label :for="`p-${p.name}`" class="text-sm font-medium">{{ p.label }}
          <span v-if="p.uncertain" class="ml-1 text-[11px] font-normal text-assumption" title="Varied in sensitivity, scenarios and Monte Carlo">uncertain</span>
        </label>
        <OriginBadge v-if="origins?.[p.name]" :origin="origins[p.name]" />
      </div>
      <template v-if="p.type === 'float' || p.type === 'int'">
        <div class="flex items-center gap-3">
          <input type="range" :min="range(p)[0]" :max="range(p)[1]" :step="range(p)[2]" :value="model[p.name] as number"
            class="flex-1 accent-[#0f5e5a]" :aria-label="p.label" @input="set(p.name, num($event))" />
          <input :id="`p-${p.name}`" type="number" :step="p.type === 'int' ? 1 : 'any'" :min="p.min ?? undefined" :max="p.max ?? undefined"
            :value="model[p.name] as number" class="field num !w-28 !py-1 text-right" @change="set(p.name, num($event))" />
        </div>
      </template>
      <select v-else-if="p.type === 'choice'" :id="`p-${p.name}`" :value="model[p.name] as string" class="field"
        @change="set(p.name, ($event.target as HTMLSelectElement).value)">
        <option v-for="c in p.choices" :key="c" :value="c">{{ c }}</option>
      </select>
      <input v-else-if="p.type === 'bool'" :id="`p-${p.name}`" type="checkbox" :checked="Boolean(model[p.name])"
        @change="set(p.name, ($event.target as HTMLInputElement).checked)" />
      <textarea v-else :id="`p-${p.name}`" :value="toText(model[p.name])" :rows="p.type === 'matrix' ? 4 : 1"
        class="field num" @change="set(p.name, fromText(p, ($event.target as HTMLTextAreaElement).value))" />
      <p v-if="p.type === 'matrix'" class="mt-0.5 text-xs text-muted">One row per line, values comma-separated.</p>
      <p v-else-if="p.description" class="mt-0.5 text-xs text-muted">{{ p.description }}</p>
    </div>
  </div>
</template>
