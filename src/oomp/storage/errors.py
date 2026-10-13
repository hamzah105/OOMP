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