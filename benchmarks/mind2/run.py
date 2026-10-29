"""Compare legacy, rules and explicitly configured local acquisition.

All model inference is executed by real durable Mind jobs. Labels are Codex
drafts; these measurements are not independently verified research claims.
"""
from __future__ import annotations

import argparse
import ctypes
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import time

from oomp.domain.graph import TemporalQuery
from oomp.domain.models import AuthorizedScope, MemoryEvent, SourceReference
from oomp.mind.contracts import JobType
from oomp.mind.handlers import MindHandlers
from oomp.mind.scheduler import MindScheduler
from oomp.mind.worker import MindWorker
from oomp.storage import SQLiteEventStore
from oomp.storage.mind_projection_store import SQLiteMindProjectionStore
from oomp.storage.graph_store import SQLiteGraphStore
from oomp.understanding.contracts import ExtractionConfiguration
from oomp.understanding.providers import OllamaExtractor, PROMPT_VERSION, SYSTEM_PROMPT
from oomp.understanding.transport import request_json

FIXTURES = Path(__file__).parent / "fixtures" / "v1"


def load_corpus():
    manifest = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
    for name, expected in manifest["files"].items():
        if hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest() != expected:
            raise ValueError("frozen_corpus_hash_mismatch")
    corpus = json.loads((FIXTURES / "sessions.json").read_text(encoding="utf-8"))
    labels = [label for session in corpus["sessions"] for event in session["events"] for label in event["labels"]]
    if len(corpus["sessions"]) != manifest["sessions"] or len(labels) != manifest["opportunities"]:
        raise ValueError("frozen_corpus_denominator_mismatch")
    seen = set()
    for session in corpus["sessions"]:
        for item in session["events"]:
            for label in item["labels"]:
                if item["text"][label["start"]:label["end"]] != label["quote"] or label["opportunity_id"] in seen:
                    raise ValueError("annotation_span_invalid")
                if label["review_status"] != "draft-pending-independent-human-review":
                    raise ValueError("annotation_review_status_invalid")
                seen.add(label["opportunity_id"])
    return corpus, manifest


def rss_bytes():
    if os.name == "nt":
        from ctypes import wintypes as w
        class Counters(ctypes.Structure):
            _fields_ = [("cb", w.DWORD), ("faults", w.DWORD),
                *[(name, ctypes.c_size_t) for name in ("peak", "working", "ppq", "pq", "pnpq", "npq", "pagefile", "peakpagefile")]]
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        kernel, psapi = ctypes.WinDLL("kernel32"), ctypes.WinDLL("psapi")
        kernel.GetCurrentProcess.restype = w.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [w.HANDLE, ctypes.c_void_p, w.DWORD]
        if psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            return counters.working
        return None
    try:
        import resource
        scale = 1 if platform.system() == "Darwin" else 1024
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * scale
    except ImportError:
        return None


def _predictions(path, scope, source, mode):
    graph = SQLiteGraphStore(path)
    predictions = []
    with graph._graph_read() as connection:
        rows = connection.execute(
            """SELECT m.*,s.source_span_json FROM memories m JOIN memory_sources s
               ON s.tenant_id=m.tenant_id AND s.namespace=m.namespace AND s.memory_id=m.memory_id
               WHERE s.tenant_id=? AND s.namespace=? AND s.event_id=? ORDER BY m.memory_id LIMIT 65""",
            (scope.tenant_id, scope.namespace, source.event_id)).fetchall()
        for row in rows:
            memory = graph._read_memory(connection, scope, row)
            p2 = memory.metadata.get("p2_episode") is True
            refinement = memory.metadata.get("canonicalization_version") == "p2.1" and not p2
            if mode != "A" and not (p2 or refinement) or mode == "A" and p2:
                continue
            state = graph._memory_state_in_connection(connection, scope, memory.memory_id, TemporalQuery())
            if source.event_id not in state.source_event_ids or state.effective_status.value != "active":
                continue
            span = json.loads(row["source_span_json"]) if row["source_span_json"] else None
            if span is None:
                continue
            if p2 or refinement:
                category, predicate = memory.metadata["category"], memory.metadata["predicate"]
                assertion, retention = memory.metadata["assertion_kind"], memory.metadata["promotion"]
            else:
                kind = memory.memory_type.value
                category = "profile" if kind == "profile" else "prospective" if kind == "project_state" else "episodic" if kind == "episodic" else "semantic"
                predicate = "preference" if kind == "profile" else "project" if "developing a project" in memory.canonical_content else "plan" if kind == "project_state" else "stated"
                assertion = "tentative" if "considering" in memory.canonical_content else "explicit"
                retention = "episodic-only" if kind == "episodic" else "canonical"
            provenance_ok = (source.content[span["start"]:span["end"]] == span["quote"]
                and source.source_reference in memory.provenance
                and memory.metadata["attribution"] == source.source_type.value)
            predictions.append({"start": span["start"], "end": span["end"], "quote": span["quote"],
                "predicate": predicate, "category": category, "assertion": assertion, "retention": retention,
                "role": memory.metadata["attribution"], "episodic": p2 or memory.memory_type.value == "episodic",
                "provenance_ok": provenance_ok, "memory_id": memory.memory_id})
    if mode != "A":
        grouped = {}
        for prediction in predictions:
            key = (prediction["start"], prediction["end"])
            previous = grouped.get(key)
            if previous is None:
                grouped[key] = prediction
            else:
                episode_present = previous["episodic"] or prediction["episodic"]
                if prediction["retention"] == "canonical" and previous["retention"] != "canonical":
                    grouped[key] = prediction
                grouped[key]["episodic"] = episode_present
        return list(grouped.values())
    return predictions


