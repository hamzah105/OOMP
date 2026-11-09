# OOMP + TRACE local startup validation

8 November 2026, Asia/Karachi. This patch implements the owner-approved local
two-terminal workflow; it does not complete P4's model evaluation or general
multi-principal scheduling. Historical submission artifacts remain preserved.

## Source and exact public changes

OOMP parent: `6f645e70064af5a21f4e77f401a320b76ea63d6d`, branch
`feature/p4-retrieval-quality`.

- `src/oomp/cli.py`
- `src/oomp/product/cli.py`
- `src/oomp/product/start.py` (new)
- `src/oomp/product/handoff.py` (new)
- `tests/test_product_start.py` (new)
- `tests/test_product_handoff.py` (new)
- `README.md`
- `LOCAL-LIVE-QUICKSTART.md` (new)
- `docs/local-start-validation.md` (this report)

TRACE parent: `dcfda75325be0254232c1f1342601692ce18f937`, branch `main`.
Changes remain confined to the five explicitly approved public files:

- `backend/app.py`: invoke the approved connection bootstrap before route imports.
- `backend/services/oomp_local.py` (new): independent private-reference bootstrap.
- `tests/test_oomp_local_bootstrap.py` (new): synthetic security/configuration tests.
- `.gitattributes`: append only `backend/services/oomp_local.py text eol=lf`.
- `LOCAL-LIVE-QUICKSTART.md` (new).

No TRACE source imports OOMP internals. Existing authentication, grants, source
contracts, worker leases/fencing, schema and legacy source-read policy were not
modified. The five frozen JSON fixtures, preregistration and checksum files are
unchanged; all eight files in their fixture directory were hash-checked.

## Environment diagnosis

TRACE's measured interpreter is
`D:\Desktop\VU BS-CS\CS619\TRACE\.venv\Scripts\python.exe`, Python 3.11.4.

| Package | Version | Actual imported location |
| --- | --- | --- |
| FastAPI | 0.115.0 | TRACE `.venv\Lib\site-packages` |
| Starlette | 0.38.6 | TRACE `.venv\Lib\site-packages` |
| Uvicorn | 0.54.0 | TRACE `.venv\Lib\site-packages` |
| Pydantic | 2.14.1 | TRACE `.venv\Lib\site-packages` |
| MCP | 2.3.0 | TRACE `.venv\Lib\site-packages` |

FastAPI requires Starlette `>=0.37.2,<0.39.0`; the current set satisfies that
constraint and `pip check` passes. TRACE's existing `requirements-oomp.txt`
already bounds SSE to `>=3.0,<3.1`, preserving this compatible stack.
No dependency reinstall or requirements change was justified or performed.

The exact reported Router `on_startup` TypeError was reproduced in a controlled
process by placing OOMP's site-packages first: FastAPI then came from TRACE, while
Starlette 1.10.0 and Uvicorn came from OOMP. The current activated TRACE shell
resolves its own Python and Uvicorn correctly. Without activation this workstation
resolves a global Uvicorn; the full old terminal traceback was unavailable, so
the controlled reproduction establishes the mechanism, not its historical origin.
The new handoff transfers no Python import paths. The local OOMP launcher uses
its own existing Python with `-I`.

## Persistence and security

The unchanged `trace-live` profile remains at `D:\os-trace-live-1108`.
Its generation is
`5e17b80dce432355dc78f54f26313c0b45a548bdfd2e050843b8a87382e65258`.
Active/generation configuration and credential bytes were checked against the
preflight inventory after setup and real stop/start. No profile was recreated,
no credential rotated and no owner/grant binding changed.

One-time files are the ignored private TRACE `.oomp.local.json`, the private
`%LOCALAPPDATA%\OOMP\startup\selection.json` plus its lock, and
`C:\Users\hamza\Scripts\oomp.cmd`. PATH and installed environments are unchanged.
The existing application directory had broader ACLs, so selection uses a newly
restricted private child; its ancestor permissions were not altered.

TRACE validates private ACLs, links, HMAC, exact profile generation/source hashes,
scope and existing secret references before applying settings in memory. Signed
settings precede legacy dotenv defaults. A foreign dotenv owner and conflicting
inherited process settings still fail closed. `.env` remains byte-identical.
The reviewed TRACE helper's exact SHA-256 is
`02b6ecf87dff7c0beef57a8028d4895d83ba833011699be684766869031b5239`;
the narrow LF attribute preserves those exact bytes across checkouts. A proposed
normalizing hash guard was rejected by automatic review and was never applied.

