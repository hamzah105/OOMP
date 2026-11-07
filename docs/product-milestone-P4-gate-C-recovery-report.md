# P4 Gate C recovery — verified local pass

6 November 2026, Asia/Karachi. Owner-authorized attempt started at
`2026-11-06T15:07:31.154127Z` (20:07:31 PKT).

| Gate | Result |
| --- | --- |
| A | Accepted local PASS, unchanged: 137/137 checks, 12/12 scenarios, 16/16 source recall, 16/18 source precision |
| C | **PASS**: one fresh independent official-SDK host attempt, 18/18 assertions |
| B | **NOT TESTED**: no real-model inference |
| Default multi-principal scheduler | **OPEN**; no worker or scheduler changes in this recovery |

P4 remains incomplete pending real-model evaluation and outstanding limitations.
This report supplements the preserved quality-recovery report; neither its
historical Gate C failure nor its accepted Gate A measurements were rewritten.

## Experimental correction and evidence

New evidence directory:
`.test-artifacts/p4-gate-c-recovery-20261106T145817Z/` (`QA` below).
The original failed Gate C ledger and every file under the prior quality-recovery
evidence directory were preserved and hash-checked after this attempt.

The previous host incorrectly demanded principal-only isolation from legacy
`memory.get_source` inside a shared tenant/namespace. Accepted
`mcp/service.py` calls `read_snapshot(scope)`, whose documented default is
`principal_only=False`; legacy source reads enforce tenant and namespace.
The P4A report explicitly retains this contract. No production behavior changed.

The corrected experimental host separates two independently provisioned,
read-only identities:

| Identity | Scope | Purpose |
| --- | --- | --- |
| `gate-c-recovery-reader` | `gate-a / foreign / trace-owner` | Independent namespace recall and legacy cross-namespace denial |
| `gate-c-recovery-principal-control` | `gate-a / fictional / trace-foreign` | Stronger context principal isolation within the primary reader's tenant/namespace |

Credentials were generated separately in process memory, sent only to the owned
server/host environments, and not saved. Neither grant allowed ingest or raw
source content. The host imported only stdlib/public HTTP/official MCP SDK APIs;
it did not import OOMP or TRACE internals. MCP protocol version was
`2026-07-28`. The actual accepted candidate runtime and existing fictional
`D:\gq-1105203249\memory.sqlite3` were reused. No ingestion, Mind processing,
indexing, package build, projection repair or database migration was repeated.

## Actual requests and proofs

The single loopback server handled 17 HTTP requests: two SDK discovery requests,
two tool listings, eleven tool calls and two rejected credential probes.
The host recorded thirteen calls excluding discovery/listing. Every semantic
tool response, arguments and latency was written before assertion to a separate
`QA/results/call-NNN.json`; server-side semantic captures and HTTP timings are
under `QA/http/`. Nested exception groups/causes and partial results are now
captured with synthetic-credential redaction if a failure occurs.

| Check | Actual result |
| --- | --- |
| `What is my ONYXNAMESPACE project?` | `found_relevant_evidence`, one independently validated original-source proof, 1,137-byte packet, 1,127.856 ms |
| Own linked source metadata | Correct user role, `user_message`, source reference/timestamp and event; raw content absent |
| Primary ORBIT42 source via independent namespace grant | Semantic `not_found`, nonretryable; no source disclosed |
| ORBIT42 context via independent namespace grant | `no_relevant_evidence`, empty evidence/references/packet, zero selected bytes |
| `tenant_id`, `namespace`, `principal_id` caller overrides | All three rejected with semantic `invalid_parameters` |
| Raw source request through context and legacy source tool | Both rejected with semantic `forbidden` |
| JADEPRINCIPAL context via separate control grant | `found_relevant_evidence`, one valid proof, 1,137-byte packet, 65.655 ms |
| ORBIT42 context via that same-namespace foreign principal | `no_relevant_evidence`, empty evidence/references/packet, zero selected bytes |
| Missing / invalid bearer | Both HTTP 401 |
| Read-only discovery / internal-import checks | Passed for the independent host and control connection |

The ONYX proof identifies fictional interaction `000000000000000000003103`, event
`trace-581412238bf3da5bb8ee50fb7622d4489898b56373889cb87f94b86b7cd43172`,
memory `mem-e6b5e80a26ae741c7fbec6ec8f9253c5a74e53c9e4521490ae9cbbfb67c23136`,
and exact span `[0,47)` of
`I am developing a project called ONYXNAMESPACE.`
The original clause SHA-256 is
`a313d0c73f70e3572f0b1a3549ee9990a2fb98311dec7921777b626074b2df8a`.
The independent host reconstructed the event/session/turn identities from its
approved fictional record, verified source approval, exact character offsets,
timestamp and literal claim semantics, and confirmed user role through the
linked source metadata.

