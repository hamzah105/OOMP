# Object-Oriented Context Map: A Temporal, Provenance-Aware Memory Architecture for Long-Term AI Context Retrieval

**Working draft, not peer reviewed.** Prepared 2026-10-27 for human revision.
The title identifies scope, not novelty. Authors, affiliations, venue and
submission/data-release decisions require maintainer confirmation.

## 1. Abstract

OOMP separates immutable source events, attributed canonical memories, temporal
relationships and bounded evidence retrieval from answer generation. An internal
synthetic study compares recent-eight memory, extractive summaries, flat lexical
memory, optional vectors and the existing OOMP implementation. On 112 positive
queries from a 48-history/four-seed study, source Recall@8 was 0.9286 for OOMP,
0.7857 for flat lexical and 0.2381 for recent-eight memory. Restricted and partly
curated fixtures limit interpretation. Recent controls tied; neighborhood expansion
gave no measured recall/path gain. In a small real embedding study, flat vectors
and hybrid OOMP tied on four positives and both returned evidence for four
unanswerable queries. Live LLaMA answer quality was not evaluated. The artifact
supports limited retrieval observations and reproducible engineering, without
claiming universal superiority or improved final answers.

## 2. Introduction

A recent conversation window cannot directly supply facts that have left it.
Persistent retrieval can supply older evidence, while creating problems of source
selection, stale/conflicting claims, authorization, privacy and cost. OOMP explores
an explicit source-to-memory pipeline with provenance and temporal inspection.
This draft presents an implementation and a transparent internal study, rather
than claiming that persistence, retrieval or graph memory are new.

The engineering objective is to retain identities and proof across ingestion,
updates and application access. The research question is whether these structures
improve source-grounded evidence selection under comparable histories/budgets, and
where additional costs or failure modes appear.

## 3. Problem formulation

Given an authorized scope, eligible history before a knowledge cutoff, query and
evidence ceiling, a method returns source-backed context. Reported validity and
system recording time are distinct. Disputed claims may coexist; absent evidence
may require abstention. Source completeness, unique-fact correctness and generated
answer accuracy are different outcomes. The host must separately budget its full
prompt and evaluate the generator.

## 4. Related work

Retrieval-augmented generation joins generation with retrieved external information
[1]. Graph RAG investigates graph-derived structures and summaries for corpus-level
queries [2]. Mem0 describes persistent conversational memory and a graph-enhanced
variant [3]. Zep describes temporally aware graph memory [4]. These provide prior
art for the problem and several component ideas; no first/best claim is made.

OOMP's offline grammar and narrowly source-governed temporal policy differ from
general learned extraction. This is a scope difference, not evidence of superior
architecture. No external Mem0/Zep/GraphRAG adapter was executed. Their published
tasks, compute and permissions are different, so their numbers are not comparative
OOMP results. A systematic literature review and independent reproduction remain
future work.

## 5. System architecture

SQLite v5 persists original events. The extraction pipeline validates candidates
against actual source spans before canonical/evidence writes. Explicit entities,
topic memberships and source-backed relationships reference existing identities.
Retrieval combines scoped lexical/vector/entity/topic candidates, governed temporal
state and bounded neighborhoods, then packs complete evidence. Explicit leased
workers maintain derived state. The optional official-SDK MCP boundary serves
local applications; TRACE remains independent. [Architecture](architecture.md).

## 6. Evidence provenance and canonicalization

Events preserve original role, content, timestamps and source reference. Canonical
identity applies conservative normalization qualified by scope/type/attribution,
not unrestricted semantic equivalence. Supported repeated claims share a node and
retain actual corroborating sources. Claims remain unverified, and assistant
assertions cannot silently become user-profile evidence. Provenance supports an
audit of what was reported, not a proof that it is objectively true.

## 7. Temporal associative graph

Ordinary links are trusted attributed assertions with scoped endpoints and proof.
Protected contradiction/supersession requires supported source policy, explicit
confirmation and transactional revalidation. Current protected governance covers
structured RAM-state/upgrade reports, not general semantic conflicts. Unknown
validity stays uncertain. Known-at views use recording history; incomplete entity
association clocks disable that lane for historical knowledge requests. Curated
validity/graph input is disclosed rather than presented as automatic extraction.

## 8. Retrieval and context budgeting

Scoped SQLite FTS5/BM25 supplies lexical candidates. Optional semantic retrieval
requires a complete compatible vector space. Rank fusion combines lane positions
rather than adding incomparable raw scores. Relevant neighborhoods are bounded to
depth two; mandatory governance remains active with neighborhoods off. Whole
evidence includes IDs, source references and path proof. Items that cannot fit are
omitted rather than truncating claims/provenance. UTF-8 bytes are a conservative
accounting proxy, not exact model tokens; host/MCP overhead is additional. Ranking
scores are not truth probabilities.

## 9. Experimental methodology

The versioned generator supplies long-history, temporal, contradiction, multi-hop,
negative and noisy cases. All methods receive the same user-source scope/knowledge
prefix; canonical-memory methods use the same actual extracted/curated corpus.
Recent-eight sees only eight observations. Summary is deterministic extractive
compression every four observations, not a representative of all learned summaries.

The held-out study uses four seeds, sizes 16/128, 48 generated histories and
160 queries: 112 positive and 48 negative. Authored templates remain related
across splits. Primary measurement is distinct source Recall@8; precision, MRR,
nDCG, provenance, empty behavior, temporal evidence and structural paths are
separate. Unavailable/failed scheduled records remain visible. Common ceilings
are eight results and 12,000 complete UTF-8 evidence bytes.

