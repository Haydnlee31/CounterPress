import { afterEach, expect, test, vi } from 'vitest'
import { fetchSnapshot } from './api'
import { defaultPreferences } from './types'

afterEach(() => vi.unstubAllGlobals())

const base = { scenario_id: 'increase', scope_id: 'viewer-one', state: { at: { elapsed_ms: 780000 } },
  insight: { insight_id: 'test-insight', revision: 1 }, audience: { preferences: defaultPreferences, variant: null } }

test('sends explicit preferences without viewer-global state and disables HTTP caching', async () => {
  const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => base })
  vi.stubGlobal('fetch', fetch)
  await fetchSnapshot('increase', 780000, new AbortController().signal, 'viewer-one', defaultPreferences)
  const [url, options] = fetch.mock.calls[0]
  expect(url).toContain('scope_id=viewer-one')
  expect(url).toContain('language=en&depth=analyst&metric_focus=balanced&card_budget=1')
  expect(options.cache).toBe('no-store')
})

test('rejects another language or perspective even at the same match cutoff', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => base }))
  await expect(fetchSnapshot('increase', 780000, new AbortController().signal, 'viewer-one', { ...defaultPreferences, language: 'zh-Hans' })).rejects.toThrow('viewing preferences')
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ...base, audience: { ...base.audience,
    variant: { insight_id: 'test-insight', revision: 1, language: 'en', depth: 'analyst', club_id: null, player_id: 'eb09' },
  } }) }))
  await expect(fetchSnapshot('increase', 780000, new AbortController().signal, 'viewer-one')).rejects.toThrow('perspective')
})

test('rejects pressure wording with stale revisions, future availability or mismatched preferences', async () => {
  const publication={insight_id:'pressure-one',revision:2,operation:'update',decision:{status:'eligible'},available_at:{elapsed_ms:780000}}
  const variant={insight_id:'pressure-one',revision:2,language:'en',depth:'analyst',club_id:null,player_id:null}
  const pressure={preferences:defaultPreferences,state:'ready',publication,variant}
  for(const changed of [
    {...pressure,variant:{...variant,revision:1}},
    {...pressure,publication:{...publication,available_at:{elapsed_ms:785000}}},
    {...pressure,preferences:{...defaultPreferences,language:'zh-Hans'}},
  ]){
    vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:true,json:async()=>({...base,pressure:changed,pressure_lifecycle:[publication],selected_kind:'pressure'})}))
    await expect(fetchSnapshot('increase',780000,new AbortController().signal,'viewer-one')).rejects.toThrow(/Pressure/)
  }
})
