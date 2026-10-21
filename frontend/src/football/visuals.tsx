import {useState,type CSSProperties} from 'react'
import {ClubCrest} from '../matchday/ClubCrest'
import type {Club,Heatmap,Player,Tile} from './data'
import {shortName,tileValue} from './data'
import {playerPortraits,portraitSrcSet} from './portraits'

export function Badge({club}:{club:Club}){
  if(club.club_id==='eastbridge'||club.club_id==='northport')return <ClubCrest club={club.club_id}/>
  return <svg className="fh-badge" viewBox="0 0 80 90" role="img" aria-label={`${club.name} crest`}>
    <path d="M7 7Q40-2 73 7V48Q72 72 40 87Q8 72 7 48Z" fill={club.primary_color} stroke="#fff1cf" strokeWidth="3"/>
    <path d="M14 13Q40 5 66 13V46Q65 65 40 78Q15 65 14 46Z" fill="none" stroke="#fff1cf" opacity=".5"/>
    {club.club_id==='southbank'?<><path d="M20 43h40L40 24ZM25 45v16m10-16v16m10-16v16m10-16v16M20 63h40" stroke="#fff1cf" strokeWidth="4" fill="#fff1cf"/><path d="M21 69q9-4 19 0t19 0" stroke="#fff1cf" fill="none"/></>:club.club_id==='redhaven'?<><path d="m40 25 4 12 16 5-13 8 1 14-8-7-8 7 1-14-13-8 16-5Z" fill="#fff1cf"/><path d="m40 30 0 23m-11-11 22 0" stroke={club.primary_color} strokeWidth="2"/></>:<text x="40" y="53" textAnchor="middle" fill="#fff1cf" fontSize="20" fontWeight="800">{club.short_name}</text>}
    <text x="40" y="20" textAnchor="middle" fill="#fff1cf" fontSize="7" letterSpacing="2">{club.short_name}</text>
  </svg>
}
export function Shirt({player,club,profile=false}:{player:Player;club:Club;profile?:boolean}){
  const [failed,setFailed]=useState<string|null>(null)
  const portrait=playerPortraits[player.player_id]
  if(portrait&&failed!==portrait)return <span className="fh-player-portrait"><img src={portrait} srcSet={portraitSrcSet(player.player_id)} sizes={profile?'(max-width: 760px) 112px, 240px':'(max-width: 760px) 44vw, (max-width: 1100px) 28vw, 300px'} alt={`${player.name} in ${club.name} colours`} loading="lazy" decoding="async" width="1254" height="1254" onError={()=>setFailed(portrait)}/><span className="fh-portrait-number">#{player.number}</span></span>
  return <svg className="fh-shirt" viewBox="0 0 220 210" aria-hidden="true">
    <ellipse cx="110" cy="193" rx="73" ry="8" fill="#000" opacity=".12"/>
    <path d="m72 27 21-8q17 15 34 0l21 8 48 37-28 36-18-13 6 101H64l6-101-18 13-28-36Z" fill={club.primary_color}/>
    <path d="m72 27-7 152m83-152 7 152" stroke="white" opacity=".12" strokeWidth="8"/>
    <path d="m93 19q17 23 34 0" stroke="#fff1cf" strokeWidth="5" fill="none"/>
    <path d="m29 62 26 32m136-32-26 32" stroke="#fff1cf" strokeWidth="6"/>
    <text x="110" y="68" textAnchor="middle" fill="#fff1cf" fontSize="10" fontWeight="700" letterSpacing="4">{shortName(player.name)}</text>
    <text x="110" y="145" textAnchor="middle" fill="#fff1cf" fontSize="73" fontWeight="800" fontFamily="Arial,sans-serif">{player.number}</text>
  </svg>
}
export function Tiles({tiles}:{tiles:Tile[]}){
  return <dl className="fh-tiles">{tiles.map(tile=><div key={tile.metric}><dt>{tile.label}</dt><dd>{tileValue(tile)}</dd>{tile.value===null?<small>Not available</small>:tile.coverage==='partial'?<small>{tile.coverage_label??'Partial coverage'}</small>:tile.unit==='estimate'?<small>Estimated</small>:null}</div>)}</dl>
}
export function ActivityMap({map,zh=false}:{map:Heatmap;zh?:boolean}){
  const max=Math.max(1,...map.cells.map(c=>c.actions))
  return <section className="fh-panel fh-activity"><div className="fh-section-head"><div><p className="fh-eyebrow">{zh?'活动热区':'ON THE PITCH'}</p><h2>{map.label}</h2></div><span>{map.total_actions.toLocaleString()} {zh?'次参与':'actions'}</span></div>
    <svg viewBox="-3 -3 111 74" role="img" aria-label={zh?'球员参与事件热图，进攻方向向右':'Action heatmap, attacking to the right'}>
      <rect x="-3" y="-3" width="111" height="74" rx="3" fill="#123d33"/>
      {map.cells.map(c=><rect key={`${c.column}-${c.row}`} x={c.column*105/map.columns} y={c.row*68/map.rows} width={105/map.columns} height={68/map.rows} fill="#d6ef7e" opacity={c.actions===0?0:.08+.85*c.actions/max}><title>{c.actions} {zh?'次参与':'actions'}</title></rect>)}
      <g fill="none" stroke="#f5f3dd" strokeWidth=".4" opacity=".7"><rect width="105" height="68"/><path d="M52.5 0v68M0 14h16.5v40H0M105 14H88.5v40H105M0 25h5.5v18H0M105 25h-5.5v18h5.5"/><circle cx="52.5" cy="34" r="9.15"/></g>
    </svg><div className="fh-map-key"><span>{zh?'较少':'Less'} <i/> {zh?'较多':'More'}</span><span>{zh?'进攻方向 →':'Attacking →'}</span></div>
  </section>
}
export const clubStyle=(club?:Club)=>({'--fh-club':club?.primary_color??'#193e33'} as CSSProperties)