The publication URI is resolved through TRACE's own reviewed helper. Only the
exact `localhost` spelling becomes `127.0.0.1` in the private process environment;
credentials, port/path/options remain intact. The existing supervisor's strict
literal-loopback admission is unchanged. Doctor resolves this reference only for
an approved existing handoff and retains its detailed invalid-profile report.

## Executed results

| Check | Actual result |
| --- | --- |
| OOMP focused regressions | 94 unique passes across preserved sequential runs; no full regression repeated |
| Final TRACE bootstrap/authentication/publication selection | 62 passed, 3 deselected, zero unexpected skips; 4.62 s |
| TRACE service exclusions | Physical Mongo persistence, external MCP role test and external service outage/replay test |
| Separate TRACE process configuration discovery | Context V1 and authenticated `memory.status`, matching pinned owner; no injected token/ID |
| Exact activated `uvicorn backend.app:app --reload` | PASS: own Python/Uvicorn, reload parent and worker, database-ready/startup-complete markers, `/health` 200 |
| Reload timing / cleanup | 3.078 s total; bounded owned Job closed; port 8000 free |
| Mongo startup effects | Five startup indexes verified pre-existing; catalog digest unchanged afterward; only selected user `_id` read for owner validation |
| Real managed CLI lifecycle | Bare stop, fresh start and status passed; final start/status passed and all MCP/Mind/publication roles are ready |
| Final full doctor | 26 PASS, 0 WARN, 0 FAIL, 5 NOT TESTED |
| Private profile / dotenv preservation | Byte-verified; no backfill, model request or model download |

Doctor's NOT TESTED results concern unselected model/provider routes and real
host login. A passing health endpoint or worker heartbeat is not a final-answer
or browser-login acceptance. The real TRACE test server was stopped; the approved
OOMp managed stack was restored and left running.

Evidence directories are `.test-artifacts/local-start-20261108/` and
`.test-artifacts/local-start-validation-r2-20261108/`. Final structured evidence
is `final-validation.json` in the latter. The Windows resource/ownership monitors
are experimental verification infrastructure; no BSOD-resolution or shipped
runtime-monitoring claim is made.

## Preserved failures and corrections

The first bootstrap correctly rejected six legacy dotenv connection settings.
The narrow corrected precedence honors the approved same-owner signed binding
while preserving explicit process conflicts and foreign-owner rejection.
First setup refused a broader application-folder ACL; it now creates its own
private child. Fresh publisher startup exposed the existing literal-host guard;
the in-memory localhost conversion satisfies it without loosening validation.
Full doctor exposed a missing reference resolution, then a detailed-error-contract
regression; both exact triggers were tested and corrected before final live checks.

An early TRACE regression selector used absolute deselection paths that did not
match pytest's relative node IDs. Two external-MCP tests ran against fictional
fixtures, and a physical-Mongo test attempted a socket; the offline guard blocked
it **before connection**. Pytest reported 57 passes/one skip, but that phase is
**not accepted as a passing safety gate**. Its warning, marker and results remain
preserved. No private Mongo record was reached by that blocked test.

The fresh validation keeps identical network denials, rejects forbidden service
nodes before execution, verifies the exact collected list and monitors its
violation marker continuously. The corrected 62-test run had three explicit
deselections, no unexpected skip and no guard violation. The original violation
marker was not cleared. A separate working-directory error in a child-process
test was corrected in the harness without weakening production assertions.

## Remaining boundaries

Real browser login/OAuth and final cross-session LLaMA answers remain manual.
The [quickstart](../LOCAL-LIVE-QUICKSTART.md) provides the two-terminal commands
and fictional project test. No model inference or downloads were run here.
Gate A/C, the 968-test inventory and the LLaMA benchmark were not repeated.
No private historical-chat backfill, unrelated research, deployment or release
was performed. General multi-principal scheduling remains open; the supported
demonstration uses one trusted owner per isolated profile. Current-patch hosted
CI, Python 3.12 execution and rebuilding the historical submission ZIP were not
part of this focused task. Only local commits are authorized; nothing is pushed.
