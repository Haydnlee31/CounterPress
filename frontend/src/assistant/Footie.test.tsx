import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import Footie,{AnswerVisual} from './Footie'
const requests:any[]=[]
let fail=false,pending:((value:Response)=>void)|null=null,delay=false
const plan={operation:'stats',player_ids:['rh09'],club_id:null,match_id:null,metric:'goals',per90:false,season:null,comparison_season:null}
const answer={request_id:'one',status:'answered',title:'From the match records',text:['Mateo Cross · career: 75 goals.'],facts:[{subject_name:'Mateo Cross',label:'Goals',value:75,unit:'count',scope:{season:null,matches:140,window:'whole_period'},coverage:{recorded_matches:140,total_matches:140},evidence:{matches:[]},href:'#football/player/rh09'}],actions:[{label:'View Mateo Cross',href:'#football/player/rh09'}],visual:null,plan,as_of:'2026-10-20T00:00:00Z',mode:'lookup',suggestions:['And last season?']}
const reply=(data:unknown,status=200)=>new Response(JSON.stringify(data),{status})
beforeEach(()=>{
 requests.length=0;fail=false;delay=false;pending=null;window.localStorage.clear();window.history.replaceState({},'','#assistant')
 vi.stubGlobal('fetch',vi.fn(async(url:RequestInfo|URL,options?:RequestInit)=>{
  const path=String(url)
  if(path==='/api/data/catalog')return reply({clubs:[{club_id:'redhaven',name:'Redhaven',featured:true}],seasons:['2026-27','2025-26'],counts:{featured_players:1,featured_clubs:1}})
  if(path.startsWith('/api/data/players?'))return reply({items:path.includes('offset=100')?[]:[{player_id:'rh09',name:'Mateo Cross',club_id:'redhaven',role:'FW',featured:true}]})
  if(path.startsWith('/api/data/matches?'))return reply({items:[{match_id:'showcase',period_lengths_ms:[2820000,2880000],kickoff:'2026-10-19T15:00:00Z',home_id:'redhaven',away_id:'redhaven'}]})
  if(path==='/api/fan/assistant/config')return reply({natural_language:false})
  if(path==='/api/fan/assistant/ask'){
   requests.push(JSON.parse(options?.body as string))
   if(delay)return new Promise<Response>(resolve=>{pending=resolve})
   return reply({...answer,request_id:String(requests.length)},fail?503:200)
  }
  throw new Error('Unexpected request '+path)
 }))
})
afterEach(()=>{cleanup();vi.unstubAllGlobals();vi.restoreAllMocks()})
it('keeps incomplete investigation disclosure visible with the direct answer',async()=>{
 const user=userEvent.setup();delay=true;render(<Footie/>);
 await user.click(await screen.findByRole('button',{name:/01.*How many goals does Mateo Cross/}))
 await screen.findByRole('button',{name:'Cancel'})
 const notice='I could not complete the full analysis. These direct statistics may answer only part of your question.'
 pending?.(reply({...answer,mode:'lookup_fallback',text:[...answer.text,notice],
  narrative:{mode:'calculated',blocks:[],fallback_reason:'research_unavailable'},
  research:{partial:true,unavailable:['orchestrator']}}))
 const visibleNotice=await screen.findByText(notice)
 expect(visibleNotice.closest('details')).toBeNull()
 expect(screen.getByText('Mateo Cross · career: 75 goals.')).toBeTruthy()
 expect(screen.getByRole('link',{name:/View Mateo Cross/})).toBeTruthy()
})
it('opens a suggested answer, exposes readable evidence and follows up with bounded context',async()=>{
 const user=userEvent.setup();render(<Footie/>);
 await user.click(await screen.findByRole('button',{name:/01.*How many goals does Mateo Cross/}))
 await screen.findByText('Mateo Cross · career: 75 goals.')
 expect(requests[0].as_of).toBe('2026-10-20T00:00:00Z')
 await user.click(screen.getByText(/Check the numbers/));expect(screen.getByText(/140\/140 recorded appearances/)).toBeTruthy()
 expect(screen.getByRole('link',{name:/View Mateo Cross/}).getAttribute('href')).toBe('#football/player/rh09')
 await user.click(screen.getByRole('button',{name:/And last season/}));await waitFor(()=>expect(requests.length).toBe(2));expect(requests[1].previous_plan).toEqual(plan)
 await user.click(screen.getByRole('button',{name:/New conversation/}));expect(screen.queryByText('Mateo Cross · career: 75 goals.')).toBeNull()
})
it('preserves a failed question for retry and never persists conversation',async()=>{
 const user=userEvent.setup();fail=true;render(<Footie/>);
 const field=await screen.findByRole('textbox',{name:'Ask a football question'});await user.type(field,'How many goals does Mateo Cross have?');await user.click(screen.getByRole('button',{name:'Send question'}))
 await screen.findByRole('alert');fail=false;await user.click(screen.getByRole('button',{name:'Try again'}));await screen.findByText('Mateo Cross · career: 75 goals.')
 expect(requests[0].question).toBe(requests[1].question);expect(localStorage.length).toBe(0)
})
it('cancels a pending response when context changes',async()=>{
 const user=userEvent.setup();delay=true;render(<Footie/>);await user.click(await screen.findByRole('button',{name:/01.*How many goals does Mateo Cross/}))
 await screen.findByRole('button',{name:'Cancel'});expect(document.querySelector('.ft-thinking [data-mood="thinking"]')).toBeTruthy()
 await user.selectOptions(screen.getByRole('combobox',{name:'Player context'}),'rh09')
 pending?.(reply(answer));await waitFor(()=>expect(screen.queryByRole('button',{name:'Cancel'})).toBeNull());expect(screen.queryByText('Mateo Cross · career: 75 goals.')).toBeNull()
 expect(document.querySelector('[data-mood="thinking"]')).toBeNull()
})
it('shows null chart values as unavailable and labels the visual',()=>{
 render(<AnswerVisual visual={{kind:'bars',label:'Saves',items:[{label:'Player A',value:null,unit:'count'},{label:'Player B',value:3,unit:'count'}]}}/>);
 expect(screen.getByText('—')).toBeTruthy();expect(screen.getByText('Saves')).toBeTruthy()
})
it('keeps the buildup collapsed and exposes readable timed actions without dummy links',async()=>{
 const user=userEvent.setup()
 render(<AnswerVisual visual={{kind:'timeline',label:'Follow the buildup',items:[
  {event_id:'regain',revision:1,time_label:'58:02',label:'Rory Ellis',detail:'Won possession'},
  {event_id:'pass',revision:2,time_label:'58:05',label:'Dario Voss',detail:'Pass to Mateo Cross'},
  {event_id:'shot',revision:1,time_label:'58:09',label:'Mateo Cross',detail:'Goal'},
 ]}}/>)
 const summary=screen.getByText('Follow the buildup',{selector:'summary span'})
 expect(summary.closest('details')?.open).toBe(false)
 await user.click(summary)
 expect(screen.getByRole('list',{name:'Follow the buildup'})).toBeTruthy()
 expect(screen.getAllByRole('listitem')).toHaveLength(3)
 expect(screen.getByText('58:05')).toBeTruthy()
 expect(screen.getByText('Pass to Mateo Cross')).toBeTruthy()
 expect(screen.queryByRole('link')).toBeNull()
})
it('shows seconds and metres without dropping a zero or inventing a missing value',()=>{
 render(<AnswerVisual visual={{kind:'groups',label:'Buildup measures',groups:[
  {kind:'bars',label:'Elapsed time',items:[{label:'Regain to shot',value:0,unit:'seconds'}]},
  {kind:'bars',label:'Forward movement',items:[{label:'Recorded advance',value:12,unit:'metres'},{label:'Unknown start',value:null,unit:'metres'}]},
 ]}}/>)
 expect(screen.getByText('0 s')).toBeTruthy()
 expect(screen.getByText('12 m')).toBeTruthy()
 expect(screen.getByText('—')).toBeTruthy()
})
it('leads with the grounded story while keeping the original figures and evidence inspectable',async()=>{
 const original=vi.mocked(fetch).getMockImplementation()!
 vi.mocked(fetch).mockImplementation(async(url,options)=>{
  if(String(url)==='/api/fan/assistant/ask')return reply({...answer,narrative:{mode:'azure_selected',blocks:[{id:'c1',text:'Mateo Cross averages 0.54 goals per appearance: 75 in 140 appearances.',fact_indices:[0],evidence_id:'bound-evidence'}]}})
  return original(url,options)
 })
 const user=userEvent.setup();render(<Footie/>)
 await user.click(await screen.findByRole('button',{name:/01.*How many goals does Mateo Cross/}))
 await screen.findByText('Mateo Cross averages 0.54 goals per appearance: 75 in 140 appearances.')
 await user.click(screen.getByText('Figures and context'))
 expect(screen.getByText('Mateo Cross · career: 75 goals.').closest('details')?.open).toBe(true)
 await user.click(screen.getByText(/Check the numbers/))
 expect(screen.getByText(/140\/140 recorded appearances/)).toBeTruthy()
 expect(screen.getByRole('link',{name:/View Mateo Cross/}).getAttribute('href')).toBe('#football/player/rh09')
})
it('does not send on open and keeps the embedded player season despite a different favourite',async()=>{
 const user=userEvent.setup()
 render(<Footie context={{label:'Mateo Cross',question:'How many goals does Mateo Cross have?',playerId:'rh09',season:'2025-26',asOf:'2026-10-20T00:00:00Z'}}/>)
 const input=await screen.findByRole('textbox',{name:'Ask a football question'})
 expect((input as HTMLTextAreaElement).value).toContain('Mateo Cross')
 expect(requests).toHaveLength(0)
 await user.click(screen.getByRole('button',{name:'Send question'}))
 await waitFor(()=>expect(requests).toHaveLength(1))
 expect(requests[0]).toMatchObject({player_id:'rh09',season:'2025-26',cutoff:null,event_id:null})
})
it('sends the frozen moment time and source revision instead of full-time career context',async()=>{
 const user=userEvent.setup()
 render(<Footie context={{label:'Match moment',question:'What happened in this moment?',matchId:'showcase',cutoff:{period:1,elapsed_ms:1234},eventId:'e9',eventRevision:2}}/>)
 await screen.findByRole('textbox',{name:'Ask a football question'})
 expect(requests).toHaveLength(0)
 await user.click(screen.getByRole('button',{name:'Send question'}))
 await waitFor(()=>expect(requests).toHaveLength(1))
 expect(requests[0]).toMatchObject({match_id:'showcase',cutoff:{period:1,elapsed_ms:1234},event_id:'e9',event_revision:2,player_id:null,season:null})
})
it('clears outdated answers and cancels late replies after a career correction without asking again',async()=>{
 const user=userEvent.setup();render(<Footie/>);
 await user.click(await screen.findByRole('button',{name:/01.*How many goals does Mateo Cross/}))
 await screen.findByText('Mateo Cross · career: 75 goals.')
 delay=true
 await user.click(screen.getByRole('button',{name:/And last season/}))
 await waitFor(()=>expect(pending).not.toBeNull())
 fireEvent(window,new CustomEvent('footie:records-changed',{detail:{matches:['showcase'],datasetChanged:false}}))
 await screen.findByText('The match records have changed. Ask again for the latest figures.')
 pending!(reply(answer))
 await waitFor(()=>expect(screen.queryByText('Mateo Cross · career: 75 goals.')).toBeNull())
 expect(requests).toHaveLength(2)
 expect(screen.queryByRole('button',{name:'Cancel'})).toBeNull()
})

