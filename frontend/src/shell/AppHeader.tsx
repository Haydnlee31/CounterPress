import { currentMatchId, matchLibrary, matchDate } from '../gi/catalog'
import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'
import { replayGallery, highlightTag } from '../matchday/replayGallery'
import './shell.css'

export type Workspace='matchday'|'explore'|'gi'|'studio'|'analysis'|'tools'
export function AppHeader({active,story,language='en',controls,fullMatch=false}:{active:Workspace;story?:string;language?:string;controls?:ReactNode;fullMatch?:boolean}) {
  const library=useRef<HTMLDetailsElement>(null),tools=useRef<HTMLDetailsElement>(null)
  useEffect(()=>{const dismiss=(event:PointerEvent)=>{for(const ref of [library,tools])if(ref.current&&!ref.current.contains(event.target as Node))ref.current.open=false};document.addEventListener('pointerdown',dismiss);return()=>document.removeEventListener('pointerdown',dismiss)},[])
  const zh=language==='zh-Hans',t=(en:string,cn:string)=>zh?cn:en
  const candidate=story??new URLSearchParams(window.location.search).get('story')??'last-gasp'
  const id=Object.hasOwn(replayGallery,candidate)?candidate:'last-gasp'
  const selected=replayGallery[id]
  const matchId=fullMatch?'synthetic-32fe41c5d304ce68d7d9':active==='matchday'||active==='explore'?selected.matchId??currentMatchId():currentMatchId()
  const href=(route:string)=>`?story=${encodeURIComponent(id)}${matchId!==matchLibrary[0].id?`&match=${matchId}`:''}#${route}`
  const close=()=>{if(library.current)library.current.open=false;if(tools.current)tools.current.open=false}
  return <div className="cp-shell" onKeyDown={e=>{if(e.key==='Escape'){const open=library.current?.open?library.current:tools.current?.open?tools.current:null;close();open?.querySelector('summary')?.focus()}}}>
    <header className="cp-header"><a className="cp-brand" href={href('matchday')} aria-label="CounterPress home">CounterPress<span aria-hidden="true">↗</span></a>
      <nav className="cp-navigation" aria-label={t('Workspace','工作区')}>
        {([['matchday','Matchday','比赛故事'],['explore','Explore data','探索数据'],['gi','Match Centre','比赛中心']] as const).map(([key,en,cn])=><a key={key} href={href(key)} aria-current={active===key?'page':undefined} onClick={close}>{t(en,cn)}</a>)}
      </nav>
      <div className="cp-tools"><details ref={tools}><summary aria-current={active==='tools'||active==='studio'||active==='analysis'?'page':undefined}>{t('Tools','工具')}</summary><div className="cp-tools-menu"><a href={href('tools')} aria-current={active==='tools'?'page':undefined} onClick={close}>{t('All tools','所有工具')} ↗</a><a href={href('studio')} aria-current={active==='studio'?'page':undefined} onClick={close}>{t('Producer Studio','制作人工作室')} ↗</a><a href={href('analysis')} aria-current={active==='analysis'?'page':undefined} onClick={close}>{t('Evidence desk','证据工作台')} ↗</a></div></details>{controls}</div>
    </header>
    <div className="cp-context"><details className="cp-library" ref={library}><summary>{t('Match library','比赛库')} <span aria-hidden="true">⌄</span></summary><div className="cp-library-menu">
        <p>{t('Highlights','精彩片段')}</p>{Object.entries(replayGallery).map(([key,item])=><a key={key} href={`?story=${key}${item.matchId?`&match=${item.matchId}`:''}#${active==='explore'?'explore':'matchday'}`} onClick={close}><span>{zh?item.title[1]:item.title[0]}</span><small>{highlightTag(item)} · {item.duration}</small></a>)}
        <a href="?match=synthetic-32fe41c5d304ce68d7d9#live" onClick={close}><span>{t('Watch the full match','观看全场比赛')}</span><small>Eastbridge × Northport · 18 Oct 2026</small></a>
        <p>{t('Full-match archive','全场比赛档案')}</p>{matchLibrary.map(match=><a key={match.id} href={`?story=${id}&match=${match.id}#gi`} aria-current={active==='gi'&&matchId===match.id?'page':undefined} onClick={close}><span>Eastbridge {match.score} Northport</span><small>{matchDate(match.date)} · {match.title}</small></a>)}
      </div></details><span className="cp-context-divider"/>
      <div className="cp-context-label"><span>{fullMatch?t('Full-match replay','全场回放'):active==='gi'?t('Full match','全场比赛'):active==='studio'?t('Producer workspace','制作人工作区'):active==='tools'?t('Tools','工具'):active==='analysis'?t('Evidence desk','证据工作台'):t('Highlight','精彩片段')}</span><strong>{fullMatch?'Eastbridge × Northport':active==='gi'?'Eastbridge × Northport':active==='studio'?t('Review & publish','审核与发布'):active==='tools'?t('Production & analysis','制作与分析'):active==='analysis'?t('Evidence & revisions','证据与修订'):zh?selected.title[1]:selected.title[0]}</strong></div>
      {active==='matchday'&&!fullMatch&&<a className="cp-context-action" href={href('explore')}>{t('Explore this highlight','分析这个片段')} ↗</a>}
      {active==='explore'&&<a className="cp-context-action" href={href('matchday')}>{t('Watch this highlight','观看这个片段')} ↗</a>}
      {active==='gi'&&<span className="cp-context-action cp-context-status">{t('FULL TIME','完场')}</span>}
    </div>
  </div>
}
