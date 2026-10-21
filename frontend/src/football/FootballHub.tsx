import {useEffect,useMemo,useState} from 'react'
import type {CSSProperties} from 'react'
import {AppHeader} from '../shell/AppHeader'
import {defaults,readPreferences,savePreferences,toggleFavorite,preferenceKey} from '../../../integrations/personalization/client'
import type {FanPreferences} from '../../../integrations/personalization/client'
import {ActivityMap,Badge,Shirt,Tiles,clubStyle} from './visuals'
import {contextKey,dateLabel,getData,loadWorld,roleName,tileValue,useFan,useResource,visiblePlayers} from './data'
import type {Club,CompareView,Highlight,History,HomeView,Match,Player,ProfileView,World} from './data'
import {HighlightPlayer} from './HighlightPlayer'
import PlayerInsights from './PlayerInsights'
import {AskFootie} from '../assistant/AskFootie'
import {FootieMascot} from '../assistant/FootieMascot'
import './football.css'
import {Standings} from './Standings'

type Page={tab:'players'|'following'|'clubs'|'compare'|'standings';kind?:'player'|'club';id?:string}
export function readPage():Page{
  const [,part,id]=window.location.hash.split('/')
  if((part==='player'||part==='club')&&id&&/^[a-zA-Z0-9_-]+$/.test(id))return {tab:part==='player'?'players':'clubs',kind:part,id}
  return {tab:part==='following'||part==='clubs'||part==='compare'||part==='standings'?part:'players'}
}
function initialPreferences(){try{return readPreferences(window.localStorage)}catch{return {preferences:defaults(),status:'unavailable' as const}}}
type Context={world:World;prefs:FanPreferences;update:(p:FanPreferences)=>void;follow:(kind:'player'|'club',id:string)=>void;compareIds:string[];toggleCompare:(id:string)=>void;season:string;setSeason:(s:string)=>void;home?:HomeView;watch:(h:Highlight)=>void}
const openProfile=(kind:'player'|'club',id:string)=>{window.location.hash=`football/${kind}/${id}`}

