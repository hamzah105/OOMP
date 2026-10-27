from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from benchmarks.adapters.corpus import prepare, scope_for
from benchmarks.adapters.memory import FlatLexical, FlatVector, LatestEight, OOMP, RollingSummary, convert, unit
from benchmarks.contracts import Config, Evidence, Result
from benchmarks.datasets.generate import eligible, generate
from benchmarks.metrics.scoring import path_scores, score, source_ranking, validate_result
from oomp.domain.models import AuthorizedScope, MemoryEvent, SourceReference
from oomp.ingestion import ExtractionPipeline
from oomp.retrieval.contracts import EmbeddingSpace, RetrievalRequest
from oomp.retrieval.engine import RetrievalEngine
from oomp.storage import SQLiteEventStore
from oomp.storage.errors import ScopeMismatchError


class SyntheticProvider:
    """Mechanics ONLY: never used in executed semantic quality experiments."""
    space=EmbeddingSpace(provider="synthetic",model="stage9-test",version="1",dimension=3)
    def embed(self,texts):
        return tuple((1.,0.,0.) if "project" in t.casefold() else (0.,1.,0.) if "amber" in t.casefold() else (0.,0.,1.) for t in texts)


@pytest.fixture(scope="module")
def corpus(tmp_path_factory):
    root=tmp_path_factory.mktemp("stage9-corpus")
    config=Config(name="adapter-test",seeds=(17,),sizes=(16,),evidence_budget=12000,summary_budget=12000)
    dataset=generate(config);histories={h.history_id:h for h in dataset.histories};cache={}
    for case in dataset.cases:
        h=histories[case.history_id];key=(h.history_id,tuple(e.event_id for e in eligible(h,case)))
        if key not in cache:
            db=root/f"corpus-{len(cache)}.sqlite3";p,costs,edges=prepare(h,case,db)
            cache[key]=(h,p,db,costs,edges)
    def get(suffix):
        c=next(c for c in dataset.cases if c.case_id.endswith(suffix));h=histories[c.history_id]
        return c,*cache[(h.history_id,tuple(e.event_id for e in eligible(h,c)))]
    return config,dataset,get


def test_latest_eight_exact_chronological_policy_and_recent_hit(corpus):
    config,d,get=corpus;c,h,p,db,_,_=get("-recent")
    result=LatestEight(p,config).retrieve(c)
    assert source_ranking(result.evidence)==tuple(e.event_id for e in p.events[-8:])
    assert c.relevant_source_event_ids[0] in source_ranking(result.evidence)
    validate_result(result,p,config)


def test_latest_eight_does_not_secretly_retrieve_earlier_sources(corpus):
    config,d,get=corpus;c,h,p,*_=get("-old-direct")
    result=LatestEight(p,config).retrieve(c)
    assert not set(c.relevant_source_event_ids)&set(source_ranking(result.evidence))


def test_latest_eight_budget_overflow_is_visible_failure(corpus):
    config,d,get=corpus;c,h,p,*_=get("-recent")
    small=config.model_copy(update={"evidence_budget":256})
    r=LatestEight(p,small).retrieve(c)
    assert r.status=="failed" and r.error_code=="latest_eight_budget_overflow" and not r.evidence


def test_rolling_summary_respects_update_schedule_budget_and_cutoff(corpus):
    config,d,get=corpus;c,h,p,*_=get("-known-before")
    adapter=RollingSummary(p,config);r=adapter.retrieve(c)
    validate_result(r,p,config)
    assert adapter.costs["summary_updates"]==len(p.events)//config.summary_update_every
    assert not set(source_ranking(r.evidence))&set(c.forbidden_source_event_ids)
    assert adapter.costs["summary_compression_ms"]>=0


def test_rolling_summary_preserves_recent_correction_as_attributed_text(corpus):
    config,d,get=corpus;c,h,p,*_=get("-preference-history")
    r=RollingSummary(p,config).retrieve(c)
    assert any("does not prefer" in e.content or "do not prefer" in e.content for e in r.evidence)
    assert all(e.temporal_status=="uninterpreted" for e in r.evidence)


