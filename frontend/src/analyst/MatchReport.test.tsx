import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import {MatchReport} from './MatchReport'
const team=(club_id:string)=>({club_id,name:club_id,totals:{goals:1,shots:3,shot_goals:1,high_recoveries:2,pass_completion:80,known_passes:5,passes:6},cells:Array(18).fill(2),lanes:[{lane:'left',shots:3,goals:1,conversion:33.3},{lane:'centre',shots:0,goals:0,conversion:null}]})
const data={match_id:'match',source_id:'version',available:true,teams:[team('Home'),team('Away')],routes:[],facts:[{id:'fact',label:'Three attempts',value:3}]}
const claim={title:'A useful pattern',text:'The side found the box.',evidence_ids:['fact']}
const reading={headline:'A balanced contest',overview:claim,teams:['Home','Away'].map(club_id=>({club_id,strength:claim,weakness:claim,adjustment:claim,player:claim}))}
beforeEach(()=>{
 Object.defineProperty(HTMLDialogElement.prototype,'showModal',{configurable:true,value:vi.fn(function(this:HTMLDialogElement){this.open=true})})
 Object.defineProperty(HTMLDialogElement.prototype,'close',{configurable:true,value:vi.fn(function(this:HTMLDialogElement){this.open=false})})
 vi.stubGlobal('fetch',vi.fn(async(_url,init)=>new Response(JSON.stringify(init?.method==='POST'?{match_id:'match',source_id:'version',status:'complete',reading}:data))))
})
afterEach(()=>{cleanup();vi.unstubAllGlobals();vi.restoreAllMocks()})
it('generates the report when opened without an approval step',async()=>{
 render(<MatchReport matchId="match" language="en"/>);expect(fetch).not.toHaveBeenCalled()
 fireEvent.click(screen.getByRole('button',{name:'Match summary ↗'}));await screen.findByText('Where they played')
 await screen.findByText('A balanced contest');expect(fetch).toHaveBeenCalledTimes(2);expect(screen.queryByText('Approve deep analysis')).toBeNull();expect(screen.getByRole('img',{name:/18-zone/}).querySelectorAll('text')).toHaveLength(19)
 await screen.findByText('A balanced contest')
 expect(fetch).toHaveBeenLastCalledWith('/api/analyst/matches/match/report',expect.objectContaining({method:'POST',body:JSON.stringify({language:'en'})}))
 fireEvent.click(screen.getByRole('button',{name:'Away'}));expect(screen.getByRole('img',{name:/Away: 18-zone/})).toBeTruthy()
 fireEvent.click(screen.getByRole('button',{name:'Close match summary'}));expect(document.activeElement).toBe(screen.getByRole('button',{name:'Match summary ↗'}))
})
it('does not show a stale report after a source correction',async()=>{
 vi.mocked(fetch).mockImplementation(async(_url,init)=>new Response(JSON.stringify(init?.method==='POST'?{match_id:'match',source_id:'new-version',status:'complete',reading}:data)))
 render(<MatchReport matchId="match" language="en"/>);fireEvent.click(screen.getByRole('button',{name:'Match summary ↗'}))
 await waitFor(()=>expect(screen.getByRole('alert').textContent).toContain('Match records changed'))
 expect(screen.queryByText('A balanced contest')).toBeNull()
})
it('keeps the visual report available when the allowance is exhausted',async()=>{
 vi.mocked(fetch).mockImplementation(async(_url,init)=>new Response(JSON.stringify(init?.method==='POST'?{match_id:'match',source_id:'version',status:'budget_limit'}:data)))
 render(<MatchReport matchId="match" language="en"/>);fireEvent.click(screen.getByRole('button',{name:'Match summary ↗'}))
 await waitFor(()=>expect(screen.getByRole('alert').textContent).toContain('couldn’t finish'))
 expect(screen.getByText('Which routes paid off?')).toBeTruthy()
})

it('uses a readable dark loading state while deep analysis runs',async()=>{
 vi.mocked(fetch).mockImplementation(async(_url,init)=>init?.method==='POST'?new Promise<Response>(()=>{}):new Response(JSON.stringify(data)))
 const {container}=render(<MatchReport matchId="match" language="en"/>)
 fireEvent.click(screen.getByRole('button',{name:'Match summary ↗'}))
 await screen.findByText('Footie is connecting the patterns…');expect(container.querySelector('.mr-intro .footie-loading.is-dark.is-compact, .mr-intro .footie-loading.is-compact.is-dark')).toBeTruthy()
 expect(screen.getByText('Footie is connecting the patterns…')).toBeTruthy()
})

it('shows a concrete coaching task and lets the reader inspect its cited passage',async()=>{
 const route={id:'shot:test',club_id:'Away',player:'Avery Moss',period:1,elapsed_ms:3000,outcome:'blocked',goal:false,entry_lane:'left',shot_lane:'centre',points:[{x:60,y:10},{x:90,y:34}],actors:['Casey Vale','Avery Moss'],actions:['pass','shot']}
 const report={...reading,teams:reading.teams.map(t=>({...t,adjustment:{...claim,action:'Review the final pass with Moss before repeating the combination.',measure:'Count blocked and unblocked attempts after the return pass.',evidence_ids:['shot:test']}}))}
 vi.stubGlobal('matchMedia',vi.fn(()=>({matches:true})))
 vi.stubGlobal('requestAnimationFrame',(fn:FrameRequestCallback)=>{fn(0);return 1})
 const scroll=vi.fn();Object.defineProperty(Element.prototype,'scrollIntoView',{configurable:true,value:scroll})
 vi.mocked(fetch).mockImplementation(async(_url,init)=>new Response(JSON.stringify(init?.method==='POST'?{match_id:'match',source_id:'version',status:'complete',reading:report}:{...data,routes:[route]})))
 render(<MatchReport matchId="match" language="en"/>);fireEvent.click(screen.getByRole('button',{name:'Match summary ↗'}))
 await screen.findByText('Try this');expect(screen.getByText('Count blocked and unblocked attempts after the return pass.')).toBeTruthy()
 fireEvent.click(screen.getByRole('button',{name:'View 0:03 · Avery Moss ↗'}))
 expect(screen.getByRole('button',{name:'Away'}).getAttribute('aria-pressed')).toBe('true')
 expect(scroll).toHaveBeenCalledWith({behavior:'instant',block:'start'})
 expect(screen.getByRole('img',{name:'Avery Moss: linked build-up to blocked'})).toBeTruthy()
})
