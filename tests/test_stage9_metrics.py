from __future__ import annotations

import math

import pytest

from benchmarks.analysis.statistics import aggregate, cluster_interval, distribution
from benchmarks.contracts import Case, Config, Evidence, Result
from benchmarks.metrics.scoring import answer_scores, path_scores, retrieval_scores, source_ranking


def test_recall_precision_and_missing_rank_denominators():
    s=retrieval_scores(("a","x"),("a","b"),4)
    assert s["recall_at_k"]==.5 and s["precision_at_k"]==.25


def test_mrr_first_hit_rank_and_miss():
    assert retrieval_scores(("x","y","a"),("a",),4)["mrr"]==pytest.approx(1/3)
    assert retrieval_scores((),("a",),4)["mrr"]==0


def test_ndcg_binary_ranks_and_ideal_denominator():
    s=retrieval_scores(("x","a","b"),("a","b"),3)
    assert s["ndcg_at_k"]==pytest.approx((1/math.log2(3)+.5)/(1+1/math.log2(3)))


def test_source_duplicates_do_not_inflate_scores():
    s=retrieval_scores(("a","a","b"),("a","b"),2)
    assert s["recall_at_k"]==s["ndcg_at_k"]==1
    ranking=source_ranking((Evidence(source_ids=("a","b"),content="one"),Evidence(source_ids=("b",),content="two")))
    assert ranking==("a","b")


def test_empty_and_unanswerable_are_not_positive_recall():
    s=retrieval_scores(("x",),(),8)
    assert all(v is None for v in s.values())
    miss=retrieval_scores((),("a",),8)
    assert set(miss.values())=={0}


def test_evidence_hit_and_truncation_at_k():
    assert retrieval_scores(("x","a"),("a",),1)["evidence_hit"]==0
    assert retrieval_scores(("x","a"),("a",),2)["evidence_hit"]==1


def test_invalid_k_is_rejected():
    with pytest.raises(ValueError):retrieval_scores((),(),0)


def test_answer_exact_match_and_normalized_multiset_f1():
    s=answer_scores("Amber, amber mode!",("amber mode",),"answerable")
    assert s["exact_match"]==0 and s["token_f1"]==pytest.approx(.8)
    assert answer_scores("4 GB",("4 gb",),"answerable")["exact_match"]==1


def test_duplicate_answer_references_do_not_change_best_match():
    a=answer_scores("amber",("amber","copper"),"answerable")
    assert a==answer_scores("amber",("amber","copper","amber"),"answerable")


def test_failed_live_generation_cannot_receive_abstention_or_match_credit():
    s=answer_scores("UNKNOWN",(),"unanswerable",status="failed")
    assert s["correct_abstention"]==s["exact_match"]==s["token_f1"]==0


def test_unsupported_assertions_are_not_falsely_automatically_judged():
    s=answer_scores("I know everything",("amber",),"answerable")
    assert s["unsupported_assertion_rate"] is None and s["requires_blinded_human_review"]


def test_citation_alignment_does_not_credit_invented_source():
    assert answer_scores("Amber [a] [invented]",("amber",),"answerable",("a",))["citation_alignment"]==.5
    assert answer_scores("Amber [a]",("amber",),"answerable",("a",))["exact_match"]==1


@pytest.mark.parametrize("alter,valid",[(None,True),("proof",False),("direction",False),("edge",False)])
def test_real_path_shape_proof_and_orientation_required(alter,valid):
    case=Case(case_id="path-test",history_id="h",category="multihop",query="fictional chain",
        history_cutoff="2026-01-01T00:00:00Z",answerability="answerable",latest_eight_available=True,
        relevant_source_event_ids=("a","b","c"),expected_answers=("c",),required_chain=(("a","b"),("b","c")),required_hops=2)
    edges=[{"edge":{"edge_id":e,"source_node_id":a,"target_node_id":b,"relationship_type":"DEPENDS_ON"},
        "evidence":[{"event_id":p}]} for e,a,b,p in (("ab","ma","mb","proof-ab"),("bc","mb","mc","proof-bc"))]
    path={"node_ids":["ma","mb","mc"],"node_source_ids":[["a"],["b"],["c"]],"edge_ids":["ab","bc"],
        "relationships":["DEPENDS_ON","DEPENDS_ON"],"directions":["forward","forward"],"proof_ids":[["proof-ab"],["proof-bc"]]}
    if alter=="proof":path["proof_ids"][1]=[]
    if alter=="direction":path["directions"][1]="reverse"
    if alter=="edge":path["edge_ids"][1]="invented"
    result=Result(method="test",evidence=(Evidence(source_ids=("a","b","c"),content="fixture",paths=(path,)),))
    s=path_scores(case,result,edges)
    assert s["chain_completion"]==int(valid)
    assert s["relevant_hops_recovered"]==(2 if valid else 1)


def cluster_rows():
    return [{"history_id":h,"metrics":{"x":v}} for h,v in (("h1",0),("h1",1),("h2",1),("h3",0))]


def test_bootstrap_seeded_reproducibility_and_cluster_count():
    a=cluster_interval(cluster_rows(),"x",samples=500,seed=9)
    assert a==cluster_interval(cluster_rows(),"x",samples=500,seed=9)
    assert a["histories"]==3 and a["cases"]==4 and a["mean"]==.5
    assert a["ci95"][0]<=a["mean"]<=a["ci95"][1]


def test_bootstrap_single_independent_history_has_no_interval():
    a=cluster_interval(cluster_rows()[:2],"x")
    assert a["mean"]==.5 and a["ci95"] is None


def test_bootstrap_empty_metric_is_not_filled_with_fabricated_samples():
    a=cluster_interval([{"history_id":"h","metrics":{"x":None}}],"x")
    assert a=={"mean":None,"ci95":None,"cases":0,"histories":0}


def test_tail_percentiles_require_sample_support():
    assert distribution(range(19))["p95"] is None
    assert distribution(range(20))["p95"] is not None
    assert distribution(range(99))["p99"] is None
    assert distribution(range(100))["p99"] is not None
    assert distribution([1])["stdev"] is None


def test_paired_effect_uses_same_cases_and_keeps_failed_queries():
    config=Config(name="test",seeds=(1,),methods=("trace_n8","oomp_full"),bootstrap_samples=100)
    rows=[]
    for h in ("h1","h2"):
        for method,value,status in (("oomp_full",1,"ok"),("trace_n8",0,"failed")):
            rows.append({"case_id":h,"history_id":h,"method":method,"repetition":0,"status":status,"category":"test",
                "metrics":{"recall_at_k":value},"retrieval_ms":1,"phase":"first_query","packet_bytes":0})
    out=aggregate(rows,config)
    assert out["paired_effects"]["oomp_full-minus-trace_n8"]["mean"]==1
    assert out["methods"]["trace_n8"]["metrics"]["recall_at_k"]["cases"]==2
