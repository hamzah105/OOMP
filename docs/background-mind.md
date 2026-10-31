# Background Mind Engine

Product P1 can explicitly supervise this unchanged worker as a separate process
with `oomp up --profile NAME`. See [the operator guide](product-onboarding.md).
Importing OOMP or connecting MCP still starts no worker. The manual procedures
below remain available for advanced independent ownership.

Stage 6 connects the immutable event log to explicit durable background work. It reuses Stage 3 extraction, Stage 4 governance and Stage 5 indexes. Importing OOMP starts no workers. Standard operation requires only Python, SQLite with FTS5 and the installed package.

## Authority and data flow

An operator supplies a trusted AuthorizedScope and worker configuration. Stored job scope and provider settings are validated data, not grants of authority. The local CLI relies on machine and filesystem access. There is no remote authenticator, listener, MCP transport or TRACE adapter.

~~~mermaid
flowchart TD
    E[Scoped event insert] --> O[Transactional outbox]
    O --> Q[Durable scoped jobs]
    Q --> W[Explicit bounded worker]
    W --> X[Existing extraction pipeline]
    X --> M[Canonical memories and actual evidence]
    M --> I[Existing lexical and optional vector indexes]
    I --> R[Existing Stage 5 recall]
    W --> S[Versioned extractive topic artifacts]
    W --> P[Pending conflict reviews]
    P --> A[Trusted confirmation and Stage 4 revalidation]
~~~

The model proposes intent or vectors. OOMP controls validation, policy, approval, durability and execution. Background work never automatically approves protected relationships.

## Intake, leases and recovery

Schema 5 extends genuine schema 4 without replacing source, memory, graph or index records. Historical migration definitions remain intact. An event INSERT creates outbox intake in the same transaction. Duplicate appends return the existing event; failed inserts roll back intake. Bounded explicit backfill handles older events. Discovery does not depend on occurrence time, so late arrivals remain eligible.

Dispatch and job identity use transactions and uniqueness constraints. Jobs contain identifiers and versioned configuration rather than copied message bodies. Queue backpressure leaves intake pending when further dispatch cannot be accepted.

