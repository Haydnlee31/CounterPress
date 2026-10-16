/** Original display identities only. No real-club marks or player likenesses. */
export const clubs = {
  eastbridge: { name: 'Eastbridge', initials: 'EB', accent: '#c4ed91' },
  northport: { name: 'Northport', initials: 'NP', accent: '#a6d9f5' },
} as const
const players: Record<string, string> = {
  eb04: 'Alex Rowan',
  eb06: 'Jamie Vale',
  eb08: 'Kai Mercer',
  eb09: 'Rory Ellis',
  np04: 'Noah Arden',
  np06: 'Sam Linden',
  np08: 'Leo Marlow',
}
export const playerName = (id: string) => players[id] ?? id
export const knownPlayer = (id: unknown): id is string =>
  typeof id === 'string' && Object.hasOwn(players, id)
export const clubName = (id: string) =>
  clubs[id as keyof typeof clubs]?.name ?? id
export const displayText = (text: string) =>
  text.replace(/\b(?:eb|np)\d{2}\b/g, playerName)
