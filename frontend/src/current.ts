// The analysis the user works on, shared across pages (Problem Explorer, Scenario Lab, ...).
import { ref, watch } from 'vue'
import { api, type AnalysisDetail } from './api'

const KEY = 'mta.currentAnalysis'
const stored = (() => { try { return Number(localStorage.getItem(KEY)) || null } catch { return null } })()

export const currentId = ref<number | null>(stored)
export const current = ref<AnalysisDetail | null>(null)
export const loading = ref(false)
export const error = ref('')

watch(currentId, (id) => { try { id ? localStorage.setItem(KEY, String(id)) : localStorage.removeItem(KEY) } catch { /* private mode */ } })

export async function load(id: number, revision?: number) {
  loading.value = true
  error.value = ''
  try {
    current.value = await api.analysis(id, revision)
    currentId.value = id
  } catch (e) {
    error.value = (e as Error).message
    if (!revision) { current.value = null; currentId.value = null }
  } finally {
    loading.value = false
  }
}

export function setCurrent(detail: AnalysisDetail) {
  current.value = detail
  currentId.value = detail.id
}
