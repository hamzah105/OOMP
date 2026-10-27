# Contributing

OOMP welcomes reproducible bug reports, documentation corrections and carefully
scoped research/provider proposals. Use the repository's
[issues](https://github.com/hamzah105/OOMP/issues) or a pull request. For sensitive
findings follow [SECURITY.md](SECURITY.md), not a public exploit report.

The runtime requires Python 3.11+; development/release checks target 3.11 and 3.12.
Windows is locally exercised and Windows/Linux CI is configured; actual remote
status is reported separately. Install `.[dev,mcp]`, run `python -m pytest -v`,
`python -m compileall -q src tests benchmarks examples scripts` and
`python -m pip check`. [Full developer setup](docs/developer-guide.md).

Use four spaces, explicit UTF-8, existing typed/Pydantic contracts and small changes
consistent with neighboring code. There is no unannounced formatter requirement.
Add meaningful regressions for correctness/security changes, preserve earlier
cases and disclose unexecuted checks. Do not edit frozen research fixtures/results
to improve a score. New tuning requires a new evaluation split/run identity.

Migration changes must preserve applied SQL/history and add exact data-preservation,
rollback and version-rejection tests. No silent reset, implicit initialization on
read or change of tenant/provenance policy. Covered alpha APIs should remain
compatible where practical; breaking externally consumed behavior needs an explicit
proposal/changelog and maintainer decision. [API boundaries](docs/api-reference.md).

For an embedding provider, propose model-space identity, transport/privacy policy,
normalization/dimension checks, complete-index behavior and bounded failures.
For an MCP integration, identify the actual client/SDK, server-owned credentials,
approval boundary, evidence/prompt accounting and negative/security tests. New
adapters must not grant models privileged writes, deletion, scope changes or signing keys.

Contribute only material you are entitled to license under Apache-2.0. Preserve
third-party notices and disclose copied/licensed material or AI-tool assistance
where relevant. Do not add real chats, tokens, embeddings, model weights, database
snapshots or personal details to issues, tests or commits. Existing synthetic
examples are the preferred reproduction format. No contributor agreement or
security-response team is invented by this guide; human maintainers review changes.
