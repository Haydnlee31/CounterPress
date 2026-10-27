from concurrent.futures import ThreadPoolExecutor

from counterpress.analyst.admission import Allowance, SQLiteStore


def test_duplicate_viewers_share_one_reservation_across_instances(tmp_path):
    path = tmp_path / 'allowance.sqlite3'
    def reserve(_):
        return Allowance(SQLiteStore(path)).reserve('same-snapshot', 1000)
    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(reserve, range(5)))
    assert sum(bool(r.get('admitted')) for r in results) == 1
    assert len({r['owner'] for r in results}) == 1


def test_failed_expired_attempts_never_refund_and_lifetime_survives_days(tmp_path):
    allowance = Allowance(SQLiteStore(tmp_path / 'allowance.sqlite3'))
    allowance.TOTAL_CENTS = 20
    for day in (1, 2):
        job = allowance.reserve(str(day), day * 86400)
        allowance.finish(str(day), job['owner'], None, day * 86400 + 1)
    assert allowance.reserve('third', 3 * 86400)['status'] == 'budget_limit'


def test_owner_and_lease_prevent_stale_worker_overwriting_cache(tmp_path):
    allowance = Allowance(SQLiteStore(tmp_path / 'allowance.sqlite3'))
    first = allowance.reserve('snapshot', 1000)
    next_job = allowance.reserve('snapshot', 1200)
    allowance.finish('snapshot', first['owner'], {'readings': ['stale']}, 1201)
    assert allowance.reserve('snapshot', 1202)['status'] == 'pending'
    allowance.finish('snapshot', next_job['owner'], {'readings': []}, 1203)
    assert allowance.reserve('snapshot', 1204)['result'] == {'readings': []}


def test_hourly_daily_and_concurrent_caps(tmp_path):
    allowance = Allowance(SQLiteStore(tmp_path / 'allowance.sqlite3'))
    a = allowance.reserve('a', 1000)
    b = allowance.reserve('b', 1000)
    assert allowance.reserve('c', 1000)['status'] == 'busy'
    allowance.finish('a', a['owner'], {}, 1001)
    allowance.finish('b', b['owner'], {}, 1001)
    allowance.MAX_HOURLY = 2
    assert allowance.reserve('c', 1002)['status'] == 'hourly_limit'
    allowance.MAX_DAILY = 2
    assert allowance.reserve('c', 5000)['status'] == 'daily_limit'


def test_oversized_result_fails_closed(tmp_path):
    allowance = Allowance(SQLiteStore(tmp_path / 'allowance.sqlite3'))
    job = allowance.reserve('a', 0)
    allowance.finish('a', job['owner'], {'text': 'x' * 16000}, 1)
    assert allowance.reserve('a', 2)['status'] == 'unavailable'


def test_uncapped_native_allowance_preserves_accounting(tmp_path):
    store=SQLiteStore(tmp_path/'uncapped')
    store.transact(lambda s:({'spent_cents':999999,'reservations':[1]*300},None))
    allowance=Allowance(store,enforce_caps=False)
    assert allowance.reserve('new',2)['admitted']
    assert store.transact(lambda s:(s,s))['spent_cents']==1000009
