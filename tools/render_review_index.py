from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Render a review index HTML for a payload output directory."
    )
    parser.add_argument("payload_dir", help="Directory containing review payload JSON files")
    parser.add_argument("-o", "--output", default="view.html", help="Output index HTML path")
    parser.add_argument("--viewer-dir", default=None, help="Directory for per-payload viewer HTML files")
    args = parser.parse_args(argv)

    from tools.export_viewer import render_review_index_from_payload_dir

    payload_dir = Path(args.payload_dir)
    output = Path(args.output)
    viewer_dir = Path(args.viewer_dir) if args.viewer_dir else None

    result = render_review_index_from_payload_dir(payload_dir, output, viewer_dir)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
