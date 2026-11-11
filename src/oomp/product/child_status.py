"""Finite child diagnostics; no exception text or arbitrary child fields."""

CODES = frozenset({"ready", "heartbeat", "work_warning", "work_complete", "service_failed"})
ROLES = frozenset({"mcp", "mind", "publication", "supervisor"})
STAGES = frozenset({"startup", "imports", "configuration", "mongo_connect", "reconcile",
                    "delivery", "mind_work", "storage", "mcp", "supervision", "shutdown"})
REASONS = frozenset({"unknown_error", "dependency_missing", "configuration_invalid",
    "mongo_connection_failed", "mongo_operation_failed", "publication_source_invalid",
    "publication_delivery_uncertain", "mcp_transport_failed", "protocol_failed",
    "storage_unavailable", "worker_failed", "process_exited", "heartbeat_timeout",
    "progress_timeout", "child_not_ready", "invalid_child_status", "cancelled"})
KINDS = frozenset({"child_reported_failure", "work_warning", "process_exit", "heartbeat_timeout",
                   "progress_timeout", "child_not_ready", "protocol_failure", "startup_failure"})


def checked_status(value):
    fields = {"code", "stage", "reason", "ready", "failed", "lost_lease", "completed", "retry_attempt"}
    if (not isinstance(value, dict) or set(value)-fields or type(value.get("code")) is not str or value["code"] not in CODES
            or "stage" in value and (type(value["stage"]) is not str or value["stage"] not in STAGES)
            or "reason" in value and (type(value["reason"]) is not str or value["reason"] not in REASONS)
            or "ready" in value and type(value["ready"]) is not bool):
        raise ValueError("invalid_child_status")
    for name in ("failed", "lost_lease", "completed", "retry_attempt"):
        if name in value and (type(value[name]) is not int or not 0 <= value[name] <= 1_000_000):
            raise ValueError("invalid_child_status")
    return value


def checked_failure(value):
    if (not isinstance(value, dict) or set(value) != {"role", "kind", "stage", "reason", "exit_code"}
            or type(value["role"]) is not str or value["role"] not in ROLES
            or type(value["kind"]) is not str or value["kind"] not in KINDS
            or type(value["stage"]) is not str or value["stage"] not in STAGES
            or type(value["reason"]) is not str or value["reason"] not in REASONS
            or value["exit_code"] is not None and (
                type(value["exit_code"]) is not int or not -(2**31) <= value["exit_code"] < 2**32)):
        raise ValueError("invalid_failure_detail")
    return dict(value)


def failure_detail(role, kind, stage, reason, exit_code=None):
    return checked_failure(dict(role=role, kind=kind, stage=stage, reason=reason, exit_code=exit_code))
