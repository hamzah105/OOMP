# Updating an existing TRACE source approval

`approve-project` updates only the host-code fingerprint of an existing,
publication-enabled TRACE profile. It does not onboard another profile, change
an owner, rotate credentials, open SQLite/MongoDB, migrate data or start services.
Normal `config`, onboarding and `--approve-trace-integration` retain their existing
restrictions; they do not bypass source approval.

Stop TRACE and the authenticated OOMP supervisor first. The operation takes the
launch, operation and saved-selection locks, requires definite supervisor exit
and free control/MCP/TRACE ports, and rejects ambiguous ownership. Existing
private permissions, no-link validation, source inventory, signed connection and
generation integrity must validate. Do not edit a running reloader checkout.

Preview the final checked-out bytes, including Windows line endings:

```powershell
oomp approve-project --home <existing-home> --profile <existing-profile> --dry-run --json
```

Review `changed_sources`, the old/new generation IDs and `plan_sha256` against the
accepted source. Only then apply that exact preview:

```powershell
oomp approve-project --home <existing-home> --profile <existing-profile> --yes --expected-plan <plan_sha256> --json
```

The command preserves the old generation, builds an immutable new generation,
and retains the exact old signed handoff/default-pin bytes in a private,
HMAC-signed `history/approval-<id>/transaction.json`. It uses the existing owner
key to sign the new reference-only handoff. Credentials, grants, identities,
database paths, server/client/writer configuration and unrelated defaults remain
unchanged. A same-profile saved default receives the new authority digest.

An interrupted transaction leaves `approval-pending.json`. Normal profile loads
fail closed, and an intermediate TRACE handoff is deliberately invalid. All
metadata replacements are atomic individually; the journal and explicit rollback
handle interruption across files. This is not a claim of one filesystem-wide
atomic transaction or coordination with an independently launched host that
ignores the stopped-service maintenance window.

For rollback, keep services stopped, restore the previously approved exact source
bytes first, and use the transaction ID returned by the applied update:

```powershell
oomp rollback-approval --home <existing-home> --profile <existing-profile> --transaction <approval-id> --dry-run --json
oomp rollback-approval --home <existing-home> --profile <existing-profile> --transaction <approval-id> --yes --expected-plan <rollback-plan_sha256> --json
```

Rollback verifies the signed journal, unchanged credentials/generation artifacts,
old source fingerprint and recognized current metadata. It refuses to overwrite
unrelated edits or another pending transaction. Old generations and the journal
are retained; credentials and memory databases are never restored or deleted.
Journal files contain private profile metadata and signed handoffs; keep their
existing private permissions and exclude them from source control.

Starting a publication-enabled profile afterwards is a separate authorization:
it resumes eligible, already-approved pending/retry/expired-lease publication,
may reconcile missing event entries for approved rows, and runs normal Mind
processing. MongoDB acknowledgement and SQLite memory/job writes are durable.
Code/approval rollback does not undo them, authorize legacy backfill or revive
permanently failed events. A startup readiness result is not sustained stability
or real-model answer acceptance.
