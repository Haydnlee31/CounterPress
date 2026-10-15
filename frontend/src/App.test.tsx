import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { InsightCard } from './InsightCard'
import * as api from './api'
import { PlaybackScope } from './playbackScope'
import { defaultPreferences } from './types'
import type { Preferences, Snapshot, Window } from './types'

vi.mock('./api', () => ({ fetchSnapshot: vi.fn(), fetchScenarios: vi.fn() }))
const baseline: Window = { start: { period: 2, elapsed_ms: 180000 }, end: { period: 2, elapsed_ms: 480000 }, boundary: '(start,end]' }
const current: Window = { start: baseline.end, end: { period: 2, elapsed_ms: 780000 }, boundary: '(start,end]' }
const ids = ['p043', 'p053', 'p064', 'p075', 'p086']
function snapshot(at: number, scenario = 'increase', scopeId = 'default'): Snapshot {
  const ready = at === 780000 && scenario === 'increase'
  const refs = ids.map(event_id => ({ event_id, revision: 1 }))
  return {
    scenario_id: scenario, scope_id: scopeId, history_version: 89, replay_end: current.end, lifecycle: null,
    state: { match_id: `match-${scenario}`, at: { period: 2, elapsed_ms: at }, score: { eastbridge: 0, northport: 1 }, controlled_possession_team_id: 'eastbridge', source_delivery_cursor: ready ? 89 : 1, applied_events: ready ? refs : [] },
    metrics: [{ team_id: 'eastbridge', pass_attempts: 24, pass_completions: 17, attempted_pass_distance_m: 322, completed_pass_distance_m: 240, high_recoveries: ready ? refs : [] }],
    windows: [baseline, current], comparison_status: ready ? 'ready' : at === 780000 ? 'no_increase' : 'collecting',
    insight: ready ? { insight_id: 'test-insight', revision: 1, evidence_id: 'test-evidence', evidence_version: 1, claim_type: 'fact', template: 'high_recovery_increase_v1', title: 'High recoveries increased', explanation: 'Eastbridge recorded 4 attacking-third recoveries, up from 1.', facts: { subject_team_id: 'eastbridge', baseline_count: 1, current_count: 4, baseline_window: baseline, current_window: current }, eligible_at: current.end } : null,
    evidence: ready ? {
      packet: { evidence_id: 'test-evidence', evidence_version: 1, match_id: 'match-increase', subject_team_id: 'eastbridge', metric: 'high_recovery_count', rule_version: 'high-recovery-v1', cutoff: current.end, baseline: { window: baseline, value: 1, source_events: refs.slice(0, 1) }, current: { window: current, value: 4, source_events: refs.slice(1) } },
      metric_definition: 'Open-play controlled possession at x ≥ 70 m.', coordinate_system: 'actor_team_attacks_positive_x',
      records: ids.map((event_id, index) => ({ schema_version: '1.0', match_id: 'match-increase', event_id, revision: 1, source_delivery_sequence: index + 1, occurrence_order: index + 1, occurred_at: { period: 2, elapsed_ms: [480000, 540000, 615000, 690000, 765000][index] }, available_at: { period: 2, elapsed_ms: [480000, 540000, 615000, 690000, 765000][index] }, actor: { team_id: 'eastbridge', player_id: 'eb08' }, position: { x: [70, 72, 77, 80, 74][index], y: 38 }, action: { kind: 'recovery', control: 'established', origin: 'open_play', from_team_id: 'northport' } })),
    } : null,
  }
}

beforeEach(() => {
  vi.mocked(api.fetchScenarios).mockResolvedValue([{ scenario_id: 'increase', label: 'Recovery increase', start: baseline.start, end: current.end }, { scenario_id: 'control', label: 'No-increase control', start: baseline.start, end: current.end }])
  vi.mocked(api.fetchSnapshot).mockImplementation(async (scenario, at, _signal, scopeId) => snapshot(at, scenario, scopeId))
})
afterEach(() => { cleanup(); vi.clearAllMocks(); vi.useRealTimers() })

