import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, test, vi } from 'vitest'
import App from './App'
import { PressureCard } from './PressureCard'
import { PlaybackScope } from './playbackScope'
import * as api from './api'
import { defaultPreferences } from './types'
import type { Preferences, PressureChange, PressureView, Snapshot, Window } from './types'

vi.mock('./api', () => ({ fetchSnapshot: vi.fn(), fetchScenarios: vi.fn() }))
afterEach(() => { cleanup(); vi.clearAllMocks(); vi.useRealTimers() })

const baseline: Window = { start: {period:2,elapsed_ms:180000},end:{period:2,elapsed_ms:480000},boundary:'(start,end]' }
const current: Window = { start: baseline.end,end:{period:2,elapsed_ms:780000},boundary:'(start,end]' }

// Small presentation stub; detector/source arithmetic is independently tested in Python.
function publication(revision = 1, operation: PressureChange['operation'] = 'create'): PressureChange {
  return { insight_id:'pressure-one',evidence_id:'pressure-ev-one',revision,operation,available_at:current.end,metric:'pressure_exposure',invalidates:revision>1?[revision-1]:[],
    decision:{metric:'pressure_exposure',status:operation==='withdraw'?'insufficient_sample':'eligible',direction:'increase',baseline_numerator:3,baseline_denominator:6,current_numerator:6,current_denominator:6,change:0.5},
    evidence:{match_id:'match-one',subject_team_id:'eastbridge',cutoff:current.end,rule_version:'observed-build-up-v1',disclosure:'Duel proxy, not causal effectiveness.',policy:{minimum_episodes:3,minimum_rate_change:0.25,cooldown_ms:60000},
      baseline:{window:baseline,included:['b1-start'],boundary_excluded:[],left_censored:[],pending:[],completed:6,exposed:3,escaped_under_pressure:3,exposure_rate:0.5,pressured_escape_rate:1},
      current:{window:current,included:[],boundary_excluded:[],left_censored:[],pending:['pending-start'],completed:6,exposed:6,escaped_under_pressure:1,exposure_rate:1,pressured_escape_rate:1/6},
      episodes:[{episode_id:'b1-start',start:{period:2,elapsed_ms:190000},end:{period:2,elapsed_ms:210000},observed_start:true,outcome:'escape',pressure_events:[],source_events:[{event_id:'b1-start',revision:1}]}],
      records:[{schema_version:'1.0',match_id:'match-one',event_id:'b1-start',revision:1,source_delivery_sequence:1,occurrence_order:1,occurred_at:{period:2,elapsed_ms:190000},available_at:{period:2,elapsed_ms:190000},actor:{team_id:'eastbridge',player_id:'eb04'},position:{x:20,y:34},action:{kind:'recovery'}}]}}
}

function view(p: Preferences = defaultPreferences, revision=1): PressureView {
  return { preferences:p,state:'ready',message:'Recorded involvement; team rates stay unchanged.',priority:10,publication:publication(revision),highlighted_events:[{event_id:'b1-start',revision:1}],
    variant:{insight_id:'pressure-one',revision,language:p.language,depth:p.depth,club_id:p.club_id,player_id:p.player_id,title:p.language==='zh-Hans'?'压迫暴露比例上升':'Pressure exposure increased',explanation:'3/6 → 6/6',qualification:'Duels are a proxy. No causal claim.',subject_name:'Eastbridge'}}
}

function snapshot(at: number, scope: string, p: Preferences, revision=1, withdrawn=false): Snapshot {
  const ready=at>=780000
  const pressure=ready&&!withdrawn&&p.card_budget?view(p,revision):{preferences:p,state:at<780000?'collecting':p.card_budget===0?'budget_hidden':'no_eligible',message:'No eligible pressure insight.',publication:null,variant:null,highlighted_events:[],priority:0}
  return {scenario_id:'pressure-increase',scope_id:scope,history_version:63+revision,replay_end:current.end,
    state:{match_id:'match-one',at:{period:2,elapsed_ms:at},score:{eastbridge:0,northport:1},controlled_possession_team_id:'northport',source_delivery_cursor:1,applied_events:[]},metrics:[],windows:[baseline,current],comparison_status:ready?'no_increase':'collecting',insight:null,evidence:null,lifecycle:null,
    audience:{preferences:p,state:'no_increase',message:'No recovery insight.',variant:null,priority:0,highlighted_events:[],sequence:[],supporting_event_count:0,selected_event_count:0},
    pressure,pressure_lifecycle:ready?[publication(revision,withdrawn?'withdraw':'create')]:[],selected_kind:pressure.state==='ready'?'pressure':null}
}

