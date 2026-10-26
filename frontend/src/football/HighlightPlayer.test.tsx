import {act,cleanup,fireEvent,render,screen,waitFor,within} from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import {HighlightPlayer} from './HighlightPlayer'
import {CAREER_CHANGED,watchCareerRevisions} from './revisions'
import {defaults} from '../../../integrations/personalization/client'
import type {Highlight,HighlightContext,Replay,World} from './data'

vi.mock('../assistant/AskFootie',()=>({AskFootie:({context}:{context:{eventRevision?:number;throughSequence?:number}})=><button data-event-revision={context.eventRevision} data-through-sequence={context.throughSequence}>Ask Footie</button>}))

const clubs=[{club_id:'redhaven',name:'Redhaven',short_name:'RH',featured:true,primary_color:'#193e33'},{club_id:'southbank',name:'Southbank',short_name:'SB',featured:true,primary_color:'#713348'}]
const players=[{player_id:'rh04',club_id:'redhaven',name:'Luca Bennett',role:'DF' as const,number:4,featured:true,star:false,birth_year:1997,debut_year:2017},{player_id:'rh09',club_id:'redhaven',name:'Mateo Cross',role:'FW' as const,number:9,featured:true,star:true,birth_year:1997,debut_year:2017},{player_id:'sb01',club_id:'southbank',name:'Leon Finch',role:'GK' as const,number:1,featured:true,star:false,birth_year:1997,debut_year:2017}]
const world:World={catalog:{clubs,seasons:['2026-27'],counts:{featured_clubs:2,featured_players:3}},players,asOf:'2026-10-20T00:00:00Z',throughDate:'2026-10-19'}
const teams=[{team_id:'southbank',name:'Southbank',player_ids:['sb01']},{team_id:'redhaven',name:'Redhaven',player_ids:['rh04','rh09']}]
const highlight:Highlight={highlight_id:'equalizer',match_id:'match',title:'Mateo Cross brings Redhaven level',tag:'Match',player_ids:['rh09'],club_ids:['redhaven'],relevance:{reason:'favorite',score:1},action:{kind:'replay',subject_id:'match',label:'Watch',replay_url:'/api/data/highlights/equalizer/replay'}}
const initialContext:HighlightContext={highlight_id:'equalizer',match_id:'match',teams,active_player_ids:players.map(p=>p.player_id),period_lengths_ms:[2700000,2700000],initial_cutoff:{period:2,elapsed_ms:999},original_cutoff:{period:2,elapsed_ms:9500},latest_cutoff:{period:2,elapsed_ms:9500},original_sequence:3,latest_sequence:3,replay_available:true,review_available:true,goal:{event_id:'goal',revision:1,retracted:false,occurred_at:{period:2,elapsed_ms:9000},available_at:{period:2,elapsed_ms:9500}},content_version:'original'}
const replay:Replay={match_id:'match',teams,initial_state:{at:{period:2,elapsed_ms:999},score:{southbank:0,redhaven:0}},events:[
 {schema_version:'1.0',match_id:'match',event_id:'pass',revision:1,source_delivery_sequence:1,occurrence_order:1,occurred_at:{period:2,elapsed_ms:1000},available_at:{period:2,elapsed_ms:2000},actor:{team_id:'redhaven',player_id:'rh04'},position:{x:60,y:34},action:{kind:'pass',outcome:'completed',end_position:{x:80,y:34},recipient:{team_id:'redhaven',player_id:'rh09'}}},
 {schema_version:'1.0',match_id:'match',event_id:'goal',revision:1,source_delivery_sequence:3,occurrence_order:2,occurred_at:{period:2,elapsed_ms:9000},available_at:{period:2,elapsed_ms:9500},actor:{team_id:'redhaven',player_id:'rh09'},position:{x:90,y:34},action:{kind:'shot',outcome:'goal',end_position:{x:105,y:34}}},
]}
const originalText='Luca Bennett completed 1 pass in the buildup to Mateo Cross’s goal.'
const correctedText='The buildup to Mateo Cross’s goal includes 2 completed passes.'
let context:HighlightContext,version:number,contextFailure:boolean,replayFailure:boolean
let available:Record<number,number>
let requests:{url:string;body:any}[],contextReads:number,contextGate:((r:Response)=>void)|null
let deferredFanSequence:number|null,pendingFan:(()=>void)|null
const dataset='a'.repeat(64)
let sockets:Socket[]=[]
class Socket{
 onopen:(()=>void)|null=null;onmessage:((e:{data:string})=>void)|null=null;onerror:(()=>void)|null=null;onclose:(()=>void)|null=null
 constructor(public url:string){sockets.push(this)}
 close(){this.onclose?.()}
}
const reply=(data:unknown,status=200)=>new Response(JSON.stringify(data),{status,headers:{'Content-Type':'application/json'}})
const changed=()=>window.dispatchEvent(new CustomEvent(CAREER_CHANGED,{detail:{matches:['match'],datasetChanged:false}}))
function revise(next:number,at=next===4?10000:next===5?11000:12000){
 available[next]=at
 version=next;context={...context,replay_available:false,latest_sequence:next,latest_cutoff:{period:2,elapsed_ms:at},content_version:`revision-${next}`,goal:{...context.goal,revision:next>=5?next-3:1,retracted:next===5,available_at:{period:2,elapsed_ms:next>=5?at:9500}}}
}
function setup(follow=true){
 const prefs={...defaults(),favorite_player_ids:follow?['rh04']:[],focus_player_id:follow?'rh04':null}
 const update=vi.fn()
 return {update,...render(<HighlightPlayer highlight={highlight} world={world} prefs={prefs} update={update} close={vi.fn()}/>)}
}
async function atGoal(){
 const slider=await screen.findByRole('slider',{name:'Highlight progress'})
 fireEvent.change(slider,{target:{value:slider.getAttribute('max')}})
 await screen.findByRole('heading',{name:originalText})
}
beforeEach(()=>{
 context=structuredClone(initialContext);version=3;available={};contextFailure=false;replayFailure=false;requests=[];contextReads=0;contextGate=null;deferredFanSequence=null;pendingFan=null;sockets=[]
 localStorage.clear()
 Object.defineProperty(HTMLDialogElement.prototype,'showModal',{configurable:true,value:vi.fn(function(this:HTMLDialogElement){this.open=true})})
 Object.defineProperty(HTMLDialogElement.prototype,'close',{configurable:true,value:vi.fn(function(this:HTMLDialogElement){this.open=false})})
 vi.stubGlobal('matchMedia',vi.fn(()=>({matches:true,addEventListener:vi.fn(),removeEventListener:vi.fn()})))
 vi.stubGlobal('WebSocket',Socket)
 vi.stubGlobal('fetch',vi.fn(async(input:RequestInfo|URL,options?:RequestInit)=>{
  const url=String(input),body=options?.body?JSON.parse(String(options.body)):null;requests.push({url,body})
  if(url==='/api/data/revisions')return reply({dataset,generation:Math.max(0,version-3),enabled:true,matches:version>3?{match:version-3}:{}})
  if(url==='/api/data/revisions/negotiate')return reply({enabled:true,url:'wss://test.webpubsub.azure.com/client?access_token=test'})
  if(url.endsWith('/context')){contextReads++;if(contextGate)return new Promise<Response>(resolve=>{contextGate=resolve});return reply(context,contextFailure?503:200)}
  if(url.endsWith('/replay'))return reply(replay,!context.replay_available?409:replayFailure?503:200)
  if(url==='/api/fan/matches/match'){
   const selected=Math.max(3,...Object.keys(available).map(Number).filter(seq=>seq<=body.through_sequence&&body.cutoff.elapsed_ms>=available[seq])),time=body.cutoff.elapsed_ms
   const goalVisible=time>=9500&&selected!==5
   const updated=selected===4
   const text=updated?correctedText:originalText
   const result=reply({version:'fan-personalization-v1',request_id:body.request_id,preferences:body.preferences,preference_id:'audience',dataset_id:dataset,facts:{score:{southbank:0,redhaven:goalVisible?1:0},players:{}},cards:goalVisible?[{id:'match:goal:buildup',kind:'goal_buildup',title:updated?'How the goal happened':'Your player in the buildup',text,action:{kind:'profile',subject_id:'rh04',label:'See player'},ask_footie:{question:'What made that goal happen?',match_id:'match',event_id:'goal',event_revision:selected>=6?3:1,cutoff:body.cutoff,label:'Goal'}}]:[],focus:{active_player_ids:players.map(p=>p.player_id),status:'active',player_id:'rh04'},view_id:`${selected}`})
   if(body.through_sequence===deferredFanSequence)return new Promise<Response>(resolve=>{pendingFan=()=>resolve(result)})
   return result
  }
  throw new Error(`Unexpected request ${url}`)
 }))
})
afterEach(()=>{cleanup();vi.unstubAllGlobals();vi.restoreAllMocks()})

it('withdraws revised animation but preserves the paused observation until review is explicit',async()=>{
 setup();await atGoal();const user=userEvent.setup()
 expect(screen.getByRole('button',{name:'Ask Footie'})).toBeTruthy()
 expect(screen.getByRole('button',{name:'Ask Footie'}).getAttribute('data-through-sequence')).toBe('3')
 act(()=>{revise(4);changed()})
 await screen.findByRole('button',{name:/Review update/})
 await screen.findByRole('heading',{name:originalText})
 expect(screen.queryByRole('group',{name:'Highlight pitch with all active players'})).toBeNull()
 expect(screen.queryByRole('button',{name:'Ask Footie'})).toBeNull()
 expect(screen.getByRole('heading',{name:'Southbank × Redhaven'})).toBeTruthy()
 expect(requests.filter(r=>r.body).at(-1)?.body).toMatchObject({cutoff:{period:2,elapsed_ms:9500},through_sequence:3})
 await user.click(screen.getByRole('button',{name:/Review update/}))
 await screen.findByRole('heading',{name:correctedText})
 expect(requests.filter(r=>r.body).at(-1)?.body).toMatchObject({cutoff:{period:2,elapsed_ms:10000},through_sequence:4})
 expect(screen.queryByRole('button',{name:/Review update/})).toBeNull()
 expect(screen.getByRole('button',{name:'Ask Footie'})).toBeTruthy()
 expect(screen.getByRole('button',{name:'Ask Footie'}).getAttribute('data-through-sequence')).toBe('4')
 await user.click(screen.getByRole('button',{name:'Return to original moment'}))
 await screen.findByRole('heading',{name:originalText})
 expect(requests.filter(r=>r.body).at(-1)?.body.through_sequence).toBe(3)
 expect(requests.filter(r=>r.url.endsWith('/replay'))).toHaveLength(1)
})

