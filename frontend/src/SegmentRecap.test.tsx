import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import App from './App'
import * as api from './api'
import { SegmentRecap, evidenceUrl } from './SegmentRecap'
import { validateRecap } from './recapValidation'
import { defaultPreferences } from './types'
import type { Preferences, Snapshot, Window } from './types'

vi.mock('./api', () => ({ fetchSnapshot: vi.fn(), fetchScenarios: vi.fn() }))
afterEach(() => { cleanup(); vi.clearAllMocks(); vi.useRealTimers() })
const baseline: Window = { start: { period: 2, elapsed_ms: 180000 }, end: { period: 2, elapsed_ms: 480000 }, boundary: '(start,end]' }
const current: Window = { start: baseline.end, end: { period: 2, elapsed_ms: 780000 }, boundary: '(start,end]' }

function snapshot(at = 780000, scope = 'one', prefs: Preferences = defaultPreferences, revision = 1, withdrawn = false): Snapshot {
  const cutoff = { period: 2 as const, elapsed_ms: at }
  const ready = at >= 780000 && !withdrawn && prefs.card_budget > 0
  const citation = { kind: 'pressure' as const, insight_id: 'pressure-one', revision, evidence_id: 'ev-one', available_at: current.end }
  const narrative = { insight_id: 'pressure-one', revision, language: prefs.language, depth: prefs.depth, club_id: prefs.club_id, player_id: prefs.player_id,
    title: prefs.language === 'zh-Hans' ? '压迫暴露比例上升' : 'Pressure exposure increased', explanation: 'Eastbridge: (48:00,53:00] 3/6 → (53:00,58:00] 6/6.', qualification: 'A duel proxy, not tactical causality.', subject_name: 'Eastbridge' }
  // Minimal transport fixture: no main card, to isolate recap scope handling.
  return { scenario_id: 'pressure-increase', scope_id: scope, history_version: revision, replay_end: current.end,
    state: { match_id: 'match-one', at: cutoff, score: { eastbridge: 0, northport: 1 }, controlled_possession_team_id: 'eastbridge', source_delivery_cursor: 1, applied_events: [] },
    windows: [baseline, current], metrics: [], comparison_status: at < 780000 ? 'collecting' : 'no_increase', insight: null, evidence: null, lifecycle: null,
    audience: { preferences: prefs, state: 'no_increase', message: '', variant: null, priority: 0, highlighted_events: [], sequence: [], supporting_event_count: 0, selected_event_count: 0 },
    pressure_lifecycle: at >= 780000 ? [{ ...citation, operation: withdrawn ? 'withdraw' : 'create' } as unknown as NonNullable<Snapshot['pressure_lifecycle']>[number]] : [],
    recap: { match_id: 'match-one', cutoff, windows: [baseline, current], preferences: prefs, state: prefs.card_budget === 0 ? 'budget_hidden' : at < 780000 ? 'collecting' : withdrawn ? 'no_eligible' : 'ready', statements: ready ? [{ citation, narrative }] : [], omitted_count: 0 } }
}

test('recap is collapsed, uses exact evidence links, updates citations and localizes', () => {
  const initial = snapshot().recap!
  const { container, rerender } = render(<SegmentRecap recap={initial} scenario="pressure-increase" />)
  expect(container.querySelector('details')!.open).toBe(false)
  fireEvent.click(screen.getByText('Catch up on this segment'))
  expect(container.querySelector('details')!.open).toBe(true)
  expect(screen.getByText(/3\/6 →.*6\/6/)).toBeTruthy()
  const link = screen.getByRole('link', { name: /Open cited evidence/ })
  expect(link.getAttribute('href')).toBe('/api/scenarios/pressure-increase/pressure/pressure-one/evidence/1?at_ms=780000')
  expect(link.getAttribute('target')).toBe('_blank')
  rerender(<SegmentRecap recap={snapshot(780000, 'one', { ...defaultPreferences, language: 'zh-Hans' }, 2).recap!} scenario="pressure-increase" />)
  expect(screen.getByRole('heading', { name: '压迫暴露比例上升' })).toBeTruthy()
  expect(screen.getByRole('link', { name: /修订 2/ }).getAttribute('href')).toContain('/evidence/2?')
  for (const [kind, path] of [['recovery', '/evidence/1'], ['contribution', '/contributions/pressure-one/evidence/1']] as const) {
    expect(evidenceUrl('increase', { ...initial.statements[0].citation, kind }, 780000)).toBe(`/api/scenarios/increase${path}?at_ms=780000`)
  }
  rerender(<SegmentRecap recap={snapshot(780000, 'one', defaultPreferences, 3, true).recap!} scenario="pressure-increase" />)
  expect(screen.queryByRole('link')).toBeNull()
  expect(screen.getByText(/does not mean nothing happened/)).toBeTruthy()
  rerender(<SegmentRecap recap={snapshot(780000, 'one', { ...defaultPreferences, card_budget: 0 }).recap!} scenario="pressure-increase" />)
  expect(container.innerHTML).toBe('')
})