export default function FootballHub(){
  const [page,setPage]=useState(readPage),[initial]=useState(initialPreferences),[prefs,setPrefs]=useState(initial.preferences)
  const [notice,setNotice]=useState(initial.status==='unavailable'?'Preferences will last for this visit; browser storage is unavailable.':initial.status==='invalid'?'Your saved preferences could not be read. Choose your favorites again.':'')
  const [season,setSeason]=useState(''),[compareIds,setCompareIds]=useState<string[]>([]),[highlight,setHighlight]=useState<Highlight|null>(null)
  const world=useResource('world',loadWorld,false)
  useEffect(()=>{const route=()=>{setPage(readPage());setHighlight(null);window.scrollTo({top:0,behavior:'instant'})};window.addEventListener('hashchange',route);return()=>window.removeEventListener('hashchange',route)},[])
  useEffect(()=>{const sync=(event:StorageEvent)=>{if(event.key===preferenceKey||event.key===null)setPrefs(initialPreferences().preferences)};window.addEventListener('storage',sync);return()=>window.removeEventListener('storage',sync)},[])
  const registry=useMemo(()=>world.data?{clubIds:new Set(world.data.catalog.clubs.map(c=>c.club_id)),playerIds:new Set(world.data.players.map(p=>p.player_id))}:undefined,[world.data])
  useEffect(()=>{
    if(!registry)return
    try{const stored=readPreferences(window.localStorage,registry);setPrefs(stored.preferences);if(stored.status==='invalid')setNotice('Choose your favorites again; some saved choices are no longer available.')}catch{/* Session preferences remain usable. */}
  },[registry])
  const update=(next:FanPreferences)=>{try{let saved=false;try{saved=savePreferences(window.localStorage,next,registry)}catch{/* Storage may be denied. */}setPrefs(next);setNotice(saved?'':'Your choices apply for this visit. Browser storage is unavailable.')}catch{setNotice('Please choose a registered player or club.')}}
  const follow=(kind:'player'|'club',id:string)=>{
    try{const next=toggleFavorite(prefs,kind,id,registry);if(kind==='club'&&!next.primary_club_id&&next.favorite_club_ids.includes(id))next.primary_club_id=id;update(next)}
    catch{setNotice(kind==='player'?'You can follow up to 12 players. Unfollow someone to add another.':'You can follow up to 4 clubs. Unfollow one to add another.')}
  }
  const toggleCompare=(id:string)=>{setCompareIds(old=>old.includes(id)?old.filter(x=>x!==id):old.length<4?[...old,id]:old);if(compareIds.length===4&&!compareIds.includes(id))setNotice('Compare up to four players. Remove one to make room.')}
  const zh=prefs.language==='zh-Hans',t=(en:string,cn:string)=>zh?cn:en
  const theme=world.data?.catalog.clubs.find(c=>c.club_id===prefs.primary_club_id)
  return <div className={`football-hub ${page.kind?'has-profile':''}`} lang={prefs.language} style={clubStyle(theme)}>
    <AppHeader active="football" language={prefs.language}/>
    <main className="fh-main">
      <div className="fh-topline"><div><p className="fh-eyebrow">COUNTERPRESS / {t('PLAYERS & CLUBS','球员与俱乐部')}</p><div className="fh-title-actions"><h1>{t('Clubhouse','Clubhouse')}<span>.</span></h1><a className="ask-footie" href="#assistant"><FootieMascot size={32}/>{t('Ask Footie','问问 Footie')} <span aria-hidden="true">↗</span></a></div></div>
        <div className="fh-settings"><label>{t('Insights','解读')}<select aria-label="Insight depth" value={prefs.depth} onChange={e=>update({...prefs,depth:e.target.value as FanPreferences['depth']})}><option value="casual">{t('At a glance','快速了解')}</option><option value="analyst">{t('In depth','深入分析')}</option></select></label><label>{t('Language','语言')}<select aria-label="Hub language" value={prefs.language} onChange={e=>update({...prefs,language:e.target.value as FanPreferences['language']})}><option value="en">English</option><option value="zh-Hans">中文</option></select></label></div>
      </div>
      <nav className="fh-tabs" aria-label={t('Clubhouse sections','Clubhouse栏目')}>{([['players','Players','球员'],['clubs','Clubs','俱乐部'],['following','Following','关注'],['compare','Compare','对比'],['standings','Standings','积分榜']] as const).map(([tab,en,cn])=><a key={tab} href={`#football/${tab}`} aria-current={page.tab===tab?'page':undefined}>{t(en,cn)}{' '}{tab==='following'&&<span>{prefs.favorite_player_ids.length+prefs.favorite_club_ids.length}</span>}{tab==='compare'&&compareIds.length>0&&<span>{compareIds.length}</span>}</a>)}</nav>
      {notice&&<div className="fh-notice" role="status">{notice}<button aria-label="Dismiss notice" onClick={()=>setNotice('')}>×</button></div>}
      {world.error?<Failure retry={world.retry}/>:!world.data?<Loading/>:<HubContent world={world.data} prefs={prefs} update={update} follow={follow} compareIds={compareIds} toggleCompare={toggleCompare} season={season} setSeason={setSeason} page={page} watch={setHighlight}/>}
      <footer className="fh-footer"><span>CounterPress · {t('Clubhouse','Clubhouse')}</span>{world.data&&<span>{t('Stats through','统计截至')} {dateLabel(world.data.throughDate,zh)}</span>}</footer>
    </main>
    {compareIds.length>0&&page.tab!=='compare'&&world.data&&<aside className="fh-compare-tray" aria-label="Selected players for comparison"><span>{compareIds.length}/4 {t('selected','已选择')}</span><div>{compareIds.map(id=><button key={id} onClick={()=>toggleCompare(id)} aria-label={`Remove ${world.data!.players.find(p=>p.player_id===id)?.name} from comparison`}>{world.data!.players.find(p=>p.player_id===id)?.name}<span>×</span></button>)}</div><a className="fh-button" href="#football/compare">{t('Compare players','对比球员')} →</a></aside>}
    {highlight&&world.data&&<HighlightPlayer highlight={highlight} world={world.data} prefs={prefs} update={update} close={()=>setHighlight(null)}/>}
  </div>
}

