import type { Snapshot } from './types'

/** A seek/reset starts a fresh scope. Forward playback retains withdrawal revisions. */
export class PlaybackScope {
  readonly id: string
  private historyVersion = -1
  private atMs = -1
  private insightRevision = 0
  private pressureRevisions = new Map<string, number>()
  private contributionRevisions = new Map<string, number>()

  constructor(id: string = crypto.randomUUID()) { this.id = id }

  accept(snapshot: Snapshot): boolean {
    const revision = snapshot.lifecycle?.revision ?? 0
    if (snapshot.scope_id !== this.id || snapshot.history_version < this.historyVersion
      || snapshot.state.at.elapsed_ms < this.atMs || revision < this.insightRevision) return false
    const pressure = new Map((snapshot.pressure_lifecycle ?? []).map(change => [change.insight_id, change.revision]))
    for (const [id, version] of this.pressureRevisions) if ((pressure.get(id) ?? 0) < version) return false
    const contributions = new Map((snapshot.contribution_lifecycle ?? []).map(change => [change.insight_id, change.revision]))
    for (const [id, version] of this.contributionRevisions) if ((contributions.get(id) ?? 0) < version) return false
    this.contributionRevisions = contributions
    this.pressureRevisions = pressure
    this.historyVersion = snapshot.history_version
    this.atMs = snapshot.state.at.elapsed_ms
    this.insightRevision = revision // Retain tombstones even though the visible insight is null.
    return true
  }
}
