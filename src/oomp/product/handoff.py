"""Explicit, reference-only handoff to one independently approved TRACE project."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit

from .safety import ProductError, read_json, restrict, safe_path

LOCAL_FILE = ".oomp.local.json"
FORMAT = "oomp.trace.local.v1"
# Updated with the reviewed independent TRACE bootstrap proposal, not host data.
TRACE_HELPER_SHA256 = "02b6ecf87dff7c0beef57a8028d4895d83ba833011699be684766869031b5239"


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


def _trace_query(project, arguments):
    project = safe_path(project)
    python = safe_path(project / ".venv/Scripts/python.exe" if os.name == "nt" else project / ".venv/bin/python")
    helper = safe_path(project / "backend/services/oomp_local.py")
    if (not python.is_file() or not helper.is_file()
            or hashlib.sha256(helper.read_bytes()).hexdigest() != TRACE_HELPER_SHA256):
        raise ProductError("reviewed_trace_bootstrap_required")
    env = {name: os.environ[name] for name in ("SystemRoot", "WINDIR", "COMSPEC", "PATH", "LANG") if name in os.environ}
    env.update(PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1")
    try:
        result = subprocess.run([str(python), "-I", "-B", str(helper), *arguments],
            cwd=project, env=env, capture_output=True, timeout=8,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        if result.returncode or len(result.stdout) > 65536 or result.stderr:
            raise ProductError("trace_local_inspection_failed")
        data = json.loads(result.stdout)
        if not isinstance(data, dict) or data.get("ok") is not True:
            raise ProductError("trace_local_inspection_failed")
        return data
    except (OSError, subprocess.SubprocessError, ValueError):
        raise ProductError("trace_local_inspection_failed") from None


def inspect_trace(project, owner_id=None):
    """Public metadata only; validation queries only the explicitly supplied user."""
    arguments = ["--inspect"]
    if owner_id is not None:
        if not re.fullmatch(r"[0-9a-fA-F]{24}", owner_id):
            raise ProductError("trace_owner_id_invalid")
        arguments += ["--owner-id", owner_id]
    data = _trace_query(project, arguments)
    return {name: data[name] for name in ("python", "mongo_database", "mongo_uri_env", "mongo_configured", "owner_validated")}


def validate_trace_owner(project, python, owner_id, *, timeout=8):
    expected = safe_path(Path(project) / (".venv/Scripts/python.exe" if os.name == "nt" else ".venv/bin/python"))
    if safe_path(python) != expected or timeout > 8:
        raise ProductError("trace_python_mismatch")
    return inspect_trace(project, owner_id)["owner_validated"] is True


@contextmanager
def prepare_environment(store, profile):
    """Resolve only the approved local Mongo reference, without persisting it."""
    if profile.adapter != "trace" or not profile.publication:
        yield
        return
    data = _trace_query(profile.project, ["--connection"])
    if data.get("mongo_database") != profile.mongo_database:
        raise ProductError("trace_database_mismatch")
    name = profile.mongo_uri_env
    selected_uri = _literal_publication_uri(data["mongo_uri"])
    previous = os.environ.get(name)
    if previous is not None and _literal_publication_uri(previous) != selected_uri:
        raise ProductError("trace_mongo_reference_conflict")
    os.environ[name] = selected_uri
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = previous


def _literal_publication_uri(value):
    """Resolve the exact localhost spelling without DNS or changing endpoints.

    The supervisor's existing literal-loopback admission stays unchanged. The
    project dotenv file and inherited reference are never rewritten.
    """
    try:
        parsed = urlsplit(value)
        if (parsed.scheme != "mongodb" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
                or "," in parsed.netloc or parsed.fragment
                or parsed.port is not None and not 1 <= parsed.port <= 65535):
            raise ValueError()
        if parsed.hostname == "localhost":
            userinfo, separator, unused_host = parsed.netloc.rpartition("@")
            authority = (userinfo + separator if separator else "") + "127.0.0.1"
            if parsed.port is not None:
                authority += ":" + str(parsed.port)
            return parsed._replace(netloc=authority).geturl()
        return value
    except (TypeError, ValueError):
        raise ProductError("explicit_local_mongo_reference_required") from None


def _payload(store, profile):
    if profile.adapter != "trace" or profile.secret_source != "file":
        raise ProductError("trace_file_profile_required")
    if store.load(profile.name) != profile:
        raise ProductError("profile_changed")
    generation = store.generation(profile)
    for name in ("profile.json", "server.json", "writers.json"):
        read_json(generation/name)
    # References only. Authentication values stay in the existing private file.
    body = {
        "format": FORMAT, "project": str(safe_path(profile.project)),
        "profile_home": str(store.home), "profile_name": profile.name,
        "generation": profile.identity, "owner_id": profile.owner_id,
        "scope": {"tenant": profile.tenant, "namespace": profile.namespace, "principal": profile.principal},
        "retrieval_api": "context_v1" if profile.context_enabled else "retrieve",
        "source_sha256": {name: hashlib.sha256((generation/name).read_bytes()).hexdigest()
                          for name in ("profile.json", "server.json", "writers.json")},
    }
    # Validate existing private credential material through the normal store.
    environment = store.environment(profile)
    key = environment[profile.reference("owner_key")].encode("ascii")
    return {**body, "signature": hmac.new(key, _canonical(body), hashlib.sha256).hexdigest()}


def preview_trace(store, profile):
    target = safe_path(Path(profile.project)/LOCAL_FILE)
    payload = _payload(store, profile)
    if target.exists():
        if read_json(target) != payload:
            raise ProductError("trace_handoff_changed_requires_review")
        return {"configured": True, "changed": False, "path": str(target), "retrieval_api": payload["retrieval_api"]}
    return {"configured": False, "changed": False, "path": str(target), "retrieval_api": payload["retrieval_api"]}


def configure_trace(store, profile, *, approve=False):
    result = preview_trace(store, profile)
    if result["configured"]:
        return result
    if not approve:
        raise ProductError("trace_file_creation_approval_required")
    target = safe_path(result["path"])
    raw = (json.dumps(_payload(store, profile), indent=2, ensure_ascii=True) + "\n").encode("utf-8")
    try:
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise ProductError("existing_trace_file_preserved") from None
    with os.fdopen(descriptor, "wb") as output:
        restrict(target)
        output.write(raw)
        output.flush()
        os.fsync(output.fileno())
    return {**result, "configured": True, "changed": True}


def ensure_connection(store, profile, *, approve=False, interactive_ui=None):
    preview = preview_trace(store, profile)
    if not preview["configured"] and not approve and interactive_ui is not None:
        interactive_ui.preview(preview)
        approve = interactive_ui.confirm("Create the private reference-only TRACE connection file shown in the plan?")
    return configure_trace(store, profile, approve=approve)


@contextmanager
def diagnostic_environment(store, name):
    """Resolve a publisher reference only for its approved existing handoff."""
    try:
        profile = store.load(name) if name else None
    except Exception:
        # Diagnose retains its existing detailed invalid-profile error report.
        # A failed load never resolves credentials or starts any service here.
        profile = None
    if (profile is not None and profile.adapter == "trace" and profile.publication
            and safe_path(Path(profile.project) / LOCAL_FILE).is_file()):
        if not preview_trace(store, profile)["configured"]:
            raise ProductError("trace_file_creation_approval_required")
        with prepare_environment(store, profile):
            yield
    else:
        yield
