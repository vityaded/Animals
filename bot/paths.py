from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def project_path(*parts: str | Path) -> Path:
    """Return an absolute path inside the project root."""
    return PROJECT_ROOT.joinpath(*[Path(p) for p in parts])


def resolve_project_path(path: str | Path) -> Path:
    """Resolve a path relative to the project root if it is not absolute."""
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate
