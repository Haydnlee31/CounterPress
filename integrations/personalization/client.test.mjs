import test from 'node:test'
import assert from 'node:assert/strict'
import {
  defaults, validatePreferences, readPreferences, savePreferences, clearPreferences,
  toggleFavorite, createFanClient, StaleFanResponse, preferenceKey,
} from './client.ts'

const registry = { clubIds: new Set(['eastbridge', 'redhaven']), playerIds: new Set(['eb09', 'rh08']) }
function storage(initial = {}) {
  const values = new Map(Object.entries(initial))
  return { values, getItem: k => values.get(k) ?? null, setItem: (k, v) => values.set(k, v), removeItem: k => values.delete(k) }
}
function response(init, changes = {}) {
  const request = JSON.parse(init.body)
  return new Response(JSON.stringify({ version: 'fan-personalization-v1', preference_id: 'hash', dataset_id: 'data',
    preferences: request.preferences, request_id: request.request_id, ...changes }), { status: 200 })
}

test('migrate existing device preferences without changing the old UI storage', () => {
  const old = JSON.stringify({ club_id: 'eastbridge', player_id: 'eb09', language: 'zh-Hans', depth: 'analyst' })
  const store = storage({ 'counterpress.matchday.preferences.v1': old })
  const result = readPreferences(store, registry)
  assert.equal(result.status, 'migrated')
  assert.deepEqual(result.preferences.favorite_player_ids, ['eb09'])
  assert.deepEqual(result.preferences.favorite_club_ids, ['eastbridge'])
  assert.equal(result.preferences.language, 'zh-Hans')
  assert.equal(store.values.size, 1)
  assert.equal(savePreferences(store, result.preferences, registry), true)
  assert.deepEqual(readPreferences(store, registry).preferences, result.preferences)
  assert.equal(store.getItem('counterpress.matchday.preferences.v1'), old)
})

test('follow, reload and unfollow are persistent and do not mutate old preferences', () => {
  const start = defaults(), store = storage()
  const followed = toggleFavorite(start, 'player', 'rh08', registry)
  followed.focus_player_id = 'rh08'
  savePreferences(store, followed, registry)
  assert.deepEqual(start.favorite_player_ids, [])
  assert.deepEqual(readPreferences(store, registry).preferences.favorite_player_ids, ['rh08'])
  const unfollowed = toggleFavorite(followed, 'player', 'rh08', registry)
  assert.equal(unfollowed.focus_player_id, null)
  assert.deepEqual(followed.favorite_player_ids, ['rh08'])
})

test('unfollowing the primary club removes its theme choice', () => {
  const p = { ...defaults(), favorite_club_ids: ['redhaven'], primary_club_id: 'redhaven' }
  assert.equal(toggleFavorite(p, 'club', 'redhaven', registry).primary_club_id, null)
})

test('reset clears both preference versions so legacy favorites cannot resurrect', () => {
  const store = storage({ [preferenceKey]: JSON.stringify(defaults()), 'counterpress.matchday.preferences.v1': '{}' })
  assert.equal(clearPreferences(store), true)
  assert.equal(readPreferences(store).status, 'empty')
})

test('corrupt/future-version preferences are not overwritten on read', () => {
  for (const raw of ['{', JSON.stringify({ ...defaults(), version: 2 })]) {
    const store = storage({ [preferenceKey]: raw })
    assert.equal(readPreferences(store).status, 'invalid')
    assert.equal(store.getItem(preferenceKey), raw)
  }
})

test('storage denial is explicit, so UI never falsely promises saved favorites', () => {
  const denied = { getItem() { throw Error() }, setItem() { throw Error() }, removeItem() { throw Error() } }
  assert.equal(readPreferences(denied).status, 'unavailable')
  assert.equal(savePreferences(denied, defaults()), false)
  assert.equal(clearPreferences(denied), false)
})

test('unknown identities, duplicate and oversized lists, invalid paths are rejected', () => {
  assert.throws(() => validatePreferences({ ...defaults(), favorite_player_ids: ['unknown'] }, registry))
  assert.throws(() => validatePreferences({ ...defaults(), favorite_player_ids: ['rh08', 'rh08'] }))
  assert.throws(() => validatePreferences({ ...defaults(), favorite_player_ids: Array.from({ length: 13 }, (_, i) => `p${i}`) }))
  assert.throws(() => toggleFavorite(defaults(), 'player', '../.env'))
  assert.throws(() => validatePreferences({ ...defaults(), token: 'unwanted' }))
})

test('preference order is canonical and defaults are independent', () => {
  assert.deepEqual(validatePreferences({ ...defaults(), favorite_player_ids: ['rh08', 'eb09'] }).favorite_player_ids, ['eb09', 'rh08'])
  const a = defaults(); a.favorite_player_ids.push('rh08')
  assert.deepEqual(defaults().favorite_player_ids, [])
})

test('client sends private read-only POST without cookies or query-string preferences', async () => {
  let call
  const client = createFanClient(async (url, init) => { call = { url, init }; return response(init) })
  const result = await client.home(defaults(), { as_of: '2026-10-20T00:00:00Z' })
  assert.equal(call.url, '/api/fan/home')
  assert.equal(call.init.cache, 'no-store')
  assert.equal(call.init.credentials, 'omit')
  assert.equal(result.preferences.depth, 'casual')
  assert.match(result.request_id, /^fan-/)
})

test('older response is rejected even when transport ignores abort', async () => {
  const pending = []
  const client = createFanClient((url, init) => new Promise(resolve => pending.push({ init, resolve })))
  const first = client.home(defaults())
  const rejected = assert.rejects(first, StaleFanResponse)
  const second = client.player('rh08', { ...defaults(), favorite_player_ids: ['rh08'] })
  assert.equal(pending[0].init.signal.aborted, true)
  pending[1].resolve(response(pending[1].init))
  assert.deepEqual((await second).preferences.favorite_player_ids, ['rh08'])
  pending[0].resolve(response(pending[0].init))
  await rejected
})

test('seeking or unmounting invalidates in-flight playback answers', async () => {
  let complete
  const client = createFanClient((url, init) => new Promise(resolve => { complete = () => resolve(response(init)) }))
  const result = client.match('career-showcase-southbank-redhaven', { period: 2, elapsed_ms: 447225 }, defaults())
  client.cancel(); complete()
  await assert.rejects(result, StaleFanResponse)
})

test('echo mismatch and unsupported response versions never render', async () => {
  for (const changes of [{ request_id: 'other-tab' }, { version: 'fan-personalization-v2' },
    { preferences: { ...defaults(), language: 'zh-Hans' } }]) {
    const client = createFanClient(async (url, init) => response(init, changes))
    await assert.rejects(client.home(defaults()), StaleFanResponse)
  }
})

test('separate surfaces do not cancel each other', async () => {
  const fetcher = async (url, init) => response(init)
  const a = createFanClient(fetcher), b = createFanClient(fetcher)
  const [ra, rb] = await Promise.all([a.player('rh08', defaults()), b.player('eb09', defaults())])
  assert.notEqual(ra.request_id, rb.request_id)
})

test('server errors are sanitized rather than exposing response bodies', async () => {
  const client = createFanClient(async () => new Response('private provider diagnostic', { status: 503 }))
  await assert.rejects(client.home(defaults()), { message: 'Personalized view unavailable (503)' })
})
