import { AppHeader } from '../shell/AppHeader'
import './tools.css'

export default function Tools() {
  const query=window.location.search
  const href=(route:string)=>`${query}#${route}`
  return <div className="tools-workspace">
    <AppHeader active="tools" />
    <main className="tools-main">
      <header className="tools-intro"><p className="tools-eyebrow">COUNTERPRESS / WORKSPACE</p><h1>Tools for the touchline.</h1><p>Review the story. Prepare the coverage. Get closer to the evidence.</p></header>
      <div className="tools-grid">
        <a className="tool-card tool-producer" href={href('studio')}>
          <div className="tool-card-top"><span className="tools-eyebrow">FOR PRODUCERS & PRESENTERS</span><span className="tool-access">Editor sign-in</span></div>
          <div className="tool-art tool-art-producer" aria-hidden="true"><div className="tool-pitch-lines"/><div className="tool-cue"><span>COUNTERPRESS / PRESENTER CUE</span><b>The story behind<br/>the momentum.</b><div className="tool-cue-lines"><i/><i/></div></div><span className="tool-art-label">REVIEW → APPROVE → EXPORT</span></div>
          <div className="tool-copy"><h2>Producer Studio <span aria-hidden="true">↗</span></h2><p>Turn a supported match story into a presenter cue or lower-third graphic. Check the wording, approve it and download your version.</p><span className="tool-cta">Open Producer Studio <span aria-hidden="true">→</span></span></div>
        </a>
        <a className="tool-card tool-evidence" href={href('analysis')}>
          <div className="tool-card-top"><span className="tools-eyebrow">FOR ANALYSTS & EDITORS</span><span className="tool-access">Open access</span></div>
          <div className="tool-art tool-art-evidence" aria-hidden="true"><div className="tool-evidence-track"><i/><i/><i/><i/></div><span className="tool-evidence-note">THE PLAY</span><div className="tool-evidence-sheet"><span>SUPPORTING EVENTS</span><i/><i/><i/><b>Trace every change ↗</b></div></div>
          <div className="tool-copy"><h2>Evidence desk <span aria-hidden="true">↗</span></h2><p>Replay insight scenarios, compare periods of play and inspect the events behind a claim. Follow what changes when a correction arrives.</p><span className="tool-cta">Open evidence desk <span aria-hidden="true">→</span></span></div>
        </a>
      </div>
      <section className="tools-route" aria-labelledby="tools-route-title"><div><p className="tools-eyebrow">LOOKING FOR THE GAME?</p><h2 id="tools-route-title">Stay close to the action.</h2></div><div><a href={href('gi')}><strong>Match Centre <span aria-hidden="true">↗</span></strong><span>Full-match numbers and key moments</span></a><a href={href('explore')}><strong>Explore data <span aria-hidden="true">↗</span></strong><span>Players, passes and the selected highlight</span></a></div></section>
      <footer className="tools-footer"><span>COUNTERPRESS / TOOLS</span><p>Producer Studio currently covers the curated insight scenarios. Match Centre and Explore data cover the match library and highlights.</p></footer>
    </main>
  </div>
}
