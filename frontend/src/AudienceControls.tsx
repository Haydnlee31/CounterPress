import type { Preferences, Snapshot } from './types'

export function AudienceControls({ preferences: p, teams, viewer, onViewer, onChange }: {
  preferences: Preferences; teams: NonNullable<Snapshot['teams']>; viewer: string;
  onViewer: (viewer: string) => void; onChange: (preferences: Preferences) => void;
}) {
  const t = (en: string, zh: string) => p.language === 'zh-Hans' ? zh : en
  return <section className="audience-controls" aria-label={t('Viewing preferences', '观看偏好')}>
    <label>{t('Local viewer', '本地观众')}<select aria-label="Local viewer" value={viewer} onChange={e => onViewer(e.target.value)}><option value="one">{t('Viewer 1', '观众 1')}</option><option value="two">{t('Viewer 2', '观众 2')}</option></select></label>
    <label>{t('View', '视图')}<select aria-label="Explanation depth" value={p.depth} onChange={e => onChange({ ...p, depth: e.target.value as Preferences['depth'] })}><option value="analyst">{t('Analyst', '分析视图')}</option><option value="casual">{t('Casual', '简明视图')}</option></select></label>
    <label>{t('Language', '语言')}<select aria-label="Language" value={p.language} onChange={e => onChange({ ...p, language: e.target.value as Preferences['language'] })}><option value="en">English</option><option value="zh-Hans">简体中文</option></select></label>
    <label>{t('Club preference', '俱乐部偏好')}<select aria-label="Club preference" value={p.club_id ?? ''} onChange={e => onChange({ ...p, club_id: e.target.value || null })}><option value="">{t('Any club', '不限俱乐部')}</option>{teams.map(team => <option key={team.team_id} value={team.team_id}>{team.name}</option>)}</select></label>
    <label>{t('Player contribution', '球员贡献')}<select aria-label="Player contribution" value={p.player_id ?? ''} onChange={e => onChange({ ...p, player_id: e.target.value || null })}><option value="">{t('All contributors', '所有贡献者')}</option>{teams.flatMap(team => team.player_ids.map(player => <option key={player} value={player}>{player} · {team.name}</option>))}</select></label>
    <label>{t('Metric focus', '指标侧重')}<select aria-label="Metric focus" value={p.metric_focus} onChange={e => onChange({ ...p, metric_focus: e.target.value as Preferences['metric_focus'] })}><option value="balanced">{t('Balanced', '均衡')}</option><option value="high_recoveries">{t('High recoveries', '前场夺回球权')}</option><option value="pressure_exposure">{t('Pressure exposure', '压迫暴露')}</option><option value="pressured_escape">{t('Escape under pressure', '受压摆脱')}</option><option value="possession_without_progression">{t('Possession without progression', '控球未推进')}</option><option value="passing">{t('Passing', '传球')}</option></select></label>
    <label>{t('Card budget', '卡片数量')}<select aria-label="Card budget" value={p.card_budget} onChange={e => onChange({ ...p, card_budget: Number(e.target.value) })}><option value="1">1</option><option value="0">0</option></select></label>
  </section>
}
