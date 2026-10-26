import {useState} from 'react'
import type {ReactNode} from 'react'
import {MetricMap} from './MetricBoard'
import {clockLabel,metricValue,recentRange} from './data'
import type {Analysis,DiscussionMessage,Evidence,Metric,Role,Snapshot} from './data'

function OpenArrow(){return <svg width="16" height="16" viewBox="0 0 20 20" fill="none" aria-hidden="true" focusable="false" style={{verticalAlign:'middle'}}><path d="M5 15 15 5M6 5h9v9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>}
function ReplyArrow(){return <svg width="13" height="13" viewBox="0 0 20 20" fill="none" aria-hidden="true" focusable="false"><path d="M4 3v9h12m-4-4 4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>}

export const specialists:{role:Role;name:string;caption:string;mark:ReactNode;keys:string[]}[]=[
  {role:'players',name:'Player Analyst',caption:'The people shaping the game',mark:'◎',keys:['passes','pass_accuracy','goals','assists','shots','duels_won']},
  {role:'control',name:'Match Analyst',caption:'Control, territory & momentum',mark:'≋',keys:['event_share','pass_accuracy','final_third_entries','tempo']},
  {role:'chance',name:'Chance Analyst',caption:'Creation & finishing',mark:<OpenArrow/>,keys:['shots','shots_on_target','goals','xg_authored']},
  {role:'defence',name:'Defensive Analyst',caption:'Recoveries & transitions',mark:'⇄',keys:['duels_won','recoveries','verified_turnovers','saves']},
]
const name=(role:string)=>specialists.find(s=>s.role===role)?.name??'Footie'
function MessageCard({message,round,onEvidence}:{message:DiscussionMessage;round:Analysis;onEvidence?:(e:Evidence)=>void}){
  const [proof,setProof]=useState(false)
  const metrics=round.metrics?.filter(m=>message.metric_ids.includes(m.id))??[]
  const evidence=round.evidence?.filter(e=>message.evidence_ids.includes(e.id))??[]
  const prose=(text:string)=>(round.metrics??[]).reduce((value,m)=>m.player_id?value.replaceAll(` (${m.player_id})`,''):value,text)
  return <article className={`an-chat-message an-role-${message.role}`}>
    <span className="an-agent-avatar" aria-hidden="true">{message.role==='footie'?'F':specialists.find(s=>s.role===message.role)?.mark}</span>
    <div className="an-message-content"><header><strong>{name(message.role)}</strong><time>{clockLabel(round.cutoff)}</time>{message.role==='footie'&&<span className="an-chair-label">Round-up</span>}</header>
      {message.reply_to&&<div className="an-reply"><ReplyArrow/> {message.relation==='challenges'?'Questions':message.relation==='qualifies'?'Adds context to':'Builds on'} {name(message.reply_to)}</div>}
      <p>{prose(message.text)}</p>{message.watch_next&&<p className="an-next"><strong>Watch next</strong> {prose(message.watch_next)}</p>}
      <button className="an-proof-button" aria-expanded={proof} onClick={()=>setProof(!proof)}>{proof?'Hide evidence':'See evidence'} <span aria-hidden="true">{proof?'−':'+'}</span></button>
      {proof&&<div className="an-message-proof">{metrics.map(m=><div key={m.id}><span>{m.label}<small>{(m as Metric&{subject?:string}).subject??'Match'} · {m.window==='prefix'?'Match so far':m.window==='current'?'Recent window':'Previous window'}</small></span><b>{metricValue(m)}</b></div>)}{evidence.map(e=><button className="an-evidence-action" key={e.id} disabled={!onEvidence} onClick={()=>onEvidence?.(e)} aria-label={`Replay ${e.kind} at ${clockLabel(e)}`}><span>{e.kind==='shot'?'Shot':e.kind==='pass'?'Pass':e.kind==='recovery'?'Recovery':'Recorded action'} · {e.outcome.replaceAll('_',' ')}</span><time>{clockLabel(e)}</time><span aria-hidden="true">↗</span></button>)}{!metrics.length&&!evidence.length&&<p>Evidence belongs to this discussion’s match snapshot.</p>}</div>}
    </div>
  </article>
}
export function AnalystConversation({rounds,pending,failed,available,playing,ready=true,analysis,refresh,onEvidence}:{rounds:Analysis[];pending:boolean;failed?:boolean;available:boolean;playing:boolean;ready?:boolean;analysis:Analysis|null;refresh:()=>void;onEvidence?:(e:Evidence)=>void}){
  const last=rounds.at(-1),older=rounds.slice(0,-1)
  return <section className="an-room" aria-labelledby="analyst-room-title"><div className="an-room-heading"><div><p className="an-eyebrow">AT THE ANALYST TABLE</p><h2 id="analyst-room-title">The conversation</h2></div><div className="an-room-status"><span className={pending?'is-thinking':''}>{pending?'Analysts discussing':playing?'Following the match':'Replay paused'}</span>{available&&<button disabled={pending||!ready} onClick={refresh}>Discuss this spell</button>}</div></div>
    <div className="an-conversation" role="log" aria-live="polite" aria-relevant="additions">
      {older.length>0&&<details className="an-earlier-rounds"><summary>Earlier discussion <span>{older.length} {older.length===1?'round':'rounds'}</span></summary>{older.map(round=><div key={round.snapshot_id} className="an-chat-round">{round.messages?.map(m=><MessageCard key={m.id} message={m} round={round} onEvidence={onEvidence}/>)}</div>)}</details>}
      {last?.messages?.length?<div key={last.snapshot_id} className="an-chat-round">{last.messages.map(m=><MessageCard key={m.id} message={m} round={last} onEvidence={onEvidence}/>)}</div>:<div className="an-room-empty"><div className="an-room-avatars" aria-hidden="true">{specialists.map(s=><span key={s.role}>{s.mark}</span>)}</div><h3>{pending?'The analysts are comparing their findings.':available?'The analysts are watching.':'Explore the analysts’ workspaces.'}</h3><p>{pending?'Checking the specialists’ findings and Footie’s review may take about two minutes. You can keep exploring the match.':available?'Start the replay. As the game develops, the analysts connect player performances, chances and the bigger match picture.':'Live discussion is not connected in this preview. The statistics below follow the replay.'}</p></div>}
    </div>
    {(failed||analysis?.status==='unavailable')&&<p className="an-room-notice" role="status">The discussion couldn’t update. Statistics are still following play. <button onClick={refresh}>Try again</button></p>}
    {analysis&&['hourly_limit','daily_limit','budget_limit'].includes(analysis.status)&&<p className="an-room-notice">The analysis allowance has been reached. You can keep exploring the match statistics.</p>}
    {analysis?.status==='insufficient_evidence'&&!pending&&<p className="an-room-notice">No new supported reading in this spell. The analysts will revisit as play develops.</p>}
    {pending&&last&&<p className="an-room-notice" role="status">Comparing the latest spell…</p>}
  </section>
}
function StatPairs({snapshot,keys,playerId}:{snapshot:Snapshot;keys:string[];playerId?:string}){
  const metrics=snapshot.metrics.filter(m=>m.window==='prefix'&&m.presentation!=='evidence_only'&&(playerId?m.player_id===playerId:!m.player_id))
  return <div className={`an-desk-stats ${playerId?'is-player':''}`}>{!playerId&&<div className="an-desk-stat-labels"><span>Match so far</span>{snapshot.clubs.map(c=><span key={c.club_id}>{c.name}</span>)}</div>}{keys.map(key=>{const rows=metrics.filter(m=>m.key===key),first=rows[0];return <div key={key} className="an-desk-stat"><span>{first?.label??key.replaceAll('_',' ')}</span>{(playerId?[rows[0]]:snapshot.clubs.map(c=>rows.find(m=>m.club_id===c.club_id))).map((m,i)=><b key={i} title={m?.basis.replaceAll('_',' ')}>{m?metricValue(m):'—'}</b>)}</div>})}</div>
}
function Momentum({snapshot}:{snapshot:Snapshot}){
  const points=snapshot.momentum??[],xs=points.map((p,i)=>`${5+i*290/Math.max(1,points.length-1)},${45-p.value*34}`).join(' ')
  return <div className="an-momentum"><div><strong>Match momentum</strong><span>Rolling threat balance</span></div><svg viewBox="0 0 300 90" role="img" aria-label="Match momentum, rolling five-minute threat balance"><path d="M5 45H295" stroke="#9aab98" strokeDasharray="2 3"/>{points.length>1&&<polyline points={xs} fill="none" stroke="#3b7053" strokeWidth="2"/>}</svg><div><span>{snapshot.clubs[0]?.name} ↑</span><span>{snapshot.clubs[1]?.name} ↓</span></div><p>Through {clockLabel(snapshot.cutoff)} · event-based index</p></div>
}
export function SpecialistDesks({snapshot,rounds,focusPlayerId,setFocus,open}:{snapshot:Snapshot|null;rounds:Analysis[];focusPlayerId:string|null;setFocus:(id:string|null)=>void;open:(role:Role)=>void}){
  const [club,setClub]=useState(''),[player,setPlayer]=useState('')
  if(!snapshot)return <div className="an-stat-loading" role="status">Loading match statistics…</div>
  const clubId=snapshot.clubs.some(c=>c.club_id===club)?club:snapshot.clubs[0]?.club_id??''
  const playerId=snapshot.players.some(p=>p.player_id===(focusPlayerId||player))?focusPlayerId||player:snapshot.players[0]?.player_id??''
  return <section aria-label="Specialist workspaces" className="an-desks"><div className="an-desks-heading"><div><p className="an-eyebrow">THE SPECIALISTS</p><h2>Follow their findings</h2></div><p>Statistics through {clockLabel(snapshot.cutoff)}</p></div><div className="an-desks-grid">{specialists.map(s=>{
    const sourceRound=rounds.at(-1)
    const reading=sourceRound?.messages?.find(m=>m.role===s.role)
    const fresh=sourceRound&&sourceRound.cutoff.period===snapshot.cutoff.period&&snapshot.cutoff.elapsed_ms>=sourceRound.cutoff.elapsed_ms&&snapshot.cutoff.elapsed_ms-sourceRound.cutoff.elapsed_ms<=180000
    return <article key={s.role} className={`an-desk an-role-${s.role}`}><header><span className="an-agent-avatar" aria-hidden="true">{s.mark}</span><div><h3>{s.name}</h3><p>{s.caption}</p></div><button aria-label={`Explore ${s.name} statistics`} onClick={()=>open(s.role)}><OpenArrow/></button></header>
      {s.role==='players'&&<label className="an-desk-picker">Follow a player<select aria-label="Player to analyse" value={playerId} onChange={e=>{setPlayer(e.target.value);setFocus(e.target.value)}}>{snapshot.players.map(p=><option key={p.player_id} value={p.player_id}>{p.name}</option>)}</select></label>}
      <StatPairs snapshot={snapshot} keys={s.keys} playerId={s.role==='players'?playerId:undefined}/>
      {s.role==='control'&&<Momentum snapshot={snapshot}/>}
      {true&&<><div className="an-desk-map-title"><strong>{s.role==='players'?'Player heatmap':s.role==='chance'?'Shot map':s.role==='control'?'Match heatmap':'On-ball activity'}</strong>{s.role!=='players'&&<select aria-label={`${s.name} map club`} value={clubId} onChange={e=>setClub(e.target.value)}>{snapshot.clubs.map(c=><option key={c.club_id} value={c.club_id}>{c.name}</option>)}</select>}</div><MetricMap metrics={snapshot.metrics.filter(m=>m.window==='prefix')} view={s.role==='chance'?'shot_map':'heatmap'} clubId={clubId} playerId={s.role==='players'?playerId:undefined}/></>}
      {reading&&sourceRound&&(fresh?<div className="an-desk-reading"><small>Discussion through {clockLabel(sourceRound.cutoff)}</small><p>{reading.text}</p></div>:<p className="an-desk-reading">Earlier finding from {clockLabel(sourceRound.cutoff)} — read it in the conversation above.</p>)}
      <footer><span>{s.role==='control'?recentRange(snapshot):'Match so far'}</span><button onClick={()=>open(s.role)}>All statistics <OpenArrow/></button></footer>
    </article>
  })}</div></section>
}
