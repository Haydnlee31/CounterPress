import {FootieLoader} from '../shell/FootieLoader'
import {useState,useSyncExternalStore} from 'react'
import {AppHeader} from '../shell/AppHeader'
import {readPreferences} from '../matchday/preferences'
import {PlaySequence} from '../gi/PlaySequence'
import {alias} from '../gi/data'
import type {GIMatch} from '../gi/data'
import {matchDate} from '../gi/catalog'
import {getData,useResource} from '../football/data'
import {replayGallery} from '../matchday/replayGallery'
import {FootieMascot} from '../assistant/FootieMascot'
import {highlightLink,removeHighlight,sourceKey,updateHighlight,useCollection} from './collection'
import type {SavedHighlight} from './collection'
import {generateSummary,subscribeSummaries,summaryState,summaryVersion} from './summary'
import '../matchday/matchday.css'
import '../gi/gi.css'
import './highlights.css'

function SavedReplay({item,zh}:{item:SavedHighlight;zh:boolean}){
  const t=(en:string,cn:string)=>zh?cn:en
  const result=useResource(`saved-highlight:${item.matchId}`,signal=>getData<GIMatch>(`/api/gi/matches/${encodeURIComponent(item.matchId)}`,signal),item.matchId)
  useSyncExternalStore(subscribeSummaries,summaryVersion)
  const [error,setError]=useState(''),[note,setNote]=useState(item.note)
  const match=result.data,event=match?.events.find(e=>e.event_id===item.eventId)
  const stale=!!match&&!!event&&(event.revision!==item.revision||sourceKey(match,event)!==item.source)
  const state=summaryState(item.id)
  function change(update:(value:SavedHighlight)=>SavedHighlight){try{updateHighlight(item.id,update);setError('')}catch(e){setError((e as Error).message)}}
  return <article className="hl-selected" aria-label="Saved highlight">
    <header className="hl-selected-heading"><div><p className="fan-kicker">{item.clock} · {item.player}</p><h2>{item.title}</h2><p>Eastbridge × Northport · {matchDate(item.date)}</p></div><a href={`?match=${encodeURIComponent(item.matchId)}&moment=${encodeURIComponent(item.eventId)}#gi`}>{t('Back to this match ↗','返回此比赛 ↗')}</a></header>
    {result.error?<div role="alert"><p>{t('The replay couldn\'t load. Your notes are still saved.','回放无法加载。您的笔记仍已保存。')}</p><button onClick={result.retry}>{t('Try again','重试')}</button></div>:!match?<FootieLoader label={t('Opening your highlight…','正在打开您的精彩片段…')}/>:!event?<p role="alert">{t('This moment is no longer in the match records. Your notes are still saved.','此时刻已不在比赛记录中。您的笔记仍已保存。')}</p>:stale?<div className="hl-update" role="status"><h3>{t('This play has been updated','此动作已更新')}</h3><p>{t('Review the latest version in Match Centre. Updating this highlight will clear its old pitch markings and summary; your written note stays.','在比赛中心查看最新版本。更新此精彩片段将清除其旧的球场标注和总结；您的文字笔记将保留。')}</p><button onClick={()=>{const updated={...item,revision:event.revision,source:sourceKey(match,event),strokes:[],summary:undefined};try{updateHighlight(item.id,()=>updated);void generateSummary(updated);setError('')}catch(e){setError((e as Error).message)}}}>{t('Use updated play','使用更新后的动作')}</button></div>:<section className="gi-detail hl-pitch" aria-label={t('Highlight replay','精彩片段回放')}><PlaySequence key={item.source} matchId={match.match_id} events={match.events} event={event} names={new Map(match.players.map(p=>[p.player_id,alias(p)]))} players={match.players} hideObservation annotations={{strokes:item.strokes,change:strokes=>change(value=>({...value,strokes}))}}/></section>}
    <section className="hl-summary" aria-label={t('Moment summary','时刻总结')}><div className="hl-summary-heading"><FootieMascot size={46}/><div><p className="fan-kicker">{t("FOOTIE'S TAKE",'FOOTIE 的点评')}</p><h3>{t("Footie's Summary",'Footie 的总结')}</h3></div></div>
      {stale||!event?<p>{t('Analysis will be available after the current play is loaded and verified.','当前动作加载并验证后，分析将可用。')}</p>:state.busy?<p role="status">{t('Footie is reviewing the recorded play… You can keep watching and add your notes.','Footie 正在分析记录的动作……您可以继续观看并添加笔记。')}</p>:item.summary&&item.summary.source===item.source?<>{item.summary.text.map((text,i)=><p key={i}>{text}</p>)}<button onClick={()=>void generateSummary(item)}>{t('Refresh summary','刷新总结')}</button>{!item.summary.ai&&<p className="hl-summary-status">{t('Statistics summary · AI analysis is currently unavailable.','统计总结 · AI 分析目前不可用。')} <button onClick={()=>void generateSummary(item)}>{t('Try AI analysis','尝试 AI 分析')}</button></p>}</>:<><p>{state.error||t('Your replay is saved. Generate Footie\'s take on the play.','您的回放已保存。生成 Footie 对此动作的点评。')}</p><button onClick={()=>void generateSummary(item)}>{t('Generate AI summary','生成 AI 总结')}</button></>}
      {state.error&&item.summary&&!state.busy&&<p role="alert">{state.error}</p>}
    </section>
    <section className="hl-notes"><label htmlFor="highlight-note">{t('Your coaching notes','您的执教笔记')}</label><p>{t('What would you repeat, or change next time?','下次你会重复什么，或者做出什么改变？')}</p><textarea id="highlight-note" value={note} maxLength={2000} rows={3} placeholder={t('A run to watch, a passing option, a different position…','值得关注的跑动、传球选择、不同的站位……')} onChange={e=>setNote(e.target.value)}/><div><small>{note.length}/2000</small><button disabled={note===item.note} onClick={()=>change(value=>({...value,note}))}>{note===item.note?t('Notes saved','笔记已保存'):t('Save notes','保存笔记')}</button></div></section>
    {error&&<p role="alert">{error}</p>}
  </article>
}

