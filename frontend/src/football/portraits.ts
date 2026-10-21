import eb01 from './portraits/eb01-portrait-v1-384.webp'
import eb02 from './portraits/eb02-portrait-v1-384.webp'
import eb03 from './portraits/eb03-portrait-v1-384.webp'
import eb04 from './portraits/eb04-portrait-v1-384.webp'
import eb05 from './portraits/eb05-portrait-v1-384.webp'
import eb06 from './portraits/eb06-portrait-v1-384.webp'
import eb07 from './portraits/eb07-portrait-v1-384.webp'
import eb08 from './portraits/eb08-portrait-v1-384.webp'
import eb09 from './portraits/eb09-portrait-v1-384.webp'
import eb10 from './portraits/eb10-portrait-v1-384.webp'
import eb11 from './portraits/eb11-portrait-v1-384.webp'
import np01 from './portraits/np01-portrait-v1-384.webp'
import np02 from './portraits/np02-portrait-v1-384.webp'
import np03 from './portraits/np03-portrait-v1-384.webp'
import np04 from './portraits/np04-portrait-v1-384.webp'
import np05 from './portraits/np05-portrait-v1-384.webp'
import np06 from './portraits/np06-portrait-v1-384.webp'
import np07 from './portraits/np07-portrait-v1-384.webp'
import np08 from './portraits/np08-portrait-v1-384.webp'
import np09 from './portraits/np09-portrait-v1-384.webp'
import np10 from './portraits/np10-portrait-v1-384.webp'
import np11 from './portraits/np11-portrait-v1-384.webp'
import sb01 from './portraits/sb01-portrait-v1-384.webp'
import sb02 from './portraits/sb02-portrait-v1-384.webp'
import sb03 from './portraits/sb03-portrait-v1-384.webp'
import sb04 from './portraits/sb04-portrait-v1-384.webp'
import sb05 from './portraits/sb05-portrait-v1-384.webp'
import sb06 from './portraits/sb06-portrait-v1-384.webp'
import sb07 from './portraits/sb07-portrait-v1-384.webp'
import sb08 from './portraits/sb08-portrait-v1-384.webp'
import sb09 from './portraits/sb09-portrait-v1-384.webp'
import sb10 from './portraits/sb10-portrait-v1-384.webp'
import sb11 from './portraits/sb11-portrait-v1-384.webp'
import rh01 from './portraits/rh01-portrait-v1-384.webp'
import rh02 from './portraits/rh02-portrait-v1-384.webp'
import rh03 from './portraits/rh03-portrait-v1-384.webp'
import rh04 from './portraits/rh04-portrait-v1-384.webp'
import rh05 from './portraits/rh05-portrait-v1-384.webp'
import rh06 from './portraits/rh06-portrait-v1-384.webp'
import rh07 from './portraits/rh07-portrait-v1-384.webp'
import rh08 from './portraits/rh08-portrait-v1-384.webp'
import rh09 from './portraits/rh09-portrait-v1-384.webp'
import rh10 from './portraits/rh10-portrait-v1-384.webp'
import rh11 from './portraits/rh11-portrait-v1-384.webp'

// Stable registry IDs keep portraits attached to the same player across every view.
// Vite emits separate cacheable image assets; cards load them lazily.
export const playerPortraits: Readonly<Record<string, string>> = {
  eb01, // Theo Ashford
  eb02, // Finn Brooks
  eb03, // Oliver Hayes
  eb04, // Alex Rowan
  eb05, // Elliot Reed
  eb06, // Jamie Vale
  eb07, // Lucas Hart
  eb08, // Kai Mercer
  eb09, // Rory Ellis
  eb10, // Milo West
  eb11, // Owen Cole
  np01, // Arthur Wells
  np02, // Ben Fletcher
  np03, // Callum Stone
  np04, // Noah Arden
  np05, // Dylan Frost
  np06, // Sam Linden
  np07, // Evan Shore
  np08, // Leo Marlow
  np09, // Henry Blake
  np10, // Isaac Lane
  np11, // Jude Rivers
  sb01, // Leon Finch
  sb02, // Adam Keene
  sb03, // Felix Ward
  sb04, // Toby Quinn
  sb05, // Max Harlow
  sb06, // Nico Alder
  sb07, // Zane Bell
  sb08, // Remy Sutton
  sb09, // Dario Voss
  sb10, // Eli Marsh
  sb11, // Asa Hale
  rh01, // Rafael Wynn
  rh02, // Hugo Dane
  rh03, // Joel Perry
  rh04, // Luca Bennett
  rh05, // Oscar Penn
  rh06, // Ruben Silva
  rh07, // Tariq Moss
  rh08, // Enzo Clarke
  rh09, // Mateo Cross
  rh10, // Seth Nolan
  rh11, // Amir Rhodes
}

// Small textures for moving pitch markers and hover cards; larger portraits are
// chosen by the browser only when the card/profile size and pixel density need them.
function variants(size: 256 | 768): Readonly<Record<string, string>> {
  const files = size === 256
    ? import.meta.glob<string>('./portraits/*-256.webp', {eager: true, query: '?url', import: 'default'})
    : import.meta.glob<string>('./portraits/*-768.webp', {eager: true, query: '?url', import: 'default'})
  return Object.fromEntries(Object.entries(files).map(([path, url]) => [path.split('/').pop()!.split('-')[0], url]))
}
export const pitchPortraits = variants(256)
export const largePortraits = variants(768)
export const portraitSrcSet = (id: string) => playerPortraits[id]
  ? `${pitchPortraits[id]} 256w, ${playerPortraits[id]} 384w, ${largePortraits[id]} 768w`
  : undefined
