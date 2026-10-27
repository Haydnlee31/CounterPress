import {AgentPortrait} from './AgentPortrait'
import {FootieLoader} from '../shell/FootieLoader'
import {useMobileLayout} from '../shell/useMobileLayout'
import {useState,useId} from 'react'
import type {ReactNode} from 'react'
import {PlayerOptions} from './PlayerOptions'
import {MetricMap} from './MetricBoard'
import {clockLabel,metricValue,recentRange} from './data'
import type {Analysis,DiscussionMessage,Evidence,Metric,Role,Snapshot} from './data'

function OpenArrow(){return <svg width="16" height="16" viewBox="0 0 20 20" fill="none" aria-hidden="true" focusable="false" style={{verticalAlign:'middle'}}><path d="M5 15 15 5M6 5h9v9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>}
function ReplyArrow(){return <svg width="13" height="13" viewBox="0 0 20 20" fill="none" aria-hidden="true" focusable="false"><path d="M4 3v9h12m-4-4 4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>}

export const specialists:{role:Role;name:string;caption:string;mark:ReactNode;keys:string[]}[]=[
  {role:'players',name:'Player Analyst',caption:'The people shaping the game',mark:<AgentPortrait role="players"/>,keys:['passes','pass_accuracy','goals','assists','shots','duels_won']},
  {role:'control',name:'Match Analyst',caption:'Control, territory & momentum',mark:<AgentPortrait role="control"/>,keys:['event_share','pass_accuracy','final_third_entries','tempo']},
  {role:'chance',name:'Chance Analyst',caption:'Creation & finishing',mark:<AgentPortrait role="chance"/>,keys:['shots','shots_on_target','goals','xg_authored']},
  {role:'defence',name:'Defensive Analyst',caption:'Recoveries & transitions',mark:<AgentPortrait role="defence"/>,keys:['duels_won','recoveries','verified_turnovers','saves']},
]
const name=(role:string)=>specialists.find(s=>s.role===role)?.name??'Footie'
function MessageCard({message,round,onEvidence}:{message:DiscussionMessage;round:Analysis;onEvidence?:(e:Evidence)=>void}){
  const [proof,setProof]=useState(false)
  const metrics=round.metrics?.filter(m=>message.metric_ids.includes(m.id))??[]
  const evidence=round.evidence?.filter(e=>message.evidence_ids.includes(e.id))??[]
  const prose=(text:string)=>(round.metrics??[]).reduce((value,m)=>m.player_id?value.replaceAll(` (${m.player_id})`,''):value,text)
  return <article className={`an-chat-message an-role-${message.role}`}>
    <span className="an-agent-avatar" aria-hidden="true">{message.role==='footie'?<AgentPortrait role="footie"/>:specialists.find(s=>s.role===message.role)?.mark}</span>
    <div className="an-message-content"><header><strong>{name(message.role)}</strong><time>{clockLabel(round.cutoff)}</time>{message.role==='footie'&&<span className="an-chair-label">Round-up</span>}</header>
      {message.reply_to&&<div className="an-reply"><ReplyArrow/> {message.relation==='challenges'?'Questions':message.relation==='qualifies'?'Adds context to':'Builds on'} {name(message.reply_to)}</div>}
      <p>{prose(message.text)}</p>{message.watch_next&&<p className="an-next"><strong>Watch next</strong> {prose(message.watch_next)}</p>}
      <button className="an-proof-button" aria-expanded={proof} onClick={()=>setProof(!proof)}>{proof?'Hide evidence':'See evidence'} <span aria-hidden="true">{proof?'−':'+'}</span></button>
      {proof&&<div className="an-message-proof">{metrics.map(m=><div key={m.id}><span>{m.label}<small>{(m as Metric&{subject?:string}).subject??'Match'} · {m.window==='prefix'?'Match so far':m.window==='current'?'Recent window':'Previous window'}</small></span><b>{metricValue(m)}</b></div>)}{evidence.map(e=><button className="an-evidence-action" key={e.id} disabled={!onEvidence} onClick={()=>onEvidence?.(e)} aria-label={`Replay ${e.kind} at ${clockLabel(e)}`}><span>{e.kind==='shot'?'Shot':e.kind==='pass'?'Pass':e.kind==='recovery'?'Recovery':'Recorded action'} · {e.outcome.replaceAll('_',' ')}</span><time>{clockLabel(e)}</time><span aria-hidden="true">↗</span></button>)}{!metrics.length&&!evidence.length&&<p>Evidence belongs to this discussion’s match snapshot.</p>}</div>}
    </div>
  </article>
}
export function AnalystConversation({rounds,pending,failed,available,playing,ready=true,analysis,discussionStatus,refresh,onEvidence,live=false}:{rounds:Analysis[];pending:boolean;failed?:boolean;available:boolean;playing:boolean;live?:boolean;ready?:boolean;analysis:Analysis|null;discussionStatus?:string;refresh:()=>void;onEvidence?:(e:Evidence)=>void}){
  const entries=rounds.flatMap(round=>(round.messages??[]).map(message=>({round,message})))
  const latest=entries.at(-1),older=entries.slice(0,-1)
  const outcome=discussionStatus??analysis?.status
  const unavailable=!pending&&(failed||outcome==='unavailable')
  const limited=!pending&&['hourly_limit','daily_limit','budget_limit'].includes(outcome??'')
  const disconnected=!available||outcome==='disabled'
  const status=pending?(live?'Reading the latest spell':'Analysts discussing'):unavailable?'Discussion unavailable':limited?'Analysis allowance reached':disconnected?'Discussion offline':playing?'Following the match':'Replay paused'
  const emptyTitle=pending?'The analysts are comparing their findings.':unavailable?'The discussion couldn’t update.':limited?'Discussion is paused.':disconnected?'Explore the analysts’ workspaces.':'The analysts are watching.'
  const emptyCopy=pending?(live?'A specialist is reading this spell. Footie checks the contribution before it appears.':'Checking the specialists’ findings and Footie’s review may take about two minutes. You can keep exploring the match.'):unavailable?'You can retry the discussion below. Match statistics remain available.':limited?'You can keep exploring the match statistics.':disconnected?'Live discussion is not connected in this preview. The statistics below follow the replay.':playing?'As the game develops, the analysts connect player performances, chances and the bigger match picture.':'Start the replay. As the game develops, the analysts connect player performances, chances and the bigger match picture.'
  return <section className={`an-room ${live?'an-live-room':''}`} aria-labelledby="analyst-room-title"><div className="an-room-heading"><div><p className="an-eyebrow">AT THE ANALYST TABLE</p><h2 id="analyst-room-title">The conversation</h2></div><div className="an-room-status"><span className={pending?'is-thinking':''}>{status}</span>{available&&<button disabled={pending||!ready} onClick={refresh}>Discuss this spell</button>}</div></div>
    <div className="an-conversation an-latest-comment" role="log" aria-live="polite" aria-atomic="true" aria-label="Latest analyst comment">
      {latest?<MessageCard key={`${latest.round.snapshot_id}:${latest.message.id}`} message={latest.message} round={latest.round} onEvidence={onEvidence}/>:<div className="an-room-empty"><div className="an-room-avatars" aria-hidden="true">{specialists.map(s=><span key={s.role}>{s.mark}</span>)}</div><h3>{emptyTitle}</h3><p>{emptyCopy}</p></div>}
    </div>
    {older.length>0&&<details className="an-conversation-history"><summary>Earlier conversation <span>{older.length} {older.length===1?'comment':'comments'}</span></summary><div className="an-history-scroll" role="region" aria-label="Earlier analyst comments" tabIndex={0}>{[...older].reverse().map(({round,message})=><MessageCard key={`${round.snapshot_id}:${message.id}`} message={message} round={round} onEvidence={onEvidence}/>)}</div></details>}
    {unavailable&&<p className="an-room-notice" role="status">The discussion couldn’t update. Statistics are still following play. <button onClick={refresh}>Try again</button></p>}
    {limited&&<p className="an-room-notice">The analysis allowance has been reached. You can keep exploring the match statistics.</p>}
    {analysis?.status==='partial'&&!pending&&<p className="an-room-notice">Showing the reviewed contributions. Some findings could not be verified.</p>}
  </section>
}
function StatPairs({snapshot,keys,playerId}:{snapshot:Snapshot;keys:string[];playerId?:string}){
  const metrics=snapshot.metrics.filter(m=>m.window==='prefix'&&m.presentation!=='evidence_only'&&(playerId?m.player_id===playerId:!m.player_id))
  return <div className={`an-desk-stats ${playerId?'is-player':''}`}>{!playerId&&<div className="an-desk-stat-labels"><span>Match so far</span>{snapshot.clubs.map(c=><span key={c.club_id}>{c.name}</span>)}</div>}{keys.map(key=>{const rows=metrics.filter(m=>m.key===key),first=rows[0];return <div key={key} className="an-desk-stat"><span>{first?.label??key.replaceAll('_',' ')}</span>{(playerId?[rows[0]]:snapshot.clubs.map(c=>rows.find(m=>m.club_id===c.club_id))).map((m,i)=><b key={i} title={m?.basis.replaceAll('_',' ')}>{m?metricValue(m):'—'}</b>)}</div>})}</div>
}
function Momentum({snapshot}:{snapshot:Snapshot}){
  const graphId=useId().replaceAll(':','')
  const points=snapshot.momentum??[],xs=points.map((p,i)=>`${5+i*290/Math.max(1,points.length-1)},${45-p.value*34}`).join(' ')
  return <div className="an-momentum an-momentum-ribbon"><div><strong>Match momentum</strong><span>Attacking threat</span></div><svg viewBox="0 0 300 100" role="img" aria-label="Match momentum, rolling five-minute threat balance"><defs><clipPath id={`${graphId}-upper`}><rect width="300" height="45"/></clipPath><clipPath id={`${graphId}-lower`}><rect y="45" width="300" height="45"/></clipPath></defs><path d="M5 45H295" stroke="#a6b59e" strokeDasharray="2 3"/>{points.length>1&&<><polygon points={`5,45 ${xs} 295,45`} fill="#b4be7a" clipPath={`url(#${graphId}-upper)`}/><polygon points={`5,45 ${xs} 295,45`} fill="#91b8c2" clipPath={`url(#${graphId}-lower)`}/><polyline points={xs} fill="none" stroke="#31594b" strokeWidth="1.6"/></>}<text x="5" y="98" fontSize="8" fill="#667760">Kick-off</text><text x="295" y="98" fontSize="8" textAnchor="end" fill="#667760">{clockLabel(snapshot.cutoff)}</text></svg><div><span>{snapshot.clubs[0]?.name} ↑</span><span>{snapshot.clubs[1]?.name} ↓</span></div><p>Rolling five-minute event-based threat balance</p></div>
}
export function SpecialistDesks({snapshot,rounds,focusPlayerId,setFocus,open,pitch,conversation}:{snapshot:Snapshot|null;rounds:Analysis[];focusPlayerId:string|null;setFocus:(id:string|null)=>void;open:(role:Role)=>void;pitch?:ReactNode;conversation?:ReactNode}){
  const [active,setActive]=useState<Role>('players')
  const mobile=useMobileLayout()
  const leader=snapshot?.metrics.filter(m=>m.window==='prefix'&&m.key==='on_ball_actions'&&m.player_id&&typeof m.value==='number').sort((a,b)=>Number(b.value)-Number(a.value))[0]?.player_id
  const playerId=focusPlayerId??leader??snapshot?.players[0]?.player_id??''
  const picker=snapshot?<label className="an-desk-picker">Follow a player<select aria-label="Player to analyse" value={focusPlayerId??''} onChange={e=>setFocus(e.target.value||null)}><option value="">Automatic spotlight</option><PlayerOptions snapshot={snapshot}/></select>{!focusPlayerId&&<small>{snapshot.players.find(p=>p.player_id===playerId)?.name} · most on-ball actions</small>}</label>:null
  return <section aria-label="Specialist workspaces" className="an-desks"><div className="an-desks-grid">{mobile&&snapshot&&<div className="an-mobile-focus"><AgentPortrait role="players"/>{picker}</div>}<div className="an-pitch-seat">{pitch}{conversation}</div><div className="an-desk-switcher" role="group" aria-label="Choose analyst workspace">{specialists.map(s=><button key={s.role} aria-pressed={active===s.role} onClick={()=>setActive(s.role)}>{s.name}</button>)}</div>{snapshot?specialists.map(s=>{
    const sourceRound=[...rounds].reverse().find(r=>r.messages?.some(m=>m.role===s.role))
    const reading=sourceRound?.messages?.find(m=>m.role===s.role)
    const fresh=sourceRound&&sourceRound.cutoff.period===snapshot.cutoff.period&&snapshot.cutoff.elapsed_ms>=sourceRound.cutoff.elapsed_ms&&snapshot.cutoff.elapsed_ms-sourceRound.cutoff.elapsed_ms<=180000
    return <article key={s.role} data-active={active===s.role} className={`an-desk an-role-${s.role}`}><header><span className="an-agent-avatar" aria-hidden="true">{s.mark}</span><div><h3>{s.name}</h3><p>{s.caption}</p></div><button aria-label={`Explore ${s.name} statistics`} onClick={()=>open(s.role)}><OpenArrow/></button></header>
      {!mobile&&s.role==='players'&&picker}
      <StatPairs snapshot={snapshot} keys={s.keys.slice(0,s.role==='players'?4:3)} playerId={s.role==='players'?playerId:undefined}/>
      {s.role==='control'&&<Momentum snapshot={snapshot}/>}

      {reading&&sourceRound&&(fresh?<details className="an-desk-reading"><summary>Finding · {clockLabel(sourceRound.cutoff)}</summary><p>{reading.text}</p></details>:<p className="an-desk-reading">Earlier finding from {clockLabel(sourceRound.cutoff)} — read it in the conversation above.</p>)}
      <footer><span>{s.role==='control'?recentRange(snapshot):'Match so far'}</span><button onClick={()=>open(s.role)}>All statistics <OpenArrow/></button></footer>
    </article>
  }):<FootieLoader compact label="Loading match statistics…"/>}</div></section>
}
