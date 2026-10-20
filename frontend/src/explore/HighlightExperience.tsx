import { useCallback, useEffect, useRef, useState } from 'react'
import type { Event } from '../types'
import { replayClock } from '../matchday/replayGallery'
import { MatchPitch } from '../matchday/MatchPitch'
import { initials, playerName } from '../matchday/identity'
import { actionLabel, actionText } from '../matchday/pitchScene'
import { replayGallery } from '../matchday/replayGallery'
import { actionCounts, availablePhases, involvedIn, participants, phaseRecords } from './highlightAnalysis'
import '../matchday/matchday.css'
import './explore.css'

/** Both modes share one mounted pitch, audio track and selection. */
export function HighlightExperience({events,storyId,language='en',breakdown=false,onPlayhead}:{events:Event[];storyId:string;language?:string;breakdown?:boolean;onPlayhead?:(head:{index:number;resolved:boolean})=>void}) {
  const story=replayGallery[storyId]
  const zh=language==='zh-Hans', t=(en:string,cn:string)=>zh?cn:en
  const [view,setView]=useState<'build'|'players'|'compare'>('build')
  const [phase,setPhase]=useState(0), [player,setPlayer]=useState<string|null>(null)
  const [head,setHead]=useState({index:0,resolved:false})
  const [seek,setSeek]=useState<{index:number;version:number}>()
  const timelineRef=useRef<HTMLOListElement>(null)
  useEffect(()=>{
    const list=timelineRef.current, active=list?.querySelector('[aria-current]')
    if(!list || !active) return
    const outer=list.getBoundingClientRect(), inner=active.getBoundingClientRect()
    if(inner.right>outer.right) list.scrollLeft+=inner.right-outer.right+8
    else if(inner.left<outer.left) list.scrollLeft-=outer.left-inner.left+8
  },[head.index])
  const [routes,setRoutes]=useState(true)
  function focusRegion(id:string) {
    const region=document.getElementById(id)
    region?.focus({preventScroll:true});region?.scrollIntoView?.({block:'start',behavior:'instant'})
  }
  useEffect(()=>{
    if(breakdown && player && window.matchMedia?.('(max-width: 800px)').matches) focusRegion('explore-insights')
  },[player,breakdown])
  const [left,setLeft]=useState(0), [right,setRight]=useState(1)
  useEffect(()=>{
    setView('build');setPhase(0);setPlayer(null);setHead({index:0,resolved:false});setSeek(undefined);setLeft(0);setRight(1)
  },[storyId])
  const phases=availablePhases(storyId,events), selectedPhase=phases[phase]
  useEffect(()=>{
    const event=events[head.index]
    const at=phases.findIndex(item=>item.ids.includes(event?.event_id))
    if(at>=0) setPhase(at)
  },[head.index,storyId])
  const records=view==='players' && player ? events.filter(e=>involvedIn(e,player)) : selectedPhase ? phaseRecords(selectedPhase,events) : []
  const people=participants(events), counts=actionCounts(events)
  const duration=events.length>1 ? (events.at(-1)!.occurred_at.elapsed_ms-events[0].occurred_at.elapsed_ms)/1000 : 0
  function seekEvent(index:number) {
    setSeek(old=>({index,version:(old?.version ?? 0)+1}))
    if(window.matchMedia?.('(max-width: 800px)').matches) {
      focusRegion('explore-pitch')
    }
  }
  function choosePhase(index:number) {
    setPhase(index)
    const at=events.findIndex(e=>phases[index]?.ids.includes(e.event_id))
    if(at>=0) seekEvent(at)
  }
  function choosePlayer(id:string|null) {setPlayer(id);setView(id?'players':'build')}
  const updateHead=useCallback((value:{index:number;resolved:boolean})=>{setHead(value);onPlayhead?.(value)},[onPlayhead])
  return <div className={`highlight-experience ${breakdown?'is-breakdown':'is-watch'}`}>
    <div hidden={!breakdown}>
        <dl className="explore-facts" aria-label={t('In this highlight','这段集锦')}><div><dt>{t('Action span','进攻时长')}</dt><dd>{duration}{t('s','秒')}</dd></div><div><dt>{t('Passes','传球')}</dt><dd>{counts[0]}</dd></div><div><dt>{t('Players involved','参与球员')}</dt><dd>{people.length}</dd></div><div><dt>{t('Shots','射门')}</dt><dd>{counts[2]}</dd></div></dl>
    </div>
        <div className="explore-workspace">
          <div className="explore-field" id="explore-pitch" tabIndex={-1} aria-label={t('Selected play','所选回放')}>
            <div className="explore-overlay" hidden={!breakdown}><span>{view==='players' ? t('Selected player · passing routes','所选球员 · 传球路线') : t('Selected phase · passing routes','所选阶段 · 传球路线')}</span><label><input type="checkbox" checked={routes} onChange={e=>setRoutes(e.target.checked)}/>{t('Show routes','显示路线')}</label></div>
            <MatchPitch events={events} language={language} compact={breakdown} companion fromStart assistantMatchId={story?.matchId} onPlayhead={updateHead} seekTo={seek} onPlayerSelect={choosePlayer} selectedPlayer={player} routes={breakdown && routes ? records : []}/>
            <section hidden={!breakdown} className="explore-timeline" aria-label={t('Highlight timeline','集锦时间线')}><h2>{t('Every step of the move','进攻的每一步')}</h2><ol ref={timelineRef}>{events.map((event,index)=><li key={`${event.event_id}:${event.revision}`}><button aria-current={index===head.index?'step':undefined} onClick={()=>seekEvent(index)} aria-label={`${replayClock(event)}: ${actionText(event,zh)}`}><time>{replayClock(event)}</time><span className={`explore-event-dot ${event.action.kind==='shot'?'is-shot':''}`}>{index+1}</span><strong>{actionLabel(event,zh)}</strong><span>{playerName(event.actor.player_id)}</span></button></li>)}</ol></section>
          </div>
          <aside hidden={!breakdown} id="explore-insights" tabIndex={-1} className="explore-insights" aria-label={t('Highlight insights','集锦解读')}>
            <button className="explore-back-pitch" onClick={()=>focusRegion('explore-pitch')}>{t('Back to pitch','返回球场')} ↑</button>
            <div className="explore-questions" role="group" aria-label={t('Analysis view','分析视角')}>
              {([['build','Build-up','进攻过程'],['players','Players','球员'],['compare','Compare','比较']] as const).map(([id,en,cn])=><button key={id} aria-pressed={view===id} onClick={()=>setView(id)}>{t(en,cn)}</button>)}
            </div>
            {view==='build' && <><p className="fan-kicker">{t('FOLLOW THE MOVE','进攻脉络')}</p><h2>{t('How did the chance develop?','机会是怎样形成的？')}</h2>
              {phases.length ? <><div className="explore-phases">{phases.map((item,index)=><button key={item.title[0]} aria-pressed={phase===index} onClick={()=>choosePhase(index)}><span>{index+1}</span>{t(...item.title)}</button>)}</div>{selectedPhase && <p className="explore-explanation">{t(...selectedPhase.explanation)}</p>}</> : <p>{t('The plays have changed. Use the timeline to inspect the latest actions.','回放已更新，请通过时间线查看最新事件。')}</p>}
            </>}
            {view==='players' && <><p className="fan-kicker">{t('THE PEOPLE BEHIND THE PLAY','参与这次进攻的球员')}</p><h2>{t('Who was involved?','谁参与其中？')}</h2><p>{t('Select a player on the pitch or below to see their part in the move.','选择球场上或下方的球员，查看他们的参与过程。')}</p>
              <div className="explore-people">{people.map(id=><button key={id} aria-pressed={player===id} onClick={()=>choosePlayer(id)}><span>{initials(id)}</span>{playerName(id)}</button>)}</div>
              {player && <div className="explore-player-summary"><h3>{playerName(player)}</h3><p>{records.length ? t(`Involved in ${records.length} ${records.length===1?'recorded action':'recorded actions'} in this highlight.`, `参与了这段集锦中的${records.length}次记录事件。`) : t('No recorded ball action involves this player in this highlight.','这段集锦中没有涉及该球员的有球事件记录。')}</p></div>}
            </>}
            {view==='compare' && <><p className="fan-kicker">{t('LOOK CLOSER','仔细观察')}</p><h2>{t('How do the phases differ?','不同阶段有何区别？')}</h2><p>{t('Compare the actions in two parts of this highlight.','比较这段集锦中两个阶段的事件。')}</p>
              {phases.length>1 ? <><div className="explore-comparison-selects">{([['First phase',left,setLeft],['Second phase',right,setRight]] as const).map(([label,value,setter],i)=><label key={label}>{t(label,i===0?'第一阶段':'第二阶段')}<select aria-label={t(label,i===0?'第一阶段':'第二阶段')} value={value} onChange={e=>setter(Number(e.target.value))}>{phases.map((item,index)=><option value={index} key={item.title[0]}>{t(...item.title)}</option>)}</select></label>)}</div>
                <table className="explore-compare-table"><caption>{t('Actions in each phase','各阶段的事件数量')}</caption><thead><tr><th scope="col">{t('Action','事件')}</th><th scope="col">{t(...phases[left].title)}</th><th scope="col">{t(...phases[right].title)}</th></tr></thead><tbody>{[['Passes','传球'],['Carries','带球'],['Shots','射门'],['Saves','扑救']].map(([en,cn],i)=><tr key={en}><th scope="row">{t(en,cn)}</th><td>{actionCounts(phaseRecords(phases[left],events))[i]}</td><td>{actionCounts(phaseRecords(phases[right],events))[i]}</td></tr>)}</tbody></table>
                <div className="explore-compare-watch"><button onClick={()=>choosePhase(left)}>{t('Show first phase','查看第一阶段')}</button><button onClick={()=>choosePhase(right)}>{t('Show second phase','查看第二阶段')}</button></div></> : <p>{t('Phase comparisons are unavailable for these actions.','这些事件暂无阶段比较。')}</p>}
            </>}
            {view!=='compare' && (view==='build' || player) && <section className="explore-evidence"><h3>{t('Supporting plays','相关回放')}</h3><ol>{records.map(event=><li key={event.event_id}><button aria-current={events.indexOf(event)===head.index?'step':undefined} onClick={()=>seekEvent(events.indexOf(event))}><time>{replayClock(event)}</time><span>{actionText(event,zh)}</span><span aria-hidden="true">↗</span></button></li>)}</ol></section>}
          </aside>
        </div>
  </div>
}
