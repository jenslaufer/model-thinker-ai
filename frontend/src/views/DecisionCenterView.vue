<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { api, type PrioritizedRecommendation } from '../api'
import AnalysisGate from '../components/AnalysisGate.vue'
import OriginBadge from '../components/OriginBadge.vue'
import { current } from '../current'
import { fmt } from '../format'

const notes = reactive<Record<number, string>>({})
const evidence = ref<{ id: number; description: string; source: string; created_at: string }[]>([])
const ev = reactive({ description: '', source: '' })
const err = ref('')

watch(() => current.value?.id, async (id) => { if (id) evidence.value = await api.evidence(id) }, { immediate: true })

async function decide(r: PrioritizedRecommendation, status: string) {
  try {
    const res = await api.decide(r.db_id!, status, notes[r.db_id!] ?? r.note ?? '')
    r.decision_status = res.decision_status as PrioritizedRecommendation['decision_status']
  } catch (e) { err.value = (e as Error).message }
}
async function addEvidence() {
  if (!current.value || !ev.description.trim()) return
  await api.addEvidence(current.value.id, { ...ev })
  evidence.value = await api.evidence(current.value.id)
  ev.description = ''; ev.source = ''
}
const STATUS: Record<string, string> = { open: 'text-muted', accepted: 'text-computed', rejected: 'text-danger', deferred: 'text-assumption' }
</script>

<template>
  <AnalysisGate title="Decision center" subtitle="Phase 9: prioritised options. Priority = model fit × confidence; cross-model items come from contradictions and data gaps. Each item cites the computed evidence it rests on.">
    <template #default="{ analysis }">
      <p v-if="err" class="mb-3 text-sm text-danger">{{ err }}</p>
      <p v-if="analysis.revision !== analysis.latest_revision" class="mb-4 text-sm text-assumption">You are viewing an older revision; decisions apply to that revision's recommendations.</p>
      <ol class="space-y-4">
        <li v-for="(r, i) in analysis.recommendations" :key="r.db_id" class="panel">
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div class="text-xs text-muted">#{{ i + 1 }} · priority <span class="num">{{ fmt(r.priority) }}</span> · {{ r.source_models.length ? r.source_models.join(', ') : 'cross-model' }}</div>
              <h2 class="text-lg font-semibold">{{ r.title }}</h2>
            </div>
            <div class="flex items-center gap-2">
              <OriginBadge :origin="r.origin" />
              <span :class="['text-sm font-medium', STATUS[r.decision_status ?? 'open']]">{{ r.decision_status }}</span>
            </div>
          </div>
          <p class="mt-1 text-sm">{{ r.rationale }}</p>
          <dl class="mt-3 grid gap-x-6 gap-y-3 text-sm md:grid-cols-3">
            <div><dt class="h-section !mb-1">Expected impact</dt><dd>{{ r.expected_impact }}</dd></div>
            <div><dt class="h-section !mb-1">Uncertainty · horizon</dt><dd>{{ r.uncertainty }} · {{ r.horizon }} term</dd></div>
            <div><dt class="h-section !mb-1">Evidence</dt><dd class="num text-xs"><div v-for="e in r.evidence" :key="e">{{ e }}</div></dd></div>
            <div><dt class="h-section !mb-1">Prerequisites</dt><dd><ul class="list-disc pl-4"><li v-for="x in r.prerequisites" :key="x">{{ x }}</li></ul></dd></div>
            <div><dt class="h-section !mb-1">Risks</dt><dd><ul class="list-disc pl-4"><li v-for="x in r.risks" :key="x">{{ x }}</li></ul></dd></div>
            <div><dt class="h-section !mb-1">Actions</dt><dd><ul class="list-disc pl-4"><li v-for="x in r.actions" :key="x">{{ x }}</li></ul></dd></div>
          </dl>
          <div class="mt-4 flex flex-wrap items-center gap-2 border-t border-line pt-3">
            <input v-model="notes[r.db_id!]" class="field !w-auto flex-1" :placeholder="r.note || 'Decision note (optional)'" maxlength="2000" />
            <button class="btn !py-1" @click="decide(r, 'accepted')">Accept</button>
            <button class="btn-ghost !py-1" @click="decide(r, 'deferred')">Defer</button>
            <button class="btn-ghost !py-1" @click="decide(r, 'rejected')">Reject</button>
          </div>
        </li>
      </ol>
      <section class="panel mt-8 max-w-3xl">
        <h2 class="h-section">Evidence log (phase 10 — evaluate)</h2>
        <p class="mb-3 text-sm text-muted">Record observed outcomes to check results later. Evidence is stored with the analysis; automatic model recalibration is not implemented yet.</p>
        <form class="flex flex-wrap gap-2" @submit.prevent="addEvidence">
          <input v-model="ev.description" class="field flex-[2]" placeholder="What was observed?" maxlength="5000" />
          <input v-model="ev.source" class="field flex-1" placeholder="Source" maxlength="300" />
          <button class="btn" :disabled="!ev.description.trim()">Add</button>
        </form>
        <ul class="mt-4 divide-y divide-line text-sm">
          <li v-for="e in evidence" :key="e.id" class="flex justify-between gap-4 py-2"><span>{{ e.description }}</span>
            <span class="shrink-0 text-xs text-muted">{{ e.source }} · {{ new Date(e.created_at).toLocaleDateString() }}</span></li>
        </ul>
      </section>
    </template>
  </AnalysisGate>
</template>
