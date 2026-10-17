import { useEffect, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import { clock, windowLabel } from '../types'
import { clubs, clubName, displayText, playerName, knownPlayer } from './identity'
import { useMatchday, SEGMENT_START, COMPARISON_TIME } from './useMatchday'
import { storiesFor } from './stories'
import { Moments } from './Moments'
import { ClubCrest } from './ClubCrest'
import { MatchPitch } from './MatchPitch'
import { scoreAtPlayhead } from './pitchScene'
import { replayGallery } from './replayGallery'
import './matchday.css'

const showcases: Record<string, [string, string]> = {
  ...Object.fromEntries(Object.entries(replayGallery).map(([id,story])=>[id,story.title])),
  increase: ['Winning it back', '前场夺回球权'],
  'pressure-increase': ['Playing under pressure', '在压力下控球'],
  'progression-increase': ['Moving the ball forward', '向前推进'],
  'contribution-increase': ['Player spotlight', '球员聚焦'],
  'stream-recovery': ['When the story changes', '当故事发生变化'],
}
export function Matchday() {
  const m = useMatchday(),
    p = m.request.preferences,
    snapshot = m.snapshot
  const t = (en: string, zh: string) => (p.language === 'zh-Hans' ? zh : en)
  const replayStory=replayGallery[m.request.scenario]
  const isReplayStory=!!replayStory
  const [pitchHead,setPitchHead]=useState({index:0,resolved:false})
  const pitchEvents=snapshot?.pitch_events ?? []
  const shownScore=isReplayStory&&snapshot?scoreAtPlayhead(snapshot.state.score,pitchEvents,pitchHead.index,pitchHead.resolved):snapshot?.state.score
  const shownTime=isReplayStory?(pitchEvents[pitchHead.index]?.occurred_at.elapsed_ms ?? 760000):m.request.atMs
  const [preferencesOpen, setPreferencesOpen] = useState(false)
  const [recapOpen, setRecapOpen] = useState(false)
  const [replayOpen, setReplayOpen] = useState(false)
  const [peopleOpen, setPeopleOpen] = useState(false)
  const [momentKey, setMomentKey] = useState<string | null>(null)
  useEffect(() => {
    if (recapOpen) document.getElementById('fan-recap-title')?.focus()
  }, [recapOpen])
  const actionButton = useRef<HTMLButtonElement>(null)
  const stories = snapshot ? storiesFor(snapshot, p) : []
  const first = stories[0],
    selectedStory = stories.find((s) => s.key === momentKey)
  const teams =
    snapshot?.teams ??
    Object.entries(clubs).map(([team_id, club]) => ({
      team_id,
      name: club.name,
      player_ids: [] as string[],
    }))
  const actors = [
    ...new Set(first?.records.map((e) => e.actor.player_id) ?? []),
  ]
  const correction =
    snapshot?.lifecycle?.operation === 'withdraw' ||
    snapshot?.pressure_lifecycle?.some((v) => v.operation === 'withdraw') ||
    snapshot?.contribution_lifecycle?.some((v) => v.operation === 'withdraw')
  const changed = stories.some((s) => s.citation.revision > 1)
  function chooseShowcase(value: string) {
    setMomentKey(null)
    m.scenario(value)
  }
  function showMoments(key: string) {
    setMomentKey(key)
  }
  const theme = clubs[(p.club_id ?? 'eastbridge') as keyof typeof clubs]
  return (
    <div
      className="matchday"
      lang={p.language}
      style={{ '--fan-accent': theme.accent, '--fan-ink': theme.ink, '--fan-background': theme.background, '--fan-soft': theme.soft } as CSSProperties}
    >
      <a className="fan-skip" href="#matchday-content">
        {t('Skip to match story', '跳至比赛故事')}
      </a>
      <header className="fan-header">
        <a className="fan-brand" href="#matchday">
          CounterPress<span aria-hidden="true">↗</span>
        </a>
        <nav aria-label={t('Workspace', '工作区')}>
          <span aria-current="page">{t('Matchday', '比赛故事')}</span>
          <a href="#analysis">{t('Explore data', '探索数据')}</a>
        </nav>
        <label className="fan-language">
          <span className="sr-only">{t('Language', '语言')}</span>
          <select
            aria-label="Language"
            value={p.language}
            onChange={(e) =>
              m.preferences({
                ...p,
                language: e.target.value as typeof p.language,
              })
            }
          >
            <option value="en">English</option>
            <option value="zh-Hans">简体中文</option>
          </select>
        </label>
      </header>
      <main id="matchday-content">
        <div className="fan-intro">
          <div>
            <p className="fan-kicker">
              {t('EASTBRIDGE × NORTHPORT', 'EASTBRIDGE × NORTHPORT')}
            </p>
            <h1>{t('Match centre', '比赛中心')}</h1>
          </div>
          <button
            className="fan-follow"
            aria-expanded={preferencesOpen}
            aria-controls="fan-preferences"
            onClick={() => setPreferencesOpen((v) => !v)}
          >
            <span>
              {p.club_id
                ? t('FOLLOWING', '正在关注')
                : t('YOUR VIEW', '你的视角')}
            </span>
            <strong>
              {p.club_id
                ? clubName(p.club_id)
                : t('Neutral · choose a side', '中立 · 选择球队')}{' '}
              <span aria-hidden="true">⌄</span>
            </strong>
          </button>
        </div>
        {preferencesOpen && (
          <section
            id="fan-preferences"
            className="fan-preferences"
            aria-label={t('My preferences', '我的偏好')}
          >
            <div className="fan-section-heading">
              <h2>{t('Make it your matchday', '你的比赛视角')}</h2>
              <button
                className="fan-secondary"
                onClick={() => setPreferencesOpen(false)}
              >
                {t('Done', '完成')}
              </button>
            </div>
            <p>
              {t(
                'Choose your team and the players you want to keep up with.',
                '选择你关注的球队和球员。',
              )}
            </p>
            <div className="fan-preference-grid">
              <label>
                {t('Follow a team', '关注球队')}
                <select
                  aria-label="Follow a team"
                  value={p.club_id ?? ''}
                  onChange={(e) =>
                    m.preferences({ ...p, club_id: e.target.value || null })
                  }
                >
                  <option value="">
                    {t('Neutral — show both sides', '中立 — 关注双方')}
                  </option>
                  {teams.map((team) => (
                    <option key={team.team_id} value={team.team_id}>
                      {team.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                {t('Follow a player', '关注球员')}
                <select
                  aria-label="Follow a player"
                  value={p.player_id ?? ''}
                  onChange={(e) =>
                    m.preferences({ ...p, player_id: e.target.value || null })
                  }
                >
                  <option value="">{t('Everyone', '所有球员')}</option>
                  {teams.flatMap((team) =>
                    team.player_ids.filter(knownPlayer).map((id) => (
                      <option key={id} value={id}>
                        {playerName(id)} · {team.name}
                      </option>
                    )),
                  )}
                </select>
              </label>
              <label>
                {t('Explanation', '解释方式')}
                <select
                  aria-label="Explanation"
                  value={p.depth}
                  onChange={(e) =>
                    m.preferences({
                      ...p,
                      depth: e.target.value as typeof p.depth,
                    })
                  }
                >
                  <option value="casual">
                    {t('Keep it simple', '简明易懂')}
                  </option>
                  <option value="analyst">
                    {t('Give me more detail', '更多细节')}
                  </option>
                </select>
              </label>
            </div>
            <div className="fan-storage">
              <p role="status">
                {m.saved === false
                  ? t(
                      'Device storage is unavailable. Preferences last for this visit only.',
                      '设备存储不可用，偏好仅在本次访问期间保留。',
                    )
                  : m.saved === true
                    ? t(
                        'Saved on this device. No account needed.',
                        '已保存在此设备，无需账户。',
                      )
                    : t(
                        'Your choices can be saved on this device. No account needed.',
                        '你的选择可保存在此设备，无需账户。',
                      )}
              </p>
              <button onClick={m.resetPreferences}>
                {t('Clear preferences', '清除偏好')}
              </button>
            </div>
          </section>
        )}
        <section
          className="fan-score"
          aria-label={t('Match scoreboard', '比赛记分牌')}
        >
          <div className="fan-team">
            <ClubCrest club="eastbridge" />
            <strong>{clubName('eastbridge')}</strong>
          </div>
          <div className="fan-score-center">
            <span>
              {shownScore?.eastbridge ?? '–'} <i>:</i>{' '}
              {shownScore?.northport ?? '–'}
            </span>
            <time>
              {clock(shownTime)} · {t('2nd half', '下半场')}
            </time>
          </div>
          <div className="fan-team away">
            <strong>{clubName('northport')}</strong>
            <ClubCrest club="northport" />
          </div>
          <div className="fan-score-foot">
            <span>
              {isReplayStory?<>{t(...replayStory.title)} · {t('Replay','回放')}</>:<>{t('Match highlights', '比赛集锦')} · 48:00–{clock(m.end)}</>}
              {snapshot && !isReplayStory && (
                <>
                  <br />
                  {t('Updated to', '更新至')}{' '}
                  {clock(snapshot.state.at.elapsed_ms)}
                </>
              )}
            </span>
            {!isReplayStory && <button
              onClick={() => setReplayOpen((v) => !v)}
              aria-expanded={replayOpen}
              aria-controls="fan-replay"
            >
              {t('Explore replay', '探索回放')} ↗
            </button>}
          </div>
        </section>
        <section className="fan-replay-gallery" aria-label={t('Choose a replay','选择回放')}>
          <div className="fan-gallery-heading"><h2>{t('Pick a moment','选择精彩片段')}</h2><span>{t('Three plays to explore','三个精彩片段')}</span></div>
          <div className="fan-replay-cards">{Object.entries(replayGallery).map(([id,story],i)=><button key={id} className={`fan-replay-card ${id===m.request.scenario?'is-active':''}`} aria-pressed={id===m.request.scenario} onClick={()=>chooseShowcase(id)}>
            <span className="fan-card-meta"><span>0{i+1}</span><span>{story.duration} <span aria-hidden="true">▶</span></span></span>
            <strong>{t(...story.title)}</strong><span>{t(...story.hook)}</span>
          </button>)}</div>
        </section>
        {replayStory && <div className="fan-replay-context"><p>{t(...replayStory.context)}</p><a href={replayStory.source} target="_blank" rel="noreferrer">{t('Original clip','原始片段')} · {replayStory.sourceLabel} ↗</a></div>}
        {snapshot && <MatchPitch key={m.request.scenario} events={snapshot.pitch_events ?? snapshot.audience?.sequence ?? []} language={p.language} fromStart={isReplayStory} onPlayhead={isReplayStory?setPitchHead:undefined} />}
        {replayOpen && !isReplayStory && (
          <section
            id="fan-replay"
            className="fan-replay"
            aria-label={t('Explore replay', '探索回放')}
          >
            <div className="fan-play-row">
              <button
                className="fan-primary"
                onClick={m.play}
                disabled={m.error}
              >
                {m.playing
                  ? t('Pause replay', '暂停回放')
                  : t('Play replay', '播放回放')}
              </button>
              <button
                className="fan-secondary"
                onClick={() => m.seek(SEGMENT_START)}
              >
                {t('Back to 48:00', '回到 48:00')}
              </button>
              <button
                className="fan-secondary"
                onClick={() => m.seek(COMPARISON_TIME)}
              >
                {t('Key moment · 58:00', '关键时刻 · 58:00')}
              </button>
              <label>
                {t('Speed', '速度')}
                <select
                  aria-label="Replay speed"
                  value={m.speed}
                  onChange={(e) => m.setSpeed(Number(e.target.value))}
                >
                  <option value="1">1×</option>
                  <option value="10">10×</option>
                  <option value="30">30×</option>
                </select>
              </label>
            </div>
            <label className="fan-timeline">
              {t('Match time', '比赛时间')}{' '}
              <strong>{clock(m.request.atMs)}</strong>
              <input
                type="range"
                aria-label="Match time"
                aria-valuetext={clock(m.request.atMs)}
                min={SEGMENT_START}
                max={m.end}
                step={1000}
                value={m.request.atMs}
                onChange={(e) => m.seek(Number(e.target.value))}
              />
            </label>
          </section>
        )}
        {m.end > COMPARISON_TIME && m.request.atMs < m.end && (
          <button className="fan-update" onClick={() => m.seek(m.end)}>
            {t(
              'A newer version of this story is available',
              '此故事有更新版本',
            )}{' '}
            · {clock(m.end)} <span>{t('See the update →', '查看更新 →')}</span>
          </button>
        )}
        {snapshot && correction && first && (
          <p className="fan-correction" role="status">
            {t(
              'A match update changed an earlier story. Here’s the latest.',
              '比赛更新改变了之前的故事。以下是最新情况。',
            )}
          </p>
        )}
        {first && (
          <div className="fan-quick-actions">
            <div className="fan-actions">
              <button
                ref={actionButton}
                className="fan-primary"
                aria-expanded={recapOpen}
                aria-controls="fan-recap"
                onClick={() => setRecapOpen((v) => !v)}
              >
                {recapOpen
                  ? t('Close catch-up', '收起回顾')
                  : t('Catch me up', '快速回顾')}{' '}
                <span aria-hidden="true">↗</span>
              </button>
              <button
                className="fan-secondary"
                aria-expanded={!!selectedStory}
                onClick={() => showMoments(first.key)}
              >
                {t('Show the moments', '查看关键事件')}
              </button>
            </div>
          </div>
        )}
        <div className="fan-section-heading fan-story-heading">
          <h2>
            {isReplayStory ? t('More match stories','更多比赛故事') : p.club_id
              ? t('What changed for your side?', '你关注的一方有哪些变化？')
              : t('What changed?', '发生了什么变化？')}
          </h2>
          <label className="fan-showcase">
            <span>{t('Explore a story', '选择故事')}</span>
            <select
              aria-label="Explore a story"
              value={m.request.scenario}
              onChange={(e) => chooseShowcase(e.target.value)}
            >
              {Object.entries(showcases)
                .filter(
                  ([id]) =>
                    id === 'increase' ||
                    m.scenarios.some((s) => s.scenario_id === id),
                )
                .map(([id, labels]) => (
                  <option key={id} value={id}>
                    {t(...labels)}
                  </option>
                ))}
            </select>
          </label>
        </div>
        {m.error ? (
          <section className="fan-empty" role="alert">
            <h3>{t('We couldn’t load this moment.', '暂时无法加载此刻。')}</h3>
            <p>
              {t(
                'Your place is saved for this visit. Try again in a moment.',
                '本次访问的回放位置已保留，请稍后重试。',
              )}
            </p>
            <button className="fan-primary" onClick={m.retry}>
              {t('Try again', '重试')}
            </button>
          </section>
        ) : !snapshot ? (
          <section className="fan-empty" role="status">
            <h3>{t('Bringing you the match story…', '正在加载比赛故事…')}</h3>
            <p>
              {t(
                'Loading the latest plays.',
                '正在加载最新回放。',
              )}
            </p>
          </section>
        ) : isReplayStory ? (
          <article className="fan-turnaround-story"><p>{t('Use “Explore a story” to see how pressure, winning the ball back and individual players change a match.', '通过“选择故事”探索施压、夺回球权和球员表现如何改变比赛。')}</p></article>
        ) : first ? (
          <article className="fan-hero">
            <div className="fan-hero-copy">
              <p className="fan-kicker">
                {first.subject} ·{' '}
                {changed
                  ? t('UPDATED STORY', '已更新的故事')
                  : t('THE STORY SO FAR', '当前故事')}
              </p>
              <h3>{first.narrative.title}</h3>
              <p className="fan-explanation">{first.narrative.explanation}</p>
              <button
                className="fan-text-button"
                aria-expanded={peopleOpen}
                onClick={() => setPeopleOpen((v) => !v)}
              >
                {t('Who was involved?', '谁参与其中？')} →
              </button>
            </div>
            <div
              className="fan-comparison"
              aria-label={`${first.before} to ${first.after}`}
            >
              <div>
                <span>{t('BEFORE', '此前')}</span>
                <strong>{first.before}</strong>
                <small>{windowLabel(first.windows[0])}</small>
              </div>
              <span className="fan-count-arrow" aria-hidden="true">
                →
              </span>
              <div>
                <span>{t('NOW', '当前')}</span>
                <strong>{first.after}</strong>
                <small>{windowLabel(first.windows[1])}</small>
              </div>
              <p>{first.unit}</p>
            </div>
          </article>
        ) : (
          <section className="fan-empty" role="status">
            <h3>
              {correction
                ? t('This story has changed.', '这则故事有变化。')
                : m.request.atMs < COMPARISON_TIME
                  ? t('Earlier in the match', '比赛的较早时刻')
                  : p.player_id
                    ? t(
                        'No highlights for this player yet.',
                        '这位球员暂时还没有集锦。',
                      )
                    : t(
                        'No new talking points just yet.',
                        '暂时还没有新的比赛焦点。',
                      )}
            </h3>
            <p>
              {correction
                ? t(
                    'The match details were updated. Check back for the next talking point.',
                    '比赛详情已更新，稍后回来查看新的焦点。',
                  )
                : t(
                    'Watch the play or choose another story to keep exploring.',
                    '观看回放或选择其他故事，继续了解比赛。',
                  )}
            </p>
            {m.request.atMs < COMPARISON_TIME && (
              <button
                className="fan-primary"
                onClick={() => m.seek(COMPARISON_TIME)}
              >
                {t('See the key moment · 58:00', '查看关键时刻 · 58:00')}
              </button>
            )}
            {p.player_id && (
              <button
                className="fan-secondary"
                onClick={() => m.preferences({ ...p, player_id: null })}
              >
                {t('Show the team story', '查看球队故事')}
              </button>
            )}
          </section>
        )}
        {snapshot && changed && (
          <p className="fan-correction" role="status">
            {t(
              'Updated match details. Use the replay to revisit an earlier moment.',
              '比赛详情已更新。可通过回放查看之前的时刻。',
            )}
          </p>
        )}
        {first && peopleOpen && (
          <section
            className="fan-people"
            aria-label={t('Who was involved?', '谁参与其中？')}
          >
            <h2>{t('The people in these moments', '这些事件中的球员')}</h2>
            <p>
              {t(
                'Tap a player to follow their part in the match.',
                '选择球员，关注他们在比赛中的表现。',
              )}
            </p>
            <div>
              {actors.map((id) => (
                <button
                  className="fan-person"
                  key={id}
                  aria-pressed={p.player_id === id}
                  onClick={() =>
                    m.preferences({
                      ...p,
                      player_id: p.player_id === id ? null : id,
                    })
                  }
                >
                  <span aria-hidden="true">
                    {playerName(id)
                      .split(' ')
                      .map((n) => n[0])
                      .join('')}
                  </span>
                  <strong>{playerName(id)}</strong>
                  <small>
                    {p.player_id === id
                      ? t('Following · tap to clear', '已关注 · 点击取消')
                      : t('Follow player', '关注球员')}
                  </small>
                </button>
              ))}
            </div>
          </section>
        )}
        {snapshot && recapOpen && (
          <section
            className="fan-recap"
            id="fan-recap"
            aria-labelledby="fan-recap-title"
          >
            <div className="fan-section-heading">
              <div>
                <p className="fan-kicker">
                  {t('YOUR QUICK CATCH-UP', '你的快速回顾')}
                </p>
                <h2 id="fan-recap-title" tabIndex={-1}>
                  {t('The story in a few moments', '几个事件，了解故事')}
                </h2>
              </div>
              <button
                className="fan-secondary"
                onClick={() => {
                  setRecapOpen(false)
                  actionButton.current?.focus()
                }}
              >
                {t('Back to the story', '返回故事')}
              </button>
            </div>
            <p>
              {t(
                'The talking points from the last ten minutes.',
                '过去十分钟的比赛焦点。',
              )}
            </p>
            {stories.length ? (
              <ol>
                {stories.map((story) => (
                  <li key={story.key}>
                    <h3>{story.narrative.title}</h3>
                    <p>{displayText(story.narrative.explanation)}</p>
                    <button
                      className="fan-text-button"
                      onClick={() => showMoments(story.key)}
                    >
                      {t('See supporting moments', '查看支持事件')} →
                    </button>
                  </li>
                ))}
              </ol>
            ) : (
              <p>
                {t(
                  'The earlier statements no longer apply at this time or for this view.',
                  '之前的陈述不再适用于此刻或此视角。',
                )}
              </p>
            )}
          </section>
        )}
        {selectedStory && (
          <Moments
            story={selectedStory}
            language={p.language}
            onClose={() => {
              setMomentKey(null)
              actionButton.current?.focus()
            }}
          />
        )}
        <footer className="fan-footer">
          {replayStory && <small className="fan-data-note">{t(...replayStory.note)} {t('Hand-authored reconstruction with fictional identities, approximate positions and a rebased clock. Visible actions and lanes are estimated from the linked footage; off-camera positions and motion are illustrative, not measured tracking. No footage or audio is reproduced. Short replays are excluded from five-minute comparisons.', '手工重建使用虚构身份、近似位置和重设时钟。可见动作和线路参考所链接影像；镜头外的位置和移动为示意，并非追踪测量。未复制影像或音频。短回放不计入五分钟比较。')}</small>}
          <a href="#studio">{t("Producer Studio", "制作人工作室")} ↗</a>
          <p>
            {t(
              'About this match',
              '关于这场比赛',
            )}
          </p>
          <span>
            {m.status === 'connected'
              ? t('Match updates connected', '比赛更新已连接')
              : t('Checking for match updates', '正在检查比赛更新')}{' '}
            · {t('Updated to', '更新至')}{' '}
            {snapshot ? clock(snapshot.state.at.elapsed_ms) : '—'}
          </span>
          <a href="#analysis">
            {t('Analysis & presenter tools', '分析与演示工具')} ↗
          </a>
          {!replayStory && <small className="fan-data-note">{t('This showcase uses fictional clubs, players and synthetic match events. The 22-player pitch is an illustration: ball actions follow the event records; off-ball positions and movement are animated, not tracking data. Comparisons cover the displayed five-minute windows, excluding the start and including the end.', '本展示使用虚构球队、球员和合成比赛事件。22人球场为示意动画：有球动作来自事件记录，无球位置和移动并非追踪数据。比较覆盖画面中的五分钟时段，不含起点、包含终点。')}</small>}
        </footer>
      </main>
    </div>
  )
}
