# Supervisor failure diagnostics and bounded publication recovery

Startup success is an authenticated readiness observation, not a guarantee of
future service health. The supervisor continues checking owned child liveness,
heartbeats and completed work. All-or-nothing supervision is unchanged: an
unrecoverable child failure stops the owned service set.

`oomp status --json` retains the legacy `last_error_code` and adds an optional
`failure` object after shutdown. `oomp logs` returns the same bounded details:

```json
{"role":"publication","kind":"child_reported_failure","stage":"reconcile","reason":"mongo_connection_failed","exit_code":1}
```

Roles, stages, kinds and reasons are explicit finite allowlists. Exit codes are
bounded integers. Unknown exceptions remain `unknown_error`; messages, URIs,
source text, prompts, control tokens and raw stderr are never diagnostic fields.
Malformed child status fails closed. A fatal status immediately makes that child
unready, even if cleanup or library threads keep its process alive. Later
heartbeats cannot erase the fatal report. Process exit, a 12-second heartbeat
timeout and a 180-second work-progress timeout remain distinct. Heartbeats do not
count as completed progress.

The TRACE bridge reports the first fault before Mongo cleanup. It identifies
imports/configuration, Mongo connection, reconciliation and delivery stages.
Only transient PyMongo `ConnectionFailure` subclasses escaping the work loop
receive bounded recovery: at most three consecutive attempts, separated by
0.5 and 1 second waits. A successful complete work pass resets this counter.
Permanent Mongo errors and unknown exceptions remain fatal. Exhaustion is fatal.
No supervisor restart loop is introduced.

Recovery reuses TRACE's conditional reconciliation, claim leases, fencing,
idempotent event identities and durable-receipt checks. It does not reset event
state, retry permanently failed work, backfill historical chats or report an
uncertain acknowledgement as delivery. Invalid-source warnings are visible
without making a healthy worker falsely unready.

Windows startup locks acquire the OS byte range before initializing an empty
lock file. This prevents a competing starter from writing into another handle's
locked byte. PR #6's private-state checks, configuration fencing, atomic stale
archive and retained-handle cleanup remain in force. A PID read from a file never
authorizes a signal. Legacy runtime records remain supported; the new optional
failure object is strictly validated during stale recovery.

The repair is stacked on unmerged PR #6. Its separate TRACE companion rejects
malformed feedback through existing source-validation and permanent-failure
contracts. A demonstrated personal-explanation paraphrase also receives the
existing bounded preference-topic expansion; it does not change grants,
source entailment, extraction, ranking weights or stored memories.

Validate using disposable synthetic storage. Do not start an existing live
profile as a read-only diagnostic: its publisher may deliver approved pending
events. Changed pinned TRACE publisher code requires owner review and an
explicit approval refresh before live deployment; do not bypass the fingerprint
guard or regenerate credentials. No private-profile update, live restart,
migration, release or model download accompanies this repair.

Historical live logs identify publication as the first fatal reporter, but its
original catch-all discarded the exception. Transient Mongo failure and malformed
feedback have been reproduced synthetically; neither is claimed as the proven
historical trigger. Future failures retain actionable bounded evidence.

For an existing profile, the separate [stopped source-approval procedure](project-approval.md)
provides exact-preview refresh and signed-journal rollback without credential
rotation or database access. It does not start services or authorize pending work.
