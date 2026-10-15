"""Sanitized storage failures. Never include stored event content in messages."""


class StorageError(Exception):
    """Base class for local event storage failures."""


class DatabaseMissingError(StorageError):
    """The configured database file does not exist."""


class DatabaseUninitializedError(StorageError):
    """The database has no recognized OOMP schema."""


class ForeignDatabaseError(DatabaseUninitializedError):
    """An unversioned database contains objects not owned by OOMP."""


class UnsupportedSchemaVersionError(StorageError):
    """The database version is newer than this package understands."""


class StorageCorruptionError(StorageError):
    """The database schema or SQLite file is invalid."""


class StoredEventCorruptionError(StorageCorruptionError):
    """A stored event does not pass domain and fingerprint validation."""


class StorageBusyError(StorageError):
    """The database could not be acquired before its busy timeout."""


class StorageUnavailableError(StorageError):
    """The database or its parent path is unavailable."""


class IdempotencyConflictError(StorageError):
    """An event identity or idempotency key was reused for different evidence."""


class ScopeMismatchError(StorageError):
    """A supplied event or cursor does not match the authorized scope."""

class MemoryConflictError(StorageError):
    """A canonical key or memory ID names incompatible derived content."""


class SourceEventMissingError(StorageError):
    """A required source event is absent from the authorized partition."""


class ProvenanceMismatchError(StorageError):
    """Memory evidence does not match the original scoped source event."""


class AliasConflictError(StorageError):
    """Explicit names would merge two existing distinct entity identities."""


class EntityEvidenceError(StorageError):
    """An entity mention or alias lacks literal source-event evidence."""


class StoredMemoryCorruptionError(StorageCorruptionError):
    """A stored memory or entity fails validation."""



class SchemaUpgradeRequiredError(StorageError):
    """Canonical memory storage requires explicit schema version 2 initialization."""



class MemoryNotFoundError(StorageError):
    """A requested canonical memory is absent from the authorized partition."""


class GraphConflictError(StorageError):
    """An edge identity or graph policy conflicts with durable state."""


class GraphLimitError(StorageError):
    """A bounded graph operation cannot safely provide a complete answer."""


class EdgeNotFoundError(StorageError):
    """A graph edge is absent from the authorized scope."""


class TopicConflictError(StorageError):
    """A topic identity or immutable parent conflicts with durable state."""


class TopicNotFoundError(StorageError):
    """A topic is absent from the authorized scope."""


class StoredGraphCorruptionError(StorageCorruptionError):
    """Stored graph data failed validation."""

class RetrievalIndexError(StorageError):
    """A derived retrieval index is unavailable or inconsistent."""


class RetrievalLimitError(RetrievalIndexError):
    """A complete scoped retrieval scan exceeds a configured bound."""


class EmbeddingSpaceError(RetrievalIndexError):
    """Vectors or metadata do not match the selected embedding space."""


class FTSUnavailableError(RetrievalIndexError):
    """The local Python SQLite runtime lacks the FTS5 module."""