Descriptive intervals use 2,000 seeded percentile resamples of whole histories,
preserving within-history dependence and method pairing. Repetition count is one.
A single positive history in the live vector sample cannot support an interval.
[Frozen methods](benchmark-methodology.md), [reviewed JSON](examples/stage9-results.json).

## 10. Results

| Offline method | Source Recall@8 | Descriptive 95% history-cluster interval |
| --- | ---: | --- |
| Recent-eight | 0.2381 | [0.1584, 0.3248] |
| Extractive summary | 0.2381 | [0.1584, 0.3248] |
| Flat lexical | 0.7857 | [0.7083, 0.8559] |
| OOMP lexical plus structure | 0.9286 | [0.8880, 0.9655] |

Paired OOMP-minus-N8 difference is 0.6905 [0.6012, 0.7817]; versus flat lexical,
0.1429 [0.0973, 0.1909]. These intervals condition on this generator and do not
establish population significance. Offline vectors are unavailable, not measured
zero-quality results. Every executed offline method recovered the eight recent
controls. Current-state evidence correctness was 1.0 for OOMP versus 0.0 for flat
lexical on eight curated RAM cases; historical correctness was 1.0 for both.
There is no isolated temporal-off switch. Lexical paraphrase misses remain.

The real `embeddinggemma:latest` sample contains two histories/eight queries.
Flat vector, hybrid OOMP and semantic OOMP each recover four positive cases and
return nonempty evidence on four negatives. No vector/OOMP recall advantage or
general semantic claim follows. No comparative LLaMA answers were generated.

Held-out successful warm medians were about 1.2407 ms (N8), 1.1364 ms (summary),
0.3670 ms (flat lexical) and 9.9438 ms (OOMP). Preparation, graph, summary and
embedding costs are recorded separately and must be included in amortized
comparisons. Concurrent desktop work, caches and one repetition limit timing
conclusions. [Original complete validation](stage9-validation.md).

## 11. Ablations

Full, neighborhood-off and the identical lexical control have recall 0.9286.
Entity/topic-off has 0.7857 on alias/topic fixtures. Complete supported chain
completion is 0/16 for full and neighborhood-off at default settings despite
lexical endpoint hits; ordinary paths for independently ranked nodes are not
attached. A separate mechanics test verifies a real two-hop path without changing
research settings. Three-hop tasks exceed configured continuous neighborhood depth.
Temporal/fusion-off lack faithful switches. Dedicated Stage 6 projections are not
consumed by recall, so a projection-off effect is not invented. Consolidation's
causal benefit remains inconclusive.

## 12. Threats to validity

Restricted authored grammar, curated structures, related splits, source-only
observations rather than full chat pairs, four seeds, one repetition and a small
live sample restrict generalization. One corroborating source can support a correct
answer with incomplete source recall. Structured path metrics favor path-exposing
protocols; flat relationship text may still support reasoning. No independent
annotation, blinded human review, large-scale execution or final-answer study is
available. Later tuning requires fresh held-out data rather than reusing favorable
results as unbiased evidence.

## 13. Security and privacy limitations

SQLite/derived data are plaintext. Trusted administrators and application scope
issuance remain required. MCP is loopback-focused, not an enterprise public-cloud
profile. Secret filtering does not remove original events. Logical erasure cannot
securely wipe WAL/free pages/backups/exports or recall returned data. Provider
retention and model prompt handling remain independent risks.
[Security review](security-review.md), [privacy](privacy-retention.md).

## 14. Discussion

The implementation demonstrates source identity, scoped durability and controlled
evidence selection. Selected cases favor persistent recall over a small recent
window, while recent cases tie and flat lexical retrieval is cheaper at query time.
Graph expansion has no measured gain here; real vectors do not separate OOMP
from a conventional baseline. Independent tasks, broader extraction coverage,
repeated isolated costs and real answer evaluation are needed for stronger claims.

## 15. Conclusion and assistance disclosure

OOMP provides an inspectable local artifact with explicit provenance, temporal
policy and bounded retrieval. Current evidence supports engineering acceptance
and limited synthetic retrieval observations, not universal superiority, human-
memory equivalence, infinite context or improved generated answers.

OpenAI Codex assisted implementation, documentation, test orchestration and this
draft. Measurements derive from executed artifacts; AI-generated text/tests are
not independent peer review. Human authors/maintainers must verify citations,
methods, attribution, data rights and final claims before submission.

## 16. References and verification status

Primary title/author/year/arXiv metadata checked on 2026-10-27. This is a bounded
check, not a systematic review. Exact software revisions and the full literature
review need independent verification before submission; no unverified venue/DOI
or product-performance comparison is invented.

1. Patrick Lewis et al. (2020). [Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks](https://arxiv.org/abs/2005.11401). arXiv:2005.11401.
2. Darren Edge et al. (2024). [From Local to Global: A Graph RAG Approach to Query-Focused Summarization](https://arxiv.org/abs/2404.16130). arXiv:2404.16130.
3. Prateek Chhikara, Dev Khant, Saket Aryan, Taranjeet Singh and Deshraj Yadav (2025). [Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory](https://arxiv.org/abs/2504.19413). arXiv:2504.19413.
4. Preston Rasmussen, Pavlo Paliychuk, Travis Beauvais, Jack Ryan and Daniel Chalef (2025). [Zep: A Temporal Knowledge Graph Architecture for Agent Memory](https://arxiv.org/abs/2501.13956). arXiv:2501.13956.

API sources: [SQLite FTS5](https://www.sqlite.org/fts5.html),
[Python SQLite backup](https://docs.python.org/3.11/library/sqlite3.html#sqlite3.Connection.backup),
[official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk).
