import { useEffect, useId, useRef, useState } from 'react'
import type { Event } from '../types'
import { replayClock } from '../matchday/replayGallery'
import { answer, completedEvents, cue, type Question } from './evidence'
import './companion.css'

export function LiveCompanion({events,index,resolved,playing,finished,language}:{events:Event[];index:number;resolved:boolean;playing:boolean;finished:boolean;language:string}) {
  const zh=language==='zh-Hans', t=(en:string,cn:string)=>zh?cn:en
  const [open,setOpen]=useState(false), [listen,setListen]=useState(false), [detailed,setDetailed]=useState(false)
  const [speechError,setSpeechError]=useState(false)
  const [question,setQuestion]=useState<{kind:Question;scope:string}|null>(null)
  const id=useId()
  const records=completedEvents(events,index,resolved), event=events[index]
  const currentKnown=resolved && records.some(e=>e.event_id===event?.event_id && e.revision===event?.revision)
  const text=cue(event,currentKnown,zh,detailed)
  const scope=JSON.stringify([events.map(e=>[e.match_id,e.event_id,e.revision]),index,resolved,language])
  const response=question?.scope===scope ? answer(question.kind,records,zh) : null
  const supported=typeof window!=='undefined' && 'speechSynthesis' in window && 'SpeechSynthesisUtterance' in window
  const spoken=useRef('')
  const speechKey=`${scope}:${detailed}`

  // One current cue, never a backlog. Seeking, language changes and corrections invalidate it.
  useEffect(()=>{
    if (!supported) return
    const synth=window.speechSynthesis
    if (!listen) {synth.cancel();spoken.current='';return}
    if (!playing) {
      if(!finished || spoken.current!==speechKey){synth.cancel();spoken.current=''}
      return
    }
    if(spoken.current===speechKey) return
    spoken.current=speechKey
    synth.cancel()
    // Short mode speaks completed actions; descriptive mode also describes the setup.
    if(!currentKnown && !detailed) return
    const utterance=new SpeechSynthesisUtterance(text)
    utterance.lang=zh?'zh-CN':'en-GB'
    const voices=synth.getVoices()
    const voice=voices.find(v=>v.lang.toLowerCase().startsWith(zh?'zh':'en'))
    if(voice)utterance.voice=voice
    utterance.onerror=e=>{if(e.error!=='interrupted' && e.error!=='canceled'){setSpeechError(true);setListen(false)}}
    synth.speak(utterance)
  },[listen,playing,finished,speechKey,currentKnown,detailed,text,zh,supported])
  useEffect(()=>()=>{if(supported)window.speechSynthesis.cancel()},[supported])
  useEffect(()=>{
    const stop=()=>{if(document.hidden){window.speechSynthesis?.cancel();setListen(false)}}
    document.addEventListener('visibilitychange',stop)
    return()=>document.removeEventListener('visibilitychange',stop)
  },[])

  return <section className="live-companion" aria-label={t('Live Companion','随场解说')}>
    <div className="companion-heading">
      <div><span className="companion-eyebrow">{t('WITH THE PLAY','紧随比赛')}</span><h3>{t('Live Companion','随场解说')}</h3></div>
      <div className="companion-actions">
        <button type="button" aria-pressed={listen} disabled={!supported} onClick={()=>{setSpeechError(false);setListen(v=>!v)}}>{listen?t('Sound off','关闭声音'):t('Listen','收听')} <span aria-hidden="true">{listen?'◼':'♪'}</span></button>
        <button type="button" aria-expanded={open} aria-controls={id} onClick={()=>setOpen(v=>!v)}>{open?t('Close','收起'):t('Follow the play','了解比赛')} <span aria-hidden="true">{open?'−':'+'}</span></button>
      </div>
    </div>
    <p className="companion-current" role="status" aria-live={listen?'off':'polite'} aria-atomic="true">{text}</p>
    {listen && <p className="companion-status">{playing?t('Following your playback · device voice','跟随回放 · 设备语音'):t('Sound is on. Press play to listen.','声音已开启，播放后即可收听。')}</p>}
    {(!supported || speechError) && <p role="status">{t('Voice is unavailable on this device. You can follow every action here in text.','此设备暂时无法播放语音，可通过文字了解每次进攻。')}</p>}
    {open && <div id={id} className="companion-body">
      <label className="companion-detail"><input type="checkbox" checked={detailed} onChange={e=>setDetailed(e.target.checked)}/>{t('Describe where the action is','描述球场位置')}</label>
      <p className="companion-prompt">{t('Understand this moment','读懂这一刻')}</p>
      <div className="companion-questions">{([
        ['happened','What just happened?','刚才发生了什么？'],
        ['buildup','How did the play develop?','进攻如何展开？'],
        ['numbers','Show me the numbers','查看比赛数据'],
      ] as const).map(([kind,en,cn])=><button key={kind} aria-pressed={question?.scope===scope&&question.kind===kind} onClick={()=>setQuestion({kind,scope})}>{t(en,cn)}</button>)}</div>
      {response && <div className="companion-answer" role="status"><p>{response.text}</p>{response.evidence.length>0 && <details><summary>{t('Actions behind this answer','答案依据')} · {response.evidence.length}</summary><ol>{response.evidence.map(e=><li key={`${e.event_id}:${e.revision}`}><time>{replayClock(e)}</time> {cue(e,true,zh)}</li>)}</ol></details>}</div>}
      <ol className="companion-transcript" aria-label={t('Recent completed actions','最近完成的进攻')}>{records.slice(-3).reverse().map(e=><li key={`${e.event_id}:${e.revision}`}><time>{replayClock(e)}</time><span>{cue(e,true,zh)}</span></li>)}</ol>
    </div>}
  </section>
}
