import {act,cleanup,fireEvent,render,screen,waitFor,within} from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import FootballHub from './FootballHub'
import {preferenceKey} from '../../../integrations/personalization/client'
import type {Club,Player} from './data'

const clubs:Club[]=[{club_id:'redhaven',name:'Redhaven',short_name:'RH',featured:true,primary_color:'#bc432e'},{club_id:'southbank',name:'Southbank',short_name:'SB',featured:true,primary_color:'#643d60'}]
const players:Player[]=[{player_id:'rh08',club_id:'redhaven',name:'Enzo Clarke',role:'MF',number:8,featured:true,star:true,birth_year:2000,debut_year:2020},{player_id:'sb09',club_id:'southbank',name:'Dario Voss',role:'FW',number:9,featured:true,star:true,birth_year:1998,debut_year:2020}]
const match={match_id:'career-showcase-southbank-redhaven',kickoff:'2026-10-19T15:00:00Z',home_id:'southbank',away_id:'redhaven',season:'2026-27',competition:'Showcase Cup',score:{southbank:3,redhaven:2},featured:true,replay_available:true,stats:{goals:1,minutes:90,shots:4,passes_completed:55,duels_won:8}}
const tile=(metric:string,label:string,value:number|null)=>({metric,label,value,unit:'count',coverage:value===null?'partial':'available',denominator:null})
function profile(id:string){const subject=players.find(p=>p.player_id===id)??clubs.find(c=>c.club_id===id)!
  return {profile:{subject,scope:{season:null,match_count:140},totals:{goals:20,appearances:140},rates:{},record:null,seasons:[{season:'2026-27',totals:{goals:3,appearances:8,minutes:720},rates:{pass_accuracy_pct:90}}],recent_form:{matches:5,totals:{goals:3},rates:{}},coverage:{}},presentation:{tiles:[tile('goals','Goals',20),tile('assists','Assists',null)],cards:[{id:'form',kind:'recent_form',title:'Recent form',text:`${subject.name} has scored 3 goals in the last 5 appearances.`,action:{kind:'history',subject_id:id,label:'See recent matches'}}],questions:[],activity_map:{label:'Where the action happens',columns:12,rows:8,cells:[{column:1,row:1,actions:3}],total_actions:3}}}
}
const requests:{url:string;body:Record<string,any>}[]=[]
let profileGate:((result:Response)=>void)|null=null,failCatalog=false
beforeEach(()=>{
  window.localStorage.clear();window.history.replaceState({},'','#football/players');requests.length=0;profileGate=null;failCatalog=false
  vi.stubGlobal('scrollTo',vi.fn())
  vi.stubGlobal('fetch',vi.fn(async(input:RequestInfo|URL,options?:RequestInit)=>{
    const url=String(input),body=options?.body?JSON.parse(String(options.body)):{}
    requests.push({url,body})
    const reply=(data:unknown,status=200)=>new Response(JSON.stringify(data),{status,headers:{'Content-Type':'application/json'}})
    const envelope={version:'fan-personalization-v1',request_id:body.request_id,preferences:body.preferences,preference_id:'view',dataset_id:'data'}
    if(url==='/api/data/catalog')return reply({clubs,seasons:['2026-27','2025-26'],counts:{featured_players:2,featured_clubs:2}},failCatalog?503:200)
    if(url.startsWith('/api/data/players?'))return reply({items:url.includes('offset=100')?[]:players})
    if(url.startsWith('/api/data/matches?'))return reply({items:[match]})
    if(url.includes('/matches?'))return reply({items:[match],total:1})
    if(url==='/api/fan/home')return reply({...envelope,following:{players:body.preferences.favorite_player_ids.map((id:string)=>({player:players.find(p=>p.player_id===id),tiles:[tile('goals','Goals',20)],cards:[]})),clubs:body.preferences.favorite_club_ids.map((id:string)=>({club:clubs.find(c=>c.club_id===id),tiles:[],record:{wins:4,draws:2,losses:2}}))},highlights:[],matches:[match],highlight_total:0})
    if(url==='/api/fan/players/compare')return reply({...envelope,players:body.player_ids.map((id:string)=>players.find(p=>p.player_id===id)),metrics:[{metric:'goals',label:'Goals',values:{rh08:tile('goals','Goals',20),sb09:tile('goals','Goals',40)}}],same_role:false,rate_comparison_available:true})
    if(url.startsWith('/api/fan/players/')||url.startsWith('/api/fan/clubs/')){
      if(body.preferences.language==='zh-Hans')return new Promise<Response>(resolve=>{profileGate=resolve})
      return reply({...envelope,...profile(url.split('/').at(-1)!)})
    }
    throw new Error(`Unexpected request: ${url}`)
  }))
})
afterEach(()=>{cleanup();vi.unstubAllGlobals();vi.restoreAllMocks()})

