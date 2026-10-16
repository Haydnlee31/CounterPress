import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, test, vi } from 'vitest'
import App from './App'
import { ContributionCard } from './ContributionCard'
import { PlaybackScope } from './playbackScope'
import * as api from './api'
import { defaultPreferences } from './types'
import type { ContributionChange, ContributionView, Preferences, Snapshot, Window } from './types'

vi.mock('./api',()=>({fetchSnapshot:vi.fn(),fetchScenarios:vi.fn()}))
afterEach(()=>{cleanup();vi.clearAllMocks();vi.useRealTimers()})
const baseline: Window={start:{period:2,elapsed_ms:180000},end:{period:2,elapsed_ms:480000},boundary:'(start,end]'}
const current: Window={start:baseline.end,end:{period:2,elapsed_ms:780000},boundary:'(start,end]'}

function publication(revision=1,withdrawn=false): ContributionChange {
  return {insight_id:'player-one',evidence_id:'player-ev-one',revision,operation:withdrawn?'withdraw':revision===1?'create':'update',available_at:current.end,invalidates:revision>1?[revision-1]:[],
    evidence:{rule_version:'player-high-recoveries-v1',metric:'player_high_recovery_share',match_id:'match-one',subject_team_id:'eastbridge',subject_player_id:'eb04',cutoff:current.end,coverage_start:baseline.start,
      baseline:{window:baseline,team_events:[{event_id:'b1-recovery',revision:1},{event_id:'b2-recovery',revision:1}],player_events:[{event_id:'b1-recovery',revision:1}],team_count:4,player_count:1,share:0.25},
      current:{window:current,team_events:[],player_events:[],team_count:4,player_count:3,share:0.75},
      policy:{minimum_team_recoveries:3,minimum_current_player_recoveries:3,minimum_count_increase:2,minimum_share_increase:0.25},
      decision:{status:withdrawn?'below_threshold':'eligible',count_change:2,share_change:0.5},disclosure:'Recorded actors only; not tactical causality.',
      records:['eb04','eb08'].map((player,index)=>({schema_version:'1.0',match_id:'match-one',event_id:`b${index+1}-recovery`,revision:1,source_delivery_sequence:index+1,occurrence_order:index+1,occurred_at:{period:2,elapsed_ms:200000+index*80000},available_at:{period:2,elapsed_ms:200000+index*80000},actor:{team_id:'eastbridge',player_id:player},position:{x:70,y:34},action:{kind:'recovery'}}))}}
}
function view(p=defaultPreferences,revision=1): ContributionView {
  return {preferences:p,state:'ready',message:'Duel winners and pass recipients receive no recovery attribution.',priority:10,publication:publication(revision),highlighted_events:[{event_id:'b1-recovery',revision:1}],
    variant:{insight_id:'player-one',revision,language:p.language,depth:p.depth,club_id:p.club_id,player_id:p.player_id,title:p.language==='zh-Hans'?'球员前场夺回球权占比增加':'Player high-recovery share increased',explanation:'eb04 · Eastbridge: 1/4 → 3/4.',qualification:'Not a player rating or tactical causality.',subject_name:'eb04 · Eastbridge'}}
}
function snapshot(at:number,scope:string,p:Preferences,revision=1,withdrawn=false,scenario='contribution-increase'):Snapshot {
  const ready=at>=780000,eligible=ready&&!withdrawn&&p.card_budget>0&&(!p.player_id||p.player_id==='eb04')&&scenario!=='contribution-control'
  const contribution=eligible?view(p,revision):{preferences:p,state:!ready?'collecting':p.card_budget===0?'budget_hidden':p.player_id?'no_contribution':'no_eligible',message:'No eligible increase in player high-recovery share.',publication:null,variant:null,highlighted_events:[],priority:0}
  return {scenario_id:scenario,scope_id:scope,history_version:48+revision,replay_end:current.end,state:{match_id:'match-one',at:{period:2,elapsed_ms:at},score:{eastbridge:0,northport:1},controlled_possession_team_id:'northport',source_delivery_cursor:48,applied_events:[]},metrics:[],windows:[baseline,current],comparison_status:ready?'no_increase':'collecting',insight:null,evidence:null,lifecycle:null,
    audience:{preferences:p,state:'no_increase',message:'No recovery increase.',variant:null,priority:0,highlighted_events:[],sequence:[],supporting_event_count:0,selected_event_count:0},contribution,contribution_lifecycle:ready&&scenario!=='contribution-control'?[publication(revision,withdrawn)]:[],selected_kind:eligible?'contribution':null,
    teams:[{team_id:'eastbridge',name:'Eastbridge',player_ids:['eb04','eb08','eb09']},{team_id:'northport',name:'Northport',player_ids:['np04']}]}
}
function mockApi(getRevision=()=>({revision:1,withdrawn:false})) {
  vi.mocked(api.fetchScenarios).mockResolvedValue(['increase','control'].map(name=>({scenario_id:`contribution-${name}`,label:`Player recovery share ${name}`,start:baseline.start,end:current.end})))
  vi.mocked(api.fetchSnapshot).mockImplementation(async(scenario,at,_signal,scope,p=defaultPreferences)=>{const state=getRevision();return snapshot(at,scope,p,state.revision,state.withdrawn,scenario)})
}

