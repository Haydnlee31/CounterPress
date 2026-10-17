import { useEffect, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import { clock, windowLabel } from '../types'
import { clubs, clubName, displayText, playerName } from './identity'
import { useMatchday, SEGMENT_START, COMPARISON_TIME } from './useMatchday'
import { storiesFor } from './stories'
import { Moments } from './Moments'
import './matchday.css'

const showcases: Record<string, [string, string]> = {
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
  const accent = p.club_id
    ? clubs[p.club_id as keyof typeof clubs]?.accent
    : undefined
  return (
    <div
      className="matchday"
      lang={p.language}
      style={{ '--fan-accent': accent ?? '#c4ed91' } as CSSProperties}
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
        <div className="fan-disclosure">
          <span aria-hidden="true">◈</span>
          {t('FICTIONAL MATCH SIMULATION', '虚构比赛模拟')}
          <span>
            {t(
              'Generated events. Not a real result.',
              '事件由模拟生成，非真实比赛结果。',
            )}
          </span>
        </div>
        <div className="fan-intro">
          <div>
            <p className="fan-kicker">
              {t('YOUR MATCHDAY COMPANION', '你的比赛故事伙伴')}
            </p>
            <h1>{t('Back in the game.', '回到比赛之中。')}</h1>
            <p>
              {t(
                'Catch up on what changed. See the moments that explain it.',
                '快速了解变化，查看背后的关键事件。',
              )}
            </p>
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
                'Following changes which stories come first. The match facts stay the same. All identities here are fictional.',
                '关注偏好会调整故事顺序，比赛事实不会改变。这里的身份均为虚构。',
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
                    team.player_ids.map((id) => (
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
        <section
          className="fan-score"
          aria-label={t('Match scoreboard', '比赛记分牌')}
        >
          <div className="fan-team">
            <span className="fan-monogram">EB</span>
            <strong>{clubName('eastbridge')}</strong>
          </div>
          <div className="fan-score-center">
            <span>
              {snapshot?.state.score.eastbridge ?? '–'} <i>:</i>{' '}
              {snapshot?.state.score.northport ?? '–'}
            </span>
            <time>
              {clock(m.request.atMs)} · {t('2nd half', '下半场')}
            </time>
          </div>
          <div className="fan-team away">
            <strong>{clubName('northport')}</strong>
            <span className="fan-monogram away">NP</span>
          </div>
          <div className="fan-score-foot">
            <span>
              {t('Recorded segment', '记录片段')} · 48:00–{clock(m.end)}
              {snapshot && (
                <>
                  <br />
                  {t('Facts through', '数据截至')}{' '}
                  {clock(snapshot.state.at.elapsed_ms)}
                </>
              )}
            </span>
            <button
              onClick={() => setReplayOpen((v) => !v)}
              aria-expanded={replayOpen}
              aria-controls="fan-replay"
            >
              {t('Explore replay', '探索回放')} ↗
            </button>
          </div>
        </section>
        {replayOpen && (
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
              'An earlier story was withdrawn because the revised events no longer support it. Other supported stories are shown below.',
              '修订后的事件不再支持先前的故事，因此已将其撤回。下方展示其他有证据支持的故事。',
            )}
          </p>
        )}
        <div className="fan-section-heading fan-story-heading">
          <h2>
            {p.club_id
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
                'Checking the recorded moments for this view.',
                '正在核对当前视角的记录事件。',
              )}
            </p>
          </section>
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
              <p className="fan-qualification">
                {first.narrative.qualification}
              </p>
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
                ? t('This story was withdrawn.', '此故事已撤回。')
                : m.request.atMs < COMPARISON_TIME
                  ? t('The comparison is still unfolding.', '比较仍在进行中。')
                  : p.player_id
                    ? t(
                        'No supported story for this player here.',
                        '这里暂无支持该球员故事的证据。',
                      )
                    : t(
                        'No supported change in this view.',
                        '此视角暂无证据支持的变化。',
                      )}
            </h3>
            <p>
              {correction
                ? t(
                    'The revised events no longer support the earlier claim. We removed it rather than leave an outdated story on screen.',
                    '修订后的事件不再支持原有结论，因此已将其移除。',
                  )
                : t(
                    'This does not mean nothing happened. We only show changes supported by the recorded events.',
                    '这并不表示没有事件发生。我们只展示记录事件所支持的变化。',
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
              'Updated from revised events. Earlier versions are available in Explore replay; your chosen time never moves automatically.',
              '已依据修订事件更新。可通过探索回放查看历史版本；你选择的时间不会自动改变。',
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
                'Fictional players appearing in this story’s evidence. Following a player never changes the team totals.',
                '以下为故事证据中出现的虚构球员。关注球员不会改变球队总数。',
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
                'A factual recap of this simulated segment, not the full match. Only supported changes are included.',
                '这是模拟片段的事实回顾，并非整场比赛。仅包含有证据支持的变化。',
              )}
            </p>
            {stories.length ? (
              <ol>
                {stories.map((story) => (
                  <li key={story.key}>
                    <h3>{story.narrative.title}</h3>
                    <p>{displayText(story.narrative.explanation)}</p>
                    <p className="fan-qualification">
                      {story.narrative.qualification}
                    </p>
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
          <a href="#studio">{t("Producer Studio", "制作人工作室")} ↗</a>
          <p>
            {t(
              'One match. Different perspectives. The same facts.',
              '同一场比赛，不同视角，相同事实。',
            )}
          </p>
          <span>
            {m.status === 'connected'
              ? t('Revision updates connected', '修订更新已连接')
              : t('Checking for revised events', '正在检查修订事件')}{' '}
            · {t('Facts through', '事实截至')}{' '}
            {snapshot ? clock(snapshot.state.at.elapsed_ms) : '—'}
          </span>
          <a href="#analysis">
            {t('Analysis & presenter tools', '分析与演示工具')} ↗
          </a>
        </footer>
      </main>
    </div>
  )
}
