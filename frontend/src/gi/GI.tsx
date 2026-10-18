import { currentMatchId, matchDate } from './catalog'
import { PlaySequence } from './PlaySequence'
import { readGIWorkspace, saveGIWorkspace } from './session'
import { readPreferences } from '../matchday/preferences'
import { AppHeader } from '../shell/AppHeader'
import { useEffect, useMemo, useState } from 'react'
import type { CSSProperties } from 'react'
import { alias, filters, matchClock, outcomeText, selectEvents } from './data'
import type { Filter, GIMatch, GIEvent } from './data'
import { ClubCrest } from '../matchday/ClubCrest'
import { clubs } from '../matchday/identity'
import '../matchday/matchday.css'
import './gi.css'

function ActionPitch({event,name,shots,onSelect,names}:{event:GIEvent;name:string;shots?:GIEvent[];onSelect:(id:string)=>void;names:Map<string,string>}) {
  return <svg className="gi-pitch" viewBox="-5 -5 115 78" role={shots?"group":"img"} aria-label={shots?"Shot locations. Both clubs attack from left to right.":`${outcomeText(event)} by ${name}. Attacking from left to right.`}>
    <defs><marker id="gi-arrow" markerWidth="5" markerHeight="5" refX="4" refY="2.5" orient="auto"><path d="M0 0L5 2.5L0 5" fill={event.team_id===4418?"#e7c771":"#a9d5f7"}/></marker></defs>
    <rect x="-5" y="-5" width="115" height="78" rx="3" fill="#153e35"/>
    {[0,1,2,3,4,5,6].map(i=><rect key={i} x={i*15} y="0" width="15" height="68" fill={i%2?'#ffffff08':'#ffffff00'}/>)}
    <g fill="none" stroke="#ffffff65" strokeWidth=".35"><rect width="105" height="68"/><path d="M52.5 0V68M0 13.84H16.5V54.16H0M105 13.84H88.5V54.16H105M0 24.84H5.5V43.16H0M105 24.84H99.5V43.16H105"/><circle cx="52.5" cy="34" r="9.15"/></g>
    <text x="52.5" y="-1.5" fill="#c5d5cf" fontSize="2.1" textAnchor="middle">ATTACKING DIRECTION →</text>
    {shots?.map(shot=>shot.start && <g key={shot.event_id} role="button" tabIndex={0} aria-label={`${matchClock(shot)} ${outcomeText(shot)}, ${names.get(shot.player_id)}`} onClick={()=>onSelect(shot.event_id)} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();onSelect(shot.event_id)}}} className="gi-shot-pin">
      <circle cx={shot.start.x} cy={shot.start.y} r={shot.outcome==='goal'?2.3:1.6} fill={shot.team_id===4418?'#e7c771':'#a9d5f7'} stroke={shot.event_id===event.event_id?'#fff':'#163c32'} strokeWidth={shot.event_id===event.event_id?'.8':'.4'}/><title>{names.get(shot.player_id)} · {outcomeText(shot)}</title>
    </g>)}
    {!shots && event.start && <>{event.end && event.kind==='Pass' && <line x1={event.start.x} y1={event.start.y} x2={event.end.x} y2={event.end.y} stroke={event.team_id===4418?"#e7c771":"#a9d5f7"} strokeWidth=".7" strokeDasharray={event.outcome==='incomplete'?'2 1':undefined} markerEnd="url(#gi-arrow)"/>}
      <circle cx={event.start.x} cy={event.start.y} r="3.5" fill={event.team_id===4418?"#e7c771":"#a9d5f7"} stroke="#fff" strokeWidth=".4"/><text x={event.start.x} y={event.start.y+1} textAnchor="middle" fontWeight="700" fontSize="2.5" fill="#153e35">{name.split(' ').map(n=>n[0]).slice(0,2).join('')}</text><title>{name}</title></>}
  </svg>
}

