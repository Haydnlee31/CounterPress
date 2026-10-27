import {useEffect,useState,useId} from 'react'
import {PlayerOptions} from './PlayerOptions'
import {clockLabel,coverageLabel,finiteMetric,metricUnit,metricValue,recentRange} from './data'
import type {Metric,Role,Snapshot} from './data'
export function MetricMap({metrics,view,clubId,playerId}:{metrics:Metric[];view:'heatmap'|'shot_map'|'pass_routes';clubId:string;playerId?:string}){
  const mapId=useId().replaceAll(':','')
  const metric=metrics.find(m=>m.key===view&&(playerId?m.player_id===playerId:m.club_id===clubId&&!m.player_id))
  const value=metric?.value&&typeof metric.value==='object'&&!Array.isArray(metric.value)?metric.value:null
  const cells=(Array.isArray(value?.cells)?value.cells:[]) as {column:number;row:number;count:number}[]
  const shots=(Array.isArray(value?.shots)?value.shots:[]) as {event_id:string;x:number;y:number;outcome:string;end?:{x:number;y:number}|null;xg_authored?:number|null;xg_geometry?:number}[]
  const passes=(Array.isArray(value?.passes)?value.passes:[]) as {event_id:string;start:{x:number;y:number};end:{x:number;y:number};outcome:string}[]
  const max=Math.max(1,...cells.map(c=>c.count))
  const available=!!value&&metric?.status!=='unavailable'
  const passColor=(outcome:string)=>['complete','completed'].includes(outcome)?'#e7c771':outcome==='incomplete'?'#ee9d86':'#a5b7b1'
  const validPoint=(p:{x:number;y:number})=>Number.isFinite(p.x)&&Number.isFinite(p.y)&&p.x>=0&&p.x<=105&&p.y>=0&&p.y<=68
  return <div className="an-map"><svg viewBox="-3 -7 111 78" role="img" aria-label={view==='heatmap'?'On-ball activity map, attacking right':view==='shot_map'?'Shot locations and recorded trajectories, attacking right':'Pass routes, attacking right'}>
    <rect x="-3" y="-7" width="111" height="78" rx="3" fill="#173e33"/>
    <defs><radialGradient id={`${mapId}-density`}><stop stopColor="#f2d77b" stopOpacity=".95"/><stop offset=".5" stopColor="#b8cd79" stopOpacity=".55"/><stop offset="1" stopColor="#b8cd79" stopOpacity="0"/></radialGradient><clipPath id={`${mapId}-pitch`}><rect width="105" height="68"/></clipPath><marker id={`${mapId}-arrow`} markerWidth="5" markerHeight="5" refX="4" refY="2.5" orient="auto"><path d="M0 0L5 2.5L0 5Z" fill="context-stroke"/></marker></defs>
    {view==='heatmap'&&cells.filter(c=>Number.isFinite(c.count)&&c.column>=0&&c.column<12&&c.row>=0&&c.row<8).map(c=><circle clipPath={`url(#${mapId}-pitch)`} key={`${c.column}:${c.row}`} cx={(c.column+.5)*8.75} cy={(c.row+.5)*8.5} r={6+7*Math.sqrt(c.count/max)} fill={`url(#${mapId}-density)`} opacity={.25+.7*c.count/max}/>)}
    <g fill="none" stroke="#c7d9c899" strokeWidth=".35"><rect width="105" height="68"/><path d="M52.5 0V68M0 13.84H16.5V54.16H0M105 13.84H88.5V54.16H105"/><circle cx="52.5" cy="34" r="9.15"/></g>
    <text x="52.5" y="-2.5" textAnchor="middle" fill="#e7eddf" fontSize="2.1">ATTACKING DIRECTION →</text>
    {view==='pass_routes'&&passes.filter(p=>p.start&&p.end&&validPoint(p.start)&&validPoint(p.end)).slice(-100).map(p=><g key={p.event_id} opacity=".5"><line x1={p.start.x} y1={p.start.y} x2={p.end.x} y2={p.end.y} stroke={passColor(p.outcome)} strokeWidth=".45"/><circle cx={p.end.x} cy={p.end.y} r=".7" fill={passColor(p.outcome)}/></g>)}
    {view==='shot_map'&&shots.filter(validPoint).map(s=>{const color=s.outcome==='goal'?'#f2d176':['saved','on_target'].includes(s.outcome)?'#abd8f0':s.outcome==='blocked'?'#bac4b7':'#eeaa90';return <g key={s.event_id}><title>{s.outcome.replaceAll('_',' ')}{s.end?' · recorded shot path':' · location only'}</title>{s.end&&validPoint(s.end)&&<path className="an-shot-path" d={`M${s.x} ${s.y}L${s.end.x} ${s.end.y}`} fill="none" stroke={color} strokeWidth=".65" opacity=".8" strokeDasharray={s.outcome==='goal'?undefined:'1.6 .9'} markerEnd={`url(#${mapId}-arrow)`}/>}<circle cx={s.x} cy={s.y} r={s.outcome==='goal'?2.1:1.3} fill={color} stroke="#fff" strokeWidth=".3"/></g>})}
    {!(view==='heatmap'?cells.length:view==='shot_map'?shots.length:passes.length)&&<text x="52.5" y="35" textAnchor="middle" fill="#fffef0" fontSize="3">{available?'No recorded actions yet':'Map unavailable for this view'}</text>}
  </svg><p className="an-map-legend">{view==='heatmap'?<>On-ball activity <span className="an-density-key">Low <i/> High</span></>:view==='shot_map'?<><span><i style={{background:'#f2d176'}}/> Goal</span><span><i style={{background:'#abd8f0'}}/> On target</span><span><i style={{background:'#eeaa90'}}/> Off target</span><span><i style={{background:'#bac4b7'}}/> Blocked</span></>:'Last 100 passes · gold completed, coral unsuccessful'}</p>{view==='shot_map'&&<small className="an-path-note">Paths connect recorded start and end points; attempts without endpoints remain dots.</small>}</div>
}

