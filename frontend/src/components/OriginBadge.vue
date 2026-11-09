<script setup lang="ts">
import { computed } from 'vue'
import type { Origin, ParamOrigin } from '../api'
import { ORIGIN_LABEL, paramOriginLabel } from '../format'

const props = defineProps<{ origin: Origin | ParamOrigin }>()
const COLORS: Record<string, string> = {
  computed: 'text-computed border-computed/40 bg-computed/5',
  assumption: 'text-assumption border-assumption/40 bg-assumption/5',
  default_assumption: 'text-assumption border-assumption/40 bg-assumption/5',
  rule_interpretation: 'text-rule border-rule/30 bg-rule/5',
  ai_interpretation: 'text-ai border-ai/40 bg-ai/5',
  ai_estimate: 'text-ai border-ai/40 bg-ai/5',
  user_input: 'text-user border-user/40 bg-user/5',
}
const label = computed(() => (ORIGIN_LABEL as Record<string, string>)[props.origin] ?? paramOriginLabel(props.origin as ParamOrigin))
</script>

<template>
  <span :class="['inline-block rounded border px-1.5 py-px text-[11px] font-medium leading-4 whitespace-nowrap', COLORS[origin]]">{{ label }}</span>
</template>