test('shows player and full team fractions with attributed and denominator-only source revisions',async()=>{
  const user=userEvent.setup()
  const {rerender}=render(<ContributionCard view={view()} open={true} onToggle={()=>{}}/>)
  expect(screen.getByLabelText('1/4 to 3/4')).toBeTruthy()
  expect(screen.getAllByText('25.0%').length).toBe(2)
  expect(screen.getByRole('table',{name:'Player and team counts'})).toBeTruthy()
  await user.click(screen.getByText(/b1-recovery@r1 · eb04/))
  expect(screen.getByText(/"source_delivery_sequence": 1/)).toBeTruthy()
  expect(screen.getByText(/b2-recovery@r1 · eb08.*Team denominator only/)).toBeTruthy()
  rerender(<ContributionCard view={view({...defaultPreferences,language:'zh-Hans',depth:'casual'})} open={true} onToggle={()=>{}}/>)
  expect(screen.getByRole('heading',{name:'球员前场夺回球权占比增加'})).toBeTruthy()
  expect(screen.getByRole('table',{name:'球员与球队计数'})).toBeTruthy()
  expect(screen.getByLabelText('1/4 to 3/4')).toBeTruthy()
  expect(screen.queryByText('证据来源')).toBeNull()
})

test('preserves per-player tombstones and rejects stale or missing streams until a fresh scope',()=>{
  const scope=new PlaybackScope('one')
  const original=snapshot(780000,'one',defaultPreferences)
  const second={...publication(),insight_id:'player-two'}
  original.contribution_lifecycle!.push(second)
  expect(scope.accept(original)).toBe(true)
  const withdrawn=snapshot(780000,'one',defaultPreferences,3,true)
  withdrawn.contribution_lifecycle!.push(second)
  expect(scope.accept(withdrawn)).toBe(true)
  const stale=snapshot(780000,'one',defaultPreferences,2)
  stale.history_version=999;stale.contribution_lifecycle!.push(second)
  expect(scope.accept(stale)).toBe(false)
  expect(scope.accept(snapshot(780000,'one',defaultPreferences,4))).toBe(false) // other player stream missing
  const restored=snapshot(780000,'one',defaultPreferences,4)
  restored.contribution_lifecycle!.push(second)
  expect(scope.accept(restored)).toBe(true)
  expect(new PlaybackScope('fresh').accept(snapshot(780000,'fresh',defaultPreferences))).toBe(true)
})

