import {useCallback,useEffect,useMemo,useState} from 'react'
import {AppHeader} from '../shell/AppHeader'
import {ClubCrest} from '../matchday/ClubCrest'
import {PlaySequence} from '../gi/PlaySequence'
import type {ReplayPlayback} from '../gi/PlaySequence'
import {alias} from '../gi/data'
import type {GIMatch} from '../gi/data'
import {currentMatchId,matchDate,matchLibrary} from '../gi/catalog'
import {readPreferences} from '../../../integrations/personalization/client'
import {clockLabel,finiteMetric,lenses,metricUnit,metricValue} from './data'
import type {Analysis,Metric,Preferences,Reading,Role,Snapshot} from './data'
import {useAnalyst} from './useAnalyst'
import '../matchday/matchday.css'
import '../gi/gi.css'
import './analyst.css'

function initialPreferences():Preferences{
  try{const p=readPreferences(localStorage).preferences;return {language:p.language,depth:p.depth,focus_player_id:p.focus_player_id??null}}
  catch{return {language:'en',depth:'analyst',focus_player_id:null}}
}

function EvidenceLinks({reading,snapshot}:{reading:Reading|NonNullable<Analysis['summary']>;snapshot:Snapshot|null}){
  const rows=snapshot?.evidence.filter(e=>reading.evidence_ids.includes(e.id))??[]
  const names=new Map(snapshot?.players.map(p=>[p.player_id,p.name]))
  return <details className="an-evidence"><summary>Supporting plays <span>{reading.evidence_ids.length}</span></summary>
    {rows.length?<ol>{rows.map(e=><li key={e.id}><time>{clockLabel(e)}</time><span><strong>{names.get(e.player_id)??'Player'}</strong><small>{e.kind==='pass'?'Pass':e.kind==='shot'?'Shot':e.kind==='recovery'?'Ball recovered':e.kind==='pressure'?'Pressure':'On-ball action'}</small></span></li>)}</ol>:<p>The finding is tied to {reading.evidence_ids.length} source {reading.evidence_ids.length===1?'play':'plays'} at its displayed match time.</p>}
  </details>
}

function MetricMap({metrics,view,clubId,playerId}:{metrics:Metric[];view:'heatmap'|'shot_map'|'pass_routes';clubId:string;playerId?:string}){
  const metric=metrics.find(m=>m.key===view&&(playerId?m.player_id===playerId:m.club_id===clubId&&!m.player_id))
  const value=metric?.value&&typeof metric.value==='object'&&!Array.isArray(metric.value)?metric.value:null
  const cells=(Array.isArray(value?.cells)?value.cells:[]) as {column:number;row:number;count:number}[]
  const shots=(Array.isArray(value?.shots)?value.shots:[]) as {event_id:string;x:number;y:number;outcome:string;xg_authored?:number|null;xg_geometry?:number}[]
  const passes=(Array.isArray(value?.passes)?value.passes:[]) as {event_id:string;start:{x:number;y:number};end:{x:number;y:number};outcome:string}[]
  const max=Math.max(1,...cells.map(c=>c.count))
  const validPoint=(p:{x:number;y:number})=>Number.isFinite(p.x)&&Number.isFinite(p.y)&&p.x>=0&&p.x<=105&&p.y>=0&&p.y<=68
  return <div className="an-map"><svg viewBox="-3 -7 111 78" role="img" aria-label={view==='heatmap'?'On-ball activity map, attacking right':view==='shot_map'?'Shot locations, attacking right':'Pass routes, attacking right'}>
    <rect x="-3" y="-7" width="111" height="78" rx="3" fill="#173e33"/>
    {view==='heatmap'&&cells.filter(c=>Number.isFinite(c.count)&&c.column>=0&&c.column<12&&c.row>=0&&c.row<8).map(c=><rect key={`${c.column}:${c.row}`} x={c.column*8.75} y={c.row*8.5} width="8.75" height="8.5" fill="#e8cb7d" opacity={.12+.75*c.count/max}/>)}
    <g fill="none" stroke="#c7d9c899" strokeWidth=".35"><rect width="105" height="68"/><path d="M52.5 0V68M0 13.84H16.5V54.16H0M105 13.84H88.5V54.16H105"/><circle cx="52.5" cy="34" r="9.15"/></g>
    <text x="52.5" y="-2.5" textAnchor="middle" fill="#e7eddf" fontSize="2.1">ATTACKING DIRECTION →</text>
    {view==='pass_routes'&&passes.filter(p=>p.start&&p.end&&validPoint(p.start)&&validPoint(p.end)).slice(-100).map(p=><g key={p.event_id} opacity=".5"><line x1={p.start.x} y1={p.start.y} x2={p.end.x} y2={p.end.y} stroke={['complete','completed'].includes(p.outcome)?'#e7c771':'#ee9d86'} strokeWidth=".45"/><circle cx={p.end.x} cy={p.end.y} r=".7" fill={['complete','completed'].includes(p.outcome)?'#e7c771':'#ee9d86'}/></g>)}
    {view==='shot_map'&&shots.filter(validPoint).map(s=><circle key={s.event_id} cx={s.x} cy={s.y} r={s.outcome==='goal'?2.3:1.5} fill={s.outcome==='goal'?'#e7c771':'#afd3d0'} stroke="#fff" strokeWidth=".35"><title>{s.outcome==='goal'?'Goal':'Shot'}</title></circle>)}
    {!(view==='heatmap'?cells.length:view==='shot_map'?shots.length:passes.length)&&<text x="52.5" y="35" textAnchor="middle" fill="#fffef0" fontSize="3">No recorded actions yet</text>}
  </svg><p>{view==='heatmap'?'Recorded on-ball involvement':view==='shot_map'?'Gold marks goals · all shots shown':'Last 100 passes · gold completed, coral unsuccessful'}</p></div>
}

