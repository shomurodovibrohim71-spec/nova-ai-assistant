"""Path-safety helpers — keep file ops inside an allow-listed root."""
from __future__ import annotations

from pathlib import Path


class PathError(ValueError):
    """Raised when a requested path escapes the allowed root."""


def safe_resolve(path: str | Path, root: str | Path) -> Path:
    """Resolve `path` (relative or absolute) and ensure it stays inside `root`.

    `~` is expanded. Symlinks are followed. Raises PathError on escape attempts.
    """
    root_p = Path(root).expanduser().resolve()
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = root_p / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root_p)
    except ValueError as e:
        raise PathError(f"path {resolved} escapes root {root_p}") from e
    return resolved
