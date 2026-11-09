<script setup lang="ts">
import katex from 'katex'
import 'katex/dist/katex.min.css'
import { computed } from 'vue'

const props = defineProps<{ tex: string }>()
const html = computed(() => katex.renderToString(props.tex, { displayMode: true, throwOnError: false }))
</script>

<template>
  <div class="overflow-x-auto py-1" v-html="html" />
</template>
