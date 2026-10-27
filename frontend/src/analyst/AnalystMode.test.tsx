import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import AnalystMode from './AnalystMode'
import type {Snapshot} from './data'
import {defaults,preferenceKey} from '../../../integrations/personalization/client'

const state=vi.hoisted(()=>({value:{} as any,inputs:[] as any[]}))
vi.mock('./useAnalyst',()=>({useAnalyst:(...args:any[])=>{state.inputs=args;return state.value}}))
vi.mock('../gi/PlaySequence',()=>({PlaySequence:({hideObservation,fullMatch}:{hideObservation:boolean;fullMatch:boolean})=><div aria-label="Test replay">{hideObservation&&fullMatch?'Full match without duplicate observations':'Unexpected replay mode'}</div>}))
const clubs=[{club_id:'eastbridge',name:'Eastbridge'},{club_id:'northport',name:'Northport'}]
const snapshot:Snapshot={snapshot_id:'snapshot-one',match_id:'wyscout-2058017',cutoff:{period:1,elapsed_ms:600000},through_sequence:20,clubs,score:{eastbridge:0,northport:0},players:[{player_id:'eb09',name:'Rory Ellis',role:'FW',club_id:'eastbridge'}],evidence:[{id:'e1',event_id:'event1',revision:1,period:1,elapsed_ms:550000,club_id:'eastbridge',player_id:'eb09',kind:'shot',outcome:'on_target'}],signals:[{id:'s1',title:'Getting closer to goal',detail:'The latest shots came from inside the box.',evidence_ids:['e1'],metric_ids:['m1'],role:'chance',salience:90}],metrics:[
  {id:'m1',key:'shots',window:'prefix',role:'chance',label:'Shots',unit:'count',basis:'recorded_events',status:'available',value:4,club_id:'eastbridge'},
  {id:'m2',key:'shots',window:'prefix',role:'chance',label:'Shots',unit:'count',basis:'recorded_events',status:'available',value:2,club_id:'northport'},
  {id:'m3',key:'shot_speed',window:'prefix',role:'chance',label:'Shot speed',unit:'km/h',basis:'unavailable',status:'unavailable',value:null,club_id:'eastbridge'},
  {id:'m4',key:'heatmap',window:'prefix',role:'control',label:'Activity',unit:'locations',basis:'recorded_events',status:'available',value:{columns:12,rows:8,cells:[{column:4,row:3,count:3}]},club_id:'eastbridge'},
  {id:'m5',key:'shot_map',window:'prefix',role:'chance',label:'Shot map',unit:'locations',basis:'recorded_events',status:'available',value:{shots:[{event_id:'e1',x:92,y:34,outcome:'goal'}]},club_id:'eastbridge'},
]}
beforeEach(()=>{
  Object.defineProperty(HTMLDialogElement.prototype,'showModal',{configurable:true,value:vi.fn(function(this:HTMLDialogElement){this.open=true})})
  Object.defineProperty(HTMLDialogElement.prototype,'close',{configurable:true,value:vi.fn(function(this:HTMLDialogElement){this.open=false})})
  localStorage.clear();history.replaceState(null,'','/#analyst')
  state.value={config:{available:false,mode:'metrics',roles:[],interval_ms:60000},snapshot,analysis:null,pending:false,failed:false,metricsFailed:false,retryConfig:vi.fn(),retrySnapshot:vi.fn(),requestDiscussion:vi.fn()}
  vi.stubGlobal('fetch',vi.fn(async()=>new Response(JSON.stringify({match_id:'wyscout-2058017',events:[{}],players:[]}))))
})
afterEach(()=>{cleanup();vi.unstubAllGlobals();vi.restoreAllMocks()})

it('shows the shared room and four workspaces without inventing agent commentary',async()=>{
  render(<AnalystMode/>);await screen.findByText('Full match without duplicate observations')
  expect(screen.getByRole('heading',{name:'The conversation'})).toBeTruthy()
  for(const role of ['Player Analyst','Match Analyst','Chance Analyst','Defensive Analyst'])expect(screen.getByRole('heading',{name:role})).toBeTruthy()
  expect(screen.getByText('Live discussion is not connected in this preview. The statistics below follow the replay.')).toBeTruthy()
  expect(screen.queryByText('Match heatmap')).toBeNull() // Maps now appear with a relevant conversation or player focus.
  fireEvent.click(screen.getByRole('button',{name:'Explore Chance Analyst statistics'}))
  fireEvent.click(screen.getByText('Other measures'))
  expect(screen.getByText('Shot speed')).toBeTruthy();expect(screen.getByText('Not available')).toBeTruthy()
  expect(document.body.textContent).not.toContain('snapshot-one')
})

