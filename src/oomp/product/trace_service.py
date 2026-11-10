"""Fixed, explicitly approved TRACE publication bridge; runs in host interpreter.

Only stdlib imports until approval validation in the parent. No OOMP import is
required in TRACE's environment. Reuses TRACE Publisher, not a copied publisher.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
import sys
import threading
import types


class PublicationFailure(Exception):
    """Static diagnostics only; never retain an exception's message as output."""
    def __init__(self, stage, reason):
        self.stage, self.reason = stage, reason
        self.reported = False
        super().__init__(reason)


def run(project, mongo_reference, database, stop, emit):
    sys.path.insert(0, str(Path(project)))
    # Publisher imports get_database even though its instance accepts a DB. Bind
    # that unused legacy helper to the explicitly selected DB in this child only,
    # before importing TRACE. This avoids TRACE's database.py load_dotenv/default
    # URI side effect. No TRACE file or existing API process is patched.
    client = None
    facade = types.ModuleType("backend.database.database")
    facade.get_database = lambda: client[database] if client is not None else None
    previous = sys.modules.get(facade.__name__)
    sys.modules[facade.__name__] = facade
    # Explicit local Mongo reference/database; no backend.database import, .env
    # loading, default production database selection, or automatic legacy backfill.
    stage = "imports"
    try:
        from backend.services.oomp_config import get_configuration
        from backend.services.oomp_publisher import Publisher
        from backend.services.oomp_diagnostics import work
        from pymongo import MongoClient
        from pymongo.errors import ConnectionFailure, PyMongoError
        stage = "configuration"
        config = get_configuration()
        if config.mode != "retrieve_and_ingest":
            raise ValueError("publication policy required")
        stage = "mongo_connect"
        client = MongoClient(os.environ[mongo_reference], serverSelectionTimeoutMS=2000,
                             connectTimeoutMS=2000, socketTimeoutMS=3000, timeoutMS=5000,
                             directConnection=True, connect=False)
        client.admin.command("ping")
        class ObservedPublisher(Publisher):
            def reconcile(self, **kwargs):
                nonlocal stage
                stage = "reconcile"
                return super().reconcile(**kwargs)

            def drain(self, **kwargs):
                nonlocal stage
                stage = "delivery"
                return super().drain(**kwargs)

        publisher = ObservedPublisher(client[database], config)
        emit("ready")
        def heartbeat():
            while not stop.wait(1):
                emit("heartbeat")
        threading.Thread(target=heartbeat, daemon=True).start()
        consecutive_failures = 0
        while not stop.is_set():
            try:
                for report in work(publisher, limit=10, cycles=0, poll_seconds=1):
                    consecutive_failures = 0
                    emit("work_complete")
                    if report.get("reconciliation", {}).get("invalid", 0):
                        emit("work_warning", stage="reconcile", reason="publication_source_invalid")
                    if any(r in {"failed", "uncertain"} for r in report["delivery"]["results"]):
                        emit("work_warning", stage="delivery", reason="publication_delivery_uncertain")
                    if stop.is_set():
                        return
            except ConnectionFailure:
                # Reconciliation is conditional/idempotent and delivery retains
                # TRACE's claim leases, fences and durable-receipt verification.
                # Never reset an event state, revive failed work or bypass a lease.
                consecutive_failures += 1
                if consecutive_failures >= 3:
                    raise
                emit("work_warning", stage=stage, reason="mongo_connection_failed",
                     retry_attempt=consecutive_failures)
                if stop.wait(.5 * 2**(consecutive_failures-1)):
                    return
    except BaseException as error:
        if isinstance(error, ImportError):
            reason = "dependency_missing"
        elif isinstance(error, KeyboardInterrupt):
            reason = "cancelled"
        elif "ConnectionFailure" in locals() and isinstance(error, ConnectionFailure):
            reason = "mongo_connection_failed"
        elif "PyMongoError" in locals() and isinstance(error, PyMongoError):
            reason = "mongo_operation_failed"
        elif stage == "configuration" and isinstance(error, (ValueError, KeyError, TypeError)):
            reason = "configuration_invalid"
        elif getattr(error, "code", None) == "invalid_source":
            reason = "publication_source_invalid"
        else:
            reason = "unknown_error"
        failure = PublicationFailure(stage, reason)
        # Report before Mongo cleanup: a blocked close must not conceal the
        # first fault behind a later supervisor heartbeat/progress timeout.
        emit("service_failed", stage=stage, reason=reason)
        failure.reported = True
        raise failure from None
    finally:
        pending_failure = sys.exception()
        try:
            if client is not None:
                client.close()
        except BaseException:
            if pending_failure is None:
                raise PublicationFailure("shutdown", "unknown_error") from None
        finally:
            if previous is None:
                sys.modules.pop(facade.__name__, None)
            else:
                sys.modules[facade.__name__] = previous


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--mongo-reference", required=True)
    parser.add_argument("--database", required=True)
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    stop = threading.Event()
    def control():
        sys.stdin.buffer.readline(32)
        stop.set()
    threading.Thread(target=control, daemon=True).start()
    output_lock = threading.Lock()
    def emit(code, **fields):
        with output_lock:
            print(json.dumps({"code": code, **fields}), flush=True)
    try:
        run(args.project, args.mongo_reference, args.database, stop, emit)
        return 0
    except PublicationFailure as error:
        if not error.reported:
            emit("service_failed", stage=error.stage, reason=error.reason)
        return 1
    except BaseException:
        emit("service_failed", stage="startup", reason="unknown_error")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
