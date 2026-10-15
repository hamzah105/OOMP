"""Local Stage 4 graph CLI and synthetic demonstration subprocess tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from oomp.domain.enums import RelationshipType
from oomp.domain.models import AuthorizedScope
from oomp.storage.graph_store import SQLiteGraphStore

SCOPE = AuthorizedScope(
    tenant_id="tenant-stage4-example", namespace="synthetic",
    principal_id="local-cli",
)


def cli(*arguments: str, database: Path) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["OOMP_DB_PATH"] = str(database)
    return subprocess.run(
        [sys.executable, "-m", "oomp", *arguments],
        capture_output=True, text=True, check=False, env=environment,
    )


def demo(database: Path) -> subprocess.CompletedProcess[str]:
    script = Path(__file__).resolve().parents[1] / "examples" / "stage4_temporal_graph.py"
    return subprocess.run(
        [sys.executable, str(script), "--db", str(database)],
        capture_output=True, text=True, check=False,
    )


def graph_cli(command: str, *options: str, database: Path) -> subprocess.CompletedProcess[str]:
    return cli(
        "graph", command, *options,
        "--tenant", SCOPE.tenant_id, "--namespace", SCOPE.namespace,
        "--db", str(database), database=database,
    )


def test_example_reopens_and_repeats_without_duplicate_graph_or_topics(tmp_path: Path) -> None:
    database = tmp_path / "dedicated" / "stage4.sqlite3"
    for _ in range(2):
        result = demo(database)
        assert result.returncode == 0, result.stderr
        assert "Source events: 4" in result.stdout
        assert "Canonical memories: 4" in result.stdout
        assert "type=SUPERSEDES evidence=1" in result.stdout
        assert "Unresolved proposal: CONTRADICTS" in result.stdout
        assert "memberships=2" in result.stdout
    assert len(SQLiteGraphStore(database).list_edges(SCOPE).edges) == 1


def test_graph_inspection_hides_canonical_content(tmp_path: Path) -> None:
    database = tmp_path / "stage4.sqlite3"
    assert demo(database).returncode == 0
    neighbors = graph_cli("neighbors", "--memory-id", "ram-old-4", database=database)
    assert neighbors.returncode == 0, neighbors.stderr
    edge = json.loads(neighbors.stdout.splitlines()[0])
    assert edge["relationship_type"] == "SUPERSEDES"
    assert edge["source_event_ids"] == ["hardware-upgrade"]
    assert "12 GB RAM" not in neighbors.stdout
    history = graph_cli(
        "history", "--memory-id", "ram-old-4",
        "--valid-at", "2026-09-10T00:00:00Z",
        database=database,
    )
    assert history.returncode == 0, history.stderr
    state = json.loads(history.stdout)
    assert state["memory_id"] == "ram-old-4"
    assert state["valid"] is True
    assert state["effective_status"] == "active"
    assert state["recorded_at"] is not None
    assert "4 GB RAM" not in history.stdout
    after_change = graph_cli(
        "history", "--memory-id", "ram-old-4",
        "--valid-at", "2026-09-20T00:00:00Z", database=database,
    )
    assert after_change.returncode == 0, after_change.stderr
    assert json.loads(after_change.stdout)["effective_status"] == "superseded"
    tree = graph_cli("topic-tree", "--root-topic-id", "ai", database=database)
    assert tree.returncode == 0, tree.stderr
    projection = json.loads(tree.stdout)
    assert {node["topic_id"] for node in projection["nodes"]} == {
        "ai", "local-models", "robotics",
    }
    shared = {
        node["topic_id"] for node in projection["nodes"] if node["memory_ids"]
    }
    assert shared == {"local-models", "robotics"}


def test_proposal_requires_explicit_confirmed_link(tmp_path: Path) -> None:
    database = tmp_path / "stage4.sqlite3"
    assert demo(database).returncode == 0
    propose = graph_cli(
        "propose", "--source", "ram-disputed-8", "--target", "ram-old-4",
        database=database,
    )
    assert propose.returncode == 0, propose.stderr
    assessment = json.loads(propose.stdout)
    assert assessment["proposal"]["relationship_type"] == "CONTRADICTS"
    assert SQLiteGraphStore(database).list_edges(
        SCOPE, relationship_type=RelationshipType.CONTRADICTS,
    ).edges == ()

    base = (
        "--source", "ram-disputed-8", "--target", "ram-old-4",
        "--relationship", "CONTRADICTS",
        "--event-id", "hardware-disputed", "--event-id", "hardware-old",
    )
    declined = graph_cli("link", *base, database=database)
    assert declined.returncode == 1
    assert SQLiteGraphStore(database).list_edges(
        SCOPE, relationship_type=RelationshipType.CONTRADICTS,
    ).edges == ()

    confirmed = graph_cli(
        "link", *base, "--confirm-resolution", database=database,
    )
    assert confirmed.returncode == 0, confirmed.stderr
    assert json.loads(confirmed.stdout)["relationship_type"] == "CONTRADICTS"
    again = graph_cli(
        "link", *base, "--confirm-resolution", database=database,
    )
    assert again.returncode == 0
    assert len(SQLiteGraphStore(database).list_edges(
        SCOPE, relationship_type=RelationshipType.CONTRADICTS,
    ).edges) == 1
    rerun = demo(database)
    assert rerun.returncode == 0, rerun.stderr
    assert len(SQLiteGraphStore(database).list_edges(
        SCOPE, relationship_type=RelationshipType.CONTRADICTS,
    ).edges) == 1


def test_missing_database_and_naive_time_fail_safely(tmp_path: Path) -> None:
    database = tmp_path / "missing" / "stage4.sqlite3"
    result = graph_cli("neighbors", "--memory-id", "anything", database=database)
    assert result.returncode == 1
    assert not database.parent.exists()
    invalid = graph_cli(
        "history", "--memory-id", "anything",
        "--valid-at", "2026-09-10T00:00:00", database=database,
    )
    assert invalid.returncode != 0
    assert not database.parent.exists()
    assert "Traceback" not in result.stderr + invalid.stderr
