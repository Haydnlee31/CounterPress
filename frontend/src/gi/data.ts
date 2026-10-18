import { playerName } from '../matchday/identity'
export type GIEvent = {
  event_id:string; provider_event_id:number; revision:number; source_order:number; occurrence_order:number;
  period:1|2; elapsed_ms:number; team_id:number; player_id:string; kind:string; detail:string; outcome:string;
  start:{x:number;y:number}|null; end:{x:number;y:number}|null; goal_for:number|null; review:boolean; tags:number[];
}
export type GIPlayer={player_id:string;provider_player_id:number;team_id:number;alias_id:string}
export type GIMatch={match_id:string; title:string; competition:string;date:string;
  teams:{team_id:number;name:string;score:number}[]; players:GIPlayer[]; events:GIEvent[];
  source:{provider:string;source:string;license:string;license_url:string;changes:string;fixture_sha256:string};
  video_url:string;video_alignment:'unverified';metric_policy:string;
}
export type Filter='key'|'all'|'shots'|'off_target'|'passes'|'incomplete'|'review'
export const filters: [Filter,string][]=[['key','Key moments'],['all','Every action'],['shots','All shots'],['off_target','Shots off target'],['passes','All passes'],['incomplete','Unsuccessful passes'],['review','Moments to review']]
export function alias(player:GIPlayer) {
  const name=playerName(player.alias_id)
  return name===player.alias_id ? `${player.team_id===4418?'Eastbridge':'Northport'} substitute ${Number(player.alias_id.slice(2))-11}` : name
}
export function matchClock(e:GIEvent) {
  const seconds=Math.floor(e.elapsed_ms/1000), mins=Math.floor(seconds/60)
  return mins>=45 ? `${e.period===1?45:90}+${mins-45}:${String(seconds%60).padStart(2,'0')}` : `${mins+(e.period===2?45:0)}:${String(seconds%60).padStart(2,'0')}`
}
export function selectEvents(events:GIEvent[],filter:Filter,team:string,player:string,period:string) {
  return events.filter(e=>(!team||String(e.team_id)===team)&&(!player||e.player_id===player)&&(!period||String(e.period)===period)&&
    (filter==='all'||filter==='key'&&(e.goal_for!==null||e.review)||filter==='shots'&&e.kind==='Shot'||filter==='off_target'&&e.kind==='Shot'&&e.outcome==='off_target'||filter==='passes'&&e.kind==='Pass'||filter==='incomplete'&&e.kind==='Pass'&&e.outcome==='incomplete'||filter==='review'&&e.review))
}
export function outcomeText(e:GIEvent) {
  const text:Record<string,string>={goal:'Goal',own_goal:'Own goal',complete:'Pass completed',incomplete:'Pass unsuccessful',off_target:'Shot off target',blocked:'Shot blocked',woodwork:'Hit the woodwork',on_target:'Shot on target'}
  const actions:Record<string,string>={'Ground attacking duel':'Challenged on the ball','Ground defending duel':'Challenged for the ball','Ground loose ball duel':'Contested a loose ball','Air duel':'Aerial challenge','Acceleration':'Run with the ball','Touch':'Ball touch','Reflexes':'Goalkeeper reaction','Goalkeeper leaving line':'Goalkeeper came off the line','Hand foul':'Handball','Save attempt':'Goalkeeper intervention'}
  return text[e.outcome] ?? (e.kind==='Pass'?'Pass · outcome unavailable':e.kind==='Shot'?'Shot · outcome unavailable':(actions[e.detail]??e.detail)||e.kind)
}
