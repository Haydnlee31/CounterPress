import {createHash} from 'node:crypto'
import {readFileSync} from 'node:fs'
import {fileURLToPath} from 'node:url'
import {dirname,resolve} from 'node:path'
import {expect,it} from 'vitest'
import {playerPortraits,pitchPortraits,largePortraits,portraitSrcSet} from './portraits'

it('assigns one distinct saved portrait to every featured registry player',()=>{
  const root=resolve(dirname(fileURLToPath(import.meta.url)),'../../..')
  const registry=JSON.parse(readFileSync(resolve(root,'fixtures/personalization/registry.json'),'utf8'))
  const prompts=JSON.parse(readFileSync(resolve(root,'docs/player-portrait-prompts.json'),'utf8')) as {player_id:string;asset:string}[]
  const featured=registry.players.filter((p:{featured:boolean})=>p.featured).map((p:{player_id:string})=>p.player_id).sort()
  expect(featured).toHaveLength(44)
  expect(Object.keys(playerPortraits).sort()).toEqual(featured)
  expect(prompts.map(p=>p.player_id).sort()).toEqual(featured)
  const hashes=prompts.map(p=>{
    expect(playerPortraits[p.player_id]).toContain(`${p.player_id}-portrait-v1-384.webp`)
    expect(p.asset).toBe(`frontend/src/football/portraits/${p.player_id}-portrait-v1.jpg`)
    const image=readFileSync(resolve(root,p.asset))
    expect([...image.subarray(0,3)]).toEqual([255,216,255])
    return createHash('sha256').update(image).digest('hex')
  })
  expect(new Set(hashes).size).toBe(44)
  for(const [size,variants] of [[256,pitchPortraits],[384,playerPortraits],[768,largePortraits]] as const){
    expect(Object.keys(variants).sort()).toEqual(featured)
    for(const id of featured){
      const filename=`${id}-portrait-v1-${size}.webp`
      expect(variants[id]).toContain(filename)
      const image=readFileSync(resolve(root,'frontend/src/football/portraits',filename))
      expect(image.toString('ascii',8,12)).toBe('WEBP')
      // Prevent accidentally shipping the large master for a tiny moving face.
      expect(image.length).toBeLessThan(size===256?12000:size===384?25000:100000)
      expect(portraitSrcSet(id)).toContain(`${variants[id]} ${size}w`)
    }
  }
  expect(portraitSrcSet('unknown-player')).toBeUndefined()
})
