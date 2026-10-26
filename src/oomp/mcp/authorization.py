"""Trusted grants and host-only, payload-bound ingestion approvals.

The approval signer is a host API, never an MCP tool. Possession of the separate
approval key represents host approval, not a claim that OOMP verified human consent.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable

from oomp.domain.models import AuthorizedScope
from .configuration import Grant, ServerConfiguration
from .contracts import ApprovalProof, IngestPayload, IngestArguments
from .errors import BoundaryError

_SECRET = re.compile(r"^[A-Za-z0-9_-]{43,256}$")
_APPROVAL_DOMAIN = "oomp.mcp.ingest.approval.v1"


def _key(value: str) -> bytes:
    if not isinstance(value, str) or not _SECRET.fullmatch(value):
        raise ValueError("invalid secret configuration; use a generated 32-byte-or-longer secret")
    return value.encode("ascii")


def _now(clock: Callable[[], datetime]) -> datetime:
    value = clock()
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("authorization clock must be timezone-aware")
    return value.astimezone(timezone.utc)


def _approval_message(grant: Grant, payload: IngestPayload, proof: ApprovalProof) -> bytes:
    return json.dumps({
        "domain": _APPROVAL_DOMAIN,
        "grant": {
            "grant_id": grant.grant_id, "principal_id": grant.principal_id,
            "tenant_id": grant.tenant_id, "namespace": grant.namespace,
            "source_type": grant.ingest_source_type.value if grant.ingest_source_type else None,
            "source_system": grant.ingest_source_system,
            "event_types": [t.value for t in grant.ingest_event_types],
        },
        "payload": payload.model_dump(mode="json"),
        "approval": proof.model_dump(mode="json", exclude={"signature"}),
    }, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")


def approve_ingestion(
    grant: Grant, payload: IngestPayload, approval_key: str, *,
    ttl_seconds: int = 60, now: datetime | None = None,
) -> ApprovalProof:
    """Trusted host calls this only after approving the exact original event."""
    grant = Grant.model_validate(grant.model_dump(mode="json"))
    payload = IngestPayload.model_validate(payload.model_dump(mode="json"))
    if "ingest" not in grant.capabilities:
        raise BoundaryError("forbidden")
    if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 300:
        raise ValueError("approval lifetime must be 1 to 300 seconds")
    issued = _now(lambda: now or datetime.now(timezone.utc))
    unsigned = ApprovalProof(
        issued_at=issued, expires_at=issued + timedelta(seconds=ttl_seconds),
        nonce="approval-" + secrets.token_hex(16), signature="0" * 64,
    )
    signature = hmac.new(_key(approval_key), _approval_message(grant, payload, unsigned), hashlib.sha256).hexdigest()
    return ApprovalProof.model_validate({**unsigned.model_dump(mode="json"), "signature": signature})


@dataclass(frozen=True)
class _Credential:
    grant: Grant
    token_digest: bytes | None = field(repr=False)
    approval_key: bytes | None = field(repr=False)


class GrantResolver:
    def __init__(
        self, config: ServerConfiguration, *,
        environ: dict[str, str] | None = None,
        clock: Callable[[], datetime] | None = None,
    ):
        self.config = config
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        environment = os.environ if environ is None else environ
        grants = ((config.stdio_grant,) if config.transport == "stdio" else config.http_grants)
        entries = {}
        used_tokens = set()
        raw_tokens = []
        for grant in grants:
            if grant is None:
                raise ValueError("missing trusted grant")
            digest = None
            if config.transport == "streamable-http":
                token = _key(environment.get(grant.bearer_token_env or "", ""))
                digest = hashlib.sha256(token).digest()
                if digest in used_tokens:
                    raise ValueError("duplicate credential configuration")
                used_tokens.add(digest)
                raw_tokens.append(token)
            approval = None
            if "ingest" in grant.capabilities:
                approval = _key(environment.get(grant.ingest_approval_key_env or "", ""))
            entries[grant.grant_id] = _Credential(grant, digest, approval)
        if any(entry.approval_key in raw_tokens for entry in entries.values() if entry.approval_key):
            raise ValueError("approval and bearer credentials must be distinct")
        self._entries = entries

    def _live(self, grant: Grant) -> bool:
        return grant.expires_at is None or _now(self.clock) < grant.expires_at

    async def verify_token(self, token: str):
        """Official SDK TokenVerifier protocol implementation."""
        from mcp.server.auth.provider import AccessToken
        try:
            digest = hashlib.sha256(_key(token)).digest()
        except (ValueError, UnicodeError):
            return None
        matched = None
        for entry in self._entries.values():
            if entry.token_digest is not None and secrets.compare_digest(digest, entry.token_digest):
                matched = entry.grant
        if matched is None or not self._live(matched):
            return None
        return AccessToken(
            token=token, client_id=matched.grant_id,
            subject=matched.principal_id,
            scopes=["memory:" + c for c in matched.capabilities],
            resource=self.config.endpoint,
            expires_at=int(matched.expires_at.timestamp()) if matched.expires_at else None,
        )

    def resolve(self) -> Grant:
        if self.config.transport == "stdio":
            grant = self.config.stdio_grant
        else:
            from mcp.server.auth.middleware.auth_context import get_access_token
            token = get_access_token()
            entry = self._entries.get(token.client_id) if token is not None else None
            grant = entry.grant if entry else None
            if (grant is None or token.subject != grant.principal_id
                    or token.resource != self.config.endpoint):
                raise BoundaryError("unauthorized")
        if grant is None or not self._live(grant):
            raise BoundaryError("unauthorized")
        return grant

    @staticmethod
    def scope(grant: Grant) -> AuthorizedScope:
        return AuthorizedScope(tenant_id=grant.tenant_id, namespace=grant.namespace,
                               principal_id=grant.principal_id)

    def verify_approval(self, grant: Grant, arguments: IngestArguments) -> IngestPayload:
        entry = self._entries.get(grant.grant_id)
        if (self.config.profile != "trusted-ingest" or "ingest" not in grant.capabilities
                or entry is None or entry.approval_key is None):
            raise BoundaryError("forbidden")
        proof = arguments.approval
        now = _now(self.clock)
        lifetime = (proof.expires_at - proof.issued_at).total_seconds()
        if (not 0 < lifetime <= 300 or now >= proof.expires_at
                or proof.issued_at > now + timedelta(seconds=30)):
            raise BoundaryError("forbidden")
        payload = IngestPayload.model_validate(arguments.model_dump(mode="json", exclude={"approval"}))
        wanted = hmac.new(entry.approval_key, _approval_message(grant, payload, proof), hashlib.sha256).hexdigest()
        if not secrets.compare_digest(proof.signature, wanted):
            raise BoundaryError("forbidden")
        if (payload.event_type not in grant.ingest_event_types
                or payload.source_reference.source_system != grant.ingest_source_system):
            raise BoundaryError("forbidden")
        return payload