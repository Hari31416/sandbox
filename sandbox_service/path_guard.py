from __future__ import annotations

import base64
import hashlib
import os
import re
from pathlib import Path


class PathEscapeError(ValueError):
    pass


_B64_DECODE_PATTERN = re.compile(r"base64\.b64decode\('([A-Za-z0-9+/=]+)'\)")
_GUEST_WORKSPACE_ROOT = "/workspace"


def rewrite_guest_path(path: str) -> str:
    """Map guest ``/workspace`` paths to cwd-relative paths for local exec."""
    candidate = path.strip()
    if candidate == _GUEST_WORKSPACE_ROOT:
        return "."
    if candidate.startswith(f"{_GUEST_WORKSPACE_ROOT}/"):
        return candidate[len(_GUEST_WORKSPACE_ROOT) + 1 :]
    return candidate


def rewrite_guest_workspace_command(command: str) -> str:
    """Rewrite guest ``/workspace`` paths in shell and DeepAgents helper commands.

    The local sandbox runtime executes on the host with ``cwd`` set to the
    scratch workspace. Absolute ``/workspace`` paths would otherwise resolve on
    the host filesystem (for example a macOS ``/workspace`` mount), not inside
    the session scratch directory.
    """
    rewritten = command.replace(f"{_GUEST_WORKSPACE_ROOT}/", "")
    rewritten = re.sub(
        r"(?<![\w./])/workspace(?![\w/])",
        ".",
        rewritten,
    )

    def _rewrite_b64(match: re.Match[str]) -> str:
        encoded = match.group(1)
        try:
            decoded = base64.b64decode(encoded).decode("utf-8")
        except (UnicodeDecodeError, ValueError):
            return match.group(0)
        mapped = rewrite_guest_path(decoded)
        if mapped == decoded:
            return match.group(0)
        new_encoded = base64.b64encode(mapped.encode("utf-8")).decode("ascii")
        return f"base64.b64decode('{new_encoded}')"

    return _B64_DECODE_PATTERN.sub(_rewrite_b64, rewritten)


def normalize_sandbox_path(path: str, *, workspace_label: str = "workspace") -> str:
    candidate = path.strip().replace("\\", "/")
    if not candidate:
        return ""
    if candidate.startswith("/"):
        candidate = candidate.lstrip("/")
    if candidate in {".", ".."}:
        raise PathEscapeError(f"Path escapes sandbox root: {path}")
    if candidate == workspace_label:
        return ""
    if candidate.startswith(f"{workspace_label}/"):
        candidate = candidate[len(workspace_label) + 1 :]
    parts = Path(candidate).parts
    if any(part == ".." for part in parts):
        raise PathEscapeError(f"Path escapes sandbox root: {path}")
    return "/".join(parts)


def resolve_host_path(root_path: str | Path, relative_path: str) -> Path:
    normalized = normalize_sandbox_path(relative_path)
    root = Path(root_path).resolve()
    target = (root / normalized).resolve() if normalized else root
    if not _is_within_root(target, root):
        raise PathEscapeError(f"Path escapes sandbox root: {relative_path}")
    if target.is_symlink():
        raise PathEscapeError(f"Symlink paths are not allowed: {relative_path}")
    return target


def _is_within_root(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_directory(path: Path, mode: int = 0o755) -> None:
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, mode)


def write_file(path: Path, content: bytes, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    os.chmod(path, mode)
