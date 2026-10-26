export type Cutoff={period:1|2;elapsed_ms:number}
export type Role='chance'|'defence'|'control'|'players'
export type Metric={id:string;key:string;window:'prefix'|'current'|'previous';role:string;label:string;unit:string;basis:string;status:string;value:number|null|Record<string,unknown>|unknown[];club_id?:string|null;player_id?:string|null;coverage?:unknown;presentation?:'evidence_only'}
export type Evidence={id:string;event_id:string;revision:number;period:1|2;elapsed_ms:number;club_id:string;player_id:string;kind:string;outcome:string;start?:{x:number;y:number}|null;end?:{x:number;y:number}|null}
export type Signal={id:string;title:string;detail:string;evidence_ids:string[];metric_ids:string[];role:string;salience:number}
export type Snapshot={momentum?:{period:1|2;elapsed_ms:number;value:number}[];snapshot_id:string;match_id:string;cutoff:Cutoff;through_sequence:number;clubs:{club_id:string;name:string}[];score:Record<string,number>;metrics:Metric[];players:{player_id:string;name:string;role:string;club_id:string}[];evidence:Evidence[];signals:Signal[];windows?:Record<string,{period:1|2|null;start_ms:number;end_ms:number;boundary:string}>;methods?:unknown;triggers?:unknown}
export type Reading={role:string;headline:string;explanation:string;alternative:string;watch_next:string;evidence_ids:string[];metric_ids:string[];confidence:string}
export type DiscussionMessage={id:string;role:Role|'footie';text:string;reply_to:string|null;relation:'observation'|'builds_on'|'challenges'|'qualifies'|'synthesis';metric_ids:string[];evidence_ids:string[];watch_next?:string}
export type Analysis={messages?:DiscussionMessage[];evidence?:Evidence[];metrics?:Metric[];match_id?:string;snapshot_id:string;cutoff:Cutoff;mode:string;status:string;readings:Reading[];summary:{headline:string;explanation:string;evidence_ids:string[];metric_ids:string[]}|null}
export type AnalystConfig={cancellation_available?:boolean;discussion_available?:boolean;discussion_runtime?:string|null;available:boolean;mode:'foundry'|'metrics';roles:{id:string;name:string;description:string}[];interval_ms:number}
export type Preferences={language:'en'|'zh-Hans';depth:'analyst'|'casual';focus_player_id:string|null}
export const lenses:{id:Role;name:string;description:string;mark:string}[]=[
  {id:'chance',name:'Chances',description:'How chances are created and finished',mark:'↗'},
  {id:'control',name:'Build-up',description:'Where possession is taking the game',mark:'⇄'},
  {id:'defence',name:'Transitions',description:'What happens when the ball changes sides',mark:'↔'},
  {id:'players',name:'Player impact',description:'The people changing the match',mark:'◎'},
]
export function clockLabel(cutoff:Cutoff){const seconds=Math.floor(cutoff.elapsed_ms/1000),minutes=Math.floor(seconds/60);return minutes>=45?`${cutoff.period===1?45:90}+${minutes-45}:${String(seconds%60).padStart(2,'0')}`:`${minutes+(cutoff.period===2?45:0)}:${String(seconds%60).padStart(2,'0')}`}
export function sameCutoff(a:Cutoff,b:Cutoff){return a?.period===b.period&&a?.elapsed_ms===b.elapsed_ms}
export function before(a:Cutoff,b:Cutoff){return a.period<b.period||(a.period===b.period&&a.elapsed_ms<b.elapsed_ms)}
export function bucket(c:Cutoff,interval:number):Cutoff{return {period:c.period,elapsed_ms:Math.floor(c.elapsed_ms/interval)*interval}}
export function finiteMetric(m:Metric):m is Metric&{value:number}{return typeof m.value==='number'&&Number.isFinite(m.value)}
export function metricValue(m:Metric){if(!finiteMetric(m))return '—';const val=new Intl.NumberFormat('en',{maximumFractionDigits:m.unit==='count'?0:2}).format(m.value);return m.unit==='percent'||m.unit==='%'?`${val}%`:val}
export function metricUnit(m:Metric){return ({expected_goals:'xG',actions_per_minute:'/ min',metres:'m',seconds:'s'} as Record<string,string>)[m.unit]??(['count','percent','%','ratio','index','probability','fraction',''].includes(m.unit)?'':m.unit)}
export function recentRange(snapshot:Snapshot|null){
  if(!snapshot)return 'Recent play in this half'
  const period=snapshot.cutoff.period,end=snapshot.windows?.current?.end_ms??snapshot.cutoff.elapsed_ms,start=snapshot.windows?.current?.start_ms??Math.max(0,end-300000)
  return `${clockLabel({period,elapsed_ms:start})} – ${clockLabel({period,elapsed_ms:end})} · ${period===1?'First':'Second'} half`
}
export function coverageLabel(metric:Metric){
  const c=metric.coverage as {numerator?:unknown;denominator?:unknown}|undefined
  return c&&typeof c.numerator==='number'&&typeof c.denominator==='number'&&c.denominator>0?`Source coverage: ${c.numerator} of ${c.denominator} eligible actions.`:''
}
const text=(value:unknown,limit=5000)=>typeof value==='string'&&value.length<=limit
const ids=(value:unknown)=>Array.isArray(value)&&value.length<=128&&value.every(v=>text(v,200))
export function validateSnapshot(value:unknown,matchId:string,cutoff:Cutoff):value is Snapshot{
  if(!value||typeof value!=='object')return false
  const s=value as Snapshot
  return s.match_id===matchId&&sameCutoff(s.cutoff,cutoff)&&text(s.snapshot_id,128)&&
    Array.isArray(s.metrics)&&s.metrics.every(m=>m&&text(m.id,200)&&text(m.label,200)&&text(m.key,100)&&text(m.unit,80)&&text(m.basis,200)&&text(m.role,50)&&text(m.status,80)&&['prefix','current','previous'].includes(m.window))&&
    Array.isArray(s.clubs)&&s.clubs.every(c=>c&&text(c.club_id,100)&&text(c.name,200))&&
    Array.isArray(s.players)&&s.players.every(p=>p&&text(p.player_id,100)&&text(p.name,200)&&text(p.club_id,100))&&
    Array.isArray(s.signals)&&s.signals.every(v=>v&&text(v.id,200)&&text(v.title,200)&&text(v.detail)&&text(v.role,50)&&ids(v.evidence_ids)&&ids(v.metric_ids))&&
    Array.isArray(s.evidence)&&s.evidence.every(e=>e&&text(e.id,200)&&text(e.event_id,100)&&text(e.player_id,100)&&text(e.kind,100)&&[1,2].includes(e.period)&&Number.isSafeInteger(e.elapsed_ms))
}
export function validateAnalysis(value:unknown,cutoff:Cutoff,matchId?:string):value is Analysis{
  if(!value||typeof value!=='object')return false
  const a=value as Analysis
  if(a.metrics!==undefined&&(!Array.isArray(a.metrics)||!a.metrics.every(m=>m&&text(m.id,200)&&text(m.label,200)&&text(m.unit,80)&&text(m.basis,200)&&['prefix','current','previous'].includes(m.window))))return false
  if(a.evidence!==undefined&&(!Array.isArray(a.evidence)||!a.evidence.every(e=>e&&text(e.id,200)&&text(e.event_id,100)&&text(e.kind,100)&&text(e.outcome,100)&&[1,2].includes(e.period)&&Number.isSafeInteger(e.elapsed_ms)&&e.elapsed_ms>=0&&Number.isSafeInteger(e.revision)&&e.revision>0&&!before(cutoff,e))))return false
  return (!a.messages||(Array.isArray(a.messages)&&a.messages.length<=5&&a.messages.every(m=>m&&['control','players','chance','defence','footie'].includes(m.role)&&m.id===m.role&&['observation','builds_on','challenges','qualifies','synthesis'].includes(m.relation)&&text(m.text,1800)&&(m.watch_next===undefined||text(m.watch_next,350))&&ids(m.metric_ids)&&ids(m.evidence_ids)&&(m.reply_to===null||text(m.reply_to,80)))))&&(!matchId||a.match_id===undefined||a.match_id===matchId)&&sameCutoff(a.cutoff,cutoff)&&text(a.snapshot_id,128)&&text(a.status,80)&&Array.isArray(a.readings)&&a.readings.length<=4&&a.readings.every(r=>r&&text(r.headline,300)&&text(r.explanation)&&text(r.role,50)&&text(r.alternative)&&text(r.watch_next)&&ids(r.evidence_ids)&&ids(r.metric_ids))&&(!a.summary||(text(a.summary.headline,300)&&text(a.summary.explanation)&&ids(a.summary.evidence_ids)&&ids(a.summary.metric_ids)))
}
