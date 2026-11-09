<script setup lang="ts">
import type { Scalar } from '../api'
import { fmt, humanize } from '../format'

defineProps<{ metrics: Record<string, Scalar>; highlight?: string | null; help?: (metric: string) => string }>()
</script>

<template>
  <table class="data">
    <tbody>
      <tr v-for="(v, k) in metrics" :key="k" :class="k === highlight ? 'bg-accent-soft/60' : ''">
        <td class="text-muted">{{ humanize(String(k)) }}
          <div v-if="help?.(String(k))" class="text-xs font-normal text-muted/80">{{ help(String(k)) }}</div></td>
        <td class="num text-right">{{ fmt(v) }}</td>
      </tr>
    </tbody>
  </table>
</template>
