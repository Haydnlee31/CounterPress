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
  localStorage.clear();history.replaceState(null,'','/#analyst')
  state.value={config:{available:false,mode:'metrics',roles:[],interval_ms:60000},snapshot,analysis:null,pending:false,failed:false,metricsFailed:false,refresh:vi.fn()}
  vi.stubGlobal('fetch',vi.fn(async()=>new Response(JSON.stringify({match_id:'wyscout-2058017',events:[{}],players:[]}))))
})
afterEach(()=>{cleanup();vi.unstubAllGlobals();vi.restoreAllMocks()})

it('presents metrics-only signals honestly and integrates the full-match replay',async()=>{
  render(<AnalystMode/>);await screen.findByText('Full match without duplicate observations')
  expect(screen.getByRole('heading',{name:'Analyst Mode.'})).toBeTruthy()
  expect(screen.getByText('MATCH SIGNALS')).toBeTruthy()
  expect(screen.queryByText('FOOTIE’S MATCH READ')).toBeNull()
  expect(screen.getAllByText('Getting closer to goal')).toHaveLength(2)
  expect(screen.getByRole('img',{name:'On-ball activity map, attacking right'})).toBeTruthy()
  expect(screen.getByText('4')).toBeTruthy()
  fireEvent.click(screen.getByText('Other measures'))
  expect(screen.getByText('Shot speed')).toBeTruthy();expect(screen.getByText('Not available')).toBeTruthy()
  fireEvent.change(screen.getByLabelText('Pitch map'),{target:{value:'shot_map'}})
  expect(screen.getByRole('img',{name:'Shot locations, attacking right'}).querySelectorAll('circle')).toHaveLength(2)
  expect(document.body.textContent).not.toContain('snapshot-one')
})

it('shows a native finding, exact source clock, counterpoint and next test',async()=>{
  state.value.config={available:true,mode:'foundry',roles:[],interval_ms:60000}
  const reading={role:'chance',headline:'An opening down the right',explanation:'The last two moves reached the box.',alternative:'A short spell rather than sustained control.',watch_next:'Look for the next box entry.',evidence_ids:['e1'],metric_ids:['m1'],confidence:'medium'}
  state.value.analysis={snapshot_id:'a1',cutoff:{period:1,elapsed_ms:540000},mode:'foundry',status:'partial',readings:[reading],summary:null}
  render(<AnalystMode/>);await screen.findByText('Full match without duplicate observations')
  expect(screen.getByText('FOOTIE’S MATCH READ')).toBeTruthy()
  expect(screen.getByText('At 9:00')).toBeTruthy()
  expect(screen.getByText('Another reading')).toBeTruthy()
  expect(screen.getByText('Look for the next box entry.')).toBeTruthy()
  expect(screen.getByText('Some specialist readings are still unavailable.')).toBeTruthy()
  const detail=screen.getAllByText('Supporting plays')[0];fireEvent.click(detail)
  expect(screen.getAllByText('Rory Ellis').length).toBeGreaterThan(0)
  expect(screen.queryByText('99%')).toBeNull()
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
  fireEvent.click(screen.getByRole('button',{name:'Recent play'}))
  expect(screen.getByText('0:00 – 2:00 · First half')).toBeTruthy()
  expect(document.body.textContent).not.toContain('Last 5 minutes')
})

it('does not turn missing player-map coverage into zero actions',async()=>{
  render(<AnalystMode/>);await screen.findByText('Full match without duplicate observations')
  fireEvent.change(screen.getByLabelText('Map subject'),{target:{value:'player:eb09'}})
  expect(screen.getByText('Map unavailable for this view')).toBeTruthy()
  expect(screen.queryByText('No recorded actions yet')).toBeNull()
})

it('renders a match-wide index once and keeps unknown pass outcomes neutral',async()=>{
  state.value.snapshot={...snapshot,metrics:[...snapshot.metrics,
    {id:'global',key:'momentum',window:'prefix',role:'control',label:'Threat balance',unit:'index',basis:'heuristic',status:'available',value:.42},
    {id:'routes',key:'pass_routes',window:'prefix',role:'control',label:'Pass routes',unit:'locations',basis:'recorded_events',status:'available',club_id:'eastbridge',value:{passes:[{event_id:'p1',start:{x:10,y:20},end:{x:25,y:30},outcome:'unknown'}]}},
  ]}
  render(<AnalystMode/>);await screen.findByText('Full match without duplicate observations')
  fireEvent.click(screen.getByRole('button',{name:/Build-up/}))
  expect(screen.getAllByText('0.42')).toHaveLength(1)
  expect(screen.getByLabelText('Match-wide Threat balance: 0.42').closest('.an-stat-global')).toBeTruthy()
  fireEvent.change(screen.getByLabelText('Pitch map'),{target:{value:'pass_routes'}})
  expect(screen.getByRole('img',{name:'Pass routes, attacking right'}).querySelector('line')?.getAttribute('stroke')).toBe('#a5b7b1')
})

it('shows loading instead of an empty map before the statistics arrive',async()=>{
  state.value.snapshot=null
  render(<AnalystMode/>);await screen.findByText('Full match without duplicate observations')
  expect(screen.getByText('Loading match statistics…')).toBeTruthy()
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
  fireEvent.click(screen.getByRole('button',{name:'Recent play'}))
  state.value.snapshot=null;rerender(<AnalystMode/>)
  expect(screen.getByText('Loading match statistics…')).toBeTruthy()
  state.value.snapshot={...snapshot,cutoff:{period:1,elapsed_ms:0}};rerender(<AnalystMode/>)
  expect(screen.getByRole('button',{name:'Recent play'}).getAttribute('aria-pressed')).toBe('true')
  expect(screen.getByText('0:00 – 0:00 · First half')).toBeTruthy()
})

it('identifies a partial supporting-play list for an earlier reading',async()=>{
  state.value.analysis={snapshot_id:'older',cutoff:{period:1,elapsed_ms:540000},mode:'foundry',status:'complete',readings:[],summary:{headline:'Earlier reading',explanation:'A linked move reached the box.',evidence_ids:['e1','older-play'],metric_ids:['m1']}}
  render(<AnalystMode/>);await screen.findByText('Full match without duplicate observations')
  fireEvent.click(screen.getByText('Supporting plays'))
  expect(screen.getByText('Showing 1 of 2 supporting plays available in this view.')).toBeTruthy()
})

it('keeps evidence-only narrative facts out of metric rows and player ranking choices',async()=>{
  state.value.snapshot={...snapshot,metrics:[...snapshot.metrics,
    {id:'internal-team',key:'transition_seconds_e1',window:'prefix',role:'chance',label:'One transition duration',unit:'seconds',basis:'recorded_events',status:'available',value:7.9,club_id:'eastbridge',presentation:'evidence_only'},
    {id:'internal-player',key:'transition_involved_eb09',window:'prefix',role:'players',label:'Player in selected transition',unit:'count',basis:'recorded_events',status:'available',value:1,club_id:'eastbridge',player_id:'eb09',presentation:'evidence_only'},
  ]}
  render(<AnalystMode/>);await screen.findByText('Full match without duplicate observations')
  expect(screen.queryByText('One transition duration')).toBeNull()
  fireEvent.click(screen.getByRole('button',{name:/Player impact/}))
  expect(screen.queryByText('Player in selected transition')).toBeNull()
})
