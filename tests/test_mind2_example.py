"""The public offline example must prove its claims and refuse existing storage."""
from __future__ import annotations

from oomp.storage.migrations import SCHEMA_VERSION

import json
from pathlib import Path
import subprocess
import sys


def test_mind2_quickstart_acceptance_and_existing_directory_refusal(tmp_path):
    script = Path(__file__).resolve().parents[1] / "examples" / "mind2_quickstart.py"
    directory = tmp_path / "new synthetic demo"
    command = [sys.executable, str(script), "--directory", str(directory)]
    completed = subprocess.run(command, text=True, capture_output=True, timeout=90)
    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert report == json.loads((directory / "acceptance.json").read_text(encoding="utf-8"))
    assert report["source_events"] == 12 and report["excluded_events"] == 3
    assert report["memories"] == report["canonical_memories"] + report["episode_records"]
    assert report["canonical_memories"] == 3 and report["episode_records"] >= 9
    assert report["episode_summaries"] >= 3 and report["model_calls"] == 0
    assert all(report[name] for name in (
        "exact_immutable_provenance", "alias_unverified", "chronological_episodes",
        "correction_requires_review", "replay_no_duplicate_growth",
        "focus_preserves_history", "retraction_respected",
    ))
    assert report["schema"] == SCHEMA_VERSION and report["extraction_mode"] == "rules"
    assert report["services_started"] is report["existing_private_storage_used"] is False
    before = {file.name: file.read_bytes() for file in directory.iterdir() if file.is_file()}
    refused = subprocess.run(command, text=True, capture_output=True, timeout=30)
    assert refused.returncode == 1
    assert json.loads(refused.stdout) == {"ok": False, "code": "new_directory_required"}
    assert {file.name: file.read_bytes() for file in directory.iterdir() if file.is_file()} == before
