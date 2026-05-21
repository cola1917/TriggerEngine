from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.export_viewer import DEFAULT_TFRECORD, export_review_payload


DEFAULT_OUTPUT = Path("review_payload.json")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Export TriggerEngine review payload JSON.")
    parser.add_argument("path", nargs="?", default=str(DEFAULT_TFRECORD), help="Waymo TFRecord file")
    parser.add_argument("-o", "--output", default=str(DEFAULT_OUTPUT), help="Output JSON payload path")
    parser.add_argument("--scenario-index", type=int, default=0, help="Scenario index in the shard")
    parser.add_argument("--scenario-id", default=None, help="Scenario id to export")
    parser.add_argument("--map-feature-limit", type=int, default=500, help="Maximum map features to embed")
    args = parser.parse_args(argv)

    output = export_review_payload(
        Path(args.path),
        Path(args.output),
        scenario_index=args.scenario_index,
        scenario_id=args.scenario_id,
        map_feature_limit=args.map_feature_limit,
    )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
