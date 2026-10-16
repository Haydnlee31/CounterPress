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

test('rejects player narratives with stale identity, another player, future evidence or missing lifecycle', async () => {
  const preferences={...defaultPreferences,player_id:'eb04'}
  const publication={insight_id:'player-one',revision:2,operation:'update',evidence:{subject_player_id:'eb04',decision:{status:'eligible'}},available_at:{period:2,elapsed_ms:780000}}
  const variant={insight_id:'player-one',revision:2,language:'en',depth:'analyst',club_id:null,player_id:'eb04'}
  const contribution={preferences,state:'ready',publication,variant}
  const response={...base,state:{at:{period:2,elapsed_ms:780000}},audience:{...base.audience,preferences},contribution,contribution_lifecycle:[publication],selected_kind:'contribution'}
  for(const changed of [
    {...response,contribution:{...contribution,variant:{...variant,revision:1}}},
    {...response,contribution:{...contribution,publication:{...publication,evidence:{...publication.evidence,subject_player_id:'eb08'}}}},
    {...response,contribution:{...contribution,publication:{...publication,available_at:{period:2,elapsed_ms:785000}}}},
    {...response,contribution_lifecycle:[]},
    {...response,contribution_lifecycle:[{...publication,operation:'withdraw'}]},
    {...response,contribution:{...contribution,preferences:{...preferences,language:'zh-Hans'}}},
  ]) {
    vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:true,json:async()=>changed}))
    await expect(fetchSnapshot('increase',780000,new AbortController().signal,'viewer-one',preferences)).rejects.toThrow(/Player/)
  }
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:true,json:async()=>response}))
  await expect(fetchSnapshot('increase',780000,new AbortController().signal,'viewer-one',preferences)).resolves.toEqual(response)
})
