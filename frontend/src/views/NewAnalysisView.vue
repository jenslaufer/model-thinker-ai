<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, type ProblemStructure, type Selection } from '../api'
import ScoreBar from '../components/ScoreBar.vue'
import { setCurrent } from '../current'
import { humanize, parseList, parseNumber } from '../format'

const router = useRouter()
const form = reactive({ title: '', description: '', objective: '', time_horizon: '', system_boundaries: '',
  available_data: '', actors: '', decision_scope: '' })
const preview = ref<{ structure: ProblemStructure; selection: Selection } | null>(null)
const busy = ref<'' | 'preview' | 'run'>('')
// Asked once when the goal lacks a target: the app never estimates the goal itself.
const goal = reactive({ asked: false, missing: [] as string[], quantity: '', value: '', risk: '' })
const err = ref('')

const EXAMPLES = [
  { title: 'App launch: referrals vs. ads', description: 'We launch a new budgeting app. Adoption depends on word of mouth and marketing reach. Should we invest in a referral programme or in ads? A competitor may react with a price cut.',
    objective: 'Maximise active users after 24 months', time_horizon: '24 months', actors: 'Our company, Competitor, Customers',
    available_data: 'Monthly signups for 6 months', decision_scope: 'Budget split between referral programme and ads', system_boundaries: 'German market' },
  { title: 'Customer churn', description: 'Our subscription customers move between active, dormant and churned states. Revenue is concentrated on few customers. Should we invest in retention or in acquisition?',
    objective: 'Maximise the long-run share of active customers', time_horizon: '3 years', actors: 'Company, Customers',
    available_data: '', decision_scope: 'Retention vs. acquisition budget', system_boundaries: 'Existing customer base' },
  { title: 'Industry standard consortium', description: 'Five competitors consider funding a shared data standard. Everyone benefits, but each prefers that the others pay. Cooperation in the past was fragile; trust is low.',
    objective: 'Get the standard funded', time_horizon: '2 years', actors: 'Firm A, Firm B, Firm C, Firm D, Firm E',
    available_data: '', decision_scope: 'Contribution rules and enforcement', system_boundaries: 'Consortium members' },
]

const target = computed(() => parseNumber(goal.value))
const risk = computed(() => parseNumber(goal.risk))
const goalError = computed(() => {
  if (Number.isNaN(target.value)) return 'The target must be a number, e.g. 1000 or 1,000.'
  if (risk.value !== null && !(risk.value > 0 && risk.value < 100)) return 'The risk must be a percentage between 0 and 100.'
  return ''
})
const problem = computed(() => ({ ...form, actors: parseList(form.actors), target_quantity: goal.quantity.trim(),
  target_value: target.value, risk_limit: risk.value === null ? null : risk.value / 100 }))
const valid = computed(() => form.description.trim().length >= 10)

function useExample(i: number) {
  Object.assign(form, EXAMPLES[i]); preview.value = null
  Object.assign(goal, { asked: false, missing: [], quantity: '', value: '', risk: '' })
}

async function doPreview() {
  busy.value = 'preview'; err.value = ''
  try { preview.value = await api.structure(problem.value) } catch (e) { err.value = (e as Error).message }
  busy.value = ''
}

async function run() {
  if (goalError.value) return
  busy.value = 'run'; err.value = ''
  try {
    if (!goal.asked) {
      const { frame, missing } = await api.frame(problem.value)
      goal.asked = true
      if (missing.length) {
        Object.assign(goal, { missing, quantity: goal.quantity || frame.quantity })
        busy.value = ''
        return
      }
    }
    const detail = await api.createAnalysis({ problem: problem.value, title: form.title || undefined })
    setCurrent(detail)
    router.push({ path: '/answer', query: { analysis: detail.id } })
  } catch (e) { err.value = (e as Error).message; busy.value = '' }
}
</script>