def _matches(prediction, label):
    return (prediction["start"], prediction["end"], prediction["quote"], prediction["predicate"],
            prediction["category"], prediction["assertion"], prediction["retention"]) == (
        label["start"], label["end"], label["quote"], label["expected_predicate"],
        label["expected_category"], label["expected_assertion"], label["expected_retention"])


def _score(rows):
    tp = fp = fn = tn = covered = episodes_expected = 0
    corrections = corrections_ok = accepted = provenance = attribution = false_promotions = sensitive_violations = 0
    failures = []
    for row in rows:
        predictions = row["predictions"]
        accepted += len(predictions)
        provenance += sum(p["provenance_ok"] for p in predictions)
        attribution += sum(p["retention"] == "canonical" and p["role"] != "user" and p["category"] == "profile" for p in predictions)
        for p in predictions:
            matching = [label for label in row["labels"] if label["useful_candidate"] and _matches(p, label)]
            if matching:
                tp += 1
            else:
                fp += 1
            aligned = next((l for l in row["labels"] if (l["start"], l["end"]) == (p["start"], p["end"])), None)
            if p["retention"] == "canonical" and (aligned is None or aligned["expected_retention"] != "canonical"):
                false_promotions += 1
                if "sensitiv" in row["theme"] or row["theme"] == "hypothetical-sensitive":
                    sensitive_violations += 1
        for label in row["labels"]:
            matched = any(_matches(p, label) for p in predictions)
            if label["useful_candidate"] and not matched:
                fn += 1
                failures.append({"opportunity_id": label["opportunity_id"], "code": "missed_or_mistyped"})
            if not label["useful_candidate"] and not any(
                (p["start"], p["end"]) == (label["start"], label["end"]) for p in predictions):
                tn += 1
            if label["useful_episode"]:
                episodes_expected += 1
                covered += int(any(p["episodic"] and p["provenance_ok"] and
                    (p["start"], p["end"], p["quote"]) == (label["start"], label["end"], label["quote"]) for p in predictions))
            if label["expected_predicate"] == "correction":
                corrections += 1
                corrections_ok += int(matched)
    precision = tp / (tp + fp) if tp + fp else 0
    recall = tp / (tp + fn) if tp + fn else 0
    return {"true_positives": tp, "false_positives": fp, "false_negatives": fn, "true_negatives": tn,
            "candidate_precision": precision, "candidate_recall": recall,
            "candidate_f1": 2 * precision * recall / (precision + recall) if precision + recall else 0,
            "episode_opportunities": episodes_expected, "episodes_covered": covered,
            "useful_episode_coverage": covered / episodes_expected if episodes_expected else None,
            "accepted_candidates": accepted, "validated_provenance": provenance,
            "accepted_provenance_rate": provenance / accepted if accepted else None,
            "source_span_validation_rate": provenance / accepted if accepted else None,
            "incorrect_user_profile_attribution": attribution, "false_positive_promotions": false_promotions,
            "sensitive_inference_violations": sensitive_violations,
            "correction_opportunities": corrections, "corrections_handled": corrections_ok,
            "correction_handling_rate": corrections_ok / corrections if corrections else None,
            "failures": failures}


class RecordingHandlers(MindHandlers):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.observations = []
        self.acquisition_code = "offline"
        if self.understanding is not None:
            process = self.understanding.process_event
            def record_acquisition(*args, **kwargs):
                result = process(*args, **kwargs)
                self.acquisition_code = result.code
                return result
            self.understanding.process_event = record_acquisition

    def execute(self, scope, job):
        started = time.perf_counter()
        try:
            counts = super().execute(scope, job)
        except Exception:
            self.observations.append({"event_id": job.target_id, "job_type": job.job_type.value,
                "seconds": time.perf_counter() - started, "code": "job_failed"})
            raise
        # Read this event's result, not provider.last_code from an older request.
        code = self.acquisition_code if job.job_type is JobType.EXTRACT_EVENT else "maintenance"
        self.observations.append({"event_id": job.target_id, "job_type": job.job_type.value,
            "seconds": time.perf_counter() - started, "code": code, "counts": counts})
        return counts


