#!/usr/bin/env python3
"""Aggregate member snapshots into an OPERA group footprint report.

Reads every `snapshots/**/*.json` file (see snapshots/README.md for the
format) and writes a Markdown group report with group totals, a per-member
table and a per-month trend.

Usage:
    uv run scripts/aggregate_group.py [--snapshots PATH] [--out PATH]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SNAPSHOTS = REPO_ROOT / "snapshots"
DEFAULT_OUT = REPO_ROOT / "data" / "group-report.md"

METRICS = [
    ("energy", "energy_kwh", "kWh"),
    ("gwp", "gwp_kgco2eq", "gCO2eq", 1000.0),
    ("adpe", "adpe_kgsbeq", "gSbeq", 1000.0),
    ("pe", "pe_mj", "MJ"),
    ("wcf", "wcf_l", "L"),
]
SCHEMA_VERSION = 1
CAR_GCO2_PER_KM = 120.0


def fmt(value, digits: int = 2) -> str:
    if value != value or value is None:
        return "-"
    if value != 0 and abs(value) < 10 ** (-digits):
        return f"{value:.2e}"
    return f"{value:,.{digits}f}"


def load_snapshots(snapshots_dir: Path) -> list[dict]:
    snaps = []
    for path in sorted(snapshots_dir.glob("*/*.json")):
        try:
            snap = json.loads(path.read_text())
        except json.JSONDecodeError as e:
            print(f"warning: skipping invalid JSON {path}: {e}", file=sys.stderr)
            continue
        if snap.get("tool") != "opencode-footprint-monitor":
            print(f"warning: skipping unrecognized file {path}", file=sys.stderr)
            continue
        if snap.get("schema_version") != SCHEMA_VERSION:
            print(
                f"warning: skipping {path}: schema version "
                f"{snap.get('schema_version')} != {SCHEMA_VERSION}",
                file=sys.stderr,
            )
            continue
        snaps.append(snap)
    return snaps


def mid(snap: dict, metric: str) -> float:
    m = snap[metric]
    return (m["min"] + m["max"]) / 2


def render(snaps: list[dict], snapshots_dir: Path) -> str:
    lines: list[str] = []
    lines.append("# OPERA group LLM footprint report")
    lines.append("")
    lines.append(f"- Generated: {datetime.now().isoformat(timespec='seconds')}")
    lines.append(f"- Source: `{snapshots_dir}/` ({len(snaps)} member-month snapshots)")
    members = sorted({s["member"] for s in snaps})
    months = sorted({s["month"] for s in snaps})
    if months:
        lines.append(f"- Period: {months[0]} to {months[-1]}")
    lines.append(f"- Members: {', '.join(members)}")
    lines.append("")

    lines.append("## Group totals")
    lines.append("")
    n_modeled = sum(s["requests"]["modeled"] for s in snaps)
    n_total = sum(s["requests"]["total"] for s in snaps)
    lines.append(f"Over **{n_modeled:,}** modeled requests ({n_total:,} including unmodeled):")
    lines.append("")
    lines.append("| Impact | Total (min) | Total (max) | Unit |")
    lines.append("|---|---:|---:|---|")
    for entry in METRICS:
        label, metric = entry[0], entry[1]
        unit = entry[2]
        scale = entry[3] if len(entry) > 3 else 1.0
        vmin = sum(s[metric]["min"] for s in snaps) * scale
        vmax = sum(s[metric]["max"] for s in snaps) * scale
        lines.append(f"| {label} | {fmt(vmin)} | {fmt(vmax)} | {unit} |")
    lines.append("")
    gwp_mid_g = sum(mid(s, "gwp_kgco2eq") for s in snaps) * 1000.0
    lines.append(
        f"Midpoint GWP is equivalent to about **{fmt(gwp_mid_g / CAR_GCO2_PER_KM, 1)} km** "
        f"in a typical French car (~{CAR_GCO2_PER_KM:.0f} gCO2eq/km)."
    )
    lines.append("")

    lines.append("## Per member")
    lines.append("")
    lines.append("| Member | Months | Requests (modeled) | Tokens generated | Energy (kWh) | GWP (gCO2eq) |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    by_member: dict[str, list[dict]] = defaultdict(list)
    for s in snaps:
        by_member[s["member"]].append(s)
    for member, group in sorted(by_member.items()):
        n_req = sum(s["requests"]["modeled"] for s in group)
        n_tok = sum(s["tokens"]["generated"] for s in group)
        energy = sum(mid(s, "energy_kwh") for s in group)
        gwp = sum(mid(s, "gwp_kgco2eq") for s in group) * 1000.0
        lines.append(
            f"| {member} | {len({s['month'] for s in group})} | {n_req:,} | {n_tok:,} "
            f"| {fmt(energy)} | {fmt(gwp)} |"
        )
    lines.append("")

    lines.append("## Per month")
    lines.append("")
    lines.append("| Month | Members reporting | Requests | GWP (gCO2eq) |")
    lines.append("|---|---:|---:|---:|")
    by_month: dict[str, list[dict]] = defaultdict(list)
    for s in snaps:
        by_month[s["month"]].append(s)
    for month in sorted(by_month):
        group = by_month[month]
        n_req = sum(s["requests"]["modeled"] for s in group)
        gwp = sum(mid(s, "gwp_kgco2eq") for s in group) * 1000.0
        lines.append(f"| {month} | {len({s['member'] for s in group})} | {n_req:,} | {fmt(gwp)} |")
    lines.append("")

    zones = sorted({s["electricity_mix_zone"] for s in snaps})
    if len(zones) > 1:
        lines.append(f"Note: snapshots use different electricity mix zones ({', '.join(zones)}); "
                     "totals sum them as-is.")
        lines.append("")

    lines.append("## Coverage")
    lines.append("")
    lines.append("| Member | Month | Modeled | Unmodeled | Share modeled |")
    lines.append("|---|---|---:|---:|---:|")
    for s in sorted(snaps, key=lambda s: (s["member"], s["month"])):
        r = s["requests"]
        share = 100.0 * r["modeled"] / r["total"] if r["total"] else 0.0
        lines.append(f"| {s['member']} | {s['month']} | {r['modeled']:,} | {r['unmodeled']:,} | {share:.1f}% |")
    lines.append("")
    lines.append(
        "Estimates follow the [EcoLogits](https://ecologits.ai) methodology; "
        "assumptions and limitations: `docs/methodology.md` in the "
        "[opencode-footprint-monitor](https://github.com/lesommer/opencode-footprint-monitor) repository."
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshots", type=Path, default=DEFAULT_SNAPSHOTS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    if not args.snapshots.is_dir():
        print(f"error: snapshots directory not found: {args.snapshots}", file=sys.stderr)
        return 1

    snaps = load_snapshots(args.snapshots)
    if not snaps:
        print("error: no valid snapshots found", file=sys.stderr)
        return 1

    report = render(snaps, args.snapshots)
    try:
        source_display = args.snapshots.relative_to(REPO_ROOT)
    except ValueError:
        source_display = args.snapshots
    report = report.replace(str(args.snapshots), str(source_display))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report)
    print(f"Group report written to {args.out} ({len(snaps)} snapshots)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
