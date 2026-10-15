"""Offline failures for optional FTS5, Ollama and partial embedding indexing."""
from __future__ import annotations

import io
import json
import socket
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler

import pytest

from oomp.domain.models import AuthorizedScope, MemoryEvent, MemoryNode, SourceReference
from oomp.providers import EmbeddingProviderError, OllamaEmbeddingProvider
from oomp.providers.ollama import _NoRedirect
from oomp.retrieval.contracts import EmbeddingSpace
from oomp.retrieval.engine import RetrievalEngine
from oomp.storage import FTSUnavailableError, SQLiteEventStore, SQLiteMemoryStore, SQLiteRetrievalStore
from oomp.storage.migrations import MIGRATION_1, MIGRATION_2, MIGRATION_3, verify_v3

NOW=datetime(2026,1,1,tzinfo=timezone.utc)


def _scope():
    return AuthorizedScope(tenant_id="failure",namespace="test",principal_id="test")


def _memory(path, suffix):
    scope=_scope()
    event=MemoryEvent(
        event_id=f"event-{suffix}",tenant_id=scope.tenant_id,namespace=scope.namespace,
        event_type="user_message",source_type="user",content=f"Project {suffix} uses Python.",
        source_reference=SourceReference(source_system="synthetic",external_event_id=f"event-{suffix}",timestamp=NOW),
        occurred_at=NOW,ingested_at=NOW,
    )
    stored=SQLiteEventStore(path).append(scope,event)
    memory=MemoryNode(
        memory_id=f"memory-{suffix}",tenant_id=scope.tenant_id,namespace=scope.namespace,
        memory_type="semantic",canonical_key=f"key-{suffix}",canonical_content=stored.content,
        source_event_ids=(stored.event_id,),provenance=(stored.source_reference,),
        created_at=NOW,updated_at=NOW,metadata={"attribution":"user","verified":False},
    )
    return SQLiteMemoryStore(path).upsert(scope,memory)


class _Response:
    status=200
    def __init__(self,raw):
        self.raw=io.BytesIO(raw)
    def __enter__(self):
        return self
    def __exit__(self,*args):
        self.raw.close()
    def read(self,limit):
        return self.raw.read(limit)


class _FakeOpener:
    def __init__(self,response=None,error=None):
        self.response=response
        self.error=error
        self.calls=0
        self.timeout=None
    def open(self,request,timeout):
        self.calls+=1
        self.timeout=timeout
        if self.error:
            raise self.error
        return _Response(self.response)


def test_fts_unavailable_does_not_create_database_or_damage_real_v3(tmp_path,monkeypatch):
    import oomp.storage.sqlite as sqlite_module
    fresh=tmp_path/"missing"/"new.sqlite3"
    monkeypatch.setattr(sqlite_module,"_fts5_available",lambda:False)
    with pytest.raises(FTSUnavailableError,match="FTS5"):
        SQLiteEventStore(fresh).initialize()
    assert not fresh.exists() and not fresh.parent.exists()
    path=tmp_path/"v3.sqlite3"
    with closing(sqlite3.connect(path)) as c,c:
        c.execute("PRAGMA foreign_keys=ON")
        c.create_function("oomp_recorded_at",0,lambda:"2026-01-01T00:00:00.000000Z")
        for statement in (*MIGRATION_1,*MIGRATION_2,*MIGRATION_3):
            c.execute(statement)
        c.execute("PRAGMA user_version=3")
    memory=_memory(path,"older")
    with pytest.raises(FTSUnavailableError,match="FTS5"):
        SQLiteEventStore(path).initialize()
    with closing(sqlite3.connect(path)) as c:
        assert c.execute("PRAGMA user_version").fetchone()[0]==3
        assert verify_v3(c)
        assert c.execute("SELECT COUNT(*) FROM memories").fetchone()[0]==1
    assert SQLiteMemoryStore(path).get(_scope(),memory.memory_id)==memory


