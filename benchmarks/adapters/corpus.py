"""Create a fresh, explicitly located synthetic database for one knowledge prefix."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from time import perf_counter_ns

from benchmarks.contracts import Case, History, Prepared, digest
from benchmarks.datasets.generate import eligible
from oomp.domain.models import AuthorizedScope, MemoryNode
from oomp.graph import GraphService
from oomp.ingestion import ExtractionPipeline
from oomp.retrieval.engine import RetrievalEngine
from oomp.storage import SQLiteEventStore
from oomp.storage.memory_store import SQLiteMemoryStore
from oomp.storage.topic_store import SQLiteTopicStore


def ms(start):
    return (perf_counter_ns() - start) / 1_000_000


def scope_for(history):
    return AuthorizedScope(tenant_id=history.tenant_id, namespace=history.namespace, principal_id="stage9-benchmark")


def prepare(history: History, case: Case, path: Path):
    if path.exists() or path.suffix != ".sqlite3":
        raise ValueError("benchmark database must be a new explicit .sqlite3 file")
    path.parent.mkdir(parents=True, exist_ok=True)
    sources = eligible(history, case)
    scope = scope_for(history)
    events, memories = SQLiteEventStore(path), SQLiteMemoryStore(path)
    start=perf_counter_ns(); events.initialize(); setup_ms=ms(start)
    pipeline = ExtractionPipeline(path)
    ingestion_ms=extraction_ms=curated_ms=graph_ms=0.0
    by_source={}
    for e in sources:
        start=perf_counter_ns(); events.append(scope,e); ingestion_ms+=ms(start)
        start=perf_counter_ns(); result=pipeline.process_event(scope,e.event_id); extraction_ms+=ms(start)
        if result.memory_ids:
            by_source[e.event_id]=result.memory_ids[0]
    # RAM statements are outside the extractor grammar. These authored structured
    # observations are visible to every canonical-memory baseline, never query labels.
    source_map={e.event_id:e for e in sources}
    for item in history.curated:
        if item.source_id not in source_map:
            continue
        e=source_map[item.source_id]
        reported=e.metadata.get("reported_validity")
        expected={"valid_from":item.valid_from.isoformat() if item.valid_from else None,
                  "valid_until":item.valid_until.isoformat() if item.valid_until else None}
        if reported!=expected:
            raise ValueError("curated validity must be explicitly established in source observations")
        node=MemoryNode(memory_id="curated-"+digest([history.history_id,e.event_id])[:32],
            tenant_id=scope.tenant_id,namespace=scope.namespace,memory_type="semantic",
            canonical_content=e.content,canonical_key="stage9:"+digest([e.event_id,e.content]),
            source_event_ids=(e.event_id,),provenance=(e.source_reference,),
            created_at=e.ingested_at,updated_at=e.ingested_at,valid_from=item.valid_from,valid_until=item.valid_until,
            metadata={"attribution":"user","verified":False,"synthetic":True,"fixture_layer":"curated_temporal"})
        start=perf_counter_ns(); memories.upsert(scope,node); curated_ms+=ms(start)
        by_source[e.event_id]=node.memory_id
    graph=GraphService(path)
    start=perf_counter_ns()
    actual_edges=[]
    for link in history.links:
        if not {link.source_event,link.target_event,*link.evidence_events} <= set(source_map):
            continue
        if link.source_event not in by_source or link.target_event not in by_source:
            raise ValueError("fixture graph endpoint did not produce a real memory")
        a,b=by_source[link.source_event],by_source[link.target_event]
        if link.relation in {"SUPERSEDES","CONTRADICTS"}:
            proposal=graph.propose_conflict(scope,a,b).proposal
            if proposal is None or proposal.relationship_type.value!=link.relation:
                raise ValueError("fixture protected relation is unsupported by production policy")
            record=graph.resolve(scope,proposal,confirm=True)
        else:
            record=graph.link(scope,a,b,link.relation,link.evidence_events)
        actual_edges.append(record.model_dump(mode="json"))
    topics=SQLiteTopicStore(path)
    for topic in history.topics:
        present=[s for s in topic.source_events if s in by_source]
        if present:
            topics.create_topic(scope,topic.topic_id,topic.name)
            for source_id in present:
                topics.assign_memory(scope,topic.topic_id,by_source[source_id])
    graph_ms=ms(start)
    start=perf_counter_ns(); index=RetrievalEngine(path).index(scope); index_ms=ms(start)
    nodes=[]; cursor=None
    while True:
        page=memories.list_memories(scope,limit=100,after=cursor)
        nodes.extend(page.memories)
        if page.next_cursor is None: break
        cursor=page.next_cursor
    nodes.sort(key=lambda m:m.memory_id)
    canonical=[{"id":m.memory_id,"content":m.canonical_content,"sources":m.source_event_ids} for m in nodes]
    prepared=Prepared(history_id=history.history_id,events=sources,memories=tuple(nodes),
        source_digest=digest([e.model_dump(mode="json") for e in sources]),canonical_digest=digest(canonical),
        replay_known_at=datetime.now(timezone.utc))
    costs={"setup_ms":setup_ms,"source_ingestion_ms":ingestion_ms,
        "extraction_canonicalization_persistence_ms":extraction_ms,"curated_memory_persistence_ms":curated_ms,
        "graph_topic_update_ms":graph_ms,"lexical_index_check_ms":index_ms,
        "canonicalization_ms":None,"trigger_lexical_index_ms":None,
        "source_count":len(sources),"canonical_count":len(nodes),"database_bytes":path.stat().st_size,
        "lexical_indexed":index.lexical_indexed,"lexical_skipped":index.lexical_skipped}
    try:
        with sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro",uri=True) as connection:
            pages=connection.execute("SELECT name,sum(pgsize) FROM dbstat GROUP BY name").fetchall()
        costs["sqlite_page_bytes_by_object"]={name:size for name,size in pages}
    except sqlite3.Error:costs["sqlite_page_bytes_by_object"]=None
    return prepared,costs,actual_edges
