"""Validate a dataset-pinned career delivery; send only with explicit --send."""
import argparse
import asyncio
from pathlib import Path
from counterpress.personalization.store import DataStore
from counterpress.streaming.contracts import CareerDelivery, MAX_DELIVERY_BYTES
from counterpress.streaming.send import send


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('delivery',type=Path)
    parser.add_argument('--fixtures',type=Path,default=Path('fixtures'))
    parser.add_argument('--send',action='store_true')
    args=parser.parse_args()
    store=None
    try:
        raw=args.delivery.read_bytes()
        if len(raw)>MAX_DELIVERY_BYTES:raise ValueError('Oversize delivery')
        delivery=CareerDelivery.model_validate_json(raw)
        store=DataStore(args.fixtures/'personalization')
        if delivery.dataset!=store.dataset:raise ValueError('Wrong dataset')
        # Local preflight checks canonical roster, clocks and revision identity.
        # The consumer additionally checks against all durably received revisions.
        store.ingest(delivery.match_id,delivery.events)
        if args.send:
            asyncio.run(send(delivery))
            print('Delivery accepted by Event Hubs; consumer validation and commit are asynchronous.')
        else:
            print('Career delivery validated against the local dataset. No cloud calls made.')
    except Exception:
        parser.exit(2,'Career delivery failed; check the dataset, event contract and private sender configuration.\n')
    finally:
        if store:store.close()


if __name__=='__main__':main()