def test_flat_lexical_real_fts_returns_source_grounded_old_project(corpus,tmp_path):
    config,d,get=corpus;c,h,p,*_=get("-old-direct")
    adapter=FlatLexical(p,config,tmp_path/"flat.sqlite3")
    try:
        result=adapter.retrieve(c);validate_result(result,p,config)
        assert set(c.relevant_source_event_ids)<=set(source_ranking(result.evidence))
        assert adapter.costs["flat_lexical_index_ms"]>=0
    finally:adapter.close()


def test_flat_lexical_does_not_get_governed_supersession(corpus,tmp_path):
    config,d,get=corpus;c,h,p,*_=get("-current")
    adapter=FlatLexical(p,config,tmp_path/"flat.sqlite3")
    try:
        r=adapter.retrieve(c)
        assert set(c.forbidden_source_event_ids)&set(source_ranking(r.evidence))
        assert all(e.temporal_status=="uninterpreted" for e in r.evidence)
    finally:adapter.close()


def test_flat_vector_synthetic_provider_ranking_and_shared_corpus(corpus):
    config,d,get=corpus;c,h,p,*_=get("-old-direct")
    adapter=FlatVector(p,config,SyntheticProvider());r=adapter.retrieve(c)
    assert set(c.relevant_source_event_ids)<=set(source_ranking(r.evidence))
    assert adapter.costs["vector_count"]==len(p.memories)
    assert adapter.costs["space"]==SyntheticProvider.space.model_dump(mode="json")
    validate_result(r,p,config)


@pytest.mark.parametrize("vector,dimension",[((0.,0.),2),((1.,),2),((float("nan"),1.),2),((True,1.),2)])
def test_flat_vector_rejects_invalid_vectors(vector,dimension):
    with pytest.raises(ValueError):unit(vector,dimension)


def test_missing_embeddings_are_unavailable_and_never_a_success(corpus):
    config,d,get=corpus;c,h,p,*_=get("-old-direct")
    r=FlatVector(p,config,None).retrieve(c)
    assert r.status=="unavailable" and not r.evidence
    assert score(c,r,p,config)["recall_at_k"]==0


def test_oomp_adapter_uses_real_extraction_and_persisted_canonical_proof(corpus):
    config,d,get=corpus;c,h,p,db,_,_=get("-old-direct")
    r=OOMP(h,p,config,db).retrieve(c);validate_result(r,p,config)
    assert set(c.relevant_source_event_ids)<=set(source_ranking(r.evidence))
    assert all(e.memory_id.startswith("mem-") for e in r.evidence)
    assert "lexical_candidates" in r.trace


def test_alias_only_query_uses_explicit_entity_identity_not_generic_project_words(corpus,tmp_path):
    config,d,get=corpus;c,h,p,db,_,_=get("-alias")
    flat=FlatLexical(p,config,tmp_path/"alias.sqlite3")
    try:
        assert not flat.retrieve(c).evidence
        result=OOMP(h,p,config,db).retrieve(c)
        assert set(c.relevant_source_event_ids)<=set(source_ranking(result.evidence))
        assert result.trace["entity_candidates"]>0
    finally:flat.close()


def test_curated_validity_without_explicit_source_annotation_is_rejected(tmp_path):
    config=Config(name="test-validity",seeds=(1,),sizes=(16,),categories=("temporal",))
    d=generate(config);h=d.histories[0]
    first=h.events[0].model_copy(update={"metadata":{"synthetic":True}})
    h=h.model_copy(update={"events":(first,*h.events[1:])})
    with pytest.raises(ValueError,match="explicitly established"):prepare(h,d.cases[0],tmp_path/"bad.sqlite3")


def test_same_canonical_input_and_model_space_for_flat_and_oomp_semantic(corpus):
    config,d,get=corpus;c,h,p,db,_,_=get("-old-direct");provider=SyntheticProvider()
    engine=RetrievalEngine(db,provider=provider);report=engine.index(scope_for(h),include_embeddings=True)
    flat=FlatVector(p,config,provider).retrieve(c)
    oomp=OOMP(h,p,config,db,"oomp_semantic",provider).retrieve(c)
    assert set(source_ranking(flat.evidence))==set(source_ranking(oomp.evidence))
    assert report.embeddings_failed==0


