"""Explicit trusted configuration; no SDK import, database creation or env-file loading."""
from __future__ import annotations

import ipaddress
import json
import os
import re
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, StrictInt, field_validator, model_validator
from oomp.domain.models import ContractModel, Identifier, UtcDateTime
from oomp.domain.enums import EventType, SourceType

Capability = Literal["read", "read_source", "ingest"]
Transport = Literal["stdio", "streamable-http"]
_ENV = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")


class Grant(ContractModel):
    grant_id: Identifier
    principal_id: Identifier
    tenant_id: Identifier
    namespace: Identifier
    capabilities: tuple[Capability, ...] = ("read",)
    bearer_token_env: str | None = None
    expires_at: UtcDateTime | None = None
    ingest_approval_key_env: str | None = None
    ingest_source_type: SourceType | None = None
    ingest_source_system: Identifier | None = None
    ingest_event_types: tuple[EventType, ...] = ()

    @field_validator("bearer_token_env", "ingest_approval_key_env")
    @classmethod
    def env_name(cls, value):
        if value is not None and not _ENV.fullmatch(value):
            raise ValueError("invalid environment-variable name")
        return value

    @model_validator(mode="after")
    def capability_policy(self):
        if "read" not in self.capabilities or len(self.capabilities) > 3:
            raise ValueError("an explicit read capability is required")
        if len(self.capabilities) != len(set(self.capabilities)):
            raise ValueError("duplicate capabilities")
        if "ingest" not in self.capabilities:
            if any((self.ingest_approval_key_env, self.ingest_source_type,
                    self.ingest_source_system, self.ingest_event_types)):
                raise ValueError("ingest settings require ingest capability")
            return self
        if not all((self.ingest_approval_key_env, self.ingest_source_type,
                    self.ingest_source_system, self.ingest_event_types)):
            raise ValueError("ingest role, provenance, approval key and event types are required")
        if self.ingest_source_type is SourceType.SYSTEM:
            raise ValueError("system-source ingestion is not exposed")
        if not 1 <= len(self.ingest_event_types) <= 6 or len(set(self.ingest_event_types)) != len(self.ingest_event_types):
            raise ValueError("invalid allowed event types")
        roles = {
            EventType.USER_MESSAGE: SourceType.USER,
            EventType.ASSISTANT_MESSAGE: SourceType.ASSISTANT,
            EventType.DOCUMENT: SourceType.DOCUMENT,
            EventType.TOOL_RESULT: SourceType.TOOL,
        }
        if any(roles.get(t, self.ingest_source_type) is not self.ingest_source_type for t in self.ingest_event_types):
            raise ValueError("source role and event types disagree")
        return self


class EmbeddingConfiguration(ContractModel):
    provider: Literal["ollama"] = "ollama"
    model: str = Field(min_length=1, max_length=128)
    dimension: StrictInt = Field(ge=1, le=4096)
    version: Identifier
    endpoint: str = "http://127.0.0.1:11434"
    timeout_seconds: float = Field(default=15, ge=.1, le=120)

    def construct_provider(self):
        from oomp.providers.ollama import OllamaEmbeddingProvider
        return OllamaEmbeddingProvider(
            model=self.model, dimension=self.dimension, version=self.version,
            endpoint=self.endpoint, timeout_seconds=self.timeout_seconds,
        )


class ServerConfiguration(ContractModel):
    database: str = Field(min_length=1, max_length=4096)
    transport: Transport = "stdio"
    profile: Literal["read-only", "trusted-ingest"] = "read-only"
    stdio_grant: Grant | None = None
    http_grants: tuple[Grant, ...] = Field(default=(), max_length=16)
    host: Literal["127.0.0.1", "::1"] = "127.0.0.1"
    port: StrictInt = Field(default=8765, ge=1, le=65535)
    allowed_origins: tuple[str, ...] = Field(default=(), max_length=8)
    max_request_bytes: StrictInt = Field(default=131072, ge=1024, le=1048576)
    max_result_bytes: StrictInt = Field(default=262144, ge=4096, le=1048576)
    max_concurrent_calls: StrictInt = Field(default=4, ge=1, le=16)
    embedding: EmbeddingConfiguration | None = None

    @field_validator("database")
    @classmethod
    def file_database(cls, value):
        if not value.strip() or value == ":memory:" or "\0" in value:
            raise ValueError("an explicit durable database path is required")
        return value

    @field_validator("allowed_origins")
    @classmethod
    def local_origins(cls, values):
        for value in values:
            parsed = urlsplit(value)
            try:
                local = ipaddress.ip_address(parsed.hostname or "").is_loopback
                port = parsed.port
            except ValueError:
                raise ValueError("origins must use literal loopback addresses") from None
            if (not local or parsed.scheme != "http" or parsed.path
                    or parsed.query or parsed.fragment or parsed.username is not None
                    or parsed.password is not None or (port is not None and not 1 <= port <= 65535)):
                raise ValueError("invalid local origin")
        if len(values) != len(set(values)):
            raise ValueError("duplicate origins")
        return values

    @model_validator(mode="after")
    def trusted_profile(self):
        grants = self.http_grants + ((self.stdio_grant,) if self.stdio_grant else ())
        if len({g.grant_id for g in grants}) != len(grants):
            raise ValueError("grant identities must be unique")
        if self.profile == "read-only" and any("ingest" in g.capabilities for g in grants):
            raise ValueError("ingest requires the trusted-ingest profile")
        if self.transport == "stdio" and self.stdio_grant is None:
            raise ValueError("stdio requires an explicit grant")
        if self.transport == "streamable-http":
            if not self.http_grants or any(g.bearer_token_env is None for g in self.http_grants):
                raise ValueError("HTTP requires explicit credential grants")
        return self

    @property
    def origin(self):
        host = f"[{self.host}]" if ":" in self.host else self.host
        return f"http://{host}:{self.port}"

    @property
    def endpoint(self):
        return self.origin + "/mcp"

    @property
    def origins(self):
        return self.allowed_origins or (self.origin,)

    def with_transport(self, transport: Transport | None):
        data = self.model_dump(mode="json")
        if transport is not None:
            data["transport"] = transport
        return type(self).model_validate(data)


def load_configuration(path: str | None, transport: Transport | None = None) -> ServerConfiguration:
    value = path or os.environ.get("OOMP_MCP_CONFIG")
    if not value:
        raise ValueError("explicit MCP configuration is required")
    file = Path(value).expanduser().resolve()
    with file.open("rb") as handle:
        content = handle.read(65537)
    if len(content) > 65536:
        raise ValueError("configuration exceeds limit")
    data = json.loads(content.decode("utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("configuration must be an object")
    if transport is not None:
        data["transport"] = transport
    config = ServerConfiguration.model_validate(data)
    database = Path(config.database).expanduser()
    if not database.is_absolute():
        database = file.parent / database
    return ServerConfiguration.model_validate({**config.model_dump(mode="json"),
                                               "database": str(database.resolve())})