it('keeps cards available across retraction, duplicate and restoration without advancing either snapshot',async()=>{
 setup();await atGoal();const user=userEvent.setup()
 act(()=>{revise(5);changed()});await user.click(await screen.findByRole('button',{name:/Review update/}))
 await screen.findByText('No active insight at this point in the match.')
 expect(screen.queryByRole('button',{name:'Ask Footie'})).toBeNull()
 act(()=>changed())
 await screen.findByText('No active insight at this point in the match.')
 expect(screen.queryByRole('button',{name:/Review update/})).toBeNull()
 act(()=>{revise(6);changed()})
 await screen.findByRole('button',{name:/Review update/})
 await screen.findByText('No active insight at this point in the match.')
 expect(requests.filter(r=>r.body).at(-1)?.body).toMatchObject({cutoff:{period:2,elapsed_ms:11000},through_sequence:5})
 await user.click(screen.getByRole('button',{name:/Review update/}))
 await screen.findByRole('heading',{name:originalText})
 expect(screen.getAllByRole('heading',{name:originalText})).toHaveLength(1)
 expect(screen.getByRole('button',{name:'Ask Footie'}).getAttribute('data-event-revision')).toBe('3')
 expect(requests.filter(r=>r.body).at(-1)?.body).toMatchObject({cutoff:{period:2,elapsed_ms:12000},through_sequence:6})
 expect(screen.queryByRole('group',{name:'Highlight pitch with all active players'})).toBeNull()
 expect(requests.some(r=>r.url.includes('/assistant/ask'))).toBe(false)
})

