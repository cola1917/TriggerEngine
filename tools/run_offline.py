from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
THIRD_PARTY = PROJECT_ROOT / "third_party"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if THIRD_PARTY.exists() and str(THIRD_PARTY) not in sys.path:
    sys.path.insert(0, str(THIRD_PARTY))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run unified offline TriggerEngine mining.")
    parser.add_argument("--source", choices=("nuscenes", "waymo"), required=True)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=5)
    parser.add_argument("--future-steps", type=int, default=8)
    parser.add_argument("--map-feature-limit", type=int, default=500)
    parser.add_argument("--map-crop-margin-m", type=float, default=80.0)
    parser.add_argument("--profile-rules", action="store_true")
    parser.add_argument("--no-payloads", action="store_true", help="Skip payload and review HTML generation")
    parser.add_argument("--no-scenario-summaries", action="store_true", help="Skip per-scenario summary details")

    parser.add_argument("--dataroot", default=None, help="nuScenes dataroot")
    parser.add_argument("--version", default="v1.0-mini", help="nuScenes version")
    parser.add_argument("--scene", action="append", dest="scenes", help="nuScenes scene name/token")
    parser.add_argument("paths", nargs="*", help="Waymo TFRecord shard paths")
    args = parser.parse_args(argv)

    from trigger_engine.offline.engine import build_default_engine
    from trigger_engine.offline.runner import OfflineRunConfig, run_offline_source
    from trigger_engine.offline.sources import make_offline_source

    if args.source == "nuscenes":
        if not args.dataroot:
            parser.error("--source nuscenes requires --dataroot")
        source = make_offline_source(
            "nuscenes",
            dataroot=Path(args.dataroot),
            version=args.version,
            scenes=args.scenes,
        )
    else:
        if not args.paths:
            parser.error("--source waymo requires TFRecord paths")
        source = make_offline_source("waymo", paths=[Path(path) for path in args.paths])

    summary = run_offline_source(
        source,
        engine=build_default_engine(profile_rules=args.profile_rules),
        config=OfflineRunConfig(
            run_dir=Path(args.run_dir),
            batch_size=args.batch_size,
            workers=args.workers,
            future_steps=args.future_steps,
            map_feature_limit=args.map_feature_limit,
            map_crop_margin_m=args.map_crop_margin_m,
            write_payloads=not args.no_payloads,
            include_scenario_summaries=not args.no_scenario_summaries,
        ),
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
