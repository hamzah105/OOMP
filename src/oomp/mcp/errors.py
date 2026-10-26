"""Sanitized application errors, independent of SDK wire types."""
from __future__ import annotations

class BoundaryError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


_MESSAGES = {
    "invalid_parameters": "Invalid tool arguments.",
    "unauthorized": "Authentication is required.",
    "forbidden": "This operation is not permitted.",
    "not_found": "The requested scoped record or tool is unavailable.",
    "conflict": "The request conflicts with previously stored evidence.",
    "storage_unavailable": "Memory storage is unavailable.",
    "embedding_unavailable": "Configured semantic retrieval is unavailable.",
    "resource_limit": "The operation exceeds a configured resource limit.",
    "busy": "Memory storage is temporarily busy.",
    "internal_error": "The operation could not be completed.",
}


def classify(error: Exception) -> str:
    from pydantic import ValidationError
    from oomp.storage import errors
    from oomp.retrieval.engine import RetrievalUnavailableError
    if isinstance(error, BoundaryError):
        return error.code if error.code in _MESSAGES else "internal_error"
    if isinstance(error, errors.StorageBusyError):
        return "busy"
    if isinstance(error, (errors.GraphLimitError, errors.RetrievalLimitError)):
        return "resource_limit"
    if isinstance(error, errors.IdempotencyConflictError):
        return "conflict"
    if isinstance(error, (errors.MemoryNotFoundError, errors.SourceEventMissingError)):
        return "not_found"
    if isinstance(error, errors.ScopeMismatchError):
        return "not_found"
    if isinstance(error, (RetrievalUnavailableError, errors.EmbeddingSpaceError)):
        return "embedding_unavailable"
    if isinstance(error, (ValidationError, TypeError, ValueError)):
        return "invalid_parameters"
    if isinstance(error, (errors.StorageError, OSError)):
        return "storage_unavailable"
    return "internal_error"


def error_data(code: str) -> dict:
    safe = code if code in _MESSAGES else "internal_error"
    return {"error": {"code": safe, "message": _MESSAGES[safe],
                      "retryable": safe in {"busy", "embedding_unavailable"}}}