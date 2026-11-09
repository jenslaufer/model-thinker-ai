<script setup lang="ts">
import AnalysisGate from '../components/AnalysisGate.vue'
import ScoreBar from '../components/ScoreBar.vue'
import { humanize } from '../format'
</script>

<template>
  <AnalysisGate title="Problem explorer" subtitle="Phases 1–2: the problem as understood and decomposed. Relations are hypotheses until evidence supports them.">
    <template #default="{ analysis }">
      <div class="grid gap-6 xl:grid-cols-2">
        <section class="panel xl:col-span-2">
          <div class="mb-2 flex items-center justify-between">
            <h2 class="h-section !mb-0">Problem</h2>
            <span class="text-xs text-muted">structured by {{ analysis.result.structure.origin }}</span>
          </div>
          <p class="leading-relaxed">{{ analysis.result.structure.restated_problem }}</p>
          <dl class="mt-4 grid gap-x-8 gap-y-2 text-sm md:grid-cols-3">
            <div><dt class="text-muted">Objective</dt><dd>{{ analysis.result.structure.objective }}</dd></div>
            <div><dt class="text-muted">Time horizon</dt><dd>{{ analysis.result.problem.time_horizon || '—' }}</dd></div>
            <div><dt class="text-muted">Decision scope</dt><dd>{{ analysis.result.problem.decision_scope || '—' }}</dd></div>
            <div><dt class="text-muted">System boundaries</dt><dd>{{ analysis.result.problem.system_boundaries || '—' }}</dd></div>
            <div><dt class="text-muted">Available data</dt><dd>{{ analysis.result.problem.available_data || '—' }}</dd></div>
          </dl>
        </section>
        <section class="panel">
          <h2 class="h-section">Problem aspects</h2>
          <div class="space-y-2">
            <div v-for="(v, k) in analysis.result.structure.problem_types" :key="k" class="grid grid-cols-[9rem_1fr_2.5rem] items-center gap-3 text-sm">
              <span>{{ humanize(String(k)) }}</span><ScoreBar :value="v" :max="1" /><span class="num text-right text-muted">{{ v }}</span>
            </div>
          </div>
          <h2 class="h-section mt-6">Selection criteria</h2>
          <div class="space-y-2">
            <div v-for="(v, k) in analysis.result.structure.criteria" :key="k" class="grid grid-cols-[9rem_1fr_2.5rem] items-center gap-3 text-sm">
              <span>{{ humanize(String(k)) }}</span><ScoreBar :value="v" :max="1" tone="muted" /><span class="num text-right text-muted">{{ v }}</span>
            </div>
          </div>
        </section>
        <section class="panel">
          <h2 class="h-section">Sub-problems</h2>
          <ol class="list-decimal space-y-1 pl-5 text-sm"><li v-for="q in analysis.result.structure.subproblems" :key="q">{{ q }}</li></ol>
          <h2 class="h-section mt-6">Actors</h2>
          <p v-if="!analysis.result.structure.actors.length" class="text-sm text-muted">None named.</p>
          <div class="flex flex-wrap gap-2"><span v-for="a in analysis.result.structure.actors" :key="a.name" class="rounded border border-line px-2 py-0.5 text-sm">{{ a.name }}</span></div>
          <h2 class="h-section mt-6">Variables</h2>
          <table class="data"><tbody>
            <tr v-for="v in analysis.result.structure.variables" :key="v.name"><td>{{ v.name }}</td><td class="text-muted">{{ v.kind }}</td><td class="text-xs text-muted">{{ v.origin }}</td></tr>
          </tbody></table>
        </section>
        <section class="panel">
          <h2 class="h-section">Hypothesised relations</h2>
          <p v-if="!analysis.result.structure.relations.length" class="text-sm text-muted">No relations detected.</p>
          <table v-else class="data">
            <thead><tr><th>From</th><th>Relation</th><th>To</th><th>Status</th></tr></thead>
            <tbody>
              <tr v-for="(r, i) in analysis.result.structure.relations" :key="i">
                <td>{{ r.source }}</td>
                <td><span class="num">{{ r.polarity }}</span> {{ r.relation }}</td>
                <td>{{ r.target }}</td>
                <td :class="r.status === 'correlational' ? 'text-assumption' : 'text-muted'">{{ r.status }}</td>
              </tr>
            </tbody>
          </table>
          <p class="mt-3 text-xs text-muted">Correlational links are never treated as causal.</p>
        </section>
        <section class="panel">
          <h2 class="h-section">Data gaps</h2>
          <p v-if="!analysis.result.structure.data_gaps.length" class="text-sm text-muted">None flagged.</p>
          <ul class="space-y-1 text-sm text-assumption"><li v-for="g in analysis.result.structure.data_gaps" :key="g">{{ g }}</li></ul>
        </section>
      </div>
    </template>
  </AnalysisGate>
</template>
