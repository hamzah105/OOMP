# Submission readiness

Updated 7 November 2026 (Asia/Karachi), for the 10 November owner deadline.
This is an alpha research submission checklist, not a release or production
certification. Submission-focused offline checks passed as recorded below.
The final archive's executed integrity gates and immutable hashes are recorded
in its `validation/submission-validation.json` and adjacent checksum receipt.

| Requirement | Current evidence / status |
| --- | --- |
| P1–P3 baseline | Previously accepted; not rewritten |
| P4 Gate A | Accepted local PASS: 137/137 checks, 12/12 scenarios, 16/16 source recall, 16/18 precision; not repeated |
| P4 Gate C | Accepted local PASS: 18/18 independent-host checks; not repeated |
| P4 Gate B | INCOMPLETE: 22 returned answers, one deadline failure, 41 unrun / 64; paired answers 0/5 no-memory, 0/5 recent, 3/5 flat, 3/5 OOMP; no superiority claim |
| Managed context onboarding | PASS: explicit opt-in and compatibility regression checks; old/default profiles preserved |
| Public generic MCP host | PASS: reviewed example, synthetic tests and source-matched SDK smoke |
| Public managed manual demo | PASS: five fictional sources, seven context queries, ObjectMap, restart/source-proof stability and shutdown |
| TRACE connection | Public contract/instructions reviewed read-only; accepted Gate A retained; no new browser, MongoDB or model run |
| Package build and clean installs | PASS: wheel/sdist, four fresh core installations on3.11/3.12,32 actual CLI checks, all95 runtime hashes matched |
| Windows / Python 3.11 | 111 unique focused passes across initial94, isolated1 and remaining16; historical968 inventory not repeated |
| Windows / Python 3.12 | 111 focused passes in112.01s; historical173 focused passes preserved |
| Ubuntu / hosted CI | Accepted base main has five successful jobs; current unpushed candidate NOT TESTED on hosted CI |
| Credentials / package / Git audit | Public inventory320 files, zero high-confidence secret matches, frozen fixtures and accepted evidence preserved; final staged/archived equivalence recorded in package manifest |
| Submission archive and local commit | Target `dist/OOMP-submission-20261107.zip`; final receipt records archive/local commit after source freeze; no push, merge, deployment or release authorized |

The current candidate branch is `feature/p4-retrieval-quality`, based on
`d34bfbbbec44b0e016ddc41da1a7e27a45d45a68`. TRACE remains at accepted
`dcfda75325be0254232c1f1342601692ce18f937`; it is not modified by this sprint.
The five successful base-main jobs are recorded in
[GitHub Actions run 41347026380](https://github.com/hamzah105/OOMP/actions/runs/41347026380).
They do **not** validate the uncommitted candidate. Candidate hosted validation
cannot be claimed without an independently authorized push and actual run.

## Operating boundary

Use a new short disposable Windows directory and a dedicated database,
tenant/namespace and single principal. Managed profile grants share that one
principal. Do not add another independently owned principal to this namespace:
the default shared-queue projection issue remains open. This restriction is
enforced by the manual demo's fresh storage and fixed scope and documented for
operators; it is not a universal database policy or a general scheduler fix.

Legacy source read remains tenant/namespace scoped; `memory.context` has stronger
principal-specific ownership. Separate untrusted hosts require separate scopes
and independently provisioned credentials. Raw source permission is unnecessary
for metadata-only source checking; TRACE independently verifies original records
against its owner/session/role authority. The public generic host validates the
wire/proof structure and cannot independently authenticate an external source
database it does not own.

The public demo uses fictional data, deterministic rules and no model/provider.
It is not an interactive TRACE login, real MongoDB exercise, or real LLaMA answer
evaluation. Retained Gate A/C results and the partial Gate B results must remain
separate from new P5 smoke results.

## Review and reproduction

- [Manual Windows commands and actual observation table](MANUAL-TESTING.md)
- [Independent official-SDK host](generic-context-host.md)
- [P4 evidence, answer results and limitations](P4-FINAL-ACCEPTANCE.md)
- [P5 executed validation and packaging scope](P5-SUBMISSION-REPORT.md)
- [Existing product limitations](limitations.md)

Local sprint evidence is preserved in
`.test-artifacts/submission-20261106T151910Z/`. Historical acceptance artifacts,
failed ledgers and fictional databases are preserved separately. Only selected
small, credential-free evidence belongs in the final archive; never include
private databases, generated profiles/secrets, `.env`, model weights, environments,
crash dumps or entire `.test-artifacts` directories.

Full-roadmap P5 research remains pending: independent pilot users, blinded human
answer adjudication, public benchmark validation and controlled version-pinned
Mem0/Graphiti comparisons. The bounded submission does not certify enterprise
security, broad model reliability, all MCP hosts or general multi-principal use.
