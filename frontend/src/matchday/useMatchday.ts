import { useEffect, useRef, useState } from 'react'
import { fetchScenarios, fetchSnapshot } from '../api'
import { PlaybackScope } from '../playbackScope'
import { subscribeRevisions } from '../revisions'
import type { RevisionStatus } from '../revisions'
import type { Preferences, Scenario, Snapshot } from '../types'
import {
  fanDefaults,
  readPreferences,
  savePreferences,
  preferenceKey,
} from './preferences'

export const SEGMENT_START = 180000,
  COMPARISON_TIME = 780000
export function useMatchday() {
  const [request, setRequest] = useState(() => ({
    scenario: new URLSearchParams(window.location.search).get('story')==='last-gasp'?'last-gasp':'increase',
    atMs: COMPARISON_TIME,
    preferences: readPreferences(),
    scope: new PlaybackScope(),
  }))
  const [data, setData] = useState<Snapshot | null>(null)
  const [scenarios, setScenarios] = useState<Scenario[]>([])
  const [error, setError] = useState(false)
  const [tick, setTick] = useState(0)
  const [status, setStatus] = useState<RevisionStatus>('polling')
  const [saved, setSaved] = useState<boolean | null>(null)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(10)
  const [ends, setEnds] = useState<Record<string, number>>({})
  const requestRef = useRef(request)
  requestRef.current = request
  const statusRef = useRef(status)
  statusRef.current = status
  const end = ends[request.scenario] ?? COMPARISON_TIME
  useEffect(() => {
    const controller = new AbortController()
    fetchScenarios(controller.signal)
      .then((items) => {
        if (!controller.signal.aborted) setScenarios(items)
      })
      .catch(() => {})
    return () => controller.abort()
  }, [])
  useEffect(
    () =>
      subscribeRevisions(
        request.scenario,
        () => setTick((n) => n + 1),
        setStatus,
      ),
    [request.scenario],
  )
  useEffect(() => {
    const controller = new AbortController()
    let pending = false,
      lastRefresh = 0,
      lastRequestedAt = -1
    setError(false)
    async function refresh() {
      if (pending) return
      pending = true
      lastRefresh = Date.now()
      const target = requestRef.current
      lastRequestedAt = target.atMs
      try {
        const snapshot = await fetchSnapshot(
          target.scenario,
          target.atMs,
          controller.signal,
          target.scope.id,
          target.preferences,
        )
        if (!controller.signal.aborted && request.scope.accept(snapshot)) {
          setData(snapshot)
          setError(false)
          setEnds((previous) =>
            previous[request.scenario] === snapshot.replay_end.elapsed_ms
              ? previous
              : {
                  ...previous,
                  [request.scenario]: snapshot.replay_end.elapsed_ms,
                },
          )
        }
      } catch {
        if (!controller.signal.aborted) {
          setError(true)
          setData(null)
          setPlaying(false)
        }
      } finally {
        pending = false
      }
    }
    void refresh()
    const interval = window.setInterval(() => {
      if (
        requestRef.current.atMs !== lastRequestedAt ||
        Date.now() - lastRefresh >=
          (statusRef.current === 'connected' ? 30000 : 2000)
      )
        void refresh()
    }, 250)
    return () => {
      controller.abort()
      window.clearInterval(interval)
    }
  }, [request.scope, request.scenario, tick])
  useEffect(() => {
    if (!playing) return
    let previous = performance.now()
    const timer = window.setInterval(() => {
      const now = performance.now(),
        elapsed = now - previous
      previous = now
      setRequest((r) => ({
        ...r,
        atMs: Math.min(end, r.atMs + Math.round(elapsed * speed)),
      }))
    }, 250)
    return () => window.clearInterval(timer)
  }, [playing, speed, end])
  useEffect(() => {
    if (request.atMs >= end) setPlaying(false)
  }, [request.atMs, end])
  const snapshot =
    data?.scope_id === request.scope.id &&
    data.scenario_id === request.scenario &&
    data.state.at.elapsed_ms <= request.atMs
      ? data
      : null
  function preferences(value: Preferences) {
    setSaved(savePreferences(value))
    setRequest((r) => ({
      ...r,
      preferences: value,
      scope: new PlaybackScope(),
    }))
  }
  function resetPreferences() {
    try {
      window.localStorage.removeItem(preferenceKey)
      setSaved(null)
    } catch {
      setSaved(false)
    }
    setRequest((r) => ({
      ...r,
      preferences: { ...fanDefaults },
      scope: new PlaybackScope(),
    }))
  }
  function seek(atMs: number) {
    setPlaying(false)
    setRequest((r) => ({ ...r, atMs, scope: new PlaybackScope() }))
  }
  function scenario(value: string) {
    setPlaying(false)
    setRequest((r) => ({
      ...r,
      scenario: value,
      atMs: COMPARISON_TIME,
      scope: new PlaybackScope(),
    }))
  }
  function play() {
    if (playing) {
      setPlaying(false)
      return
    }
    if (request.atMs >= end)
      setRequest((r) => ({
        ...r,
        atMs: SEGMENT_START,
        scope: new PlaybackScope(),
      }))
    setPlaying(true)
  }
  return {
    request,
    snapshot,
    scenarios,
    error,
    status,
    saved,
    playing,
    speed,
    end,
    preferences,
    resetPreferences,
    seek,
    scenario,
    play,
    setSpeed,
    retry: () => setTick((n) => n + 1),
  }
}
