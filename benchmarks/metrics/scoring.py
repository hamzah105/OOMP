from __future__ import annotations

import json
import math
import re
from collections import Counter


DEFINITIONS={
    "recall_at_k":"unique relevant source IDs in first k distinct retrieved source IDs / all labeled relevant IDs; null on negatives",
    "precision_at_k":"relevant IDs in first k distinct source IDs / k; missing ranks count zero; null on negatives",
    "mrr":"reciprocal first relevant distinct source rank; zero for missing/failed results; null on negatives",
    "ndcg_at_k":"binary source gain / log2(rank+1), divided by ideal DCG at k; null on negatives",
    "evidence_hit":"any labeled relevant source returned at k; null on negatives",
    "provenance_correctness":"returned distinct source IDs resolving to the eligible prefix / returned distinct source IDs; null on empty",
    "query_coverage":"status ok AND at least one returned evidence object, all cases included",
    "correct_empty":"successful empty retrieval on unanswerable cases; failures/unavailable do not receive abstention credit",
    "false_memory_match":"nonempty successful retrieval on unanswerable cases (topical but non-answering context also counts)",
    "temporal_evidence_correct":"all required sources recovered and no forbidden state, retrieval evidence only, NOT answer accuracy",
    "known_at_fidelity":"successful result with no source outside frozen known-at prefix; failures count zero",
    "current_state_evidence_correctness":"temporal_evidence_correct on current-state fixtures only; not generated-answer correctness",
    "historical_state_evidence_correctness":"temporal_evidence_correct on historical fixtures only",
    "superseded_claim_handling":"current-state required evidence present and superseded forbidden source absent",
    "late_arrival_recall":"source-level recall@k on late-arriving report queries only",
    "temporal_abstention":"successful empty retrieval on the unsupported uncertain RAM claim query",
    "conflict_evidence_coverage":"all competing labeled source claims returned on disputed queries, independent of authoritative answer claims",
    "conflict_labeling":"all competing claims returned and marked contradicted; uninterpreted raw evidence is not credited",
    "chain_completion":"all required source endpoints and all required fixture edge pairs returned with actual edge/proof validation",
    "path_validity":"actual returned edge segments matching stored endpoint IDs, orientation, relation and nonempty exact proof / all returned segments; zero if required but absent",
    "relevant_hops_recovered":"number of distinct required undirected fixture edge pairs recovered through valid returned segments",
    "irrelevant_expansion_rate":"returned validated segments outside required chain / all returned segments, including invalid segments as irrelevant",
    "source_proof_retention":"returned edge segments retaining nonempty exact original edge proof / all returned segments",
    "exact_match":"max normalized exact match over distinct acceptable references, failed generations always zero",
    "token_f1":"max multiset normalized token F1 over distinct acceptable references, failed generations always zero",
    "unsupported_assertion_rate":"null unless blinded human review is supplied; lexical references cannot determine factual support of arbitrary prose",
    "citation_alignment":"fraction of syntactically valid [source-id] citations present in supplied evidence; null if no citations",
}


def source_ranking(evidence):
    # Evidence order, then the stable stored source order within a consolidated node.
    return tuple(dict.fromkeys(s for item in evidence for s in item.source_ids))


def retrieval_scores(retrieved,relevant,k):
    if type(k) is not int or k<=0:raise ValueError("k must be positive")
    ranking=tuple(dict.fromkeys(retrieved))[:k]; truth=set(relevant)
    if not truth:return dict.fromkeys(("recall_at_k","precision_at_k","mrr","ndcg_at_k","evidence_hit"),None)
    hits=[int(s in truth) for s in ranking]; found=sum(hits)
    dcg=sum(h/math.log2(i+2) for i,h in enumerate(hits))
    ideal=sum(1/math.log2(i+2) for i in range(min(k,len(truth))))
    return {"recall_at_k":found/len(truth),"precision_at_k":found/k,
        "mrr":next((1/(i+1) for i,h in enumerate(hits) if h),0.0),
        "ndcg_at_k":dcg/ideal,"evidence_hit":float(found>0)}


