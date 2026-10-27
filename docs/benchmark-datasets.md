# Synthetic benchmark datasets

Generator: `benchmarks.datasets.generate`, version `stage9-synthetic-v1`.
Fixtures are authored for this repository under its Apache-2.0 license. They
contain no private conversations, real contact details or credentials. Case,
history, source, entity and topic IDs are deterministic. The same normalized
configuration and generator produce byte-equivalent dataset JSON and SHA-256.

Each immutable `History` stores seed, split, fictional scope, knowledge-ordered
source events, optional explicit curated observations, links and topics. Each
`Case` stores query, source cutoff, known/valid instants, expected acceptable
answers, relevant/forbidden source IDs, answerability, fact distance, latest-eight
availability, fixture layer, semantic label and an ordered required source chain.
Every relevant ID must exist in the eligible prefix. Cases/IDs cannot duplicate;
missing, foreign, excluded or future labels and invented graph chains fail
validation. A query copied verbatim into source text is rejected.

One interaction is one synthetic user-source observation. There is no fabricated
assistant response paired with it. Assistant-only noise is explicitly excluded
by the common source policy. TRACE's real application stores interaction pairs;
the pure formatter bridge renders empty assistant fields for this synthetic
source-only study. This simplification must not be called a complete application
conversation benchmark.

| Family | Construction and labels |
| --- | --- |
| Long history | Early named project plus explicit alias, exact duplicate corroboration, direct/paraphrased/alias-only questions, recent preference control. Relevant ages vary with size and positions; project duplicate sources share one canonical node. |
| Temporal | Fictional RAM report, explicit upgrade, source-authored reported validity bounds, current/historical/known-before questions and a late-arriving archive fact. Only the supported RAM grammar receives governed supersession. |
| Contradiction | Two incompatible, overlapping structured RAM reports, an unrelated computer that is not the same entity, and an uncertain modal report. Competing sources are both relevant; no authoritative winner is invented. |
| Multi-hop | Four nodes, three source-backed dependency links, a related irrelevant neighbor, explicit shared topic and two-/three-hop requests. Three hops exceeds the configured continuous neighborhood depth of two. Endpoint relevance and actual path completion score separately. |
| Negative | Never-mentioned purchase, foreign tenant, excluded assistant claim and future assertion. Correct evidence behavior is empty retrieval; infrastructure failure is not abstention success. |
| Noisy | Repetition, changed positive/negative preference, modal question, quoted third-party text, assistant suggestion and harmless instruction-injection marker. Claims remain untrusted data. |

RAM statement text alone does **not** establish validity intervals. These fixtures
include explicit `reported_validity` metadata as part of the authored source
observation; the curated adapter verifies exact agreement before writing a
memory. All canonical methods receive the same validity bounds, and raw baseline
evidence also retains those source bounds. Plain extracted facts keep validity
unknown. This is a curated temporal retrieval study, not automated natural-language
temporal extraction. Overlaps intentionally test disputes and supersession.

History sizes 16, 64, 128, 512 and 1024 are supported. The smoke uses 128, leaving
over 100 turns after an early fact. The primary held-out run uses 16 and 128 for
CPU/disk feasibility. The scaling config offers all sizes; it is not automatically
run or reported as measured. Each fourth ordinary turn is an extractable distractor,
so canonical search faces competing content rather than an otherwise empty index.

Development seed 11, validation seeds 43/47 and held-out seeds
1009/1013/1019/1021 use different stream identities, project/alias values and
fictional timeline offsets. Generator PRNG streams additionally depend on size,
category and split. The long-history query templates differ across splits.
Temporal/conflict templates and the production-supported grammar remain related;
full template disjointness is **not** achieved. The author knows the generator,
so held-out means not used for tuning, not independently authored unseen data.

No future source is indexed: prefix materialization uses the minimum knowledge
cutoff and explicit known-at label, never occurrence time alone. A late report can
describe a date before the cutoff while still being unavailable then. `fact_distance`
uses the visible cutoff position, not the full history's future tail. Ground-truth
answers and relevance labels never enter retrieval calls or generation templates.
They are scored only after retrieval/generation. Dataset JSON is frozen before
execution, and its digest is repeated in every query record.

The controlled graph fixtures contain explicit trusted edges; they do not assert
automatic dependency extraction or general entity resolution. Multi-hop wording
shares component vocabulary, so direct lexical endpoint recall is a deliberate
control. A complete path still needs actual returned edge IDs, relation direction
and original source proof. This distinction can produce high source recall with
zero supported-chain completion and must be preserved in the report.