def run_mode(mode, corpus, output, *, model=None, endpoint="http://127.0.0.1:11434", timeout=20):
    path = output / ("mode-" + mode + ".sqlite3")
    store = SQLiteEventStore(path)
    store.initialize()
    rows, observations, workers, providers = [], [], {}, {}
    started, cpu_started, rss_start = time.perf_counter(), time.process_time(), rss_bytes()
    max_rss = rss_start or 0
    replay_new_records = []
    unauthorized_writes = 0
    scope = AuthorizedScope(tenant_id="mind2-synthetic", namespace="evaluation", principal_id="synthetic-host")
    for session_index, session in enumerate(corpus["sessions"]):
        exclusions = tuple(e["excluded_term"] for e in session["events"] if "excluded_term" in e)
        config = None if mode == "A" else ExtractionConfiguration(
            mode="local-llm" if mode == "C" else "rules", model=model if mode == "C" else None,
            endpoint=endpoint, timeout_seconds=timeout,
            sensitive_episodes=session.get("sensitive_episodes", False), exclude_terms=exclusions)
        key = config.identity if config else "legacy"
        if key not in workers:
            provider = OllamaExtractor(config) if mode == "C" else None
            providers[key] = provider
            handlers = RecordingHandlers(path, extraction_configuration=config, extraction_provider=provider)
            workers[key] = MindWorker(path, scope, handlers=handlers)
        worker = workers[key]
        scheduler = MindScheduler(path)
        constructed = {}
        for item in session["events"]:
            if "replay_of" in item:
                source = constructed[item["replay_of"]]
            else:
                when = datetime(2026, 1, 2, 12, tzinfo=timezone.utc) + timedelta(hours=session_index, seconds=item["turn"])
                event_scope = scope.model_copy(update={"tenant_id": "mind2-other-owner"}) if item.get("foreign_scope") else scope
                source = MemoryEvent(event_id=item["event_id"], tenant_id=event_scope.tenant_id,
                    namespace=event_scope.namespace, event_type=item["role"] + "_message", source_type=item["role"],
                    content=item["text"], occurred_at=when, ingested_at=when,
                    source_reference=SourceReference(source_system="mind2-synthetic", external_event_id=item["event_id"],
                        timestamp=when, session_id=session["session_id"]), metadata={"ingested_by": scope.principal_id})
            constructed[item["turn"]] = source
            event_scope = scope.model_copy(update={"tenant_id": source.tenant_id})
            store.append(event_scope, source)
            if item.get("foreign_scope"):
                predictions = _predictions(path, scope, source, mode)
                unauthorized_writes += len(predictions)
            else:
                before = len(_predictions(path, scope, source, mode)) if "replay_of" in item else 0
                if "replay_of" in item:
                    scheduler.enqueue(scope, JobType.EXTRACT_EVENT, source.event_id, generation="evaluation-replay")
                # Only current events exist in this disposable DB. This drains
                # extraction plus ordinary follow-up jobs through the real worker.
                work = worker.run_once(max_jobs=8, dispatch_limit=16)
                if item.get("retracted"):
                    existing = _predictions(path, scope, source, mode)
                    for prediction in existing:
                        SQLiteMindProjectionStore(path).retract_source(scope, prediction["memory_id"], source.event_id)
                    scheduler.enqueue(scope, JobType.EXTRACT_EVENT, source.event_id, generation="evaluation-retraction-replay")
                    worker.run_once(max_jobs=4)
                predictions = _predictions(path, scope, source, mode)
                if "replay_of" in item:
                    replay_new_records.append(max(0, len(predictions) - before))
            rows.append({"session_id": session["session_id"], "theme": session["theme"],
                "event_id": source.event_id, "labels": item["labels"], "predictions": predictions,
                "foreign_scope": item.get("foreign_scope", False)})
            max_rss = max(max_rss, rss_bytes() or 0)
        print(json.dumps({"mode": mode, "sessions_completed": session_index + 1, "events_scored": len(rows)}), flush=True)
    for worker in workers.values():
        observations.extend(worker.handlers.observations)
    extraction = [o for o in observations if o["job_type"] == "extract_event"]
    times = sorted(o["seconds"] for o in extraction)
    result = _score(rows)
    result.update(mode=mode, sessions=len(corpus["sessions"]), events=len(rows),
        opportunities=sum(len(r["labels"]) for r in rows), annotation_status="Codex draft; pending independent human review",
        unauthorized_cross_scope_writes=unauthorized_writes, replay_new_candidate_records=sum(replay_new_records),
        model_invocations=sum(o.get("counts", {}).get("model_calls", 0) for o in extraction),
        model_proposals=sum(o.get("counts", {}).get("model_proposals", 0) for o in extraction),
        model_accepted=sum(o.get("counts", {}).get("model_accepted", 0) for o in extraction),
        model_rejected=sum(o.get("counts", {}).get("model_rejected", 0) for o in extraction),
        model_refinements=sum(o.get("counts", {}).get("model_refinements", 0) for o in extraction),
        degraded_extraction_jobs=sum(o.get("counts", {}).get("extraction_degraded", 0) for o in extraction),
        failed_extraction_jobs=sum(o.get("code") == "job_failed" for o in extraction),
        extraction_jobs=len(extraction), wall_seconds=time.perf_counter() - started,
        extraction_latency_p50_seconds=statistics.median(times) if times else None,
        extraction_latency_p95_seconds=times[max(0, int(len(times) * .95) - 1)] if times else None,
        client_cpu_seconds=time.process_time() - cpu_started, client_rss_start_bytes=rss_start,
        client_rss_sampled_peak_bytes=max_rss or None,
        resource_scope="Python client only; does not measure Ollama CPU, RAM, or GPU consumption",
        monetary_cost="not measured; no paid API invoked", rows=rows, observations=observations)
    with SQLiteGraphStore(path)._graph_read() as connection:
        exact_duplicates = connection.execute(
            """SELECT SUM(n-1) FROM (SELECT COUNT(*) n FROM memories
               WHERE json_extract(metadata_json,'$.p2_episode') IS NOT 1
               GROUP BY tenant_id,namespace,memory_type,canonical_content HAVING COUNT(*)>1)""").fetchone()[0] or 0
        canonical = connection.execute("SELECT COUNT(*) FROM memories WHERE json_extract(metadata_json,'$.p2_episode') IS NOT 1").fetchone()[0]
    result.update(exact_content_duplicate_memories=exact_duplicates, canonical_records=canonical,
                  duplicate_memory_rate=exact_duplicates / canonical if canonical else 0)
    result["targets_met"] = {
        "precision": result["candidate_precision"] >= .95, "recall": result["candidate_recall"] >= .85,
        "provenance": result["accepted_provenance_rate"] == 1,
        "no_unauthorized_writes": unauthorized_writes == 0,
        "no_assistant_profile_promotion": result["incorrect_user_profile_attribution"] == 0}
    (output / f"mode-{mode}.json").write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="NEW disposable output directory")
    parser.add_argument("--modes", nargs="+", choices=("A", "B", "C"), default=["A", "B"])
    parser.add_argument("--local-model", help="explicit already-installed generation model; required for C")
    parser.add_argument("--endpoint", default="http://127.0.0.1:11434")
    parser.add_argument("--timeout", type=int, default=20)
    args = parser.parse_args(argv)
    if "C" in args.modes and not args.local_model:
        parser.error("C requires --local-model; no model is selected or downloaded automatically")
    corpus, manifest = load_corpus()
    args.output.mkdir(parents=True, exist_ok=False)
    metadata = {"python": platform.python_version(), "sqlite": __import__("sqlite3").sqlite_version,
        "platform": platform.system(), "logical_cpus": os.cpu_count(), "dataset_manifest": manifest,
        "prompt_version": PROMPT_VERSION, "system_prompt": SYSTEM_PROMPT,
        "prompt_sha256": hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest(),
        "privacy_route": "literal-loopback; synthetic data only", "local_model": args.local_model}
    if args.local_model:
        for name, route, payload in (("version", "/api/version", None), ("tags", "/api/tags", None),
                ("show", "/api/show", {"model": args.local_model})):
            try:
                document = request_json(args.endpoint, route, payload=payload, timeout=3, max_bytes=131072)
                if name == "tags":
                    document = {"models": [m for m in document.get("models", []) if m.get("name") == args.local_model]}
                if name == "show":
                    document = {key: document[key] for key in ("details", "capabilities") if key in document}
                metadata["ollama_" + name] = document
            except Exception:
                metadata["ollama_" + name] = {"status": "NOT TESTED"}
    (args.output / "run.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    results = [run_mode(mode, corpus, args.output, model=args.local_model, endpoint=args.endpoint, timeout=args.timeout) for mode in args.modes]
    summary = [{key: value for key, value in result.items() if key not in {"rows", "observations", "failures"}} for result in results]
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
