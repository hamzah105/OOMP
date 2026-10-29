"""Private local files and OS locks. Never execute repository-supplied commands."""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import stat
import tempfile


class ProductError(ValueError):
    """Only a static, safe code crosses the product CLI boundary."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def safe_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if not str(value).strip() or ".." in path.parts or any(ord(c) < 32 or ord(c) == 127 for c in str(value)):
        raise ProductError("unsafe_path")
    path = path.absolute()
    for part in (*reversed(path.parents), path):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ProductError("linked_path_refused")
        if part == path and stat.S_ISREG(info.st_mode) and info.st_nlink > 1:
            raise ProductError("linked_path_refused")
    return path


def profile_name(value: str) -> str:
    if (not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", value)
            or value.upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(10)), *(f"LPT{i}" for i in range(10))}):
        raise ProductError("invalid_profile_name")
    return value


def _windows_private_dacl(descriptor, user_sid, system_sid, adv) -> bool:
    """Compare binary trustees, independent of SDDL's domain-relative aliases."""
    import ctypes as c
    from ctypes import wintypes as w

    class ACL(c.Structure):
        _fields_ = [("revision", w.BYTE), ("reserved", w.BYTE),
                    ("size", w.WORD), ("count", w.WORD), ("reserved2", w.WORD)]

    adv.GetSecurityDescriptorControl.argtypes = [c.c_void_p, c.POINTER(w.WORD), c.POINTER(w.DWORD)]
    adv.GetSecurityDescriptorDacl.argtypes = [c.c_void_p, c.POINTER(w.BOOL), c.POINTER(c.c_void_p), c.POINTER(w.BOOL)]
    adv.GetAce.argtypes = [c.c_void_p, w.DWORD, c.POINTER(c.c_void_p)]
    adv.IsValidSid.argtypes = [c.c_void_p]
    adv.GetLengthSid.argtypes = [c.c_void_p]
    adv.GetLengthSid.restype = w.DWORD
    adv.EqualSid.argtypes = [c.c_void_p, c.c_void_p]
    control, revision = w.WORD(), w.DWORD()
    present, defaulted, acl = w.BOOL(), w.BOOL(), c.c_void_p()
    if not adv.GetSecurityDescriptorControl(descriptor, c.byref(control), c.byref(revision)) or not control.value & 0x1000:
        return False
    if not adv.GetSecurityDescriptorDacl(descriptor, c.byref(present), c.byref(acl), c.byref(defaulted)) or not present.value or not acl.value:
        return False
    header = c.cast(acl, c.POINTER(ACL)).contents
    if not header.count or header.size < c.sizeof(ACL):
        return False
    user_full_access = False
    for index in range(header.count):
        ace = c.c_void_p()
        if not adv.GetAce(acl, index, c.byref(ace)) or not ace.value:
            return False
        offset = ace.value - acl.value
        if offset < c.sizeof(ACL) or offset + 8 > header.size:
            return False
        ace_type, flags, length = c.c_ubyte.from_address(ace.value).value, c.c_ubyte.from_address(ace.value + 1).value, c.c_ushort.from_address(ace.value + 2).value
        # Only effective, explicit allow ACEs; OI/CI are the only allowed flags.
        if ace_type != 0 or flags & ~3 or length < 16 or offset + length > header.size:
            return False
        trustee = ace.value + 8
        if not adv.IsValidSid(trustee) or adv.GetLengthSid(trustee) > length - 8:
            return False
        own = bool(adv.EqualSid(trustee, user_sid))
        if not own and not adv.EqualSid(trustee, system_sid):
            return False
        mask = c.c_uint32.from_address(ace.value + 4).value
        user_full_access |= own and mask & 0x1F01FF == 0x1F01FF
    return user_full_access


