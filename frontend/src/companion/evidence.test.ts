import {describe, expect, it} from 'vitest'
import {cue} from './evidence'
import type {Event} from '../types'

describe('drawn challenges', () => {
  it('does not turn a known draw into a loss in either language', () => {
    const event:Event={schema_version:'1.0',match_id:'match',event_id:'duel',revision:1,
      source_delivery_sequence:1,occurrence_order:1,occurred_at:{period:1,elapsed_ms:1000},available_at:{period:1,elapsed_ms:1100},
      actor:{team_id:'eastbridge',player_id:'eb02'},position:{x:30,y:20},
      action:{kind:'duel',outcome:'draw',opponent:{team_id:'northport',player_id:'np02'}}}
    expect(cue(event,true,false,false)).toBe('Neither player wins the challenge.')
    expect(cue(event,true,true,false)).toBe('双方争抢，未分胜负。')
  })
})
