"""Owned subprocesses: stop via parent pipe EOF/message, never shared PID files."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import signal
import sys
import threading
import time

from .profiles import ProfileStore
from .safety import ProductError, safe_path


def _emit(code, **counts):
    print(json.dumps({"code": code, **counts}, separators=(",", ":")), flush=True)


def run_role(store, profile, role):
    stop = threading.Event()
    ready = threading.Event()
    def control():
        # EOF also stops children when the supervisor dies unexpectedly.
        sys.stdin.buffer.readline(32)
        stop.set()
    threading.Thread(target=control, daemon=True).start()
    def heartbeat():
        while not stop.wait(1):
            _emit("heartbeat", ready=ready.is_set())
    threading.Thread(target=heartbeat, daemon=True).start()
    from oomp.storage import SQLiteEventStore
    if not SQLiteEventStore(profile.database).status().ready:
        raise ProductError("storage_not_ready")
    if role == "mind":
        from oomp.mind.worker import MindWorker
        provider = profile.provider.construct_provider() if profile.provider else None
        worker = MindWorker(profile.database, profile.scope, embedding_provider=provider,
                            auto_embed_on_extract=provider is not None)
        ready.set()
        _emit("ready")
        while not stop.is_set():
            result = worker.run_once(max_jobs=4, dispatch_limit=16)
            if result.failed or result.lost_lease:
                _emit("work_warning", failed=result.failed, lost_lease=result.lost_lease)
            _emit("work_complete", completed=result.completed, failed=result.failed, lost_lease=result.lost_lease)
            stop.wait(.5)
    elif role == "mcp":
        from oomp.mcp.cli import _sdk_ready
        _sdk_ready()
        from oomp.mcp.server import build_server, build_http_app
        import uvicorn
        server = build_server(profile.server(), environ=store.environment(profile))
        runner = uvicorn.Server(uvicorn.Config(build_http_app(server), host="127.0.0.1", port=profile.port,
            log_level="critical", access_log=False, server_header=False, proxy_headers=False,
            timeout_graceful_shutdown=4, limit_concurrency=20, h11_max_incomplete_event_size=16384))
        thread = threading.Thread(target=runner.run, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic()+20
            while not runner.started:
                if not thread.is_alive() or time.monotonic() >= deadline or stop.wait(.05):
                    raise ProductError("mcp_startup_failed")
            ready.set()
            _emit("ready")
            while thread.is_alive() and not stop.wait(.1):
                pass
            if not stop.is_set():
                raise ProductError("mcp_exited")
        finally:
            runner.should_exit = True
            thread.join(5)
    else:
        raise ProductError("unknown_service_role")
    stop.set()


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True)
    parser.add_argument("--home", required=True)
    parser.add_argument("--role", choices=("mcp", "mind"), required=True)
    args = parser.parse_args(argv)
    try:
        store = ProfileStore(args.home)
        run_role(store, store.load(args.profile), args.role)
        return 0
    except KeyboardInterrupt:
        return 130
    except BaseException:
        _emit("service_failed")  # no arbitrary exception/config/source text
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
