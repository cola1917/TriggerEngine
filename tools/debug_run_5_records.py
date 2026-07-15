from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
THIRD_PARTY = PROJECT_ROOT / "third_party"
if THIRD_PARTY.exists() and str(THIRD_PARTY) not in sys.path:
    sys.path.insert(0, str(THIRD_PARTY))

from tools.run_review_batch import run_batch


def _default_shards(limit: int) -> list[Path]:
    data_dir = PROJECT_ROOT / "data"
    return sorted(data_dir.glob("validation_interactive.tfrecord-*"))[:limit]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run TriggerEngine on the first few validation shards for debugging.")
    parser.add_argument("--limit", type=int, default=5, help="Number of validation shards to run")
    parser.add_argument("--workers", type=int, default=1, help="Worker count for shard execution")
    parser.add_argument("--output", default="review_batch_debug_5.json", help="Summary JSON output")
    parser.add_argument("--profile-rules", action="store_true", help="Include per-rule engine profiling in the summary")
    parser.add_argument("--payload-dir", default=None, help="Optional directory for review payload JSON")
    parser.add_argument("--view-output", default=None, help="Optional review index HTML output")
    parser.add_argument("--viewer-dir", default=None, help="Optional per-payload viewer HTML directory")
    args = parser.parse_args(argv)

    shards = _default_shards(args.limit)
    if not shards:
        parser.error("No validation shards were found under data/")

    summary = run_batch(
        shards,
        workers=args.workers,
        output=Path(args.output),
        payload_dir=Path(args.payload_dir) if args.payload_dir else None,
        view_output=Path(args.view_output) if args.view_output else None,
        viewer_dir=Path(args.viewer_dir) if args.viewer_dir else None,
        map_feature_limit=300,
        future_frames=30,
        map_crop_margin_m=80.0,
        profile_rules=args.profile_rules,
    )
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())