function MetricBoard({snapshot,lens,focusPlayerId}:{snapshot:Snapshot|null;lens:Role;focusPlayerId:string|null}){
  const [window,setWindow]=useState<'prefix'|'current'>('prefix')
  const [visual,setVisual]=useState<'heatmap'|'shot_map'|'pass_routes'>('heatmap')
  const [subject,setSubject]=useState(focusPlayerId?`player:${focusPlayerId}`:'')
  useEffect(()=>setSubject(focusPlayerId?`player:${focusPlayerId}`:''),[focusPlayerId])
  const all=snapshot?.metrics??[],clubs=snapshot?.clubs??[]
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
  return <section className="an-metric-board" aria-label="Match statistics"><div className="an-section-head"><div><p className="an-eyebrow">THE EVIDENCE</p><h2>See the pattern.</h2></div><div className="an-segment" role="group" aria-label="Statistics time window"><button aria-pressed={window==='prefix'} onClick={()=>setWindow('prefix')}>Match so far</button><button aria-pressed={window==='current'} onClick={()=>setWindow('current')}>Last 5 minutes</button></div></div>
    <div className="an-metric-layout"><div>
      {lens==='players'&&ranks.length>0?<><label className="an-player-metric">Compare players<select value={actualPlayerKey} onChange={e=>setPlayerKey(e.target.value)}>{playerKeys.map(key=><option key={key} value={key}>{players.find(m=>m.key===key)?.label}</option>)}</select></label><ol className="an-rankings">{ranks.map((m,i)=><li key={m.id}><span>{String(i+1).padStart(2,'0')}</span><strong>{names.get(m.player_id!)??'Player'}</strong><b>{metricValue(m)} <small>{metricUnit(m)}</small></b></li>)}</ol></>:<>
        <div className="an-club-head"><span>Measure</span>{clubs.map(c=><strong key={c.club_id}>{c.name}</strong>)}</div>
        {keys.length?<div className="an-stat-list">{keys.map(key=>{const group=selected.filter(m=>m.key===key),first=group[0];return <details className="an-stat-row" key={key}><summary><span>{first.label}</span>{clubs.map(c=>{const m=group.find(v=>v.club_id===c.club_id)??group.find(v=>!v.club_id);return <strong key={c.club_id}>{m?metricValue(m):'—'}{m&&<small>{metricUnit(m)}</small>}</strong>})}</summary><p>{first.basis.replaceAll('_',' ')}{first.unit&&first.unit!=='count'?` · ${first.unit.replaceAll('_',' ')}`:''}. {window==='current'?'The latest five-minute window.':'From kick-off to the displayed match time.'}</p></details>})}</div>:<p className="an-empty">These measures will appear as the match develops.</p>}
      </>}
      {unavailable.length>0&&<details className="an-coverage"><summary>Other measures <span>{unavailable.length}</span></summary><p>These measures need additional source coverage.</p><ul>{unavailable.map(label=><li key={label}>{label}<span>Not available</span></li>)}</ul></details>}
    </div><div className="an-spatial"><div className="an-map-controls"><label><span className="sr-only">Pitch map</span><select aria-label="Pitch map" value={visual} onChange={e=>setVisual(e.target.value as typeof visual)}><option value="heatmap">Activity map</option><option value="shot_map">Shot map</option><option value="pass_routes">Pass routes</option></select></label><label><span className="sr-only">Map subject</span><select aria-label="Map subject" value={selectedSubject} onChange={e=>setSubject(e.target.value)}><optgroup label="Clubs">{clubs.map(c=><option value={`club:${c.club_id}`} key={c.club_id}>{c.name}</option>)}</optgroup><optgroup label="Players">{snapshot?.players.map(p=><option key={p.player_id} value={`player:${p.player_id}`}>{p.name}</option>)}</optgroup></select></label></div><MetricMap metrics={all.filter(m=>m.window===window)} view={visual} clubId={selectedClub} playerId={selectedPlayer}/></div></div>
  </section>
}

