from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trigger_engine.contracts.evaluation_feedback import import_evaluation_result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import ClosedLoopBench evaluation_run_result.v1 as Trigger feedback."
    )
    parser.add_argument("result", type=Path, help="evaluation_run_result.v1 JSON file")
    parser.add_argument(
        "--feedback-root",
        type=Path,
        default=ROOT / "outputs" / "evaluation_feedback",
        help="immutable scenario_feedback.v1 output directory",
    )
    args = parser.parse_args()
    result = json.loads(args.result.read_text(encoding="utf-8"))
    feedback, path, created = import_evaluation_result(result, args.feedback_root)
    print(
        json.dumps(
            {
                "path": str(path),
                "created": created,
                "feedback_id": feedback["feedback_id"],
                "classification": feedback["classification"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
