import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import App from '../App'
import * as api from '../api'
import type { Preferences, Snapshot, Window } from '../types'
import { fanDefaults, preferenceKey, readPreferences } from './preferences'
import { storiesFor } from './stories'

vi.mock('../api', () => ({ fetchSnapshot: vi.fn(), fetchScenarios: vi.fn() }))
vi.mock('../revisions', () => ({ subscribeRevisions: vi.fn(() => () => {}) }))
const windows: [Window, Window] = [
  {
    start: { period: 2, elapsed_ms: 180000 },
    end: { period: 2, elapsed_ms: 480000 },
    boundary: '(start,end]',
  },
  {
    start: { period: 2, elapsed_ms: 480000 },
    end: { period: 2, elapsed_ms: 780000 },
    boundary: '(start,end]',
  },
]
function fixture(
  scenario: string,
  at: number,
  scope: string,
  p: Preferences = fanDefaults,
  revision = 1,
  withdrawn = false,
): Snapshot {
  const ready = at >= 780000 && !withdrawn && p.player_id !== 'eb04'
  const refs = ['a', 'b', 'c', 'd', 'e'].map((event_id) => ({
    event_id,
    revision: 1,
  }))
  const citation = {
    kind: 'recovery' as const,
    insight_id: 'story',
    revision,
    evidence_id: 'proof',
    available_at: windows[1].end,
  }
  const evidence = {
    packet: {
      evidence_id: 'proof',
      evidence_version: revision,
      match_id: 'synthetic',
      subject_team_id: 'eastbridge',
      metric: 'high_recovery_count',
      rule_version: 'test-v1',
      cutoff: windows[1].end,
      baseline: {
        window: windows[0],
        value: 1,
        source_events: refs.slice(0, 1),
      },
      current: {
        window: windows[1],
        value: revision === 2 ? 3 : 4,
        source_events: refs.slice(1),
      },
    },
    metric_definition: 'Recorded recovery',
    coordinate_system: 'actor_team_attacks_positive_x',
    records: refs.map((ref, i) => ({
      ...ref,
      schema_version: '1.0',
      match_id: 'synthetic',
      source_delivery_sequence: i + 1,
      occurrence_order: i + 1,
      occurred_at: {
        period: 2 as const,
        elapsed_ms: [480000, 540000, 615000, 690000, 765000][i],
      },
      available_at: windows[1].end,
      actor: { team_id: 'eastbridge', player_id: i === 1 ? 'eb09' : 'eb08' },
      position: { x: 75, y: 34 },
      action: { kind: 'recovery' },
    })),
  }
  const insight = {
    insight_id: 'story',
    revision,
    evidence_id: 'proof',
    evidence_version: revision,
    claim_type: 'fact' as const,
    template: 'high_recovery_increase_v1' as const,
    title: 'Recovery increase',
    explanation: 'Four compared with one.',
    facts: {
      subject_team_id: 'eastbridge',
      baseline_count: 1,
      current_count: 4,
      baseline_window: windows[0],
      current_window: windows[1],
    },
    eligible_at: windows[1].end,
  }
  const narrative = {
    insight_id: 'story',
    revision,
    ...p,
    title: 'Recovery increase',
    explanation: 'Four compared with one.',
    qualification:
      p.language === 'en'
        ? 'Recorded counts do not establish tactical cause.'
        : '记录次数不能证明战术因果关系。',
    subject_name: 'Eastbridge',
  }
  return {
    scenario_id: scenario,
    scope_id: scope,
    history_version: 90 + revision,
    replay_end: { period: 2, elapsed_ms: 795000 },
    state: {
      match_id: 'synthetic',
      at: { period: 2, elapsed_ms: at },
      score: { eastbridge: 0, northport: 1 },
      controlled_possession_team_id: 'eastbridge',
      source_delivery_cursor: 90,
      applied_events: refs,
    },
    teams: [
      {
        team_id: 'eastbridge',
        name: 'Eastbridge',
        player_ids: ['eb04', 'eb08', 'eb09'],
      },
      { team_id: 'northport', name: 'Northport', player_ids: ['np08'] },
    ],
    pitch_events: evidence.records,
    metrics: [],
    windows,
    comparison_status: ready
      ? 'ready'
      : at < 780000
        ? 'collecting'
        : 'no_increase',
    insight: ready ? insight : null,
    evidence: ready ? evidence : null,
    lifecycle:
      at >= 780000
        ? {
            ...citation,
            operation: withdrawn
              ? 'withdraw'
              : revision > 1
                ? 'update'
                : 'create',
            insight: ready ? insight : null,
            evidence,
            invalidates: [],
          }
        : null,
    audience: {
      preferences: p,
      state: ready ? 'ready' : 'no_increase',
      message: '',
      variant: ready ? narrative : null,
      priority: 1,
      supporting_event_count: 5,
      selected_event_count: 5,
      highlighted_events: refs,
      sequence: [],
    },
    recap: {
      match_id: 'synthetic',
      cutoff: { period: 2, elapsed_ms: at },
      windows,
      preferences: p,
      state: ready ? 'ready' : 'no_eligible',
      statements: ready ? [{ citation, narrative }] : [],
      omitted_count: 0,
    },
  }
}
beforeEach(() => {
  const entries = new Map<string, string>()
  Object.defineProperty(window, 'localStorage', {
    configurable: true,
    value: {
      getItem: (key: string) => entries.get(key) ?? null,
      setItem: (key: string, value: string) => {
        entries.set(key, value)
      },
      removeItem: (key: string) => {
        entries.delete(key)
      },
      clear: () => entries.clear(),
    },
  })
  window.history.replaceState(null, '', '/?story=increase')
  vi.mocked(api.fetchScenarios).mockResolvedValue([
    {
      scenario_id: 'increase',
      label: 'Recovery',
      start: windows[0].start,
      end: windows[1].end,
    },
  ])
  vi.mocked(api.fetchSnapshot).mockImplementation(
    async (scenario, at, _signal, scope, p) => fixture(scenario, at, scope, p),
  )
})
afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  vi.useRealTimers()
})

