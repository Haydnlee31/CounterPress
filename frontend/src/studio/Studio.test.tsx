import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import Studio from './Studio'
import type { Review, Session } from './session'
import { defaultPreferences } from '../types'

afterEach(() => { cleanup(); vi.useRealTimers() })
const view = (status: Review['status'] = 'unreviewed', fingerprint = 'a'.repeat(64)): Review => ({
  fingerprint, status, source_version: 89, approval_id: status === 'approved' ? 'approval-1' : null,
  approved_at_unix_ms: status === 'approved' ? 1000 : null, evidence: [],
  recap: { match_id: 'match-1', cutoff: { period: 2, elapsed_ms: 780000 },
    windows: [{ start: { period: 2, elapsed_ms: 180000 }, end: { period: 2, elapsed_ms: 480000 }, boundary: '(start,end]' },
      { start: { period: 2, elapsed_ms: 480000 }, end: { period: 2, elapsed_ms: 780000 }, boundary: '(start,end]' }],
    preferences: { ...defaultPreferences, depth: 'casual' }, state: 'ready', omitted_count: 0,
    statements: [{ narrative: { insight_id: 'insight-1', revision: 1, language: 'en', depth: 'casual', club_id: null, player_id: null,
      title: 'Winning it back high', explanation: 'Four recoveries, up from one.', qualification: 'No claim about pressing effectiveness.', subject_name: 'Eastbridge' },
      citation: { kind: 'recovery', insight_id: 'insight-1', revision: 1, evidence_id: 'evidence-1', available_at: { period: 2, elapsed_ms: 780000 } } }],
  },
})
function session(initial = view()) {
  let current = initial
  return { signIn: vi.fn(async () => {}), signOut: vi.fn(async () => {}), download: vi.fn(async () => new Blob(['snapshot'])),
    call: vi.fn(async (action: string) => { if (action === 'approve') current = view('approved'); if (action === 'revoke') current = view('revoked'); return current }),
    change(next: Review) { current = next },
  }
}
async function start(s: Session) {
  render(<Studio sessionFactory={async () => s} />)
  await waitFor(() => expect((screen.getByText('Sign in with Microsoft') as HTMLButtonElement).disabled).toBe(false))
  fireEvent.click(screen.getByText('Sign in with Microsoft'))
  await screen.findByText('Needs your review')
}
describe('Studio producer flow', () => {
  it('keeps review private and explains a disabled deployment', async () => {
    render(<Studio sessionFactory={async () => null} />)
    await screen.findByText(/Studio is not enabled/)
    expect((screen.getByText('Sign in with Microsoft') as HTMLButtonElement).disabled).toBe(true)
    expect(screen.queryByText('1. Review the story')).toBeNull()
  })
  it('requires explicit approval before preview and revokes it', async () => {
    const s = session(); await start(s)
    expect(s.call.mock.calls.map(c => c[0])).toEqual(['review'])
    expect((screen.getByText('Download approved snapshot') as HTMLButtonElement).disabled).toBe(true)
    fireEvent.click(screen.getByText('I reviewed this version · Approve'))
    await screen.findByText('Approved for this snapshot')
    expect(s.call).toHaveBeenCalledWith('approve', 'increase', expect.anything(), 'a'.repeat(64))
    fireEvent.click(screen.getByText('Open clean preview'))
    expect(screen.getByLabelText('Approved clean preview')).toBeTruthy()
    fireEvent.click(screen.getByText('Revoke this approval'))
    await screen.findByText('Approval revoked')
    expect(screen.queryByLabelText('Approved clean preview')).toBeNull()
  })
  it('clears approval immediately when language changes or the session ends', async () => {
    const s = session(); await start(s)
    fireEvent.click(screen.getByText('I reviewed this version · Approve'))
    await screen.findByText('Approved for this snapshot')
    s.change(view('changed', 'b'.repeat(64)))
    fireEvent.change(screen.getByLabelText('Story language'), { target: { value: 'zh-Hans' } })
    expect((screen.getByText('Download approved snapshot') as HTMLButtonElement).disabled).toBe(true)
    await screen.findByText('New version · review again')
    fireEvent.click(screen.getByText('End Studio session'))
    expect(screen.queryByText('Four recoveries, up from one.')).toBeNull()
    expect(s.signOut).toHaveBeenCalledOnce()
  })
  it('hides stale preview after a correction is polled', async () => {
    const s = session(); await start(s)
    fireEvent.click(screen.getByText('I reviewed this version · Approve'))
    await screen.findByText('Approved for this snapshot')
    fireEvent.click(screen.getByText('Open clean preview'))
    s.change(view('changed', 'b'.repeat(64)))
    fireEvent.click(screen.getByText('Refresh evidence'))
    expect(screen.queryByLabelText('Approved clean preview')).toBeNull()
    await screen.findByText('New version · review again')
    expect((screen.getByText('Download approved snapshot') as HTMLButtonElement).disabled).toBe(true)
  })
  it('a failed recheck locks export and discards the previous story', async () => {
    const s = session(); await start(s)
    s.call.mockRejectedValueOnce(new Error('Storage is unavailable.'))
    fireEvent.click(screen.getByText('Refresh evidence'))
    await screen.findByRole('alert')
    expect(screen.queryByText('Four recoveries, up from one.')).toBeNull()
    expect((screen.getByText('Download approved snapshot') as HTMLButtonElement).disabled).toBe(true)
  })
  it('ignores a late response after sign-out', async () => {
    const s = session(); await start(s)
    let finish!: (r: Review) => void
    s.call.mockImplementationOnce(() => new Promise<Review>(resolve => { finish = resolve }))
    fireEvent.click(screen.getByText('Refresh evidence'))
    fireEvent.click(screen.getByText('End Studio session'))
    await act(async () => finish(view('approved')))
    expect(screen.queryByText('Approved for this snapshot')).toBeNull()
  })
})
