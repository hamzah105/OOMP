from __future__ import annotations

import math
import re
import sqlite3
from contextlib import contextmanager
from time import perf_counter_ns

from benchmarks.adapters.corpus import ms, scope_for
from benchmarks.contracts import Evidence, Result, digest
from oomp.domain.enums import MemoryType
from oomp.retrieval.contracts import MemoryEvidence, RetrievalRequest
from oomp.retrieval.engine import RetrievalEngine
from oomp.retrieval.packing import pack_evidence

# Explicit conventional stoplist; literal OR FTS terms, never executable FTS input.
STOP=frozenset("a an and are at be by did do does for from has have how i in is it me my of on or our the their them there these this those to us was were what when where which who why with you your user tell about".split())


def terms(text):
    return tuple(dict.fromkeys(x.casefold() for x in re.findall(r"[^\W_]+",text) if len(x)>1 and x.casefold() not in STOP))[:32]


def raw_evidence(e):
    reported=e.metadata.get("reported_validity") or {}
    return MemoryEvidence(memory_id="raw-"+e.event_id, memory_type=MemoryType.EPISODIC,
        canonical_content=e.content,source_event_ids=(e.event_id,),source_references=(e.source_reference,),
        valid_from=reported.get("valid_from"),valid_until=reported.get("valid_until"),
        temporal_status="uninterpreted")


def node_evidence(m):
    return MemoryEvidence(memory_id=m.memory_id,memory_type=m.memory_type,canonical_content=m.canonical_content,
        source_event_ids=m.source_event_ids,source_references=m.provenance,valid_from=m.valid_from,valid_until=m.valid_until,
        temporal_status="uninterpreted")


def convert(memories, nodes=None):
    mapping={} if nodes is None else {n.memory_id:n.source_event_ids for n in nodes}
    evidence=[]
    for m in memories:
        paths=[]
        for p in m.graph_paths:
            paths.append({"node_source_ids":[list(mapping.get(n,())) for n in p.node_ids],
                "node_ids":list(p.node_ids),"edge_ids":list(p.edge_ids),
                "relationships":[r.value for r in p.relationship_types],
                "directions":list(p.edge_directions),"validity":list(p.edge_validity),
                "proof_ids":[[r.external_event_id for r in group] for group in p.edge_evidence]})
        evidence.append(Evidence(source_ids=m.source_event_ids,content=m.canonical_content,
            temporal_status=m.temporal_status,valid_from=m.valid_from,valid_until=m.valid_until,
            memory_id=m.memory_id,paths=tuple(paths)))
    return tuple(evidence)


def packed(method, candidates, config, started, warnings=(), limit=None):
    start=perf_counter_ns()
    packet=pack_evidence(tuple(candidates),config.evidence_budget,limit or config.max_results)
    return Result(method=method,evidence=convert(packet.memories),packet=packet.context_packet,
        packet_bytes=packet.estimated_token_count,retrieval_ms=ms(started),packing_ms=ms(start),warnings=warnings)


class LatestEight:
    def __init__(self,prepared,config): self.prepared,self.config=prepared,config
    def retrieve(self,case):
        start=perf_counter_ns()
        candidates=tuple(raw_evidence(e) for e in self.prepared.events[-8:])
        # Original policy keeps all eight. Refuse a comparison whose budget cannot
        # hold them; silently dropping old turns would change TRACE-N8.
        result=packed("trace_n8",candidates,self.config,start,limit=8)
        if len(result.evidence)!=len(candidates):
            return result.model_copy(update={"status":"failed","error_code":"latest_eight_budget_overflow",
                                            "evidence":(),"packet":"","packet_bytes":0})
        return result


class RollingSummary:
    """Recency-prioritized, exact-deduplicated extractive compression every N events.

    Retains both corrections and old claims if they fit; no semantic resolution.
    Pending events are incorporated at query time under the same memory budget.
    """
    def __init__(self,prepared,config):
        start=perf_counter_ns(); summary=[]; pending=[]; updates=0
        for event in prepared.events:
            pending.append(raw_evidence(event))
            if len(pending)==config.summary_update_every:
                summary=self._update(summary,pending,config); pending=[];updates+=1
        self.candidates=self._update(summary,pending,config)
        self.config=config
        self.costs={"summary_compression_ms":ms(start),"summary_updates":updates,
                    "summary_budget":config.summary_budget,"update_every":config.summary_update_every}
    @staticmethod
    def _update(previous,pending,config):
        unique={}
        for m in (*previous,*pending):
            key=" ".join(m.canonical_content.casefold().split())
            unique.pop(key,None);unique[key]=m
        # Count full source proof and JSON. Summary storage has the same accounting.
        packed_summary=pack_evidence(tuple(reversed(tuple(unique.values()))),config.summary_budget,100)
        return list(reversed(packed_summary.memories))
    def retrieve(self,case):
        start=perf_counter_ns()
        return packed("rolling_summary",self.candidates[-self.config.max_results:],self.config,start)


