# Stage 3 extraction and canonicalization

Stage 3 is a synchronous, deterministic subsystem. It reads already stored immutable events and creates attributed, unverified canonical memories. It does not verify objective truth, infer a complete biography, search a graph or run a model.

## Pipeline and interfaces

1. The trusted caller supplies AuthorizedScope; the pipeline revalidates it.
2. SQLiteEventStore retrieves the requested event inside both tenant and namespace.
3. Eligibility policy checks role, input bounds, question markers and recognizable secrets.
4. DeterministicExtractor creates immutable MemoryCandidate values with actual source IDs and exact SourceSpan evidence.
5. The pipeline validates every proposal, including injected-provider output, against independently derived supported candidates. An unknown type, wrong scope/reference/span, invented claim, entity, qualifier or measured-confidence claim fails before persistence.
6. Canonicalization produces a MemoryNode with a scoped versioned key and source attribution.
7. SQLiteMemoryStore.apply_batch resolves entities and inserts/reuses memories, evidence and entity associations in one transaction.
8. ProcessingResult reports actual created/reused rows and newly added evidence.

The original Stage 1 MemoryExtractor.extract(scope,events) interface is implemented as pure derivation returning nodes. CandidateExtractor.extract_candidates(scope,event) is the validated proposal seam used by ExtractionPipeline. Neither extractor owns database write authority. SQL resides in storage. Candidate extraction and the default pipeline make no network calls.

## Supported deterministic constructions

Patterns match whole recognized statements; fixed lead-in phrases are case insensitive except the technical subject rule. Unicode evidence and objects are preserved. The extractor splits on sentence punctuation, trims boundary whitespace and handles a final statement without punctuation. This is a small recognizer, not a general language parser.

| Source construction | Type | Canonical rendering |
| --- | --- | --- |
| I prefer Python for local AI development. | profile | User prefers Python for local AI development. |
| I do not prefer Python. / I don't prefer Python. | profile | User does not prefer Python. |
| I am developing a project called OOMP. | project_state | User is developing a project called OOMP. |
| I am developing a project called OOMP (Object-Oriented Context Map). | project_state | Same OOMP statement, with an explicit project entity alias |
| OOMP uses an independent SQLite-backed memory store. | semantic | Original named-subject uses assertion, attributed to its source |
| We decided to keep OOMP independent from TRACE. | decision | We decided to keep OOMP independent from TRACE. |
| I am considering buying a 3D printer. | project_state | User is considering buying a 3D printer. |
| I plan to buy a 3D printer. | project_state | User plans to buy a 3D printer. |
| I purchased a 3D printer. | episodic | User purchased a 3D printer. |

The technical subject must begin with an ASCII capital letter and contain 2-64 ASCII letters/digits/underscore/hyphen; unsupported pronoun subjects are excluded. Technical claims do not automatically create technology entities. Explicit project names/aliases are limited to 128 characters by this extractor. Punctuation inside names, abbreviations or quoted prose can cause safe non-extraction; no robust quote/discourse parser is claimed.

Supported preference, project, considering, planning and purchase patterns require a user source. User messages, user corrections and user feedback are eligible. Documents support technical uses assertions and explicit decisions as document claims. Assistant, tool and system events are ineligible under the default policy, including through an injected extractor.

A question mark anywhere in an event skips default extraction for the whole event. Statements containing maybe, might, could, should, would, if, unless, hypothetical, possibly or perhaps are skipped. Unrecognized constructions such as conditional lead-ins or ordinary conversation yield no candidate. Considering and plans retain their modality; they never become completed purchases. Negation is retained. Unsupported certainty, dates, validity ranges and confidence are not invented.

## Resource and secret policy

Input is at most 16,384 Python Unicode characters. Larger events remain in the Stage 2 log but produce an empty processing result with a reason. At most the first 32 recognized statements become deterministic candidates; later statements are outside this call's extraction coverage. An injected provider returning more than 32 proposals is rejected. Candidate content/span quotes are bounded to 16,384 characters, entity hints to eight per candidate and aliases to eight per hint.

Recognizable passwords, API keys, bearer credentials, private-key headers, common credential prefixes and secret/token assignments cause whole-event exclusion. The heuristic deliberately favors omission; it is neither a comprehensive credential detector nor protection for the original source log. Direct trusted MemoryStore callers own their content policy.

Unsupported sentences never become candidates. ProcessingResult.skipped_candidates is zero in the current all-or-nothing candidate-validation policy; it is not a sentence count. An empty result does not imply the original event was absent or deleted.

## Canonical identity version 1

Canonical content uses Unicode NFC, collapses whitespace, trims outer whitespace and normalizes terminal periods to one period. Important words, names, case, negation and modality remain meaningful. Supported first-person patterns render a fixed User lead-in; arbitrary text is never case-folded or paraphrased.

The hash input is compact UTF-8 JSON:

~~~text
[tenant_id, namespace, memory_type, source_type, normalized_canonical_content]
~~~

