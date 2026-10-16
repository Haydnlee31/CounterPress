import { afterEach, describe, expect, it, vi } from 'vitest'
import { subscribeRevisions } from './revisions'
class Socket {
  static all: Socket[] = []
  onopen: (() => void) | null = null
  onmessage: ((e: {data: string}) => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null
  close = vi.fn()
  constructor(public url: string) { Socket.all.push(this) }
}
async function settle() { for (let i = 0; i < 6; i++) await Promise.resolve() }
const config = () => Promise.resolve({ ok: true, json: async () => ({ enabled: true, url: 'wss://test.webpubsub.azure.com/client?access_token=short-lived' }) })
function message(version: number, scenario = 'increase') {
  return {data: JSON.stringify({type:'history.changed',schema_version:1,scenario_id:scenario,match_id:'match',history_version:version,replay_end:{period:2,elapsed_ms:795000},revisions:[]})}
}
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); Socket.all=[] })
describe('revision transport', () => {
  it('resyncs on connect and deduplicates notices without applying their facts', async () => {
    vi.stubGlobal('fetch',vi.fn(config));vi.stubGlobal('WebSocket',Socket)
    const refresh=vi.fn(), status=vi.fn(), stop=subscribeRevisions('increase',refresh,status)
    await settle();const ws=Socket.all[0];ws.onopen!()
    expect(refresh).toHaveBeenCalledTimes(1)
    ws.onmessage!(message(93));ws.onmessage!(message(93));ws.onmessage!(message(92));ws.onmessage!(message(94,'control'))
    ws.onmessage!({data:'invalid'})
    expect(refresh).toHaveBeenCalledTimes(2)
    expect(status).toHaveBeenLastCalledWith('connected')
    stop();expect(ws.close).toHaveBeenCalledOnce()
    ws.onmessage!(message(95));expect(refresh).toHaveBeenCalledTimes(2)
  })
  it('reconnects and requests a full snapshot after missed revisions', async () => {
    vi.useFakeTimers();vi.stubGlobal('fetch',vi.fn(config));vi.stubGlobal('WebSocket',Socket)
    const refresh=vi.fn(),status=vi.fn(),stop=subscribeRevisions('increase',refresh,status)
    await settle();Socket.all[0].onopen!();Socket.all[0].onclose!()
    expect(status).toHaveBeenLastCalledWith('polling')
    await vi.advanceTimersByTimeAsync(1000);await settle();Socket.all[1].onopen!()
    expect(refresh).toHaveBeenCalledTimes(2)
    stop()
  })
  it('falls back when disabled and never opens an untrusted endpoint', async () => {
    const f=vi.fn().mockResolvedValueOnce({ok:true,json:async()=>({enabled:false})})
      .mockResolvedValueOnce({ok:true,json:async()=>({enabled:true,url:'wss://attacker.example/client'})})
    vi.stubGlobal('fetch',f);vi.stubGlobal('WebSocket',Socket)
    const status=vi.fn(),stop=subscribeRevisions('increase',vi.fn(),status)
    await settle();expect(status).toHaveBeenLastCalledWith('polling');expect(Socket.all).toHaveLength(0);stop()
    const stop2=subscribeRevisions('increase',vi.fn(),status);await settle()
    expect(Socket.all).toHaveLength(0);stop2()
  })
  it('ignores a negotiated connection after the viewer changes scenario', async () => {
    let resolve!: (v: unknown) => void
    vi.stubGlobal('fetch',vi.fn(()=>new Promise(r=>{resolve=r})));vi.stubGlobal('WebSocket',Socket)
    const stop=subscribeRevisions('increase',vi.fn(),vi.fn());stop()
    resolve(await config());await settle();expect(Socket.all).toHaveLength(0)
  })
})
