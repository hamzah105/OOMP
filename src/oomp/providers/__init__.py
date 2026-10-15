"""Explicit opt-in local embedding adapters."""

from .ollama import OllamaEmbeddingProvider, EmbeddingProviderError

__all__ = ["OllamaEmbeddingProvider", "EmbeddingProviderError"]