"""Private profiles, atomic generations and explicit new-database setup."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import secrets
import sys

from .models import Profile
from .safety import (ProductError, file_lock, private_directory, private_permissions,
                     profile_name, read_json, restrict, safe_path, write_json)


def default_home() -> Path:
    explicit = os.environ.get("OOMP_PROFILE_HOME")
    if explicit is not None:
        return safe_path(explicit)
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home()/"AppData/Local") / "OOMP"
    elif sys.platform == "darwin":
        base = Path.home()/"Library/Application Support/OOMP"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home()/".config") / "oomp"
    return safe_path(base / "profiles")


class ProfileStore:
    def __init__(self, home: str | Path | None = None):
        self.home = safe_path(home) if home is not None else default_home()

    def directory(self, name: str) -> Path:
        directory = safe_path(self.home / profile_name(name))
        if os.name == "nt":
            # Windows paths count UTF-16 code units, not Unicode code points.
            longest = str(directory) + "\\generations\\" + "0"*64 + "\\profile.json"
            if len(longest.encode("utf-16-le"))//2 >= 260:
                raise ProductError("profile_path_too_long_use_shorter_home")
        return directory

    def load(self, name: str) -> Profile:
        directory = self.directory(name)
        if not directory.exists():
            raise ProductError("profile_missing")
        active = read_json(directory / "active.json")
        identity = active.get("generation", "")
        if not re.fullmatch(r"[a-f0-9]{64}", identity):
            raise ProductError("invalid_profile_generation")
        profile = Profile.model_validate(read_json(directory / "generations" / identity / "profile.json"))
        if profile.name != name or profile.identity != identity:
            raise ProductError("invalid_profile_generation")
        return profile

    def generation(self, profile: Profile) -> Path:
        return safe_path(self.directory(profile.name) / "generations" / profile.identity)

    def environment(self, profile: Profile) -> dict[str, str]:
        if profile.secret_source == "file":
            values = read_json(self.directory(profile.name) / "secrets.json")
        else:
            values = {profile.reference(role): os.environ.get(profile.reference(role), "")
                      for role in profile.secret_roles()}
        selected = {profile.reference(role): values.get(profile.reference(role), "") for role in profile.secret_roles()}
        if (any(not isinstance(v, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43,256}", v) for v in selected.values())
                or len(set(selected.values())) != len(selected)):
            raise ProductError("credentials_missing_or_not_distinct")
        return selected

    def preview(self, profile: Profile) -> dict:
        directory = self.directory(profile.name)
        exists = (directory / "active.json").exists()
        if exists and self.load(profile.name) != profile:
            raise ProductError("profile_exists_use_config")
        files = ["active.json", "database-claim.json", "operation.lock",
                 "generations/<identity>/profile.json", "generations/<identity>/server.json",
                 "generations/<identity>/client.json", "generations/<identity>/writers.json"]
        if profile.secret_source == "file":
            files.append("secrets.json")
        return {"profile": profile.name, "action": "validate unchanged profile" if exists else "create profile",
                "files": [str(directory / n) for n in files],
                "temporary_setup_files": [] if exists else [str(directory / "pending-profile.json"), str(directory / ".p-<random>")],
                "existing_files_overwritten": [],
                "scope": {"tenant": profile.tenant, "namespace": profile.namespace, "principal": profile.principal},
                "file_action": "validate; only the operation lock is acquired" if exists else "create new private files",
                "new_database": None if exists else profile.database,
                "host_project_files_modified": [], "credentials": "references only; values never displayed",
                "services_started": False, "retention": "operator managed; no automatic backfill or deletion",
                "mode": profile.mode, "transport": profile.transport, "mind": profile.mind, "read_source": profile.read_source,
                "publication": profile.publication,
                "extraction": profile.extraction.model_dump(mode="json") if profile.extraction else {"mode": "legacy"},
                "extraction_route": "explicit literal-loopback only" if profile.extraction and profile.extraction.mode == "local-llm" else "offline"}

    def _generation(self, profile: Profile):
        directory = self.directory(profile.name)
        generations = private_directory(directory / "generations")
        target = private_directory(generations / profile.identity)
        write_json(target / "profile.json", profile.model_dump(mode="json"))
        write_json(target / "server.json", profile.server().model_dump(mode="json"))
        _, writers = profile.grants()
        write_json(target / "writers.json", {role: {
            "grant_id": g.grant_id, "principal_id": g.principal_id, "tenant_id": g.tenant_id,
            "namespace": g.namespace, "source_type": g.ingest_source_type.value,
            "source_system": g.ingest_source_system, "event_types": [e.value for e in g.ingest_event_types],
            "bearer_token_env": g.bearer_token_env, "approval_key_env": g.ingest_approval_key_env,
        } for role, g in writers.items()})
        if profile.transport == "stdio":
            client = {"mcpServers": {"oomp": {"command": str(Path(sys.executable).absolute()),
                "args": ["-m", "oomp", "connect", "--profile", profile.name, "--home", str(self.home)]}}}
        else:
            client = {"mcpServers": {"oomp": {"url": profile.server().endpoint,
                "headers": {"Authorization": "Bearer <HOST_RESOLVES:"+profile.reference("read_token")+">"}}}}
        write_json(target / "client.json", client)
        write_json(directory / "active.json", {"generation": profile.identity})

    def create(self, profile: Profile, *, create_credentials: bool = False) -> bool:
        private_directory(self.home)
        directory = self.directory(profile.name)
        private_directory(directory)
        with file_lock(directory / "operation.lock"):
            if (directory / "active.json").exists():
                current = self.load(profile.name)
                if current != profile:
                    raise ProductError("profile_exists_use_config")
                self.environment(current)
                return False
            if (directory / "pending-profile.json").exists():
                raise ProductError("setup_incomplete_use_resume")
            database = safe_path(profile.database)
            if database.exists():
                raise ProductError("existing_database_refused")
            if not database.parent.is_dir():
                raise ProductError("database_parent_missing")
            if not private_permissions(database.parent):
                raise ProductError("database_parent_private_permissions_required")
            if profile.secret_source == "file" and not create_credentials:
                raise ProductError("credential_creation_requires_confirmation")
            if (directory / "secrets.json").exists():
                raise ProductError("existing_credentials_preserved")
            if profile.secret_source == "environment":
                self.environment(profile)  # check before writing anything else
            write_json(directory / "pending-profile.json", profile.model_dump(mode="json"))
            if profile.secret_source == "file":
                write_json(directory / "secrets.json", {profile.reference(role): secrets.token_urlsafe(32)
                                                        for role in profile.secret_roles()})
            self._initialize_new(directory, database)
            self.environment(profile)
            self._generation(profile)
            (directory / "pending-profile.json").unlink()
            return True

    def _initialize_new(self, directory: Path, database: Path):
        from oomp.storage import SQLiteEventStore
        database = safe_path(database)
        # Explicit custom parent must exist: don't create or chmod an arbitrary
        # host directory tree. Defaults live in the already private profile folder.
        if not database.parent.is_dir():
            raise ProductError("database_parent_missing")
        if not private_permissions(database.parent):
            raise ProductError("database_parent_private_permissions_required")
        descriptor = os.open(database, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
        restrict(database)
        info = database.stat()
        write_json(directory / "database-claim.json", {"device": info.st_dev, "inode": info.st_ino})
        SQLiteEventStore(database).initialize()

    def resume(self, name: str):
        directory = self.directory(name)
        with file_lock(directory / "operation.lock"):
            profile = Profile.model_validate(read_json(directory / "pending-profile.json"))
            if profile.name != name:
                raise ProductError("invalid_profile_generation")
            database = safe_path(profile.database)
            from oomp.storage import SQLiteEventStore
            if not database.exists():
                self._initialize_new(directory, database)
            else:
                claim = read_json(directory / "database-claim.json")
                info = database.stat()
                if claim != {"device": info.st_dev, "inode": info.st_ino}:
                    raise ProductError("database_ownership_unverified")
                if info.st_size == 0:
                    SQLiteEventStore(database).initialize()
                elif not SQLiteEventStore(database).status().ready:
                    raise ProductError("incomplete_database_needs_review")
            self.environment(profile)  # never regenerate existing/missing secrets
            self._generation(profile)
            (directory / "pending-profile.json").unlink()
            return profile

    def update(self, profile: Profile):
        directory = self.directory(profile.name)
        with file_lock(directory / "operation.lock"):
            old = self.load(profile.name)
            # Changing identity/data/write authority requires another explicit
            # onboarding profile; it is not a silent config migration or rebind.
            mutable = {"port", "mind", "provider", "transport", "extraction"}
            before, after = old.model_dump(mode="json"), profile.model_dump(mode="json")
            if any(before[k] != after[k] for k in before.keys() - mutable):
                raise ProductError("identity_change_requires_new_profile")
            self.environment(profile)
            self._generation(profile)

    def host_environment(self, profile: Profile):
        values = self.environment(profile)
        if profile.adapter == "trace":
            values.update({"TRACE_OOMP_MODE": "retrieve_and_ingest" if profile.mode == "trusted-ingest" else "retrieve",
                "TRACE_OOMP_URL": profile.server().endpoint, "TRACE_OOMP_TRACE_ORIGIN": profile.host_origin,
                "TRACE_OOMP_OWNER_ID": profile.owner_id, "TRACE_OOMP_TENANT_ID": profile.tenant,
                "TRACE_OOMP_NAMESPACE": profile.namespace, "TRACE_OOMP_PRINCIPAL_ID": profile.principal,
                "TRACE_OOMP_SOURCE_SYSTEM": "trace-ai", "TRACE_OOMP_READ_TOKEN": values[profile.reference("read_token")],
                "TRACE_OOMP_OWNER_KEY": values[profile.reference("owner_key")],
                "TRACE_OOMP_WRITER_CONFIG": str(self.generation(profile) / "writers.json"),
                "TRACE_OOMP_RETRIEVAL_MODE": "lexical"})
        return values

    def exported_template(self, profile: Profile, output: Path | None, *, apply: bool = False):
        directory = self.directory(profile.name)
        template = read_json(self.generation(profile) / "client.json")
        raw = (json.dumps(template, indent=2, ensure_ascii=True) + "\n").encode()
        if output is None:
            return {"artifact": str(self.generation(profile) / "client.json"), "host_files_changed": [],
                    "note": "Connect the installed distribution; HTTP credential placeholders require host secret resolution."}
        output = safe_path(output)
        if (output.suffix.lower() != ".json" or output.name.lower() in {"package.json", "composer.json"}
                or any(n.lower() in {".git", "credentials", "secrets"} or n.startswith(".env") for n in output.parts)):
            raise ProductError("host_configuration_target_refused")
        if not output.parent.is_dir():
            raise ProductError("output_parent_missing")
        import hashlib
        receipt = {"path": str(output), "sha256": hashlib.sha256(raw).hexdigest()}
        if output.exists() and output.read_bytes() != raw:
            raise ProductError("existing_host_file_preserved")
        if apply:
            with file_lock(directory / "operation.lock"):
                receipt_file = directory / "integration-receipt.json"
                if receipt_file.exists() and read_json(receipt_file)["path"] != str(output):
                    raise ProductError("uninstall_previous_export_before_rebinding")
                if output.exists() and not (directory / "integration-receipt.json").exists():
                    return {"artifact": str(output), "operation": "preserve identical pre-existing unowned file", "applied": False}
                if output.exists():
                    owned = read_json(receipt_file)
                    info = safe_path(output).stat()
                    if (owned.get("device"), owned.get("inode"), owned.get("sha256")) != (
                            info.st_dev, info.st_ino, hashlib.sha256(output.read_bytes()).hexdigest()):
                        raise ProductError("modified_host_artifact_preserved")
                if not output.exists():
                    descriptor = os.open(output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                    with os.fdopen(descriptor, "wb") as handle:
                        handle.write(raw)
                    restrict(output)
                info = output.stat()
                receipt.update(device=info.st_dev, inode=info.st_ino)
                write_json(directory / "integration-receipt.json", receipt)
        return {"proposed_host_artifact": receipt["path"], "operation": "create new reference-only template", "applied": apply}

    def uninstall(self, name: str, *, apply: bool = False):
        directory = self.directory(name)
        receipt_path = directory / "integration-receipt.json"
        if not receipt_path.exists():
            return {"host_files_removed": [], "preserved": "profile, credentials, database and host application"}
        receipt = read_json(receipt_path)
        output = safe_path(receipt["path"])
        import hashlib
        def verify_owned():
            if output.exists():
                info = safe_path(output).stat()
                if ((info.st_dev, info.st_ino) != (receipt.get("device"), receipt.get("inode"))
                        or hashlib.sha256(output.read_bytes()).hexdigest() != receipt["sha256"]):
                    raise ProductError("modified_host_artifact_preserved")
        verify_owned()
        if apply:
            with file_lock(directory / "operation.lock"):
                verify_owned()
                if output.exists():
                    output.unlink()
                receipt_path.unlink()
        return {"owned_host_artifact": str(output), "operation": "remove only unchanged exported template",
                "applied": apply, "preserved": "profile, credentials, database and host application"}