test('opens episode classifications and exact source revisions while retaining the rate denominators', async () => {
  const user=userEvent.setup()
  const {rerender}=render(<PressureCard view={view()} open={false} onToggle={()=>{}}/>)
  expect(screen.getByLabelText('3/6 to 6/6')).toBeTruthy()
  expect(screen.getByText('50.0%')).toBeTruthy()
  rerender(<PressureCard view={view()} open={true} onToggle={()=>{}}/>)
  expect(screen.getByRole('table',{name:'Samples and exclusions'})).toBeTruthy()
  await user.click(screen.getByText(/b1-start ·/))
  await user.click(screen.getByText(/b1-start@r1 · eb04/))
  expect(screen.getByText(/"source_delivery_sequence": 1/)).toBeTruthy()
  expect(screen.getByText(/Baseline: included/)).toBeTruthy()
  rerender(<PressureCard view={view({...defaultPreferences,language:'zh-Hans',depth:'casual'})} open={false} onToggle={()=>{}}/>)
  expect(screen.getByRole('heading',{name:'压迫暴露比例上升'})).toBeTruthy()
  expect(screen.getByLabelText('3/6 to 6/6')).toBeTruthy()
})

test('retains separate pressure tombstones and refuses missing or stale streams', () => {
  const scope=new PlaybackScope('viewer')
  expect(scope.accept(snapshot(780000,'viewer',defaultPreferences))).toBe(true)
  expect(scope.accept(snapshot(780000,'viewer',defaultPreferences,3,true))).toBe(true)
  expect(scope.accept({...snapshot(780000,'viewer',defaultPreferences,2),history_version:999})).toBe(false)
  expect(scope.accept({...snapshot(780000,'viewer',defaultPreferences,4),pressure_lifecycle:[]})).toBe(false)
  expect(scope.accept(snapshot(780000,'viewer',defaultPreferences,4))).toBe(true)
  expect(new PlaybackScope('fresh').accept(snapshot(780000,'fresh',defaultPreferences))).toBe(true)
})

test('screen removes a withdrawn pressure card and evidence, rejects a stale replay, then restores a new revision', async () => {
  vi.useFakeTimers({toFake:['setInterval','clearInterval']})
  let revision=1,withdrawn=false
  vi.mocked(api.fetchScenarios).mockResolvedValue([{scenario_id:'pressure-increase',label:'Pressure and escape shift',start:baseline.start,end:current.end}])
  vi.mocked(api.fetchSnapshot).mockImplementation(async (_scenario,at,_signal,scope,p=defaultPreferences)=>snapshot(at,scope,p,revision,withdrawn))
  render(<App/>)
  await act(async()=>{})
  fireEvent.change(screen.getByLabelText('Replay scenario'),{target:{value:'pressure-increase'}})
  await act(async()=>{})
  fireEvent.click(screen.getByRole('button',{name:/Go to comparison/}))
  await act(async()=>{})
  expect(screen.getByRole('heading',{name:'Pressure exposure increased'})).toBeTruthy()
  expect(screen.queryByRole('heading',{name:'Where control was recovered'})).toBeNull()
  fireEvent.click(screen.getByRole('button',{name:/Show evidence/}))
  expect(screen.getByRole('region',{name:'Pressure evidence'})).toBeTruthy()
  revision=3;withdrawn=true
  await act(async()=>{vi.advanceTimersByTime(2000)})
  expect(screen.getByRole('heading',{name:'Insight withdrawn.'})).toBeTruthy()
  expect(screen.queryByRole('region',{name:'Pressure evidence'})).toBeNull()
  revision=1;withdrawn=false
  await act(async()=>{vi.advanceTimersByTime(2000)})
  expect(screen.queryByRole('heading',{name:'Pressure exposure increased'})).toBeNull()
  revision=4
  await act(async()=>{vi.advanceTimersByTime(2000)})
  expect(screen.getByRole('heading',{name:'Pressure exposure increased'})).toBeTruthy()
  fireEvent.click(screen.getByRole('button',{name:'Reset replay'}))
  await act(async()=>{})
  expect(screen.queryByRole('heading',{name:'Pressure exposure increased'})).toBeNull()
})