test('transport rejects stale, future, wrong-match, withdrawn, duplicate and wrong-perspective recap citations', () => {
  expect(() => validateRecap(snapshot(), defaultPreferences)).not.toThrow()
  const mutations: ((s: Snapshot) => void)[] = [
    s => { s.recap!.match_id = 'another-match' },
    s => { s.recap!.cutoff = { period: 2, elapsed_ms: 780001 } },
    s => { s.recap!.statements[0].citation.revision = 2 },
    s => { s.recap!.statements[0].citation.evidence_id = 'another-evidence' },
    s => { s.recap!.statements[0].citation.available_at = { period: 2, elapsed_ms: 785000 } },
    s => { s.recap!.statements[0].narrative.language = 'zh-Hans' },
    s => { s.recap!.preferences = { ...defaultPreferences, player_id: 'eb09' } },
    s => { s.pressure_lifecycle![0].operation = 'withdraw' },
    s => { s.pressure_lifecycle = [] },
    s => { s.recap!.statements.push(s.recap!.statements[0]) },
    s => { s.recap!.state = 'no_eligible' },
  ]
  for (const mutate of mutations) { const s = structuredClone(snapshot()); mutate(s); expect(() => validateRecap(s, defaultPreferences)).toThrow(/Recap/) }
})

test('screen removes withdrawn recap, ignores stale delivery, and clears it on rewind or viewer change', async () => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  let revision = 1, withdrawn = false
  vi.mocked(api.fetchScenarios).mockResolvedValue([{ scenario_id: 'pressure-increase', label: 'Pressure shift', start: baseline.start, end: current.end }])
  vi.mocked(api.fetchSnapshot).mockImplementation(async (scenario, at, _signal, scope, prefs = defaultPreferences) => ({ ...snapshot(at, scope, prefs, revision, withdrawn), scenario_id: scenario }))
  render(<App />); await act(async () => {})
  fireEvent.click(screen.getByRole('button', { name: /Go to comparison/ })); await act(async () => {})
  fireEvent.click(screen.getByText('Catch up on this segment'))
  expect(screen.getByRole('link', { name: /Open cited evidence/ })).toBeTruthy()
  revision = 2; withdrawn = true
  await act(async () => { vi.advanceTimersByTime(2000) })
  expect(screen.queryByRole('link', { name: /Open cited evidence/ })).toBeNull()
  revision = 1; withdrawn = false
  await act(async () => { vi.advanceTimersByTime(2000) })
  expect(screen.queryByRole('link', { name: /Open cited evidence/ })).toBeNull()
  revision = 3
  await act(async () => { vi.advanceTimersByTime(2000) })
  expect(screen.getByRole('link', { name: /revision 3/ })).toBeTruthy()
  fireEvent.change(screen.getByLabelText('Local viewer'), { target: { value: 'two' } }); await act(async () => {})
  expect(screen.getByText('Catch up on this segment').closest('details')!.open).toBe(false) // new scope starts collapsed
  fireEvent.click(screen.getByRole('button', { name: 'Reset replay' })); await act(async () => {})
  fireEvent.click(screen.getByText('Catch up on this segment'))
  expect(screen.getByText(/Waiting for both comparison windows/)).toBeTruthy()
  expect(screen.queryByRole('link', { name: /Open cited evidence/ })).toBeNull()
})
