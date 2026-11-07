"""Shared deterministic artifact-bundle persistence primitives."""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from pathlib import Path
from typing import Any


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, allow_nan=False, ensure_ascii=False,
                        separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")


def content_digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def execution_environment() -> dict[str, str]:
    lock_path = Path(__file__).resolve().parents[3] / "uv.lock"
    try:
        lock_digest = content_digest(lock_path.read_bytes())
    except OSError:
        lock_digest = "unavailable"
    return {
        "machine": platform.machine(),
        "python": platform.python_version(),
        "sys_platform": sys.platform,
        "uv_lock": lock_digest,
    }


def write_artifact_bundle(root: str | Path, run_id: str,
                          artifacts: dict[str, bytes],
                          metadata: dict[str, Any]) -> Path:
    """Atomically create a run directory with a digest manifest."""
    root_path = Path(root)
    destination = root_path / run_id
    temporary = root_path / f".{run_id}.tmp"
    root_path.mkdir(parents=True, exist_ok=True)
    if destination.exists() or temporary.exists():
        raise FileExistsError("run destination already exists")
    temporary.mkdir()
    try:
        for name in sorted(artifacts):
            if Path(name).name != name or name == "manifest.json":
                raise ValueError(f"invalid artifact name: {name}")
            (temporary / name).write_bytes(artifacts[name])
        manifest = dict(metadata)
        manifest["artifacts"] = {
            name: content_digest(artifacts[name]) for name in sorted(artifacts)
        }
        manifest["run_id"] = run_id
        (temporary / "manifest.json").write_bytes(canonical_json_bytes(manifest))
        temporary.rename(destination)
    except (OSError, ValueError):
        for child in temporary.iterdir():
            child.unlink()
        temporary.rmdir()
        raise
    return destination


def read_artifact_bundle(path: str | Path, artifact_names: tuple[str, ...],
                         expected_schema: str) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Read named artifacts only after manifest and digest verification."""
    run_path = Path(path)
    manifest = json.loads((run_path / "manifest.json").read_text(encoding="utf-8"))
    if manifest["schema_version"] != expected_schema:
        raise ValueError("unsupported run store schema")
    if manifest["run_id"] != run_path.name:
        raise ValueError("run directory and manifest identifiers differ")
    artifacts: dict[str, bytes] = {}
    for name in artifact_names:
        content = (run_path / name).read_bytes()
        if manifest["artifacts"].get(name) != content_digest(content):
            raise ValueError(f"artifact digest mismatch: {name}")
        artifacts[name] = content
    return manifest, artifacts
