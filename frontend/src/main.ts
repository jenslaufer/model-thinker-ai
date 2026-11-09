import { createApp } from 'vue'
import App from './App.vue'
import { initAuth } from './auth'
import { router } from './router'
import './style.css'

initAuth()
  .then((ready) => { if (ready) createApp(App).use(router).mount('#app') })
  .catch((e: Error) => {
    // Reloading /callback would replay a used code, so offer a fresh start instead.
    const app = document.getElementById('app')!
    app.textContent = `Sign-in failed: ${e.message}. `
    const retry = Object.assign(document.createElement('a'), { href: '/', textContent: 'Sign in again' })
    app.append(retry)
  })
