"""Stage 7 configuration/CLI fail-closed behavior, including SDK-free core use."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from pydantic import ValidationError

from oomp.cli import main
from oomp.mcp.configuration import Grant, ServerConfiguration, load_configuration
from oomp.mcp.authorization import GrantResolver


def grant(**values):
    return Grant(grant_id="local", principal_id="host", tenant_id="tenant", namespace="personal", **values)


@pytest.mark.parametrize("patch", [
    {"host": "0.0.0.0"}, {"host": "localhost"}, {"host": "192.168.1.1"},
    {"port": True}, {"max_concurrent_calls": 17}, {"max_request_bytes": 1048577},
    {"allowed_origins": ["*"]}, {"allowed_origins": ["http://example.com"]},
    {"allowed_origins": ["http://127.0.0.1:8765/path"]},
    {"allowed_origins": ["http://user@127.0.0.1:8765"]},
])
def test_unsafe_network_or_resource_configuration_is_rejected(patch):
    with pytest.raises(ValidationError):
        ServerConfiguration(database="existing.sqlite3", stdio_grant=grant(), **patch)


def test_no_implicit_authority_or_http_credential_fallback():
    with pytest.raises(ValidationError):
        ServerConfiguration(database="existing.sqlite3")
    with pytest.raises(ValidationError):
        ServerConfiguration(database="existing.sqlite3", transport="streamable-http", stdio_grant=grant())
    with pytest.raises(ValidationError):
        Grant(grant_id="x", principal_id="host", tenant_id="tenant", namespace="personal", capabilities=())


def test_server_generated_config_and_windows_client_json_roundtrip(tmp_path, capsys):
    path = tmp_path / "config directory" / "server config.json"
    database = tmp_path / "database folder" / "memory.sqlite3"
    assert main(["mcp", "config", "--format", "server", "--config", str(path),
                 "--db", str(database), "--tenant", "tenant", "--namespace", "personal",
                 "--principal", "trusted-host"]) == 0
    config = json.loads(capsys.readouterr().out)
    parsed = ServerConfiguration.model_validate(config)
    assert parsed.profile == "read-only"
    assert parsed.stdio_grant.principal_id == "trusted-host"
    assert not path.exists() and not database.exists()
    assert main(["mcp", "config", "--config", str(path)]) == 0
    host = json.loads(capsys.readouterr().out)["mcpServers"]["oomp"]
    assert host["command"] == str(Path(sys.executable).resolve())
    assert host["args"][-3:] == [str(path.resolve()), "--transport", "stdio"]
    assert "env" not in host and "headers" not in host


def test_http_config_prints_placeholders_without_reading_secrets(tmp_path, capsys, monkeypatch):
    path = tmp_path / "http.json"
    monkeypatch.setenv("OOMP_MCP_TOKEN", "PRIVATE-SECRET-MUST-NOT-PRINT")
    assert main(["mcp", "config", "--format", "server", "--transport", "streamable-http",
                 "--config", str(path), "--db", str(tmp_path/"absent.sqlite3"),
                 "--tenant", "tenant", "--namespace", "personal", "--principal", "host"]) == 0
    config = json.loads(capsys.readouterr().out)
    path.write_text(json.dumps(config), encoding="utf-8")
    assert main(["mcp", "config", "--transport", "streamable-http", "--config", str(path)]) == 0
    output = capsys.readouterr().out
    assert "PRIVATE-SECRET" not in output
    assert json.loads(output)["mcpServers"]["oomp"]["headers"]["Authorization"] == "Bearer <HOST_SUPPLIED_SECRET>"


def test_missing_config_and_database_fail_without_creation(tmp_path, capsys, monkeypatch):
    pytest.importorskip("mcp")
    monkeypatch.delenv("OOMP_MCP_CONFIG", raising=False)
    assert main(["mcp", "check"]) == 1
    path = tmp_path / "private config.json"
    config = ServerConfiguration(database=str(tmp_path/"missing dir"/"private-db.sqlite3"),
                                 stdio_grant=grant())
    path.write_text(config.model_dump_json(), encoding="utf-8")
    for operation in ("serve", "check"):
        assert main(["mcp", operation, "--config", str(path)]) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "private" not in output.err.lower()
    assert not (tmp_path/"missing dir").exists()


def test_relative_database_config_and_explicit_transport_validation(tmp_path):
    path = tmp_path / "server.json"
    path.write_text(ServerConfiguration(database="relative db.sqlite3", stdio_grant=grant()).model_dump_json(),
                    encoding="utf-8")
    assert load_configuration(str(path)).database == str(tmp_path/"relative db.sqlite3")
    with pytest.raises(ValidationError):
        load_configuration(str(path), "streamable-http")


def test_missing_weak_duplicate_and_shared_host_credentials_fail_closed():
    from oomp.mcp.configuration import Grant
    base = grant(bearer_token_env="A")
    config = ServerConfiguration(database="absent", transport="streamable-http", http_grants=(base,))
    for environment in ({}, {"A": "short"}):
        with pytest.raises(ValueError):
            GrantResolver(config, environ=environment)
    second = Grant.model_validate({**base.model_dump(mode="json"), "grant_id": "second", "bearer_token_env": "B"})
    config = ServerConfiguration(database="absent", transport="streamable-http", http_grants=(base, second))
    with pytest.raises(ValueError):
        GrantResolver(config, environ={"A": "A"*43, "B": "A"*43})
    privileged = Grant.model_validate({
        **base.model_dump(mode="json"), "capabilities": ["read", "ingest"],
        "ingest_approval_key_env": "KEY", "ingest_source_type": "user",
        "ingest_source_system": "trusted-host", "ingest_event_types": ["user_message"],
    })
    with pytest.raises(ValidationError):
        ServerConfiguration(database="absent", stdio_grant=privileged)
    config = ServerConfiguration(database="absent", profile="trusted-ingest",
        transport="streamable-http", http_grants=(privileged,))
    with pytest.raises(ValueError):
        GrantResolver(config, environ={"A": "A"*43, "KEY": "A"*43})


def test_core_and_doctor_work_when_optional_sdk_imports_are_blocked():
    script = """
import importlib.abc, sys
class BlockMCP(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'mcp' or fullname.startswith('mcp.'):
            raise ModuleNotFoundError('optional SDK deliberately blocked')
sys.meta_path.insert(0, BlockMCP())
import oomp.domain.models, oomp.storage, oomp.retrieval.engine, oomp.mind.worker
from oomp.cli import main
assert main(['doctor']) == 0
assert main(['mcp', '--help']) == 0
"""
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr


def test_oversized_and_extra_configuration_never_prints_input(tmp_path, capsys):
    file = tmp_path / "oversized.json"
    file.write_text("PRIVATE-INPUT" * 7000, encoding="utf-8")
    assert main(["mcp", "check", "--config", str(file)]) == 1
    output = capsys.readouterr()
    assert "PRIVATE-INPUT" not in output.err
    file.write_text('{"database":"PRIVATE-DATABASE","unknown":"PRIVATE-INPUT"}', encoding="utf-8")
    assert main(["mcp", "config", "--format", "server", "--config", str(file)]) == 1
    assert "PRIVATE-" not in capsys.readouterr().err