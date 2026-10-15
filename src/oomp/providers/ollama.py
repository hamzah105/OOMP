"""Opt-in loopback-only Ollama /api/embed adapter with bounded responses."""

from __future__ import annotations

import ipaddress
import json
import math
from collections.abc import Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from oomp.retrieval.contracts import EmbeddingSpace


class EmbeddingProviderError(ValueError):
    """A local provider failed or returned an invalid embedding payload."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, newurl):
        return None


class OllamaEmbeddingProvider:
    """No network call occurs until embed() is explicitly invoked."""

    def __init__(
        self, *, model: str, dimension: int,
        endpoint: str = "http://127.0.0.1:11434",
        timeout_seconds: float = 15.0,
        version: str = "ollama-api-embed-v1",
        max_input_chars: int = 16384,
        max_batch: int = 16,
        max_response_bytes: int = 4_000_000,
    ) -> None:
        parsed = urlsplit(endpoint)
        try:
            address = ipaddress.ip_address(parsed.hostname or "")
        except ValueError as error:
            raise ValueError("embedding endpoint must use a literal loopback IP address") from error
        if (
            parsed.scheme != "http" or not address.is_loopback
            or parsed.username is not None or parsed.password is not None
            or parsed.path not in {"", "/"} or parsed.query or parsed.fragment
            or parsed.port is None
        ):
            raise ValueError("embedding endpoint must be plain HTTP on a literal loopback IP and port")
        if type(timeout_seconds) not in (int, float) or not math.isfinite(timeout_seconds) or not 0.1 <= timeout_seconds <= 120:
            raise ValueError("embedding timeout must be finite and from 0.1 to 120 seconds")
        if type(max_input_chars) is not int or not 1 <= max_input_chars <= 16384:
            raise ValueError("embedding input limit must be 1 to 16384 characters")
        if type(max_batch) is not int or not 1 <= max_batch <= 16:
            raise ValueError("embedding batch limit must be 1 to 16")
        if type(max_response_bytes) is not int or not 1024 <= max_response_bytes <= 4_000_000:
            raise ValueError("embedding response limit must be from 1024 to 4000000 bytes")
        self.space = EmbeddingSpace(provider="ollama", model=model, version=version, dimension=dimension)
        self.endpoint = endpoint.rstrip("/") + "/api/embed"
        self.timeout_seconds = float(timeout_seconds)
        self.max_input_chars = max_input_chars
        self.max_batch = max_batch
        self.max_response_bytes = max_response_bytes
        self._opener = build_opener(ProxyHandler({}), _NoRedirect())

    def embed(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        if isinstance(texts, (str, bytes)) or not isinstance(texts, Sequence):
            raise TypeError("embedding input must be a sequence of texts")
        if not 1 <= len(texts) <= self.max_batch:
            raise ValueError("embedding batch exceeds configured limit")
        for item in texts:
            if not isinstance(item, str) or not item.strip() or len(item) > self.max_input_chars:
                raise ValueError("embedding text is blank or exceeds configured limit")
        body = json.dumps(
            {"model": self.space.model, "input": list(texts), "truncate": False, "dimensions": self.space.dimension},
            ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8")
        request = Request(
            self.endpoint, data=body, method="POST",
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with self._opener.open(request, timeout=self.timeout_seconds) as response:
                if response.status != 200:
                    raise EmbeddingProviderError("local embedding service returned a non-success status")
                raw = response.read(self.max_response_bytes + 1)
        except HTTPError as error:
            raise EmbeddingProviderError(f"local embedding request failed (HTTP {error.code})") from None
        except (URLError, OSError, TimeoutError):
            raise EmbeddingProviderError("local embedding service is unavailable") from None
        if len(raw) > self.max_response_bytes:
            raise EmbeddingProviderError("local embedding response exceeds configured limit")
        try:
            document = json.loads(raw)
        except (ValueError, UnicodeError, RecursionError):
            raise EmbeddingProviderError("local embedding response is invalid JSON") from None
        if not isinstance(document, dict) or document.get("model") != self.space.model:
            raise EmbeddingProviderError("local embedding response model differs from the requested model")
        vectors = document.get("embeddings")
        if not isinstance(vectors, list) or len(vectors) != len(texts):
            raise EmbeddingProviderError("local embedding response count is invalid")
        result = []
        for vector in vectors:
            if not isinstance(vector, list) or len(vector) != self.space.dimension:
                raise EmbeddingProviderError("local embedding dimension differs from configured space")
            values = []
            for value in vector:
                if type(value) not in (int, float):
                    raise EmbeddingProviderError("local embedding vector contains a non-finite number")
                try:
                    numeric = float(value)
                except OverflowError:
                    raise EmbeddingProviderError("local embedding vector contains an oversized number") from None
                if not math.isfinite(numeric):
                    raise EmbeddingProviderError("local embedding vector contains a non-finite number")
                values.append(numeric)
            norm = math.hypot(*values)
            if not math.isfinite(norm) or norm <= 0:
                raise EmbeddingProviderError("local embedding vector has invalid norm")
            result.append(tuple(values))
        return tuple(result)

    def embed_text(self, text: str) -> tuple[float, ...]:
        return self.embed((text,))[0]

    def embed_query(self, query: str) -> tuple[float, ...]:
        return self.embed((query,))[0]