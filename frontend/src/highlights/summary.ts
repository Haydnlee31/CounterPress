import {defaults} from '../../../integrations/personalization/client'
import {updateHighlight} from './collection'
import type {SavedHighlight,Summary} from './collection'

const jobs=new Map<string,Promise<void>>()
let version=0
const errors=new Map<string,string>(),listeners=new Set<()=>void>()
const changed=()=>{version++;listeners.forEach(fn=>fn())}
export const subscribeSummaries=(fn:()=>void)=>{listeners.add(fn);return()=>{listeners.delete(fn)}}
export const summaryVersion=()=>version
export const summaryState=(id:string)=>({busy:jobs.has(id),error:errors.get(id)??''})
export async function requestSummary(h:SavedHighlight,signal:AbortSignal):Promise<Summary>{
  const query=new URLSearchParams({match_id:h.matchId,event_id:h.eventId,revision:String(h.revision),resolved:'true'})
  const resolve=await fetch(`/api/fan/assistant/moment?${query}`,{signal,credentials:'omit',cache:'no-store'})
  if(!resolve.ok)throw Error('This moment may have changed. Reopen it from Match Centre.')
  const {cutoff}=await resolve.json()
  const response=await fetch('/api/fan/assistant/summary',{method:'POST',signal,credentials:'omit',cache:'no-store',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:h.title==='Goal'?'What made this goal happen?':'What happened in this moment?',match_id:h.matchId,event_id:h.eventId,event_revision:h.revision,cutoff,preferences:{...defaults(),depth:'analyst'}})})
  if(!response.ok)throw Error(response.status===429?'Footie is busy. Your highlight is saved; try the summary again shortly.':'The analysis could not finish. Your highlight is saved; try again.')
  const answer=await response.json()
  const ai=answer.mode==='azure_generated_verified'&&answer.review?.supported===true&&answer.review?.issues?.length===0
  if(!ai)throw Error('Footie could not verify the summary. Please try again.')
  const text=answer.text
  if(!Array.isArray(text)||!text.length||!text.every(t=>typeof t==='string'))throw Error('Footie could not produce a summary. Try again.')
  return {text:text.slice(0,20),ai,requestId:answer.request_id,source:h.source}
}
// Import starts one request even if the user opens the saved workspace immediately.
// Refreshing/reopening never spends another model call automatically.
export function generateSummary(h:SavedHighlight){
  const current=jobs.get(h.id);if(current)return current
  errors.delete(h.id)
  const controller=new AbortController(),timer=window.setTimeout(()=>controller.abort(),90000)
  const job=requestSummary(h,controller.signal).then(summary=>updateHighlight(h.id,current=>current.source===h.source?{...current,summary}:current)).catch(e=>{errors.set(h.id,e.name==='AbortError'?'The summary took too long. Your highlight is saved; try again.':e.message)}).finally(()=>{clearTimeout(timer);jobs.delete(h.id);changed()})
  jobs.set(h.id,job);changed();return job
}