export default function Highlights({selectedId}:{selectedId?:string}){
  const {items,error}=useCollection(),[failure,setFailure]=useState(''),[remove,setRemove]=useState<string|null>(null)
  const [language]=useState(()=>readPreferences().language)
  const zh=language==='zh-Hans', t=(en:string,cn:string)=>zh?cn:en
  const selected=selectedId?items.find(h=>h.id===selectedId):items[0]
  return <div className="matchday hl-page"><AppHeader active="matchday" language={language}/><main id="highlights-content">
    <header className="hl-heading"><div><p className="fan-kicker">{t('YOUR COLLECTION','您的收藏')}</p><h1>{t('Highlights','精彩片段')}<span>.</span></h1><p>{t('Keep the play. Make it yours.','保存动作，属于你的回忆。')}</p></div><a className="hl-primary" href="#gi">{t('Find a moment ＋','找一个时刻 ＋')}</a></header>
    {error&&<p role="alert">{error}</p>}
    {selectedId&&!selected&&<p role="status">{t("This highlight isn't saved in this browser.",'此精彩片段未在此浏览器中保存。')} <a href="#highlights">{t('Open your collection','打开您的收藏')}</a></p>}
    {selected?<SavedReplay key={selected.id} item={selected} zh={zh}/>:!error&&<section className="hl-empty"><span aria-hidden="true">↗</span><h2>{t('Your favourite plays, all here.','您最喜爱的动作，全在这里。')}</h2><p>{t('Open Moments in Match Centre and save a play. Watch it again, read Footie\'s analysis, and draw your ideas straight onto the pitch.','在比赛中心打开时刻并保存一个动作。再次观看，阅读 Footie 的分析，并在球场上直接绘制您的想法。')}</p><a href="#gi">{t('Explore Match Centre →','探索比赛中心 →')}</a></section>}
    {!!items.length&&<section className="hl-collection" aria-label={t('Your saved highlights','您保存的精彩片段')}><div className="hl-section-heading"><h2>{t('Your highlights','您的精彩片段')}</h2><span>{items.length} {t('saved','已保存')}</span></div><div className="hl-grid">{items.map(h=><article className="hl-card" key={h.id} data-selected={selected?.id===h.id}><a href={highlightLink(h.id)} aria-current={selected?.id===h.id?'true':undefined}><span className="fan-kicker">{matchDate(h.date)} · {h.clock}</span><h3>{h.title}</h3><p>{h.player}</p><small>Eastbridge × Northport {h.strokes.length>0?t('· Annotated','· 已标注'):''}</small><span className="hl-card-arrow" aria-hidden="true">↗</span></a>{remove===h.id?<div className="hl-remove"><span>{t('Remove replay and notes?','删除回放和笔记？')}</span><button onClick={()=>{try{removeHighlight(h.id);setRemove(null);setFailure('');if(selected?.id===h.id)window.location.hash='highlights'}catch(e){setFailure((e as Error).message)}}}>{t('Remove','删除')}</button><button onClick={()=>setRemove(null)}>{t('Keep','保留')}</button></div>:<button className="hl-remove-link" aria-label={`Remove ${h.title} by ${h.player}`} onClick={()=>setRemove(h.id)}>Remove</button>}</article>)}</div></section>}
    {failure&&<p role="alert">{failure}</p>}
    <details className="hl-preloaded"><summary>{t('Preloaded highlights','预载精彩片段')}</summary><div className="hl-grid">{Object.entries(replayGallery).map(([id,h])=><a className="hl-card" key={id} href={`?story=${encodeURIComponent(id)}#highlights/preloaded`}><span className="fan-kicker">{h.duration}</span><h3>{h.title[0]}</h3><span>{t('Watch highlight ↗','观看精彩片段 ↗')}</span></a>)}</div></details>
    <footer className="hl-storage-note">{t('Your collection, drawings and notes are saved in this browser. AI summaries use the recorded match events.','您的收藏、绘图和笔记已保存在此浏览器中。AI 总结使用记录的比赛事件。')}</footer>
  </main></div>
}
