# P3 object-memory architecture

Design recorded before runtime changes, 30 October 2026. Implementation and
validation status will be reconciled in `product-milestone-P3-report.md`.

## Predecessor and inventory

Parent: `29ceb96c85055e624783df27123d93e91b187148`. The exact SHA's
[Actions run](https://github.com/hamzah105/OOMP/actions/runs/41034632588)
completed successfully: Windows and Ubuntu, Python 3.11 and 3.12, plus archive
build/content/clean-install validation. PR #1 remains open and draft. Development
uses the local `feature/p3-object-memory-map` branch; no push or merge is planned.
The starting tracked worktree and index were clean. Machine-local evidence is
under `.test-artifacts/product-P3-20261030/`; older artifacts remain untouched.

| Existing primitive | Reuse and remaining gap |
| --- | --- |
| Immutable scoped `events`, exact `memory_sources` spans, fingerprints | Authoritative evidence; no new transcript store |
| Canonical/episodic `memories`, legacy entities and aliases | Preserve IDs; entity-name uniqueness alone cannot resolve ambiguous P3 identity |
| `memory_edges`, recording history, governed corrections | Reuse vocabulary and temporal semantics; membership is not claim endorsement |
| `topics`, multiple memory memberships | Retain existing records; add a DAG over typed objects rather than changing immutable topic parentage |
| P2 episode topics and `mind_summary_revisions/sources` | Reference existing episodes and revisions; summaries remain derived |
| `AuthorizedScope`, source-principal checks, MCP grants | Trusted callers supply authority; no new remotely supplied scopes or MCP tools |
| Mind transactions, leases/fencing, retraction, explicit erasure | Retain; projection commits can receive the same fenced job context |
| FTS/optional vectors and bounded retrieval | Remain separate; P3 supplies inspection, not a new P4 retrieval planner |

The attached product roadmap predates P1/P2/P2.1. Its statements that onboarding
and model extraction are absent describe historical gaps, not this baseline.
The accepted model success remains one prompt-adjacent synthetic case, not broad
model quality, cold/default-timeout reliability or a BSOD fix.

## Proposed minimal extension

Add a typed object registry and normalized proofs, hierarchy memberships and
associations in schema v6. Historical migration statement tuples 1–5 remain
unchanged. Schema verification gains explicit v6 support; old-version fixtures,
unsupported-future rejection and atomic initialization remain tested. Existing
examples/tests that mean "current schema" use the supported version constant;
historical fixtures continue to specify their actual historical versions.

Object types cover claimed person/alias, project, plan, place, organization,
topic, episode, concept, fact and original source reference. Owner/domain and
session/revision nodes are structural navigation records. All new keys and
lookups include tenant, namespace and trusted principal. Existing event, memory,
topic and summary IDs are retained as references, not replaced.

Identity uses a deterministic immutable source/reference anchor, separate from
the display label. Rebuilding memberships cannot mint new identities. Similar
spelling or embeddings never merge objects. Explicitly named references may
reuse an existing object only with a unique source-grounded match; ambiguity
retains separate objects or an unresolved reason. Explicit, independently
validated rename/alias evidence can add label revisions without changing the
object ID. Claimed aliases do not authenticate a legal identity.

Proof rows reference existing memory/source links and validated Unicode spans.
They contain only the small label/interpretation needed for navigation, not
copies of transcript documents. Source bodies remain in the event store.
Object labels are selected from eligible proof revisions; unsupported orphan
registry entries never appear as active objects. Foreign keys cascade derived
proof/label cleanup when the existing privileged erasure removes its planned
authoritative source links. The privileged planning/deletion procedure is not
extended with new deletion steps; summaries retain existing cleanup. Opaque
identity anchors may remain without labels/proofs, preserving stable identity
without exposing unsupported objects. Session anchors use opaque identifier
digests rather than retaining source session strings in the registry.
Retraction and historical queries recheck live endorsement in the read snapshot;
an old index must not expose stale labels or associations.

## Navigation and temporal semantics

The hierarchy is a normalized DAG. Multiple parent paths share object IDs and
canonical evidence. A bounded, serialized cycle check rejects unsafe membership
updates. Scope and allowed endpoint types are checked before writes. Ordering,
keyset continuation and explicit depth/node/edge/work ceilings bound inspection.
An incomplete result is marked; it is never presented as exhaustive.

The fictional relocation map must provide Plans, Places/Islamabad/Related plans,
and Episodes/City comparison/Referenced objects paths to one plan. A plan's
facts lead to original source references and exact spans; episode/revision
navigation references P2's established summary records. Associative graph cycles
are distinct from forbidden hierarchy cycles.

Reuse the actual enum: `ABOUT`, `RELATED_TO`, `DERIVED_FROM`, `SUPPORTS`,
`DEPENDS_ON`, `CONTRADICTS` and `SUPERSEDES` where their existing semantics apply. A controlled
semantic role can express consideration, candidates, preference or correction
review without changing the public relationship enum. Nonstructural links need
independently checked source proof or an explicitly identified existing graph
basis. Generic association cannot bypass governed supersession.

Keep source occurrence, system recording/knowledge time and supported validity
separate. Missing times remain unknown. Initial tentative relocation and later
"not moving this year" remain independently evidenced. A correction can create
a reviewable lineage and a newer attributed intention; it cannot silently
supersede a protected canonical memory or invent a completed move. Historical
`known_at` and `valid_at` filters reuse existing conservative semantics.

## API, privacy and integration

Add bounded in-process projection, lookup, membership, history, association,
explanation and rebuild APIs. Explicit projection builds read eligible existing
records; they do not crawl private profiles or call extraction models. A passed
Mind job is fenced before and after projection writes in the same transaction.
No model-generated scope, principal or identity establishes authority.

Extend existing `oomp memory` with tree, inspect, history, explain, redacted
export and an explicit projection-build operation. Keep extract/list/index
arguments unchanged. Inspection relies on trusted local filesystem authority,
as existing CLI commands do. Default views omit source bodies and excerpts;
content display requires deliberate trusted inspection. Redacted export omits
private labels, raw text, locators and credentials. Unicode, JSON, noninteractive
PowerShell and `NO_COLOR` remain supported. No new MCP listener or remote write
capability is introduced.

Sensitive, quoted, question, hypothetical and assistant statements never become
asserted user attributes. Sensitive episode pointers remain topic-only under
the established policy; source text, model output and labels execute nothing.
No real OOMP/TRACE database or MongoDB record is used in validation.

## Planned changes, validation and resources

Expected paths: new `src/oomp/objects/` contracts/policy/storage/service/CLI;
additive migration support in storage; CLI delegation; schema-aware existing
examples/install checks; focused P3 tests, frozen fictional fixture, offline
quickstart and P3 report. Preserve provider prompts/diagnostics and existing
authentication and worker contracts. Review any additional path before expanding
scope.

Run guarded focused baseline tests before runtime edits. Then test object and
scope validation, Unicode spans, ambiguous/renamed identities, three-path reuse,
cycles/orphans, replay, restart, rebuild, historical correction, source tampering,
retraction/erasure, leases/fencing, migration rollback/interruption and WAL backup.
Run full Python 3.11 then 3.12 sequentially, followed by current wheel/sdist
clean installs and archive/credential audits. Use isolated test-environment
startup guards; never leave a hook in the original developer environment.

Run one bounded 1,000-record synthetic SQLite evaluation against the same flat
memory/graph data. Record navigation/evidence correctness, false associations and
merges, identity/rebuild stability, correction/retraction/isolation, latency,
database size and process memory. Capacity estimates are provisional until
measured; no 10,000-record run is necessary. Check Windows RAM/commit, loaded
model/process metadata and new critical errors first. Use short fresh temporary
roots and stop on instability. No inference, model downloads, stress tests or
Windows configuration changes. Experimental resource/polling controls remain
test-harness functionality, not a shipped BSOD remedy.

Migration risks are additional foreign-key dependencies, historical schema
verification, derived-cache erasure, and changes to current-version assertions.
Backup/restore uses SQLite's existing WAL-aware backup example with fresh
destinations; validate synthetic restore and failed-upgrade rollback before any
future operator-approved migration. P3 never migrates a real profile here.

P4 query planning/context virtualization/TRACE prompting and P5 releases or
competitive benchmarking remain deferred. Completion requires measured results
and owner review; no commit, push, merge or publication is authorized.

## Implemented contracts and boundaries

Six normalized tables (`map_objects`, `map_proofs`, `map_memberships`,
`map_membership_supports`, `map_relations`, `map_relation_proofs`) and eight
indexes are added. Identity hashes include `object-map.v1`, tenant, namespace,
principal, type and immutable source/reference anchor. The label is never part
of a project/plan/person identity. Places/concepts use a literal source mention
and may reuse only a unique exact, validated, chronological episode-context match.
Original event/memory/topic/summary IDs remain references. Session references
are digests. Canonical evidence is never duplicated to create another parent.

| Association role | Independent basis |
| --- | --- |
| `derivation` / DERIVED_FROM | Fact's actual memory-source pair and original event wrapper |
| `candidate_for`, `origin`, `decision_criterion` / RELATED_TO | Exact supported literal role plus tentative plan in the same event or actual existing P2 episode |
| `about` / ABOUT | Existing P2 episode membership; explicitly derived context |
| `work_context` / RELATED_TO | Explicit `for project <exact unique label>` relocation criterion and the plan's episode context |
| `correction_review` / RELATED_TO | Independently parsed later correction in the same episode; review pending, no protected supersession |
| `existing_graph` / existing enum | Exact existing endpoints, type, evidence, endorsement and validity; generic caller cannot invent a protected edge |

Unrelated facts cannot be attached with another fact's proof. Contextual topic
memberships also require the grounded relation. Every relation is validated at
write and read; current uncertainty is recomputed from supported endpoints.
No graph edge or summary verifies a person or user claim.

`ObjectMap` offers explicit bounded build/rebuild/project, get/list/exact-find,
memberships/relations, history/explain and redacted export. Projection is not a
new default worker handler: eligible extraction/episodes are produced through
the existing Mind jobs, and callers explicitly materialize the map. Optional
claimed-job projection checks actual target and existing lease/fencing in its
write transaction. No P2 provider, prompt, fallback, authentication or grant
implementation is changed.

Ceilings: 5,000 registry objects per authority partition, 128 proofs per object,
16 proofs per relation/summary revision, 32 memories per projected event,
1,000 events per build page; read work 10,000, depth 10, 500 nodes and 2,000 edges.
History is bounded to 128 assertion proofs and 64 P2 revisions. Capacity errors
fail explicitly; results are not silently claimed complete. Rebuild replays
the same immutable anchors and supports rather than deleting history. Source
withdrawals are filtered on reads even before replay. Prior semantic anchors
can remain after erasure, without labels or supported views. This is not
physical secure deletion and does not remove old backups or SQLite free pages.

Recognizer coverage is deliberately small and English-pattern based. Unsupported
wording remains an attributed fact if existing extraction supports it. Ambiguous
aliases stay separate; no general entity-resolution or natural-language planner
is claimed. An explicit rename can preserve identity only when its prior exact
name has a unique eligible match. New proof knowledge is not backdated to source
occurrence. Old states remain inspectable with `known_at` while evidence exists;
confirmed erasure removes their source-backed label views.

If a P2 summary's live source manifest no longer matches its stored revision,
the object view fails closed with `object_summary_source_changed` until existing
P2 consolidation produces a supported revision. P3 does not silently refresh
or authenticate stale summary content. Graph-dependent erasure and unsupported
shared-entity erasure retain the existing privileged refusal policy.

## Schema-v6 MCP compatibility

MCP admission requires a ready database at `SCHEMA_VERSION` (currently 6).
Historical v5 databases require the existing explicit initialization/upgrade
path and are not automatically migrated by an MCP read or readiness check.
Future versions remain rejected. Current `memory.status`, `mcp check` and
synthetic doctor results truthfully report schema 6. `StatusResult.schema_version`
explicitly accepts only 5 and 6 so new clients can still validate a historical
v5 server response; its default is 6 and current servers set it explicitly.
An old client that hard-codes only v5 must upgrade before consuming v6 status.
This is an additive documented response-enum change, not a new grant, capability,
tool, schema-adoption permission or authentication path.
