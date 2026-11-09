import { createHash } from 'node:crypto'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { authorizeUrl, decodeClaims, handleCallback, pkceChallenge, session } from './auth'

const CFG = { mode: 'oidc' as const, issuer: 'https://auth.example.test/t/mta', client_id: 'mta-spa' }

describe('PKCE', () => {
  it('matches an independent S256 implementation', async () => {
    const verifier = 'abcdefghijklmnopqrstuvwxyz-0123456789._~ABCDEFGHIJKLMNOP'
    expect(await pkceChallenge(verifier)).toBe(createHash('sha256').update(verifier).digest('base64url'))
  })

  it('builds the launch-kit authorize URL', () => {
    const url = new URL(authorizeUrl(CFG, { challenge: 'C', state: 'S', redirectUri: 'http://app.test/callback' }))
    expect(url.origin + url.pathname).toBe('https://auth.example.test/t/mta/auth/authorize')
    expect(Object.fromEntries(url.searchParams)).toEqual({
      response_type: 'code', client_id: 'mta-spa', redirect_uri: 'http://app.test/callback',
      scope: 'openid profile email', state: 'S', code_challenge: 'C', code_challenge_method: 'S256',
    })
  })
})

describe('claims', () => {
  it('decodes base64url JWT payloads with unicode', () => {
    const payload = Buffer.from(JSON.stringify({ email: 'jürgen@x.de', role: 'user' })).toString('base64url')
    expect(decodeClaims(`h.${payload}.s`)).toEqual({ email: 'jürgen@x.de', role: 'user' })
  })
})

describe('callback', () => {
  beforeEach(() => { sessionStorage.clear(); localStorage.clear(); session.accessToken = null })

  it('rejects a state mismatch without calling the token endpoint', async () => {
    localStorage.setItem('mta.pkce.expected', JSON.stringify({ verifier: 'v', returnTo: '/' }))
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
    await expect(handleCallback(CFG, '?code=abc&state=forged')).rejects.toThrow(/state/)
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  // The login can finish in another tab (e.g. a password-reset mail link), so the
  // pending PKCE data must live in localStorage, keyed by state.
  it('exchanges the code and stores tokens', async () => {
    localStorage.setItem('mta.pkce.s1', JSON.stringify({ verifier: 'v', returnTo: '/models' }))
    const access = `h.${Buffer.from(JSON.stringify({ email: 'a@b.de', role: 'user' })).toString('base64url')}.s`
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ access_token: access, refresh_token: 'rt', id_token: 'idt' }), { status: 200 }))
    const returnTo = await handleCallback(CFG, '?code=abc&state=s1')
    expect(returnTo).toBe('/models')
    const [url, init] = fetchSpy.mock.calls[0]
    expect(url).toBe('https://auth.example.test/t/mta/auth/token')
    const body = new URLSearchParams(String(init?.body))
    expect(Object.fromEntries(body)).toMatchObject({ grant_type: 'authorization_code', code: 'abc', code_verifier: 'v', client_id: 'mta-spa' })
    expect(session.accessToken).toBe(access)
    expect(session.user?.email).toBe('a@b.de')
    expect(localStorage.getItem('mta.pkce.s1')).toBeNull()
  })

  it('keeps parallel login attempts apart', async () => {
    localStorage.setItem('mta.pkce.a', JSON.stringify({ verifier: 'va', returnTo: '/a' }))
    localStorage.setItem('mta.pkce.b', JSON.stringify({ verifier: 'vb', returnTo: '/b' }))
    const access = `h.${Buffer.from(JSON.stringify({ email: 'a@b.de' })).toString('base64url')}.s`
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ access_token: access }), { status: 200 }))
    expect(await handleCallback(CFG, '?code=c&state=a')).toBe('/a')
    expect(new URLSearchParams(String(fetchSpy.mock.calls[0][1]?.body)).get('code_verifier')).toBe('va')
    expect(localStorage.getItem('mta.pkce.b')).not.toBeNull()
  })
})
