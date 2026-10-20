import {useEffect, useState} from 'react'
import {createFanClient, StaleFanResponse} from '../../../integrations/personalization/client'
import type {FanPreferences, FanResponse} from '../../../integrations/personalization/client'
import type {Event, MatchTime} from '../types'

export type Player={player_id:string;club_id:string;name:string;role:'GK'|'DF'|'MF'|'FW';number:number;featured:boolean;star:boolean;birth_year:number;debut_year:number}
export type Club={club_id:string;name:string;short_name:string;featured:boolean;primary_color:string}
export type Catalog={clubs:Club[];seasons:string[];counts:{featured_clubs:number;featured_players:number}}
export type Tile={metric:string;label:string;value:number|null;unit:string;coverage:string;denominator:number|null;coverage_label?:string|null}
export type Action={kind:string;subject_id:string;subject_kind?:string;label:string;season?:string;event_id?:string;scenario_id?:string;replay_url?:string}
export type Card={id:string;kind:string;title:string;text:string;action:Action}
export type Question={id:string;text:string;action:Action}
export type Heatmap={columns:number;rows:number;cells:{column:number;row:number;actions:number}[];total_actions:number;label?:string}
export type Totals=Record<string,number|null>
export type Match={match_id:string;kickoff:string;home_id:string;away_id:string;season:string;competition:string;score:Record<string,number>;featured:boolean;replay_available:boolean;stats?:Totals;rates?:Totals}
export type Highlight={highlight_id:string;match_id:string|null;title:string;tag:string;date?:string;player_ids:string[];club_ids:string[];relevance:{reason:string;score:number};action:Action}
export type ProfileView=FanResponse & {profile:{subject:Player|Club;scope:{season:string|null;match_count:number};totals:Totals;rates:Totals;seasons:{season:string;totals:Totals;rates:Totals}[];record:{wins:number;draws:number;losses:number}|null;recent_form:{matches:number;totals:Totals;rates:Totals};coverage:Record<string,unknown>};presentation:{tiles:Tile[];cards:Card[];questions:Question[];activity_map:Heatmap}}
export type HomeView=FanResponse & {following:{players:{player:Player;tiles:Tile[];cards:Card[]}[];clubs:{club:Club;record:{wins:number;draws:number;losses:number};tiles:Tile[]}[]};highlights:Highlight[];matches:Match[];highlight_total:number}
export type CompareView=FanResponse & {players:Player[];metrics:{metric:string;label:string;values:Record<string,Tile>}[];same_role:boolean;rate_comparison_available:boolean;minimum_minutes_for_rate_comparison:number}
export type LiveView=FanResponse & {facts:{score:Record<string,number>;players:Record<string,{career_at_cutoff:Totals}>};cards:Card[];focus:{active_player_ids:string[];status:string;player_id:string|null};view_id:string}
export type Replay={match_id:string;teams:{team_id:string;name:string;player_ids:string[]}[];events:Event[];initial_state:{at:MatchTime;score:Record<string,number>}}
export type History={items:Match[];total:number}
export type World={catalog:Catalog;players:Player[];asOf:string;throughDate:string}

export async function getData<T>(url:string,signal?:AbortSignal):Promise<T>{
  const response=await fetch(url,{signal,credentials:'omit',cache:'no-store'})
  if(!response.ok)throw new Error('This view could not be loaded. Please try again.')
  return response.json() as Promise<T>
}
export async function loadWorld(signal:AbortSignal):Promise<World>{
  const [catalog,a,b,matches]=await Promise.all([
    getData<Catalog>('/api/data/catalog',signal),
    getData<{items:Player[]}>('/api/data/players?featured=false&limit=100',signal),
    getData<{items:Player[]}>('/api/data/players?featured=false&limit=100&offset=100',signal),
    getData<{items:Match[]}>('/api/data/matches?featured=true',signal),
  ])
  const throughDate=matches.items.map(m=>m.kickoff.slice(0,10)).sort().at(-1)
  if(!throughDate)throw new Error('The match library is unavailable.')
  // An explicit library snapshot, shown in the UI, keeps every profile/comparison
  // on the same date. Match replay uses its own causal source clock instead.
  const asOf=new Date(Date.parse(`${throughDate}T00:00:00Z`)+86400000).toISOString().replace('.000Z','Z')
  return {catalog,players:[...a.items,...b.items],asOf,throughDate}
}
export function useResource<T>(key:string,load:(signal:AbortSignal)=>Promise<T>){
  const [retry,setRetry]=useState(0)
  const [state,setState]=useState<{key:string;data?:T;error?:string}>({key:''})
  useEffect(()=>{
    const controller=new AbortController();let current=true
    setState({key})
    load(controller.signal).then(data=>{if(current)setState({key,data})}).catch(error=>{
      if(current&&error?.name!=='AbortError'&&!(error instanceof StaleFanResponse))setState({key,error:'We couldn’t load this view. Please try again.'})
    })
    return()=>{current=false;controller.abort()}
  },[key,retry]) // key includes the full viewing context, including preferences.
  return {...(state.key===key?state:{}),retry:()=>setRetry(v=>v+1)}
}
export function useFan<T extends FanResponse>(key:string,load:(client:ReturnType<typeof createFanClient>)=>Promise<FanResponse>){
  return useResource<T>(key,async signal=>{
    const client=createFanClient();signal.addEventListener('abort',client.cancel,{once:true})
    try{return await load(client) as T}finally{signal.removeEventListener('abort',client.cancel);client.cancel()}
  })
}
export const contextKey=(p:FanPreferences,season:string)=>JSON.stringify([p,season])
export const shortName=(name:string)=>name.split(' ').map(n=>n[0]).slice(0,2).join('')
export const roleName=(role:string,zh=false)=>({GK:zh?'门将':'Goalkeeper',DF:zh?'后卫':'Defender',MF:zh?'中场':'Midfielder',FW:zh?'前锋':'Forward'}[role]??role)
export const dateLabel=(date:string,zh=false)=>new Intl.DateTimeFormat(zh?'zh-CN':'en-GB',{day:'numeric',month:'short',year:'numeric',timeZone:'UTC'}).format(new Date(date))
export function tileValue(tile:Tile){
  if(tile.value===null)return '—'
  return new Intl.NumberFormat('en-GB',{maximumFractionDigits:tile.unit==='per90'?2:tile.unit==='percent'||tile.unit==='estimate'?1:0}).format(tile.value)+(tile.unit==='percent'?'%':'')
}
export function visiblePlayers(players:Player[],search:string,club:string,role:string,following:string[]|null){
  const q=search.trim().toLocaleLowerCase()
  return players.filter(p=>p.featured&&(!q||p.name.toLocaleLowerCase().includes(q))&&(!club||p.club_id===club)&&(!role||p.role===role)&&(!following||following.includes(p.player_id))).sort((a,b)=>Number(b.star)-Number(a.star)||a.name.localeCompare(b.name))
}