export function MetricBoard({snapshot,lens,focusPlayerId}:{snapshot:Snapshot|null;lens:Role;focusPlayerId:string|null}){
  const [window,setWindow]=useState<'prefix'|'current'>('prefix')
  const [visual,setVisual]=useState<'heatmap'|'shot_map'|'pass_routes'>('heatmap')
  const [subject,setSubject]=useState(focusPlayerId?`player:${focusPlayerId}`:'')
  useEffect(()=>setSubject(focusPlayerId?`player:${focusPlayerId}`:''),[focusPlayerId])
  const all=(snapshot?.metrics??[]).filter(m=>m.presentation!=='evidence_only'),clubs=snapshot?.clubs??[]
  const selectedPlayer=subject.startsWith('player:')&&snapshot?.players.some(p=>p.player_id===subject.slice(7))?subject.slice(7):undefined
  const selectedClub=clubs.some(c=>`club:${c.club_id}`===subject)?subject.slice(5):clubs[0]?.club_id??''
  const selectedSubject=selectedPlayer?`player:${selectedPlayer}`:`club:${selectedClub}`
  const selected=all.filter(m=>m.window===window&&m.role===lens&&!m.player_id)
  const keys=[...new Set(selected.filter(finiteMetric).map(m=>m.key))]
  const unavailable=[...new Set(selected.filter(m=>m.status==='unavailable'||m.value===null).map(m=>m.label))]
  const names=new Map(snapshot?.players.map(p=>[p.player_id,p.name]))
  const players=all.filter(m=>m.window===window&&m.player_id&&finiteMetric(m))
  const playerKeys=[...new Set(players.map(m=>m.key))]
  const [playerKey,setPlayerKey]=useState('goals')
  const actualPlayerKey=playerKeys.includes(playerKey)?playerKey:playerKeys[0]
  const ranks=players.filter(m=>m.key===actualPlayerKey&&finiteMetric(m)).sort((a,b)=>Number(b.value)-Number(a.value)).slice(0,10)
  if(!snapshot)return <div className="an-stat-loading" role="status">Loading match statistics…</div>
  return <section className="an-metric-board" aria-label="Match statistics"><div className="an-section-head"><div><p className="an-eyebrow">THE EVIDENCE</p><h2>See the pattern.</h2></div><div className="an-segment" role="group" aria-label="Statistics time window"><button aria-pressed={window==='prefix'} onClick={()=>setWindow('prefix')}>Match so far</button><button aria-pressed={window==='current'} onClick={()=>setWindow('current')}>Recent play</button></div></div>
    <p className="an-window-range">{window==='current'?recentRange(snapshot):`Kick-off to ${snapshot?clockLabel(snapshot.cutoff):'now'}`}</p><div className="an-metric-layout"><div>
      {lens==='players'&&ranks.length>0?<><label className="an-player-metric">Compare players<select value={actualPlayerKey} onChange={e=>setPlayerKey(e.target.value)}>{playerKeys.map(key=><option key={key} value={key}>{players.find(m=>m.key===key)?.label}</option>)}</select></label><ol className="an-rankings">{ranks.map((m,i)=><li key={m.id}><span>{String(i+1).padStart(2,'0')}</span><strong>{names.get(m.player_id!)??'Player'}</strong><b>{metricValue(m)} <small>{metricUnit(m)}</small></b></li>)}</ol></>:<>
        <div className="an-club-head"><span>Measure</span>{clubs.map(c=><strong key={c.club_id}>{c.name}</strong>)}</div>
        {keys.length?<div className="an-stat-list">{keys.map(key=>{const group=selected.filter(m=>m.key===key),first=group[0],global=group.find(v=>!v.club_id);return <details className={`an-stat-row ${global?'an-stat-global':''}`} key={key}><summary><span>{first.label}</span>{global?<strong aria-label={`Match-wide ${first.label}: ${metricValue(global)}`}>{metricValue(global)}<small>Match-wide</small></strong>:clubs.map(c=>{const m=group.find(v=>v.club_id===c.club_id);return <strong key={c.club_id}>{m?metricValue(m):'—'}{m&&<small>{metricUnit(m)}</small>}</strong>})}</summary><p>{first.basis.replaceAll('_',' ')}{first.unit&&first.unit!=='count'?` · ${first.unit.replaceAll('_',' ')}`:''}. {window==='current'?recentRange(snapshot):'From kick-off to the displayed match time.'} {global&&key==='momentum'?`Positive values favour ${clubs[0]?.name}; negative values favour ${clubs[1]?.name}.`:''}</p>{group.some(m=>coverageLabel(m))&&<div className="an-metric-coverage">{group.filter(m=>coverageLabel(m)).map(m=><p key={m.id}>{clubs.find(c=>c.club_id===m.club_id)?.name}: {coverageLabel(m)}</p>)}</div>}</details>})}</div>:<p className="an-empty">These measures will appear as the match develops.</p>}
      </>}
      {unavailable.length>0&&<details className="an-coverage"><summary>Other measures <span>{unavailable.length}</span></summary><p>These measures need additional source coverage.</p><ul>{unavailable.map(label=><li key={label}>{label}<span>Not available</span></li>)}</ul></details>}
    </div><div className="an-spatial"><div className="an-map-controls"><label><span className="sr-only">Pitch map</span><select aria-label="Pitch map" value={visual} onChange={e=>setVisual(e.target.value as typeof visual)}><option value="heatmap">Activity map</option><option value="shot_map">Shot map</option><option value="pass_routes">Pass routes</option></select></label><label><span className="sr-only">Map subject</span><select aria-label="Map subject" value={selectedSubject} onChange={e=>setSubject(e.target.value)}><optgroup label="Clubs">{clubs.map(c=><option value={`club:${c.club_id}`} key={c.club_id}>{c.name}</option>)}</optgroup><PlayerOptions snapshot={snapshot} prefix="player:"/></select></label></div><MetricMap metrics={all.filter(m=>m.window===window)} view={visual} clubId={selectedClub} playerId={selectedPlayer}/></div></div>
  </section>
}