it('offers equal-clock revisions using sequence ceilings and never silently rewrites the historical card',async()=>{
 setup();await atGoal();act(()=>{revise(5,9500);changed()})
 await screen.findByRole('button',{name:/Review update/});await screen.findByRole('heading',{name:originalText})
 expect(requests.filter(r=>r.body).at(-1)?.body).toMatchObject({cutoff:{period:2,elapsed_ms:9500},through_sequence:3})
 await userEvent.setup().click(screen.getByRole('button',{name:/Review update/}))
 await screen.findByText('No active insight at this point in the match.')
 expect(requests.filter(r=>r.body).at(-1)?.body).toMatchObject({cutoff:{period:2,elapsed_ms:9500},through_sequence:5})
})

it('opens historical and updated insight views even when the initial replay returns409',async()=>{
 revise(5);setup()
 await screen.findByRole('heading',{name:originalText})
 expect(screen.getByRole('combobox',{name:'Highlight player focus'})).toBeTruthy()
 expect(screen.queryByText('This highlight couldn’t be loaded.')).toBeNull()
 await userEvent.setup().click(screen.getByRole('button',{name:/Review update/}))
 await screen.findByText('No active insight at this point in the match.')
})

it('keeps the last observation through a failed context read and recovers without resetting favorites',async()=>{
 const {update}=setup();await atGoal();act(()=>{revise(4);contextFailure=true;changed()})
 await screen.findByRole('heading',{name:'Update unavailable'})
 expect(screen.queryByRole('button',{name:/Review update/})).toBeNull()
 expect(screen.queryByRole('group',{name:'Highlight pitch with all active players'})).toBeNull()
 await screen.findByRole('heading',{name:originalText})
 contextFailure=false;await userEvent.setup().click(screen.getByRole('button',{name:'Try again'}))
 await screen.findByRole('button',{name:/Review update/})
 expect((screen.getByRole('combobox',{name:'Highlight player focus'}) as HTMLSelectElement).value).toBe('rh04')
 expect(update).not.toHaveBeenCalled()
})

it('recovers missed socket updates by authoritative polling without changing the selected observation',async()=>{
 setup();await atGoal();const stop=watchCareerRevisions()
 try{
  await waitFor(()=>expect(sockets).toHaveLength(1))
  sockets[0].close();const before=contextReads
  act(()=>{revise(4);document.dispatchEvent(new Event('visibilitychange'))})
  await screen.findByRole('button',{name:/Review update/})
  await screen.findByRole('heading',{name:originalText})
  expect(contextReads).toBeGreaterThan(before)
  expect(requests.filter(r=>r.body).at(-1)?.body.through_sequence).toBe(3)
  act(()=>document.dispatchEvent(new Event('visibilitychange')))
  await waitFor(()=>expect(requests.filter(r=>r.url==='/api/data/revisions').length).toBeGreaterThanOrEqual(3))
  expect(within(screen.getByRole('complementary',{name:'Moment insights'})).getAllByRole('heading',{name:originalText})).toHaveLength(1)
 }finally{stop()}
})

it('ignores a late context response after a newer correction has been reviewed',async()=>{
 setup();await atGoal()
 contextGate=()=>{}
 act(()=>changed())
 await waitFor(()=>expect(contextReads).toBe(2))
 const finish=contextGate!;contextGate=null
 act(()=>{revise(5);changed()})
 await userEvent.setup().click(await screen.findByRole('button',{name:/Review update/}))
 await screen.findByText('No active insight at this point in the match.')
 await act(async()=>finish(reply(initialContext)))
 expect(screen.queryByRole('group',{name:'Highlight pitch with all active players'})).toBeNull()
 expect(screen.queryByRole('heading',{name:originalText})).toBeNull()
 expect(screen.queryByRole('button',{name:/Review update/})).toBeNull()
})

