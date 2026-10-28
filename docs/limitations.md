# Implementation and deployment limitations

Product P1 adds local onboarding/profiles/supervision and diagnostics; it does not
improve the memory-intelligence/research limits below. Its tested environment,
owned-process/host limitations and outstanding checks are in
[the P1 report](product-milestone-P1-report.md) and [product security](product-security.md).

Version 0.1.0 is an alpha local research candidate. Engineering tests establish
specified behavior on the exercised environments, not production readiness.

- **Storage:** plaintext SQLite on a local filesystem, not a distributed database.
  WAL/transactions do not protect against a hostile administrator, damaged
  hardware, lost backups or arbitrary network filesystem semantics.
- **Authority:** scope values require trusted application issuance. Local CLI
  tenant strings do not authenticate callers. HTTP supports a preissued-grant,
  loopback-focused profile, without public TLS/proxy/OAuth deployment readiness.
- **Extraction:** a conservative deterministic grammar, limited roles and explicit
  project aliases. Unsupported prose, modality/questions and heuristic secret
  patterns may yield no memory. The original source may still be sensitive.
- **Governance:** protected temporal conflict/supersession supports a narrow
  source-grounded RAM policy. No general factual verifier, semantic resolver,
  automatic authoritative latest-claim winner or unrestricted entity merge.
- **Time:** reported validity and system recording time differ. Legacy recording
  history and entity association clocks can be incomplete; explicit known-at
  retrieval disables the unhistoried entity lane. Unknown validity stays uncertain.
- **Retrieval:** bounded scoped FTS5 and exact cosine scans, not large-scale ANN.
  Graph neighborhood depth is at most two. Ordinary paths for independently
  ranked endpoints need not be attached. Ranking scores are not truth probabilities.
- **Embeddings:** optional explicit local model, complete compatible vector space,
  finite/nonzero dimensions and an uncalibrated cosine threshold. Quality,
  capacity, server retention and caches depend on that separately installed model.
- **Budget:** default accounting counts UTF-8 evidence bytes, not exact tokenizer
  output. MCP envelope/host prompts add overhead. A budget does not extend native
  model context or guarantee factual or injection-safe model answers.
- **Mind:** explicitly run same-host durable workers with bounded leases/retries.
  Summary projections are extractive, separate from canonical recall; no new
  autonomous learned consolidation algorithm or distributed coordinator.
- **Erasure:** constrained privileged local workflow; unsupported dependencies
  block. Logical erasure does not securely wipe WAL/free pages/backups/exports or
  revoke data already returned. Restoring old backups requires retention reconciliation.
- **MCP:** actual official SDK 2.3.0 clients were exercised. Modern/legacy protocol
  compatibility does not certify all desktop hosts, IPv6, browsers or cloud clients.
- **Research:** related synthetic templates, curated structures, small independent
  samples, one repetition and concurrent desktop work limit generalization. Flat
  vectors and hybrid OOMP tied on four positives and false-matched four negatives.
  Default graph expansion showed no recall/path gain in the held-out workload.
  Live LLaMA comparative answer quality and independent human review remain absent.

The source candidate includes Windows/Linux × Python 3.11/3.12 CI configuration.
Only executed local results are claimed; a green remote CI matrix is pending a
user push and actual workflow runs. See [current validation](stage10-validation.md)
and [release gates](release-checklist.md). Do not deploy a public memory server
or label this enterprise-ready without additional engineering and testing.
