import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import AnalystMode from './AnalystMode'
import type {Snapshot} from './data'

const state=vi.hoisted(()=>({value:{} as any}))
vi.mock('./useAnalyst',()=>({useAnalyst:()=>state.value}))
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
