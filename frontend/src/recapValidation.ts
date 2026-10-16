import type { Preferences, Snapshot } from './types'

/** A recap travels with the accepted snapshot, never in a separate response/cache. */
export function validateRecap(data: Snapshot, prefs: Preferences) {
  const recap = data.recap
  if (!recap) {
    if (data.adapted_recap || data.recap_workflow?.applied) throw new Error('Recap adaptation requires a factual fallback.')
    return // Older contract fixtures remain readable.
  }
  const fail = () => { throw new Error('Recap did not match the current evidence and perspective.') }
  if (recap.match_id !== data.state.match_id || recap.cutoff.period !== data.state.at.period
    || recap.cutoff.elapsed_ms !== data.state.at.elapsed_ms
    || JSON.stringify(recap.windows) !== JSON.stringify(data.windows)
    || Object.entries(prefs).some(([key, value]) => recap.preferences[key as keyof Preferences] !== value)
    || !['ready', 'collecting', 'no_eligible', 'budget_hidden'].includes(recap.state)
    || (recap.state === 'ready') !== (recap.statements.length > 0)
    || recap.statements.length > 4 || !Number.isInteger(recap.omitted_count) || recap.omitted_count < 0
    || (recap.state !== 'ready' && recap.omitted_count !== 0)
    || (prefs.card_budget === 0 && recap.state !== 'budget_hidden')
    || (recap.statements.length > 0 && recap.cutoff.elapsed_ms < data.windows[1].end.elapsed_ms)) fail()
  const seen = new Set<string>()
  for (const { citation: c, narrative: n } of recap.statements) {
    const publication = c.kind === 'recovery' ? data.lifecycle : c.kind === 'pressure'
      ? data.pressure_lifecycle?.find(item => item.insight_id === c.insight_id)
      : c.kind === 'contribution' ? data.contribution_lifecycle?.find(item => item.insight_id === c.insight_id) : undefined
    const evidenceId = c.kind === 'recovery' ? data.lifecycle?.evidence.packet.evidence_id
      : publication && 'evidence_id' in publication ? publication.evidence_id : undefined
    if (!publication || publication.operation === 'withdraw' || publication.insight_id !== c.insight_id
      || publication.revision !== c.revision || evidenceId !== c.evidence_id || seen.has(c.insight_id)
      || c.available_at.period !== recap.cutoff.period || c.available_at.elapsed_ms > recap.cutoff.elapsed_ms
      || c.available_at.period !== publication.available_at.period || c.available_at.elapsed_ms !== publication.available_at.elapsed_ms
      || n.insight_id !== c.insight_id || n.revision !== c.revision
      || n.language !== prefs.language || n.depth !== prefs.depth || n.club_id !== prefs.club_id || n.player_id !== prefs.player_id) fail()
    seen.add(c.insight_id)
  }
  const adapted = data.adapted_recap, workflow = data.recap_workflow
  if (adapted) {
    if (!workflow?.applied || !['accepted', 'narrowed'].includes(workflow.status)
      || !['segment_review', 'key_changes'].includes(workflow.heading ?? '')
      || !Number.isFinite(workflow.expires_at_unix_ms) || adapted.state !== 'ready'
      || adapted.omitted_count !== recap.omitted_count + recap.statements.length - adapted.statements.length) fail()
    validateRecap({ ...data, recap: adapted, adapted_recap: null, recap_workflow: null }, prefs)
    for (const statement of adapted.statements) {
      const original = recap.statements.find(s => s.citation.insight_id === statement.citation.insight_id)
      if (!original || JSON.stringify(original.citation) !== JSON.stringify(statement.citation)
        || original.narrative.title !== statement.narrative.title
        || original.narrative.qualification !== statement.narrative.qualification
        || original.narrative.subject_name !== statement.narrative.subject_name) fail()
    }
  } else if (workflow?.applied) fail()
}
