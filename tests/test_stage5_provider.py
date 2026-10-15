from __future__ import annotations

import io
import json

import pytest

from oomp.providers import EmbeddingProviderError, OllamaEmbeddingProvider


class _Response:
    status = 200

    def __init__(self, payload):
        self.body = io.BytesIO(json.dumps(payload).encode("utf-8"))

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.body.close()

    def read(self, limit):
        return self.body.read(limit)


class _Opener:
    def __init__(self, payload):
        self.payload = payload
        self.request = None

    def open(self, request, timeout):
        self.request = request
        return _Response(self.payload)


def test_opt_in_provider_sends_bounded_untruncated_embed_request():
    provider = OllamaEmbeddingProvider(model="embeddinggemma", dimension=2)
    fake = _Opener({"model": "embeddinggemma", "embeddings": [[0.6, 0.8]]})
    provider._opener = fake
    assert provider.embed_query("question") == (0.6, 0.8)
    assert fake.request.get_method() == "POST"
    body = json.loads(fake.request.data)
    assert body == {"model": "embeddinggemma", "input": ["question"], "truncate": False, "dimensions": 2}
    assert provider.space.dimension == 2


@pytest.mark.parametrize("endpoint", [
    "https://127.0.0.1:11434", "http://localhost:11434",
    "http://example.com:11434", "http://192.168.1.5:11434",
    "http://127.0.0.1:11434/path", "http://127.0.0.1:11434/?x=1",
])
def test_provider_rejects_nonliteral_or_nonloopback_endpoint(endpoint):
    with pytest.raises(ValueError):
        OllamaEmbeddingProvider(model="embeddinggemma", dimension=2, endpoint=endpoint)


@pytest.mark.parametrize("payload", [
    {"model": "other", "embeddings": [[1.0, 0.0]]},
    {"model": "embeddinggemma", "embeddings": [[0.0, 0.0]]},
    {"model": "embeddinggemma", "embeddings": [[1.0]]},
    {"model": "embeddinggemma", "embeddings": [[float("nan"), 0.0]]},
    {"model": "embeddinggemma", "embeddings": [[True, 0.0]]},
    {"model": "embeddinggemma", "embeddings": [[1.7e308, 1.7e308]]},
    {"model": "embeddinggemma", "embeddings": [[10 ** 1000, 0.0]]},
])
def test_provider_rejects_invalid_model_vectors_and_zero_norm(payload):
    provider = OllamaEmbeddingProvider(model="embeddinggemma", dimension=2)
    provider._opener = _Opener(payload)
    with pytest.raises(EmbeddingProviderError):
        provider.embed_query("question")


def test_provider_rejects_blank_or_overlong_input_before_request():
    provider = OllamaEmbeddingProvider(model="embeddinggemma", dimension=2)
    with pytest.raises(ValueError):
        provider.embed_query(" ")
    with pytest.raises(ValueError):
        provider.embed_query("x" * 16385)