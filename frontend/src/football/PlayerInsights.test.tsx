import {act,cleanup,fireEvent,render,screen,within} from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import {afterEach,expect,it,vi} from 'vitest'
import PlayerInsights,{PitchExplorer,StatLibrary,type Analytics,type Metric} from './PlayerInsights'
const metric=(key:string,label:string,value:number|null,per90:number|null,unit='count',group='Shooting'):Metric=>({key,label,value,per90,unit,group,covered_matches:9,total_matches:10,covered_minutes:810,description:`Definition of ${label}.`})
export const analytics:Analytics={player_id:'rh09',role:'FW',scope:{season:null,matches:10},metrics:[metric('goals','Goals',4,.44),metric('pass_accuracy','Pass completion',80,null,'percent','Passing'),{...metric('headed_shots','Headed shots',null,null),covered_matches:0}],heatmap:{columns:12,rows:8,cells:[{column:8,row:3,actions:20}],total_actions:20},defense:[{column:2,row:4,actions:3}],shots:[{event_id:'e1',revision:1,match_id:'m1',date:'2026-10-19',x:92,y:34,period:1,elapsed_ms:300000,outcome:'goal',xg:.4,penalty:false},{event_id:'e2',revision:1,match_id:'m1',date:'2026-10-19',x:80,y:20,period:2,elapsed_ms:400000,outcome:'off_target',xg:null,penalty:false}],passing_routes:[{x:50,y:34,end_x:80,end_y:34,outcome:'completed',progressive:true,count:5},{x:60,y:34,end_x:65,end_y:34,outcome:'incomplete',progressive:false,count:2}],thirds:{own_third_actions:2,middle_third_actions:8,final_third_actions:10},goal_timing:[1,0,0,0,0,0],recent:[],comparison:{minimum_minutes:900,role:'FW',metrics:[{key:'goals',label:'Goals',value:.44,unit:'per90',percentile:75,cohort_size:12}]},definitions:{missing:['Continuous tracking']}}
afterEach(()=>{cleanup();vi.unstubAllGlobals()})
it('switches pitch modes, filters shots and exposes keyboard-accessible shot details',async()=>{
  const user=userEvent.setup();render(<PitchExplorer data={analytics}/>)
  await user.click(screen.getByRole('button',{name:'Shooting'}))
  expect(screen.getByText('2 located shots')).toBeTruthy()
  const goal=screen.getByRole('button',{name:/Goal, 2026-10-19/})
  fireEvent.keyDown(goal,{key:'Enter'})
  expect(screen.getByText('Goal · 5′')).toBeTruthy()
  await user.selectOptions(screen.getByRole('combobox',{name:'Shot filter'}),'goals')
  expect(screen.getByText('1 located shots')).toBeTruthy()
  expect(screen.queryByRole('button',{name:/Off target,/})).toBeNull()
  expect(screen.queryByText('Goal · 5′')).toBeNull()
  await user.click(screen.getByRole('button',{name:'Ball winning'}))
  expect(screen.getByText('3 actions',{selector:'span'})).toBeTruthy()
  await user.click(screen.getByRole('button',{name:'Show zone counts'}))
  expect(screen.getByRole('button',{name:'Smooth view'}).getAttribute('aria-pressed')).toBe('true')
})
it('filters route volumes together with the plotted routes',async()=>{
  const user=userEvent.setup();render(<PitchExplorer data={analytics}/>)
  await user.click(screen.getByRole('button',{name:'Passing'}))
  expect(screen.getByText('7 passes')).toBeTruthy()
  await user.selectOptions(screen.getByRole('combobox',{name:'Pass filter'}),'progressive')
  expect(screen.getByText('5 passes')).toBeTruthy()
  expect(screen.getByText('Top 1 zone-to-zone routes · 100% of selected passes.')).toBeTruthy()
})
it('normalizes counts per 90, keeps percentages intact, and exposes coverage on demand',async()=>{
  const user=userEvent.setup();render(<StatLibrary data={analytics}/>)
  expect(screen.getByText('2 statistics · 10 matches')).toBeTruthy()
  expect(screen.queryByText('Headed shots')).toBeNull()
  await user.click(screen.getByRole('button',{name:'Per 90'}))
  expect(screen.getByText('0.44')).toBeTruthy()
  expect(screen.getByText('80%')).toBeTruthy()
  await user.type(screen.getByRole('textbox',{name:'Search statistics'}),'pass')
  expect(screen.queryByText('Goals')).toBeNull()
  await user.click(screen.getByText('Pass completion'))
  expect(screen.getByText('Definition of Pass completion.')).toBeTruthy()
  expect(screen.getByText(/9 \/ 10 matches covered/)).toBeTruthy()
  await user.selectOptions(screen.getByRole('combobox',{name:'Statistic category'}),'Shooting')
  expect(screen.getByText('Try another statistic or category.')).toBeTruthy()
})
it('removes stale maps immediately when the season changes, and sends the common cutoff',async()=>{
  let resolve:((r:Response)=>void)|undefined
  const fetch=vi.fn(async(url:string)=>url.includes('2025-26')?new Promise<Response>(r=>{resolve=r}):new Response(JSON.stringify(analytics)))
  vi.stubGlobal('fetch',fetch)
  const props={playerId:'rh09',season:'',before:'2026-10-20T00:00:00Z',clubs:[]}
  const view=render(<PlayerInsights {...props}/>)
  await screen.findByRole('heading',{name:'Pitch activity'})
  view.rerender(<PlayerInsights {...props} season="2025-26"/>)
  expect(screen.queryByRole('heading',{name:'Pitch activity'})).toBeNull()
  expect(screen.getByRole('status').textContent).toContain('Loading pitch maps')
  await act(async()=>resolve!(new Response(JSON.stringify({...analytics,scope:{season:'2025-26',matches:3}}))))
  await screen.findByText('3 matches')
  expect(String(fetch.mock.calls.at(-1)?.[0])).toContain('season=2025-26')
  expect(String(fetch.mock.calls.at(-1)?.[0])).toContain('before=2026-10-20T00%3A00%3A00Z')
})
it('offers a working retry when the statistics service is unavailable',async()=>{
  const user=userEvent.setup(),fetch=vi.fn().mockResolvedValueOnce(new Response('',{status:503})).mockResolvedValueOnce(new Response(JSON.stringify(analytics)))
  vi.stubGlobal('fetch',fetch)
  render(<PlayerInsights playerId="rh09" season="" before="2026-10-20T00:00:00Z" clubs={[]}/>)
  await screen.findByRole('alert')
  await user.click(screen.getByRole('button',{name:'Try again'}))
  await screen.findByRole('heading',{name:'Pitch activity'})
  expect(document.querySelector('pre')).toBeNull()
})

it('puts goalkeeping statistics before attacking statistics for goalkeepers',()=>{
  const data={...analytics,role:'GK',metrics:[...analytics.metrics,metric('saves','Saves',30,3,'count','Goalkeeping')]}
  render(<StatLibrary data={data}/>)
  const summaries=[...document.querySelectorAll('summary')].map(e=>e.textContent)
  expect(summaries[0]).toContain('Saves')
  expect(summaries.indexOf(summaries.find(s=>s?.includes('Goals'))!)).toBeGreaterThan(0)
})
