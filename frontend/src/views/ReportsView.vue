<script setup lang="ts">
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import { computed, ref, watch } from 'vue'
import { api } from '../api'
import AnalysisGate from '../components/AnalysisGate.vue'
import { current } from '../current'

const md = ref('')
watch(() => current.value && [current.value.id, current.value.revision], async () => {
  if (current.value) md.value = (await api.report(current.value.id, current.value.revision)).content
}, { immediate: true })
// The report embeds user-written problem text: sanitize before rendering.
const html = computed(() => DOMPurify.sanitize(marked.parse(md.value, { async: false }) as string))

const print = () => window.print()

function download() {
  const a = document.createElement('a')
  a.href = URL.createObjectURL(new Blob([md.value], { type: 'text/markdown' }))
  a.download = `analysis-${current.value?.id}-rev${current.value?.revision}.md`
  a.click()
  URL.revokeObjectURL(a.href)
}
</script>

<template>
  <AnalysisGate title="Reports" subtitle="Automated report for the selected revision. Every section states whether content is computed, assumed or interpreted.">
    <div class="mb-4 flex gap-2"><button class="btn" :disabled="!md" @click="download">Download Markdown</button>
      <button class="btn-ghost" :disabled="!md" @click="print">Print</button></div>
    <article class="panel report max-w-4xl" v-html="html" />
  </AnalysisGate>
</template>

<style scoped>
.report :deep(h1) { font-size: 1.6rem; font-weight: 600; margin-bottom: .5rem }
.report :deep(h2) { font-size: 1.2rem; font-weight: 600; margin: 1.8rem 0 .6rem; padding-top: .8rem; border-top: 1px solid var(--color-line) }
.report :deep(h3) { font-weight: 600; margin: 1.2rem 0 .4rem }
.report :deep(p), .report :deep(li) { font-size: .92rem; line-height: 1.6 }
.report :deep(ul) { list-style: disc; padding-left: 1.2rem; margin: .4rem 0 }
.report :deep(table) { display: block; overflow-x: auto; width: 100%; font-size: .85rem; margin: .6rem 0; border-collapse: collapse }
.report :deep(th), .report :deep(td) { border-bottom: 1px solid var(--color-line); padding: .35rem .6rem .35rem 0; text-align: left; vertical-align: top }
.report :deep(blockquote) { border-left: 3px solid var(--color-accent); padding-left: .8rem; color: var(--color-muted); margin: .8rem 0 }
.report :deep(code) { font-family: var(--font-mono); font-size: .85em }
</style>
