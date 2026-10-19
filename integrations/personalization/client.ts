/** Framework-independent adapter. Import into the redesigned UI when it is ready.
 * No DOM, layout, sign-in, model call, or server-side preference persistence.
 */
export type FanPreferences = {
  version: 1
  favorite_club_ids: string[]
  favorite_player_ids: string[]
  primary_club_id: string | null
  language: 'en' | 'zh-Hans'
  depth: 'casual' | 'analyst'
  metric_focus: 'balanced' | 'scoring' | 'creating' | 'passing' | 'defending'
  focus_player_id: string | null
}
export type StorageLike = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>
export type Registry = { clubIds: ReadonlySet<string>; playerIds: ReadonlySet<string> }
export type Cutoff = { period: 1 | 2; elapsed_ms: number }
export type HistoryScope = { as_of?: string; season?: string }
export type FanResponse = {
  version: 'fan-personalization-v1'
  request_id: string
  preferences: FanPreferences
  preference_id: string
  dataset_id: string
  [key: string]: unknown
}

export const preferenceKey = 'counterpress.fan.preferences.v1'
const legacyKey = 'counterpress.matchday.preferences.v1'
const identifier = /^[a-zA-Z0-9][a-zA-Z0-9_-]{0,95}$/
export const defaults = (): FanPreferences => ({
  version: 1, favorite_club_ids: [], favorite_player_ids: [], primary_club_id: null,
  language: 'en', depth: 'casual', metric_focus: 'balanced', focus_player_id: null,
})

function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('Invalid preferences')
  return value as Record<string, unknown>
}
function id(value: unknown): string {
  if (typeof value !== 'string' || !identifier.test(value)) throw new Error('Invalid identifier')
  return value
}
function ids(value: unknown, limit: number): string[] {
  if (!Array.isArray(value) || value.length > limit) throw new Error('Too many favorites')
  const result = value.map(id)
  if (new Set(result).size !== result.length) throw new Error('Duplicate favorites')
  return result.sort()
}
export function validatePreferences(value: unknown, registry?: Registry): FanPreferences {
  const raw = object(value)
  const allowed = new Set(Object.keys(defaults()))
  if (Object.keys(raw).some(k => !allowed.has(k)) || raw.version !== 1) throw new Error('Unsupported preferences')
  const clubs = ids(raw.favorite_club_ids, 4), players = ids(raw.favorite_player_ids, 12)
  const primary = raw.primary_club_id === null ? null : id(raw.primary_club_id)
  const focus = raw.focus_player_id === null ? null : id(raw.focus_player_id)
  if (primary && !clubs.includes(primary)) throw new Error('Primary club must be followed')
  if (registry && (clubs.some(c => !registry.clubIds.has(c)) || players.some(p => !registry.playerIds.has(p)) ||
    (focus && !registry.playerIds.has(focus)))) throw new Error('Unknown club or player')
  if (raw.language !== 'en' && raw.language !== 'zh-Hans') throw new Error('Unsupported language')
  if (raw.depth !== 'casual' && raw.depth !== 'analyst') throw new Error('Unsupported depth')
  const focusMetrics = ['balanced', 'scoring', 'creating', 'passing', 'defending']
  if (typeof raw.metric_focus !== 'string' || !focusMetrics.includes(raw.metric_focus)) throw new Error('Unsupported metric')
  return { version: 1, favorite_club_ids: clubs, favorite_player_ids: players, primary_club_id: primary,
    focus_player_id: focus, language: raw.language, depth: raw.depth,
    metric_focus: raw.metric_focus as FanPreferences['metric_focus'] }
}