describe('the local replay screen', () => {
  it('opens the exact evidence records and hides them on reset, then replays again', async () => {
    const user = userEvent.setup()
    render(<App/>)
    await user.click(screen.getByRole('button', { name: /Go to comparison/ }))
    await screen.findByRole('heading', { name: 'High recoveries increased' })
    expect(screen.getByLabelText('1 to 4 high recoveries')).toBeTruthy()
    await user.click(screen.getByRole('button', { name: /Show evidence/ }))
    expect(screen.getAllByRole('row')).toHaveLength(6)
    await user.click(screen.getByRole('button', { name: 'p053' }))
    expect(screen.getByRole('heading', { name: 'Source record · p053' })).toBeTruthy()
    expect(screen.getByText(/"source_delivery_sequence": 2/)).toBeTruthy()
    await user.click(screen.getByRole('button', { name: 'Reset replay' }))
    expect(screen.queryByRole('heading', { name: 'High recoveries increased' })).toBeNull()
    expect(screen.queryByRole('table')).toBeNull()
    await user.click(screen.getByRole('button', { name: /Go to comparison/ }))
    await screen.findByRole('heading', { name: 'High recoveries increased' })
  })

  it('shows no increase card for the control and no future evidence after a seek', async () => {
    const user = userEvent.setup()
    render(<App/>)
    await screen.findByText(/Facts through 48:00/)
    await user.selectOptions(screen.getByLabelText('Replay scenario'), 'control')
    await user.click(screen.getByRole('button', { name: /Go to comparison/ }))
    await screen.findByText('No increase this time.')
    expect(screen.queryByRole('button', { name: /Show evidence/ })).toBeNull()
    await user.selectOptions(screen.getByLabelText('Replay scenario'), 'increase')
    await user.click(screen.getByRole('button', { name: /Go to comparison/ }))
    await screen.findByRole('heading', { name: 'High recoveries increased' })
    fireEvent.change(screen.getByRole('slider', { name: 'Match time' }), { target: { value: '540000' } })
    expect(screen.queryByRole('heading', { name: 'High recoveries increased' })).toBeNull()
    expect(screen.queryByRole('button', { name: /p064/ })).toBeNull()
    await waitFor(() => expect(api.fetchSnapshot).toHaveBeenLastCalledWith('increase', 540000, expect.any(AbortSignal), expect.any(String), defaultPreferences))
  })

  it('ignores a delayed end-of-replay response after reset', async () => {
    let release!: (value: Snapshot) => void
    vi.mocked(api.fetchSnapshot).mockImplementation(async (scenario, at, _signal, scopeId) => at === 780000 ? new Promise(resolve => { release = resolve }) : snapshot(at, scenario, scopeId))
    const user = userEvent.setup()
    render(<App/>)
    await user.click(screen.getByRole('button', { name: /Go to comparison/ }))
    await waitFor(() => expect(release).toBeTypeOf('function'))
    await user.click(screen.getByRole('button', { name: 'Reset replay' }))
    await act(async () => release(snapshot(780000)))
    expect(screen.queryByRole('heading', { name: 'High recoveries increased' })).toBeNull()
    expect(screen.getByRole('slider', { name: 'Match time' }).getAttribute('aria-valuetext')).toBe('48:00')
  })

  it('shows a usable error and retries without inventing a score', async () => {
    vi.mocked(api.fetchSnapshot).mockRejectedValueOnce(new Error('Backend unavailable.'))
    const user = userEvent.setup()
    render(<App/>)
    expect(await screen.findByRole('alert')).toBeTruthy()
    await user.click(screen.getByRole('button', { name: 'Retry' }))
    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull())
    await waitFor(() => expect(screen.getByText(/Facts through 48:00/)).toBeTruthy())
  })

  it('plays, changes speed, pauses and resets the visible clock', async () => {
    const { container } = render(<App/>)
    await screen.findByText(/Facts through 48:00/)
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval', 'performance'] })
    fireEvent.click(screen.getByRole('button', { name: 'Play replay' }))
    await act(async () => { vi.advanceTimersByTime(1000) })
    expect(container.querySelector('time')?.textContent).toBe('48:30')
    fireEvent.change(screen.getByLabelText('Playback speed'), { target: { value: '60' } })
    await act(async () => { vi.advanceTimersByTime(1000) })
    expect(container.querySelector('time')?.textContent).toBe('49:30')
    fireEvent.click(screen.getByRole('button', { name: 'Pause replay' }))
    await act(async () => { vi.advanceTimersByTime(1000) })
    expect(container.querySelector('time')?.textContent).toBe('49:30')
    fireEvent.click(screen.getByRole('button', { name: 'Reset replay' }))
    await act(async () => {})
    expect(container.querySelector('time')?.textContent).toBe('48:00')
  })
})

