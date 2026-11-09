<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api, type Dashboard } from '../api'
import OriginBadge from '../components/OriginBadge.vue'
import { fmt } from '../format'

const d = ref<Dashboard | null>(null)
const err = ref('')
onMounted(async () => { try { d.value = await api.dashboard() } catch (e) { err.value = (e as Error).message } })
</script>

<template>
  <div>
    <div class="mb-6 flex items-end justify-between">
      <div>
        <h1 class="h-page">Dashboard</h1>
        <p class="mt-1 text-sm text-muted">Analyses, model runs and open decisions in this workspace.</p>
      </div>
      <RouterLink to="/new" class="btn">New analysis</RouterLink>
    </div>
    <p v-if="err" class="text-danger">{{ err }}</p>
    <template v-if="d">
      <div class="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <div v-for="(v, k) in { 'Analyses': d.counts.analyses, 'Projects': d.counts.projects, 'Model executions': d.counts.executions, 'Open decisions': d.counts.open_decisions }"
          :key="k" class="panel !p-4">
          <div class="text-xs text-muted">{{ k }}</div>
          <div class="num mt-1 text-2xl font-medium">{{ v }}</div>
        </div>
      </div>
      <div v-if="!d.counts.analyses" class="panel max-w-2xl">
        <h2 class="mb-2 font-semibold">Start with a problem</h2>
        <p class="mb-4 text-sm text-muted">Describe a decision in plain language. The platform structures it, selects
          complementary models, computes them and compares the perspectives.</p>
        <RouterLink to="/new" class="btn">Describe a problem</RouterLink>
      </div>
      <div v-else class="grid gap-4 lg:grid-cols-2">
        <section class="panel">
          <h2 class="h-section">Active analyses</h2>
          <ul class="divide-y divide-line">
            <li v-for="a in d.active_analyses" :key="a.id" class="flex items-center justify-between py-2">
              <RouterLink :to="{ path: '/analysis', query: { analysis: a.id } }" class="font-medium hover:text-accent">{{ a.title }}</RouterLink>
              <span class="text-xs text-muted">rev {{ a.revision }} · {{ new Date(a.updated_at).toLocaleDateString() }}</span>
            </li>
          </ul>
        </section>
        <section class="panel">
          <h2 class="h-section">Open decisions</h2>
          <p v-if="!d.open_decisions.length" class="text-sm text-muted">None.</p>
          <ul class="divide-y divide-line">
            <li v-for="r in d.open_decisions" :key="r.db_id" class="flex items-start justify-between gap-4 py-2">
              <RouterLink :to="{ path: '/decisions', query: { analysis: r.analysis_id } }" class="hover:text-accent">
                <div class="text-sm font-medium">{{ r.title }}</div>
                <div class="text-xs text-muted">{{ r.analysis }}</div>
              </RouterLink>
              <span class="num text-xs text-muted">P {{ fmt(r.priority) }}</span>
            </li>
          </ul>
        </section>
        <section class="panel">
          <h2 class="h-section">Key findings</h2>
          <ul class="space-y-2.5">
            <li v-for="(x, i) in d.insights" :key="i" class="text-sm">
              <OriginBadge :origin="x.origin" /> {{ x.text }}
              <div class="text-xs text-muted">{{ x.analysis }}</div>
            </li>
          </ul>
        </section>
        <section class="panel">
          <h2 class="h-section">Models in use</h2>
          <div class="flex flex-wrap gap-2">
            <RouterLink v-for="[k, n] in d.models_used" :key="k" :to="`/models/${k}`"
              class="rounded border border-line px-2 py-1 text-sm hover:border-accent">{{ k }} <span class="num text-muted">×{{ n }}</span></RouterLink>
          </div>
          <h2 class="h-section mt-5">Recent simulations</h2>
          <table class="data">
            <tbody>
              <tr v-for="(s, i) in d.recent_simulations" :key="i">
                <td>{{ s.model }}</td>
                <td class="text-muted">{{ s.primary_metric }}</td>
                <td class="num text-right text-xs">{{ s.interval ? `${fmt(s.interval[0])} – ${fmt(s.interval[1])}` : s.status }}</td>
              </tr>
            </tbody>
          </table>
        </section>
      </div>
    </template>
  </div>
</template>