def validate_result(result,prepared,config):
    sources={e.event_id:e for e in prepared.events}
    nodes={m.memory_id:m for m in prepared.memories}
    if result.packet_bytes!=len(result.packet.encode("utf-8")) or result.packet_bytes>config.evidence_budget:
        raise ValueError("evidence budget/counter mismatch")
    if not set(source_ranking(result.evidence)) <= set(sources):
        raise ValueError("retrieved foreign, future or excluded source")
    if result.status!="ok" and (result.evidence or result.packet):
        raise ValueError("unsuccessful result cannot supply scored evidence")
    if not result.evidence:
        if result.packet:raise ValueError("packet/evidence mismatch")
        return
    packet=json.loads(result.packet)
    if packet["estimated_token_count"]!=result.packet_bytes or packet["token_budget"]!=config.evidence_budget:
        raise ValueError("packet accounting fields mismatch")
    items=packet["memories"]
    if len(items)!=len(result.evidence):raise ValueError("packet/evidence count mismatch")
    if len(items)>(8 if result.method=="trace_n8" else config.max_results):
        raise ValueError("result count exceeded")
    for item,returned in zip(items,result.evidence,strict=True):
        ids=item["source_event_ids"]; refs=item["source_references"]
        if tuple(ids)!=returned.source_ids or item["canonical_content"]!=returned.content or len(refs)!=len(ids):
            raise ValueError("packet/evidence source mismatch")
        identity=item["memory_id"]
        if identity.startswith("raw-") and len(ids)==1 and identity=="raw-"+ids[0]:
            grounded_content=sources[ids[0]].content
        elif identity in nodes and set(ids)<=set(nodes[identity].source_event_ids):
            grounded_content=nodes[identity].canonical_content
        else:raise ValueError("evidence identity does not resolve to the supplied corpus")
        if returned.content!=grounded_content:
            raise ValueError("evidence content is not grounded in the supplied corpus")
        for source_id,reference in zip(ids,refs,strict=True):
            if reference!=sources[source_id].source_reference.model_dump(mode="json",exclude_none=True):
                # Pydantic exclude_none used by production packing also removes optional nulls.
                reference={k:v for k,v in reference.items() if v is not None}
                if reference!=sources[source_id].source_reference.model_dump(mode="json",exclude_none=True):
                    raise ValueError("incorrect source reference")


def path_scores(case,result,edges):
    if not case.required_chain:return {k:None for k in ("chain_completion","path_validity","relevant_hops_recovered","irrelevant_expansion_rate","source_proof_retention")}
    actual={r["edge"]["edge_id"]:r for r in edges}
    required={frozenset(pair) for pair in case.required_chain}
    returned_segments={}
    for item in result.evidence:
        for path in item.paths:
            for i,edge_id in enumerate(path["edge_ids"]):
                # Identical repeated path segments do not inflate hop recovery.
                key=(edge_id,path["node_ids"][i],path["node_ids"][i+1])
                returned_segments[key]=(path,i)
    valid=proofs=irrelevant=0; recovered=set()
    for (edge_id,a,b),(path,i) in returned_segments.items():
        record=actual.get(edge_id)
        if record is None:
            irrelevant+=1;continue
        edge=record["edge"]
        expected_direction="forward" if (a,b)==(edge["source_node_id"],edge["target_node_id"]) else "reverse"
        endpoints={a,b}=={edge["source_node_id"],edge["target_node_id"]}
        actual_proof={x["event_id"] for x in record["evidence"]}
        proof=set(path["proof_ids"][i])
        has_proof=bool(proof) and proof==actual_proof
        proofs+=int(has_proof)
        is_valid=endpoints and path["directions"][i]==expected_direction and path["relationships"][i]==edge["relationship_type"] and has_proof
        valid+=int(is_valid)
        matches={frozenset((x,y)) for x in path["node_source_ids"][i] for y in path["node_source_ids"][i+1]}
        selected=matches & required if is_valid else set()
        recovered.update(selected)
        irrelevant+=int(not selected)
    n=len(returned_segments)
    complete=required<=recovered and set(case.relevant_source_event_ids)<=set(source_ranking(result.evidence))
    return {"chain_completion":float(complete and result.status=="ok"),"path_validity":valid/n if n else 0.0,
        "relevant_hops_recovered":len(recovered),"irrelevant_expansion_rate":irrelevant/n if n else 0.0,
        "source_proof_retention":proofs/n if n else 0.0}