function HubContent(props:Context & {page:Page}){
  const {world,prefs,season,page}=props
  const home=useFan<HomeView>(`home:${contextKey(prefs,season)}:${world.asOf}`,client=>client.home(prefs,{as_of:world.asOf,...(season?{season}:{})}))
  const ctx={...props,home:home.data}
  return <>
    {page.kind&&page.id?<Profile key={`${page.kind}:${page.id}`} {...ctx} kind={page.kind} id={page.id}/>:page.tab==='standings'?<Standings world={world}/>:page.tab==='players'?<Directory {...ctx}/>:page.tab==='clubs'?<Clubs {...ctx}/>:page.tab==='compare'?<Comparison {...ctx}/>:<Following {...ctx} error={!!home.error} retry={home.retry}/>}
  </>
}
export function Loading(){return <div className="fh-loading" role="status"><span/>{'Loading your football…'}</div>}
export function Failure({retry}:{retry:()=>void}){return <div className="fh-empty" role="alert"><h2>This view couldn’t be loaded.</h2><p>Please try again.</p><button className="fh-button" onClick={retry}>Try again</button></div>}
function Follow({active,name,onClick}:{active:boolean;name:string;onClick:()=>void}){return <button className={`fh-follow ${active?'is-following':''}`} onClick={onClick} aria-pressed={active} aria-label={`${active?'Unfollow':'Follow'} ${name}`}><span aria-hidden="true">{active?'♥':'♡'}</span><span>{active?'Following':'Follow'}</span></button>}
function PlayerCard({player,ctx}:{player:Player;ctx:Context}){
  const club=ctx.world.catalog.clubs.find(c=>c.club_id===player.club_id)!
  const comparing=ctx.compareIds.includes(player.player_id)
  return <article className="fh-player-card" style={clubStyle(club)}>
    <a className="fh-player-art" href={`#football/player/${player.player_id}`} aria-label={`View ${player.name}`}><span className="fh-card-club"><Badge club={club}/>{club.name}</span><Shirt player={player} club={club}/><span className="fh-art-arrow">↗</span></a>
    <div className="fh-player-copy"><p>{roleName(player.role,ctx.prefs.language==='zh-Hans')} <span>#{player.number}</span></p><a href={`#football/player/${player.player_id}`}><h3>{player.name}</h3></a><div className="fh-card-actions"><Follow active={ctx.prefs.favorite_player_ids.includes(player.player_id)} name={player.name} onClick={()=>ctx.follow('player',player.player_id)}/><button className="fh-compare-add" aria-pressed={comparing} aria-label={`${comparing?'Remove':'Add'} ${player.name} ${comparing?'from':'to'} comparison`} onClick={()=>ctx.toggleCompare(player.player_id)}>{comparing?'✓':'⇄'}<span>Compare</span></button></div></div>
  </article>
}
function Directory(ctx:Context){
  const [query,setQuery]=useState(''),[club,setClub]=useState(''),[role,setRole]=useState(''),[onlyFollowing,setOnlyFollowing]=useState(false)
  const zh=ctx.prefs.language==='zh-Hans',t=(en:string,cn:string)=>zh?cn:en
  const players=visiblePlayers(ctx.world.players,query,club,role,onlyFollowing?ctx.prefs.favorite_player_ids:null)
  return <><div className="fh-directory-title"><div><p className="fh-eyebrow">{ctx.world.catalog.counts.featured_players} {t('PLAYERS','位球员')} / {ctx.world.catalog.counts.featured_clubs} {t('CLUBS','家俱乐部')}</p><h2>{t('Find your favorites.','找到你喜欢的球员。')}</h2><p>{t('Career stats, match history and highlights.','生涯数据、近期状态和重要时刻。')}</p></div><a className="fh-spotlight" href="#football/player/rh08"><span>{t('IN FOCUS','焦点球员')}</span><strong>Enzo Clarke <span>↗</span></strong><small>Redhaven · {t('Midfielder','中场')}</small></a></div>
    <div className="fh-filters"><label className="fh-search"><span aria-hidden="true">⌕</span><input aria-label="Search players" placeholder={t('Search players…','搜索球员…')} value={query} onChange={e=>setQuery(e.target.value)}/>{query&&<button onClick={()=>setQuery('')} aria-label="Clear search">×</button>}</label><label className="sr-only" htmlFor="fh-club-filter">Club</label><select id="fh-club-filter" value={club} onChange={e=>setClub(e.target.value)}><option value="">{t('All clubs','所有俱乐部')}</option>{ctx.world.catalog.clubs.filter(c=>c.featured).map(c=><option key={c.club_id} value={c.club_id}>{c.name}</option>)}</select><label className="sr-only" htmlFor="fh-position">Position</label><select id="fh-position" value={role} onChange={e=>setRole(e.target.value)}><option value="">{t('All positions','所有位置')}</option>{['GK','DF','MF','FW'].map(r=><option key={r} value={r}>{roleName(r,zh)}</option>)}</select><button className="fh-filter-toggle" aria-pressed={onlyFollowing} onClick={()=>setOnlyFollowing(!onlyFollowing)}>♡ {t('Following only','只看关注')}</button></div>
    <p className="fh-result-count" role="status">{players.length} {t(players.length===1?'player':'players','位球员')}</p>
    {players.length?<div className="fh-player-grid">{players.map(p=><PlayerCard key={p.player_id} player={p} ctx={ctx}/>)}</div>:<div className="fh-empty"><h2>{t('No players found','没有找到球员')}</h2><p>{t('Try a different name or clear your filters.','试试其他名字或清除筛选。')}</p><button className="fh-button" onClick={()=>{setQuery('');setClub('');setRole('');setOnlyFollowing(false)}}>{t('Show all players','显示所有球员')}</button></div>}
  </>
}
function Clubs(ctx:Context){
  const zh=ctx.prefs.language==='zh-Hans'
  return <><div className="fh-section-head fh-spaced"><div><p className="fh-eyebrow">{zh?'俱乐部':'THE CLUBS'}</p><h2>{zh?'选择你的主队':'Who’s your club?'}</h2></div><span>{zh?'关注俱乐部，获取相关动态':'Follow a club to bring its stories closer.'}</span></div><div className="fh-club-grid">{ctx.world.catalog.clubs.filter(c=>c.featured).map(club=><article className="fh-club-card" key={club.club_id} style={clubStyle(club)}><a href={`#football/club/${club.club_id}`}><Badge club={club}/><p>{club.short_name} / FC</p><h3>{club.name}</h3></a><div className="fh-club-actions"><Follow active={ctx.prefs.favorite_club_ids.includes(club.club_id)} name={club.name} onClick={()=>ctx.follow('club',club.club_id)}/><button className="fh-link" onClick={()=>openProfile('club',club.club_id)}>{zh?'查看俱乐部':'View club'} ↗</button></div></article>)}</div></>
}
function Scope({ctx}:{ctx:Context}){return <label className="fh-scope">{ctx.prefs.language==='zh-Hans'?'赛季':'Period'}<select aria-label="Statistics period" value={ctx.season} onChange={e=>ctx.setSeason(e.target.value)}><option value="">{ctx.prefs.language==='zh-Hans'?'整个生涯':'Career'}</option>{ctx.world.catalog.seasons.map(s=><option key={s}>{s}</option>)}</select></label>}
function Highlights({items,ctx}:{items:Highlight[];ctx:Context}){
  const zh=ctx.prefs.language==='zh-Hans'
  if(!items.length)return <p className="fh-muted">{zh?'此时间范围内暂无精彩片段。':'No highlights in this period.'}</p>
  return <div className="fh-highlight-grid">{items.map((h,index)=>{
    const club=ctx.world.catalog.clubs.find(c=>c.club_id===h.club_ids[0])
    const player=ctx.world.players.find(p=>p.player_id===h.player_ids.find(id=>ctx.prefs.favorite_player_ids.includes(id)))??ctx.world.players.find(p=>h.player_ids.includes(p.player_id)&&p.star)
    const content=<><div className="fh-highlight-art" style={clubStyle(club)}><span className="fh-play-icon">▶</span>{player?<span className="fh-highlight-number">{player.number}</span>:<span className="fh-highlight-number">{String(index+1).padStart(2,'0')}</span>}<span className="fh-highlight-match">{h.tag==='preloaded'?(zh?'预载精彩片段':'Preloaded'):h.club_ids.map(id=>ctx.world.catalog.clubs.find(c=>c.club_id===id)?.name??id).join(' × ')}</span></div><div className="fh-highlight-copy"><small>{h.date?dateLabel(h.date,zh):zh?'精彩片段':'HIGHLIGHT'}</small><h3>{h.title}</h3><p>{h.relevance.reason}</p><span>{zh?'观看回放':'Watch highlight'} ↗</span></div></>
    return h.action.replay_url?<button className="fh-highlight-card" key={h.highlight_id} onClick={()=>ctx.watch(h)}>{content}</button>:<a className="fh-highlight-card" key={h.highlight_id} href={`?story=${encodeURIComponent(h.action.scenario_id??h.highlight_id)}${h.match_id?`&match=${encodeURIComponent(h.match_id)}`:''}#matchday`}>{content}</a>
  })}</div>
}
function Following(ctx:Context & {error:boolean;retry:()=>void}){
  const zh=ctx.prefs.language==='zh-Hans',t=(en:string,cn:string)=>zh?cn:en
  if(ctx.error)return <Failure retry={ctx.retry}/>
  if(!ctx.home)return <Loading/>
  const {following}=ctx.home
  return <><div className="fh-section-head fh-spaced"><div><p className="fh-eyebrow">{t('YOUR CLUBS & PLAYERS','你关注的俱乐部与球员')}</p><h2>{t('Following','关注动态')}</h2></div><Scope ctx={ctx}/></div>
    {!following.players.length&&!following.clubs.length?<div className="fh-welcome"><span>♡</span><div><h2>{t('Start with a favorite.','从你喜欢的球员开始。')}</h2><p>{t('Follow players and clubs to keep their form and highlights together.','关注球员和俱乐部，集中查看状态和精彩片段。')}</p></div><a href="#football/players" className="fh-button">{t('Find players','寻找球员')} →</a></div>:<>
      <div className="fh-following-grid">{following.players.map(({player,tiles,cards})=><article className="fh-following-card" key={player.player_id} style={clubStyle(ctx.world.catalog.clubs.find(c=>c.club_id===player.club_id))}><div className="fh-section-head"><a href={`#football/player/${player.player_id}`}><span className="fh-eyebrow">{roleName(player.role,zh)}</span><h3>{player.name} ↗</h3></a><Follow active name={player.name} onClick={()=>ctx.follow('player',player.player_id)}/></div><Tiles tiles={tiles.slice(0,3)}/>{cards.at(-1)&&<p>{cards.at(-1)!.text}</p>}</article>)}</div>
      {following.clubs.length>0&&<div className="fh-following-clubs">{following.clubs.map(({club,record})=><div key={club.club_id}><a href={`#football/club/${club.club_id}`}><Badge club={club}/><span><strong>{club.name}</strong><small>{record.wins} W · {record.draws} D · {record.losses} L</small></span></a><button className="fh-link" onClick={()=>ctx.update({...ctx.prefs,primary_club_id:club.club_id})} aria-pressed={ctx.prefs.primary_club_id===club.club_id}>{ctx.prefs.primary_club_id===club.club_id?t('Your club ✓','你的主队 ✓'):t('Make my club','设为主队')}</button><Follow active name={club.name} onClick={()=>ctx.follow('club',club.club_id)}/></div>)}</div>}
    </>}
    <div className="fh-section-head fh-spaced"><h2>{t('Highlights for you','为你推荐的精彩片段')}</h2><span>{t('From across the grounds','来自各个球场')}</span></div><Highlights items={ctx.home.highlights} ctx={ctx}/>
  </>
}

