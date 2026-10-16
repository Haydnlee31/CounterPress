import { defaultPreferences } from './types'
import type { Preferences, Scenario, Snapshot } from './types'
import { validateRecap } from './recapValidation'

export async function fetchScenarios(signal: AbortSignal): Promise<Scenario[]> {
  const response = await fetch('/api/scenarios', { signal })
  if (!response.ok) throw new Error('The replay scenarios could not be loaded.')
  return response.json()
}

export async function fetchSnapshot(scenario: string, atMs: number, signal: AbortSignal, scopeId: string, preferences: Preferences = defaultPreferences): Promise<Snapshot> {
  const query = new URLSearchParams({ at_ms: String(atMs), scope_id: scopeId })
  for (const [key, value] of Object.entries(preferences)) if (value !== null) query.set(key, String(value))
  const response = await fetch(`/api/scenarios/${encodeURIComponent(scenario)}/snapshot?${query}`, { signal, cache: 'no-store' })
  if (!response.ok) throw new Error('The replay is unavailable. Check that the backend is running and the fixture is valid.')
  const data: Snapshot = await response.json()
  if (data.scenario_id !== scenario || data.scope_id !== scopeId || data.state.at.elapsed_ms !== atMs) throw new Error('The replay response did not match this playback position. Please retry.')
  if (!data.audience || Object.entries(preferences).some(([key, value]) => data.audience!.preferences[key as keyof Preferences] !== value)) throw new Error('The replay response did not match these viewing preferences. Please retry.')
  const variant = data.audience.variant
  if (variant && (variant.insight_id !== data.insight?.insight_id || variant.revision !== data.insight.revision
    || variant.language !== preferences.language || variant.depth !== preferences.depth
    || variant.club_id !== preferences.club_id || variant.player_id !== preferences.player_id)) throw new Error('The explanation did not match the requested evidence and perspective. Please retry.')
  const pressure = data.pressure
  if (pressure && Object.entries(preferences).some(([key, value]) => pressure.preferences[key as keyof Preferences] !== value)) throw new Error('Pressure evidence did not match these viewing preferences.')
  if (pressure?.variant) {
    const publication = pressure.publication, text = pressure.variant
    if (!publication || publication.operation === 'withdraw' || publication.decision.status !== 'eligible'
      || text.insight_id !== publication.insight_id || text.revision !== publication.revision
      || text.language !== preferences.language || text.depth !== preferences.depth
      || text.club_id !== preferences.club_id || text.player_id !== preferences.player_id
      || publication.available_at.elapsed_ms > atMs
      || !data.pressure_lifecycle?.some(change => change.insight_id === publication.insight_id && change.revision === publication.revision && change.operation !== 'withdraw')) throw new Error('Pressure explanation did not match its evidence and perspective.')
  }
  if (data.selected_kind === 'pressure' && (!pressure?.variant || pressure.state !== 'ready' || preferences.card_budget === 0)) throw new Error('Pressure card selection is invalid.')
  const contribution = data.contribution
  if (contribution && Object.entries(preferences).some(([key, value]) => contribution.preferences[key as keyof Preferences] !== value)) throw new Error('Player evidence did not match these viewing preferences.')
  if (contribution?.variant) {
    const publication = contribution.publication, text = contribution.variant
    const latest = data.contribution_lifecycle?.find(change => change.insight_id === publication?.insight_id)
    if (!publication || publication.operation === 'withdraw' || publication.evidence.decision.status !== 'eligible'
      || text.insight_id !== publication.insight_id || text.revision !== publication.revision
      || text.language !== preferences.language || text.depth !== preferences.depth
      || text.club_id !== preferences.club_id || text.player_id !== preferences.player_id
      || (preferences.player_id !== null && publication.evidence.subject_player_id !== preferences.player_id)
      || publication.available_at.period !== data.state.at.period || publication.available_at.elapsed_ms > atMs
      || !latest || latest.revision !== publication.revision || latest.operation === 'withdraw'
      || JSON.stringify(latest) !== JSON.stringify(publication)) throw new Error('Player explanation did not match its evidence and perspective.')
  }
  if (data.selected_kind === 'contribution' && (!contribution?.variant || contribution.state !== 'ready' || preferences.card_budget === 0)) throw new Error('Player card selection is invalid.')
  validateRecap(data, preferences)
  return data
}