it('does not offer a later observation when only an unrelated later play invalidates the replay',async()=>{
 setup();await screen.findByRole('slider',{name:'Highlight progress'})
 act(()=>{context={...context,replay_available:false,content_version:'later-unrelated-change'};changed()})
 await screen.findByRole('heading',{name:'The play has been updated'})
 expect(screen.queryByRole('button',{name:/Review update/})).toBeNull()
 expect(requests.filter(r=>r.body).at(-1)?.body).toMatchObject({cutoff:{period:2,elapsed_ms:999},through_sequence:3})
})

it('keeps the validated replay score visible during ordinary insight reads',async()=>{
 deferredFanSequence=3;setup()
 const slider=await screen.findByRole('slider',{name:'Highlight progress'})
 expect(screen.getByLabelText('Score at 45:00').querySelector('strong')?.textContent).toBe('0 – 045:00')
 fireEvent.change(slider,{target:{value:slider.getAttribute('max')}})
 expect(screen.getByLabelText('Score at 45:09').querySelector('strong')?.textContent).toBe('0 – 145:09')
})

it('never substitutes an old replay score while an updated observation is loading',async()=>{
 setup();await atGoal();act(()=>{revise(5);changed()})
 await screen.findByRole('button',{name:/Review update/})
 deferredFanSequence=5
 await userEvent.setup().click(screen.getByRole('button',{name:/Review update/}))
 await waitFor(()=>expect(pendingFan).not.toBeNull())
 expect(screen.getByLabelText('Score at 45:11').querySelector('strong')?.textContent).toBe('— – —45:11')
 await act(async()=>pendingFan!())
 expect(screen.getByLabelText('Score at 45:11').querySelector('strong')?.textContent).toBe('0 – 045:11')
})

it('offers Clubhouse for a late update outside the playable observation range without clamping the clock',async()=>{
 setup();await atGoal()
 act(()=>{revise(5,2900000);context.review_available=false;changed()})
 await screen.findByText('The later update is available in Clubhouse.')
 expect(screen.queryByRole('button',{name:/Review update/})).toBeNull()
 expect(screen.getByRole('link',{name:/View player/}).getAttribute('href')).toBe('#football/player/rh04')
 expect(requests.filter(r=>r.body).at(-1)?.body).toMatchObject({cutoff:{period:2,elapsed_ms:9500},through_sequence:3})
 await screen.findByRole('heading',{name:originalText})
})

it('never moves behind the start when an animation callback predates effect setup',async()=>{
 const callbacks:FrameRequestCallback[]=[]
 vi.stubGlobal('matchMedia',vi.fn(()=>({matches:false,addEventListener:vi.fn(),removeEventListener:vi.fn()})))
 vi.stubGlobal('requestAnimationFrame',vi.fn((callback:FrameRequestCallback)=>{callbacks.push(callback);return callbacks.length}))
 vi.stubGlobal('cancelAnimationFrame',vi.fn())
 vi.spyOn(performance,'now').mockReturnValue(100)
 setup()
 const slider=await screen.findByRole('slider',{name:'Highlight progress'}) as HTMLInputElement
 await waitFor(()=>expect(callbacks.length).toBeGreaterThan(0))
 act(()=>callbacks.at(-1)!(50))
 expect(slider.value).toBe('0')
 expect(screen.queryByText(/^-1\s*\//)).toBeNull()
 expect(requests.filter(r=>r.body).at(-1)?.body.cutoff).toEqual({period:2,elapsed_ms:999})
})

it('focuses the first actor rather than the first goalkeeper when no favorite is selected',async()=>{
 context.active_player_ids=['sb01','rh04','rh09'];setup(false)
 await screen.findByRole('slider',{name:'Highlight progress'})
 expect((screen.getByRole('combobox',{name:'Highlight player focus'}) as HTMLSelectElement).value).toBe('rh04')
})

it('uses the goal actor as a relevant focus when the replay is unavailable on opening',async()=>{
 revise(5);context.active_player_ids=['sb01','rh04','rh09'];context.goal.player_id='rh09';setup(false)
 await screen.findByRole('button',{name:/Review update/})
 expect((screen.getByRole('combobox',{name:'Highlight player focus'}) as HTMLSelectElement).value).toBe('rh09')
})
