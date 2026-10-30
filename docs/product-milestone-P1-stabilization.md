# P1 stabilization — 29 October 2026

The owner reported successful synthetic onboarding, authenticated ingestion,
restart, diagnostics and cleanup using `product_quickstart.py`. That acceptance
is owner-supplied evidence; this assignment does not reuse its database.

## Starting evidence

Local and live GitHub main were both
`7528aff011cd33c7d6482eae068ead65779351ba`, with a clean working tree.
The unmodified Windows Python 3.11.4 suite passed **575/575** in 553.56 seconds.
The latest inspected Actions run, **40771852431**, failed all four test matrix
jobs; its distribution job passed. Actual job logs, including Windows job
123110818956 and Ubuntu job 123110818751, were inspected and saved in the
ignored task evidence directory `.test-artifacts/product-P2-20261029`.

## Causes and fixes

Windows reported 29 `private_permissions_required` failures. The checker
serialized the DACL to SDDL and compared trustee spelling against the numeric
token SID. Windows can serialize the built-in administrator's domain-relative
SID as `LA`. An in-memory native API reproduction produced
`D:P(A;;FA;;;LA)(A;;FA;;;SY)`; the CI logs themselves do not expose their token
SID. This is the supported root-cause explanation, rather than a claim that we
inspected the remote runner's binary token.

The checker now uses native binary `EqualSid` comparisons against the actual
process-token user and SYSTEM. It requires a protected, present, nonempty DACL,
effective explicit allow ACEs, no other trustee, and full access for the current
user. Deny, inherit-only, inherited and unknown ACE types fail closed. There is
no administrator-group exemption and no relaxation of the POSIX permission
policy. Token storage stays alive through the binary check.

Microsoft documents both the [LA SID alias](https://learn.microsoft.com/en-us/windows/win32/secauthz/sid-strings)
and [binary SID equality](https://learn.microsoft.com/en-us/windows/win32/secauthz/security-identifiers).

Ubuntu reported one approved-publication dry-run failure. Its fixture passed
the setup-python executable symlink directly into a path contract that
deliberately refuses links. The fixture now supplies the resolved executable,
as its other publication fixtures already did. Production path and host-code
approval rules are unchanged. A regression checks link refusal when the OS
allows creating a synthetic symlink.

The interactive wizard now requests a project directory immediately after
TRACE or generic-MCP selection, safely rediscovers and displays framework/kind
indicators, and offers retry, return to adapter selection, or cancellation.
These paths precede authority/storage/provider questions and create no files.
Standalone needs no project. Noninteractive consent rules remain unchanged.

Changed implementation: `src/oomp/product/safety.py`,
`src/oomp/product/cli.py`; regression changes:
`tests/test_product_trace.py`, `tests/test_product_stabilization.py`.

## Validation gate

The 60 existing P1 tests plus 16 stabilization regressions passed **76/76** on
Windows Python 3.11.4 (105.40 seconds) and Python 3.12.6 (100.83 seconds).
The wheel and source archive built, passed `twine check`, and each passed the
existing clean-install verifier in its own new core-only environment, including
`pip check`, CLI and source-to-memory flow. Evidence is in `p1-gate-311.*`,
`p1-gate-312.*`, `p1-build.txt`, `p1-installs.txt` and
`p1-installs/clean-installs.json` under the ignored evidence directory.

Native Windows SID tests ran rather than being skipped. A synthetic executable
symlink test checks refusal where creating links is permitted. No Linux runtime
is claimed by these local Windows results. All test databases and credentials
are synthetic and disposable. No source change was made before the 575-test
baseline completed; P2 implementation began only after this stabilization gate.

## Remote gate

**Remote CI remains pending.** No commit, push, workflow dispatch, publication,
deployment, private database migration, or TRACE application edit is authorized
or performed. The owner can review this working-tree patch and then run the
unchanged Windows/Ubuntu Python 3.11/3.12 matrix. Local tests cannot establish
that a future hosted run will be green.
