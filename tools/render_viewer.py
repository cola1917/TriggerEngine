from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.export_viewer import render_viewer_from_payload


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Render static HTML viewer from review payload JSON.")
    parser.add_argument("payload", help="Review payload JSON path")
    parser.add_argument("-o", "--output", default="viewer.html", help="Output HTML path")
    args = parser.parse_args(argv)

    output = render_viewer_from_payload(Path(args.payload), Path(args.output))
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
