import { PublicClientApplication, type AccountInfo } from '@azure/msal-browser'
import type { Event, Preferences, SegmentRecap } from '../types'

export type Review = {
  evidence: { evidence_id: string; revision: number; definition: string; records: Event[] }[]
  fingerprint: string; source_version: number; recap: SegmentRecap
  status: 'unreviewed' | 'approved' | 'revoked' | 'changed' | 'unavailable'
  attempt_id?: string | null; workflow?: { applied: boolean; status: string; expires_at_unix_ms: number } | null
  valid_for_ms?: number | null; editor_enabled?: boolean; editorial_status?: string | null
  approval_id: string | null; approved_at_unix_ms: number | null
}
export type Session = {
  signIn(): Promise<void>; signOut(): Promise<void>
  call(action: 'review' | 'approve' | 'revoke' | 'draft', scenario: string, preferences: Preferences, fingerprint?: string, signal?: AbortSignal, attemptId?: string | null): Promise<Review>
  download(scenario: string, preferences: Preferences, fingerprint: string, attemptId?: string | null): Promise<Blob>
}

export async function createSession(): Promise<Session | null> {
  const response = await fetch('/api/studio/config', { cache: 'no-store', referrerPolicy: 'no-referrer' })
  if (!response.ok) throw new Error('Studio configuration is unavailable. Try again later.')
  const config = await response.json()
  if (config.enabled === false) return null
  const uuid = '[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}'
  if (config.enabled !== true || !new RegExp(`^${uuid}$`).test(config.client_id)
    || !new RegExp(`^https://login\\.microsoftonline\\.com/${uuid}$`).test(config.authority)
    || !new RegExp(`^api://${uuid}/Editorial\\.Run$`).test(config.scope)) throw new Error('Studio sign-in configuration is invalid.')
  const app = new PublicClientApplication({
    auth: { clientId: config.client_id, authority: config.authority, redirectUri: `${location.origin}/auth.html` },
    cache: { cacheLocation: 'memoryStorage' },
    system: { popupBridgeTimeout: 300000, loggerOptions: { loggerCallback: () => {}, piiLoggingEnabled: false } },
  })
  await app.initialize()
  let account: AccountInfo | null = null
  const scopes = [config.scope]
  const request = async (action: string, scenario: string, preferences: Preferences, fingerprint?: string, signal?: AbortSignal, attemptId?: string | null) => {
    if (!account) throw new Error('Sign in to review this version.')
    let accessToken: string
    try { accessToken = (await app.acquireTokenSilent({ scopes, account })).accessToken }
    catch { throw new Error('Your session needs a new sign-in. End this Studio session and sign in again.') }
    if (signal?.aborted) throw new DOMException('Aborted', 'AbortError')
    const result = await fetch(`/api/studio/${encodeURIComponent(scenario)}/${action}`, {
      method: 'POST', cache: 'no-store', referrerPolicy: 'no-referrer',
      signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(action === 'draft' ? 25000 : 15000)]) : AbortSignal.timeout(action === 'draft' ? 25000 : 15000),
      headers: { Authorization: `Bearer ${accessToken}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ preferences, ...(fingerprint ? { fingerprint } : {}), ...(attemptId ? { attempt_id: attemptId } : {}) }),
    })
    if (!result.ok) {
      const messages: Record<number, string> = {
        401: 'Your session expired. End this Studio session and sign in again.',
        403: 'This account is not assigned Studio editor access.',
        409: 'This version changed or its approval was revoked. Refresh and review the latest version.',
        503: 'Studio cannot verify approval right now. Try again later.',
      }
      throw new Error(messages[result.status] ?? 'Studio could not complete this request. Try refreshing.')
    }
    return result
  }
  return {
    async signIn() {
      try { account = (await app.loginPopup({ scopes, prompt: 'select_account' })).account }
      catch { throw new Error('Sign-in did not finish. Allow the Microsoft sign-in popup and try again.') }
      if (!account) throw new Error('No account was selected. Try signing in again.')
    },
    async signOut() { account = null; await app.clearCache() },
    async call(action, scenario, preferences, fingerprint, signal, attemptId) {
      return (await request(action, scenario, preferences, fingerprint, signal, attemptId)).json()
    },
    async download(scenario, preferences, fingerprint, attemptId) {
      return (await request('export', scenario, preferences, fingerprint, undefined, attemptId)).blob()
    },
  }
}