function AnalysisLead({analysis,snapshot,pending,failed,foundry,playing,refresh}:{analysis:Analysis|null;snapshot:Snapshot|null;pending:boolean;failed?:boolean;foundry:boolean;playing:boolean;refresh:()=>void}){
  const lead=analysis?.summary??analysis?.readings[0]
  const limited=analysis&&['hourly_limit','daily_limit','budget_limit','busy'].includes(analysis.status)
  const signal=snapshot?.signals[0]
  return <aside className="an-lead" aria-label="Match reading"><div className="an-lead-top"><span className="an-eyebrow">{foundry?'FOOTIE’S MATCH READ':'MATCH SIGNALS'}</span><span className={`an-status ${pending?'is-thinking':''}`}>{pending?'Reading the game':lead?'Updated':playing?'Following play':'Paused'}</span></div>
    {lead?<><time className="an-source-time">At {clockLabel(analysis!.cutoff)}</time><h2>{lead.headline}</h2><p className="an-lead-text">{lead.explanation}</p><EvidenceLinks reading={lead} snapshot={snapshot}/></>:signal?<><time className="an-source-time">At {clockLabel(snapshot!.cutoff)}</time><h2>{signal.title}</h2><p className="an-lead-text">{signal.detail}</p><p className="an-note">From the recorded play</p></>:<><div className="an-empty-mark" aria-hidden="true">↗</div><h2>{playing?'Let the game develop.':'Watch it unfold.'}</h2><p className="an-lead-text">{foundry?'Play the match to follow the chances, changes of control and players making a difference.':'Play the match to explore its patterns, player involvement and chances.'}</p></>}
    {limited&&<p className="an-notice">Live analysis is resting. Match statistics keep updating.</p>}
    {(failed||analysis?.status==='unavailable')&&<div className="an-notice"><p>Live analysis couldn’t update. You can keep watching.</p><button onClick={refresh}>Try again</button></div>}
    {analysis?.status==='partial'&&<p className="an-note">Some specialist readings are still unavailable.</p>}
  </aside>
}

