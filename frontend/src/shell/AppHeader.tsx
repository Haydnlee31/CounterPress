import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'
import { replayGallery } from '../matchday/replayGallery'
import './shell.css'

export type Workspace='matchday'|'explore'|'gi'|'studio'|'analysis'
export function AppHeader({active,story,language='en',controls}:{active:Workspace;story?:string;language?:string;controls?:ReactNode}) {
  const library=useRef<HTMLDetailsElement>(null),tools=useRef<HTMLDetailsElement>(null)
  useEffect(()=>{const dismiss=(event:PointerEvent)=>{for(const ref of [library,tools])if(ref.current&&!ref.current.contains(event.target as Node))ref.current.open=false};document.addEventListener('pointerdown',dismiss);return()=>document.removeEventListener('pointerdown',dismiss)},[])
  const zh=language==='zh-Hans',t=(en:string,cn:string)=>zh?cn:en
  const candidate=story??new URLSearchParams(window.location.search).get('story')??'last-gasp'
  const id=Object.hasOwn(replayGallery,candidate)?candidate:'last-gasp'
  const selected=replayGallery[id]
  const href=(route:string)=>`?story=${encodeURIComponent(id)}#${route}`
  const close=()=>{if(library.current)library.current.open=false;if(tools.current)tools.current.open=false}
  return <div className="cp-shell" onKeyDown={e=>{if(e.key==='Escape'){const open=library.current?.open?library.current:tools.current?.open?tools.current:null;close();open?.querySelector('summary')?.focus()}}}>
    <header className="cp-header"><a className="cp-brand" href={href('matchday')} aria-label="CounterPress home">CounterPress<span aria-hidden="true">↗</span></a>
      <nav className="cp-navigation" aria-label={t('Workspace','工作区')}>
        {([['matchday','Matchday','比赛故事'],['explore','Explore data','探索数据'],['gi','GI','GI']] as const).map(([key,en,cn])=><a key={key} href={href(key)} aria-current={active===key?'page':undefined} onClick={close}>{t(en,cn)}</a>)}
      </nav>
      <div className="cp-tools"><details ref={tools}><summary aria-current={active==='studio'||active==='analysis'?'page':undefined}>{t('Tools','工具')}</summary><div className="cp-tools-menu"><a href={href('studio')} aria-current={active==='studio'?'page':undefined} onClick={close}>{t('Producer Studio','制作人工作室')} ↗</a><a href={href('analysis')} aria-current={active==='analysis'?'page':undefined} onClick={close}>{t('Advanced analysis','高级分析')} ↗</a></div></details>{controls}</div>
    </header>
    <div className="cp-context"><details className="cp-library" ref={library}><summary>{t('Match library','比赛库')} <span aria-hidden="true">⌄</span></summary><div className="cp-library-menu">
        <p>{t('Highlights','精彩片段')}</p>{Object.entries(replayGallery).map(([key,item])=><a key={key} href={`?story=${key}#${active==='explore'?'explore':'matchday'}`} onClick={close}><span>{zh?item.title[1]:item.title[0]}</span><small>{item.duration} · Eastbridge × Northport</small></a>)}
        <p>{t('Full-match archive','全场比赛档案')}</p><a href={href('gi')} onClick={close}><span>Eastbridge 4 – 2 Northport</span><small>{t('Full time · Match intelligence','完场 · 比赛洞察')}</small></a>
      </div></details><span className="cp-context-divider"/>
      <div className="cp-context-label"><span>{active==='gi'?t('Full match','全场比赛'):active==='studio'?t('Producer workspace','制作人工作区'):active==='analysis'?t('Advanced workspace','高级工作区'):t('Highlight','精彩片段')}</span><strong>{active==='gi'?'Eastbridge × Northport':active==='studio'?t('Review & publish','审核与发布'):active==='analysis'?t('Evidence & revisions','证据与修订'):zh?selected.title[1]:selected.title[0]}</strong></div>
      {active==='matchday'&&<a className="cp-context-action" href={href('explore')}>{t('Explore this highlight','分析这个片段')} ↗</a>}
      {active==='explore'&&<a className="cp-context-action" href={href('matchday')}>{t('Watch this highlight','观看这个片段')} ↗</a>}
      {active==='gi'&&<span className="cp-context-action cp-context-status">{t('FULL TIME','完场')}</span>}
    </div>
  </div>
}
