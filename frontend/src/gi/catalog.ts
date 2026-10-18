export const matchLibrary=[
  {id:'wyscout-2058017',score:'4 – 2',title:'Six goals. Eastbridge take it.'},
  {id:'wyscout-2058007',score:'3 – 2',title:'Back from two down.'},
] as const
export function currentMatchId() {
  const candidate=new URLSearchParams(window.location.search).get('match')
  return matchLibrary.find(m=>m.id===candidate)?.id??matchLibrary[0].id
}
