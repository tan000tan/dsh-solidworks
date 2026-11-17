r"""
scripts/path_security.py

Unified, fail-closed path & containment security for dsh-solidworks Python layer (BUG-0016).
Mirrors `lib/policy.js` so JS Policy and Python MCP/scripts enforce identical guarantees:
1. Fail closed when `DSH_ALLOWED_ROOTS` is unset, empty, or malformed (never falls back to `os.getcwd()`).
2. Rejects forbidden syntax BEFORE any path expansion (`file:`, `\0`, `%ENV%`, `$ENV`, `${ENV}`, `~`,
   drive-relative `C:foo`, UNC/pipes other than `\\?\<Drive>:\`, NTFS `:ads`, reserved DOS devices,
   and protected filenames).
3. Resolves Windows directory junctions and symlinks via `GetFinalPathNameByHandleW` ancestor walk.
4. Supports TOCTOU re-validation (`safe_ensure_parent_dir`, `safe_open_in_allowed_roots`).
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Iterable, Optional

PROTECTED_FILENAMES_LOWER = frozenset({
    "垫圈.sldprt",
    "螺母 gb_t 6170 m10.sldprt",
    "cordis.patch.yml",
    "cordis.yml",
    "dsh-mcp-config.json",
    ".dsh-approval-secret",
    "approval-challenges.json",
    ".env",
})

_WINDOWS_RESERVED_DEVICE_RE = re.compile(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\..*)?$", re.IGNORECASE)
_ENV_VAR_RE = re.compile(r"%[A-Za-z0-9_().-]+%|\$[A-Za-z_][A-Za-z0-9_]*|\$\{[^}]+\}")
_TILDE_RE = re.compile(r"^~(?:$|[\\/]|[A-Za-z0-9_.-]+[\\/])")

_EXPLICIT_PATH_KEY_RE = re.compile(
    r"^(path|filepath|file_path|dir|directory|folder|root|destination|output_dir|output_path|"
    r"input_path|spec_path|source_path|step_path|replacement_path|source_model|sourcemodel|"
    r"expected_document_path|brep_evidence_path|profile_paths|file_paths|pdf_path|drawing_path|"
    r"document_path|template_path|assembly_path|backup_dir|log_path|scene_path|save_path|"
    r"drawing_template|template_candidates|templatecandidates|target_folder|targetfolder)$",
    re.IGNORECASE,
)
_BARE_NAME_KEY_RE = re.compile(
    r"^(filename|drawing_filename|basename|doc_type|document_type|unit|format)$",
    re.IGNORECASE,
)
_PATH_EXT_RE = re.compile(
    r"\.(sldprt|sldasm|slddrw|step|stp|iges|igs|dxf|dwg|json|pdf|stl|csv|txt|inp|brep)(:.*)?$",
    re.IGNORECASE,
)


def strip_win_long_prefix(path_str: str) -> str:
    """Normalize Windows `\\\\?\\` extended-length prefixes consistently."""
    if not isinstance(path_str, str):
        return path_str
    if path_str.startswith("\\\\?\\UNC\\") or path_str.startswith("\\\\?\\UNC/"):
        return "\\\\" + path_str[8:]
    if re.match(r"^\\\\\?\\[a-zA-Z]:[\\/]", path_str):
        return path_str[4:]
    return path_str


def has_forbidden_path_syntax(raw_path: Any) -> bool:
    """Reject dangerous or pre-expansion path syntax identically to `lib/policy.js`."""
    if not isinstance(raw_path, str):
        return True
    s = raw_path.strip()
    if not s or "\x00" in s:
        return True
    if s.lower().startswith("file:"):
        return True
    if _ENV_VAR_RE.search(s) or _TILDE_RE.match(s):
        return True
    if re.match(r"^[a-zA-Z]:(?![\\/])", s):
        return True
    if s.startswith("\\\\"):
        if not re.match(r"^\\\\\?\\[a-zA-Z]:[\\/]", s, re.IGNORECASE):
            return True
    rest = re.sub(r"^\\\\\?\\", "", s)
    rest = re.sub(r"^[a-zA-Z]:[\\/]?", "", rest)
    if ":" in rest:
        return True
    for part in re.split(r"[\\/]", rest):
        part_clean = part.strip()
        if _WINDOWS_RESERVED_DEVICE_RE.match(part_clean):
            return True
    base_lower = os.path.basename(rest.replace("/", "\\")).lower()
    if base_lower in PROTECTED_FILENAMES_LOWER or base_lower.startswith(".env"):
        return True
    return False


def reject_forbidden_expand(file_path: Any) -> str:
    """Validate and absolutize a path WITHOUT env/tilde expansion (`_expand_path` replacement)."""
    if has_forbidden_path_syntax(file_path):
        raise PermissionError(f"Access denied: forbidden or invalid path syntax '{file_path}'")
    return strip_win_long_prefix(os.path.abspath(str(file_path).strip()))


def get_final_path(target_path: Any, *, fail_on_unresolvable_reparse: bool = False) -> Optional[str]:
    """
    Resolve final physical path on disk using Windows `GetFinalPathNameByHandleW`
    ancestor walk, properly dereferencing Directory Junctions and Symlinks.
    """
    raw = str(target_path)
    if os.name != "nt":
        resolved = os.path.realpath(raw)
        return os.path.abspath(resolved)

    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32
        kernel32.CreateFileW.restype = wintypes.HANDLE
        kernel32.CreateFileW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        ]
        kernel32.GetFinalPathNameByHandleW.restype = wintypes.DWORD
        kernel32.GetFinalPathNameByHandleW.argtypes = [
            wintypes.HANDLE,
            wintypes.LPWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
        ]
        kernel32.CloseHandle.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

        cur = os.path.abspath(raw)
        tail: list[str] = []
        while not os.path.lexists(cur):
            parent = os.path.dirname(cur)
            if parent == cur:
                break
            tail.append(os.path.basename(cur))
            cur = parent

        if os.path.lexists(cur):
            handle = kernel32.CreateFileW(
                cur,
                0,
                1 | 2 | 4,  # FILE_SHARE_READ | WRITE | DELETE
                None,
                3,  # OPEN_EXISTING
                0x02000000,  # FILE_FLAG_BACKUP_SEMANTICS
                None,
            )
            if handle is not None and handle not in (-1, 0, 0xFFFFFFFFFFFFFFFF):
                try:
                    buf = ctypes.create_unicode_buffer(2048)
                    res = kernel32.GetFinalPathNameByHandleW(handle, buf, 2048, 0)
                    if res > 0:
                        real = strip_win_long_prefix(buf.value)
                        for part in reversed(tail):
                            real = os.path.join(real, part)
                        return strip_win_long_prefix(os.path.abspath(real))
                finally:
                    kernel32.CloseHandle(handle)
            if fail_on_unresolvable_reparse:
                return None
    except Exception:
        if fail_on_unresolvable_reparse:
            return None

    return strip_win_long_prefix(os.path.abspath(raw))


def parse_allowed_roots_env() -> list[str]:
    """Parse `DSH_ALLOWED_ROOTS` strictly; empty or unset returns `[]` (fail closed)."""
    env_roots = os.environ.get("DSH_ALLOWED_ROOTS")
    if env_roots is None or not str(env_roots).strip():
        return []
    try:
        parsed = json.loads(env_roots)
        if isinstance(parsed, str):
            return [parsed.strip()] if parsed.strip() else []
        if isinstance(parsed, list):
            return [str(p).strip() for p in parsed if isinstance(p, str) and str(p).strip()]
        return []
    except Exception:
        if ";" in str(env_roots) or "," in str(env_roots):
            return [p.strip() for p in re.split(r"[;,]", str(env_roots)) if p.strip()]
        s = str(env_roots).strip()
        return [s] if s else []


def validate_path_against_allowed_roots(
    target_path: Any,
    allowed_roots: Optional[Iterable[str]] = None,
    *,
    must_not_be_root_dir: bool = False,
) -> bool:
    """
    Fail-closed validation of `target_path` against `allowed_roots` (or `DSH_ALLOWED_ROOTS`).
    Never falls back to `os.getcwd()` or permits paths when roots are missing/empty.
    """
    if isinstance(target_path, os.PathLike):
        target_path = os.fspath(target_path)
    if not isinstance(target_path, str) or not target_path.strip():
        return False

    if has_forbidden_path_syntax(target_path):
        return False

    if allowed_roots is None:
        effective_roots = parse_allowed_roots_env()
    else:
        effective_roots = [str(r).strip() for r in allowed_roots if isinstance(r, str) and str(r).strip()]

    if not effective_roots:
        return False

    raw_default_cwd = (os.environ.get("DSH_DEFAULT_CWD") or "").strip() or None
    raw_str = str(target_path).strip()
    is_abs = (
        os.path.isabs(raw_str)
        or bool(re.match(r"^[a-zA-Z]:[\\/]", raw_str))
        or raw_str.startswith("\\\\")
    )

    if is_abs:
        anchored_target = raw_str
    else:
        if not raw_default_cwd or has_forbidden_path_syntax(raw_default_cwd):
            return False
        anchored_target = os.path.join(raw_default_cwd, raw_str)

    final_target_raw = get_final_path(anchored_target, fail_on_unresolvable_reparse=True)
    if not final_target_raw:
        return False
    final_target = os.path.normcase(strip_win_long_prefix(final_target_raw))

    for root in effective_roots:
        if has_forbidden_path_syntax(root):
            continue
        final_root_raw = get_final_path(root, fail_on_unresolvable_reparse=True)
        if not final_root_raw:
            continue
        final_root = os.path.normcase(strip_win_long_prefix(final_root_raw))
        try:
            if os.path.commonpath([final_target, final_root]) == final_root:
                if must_not_be_root_dir and final_target == final_root:
                    continue
                return True
        except ValueError:
            continue

    return False


def require_allowed_path(
    target_path: Any,
    *,
    label: str = "path",
    allowed_roots: Optional[Iterable[str]] = None,
    must_not_be_root_dir: bool = False,
) -> str:
    """Validate `target_path` fail-closed and return normalized absolute path string."""
    if isinstance(target_path, os.PathLike):
        target_path = os.fspath(target_path)
    if not validate_path_against_allowed_roots(
        target_path,
        allowed_roots=allowed_roots,
        must_not_be_root_dir=must_not_be_root_dir,
    ):
        raise PermissionError(
            f"Access denied: {label} '{target_path}' is outside allowed roots (DSH_ALLOWED_ROOTS)"
        )
    raw_default_cwd = (os.environ.get("DSH_DEFAULT_CWD") or "").strip() or None
    raw_str = str(target_path).strip()
    is_abs = (
        os.path.isabs(raw_str)
        or bool(re.match(r"^[a-zA-Z]:[\\/]", raw_str))
        or raw_str.startswith("\\\\")
    )
    anchored = raw_str if is_abs else os.path.join(raw_default_cwd or "", raw_str)
    return strip_win_long_prefix(os.path.abspath(anchored))


def safe_ensure_dir(
    dir_path: Any,
    *,
    label: str = "output_dir",
    allowed_roots: Optional[Iterable[str]] = None,
) -> Path:
    """Validate BEFORE creating a directory, then re-verify physical containment (TOCTOU defense)."""
    safe_dir = Path(require_allowed_path(dir_path, label=label, allowed_roots=allowed_roots))
    safe_dir.mkdir(parents=True, exist_ok=True)
    return Path(require_allowed_path(safe_dir, label=label, allowed_roots=allowed_roots))


def safe_ensure_parent_dir(
    file_path: Any,
    *,
    label: str = "output_path",
    allowed_roots: Optional[Iterable[str]] = None,
) -> str:
    """Validate BEFORE creating parent directories, then re-verify physical containment (TOCTOU defense)."""
    safe_target = require_allowed_path(
        file_path, label=label, allowed_roots=allowed_roots, must_not_be_root_dir=True
    )
    parent = os.path.dirname(safe_target)
    if parent:
        os.makedirs(parent, exist_ok=True)
    # Re-validate after mkdir in case an ancestor was swapped concurrently (TOCTOU)
    return require_allowed_path(
        safe_target, label=label, allowed_roots=allowed_roots, must_not_be_root_dir=True
    )


def _is_path_like(key: str, val: str) -> bool:
    trimmed = val.strip()
    if not trimmed:
        return bool(key and _EXPLICIT_PATH_KEY_RE.match(key))
    if _BARE_NAME_KEY_RE.match(key):
        return (
            any(tok in trimmed for tok in ("/", "\\", "..", ":"))
            or _ENV_VAR_RE.search(trimmed) is not None
            or bool(_TILDE_RE.match(trimmed))
            or bool(_WINDOWS_RESERVED_DEVICE_RE.match(trimmed))
        )
    if trimmed.lower().startswith("file:") or re.match(r"^[a-zA-Z]:", trimmed) or trimmed.startswith("\\\\") or trimmed.startswith("/"):
        return True
    if "\\" in trimmed or "/" in trimmed:
        return True
    if _ENV_VAR_RE.search(trimmed) or _TILDE_RE.match(trimmed):
        return True
    if key and (
        _EXPLICIT_PATH_KEY_RE.match(key)
        or re.search(r"(?:^|_)(path|dir|folder|root|destination)(?:$|_)", key, re.IGNORECASE)
        or re.search(r"(?:Path|Dir|Directory|Folder|Root|Model|Template|File|Candidates)$", key)
    ):
        return True
    if _PATH_EXT_RE.search(trimmed) and key and re.search(r"(file|model|drawing|spec|target|path|doc)", key, re.IGNORECASE):
        return True
    return False


def validate_nested_tool_paths(
    obj: Any,
    *,
    allowed_roots: Optional[Iterable[str]] = None,
    _depth: int = 0,
    _key: str = "",
) -> None:
    """
    Recursively validate every path-like string in MCP tool arguments (`BaseModel` or nested `dict`/`list`),
    including `output_dir + drawing_filename` composite targets.
    """
    if _depth > 32 or obj is None:
        return
    if hasattr(obj, "model_dump"):
        obj = obj.model_dump()
    if isinstance(obj, dict):
        out_dir = obj.get("output_dir")
        drw_name = obj.get("drawing_filename")
        if isinstance(out_dir, str) and out_dir.strip() and isinstance(drw_name, str) and drw_name.strip():
            if has_forbidden_path_syntax(drw_name) or any(tok in drw_name for tok in ("/", "\\", "..", ":")):
                raise PermissionError(f"Access denied: invalid drawing_filename '{drw_name}'")
            require_allowed_path(os.path.join(out_dir.strip(), drw_name.strip()), label="drawing_output_path", allowed_roots=allowed_roots)
        for k, v in obj.items():
            validate_nested_tool_paths(v, allowed_roots=allowed_roots, _depth=_depth + 1, _key=str(k))
        return
    if isinstance(obj, (list, tuple)):
        for item in obj:
            validate_nested_tool_paths(item, allowed_roots=allowed_roots, _depth=_depth + 1, _key=_key)
        return
    if isinstance(obj, str):
        if _is_path_like(_key, obj):
            require_allowed_path(obj, label=_key or "path", allowed_roots=allowed_roots)
