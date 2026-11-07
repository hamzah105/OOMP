"""Read context through the official MCP SDK, without importing the server package.

Requires the installed MCP 2.3 SDK (and its httpx2 dependency). See
docs/generic-context-host.md. Importing this module does not connect or start work.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
import json
import logging
import math
import os
import re
import sys
from urllib.parse import urlsplit

VERSION = "oomp.context.v1"
COUNTING = "utf8_bytes_upper_bound_v1"
DEFAULT_ENDPOINT = "http://127.0.0.1:8765/mcp"
STATUSES = {"found_relevant_evidence", "no_relevant_evidence", "index_incomplete",
            "coverage_unknown", "unavailable", "unauthorized", "candidate_uncertain", "budget_excluded"}


class HostError(ValueError):
    """A local validation failure; messages contain static codes only."""


def require(condition, code):
    if not condition:
        raise HostError(code)


def shape(value, required, optional=()):
    require(type(value) is dict and set(required) <= value.keys()
            and value.keys() <= set(required) | set(optional), "invalid_object_shape")


def text(value, maximum):
    return type(value) is str and 0 < len(value) <= maximum and bool(value.strip()) and "\0" not in value


def identifier(value):
    return type(value) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", value) is not None


def integer(value, minimum, maximum):
    return type(value) is int and minimum <= value <= maximum


def timestamp(value):
    require(type(value) is str, "invalid_timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        require(parsed.utcoffset() is not None, "invalid_timestamp")
    except ValueError:
        raise HostError("invalid_timestamp") from None


def reference(value):
    shape(value, {"source_system", "external_event_id", "timestamp"}, {"session_id", "turn_id", "locator"})
    require(identifier(value["source_system"]) and text(value["external_event_id"], 512), "invalid_reference_identity")
    timestamp(value["timestamp"])
    for key in ("session_id", "turn_id"):
        require(value.get(key) is None or identifier(value[key]), "invalid_reference_identity")
    require(value.get("locator") is None or text(value["locator"], 1024), "invalid_reference_locator")
    return {key: item for key, item in value.items() if item is not None}


def evidence(value):
    required = {"unit_id", "resolution", "content", "memory_ids", "source_proofs", "object_ids",
                "assertion_kinds", "temporal_status", "selection_reasons", "derived", "uncertain"}
    optional = {"revision_id", "source_fingerprint", "retrieval_score"}
    shape(value, required, optional)
    require(identifier(value["unit_id"]) and text(value["content"], 1_000_000), "invalid_evidence")
    require(value["resolution"] in {"object_snapshot", "episode_summary", "canonical_fact", "source_evidence"},
            "invalid_resolution")
    for key, minimum, maximum in (("memory_ids", 1, 16), ("object_ids", 0, 8), ("selection_reasons", 0, 16)):
        items = value[key]
        require(type(items) is list and minimum <= len(items) <= maximum
                and all(identifier(item) for item in items) and len(set(items)) == len(items), "invalid_evidence_ids")
    require(type(value["assertion_kinds"]) is list and len(value["assertion_kinds"]) <= 16
            and all(text(item, 64) for item in value["assertion_kinds"])
            and text(value["temporal_status"], 64)
            and type(value["derived"]) is bool and type(value["uncertain"]) is bool, "invalid_evidence_metadata")
    require(value.get("revision_id") is None or identifier(value["revision_id"]), "invalid_revision")
    fingerprint = value.get("source_fingerprint")
    require(fingerprint is None or (type(fingerprint) is str and re.fullmatch(r"[a-f0-9]{64}", fingerprint)),
            "invalid_fingerprint")
    score = value.get("retrieval_score")
    require(score is None or (type(score) in (float, int) and math.isfinite(score)), "invalid_score")
    proofs, identities = [], set()
    require(type(value["source_proofs"]) is list and 1 <= len(value["source_proofs"]) <= 16, "missing_source_proofs")
    for proof in value["source_proofs"]:
        shape(proof, {"memory_id", "event_id", "source_reference", "span_start", "span_end"}, {"quote"})
        start, end = proof["span_start"], proof["span_end"]
        require(identifier(proof["memory_id"]) and identifier(proof["event_id"])
                and integer(start, 0, 999_999) and integer(end, 1, 1_000_000) and start < end,
                "invalid_source_proof")
        require(proof.get("quote") is None, "unexpected_raw_source")
        identity = (proof["memory_id"], proof["event_id"], start, end)
        require(identity not in identities, "duplicate_source_proof")
        identities.add(identity)
        proofs.append({**{key: item for key, item in proof.items() if key != "quote"},
                       "source_reference": reference(proof["source_reference"])})
    require(set(value["memory_ids"]) == {proof["memory_id"] for proof in proofs}, "memory_proof_mismatch")
    return {**{key: item for key, item in value.items() if key not in optional or item is not None},
            "source_proofs": proofs}


def json_object(pairs):
    require(len(pairs) == len(dict(pairs)), "duplicate_json_key")
    return dict(pairs)


def invalid_constant(_value):
    raise HostError("invalid_json_number")


def validate_context(data, budget, max_results):
    """Check wire structure and byte accounting; this does not authenticate sources."""
    require(type(data) is dict and data.get("context_contract_version") == VERSION, "unsupported_context_version")
    require(data.get("source_data_untrusted") is True and data.get("budget_scope") == "context_packet_only"
            and data.get("counting_method") == COUNTING, "invalid_context_markers")
    require(data.get("retrieval_status") in STATUSES, "invalid_context_status")
    require(integer(data.get("token_budget"), 1, 32768) and data["token_budget"] == budget, "budget_mismatch")
    packet, units, references = data.get("context_packet"), data.get("evidence_packets"), data.get("source_references")
    require(type(packet) is str and type(units) is list and len(units) <= max_results
            and type(references) is list and len(references) <= 320, "invalid_context_shape")
    measured = len(packet.encode("utf-8"))
    require(integer(data.get("selected_context_bytes"), 0, budget)
            and data["selected_context_bytes"] == measured, "invalid_packet_bytes")
    if not units:
        require(packet == "" and references == [] and data["retrieval_status"] != "found_relevant_evidence",
                "invalid_empty_context")
        return []
    require(data["retrieval_status"] in {"found_relevant_evidence", "candidate_uncertain"}, "unexpected_context_evidence")
    decoded = json.loads(packet, object_pairs_hook=json_object, parse_constant=invalid_constant)
    shape(decoded, {"context_contract_version", "evidence_packets", "token_budget", "counting_method", "selected_context_bytes"})
    require(decoded["context_contract_version"] == VERSION and decoded["counting_method"] == COUNTING
            and integer(decoded["token_budget"], 1, 32768) and decoded["token_budget"] == budget
            and integer(decoded["selected_context_bytes"], 1, budget) and decoded["selected_context_bytes"] == measured,
            "invalid_packet_metadata")
    normalized = [evidence(unit) for unit in units]
    require(type(decoded["evidence_packets"]) is list
            and [evidence(unit) for unit in decoded["evidence_packets"]] == normalized, "packet_evidence_mismatch")
    expected = []
    proofs = [proof for unit in normalized for proof in unit["source_proofs"]]
    for proof in proofs:
        if proof["source_reference"] not in expected:
            expected.append(proof["source_reference"])
    require([reference(item) for item in references] == expected, "source_reference_mismatch")
    return proofs


def validate_source(data, proof):
    shape(data, {"memory_id", "sources", "source_data_untrusted"}, {"next_event_id"})
    require(data["source_data_untrusted"] is True and data["memory_id"] == proof["memory_id"]
            and data.get("next_event_id") is None and type(data["sources"]) is list and len(data["sources"]) == 1,
            "invalid_linked_source")
    source = data["sources"][0]
    shape(source, {"event_id", "event_type", "source_type", "source_reference", "occurred_at", "ingested_at"}, {"content"})
    require(source["event_id"] == proof["event_id"] and source.get("content") is None
            and text(source["event_type"], 128) and text(source["source_type"], 128)
            and reference(source["source_reference"]) == proof["source_reference"], "linked_source_mismatch")
    timestamp(source["occurred_at"])
    timestamp(source["ingested_at"])


def connection_settings(environment, token_env):
    endpoint = environment.get("MCP_ENDPOINT", DEFAULT_ENDPOINT)
    require(type(endpoint) is str and not any(ord(char) <= 32 for char in endpoint), "invalid_endpoint")
    parts = urlsplit(endpoint)
    port = 80 if parts.port is None else parts.port
    require(parts.scheme == "http" and parts.hostname in {"127.0.0.1", "::1"}
            and parts.path == "/mcp" and parts.username is None and parts.password is None
            and not parts.query and not parts.fragment and 1 <= port <= 65535, "literal_loopback_required")
    token = environment.get(token_env, "")
    require(type(token) is str and 32 <= len(token) <= 4096 and not any(char.isspace() for char in token)
            and all(32 <= ord(char) < 127 for char in token), "missing_or_invalid_bearer")
    return endpoint, token


async def read_context(query, *, token_budget=6000, max_results=8, get_source=False,
                       token_env="MCP_BEARER_TOKEN", environment=None):
    require(text(query, 4096) and integer(token_budget, 1, 32768)
            and integer(max_results, 1, 20), "invalid_request")
    endpoint, token = connection_settings(os.environ if environment is None else environment, token_env)
    import httpx2
    from mcp import Client
    from mcp.client.streamable_http import streamable_http_client

    async with asyncio.timeout(20):
        async with httpx2.AsyncClient(headers={"Authorization": "Bearer " + token}, trust_env=False,
                                      timeout=5, follow_redirects=False) as http:
            async with Client(streamable_http_client(endpoint, http_client=http)) as client:
                names = {tool.name for tool in (await client.list_tools()).tools}
                require("memory.context" in names and (not get_source or "memory.get_source" in names),
                        "required_read_tool_unavailable")
                response = await client.call_tool("memory.context", {
                    "query": query, "token_budget": token_budget, "max_results": max_results,
                    "include_source_content": False,
                })
                require(response.is_error is False, "context_tool_failed")
                data = response.structured_content
                proofs = validate_context(data, token_budget, max_results)
                if get_source and proofs:
                    proof = proofs[0]
                    linked = await client.call_tool("memory.get_source", {
                        "memory_id": proof["memory_id"], "event_id": proof["event_id"],
                        "include_content": False, "limit": 1,
                    })
                    require(linked.is_error is False, "source_tool_failed")
                    validate_source(linked.structured_content, proof)
    return {"context_contract_version": VERSION, "retrieval_status": data["retrieval_status"],
            "packet_bytes": data["selected_context_bytes"], "evidence_units": len(data["evidence_packets"]),
            "source_proofs": len(proofs), "linked_source_checked": bool(get_source and proofs)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query")
    parser.add_argument("--token-env", default="MCP_BEARER_TOKEN", help="name of the bearer environment variable")
    parser.add_argument("--token-budget", type=int, default=6000)
    parser.add_argument("--max-results", type=int, default=8)
    parser.add_argument("--get-source", action="store_true", help="check metadata for the first returned source proof")
    args = parser.parse_args(argv)
    previous_logging_disable = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        result = asyncio.run(read_context(args.query, token_env=args.token_env, token_budget=args.token_budget,
                                         max_results=args.max_results, get_source=args.get_source))
    except Exception:
        # Transport/SDK exception messages can contain sensitive server data.
        print("generic_context_host_failed", file=sys.stderr)
        return 1
    finally:
        logging.disable(previous_logging_disable)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
