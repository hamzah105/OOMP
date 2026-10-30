"""P1 recovery paths and real Windows DACL checks; no production files."""
from __future__ import annotations

import os
from pathlib import Path
import sys

import pytest

from oomp.cli import main
from oomp.product.safety import ProductError, safe_path
from oomp.product.ui import UI


def wizard(monkeypatch, tmp_path, adapter, paths, actions=()):
    calls, previews = [], []
    paths, actions = iter(paths), iter(actions)
    adapters = iter(adapter)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    def choose(self, label, choices, default=None):
        calls.append(label)
        if label.startswith("Connection type"):
            return next(adapters)
        if label == "Project discovery recovery":
            return next(actions)
        return default or choices[0]
    def text(self, label, default=""):
        calls.append(label)
        return str(next(paths)) if label == "Project directory" else default
    monkeypatch.setattr(UI, "choose", choose)
    monkeypatch.setattr(UI, "text", text)
    monkeypatch.setattr(UI, "confirm", lambda *_: False)
    monkeypatch.setattr(UI, "preview", lambda self, value: previews.append(value))
    home = tmp_path / "profiles"
    return home, calls, previews


@pytest.mark.parametrize("adapter", ["trace", "generic-mcp"])
def test_project_is_requested_and_discovered_before_authority(tmp_path, monkeypatch, adapter):
    from oomp.product.discovery import TRACE_FILES
    project = tmp_path / "synthetic project"
    project.mkdir()
    if adapter == "trace":
        for name in TRACE_FILES:
            file = project / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text("# synthetic\n")
    (project / "requirements.txt").write_text("fastapi\n")
    home, calls, previews = wizard(monkeypatch, tmp_path, [adapter], [project])
    assert main(["onboard", "--home", str(home), "--owner-id", "synthetic", "--plain"]) == 1
    assert calls.index("Project directory") < calls.index("Memory authority")
    discovery = next(p["project_discovery"] for p in previews if "project_discovery" in p)
    assert discovery["frameworks"] and discovery["languages"] == ["Python"]
    assert not home.exists()


@pytest.mark.parametrize("bad", ["missing", "incompatible"])
def test_bad_trace_project_can_cancel_before_files(tmp_path, monkeypatch, capsys, bad):
    project = tmp_path / bad
    if bad == "incompatible":
        project.mkdir()
    home, calls, _ = wizard(monkeypatch, tmp_path, ["trace"], [project], ["Cancel"])
    assert main(["onboard", "--home", str(home), "--plain"]) == 1
    assert "cancelled_no_changes" in capsys.readouterr().out
    assert "Memory authority" not in calls and not home.exists()


def test_discovery_can_return_to_standalone_without_project(tmp_path, monkeypatch):
    home, calls, _ = wizard(monkeypatch, tmp_path, ["trace", "standalone"], [tmp_path / "absent"], ["Back to connection type"])
    assert main(["onboard", "--home", str(home), "--plain"]) == 1
    assert calls.count("Project directory") == 1
    assert not home.exists()


def test_discovery_can_retry_an_existing_directory(tmp_path, monkeypatch):
    home, calls, previews = wizard(monkeypatch, tmp_path, ["generic-mcp"], [tmp_path / "absent", tmp_path], ["Choose another directory"])
    assert main(["onboard", "--home", str(home), "--plain"]) == 1
    assert calls.count("Project directory") == 2
    assert any("project_discovery" in item for item in previews)
    assert not home.exists()


def test_host_executable_symlink_remains_refused(tmp_path):
    target = tmp_path / "real-python"
    target.write_text("synthetic, never executable")
    link = tmp_path / "linked-python"
    try:
        link.symlink_to(target)
    except OSError:
        # Non-admin Windows may prohibit creating symlinks. Exercise the actual
        # POSIX setup-python symlink in Linux CI; no production exemption.
        if os.name == "nt":
            return
        raise
    with pytest.raises(ProductError, match="linked_path_refused"):
        safe_path(link)
    assert safe_path(link.resolve()) == target


@pytest.mark.skipif(os.name != "nt", reason="native Windows security descriptor API")
@pytest.mark.parametrize("sddl,accepted", [
    ("D:P(A;;FA;;;LA)(A;;FA;;;SY)", True),
    ("D:P(A;;FA;;;LA)(A;;FA;;;S-1-5-18)", True),
    ("D:P(A;;FA;;;LA)(A;;FR;;;WD)", False),
    ("D:(A;;FA;;;LA)", False),
    ("D:P", False),
    ("D:PNO_ACCESS_CONTROL", False),
    ("D:P(A;IO;FA;;;LA)", False),
    ("D:P(D;;FR;;;LA)(A;;FA;;;LA)", False),
    ("D:P(A;;FR;;;LA)", False),
])
def test_binary_dacl_checks_aliases_and_rejects_unauthorized_grants(sddl, accepted):
    import ctypes as c
    from ctypes import wintypes as w
    from oomp.product.safety import _windows_private_dacl
    adv, kernel = c.WinDLL("advapi32"), c.WinDLL("kernel32")
    adv.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [w.LPCWSTR, w.DWORD, c.POINTER(c.c_void_p), c.POINTER(w.DWORD)]
    adv.ConvertStringSidToSidW.argtypes = [w.LPCWSTR, c.POINTER(c.c_void_p)]
    kernel.LocalFree.argtypes = [c.c_void_p]
    descriptor, admin, system = c.c_void_p(), c.c_void_p(), c.c_void_p()
    try:
        assert adv.ConvertStringSidToSidW("LA", c.byref(admin))
        assert adv.ConvertStringSidToSidW("S-1-5-18", c.byref(system))
        assert adv.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, c.byref(descriptor), None)
        assert _windows_private_dacl(descriptor, admin, system, adv) is accepted
    finally:
        for pointer in (descriptor, admin, system):
            if pointer:
                kernel.LocalFree(pointer)
