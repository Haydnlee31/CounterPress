"""Local SQLite index over a reproducible canonical ledger, plus revision overlays.

Source artifacts contain no keys. Azure storage/stream connections are deliberately
not configured here. The same reducer handles static and corrected/live views.
"""
from contextlib import contextmanager
from functools import lru_cache
from hashlib import sha256
import gzip
import json
from pathlib import Path
import sqlite3
from threading import RLock
from counterpress.history import HistoryStorageError
from .contracts import Action,Club,Fixture,MatchRecord,Player
from .metrics import digest,reduce_record,select_events
from .simulation import simulate


class DataStore:
    def __init__(self,root:Path,path=':memory:',*,allow_unreviewed_spatial=False,journal=None):
        self.root=root;self.lock=RLock()
        self.journal=journal;self._frame=None
        self.manifest=json.loads((root/'manifest.json').read_text())
        if self.manifest.get('validation_status','passed')!='passed':
            raise ValueError('Career dataset did not pass validation; keep the previous dataset active')
        for file,expected in self.manifest['files'].items():
            if Path(file).name!=file or sha256((root/file).read_bytes()).hexdigest()!=expected:
                raise ValueError('Career artifact checksum mismatch')
        self.model=json.loads((root/'model.json').read_text())
        if self.model.get('spatial') and not allow_unreviewed_spatial:
            if 'spatial-validation.json' not in self.manifest['files']:
                raise ValueError('Spatial dataset needs the expanded position audit before use')
            review=json.loads((root/'spatial-validation.json').read_text())
            if (not isinstance(review,dict) or review.get('status')!='passed_with_coverage_limits' or
                any(review.get('input_sha256',{}).get(name)!=self.manifest['files'].get(name) for name in ('model.json','ledger.json.gz','registry.json')) or
                review.get('prior_position_report_sha256')!=self.manifest['files'].get('position-validation.json')):
                raise ValueError('Spatial position audit failed or does not match this dataset')
        registry=json.loads((root/'registry.json').read_text())
        self.clubs={c.club_id:c for c in (Club.model_validate(x) for x in registry['clubs'])}
        self.players={p.player_id:p for p in (Player.model_validate(x) for x in registry['players'])}
        if len(self.players)!=len(registry['players']) or any(p.club_id not in self.clubs for p in self.players.values()):raise ValueError('Invalid registry')
        if path!=':memory:':Path(path).parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(path,check_same_thread=False);self.db.row_factory=sqlite3.Row
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS career_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS career_matches(id TEXT PRIMARY KEY,kickoff TEXT NOT NULL,season TEXT NOT NULL,
            home TEXT NOT NULL,away TEXT NOT NULL,featured INTEGER NOT NULL,fixture TEXT NOT NULL,digest TEXT NOT NULL,summary TEXT NOT NULL);
          CREATE INDEX IF NOT EXISTS career_dates ON career_matches(kickoff,season);
          CREATE TABLE IF NOT EXISTS career_revisions(match_id TEXT NOT NULL,event_id TEXT NOT NULL,revision INTEGER NOT NULL,
            sequence INTEGER NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(match_id,event_id,revision),UNIQUE(match_id,sequence));
        ''')
        fingerprint=self.manifest['files']['ledger.json.gz']
        old=self.db.execute("SELECT value FROM career_meta WHERE key='ledger'").fetchone()
        if old and old[0]!=fingerprint and self.db.execute('SELECT 1 FROM career_revisions LIMIT 1').fetchone():
            raise ValueError('Dataset changed with live revisions present; choose a new career database')
        if not old or old[0]!=fingerprint:
            rows=json.loads(gzip.decompress((root/'ledger.json.gz').read_bytes()))
            if len({r['fixture']['match_id'] for r in rows})!=len(rows):raise ValueError('Duplicate fixture')
            with self.db:
                self.db.execute('DELETE FROM career_matches')
                for row in rows:
                    f=Fixture.model_validate_json(json.dumps(row['fixture']))
                    if f.home_id not in self.clubs or f.away_id not in self.clubs:raise ValueError('Unknown fixture club')
                    if any(a.player_id not in self.players or self.players[a.player_id].club_id!=a.club_id for a in f.appearances):raise ValueError('Unknown appearance')
                    self.db.execute('INSERT INTO career_matches VALUES(?,?,?,?,?,?,?,?,?)',
                        (f.match_id,f.kickoff,f.season,f.home_id,f.away_id,int(f.featured),f.model_dump_json(),row['event_digest'],json.dumps(row['summary'],separators=(',',':'))))
                self.db.execute("INSERT OR REPLACE INTO career_meta VALUES('ledger',?)",(fingerprint,))

    def close(self):self.db.close()

    def rows(self,club=None,season=None,before=None,featured=None):
        where=[];args=[]
        if club:where.append('(home=? OR away=?)');args.extend([club,club])
        if season:where.append('season=?');args.append(season)
        if before:where.append('kickoff<?');args.append(before)
        if featured is not None:where.append('featured=?');args.append(int(featured))
        with self.lock:
            return list(self.db.execute('SELECT * FROM career_matches'+(' WHERE '+' AND '.join(where) if where else '')+' ORDER BY kickoff DESC,id',args))

    def row(self,mid):
        with self.lock:r=self.db.execute('SELECT * FROM career_matches WHERE id=?',(mid,)).fetchone()
        if r is None:raise KeyError(mid)
        return r

    @lru_cache(maxsize=12)
    def original(self,mid):
        row=self.row(mid);fixture=Fixture.model_validate_json(row['fixture'])
        if fixture.featured:
            record=MatchRecord.model_validate_json(gzip.decompress((self.root/(mid+'.json.gz')).read_bytes()))
        else:
            record=simulate(self.model,list(self.players.values()),fixture.home_id,fixture.away_id,mid,fixture.kickoff,fixture.season,fixture.seed)
        if record.fixture!=fixture or digest(record.events)!=row['digest']:raise ValueError('Reproduced events do not match canonical ledger')
        return record

    def events(self,mid):
        original=self.original(mid)
        with self.lock:rows=list(self.db.execute('SELECT payload FROM career_revisions WHERE match_id=? ORDER BY sequence',(mid,)))
        return (*original.events,*(Action.model_validate_json(r[0]) for r in rows))

    def evidence_digest(self,mid,cutoff=None):
        with self.lock:changed=self.db.execute('SELECT 1 FROM career_revisions WHERE match_id=? LIMIT 1',(mid,)).fetchone()
        return digest(select_events(self.events(mid),cutoff)) if changed else self.row(mid)['digest']

    def summary(self,mid,cutoff=None,sequence=None,completed=False):
        row=self.row(mid)
        with self.lock:changed=self.db.execute('SELECT 1 FROM career_revisions WHERE match_id=? LIMIT 1',(mid,)).fetchone()
        fixture=Fixture.model_validate_json(row['fixture'])
        complete_initial=completed and cutoff is not None and cutoff>=(2,fixture.period_lengths_ms[1]+1000)
        if not changed and (cutoff is None or complete_initial) and sequence is None:return json.loads(row['summary'])
        record=self.original(mid);events=self.events(mid)
        if sequence is not None:events=tuple(e for e in events if e.delivery_sequence<=sequence)
        # A revision history intentionally contains repeated IDs. Validate the
        # selected version set as a match, rather than bypassing actor checks.
        selected=select_events(events,cutoff)
        current=MatchRecord(fixture=record.fixture,events=tuple(selected))
        return reduce_record(current,None if completed else cutoff)

    @property
    def dataset(self):return self.manifest['files']['ledger.json.gz']

    @contextmanager
    def snapshot(self):
        """One consistent compound read, refreshed from shared durable revisions."""
        with self.lock:
            if self.journal:self._materialize(self.journal.read(self.dataset))
            yield self

    def revision_state(self):
        with self.snapshot():
            return {'dataset':self.dataset,'generation':self._frame.generation if self._frame else 0,
                    'enabled':self.journal is not None,
                    'matches':{mid:sum(e.match_id==mid for e in self._frame.actions) for mid in {e.match_id for e in self._frame.actions}} if self._frame else {}}

    def _materialize(self,frame):
        if frame.dataset!=self.dataset:raise HistoryStorageError('Career dataset mismatch')
        if self._frame==frame:return
        if self._frame and (frame.generation<self._frame.generation or
                frame.actions[:len(self._frame.actions)]!=self._frame.actions):
            raise HistoryStorageError('Career correction history regressed')
        with self.db:
            local={r[0] for r in self.db.execute('SELECT payload FROM career_revisions')}
            shared={e.model_dump_json() for e in frame.actions}
            if not local.issubset(shared):
                raise HistoryStorageError('Local career revisions differ from shared history')
            grouped={}
            for e in frame.actions:
                if e.model_dump_json() not in local:grouped.setdefault(e.match_id,[]).append(e)
            try:
                for mid,incoming in grouped.items():
                    pending,_=self._validate(mid,incoming,self.events(mid))
                    self._insert(pending)
            except (ValueError,KeyError):
                raise HistoryStorageError('Shared career revisions failed validation') from None
        self._frame=frame

    def _insert(self,pending):
        for e in pending:self.db.execute('INSERT INTO career_revisions VALUES(?,?,?,?,?)',
            (e.match_id,e.event_id,e.revision,e.delivery_sequence,e.model_dump_json()))

    def ingest(self,mid,events):
        """Validate, durably commit, then materialize; duplicate retries are harmless."""
        incoming=[Action.model_validate_json(e.model_dump_json()) for e in events]
        if any(e.match_id!=mid for e in incoming):raise ValueError('Wrong match')
        with self.lock:
            if not self.journal:
                with self.db:
                    pending,result=self._validate(mid,incoming,self.events(mid))
                    self._insert(pending)
                return result
            self._materialize(self.journal.read(self.dataset))
            result={}
            def build(previous):
                # A Cosmos conflict rebuilds against the winning durable frame,
                # never against an index that missed another replica's commit.
                existing=(*self.original(mid).events,*(e for e in previous.actions if e.match_id==mid))
                pending,counts=self._validate(mid,incoming,existing)
                result.clear();result.update(counts)
                return (*previous.actions,*pending)
            frame=self.journal.transact(self.dataset,build)
            self._materialize(frame)
            return {**result,'generation':frame.generation}

    def _validate(self,mid,incoming,existing):
        by_version={(e.event_id,e.revision):e for e in existing};by_seq={e.delivery_sequence:e for e in existing}
        identities={e.event_id:e.occurrence_order for e in existing}
        pending=[]
        for e in incoming:
            version=(e.event_id,e.revision)
            if version in by_version:
                if e!=by_version[version]:raise ValueError('Conflicting event revision')
                continue
            if e.delivery_sequence in by_seq:raise ValueError('Conflicting delivery sequence')
            if e.event_id in identities and e.occurrence_order!=identities[e.event_id]:raise ValueError('Occurrence order is immutable')
            # A correction must become available after every earlier revision.
            versions=[v for (eid,_),v in by_version.items() if eid==e.event_id]
            for old in versions:
                if (e.revision>old.revision)!=( (e.available_period,e.available_ms,e.delivery_sequence)>(old.available_period,old.available_ms,old.delivery_sequence)):
                    raise ValueError('Revision chronology conflicts with availability')
            by_version[version]=e;by_seq[e.delivery_sequence]=e;identities[e.event_id]=e.occurrence_order;pending.append(e)
        all_events=(*existing,*pending)
        # Validate every supplied revision independently, even one superseded
        # in this batch, as well as the latest whole-match identity set.
        fixture=self.original(mid).fixture
        for e in pending:MatchRecord(fixture=fixture,events=(e,))
        MatchRecord(fixture=fixture,events=tuple(select_events(all_events)))
        return pending,{'accepted':len(pending),'duplicates':len(incoming)-len(pending),
                        'received_through_sequence':max(by_seq,default=0)}