export function readPreferences(storage: StorageLike, registry?: Registry): {
  preferences: FanPreferences; status: 'saved' | 'migrated' | 'empty' | 'unavailable' | 'invalid'
} {
  let raw: string | null, old: string | null
  try { raw = storage.getItem(preferenceKey); old = raw === null ? storage.getItem(legacyKey) : null }
  catch { return { preferences: defaults(), status: 'unavailable' } }
  try {
    if (raw !== null) return { preferences: validatePreferences(JSON.parse(raw), registry), status: 'saved' }
    if (old !== null) {
      const previous = object(JSON.parse(old)), next = defaults()
      next.language = previous.language === 'zh-Hans' ? 'zh-Hans' : 'en'
      next.depth = previous.depth === 'analyst' ? 'analyst' : 'casual'
      if (typeof previous.club_id === 'string' && identifier.test(previous.club_id) && (!registry || registry.clubIds.has(previous.club_id))) {
        next.favorite_club_ids = [previous.club_id]; next.primary_club_id = previous.club_id
      }
      if (typeof previous.player_id === 'string' && identifier.test(previous.player_id) && (!registry || registry.playerIds.has(previous.player_id))) {
        next.favorite_player_ids = [previous.player_id]; next.focus_player_id = previous.player_id
      }
      // Reading never writes or destroys the old UI's preferences.
      return { preferences: next, status: 'migrated' }
    }
    return { preferences: defaults(), status: 'empty' }
  } catch { return { preferences: defaults(), status: 'invalid' } }
}

export function savePreferences(storage: StorageLike, value: FanPreferences, registry?: Registry): boolean {
  const normalized = validatePreferences(value, registry)
  try { storage.setItem(preferenceKey, JSON.stringify(normalized)); return true }
  catch { return false }
}
export function clearPreferences(storage: StorageLike): boolean {
  try { storage.removeItem(preferenceKey); storage.removeItem(legacyKey); return true }
  catch { return false }
}
export function toggleFavorite(value: FanPreferences, kind: 'player' | 'club', subject: string, registry?: Registry): FanPreferences {
  id(subject)
  const p = validatePreferences(value, registry), key = kind === 'player' ? 'favorite_player_ids' : 'favorite_club_ids'
  const removing = p[key].includes(subject)
  p[key] = removing ? p[key].filter(x => x !== subject) : [...p[key], subject]
  if (removing && kind === 'club' && p.primary_club_id === subject) p.primary_club_id = null
  if (removing && kind === 'player' && p.focus_player_id === subject) p.focus_player_id = null
  return validatePreferences(p, registry)
}

export class StaleFanResponse extends Error {
  constructor() { super('The viewing context changed'); this.name = 'StaleFanResponse' }
}

/** One client per independently rendered surface. cancel() on unmount or seek.
 * Only the newest request on this client may produce a renderable result.
 */
export function createFanClient(fetcher: typeof fetch = fetch) {
  let sequence = 0
  let active: AbortController | undefined
  const instance = crypto.randomUUID().replaceAll('-', '')
  const cancel = () => { sequence++; active?.abort(); active = undefined }
  async function post(path: string, preferences: FanPreferences, extra: Record<string, unknown> = {}): Promise<FanResponse> {
    cancel()
    const turn = sequence, controller = new AbortController(); active = controller
    const normalized = validatePreferences(preferences), request_id = `fan-${instance}-${turn}`
    const response = await fetcher(`/api/fan/${path}`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...extra, preferences: normalized, request_id }),
      signal: controller.signal, cache: 'no-store', credentials: 'omit' })
    if (turn !== sequence) throw new StaleFanResponse()
    if (!response.ok) throw new Error(`Personalized view unavailable (${response.status})`)
    const result = object(await response.json())
    if (turn !== sequence) throw new StaleFanResponse()
    if (result.version !== 'fan-personalization-v1' || result.request_id !== request_id ||
      JSON.stringify(validatePreferences(result.preferences)) !== JSON.stringify(normalized)) throw new StaleFanResponse()
    return result as FanResponse
  }
  return {
    cancel,
    validate: (p: FanPreferences) => post('preferences/validate', p),
    home: (p: FanPreferences, scope: HistoryScope & { limit?: number } = {}) => post('home', p, scope),
    player: (pid: string, p: FanPreferences, scope: HistoryScope = {}) => post(`players/${id(pid)}`, p, scope),
    club: (cid: string, p: FanPreferences, scope: HistoryScope = {}) => post(`clubs/${id(cid)}`, p, scope),
    compare: (player_ids: string[], p: FanPreferences, scope: HistoryScope = {}) => post('players/compare', p, { ...scope, player_ids: player_ids.map(id) }),
    match: (mid: string, cutoff: Cutoff, p: FanPreferences, options: { through_sequence?: number; card_budget?: number } = {}) =>
      post(`matches/${id(mid)}`, p, { ...options, cutoff }),
  }
}
