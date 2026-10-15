import type { Workflow } from './types'

export function WorkflowActivity({ workflow, language = 'en' }: { workflow?: Workflow | null; language?: 'en' | 'zh-Hans' }) {
  if (!workflow) return null
  const labels: Record<string, string> = { 'Requested comparison': '已请求比较', 'Checked data quality': '已检查数据质量', 'Requested event sequence': '已请求事件序列', 'Accepted supported comparison': '已接受有证据支持的比较', 'Narrowed to recovery counts': '已缩小为夺回球权计数', 'Rejected insufficient evidence': '证据不足，已拒绝', 'Prepared explanation': '已准备说明', 'Used factual fallback': '已使用事实说明', 'Discarded stale result': '已丢弃过时结果' }
  const title = language === 'zh-Hans' ? '分析记录' : 'Analysis activity'
  return <section className="workflow-activity" aria-label={title}>
    <h3>{title}</h3>
    <ol>{workflow.actions.map((action, index) => <li key={`${workflow.attempt_id}-${index}`}>{language === 'zh-Hans' ? labels[action.label] ?? action.label : action.label}</li>)}</ol>
  </section>
}
