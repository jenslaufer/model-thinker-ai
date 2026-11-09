<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import AnalysisGate from '../components/AnalysisGate.vue'
import ScoreBar from '../components/ScoreBar.vue'
import { current, setCurrent } from '../current'
import { humanize } from '../format'

const router = useRouter()
const chosen = ref<string[]>([])
const busy = ref(false)
const err = ref('')
watch(current, (a) => { if (a) chosen.value = a.result.executions.map((e) => e.model_key) }, { immediate: true })

function toggle(k: string) {
  chosen.value = chosen.value.includes(k) ? chosen.value.filter((x) => x !== k) : [...chosen.value, k]
}
async function rerun() {
  if (!current.value) return
  busy.value = true; err.value = ''
  try {
    setCurrent(await api.rerun(current.value.id, { selected: chosen.value }))
    router.push({ path: '/analysis', query: { analysis: current.value.id } })
  } catch (e) { err.value = (e as Error).message }
  busy.value = false
}
</script>

<template>
  <AnalysisGate title="Model selection" subtitle="Phase 3: every model family scored against the problem. The Model Fit Score (0–100) is a transparent heuristic, not a validated probability.">
    <template #default="{ analysis }">
      <div class="panel mb-6 flex flex-wrap items-center justify-between gap-4">
        <div class="text-sm">
          <span class="font-medium">{{ chosen.length }} selected:</span>
          <span class="text-muted"> {{ chosen.join(', ') || 'none' }}</span>
        </div>
        <div class="flex items-center gap-3">
          <span v-if="err" class="text-sm text-danger">{{ err }}</span>
          <button class="btn" :disabled="busy || !chosen.length || chosen.length > 10" @click="rerun">
            {{ busy ? 'Computing…' : 'Run selection as new revision' }}</button>
        </div>
      </div>
      <div class="panel overflow-x-auto">
        <table class="data min-w-[860px]">
          <thead><tr><th></th><th>Model</th><th class="w-40">Fit score</th><th>Components</th><th>Reasons / blockers</th></tr></thead>
          <tbody>
            <tr v-for="f in analysis.result.selection.fits" :key="f.key" :class="!f.implemented && 'opacity-50'">
              <td><input type="checkbox" class="accent-[#0f5e5a]" :disabled="!f.implemented" :checked="chosen.includes(f.key)"
                :aria-label="`Select ${f.name}`" @change="toggle(f.key)" /></td>
              <td>
                <RouterLink :to="`/models/${f.key}`" class="font-medium hover:text-accent">{{ f.name }}</RouterLink>
                <div class="text-xs text-muted">{{ f.perspective }}{{ f.implemented ? '' : ' · not implemented' }}</div>
              </td>
              <td><div class="num mb-1">{{ f.score }}</div><ScoreBar :value="f.score" /></td>
              <td class="text-xs text-muted">
                <div v-for="(v, k) in f.components" :key="k" class="flex justify-between gap-3"><span>{{ humanize(String(k)) }}</span><span class="num">{{ v }}</span></div>
              </td>
              <td class="text-sm">
                <div v-for="r in f.reasons" :key="r">{{ r }}</div>
                <div v-for="b in f.blockers" :key="b" class="text-danger">{{ b }}</div>
                <div v-for="m in f.missing_data" :key="m" class="text-xs text-assumption">Needs: {{ m }}</div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p class="mt-3 text-xs text-muted">{{ analysis.result.selection.note }} Auto-selection penalises repeated perspectives so the set covers different mechanisms.</p>
    </template>
  </AnalysisGate>
</template>