SHA-256 produces canonical_key = v1:<64 hex digits> and memory_id = mem-<same digest>. Confidence is null, validity bounds are null, and record timestamps use the actual UTC processing time. Metadata contains attribution, verified=false and canonicalization_version=1. Source timestamps remain evidence timestamps and are not inferred fact dates.

Equivalent supported content in one partition reuses the first stored memory ID and unions source links. A new event repeating a preference adds a second reference. Reprocessing the same event adds neither a node nor a source/entity pair and preserves no-op timestamps. Negated preferences, considering versus purchased, source roles, types and scopes have distinct identities. Canonical-key collisions with different stable node payloads are rejected.

Entity resolution does not generally rewrite canonical text. OOMP and its spelled-out alias can share one entity while differently worded memories remain distinct. Explicit parenthetical annotation is removed from the supported project memory rendering, allowing that narrow construction to deduplicate. No embeddings, fuzzy name matching or general paraphrase equivalence are implemented. Future changes to version 1 normalization require an explicit compatibility/migration policy.

## Conservative entity identities

EntityType supports person, project, organization, technology, location and concept. The default extractor proposes only explicitly named projects. Direct trusted entity callers supply the type and literal same-scope source evidence.

Names normalize with NFC, collapsed whitespace and casefold within type and scope. Initial entity ID is ent_ plus the first 32 hex digits of SHA-256 over the storage canonical JSON of scope, type and normalized initial name. Reusing an explicit alias preserves the original ID and canonical display name. Name equality is a conservative local rule, not proof that two real-world people share an identity.

A parenthetical name/alias pair must occur in the exact source span. Names that already identify different records cause an alias conflict; no automatic merge occurs. Sam and Samuel stay separate. Java as technology and Java as location stay separate. The same name in separate tenants/namespaces has separate private identity. Alias records retain their first supporting source event. Alias sets are bounded to 64 and remain durable across reopening.

## Evidence, transactions and counters

Every memory source ID must resolve to an actual event in the authorized partition. Supplied SourceReferences must exactly match those stored events. Source links form a many-to-many relation and preserve insertion order, exact spans when supplied, and the extraction method. Readback reconstructs IDs and references together from the original events. Original content, event timestamps and fingerprints remain unchanged.

A per-event batch uses BEGIN IMMEDIATE for entity, memory, evidence and association changes. Any failure rolls back all derived writes for that event. The source event was ingested independently and stays stored. Concurrent writers rely on SQLite transactions and scoped uniqueness; no process-local cache/lock establishes identity. New evidence updates updated_at, while no-op retries preserve it. Counts report actual insert/reuse operations, not predictions; memory_ids contains unique retained identities.

MemoryStore put/upsert and attach_evidence are trusted persistence operations, not extraction recognizers. They verify source existence, scope, references and claim-attribution rules but cannot establish that arbitrary manually submitted canonical text is supported by the source's meaning. Use ExtractionPipeline for the default grounding policy.

## Optional model status

No Ollama, local inference transport, timeout/model configuration, cloud API or provider package is implemented. CandidateExtractor and strict MemoryCandidate are the provider-independent adapter interface. Tests use injected fake proposals without a live server. The pipeline currently permits only the same deterministic transformations, so a future model cannot expand supported semantics without an explicitly reviewed grounding policy. No weights are downloaded and no endpoint is configured by default.

## Manual use and Stage 4 handoff

~~~powershell
.\\.venv\\Scripts\\python.exe examples\\stage3_memory_extraction.py --db .\\data\\stage3-synthetic.sqlite3
.\\.venv\\Scripts\\oomp.exe memory extract --tenant tenant-stage3-example --namespace synthetic --event-id preference-1 --db .\\data\\stage3-synthetic.sqlite3
.\\.venv\\Scripts\\oomp.exe memory list --tenant tenant-stage3-example --namespace synthetic --db .\\data\\stage3-synthetic.sqlite3
.\\.venv\\Scripts\\oomp.exe memory list --tenant tenant-stage3-example --namespace synthetic --show-content --db .\\data\\stage3-synthetic.sqlite3
~~~

CLI scope is trusted local administrative intent, not network authentication. Default list output exposes IDs, types and evidence counts/source IDs; canonical content requires show-content. Storage initialization/upgrades are explicit. See [storage](storage.md), [security](security-model.md) and [validation](stage3-validation.md).

Stage 4 must define semantic relationship persistence, endpoint/provenance validation, temporal conflict/supersession policy, traversal bounds and graph transaction behavior before implementation. It must preserve Stage 3 source evidence and scoped identities. Memory-to-entity associations are not a completed temporal graph. Stages 4-10 remain outside this work.

## Stage 4 integration boundary

Stage 4 uses existing canonical memories and their original source evidence; it does not expand these extraction rules. The temporal-graph example creates unsupported RAM memories through the documented trusted MemoryStore API with actual stored SourceReferences and explicit validity.

Conservative conflict policy independently recognizes only its documented source-backed slot grammar. It does not accept arbitrary extraction/model metadata as a verified claim slot. Graph assertions and topic memberships preserve canonical memory IDs. [Temporal graph and governance](temporal-graph.md) describes the separate policy, confirmation and recording-time boundaries. Hybrid retrieval remains Stage 5.
