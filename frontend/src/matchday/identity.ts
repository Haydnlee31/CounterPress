/** Original display identities only. No real-club marks or player likenesses. */
export const clubs = {
  eastbridge: { name: 'Eastbridge', initials: 'EB', accent: '#e7c771', ink: '#163c32', background: '#e6eee7', soft: '#d8e6d8' },
  northport: { name: 'Northport', initials: 'NP', accent: '#c3e4ff', ink: '#183d64', background: '#e6edf5', soft: '#d8e5f3' },
} as const
const players: Record<string, string> = {
  eb04: 'Alex Rowan',
  eb06: 'Jamie Vale',
  eb08: 'Kai Mercer',
  eb09: 'Rory Ellis',
  np04: 'Noah Arden',
  np06: 'Sam Linden',
  np08: 'Leo Marlow',
  eb01: 'Theo Ashford', eb02: 'Finn Brooks', eb03: 'Oliver Hayes', eb05: 'Elliot Reed',
  eb07: 'Lucas Hart', eb10: 'Milo West', eb11: 'Owen Cole',
  np01: 'Arthur Wells', np02: 'Ben Fletcher', np03: 'Callum Stone', np05: 'Dylan Frost',
  np07: 'Evan Shore', np09: 'Henry Blake', np10: 'Isaac Lane', np11: 'Jude Rivers',
}
// A full visual cast for the replay. Only the original event actors are followable.
export const squads = Object.keys(clubs).flatMap(team_id => Array.from({length:11}, (_, i) => ({
  team_id, player_id: `${team_id === 'eastbridge' ? 'eb' : 'np'}${String(i+1).padStart(2,'0')}`, number: i+1,
})))
const recordedPlayers = new Set(['eb04','eb06','eb08','eb09','np04','np06','np08'])
export const initials = (id: string) => playerName(id).split(' ').map(n => n[0]).join('').slice(0,2)
export const playerName = (id: string) => players[id] ?? id
export const knownPlayer = (id: unknown): id is string =>
  typeof id === 'string' && recordedPlayers.has(id)
export const clubName = (id: string) =>
  clubs[id as keyof typeof clubs]?.name ?? id
export const displayText = (text: string) =>
  text.replace(/\b(?:eb|np)\d{2}\b/g, playerName)
