import {afterEach,expect,it} from 'vitest'
import {cleanup,render,screen} from '@testing-library/react'
import {readFileSync} from 'node:fs'
import {resolve} from 'node:path'
import {PreloadedSummary,verifiedSummary} from './PreloadedSummary'
import {replayGallery} from '../matchday/replayGallery'
import type {Event} from '../types'
const names:Record<string,string>={'last-gasp':'last_gasp','one-touch':'one_touch','breakaway':'breakaway','level-first':'level-first','take-lead':'take-lead','level-late':'level-late'}
function fixture(id:string){
 const d=JSON.parse(readFileSync(resolve(process.cwd(),`../fixtures/showcases/${names[id]}.json`),'utf8'))
 const events:Event[]=d.events.map((e:Event)=>({...e,action:{...e.action,...(e.action.kind==='pass'?{technique:e.action.technique??'ground'}:{}),...(e.action.kind==='shot'?{situation:e.action.situation??'open_play'}:{})}}))
 const score={...d.initial_state.score}
 events.filter(e=>e.action.outcome==='goal').forEach(e=>score[e.actor.team_id]++)
 return {events,score}
}
afterEach(cleanup)
it('provides a source-matching prepared AI summary for every preloaded highlight',()=>{
 expect(Object.keys(names).sort()).toEqual(Object.keys(replayGallery).sort())
 for(const id of Object.keys(names)){
  const {events,score}=fixture(id)
  expect(verifiedSummary(id,events,score)?.text.length,id).toBeGreaterThan(0)
 }
})
it('withholds summaries after revisions, action changes, missing events or score corrections',()=>{
 const {events,score}=fixture('level-first')
 expect(verifiedSummary('level-first',events.slice(1),score)).toBeNull()
 expect(verifiedSummary('level-first',events,{...score,eastbridge:3})).toBeNull()
 expect(verifiedSummary('level-first',events.map((e,i)=>i===0?{...e,revision:2}:e),score)).toBeNull()
 expect(verifiedSummary('level-first',events.map((e,i)=>i===0?{...e,position:{x:60,y:20}}:e),score)).toBeNull()
})
it('renders a separate readable card without making a paid request',()=>{
 const {events,score}=fixture('level-first')
 render(<PreloadedSummary storyId="level-first" events={events} score={score}/>)
 expect(screen.getByRole('region',{name:'Highlight AI summary'})).toBeTruthy()
 expect(screen.getByRole('heading',{name:"Footie's Summary"})).toBeTruthy()
 expect(screen.queryByRole('button')).toBeNull()
})
