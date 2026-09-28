#!/usr/bin/env python3
"""Aggregate footprint results into a Markdown report with totals and breakdowns.

Reads the CSV produced by `compute_footprint.py` and writes a Markdown report
plus a machine-readable totals JSON.

Usage:
    uv run scripts/report.py [--footprint PATH] [--out PATH] [--totals PATH]
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FOOTPRINT = REPO_ROOT / "data" / "footprint.csv"
DEFAULT_OUT = REPO_ROOT / "data" / "report.md"
DEFAULT_TOTALS = REPO_ROOT / "data" / "totals.json"

METRICS = [
    ("energy", "energy_kwh", "kWh", 1.0),
    ("gwp", "gwp_kgco2eq", "gCO2eq", 1000.0),
    ("adpe", "adpe_kgsbeq", "gSbeq", 1000.0),
    ("pe", "pe_mj", "MJ", 1.0),
    ("wcf", "wcf_l", "L", 1.0),
]

# Rough communication aid (ADEME order of magnitude): a typical French car
# emits about 120 gCO2eq per km (well-to-wheel, average fleet).
CAR_GCO2_PER_KM = 120.0


def fmt(value, digits: int = 3) -> str:
    if value is None or value != value:
        return "-"
    if value != 0 and abs(value) < 10 ** -(digits):
        return f"{value:.2e}"
    return f"{value:,.{digits}f}"


def load_rows(path: Path) -> list[dict]:
    with path.open(newline="") as fd:
        return list(csv.DictReader(fd))


def to_float(value) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def sum_metric(rows: list[dict], base: str, bound: str) -> float:
    total = 0.0
    for row in rows:
        v = to_float(row.get(f"{base}_{bound}"))
        if v is not None:
            total += v
    return total


def aggregate(rows: list[dict], keys: tuple[str, ...]) -> dict:
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        groups[tuple(row.get(k) or "unknown" for k in keys)].append(row)
    result = {}
    for keyvals, group in groups.items():
        entry = {
            "requests": len(group),
            "tokens_in": sum(int(float(r["tokens_input"])) for r in group),
            "tokens_generated": sum(int(float(r["tokens_generated"])) for r in group),
            "cost_usd": sum(float(r["cost_usd"] or 0) for r in group),
        }
        for _label, base, _unit, _scale in METRICS:
            entry[f"{base}_min"] = sum_metric(group, base, "min")
            entry[f"{base}_max"] = sum_metric(group, base, "max")
        result[keyvals] = entry
    return result


def month_of(row: dict) -> str:
    ts = row.get("ts") or ""
    return (ts[:7] + "-01") if ts >= "2000" else "unknown"


def render_report(rows: list[dict], footprint_path: Path) -> str:
    modeled = [r for r in rows if r["status"] == "modeled"]
    unmodeled = [r for r in rows if r["status"] != "modeled"]

    lines: list[str] = []
    lines.append("# OpenCode environmental footprint report")
    lines.append("")
    lines.append(f"- Generated: {datetime.now().isoformat(timespec='seconds')}")
    lines.append(f"- Source: `{footprint_path}` ({len(rows)} requests, {len(modeled)} modeled, {len(unmodeled)} unmodeled)")
    if modeled:
        lines.append(f"- Period: {min(r['ts'] for r in modeled)[:10]} to {max(r['ts'] for r in modeled)[:10]}")
    lines.append("")

    # --- Totals -----------------------------------------------------------
    lines.append("## Totals")
    lines.append("")
    n_sessions = len({r["session_id"] for r in rows})
    lines.append(f"Over **{len(modeled):,}** modeled requests across **{n_sessions:,}** sessions:")
    lines.append("")
    lines.append("| Impact | Total (min) | Total (max) | Unit |")
    lines.append("|---|---:|---:|---|")
    totals = {}
    for label, base, unit, scale in METRICS:
        vmin = sum_metric(modeled, base, "min") * scale
        vmax = sum_metric(modeled, base, "max") * scale
        totals[base] = {"min": vmin, "max": vmax, "unit": unit}
        lines.append(f"| {label} | {fmt(vmin)} | {fmt(vmax)} | {unit} |")
    lines.append("")
    gwp_total_unscaled = sum_metric(modeled, "gwp_kgco2eq", "max") or 1.0
    gwp_mid_g = (totals["gwp_kgco2eq"]["min"] + totals["gwp_kgco2eq"]["max"]) / 2
    km_car = gwp_mid_g / CAR_GCO2_PER_KM
    lines.append(
        f"For context: the midpoint GWP estimate is equivalent to about "
        f"**{fmt(km_car, 1)} km** driven in a typical French car "
        f"(~{CAR_GCO2_PER_KM:.0f} gCO2eq/km)."
    )
    lines.append("")

    # --- Per model ----------------------------------------------------------
    lines.append("## Per model")
    lines.append("")
    lines.append("| Model | Requests | Tokens (in/gen) | Energy (kWh) | GWP (gCO2eq) | Share of GWP | Mapping |")
    lines.append("|---|---:|---:|---:|---:|---:|---|")
    gwp_total_unscaled = sum_metric(modeled, "gwp_kgco2eq", "max") or 1.0
    by_model = aggregate(modeled, ("model",))
    for (model,), e in sorted(by_model.items(), key=lambda kv: -kv[1]["gwp_kgco2eq_max"]):
        mapping = next((r["mapping"] for r in modeled if r["model"] == model), "-")
        share = 100.0 * e["gwp_kgco2eq_max"] / gwp_total_unscaled
        lines.append(
            f"| `{model}` | {e['requests']:,} | {e['tokens_in']:,} / {e['tokens_generated']:,} "
            f"| {fmt((e['energy_kwh_min'] + e['energy_kwh_max']) / 2)} "
            f"| {fmt((e['gwp_kgco2eq_min'] + e['gwp_kgco2eq_max']) / 2 * 1000)} "
            f"| {share:.1f}% | {mapping} |"
        )
    lines.append("")

    # --- Per month ----------------------------------------------------------
    lines.append("## Per month")
    lines.append("")
    lines.append("| Month | Requests | Tokens generated | Energy (kWh) | GWP (gCO2eq) |")
    lines.append("|---|---:|---:|---:|---:|")
    by_month = defaultdict(list)
    for r in modeled:
        by_month[month_of(r)].append(r)
    for month in sorted(by_month):
        group = by_month[month]
        e = {"requests": len(group)}
        for _l, base, _u, _s in METRICS:
            e[f"{base}_min"] = sum_metric(group, base, "min")
            e[f"{base}_max"] = sum_metric(group, base, "max")
        e["tokens_generated"] = sum(int(float(r["tokens_generated"])) for r in group)
        lines.append(
            f"| {month} | {e['requests']:,} | {e['tokens_generated']:,} "
            f"| {fmt((e['energy_kwh_min'] + e['energy_kwh_max']) / 2)} "
            f"| {fmt((e['gwp_kgco2eq_min'] + e['gwp_kgco2eq_max']) / 2 * 1000)} |"
        )
    lines.append("")

    # --- Per agent ----------------------------------------------------------
    lines.append("## Per agent")
    lines.append("")
    lines.append("| Agent | Requests | Tokens generated | GWP (gCO2eq) |")
    lines.append("|---|---:|---:|---:|")
    by_agent = aggregate(modeled, ("agent",))
    for (agent,), e in sorted(by_agent.items(), key=lambda kv: -kv[1]["gwp_kgco2eq_max"]):
        lines.append(
            f"| {agent} | {e['requests']:,} | {e['tokens_generated']:,} "
            f"| {fmt((e['gwp_kgco2eq_min'] + e['gwp_kgco2eq_max']) / 2 * 1000)} |"
        )
    lines.append("")

    # --- Unmodeled ----------------------------------------------------------
    if unmodeled:
        lines.append("## Unmodeled requests")
        lines.append("")
        lines.append("No EcoLogits mapping available; excluded from the totals above.")
        lines.append("")
        lines.append("| Model | Requests | Tokens generated | Status |")
        lines.append("|---|---:|---:|---|")
        by_unmodeled = aggregate(unmodeled, ("model", "status"))
        for (model, status), e in sorted(by_unmodeled.items(), key=lambda kv: -kv[1]["tokens_generated"]):
            lines.append(f"| `{model}` | {e['requests']:,} | {e['tokens_generated']:,} | {status} |")
        lines.append("")

    lines.append("## Notes")
    lines.append("")
    lines.append("- All values are estimates from the [EcoLogits](https://ecologits.ai) methodology; see `docs/methodology.md`.")
    lines.append("- Min/max intervals reflect uncertainty in model architectures (unreleased architectures).")
    lines.append("- Energy is driven by *generated* tokens (output + reasoning) and request latency; input tokens do not enter the model.")
    lines.append("- `estimated-arch` mappings rely on architecture guesses documented in `config/model_mapping.json`.")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--footprint", type=Path, default=DEFAULT_FOOTPRINT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--totals", type=Path, default=DEFAULT_TOTALS)
    args = parser.parse_args()

    if not args.footprint.exists():
        print(f"error: footprint file not found: {args.footprint}", file=sys.stderr)
        print("run scripts/compute_footprint.py first", file=sys.stderr)
        return 1

    rows = load_rows(args.footprint)
    report = render_report(rows, args.footprint)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report)
    print(f"Report written to {args.out}")

    modeled = [r for r in rows if r["status"] == "modeled"]
    totals = {"requests_modeled": len(modeled), "requests_unmodeled": len(rows) - len(modeled)}
    for _l, base, _u, scale in METRICS:
        totals[base] = {
            "min": sum_metric(modeled, base, "min") * scale,
            "max": sum_metric(modeled, base, "max") * scale,
        }
    args.totals.write_text(json.dumps(totals, indent=2))
    print(f"Totals written to {args.totals}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