test('first visit has a full pitch, footer-only disclosure and readable moments without JSON', async () => {
  const user = userEvent.setup()
  render(<App />)
  await screen.findByLabelText('1 to 4')
  expect(api.fetchSnapshot).toHaveBeenCalledWith(
    'increase',
    780000,
    expect.any(AbortSignal),
    expect.any(String),
    fanDefaults,
  )
  expect(screen.getByText(/This showcase uses fictional/).closest('footer')).toBeTruthy()
  expect(document.querySelectorAll('.fan-pitch-player')).toHaveLength(22)
  expect(document.querySelectorAll('pre')).toHaveLength(0)
  expect(screen.queryByText('Recorded counts do not establish tactical cause.')).toBeNull()
  expect(screen.queryByLabelText('Local viewer')).toBeNull()
  expect(screen.queryByRole('slider',{name:'Match time'})).toBeNull()
  expect(screen.getByRole('slider',{name:'Replay position'})).toBeTruthy()
  await user.click(screen.getByRole('button', { name: /Catch me up/ }))
  expect(
    screen.getByRole('region', { name: 'The story in a few moments' }),
  ).toBeTruthy()
  await user.click(screen.getByRole('button', { name: 'Show the moments' }))
  const moments = screen.getByRole('region', { name: 'See it for yourself' })
  expect(
    within(moments)
      .getAllByRole('button')
      .some((b) => b.textContent?.includes('Rory Ellis')),
  ).toBe(true)
  expect(screen.queryByRole('table')).toBeNull()
  expect(screen.queryByRole('link', { name: /Open cited evidence/ })).toBeNull()
  expect(
    within(moments).getByRole('heading', { name: 'See it for yourself' }),
  ).toBe(document.activeElement)
})

test('team and language changes preserve open recap and shared numbers; profile survives reload and clears', async () => {
  const user = userEvent.setup()
  const view = render(<App />)
  await screen.findByLabelText('1 to 4')
  await user.click(screen.getByRole('button', { name: /Catch me up/ }))
  await user.click(
    screen.getByRole('button', { name: /Neutral · choose a side/ }),
  )
  await user.selectOptions(screen.getByLabelText('Follow a team'), 'northport')
  await screen.findByLabelText('1 to 4')
  expect(
    screen.getByRole('region', { name: 'The story in a few moments' }),
  ).toBeTruthy()
  await user.selectOptions(screen.getByLabelText('Language'), 'zh-Hans')
  await screen.findByLabelText('1 to 4')
  expect(
    screen.getByRole('region', { name: '几个事件，了解故事' }),
  ).toBeTruthy()
  expect(screen.getByText(/已保存在此设备/)).toBeTruthy()
  view.unmount()
  render(<App />)
  await screen.findByLabelText('1 to 4')
  expect(api.fetchSnapshot).toHaveBeenLastCalledWith(
    'increase',
    780000,
    expect.any(AbortSignal),
    expect.any(String),
    { ...fanDefaults, club_id: 'northport', language: 'zh-Hans' },
  )
  await user.click(screen.getByRole('button', { name: /正在关注/ }))
  await user.click(screen.getByRole('button', { name: '清除偏好' }))
  await screen.findByLabelText('1 to 4')
  expect(window.localStorage.getItem(preferenceKey)).toBeNull()
  expect((screen.getByLabelText('Language') as HTMLSelectElement).value).toBe(
    'en',
  )
})