it('renders separate scales for compound answers without turning missing figures into zero',()=>{
 render(<AnswerVisual visual={{kind:'groups',label:'Measures at a glance',groups:[
  {kind:'bars',label:'Goals',items:[{label:'Mateo Cross · Career',value:75,unit:'count'},{label:'Rory Ellis · Career',value:51,unit:'count'}]},
  {kind:'bars',label:'Pass completion',items:[{label:'Mateo Cross · Career',value:82,unit:'percent'},{label:'Rory Ellis · Career',value:null,unit:'percent'}]},
 ]}}/>);
 expect(screen.getByRole('region',{name:'Measures at a glance'})).toBeTruthy()
 expect(screen.getByText('Goals')).toBeTruthy()
 expect(screen.getByText('Pass completion')).toBeTruthy()
 expect(screen.getByText('82%')).toBeTruthy()
 expect(screen.getByText('—')).toBeTruthy()
 const charts=screen.getAllByRole('figure')
 expect(charts).toHaveLength(2)
 expect(charts[0].querySelector('.ft-track span')?.getAttribute('style')).toContain('100%')
 expect(charts[1].querySelector('.ft-track span')?.getAttribute('style')).toContain('100%')
})
it('keeps both question inputs individually labelled when a drawer opens above Footie',async()=>{
 render(<><Footie/><section aria-label="Embedded assistant"><Footie context={{playerId:'rh09',question:'How many goals does Mateo Cross have?',label:'Mateo Cross'}}/></section></>)
 await waitFor(()=>expect(screen.getAllByRole('textbox',{name:'Ask a football question'})).toHaveLength(2))
 const inputs=screen.getAllByRole('textbox',{name:'Ask a football question'}) as HTMLTextAreaElement[]
 expect(new Set(inputs.map(input=>input.id)).size).toBe(2)
 expect(inputs[1].value).toBe('How many goals does Mateo Cross have?')
 expect(requests).toHaveLength(0)
})

it('uses the recorded second-half duration for a completed match including added time',async()=>{
 const user=userEvent.setup();render(<Footie/>)
 await user.click(await screen.findByText('A match',{selector:'summary'}))
 await user.selectOptions(screen.getByRole('combobox',{name:'Match context'}),'showcase')
 await user.click(screen.getByRole('button',{name:/01.*What made that goal happen/}))
 await waitFor(()=>expect(requests).toHaveLength(1))
 expect(requests[0].cutoff).toEqual({period:2,elapsed_ms:2880000})
})
