"""P3 upgrades only disposable fixtures; original migration SQL is immutable."""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from oomp.domain.models import AuthorizedScope, MemoryEvent, SourceReference
from oomp.ingestion.pipeline import ExtractionPipeline
from oomp.storage.errors import StorageUnavailableError, UnsupportedSchemaVersionError
from oomp.storage.migrations import MIGRATIONS, MIGRATION_5, SCHEMA_VERSION, verify_v5, verify_v6
from oomp.storage.sqlite import SQLiteEventStore
from test_stage6_storage import old_v4

SCOPE=AuthorizedScope(tenant_id="p3-migration",namespace="synthetic",principal_id="owner")
NOW=datetime(2026,1,1,tzinfo=timezone.utc)
HISTORICAL_HASHES={
    1:"08650759cc0d1c32136c4d7ca1a34d01f2a047dc81892fc19229c550230ea582",
    2:"088ea6dfc2ffbdcaac8340eb104237da56226a8a507bc65391e1f7046313fa39",
    3:"8131113b7d7b22c94e556b2991465040c2165af785871371759ddc1b135f9171",
    4:"c3178b415ecd1d7c318c12f79d44e42c0d9b7132f05a10187e8b0f4c00684b75",
    5:"7942c3382fbe710f088285e6be7c3d185725ed66b5d57c9515ecf8b8535f6c19",
}


def v5_fixture(path):
    old_v4(path)
    with closing(sqlite3.connect(path)) as c,c:
        c.create_function("oomp_recorded_at",0,lambda:"2026-01-01T00:00:00.000000Z")
        for statement in MIGRATION_5:c.execute(statement)
        c.execute("PRAGMA user_version=5")
        assert verify_v5(c)
    event=MemoryEvent(event_id="migration-source",tenant_id=SCOPE.tenant_id,namespace=SCOPE.namespace,
        event_type="user_message",source_type="user",content="I prefer concise technical explanations.",
        source_reference=SourceReference(source_system="synthetic",external_event_id="migration-source",timestamp=NOW),
        occurred_at=NOW,ingested_at=NOW)
    SQLiteEventStore(path).append(SCOPE,event)
    ExtractionPipeline(path).process_event(SCOPE,event.event_id)
    return event


def original_rows(path):
    with closing(sqlite3.connect(path)) as c:
        return {table:c.execute("SELECT * FROM "+table).fetchall() for table in
                ("events","memories","memory_sources","memory_source_recordings","entities",
                 "entity_aliases","memory_entities","topics","topic_memberships","memory_edges",
                 "mind_jobs","mind_summary_revisions","mind_summary_sources")}


@pytest.mark.parametrize("version",sorted(HISTORICAL_HASHES))
def test_applied_migration_statements_remain_exactly_unchanged(version):
    assert hashlib.sha256(json.dumps(MIGRATIONS[version],ensure_ascii=True).encode()).hexdigest()==HISTORICAL_HASHES[version]


def test_genuine_v5_upgrade_preserves_sources_memories_and_graph(tmp_path):
    path=tmp_path/"old.sqlite3"
    event=v5_fixture(path)
    before=original_rows(path)
    store=SQLiteEventStore(path)
    assert not store.status().ready and store.status().schema_version==5
    assert store.initialize()==SCHEMA_VERSION==6
    assert store.initialize()==6
    assert store.status().ready and store.get(SCOPE,event.event_id)==event
    assert original_rows(path)==before
    with closing(sqlite3.connect(path)) as c:
        assert verify_v6(c) and c.execute("PRAGMA foreign_key_check").fetchall()==[]
        with pytest.raises(sqlite3.IntegrityError):c.execute("DELETE FROM events")


def test_failed_v6_upgrade_rolls_back_every_statement_and_original_data(tmp_path,monkeypatch):
    path=tmp_path/"rollback.sqlite3"
    v5_fixture(path)
    before=original_rows(path)
    monkeypatch.setitem(MIGRATIONS,6,MIGRATIONS[6]+("CREATE TABLE events (invalid TEXT)",))
    with pytest.raises(StorageUnavailableError):SQLiteEventStore(path).initialize()
    with closing(sqlite3.connect(path)) as c:
        assert c.execute("PRAGMA user_version").fetchone()[0]==5 and verify_v5(c)
        assert c.execute("SELECT name FROM sqlite_master WHERE name LIKE 'map_%'").fetchall()==[]
    assert original_rows(path)==before


def test_process_exit_during_uncommitted_upgrade_recovers_v5(tmp_path):
    path=tmp_path/"interrupted.sqlite3"
    v5_fixture(path)
    before=original_rows(path)
    code=("import os,sys;from oomp.storage.sqlite import SQLiteEventStore;"
          "from oomp.storage.migrations import MIGRATIONS;"
          "c=SQLiteEventStore(sys.argv[1])._connect('rw');c.execute('BEGIN IMMEDIATE');"
          "[c.execute(s) for s in MIGRATIONS[6][:3]];os._exit(23)")
    child=subprocess.run([sys.executable,"-I","-c",code,str(path)],timeout=15,capture_output=True)
    assert child.returncode==23
    with closing(sqlite3.connect(path)) as c:
        assert c.execute("PRAGMA user_version").fetchone()[0]==5 and verify_v5(c)
    assert original_rows(path)==before
    assert SQLiteEventStore(path).initialize()==6


def test_future_schema_rejected_without_writes(tmp_path):
    path=tmp_path/"future.sqlite3"
    with closing(sqlite3.connect(path)) as c,c:c.execute(f"PRAGMA user_version={SCHEMA_VERSION+1}")
    before=path.read_bytes()
    with pytest.raises(UnsupportedSchemaVersionError):SQLiteEventStore(path).initialize()
    assert path.read_bytes()==before


def test_v6_wal_backup_reopen_and_schema_tampering_detection(tmp_path):
    path=tmp_path/"source.sqlite3"
    event=v5_fixture(path)
    store=SQLiteEventStore(path)
    store.initialize()
    backup=tmp_path/"fresh-backup.sqlite3"
    with closing(store._connect("ro")) as source,closing(sqlite3.connect(backup)) as target:
        source.backup(target)
    restored=SQLiteEventStore(backup)
    assert restored.status().ready and restored.get(SCOPE,event.event_id)==event
    with closing(sqlite3.connect(backup)) as c,c:
        assert c.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
        c.execute("DROP INDEX map_proofs_source")
    assert not restored.status().ready
