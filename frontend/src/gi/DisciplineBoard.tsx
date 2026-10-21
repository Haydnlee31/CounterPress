import type {GIMatch,GIEvent} from './data'
import {matchClock} from './data'
import {cardType,discipline} from './discipline'
export function DisciplineBoard({match,names,inspect}:{match:GIMatch;names:Map<string,string>;inspect:(event:GIEvent)=>void}){
  const {cards,players}=discipline(match.events)
  const yellow=players.reduce((n,p)=>n+p.yellows,0),red=players.filter(p=>p.sentOff).length
  return <section className="gi-discipline" aria-labelledby="discipline-title"><header><div><p className="fan-kicker">DISCIPLINE</p><h2 id="discipline-title">Bookings & send-offs</h2></div><div className="gi-card-count"><span><i className="card-yellow"/>{match.synthetic?'—':yellow} bookings</span><span><i className="card-red"/>{match.synthetic?'—':red} sent off</span></div></header>
    {!cards.length?<p>{match.synthetic?'Cards were not recorded for this match.':'No cards recorded in this match.'}</p>:<div className="gi-bookings">{players.map(p=><button key={p.player_id} onClick={()=>inspect(p.event)}><span className="gi-booking-icon"><i className={p.sentOff?'card-red':'card-yellow'}/>{p.yellows>1&&<i className="card-yellow"/>}</span><span><strong>{names.get(p.player_id)??'Player'}</strong><small>{p.sentOff?cardType(p.event)==='red'?'Red card · sent off':'Second booking · sent off':'Booked · on a yellow in this match'}</small>{p.sentOff&&<small>Future suspension: awaiting a recorded decision</small>}</span><time>{matchClock(p.event)}</time><span aria-hidden="true">↗</span></button>)}</div>}
  </section>
}
