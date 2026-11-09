<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
import { humanize } from '../format'

const s = ref<Awaited<ReturnType<typeof api.settings>> | null>(null)
const audit = ref<Awaited<ReturnType<typeof api.audit>>>([])
onMounted(async () => { [s.value, audit.value] = await Promise.all([api.settings(), api.audit()]) })
const tone = (v: string) => v.startsWith('NOT') ? 'text-danger' : v.startsWith('PARTIAL') ? 'text-assumption' : 'text-computed'
</script>

<template>
  <div>
    <h1 class="h-page">Settings</h1>
    <p class="mt-1 mb-6 text-sm text-muted">Runtime configuration and implementation status. Configure via environment variables (see README).</p>
    <div v-if="s" class="grid gap-6 xl:grid-cols-2">
      <section class="panel">
        <h2 class="h-section">Runtime</h2>
        <dl class="space-y-2 text-sm">
          <div class="flex justify-between"><dt class="text-muted">LLM provider</dt><dd class="num">{{ s.provider }}</dd></div>
          <div class="flex justify-between"><dt class="text-muted">Database</dt><dd class="num">{{ s.database }}</dd></div>
          <div class="flex justify-between"><dt class="text-muted">Models implemented</dt><dd class="num">{{ s.models_implemented }} / {{ s.models_total }}</dd></div>
        </dl>
        <p class="mt-4 text-xs text-muted">Set <code>LLM_PROVIDER=anthropic</code> and <code>ANTHROPIC_API_KEY</code> to let Claude structure problems and propose parameters.
          The AI never computes results; its proposals are bounds-checked and labelled.</p>
      </section>
      <section class="panel">
        <h2 class="h-section">Feature status</h2>
        <table class="data"><tbody><tr v-for="(v, k) in s.features" :key="k">
          <td>{{ humanize(String(k)) }}</td><td :class="['text-sm', tone(v)]">{{ v }}</td></tr></tbody></table>
      </section>
      <section class="panel xl:col-span-2 overflow-x-auto">
        <h2 class="h-section">Audit log</h2>
        <table class="data"><thead><tr><th>Time</th><th>Actor</th><th>Action</th><th>Entity</th><th>Detail</th></tr></thead>
          <tbody><tr v-for="(a, i) in audit" :key="i">
            <td class="num text-xs">{{ new Date(a.at).toLocaleString() }}</td><td class="text-sm">{{ a.actor }}</td>
            <td class="num text-sm">{{ a.action }}</td><td class="text-sm">{{ a.entity }} #{{ a.entity_id }}</td>
            <td class="num text-xs text-muted">{{ JSON.stringify(a.detail) }}</td></tr></tbody></table>
      </section>
    </div>
  </div>
</template>