<template>
  <div>
    <h1 class="h-page">New analysis</h1>
    <p class="mt-1 mb-6 max-w-3xl text-sm text-muted">Describe the problem in plain language and add structure where you can.
      The more concrete the objective and data, the fewer results rest on default assumptions.</p>
    <div class="mb-5 flex flex-wrap items-center gap-2 text-sm">
      <span class="text-muted">Examples:</span>
      <button v-for="(e, i) in EXAMPLES" :key="i" class="btn-ghost !py-1" @click="useExample(i)">{{ e.title }}</button>
    </div>
    <div class="grid gap-6 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <form class="panel space-y-4" @submit.prevent="run">
        <div>
          <label class="label" for="title">Title</label>
          <input id="title" v-model="form.title" class="field" maxlength="200" placeholder="Optional — defaults to the problem text" />
        </div>
        <div>
          <label class="label" for="desc">Problem <span class="text-danger">*</span></label>
          <textarea id="desc" v-model="form.description" class="field min-h-32" maxlength="10000"
            placeholder="What is happening, what is at stake, what decision is open?" />
        </div>
        <div class="grid gap-4 md:grid-cols-2">
          <div><label class="label" for="obj">Objective</label><input id="obj" v-model="form.objective" class="field" /></div>
          <div><label class="label" for="hor">Time horizon</label><input id="hor" v-model="form.time_horizon" class="field" placeholder="e.g. 24 months" /></div>
          <div><label class="label" for="act">Actors <span class="font-normal text-muted">(comma-separated)</span></label><input id="act" v-model="form.actors" class="field" /></div>
          <div><label class="label" for="dec">Decision scope</label><input id="dec" v-model="form.decision_scope" class="field" placeholder="What can you actually change?" /></div>
          <div><label class="label" for="sys">System boundaries</label><input id="sys" v-model="form.system_boundaries" class="field" /></div>
          <div><label class="label" for="data">Available data</label><input id="data" v-model="form.available_data" class="field" placeholder="e.g. monthly signups for 6 months" /></div>
        </div>
        <section :class="['rounded border p-4', goal.missing.length ? 'border-assumption/40 bg-assumption/5' : 'border-line']" aria-live="polite">
          <div class="text-sm font-semibold">What number by when would count as success?
            <span v-if="!goal.missing.length" class="font-normal text-muted">(optional)</span></div>
          <p class="mt-1 text-sm text-muted">{{ goal.missing.length
            ? 'Your question has no target yet. Without one the app can explain the situation but cannot say yes or no. Fill in what you know, or run it as it is.'
            : 'With a target the answer says yes or no and what it would take. The app never makes one up.' }}</p>
          <div class="mt-3 grid gap-3 sm:grid-cols-3">
            <div><label class="label" for="gq">Quantity</label><input id="gq" v-model="goal.quantity" class="field" placeholder="e.g. paying users" /></div>
            <div><label class="label" for="gv">Target number</label>
              <input id="gv" v-model="goal.value" class="field" inputmode="decimal" placeholder="e.g. 1000" /></div>
            <div><label class="label" for="gr">Or: highest acceptable risk (%)</label>
              <input id="gr" v-model="goal.risk" class="field" inputmode="decimal" placeholder="e.g. 5" /></div>
          </div>
        </section>
        <p v-if="goalError" class="text-sm text-danger" role="alert">{{ goalError }}</p>
        <p v-if="err" class="text-sm text-danger">{{ err }}</p>
        <div class="flex gap-3">
          <button type="button" class="btn-ghost" :disabled="!valid || !!busy" @click="doPreview">
            {{ busy === 'preview' ? 'Structuring…' : 'Preview structure' }}</button>
          <button type="submit" class="btn" :disabled="!valid || !!busy">
            {{ busy === 'run' ? 'Computing models…' : 'Run analysis' }}</button>
        </div>
      </form>
      <aside class="panel">
        <h2 class="h-section">Preview</h2>
        <p v-if="!preview" class="text-sm text-muted">Preview shows detected problem aspects and the suggested model set
          before anything is computed.</p>
        <template v-else>
          <div class="mb-1 text-xs text-muted">Structured by: {{ preview.structure.origin }}</div>
          <div class="mb-4 flex flex-wrap gap-1.5">
            <span v-for="(_v, k) in preview.structure.problem_types" :key="k"
              class="rounded bg-accent-soft px-2 py-0.5 text-xs text-accent">{{ humanize(String(k)) }}</span>
          </div>
          <h3 class="h-section">Suggested models</h3>
          <ul class="space-y-2.5">
            <li v-for="k in preview.selection.selected" :key="k">
              <template v-for="f in preview.selection.fits.filter((x) => x.key === k)" :key="f.key">
                <div class="flex justify-between text-sm"><span class="font-medium">{{ f.name }}</span><span class="num">{{ f.score }}</span></div>
                <ScoreBar :value="f.score" />
                <div class="mt-0.5 text-xs text-muted">{{ f.reasons[0] }}</div>
              </template>
            </li>
          </ul>
          <ul v-if="preview.structure.data_gaps.length" class="mt-4 space-y-1 text-xs text-assumption">
            <li v-for="g in preview.structure.data_gaps" :key="g">{{ g }}</li>
          </ul>
          <p class="mt-4 text-xs text-muted">{{ preview.selection.note }}</p>
        </template>
      </aside>
    </div>
  </div>
</template>
