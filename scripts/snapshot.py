#!/usr/bin/env python3
"""Write a monthly snapshot of one's footprint results for group sharing.

Reads the CSV produced by `compute_footprint.py` and writes a small JSON
snapshot under `snapshots/YYYY-MM/<member>-<machine>.json`. Snapshots are
the unit shared at the OPERA group level (see snapshots/README.md).

Only aggregate numbers are stored: no project paths, no session IDs, no
costs, no per-request detail.

Usage:
    uv run scripts/snapshot.py --member lesommer --machine macbook [--month 2026-09 | --all]
"""

from __future__ import annotations

import argparse
import csv
import json
import platform
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FOOTPRINT = REPO_ROOT / "data" / "footprint.csv"
DEFAULT_SNAPSHOTS = REPO_ROOT / "snapshots"
DEFAULT_MAPPING = REPO_ROOT / "config" / "model_mapping.json"

SCHEMA_VERSION = 1

METRICS = ["energy_kwh", "gwp_kgco2eq", "adpe_kgsbeq", "pe_mj", "wcf_l"]


def to_float(value) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def month_of(ts: str) -> str:
    return ts[:7]


def load_zone() -> str:
    with DEFAULT_MAPPING.open() as fd:
        return json.load(fd).get("electricity_mix_zone", "FRA")


def snapshot_for_month(rows: list[dict], month: str, member: str, machine: str, zone: str) -> dict:
    modeled = [r for r in rows if month_of(r["ts"]) == month and r["status"] == "modeled"]
    all_month = [r for r in rows if month_of(r["ts"]) == month]
    if not all_month:
        return {}

    snap = {
        "schema_version": SCHEMA_VERSION,
        "tool": "opencode-footprint-monitor",
        "member": member,
        "machine": machine,
        "month": month,
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "electricity_mix_zone": zone,
        "requests": {
            "total": len(all_month),
            "modeled": len(modeled),
            "unmodeled": len(all_month) - len(modeled),
        },
        "tokens": {
            "input": sum(int(float(r["tokens_input"])) for r in all_month),
            "generated": sum(int(float(r["tokens_generated"])) for r in all_month),
        },
    }
    for metric in METRICS:
        snap[metric] = {
            "min": sum(to_float(r.get(f"{metric}_min")) or 0.0 for r in modeled),
            "max": sum(to_float(r.get(f"{metric}_max")) or 0.0 for r in modeled),
        }
    by_mapping: dict[str, dict] = defaultdict(lambda: {"requests": 0, "tokens_generated": 0})
    for r in modeled:
        key = r.get("mapping") or "unknown"
        by_mapping[key]["requests"] += 1
        by_mapping[key]["tokens_generated"] += int(float(r["tokens_generated"]))
    snap["mapping_breakdown"] = {
        k: v for k, v in sorted(by_mapping.items(), key=lambda kv: -kv[1]["requests"])
    }
    unmodeled: Counter = Counter()
    for r in all_month:
        if r["status"] != "modeled":
            unmodeled[r["model"]] += 1
    snap["unmodeled_models"] = dict(unmodeled) if unmodeled else {}
    return snap


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--member", required=True, help="Your name/identifier as known to the group")
    parser.add_argument(
        "--machine",
        default=platform.node().split(".")[0].lower() or "localhost",
        help="Machine name (default: hostname)",
    )
    parser.add_argument("--month", help="Month to snapshot, format YYYY-MM (default: last month in data)")
    parser.add_argument("--all", action="store_true", help="Snapshot every month found in the data")
    parser.add_argument("--footprint", type=Path, default=DEFAULT_FOOTPRINT)
    parser.add_argument("--out", type=Path, default=DEFAULT_SNAPSHOTS, help="Snapshots directory")
    args = parser.parse_args()

    if not args.footprint.exists():
        print(f"error: {args.footprint} not found; run compute_footprint.py first", file=sys.stderr)
        return 1

    with args.footprint.open(newline="") as fd:
        rows = list(csv.DictReader(fd))
    if not rows:
        print("error: no rows in footprint file", file=sys.stderr)
        return 1

    months = sorted({month_of(r["ts"]) for r in rows})
    if args.all:
        targets = months
    elif args.month:
        if args.month not in months:
            print(f"error: month {args.month} not in data (available: {', '.join(months)})", file=sys.stderr)
            return 1
        targets = [args.month]
    else:
        targets = [months[-1]]

    zone = load_zone()
    n_written = 0
    for month in targets:
        snap = snapshot_for_month(rows, month, args.member, args.machine, zone)
        if not snap:
            print(f"warning: no data for {month}, skipped", file=sys.stderr)
            continue
        out_dir = args.out / month
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"{args.member}-{args.machine}.json"
        out_file.write_text(json.dumps(snap, indent=2) + "\n")
        print(f"wrote {out_file.relative_to(REPO_ROOT)} ({snap['requests']['modeled']} modeled requests)")
        n_written += 1

    if not n_written:
        print("no snapshots written", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
