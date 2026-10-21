#!/usr/bin/env python3
"""Offline correction smoke check. Isolated temporary journals; no model/cloud calls."""
import json
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from counterpress.personalization.api import install_personalization
from counterpress.personalization.store import DataStore
from counterpress.personalization.journal import SQLiteCareerJournal
from counterpress.assistant.api import install_assistant


def main():
    # Explicit test doubles keep this verification offline even in an Azure shell.
    class NoModel:
        async def plan(self,*args):raise ValueError('Offline verification')
    with tempfile.TemporaryDirectory(prefix='footie-revisions-') as folder:
        path=Path(folder)/'journal.sqlite3'
        writer_journal=SQLiteCareerJournal(path);reader_journal=SQLiteCareerJournal(path)
        writer=DataStore(ROOT/'fixtures/personalization',journal=writer_journal)
        app=FastAPI();reader=install_personalization(app,ROOT/'fixtures',reader_journal)
        install_assistant(app,reader,planner=NoModel())
        mid='career-showcase-southbank-redhaven'
        record=writer.original(mid);goal=next(e for e in record.events if e.event_id=='e01178')
        sequence=max(e.delivery_sequence for e in record.events)
        readings=[]
        try:
            with TestClient(app) as client:
                for revision in (1,2,3):
                    if revision>1:
                        event=goal.model_copy(update={'revision':revision,'delivery_sequence':sequence+revision-1,
                            'available_period':2,'available_ms':2700000+100*(revision-1),'retracted':revision==2})
                        writer.ingest(mid,[event])
                        assert writer.ingest(mid,[event])['accepted']==0
                    profile=client.get('/api/data/players/rh09').json()['totals']['goals']
                    result=client.post('/api/fan/assistant/ask',json={'question':'How many goals does Mateo Cross have?','as_of':'2026-10-20T00:00:00Z'})
                    assert result.status_code==200
                    answer=result.json()['facts'][0]['value']
                    assert profile==answer
                    readings.append(profile)
                assert readings==[75,74,75]
                state=client.get('/api/data/revisions').json()
                assert state['generation']==2
            restarted=DataStore(ROOT/'fixtures/personalization',journal=SQLiteCareerJournal(path))
            try:
                with restarted.snapshot():assert len(restarted.journal.read(restarted.dataset).actions)==2
            finally:restarted.journal.close();restarted.close()
            print(json.dumps({'status':'passed','profile_and_footie_goals':readings,'durable_generations':state['generation'],
                'duplicate_deliveries':'ignored','restart':'passed','azure_calls':0,'model_calls':0},indent=2))
        finally:
            reader().store.close();writer.close();reader_journal.close();writer_journal.close()


if __name__=='__main__':main()