test('late viewpoint response cannot replace a newer selection', async () => {
  const user = userEvent.setup()
  render(<App />)
  await screen.findByLabelText('1 to 4')
  let release!: () => void
  vi.mocked(api.fetchSnapshot).mockImplementation(
    async (scenario, at, _signal, scope, p = fanDefaults) => {
      if (p.language === 'zh-Hans')
        return new Promise((resolve) => {
          release = () => resolve(fixture(scenario, at, scope, p))
        })
      return fixture(scenario, at, scope, p)
    },
  )
  await user.selectOptions(screen.getByLabelText('Language'), 'zh-Hans')
  await waitFor(() => expect(release).toBeTypeOf('function'))
  await user.selectOptions(screen.getByLabelText('Language'), 'en')
  await screen.findByLabelText('1 to 4')
  await act(async () => release())
  expect(
    screen.getByRole('heading', {
      name: 'Eastbridge are winning it back more often',
    }),
  ).toBeTruthy()
  expect(screen.queryByText('记录次数不能证明战术因果关系。')).toBeNull()
})

test('withdrawal removes story and evidence; stale poll cannot revive it; rewind has no future facts', async () => {
  let revision = 1,
    withdrawn = false
  vi.mocked(api.fetchSnapshot).mockImplementation(
    async (s, a, _signal, scope, p) =>
      fixture(s, a, scope, p, revision, withdrawn),
  )
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval', 'Date'] })
  render(<App />)
  await act(async () => {})
  fireEvent.click(screen.getByRole('button', { name: 'Show the moments' }))
  expect(
    screen.getByRole('region', { name: 'See it for yourself' }),
  ).toBeTruthy()
  revision = 3
  withdrawn = true
  await act(async () => {
    vi.advanceTimersByTime(2000)
  })
  expect(
    screen.getByRole('heading', { name: 'This story has changed.' }),
  ).toBeTruthy()
  expect(
    screen.queryByRole('region', { name: 'See it for yourself' }),
  ).toBeNull()
  revision = 1
  withdrawn = false
  await act(async () => {
    vi.advanceTimersByTime(2000)
  })
  expect(screen.queryByLabelText('1 to 4')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: /Explore replay/ }))
  fireEvent.click(screen.getByRole('button', { name: 'Back to 48:00' }))
  await act(async () => {})
  expect(
    screen.getByRole('heading', { name: 'Earlier in the match' }),
  ).toBeTruthy()
  expect(screen.queryByLabelText('1 to 4')).toBeNull()
})

test('latest correction is an explicit action and keeps paused time until requested', async () => {
  const user = userEvent.setup()
  render(<App />)
  await screen.findByLabelText('1 to 4')
  await user.click(screen.getByRole('button', { name: /Explore replay/ }))
  expect(screen.getByRole('slider',{name:'Match time'}).getAttribute('aria-valuetext')).toBe(
    '58:00',
  )
  await user.click(screen.getByRole('button', { name: /A newer version/ }))
  await waitFor(() =>
    expect(api.fetchSnapshot).toHaveBeenLastCalledWith(
      'increase',
      795000,
      expect.any(AbortSignal),
      expect.any(String),
      fanDefaults,
    ),
  )
  expect(screen.getByRole('slider',{name:'Match time'}).getAttribute('aria-valuetext')).toBe(
    '58:15',
  )
})

test('following a player has an honest no-evidence exit back to the team', async () => {
  const user = userEvent.setup()
  render(<App />)
  await screen.findByLabelText('1 to 4')
  await user.click(
    screen.getByRole('button', { name: /Neutral · choose a side/ }),
  )
  await user.selectOptions(screen.getByLabelText('Follow a player'), 'eb04')
  await screen.findByRole('heading', {
    name: 'No highlights for this player yet.',
  })
  await user.click(screen.getByRole('button', { name: 'Show the team story' }))
  await screen.findByLabelText('1 to 4')
})

test('storage corruption and unknown identifiers never become request preferences', () => {
  window.localStorage.setItem(preferenceKey, 'broken')
  expect(readPreferences()).toEqual(fanDefaults)
  window.localStorage.setItem(
    preferenceKey,
    JSON.stringify({
      language: 'unknown',
      club_id: 'unapproved',
      player_id: 'secret-like-free-text',
      card_budget: 0,
      metric_focus: 'invented',
    }),
  )
  expect(readPreferences()).toEqual(fanDefaults)
})

