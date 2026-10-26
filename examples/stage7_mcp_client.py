"""Synthetic Stage 7 demo using an actual SDK client, never your personal data.

Install: python -m pip install -e ".[mcp]"
Run: python examples/stage7_mcp_client.py --transport stdio
Or:  python examples/stage7_mcp_client.py --transport streamable-http

All files and listeners are temporary. The example explicitly runs the existing
Mind worker before connecting; the MCP server never starts one.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
import time

import httpx2
from mcp import Client, StdioServerParameters
from mcp.client.streamable_http import streamable_http_client

from oomp.domain.models import AuthorizedScope, MemoryEvent, SourceReference, MemoryEdge
from oomp.mcp.configuration import Grant, ServerConfiguration
from oomp.mind.worker import MindWorker
from oomp.storage import SQLiteEventStore, SQLiteMemoryStore, SQLiteGraphStore


SCOPE = AuthorizedScope(tenant_id="synthetic-demo", namespace="personal", principal_id="demo-host")


def seed(database):
    events = SQLiteEventStore(database)
    events.initialize()
    now = datetime.now(timezone.utc)
    for identifier, text in (
        ("early-project", "I am developing a project called OOMP."),
        ("early-tool", "OOMP uses Python."),
    ):
        events.append(SCOPE, MemoryEvent(
            event_id=identifier, tenant_id=SCOPE.tenant_id, namespace=SCOPE.namespace,
            event_type="user_message", source_type="user", content=text,
            source_reference=SourceReference(source_system="synthetic-demo",
                                             external_event_id=identifier, timestamp=now),
            occurred_at=now, ingested_at=now, idempotency_key="key-" + identifier,
        ))
    worker = MindWorker(database, SCOPE, worker_id="explicit-demo-worker")
    worker.run_once(max_jobs=16)
    memories = SQLiteMemoryStore(database).list_memories(SCOPE).memories
    project = next(m for m in memories if "early-project" in m.source_event_ids)
    tool = next(m for m in memories if "early-tool" in m.source_event_ids)
    SQLiteGraphStore(database).add_edge(SCOPE, MemoryEdge(
        edge_id="demo-project-tool", tenant_id=SCOPE.tenant_id, namespace=SCOPE.namespace,
        source_node_id=project.memory_id, target_node_id=tool.memory_id,
        relationship_type="RELATED_TO", source_event_ids=("early-project",), created_at=now,
    ))
    for number in range(105):
        when = now + timedelta(seconds=number + 1)
        events.append(SCOPE, MemoryEvent(
            event_id=f"later-{number}", tenant_id=SCOPE.tenant_id, namespace=SCOPE.namespace,
            event_type="user_message", source_type="user",
            content=f"Synthetic unrelated conversation turn {number}.",
            source_reference=SourceReference(source_system="synthetic-demo",
                                             external_event_id=f"later-{number}", timestamp=when),
            occurred_at=when, ingested_at=when,
        ))
    return project.memory_id


@asynccontextmanager
async def connected(config, file):
    arguments = ["-m", "oomp", "mcp", "serve", "--config", str(file)]
    if config.transport == "stdio":
        async with Client(StdioServerParameters(command=sys.executable, args=arguments)) as client:
            yield client
        return
    token = secrets.token_urlsafe(32)
    process = subprocess.Popen(
        [sys.executable, *arguments], env={**os.environ, "OOMP_DEMO_TOKEN": token},
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("temporary HTTP server exited")
            try:
                with socket.create_connection((config.host, config.port), timeout=.1):
                    break
            except OSError:
                await asyncio.sleep(.05)
        else:
            raise RuntimeError("temporary HTTP server did not become ready")
        async with httpx2.AsyncClient(headers={"Authorization": "Bearer " + token},
                                      trust_env=False, timeout=15) as http:
            async with Client(streamable_http_client(config.endpoint, http_client=http)) as client:
                yield client
    finally:
        process.terminate()
        process.wait(10)


async def demo(transport):
    with TemporaryDirectory(prefix="oomp-stage7-") as directory:
        folder = Path(directory)
        database = folder / "synthetic memory.sqlite3"
        project_id = seed(database)
        grant = Grant(grant_id="demo-reader", principal_id=SCOPE.principal_id,
                      tenant_id=SCOPE.tenant_id, namespace=SCOPE.namespace,
                      bearer_token_env="OOMP_DEMO_TOKEN" if transport == "streamable-http" else None)
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        config = ServerConfiguration(
            database=str(database), transport=transport, port=port,
            stdio_grant=grant if transport == "stdio" else None,
            http_grants=(grant,) if transport == "streamable-http" else (),
        )
        file = folder / "server config.json"
        file.write_text(config.model_dump_json(), encoding="utf-8")
        async with connected(config, file) as client:
            tools = [t.name for t in (await client.list_tools()).tools]
            retrieval = await client.call_tool("memory.retrieve", {
                "query": "What project was the user developing?", "token_budget": 1200,
            })
            assert not retrieval.is_error
            data = retrieval.structured_content
            assert any(m["memory_id"] == project_id for m in data["memories"])
            assert len(data["context_packet"].encode("utf-8")) == data["estimated_token_count"] <= 1200
            sources = await client.call_tool("memory.get_source", {"memory_id": project_id})
            expansion = await client.call_tool("memory.expand", {"memory_id": project_id, "historical": True})
            status = await client.call_tool("memory.status", {})
            assert not sources.is_error and not expansion.is_error and not status.is_error
            print(json.dumps({
                "transport": transport, "protocol": client.protocol_version, "tools": tools,
                "later_unrelated_turns": 105, "retrieved": data["memories"],
                "budget_bytes": data["estimated_token_count"],
                "budget_scope": data["budget_scope"],
                "sources": sources.structured_content,
                "graph_edges": expansion.structured_content["edges"],
                "worker_started_by_server": status.structured_content["mind_worker_started_by_server"],
            }, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transport", choices=("stdio", "streamable-http"), default="stdio")
    asyncio.run(demo(parser.parse_args().transport))