function Profile(ctx:Context & {kind:'player'|'club';id:string}){
  const {kind,id,prefs,world,season}=ctx
  const [section,setSection]=useState<'overview'|'history'|'seasons'>('overview')
  const zh=prefs.language==='zh-Hans',t=(en:string,cn:string)=>zh?cn:en
  const view=useFan<ProfileView>(`profile:${kind}:${id}:${contextKey(prefs,season)}`,client=>client[kind](id,prefs,{as_of:world.asOf,...(season?{season}:{})}))
  const entity=kind==='player'?world.players.find(p=>p.player_id===id):world.catalog.clubs.find(c=>c.club_id===id)
  if(!entity)return <div className="fh-empty"><h2>{t('Profile not found','未找到资料')}</h2><a href="#football/players">{t('Browse players','浏览球员')}</a></div>
  const player=kind==='player'?entity as Player:null,club=world.catalog.clubs.find(c=>c.club_id===entity.club_id)!
  const favorite=(kind==='player'?prefs.favorite_player_ids:prefs.favorite_club_ids).includes(id)
  const clips=ctx.home?.highlights.filter(h=>kind==='player'?h.player_ids.includes(id):h.club_ids.includes(id))??[]
  const action=(a:{kind:string;season?:string})=>{if(a.season){ctx.setSeason(a.season);setSection('history')}else setSection(a.kind==='profile'?'seasons':'history')}
  return <div className="fh-profile" style={clubStyle(club)}><a className="fh-back" href={`#football/${kind==='player'?'players':'clubs'}`}>← {t(kind==='player'?'All players':'All clubs',kind==='player'?'所有球员':'所有俱乐部')}</a>
    <div className="fh-profile-hero"><div className="fh-profile-heading"><a className="fh-profile-club" href={`#football/club/${club.club_id}`}><Badge club={club}/>{club.name}</a><p className="fh-eyebrow">{player?`${roleName(player.role,zh)} / #${player.number}`:t('CLUB PROFILE','俱乐部档案')}</p><h2>{entity.name}</h2><p>{player?`${t('Born','出生于')} ${player.birth_year} · ${t('Career since','生涯始于')} ${player.debut_year}`:t('Squad, form & club history','阵容、状态与俱乐部历史')}</p><div className="fh-profile-actions"><AskFootie context={{label:entity.name,question:player?`How many ${{GK:'saves',DF:'duels won',MF:'assists',FW:'goals'}[player.role]} does ${entity.name} have?`:`Who leads ${entity.name} in assists?`,...(player?{playerId:id}:{clubId:id}),season,asOf:world.asOf}}/><Follow active={favorite} name={entity.name} onClick={()=>ctx.follow(kind,id)}/>{player?<button className="fh-outline" aria-pressed={ctx.compareIds.includes(id)} onClick={()=>ctx.toggleCompare(id)}>{ctx.compareIds.includes(id)?'✓ ':''}{t('Compare player','对比球员')} ⇄</button>:favorite&&<button className="fh-outline" onClick={()=>ctx.update({...prefs,primary_club_id:id})}>{prefs.primary_club_id===id?t('Your club ✓','你的主队 ✓'):t('Make my club','设为主队')}</button>}</div></div><div className="fh-profile-art">{player?<Shirt player={player} club={club} profile/>:<Badge club={club}/>}</div></div>
    <div className="fh-profile-toolbar"><nav aria-label="Profile sections">{(['overview','history','seasons'] as const).map(s=><button key={s} aria-pressed={section===s} onClick={()=>setSection(s)}>{s==='overview'?t('Overview','概览'):s==='history'?t('Match history','比赛历史'):t('Seasons','赛季')}</button>)}</nav><Scope ctx={ctx}/><label className="fh-scope">{t('Focus','关注指标')}<select aria-label="Metric focus" value={prefs.metric_focus} onChange={e=>ctx.update({...prefs,metric_focus:e.target.value as FanPreferences['metric_focus']})}>{([['balanced','All-round','全面'],['scoring','Scoring','进球'],['creating','Creating','创造机会'],['passing','Passing','传球'],['defending','Defending','防守']] as const).map(([v,en,cn])=><option key={v} value={v}>{t(en,cn)}</option>)}</select></label></div>
    {view.error?<Failure retry={view.retry}/>:!view.data?<Loading/>:<>
      <Tiles tiles={view.data.presentation.tiles}/>
      {view.data.profile.record&&<div className="fh-record">{Object.entries(view.data.profile.record).map(([k,v])=><span key={k}><strong>{v}</strong> {k==='wins'?t('Wins','胜'):k==='draws'?t('Draws','平'):t('Losses','负')}</span>)}</div>}
      {section==='history'?<HistoryList key={`${id}:${season}`} {...ctx}/>:section==='seasons'?<Seasons view={view.data} ctx={ctx}/>:<>
        <>{player&&<PlayerInsights key={`${id}:${season}`} playerId={id} season={season} before={world.asOf} clubs={world.catalog.clubs} zh={zh}/>}</><div className={player?"fh-profile-stories":"fh-profile-grid"}>{!player&&<ActivityMap map={view.data.presentation.activity_map} zh={zh}/>}<section className="fh-stories"><div className="fh-section-head"><div><p className="fh-eyebrow">{t('THE STORY IN THE NUMBERS','数字背后的故事')}</p><h2>{t('Worth knowing','值得关注')}</h2></div></div>{view.data.presentation.cards.map(card=><article key={card.id}><small>{card.title}</small><h3>{card.text}</h3><button className="fh-link" onClick={()=>action(card.action)}>{card.action.label} →</button></article>)}{view.data.presentation.questions.map(q=><button className="fh-question" key={q.id} onClick={()=>action(q.action)}>{q.text}<span>↗</span></button>)}</section></div>
        {kind==='club'&&<><div className="fh-section-head fh-spaced"><h2>{t('The squad','球队阵容')}</h2></div><div className="fh-player-grid">{world.players.filter(p=>p.club_id===id&&p.featured).map(p=><PlayerCard key={p.player_id} player={p} ctx={ctx}/>)}</div></>}
        {clips.length>0&&<><div className="fh-section-head fh-spaced"><h2>{t('In the highlights','精彩时刻')}</h2></div><Highlights items={clips} ctx={ctx}/></>}
      </>}
    </>}
  </div>
}
function Seasons({view,ctx}:{view:ProfileView;ctx:Context}){
  const seasons=[...view.profile.seasons].reverse(),max=Math.max(1,...seasons.map(s=>s.totals.goals??0)),zh=ctx.prefs.language==='zh-Hans'
  return <section className="fh-panel fh-seasons"><div className="fh-section-head"><div><p className="fh-eyebrow">{zh?'生涯趋势':'CAREER TREND'}</p><h2>{zh?'每个赛季的进球':'Goals, season by season'}</h2></div><span>{zh?'点击赛季查看':'Choose a season to explore'}</span></div><div className="fh-season-chart">{seasons.map(s=><button key={s.season} onClick={()=>ctx.setSeason(s.season)} aria-label={`${s.season}: ${s.totals.goals} goals`}><span>{s.totals.goals}</span><i style={{height:`${Math.max(2,(s.totals.goals??0)/max*150)}px`}}/><small>{s.season}</small></button>)}</div><div className="fh-table-wrap"><table><caption className="sr-only">Season statistics</caption><thead><tr><th>{zh?'赛季':'Season'}</th><th>{zh?'出场':'Matches'}</th><th>{zh?'进球':'Goals'}</th><th>{zh?'分钟':'Minutes'}</th><th>{zh?'传球成功率':'Pass completion'}</th></tr></thead><tbody>{view.profile.seasons.map(s=><tr key={s.season}><th scope="row"><button className="fh-link" onClick={()=>ctx.setSeason(s.season)}>{s.season}</button></th><td>{s.totals.appearances}</td><td>{s.totals.goals}</td><td>{Math.round(s.totals.minutes??0).toLocaleString()}</td><td>{s.rates.pass_accuracy_pct===null?'—':`${s.rates.pass_accuracy_pct?.toFixed(1)}%`}</td></tr>)}</tbody></table></div></section>
}
function HistoryList(ctx:Context & {kind:'player'|'club';id:string}){
  const [offset,setOffset]=useState(0),[selected,setSelected]=useState<string|null>(null)
  const params=new URLSearchParams({offset:String(offset),limit:'10',...(ctx.season?{season:ctx.season}:{}),...(ctx.kind==='player'?{before:ctx.world.asOf}:{})})
  const history=useResource<History>(`history:${ctx.kind}:${ctx.id}:${params}`,signal=>getData(`/api/data/${ctx.kind==='player'?'players':'clubs'}/${ctx.id}/matches?${params}`,signal))
  const zh=ctx.prefs.language==='zh-Hans',t=(en:string,cn:string)=>zh?cn:en
  const club=(id:string)=>ctx.world.catalog.clubs.find(c=>c.club_id===id)?.name??id
  if(history.error)return <Failure retry={history.retry}/>
  if(!history.data)return <Loading/>
  return <section className="fh-history"><div className="fh-section-head"><h2>{t('Match history','比赛历史')}</h2><span>{history.data.total} {t('matches','场比赛')}</span></div>{history.data.items.length===0&&<p className="fh-muted">{t('No appearances in this period.','此时间范围内暂无出场记录。')}</p>}
    {history.data.items.map(match=><article className="fh-history-row" key={match.match_id}><button className="fh-match-summary" aria-expanded={selected===match.match_id} onClick={()=>setSelected(selected===match.match_id?null:match.match_id)}><time>{dateLabel(match.kickoff,zh)}<small>{match.competition}</small></time><span className="fh-match-teams"><span>{club(match.home_id)}</span><strong>{match.score[match.home_id]} <em>–</em> {match.score[match.away_id]}</strong><span>{club(match.away_id)}</span></span><span className="fh-match-form">{match.stats?`${match.stats.goals??0} ${t('goals','进球')} · ${Math.round(match.stats.minutes??0)} ${t('min','分钟')}`:match.season}</span><span>{selected===match.match_id?'−':'+'}</span></button>{selected===match.match_id&&<HistoryDetail match={match} ctx={ctx}/>}</article>)}
    <div className="fh-pagination"><button className="fh-outline" disabled={offset===0} onClick={()=>{setOffset(Math.max(0,offset-10));setSelected(null)}}>{t('Previous','上一页')}</button><span>{history.data.total?offset+1:0}–{Math.min(offset+10,history.data.total)} / {history.data.total}</span><button className="fh-outline" disabled={offset+10>=history.data.total} onClick={()=>{setOffset(offset+10);setSelected(null)}}>{t('Next','下一页')}</button></div>
  </section>
}
function HistoryDetail({match,ctx}:{match:Match;ctx:Context}){
  const clips=ctx.home?.highlights.filter(h=>h.match_id===match.match_id)??[]
  return <div className="fh-history-detail">{match.stats&&<dl>{[['goals','Goals'],['shots','Shots'],['passes_completed','Completed passes'],['duels_won','Challenges won']].map(([key,label])=><div key={key}><dt>{label}</dt><dd>{match.stats![key]??'—'}</dd></div>)}</dl>}{clips.map(h=><button key={h.highlight_id} className="fh-link" onClick={()=>h.action.replay_url?ctx.watch(h):window.location.assign(`?story=${h.action.scenario_id??h.highlight_id}#matchday`)}>▶ {h.title}</button>)}{match.featured&&!clips.length&&match.match_id!=='career-showcase-southbank-redhaven'&&<a className="fh-link" href={`?match=${encodeURIComponent(match.match_id)}#gi`}>Open Match Centre ↗</a>}</div>
}
function Comparison(ctx:Context){
  const zh=ctx.prefs.language==='zh-Hans',t=(en:string,cn:string)=>zh?cn:en
  return <><div className="fh-section-head fh-spaced"><div><p className="fh-eyebrow">{t('SIDE BY SIDE','并排对比')}</p><h2>{t('Player comparison','球员对比')}</h2></div><Scope ctx={ctx}/></div><div className="fh-compare-selectors">{ctx.compareIds.map(id=>{const p=ctx.world.players.find(p=>p.player_id===id)!;const club=ctx.world.catalog.clubs.find(c=>c.club_id===p.club_id)!;return <div key={id} style={clubStyle(club)}><Badge club={club}/><a href={`#football/player/${id}`}><strong>{p.name}</strong><small>{club.name} · {roleName(p.role,zh)}</small></a><button aria-label={`Remove ${p.name} from comparison`} onClick={()=>ctx.toggleCompare(id)}>×</button></div>})}{ctx.compareIds.length<4&&<label>{t('Add a player','添加球员')}<select aria-label="Add a player to compare" value="" onChange={e=>{if(e.target.value)ctx.toggleCompare(e.target.value)}}><option value="">{t('Choose player…','选择球员…')}</option>{ctx.world.players.filter(p=>p.featured&&!ctx.compareIds.includes(p.player_id)).sort((a,b)=>a.name.localeCompare(b.name)).map(p=><option key={p.player_id} value={p.player_id}>{p.name} · {ctx.world.catalog.clubs.find(c=>c.club_id===p.club_id)?.name}</option>)}</select></label>}</div>
    {ctx.compareIds.length<2?<div className="fh-empty"><span className="fh-empty-icon">⇄</span><h2>{t('Who are you comparing?','你想对比谁？')}</h2><p>{t('Choose two to four players to compare their numbers over the same period.','选择两到四位球员，对比同一时期的表现。')}</p><a className="fh-button" href="#football/players">{t('Browse players','浏览球员')} →</a></div>:<ComparisonResults {...ctx}/>}
  </>
}
function ComparisonResults(ctx:Context){
  const view=useFan<CompareView>(`compare:${ctx.compareIds.join(',')}:${contextKey(ctx.prefs,ctx.season)}`,client=>client.compare(ctx.compareIds,ctx.prefs,{as_of:ctx.world.asOf,...(ctx.season?{season:ctx.season}:{})}))
  const zh=ctx.prefs.language==='zh-Hans'
  if(view.error)return <Failure retry={view.retry}/>
  if(!view.data)return <Loading/>
  return <section className="fh-panel fh-comparison" style={{'--fh-compare-cols':view.data.players.length} as CSSProperties}>{!view.data.same_role&&<p className="fh-muted">{zh?'这些球员的位置不同，结合各自职责看待数据。':'These players play different positions. Read their numbers alongside their roles.'}</p>}{!view.data.rate_comparison_available&&<p className="fh-muted">{zh?'每位球员至少出场180分钟后，才显示每90分钟的对比。':'Per-90 comparisons appear once each player has played 180 minutes.'}</p>}<div className="fh-comparison-head"><span>{zh?'指标':'Metric'}</span>{view.data.players.map(p=><strong key={p.player_id}>{p.name}</strong>)}</div>{view.data.metrics.map(metric=>{
    const maximum=Math.max(1,...Object.values(metric.values).map(v=>v.value??0))
    return <div className="fh-comparison-row" key={metric.metric}><span>{metric.label}</span>{view.data!.players.map(p=>{const tile=metric.values[p.player_id],hidden=tile.unit==='per90'&&!view.data!.rate_comparison_available;return <div key={p.player_id} style={clubStyle(ctx.world.catalog.clubs.find(c=>c.club_id===p.club_id))}><strong>{hidden?'—':tileValue(tile)}</strong><i><span style={{width:`${hidden||tile.value===null?0:tile.value/maximum*100}%`}}/></i>{tile.value===null&&<small>{zh?'暂无数据':'Not available'}</small>}</div>})}</div>
  })}</section>
}
