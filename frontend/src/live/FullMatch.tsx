import {useEffect,useMemo,useRef,useState} from 'react'
import type {CSSProperties} from 'react'
import type {Event} from '../types'
import {AppHeader} from '../shell/AppHeader'
import {MatchPitch} from '../matchday/MatchPitch'
import {LiveCompanion} from '../companion/LiveCompanion'
import {ClubCrest} from '../matchday/ClubCrest'
import {clubs} from '../matchday/identity'
import {readPreferences} from '../matchday/preferences'
import {END,HALF,FULL_MATCH,matchFrame} from './playback'
import '../matchday/matchday.css'
import './live.css'

export default function FullMatch(){
  const [events,setEvents]=useState<Event[]>([]),[error,setError]=useState(false)
  const [at,setAt]=useState(0),[playing,setPlaying]=useState(false),[speed,setSpeed]=useState(1),[epoch,setEpoch]=useState(0)
  const [language,setLanguage]=useState(readPreferences().language)
  const zh=language==='zh-Hans',t=(en:string,cn:string)=>zh?cn:en
  const timeRef=useRef(0)
  useEffect(()=>{
    const controller=new AbortController()
    fetch(`/api/live/matches/${FULL_MATCH}`,{signal:controller.signal}).then(r=>{if(!r.ok)throw Error();return r.json()}).then(data=>setEvents(data.events)).catch(e=>{if(e.name!=='AbortError')setError(true)})
    return()=>controller.abort()
  },[])
  useEffect(()=>{
    if(!playing)return
    let previous=performance.now()
    const timer=window.setInterval(()=>{
      const now=performance.now(),old=timeRef.current
      const next=Math.min(END,old+Math.min(250,now-previous)*speed);previous=now
      if(old<HALF && next>=HALF){timeRef.current=HALF;setAt(HALF);setPlaying(false)}
      else {timeRef.current=next;setAt(next);if(next===END)setPlaying(false)}
    },40)
    const hidden=()=>{if(document.hidden)setPlaying(false)}
    document.addEventListener('visibilitychange',hidden)
    return()=>{clearInterval(timer);document.removeEventListener('visibilitychange',hidden)}
  },[playing,speed])
  const frame=useMemo(()=>matchFrame(events,at),[events,at])
  const seek=(value:number)=>{setPlaying(false);setEpoch(v=>v+1);timeRef.current=value;setAt(value)}
  const play=()=>{if(at===END){seek(0)}setPlaying(v=>!v)}
  const minute=Math.floor(at/60000),second=Math.floor(at/1000)%60
  const theme=clubs[readPreferences().club_id==='northport'?'northport':'eastbridge']
  const stats=['eastbridge','northport'].map(team=>{
    const own=frame.completed.filter(e=>e.actor.team_id===team)
    return {team,shots:own.filter(e=>e.action.kind==='shot').length,passes:own.filter(e=>e.action.kind==='pass'&&e.action.outcome==='completed').length}
  })
  return <div className="matchday" lang={language} style={{'--fan-accent':theme.accent,'--fan-ink':theme.ink,'--fan-background':theme.background,'--fan-soft':theme.soft} as CSSProperties}>
    <AppHeader active="gi" language={language} fullMatch/>
    <main className="live-match">
      <div className="live-intro"><div><p className="fan-kicker">18 OCT 2026 · {t('FULL MATCH REPLAY','全场回放')}</p><h1>Eastbridge × Northport</h1></div><label>{t('Language','语言')} <select aria-label="Commentary language" value={language} onChange={e=>setLanguage(e.target.value as typeof language)}><option value="en">English</option><option value="zh-Hans">中文</option></select></label></div>
      {error?<p role="alert">{t('The match could not load. Refresh to try again.','比赛加载失败，请刷新重试。')}</p>:!events.length?<p role="status">{t('Opening the match…','加载比赛…')}</p>:<>
      <section className="live-score" aria-label={t('Match scoreboard','比赛记分牌')}><ClubCrest club="eastbridge"/><div><strong>{frame.score.eastbridge} : {frame.score.northport}</strong><time>{minute}:{String(second).padStart(2,'0')}</time><span>{at===END?t('Full time','完场'):at===HALF?t('Half time','中场休息'):at<HALF?t('First half','上半场'):t('Second half','下半场')}</span></div><ClubCrest club="northport"/></section>
      <section className="live-controls" aria-label={t('Full-match playback','全场回放控制')}>
        <button className="fan-primary" onClick={play}>{playing?t('Pause match','暂停比赛'):at===HALF?t('Start second half','开始下半场'):at===END?t('Replay match','重新播放'):t('Play match','播放比赛')}</button>
        <button onClick={()=>seek(Math.max(0,at-30000))}>{t('Back 30s','后退30秒')}</button><button onClick={()=>seek(Math.min(END,at+30000))}>{t('Forward 30s','前进30秒')}</button>
        <label>{t('Speed','速度')} <select aria-label="Match playback speed" value={speed} onChange={e=>setSpeed(Number(e.target.value))}><option value="1">1×</option><option value="1.5">1.5×</option><option value="3">3×</option></select></label>
        <label className="live-seek"><span>{t('Match clock','比赛时间')}</span><input aria-label="Match clock" type="range" min="0" max={END} step="1000" value={at} onChange={e=>seek(Number(e.target.value))}/></label>
      </section>
      <div className="live-stats" aria-label={t('Match numbers so far','截至目前的比赛数据')}>{stats.map(s=><div key={s.team}><strong>{s.team==='eastbridge'?'Eastbridge':'Northport'}</strong><span>{s.shots} {t('shots','射门')} · {s.passes} {t('completed passes','成功传球')}</span></div>)}</div>
      <MatchPitch events={frame.visible} language={language} playback={{index:Math.max(0,frame.index),progress:frame.progress,playing}}/>
      <LiveCompanion cutoff={{period:at<HALF?1:2,elapsed_ms:at<HALF?at:at-HALF}} events={frame.visible} sourceEvents={events} index={frame.index} resolved={frame.resolved} playing={playing} finished={at===END||at===HALF} speechEpoch={epoch} language={language} fullMatch/>
      </>}
      <footer className="live-footer"><a href={`?match=${FULL_MATCH}#gi`}>{t('Explore this match','探索这场比赛')} ↗</a><a href="?story=level-first#matchday">{t('Match highlights','比赛集锦')} ↗</a><p>{t('Original clubs and players. Generated match events; player movement is an illustration of the play.','原创球队与球员。比赛事件为生成数据，球员移动为进攻示意。')}</p></footer>
    </main>
  </div>
}
