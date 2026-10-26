import {beforeEach,expect,it,vi} from 'vitest'
import {readCollection,saveMoment,updateHighlight,removeHighlight,sourceKey} from './collection'
import {requestSummary,generateSummary} from './summary'
import type {GIMatch,GIEvent} from '../gi/data'
export const event:GIEvent={event_id:'goal',provider_event_id:null,revision:1,source_order:1,occurrence_order:1,period:1,elapsed_ms:3000,team_id:4418,player_id:'eb09',kind:'Shot',detail:'Shot',outcome:'goal',start:{x:90,y:34},end:{x:105,y:34},goal_for:4418,review:false,tags:[]}
const match={match_id:'match',display_date:'2026-10-18',players:[{player_id:'eb09',alias_id:'eb09',provider_player_id:null,team_id:4418}],events:[event],source:{fixture_sha256:'v1'}} as GIMatch
beforeEach(()=>{localStorage.clear();vi.unstubAllGlobals();vi.restoreAllMocks()})
it('saves references, deduplicates a moment and preserves drawings and notes on reimport',()=>{
 const h=saveMoment(match,event)
 updateHighlight(h.id,x=>({...x,note:'Hold the line',strokes:[{at:.4,points:[{x:12,y:25},{x:30,y:45}]}]}))
 const again=saveMoment(match,event)
 expect(readCollection()).toHaveLength(1);expect(again.note).toBe('Hold the line');expect(again.strokes[0].at).toBe(.4)
 expect(again).not.toHaveProperty('events')
 removeHighlight(h.id);expect(readCollection()).toEqual([])
})
it('detects source corrections and prevents a deleted highlight being resurrected by analysis',async()=>{
 const h=saveMoment(match,event)
 expect(sourceKey({...match,source:{...match.source,fixture_sha256:'v2'}},event)).not.toBe(h.source)
 removeHighlight(h.id);updateHighlight(h.id,x=>({...x,note:'Late result'}));expect(readCollection()).toEqual([])
})
it('does not overwrite a damaged collection or pretend a quota failure saved',()=>{
 localStorage.setItem('footie.highlights.v1','not json')
 expect(()=>saveMoment(match,event)).toThrow();expect(localStorage.getItem('footie.highlights.v1')).toBe('not json')
 localStorage.clear();vi.spyOn(Storage.prototype,'setItem').mockImplementation(()=>{throw Error('quota')})
 expect(()=>saveMoment(match,event)).toThrow(/browser could not save/)
})
it('rejects invalid pitch coordinates in persisted drawings',()=>{
 const h=saveMoment(match,event)
 expect(()=>updateHighlight(h.id,x=>({...x,strokes:[{at:.2,points:[{x:NaN,y:10}]}]}))).toThrow()
 expect(readCollection()[0].strokes).toEqual([])
})
it('resolves the canonical revision clock before asking and keeps model provenance',async()=>{
 const h=saveMoment(match,event),fetcher=vi.fn().mockResolvedValueOnce({ok:true,json:async()=>({cutoff:{period:1,elapsed_ms:4100}})}).mockResolvedValueOnce({ok:true,json:async()=>({request_id:'receipt',mode:'azure_generated_verified',review:{supported:true,issues:[]},text:['The goal brought the teams level.']})})
 vi.stubGlobal('fetch',fetcher)
 const result=await requestSummary(h,new AbortController().signal)
 const body=JSON.parse(fetcher.mock.calls[1][1].body)
 expect(body).toMatchObject({match_id:'match',event_id:'goal',event_revision:1,cutoff:{period:1,elapsed_ms:4100}})
 expect(result).toMatchObject({ai:true,requestId:'receipt',source:h.source})
})
it('never labels a calculated fallback as AI analysis',async()=>{
 const h=saveMoment(match,{...event,outcome:'own_goal'})
 const fetcher=vi.fn().mockResolvedValueOnce({ok:true,json:async()=>({cutoff:{period:1,elapsed_ms:3000}})}).mockResolvedValueOnce({ok:true,json:async()=>({status:'answered',mode:'azure',request_id:'receipt',narrative:{mode:'calculated',blocks:[]},text:['Score changed.']})})
 vi.stubGlobal('fetch',fetcher)
 await expect(requestSummary(h,new AbortController().signal)).rejects.toThrow(/verify/)
 expect(JSON.parse(fetcher.mock.calls[1][1].body).question).toBe('What happened in this moment?')
})
it('deduplicates in-flight imports and keeps the replay when the provider fails',async()=>{
 const h=saveMoment(match,event);let resolve:(value:unknown)=>void=()=>{}
 const fetcher=vi.fn(()=>new Promise(r=>{resolve=r}));vi.stubGlobal('fetch',fetcher)
 const first=generateSummary(h),second=generateSummary(h)
 expect(first).toBe(second);expect(fetcher).toHaveBeenCalledTimes(1)
 resolve({ok:false});await first
 expect(readCollection()[0].id).toBe(h.id);expect(readCollection()[0].summary).toBeUndefined()
})