@pytest.mark.parametrize("error,expected",[
    (URLError("unavailable"),"unavailable"),
    (HTTPError("http://127.0.0.1:11434/api/embed",404,"not found",None,None),"HTTP 404"),
    (TimeoutError("timed out"),"unavailable"),
])
def test_ollama_transport_failures_are_sanitized_offline(error,expected):
    provider=OllamaEmbeddingProvider(model="embeddinggemma",dimension=2,timeout_seconds=0.5)
    fake=_FakeOpener(error=error)
    provider._opener=fake
    with pytest.raises(EmbeddingProviderError,match=expected):
        provider.embed_query("a bounded query")
    assert fake.calls==1 and fake.timeout==0.5


@pytest.mark.parametrize("raw,expected",[
    (b"{","invalid JSON"),
    (b"x"*1025,"exceeds configured limit"),
    (json.dumps({"model":"embeddinggemma","embeddings":[[1.0]]}).encode(),"dimension"),
    (json.dumps({"model":"embeddinggemma","embeddings":[]}).encode(),"count"),
])
def test_ollama_malformed_oversized_and_incomplete_responses_fail(raw,expected):
    provider=OllamaEmbeddingProvider(
        model="embeddinggemma",dimension=2,max_response_bytes=1024,
    )
    provider._opener=_FakeOpener(response=raw)
    with pytest.raises(EmbeddingProviderError,match=expected):
        provider.embed_query("question")


def test_ollama_input_timeout_proxy_redirect_limits_never_open_socket(monkeypatch):
    def forbid_socket(*args,**kwargs):
        raise AssertionError("network socket opened")
    monkeypatch.setattr(socket,"create_connection",forbid_socket)
    with pytest.raises(ValueError):
        OllamaEmbeddingProvider(model="embeddinggemma",dimension=2,timeout_seconds=0)
    import oomp.providers.ollama as adapter
    actual_builder=adapter.build_opener
    captured=[]
    def capture_handlers(*handlers):
        captured.extend(handlers)
        return actual_builder(*handlers)
    monkeypatch.setattr(adapter,"build_opener",capture_handlers)
    provider=OllamaEmbeddingProvider(
        model="embeddinggemma",dimension=2,max_input_chars=8,max_batch=1,
    )
    proxy_handlers=[item for item in captured if isinstance(item,ProxyHandler)]
    redirect_handlers=[item for item in captured if isinstance(item,_NoRedirect)]
    assert len(proxy_handlers)==1 and proxy_handlers[0].proxies=={}
    assert len(redirect_handlers)==1
    assert redirect_handlers[0].redirect_request(None,None,302,"Moved",{}, "http://example.com") is None
    fake=_FakeOpener(response=b"")
    provider._opener=fake
    for texts in ((),("one","two"),("x"*9,),(" ",)):
        with pytest.raises(ValueError):
            provider.embed(texts)
    assert fake.calls==0


class _FailSecondBatch:
    space=EmbeddingSpace(provider="test",model="fixed",version="v1",dimension=2)
    def __init__(self):
        self.calls=0
    def embed(self,texts):
        self.calls+=1
        if self.calls==2:
            raise RuntimeError("simulated provider failure")
        return tuple((1.0,0.0) for _ in texts)


def test_provider_failure_after_one_batch_keeps_lexical_and_prior_vectors(tmp_path):
    path=tmp_path/"partial.sqlite3"
    SQLiteEventStore(path).initialize()
    for suffix in ("one","two","three"):
        _memory(path,suffix)
    provider=_FailSecondBatch()
    engine=RetrievalEngine(path,provider=provider)
    report=engine.index(_scope(),batch_size=1,include_embeddings=True)
    assert report.lexical_skipped==3
    assert report.embeddings_indexed==1
    assert report.embeddings_failed==1
    assert report.warnings and report.warnings[0].startswith("embedding_batch_failed:")
    status=SQLiteRetrievalStore(path).index_status(_scope(),provider.space)
    assert status.canonical_count==3
    assert status.lexical_count==3 and status.lexical_stale==0
    assert status.compatible_embeddings==1 and status.stale_embeddings==0
    with SQLiteRetrievalStore(path).read_snapshot(_scope()) as snapshot:
        assert len(snapshot.lexical("Python"))==3
