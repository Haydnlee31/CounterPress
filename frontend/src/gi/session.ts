import { filters } from './data'
import type { Filter } from './data'
export const giSessionKey='counterpress.gi.workspace.v1'
export type GIWorkspace={filter:Filter;team:string;player:string;period:string;selected:string|null;map:boolean}
const defaults:GIWorkspace={filter:'key',team:'',player:'',period:'',selected:null,map:false}
export function readGIWorkspace(matchId='wyscout-2058017'):GIWorkspace {
  try {
    const value=JSON.parse(sessionStorage.getItem(matchId==='wyscout-2058017'?giSessionKey:`${giSessionKey}.${matchId}`)??'null')
    if(!value||typeof value!=='object')return {...defaults}
    return {filter:filters.some(([id])=>id===value.filter)?value.filter:'key',team:['','4418','9598'].includes(value.team)?value.team:'',
      player:typeof value.player==='string'&&(matchId.startsWith('synthetic-')?/^(eb|np)\d{2}$/:/^wyscout-player-\d+$/).test(value.player)?value.player:'',period:['','1','2'].includes(value.period)?value.period:'',
      selected:typeof value.selected==='string'&&(matchId.startsWith('synthetic-')?/^a\d{5}$/:/^wyscout-\d+$/).test(value.selected)?value.selected:null,map:value.map===true}
  }catch{return {...defaults}}
}
export function saveGIWorkspace(value:GIWorkspace,matchId='wyscout-2058017') {try{sessionStorage.setItem(matchId==='wyscout-2058017'?giSessionKey:`${giSessionKey}.${matchId}`,JSON.stringify(value))}catch{/* Browsing still works when storage is blocked. */}}
