"""Real R0 acceptance: preserve each link's partial failures; never call a model."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.collection_probe import run_isolated_probe


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", help="profile URL or original share text")
    parser.add_argument("--video", help="video URL or original share text")
    parser.add_argument("--cookie-file", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--media-dir", type=Path, default=Path(".media/probe-scratch"),
                        help="scratch directory; sample is removed after FFprobe")
    args = parser.parse_args()
    if not args.profile and not args.video:
        parser.error("provide --profile or --video")
    reports = {}
    for name, text in (("profile", args.profile), ("video", args.video)):
        if text:
            reports[name] = run_isolated_probe(text, True, str(args.cookie_file or ""), args.media_dir)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(reports, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
            print(name, "passed" if reports[name]["complete"] else "not_passed", flush=True)
    return 0 if all(report["complete"] for report in reports.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
