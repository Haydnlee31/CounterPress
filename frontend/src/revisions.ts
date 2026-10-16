/** Push carries revision hints only. Authoritative facts still come from snapshots. */
export type RevisionStatus = 'connecting' | 'connected' | 'polling'
export function subscribeRevisions(scenario: string, refresh: () => void, status: (value: RevisionStatus) => void) {
  let stopped = false, socket: WebSocket | null = null, retry: ReturnType<typeof setTimeout> | undefined
  let attempt = 0, highest = -1
  const abort = new AbortController()
  function reconnect() {
    if (stopped) return
    status('polling')
    retry = setTimeout(() => { void connect() }, Math.min(30000, 1000 * 2 ** Math.min(attempt++, 5)))
  }
  async function connect() {
    if (stopped) return
    status('connecting')
    try {
      const response = await fetch(`/api/revisions/negotiate?scenario_id=${encodeURIComponent(scenario)}`, { signal: abort.signal, cache: 'no-store' })
      if (!response.ok) throw new Error('negotiation failed')
      const config = await response.json()
      if (stopped) return
      if (config.enabled === false) { status('polling'); return }
      const url = new URL(config.url)
      if (url.protocol !== 'wss:' || !url.hostname.endsWith('.webpubsub.azure.com') || url.username || url.password) throw new Error('invalid service URL')
      const current = new WebSocket(url.href)
      socket = current
      current.onopen = () => {
        if (stopped || socket !== current) return
        attempt = 0; status('connected'); refresh() // Recover everything missed while disconnected.
      }
      current.onmessage = event => {
        if (stopped || socket !== current || typeof event.data !== 'string' || event.data.length > 64000) return
        try {
          const data = JSON.parse(event.data)
          if (data.type !== 'history.changed' || data.schema_version !== 1 || data.scenario_id !== scenario
            || typeof data.match_id !== 'string' || !Number.isSafeInteger(data.history_version)
            || data.history_version <= highest || data.replay_end?.period !== 2
            || !Number.isSafeInteger(data.replay_end?.elapsed_ms) || !Array.isArray(data.revisions)) return
          highest = data.history_version
          refresh() // Never apply pushed counts, clocks or tombstones directly to the screen.
        } catch { /* Invalid messages cannot change facts. */ }
      }
      current.onerror = () => current.close()
      current.onclose = () => { if (!stopped && socket === current) { socket = null; reconnect() } }
    } catch { if (!stopped) reconnect() }
  }
  void connect()
  return () => { stopped = true; abort.abort(); clearTimeout(retry); socket?.close() }
}
