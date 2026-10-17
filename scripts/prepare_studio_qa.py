"""Create an ignored, local-only UI fixture. Never included in the production build."""
from pathlib import Path
from counterpress.api.snapshots import SnapshotService
from counterpress.studio.service import StudioService, ReviewRequest
from counterpress.audience import ViewingPreferences

ROOT = Path(__file__).resolve().parents[1]
target = ROOT / 'frontend/var'
target.mkdir(exist_ok=True)
view = StudioService(SnapshotService(ROOT/'fixtures')).review('increase', ReviewRequest(preferences=ViewingPreferences(depth='casual')))
(target/'studio-review.json').write_text(view.model_dump_json())
(target/'studio-qa.html').write_text('''<!doctype html><html><meta name="viewport" content="width=device-width,initial-scale=1"><body style="margin:0"><div id="root"></div><script type="module" src="/var/studio-qa.tsx"></script></body></html>''')
(target/'studio-qa.tsx').write_text('''import React from 'react'
import { createRoot } from 'react-dom/client'
import Studio from '../src/studio/Studio'
import '../src/styles.css'
import review from './studio-review.json'
let current = review
const session = { async signIn() {}, async signOut() {}, async call(action) {
 if (action === 'approve') current = {...current, status:'approved', approval_id:'qa-approval'}
 if (action === 'revoke') current = {...current, status:'revoked', approval_id:null}
 return current
}, async download() { return new Blob(['QA snapshot']) } }
const factory = async () => session
createRoot(document.getElementById('root')).render(<Studio sessionFactory={factory}/>)
''')
print('PASS prepared local Studio fixture; authentication is mocked, no Azure configuration used.')
