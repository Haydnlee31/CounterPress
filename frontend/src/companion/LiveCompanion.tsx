import { useEffect, useId, useRef, useState } from 'react'
import type { Event, MatchTime } from '../types'
import { replayClock } from '../matchday/replayGallery'
import { answer, completedEvents, cue, type Question } from './evidence'
import './companion.css'
import { playBroadcast } from './broadcast'
import { CommentarySpeech } from './speech'

export function LiveCompanion({events,index,resolved,playing,finished,language,speechEpoch=0,sourceEvents,fullMatch=false,cutoff}:{events:Event[];index:number;resolved:boolean;playing:boolean;finished:boolean;language:string;speechEpoch?:number;sourceEvents?:Event[];fullMatch?:boolean;cutoff?:MatchTime}) {
  const zh=language==='zh-Hans', t=(en:string,cn:string)=>zh?cn:en
  const [open,setOpen]=useState(false), [listen,setListen]=useState(false), [detailed,setDetailed]=useState(false)
  const [azure,setAzure]=useState(false),[voice,setVoice]=useState<'broadcast'|'device'>('broadcast'),[fallback,setFallback]=useState(false)
  useEffect(()=>{const controller=new AbortController();fetch('/api/voice/config',{signal:controller.signal}).then(r=>r.ok?r.json():null).then(c=>setAzure(c?.azure===true)).catch(()=>{});return()=>controller.abort()},[])
  const [speechError,setSpeechError]=useState(false)
  const [question,setQuestion]=useState<{kind:Question;scope:string}|null>(null)
  const id=useId()
  const records=completedEvents(events,index,resolved,cutoff), event=events[index]
  const currentKnown=resolved && records.some(e=>e.event_id===event?.event_id && e.revision===event?.revision)
  const text=cue(event,currentKnown,zh,detailed)
  const scope=JSON.stringify([events.map(e=>[e.match_id,e.event_id,e.revision]),index,resolved,language])
  const response=question?.scope===scope ? answer(question.kind,records,zh) : null
  const deviceSupported=typeof window!=='undefined' && 'speechSynthesis' in window && 'SpeechSynthesisUtterance' in window
  const supported=deviceSupported||azure
  const broadcast=azure&&voice==='broadcast'
  const speech=useRef<CommentarySpeech|null>(null)
  const previous=useRef({index,resolved})
  const signature=(sourceEvents??events).map(e=>`${e.match_id}:${e.event_id}:${e.revision}`).join('|')
  useEffect(()=>{
    if(!supported)return
    const queue=new CommentarySpeech(window.speechSynthesis??{cancel:()=>{},getVoices:()=>[],speak:()=>{throw Error()}} as unknown as SpeechSynthesis,zh,detailed,()=>{setSpeechError(true);setListen(false)},broadcast?playBroadcast:undefined,()=>setFallback(true))
    setFallback(false)
    speech.current=queue
    return()=>{queue.stop();speech.current=null}
  },[supported,zh,detailed,signature,speechEpoch,broadcast])
  useEffect(()=>{
    const backwards=index<previous.current.index || (index===previous.current.index && previous.current.resolved && !resolved)
    previous.current={index,resolved}
    if(!listen || (!playing && !finished) || backwards)speech.current?.stop()
    if(listen && playing && currentKnown && event)speech.current?.offer(event)
    // Natural completion lets the current sentence and bounded summary finish.
    // Pending animation transitions never cancel a spoken sentence.
  },[listen,playing,finished,index,resolved,currentKnown,signature,zh,detailed,speechEpoch,broadcast])
  useEffect(()=>()=>speech.current?.stop(),[])

  useEffect(()=>{
    const stop=()=>{if(document.hidden){speech.current?.stop();setListen(false)}}
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
    {listen && <p className="companion-status">{playing?(broadcast&&!fallback?t('Broadcast voice · Azure','广播解说 · Azure'):t(fallback?'Using device voice for now':'Following your playback · device voice',fallback?'暂时使用设备语音':'跟随回放 · 设备语音')):t('Sound is on. Press play to listen.','声音已开启，播放后即可收听。')}</p>}
    {(!supported || speechError) && <p role="status">{t('Voice is unavailable on this device. You can follow every action here in text.','此设备暂时无法播放语音，可通过文字了解每次进攻。')}</p>}
    {open && <div id={id} className="companion-body">
      {azure && <label className="companion-detail">{t('Voice','声音')} <select aria-label={t('Commentary voice','解说声音')} value={voice} onChange={e=>setVoice(e.target.value as typeof voice)}><option value="broadcast">{t('Broadcast · Azure','广播 · Azure')}</option><option value="device">{t('Device voice','设备语音')}</option></select></label>}
      <label className="companion-detail"><input type="checkbox" checked={detailed} onChange={e=>setDetailed(e.target.checked)}/>{t('Describe where the action is','描述球场位置')}</label>
      <p className="companion-prompt">{t('Understand this moment','读懂这一刻')}</p>
      <div className="companion-questions">{([
        ['happened','What just happened?','刚才发生了什么？'],
        ['buildup','How did the play develop?','进攻如何展开？'],
        ['numbers','Show me the numbers','查看比赛数据'],
      ] as const).map(([kind,en,cn])=><button key={kind} aria-pressed={question?.scope===scope&&question.kind===kind} onClick={()=>setQuestion({kind,scope})}>{t(en,cn)}</button>)}</div>
      {response && <div className="companion-answer" role="status"><p>{(fullMatch?response.text.replace('In this sequence so far:', 'In this match so far:').replace('本片段截至目前：','本场截至目前：'):response.text)}</p>{response.evidence.length>0 && <details><summary>{t('Actions behind this answer','答案依据')} · {response.evidence.length}</summary><ol>{response.evidence.map(e=><li key={`${e.event_id}:${e.revision}`}><time>{replayClock(e)}</time> {cue(e,true,zh)}</li>)}</ol></details>}</div>}
      <ol className="companion-transcript" aria-label={t('Recent completed actions','最近完成的进攻')}>{records.slice(-3).reverse().map(e=><li key={`${e.event_id}:${e.revision}`}><time>{replayClock(e)}</time><span>{cue(e,true,zh)}</span></li>)}</ol>
    </div>}
  </section>
}
