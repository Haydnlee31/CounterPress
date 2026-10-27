import type {Snapshot} from './data'
export function PlayerOptions({snapshot,prefix=''}:{snapshot:Snapshot;prefix?:string}){
  return <>{snapshot.clubs.map(club=><optgroup key={club.club_id} label={club.name}>{snapshot.players.filter(p=>p.club_id===club.club_id).map(p=><option key={p.player_id} value={prefix+p.player_id}>{p.name}{p.role?` · ${p.role}`:''}</option>)}</optgroup>)}</>
}
