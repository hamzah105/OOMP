r"""Explicit real-model acceptance using new, public synthetic storage only.

An installed model and an already-running literal-loopback Ollama are required.
No weights are downloaded and no service is started. The output directory must
not exist. Both modes process identical selected cases through actual Mind jobs.

    .\.venv\Scripts\python.exe examples/mind2_model_acceptance.py `
        --model llama3:latest --directory "$env:TEMP\oomp-model-new-run"

Exit 0 requires independently validated model output, persisted model evidence,
and a canonical interpretation absent from rules-only output. Fallback is not
model success. All source text in the artifact is fixed, public synthetic text.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import time


CASES = (
    ("preference", "user", "I prefer tea."),
    ("procedure", "user", "Please use numbered setup steps."),
    ("alias", "user", "My friends call me Cedar."),
    ("assistant", "assistant", "I prefer tea."),
)
_METRICS = {
    "elapsed_seconds", "total_duration", "load_duration", "prompt_eval_count",
    "prompt_eval_duration", "eval_count", "eval_duration", "prompt_eval_cached_count",
}
_SNAPSHOT_QUERIES = (
    "SELECT event_id,content FROM events ORDER BY event_id",
    "SELECT memory_id,memory_type,canonical_content,metadata_json FROM memories ORDER BY memory_id",
    "SELECT memory_id,event_id,source_span_json,extraction_method FROM memory_sources ORDER BY memory_id,event_id",
)


def _snapshot(connection):
    rows = [connection.execute(query).fetchall() for query in _SNAPSHOT_QUERIES]
    return hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()


def _require(condition, code):
    if not condition:
        raise RuntimeError("synthetic model acceptance failed: " + code)


def _mode(directory, scope, originals, configuration, provider=None):
    from oomp.mind.handlers import MindHandlers
    from oomp.mind.worker import MindWorker
    from oomp.storage import SQLiteEventStore
    from oomp.storage.memory_store import SQLiteMemoryStore
    from oomp.understanding.engine import UnderstandingEngine

    records = []

    class ObservedEngine(UnderstandingEngine):
        def process_event(self, authorized, event_id, *, job=None):
            started = time.monotonic()
            result = super().process_event(authorized, event_id, job=job)
            metrics = getattr(self.provider, "last_metrics", {})
            records.append({
                "event_id": event_id,
                "elapsed_seconds": time.monotonic() - started,
                "code": result.code,
                "degraded": result.degraded,
                "model_calls": result.model_calls,
                "model_proposals": result.model_proposals,
                "model_accepted": result.model_accepted,
                "model_rejected": result.model_rejected,
                "model_refinements": result.model_refinements,
                "processing": result.processing.model_dump(mode="json"),
                "model_classifications": getattr(self.provider, "last_classifications", []) if result.model_calls else [],
                "inference_metrics": {
                    key: value for key, value in metrics.items()
                    if key in _METRICS and type(value) in {int, float}
                    and value >= 0
                } if result.model_calls else {},
            })
            return result

    directory.mkdir()
    path = directory / "synthetic.sqlite3"
    sources = SQLiteEventStore(path)
    _require(sources.initialize() == 5, "schema_version")
    for source in originals.values():
        sources.append(scope, source)
    handlers = MindHandlers(path, extraction_configuration=configuration,
                            extraction_provider=provider)
    handlers.understanding = ObservedEngine(path, configuration, provider=provider)
    worker = MindWorker(path, scope, handlers=handlers)
    started = time.monotonic()
    result = worker.run_once(max_jobs=100)
    elapsed = time.monotonic() - started
    _require(result.completed >= len(originals)
             and not any((result.failed, result.retried, result.lost_lease)),
             "worker_completion")
    _require(len(records) == len(originals), "every_selected_case_observed")

    memories = SQLiteMemoryStore(path).list_memories(scope, limit=100)
    _require(memories.next_cursor is None, "bounded_inspection")
    memory_by_id = {memory.memory_id: memory for memory in memories.memories}
    _require(all(sources.get(scope, key) == source for key, source in originals.items()),
             "immutable_source")
    _require(all(memory.provenance == tuple(originals[key].source_reference
                 for key in memory.source_event_ids) for memory in memories.memories),
             "exact_provenance")
    proofs = []
    with sqlite3.connect(path) as connection:
        for memory_id, event_id, raw_span, method in connection.execute(
            "SELECT memory_id,event_id,source_span_json,extraction_method FROM memory_sources"
        ):
            span = json.loads(raw_span)
            _require(originals[event_id].content[span["start"]:span["end"]] == span["quote"],
                     "exact_source_span")
            proofs.append({"memory_id": memory_id, "event_id": event_id,
                           "source_span": span, "extraction_method": method,
                           "canonical": memory_by_id[memory_id].memory_type.value != "episodic"})
        snapshot = _snapshot(connection)

    # A separate isolated Python process reopens only the newly created database.
    # It imports no model/provider code and returns a hash, never source content.
    restart_code = (
        "import hashlib,json,sqlite3,sys; from pathlib import Path; "
        "p=Path(sys.argv[1]); c=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True); "
        "queries=json.loads(sys.argv[2]); rows=[c.execute(q).fetchall() for q in queries]; "
        "print(hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()); c.close()"
    )
    reopened = subprocess.run(
        [sys.executable, "-I", "-c", restart_code, str(path.absolute()),
         json.dumps(_SNAPSHOT_QUERIES)], capture_output=True, text=True, timeout=20,
    )
    _require(reopened.returncode == 0 and reopened.stdout.strip() == snapshot,
             "restart_persists_sources_memories_proofs")
    # A fresh worker must find no extraction work and make no new inference call.
    calls_before = getattr(provider, "calls", 0)
    restarted = MindWorker(path, scope, extraction_configuration=configuration,
                           extraction_provider=provider).run_once(max_jobs=100)
    _require(restarted.claimed == 0 and getattr(provider, "calls", 0) == calls_before,
             "restart_does_not_repeat_extraction")
    canonical_ids = sorted(key for key, memory in memory_by_id.items()
                           if memory.memory_type.value != "episodic")
    _require(all(memory.memory_type.value == "episodic"
                 for memory in memory_by_id.values()
                 if "p21-model-assistant" in memory.source_event_ids),
             "assistant_never_becomes_user_profile")
    for memory in memory_by_id.values():
        if memory.metadata.get("predicate") == "alias":
            _require(memory.metadata.get("authenticated") is False
                     and memory.metadata.get("verified") is False, "alias_not_authenticated")
    return {
        "mode": configuration.mode, "worker": asdict(result),
        "elapsed_seconds": elapsed, "events": records,
        "memories": len(memory_by_id), "memory_ids": sorted(memory_by_id), "canonical_ids": canonical_ids,
        "proofs": proofs, "restart_verified": True,
        "immutable_exact_provenance": True, "assistant_profile_promotions": 0,
        **{key: sum(row[key] for row in records) for key in (
            "model_calls", "model_proposals", "model_accepted", "model_rejected", "model_refinements")},
    }


def run(directory, *, model, endpoint="http://127.0.0.1:11434", timeout=60,
        max_output_tokens=128, cases=None, warmup_timeout=None):
    """Run selected frozen public cases; existing output paths are refused first."""
    directory = Path(directory).absolute()
    directory.mkdir(parents=True, exist_ok=False)

    from oomp.domain.models import AuthorizedScope, MemoryEvent, SourceReference
    from oomp.understanding.contracts import ExtractionConfiguration
    from oomp.understanding.providers import OllamaExtractor, PROMPT_VERSION
    from oomp.understanding.providers import SYSTEM_PROMPT
    from oomp.understanding.transport import ExtractionUnavailable, request_json
    from oomp.understanding.validator import CandidateValidator, CandidateRejected

    configuration = ExtractionConfiguration(mode="local-llm", model=model, endpoint=endpoint,
        timeout_seconds=timeout, max_output_tokens=max_output_tokens)
    if warmup_timeout is not None and (type(warmup_timeout) is not int or not 1 <= warmup_timeout <= 180):
        raise ValueError("warmup_timeout_must_be_1_to_180_seconds")
    selected = tuple(case for case in CASES if cases is None or case[0] in cases)
    _require(bool(selected) and (cases is None or set(cases) <= {case[0] for case in CASES}),
             "supported_synthetic_cases_required")
    report = {
        "version": "mind2.model-acceptance.v1", "synthetic": True,
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "configuration": configuration.model_dump(mode="json"),
        "prompt_version": PROMPT_VERSION, "selected_cases": [case[0] for case in selected],
        "system_prompt_sha256": hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest(),
        "source_events": len(selected), "acceptance": False,
        "model_downloads": 0, "services_started": False, "existing_private_storage_used": False,
    }
    try:
        version = request_json(endpoint, "/api/version", timeout=3)
        tags = request_json(endpoint, "/api/tags", timeout=3)
        installed = next((entry for entry in tags.get("models", [])[:128]
                          if isinstance(entry, dict) and entry.get("name") == model), None)
        if installed is None:
            raise ExtractionUnavailable("extraction_model_not_installed")
        report["ollama"] = {"version": version.get("version"), "model": model,
            "digest": installed.get("digest"), "size_bytes": installed.get("size"),
            "details": installed.get("details", {})}
    except ExtractionUnavailable as error:
        report["code"] = error.code
        (directory / "acceptance.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        return report

    scope = AuthorizedScope(tenant_id="p21-public-model-demo", namespace="synthetic",
                            principal_id="fictional-demo-host")
    when = datetime(2026, 1, 2, 12, tzinfo=timezone.utc)
    originals = {}
    for index, (name, role, content) in enumerate(selected):
        event_id = "p21-model-" + name
        timestamp = when + timedelta(seconds=index)
        originals[event_id] = MemoryEvent(
            event_id=event_id, tenant_id=scope.tenant_id, namespace=scope.namespace,
            event_type=role + "_message", source_type=role, content=content,
            occurred_at=timestamp, ingested_at=timestamp,
            source_reference=SourceReference(source_system="public-synthetic-model-demo",
                external_event_id=event_id, timestamp=timestamp,
                session_id="fictional-model-demo-session", turn_id="turn-" + str(index)),
            metadata={"ingested_by": scope.principal_id},
        )
    report["synthetic_cases"] = [source.model_dump(mode="json") for source in originals.values()]
    report["synthetic_cases_sha256"] = hashlib.sha256(
        json.dumps(report["synthetic_cases"], sort_keys=True).encode()
    ).hexdigest()
    report["rules"] = _mode(directory / "rules", scope, originals, ExtractionConfiguration())
    if warmup_timeout is not None:
        # Explicit operator diagnostic, separate from extraction's <=60s budget.
        # Empty prompt loads the already-installed model; no source is forwarded.
        started = time.monotonic()
        try:
            loaded = request_json(endpoint, "/api/generate", timeout=warmup_timeout,
                payload={"model": model, "prompt": "", "stream": False, "keep_alive": "30s",
                    "options": {"num_ctx": 4096, "num_thread": 2, "num_predict": 1}})
            report["warmup"] = {"code": "model_load_completed" if loaded.get("done") is True
                and loaded.get("model") == model else "model_load_invalid",
                "metrics": {key: value for key, value in loaded.items()
                            if key in _METRICS and type(value) is int and 0 <= value <= 10**18}}
        except ExtractionUnavailable as error:
            report["warmup"] = {"code": error.code}
        report["warmup"].update(timeout_seconds=warmup_timeout,
                                elapsed_seconds=time.monotonic() - started)
    class ObservedProvider(OllamaExtractor):
        def propose(self, authorized, source):
            self.last_classifications = []
            proposals = super().propose(authorized, source)
            for proposal in proposals:
                classification = {key: getattr(proposal, key) for key in (
                    "predicate", "memory_category", "assertion_kind")}
                try:
                    CandidateValidator(configuration).validate(authorized, source, (proposal,))
                    classification["validation_code"] = "candidate_validated"
                except CandidateRejected as error:
                    classification["validation_code"] = error.code
                self.last_classifications.append(classification)
            return proposals
    provider = ObservedProvider(configuration)
    report["model"] = _mode(directory / "model", scope, originals, configuration, provider)
    _require(set(report["rules"]["memory_ids"]) <= set(report["model"]["memory_ids"]),
             "rules_memories_preserved")
    added = set(report["model"]["canonical_ids"]) - set(report["rules"]["canonical_ids"])
    model_proofs = [proof for proof in report["model"]["proofs"]
                    if proof["extraction_method"].startswith("mind2.ollama.")]
    incremental_proofs = [proof for proof in model_proofs
                          if proof["canonical"] and proof["memory_id"] in added]
    report["model_persisted_proofs"] = len(model_proofs)
    report["incremental_canonical_ids"] = sorted(added)
    report["incremental_model_proofs"] = len(incremental_proofs)
    report["rules_memories_preserved"] = True
    report["acceptance"] = bool(report["model"]["model_calls"] > 0
        and report["model"]["model_proposals"] > 0
        and report["model"]["model_accepted"] > 0 and incremental_proofs
        and report["model"]["restart_verified"])
    report["code"] = "model_incremental_acceptance_passed" if report["acceptance"] else "model_incremental_acceptance_failed"
    (directory / "acceptance.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True, help="new disposable directory; existing paths are refused")
    parser.add_argument("--model", required=True, help="explicit already-installed Ollama generation model")
    parser.add_argument("--endpoint", default="http://127.0.0.1:11434")
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--max-output-tokens", type=int, default=128)
    parser.add_argument("--warmup-timeout", type=int, help="explicit empty-prompt model load, 1-180 seconds; separate from extraction")
    parser.add_argument("--case", action="append", choices=[case[0] for case in CASES],
                        help="explicit subset; repeat to select more cases (default: all four)")
    args = parser.parse_args(argv)
    try:
        report = run(args.directory, model=args.model, endpoint=args.endpoint,
                     timeout=args.timeout, max_output_tokens=args.max_output_tokens, cases=args.case,
                     warmup_timeout=args.warmup_timeout)
    except FileExistsError:
        print(json.dumps({"acceptance": False, "code": "new_directory_required"}))
        return 1
    summary = {key: report[key] for key in ("acceptance", "code", "source_events") if key in report}
    if "model" in report:
        summary.update({key: report["model"][key] for key in (
            "model_calls", "model_proposals", "model_accepted", "model_rejected", "model_refinements")})
        summary["incremental_model_proofs"] = report["incremental_model_proofs"]
    print(json.dumps(summary))
    return 0 if report["acceptance"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
