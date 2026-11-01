"""Frozen offline P4A source-retrieval evaluation over real synthetic storage.

No answer model, external provider, private profile or TRACE database is used.
A changed fixture/policy requires a new version, never overwriting v1.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import ctypes
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import sqlite3
import statistics
import time

from oomp.context.contracts import ContextRequest
from oomp.domain.models import AuthorizedScope, MemoryEvent, SourceReference
from oomp.mind.worker import MindWorker
from oomp.objects import ObjectMap
from oomp.retrieval.contracts import EmbeddingSpace, RetrievalRequest
from oomp.retrieval.engine import RetrievalEngine
from oomp.storage.sqlite import SQLiteEventStore
from oomp.understanding.contracts import ExtractionConfiguration

FIXTURES = Path(__file__).parent / "fixtures" / "v1"


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _write_new(path, document):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(document, stream, ensure_ascii=True, indent=2, allow_nan=False)
        stream.write("\n")


def load_frozen():
    """Fail before storage creation if any preregistered byte changed."""
    raw_manifest = (FIXTURES / "manifest.json").read_bytes()
    manifest = json.loads(raw_manifest)
    for name, expected in manifest["files"].items():
        if _digest((FIXTURES / name).read_bytes()) != expected:
            raise ValueError("context_frozen_fixture_hash_mismatch")
    setup_raw = (FIXTURES / "setup-policy.json").read_bytes()
    expected_setup = (FIXTURES / "setup-policy.sha256").read_text(encoding="ascii").split()[0]
    if _digest(setup_raw) != expected_setup:
        raise ValueError("context_frozen_setup_hash_mismatch")
    setup = json.loads(setup_raw)
    if setup["original_manifest_sha256"] != _digest(raw_manifest):
        raise ValueError("context_setup_manifest_mismatch")
    fixture = json.loads((FIXTURES / "three-session.json").read_bytes())
    policy = json.loads((FIXTURES / "preregistration.json").read_bytes())
    if not all(doc.get("synthetic", doc.get("synthetic_only")) for doc in (manifest, fixture, policy, setup)):
        raise ValueError("synthetic_fixture_required")
    event_ids = {item["id"] for item in fixture["turns"]}
    if len(event_ids) != manifest["owned_source_events"] or len(policy["queries"]) != manifest["queries"]:
        raise ValueError("context_frozen_denominator_mismatch")
    for query in policy["queries"]:
        required, allowed = set(query["required_source_event_ids"]), set(query["allowed_source_event_ids"])
        if not required <= allowed <= event_ids or set(query["irrelevant_source_event_ids"]) != event_ids - allowed:
            raise ValueError("context_gold_source_identity_invalid")
    return fixture, policy, setup, manifest, {
        "manifest": _digest(raw_manifest),
        **manifest["files"],
        "setup-policy.json": expected_setup,
    }


class SyntheticEmbedding:
    """A frozen keyword-vector mock. It cannot establish real semantic quality."""

    space = EmbeddingSpace(
        provider="synthetic", model="context-keyword-fixture", version="v1", dimension=8,
    )

    def __init__(self, categories):
        self.categories = tuple(tuple(terms) for terms in categories.values())
        self.calls = 0

    def embed(self, texts):
        self.calls += 1
        vectors = []
        for text in texts:
            lowered = text.casefold()
            vector = [float(sum(term in lowered for term in terms)) for terms in self.categories]
            if not any(vector):
                vector[-1] = 1.0
            norm = math.sqrt(sum(value * value for value in vector))
            vectors.append(tuple(value / norm for value in vector))
        return tuple(vectors)


def process_memory_stats():
    """Client process RSS/peak only; no inference/server resource claim."""
    if os.name == "nt":
        from ctypes import wintypes as w

        class Counters(ctypes.Structure):
            _fields_ = [("cb", w.DWORD), ("faults", w.DWORD)] + [
                (name, ctypes.c_size_t) for name in
                ("peak", "working", "ppq", "pq", "pnpq", "npq", "pagefile", "peakpagefile")
            ]
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        kernel, psapi = ctypes.WinDLL("kernel32"), ctypes.WinDLL("psapi")
        kernel.GetCurrentProcess.restype = w.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [w.HANDLE, ctypes.c_void_p, w.DWORD]
        if psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            return {"rss_bytes": counters.working, "process_lifetime_peak_bytes": counters.peak}
        return {"rss_bytes": None, "process_lifetime_peak_bytes": None}
    try:
        import resource
        scale = 1 if platform.system() == "Darwin" else 1024
        return {"rss_bytes": None, "process_lifetime_peak_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * scale}
    except ImportError:
        return {"rss_bytes": None, "process_lifetime_peak_bytes": None}


def sqlite_size(path):
    return sum(candidate.stat().st_size for candidate in
               (path, Path(str(path) + "-wal"), Path(str(path) + "-shm")) if candidate.exists())


def _read_connection(path):
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def source_data_fingerprint(path):
    """Detect accidental source/canonical writes during read-only comparisons."""
    payload = {}
    with closing(_read_connection(path)) as connection:
        tables = connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
        for (table,) in tables:
            identifier = '"' + table.replace('"', '""') + '"'
            rows = connection.execute("SELECT * FROM " + identifier).fetchall()
            payload[table] = sorted([tuple(row) for row in rows], key=repr)
    return _digest(json.dumps(payload, ensure_ascii=True, default=str, sort_keys=True).encode())


def build_synthetic(path, fixture, policy, setup):
    """Only fresh caller-created storage, explicit rules jobs and P3 projection."""
    path = Path(path).resolve()
    if path.exists() or not path.parent.is_dir():
        raise ValueError("fresh_synthetic_database_required")
    scope = AuthorizedScope.model_validate(fixture["scope"])
    source = SQLiteEventStore(path)
    schema = source.initialize()
    extraction = setup["extraction"]
    configuration = ExtractionConfiguration(
        mode=extraction["mode"], retain_episodes=extraction["retain_episodes"],
        sensitive_episodes=extraction["sensitive_episodes"],
    )
    worker = MindWorker(path, scope, extraction_configuration=configuration)
    graph = ObjectMap(path)
    base = datetime.fromisoformat(fixture["base_time"])
    events = {}

    def event_for(turn, authorized, index):
        occurred = base + timedelta(days=turn["session"], minutes=index)
        return MemoryEvent(
            event_id=turn["id"], tenant_id=authorized.tenant_id, namespace=authorized.namespace,
            event_type=turn["role"] + "_message", source_type=turn["role"], content=turn["text"],
            source_reference=SourceReference(
                source_system=fixture["source_system"], external_event_id=turn["id"],
                timestamp=occurred, session_id="p4a-session-" + str(turn["session"]),
                turn_id="p4a-turn-" + str(index),
            ), occurred_at=occurred, ingested_at=occurred,
            metadata={"ingested_by": authorized.principal_id},
        )

    runs = []

    def drain(active_worker):
        for _ in range(4):
            result = active_worker.run_once(max_jobs=100)
            runs.append(asdict(result))
            if result.failed or result.retried or result.lost_lease:
                raise ValueError("synthetic_mind_job_failed")
            if active_worker.handlers.understanding.provider is not None:
                raise ValueError("rules_only_worker_required")
            if result.claimed == 0:
                return
        raise ValueError("synthetic_job_drain_limit")

    before_correction = None
    for index, turn in enumerate(fixture["turns"]):
        if turn["id"] == "p4a-correction":
            drain(worker)
            graph.build(scope, limit=setup["projection"]["page_limit"])
            before_correction = datetime.now(timezone.utc)
        event = event_for(turn, scope, index)
        source.append(scope, event)
        events[event.event_id] = event
    drain(worker)
    built = graph.build(scope, limit=setup["projection"]["page_limit"])
    if built.incomplete or before_correction is None:
        raise ValueError("synthetic_projection_incomplete")
    own_bytes = sqlite_size(path)
    scopes = [scope]
    for index, turn in enumerate(fixture["foreign_turns"], start=len(fixture["turns"])):
        foreign = scope.model_copy(update=(
            {"tenant_id": "context-foreign-owner", "principal_id": "foreign-owner"}
            if turn["partition"] == "other-tenant" else {"principal_id": "foreign-principal"}
        ))
        event = event_for(turn, foreign, index)
        source.append(foreign, event)
        events[event.event_id] = event
        foreign_worker = MindWorker(path, foreign, extraction_configuration=ExtractionConfiguration(mode="rules"))
        drain(foreign_worker)
        graph.build(foreign, limit=setup["projection"]["page_limit"])
        scopes.append(foreign)
    provider = SyntheticEmbedding(policy["mock_embedding"]["categories"])
    index_reports = []
    for authorized in (scope, scopes[1]):
        index_reports.append(asdict(RetrievalEngine(path, provider=provider).index(authorized, include_embeddings=True)))
    if any(report["embeddings_failed"] for report in index_reports):
        raise ValueError("synthetic_mock_index_failed")
    return {
        "scope": scope, "source": source, "events": events, "provider": provider,
        "before_correction": before_correction, "schema_version": schema,
        "worker_runs": runs, "projection": built.model_dump(mode="json"),
        "index_reports": index_reports, "owned_projection_bytes": own_bytes,
        "indexed_sqlite_bytes": sqlite_size(path),
    }


def _verified_proof(connection, data, scope, events):
    event = events.get(data["event_id"])
    row = connection.execute(
        "SELECT source_span_json FROM memory_sources WHERE tenant_id=? AND namespace=? AND memory_id=? AND event_id=?",
        (scope.tenant_id, scope.namespace, data["memory_id"], data["event_id"]),
    ).fetchone()
    if row is None or event is None:
        return False
    if (event.tenant_id, event.namespace, event.metadata.get("ingested_by")) != (
        scope.tenant_id, scope.namespace, scope.principal_id,
    ):
        return False
    span = json.loads(row["source_span_json"]) if row["source_span_json"] else None
    if span is None or (span["start"], span["end"]) != (data["span_start"], data["span_end"]):
        return False
    quote = event.content[span["start"]:span["end"]]
    if quote != span["quote"] or data.get("quote") not in (None, quote):
        return False
    return SourceReference.model_validate(data["source_reference"]) == event.source_reference


def normalize_result(path, response, scope, events):
    """Extract and independently validate persisted source pairs/ref/span."""
    data = response.model_dump(mode="json")
    units, proofs, episode = [], [], False
    if "evidence_packets" in data:
        for unit in data["evidence_packets"]:
            units.append(unit)
            proofs.extend(unit["source_proofs"])
            episode |= unit["resolution"] == "episode_summary"
        packet, measured, budget = data["context_packet"], data["selected_context_bytes"], data["token_budget"]
        retrieval_status = data["retrieval_status"]
        retrieval_intent = data["retrieval_intent"]
    else:
        with closing(_read_connection(path)) as connection:
            for memory in data["memories"]:
                units.append(memory)
                episode |= memory["memory_type"] == "episodic"
                for event_id, reference in zip(memory["source_event_ids"], memory["source_references"]):
                    row = connection.execute(
                        "SELECT source_span_json FROM memory_sources WHERE tenant_id=? AND namespace=? AND memory_id=? AND event_id=?",
                        (scope.tenant_id, scope.namespace, memory["memory_id"], event_id),
                    ).fetchone()
                    span = json.loads(row["source_span_json"]) if row and row["source_span_json"] else None
                    proofs.append({
                        "memory_id": memory["memory_id"], "event_id": event_id, "source_reference": reference,
                        "span_start": span["start"] if span else -1, "span_end": span["end"] if span else -1,
                        "quote": span["quote"] if span else None,
                    })
        packet, measured, budget = data["context_packet"], data["estimated_token_count"], data["token_budget"]
        retrieval_status = "found_relevant_evidence" if data["memories"] else "no_relevant_evidence"
        retrieval_intent = "legacy_query_only"
    with closing(_read_connection(path)) as connection:
        valid = [_verified_proof(connection, proof, scope, events) for proof in proofs]
    ids = tuple(dict.fromkeys(proof["event_id"] for proof in proofs))
    pairs = [(p["memory_id"], p["event_id"], p["span_start"], p["span_end"]) for p in proofs]
    original_spans = [(p["event_id"], p["span_start"], p["span_end"]) for p in proofs]
    foreign = {
        identifier for identifier in ids
        if identifier not in events or
        (events[identifier].tenant_id, events[identifier].namespace, events[identifier].metadata.get("ingested_by"))
        != (scope.tenant_id, scope.namespace, scope.principal_id)
    }
    return {
        "source_event_ids": list(ids), "source_proof_count": len(proofs),
        "invalid_source_proofs": len(valid) - sum(valid), "duplicate_source_proofs": len(pairs) - len(set(pairs)),
        "duplicate_original_source_spans": len(original_spans) - len(set(original_spans)),
        "cross_scope_sources": sorted(foreign), "has_episode_resolution": episode,
        "selected_context_bytes": measured, "token_budget": budget,
        "counting_method": data["counting_method"],
        "budget_overflow": measured > budget or measured != len(packet.encode("utf-8")),
        "retrieval_status": retrieval_status, "retrieval_intent": retrieval_intent,
        "degraded": data["degraded"], "evidence_unit_count": len(units),
        "response": data,
    }


def score_record(query, normalized):
    """Score identities once: duplicate hierarchy paths never inflate recall."""
    selected = tuple(dict.fromkeys(normalized["source_event_ids"]))
    required, allowed = set(query["required_source_event_ids"]), set(query["allowed_source_event_ids"])
    found = set(selected)
    failed = normalized.get("operation_failed", False)
    recall = len(found & required) / len(required) if required else None
    precision = len(found & allowed) / len(found) if found else None
    abstained = not found and not failed and normalized["retrieval_status"] in {
        "no_relevant_evidence", "candidate_uncertain",
    }
    return {
        "source_recall_at_k": len(set(selected[:8]) & required) / len(required) if required else None,
        "source_recall_at_budget": recall,
        "evidence_precision": precision,
        "relevant_sources": len(found & allowed), "returned_distinct_sources": len(found),
        "false_positive_sources": len(found - allowed),
        "false_positive_retrieval": int(bool(found)) if query["abstain"] else None,
        "correct_abstention": int(abstained) if query["abstain"] else None,
        "episode_recall": recall if query["expected_intent_category"] == "episodic_recall" else None,
        "temporal_correction_accuracy": int("p4a-correction" in found and "p4a-assistant" not in found)
            if query["id"] in {"decision", "referent"} else
            int("p4a-plan" in found and "p4a-correction" not in found)
            if query["id"] == "before-correction" else None,
        "provenance_fidelity": int(normalized["invalid_source_proofs"] == 0 and not failed),
    }


def _percentile(values, fraction):
    values = sorted(values)
    return values[max(0, math.ceil(len(values) * fraction) - 1)] if values else None


def summarize(records, policy):
    summaries = []
    for method in policy["methods"]:
        for budget_label in ("primary", "constrained"):
            rows = [r for r in records if r["method"] == method and r["budget_label"] == budget_label]
            if not rows:
                continue
            def mean(key):
                values = [row[key] for row in rows if row.get(key) is not None]
                return statistics.mean(values) if values else None
            selected = sum(r["returned_distinct_sources"] for r in rows)
            times = [r["latency_ms"] for r in rows]
            summaries.append({
                "method": method, "budget_label": budget_label, "queries": len(rows),
                "failed_queries": sum(r["status"] != "completed" for r in rows),
                "source_recall_at_k": mean("source_recall_at_k"),
                "source_recall_at_budget": mean("source_recall_at_budget"),
                "evidence_precision": sum(r["relevant_sources"] for r in rows) / selected if selected else None,
                "episode_recall": mean("episode_recall"),
                "temporal_correction_accuracy": mean("temporal_correction_accuracy"),
                "false_positive_retrieval": mean("false_positive_retrieval"),
                "abstention_correctness": mean("correct_abstention"),
                "cross_scope_violations": sum(len(r["cross_scope_sources"]) for r in rows),
                "invalid_source_proofs": sum(r["invalid_source_proofs"] for r in rows),
                "duplicate_source_proofs": sum(r["duplicate_source_proofs"] for r in rows),
                "duplicate_original_source_spans": sum(r["duplicate_original_source_spans"] for r in rows),
                "budget_overflows": sum(r["budget_overflow"] for r in rows),
                "provenance_fidelity": mean("provenance_fidelity"),
                "latency_p50_ms": statistics.median(times), "latency_p95_ms": _percentile(times, .95),
                "selected_context_bytes_mean": mean("selected_context_bytes"),
                "selected_context_bytes_max": max(r["selected_context_bytes"] for r in rows),
            })
    primary = [r for r in records if r["method"] == "context-lexical" and r["budget_label"] == "primary"]
    primary_ids = set(policy["primary_required_query_ids"])
    required = [r for r in primary if r["query_id"] in primary_ids and r["source_recall_at_budget"] is not None]
    context_summary = next((r for r in summaries if r["method"] == "context-lexical" and r["budget_label"] == "primary"), {})
    threshold = policy["thresholds"]
    required_recall = statistics.mean(r["source_recall_at_budget"] for r in required) if required else 0
    gates = {
        "complete_context_primary_denominator": len(primary) == len(policy["queries"]),
        "required_six_source_recall": required_recall >= threshold["context_primary_required_six_source_recall_min"],
        "primary_precision": (context_summary.get("evidence_precision") or 0) >= threshold["context_primary_evidence_precision_min"],
        "abstention": context_summary.get("abstention_correctness") == threshold["context_abstention_accuracy_min"],
        "isolation": context_summary.get("cross_scope_violations") == threshold["context_cross_scope_violations_max"],
        "provenance": context_summary.get("provenance_fidelity") == threshold["context_provenance_fidelity_min"],
        "budget": context_summary.get("budget_overflows") == threshold["context_budget_overflows_max"],
        "duplicates": context_summary.get("duplicate_source_proofs") == threshold["context_duplicate_source_proofs_max"],
        "original_source_span_duplicates": context_summary.get("duplicate_original_source_spans") == threshold["context_duplicate_source_proofs_max"],
        "no_failed_queries": all(r["status"] == "completed" for r in records),
    }
    declared_queries = [q for q in policy["queries"] if q["id"] in primary_ids]
    positive_queries = [q for q in declared_queries if q["required_source_event_ids"]]
    negative_queries = [q for q in declared_queries if not q["required_source_event_ids"]]
    return {
        "methods": summaries,
        "context_primary_positive_required_recall": required_recall,
        # Retain the original preregistered label while exposing its denominator.
        "context_primary_required_six_recall": required_recall,
        "primary_required_denominator": {
            "declared_query_ids": [q["id"] for q in declared_queries],
            "declared_cases": len(declared_queries),
            "positive_source_recall_query_ids": [q["id"] for q in positive_queries],
            "positive_source_recall_cases": len(positive_queries),
            "observed_positive_source_recall_cases": len(required),
            "separate_abstention_query_ids": [q["id"] for q in negative_queries],
            "separate_abstention_cases": len(negative_queries),
            "all_abstention_query_ids": [q["id"] for q in policy["queries"] if q["abstain"]],
            "weighting": "Unweighted macro source recall over five positive required cases; the pet case has no gold source denominator and is scored separately as abstention.",
            "label_caveat": "The frozen required_six label names six cases, not six positive recall denominators. Thresholds and gold remain unchanged.",
        },
        "ranking_metric_scope": {
            "source_recall_at_k": "First eight distinct source-event identities returned after byte-budget packing; manifest order is used within a multi-source evidence unit.",
            "source_recall_at_budget": "All distinct source-event identities in the returned byte-admitted packet.",
            "comparison_limit": "Both use the same already packed evidence. They coincide when at most eight distinct sources are returned; pre-packing candidate Recall@k is not measured.",
        },
        "acceptance_gates": gates, "acceptance_passed": all(gates.values()),
    }


def run(directory, *, methods=None, budget_labels=None, query_ids=None):
    """Every invocation creates a new directory, with no automatic retry."""
    fixture, policy, setup, manifest, hashes = load_frozen()
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    methods = tuple(methods or policy["methods"])
    budget_labels = tuple(budget_labels or ("primary", "constrained"))
    if not set(methods) <= set(policy["methods"]) or not set(budget_labels) <= {"primary", "constrained"}:
        raise ValueError("unregistered_evaluation_selection")
    queries = [q for q in policy["queries"] if query_ids is None or q["id"] in query_ids]
    if query_ids is not None and len(queries) != len(set(query_ids)):
        raise ValueError("unknown_evaluation_query")
    _write_new(directory / "manifest.json", {
        "synthetic": True, "fixture_hashes": hashes, "baseline_commit": policy["baseline_commit"],
        "methods": methods, "budgets": budget_labels, "query_ids": [q["id"] for q in queries],
        "annotation_status": manifest["annotation_status"], "answer_quality_measured": False,
        "real_model_calls": 0, "real_embedding_calls": 0, "setup_policy": setup,
    })
    path = directory / "fictional.sqlite3"
    started = time.perf_counter()
    cpu_started = time.process_time()
    records = []
    try:
        built = build_synthetic(path, fixture, policy, setup)
        scope, provider = built["scope"], built["provider"]
        _write_new(directory / "setup.json", {
            k: v for k, v in built.items() if k not in {"scope", "source", "events", "provider", "before_correction"}
        } | {"scope": scope.model_dump(mode="json"),
             "before_correction_recording_cutoff": built["before_correction"].isoformat(),
             "model_calls": 0})
        original = source_data_fingerprint(path)
        from oomp.context.engine import ContextEngine
        context_engine = ContextEngine(path)
        mock_context_engine = ContextEngine(path, provider=provider)
        lexical = RetrievalEngine(path)
        hybrid = RetrievalEngine(path, provider=provider)
        with (directory / "per_query.jsonl").open("x", encoding="utf-8", newline="\n") as stream:
            for budget_label in budget_labels:
                budget = policy["budgets"][budget_label]
                for query in queries:
                    common = dict(
                        tenant_id=scope.tenant_id, namespace=scope.namespace, query=query["query"],
                        token_budget=budget, **policy["limits"],
                    )
                    if query.get("historical"):
                        common["historical"] = True
                    if query.get("known_at_marker"):
                        common["known_at"] = built["before_correction"]
                    for method in methods:
                        item = {"method": method, "query_id": query["id"], "budget_label": budget_label,
                                "required_source_event_ids": query["required_source_event_ids"],
                                "allowed_source_event_ids": query["allowed_source_event_ids"]}
                        clock = time.perf_counter()
                        try:
                            values = dict(common)
                            if method.startswith("legacy"):
                                values["mode"] = "hybrid" if method == "legacy-hybrid-mock" else "lexical"
                                response = (hybrid if values["mode"] == "hybrid" else lexical).retrieve(scope, RetrievalRequest(**values))
                            else:
                                values["mode"] = "hybrid" if method == "context-hybrid-mock" else "lexical"
                                if method == "context-graph1":
                                    values["graph_depth"] = 1
                                values["recent_user_turns"] = tuple(query.get("recent_referents", ()))
                                values["explain"] = True  # This explicit synthetic benchmark is trusted inspection.
                                response = (mock_context_engine if values["mode"] == "hybrid" else context_engine).retrieve(scope, ContextRequest(**values))
                            normalized = normalize_result(path, response, scope, built["events"])
                            item.update(status="completed", **normalized)
                        except Exception as error:
                            normalized = {
                                "source_event_ids": [], "source_proof_count": 0, "invalid_source_proofs": 0,
                                "duplicate_source_proofs": 0, "cross_scope_sources": [],
                                "duplicate_original_source_spans": 0,
                                "selected_context_bytes": 0, "token_budget": budget,
                                "budget_overflow": False, "retrieval_status": "unavailable",
                                "retrieval_intent": "not_completed", "operation_failed": True,
                            }
                            item.update(status="failed", error_code=type(error).__name__, **normalized)
                        item.update(score_record(query, normalized))
                        item["latency_ms"] = (time.perf_counter() - clock) * 1000
                        stream.write(json.dumps(item, ensure_ascii=True, allow_nan=False) + "\n")
                        stream.flush()
                        records.append(item)
        unchanged = original == source_data_fingerprint(path)
        if not unchanged:
            raise ValueError("read_only_evaluation_changed_source_data")
        summary = summarize(records, policy)
        summary.update({
            "synthetic": True, "query_records": len(records),
            "full_preregistered_comparison": len(records) == len(policy["methods"]) * len(policy["queries"]) * 2,
            "source_data_unchanged": unchanged, "schema_version": built["schema_version"],
            "fixture_hashes": hashes, "model_calls": 0, "mock_embedding_calls": provider.calls,
            "wall_seconds": time.perf_counter() - started, "cpu_seconds": time.process_time() - cpu_started,
            "resources": process_memory_stats(), "indexed_sqlite_bytes": built["indexed_sqlite_bytes"],
            "sqlite_after_queries_bytes": sqlite_size(path),
            "sqlite_growth_during_queries_bytes": sqlite_size(path) - built["indexed_sqlite_bytes"],
            "resource_scope": "This Python client and synthetic SQLite only; peak includes setup.",
            "quality_scope": "Developer-labeled synthetic source recall; mock vectors are mechanics only. No final answer generation or real semantic-model accuracy.",
            "provenance_fidelity_scope": "Independent stored memory/source pair, exact source reference and span integrity; not an automated entailment judgment of arbitrary prose.",
        })
        _write_new(directory / "result.json", summary)
        return summary
    except BaseException as error:
        _write_new(directory / "failure.json", {
            "status": "failed", "error_code": type(error).__name__, "completed_query_records": len(records),
            "wall_seconds": time.perf_counter() - started, "model_calls": 0,
            "resume_or_automatic_retry": False,
        })
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, type=Path, help="new short synthetic result directory")
    args = parser.parse_args()
    result = run(args.directory)
    print(json.dumps({
        "directory": str(args.directory.resolve()), "query_records": result["query_records"],
        "full_preregistered_comparison": result["full_preregistered_comparison"],
        "acceptance_passed": result["acceptance_passed"], "acceptance_gates": result["acceptance_gates"],
        "model_calls": result["model_calls"], "detailed_results": "result.json and per_query.jsonl",
    }, ensure_ascii=True, indent=2, allow_nan=False))
    return 0 if result["acceptance_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
