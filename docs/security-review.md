# Stage 10 focused security review

Review date: 2026-10-27. Scope: existing OOMP 0.1.0 trust boundaries, packaging,
examples and maintainer CI. This is a local code/test/advisory review, not an
independent penetration test, legal assessment or production certification.

| Surface | Inspected behavior and retained regression evidence |
| --- | --- |
| Persistent storage | SQLite/memory/entity stores: scope revalidation, composite partition keys, immutable events, exact retry/conflicts, transactional migration/rollback, corruption errors and explicit paths. Stage 2/3/migration fixtures cover isolation/reopen/concurrency. |
| Extraction | Extractor/pipeline/canonicalization: supported role/grammar, exact source spans, independent grounding, heuristic secret exclusion and atomic batches. Stage 3 forged-provider/source/role tests remain intact. Sensitive originals are not sanitized by the heuristic. |
| Temporal graph | Graph service/policy/stores: actual scoped endpoints/proof, confirmed protected writes, valid/known time separation and finite traversal/cycles. Stage 4/5 negatives preserve unsupported/uncertain cases. |
| Retrieval | Engine/store/fusion/packer: quoted FTS terms, scoped BM25, exact compatible vectors, finite bounds, single snapshot and whole-evidence accounting. Stage 5 provider/index/budget/failure tests validate these controls. |
| Mind | Scheduler/contracts/worker/handlers/privacy stores: restricted jobs, lease fencing, bounded retry, idempotent replay, source revalidation after erasure, scoped projections and safe operational errors. Stage 6 crash/stale-fence/erasure tests exercise recovery. |
| MCP | Grant/approval/config/contracts/service/server: server-owned scopes, constant-time credential/signature comparison, exact payload/domain, source capabilities, SDK authentication/parsing and literal loopback Host/Origin/header/body/result/work bounds. Stage 7 actual SDK negative tests cover adversarial inputs/replay/isolation. |
| Research | Frozen sources, equal cutoff/scope/budget/model space, body/proof checks, retained failures/availability and incomplete-run states. Stage 9 separates retrieval evidence from unexecuted generated-answer claims. |
| Packaging / CI | Explicit archive inclusion/exclusion, content/license checks, clean installed-package acceptance, first-party SHA-pinned actions, read-only permissions, no persisted checkout credential or privileged fork/publishing trigger. New tests cover overwrite refusal, WAL recovery and unsafe/private archive names. |

No core authorization, governance, retrieval or erasure algorithm change was
needed to obtain passing release checks. Trusted local administrative APIs remain
privileged; a caller-created scope object is not authentication.

## Isolated release repairs

1. The baseline source archive included Stage 9 tests but omitted benchmark code,
   examples and docs. The explicit manifest now includes intended source/research
   files and prunes private/generated content. Actual archive and clean-install
   checks validate the result.
2. Baseline `pip-audit` flagged pip 23.1.2 and setuptools 84.0.0: 15 advisory
   entries including duplicate IDs, eight distinct IDs across those tools. Build
   requirements now use setuptools >=84.1,<85; patched local/CI installers use
   pip >=26.2.2,<27. Runtime Pydantic/MCP/uvicorn constraints remain unchanged.
   The Windows setuptools issue is [GHSA-xmj3-9gf7-h52w](https://github.com/advisories/GHSA-xmj3-9gf7-h52w).
3. The new backup example uses SQLite's online backup API, with a committed-WAL
   recovery fixture and refusal to overwrite destinations/source. It is local
   administrator example code, not a new model or MCP permission.
4. An unrendered Stage 9 validation placeholder is corrected only to its existing
   JSON measurement, 87,334,912 bytes. No dataset or raw result is changed.
5. Installed example acceptance found a stale schema-v4 assertion/output in the
   Stage 5 demo. Both now reflect existing v5, with a captured failing regression
   and a passing full-example test. No production schema or retrieval change.

Final scanner versions/counts and skipped local-package coverage are in
[Stage 10 validation](stage10-validation.md). Unpublished `oomp-memory` has no
PyPI advisory record and is not scanner-verified source. Dependency scans do not
cover all code logic, CPython/SQLite runtime, external applications or model
weights. Source review and vendor/runtime updates remain necessary.

## Retained risks and gates

Plaintext files/backups, trusted administrators, limited extraction/secrets
heuristics, RAM-only protected policy, possible model prompt injection,
uncalibrated semantic false matches, same-host SQLite/workers, incomplete historical
entity clocks and non-cryptographic erasure remain explicit. No public-cloud MCP,
universal desktop-host, remote Linux CI or live answer-quality certification.

Remote CI is configured, not claimed executed. Maintainers must enable private
vulnerability reporting or establish another real confidential contact before
publication. A critical code/licensing flaw blocks publication. The recommendation
is a local research candidate subject to [recorded human/CI gates](release-checklist.md).
