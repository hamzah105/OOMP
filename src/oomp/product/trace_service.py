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
    try:
        from backend.services.oomp_config import get_configuration
        from backend.services.oomp_publisher import Publisher
        from backend.services.oomp_diagnostics import work
        from pymongo import MongoClient
        config = get_configuration()
        if config.mode != "retrieve_and_ingest":
            raise ValueError("publication policy required")
        client = MongoClient(os.environ[mongo_reference], serverSelectionTimeoutMS=2000,
                             connectTimeoutMS=2000, socketTimeoutMS=3000, timeoutMS=5000,
                             directConnection=True, connect=False)
        client.admin.command("ping")
        publisher = Publisher(client[database], config)
        emit("ready")
        def heartbeat():
            while not stop.wait(1):
                emit("heartbeat")
        threading.Thread(target=heartbeat, daemon=True).start()
        for report in work(publisher, limit=10, cycles=0, poll_seconds=1):
            emit("work_complete")
            if any(r in {"failed", "uncertain"} for r in report["delivery"]["results"]):
                emit("work_warning")
            if stop.is_set():
                break
    finally:
        if client is not None:
            client.close()
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
    def emit(code):
        print(json.dumps({"code": code}), flush=True)
    try:
        run(args.project, args.mongo_reference, args.database, stop, emit)
        return 0
    except BaseException:
        emit("service_failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
