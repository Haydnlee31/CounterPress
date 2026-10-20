import type {MatchTime,Event} from '../types'
import {replayTime} from '../matchday/replayGallery'

export type FootieContext={
  label:string;question:string;playerId?:string;clubId?:string;season?:string;asOf?:string;
  matchId?:string;cutoff?:MatchTime;eventId?:string;eventRevision?:number;resolveSource?:boolean;resolved?:boolean
}

export function matchdayContext(matchId:string,event:Event,resolved:boolean,label:string):FootieContext{
  const occurred=replayTime(event)
  const offset=occurred.elapsed_ms-event.occurred_at.elapsed_ms
  return {...momentContext(matchId,{...event,occurred_at:occurred,available_at:{period:occurred.period,elapsed_ms:event.available_at.elapsed_ms+offset}},resolved,label),resolveSource:true,resolved}
}

/** Freeze the source clock, not the animation's compressed presentation clock. */
export function momentContext(matchId:string,event:Pick<Event,'event_id'|'revision'|'occurred_at'|'available_at'>,resolved:boolean,label:string):FootieContext{
  const cutoff=resolved?event.available_at:{period:event.occurred_at.period,elapsed_ms:Math.max(0,event.occurred_at.elapsed_ms-1)}
  return {label,question:'What happened in this moment?',matchId,cutoff:{...cutoff},eventId:event.event_id,eventRevision:event.revision}
}
