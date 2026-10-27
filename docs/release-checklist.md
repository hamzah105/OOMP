# 0.1.0 research release checklist

This is a local **conditional research candidate**, not a published release or
production-cloud certification. Version remains **0.1.0**, intended license
**Apache-2.0**, schema **v5**. The final executed results are in
[Stage 10 validation](stage10-validation.md) and [the 40-item report](stage-10-report.md).

## Completed source preparation

- [x] Clean/reconciled baseline verified against live origin/main, including LICENSE commits.
- [x] Existing 498-test suite executed before changes.
- [x] Apache-2.0 license metadata/NOTICE and explicit source archive policy prepared.
- [x] Runtime dependency and core algorithm/schema/API boundaries preserved.
- [x] New synthetic quickstart and WAL-safe backup/restore example with regressions.
- [x] Clean installed-archive/CLI/content validation scripts and CI workflow created.
- [x] User/developer/API/privacy/security/troubleshooting guides and contributor materials.
- [x] Original Stage 9 strengths, ties, false matches, path limits and absent live answers preserved.
- [x] Manuscript draft with verified primary metadata, limitations and assistance disclosure.

Actual build, clean-install, Python, tests, scanner and examples are acceptance
checks, not inferred from the above source-preparation boxes. Their exact final
status/counts/artifact inventory are recorded in the linked validation/report.

## Required human/remote decisions before publication

- [ ] Review and accept the candidate and its limitations; confirm contribution/attribution rights.
- [ ] Use currently patched supported Python/SQLite/OS runtimes for deployment;
  local interpreter versions establish compatibility, not a runtime-security endorsement.
- [ ] Push the reviewed commit manually and inspect actual Windows/Linux × Python 3.11/3.12 CI runs.
- [ ] Enable GitHub private vulnerability reporting or establish a real confidential channel.
- [ ] Confirm PyPI account rights/name availability at publication time. The exact official
  project JSON/simple endpoints returned 404 during preparation; this reserves nothing.
- [ ] Decide whether to publish 0.1.0 as the alpha research artifact or choose another
  deliberate version and update all version surfaces/rebuild/retest consistently.
- [ ] Inspect the final wheel/sdist inventory, scanner coverage, license/NOTICE and
  repository diff; ensure no personal source data, tokens or private generated output.
- [ ] Confirm any research artifact/data sharing and manuscript authorship/submission separately.

A new critical security/licensing issue blocks publication. Current known risks
include plaintext local storage, constrained erasure, trusted administrators,
loopback-only network assumptions, model prompt risk and limited research evidence.
[Focused review](security-review.md), [limitations](limitations.md).

## Build/verify commands

Use a patched installer and isolated maintainer tools, from a clean reviewed tree:

~~~powershell
python -m pip install --upgrade "pip>=26.2.2,<27"
python -m pip install -r requirements-release.txt
python -m build
python -m twine check dist/*
python scripts/check_artifacts.py dist --output artifact-inventory.json
python scripts/check_clean_installs.py --dist dist --output .test-artifacts/final-clean-installs
python -m pytest -v
python -m compileall -q src tests benchmarks examples scripts
python -m pip check
git diff --check
~~~

Use new/clean output locations and inspect actual hashes. Do not publish an old
artifact left under the same version. Scanner failures/unavailable services are
not passing audits; the unpublished local package is reviewed as source, not
certified by its absent PyPI advisory record. Remote CI is not executed until pushed.

## Publishing commands — manual only

After **all** decisions/checks above and account authorization, a maintainer may
choose to upload the inspected files, for example `python -m twine upload --repository
testpypi dist/*`, review the separate TestPyPI project/dependencies, then separately
authorize `python -m twine upload dist/*`. Credentials belong in a supported
interactive/secret mechanism, not a command line, source file or transcript.
These are instructions only; no upload was executed by release preparation.

Commit, tag, push and GitHub Release creation are independent manual decisions.
No workflow publishes to either registry or creates a release. Remote/main may
change after the reconciliation check; inspect/fetch/reconcile normally, without
force-pushing or discarding user work.
