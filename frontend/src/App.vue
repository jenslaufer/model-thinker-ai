<script setup lang="ts">
import { ref } from 'vue'
import { NAV } from './router'
import { current } from './current'
import { logout, session } from './auth'

const open = ref(false)
const pick = (...paths: string[]) => paths.map((p) => NAV.find((n) => n.path === p)!)
const GROUPS = [
  { label: '', items: pick('/', '/new') },
  { label: 'Analysis', items: pick('/answer', '/problem', '/selection', '/analysis', '/scenarios', '/graph', '/decisions', '/reports') },
  { label: 'Tools', items: pick('/models', '/simulation', '/settings') },
]
</script>

<template>
  <div class="min-h-screen md:flex">
    <aside :class="['border-line bg-panel md:sticky md:top-0 md:block md:h-screen md:w-60 md:shrink-0 md:border-r', open ? 'block' : 'hidden']">
      <div class="px-5 pt-5 pb-4">
        <div class="text-[15px] font-semibold tracking-tight">Model Thinking <span class="text-accent">AI</span></div>
        <div class="text-xs text-muted">Multi-model decision intelligence</div>
      </div>
      <nav class="px-3 pb-6" @click="open = false">
        <template v-for="g in GROUPS" :key="g.label">
          <div v-if="g.label" class="mt-5 mb-1 px-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted">{{ g.label }}</div>
          <RouterLink v-for="item in g.items" :key="item.path" :to="item.path"
            class="block rounded px-2 py-1.5 text-sm text-ink/80 hover:bg-paper hover:text-ink"
            active-class="!bg-accent-soft !text-accent font-medium" :exact-active-class="item.path === '/' ? '!bg-accent-soft !text-accent font-medium' : ''">
            {{ item.name }}
          </RouterLink>
        </template>
        <div v-if="session.user" class="mt-6 flex items-center justify-between gap-2 border-t border-line px-2 pt-3 text-xs">
          <span class="truncate" :title="session.user.email">{{ session.user.email ?? session.user.name }}</span>
          <button class="shrink-0 text-muted hover:text-accent" @click.stop="logout">Sign out</button>
        </div>
        <div v-else-if="session.config?.mode === 'dev'" class="mt-6 px-2 text-xs text-assumption">Dev mode — no sign-in</div>
        <div v-if="current" class="mt-4 rounded border border-line px-2.5 py-2 text-xs">
          <div class="text-muted">Current analysis</div>
          <div class="truncate font-medium" :title="current.title">{{ current.title }}</div>
          <div class="text-muted">revision {{ current.revision }}</div>
        </div>
      </nav>
    </aside>
    <div class="flex items-center justify-between border-b border-line bg-panel px-4 py-3 md:hidden">
      <span class="font-semibold">Model Thinking <span class="text-accent">AI</span></span>
      <button class="btn-ghost !py-1" @click="open = !open">Menu</button>
    </div>
    <main class="min-w-0 flex-1 px-4 py-6 md:px-10 md:py-8">
      <RouterView />
    </main>
  </div>
</template>
