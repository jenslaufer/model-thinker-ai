// Login via launch-kit (OIDC authorization code + PKCE). The app never sees passwords.
// Tokens live in sessionStorage: they survive a reload but not the tab. Pending PKCE data lives in
// localStorage, keyed by state, because the login may finish in another tab (e.g. a mail link).
import { reactive } from 'vue'

export type AuthConfig = { mode: 'dev' } | { mode: 'oidc'; issuer: string; client_id: string }
type OidcConfig = Extract<AuthConfig, { mode: 'oidc' }>
type Claims = { email?: string; name?: string; role?: string; exp?: number }

const TOKENS = 'mta.tokens'
const PKCE = 'mta.pkce.'
const CALLBACK = '/callback'

const load = <T>(key: string, store: Storage = sessionStorage): T | null => {
  try { return JSON.parse(store.getItem(key) ?? 'null') } catch { return null }
}

export const session = reactive({
  config: null as AuthConfig | null,
  accessToken: null as string | null,
  user: null as Claims | null,
})

const base64url = (bytes: Uint8Array) =>
  btoa(String.fromCharCode(...bytes)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')

const randomString = () => base64url(crypto.getRandomValues(new Uint8Array(32)))

export async function pkceChallenge(verifier: string): Promise<string> {
  return base64url(new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier))))
}

export function decodeClaims(jwt: string): Claims {
  const b64 = jwt.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')
  const bytes = Uint8Array.from(atob(b64.padEnd(b64.length + ((4 - (b64.length % 4)) % 4), '=')), (c) => c.charCodeAt(0))
  return JSON.parse(new TextDecoder().decode(bytes))
}

const endpoint = (cfg: OidcConfig, path: string) => `${cfg.issuer.replace(/\/$/, '')}/auth/${path}`

export function authorizeUrl(cfg: OidcConfig, p: { challenge: string; state: string; redirectUri: string }) {
  const q = new URLSearchParams({
    response_type: 'code', client_id: cfg.client_id, redirect_uri: p.redirectUri, scope: 'openid profile email',
    state: p.state, code_challenge: p.challenge, code_challenge_method: 'S256',
  })
  return `${endpoint(cfg, 'authorize')}?${q}`
}

function store(t: { access_token: string; refresh_token?: string; id_token?: string }) {
  const prev = load<Record<string, string>>(TOKENS) ?? {}
  const tokens = { access: t.access_token, refresh: t.refresh_token ?? prev.refresh, id: t.id_token ?? prev.id }
  sessionStorage.setItem(TOKENS, JSON.stringify(tokens))
  session.accessToken = tokens.access
  session.user = decodeClaims(tokens.access)
}

async function tokenRequest(cfg: OidcConfig, params: Record<string, string>) {
  const res = await fetch(endpoint(cfg, 'token'), {
    method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ ...params, client_id: cfg.client_id }).toString(),
  })
  if (!res.ok) throw new Error(`token request failed (${res.status})`)
  store(await res.json())
}

export async function login(returnTo = location.pathname + location.search) {
  const cfg = session.config as OidcConfig
  const verifier = randomString()
  const state = randomString()
  localStorage.setItem(PKCE + state, JSON.stringify({ verifier, returnTo }))
  location.assign(authorizeUrl(cfg, { challenge: await pkceChallenge(verifier), state, redirectUri: location.origin + CALLBACK }))
}

/** Completes the redirect from launch-kit. Returns the path to continue at. */
export async function handleCallback(cfg: OidcConfig, search: string): Promise<string> {
  const q = new URLSearchParams(search)
  const key = PKCE + (q.get('state') ?? '')
  const pending = load<{ verifier: string; returnTo: string }>(key, localStorage)
  localStorage.removeItem(key)
  if (q.get('error')) throw new Error(q.get('error_description') ?? q.get('error')!)
  if (!pending) throw new Error('login state mismatch — please sign in again')
  await tokenRequest(cfg, { grant_type: 'authorization_code', code: q.get('code') ?? '',
    redirect_uri: location.origin + CALLBACK, code_verifier: pending.verifier })
  return pending.returnTo || '/'
}

/** Tries the refresh token once; returns false if the user must sign in again. */
export async function refresh(): Promise<boolean> {
  const cfg = session.config
  const rt = load<Record<string, string>>(TOKENS)?.refresh
  if (cfg?.mode !== 'oidc' || !rt) return false
  try { await tokenRequest(cfg, { grant_type: 'refresh_token', refresh_token: rt }); return true } catch { return false }
}

export function logout() {
  const cfg = session.config
  const idToken = load<Record<string, string>>(TOKENS)?.id
  sessionStorage.removeItem(TOKENS)
  session.accessToken = null
  session.user = null
  if (cfg?.mode !== 'oidc') return
  const q = new URLSearchParams({ client_id: cfg.client_id, post_logout_redirect_uri: location.origin + '/' })
  if (idToken) q.set('id_token_hint', idToken)
  location.assign(`${endpoint(cfg, 'logout')}?${q}`)
}

/** Runs before the app mounts. Returns false when the browser is being redirected to launch-kit. */
export async function initAuth(): Promise<boolean> {
  session.config = await (await fetch('/api/auth/config')).json()
  const cfg = session.config!
  if (cfg.mode === 'dev') return true
  if (location.pathname === CALLBACK) {
    const returnTo = await handleCallback(cfg, location.search)
    history.replaceState(null, '', returnTo)
    return true
  }
  const tokens = load<Record<string, string>>(TOKENS)
  if (tokens?.access) {
    session.accessToken = tokens.access
    session.user = decodeClaims(tokens.access)
    if ((session.user.exp ?? 0) * 1000 > Date.now() + 30_000 || (await refresh())) return true
  }
  await login()
  return false
}
