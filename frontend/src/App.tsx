import { useEffect, useState } from 'react'
import AnalysisApp from './AnalysisApp'
import { Matchday } from './matchday/Matchday'

/** Explicit deep link keeps the existing analysis workspace available. */
export default function App() {
  const [analysis, setAnalysis] = useState(
    () => window.location.hash === '#analysis',
  )
  useEffect(() => {
    const update = () => setAnalysis(window.location.hash === '#analysis')
    window.addEventListener('hashchange', update)
    return () => window.removeEventListener('hashchange', update)
  }, [])
  return analysis ? (
    <>
      <nav className="workspace-return" aria-label="Workspace">
        <a href="#matchday">← Matchday / 比赛故事</a>
        <span>Analysis & presenter tools · 分析与演示工具</span>
      </nav>
      <AnalysisApp />
    </>
  ) : (
    <Matchday />
  )
}
