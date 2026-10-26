"""Provider-neutral embedding failure taxonomy for retry decisions."""


class EmbeddingProviderError(ValueError):
    """A configured provider returned invalid or permanently rejected output."""


class EmbeddingProviderUnavailable(EmbeddingProviderError):
    """A configured provider is temporarily unreachable or rate limited."""