export default function AnalystMode(){
  const [matchId,setMatchId]=useState<string>(currentMatchId)
  const [match,setMatch]=useState<GIMatch|null>(null),[matchError,setMatchError]=useState(false),[attempt,setAttempt]=useState(0)
  const [preferences,setPreferences]=useState(initialPreferences)
  const [playback,setPlayback]=useState<ReplayPlayback>({cutoff:{period:1,elapsed_ms:0},playing:false})
  const [lens,setLens]=useState<Role>('chance')
  const {config,snapshot,analysis,pending,failed,metricsFailed,refresh}=useAnalyst(matchId,playback.cutoff,playback.playing,preferences)
  const names=useMemo(()=>new Map(match?.players.map(p=>[p.player_id,alias(p)])),[match])
  const onPlayback=useCallback((value:ReplayPlayback)=>setPlayback(old=>old.playing===value.playing&&old.cutoff.period===value.cutoff.period&&old.cutoff.elapsed_ms===value.cutoff.elapsed_ms?old:value),[])
  useEffect(()=>{let active=true;const controller=new AbortController();setMatch(null);setMatchError(false)
    fetch(`/api/gi/matches/${encodeURIComponent(matchId)}`,{signal:controller.signal}).then(r=>{if(!r.ok)throw Error();return r.json()}).then(value=>{if(active){if(value.match_id!==matchId||!Array.isArray(value.events)||!value.events.length)throw Error();setMatch(value)}}).catch(e=>{if(active&&e.name!=='AbortError')setMatchError(true)})
    return()=>{active=false;controller.abort()}
  },[matchId,attempt])
  function chooseMatch(value:string){setPlayback({cutoff:{period:1,elapsed_ms:0},playing:false});setMatchId(value);setPreferences(p=>({...p,focus_player_id:null}));const url=new URL(location.href);url.searchParams.set('match',value);history.replaceState(null,'',url)}
  const reading=analysis?.readings.find(r=>r.role===lens)
  const signals=snapshot?.signals.filter(s=>s.role===lens)??[]
  const selectedLens=lenses.find(l=>l.id===lens)!
  return <div className="analyst-mode matchday"><a className="fan-skip" href="#analyst-main">Skip to Analyst Mode</a><AppHeader active="matchday"/>
    <main id="analyst-main" className="an-main" tabIndex={-1}>
      <header className="an-heading"><div><a className="an-back" href="#matchday">← Matchday</a><p className="an-eyebrow">THE FULL MATCH</p><h1>Analyst Mode<span>.</span></h1></div><label className="an-match-picker">Choose a match<select aria-label="Choose a match" value={matchId} onChange={e=>chooseMatch(e.target.value)}>{matchLibrary.map(m=><option value={m.id} key={m.id}>Eastbridge × Northport · {matchDate(m.date)}</option>)}</select></label></header>
      <div className="an-toolbar"><div className="an-matchup"><ClubCrest club="eastbridge"/><span>Eastbridge <i>×</i> Northport</span><ClubCrest club="northport"/></div><details className="an-view-settings"><summary>Your view <span aria-hidden="true">⌄</span></summary><div><label>Detail<select aria-label="Analysis detail" value={preferences.depth} onChange={e=>setPreferences(p=>({...p,depth:e.target.value as Preferences['depth']}))}><option value="casual">Match story</option><option value="analyst">In depth</option></select></label><label>Language<select aria-label="Analysis language" value={preferences.language} onChange={e=>setPreferences(p=>({...p,language:e.target.value as Preferences['language']}))}><option value="en">English</option><option value="zh-Hans">简体中文</option></select></label><label>Player focus<select aria-label="Player focus" value={preferences.focus_player_id??''} onChange={e=>setPreferences(p=>({...p,focus_player_id:e.target.value||null}))}><option value="">Everyone</option>{snapshot?.players.map(p=><option value={p.player_id} key={p.player_id}>{p.name}</option>)}</select></label></div></details></div>
      <section className="an-watch-layout" aria-label="Full match and analysis"><div className="an-pitch-panel">
        {matchError?<div className="an-replay-error" role="alert"><h2>The match couldn’t load.</h2><button onClick={()=>setAttempt(n=>n+1)}>Try again</button></div>:match?<PlaySequence key={matchId} matchId={matchId} events={match.events} event={match.events[0]} names={names} players={match.players} fullMatch hideObservation onPlaybackChange={onPlayback}/>:<div className="an-replay-loading" role="status">Opening the match…</div>}
      </div><AnalysisLead analysis={analysis} snapshot={snapshot} pending={pending} failed={failed} foundry={config?.mode==='foundry'&&config.available} playing={playback.playing} refresh={refresh}/></section>
      <section className="an-lenses" aria-label="Specialist perspectives"><div className="an-lens-tabs" role="group" aria-label="Analysis lens">{lenses.map(l=>{const hasReading=analysis?.readings.some(r=>r.role===l.id);return <button key={l.id} aria-pressed={lens===l.id} onClick={()=>setLens(l.id)}><span className="an-lens-symbol" aria-hidden="true">{l.mark}</span><span><strong>{l.name}</strong><small>{hasReading?'New reading':l.description}</small></span><span className={`an-lens-dot ${hasReading?'has-reading':''}`} aria-hidden="true"/></button>})}</div>
        <div className="an-lens-detail"><div><p className="an-eyebrow">{selectedLens.name.toUpperCase()}</p><h2>{reading?.headline??signals[0]?.title??selectedLens.description}</h2></div><div>{reading?<><p>{reading.explanation}</p>{reading.alternative&&<p className="an-counterpoint"><strong>Another reading</strong>{reading.alternative}</p>}{reading.watch_next&&<div className="an-watch-next"><span aria-hidden="true">↗</span><p><strong>Watch next</strong>{reading.watch_next}</p></div>}<EvidenceLinks reading={reading} snapshot={snapshot}/></>:signals.length?<><p>{signals[0].detail}</p><p className="an-note">Match signal · {clockLabel(snapshot!.cutoff)}</p></>:<p className="an-empty">{pending?'Looking for a supported pattern in this part of the game.':'Explore the numbers below as the match develops.'}</p>}</div></div>
      </section>
      {metricsFailed?<div className="an-notice" role="status">The statistics couldn’t refresh. <button onClick={refresh}>Try again</button></div>:<MetricBoard key={matchId} snapshot={snapshot} lens={lens} focusPlayerId={preferences.focus_player_id}/>}
      <footer className="an-footer"><span>{snapshot?`Statistics through ${clockLabel(snapshot.cutoff)}`:'Statistics update with completed play'}</span><a href={`?match=${encodeURIComponent(matchId)}#gi`}>Open Match Centre ↗</a></footer>
    </main>
  </div>
}