function publication(revision: number, operation: 'create' | 'update' | 'withdraw', scopeId: string): Snapshot {
  const value = snapshot(780000, 'increase', scopeId)
  const evidence = { ...value.evidence!, packet: { ...value.evidence!.packet, evidence_version: revision } }
  const insight = operation === 'withdraw' ? null : { ...value.insight!, revision, evidence_version: revision }
  return { ...value, history_version: 88 + revision, insight, evidence: insight ? evidence : null,
    comparison_status: insight ? 'ready' : 'no_increase',
    lifecycle: { insight_id: 'test-insight', revision, operation, available_at: current.end,
      insight, evidence, invalidates: revision > 1 ? [{ evidence_id: 'test-evidence', evidence_version: revision - 1 }] : [] } }
}

describe('correction delivery to a paused viewer', () => {
  it('retains a tombstone across duplicate/out-of-order messages, but accepts a newer creation', () => {
    const scope = new PlaybackScope('viewer-a')
    expect(scope.accept(publication(1, 'create', 'viewer-a'))).toBe(true)
    expect(scope.accept(publication(3, 'withdraw', 'viewer-a'))).toBe(true)
    expect(scope.accept(publication(3, 'withdraw', 'viewer-a'))).toBe(true)
    expect(scope.accept({ ...publication(2, 'update', 'viewer-a'), history_version: 100 })).toBe(false)
    expect(scope.accept(publication(4, 'create', 'old-scope'))).toBe(false)
    expect(scope.accept(snapshot(180000, 'increase', 'viewer-a'))).toBe(false)
    expect(scope.accept(publication(4, 'create', 'viewer-a'))).toBe(true)
    expect(new PlaybackScope('viewer-b').accept(publication(1, 'create', 'viewer-b'))).toBe(true)
  })
  it('withdraws a card on polling and rejects a later stale create', async () => {
    let revision = 1
    vi.mocked(api.fetchSnapshot).mockImplementation(async (_scenario, at, _signal, scopeId) =>
      at === 780000 ? publication(revision, revision === 3 ? 'withdraw' : 'create', scopeId) : snapshot(at, 'increase', scopeId))
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
    render(<App/>)
    await act(async () => {})
    fireEvent.click(screen.getByRole('button', { name: /Go to comparison/ }))
    await act(async () => {})
    expect(screen.getByRole('heading', { name: 'High recoveries increased' })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /Show evidence/ }))
    revision = 3
    await act(async () => { vi.advanceTimersByTime(2000) })
    expect(screen.getByRole('heading', { name: 'Insight withdrawn.' })).toBeTruthy()
    expect(screen.queryByRole('table')).toBeNull()
    revision = 1
    await act(async () => { vi.advanceTimersByTime(2000) })
    expect(screen.queryByRole('heading', { name: 'High recoveries increased' })).toBeNull()
    expect(screen.getByRole('heading', { name: 'Insight withdrawn.' })).toBeTruthy()
    // An intentional seek creates a new scope and may display historical revision one.
    fireEvent.click(screen.getByRole('button', { name: 'Reset replay' }))
    await act(async () => {})
    fireEvent.click(screen.getByRole('button', { name: /Go to comparison/ }))
    await act(async () => {})
    expect(screen.getByRole('heading', { name: 'High recoveries increased' })).toBeTruthy()
  })

  it('discovers a longer correction horizon without moving the viewer automatically', async () => {
    vi.mocked(api.fetchSnapshot).mockImplementation(async (scenario, at, _signal, scopeId) =>
      ({ ...snapshot(at, scenario, scopeId), replay_end: { period: 2, elapsed_ms: 795000 } }))
    const user = userEvent.setup()
    render(<App/>)
    await screen.findByRole('button', { name: 'View latest corrections · 58:15' })
    expect(screen.getByRole('slider', { name: 'Match time' }).getAttribute('aria-valuetext')).toBe('48:00')
    await user.click(screen.getByRole('button', { name: 'View latest corrections · 58:15' }))
    await waitFor(() => expect(api.fetchSnapshot).toHaveBeenLastCalledWith('increase', 795000, expect.any(AbortSignal), expect.any(String), defaultPreferences))
    expect(screen.getByRole('slider', { name: 'Match time' }).getAttribute('max')).toBe('795000')
  })
})