def test_current_temporal_evidence_and_historical_views_are_distinct(corpus):
    config,d,get=corpus
    for suffix in ("-current","-historical","-known-before"):
        c,h,p,db,_,edges=get(suffix);r=OOMP(h,p,config,db).retrieve(c)
        assert score(c,r,p,config,edges)["temporal_evidence_correct"]==1
        assert not set(source_ranking(r.evidence))&set(c.forbidden_source_event_ids)


def test_conflicts_preserve_competing_proof_and_actual_dispute_labels(corpus):
    config,d,get=corpus;c,h,p,db,_,edges=get("-dispute")
    r=OOMP(h,p,config,db).retrieve(c);s=score(c,r,p,config,edges)
    assert s["conflict_evidence_coverage"]==s["conflict_labeling"]==1
    assert all(e.temporal_status=="contradicted" for e in r.evidence if set(e.source_ids)&set(c.relevant_source_event_ids))


def test_unavailable_negative_query_is_not_credited_as_correct_abstention(corpus):
    config,d,get=corpus;c,h,p,db,_,edges=get("-never")
    s=score(c,Result(method="flat_vector",status="unavailable"),p,config,edges)
    assert s["correct_empty"]==0


def test_multihop_lexical_endpoint_hits_do_not_count_as_a_supported_path(corpus,tmp_path):
    config,d,get=corpus;c,h,p,*_=get("-2-hop")
    adapter=FlatLexical(p,config,tmp_path/"flat.sqlite3")
    try:
        r=adapter.retrieve(c)
        assert set(c.relevant_source_event_ids)<=set(source_ranking(r.evidence))
        assert path_scores(c,r,())["chain_completion"]==0
    finally:adapter.close()


def test_multihop_three_hop_requirement_exceeds_actual_configured_depth(corpus):
    config,d,get=corpus;c,h,p,db,_,edges=get("-3-hop")
    assert c.required_hops==3 and config.graph_depth==2
    r=OOMP(h,p,config,db).retrieve(c)
    assert all(len(path["edge_ids"])<=2 for e in r.evidence for path in e.paths)


def test_path_metric_accepts_actual_production_two_hop_chain_with_retained_proof(corpus):
    config,d,get=corpus;c,h,p,db,_,edges=get("-2-hop")
    # A mechanics test with one seed candidate exposes real structural paths.
    # Experiments keep the production default 40; this is not a reported ablation.
    response=RetrievalEngine(db).retrieve(scope_for(h),RetrievalRequest(tenant_id=h.tenant_id,
        namespace=h.namespace,query=c.query,candidate_limit=1,graph_depth=2,token_budget=12000))
    r=Result(method="mechanics-only",evidence=convert(response.memories,p.memories),packet=response.context_packet,
        packet_bytes=response.estimated_token_count)
    validate_result(r,p,config)
    metrics=path_scores(c,r,edges)
    assert metrics["chain_completion"]==1 and metrics["path_validity"]==metrics["source_proof_retention"]==1


def test_entity_topic_ablation_uses_a_session_wrapper_and_leaves_store_unchanged(corpus):
    config,d,get=corpus;c,h,p,db,_,_=get("-topic")
    full=OOMP(h,p,config,db).retrieve(c)
    ablated=OOMP(h,p,config,db,"oomp_no_augmentation").retrieve(c)
    assert full.trace["topic_candidates"]>0 and ablated.trace["topic_candidates"]==ablated.trace["entity_candidates"]==0
    again=OOMP(h,p,config,db).retrieve(c)
    assert source_ranking(again.evidence)==source_ranking(full.evidence)


def test_no_graph_ablation_does_not_disable_conflict_safety(corpus):
    config,d,get=corpus;c,h,p,db,_,edges=get("-dispute")
    r=OOMP(h,p,config,db,"oomp_no_graph").retrieve(c)
    assert score(c,r,p,config,edges)["conflict_labeling"]==1


def test_faithless_ablations_are_explicitly_unsupported(corpus):
    config,d,get=corpus;c,h,p,db,_,_=get("-old-direct")
    for method in ("flat_no_temporal","oomp_no_fusion"):
        assert OOMP(h,p,config,db,method).retrieve(c).status=="unavailable"