it('shows actual peer replies, their original source clock and expandable evidence',async()=>{
  state.value.config.discussion_available=true
  state.value.rounds=[{snapshot_id:'a1',cutoff:{period:1,elapsed_ms:540000},mode:'discussion',status:'complete',readings:[],summary:null,metrics:snapshot.metrics,evidence:snapshot.evidence,messages:[
    {id:'control',role:'control',text:'The activity has produced four shots.',reply_to:null,relation:'observation',metric_ids:['m1'],evidence_ids:[]},
    {id:'chance',role:'chance',text:'That activity includes an effort on target.',reply_to:'control',relation:'builds_on',metric_ids:[],evidence_ids:['e1']},
  ]}]
  render(<AnalystMode/>);await screen.findByText('Full match without duplicate observations')
  expect(screen.getByRole('log').textContent).toContain('Builds on Match Analyst')
  expect(screen.getAllByText('9:00').length).toBe(2)
  fireEvent.click(screen.getAllByText('See evidence')[1])
  expect(screen.getByText('Shot · on target')).toBeTruthy()
  fireEvent.click(screen.getByRole('button',{name:'Discuss this spell'}))
  expect(state.value.requestDiscussion).not.toHaveBeenCalled() // Replay is still at kick-off; no paid empty round.
})

it('keeps the new match selection in its own route and avoids result spoilers in the picker',async()=>{
  render(<AnalystMode/>);await screen.findByText('Full match without duplicate observations')
  const picker=screen.getByLabelText('Choose a match')
  expect(picker.querySelectorAll('option')).toHaveLength(3)
  expect(picker.textContent).not.toContain('4 – 2')
  fireEvent.change(picker,{target:{value:'wyscout-2058007'}})
  expect(location.hash).toBe('#analyst');expect(location.search).toBe('?match=wyscout-2058007')
  await waitFor(()=>expect(fetch).toHaveBeenCalledWith('/api/gi/matches/wyscout-2058007',expect.anything()))
})

it('labels a short early-game window by its actual bounds',async()=>{
  state.value.snapshot={...snapshot,cutoff:{period:1,elapsed_ms:120000},windows:{current:{period:1,start_ms:0,end_ms:120000,boundary:'(start,end]'}},metrics:snapshot.metrics.map(m=>({...m,window:'current'}))}
  render(<AnalystMode/>);await screen.findByText('Full match without duplicate observations')
  fireEvent.click(screen.getByRole('button',{name:'Explore Match Analyst statistics'}))
  fireEvent.click(screen.getByRole('button',{name:'Recent play'}))
  expect(screen.getAllByText('0:00 – 2:00 · First half').length).toBeGreaterThan(0)
  expect(document.body.textContent).not.toContain('Last 5 minutes')
})

it('does not turn missing player-map coverage into zero actions',async()=>{
  render(<AnalystMode/>);await screen.findByText('Full match without duplicate observations')
  fireEvent.click(screen.getByRole('button',{name:'Explore Player Analyst statistics'}))
  fireEvent.change(screen.getByLabelText('Map subject'),{target:{value:'player:eb09'}})
  expect(screen.getAllByText('Map unavailable for this view').length).toBeGreaterThan(0)
  expect(screen.queryByText('No recorded actions yet')).toBeNull()
})

it('renders a match-wide index once and keeps unknown pass outcomes neutral',async()=>{
  state.value.snapshot={...snapshot,metrics:[...snapshot.metrics,
    {id:'global',key:'momentum',window:'prefix',role:'control',label:'Threat balance',unit:'index',basis:'heuristic',status:'available',value:.42},
    {id:'routes',key:'pass_routes',window:'prefix',role:'control',label:'Pass routes',unit:'locations',basis:'recorded_events',status:'available',club_id:'eastbridge',value:{passes:[{event_id:'p1',start:{x:10,y:20},end:{x:25,y:30},outcome:'unknown'}]}},
  ]}
  render(<AnalystMode/>);await screen.findByText('Full match without duplicate observations')
  fireEvent.click(screen.getByRole('button',{name:'Explore Match Analyst statistics'}))
  expect(screen.getAllByText('0.42')).toHaveLength(1)
  expect(screen.getByLabelText('Match-wide Threat balance: 0.42').closest('.an-stat-global')).toBeTruthy()
  fireEvent.change(screen.getByLabelText('Pitch map'),{target:{value:'pass_routes'}})
  expect(screen.getByRole('img',{name:'Pass routes, attacking right'}).querySelector('line')?.getAttribute('stroke')).toBe('#a5b7b1')
})

it('shows loading instead of an empty map before the statistics arrive',async()=>{
  state.value.snapshot=null
  render(<AnalystMode/>);await screen.findByText('Full match without duplicate observations')
  expect(screen.getAllByText('Loading match statistics…').length).toBeGreaterThan(0)
  expect(screen.queryByText('No recorded actions yet')).toBeNull()
})

