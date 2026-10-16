import { defaultPreferences } from '../types'
import type { Preferences } from '../types'
import { clubs, knownPlayer } from './identity'

export const preferenceKey = 'counterpress.matchday.preferences.v1'
export const fanDefaults: Preferences = {
  ...defaultPreferences,
  depth: 'casual',
}
export function readPreferences(): Preferences {
  try {
    const raw = JSON.parse(window.localStorage.getItem(preferenceKey) ?? 'null')
    if (!raw || typeof raw !== 'object') return { ...fanDefaults }
    return {
      ...fanDefaults,
      language: raw.language === 'zh-Hans' ? 'zh-Hans' : 'en',
      depth: raw.depth === 'analyst' ? 'analyst' : 'casual',
      club_id:
        typeof raw.club_id === 'string' && Object.hasOwn(clubs, raw.club_id)
          ? raw.club_id
          : null,
      player_id: knownPlayer(raw.player_id) ? raw.player_id : null,
    }
  } catch {
    return { ...fanDefaults }
  }
}
export function savePreferences(p: Preferences): boolean {
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
    return true
  } catch {
    return false
  }
}
