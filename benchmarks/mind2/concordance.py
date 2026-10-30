"""Check whether final rules still emit the recorded frozen-corpus predictions.

This does not rerun inference or recreate timing/storage measurements. Security
hardening can be checked against every recorded opportunity without rewriting
the original experiment. Retractions and foreign scopes follow fixture controls.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

from oomp.domain.models import AuthorizedScope, MemoryEvent, SourceReference
from oomp.understanding.contracts import ExtractionConfiguration
from oomp.understanding.rules import RulesExtractor, promotion
from oomp.understanding.validator import CandidateValidator
from .run import load_corpus


def verify(reference: Path):
    corpus, manifest = load_corpus()
    measured = json.loads(reference.read_text(encoding="utf-8"))
    if measured["mode"] != "B" or measured["opportunities"] != manifest["opportunities"]:
        raise ValueError("rules_reference_required")
    actual_rows, mismatches = measured["rows"], []
    source_scope = AuthorizedScope(tenant_id="mind2-synthetic", namespace="evaluation", principal_id="synthetic-host")
    position = 0
    for index, session in enumerate(corpus["sessions"]):
        config = ExtractionConfiguration(sensitive_episodes=session.get("sensitive_episodes", False),
            exclude_terms=tuple(e["excluded_term"] for e in session["events"] if "excluded_term" in e))
        prior = {}
        for item in session["events"]:
            when = datetime(2026, 1, 2, 12, tzinfo=timezone.utc) + timedelta(hours=index, seconds=item["turn"])
            source = prior[item["replay_of"]] if "replay_of" in item else MemoryEvent(
                event_id=item["event_id"], tenant_id=source_scope.tenant_id, namespace=source_scope.namespace,
                event_type=item["role"] + "_message", source_type=item["role"], content=item["text"],
                occurred_at=when, ingested_at=when, source_reference=SourceReference(source_system="mind2-synthetic",
                    external_event_id=item["event_id"], timestamp=when, session_id=session["session_id"]),
                metadata={"ingested_by": source_scope.principal_id})
            prior[item["turn"]] = source
            proposed = () if item.get("retracted") or item.get("foreign_scope") else RulesExtractor(config).propose(source_scope, source)
            accepted = CandidateValidator(config).validate(source_scope, source, proposed) if proposed else ()
            expected = sorted((p.source_spans[0].start, p.source_spans[0].end, p.object,
                p.predicate, p.memory_category, p.assertion_kind, promotion(p)[0], p.claimed_by) for p in accepted)
            recorded = sorted((p["start"], p["end"], p["quote"], p["predicate"], p["category"],
                p["assertion"], p["retention"], p["role"]) for p in actual_rows[position]["predictions"])
            if expected != recorded or actual_rows[position]["event_id"] != source.event_id:
                mismatches.append({"session_id": session["session_id"], "turn": item["turn"]})
            position += 1
    files = [*Path("src/oomp/understanding").glob("*.py"),
             Path("src/oomp/storage/graph_store.py"), Path("src/oomp/storage/privacy_store.py")]
    return {"version": "mind2.rules-concordance.v1", "reference_sha256": hashlib.sha256(reference.read_bytes()).hexdigest(),
            "sessions": len(corpus["sessions"]), "events": position, "opportunities": manifest["opportunities"],
            "mismatches": mismatches, "all_recorded_predictions_unchanged": not mismatches,
            "scope": "Current pure rules/validator typed output; fixture retractions/scopes applied. Not a new timing or inference experiment.",
            "source_sha256": {p.as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    report = verify(args.reference)
    with args.output.open("x", encoding="utf-8") as output:
        output.write(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "source_sha256"}))
    return 0 if report["all_recorded_predictions_unchanged"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
