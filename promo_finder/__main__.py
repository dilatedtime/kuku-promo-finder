from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description="Find source-grounded 20-60s promo candidates. Outputs contain confidential clip text.")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("run")
    p.add_argument("--input", required=True, help="Timed screenplay file or a directory of supported files")
    p.add_argument("--output", required=True, help="New/empty private run directory; never overwritten")
    p.add_argument("--config", default="configs/mock.json")
    p.add_argument("--variant", choices=["baseline", "refined"], default="refined")
    p.add_argument("--per-episode", type=int, default=2)
    p.add_argument("--limit", type=int, default=40)
    p.add_argument("--stitches", action="store_true")
    p.add_argument("--fresh", action="store_true", help="Bypass judgment cache for a genuine model stability test")
    p.add_argument("--cache-dir")
    p.add_argument("--expected-episodes", type=int)
    p.add_argument("--critic-top", type=int, default=0, help="Fresh clip-only viewer checks for the pre-critic top N (real model only)")
    p = sub.add_parser("review-metrics")
    p.add_argument("--labels", required=True)
    p.add_argument("--output")
    p = sub.add_parser("compare")
    p.add_argument("runs", nargs="+", help="Two or more run directories")
    p.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        if args.command == "run":
            from .pipeline import run
            cfg = json.loads(Path(args.config).read_text(encoding="utf-8-sig"))
            result = run(args.input,args.output,cfg,variant=args.variant,per_episode=args.per_episode,limit=args.limit,stitches=args.stitches,fresh=args.fresh,cache_dir=args.cache_dir,expected_episodes=args.expected_episodes,critic_top=args.critic_top)
            print(f"SUCCESS: {len(result['promos'])} promos; {result['usage']['model_requests']} model requests. {args.output}")
        elif args.command == "review-metrics":
            from .evaluation import review_metrics
            result = review_metrics(Path(args.labels))
            content = json.dumps(result, indent=2)
            if args.output:
                Path(args.output).write_text(content, encoding="utf-8")
            print(content)
        else:
            from .evaluation import compare_runs
            result = compare_runs([Path(x) for x in args.runs])
            Path(args.output).write_text(json.dumps(result,indent=2),encoding="utf-8")
            print(json.dumps(result,indent=2))
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
