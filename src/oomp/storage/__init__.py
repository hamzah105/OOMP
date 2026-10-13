"""Stage 2 local source event persistence."""

from .errors import (
    DatabaseMissingError,
    DatabaseUninitializedError,
    ForeignDatabaseError,
    IdempotencyConflictError,
    ScopeMismatchError,
    StorageBusyError,
    StorageCorruptionError,
    StorageError,
    StorageUnavailableError,
    StoredEventCorruptionError,
    UnsupportedSchemaVersionError,
)
from .sqlite import SQLiteEventStore, StorageStatus

__all__ = [
    "DatabaseMissingError", "DatabaseUninitializedError", "ForeignDatabaseError",
    "IdempotencyConflictError", "ScopeMismatchError", "SQLiteEventStore",
    "StorageBusyError", "StorageCorruptionError", "StorageError", "StorageStatus",
    "StorageUnavailableError", "StoredEventCorruptionError", "UnsupportedSchemaVersionError",
]