class FlatLexical:
    def __init__(self,prepared,config,path):
        start=perf_counter_ns()
        if path.exists(): raise ValueError("flat index must be a new file")
        self.connection=sqlite3.connect(path)
        self.connection.execute("CREATE VIRTUAL TABLE documents USING fts5(memory_id UNINDEXED,content,tokenize='unicode61')")
        self.nodes={m.memory_id:m for m in prepared.memories}
        self.connection.executemany("INSERT INTO documents VALUES (?,?)",[(m.memory_id,m.canonical_content) for m in prepared.memories])
        self.connection.commit();self.config=config
        self.costs={"flat_lexical_index_ms":ms(start),"database_bytes":path.stat().st_size}
    def retrieve(self,case):
        start=perf_counter_ns(); query_terms=terms(case.query)
        expression=" OR ".join('"'+x.replace('"','""')+'"' for x in query_terms)
        rows=[] if not expression else self.connection.execute(
            "SELECT memory_id FROM documents WHERE documents MATCH ? ORDER BY bm25(documents),memory_id LIMIT 40",(expression,)).fetchall()
        return packed("flat_lexical",[node_evidence(self.nodes[r[0]]) for r in rows],self.config,start)
    def close(self): self.connection.close()


def unit(vector,dimension):
    if len(vector)!=dimension or any(type(v) not in (int,float) or not math.isfinite(v) for v in vector):
        raise ValueError("invalid embedding dimensions or values")
    norm=math.hypot(*vector)
    if not math.isfinite(norm) or norm<=0: raise ValueError("invalid embedding norm")
    return tuple(v/norm for v in vector)


class FlatVector:
    def __init__(self,prepared,config,provider):
        self.prepared,self.config,self.provider=prepared,config,provider
        self.vectors=[]; start=perf_counter_ns()
        if provider is not None:
            for i in range(0,len(prepared.memories),16):
                batch=prepared.memories[i:i+16]
                vectors=provider.embed(tuple(m.canonical_content for m in batch))
                if len(vectors)!=len(batch):raise ValueError("incomplete embedding batch")
                self.vectors.extend(unit(v,provider.space.dimension) for v in vectors)
        self.costs={"embedding_generation_and_validation_ms":ms(start) if provider else None,
            "vector_numeric_payload_bytes":len(self.vectors)*(provider.space.dimension if provider else 0)*8,
            "vector_count":len(self.vectors),"space":None if provider is None else provider.space.model_dump(mode="json")}
    def retrieve(self,case):
        start=perf_counter_ns()
        if self.provider is None:
            return Result(method="flat_vector",status="unavailable",error_code="embedding_not_enabled")
        response=self.provider.embed((case.query,))
        if len(response)!=1:raise ValueError("incomplete query embedding")
        query=unit(response[0],self.provider.space.dimension)
        scored=[]
        for m,v in zip(self.prepared.memories,self.vectors,strict=True):
            score=max(-1.0,min(1.0,math.fsum(a*b for a,b in zip(query,v,strict=True))))
            if score>=self.config.min_similarity:scored.append((score,m))
        scored.sort(key=lambda x:(-x[0],x[1].memory_id))
        return packed("flat_vector",[node_evidence(m) for _,m in scored[:40]],self.config,start)


class _NoAugmentationSession:
    def __init__(self,session):self.session=session
    def __getattr__(self,key): return getattr(self.session,key)
    def entity_candidates(self,*a,**kw):return ()
    def topic_candidates(self,*a,**kw):return ()


class _NoAugmentationStore:
    def __init__(self,store):self.store=store
    def __getattr__(self,key):return getattr(self.store,key)
    @contextmanager
    def read_snapshot(self,scope):
        with self.store.read_snapshot(scope) as session:
            yield _NoAugmentationSession(session)


class OOMP:
    def __init__(self,history,prepared,config,path,method="oomp_full",provider=None):
        self.scope,self.prepared,self.config=scope_for(history),prepared,config
        self.method=method;self.engine=RetrievalEngine(path,provider=provider)
        if method=="oomp_no_augmentation":self.engine.store=_NoAugmentationStore(self.engine.store)
    def retrieve(self,case):
        start=perf_counter_ns()
        if self.method in {"flat_no_temporal","oomp_no_fusion"}:
            return Result(method=self.method,status="unavailable",error_code="no_faithful_production_switch")
        mode={"oomp_lexical":"lexical","oomp_semantic":"semantic"}.get(self.method,self.config.mode)
        if mode in {"semantic","hybrid"} and self.engine.provider is None:
            return Result(method=self.method,status="unavailable",error_code="embedding_not_enabled")
        request=RetrievalRequest(tenant_id=self.scope.tenant_id,namespace=self.scope.namespace,query=case.query,
            token_budget=self.config.evidence_budget,max_results=self.config.max_results,mode=mode,
            graph_depth=0 if self.method=="oomp_no_graph" else self.config.graph_depth,
            historical=case.historical,valid_at=case.valid_at,
            # The physical corpus is already the frozen knowledge prefix. The
            # recorded replay instant is the real store clock, not fictional time.
            known_at=self.prepared.replay_known_at if case.known_at else None,
            min_semantic_similarity=self.config.min_similarity,allow_degraded=False)
        response=self.engine.retrieve(self.scope,request)
        return Result(method=self.method,evidence=convert(response.memories,self.prepared.memories),
            packet=response.context_packet,packet_bytes=response.estimated_token_count,
            retrieval_ms=ms(start),warnings=response.warnings,
            trace=response.retrieval_trace.model_dump(mode="json"))
