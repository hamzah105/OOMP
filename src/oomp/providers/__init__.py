"""Explicit opt-in local embedding adapters."""

from .ollama import OllamaEmbeddingProvider
from .errors import EmbeddingProviderError, EmbeddingProviderUnavailable

__all__ = ["OllamaEmbeddingProvider", "EmbeddingProviderError", "EmbeddingProviderUnavailable"]