Claims use BEGIN IMMEDIATE, a scoped ready query, bounded leases, worker identity and increasing fencing tokens. Renewal, completion and failure must match the valid owner, token and lease. Expired ownership is recoverable; a stale owner cannot acknowledge another claim. SQLite WAL coordinates processes on the same host, not multiple network hosts. [Transactions](https://www.sqlite.org/lang_transaction.html), [WAL](https://www.sqlite.org/wal.html).

Execution is **at least once**. Stage 3 and Stage 5 effects commit independently of job acknowledgement. A crash after an effect commits can replay it. Existing canonical identities, evidence uniqueness and compatible vector digests make persistent effects idempotent. No write transaction spans slow provider I/O. Cancellation cannot undo effects already committed.

Retries have bounded attempts and backoff. Job timing uses an injectable clock for deterministic tests. Invalid scope/evidence, schema incompatibility and unsupported policy are permanent failures. Temporary provider outages and database-busy conditions are distinguishable. Logs expose allowlisted error codes, not exception text or provider bodies. Administrative retry remains subject to policy and preserves attempt history.

## Extraction and maintenance

Extraction calls the existing ExtractionPipeline.process_event(scope,event_id). Eligibility, exact spans, independently checked transformations, canonical identity and attributed unverified claims retain Stage 3 semantics. Ineligible events and zero supported candidates can complete successfully.

New canonical memories already receive lexical rows through the Stage 5 trigger. Maintenance checks or repairs the existing index. Embeddings default to disabled. Opt-in jobs pin provider, model, configuration version and dimension and require matching trusted worker configuration. Missing vectors remain incomplete coverage. A later provider failure preserves lexical recall and earlier successful vectors. OOMP downloads no model.

Consolidation uses canonical keys and explicit topic memberships. It does not infer semantic equivalence, merge different claims, verify assertions or supersede facts from similarity. Complete source and output bounds prevent silently incomplete summaries.

## Summary revisions and reviews

Summaries are dedicated artifacts, outside canonical MemoryNode storage. One representation records actual memory IDs, event IDs, SourceReferences, attribution and uncertainty. Default summaries are deterministic and extractive. Unchanged support is a no-op; changed support creates an auditable revision. System recording time governs known_at. Retired or invalidated revisions cannot appear as current.

Stage 5 recall continues to return canonical memories; it does not automatically search or inject these separate artifacts. Summary inspection is explicit. No fabricated SUPERSEDES relationship connects summary revisions. Model-assisted summarization is deferred.

Background conflict inspection uses the existing Stage 4 pure policy for the documented exact test-computer RAM claims. It creates bounded deduplicated pending reviews, not universal semantic-conflict detection. Neither source is erased or automatically superseded. A trusted approval invokes the existing transactional Stage 4 confirmation path and revalidates current evidence.

## Correction, retraction and erasure

Corrections append actual events through the ordinary source API. They do not rewrite earlier messages. Retraction withdraws endorsement of evidence while retaining historical origin. It invalidates affected summaries and respects recording-time history and surviving independent support. Current recall excludes withdrawn support; an explicit known_at cutoff before its recorded retraction can still expose the earlier retained evidence. A historical validity request alone does not undo present-day retraction policy.

Erasure is privileged local administration: select an explicit scoped event, inspect a nonmutating dependency plan, then confirm that exact plan. Confirmation rechecks dependencies in one write transaction, removes affected local representations, preserves independently supported shared objects, cleans derived indexes, removes affected summary content and cancels work. Unsupported or excessive dependencies fail closed.

Ordinary event UPDATE/DELETE protection remains. Any privileged delete-trigger bypass is confined to the erasure transaction, restored before commit and rolled back on failure. Foreign keys remain enabled. Scoped tombstones block erased identity replay. Extraction/index writes revalidate actual source or memory existence inside write transactions; summary writes revalidate proof too. A paused worker cannot recreate a deleted source's derived records.

Logical erasure cannot recall data already returned to another process, remove external exports, or promise cryptographic secure deletion from SQLite free pages, WAL/SHM files, snapshots or backups. Deleted FTS5 entries can also leave forensic traces in index segments or shadow storage. Operators must apply backup/export retention separately. [SQLite deletion limits](https://www.sqlite.org/pragma.html#pragma_secure_delete), [FTS5 deletion behavior](https://www.sqlite.org/fts5.html#the_secure_delete_configuration_option). IDs in audits and tombstones can be sensitive. Neither erased source bodies nor their hashes belong in these records.

## Operations and next-stage boundary

Diagnostics show actual scoped job states, oldest pending age, last completion/error and supported intake/review metrics. Vector coverage refers to an explicitly selected model space. Doctor checks package readiness; it does not certify a running worker or successful inference.

Workers use bounded batches, attempts, leases, polling and SQLite busy timeouts, with sequential execution by default and explicit interruption. No daemon is installed or started automatically.

Before Stage 7 exposes any capability, it needs authenticated principal-to-scope mapping, tool policy, approval boundaries, resource limits and transport security. Privileged erasure is not a model-controlled remote forget tool.

Exact commands, executed validation and limitations are recorded in [Stage 6 validation](stage6-validation.md) and the [completion report](stage-6-report.md).


## Schema and resource controls

| Schema 5 table | Purpose |
| --- | --- |
| mind_event_outbox | One pending/dispatched intake identity per scoped event |
| mind_jobs | Restricted versioned work, status, attempts, availability, lease and fence |
| mind_job_attempts | Durable per-attempt owner/fence/start/end/status/error |
| mind_maintenance_audit | Scoped operation, policy, actor, status and affected-count audit |
| mind_summary_revisions | One current topic artifact plus retired revisions |
| mind_summary_sources | Actual scoped memory/event evidence for each revision |
| mind_review_proposals | Deduplicated pending/approved/rejected governed proposals |
| mind_retractions | Append-only withdrawal of particular memory/event support |
| mind_erased_events | Scoped erased event/idempotency identities, operation and operator |

Migration 5 adds eleven indexes and two triggers: transactional event intake and erased-identity replay protection. Existing migration SQL 1–4 and their ordinary immutability triggers remain unchanged.

| Operation | Default and hard bounds |
| --- | --- |
| Active jobs per trusted configuration | 1000; configurable 4–10000 |
| Outbox dispatch/backfill | At most 100 per call |
| Worker run-once | 16 claims; configurable 1–100 |
| Worker lease | 120 seconds; configurable 10–3600; queue API allows 1–3600 for explicit tests/admin use |
| Heartbeat | Lease/3, with a minimum of one second; worker SQLite busy timeout is one second |
| Attempts | 3; initial maximum 1–20; administrative transient retry extends within 20 |
| Retry delay | 1 second, doubling to a ceiling of 3600 seconds |
| Polling | 1 second; configurable 0.1–60, optional bounded cycle count |
| Summary | 16 direct memberships, 1000 proof pairs, 512 characters per canonical statement, 4096 output characters |
| Conflict inspection | 64 canonical memories by default (hard maximum 100); 16 proposals (maximum 32); at most four selected proof events per target |
| Erasure | At most 1000 total affected memory/source proof pairs; bounded 1000-row dependency categories and complete review scan |

Outbox dispatch reserves two active slots and downstream index/review jobs receive priority 10. This lets a sequential worker drain extraction followups without consuming all maintenance capacity. Queue-full is retryable; intake remains pending. Operators coordinating multiple workers should use consistent capacity settings. The global constructor ceiling remains 10000 active jobs.

Index work retains Stage 5's corpus, byte, vector and batch limits. It reuses the existing bounded scope scan rather than implementing per-memory embedding jobs. Compatible vector filling can take multiple batches; interruption preserves earlier commits.

## Local procedures

Create or explicitly migrate the chosen database before work. Every mind command requires --db, --tenant and --namespace. These examples use only the dedicated synthetic scope:

~~~powershell
.\.venv\Scripts\oomp.exe storage init --db .\data\stage6-synthetic.sqlite3
.\.venv\Scripts\python.exe examples\stage6_background_mind.py --db .\data\stage6-synthetic.sqlite3
.\.venv\Scripts\oomp.exe mind status --db .\data\stage6-synthetic.sqlite3 --tenant synthetic-demo --namespace stage6
.\.venv\Scripts\oomp.exe mind backfill --limit 100 --db .\data\stage6-synthetic.sqlite3 --tenant synthetic-demo --namespace stage6
.\.venv\Scripts\oomp.exe mind run-once --max-jobs 16 --max-pending 1000 --db .\data\stage6-synthetic.sqlite3 --tenant synthetic-demo --namespace stage6
.\.venv\Scripts\oomp.exe mind work --cycles 3 --poll-seconds 1 --max-jobs 16 --db .\data\stage6-synthetic.sqlite3 --tenant synthetic-demo --namespace stage6
.\.venv\Scripts\oomp.exe mind jobs --limit 50 --db .\data\stage6-synthetic.sqlite3 --tenant synthetic-demo --namespace stage6
.\.venv\Scripts\oomp.exe mind summary --topic-id topic-local-ai --db .\data\stage6-synthetic.sqlite3 --tenant synthetic-demo --namespace stage6
.\.venv\Scripts\oomp.exe mind consolidate --topic-id topic-local-ai --db .\data\stage6-synthetic.sqlite3 --tenant synthetic-demo --namespace stage6
.\.venv\Scripts\oomp.exe mind reviews --db .\data\stage6-synthetic.sqlite3 --tenant synthetic-demo --namespace stage6
~~~

Mind jobs returns a bounded latest slice; reviews returns a bounded oldest pending slice that drains as decisions are recorded. Decisions look up a proposal directly and do not require loading the whole backlog. Statistics include actual pending-review count. Topic-needs-consolidation is not advertised as a computed metric. Use retrieval status with an explicitly selected embedding space for vector coverage.

Enqueue requires a target and explicit generation, for example mind enqueue --type consolidate_topic --target-id topic-local-ai --generation operator-run-1 followed by the common database/scope flags. Identical scope/type/target/policy/generation is idempotent; incompatible configuration collides. A new intentional run needs a new generation. Use mind retry --job-id ID only for eligible terminal transient failures, or mind cancel --job-id ID for active work.

Reviews require --action approve or reject, --proposal-id ID and --confirm. Approval commits both the existing transactionally revalidated Stage 4 relationship and its review decision atomically. Retraction uses mind retract --memory-id ID --event-id ID --confirm; allowed reason codes are operator_retraction, source_correction and evidence_withdrawn. Append actual corrections through SQLiteEventStore.append; a new correction alone does not silently supersede unsupported claims.

For erasure, first run mind erase-plan --event-id ID with the common scope/database flags. Inspect blocked_reason, counts and affected IDs. The public plan exposes alias count, not alias names. Then deliberately run mind erase-confirm --event-id ID --plan-digest DIGEST --confirm with the same flags. Any changed dependency plan or unsupported case fails. The synthetic demo's already-erased event cannot be recreated to repeat erasure.

Worker CLI exit 0 means a bounded pass finished without terminal/lost-lease failures; queued or retry_wait work can remain and must be inspected in the JSON/status. Terminal failures or lost leases return 1; invalid operator operations return 1; argparse errors return 2; Ctrl+C returns 130. Content is hidden by default; summary --show-content is deliberate inspection.

Embeddings require explicit provider/model/version/dimension flags. Merely configuring a worker provider does not enable automatic embedding. Use enqueue --type maintain_index --include-embeddings with a pinned space, or deliberately select --auto-embed on a configured run-once/work command. No model is downloaded. The example's two-dimensional vectors are labelled synthetic mechanics fixtures.

## Deliberate limitations

Summary artifacts are separate from Stage 5 recall and summarize direct memberships, not an inferred descendant cluster. Historical inspection reports recorded_projection or stale freshness; source validity remains distinct from recording time. Semantic merge/model summarization is not implemented.

Conflict inspection rejects a corpus beyond its complete bound; it does not pretend to review arbitrary larger stores exhaustively. Generic unsupported language remains unsupported.

Erasure refuses any affected graph edge, shared memories with entity associations, arbitrary shared metadata/tags or unsupported independent grounding, and review/dependency scans beyond their complete bounds. Safely retained shared canonical content requires independently endorsed deterministic re-derivation or the narrowly allowed exact manual proof. Surviving safe shared canonical indexes can remain because their content is independently supported. Unsupported cases require a future reviewed administrative policy; they are never reported erased.

Job/audit/tombstone identifiers are retained where needed for replay protection and accountability. No source body or source-body fingerprint is copied into those records. There is no application-level persistent cache beyond the documented projections; external caches and already-open snapshots remain the consumer's responsibility.

Active-job capacity is bounded; durable source, outbox, attempt and audit history grows with ingestion and is not automatically pruned. Operators must monitor local disk and apply their retention policy. Stage 6 acceptance passed with 321 tests; see the actual validation record rather than treating these bounds as performance measurements.

## Stage 7 MCP boundary

MCP never starts a MindWorker, runs extraction, dispatches the outbox or accepts reviews on connection. A separately approved memory.ingest appends the real immutable source event through Stage 2, creating an outbox record atomically (the outbox was introduced in schema v5 and is retained in current schema v6). Its reply reports persisted event ID, pending/dispatched intake and latest extraction job state independently; acceptance is not extraction completion.

memory.status exposes scoped queue/index counts and explicitly says that the worker operates as a separate process. Existing CLI worker execution, WAL snapshots and replay guarantees continue while MCP clients read. Retraction, review approval and privileged erasure remain local administrative workflows. MCP reconnects and restarts do not build indexes, create new memory identities or change the database schema. [Integration](mcp-integration.md) and [MCP security](mcp-security.md).