The control proof identifies fictional interaction `000000000000000000003101`,
event `trace-af0b05a1900fd58ea348d5905d93da1a598c47a01f2a6029c1a12b3ce62d9072`,
and exact span `[0,47)` of
`I am developing a project called JADEPRINCIPAL.`
Its original SHA-256 is
`bbc23811c17155fb1239474f3f9471f508904d2cabde841d6b6392d5ebb779b4`.
Both positive packets matched their structured evidence and exact UTF-8 byte
accounting under the 12,000-byte budget. Both live clauses are ASCII; Unicode
character/byte-offset rejection was verified offline, and prior Gate A Unicode
evidence remains unchanged. These single-call latencies are not model or
production performance benchmarks.

The legacy limitation remains explicit: different principals in the same
tenant/namespace can read namespace-scoped legacy source metadata. Such a
namespace is a shared legacy read boundary. `memory.context` applies the
stronger principal policy, demonstrated separately above. This run does not
claim principal isolation for the legacy tool.

## Validation, Windows disposition and cleanup

Fresh guarded, sequential offline validation on Python 3.11.4 passed **31 tests**
in 0.151 seconds, with zero failures, errors, skips or guard violations. These
cover the corrected scope contract, separate least-privilege grants, source
identity/role/Unicode spans, forged claim rejection, packet alignment and byte
budgets, exact health-event disposition, nested exception redaction and the
unchanged SQLite/network guard. No SDK/network/database/model call occurred in
those offline checks. The live attempt then passed **18/18** assertions.

Historical regression evidence remains **968 unique Python 3.11 passes across
bounded segments** and **173 focused Python 3.12 passes**, with the previously
documented full-command timeout and incomplete full-3.12 coverage. Neither was
rerun or relabeled as fresh. No runtime file changed during Gate C recovery.

The owner's limited Windows disposition was applied only after read-only checks:

- TPM-WMI 1801 at `2026-11-06T14:30:11.3672266Z`: reviewed Secure Boot CA/key
  servicing message.
- SCM 7000 at `2026-11-06T14:24:14.8093113Z`: missing `RealtekWlanU` service file.
- No associated crash/BugCheck, Kernel-Power 41, unexpected-shutdown 6008,
  WHEA/storage fault or Application crash was found. The preceding shutdown had
  EventLog 6006 and Kernel-Power 109 (`Shutdown Reason: Kernel API`). Loopback
  routing was present; WLAN was not a test dependency.

An initial PowerShell DateTime-filter query incorrectly included 76 pre-boot
DCOM events. Its failed `health-disposition.json` remains preserved. Explicit
UTC Event Log XPath corrected only the query range; `health-disposition-utc.json`
records exactly the two owner-reviewed events, with no later errors. The older
DCOM burst was preserved without a new blanket disposition. Every later
unreviewed System error remained blocking. No Windows setting, driver, service,
firmware or event-logging change was made; no BSOD-resolution claim is made.

Admission and continuous monitoring retained the existing 4 GiB RAM / <75% commit
admission, 1.5 GiB RAM / 85% commit stop limits, cancellation and native PID /
Windows Job / listener ownership checks. Live elapsed time was **14.000 s**,
minimum available RAM **6,877,609,984 bytes**, maximum commit ratio
**0.3997593540**. Both owned processes exited 0; the Windows Job closed, with no
remaining listener or cleanup failure. Post-attempt inspection through
`2026-11-06T15:09:14.5154184Z` found no later System errors or Python processes.
These safeguards remain experimental-harness functionality.

## Preservation and owner stop gate

All 95 accepted runtime modules matched source, the packaged snapshot and the
installed candidate before/after. All historical QA files, the baseline and
separate retraction copy, existing descriptors and new sealed inputs remained
unchanged. Key SHA-256 values:

| Evidence | SHA-256 |
| --- | --- |
| Accepted fictional database | `206af1066b860784ff4ad3ded1295a99168292e9656ebcbbb3dd0d7cbbf7c47d` |
| Accepted Gate A result | `585b4d8427300572a38f215a867fa1729b2eaf418d9741f876133e373c164460` |
| Preserved final quality-recovery report | `7cdae0b53d187959ae14cdbf3c5b1bfe65a43c3fed52d72703631b967b1bc793` |
| New Gate C result | `982ec3a50525eee5237f5ca84c0a3f0dda3e23a75a7cd00b818b755eaa9263aa` |

OOMP remains on `feature/p4-retrieval-quality` at
`d34bfbbbec44b0e016ddc41da1a7e27a45d45a68` with its existing uncommitted changes.
The tracked diff is unchanged: six files, 280 insertions / 30 deletions
(`MANIFEST.in` plus five runtime modules). This recovery adds only ignored
experimental evidence and this new report. Existing untracked quality tests,
fixtures and reports were preserved. The index is empty; `git diff --check`
passes, with existing line-ending warnings retained. TRACE is clean and remains
at `dcfda75325be0254232c1f1342601692ce18f937`.

No private database, physical MongoDB, `.env`, real model, cloud service, model
download, commit, push, merge, release or deployment was used. There was one
new live attempt and no automatic retry. The working host is an experimental
generic Python example, not a newly released adapter or hosted-CI claim.

Gate B real-model cross-session evaluation is still NOT TESTED. The default
multi-principal scheduling defect, heuristic language coverage, legacy shared
namespace limitation and two non-gold Gate A source/query selections remain
documented. **STOP for owner review; do not begin P5 or claim full P4 acceptance.**