it('lets a fan search, follow, and retain favorites after reopening the hub',async()=>{
  const user=userEvent.setup(),first=render(<FootballHub/>)
  await user.type(await screen.findByRole('textbox',{name:'Search players'}),'Enzo')
  expect(screen.queryByRole('link',{name:'Dario Voss'})).toBeNull()
  await user.click(screen.getByRole('button',{name:'Follow Enzo Clarke'}))
  expect(JSON.parse(localStorage.getItem(preferenceKey)!).favorite_player_ids).toEqual(['rh08'])
  first.unmount();render(<FootballHub/>)
  await screen.findByRole('button',{name:'Unfollow Enzo Clarke'})
  await user.click(screen.getByRole('link',{name:'Following 1'}))
  await screen.findByRole('heading',{name:'Enzo Clarke ↗'})
  await user.click(screen.getByRole('button',{name:'Unfollow Enzo Clarke'}))
  await screen.findByRole('heading',{name:'Start with a favorite.'})
})
it('opens career statistics and match history without presenting missing assists as zero',async()=>{
  const user=userEvent.setup();render(<FootballHub/>)
  await user.click(await screen.findByRole('link',{name:'View Enzo Clarke'}))
  await screen.findByRole('heading',{name:'Enzo Clarke has scored 3 goals in the last 5 appearances.'})
  expect(screen.getByText('Not available')).toBeTruthy()
  const assist=screen.getByText('Assists').parentElement!
  expect(within(assist).getByText('—')).toBeTruthy()
  await user.click(screen.getByRole('button',{name:'Match history'}))
  await user.click(await screen.findByRole('button',{name:/Showcase Cup/}))
  expect(screen.getByText('Completed passes')).toBeTruthy()
  expect(screen.getByText('55')).toBeTruthy()
  expect(document.querySelector('pre')).toBeNull()
})
it('compares the chosen players using one visible season and shared data cutoff',async()=>{
  const user=userEvent.setup();render(<FootballHub/>)
  await user.click(await screen.findByRole('button',{name:'Add Enzo Clarke to comparison'}))
  await user.click(screen.getByRole('button',{name:'Add Dario Voss to comparison'}))
  await user.click(screen.getByRole('link',{name:'Compare players →'}))
  await screen.findByText('These players play different positions. Read their numbers alongside their roles.')
  await user.selectOptions(screen.getByRole('combobox',{name:'Statistics period'}),'2025-26')
  await waitFor(()=>expect(requests.filter(r=>r.url==='/api/fan/players/compare').at(-1)?.body).toMatchObject({player_ids:['rh08','sb09'],season:'2025-26',as_of:'2026-10-20T00:00:00Z'}))
})
it('withdraws old cards immediately on a preference change and ignores late responses',async()=>{
  const user=userEvent.setup();render(<FootballHub/>)
  await user.click(await screen.findByRole('link',{name:'View Enzo Clarke'}))
  await screen.findByRole('heading',{name:'Enzo Clarke has scored 3 goals in the last 5 appearances.'})
  await user.selectOptions(screen.getByRole('combobox',{name:'Hub language'}),'zh-Hans')
  await waitFor(()=>expect(profileGate).not.toBeNull())
  expect(screen.queryByRole('heading',{name:'Enzo Clarke has scored 3 goals in the last 5 appearances.'})).toBeNull()
  const old=requests.filter(r=>r.url==='/api/fan/players/rh08').at(-1)!.body
  await user.selectOptions(screen.getByRole('combobox',{name:'Hub language'}),'en')
  await screen.findByRole('heading',{name:'Enzo Clarke has scored 3 goals in the last 5 appearances.'})
  await act(async()=>profileGate!(new Response(JSON.stringify({version:'fan-personalization-v1',request_id:old.request_id,preferences:old.preferences,...profile('rh08'),presentation:{...profile('rh08').presentation,cards:[{id:'old',text:'STALE CARD',action:{}}]}}))))
  expect(screen.queryByText('STALE CARD')).toBeNull()
})
it('offers recovery when loading fails and makes club following available through the UI',async()=>{
  failCatalog=true;const user=userEvent.setup();render(<FootballHub/>)
  await screen.findByRole('alert');failCatalog=false
  await user.click(screen.getByRole('button',{name:'Try again'}))
  await screen.findByRole('textbox',{name:'Search players'})
  await user.click(screen.getByRole('link',{name:'Clubs'}))
  await user.click(await screen.findByRole('button',{name:'Follow Redhaven'}))
  expect(JSON.parse(localStorage.getItem(preferenceKey)!).primary_club_id).toBe('redhaven')
})
it('does not silently promise persistence when browser storage rejects a save',async()=>{
  const user=userEvent.setup();render(<FootballHub/>)
  await screen.findByRole('textbox',{name:'Search players'})
  vi.spyOn(Storage.prototype,'setItem').mockImplementation(()=>{throw new Error('Denied')})
  await user.click(screen.getByRole('button',{name:'Follow Enzo Clarke'}))
  expect(screen.getByText('Your choices apply for this visit. Browser storage is unavailable.')).toBeTruthy()
  expect(screen.getByRole('button',{name:'Unfollow Enzo Clarke'})).toBeTruthy()
})
it('updates favorites when another tab changes device preferences',async()=>{
  const user=userEvent.setup();render(<FootballHub/>)
  await user.click(await screen.findByRole('button',{name:'Follow Enzo Clarke'}))
  const next=JSON.parse(localStorage.getItem(preferenceKey)!);next.favorite_player_ids=[];localStorage.setItem(preferenceKey,JSON.stringify(next))
  fireEvent(window,new StorageEvent('storage',{key:preferenceKey}))
  await screen.findByRole('button',{name:'Follow Enzo Clarke'})
})

it('keeps a recorded partial total visible with its match coverage',async()=>{
  const {Tiles}=await import('./visuals')
  render(<Tiles tiles={[{metric:'assists',label:'Assists',value:12,unit:'count',coverage:'partial',coverage_label:'138 of 140 matches',denominator:null}]}/> )
  expect(screen.getByText('12')).toBeTruthy()
  expect(screen.getByText('138 of 140 matches')).toBeTruthy()
  expect(screen.queryByText('Not available')).toBeNull()
})

it('uses a stable player portrait and falls back to the kit if it fails',async()=>{
  const {Shirt}=await import('./visuals')
  render(<Shirt player={players[0]} club={clubs[0]}/> )
  const image=screen.getByRole('img',{name:'Enzo Clarke in Redhaven colours'})
  expect(image.getAttribute('src')).toContain('rh08-portrait-v1')
  fireEvent.error(image)
  expect(screen.queryByRole('img')).toBeNull()
  expect(document.querySelector('.fh-shirt')).not.toBeNull()
})
