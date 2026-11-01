# P4A synthetic context evaluation

`fixtures/v1/manifest.json` freezes the fictional three-session sources and the
pre-registered queries, gold source identities, relevant/irrelevant labels,
abstention controls, budgets, baseline configurations and acceptance thresholds.
The v1 policy was authored before context ranking implementation or tuning.
Labels are developer-authored and still require independent/owner review.

The separately hashed `setup-policy.json` supplement was frozen before the first
run. It leaves the original inputs/gold/configuration unchanged and specifies
explicit consent to fictional topic-only sensitive episodes, real rules-only
Mind jobs, the recording cutoff, mock-vector algorithm and timing denominators.
The runner verifies its hash sidecar and its reference to the original manifest.

The 15 owned source turns are ingested through real rules-only Mind jobs and
explicit P3 projection. Session 2 questions are evaluation requests, not inserted
as source facts. Two separate tenant/principal pet-name controls must not become
the owner's pet evidence. Legacy canonical retrieval is namespace-scoped; any
foreign-principal baseline behavior is reported explicitly rather than silently
changing its contract.

Primary quality uses a 6,000-unit evidence budget. The 1,200-unit constrained
budget measures exclusions without imposing an impossible fixed recall target;
a one-unit control checks honest budget exclusion. Ranking parameters are frozen
in the preregistration. Graph expansion is off by default and evaluated separately
at depth one. The deterministic keyword-vector provider is a mechanics fixture,
not evidence of real embedding quality. No answer model is called.

The frozen depth-one ablation changes only `graph_depth`; it does not add
gold-derived exact object anchors. It enables the existing canonical graph and
only P3 traversal actually reached by the planner's supplied anchors. Inspect
the raw trace counters: a run with zero P3 traversal is not evidence of either
P3 graph benefit or P3 graph failure. Explicit-anchor traversal belongs in a
separately labeled mechanics diagnostic, not substituted into this comparison.

The frozen `primary_required_query_ids` label names six cases, but only five
have positive gold source sets: project, moving, decision, style and earlier-name.
The sixth is the unknown-pet abstention control. The primary source-recall gate
is an unweighted mean across those five positive cases; pet is evaluated
separately alongside current-session-only and vague-request abstention. Results
expose declared, positive, observed and abstention query IDs/counts. The original
`required_six` metric label is retained with this caveat; inputs, gold and
thresholds are unchanged.

`Source Recall@k` uses the first eight distinct returned source-event IDs after
byte-budget packing, with proof-manifest order within a multi-source unit.
`Source Recall@budget` uses all distinct returned source IDs from that same
packed response. They coincide when at most eight sources are returned. This
evaluation does not measure a separate pre-packing candidate-ranking Recall@k,
and those two metrics must not be presented as independent quality evidence.

Run only inside the approved offline/resource-guarded environment:

```powershell
python -B -m benchmarks.context.runner --directory <fresh-short-result-directory>
```

The console output is a summary; `per_query.jsonl` preserves every returned
synthetic packet, source score, failure and explicitly requested query plan.
`result.json` records source metrics, acceptance gates, resource/cost scope and
whether the complete preregistered denominator ran. No failed call is retried.

Every evaluation output must use a fresh directory. Keep raw per-query records,
timings, source manifests, resource metrics, failures and unfinished denominators.
Do not replace historical Stage 9, P2 or P3 inputs/results. Changed inputs, gold,
budgets, thresholds or tuning policy require a new explicitly labeled version.