test('unavailable storage does not break following or falsely promise persistence', async () => {
  vi.spyOn(window.localStorage, 'setItem').mockImplementation(() => {
    throw new Error('denied')
  })
  const user = userEvent.setup()
  render(<App />)
  await screen.findByLabelText('1 to 4')
  await user.click(
    screen.getByRole('button', { name: /Neutral · choose a side/ }),
  )
  await user.selectOptions(screen.getByLabelText('Follow a team'), 'eastbridge')
  await screen.findByLabelText('1 to 4')
  expect(screen.getByText(/Preferences last for this visit only/)).toBeTruthy()
})

test('error can retry without inventing score or leaving an outdated story', async () => {
  vi.mocked(api.fetchSnapshot).mockRejectedValueOnce(
    new Error('private-error-must-not-render'),
  )
  const user = userEvent.setup()
  render(<App />)
  await screen.findByRole('alert')
  expect(screen.queryByText('private-error-must-not-render')).toBeNull()
  expect(screen.queryByLabelText('1 to 4')).toBeNull()
  await user.click(screen.getByRole('button', { name: 'Try again' }))
  await screen.findByLabelText('1 to 4')
})

test('exact evidence revision is required for story presentation', () => {
  const s = fixture('increase', 780000, 'scope')
  expect(storiesFor(s, fanDefaults)).toHaveLength(1)
  s.lifecycle!.evidence.packet.evidence_version = 99
  expect(storiesFor(s, fanDefaults)).toEqual([])
})

test('analysis deep link keeps the existing presenter tools accessible', async () => {
  window.history.replaceState(null, '', '/#analysis')
  render(<App />)
  expect(screen.getByLabelText('Local viewer')).toBeTruthy()
  expect(
    screen.getByRole('link', { name: 'Matchday' }),
  ).toBeTruthy()
  window.location.hash = '#matchday'
  fireEvent(window, new HashChangeEvent('hashchange'))
  await screen.findByRole('heading', {level:1,name:'Last-second turnaround'})
  expect(screen.queryByLabelText('Local viewer')).toBeNull()
})

test('slow replay requests finish while the clock advances; accepted facts remain dated', async () => {
  vi.useFakeTimers()
  render(<App />)
  await act(async () => {})
  fireEvent.click(screen.getByRole('button', { name: /Explore replay/ }))
  fireEvent.click(screen.getByRole('button', { name: 'Back to 48:00' }))
  await act(async () => {})
  let finish: (() => void) | undefined
  let signal: AbortSignal | undefined
  vi.mocked(api.fetchSnapshot).mockImplementationOnce(
    (scenario, at, abort, scope, p) => {
      signal = abort
      return new Promise((resolve) => {
        finish = () => resolve(fixture(scenario, at, scope, p))
      })
    },
  )
  fireEvent.click(screen.getByRole('button', { name: 'Play replay' }))
  for (let i = 0; i < 6; i++) {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(250)
    })
  }
  expect(finish).toBeTypeOf('function')
  expect(signal?.aborted).toBe(false)
  await act(async () => {
    finish!()
  })
  expect(
    within(screen.getByRole('region', { name: 'Match scoreboard' })).getByText(
      /Updated to/,
    ).textContent,
  ).not.toContain('Updated to 48:00')
  expect(screen.queryByLabelText('1 to 4')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Pause replay' }))
})

test('home leads with the featured highlight and keeps only related highlights below the action', async () => {
  window.history.replaceState(null, '', '/')
  render(<App />)
  const title = await screen.findByRole('heading', {level:1,name:'Last-second turnaround'})
  expect(screen.getByText('Highlight of the day')).toBeTruthy()
  expect(screen.queryByText('Pick a moment')).toBeNull()
  expect(screen.queryByLabelText('Explore a story')).toBeNull()
  const more = screen.getByRole('region', {name:'More highlights'})
  expect(within(more).getAllByRole('button')).toHaveLength(2)
  expect(within(more).queryByText('Last-second turnaround')).toBeNull()
  expect(screen.getByRole('link', {name:/Original clip/}).closest('footer')).toBeTruthy()
  const card = within(more).getByRole('button', {name:/Pass, move, finish/})
  fireEvent.click(card)
  expect(await screen.findByRole('heading', {level:1,name:'Pass, move, finish'})).toBe(title)
  expect(document.activeElement).toBe(title)
  expect(window.location.search).toBe('?story=one-touch')
  expect(within(more).getAllByRole('button')).toHaveLength(2)
  fireEvent.click(within(more).getByRole('button', {name:/Last-second turnaround/}))
  expect(await screen.findByRole('heading', {level:1,name:'Last-second turnaround'})).toBeTruthy()
})