test('screen withdraws a player card and its evidence, refuses stale replay and restores a new revision',async()=>{
  vi.useFakeTimers({toFake:['setInterval','clearInterval']})
  let revision=1,withdrawn=false
  mockApi(()=>({revision,withdrawn}))
  render(<App/>);await act(async()=>{})
  fireEvent.change(screen.getByLabelText('Replay scenario'),{target:{value:'contribution-increase'}});await act(async()=>{})
  fireEvent.click(screen.getByRole('button',{name:/Go to comparison/}));await act(async()=>{})
  expect(screen.getByRole('heading',{name:'Player high-recovery share increased'})).toBeTruthy()
  expect(screen.queryByRole('heading',{name:'Where control was recovered'})).toBeNull()
  fireEvent.change(screen.getByLabelText('Player contribution'),{target:{value:'eb04'}});await act(async()=>{})
  fireEvent.click(screen.getByRole('button',{name:/Show evidence/}))
  expect(screen.getByRole('region',{name:'Player contribution evidence'})).toBeTruthy()
  revision=3;withdrawn=true
  await act(async()=>{vi.advanceTimersByTime(2000)})
  expect(screen.getByRole('heading',{name:'Insight withdrawn.'})).toBeTruthy()
  expect(screen.queryByRole('region',{name:'Player contribution evidence'})).toBeNull()
  fireEvent.change(screen.getByLabelText('Player contribution'),{target:{value:'eb09'}});await act(async()=>{})
  expect(screen.getByRole('heading',{name:'No qualifying contribution.'})).toBeTruthy()
  fireEvent.change(screen.getByLabelText('Player contribution'),{target:{value:'eb04'}});await act(async()=>{})
  expect(screen.getByRole('heading',{name:'Insight withdrawn.'})).toBeTruthy()
  revision=1;withdrawn=false
  await act(async()=>{vi.advanceTimersByTime(2000)})
  expect(screen.queryByRole('heading',{name:'Player high-recovery share increased'})).toBeNull()
  revision=4
  await act(async()=>{vi.advanceTimersByTime(2000)})
  expect(screen.getByRole('heading',{name:'Player high-recovery share increased'})).toBeTruthy()
  fireEvent.click(screen.getByRole('button',{name:'Reset replay'}));await act(async()=>{})
  expect(screen.queryByRole('region',{name:'Player contribution evidence'})).toBeNull()
})

test('player choice, card budget, language, viewers and negative control keep their own presentation',async()=>{
  const user=userEvent.setup();mockApi();render(<App/>)
  await screen.findByRole('option',{name:'Player recovery share increase'})
  await user.selectOptions(screen.getByLabelText('Replay scenario'),'contribution-increase')
  await user.click(screen.getByRole('button',{name:/Go to comparison/}))
  await screen.findByRole('heading',{name:'Player high-recovery share increased'})
  await user.selectOptions(screen.getByLabelText('Player contribution'),'eb09')
  await screen.findByRole('heading',{name:'No qualifying contribution.'})
  await user.selectOptions(screen.getByLabelText('Player contribution'),'eb04')
  await screen.findByRole('heading',{name:'Player high-recovery share increased'})
  await user.selectOptions(screen.getByLabelText('Card budget'),'0')
  await screen.findByRole('heading',{name:'Cards hidden.'})
  await user.selectOptions(screen.getByLabelText('Local viewer'),'two')
  await screen.findByRole('heading',{name:'Player high-recovery share increased'})
  await user.selectOptions(screen.getByLabelText('Language'),'zh-Hans')
  await screen.findByRole('heading',{name:'球员前场夺回球权占比增加'})
  expect(screen.getByLabelText('1/4 to 3/4')).toBeTruthy()
  await user.selectOptions(screen.getByLabelText('Local viewer'),'one')
  await screen.findByRole('heading',{name:'Cards hidden.'})
  await user.selectOptions(screen.getByLabelText('Card budget'),'1')
  await user.selectOptions(screen.getByLabelText('Replay scenario'),'contribution-control')
  await user.click(screen.getByRole('button',{name:/Go to comparison/}))
  expect(screen.queryByRole('heading',{name:'Player high-recovery share increased'})).toBeNull()
})
