export const matchLibrary=[
  {id:'wyscout-2058017',date:'2026-10-16',score:'4 – 2',title:'Six goals. Eastbridge take it.'},
  {id:'synthetic-32fe41c5d304ce68d7d9',date:'2026-10-18',score:'2 – 2',title:'Level again at 75′.'},
  {id:'wyscout-2058007',date:'2026-10-17',score:'3 – 2',title:'Back from two down.'},
] as const
export function currentMatchId() {
  const candidate=new URLSearchParams(window.location.search).get('match')
  return matchLibrary.find(m=>m.id===candidate)?.id??matchLibrary[0].id
}

export const matchDate=(date:string)=>new Date(`${date}T12:00:00Z`).toLocaleDateString('en-GB',{day:'numeric',month:'short',year:'numeric',timeZone:'UTC'})
