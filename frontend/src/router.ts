import { createRouter, createWebHistory } from 'vue-router'

export const NAV = [
  { path: '/', name: 'Dashboard', view: () => import('./views/DashboardView.vue') },
  { path: '/new', name: 'New Analysis', view: () => import('./views/NewAnalysisView.vue') },
  { path: '/answer', name: 'Answer', view: () => import('./views/AnswerView.vue') },
  { path: '/problem', name: 'Problem Explorer', view: () => import('./views/ProblemExplorerView.vue') },
  { path: '/models', name: 'Model Library', view: () => import('./views/ModelLibraryView.vue') },
  { path: '/selection', name: 'Model Selection', view: () => import('./views/ModelSelectionView.vue') },
  { path: '/analysis', name: 'Model Results', view: () => import('./views/MultiModelView.vue') },
  { path: '/scenarios', name: 'Scenario Lab', view: () => import('./views/ScenarioLabView.vue') },
  { path: '/simulation', name: 'Simulation Center', view: () => import('./views/SimulationCenterView.vue') },
  { path: '/graph', name: 'Knowledge Graph', view: () => import('./views/KnowledgeGraphView.vue') },
  { path: '/decisions', name: 'Decision Center', view: () => import('./views/DecisionCenterView.vue') },
  { path: '/reports', name: 'Reports', view: () => import('./views/ReportsView.vue') },
  { path: '/settings', name: 'Settings', view: () => import('./views/SettingsView.vue') },
]

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    ...NAV.map((n) => ({ path: n.path, name: n.name, component: n.view })),
    { path: '/models/:modelKey', name: 'Model Detail', component: () => import('./views/ModelDetailView.vue'), props: true },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})