def _windows_security(path: Path, *, set_private: bool) -> bool:
    # Explicit current-user + SYSTEM DACL, no inherited grants. No shell/username
    # interpolation, ACL changes to ancestors, or claim that chmod secures Windows.
    import ctypes as c
    from ctypes import wintypes as w
    adv = c.WinDLL("advapi32", use_last_error=True)
    kernel = c.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = w.HANDLE
    adv.OpenProcessToken.argtypes = [w.HANDLE, w.DWORD, c.POINTER(w.HANDLE)]
    adv.GetTokenInformation.argtypes = [w.HANDLE, c.c_int, c.c_void_p, w.DWORD, c.POINTER(w.DWORD)]
    adv.ConvertSidToStringSidW.argtypes = [c.c_void_p, c.POINTER(w.LPWSTR)]
    adv.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [w.LPCWSTR, w.DWORD, c.POINTER(c.c_void_p), c.POINTER(w.DWORD)]
    adv.SetFileSecurityW.argtypes = [w.LPCWSTR, w.DWORD, c.c_void_p]
    adv.GetFileSecurityW.argtypes = [w.LPCWSTR, w.DWORD, c.c_void_p, w.DWORD, c.POINTER(w.DWORD)]
    adv.ConvertStringSidToSidW.argtypes = [w.LPCWSTR, c.POINTER(c.c_void_p)]
    kernel.LocalFree.argtypes = [c.c_void_p]
    kernel.CloseHandle.argtypes = [w.HANDLE]
    token = w.HANDLE()
    sid_text = w.LPWSTR()
    descriptor = c.c_void_p()
    system_sid = c.c_void_p()
    try:
        if not adv.OpenProcessToken(kernel.GetCurrentProcess(), 8, c.byref(token)):
            return False
        size = w.DWORD()
        adv.GetTokenInformation(token, 1, None, 0, c.byref(size))
        token_buffer = c.create_string_buffer(size.value)
        if not adv.GetTokenInformation(token, 1, token_buffer, size, c.byref(size)):
            return False
        sid = c.cast(token_buffer, c.POINTER(c.c_void_p))[0]
        if not adv.ConvertSidToStringSidW(sid, c.byref(sid_text)):
            return False
        if set_private:
            flags = "OICI" if path.is_dir() else ""
            sddl = f"D:P(A;{flags};FA;;;{sid_text.value})(A;{flags};FA;;;SY)"
            if not adv.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, c.byref(descriptor), None):
                return False
            return bool(adv.SetFileSecurityW(str(path), 0x80000004, descriptor))
        adv.GetFileSecurityW(str(path), 4, None, 0, c.byref(size))
        buffer = c.create_string_buffer(size.value)
        if not adv.GetFileSecurityW(str(path), 4, buffer, size, c.byref(size)):
            return False
        if not adv.ConvertStringSidToSidW("S-1-5-18", c.byref(system_sid)):
            return False
        return _windows_private_dacl(buffer, sid, system_sid, adv)
    finally:
        for pointer in (sid_text, descriptor, system_sid):
            if pointer:
                kernel.LocalFree(c.cast(pointer, c.c_void_p))
        if token:
            kernel.CloseHandle(token)


def private_permissions(path: Path) -> bool:
    path = safe_path(path)
    if os.name == "nt":
        return _windows_security(path, set_private=False)
    return path.stat().st_uid == os.getuid() and not path.stat().st_mode & 0o077


def restrict(path: Path) -> None:
    path = safe_path(path)
    if os.name == "nt":
        if not _windows_security(path, set_private=True):
            raise ProductError("private_permissions_failed")
    else:
        path.chmod(0o700 if path.is_dir() else 0o600)


def private_directory(path: Path) -> Path:
    path = safe_path(path)
    if not path.exists():
        path.mkdir(parents=True, mode=0o700)
        restrict(path)
    if not path.is_dir() or not private_permissions(path):
        raise ProductError("private_permissions_required")
    return path


def read_json(path: Path, *, limit: int = 65536):
    path = safe_path(path)
    if not private_permissions(path):
        raise ProductError("private_permissions_required")
    with path.open("rb") as handle:
        raw = handle.read(limit + 1)
    if len(raw) > limit:
        raise ProductError("file_limit")
    return json.loads(raw.decode("utf-8"))


def write_json(path: Path, value) -> None:
    path = safe_path(path)
    private_directory(path.parent)
    raw = (json.dumps(value, ensure_ascii=True, indent=2, allow_nan=False) + "\n").encode()
    # Keep atomic temporary names no longer than the destination filenames.
    # Deep Windows profile generations otherwise hit MAX_PATH before commit.
    descriptor, name = tempfile.mkstemp(prefix=".p-", dir=path.parent)
    temporary = Path(name)
    try:
        os.close(descriptor)
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


@contextmanager
def file_lock(path: Path):
    """Held handle, not PID-file ownership. The OS releases it on crashes."""
    path = safe_path(path)
    private_directory(path.parent)
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    handle = os.fdopen(descriptor, "r+b")
    locked = False
    try:
        restrict(path)
        if path.stat().st_size == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
        except OSError:
            raise ProductError("profile_busy") from None
        yield
    finally:
        if locked:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_UN)
        handle.close()
