from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class OfflineArtifactPaths:
    summary: Path
    payload_dir: Path
    review_html: Path
    viewer_dir: Path


def offline_artifact_paths(
    run_dir: Path,
    *,
    summary: Path | None = None,
    payload_dir: Path | None = None,
    review_html: Path | None = None,
    viewer_dir: Path | None = None,
) -> OfflineArtifactPaths:
    return OfflineArtifactPaths(
        summary=summary or run_dir / "summary.json",
        payload_dir=payload_dir or run_dir / "payloads",
        review_html=review_html or run_dir / "review.html",
        viewer_dir=viewer_dir or run_dir / "viewers",
    )
