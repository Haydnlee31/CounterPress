import { useState } from 'react'
import { AppHeader } from '../shell/AppHeader'
import { readPreferences } from '../matchday/preferences'
import './tools.css'

export default function Tools() {
  const query=window.location.search
  const href=(route:string)=>`${query}#${route}`
  const [language]=useState(()=>readPreferences().language)
  const zh=language==='zh-Hans',t=(en:string,cn:string)=>zh?cn:en
  return <div className="tools-workspace">
    <AppHeader active="tools" language={language} />
    <main className="tools-main">
      <header className="tools-intro"><p className="tools-eyebrow">{t('FOOTIE / WORKSPACE','FOOTIE / 工作区')}</p><h1>{t('Tools for the touchline.','触线工具。')}</h1><p>{t('Review the story. Prepare the coverage. Get closer to the evidence.','审核故事。准备报道。深入了解证据。')}</p></header>
      <div className="tools-grid">
        <a className="tool-card tool-producer" href={href('studio')}>
          <div className="tool-card-top"><span className="tools-eyebrow">{t('FOR PRODUCERS & PRESENTERS','制作人与主持人专区')}</span><span className="tool-access">{t('Editor sign-in','编辑登录')}</span></div>
          <div className="tool-art tool-art-producer" aria-hidden="true"><div className="tool-pitch-lines"/><div className="tool-cue"><span>FOOTIE / PRESENTER CUE</span><b>The story behind<br/>the momentum.</b><div className="tool-cue-lines"><i/><i/></div></div><span className="tool-art-label">REVIEW → APPROVE → EXPORT</span></div>
          <div className="tool-copy"><h2>{t('Producer Studio','制作人工作室')} <span aria-hidden="true">↗</span></h2><p>{t('Turn a supported match story into a presenter cue or lower-third graphic. Check the wording, approve it and download your version.','将支持的比赛故事转换为主持人提示或下方字幕图形。核查措辞，批准后下载您的版本。')}</p><span className="tool-cta">{t('Open Producer Studio','打开制作人工作室')} <span aria-hidden="true">→</span></span></div>
        </a>
        <a className="tool-card tool-evidence" href={href('analysis')}>
          <div className="tool-card-top"><span className="tools-eyebrow">{t('FOR ANALYSTS & EDITORS','分析师与编辑专区')}</span><span className="tool-access">{t('Open access','开放访问')}</span></div>
          <div className="tool-art tool-art-evidence" aria-hidden="true"><div className="tool-evidence-track"><i/><i/><i/><i/></div><span className="tool-evidence-note">THE PLAY</span><div className="tool-evidence-sheet"><span>SUPPORTING EVENTS</span><i/><i/><i/><b>Trace every change ↗</b></div></div>
          <div className="tool-copy"><h2>{t('Evidence desk','证据工作台')} <span aria-hidden="true">↗</span></h2><p>{t('Replay insight scenarios, compare periods of play and inspect the events behind a claim. Follow what changes when a correction arrives.','回放洞察场景，对比比赛时段，检查声明背后的事件。跟踪更正到来时发生的变化。')}</p><span className="tool-cta">{t('Open evidence desk','打开证据工作台')} <span aria-hidden="true">→</span></span></div>
        </a>
      </div>
      <section className="tools-route" aria-labelledby="tools-route-title"><div><p className="tools-eyebrow">{t('LOOKING FOR THE GAME?','寻找比赛？')}</p><h2 id="tools-route-title">{t('Stay close to the action.','紧跟比赛动态。')}</h2></div><div><a href={href('gi')}><strong>{t('Match Centre','比赛中心')} <span aria-hidden="true">↗</span></strong><span>{t('Full-match numbers and key moments','全场数据与关键时刻')}</span></a><a href={href('explore')}><strong>{t('Explore data','探索数据')} <span aria-hidden="true">↗</span></strong><span>{t('Players, passes and the selected highlight','球员、传球与精选高光')}</span></a></div></section>
      <footer className="tools-footer"><span>{t('FOOTIE / TOOLS','FOOTIE / 工具')}</span><p>{t('Producer Studio currently covers the curated insight scenarios. Match Centre and Explore data cover the match library and highlights.','制作人工作室目前涵盖精选洞察场景。比赛中心和探索数据涵盖比赛库和精彩片段。')}</p></footer>
    </main>
  </div>
}
