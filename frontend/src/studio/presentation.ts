import type { Review } from './session'
export type Statement = Review['recap']['statements'][number]
export function readingEstimate(statement: Statement) {
  const text=[statement.narrative.title,statement.narrative.explanation,statement.narrative.qualification].join(' ')
  const chinese=statement.narrative.language==='zh-Hans'
  const units=chinese?Array.from(text.replace(/\s/g,'')).length:(text.match(/\S+/g)??[]).length
  return {seconds:Math.max(1,Math.ceil(units/(chinese?240:140)*60)),basis:chinese?'240 characters/min':'140 words/min'}
}
/** Compare content, never infer a football change from the fingerprint alone. */
export function changedStories(before:Review,after:Review):string[] {
  const old=new Map(before.recap.statements.map(s=>[s.citation.insight_id,s]))
  const result:string[]=[]
  for(const next of after.recap.statements){
    const prior=old.get(next.citation.insight_id)
    if(!prior)result.push(`Added: ${next.narrative.title}`)
    else if(JSON.stringify(prior)!==JSON.stringify(next))result.push(`Updated: ${next.narrative.title}`)
    old.delete(next.citation.insight_id)
  }
  for(const prior of old.values())result.push(`Removed: ${prior.narrative.title}`)
  return result.length?result:['The source or approval context changed. Check the current evidence before approving again.']
}
