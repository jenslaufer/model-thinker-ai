<script setup lang="ts">
defineProps<{ value: number; max?: number; tone?: 'accent' | 'muted' }>()
</script>

<template>
  <div class="h-1.5 w-full overflow-hidden rounded-full bg-line/70">
    <div :class="['h-full rounded-full', tone === 'muted' ? 'bg-muted/60' : 'bg-accent']"
      :style="{ width: `${Math.max(0, Math.min(100, (value / (max ?? 100)) * 100))}%` }" />
  </div>
</template>
