"""Stage 2 local source event persistence."""

from .errors import (
    DatabaseMissingError,
    DatabaseUninitializedError,
    ForeignDatabaseError,
    IdempotencyConflictError,
    AliasConflictError,
    EntityEvidenceError,
    MemoryConflictError,
    MemoryNotFoundError,
    ProvenanceMismatchError,
    SchemaUpgradeRequiredError,
    SourceEventMissingError,
    StoredMemoryCorruptionError,
    ScopeMismatchError,
    StorageBusyError,
    StorageCorruptionError,
    StorageError,
    StorageUnavailableError,
    StoredEventCorruptionError,
    UnsupportedSchemaVersionError,
)
from .sqlite import SQLiteEventStore, StorageStatus
from .memory_store import SQLiteMemoryStore
from .entity_store import SQLiteEntityStore

__all__ = [
    "DatabaseMissingError", "DatabaseUninitializedError", "ForeignDatabaseError",
    "IdempotencyConflictError", "ScopeMismatchError", "SQLiteEventStore",
    "SQLiteMemoryStore", "SQLiteEntityStore", "MemoryConflictError",
    "MemoryNotFoundError", "ProvenanceMismatchError", "SourceEventMissingError",
    "AliasConflictError", "EntityEvidenceError", "SchemaUpgradeRequiredError",
    "StoredMemoryCorruptionError",
    "StorageBusyError", "StorageCorruptionError", "StorageError", "StorageStatus",
    "StorageUnavailableError", "StoredEventCorruptionError", "UnsupportedSchemaVersionError",
]
from .graph_store import SQLiteGraphStore
from .topic_store import SQLiteTopicStore
from .errors import (
    GraphConflictError, GraphLimitError, EdgeNotFoundError,
    TopicConflictError, TopicNotFoundError, StoredGraphCorruptionError,
)
__all__ += [
    "SQLiteGraphStore", "SQLiteTopicStore", "GraphConflictError",
    "GraphLimitError", "EdgeNotFoundError", "TopicConflictError",
    "TopicNotFoundError", "StoredGraphCorruptionError",
]

from .retrieval_store import (
    SQLiteRetrievalStore, RetrievalReadSession, IndexStatus,
    LexicalHit, SemanticHit, EntityHit, TopicHit, content_digest,
)
from .errors import FTSUnavailableError, RetrievalIndexError, RetrievalLimitError, EmbeddingSpaceError
__all__ += [
    "SQLiteRetrievalStore", "RetrievalReadSession", "IndexStatus",
    "LexicalHit", "SemanticHit", "EntityHit", "TopicHit", "content_digest",
    "FTSUnavailableError", "RetrievalIndexError", "RetrievalLimitError", "EmbeddingSpaceError",
]
