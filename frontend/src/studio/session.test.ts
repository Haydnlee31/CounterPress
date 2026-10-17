import { afterEach, expect, it, vi } from 'vitest'
const mocks = vi.hoisted(() => ({ initialize: vi.fn(async () => {}), loginPopup: vi.fn(async () => ({ account: { homeAccountId: 'test' } })),
  acquireTokenSilent: vi.fn(async () => ({ accessToken: 'test-access-token' })), clearCache: vi.fn(async () => {}), constructor: vi.fn() }))
vi.mock('@azure/msal-browser', () => ({ PublicClientApplication: class {
  constructor(config: unknown) { mocks.constructor(config) }
  initialize = mocks.initialize; loginPopup = mocks.loginPopup; acquireTokenSilent = mocks.acquireTokenSilent; clearCache = mocks.clearCache
} }))
import { createSession } from './session'
import { defaultPreferences } from '../types'
const config = { enabled: true, client_id: '11111111-1111-4111-8111-111111111111', authority: 'https://login.microsoftonline.com/22222222-2222-4222-8222-222222222222', scope: 'api://33333333-3333-4333-8333-333333333333/Editorial.Run' }
afterEach(() => { vi.unstubAllGlobals(); vi.clearAllMocks() })
it('only sends a delegated access token to same-origin API after explicit sign-in', async () => {
  const fetch = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify(config))).mockResolvedValue(new Response('{}'))
  vi.stubGlobal('fetch', fetch)
  const session = (await createSession())!
  await expect(session.call('review', 'increase', defaultPreferences)).rejects.toThrow('Sign in')
  expect(fetch).toHaveBeenCalledTimes(1)
  await session.signIn()
  await session.call('approve', 'increase', defaultPreferences, 'a'.repeat(64))
  expect(fetch.mock.calls[1][0]).toBe('/api/studio/increase/approve')
  expect(fetch.mock.calls[1][1]).toMatchObject({ headers: { Authorization: 'Bearer test-access-token' }, cache: 'no-store', referrerPolicy: 'no-referrer' })
  expect(mocks.constructor).toHaveBeenCalledWith(expect.objectContaining({ cache: { cacheLocation: 'memoryStorage' } }))
  await session.signOut()
  await expect(session.call('review', 'increase', defaultPreferences)).rejects.toThrow('Sign in')
  expect(mocks.clearCache).toHaveBeenCalledOnce()
})
it('rejects an unexpected authority before initializing Microsoft sign-in', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ ...config, authority: 'https://invalid.example' }))))
  await expect(createSession()).rejects.toThrow('configuration is invalid')
  expect(mocks.constructor).not.toHaveBeenCalled()
})
it('does not open a new login popup automatically when silent renewal fails', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(config))))
  const session = (await createSession())!
  await session.signIn()
  mocks.acquireTokenSilent.mockRejectedValueOnce(new Error('private diagnostic'))
  await expect(session.call('review', 'increase', defaultPreferences)).rejects.toThrow('new sign-in')
  expect(mocks.loginPopup).toHaveBeenCalledTimes(1)
})
it('sends broadcast selection and exact approval/attempt to the protected same-origin endpoint', async () => {
  const fetch = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify(config)))
    .mockResolvedValueOnce(new Response('<html>approved</html>', { headers: { 'Content-Type': 'text/html' } }))
  vi.stubGlobal('fetch', fetch)
  const session = (await createSession())!
  await session.signIn()
  const blob = await session.download('increase', defaultPreferences, 'a'.repeat(64), 'editor-1',
    { insight_id: 'story-2', format: 'lower-third' })
  expect(blob.size).toBeGreaterThan(0)
  expect(fetch.mock.calls[1][0]).toBe('/api/studio/increase/broadcast')
  expect(JSON.parse(fetch.mock.calls[1][1].body)).toEqual({ preferences: defaultPreferences,
    fingerprint: 'a'.repeat(64), attempt_id: 'editor-1', insight_id: 'story-2', format: 'lower-third' })
})
