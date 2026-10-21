import {useState} from 'react'
import {dateLabel,getData,useResource} from './data'
import type {World} from './data'
import {Badge} from './visuals'
import './standings.css'
type Row={rank:number;club_id:string;played:number;wins:number;draws:number;losses:number;goals_for:number;goals_against:number;points:number}
type Table={season:string;competition:string;items:Row[];match_ids:string[]}
export function Standings({world}:{world:World}){
  const [season,setSeason]=useState(world.catalog.seasons[0]),[allColumns,setAllColumns]=useState(false)
  const table=useResource(`standings:${season}`,signal=>getData<Table>(`/api/data/standings/${encodeURIComponent(season)}`,signal))
  const club=(id:string)=>world.catalog.clubs.find(c=>c.club_id===id)
  const leader=table.data?.items[0]
  return <section className="league" aria-labelledby="league-title"><header className="league-heading"><div><p className="fh-eyebrow">THE SEASON</p><h2 id="league-title">The race for the top.</h2><p>League standings · results through {dateLabel(world.throughDate)}</p></div><label>Season <select aria-label="Standings season" value={season} onChange={e=>setSeason(e.target.value)}>{world.catalog.seasons.map(s=><option key={s}>{s}</option>)}</select></label></header>
    {table.error?<div role="alert">The table couldn’t be loaded. <button onClick={table.retry}>Try again</button></div>:!table.data?<p role="status">Loading the league table…</p>:<>
      <div className="league-featured">{table.data.items.filter(r=>club(r.club_id)?.featured).map(r=><a key={r.club_id} href={`#football/club/${r.club_id}`}><span className="league-position">{r.rank}<small>PLACE</small></span><Badge club={club(r.club_id)!}/><div><strong>{club(r.club_id)?.name}</strong><span>{r.points} points · {r.played} played</span><small>{r.rank===1?'Setting the pace':`${(leader?.points??r.points)-r.points} points off the lead`}</small></div><b aria-hidden="true">↗</b></a>)}</div>
      <button className="league-columns" aria-pressed={allColumns} onClick={()=>setAllColumns(!allColumns)}>{allColumns?'Compact table':'Show all columns'}</button>
      <div className={`league-table-wrap ${allColumns?'all-columns':'compact-columns'}`} role="region" aria-label={allColumns?'League table, scroll horizontally for all columns':'League standings'} tabIndex={0}><table className="league-table"><caption>{table.data.competition} · {season}</caption><thead><tr><th scope="col">Pos</th><th scope="col">Club</th><th scope="col"><abbr title="Played">P</abbr></th><th scope="col"><abbr title="Won">W</abbr></th><th scope="col"><abbr title="Drawn">D</abbr></th><th scope="col"><abbr title="Lost">L</abbr></th><th scope="col"><abbr title="Goals for">GF</abbr></th><th scope="col"><abbr title="Goals against">GA</abbr></th><th scope="col"><abbr title="Goal difference">GD</abbr></th><th scope="col"><abbr title="Points">Pts</abbr></th></tr></thead><tbody>{table.data.items.map(r=><tr key={r.club_id} data-featured={club(r.club_id)?.featured}><td>{r.rank}</td><th scope="row"><a href={`#football/club/${r.club_id}`}>{club(r.club_id)?.name??r.club_id}</a></th><td>{r.played}</td><td>{r.wins}</td><td>{r.draws}</td><td>{r.losses}</td><td>{r.goals_for}</td><td>{r.goals_against}</td><td>{r.goals_for-r.goals_against>0?'+':''}{r.goals_for-r.goals_against}</td><td><strong>{r.points}</strong></td></tr>)}</tbody></table></div>
      <p className="league-rules">3 points for a win, 1 for a draw. Ordered by points, goal difference, then goals scored. Cup matches are separate.</p>
    </>}
  </section>
}