export default function GI() {
  const [view,setView]=useState<'overview'|'moments'>('overview')
  const [guide,setGuide]=useState(false)
  const [matchId]=useState(currentMatchId)
  const [saved]=useState(()=>readGIWorkspace(matchId))
  const [preference]=useState(readPreferences)
  const theme=clubs[(preference.club_id??'eastbridge') as keyof typeof clubs]
  const [match,setMatch]=useState<GIMatch|null>(null),[error,setError]=useState(false),[attempt,setAttempt]=useState(0)
  const [filter,setFilter]=useState<Filter>(saved.filter),[team,setTeam]=useState(saved.team),[player,setPlayer]=useState(saved.player),[period,setPeriod]=useState(saved.period)
  const [map,setMap]=useState(saved.map)
  const [selected,setSelected]=useState<string|null>(saved.selected),[limit,setLimit]=useState(40)
  useEffect(()=>{const controller=new AbortController();setError(false)
    fetch(`/api/gi/matches/${matchId}`,{signal:controller.signal}).then(r=>{if(!r.ok)throw Error();return r.json()}).then(setMatch).catch(e=>{if(e.name!=='AbortError')setError(true)})
    return ()=>controller.abort()
  },[attempt,matchId])
  useEffect(()=>saveGIWorkspace({filter,team,player,period,selected,map},matchId),[filter,team,player,period,selected,map,matchId])
  useEffect(()=>{if(match&&player&&!match.players.some(p=>p.player_id===player&&(!team||String(p.team_id)===team)))setPlayer('')},[match,player,team])
  const names=useMemo(()=>new Map(match?.players.map(p=>[p.player_id,alias(p)])),[match])
  const records=useMemo(()=>selectEvents(match?.events??[],filter,team,player,period),[match,filter,team,player,period])
  const scope=useMemo(()=>selectEvents(match?.events??[],'all',team,player,period),[match,team,player,period])
  useEffect(()=>{setLimit(40)},[filter,team,player,period])
  const current=records.find(e=>e.event_id===selected)??records[0]
  const currentIndex=current?match!.events.findIndex(e=>e.event_id===current.event_id):-1
  const context=current?match!.events.filter(e=>e.period===current.period).filter(e=>e.elapsed_ms>current.elapsed_ms-10000&&e.elapsed_ms<=current.elapsed_ms+10000):[]
  const teamName=(id:number)=>id===4418?'Eastbridge':id===9598?'Northport':''
  const clubId=(id:number)=>id===4418?'eastbridge':'northport'
  const goals=match?.events.filter(e=>e.goal_for!==null)??[]
  function inspect(id:string) {setSelected(id);document.getElementById('gi-detail')?.focus({preventScroll:true});if(window.matchMedia?.('(max-width: 800px)').matches)document.getElementById('gi-detail')?.scrollIntoView({block:'start'})}
  function jump(id:string) {setView('moments');setFilter('all');setTeam('');setPlayer('');setPeriod('');setSelected(id);requestAnimationFrame(()=>{document.getElementById('gi-detail')?.focus({preventScroll:true});document.getElementById('gi-detail')?.scrollIntoView({block:'start'})})}
  const metricCards:[Filter,string,number][]=[['shots','Shots',scope.filter(e=>e.kind==='Shot').length],['off_target','Off target',scope.filter(e=>e.kind==='Shot'&&e.outcome==='off_target').length],['passes','Passes',scope.filter(e=>e.kind==='Pass').length],['incomplete','Unsuccessful passes',scope.filter(e=>e.kind==='Pass'&&e.outcome==='incomplete').length]]
  return <div className="matchday gi" data-club={preference.club_id??'eastbridge'} style={{'--fan-accent':theme.accent,'--fan-ink':theme.ink,'--fan-background':theme.background,'--fan-soft':theme.soft} as CSSProperties}>
    <a className="fan-skip" href="#gi-content" onClick={e=>{e.preventDefault();document.getElementById('gi-content')?.focus()}}>Skip to match centre</a>
    <AppHeader active="gi"/>
    <main id="gi-content" tabIndex={-1}>
      {error?<section role="alert"><h1>The match couldn’t load</h1><button onClick={()=>setAttempt(n=>n+1)}>Try again</button></section>:!match?<p role="status">Opening match centre…</p>:<>
        <section className="gi-match-header" aria-label="Match result">
          <div className="gi-match-label"><span className="gi-live-dot"/> FULL TIME <span>MATCH CENTRE</span></div>
          <h1 aria-label={`Eastbridge ${match.teams[0].score} – ${match.teams[1].score} Northport`}><span className="gi-club"><ClubCrest club="eastbridge"/>Eastbridge</span><span className="gi-score">{match.teams[0].score}<i>:</i>{match.teams[1].score}</span><span className="gi-club">Northport<ClubCrest club="northport"/></span></h1>
          <p><time dateTime={match.display_date}>{matchDate(match.display_date)}</time></p>
          <p>{match.teams[0].score===match.teams[1].score?'Full time · All square':`${match.teams[0].score>match.teams[1].score?'Eastbridge':'Northport'} win`} · {goals.length} goals</p>
        </section>
        <div className="gi-view-switch" role="group" aria-label="Match centre view"><button aria-pressed={view==='overview'} onClick={()=>setView('overview')}>Overview</button><button aria-pressed={view==='moments'} onClick={()=>setView('moments')}>Moments</button><button onClick={()=>setGuide(!guide)} aria-expanded={guide}>How to explore</button></div>
        {guide&&<aside className="gi-guide" aria-label="Match centre guide"><h2>Your match, at a glance</h2><p>Start with the score and team comparisons. Select a goal below to open its build-up. In Moments, watch the play unfold, or open Filters to follow a player or half.</p><button onClick={()=>{setView('moments');setGuide(false)}}>Take me to the moments →</button><button onClick={()=>setGuide(false)}>Close guide</button></aside>}
        {view==='overview'&&<section className="gi-overview" aria-label="Full match overview"><div className="gi-editorial"><p className="fan-kicker">THE MATCH IN NUMBERS</p><h2>{match.headline}</h2><p>{match.summary}</p><button onClick={()=>setView('moments')}>Explore the key moments ↗</button></div><div className="gi-comparisons"><div className="gi-comparison-clubs"><strong>Eastbridge</strong><strong>Northport</strong></div>{(['Shots','Passes completed','Passes unsuccessful','Shots off target'] as const).map(label=>{const counts=[4418,9598].map(id=>match.events.filter(e=>e.team_id===id&&(label==='Shots'?e.kind==='Shot':label==='Shots off target'?e.kind==='Shot'&&e.outcome==='off_target':e.kind==='Pass'&&e.outcome===(label==='Passes completed'?'complete':'incomplete'))).length);return <div className="gi-comparison" key={label}><div><strong>{counts[0]}</strong><span>{label}</span><strong>{counts[1]}</strong></div><div className="gi-comparison-bar"><i style={{flex:counts[0]||.01}}/><i style={{flex:counts[1]||.01}}/></div></div>})}</div></section>}
        <div hidden={view!=='moments'}>
        <details className="gi-filter-disclosure"><summary>Filters · club, player & half</summary>
        <div className="gi-toolbar">
          <div className="gi-team-tabs" role="group" aria-label="Team">{[['','Both clubs'],['4418','Eastbridge'],['9598','Northport']].map(([id,label])=><button key={id} aria-pressed={team===id} onClick={()=>{setTeam(id);setPlayer('')}}>{id&&<span className={`gi-team-dot ${id==='9598'?'away':''}`}/>}{label}</button>)}</div>
          <label className="gi-player-select"><span>Follow a player</span><select aria-label="Player" value={player} onChange={e=>setPlayer(e.target.value)}><option value="">Everyone</option>{match.players.filter(p=>!team||String(p.team_id)===team).map(p=><option key={p.player_id} value={p.player_id}>{alias(p)} · {teamName(p.team_id)}</option>)}</select></label>
          <div className="gi-period-tabs" role="group" aria-label="Period">{[['','Full match'],['1','1st half'],['2','2nd half']].map(([id,label])=><button key={id} aria-pressed={period===id} onClick={()=>setPeriod(id)}>{label}</button>)}</div>
        </div>
        </details>
        <div className="gi-workspace">
          <section className="gi-detail" id="gi-detail" tabIndex={-1} aria-label="Selected action">
            <div className="gi-canvas-toolbar"><span><span className="gi-live-dot"/> ON THE PITCH</span><div role="group" aria-label="Pitch view"><button aria-pressed={!map} onClick={()=>setMap(false)}>Selected play</button><button aria-pressed={map} onClick={()=>setMap(true)}>Shot map <span>{scope.filter(e=>e.kind==='Shot').length}</span></button></div></div>
            {current?<>
              <div className="gi-detail-heading"><p className="fan-kicker">{teamName(current.team_id)} <span> / </span> {matchClock(current)}</p><h2>{outcomeText(current)}</h2><p><span className="gi-player-avatar">{(names.get(current.player_id)??'').split(' ').map(n=>n[0]).slice(0,2).join('')}</span>{names.get(current.player_id)}</p></div>
              <>{!map?(view==='moments'&&<PlaySequence key={current.event_id} events={match.events} event={current} names={names} players={match.players}/>):<ActionPitch event={current} name={names.get(current.player_id)??'Player'} shots={map?scope.filter(e=>e.kind==='Shot'):undefined} onSelect={id=>{setFilter('shots');inspect(id)}} names={names}/>}</>
              <div className="gi-canvas-caption"><span>{map?'Select a shot to explore the play':current.start?'Follow the highlighted players':'Location unavailable for this action'}</span>{map&&<span className="gi-legend"><i/>Eastbridge <i/>Northport</span>}</div>
              <div className="gi-scrubber"><time>{matchClock(current)}</time><input aria-label="Match timeline" aria-valuetext={matchClock(current)} type="range" min={0} max={match.events.length-1} value={currentIndex} onChange={e=>jump(match.events[Number(e.target.value)].event_id)}/><span>FT</span></div>
              <div className="gi-step"><button disabled={currentIndex<=0} onClick={()=>jump(match.events[currentIndex-1].event_id)}>← Previous action</button><span>{current.period===1?'FIRST HALF':'SECOND HALF'}</span><button disabled={currentIndex>=match.events.length-1} onClick={()=>jump(match.events[currentIndex+1].event_id)}>Next action →</button></div>
            </>:<div className="gi-canvas-empty"><h2>No plays in this view</h2><p>Try another player or half to explore their match.</p><button onClick={()=>{setTeam('');setPlayer('');setPeriod('');setFilter('key')}}>Show key moments</button></div>}
          </section>
          <section className="gi-actions" aria-label="Match actions"><div className="gi-actions-heading"><span className="fan-kicker">THE MATCH, UNPACKED</span><h2>Find your moment<span>↘</span></h2></div>
            <div className="gi-topic-tabs" role="group" aria-label="Explore actions">{filters.map(([id,label])=><button key={id} aria-pressed={filter===id} onClick={()=>setFilter(id)}>{label}</button>)}</div>
            <div className="gi-results"><span>{records.length} {records.length===1?'play':'plays'}{player?` · ${names.get(player)}`:''}</span><button onClick={()=>{setTeam('');setPlayer('');setPeriod('');setFilter('key')}}>Reset filters</button></div>
            {!records.length?<p className="gi-empty">No actions match these filters. Try another player or period.</p>:<ol className="gi-action-list">{records.slice(0,limit).map(e=><li key={e.event_id}><button aria-current={e.event_id===current?.event_id?'true':undefined} onClick={()=>inspect(e.event_id)}><time>{matchClock(e)}</time><span><strong>{outcomeText(e)}</strong><small><i className={`gi-team-dot ${e.team_id===9598?'away':''}`}/>{names.get(e.player_id)} · {teamName(e.team_id)}</small></span><span aria-hidden="true">↗</span></button></li>)}</ol>}
            {records.length>limit&&<button className="gi-more" onClick={()=>setLimit(n=>n+40)}>Show more actions ({records.length-limit} remaining)</button>}
          </section>
        </div>
        </div>
        <section className="gi-goals" aria-label="Goal timeline"><div><span className="fan-kicker">GOAL BY GOAL</span><h2>The story in goals.</h2></div><div className="gi-goal-ribbon">{goals.map((e,i)=><button key={e.event_id} onClick={()=>jump(e.event_id)} aria-current={current?.event_id===e.event_id?'true':undefined}><time>{matchClock(e)}</time><span className="gi-goal-marker"><ClubCrest club={clubId(e.goal_for!)}/></span><strong>{goals.slice(0,i+1).filter(g=>g.goal_for===4418).length} – {goals.slice(0,i+1).filter(g=>g.goal_for===9598).length}</strong><span>{e.outcome==='own_goal'?'Own goal':names.get(e.player_id)}</span></button>)}</div></section>
        <div className="gi-below" hidden={view!=='moments'}><section className="gi-stats" aria-label="Match statistics"><p className="fan-kicker">LOOK A LITTLE CLOSER</p><h2>Shots &amp; passes.<br/>A closer look.</h2><p className="gi-scope-label">{team?teamName(Number(team)):'Both clubs'} · {period?period==='1'?'First half':'Second half':'Full match'}{player?` · ${names.get(player)}`:''}</p><div>{metricCards.map(([id,label,count])=><button key={id} aria-pressed={filter===id} onClick={()=>{setFilter(id);document.getElementById('gi-detail')?.scrollIntoView({block:'start',behavior:'instant'})}}><span>{label}</span><strong>{count}</strong><span aria-hidden="true">↗</span></button>)}</div></section>
          <section className="gi-context"><p className="fan-kicker">CONNECT THE PLAYS</p><h2>Around this moment</h2>{current?<><p>Ten seconds either side of {matchClock(current)}.</p>{current.goal_for!==null&&<p className="gi-insight">{teamName(current.goal_for)} add a goal{current.outcome==='own_goal'?' through an own goal':''}.</p>}{current.review&&<p className="gi-insight">A dangerous loss of the ball. Follow the surrounding plays to see what happened next.</p>}<ol>{context.map(e=><li key={e.event_id}><button aria-current={e.event_id===current.event_id?'true':undefined} onClick={()=>jump(e.event_id)}><time>{matchClock(e)}</time><span>{names.get(e.player_id)}<strong>{outcomeText(e)}</strong></span><span aria-hidden="true">↗</span></button></li>)}</ol></>:<p>Select a play to follow the sequence.</p>}</section></div>
        <footer className="fan-footer gi-footer">{match.video_url&&<a href={match.video_url} target="_blank" rel="noreferrer">Watch source match ↗</a>}{match.synthetic?<p>Original CounterPress match generated from aggregate football patterns. Calibration: 15 licensed Wyscout matches; fictional clubs and players.</p>:<p>Eastbridge, Northport and player names are display aliases. Actions and the result are adapted from {match.source_label}. Substitute labels identify additional participants.</p>}<p>{match.synthetic?'Calibration data:':'Event data:'} Luca Pappalardo & Emanuele Massucco / Wyscout · <a href={match.source.source} target="_blank" rel="noreferrer">Original dataset</a> · <a href={match.source.license_url} target="_blank" rel="noreferrer">CC BY 4.0</a>. {match.synthetic?'Generated actions and outcomes are new; source matches supply aggregate calibration only.':'Adapted with display aliases, scaled coordinates and outcome classifications.'}</p><details><summary>Sources & how the numbers are counted</summary>{current&&<p>{current.provider_event_id===null?`Generated event ${current.event_id}`:`Wyscout event ${current.provider_event_id}`} · revision {current.revision}. {current.period===1?'First':'Second'} half, {(current.elapsed_ms/1000).toFixed(2)} seconds.</p>}<p>Pitch locations use a 105 × 68 metre display, with the acting team attacking right. The replay reconstructs the action with a full-team formation. Supporting positions and movement are illustrative, not continuous tracking. Video timing has not been verified; the source link opens the original replay.</p><p>{match.metric_policy} On-target shots without a goal are not automatically labelled saves. An unsuccessful pass is a recorded outcome, not a judgment of the player.</p></details></footer>
      </>}
    </main>
  </div>
}