it('uses only matching unexpired adaptation text and restores the factual fallback on expiry', async () => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'Date'] })
  const insight = snapshot(780000).insight!
  const adaptation = { attempt_id: 'adapt-test', evidence_id: insight.evidence_id, evidence_version: 1,
    text: 'Approved short comparison.', expires_at_unix_ms: Date.now() + 1000 }
  const { rerender } = render(<InsightCard insight={insight} adaptation={adaptation} open={false} onToggle={() => {}}/>)
  expect(screen.getByText(adaptation.text)).toBeTruthy()
  expect(screen.getByLabelText('1 to 4 high recoveries')).toBeTruthy()
  await act(async () => { vi.advanceTimersByTime(1000) })
  expect(screen.queryByText(adaptation.text)).toBeNull()
  expect(screen.getByText(insight.explanation)).toBeTruthy()
  rerender(<InsightCard insight={insight} adaptation={{ ...adaptation, evidence_version: 2, expires_at_unix_ms: Date.now() + 1000 }} open={false} onToggle={() => {}}/>)
  expect(screen.queryByText(adaptation.text)).toBeNull()
  expect(screen.getByText(insight.explanation)).toBeTruthy()
})

function audienceSnapshot(at: number, scenario: string, scope: string, p: Preferences = defaultPreferences): Snapshot {
  const data = snapshot(at, scenario, scope)
  data.teams = [{ team_id: 'eastbridge', name: 'Eastbridge', player_ids: ['eb08', 'eb09', 'eb04'] }, { team_id: 'northport', name: 'Northport', player_ids: ['np08'] }]
  if (data.evidence) data.evidence.records[2].actor.player_id = 'eb09'
  const ready = !!data.insight && p.player_id !== 'eb04' && p.card_budget === 1
  data.audience = {
    preferences: p, state: !data.insight ? 'collecting' : p.player_id === 'eb04' ? 'no_contribution' : p.card_budget === 0 ? 'budget_hidden' : 'ready',
    message: 'Preference review', priority: 10, supporting_event_count: 5, selected_event_count: p.player_id === 'eb09' ? 1 : 5,
    highlighted_events: ready ? (p.player_id === 'eb09' ? [{ event_id: 'p064', revision: 1 }] : data.evidence!.packet.baseline.source_events.concat(data.evidence!.packet.current.source_events)) : [],
    sequence: ready && p.depth === 'analyst' ? data.evidence!.records : [],
    variant: ready ? { insight_id: 'test-insight', revision: 1, language: p.language, depth: p.depth, club_id: p.club_id, player_id: p.player_id,
      title: p.language === 'zh-Hans' ? '前场夺回球权次数增加' : 'High recoveries increased', subject_name: 'Eastbridge',
      explanation: p.language === 'zh-Hans' ? 'Eastbridge 在 53:00–58:00 前场夺回球权 4 次，前一时段 48:00–53:00 为 1 次。' : 'Eastbridge: 4 high recoveries in 53:00–58:00, compared with 1 in 48:00–53:00.',
      qualification: p.language === 'zh-Hans' ? '不能据此判断压迫是否有效。' : 'It does not establish whether pressure was effective.',
    } : null,
  }
  return data
}