def test_tenant_scope_and_foreign_id_do_not_change_authorized_retrieval(corpus):
    config,d,get=corpus;c,h,p,db,_,_=get("-foreign")
    assert not p.events[0].event_id==c.forbidden_source_event_ids[0]
    r=OOMP(h,p,config,db).retrieve(c)
    assert not set(c.forbidden_source_event_ids)&set(source_ranking(r.evidence))
    wrong=AuthorizedScope(tenant_id="another-synthetic-tenant",namespace=h.namespace,principal_id="test")
    with pytest.raises(ScopeMismatchError):RetrievalEngine(db).retrieve(wrong,RetrievalRequest(tenant_id=h.tenant_id,namespace=h.namespace,query=c.query))


def test_provenance_forgery_is_rejected_before_scoring(corpus):
    config,d,get=corpus;c,h,p,*_=get("-old-direct")
    with pytest.raises(ValueError,match="foreign"):
        validate_result(Result(method="test",evidence=(Evidence(source_ids=("invented",),content="invented"),)),p,config)


def test_valid_source_id_cannot_launder_invented_evidence_text(corpus):
    import json
    config,d,get=corpus;c,h,p,*_=get("-recent")
    r=LatestEight(p,config).retrieve(c);payload=json.loads(r.packet)
    payload["memories"][0]["canonical_content"]="Fabricated answer with a real source ID"
    evidence=list(r.evidence);evidence[0]=evidence[0].model_copy(update={"content":payload["memories"][0]["canonical_content"]})
    # Converge the legitimate accounting fields to isolate the grounding guard.
    for _ in range(8):
        packet=json.dumps(payload,ensure_ascii=False,separators=(",",":"));payload["estimated_token_count"]=len(packet.encode("utf-8"))
    packet=json.dumps(payload,ensure_ascii=False,separators=(",",":"))
    forged=r.model_copy(update={"evidence":tuple(evidence),"packet":packet,"packet_bytes":len(packet.encode("utf-8"))})
    with pytest.raises(ValueError,match="not grounded"):validate_result(forged,p,config)


def test_inconsistent_evidence_budget_counter_is_rejected(corpus):
    config,d,get=corpus;c,h,p,*_=get("-recent")
    r=LatestEight(p,config).retrieve(c)
    with pytest.raises(ValueError,match="counter"):validate_result(r.model_copy(update={"packet_bytes":1}),p,config)


def test_actual_known_at_excludes_a_later_recorded_event_even_when_backdated(tmp_path):
    config=Config(name="known-at",seeds=(17,),sizes=(16,),categories=("long_history",))
    d=generate(config);h=d.histories[0];c=d.cases[0];p,_,_=prepare(h,c,tmp_path/"known.sqlite3")
    before=datetime.now(timezone.utc)
    e=MemoryEvent(event_id="later-recorded",tenant_id=h.tenant_id,namespace=h.namespace,
        event_type="user_message",source_type="user",content="FutureProbe uses amber component.",
        occurred_at=h.events[0].occurred_at,ingested_at=h.events[0].ingested_at,
        source_reference=SourceReference(source_system="stage9-synthetic",external_event_id="later-recorded",timestamp=h.events[0].occurred_at))
    SQLiteEventStore(tmp_path/"known.sqlite3").append(scope_for(h),e)
    ExtractionPipeline(tmp_path/"known.sqlite3").process_event(scope_for(h),e.event_id)
    response=RetrievalEngine(tmp_path/"known.sqlite3").retrieve(scope_for(h),RetrievalRequest(
        tenant_id=h.tenant_id,namespace=h.namespace,query="FutureProbe amber",known_at=before,token_budget=12000))
    assert not response.memories


def test_preparation_never_reuses_existing_database_or_default_path(corpus):
    config,d,get=corpus;c,h,p,db,*_=get("-recent")
    with pytest.raises(ValueError,match="new explicit"):prepare(h,c,db)


def test_costs_are_observed_or_explicitly_null(corpus):
    config,d,get=corpus;c,h,p,db,costs,_=get("-recent")
    assert costs["source_ingestion_ms"]>0 and costs["database_bytes"]>0
    assert costs["canonicalization_ms"] is None and costs["trigger_lexical_index_ms"] is None