it('scopes saved player focus to the current roster while retaining analysis language and depth',async()=>{
  localStorage.setItem(preferenceKey,JSON.stringify({...defaults(),focus_player_id:'sb09',language:'zh-Hans',depth:'analyst'}))
  vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({match_id:'wyscout-2058017',events:[{}],players:[{player_id:'source-player',alias_id:'eb09',team_id:4418}]})))
  render(<AnalystMode/>);await screen.findByText('Full match without duplicate observations')
  expect(state.inputs[3]).toEqual({language:'zh-Hans',depth:'analyst',focus_player_id:null})
  fireEvent.click(screen.getByText('Your view'))
  fireEvent.change(screen.getByLabelText('Player focus'),{target:{value:'eb09'}})
  expect(state.inputs[3].focus_player_id).toBe('eb09')
  fireEvent.change(screen.getByLabelText('Analysis detail'),{target:{value:'casual'}})
  expect(state.inputs[3].depth).toBe('casual')
})

it('keeps the selected metric window through a seek refresh without showing stale data',async()=>{
  const {rerender}=render(<AnalystMode/>);await screen.findByText('Full match without duplicate observations')
  fireEvent.click(screen.getByRole('button',{name:'Explore Match Analyst statistics'}))
  fireEvent.click(screen.getByRole('button',{name:'Recent play'}))
  state.value.snapshot=null;rerender(<AnalystMode/>)
  expect(screen.getAllByText('Loading match statistics…').length).toBeGreaterThan(0)
  state.value.snapshot={...snapshot,cutoff:{period:1,elapsed_ms:0}};rerender(<AnalystMode/>)
  expect(screen.getByRole('button',{name:'Recent play'}).getAttribute('aria-pressed')).toBe('true')
  expect(screen.getAllByText('0:00 – 0:00 · First half').length).toBeGreaterThan(0)
})

it('keeps evidence-only narrative facts out of metric rows and player ranking choices',async()=>{
  state.value.snapshot={...snapshot,metrics:[...snapshot.metrics,
    {id:'internal-team',key:'transition_seconds_e1',window:'prefix',role:'chance',label:'One transition duration',unit:'seconds',basis:'recorded_events',status:'available',value:7.9,club_id:'eastbridge',presentation:'evidence_only'},
    {id:'internal-player',key:'transition_involved_eb09',window:'prefix',role:'players',label:'Player in selected transition',unit:'count',basis:'recorded_events',status:'available',value:1,club_id:'eastbridge',player_id:'eb09',presentation:'evidence_only'},
  ]}
  render(<AnalystMode/>);await screen.findByText('Full match without duplicate observations')
  expect(screen.queryByText('One transition duration')).toBeNull()
  fireEvent.click(screen.getByRole('button',{name:'Explore Player Analyst statistics'}))
  expect(screen.queryByText('Player in selected transition')).toBeNull()
})

it('keeps old discussion timestamped while withholding stale prose from current statistics desks',async()=>{
  state.value.snapshot={...snapshot,cutoff:{period:1,elapsed_ms:840000}}
  state.value.rounds=[{snapshot_id:'old',cutoff:{period:1,elapsed_ms:600000},mode:'discussion',status:'complete',readings:[],summary:null,messages:[{id:'chance',role:'chance',text:'An earlier chance finding.',reply_to:null,relation:'observation',metric_ids:['m1'],evidence_ids:[]}]}]
  const {container}=render(<AnalystMode/>);await screen.findByText('Full match without duplicate observations')
  expect(screen.getByRole('log').textContent).toContain('An earlier chance finding.')
  expect(Array.from(container.querySelectorAll('.an-desk')).map(e=>e.textContent).join(' ')).not.toContain('An earlier chance finding.')
  expect(Array.from(container.querySelectorAll('.an-desk')).map(e=>e.textContent).join(' ')).toContain('Earlier finding from 10:00')
})

it('moves keyboard focus into statistics and restores it to the opening control',async()=>{
  const {container}=render(<AnalystMode/>);await screen.findByText('Full match without duplicate observations')
  const open=screen.getByRole('button',{name:'Explore Chance Analyst statistics'});open.focus();fireEvent.click(open)
  expect(document.activeElement).toBe(container.querySelector('.an-expanded-stats'))
  fireEvent.click(screen.getByRole('button',{name:'Close details ×'}))
  expect(document.activeElement).toBe(open)
})


it('preserves the replay node while metric refreshes temporarily clear the snapshot',async()=>{
  const {rerender}=render(<AnalystMode/>);await screen.findByText('Full match without duplicate observations')
  const replay=screen.getByLabelText('Test replay')
  state.value.snapshot=null;rerender(<AnalystMode/>)
  expect(screen.getByLabelText('Test replay')).toBe(replay)
  state.value.snapshot=snapshot;rerender(<AnalystMode/>)
  expect(screen.getByLabelText('Test replay')).toBe(replay)
})

it('closes the metric dialog on Escape and restores its opener',async()=>{
  render(<AnalystMode/>);await screen.findByText('Full match without duplicate observations')
  const open=screen.getByRole('button',{name:'Explore Match Analyst statistics'});open.focus();fireEvent.click(open)
  const dialog=screen.getByRole('dialog',{name:'Explore the evidence'})
  fireEvent(dialog,new Event('cancel',{cancelable:true}))
  expect(screen.queryByRole('dialog')).toBeNull();expect(document.activeElement).toBe(open)
})
