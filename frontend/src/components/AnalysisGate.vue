<script setup lang="ts">
// Wraps analysis-scoped pages: loads the current analysis or lets the user pick one.
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, type AnalysisListItem } from '../api'
import { current, currentId, error, load, loading } from '../current'

defineProps<{ title: string; subtitle?: string }>()
const route = useRoute()
const router = useRouter()
const list = ref<AnalysisListItem[]>([])

async function init() {
  const rid = Number(route.query.analysis) || currentId.value
  if (rid && current.value?.id !== rid) await load(rid)
  if (!current.value) list.value = await api.analyses()
}
onMounted(init)
watch(() => route.query.analysis, init)

function pick(id: number) {
  router.replace({ query: { ...route.query, analysis: id } })
}
async function switchAnalysis() {
  current.value = null
  currentId.value = null
  await router.replace({ query: {} })
  list.value = await api.analyses()
}
function changeRevision(e: Event) {
  if (current.value) load(current.value.id, Number((e.target as HTMLSelectElement).value))
}
</script>

<template>
  <div>
    <header class="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 class="h-page">{{ title }}</h1>
        <p v-if="subtitle" class="mt-1 max-w-3xl text-sm text-muted">{{ subtitle }}</p>
      </div>
      <div v-if="current" class="flex min-w-0 max-w-full flex-wrap items-center gap-3 text-sm">
        <span class="min-w-0 max-w-xs truncate font-medium" :title="current.title">{{ current.title }}</span>
        <select class="field !w-auto !py-1" :value="current.revision" @change="changeRevision" aria-label="Revision">
          <option v-for="r in current.latest_revision" :key="r" :value="r">Revision {{ r }}</option>
        </select>
        <button class="btn-ghost !py-1" @click="switchAnalysis">Switch</button>
      </div>
    </header>
    <p v-if="loading" class="text-muted">Loading analysis…</p>
    <p v-else-if="error" class="text-danger">{{ error }}</p>
    <slot v-else-if="current" :analysis="current" />
    <div v-else class="panel max-w-2xl">
      <p class="mb-4 text-sm text-muted">Choose an analysis to work on.</p>
      <ul v-if="list.length" class="divide-y divide-line">
        <li v-for="a in list" :key="a.id">
          <button class="flex w-full items-center justify-between py-2.5 text-left hover:text-accent" @click="pick(a.id)">
            <span class="font-medium">{{ a.title }}</span>
            <span class="text-xs text-muted">rev {{ a.revision }} · {{ a.models.length }} models</span>
          </button>
        </li>
      </ul>
      <RouterLink v-else to="/new" class="btn">Start a new analysis</RouterLink>
    </div>
  </div>
</template>
