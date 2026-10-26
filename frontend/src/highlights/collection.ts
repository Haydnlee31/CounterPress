import {useSyncExternalStore} from 'react'
import type {GIEvent,GIMatch} from '../gi/data'
import {alias,matchClock,outcomeText} from '../gi/data'
import {sequenceEvents} from '../gi/replay'

export type Stroke={at:number;points:{x:number;y:number}[]}
export type Summary={text:string[];ai:boolean;requestId:string;source:string}
export type SavedHighlight={id:string;matchId:string;eventId:string;revision:number;title:string;player:string;clock:string;date:string;source:string;created:string;strokes:Stroke[];note:string;summary?:Summary}
const KEY='footie.highlights.v1',CHANGE='footie-highlights-changed'
const validString=(v:unknown,max=500):v is string=>typeof v==='string'&&v.length<=max
function valid(value:unknown):value is SavedHighlight{
  if(!value||typeof value!=='object')return false
  const h=value as SavedHighlight
  return ['id','matchId','eventId','title','player','clock','date','created'].every(k=>validString(h[k as keyof SavedHighlight]))&&Number.isInteger(h.revision)&&h.revision>0&&validString(h.source,100000)&&validString(h.note,2000)&&Array.isArray(h.strokes)&&h.strokes.length<=30&&h.strokes.every(s=>Number.isFinite(s.at)&&s.at>=0&&s.at<=1&&Array.isArray(s.points)&&s.points.length<=250&&s.points.every(p=>Number.isFinite(p.x)&&p.x>=0&&p.x<=105&&Number.isFinite(p.y)&&p.y>=0&&p.y<=68))&&(!h.summary||(typeof h.summary.ai==='boolean'&&validString(h.summary.requestId)&&validString(h.summary.source,100000)&&Array.isArray(h.summary.text)&&h.summary.text.length<=20&&h.summary.text.every(t=>validString(t,4000))))
}
export function readCollection():SavedHighlight[]{
  const raw=localStorage.getItem(KEY)
  if(!raw)return []
  const parsed:unknown=JSON.parse(raw)
  if(!Array.isArray(parsed)||parsed.length>50||!parsed.every(valid))throw Error('Your saved highlights could not be read. Your existing collection has not been changed.')
  return parsed
}
export const highlightId=(matchId:string,eventId:string)=>`${matchId}:${eventId}`
export const sourceKey=(match:GIMatch,event:GIEvent)=>JSON.stringify([match.source.fixture_sha256,sequenceEvents(match.events,event)])
export function saveMoment(match:GIMatch,event:GIEvent){
  const id=highlightId(match.match_id,event.event_id),items=readCollection(),existing=items.find(h=>h.id===id)
  if(existing)return existing
  if(items.length>=50)throw Error('Your collection is full. Remove a highlight before adding another.')
  const h:SavedHighlight={id,matchId:match.match_id,eventId:event.event_id,revision:event.revision,title:outcomeText(event),player:alias(match.players.find(p=>p.player_id===event.player_id)??{player_id:event.player_id,provider_player_id:null,team_id:event.team_id,alias_id:event.player_id}),clock:matchClock(event),date:match.display_date,source:sourceKey(match,event),created:new Date().toISOString(),strokes:[],note:''}
  write([h,...items]);return h
}
function write(items:SavedHighlight[]){
  if(!items.every(valid))throw Error('This highlight could not be saved.')
  try{localStorage.setItem(KEY,JSON.stringify(items))}catch{throw Error('Your browser could not save this change. Free some storage or allow site storage, then try again.')}
  window.dispatchEvent(new Event(CHANGE))
}
export function updateHighlight(id:string,update:(h:SavedHighlight)=>SavedHighlight){
  const items=readCollection();if(!items.some(h=>h.id===id))return
  write(items.map(h=>h.id===id?update(h):h))
}
export function removeHighlight(id:string){write(readCollection().filter(h=>h.id!==id))}
const subscribe=(notify:()=>void)=>{window.addEventListener(CHANGE,notify);window.addEventListener('storage',notify);return()=>{window.removeEventListener(CHANGE,notify);window.removeEventListener('storage',notify)}}
// Snapshot is a primitive so useSyncExternalStore remains stable between writes.
function snapshot(){try{return localStorage.getItem(KEY)??'[]'}catch{return 'unavailable'}}
export function useCollection(){useSyncExternalStore(subscribe,snapshot);try{return {items:readCollection(),error:''}}catch(e){return {items:[] as SavedHighlight[],error:e instanceof Error?e.message:'Your collection could not be opened.'}}}
export const highlightLink=(id:string)=>`#highlights/${encodeURIComponent(id)}`