describe('audience views', () => {
  beforeEach(() => {
    vi.mocked(api.fetchSnapshot).mockImplementation(async (scenario, at, _signal, scope, p) => audienceSnapshot(at, scenario, scope, p))
  })
  it('switches depth and language without changing the count graphic', async () => {
    const user = userEvent.setup()
    render(<App/>)
    await user.click(screen.getByRole('button', { name: /Go to comparison/ }))
    await screen.findByRole('region', { name: 'Event sequence' })
    await user.selectOptions(screen.getByLabelText('Explanation depth'), 'casual')
    await screen.findByRole('heading', { name: 'High recoveries increased' })
    expect(screen.queryByRole('region', { name: 'Event sequence' })).toBeNull()
    expect(screen.queryByRole('heading', { name: 'Where control was recovered' })).toBeNull()
    expect(screen.getByLabelText('1 to 4 high recoveries')).toBeTruthy()
    await user.selectOptions(screen.getByLabelText('Language'), 'zh-Hans')
    await screen.findByRole('heading', { name: '前场夺回球权次数增加' })
    expect(screen.getByLabelText('1 to 4 high recoveries')).toBeTruthy()
    expect(screen.getByText(/不能据此判断压迫是否有效/)).toBeTruthy()
  })
  it('selects real player evidence and shows honest empty and budget states', async () => {
    const user = userEvent.setup()
    render(<App/>)
    await user.click(screen.getByRole('button', { name: /Go to comparison/ }))
    await screen.findByRole('heading', { name: 'High recoveries increased' })
    await user.selectOptions(screen.getByLabelText('Player contribution'), 'eb09')
    await screen.findByText(/Selected contributions: 1 \/ 5/)
    await user.click(screen.getByRole('button', { name: /Show evidence/ }))
    expect(screen.getAllByRole('row')).toHaveLength(2)
    expect(screen.getByRole('button', { name: 'p064' })).toBeTruthy()
    expect(screen.getByLabelText('1 to 4 high recoveries')).toBeTruthy()
    await user.selectOptions(screen.getByLabelText('Player contribution'), 'eb04')
    await screen.findByRole('heading', { name: 'No qualifying contribution.' })
    expect(screen.queryByRole('table')).toBeNull()
    await user.selectOptions(screen.getByLabelText('Player contribution'), '')
    await user.selectOptions(screen.getByLabelText('Card budget'), '0')
    await screen.findByRole('heading', { name: 'Cards hidden.' })
    expect(screen.queryByLabelText('1 to 4 high recoveries')).toBeNull()
  })
  it('isolates viewer preferences and discards a delayed response from the previous viewer', async () => {
    const user = userEvent.setup()
    render(<App/>)
    await user.click(screen.getByRole('button', { name: /Go to comparison/ }))
    await screen.findByRole('heading', { name: 'High recoveries increased' })
    let release!: () => void
    vi.mocked(api.fetchSnapshot).mockImplementation(async (scenario, at, _signal, scope, p = defaultPreferences) => {
      if (p.language === 'zh-Hans') return new Promise(resolve => { release = () => resolve(audienceSnapshot(at, scenario, scope, p)) })
      return audienceSnapshot(at, scenario, scope, p)
    })
    await user.selectOptions(screen.getByLabelText('Language'), 'zh-Hans')
    await waitFor(() => expect(release).toBeTypeOf('function'))
    await user.selectOptions(screen.getByLabelText('Local viewer'), 'two')
    await screen.findByRole('heading', { name: 'High recoveries increased' })
    await act(async () => release())
    expect(screen.queryByRole('heading', { name: '前场夺回球权次数增加' })).toBeNull()
    expect((screen.getByLabelText('Language') as HTMLSelectElement).value).toBe('en')
    expect((screen.getByLabelText('Explanation depth') as HTMLSelectElement).value).toBe('casual')
    vi.mocked(api.fetchSnapshot).mockImplementation(async (scenario, at, _signal, scope, p) => audienceSnapshot(at, scenario, scope, p))
    await user.selectOptions(screen.getByLabelText('Local viewer'), 'one')
    await screen.findByRole('heading', { name: '前场夺回球权次数增加' })
    expect((screen.getByLabelText('Explanation depth') as HTMLSelectElement).value).toBe('analyst')
  })
})