function progressionView(): PressureView {
  const result=view({...defaultPreferences,metric_focus:'possession_without_progression'})
  result.variant={...result.variant!,title:'Possession without progression increased',qualification:'Less than 15 m of observed forward gain; not tactical value.'}
  const p=result.publication!
  p.metric='possession_without_progression';p.decision={...p.decision,metric:p.metric,baseline_numerator:1,current_numerator:4}
  p.evidence.rule_version='sustained-possession-v1'
  p.evidence.policy={...p.evidence.policy,forward_gain_m:15,minimum_completed_actions:3,minimum_controlled_span_ms:20000}
  p.evidence.baseline={window:baseline,included:['b1-start'],without_progression:['b1-start'],without_progression_count:1,completed:6,rate:1/6,boundary_excluded:[],left_censored:[],pending:[],brief_excluded:['brief-start'],limited_space:[]}
  p.evidence.current={...p.evidence.baseline,window:current,without_progression_count:4,rate:4/6,brief_excluded:[],limited_space:['near-goal']}
  p.evidence.episodes=[{episode_id:'b1-start',start:{period:2,elapsed_ms:190000},end:{period:2,elapsed_ms:216000},observed_start:true,outcome:'turnover',source_events:[{event_id:'b1-start',revision:1}],start_x:30,maximum_x:40,forward_gain_m:10,completed_actions:3,controlled_span_ms:22000}]
  return result
}

test('progression evidence shows furthest controlled gain and its own sample exclusions', async () => {
  const user=userEvent.setup()
  render(<PressureCard view={progressionView()} open={true} onToggle={()=>{}}/>)
  expect(screen.getByLabelText('1/6 to 4/6')).toBeTruthy()
  expect(screen.getByText('16.7%')).toBeTruthy()
  expect(screen.getByText('66.7%')).toBeTruthy()
  expect(screen.getByRole('columnheader',{name:'Brief'})).toBeTruthy()
  expect(screen.getByRole('columnheader',{name:'Limited space'})).toBeTruthy()
  expect(screen.queryByRole('columnheader',{name:'Exposed'})).toBeNull()
  await user.click(screen.getByText(/b1-start ·/))
  expect(screen.getByText(/Forward gain: 10 m · x 30 → 40/)).toBeTruthy()
  expect(screen.getByText(/included: without progression/)).toBeTruthy()
  expect(screen.queryByText(/Pressure proxy events/)).toBeNull()
})

test('selects the progression scenario and renders one possession card without recovery pitch markers', async () => {
  const user=userEvent.setup()
  vi.mocked(api.fetchScenarios).mockResolvedValue([{scenario_id:'progression-increase',label:'Possession without progression',start:baseline.start,end:current.end}])
  vi.mocked(api.fetchSnapshot).mockImplementation(async (scenario,at,_signal,scope,p=defaultPreferences)=>({
    ...snapshot(at,scope,p),scenario_id:scenario,pressure:at>=780000?progressionView():snapshot(at,scope,p).pressure,
    selected_kind:at>=780000?'pressure':null,
  }))
  render(<App/>)
  await screen.findByRole('option',{name:'Possession without progression'})
  await user.selectOptions(screen.getByLabelText('Replay scenario'),'progression-increase')
  await user.click(screen.getByRole('button',{name:/Go to comparison/}))
  await screen.findByRole('heading',{name:'Possession without progression increased'})
  expect(screen.getByLabelText('1/6 to 4/6')).toBeTruthy()
  expect(screen.queryByRole('heading',{name:'Where control was recovered'})).toBeNull()
  await user.click(screen.getByRole('button',{name:/Show evidence/}))
  expect(screen.getByRole('region',{name:'Possession evidence'})).toBeTruthy()
})
