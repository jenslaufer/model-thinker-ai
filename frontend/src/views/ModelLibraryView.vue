<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api, type ModelSummary } from '../api'
import { FAMILY } from '../format'

const models = ref<ModelSummary[]>([])
const onlyImplemented = ref(false)
onMounted(async () => { models.value = await api.models() })
const byFamily = computed(() => (['A', 'B', 'C'] as const).map((f) => ({
  family: f, items: models.value.filter((m) => m.family === f && (!onlyImplemented.value || m.implemented)),
})))
const done = computed(() => models.value.filter((m) => m.implemented).length)
</script>

<template>
  <div>
    <div class="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 class="h-page">Model library</h1>
        <p class="mt-1 text-sm text-muted">24 model families after Scott E. Page, <em>The Model Thinker</em>.
          <span class="num">{{ done }}</span> are implemented and executable; the rest are catalogued and marked.</p>
      </div>
      <label class="flex items-center gap-2 text-sm"><input v-model="onlyImplemented" type="checkbox" class="accent-[#0f5e5a]" /> Executable only</label>
    </div>
    <section v-for="g in byFamily" :key="g.family" class="mb-8">
      <h2 class="h-section">{{ g.family }} · {{ FAMILY[g.family] }}</h2>
      <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        <RouterLink v-for="m in g.items" :key="m.key" :to="`/models/${m.key}`"
          :class="['panel !p-4 transition hover:border-accent', !m.implemented && 'opacity-60']">
          <div class="flex items-start justify-between gap-3">
            <div class="font-medium"><span class="num mr-1.5 text-muted">{{ String(m.number).padStart(2, '0') }}</span>{{ m.name }}</div>
            <span :class="['shrink-0 rounded px-1.5 py-px text-[11px]', m.implemented ? 'bg-accent-soft text-accent' : 'border border-line text-muted']">
              {{ m.implemented ? `v${m.version}` : 'planned' }}</span>
          </div>
          <p class="mt-1.5 text-sm text-muted">{{ m.summary }}</p>
          <div class="mt-2 text-xs text-muted">{{ m.perspective }} perspective</div>
        </RouterLink>
      </div>
    </section>
  </div>
</template>
