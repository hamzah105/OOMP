"""Versioned product settings; existing MCP/domain/database contracts stay intact."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Literal

from pydantic import Field, StrictBool, StrictInt, field_validator, model_validator
from oomp.domain.models import ContractModel, Identifier, AuthorizedScope
from oomp.mcp.configuration import EmbeddingConfiguration, ServerConfiguration, Grant
from .safety import ProductError, profile_name, safe_path


class Profile(ContractModel):
    format_version: Literal[1] = 1
    name: str
    adapter: Literal["standalone", "generic-mcp", "trace"] = "standalone"
    project: str | None = None
    database: str
    transport: Literal["streamable-http", "stdio"] = "streamable-http"
    mode: Literal["read-only", "trusted-ingest"] = "read-only"
    tenant: Identifier = "local"
    namespace: Identifier = "personal"
    principal: Identifier = "local-host"
    port: StrictInt = Field(default=8765, ge=1024, le=65535)
    mind: StrictBool = True
    read_source: StrictBool = False
    provider: EmbeddingConfiguration | None = None
    secret_source: Literal["file", "environment"] = "file"
    owner_id: str | None = Field(default=None, min_length=1, max_length=128)
    host_origin: str = "http://127.0.0.1:8000"
    publication: StrictBool = False
    host_python: str | None = None
    approved_project: dict[str, str] = Field(default_factory=dict)
    mongo_uri_env: str | None = None
    mongo_database: str | None = None

    @field_validator("name")
    @classmethod
    def valid_name(cls, value):
        return profile_name(value)

    @field_validator("database", "project", "host_python")
    @classmethod
    def path(cls, value):
        return str(safe_path(value)) if value is not None else None

    @model_validator(mode="after")
    def policy(self):
        if self.provider:
            self.provider.construct_provider()  # syntax/loopback validation, no I/O
        ServerConfiguration.local_origins((self.host_origin,))
        if self.adapter != "standalone" and not self.project:
            raise ProductError("project_required")
        if self.adapter == "trace":
            if not self.owner_id or self.owner_id == "anonymous" or self.transport != "streamable-http":
                raise ProductError("trace_owner_and_http_required")
        elif self.owner_id or self.publication:
            raise ProductError("trace_settings_require_trace")
        if self.publication and (self.mode != "trusted-ingest" or not self.host_python
                                or not self.approved_project or not self.mongo_database
                                or not self.mongo_uri_env):
            raise ProductError("publication_approval_required")
        if self.mongo_uri_env and not re.fullmatch(r"[A-Z][A-Z0-9_]{0,127}", self.mongo_uri_env):
            raise ProductError("invalid_environment_reference")
        if self.mongo_database and not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", self.mongo_database):
            raise ProductError("invalid_mongo_database")
        return self

    @property
    def identity(self):
        return hashlib.sha256(json.dumps(self.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()

    @property
    def scope(self):
        return AuthorizedScope(tenant_id=self.tenant, namespace=self.namespace, principal_id=self.principal)

    def reference(self, role):
        return "OOMP_" + self.name.upper().replace("-", "_") + "_" + role.upper()

    def grants(self):
        read = Grant(grant_id="host-read", principal_id=self.principal, tenant_id=self.tenant,
                     namespace=self.namespace, capabilities=("read", "read_source") if self.read_source else ("read",),
                     bearer_token_env=self.reference("read_token"))
        writers = {}
        if self.mode == "trusted-ingest":
            roles = ("user", "assistant", "feedback") if self.adapter == "trace" else ("user",)
            for role in roles:
                writers[role] = Grant(grant_id="host-"+role, principal_id=self.principal,
                    tenant_id=self.tenant, namespace=self.namespace, capabilities=("read", "ingest", "read_source") if self.read_source and self.transport == "stdio" else ("read", "ingest"),
                    bearer_token_env=self.reference(role+"_token"),
                    ingest_approval_key_env=self.reference(role+"_approval"),
                    ingest_source_type="assistant" if role == "assistant" else "user",
                    ingest_source_system="trace-ai" if self.adapter == "trace" else "approved-host",
                    ingest_event_types=("feedback" if role == "feedback" else role+"_message",))
        return read, writers

    def secret_roles(self):
        roles = ["read_token"] + (["owner_key"] if self.adapter == "trace" else [])
        _, writers = self.grants()
        return roles + [r+s for r in writers for s in ("_token", "_approval")]

    def server(self):
        read, writers = self.grants()
        return ServerConfiguration(database=self.database, transport=self.transport, profile=self.mode,
            port=self.port, allowed_origins=(self.host_origin,) if self.adapter == "trace" else (),
            http_grants=(read, *writers.values()) if self.transport == "streamable-http" else (),
            stdio_grant=(writers.get("user") or read) if self.transport == "stdio" else None,
            embedding=self.provider)
