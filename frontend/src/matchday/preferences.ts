import { defaultPreferences } from '../types'
import type { Preferences } from '../types'
import { clubs, knownPlayer } from './identity'

export const preferenceKey = 'counterpress.matchday.preferences.v1'
/** Shared store written by the Clubhouse (fan personalization) workspace. */
const fanPreferenceKey = 'counterpress.fan.preferences.v1'
export const fanDefaults: Preferences = {
  ...defaultPreferences,
  depth: 'casual',
}

/** Read language and depth from the fan store, which Clubhouse writes to. */
function readFanShared(): { language: Preferences['language']; depth: Preferences['depth'] } | null {
  try {
    const raw = JSON.parse(window.localStorage.getItem(fanPreferenceKey) ?? 'null')
    if (!raw || typeof raw !== 'object') return null
    return {
      language: raw.language === 'zh-Hans' ? 'zh-Hans' : 'en',
      depth: raw.depth === 'analyst' ? 'analyst' : 'casual',
    }
  } catch {
    return null
  }
}

export function readPreferences(): Preferences {
  // Language and depth come from the fan store when available — Clubhouse is
  // the primary writer of counterpress.fan.preferences.v1, so we defer to it
  // to keep language consistent across all workspaces.
  const fan = readFanShared()
  try {
    const raw = JSON.parse(window.localStorage.getItem(preferenceKey) ?? 'null')
    if (!raw || typeof raw !== 'object') return { ...fanDefaults, ...(fan ?? {}) }
    return {
      ...fanDefaults,
      language: fan?.language ?? (raw.language === 'zh-Hans' ? 'zh-Hans' : 'en'),
      depth: fan?.depth ?? (raw.depth === 'analyst' ? 'analyst' : 'casual'),
      club_id:
        typeof raw.club_id === 'string' && Object.hasOwn(clubs, raw.club_id)
          ? raw.club_id
          : null,
      player_id: knownPlayer(raw.player_id) ? raw.player_id : null,
    }
  } catch {
    return { ...fanDefaults, ...(fan ?? {}) }
  }
}
export function savePreferences(p: Preferences): boolean {
  let ok = true
  try {
    window.localStorage.setItem(
      preferenceKey,
      JSON.stringify({
        language: p.language,
        depth: p.depth,
        club_id: p.club_id,
        player_id: p.player_id,
      }),
    )
  } catch {
    ok = false
  }
  // Keep language and depth in sync with the fan store so Clubhouse picks up
  // changes made in Matchday/GI without requiring a separate preference update.
  try {
    const fanRaw = window.localStorage.getItem(fanPreferenceKey)
    if (fanRaw !== null) {
      const fan = JSON.parse(fanRaw)
      if (fan && typeof fan === 'object') {
        window.localStorage.setItem(
          fanPreferenceKey,
          JSON.stringify({ ...fan, language: p.language, depth: p.depth }),
        )
      }
    }
  } catch {
    // Fan store sync is best-effort; matchday preferences are still saved above.
  }
  return ok
}
