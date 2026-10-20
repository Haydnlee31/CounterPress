"""Materialize event-derived analytics without rebuilding or changing career data."""
import argparse
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import gzip
import json
from hashlib import sha256
from counterpress.personalization.store import DataStore
from counterpress.personalization import analytics


def batch(args):
    root,ids,unreviewed=args
    store=DataStore(root,allow_unreviewed_spatial=unreviewed)
    try:
        result={}
        for mid in ids:
            row=store.row(mid);record=store.original(mid)
            result[mid]={'digest':row['digest'],'players':analytics.derive(record,json.loads(row['summary']))}
        return result
    finally:store.close()


def main():
    root=Path(__file__).resolve().parents[1]
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixtures',type=Path,default=root/'fixtures/personalization')
    parser.add_argument('--output',type=Path,default=root/'fixtures/analytics')
    parser.add_argument('--workers',type=int,default=4)
    parser.add_argument('--review-unvalidated',action='store_true',help='Build a staged analytics artifact for an expanded spatial audit; does not authorize app use')
    args=parser.parse_args()
    store=DataStore(args.fixtures,allow_unreviewed_spatial=args.review_unvalidated)
    try:
        ids=[r['id'] for r in store.rows()];matches={}
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            for part in pool.map(batch,[(args.fixtures,ids[i:i+100],args.review_unvalidated) for i in range(0,len(ids),100)]):
                matches.update(part);print(f'Indexed {len(matches)} matches',flush=True)
        result={'version':analytics.VERSION,'ledger_sha256':store.manifest['files']['ledger.json.gz'],
                'reducer_sha256':sha256(Path(analytics.__file__).read_bytes()).hexdigest(),'matches':matches}
        target=args.output;target.mkdir(parents=True,exist_ok=True)
        raw=gzip.compress(json.dumps(result,separators=(',',':'),sort_keys=True).encode(),mtime=0)
        (target/'players.json.gz').write_bytes(raw)
        (target/'manifest.json').write_text(json.dumps({'version':result['version'],'sha256':sha256(raw).hexdigest(),
            'ledger_sha256':result['ledger_sha256'],'matches':len(matches)},indent=2)+'\n')
        print(json.dumps({'status':'built','matches':len(matches),'compressed_bytes':len(raw)}))
    finally:store.close()

if __name__=='__main__':main()
