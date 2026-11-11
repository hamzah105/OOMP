"""Explicit stopped-only host-code approval; never opens a memory database.

A signed private journal retains both metadata states. An interrupted switch
fails closed until an explicit rollback, with the old source restored, succeeds.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import tempfile
from urllib.parse import urlsplit

from . import handoff, lifecycle, start
from .discovery import project_fingerprint
from .models import Profile
from .safety import ProductError, private_directory, read_json, restrict, safe_path, write_json

PENDING = "approval-pending.json"
GENERATION_FILES = ("profile.json", "server.json", "writers.json", "client.json")


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _raw(value):
    return (json.dumps(value, ensure_ascii=True, indent=2, allow_nan=False) + "\n").encode()


def _snapshot(path, *, optional=False):
    path = safe_path(path)
    if optional and not path.exists():
        return None
    before = path.stat()
    read_json(path)  # bounded JSON, no links, and private permissions required
    raw = path.read_bytes()
    after = path.stat()
    identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    if identity(before) != identity(after) or len(raw) > 65536:
        raise ProductError("approval_input_changed")
    return {"raw": base64.b64encode(raw).decode(), "sha256": hashlib.sha256(raw).hexdigest()}


def _document(snapshot):
    raw = base64.b64decode(snapshot["raw"], validate=True)
    if hashlib.sha256(raw).hexdigest() != snapshot["sha256"]:
        raise ProductError("invalid_approval_journal")
    return raw


def _encoded(value):
    raw = _raw(value)
    return {"raw": base64.b64encode(raw).decode(), "sha256": hashlib.sha256(raw).hexdigest()}


def _write(path, snapshot):
    """Atomic private replacement retaining the exact approved JSON bytes."""
    path = safe_path(path)
    raw = _document(snapshot)
    if not path.parent.is_dir():
        raise ProductError("approval_parent_missing")
    fd, name = tempfile.mkstemp(prefix=".p-", dir=path.parent)
    temporary = Path(name)
    try:
        os.close(fd)
        restrict(temporary)
        with temporary.open("wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        safe_path(path)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _targets(store, profile):
    return {"active": store.directory(profile.name)/"active.json",
            "handoff": safe_path(Path(profile.project)/handoff.LOCAL_FILE),
            "selection": start.selection_path()}


def _capture(paths):
    return {key: _snapshot(path, optional=key == "selection") for key, path in paths.items()}


def _generation(store, identity, name):
    if not isinstance(identity, str) or not re.fullmatch(r"[a-f0-9]{64}", identity):
        raise ProductError("invalid_approval_journal")
    root = safe_path(store.directory(name)/"generations"/identity)
    profile = Profile.model_validate(read_json(root/"profile.json"))
    if profile.name != name or profile.identity != identity:
        raise ProductError("invalid_profile_generation")
    return profile, {n: _snapshot(root/n) for n in GENERATION_FILES}


def _stopped(store, profile):
    runtime = store.directory(profile.name)/"runtime.json"
    if runtime.exists():
        state, _ = lifecycle._runtime_snapshot(runtime, profile, allow_stopped=True)
        if not state["stopped"] or not lifecycle._process_gone(state["pid"]):
            raise ProductError("approval_requires_stopped_services")
        if not lifecycle.port_available(state["port"]):
            raise ProductError("approval_requires_free_ports")
    origin = urlsplit(profile.host_origin)
    for port in {profile.port, origin.port or (443 if origin.scheme == "https" else 80)}:
        if not lifecycle.port_available(port):
            raise ProductError("approval_requires_free_ports")


@contextmanager
def _locks(store, name):
    directory = store.directory(name)
    with lifecycle._checked_lock(directory/"launch.lock"):
        with lifecycle._checked_lock(directory/"operation.lock"):
            with lifecycle._checked_lock(start.selection_path().with_name("start-selection.lock")):
                yield


def _key(store, profile):
    return store.environment(profile)[profile.reference("owner_key")].encode("ascii")


def _sign(body, key):
    return {**body, "signature": hmac.new(key, _canonical(body), hashlib.sha256).hexdigest()}


def _journal(path, body, key):
    record = _sign(body, key)
    # Every prepared journal must remain readable by the bounded recovery API,
    # including the slightly longer committed/rolled_back state labels.
    if len(_raw(record)) + 32 > 65536:
        raise ProductError("approval_journal_too_large")
    write_json(path, record)


def _prepare(store, name):
    old = store.load(name)
    if old.adapter != "trace" or not old.publication or old.secret_source != "file":
        raise ProductError("approval_requires_existing_trace_publisher")
    _stopped(store, old)
    handoff.preview_trace(store, old)  # existing signed handoff must already agree
    fingerprint = project_fingerprint(old.project)
    if set(fingerprint) != set(old.approved_project):
        raise ProductError("approval_source_inventory_changed")
    if fingerprint == old.approved_project:
        raise ProductError("approval_source_unchanged")
    new = Profile.model_validate({**old.model_dump(mode="json"), "approved_project": fingerprint})
    _, generation = _generation(store, old.identity, name)
    paths = _targets(store, old)
    before = _capture(paths)
    pin = json.loads(_document(before["selection"])) if before["selection"] else None
    if pin is not None and not isinstance(pin, dict):
        raise ProductError("invalid_start_selection")
    if pin and pin.get("home") == str(store.home) and pin.get("profile") == name:
        if pin != start._binding(store, old):
            raise ProductError("selected_profile_authority_changed")
    secrets_hash = _snapshot(store.directory(name)/"secrets.json")["sha256"]
    plan = {"format": "oomp.project-approval.v1", "profile": name,
            "from_generation": old.identity, "to_generation": new.identity,
            "changed_sources": {n: {"before": old.approved_project[n], "after": fingerprint[n]}
                                for n in fingerprint if fingerprint[n] != old.approved_project[n]},
            "update_saved_default": pin == start._binding(store, old),
            "credentials_rotated": False, "database_access": False}
    token = hashlib.sha256(_canonical({"plan": plan, "before": before,
        "generation": generation, "credentials_sha256": secrets_hash})).hexdigest()
    return old, new, generation, paths, before, secrets_hash, {**plan, "plan_sha256": token}


def refresh(store, name, *, expected_plan=None):
    """Preview unless an exact reviewed plan digest is explicitly supplied."""
    with _locks(store, name):
        old, new, generation, paths, before, secrets_hash, plan = _prepare(store, name)
        if expected_plan is None:
            return plan
        if not hmac.compare_digest(expected_plan, plan["plan_sha256"]):
            raise ProductError("approval_plan_changed")
        target = safe_path(store.generation(new))
        expected_generation = {**generation, "profile.json": _encoded(new.model_dump(mode="json"))}
        if target.exists():
            if _generation(store, new.identity, name)[1] != expected_generation:
                raise ProductError("approval_generation_changed")
        else:
            private_directory(target)
            for filename, snapshot in expected_generation.items():
                _write(target/filename, snapshot)
        after = {**before, "active": _encoded({"generation": new.identity}),
                 "handoff": _encoded(handoff._generation_payload(store, new))}
        if plan["update_saved_default"]:
            after["selection"] = _encoded(start._binding(store, new))
        # Recheck the whole plan, including source hashes, after preparation.
        if _prepare(store, name)[-1] != plan:
            raise ProductError("approval_input_changed")
        transaction = "approval-" + secrets.token_hex(12)
        history = private_directory(store.directory(name)/"history")/transaction
        history.mkdir(mode=0o700)  # exclusive: never replace a prior approval record
        restrict(history)
        body = {"format": "oomp.approval-journal.v1", "profile": name, "home": str(store.home),
                "transaction": transaction, "old_generation": old.identity, "new_generation": new.identity,
                "before": before, "after": after, "credentials_sha256": secrets_hash,
                "old_files": generation, "new_files": expected_generation, "state": "prepared",
                "created_at": datetime.now(timezone.utc).isoformat()}
        key = _key(store, old)
        _journal(history/"transaction.json", body, key)
        write_json(store.directory(name)/PENDING, {"transaction": transaction})
        _switch(store, new, paths, before, after)
        if (_snapshot(store.directory(name)/"secrets.json")["sha256"] != secrets_hash
                or _generation(store, old.identity, name)[1] != generation
                or _generation(store, new.identity, name)[1] != expected_generation):
            raise ProductError("approval_preserved_input_changed")
        body["state"] = "committed"
        _journal(history/"transaction.json", body, key)
        safe_path(store.directory(name)/PENDING).unlink()
        return {**plan, "applied": True, "transaction": transaction}


def _switch(store, profile, paths, before, after):
    if _capture(paths) != before:
        raise ProductError("approval_input_changed")
    # Invalidate TRACE's connection before switching the other metadata. A crash
    # leaves OOMP blocked by PENDING and TRACE blocked by a mismatched handoff.
    transition = _encoded({"format": "oomp.approval.pending.v1"})
    _write(paths["handoff"], transition)
    if _snapshot(paths["active"]) != before["active"]:
        raise ProductError("approval_input_changed")
    _write(paths["active"], after["active"])
    if before["selection"] != after["selection"]:
        if _snapshot(paths["selection"], optional=True) != before["selection"]:
            raise ProductError("approval_input_changed")
        _write(paths["selection"], after["selection"])
    if project_fingerprint(profile.project) != profile.approved_project:
        raise ProductError("approval_source_changed")
    if _snapshot(paths["handoff"]) != transition:
        raise ProductError("approval_input_changed")
    _write(paths["handoff"], after["handoff"])
    if _capture(paths) != after:
        raise ProductError("approval_input_changed")


def rollback(store, name, transaction, *, expected_plan=None):
    """Restore a signed bundle only with old source and recognized metadata."""
    if not re.fullmatch(r"approval-[a-f0-9]{24}", transaction):
        raise ProductError("invalid_approval_transaction")
    with _locks(store, name):
        journal = safe_path(store.directory(name)/"history"/transaction/"transaction.json")
        record = read_json(journal)
        body = {k: v for k, v in record.items() if k != "signature"}
        old, old_files = _generation(store, body.get("old_generation"), name)
        key = _key(store, old)
        if (record != _sign(body, key) or body.get("format") != "oomp.approval-journal.v1"
                or body.get("profile") != name or body.get("home") != str(store.home)
                or body.get("transaction") != transaction or body.get("state") not in {"prepared", "committed"}):
            raise ProductError("invalid_approval_journal")
        new, new_files = _generation(store, body["new_generation"], name)
        if (old_files != body["old_files"] or new_files != body["new_files"]
                or {**old.model_dump(mode="json"), "approved_project": new.approved_project} != new.model_dump(mode="json")
                or _snapshot(store.directory(name)/"secrets.json")["sha256"] != body["credentials_sha256"]):
            raise ProductError("approval_preserved_input_changed")
        _stopped(store, new)
        if project_fingerprint(old.project) != old.approved_project:
            raise ProductError("approval_restore_old_source_first")
        pending = store.directory(name)/PENDING
        if pending.exists() and read_json(pending) != {"transaction": transaction}:
            raise ProductError("approval_other_transaction_pending")
        paths = _targets(store, old)
        current = _capture(paths)
        transition = _encoded({"format": "oomp.approval.pending.v1"})
        for field in current:
            allowed = (body["before"][field], body["after"][field])
            if field == "handoff" and pending.exists():
                allowed += (transition,)
            if current[field] not in allowed:
                raise ProductError("approval_metadata_changed")
        if not pending.exists() and current != body["after"]:
            raise ProductError("approval_metadata_changed")
        plan = {"operation": "rollback", "transaction": transaction, "profile": name,
                "from_generation": new.identity, "to_generation": old.identity,
                "credentials_rotated": False, "database_access": False}
        plan["plan_sha256"] = hashlib.sha256(_canonical({"plan": plan, "current": current,
            "journal_sha256": _snapshot(journal)["sha256"]})).hexdigest()
        if expected_plan is None:
            return plan
        if not hmac.compare_digest(expected_plan, plan["plan_sha256"]):
            raise ProductError("approval_plan_changed")
        write_json(pending, {"transaction": transaction})
        _switch(store, old, paths, current, body["before"])
        body["state"] = "rolled_back"
        _journal(journal, body, key)
        safe_path(pending).unlink()
        return {**plan, "applied": True}