def score(case,result,prepared,config,edges=()):
    ranking=source_ranking(result.evidence) if result.status=="ok" else ()
    scores=retrieval_scores(ranking,case.relevant_source_event_ids,config.metric_k)
    available={e.event_id for e in prepared.events}; good=result.status=="ok"
    scores.update(provenance_correctness=len(set(ranking)&available)/len(ranking) if ranking else None,
        query_coverage=float(good and bool(ranking)),
        correct_empty=float(good and not ranking) if case.answerability=="unanswerable" else None,
        false_memory_match=float(good and bool(ranking)) if case.answerability=="unanswerable" else None,
        successful_query=float(good))
    all_found=set(case.relevant_source_event_ids)<=set(ranking)
    no_forbidden=not bool(set(ranking)&set(case.forbidden_source_event_ids))
    scores["temporal_evidence_correct"]=float(good and all_found and no_forbidden) if case.fixture_layer=="curated_temporal" else None
    scores["known_at_fidelity"]=float(good and set(ranking)<=available) if case.known_at else None
    task=case.case_id.removeprefix(case.history_id+"-")
    scores["current_state_evidence_correctness"]=scores["temporal_evidence_correct"] if task=="current" else None
    scores["historical_state_evidence_correctness"]=scores["temporal_evidence_correct"] if task=="historical" else None
    scores["superseded_claim_handling"]=scores["temporal_evidence_correct"] if task=="current" else None
    scores["late_arrival_recall"]=scores["recall_at_k"] if task=="late-arrival" else None
    scores["temporal_abstention"]=float(good and not ranking) if task=="uncertain" else None
    scores["conflict_evidence_coverage"]=float(good and all_found) if case.answerability=="disputed" else None
    competing=[x for x in result.evidence if set(x.source_ids)&set(case.relevant_source_event_ids)]
    scores["conflict_labeling"]=float(good and all_found and bool(competing) and all(x.temporal_status=="contradicted" for x in competing)) if case.answerability=="disputed" else None
    scores.update(path_scores(case,result,edges))
    return scores


def normalized(text):
    return re.findall(r"\w+",text.casefold(),re.UNICODE)


def answer_scores(answer,references,answerability,evidence_ids=(),status="ok"):
    refs=list(dict.fromkeys(references))
    # Citation syntax is scored independently, so citation IDs do not penalize
    # exact-match/F1 of an otherwise correct short answer.
    tokens=normalized(re.sub(r"\[[A-Za-z0-9_-]+\]","",answer))
    abstentions={"unknown","not in current session memory","insufficient evidence","i do not know"}
    abstained=" ".join(tokens) in abstentions
    if answerability=="unanswerable":refs=list(abstentions)
    exact=f1=0.0
    if status=="ok":
        for ref in refs:
            target=normalized(ref)
            exact=max(exact,float(tokens==target))
            overlap=sum((Counter(tokens)&Counter(target)).values())
            score=2*overlap/(len(tokens)+len(target)) if tokens or target else 1.0
            f1=max(f1,score)
    citations=re.findall(r"\[([A-Za-z0-9_-]+)\]",answer)
    return {"exact_match":exact,"token_f1":f1,
        "correct_abstention":float(status=="ok" and abstained) if answerability=="unanswerable" else None,
        "citation_alignment":sum(s in set(evidence_ids) for s in citations)/len(citations) if citations else None,
        "unsupported_assertion_rate":None,"contradiction_answer_correctness":None,
        "automatic_scoring_limited":True,"requires_blinded_human_review":True}
