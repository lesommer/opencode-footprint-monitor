#!/usr/bin/env python3
"""Compute EcoLogits environmental impact estimates for extracted requests.

Reads the JSONL produced by `extract_usage.py`, maps OpenCode modelIDs to the
EcoLogits model registry (see config/model_mapping.json), computes per-request
impacts and writes a CSV with min/max intervals.

Usage:
    uv run scripts/compute_footprint.py [--requests PATH] [--mapping PATH]
                                        [--out PATH] [--zone FRA]
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

from ecologits.tracers.utils import llm_impacts

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REQUESTS = REPO_ROOT / "data" / "requests.jsonl"
DEFAULT_MAPPING = REPO_ROOT / "config" / "model_mapping.json"
DEFAULT_OUT = REPO_ROOT / "data" / "footprint.csv"

IMPACT_FIELDS = {
    "energy": ("energy_kwh", "kWh"),
    "gwp": ("gwp_kgco2eq", "kgCO2eq"),
    "adpe": ("adpe_kgsbeq", "kgSbeq"),
    "pe": ("pe_mj", "MJ"),
    "wcf": ("wcf_l", "L"),
}

CSV_FIELDS = [
    "msg_id",
    "session_id",
    "ts",
    "model",
    "opencode_provider",
    "agent",
    "mode",
    "project",
    "tokens_input",
    "tokens_cache_read",
    "tokens_cache_write",
    "tokens_output",
    "tokens_reasoning",
    "tokens_generated",
    "latency_s",
    "cost_usd",
    "status",
    "mapping",
    "energy_kwh_min",
    "energy_kwh_max",
    "gwp_kgco2eq_min",
    "gwp_kgco2eq_max",
    "adpe_kgsbeq_min",
    "adpe_kgsbeq_max",
    "pe_mj_min",
    "pe_mj_max",
    "wcf_l_min",
    "wcf_l_max",
    "warnings",
]


def load_mapping(path: Path) -> dict:
    with path.open() as fd:
        return json.load(fd)


def register_custom_models(mapping: dict) -> None:
    """Add models with a `custom_architecture` to the EcoLogits global registry.

    `llm_impacts()` reads the module-level repository of `ecologits.model_repository`,
    so we import and mutate that exact instance.
    """
    import ecologits.model_repository as mr

    for oc_model, entry in mapping.get("models", {}).items():
        arch = entry.get("custom_architecture")
        if not arch:
            continue
        model = {
            "type": "model",
            "provider": entry["ecologits_provider"],
            "name": entry["ecologits_name"],
            "architecture": {
                "type": arch["type"],
                "parameters": (
                    {"total": arch["total"], "active": arch["active"]}
                    if arch["type"] == "moe"
                    else arch["parameters"]
                ),
            },
            "warnings": None,
            "sources": [],
            "deployment": None,
        }
        mr.models.add_model(model)


def range_bounds(value) -> tuple[float, float]:
    """Return (min, max) from an EcoLogits ValueOrRange."""
    if value is None:
        return float("nan"), float("nan")
    vmin = getattr(value, "min", None)
    vmax = getattr(value, "max", None)
    if vmin is None and vmax is None:
        v = float(value)
        return v, v
    vmin = float(vmin if vmin is not None else vmax)
    vmax = float(vmax if vmax is not None else vmin)
    return vmin, vmax


def compute(requests_path: Path, mapping_path: Path, out_path: Path, zone: str) -> dict:
    mapping = load_mapping(mapping_path)
    if zone is None:
        zone = mapping.get("electricity_mix_zone", "FRA")
    register_custom_models(mapping)
    model_map = mapping.get("models", {})

    rows = []
    n_modeled = n_unmodeled = 0
    unmodeled_models: dict[str, dict[str, float]] = {}

    with requests_path.open() as fd:
        for line in fd:
            req = json.loads(line)
            row = {field: req.get(field) for field in CSV_FIELDS[:16]}
            row["status"] = "unmodeled"
            row["mapping"] = None
            row["warnings"] = None
            for field in CSV_FIELDS[17:]:
                row[field] = None

            entry = model_map.get(req["model"])
            if entry is None:
                n_unmodeled += 1
                m = unmodeled_models.setdefault(req["model"], Counter())
                m["requests"] += 1
                m["tokens_generated"] += req["tokens_generated"]
                rows.append(row)
                continue

            latency = req.get("latency_s") or 1.0
            impacts = llm_impacts(
                provider=entry["ecologits_provider"],
                model_name=entry["ecologits_name"],
                output_token_count=req["tokens_generated"],
                request_latency=max(latency, 0.001),
                electricity_mix_zone=zone,
            )

            if impacts.has_errors:
                n_unmodeled += 1
                m = unmodeled_models.setdefault(req["model"], Counter())
                m["requests"] += 1
                m["tokens_generated"] += req["tokens_generated"]
                row["status"] = f"error: {impacts.errors[0].code}"
                rows.append(row)
                continue

            row["status"] = "modeled"
            row["mapping"] = entry["mapping"]
            for key, (csv_base, _unit) in IMPACT_FIELDS.items():
                vmin, vmax = range_bounds(getattr(impacts, key).value)
                row[f"{csv_base}_min"] = vmin
                row[f"{csv_base}_max"] = vmax
            if impacts.warnings:
                row["warnings"] = ";".join(w.code for w in impacts.warnings)
            n_modeled += 1
            rows.append(row)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="") as fd:
        writer = csv.DictWriter(fd, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    return {
        "requests_path": str(requests_path),
        "mapping_path": str(mapping_path),
        "out_path": str(out_path),
        "zone": zone,
        "modeled": n_modeled,
        "unmodeled": n_unmodeled,
        "unmodeled_models": unmodeled_models,
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requests", type=Path, default=DEFAULT_REQUESTS)
    parser.add_argument("--mapping", type=Path, default=DEFAULT_MAPPING)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--zone",
        default=None,
        help="ISO 3166-1 alpha-3 electricity mix zone (default: value from mapping config)",
    )
    args = parser.parse_args()

    if not args.requests.exists():
        print(f"error: requests file not found: {args.requests}", file=sys.stderr)
        print("run scripts/extract_usage.py first", file=sys.stderr)
        return 1

    result = compute(args.requests, args.mapping, args.out, args.zone)

    print(f"Requests file : {result['requests_path']}")
    print(f"Mapping file  : {result['mapping_path']}")
    print(f"Output        : {result['out_path']}")
    print(f"Mix zone      : {result['zone']}")
    print(f"Modeled       : {result['modeled']} requests")
    print(f"Unmodeled     : {result['unmodeled']} requests")
    for model, m in sorted(result["unmodeled_models"].items(), key=lambda kv: -kv[1]["tokens_generated"]):
        print(f"  - {model}: {m['requests']:.0f} requests, {m['tokens_generated']:.0f} generated tokens")
    return 0


if __name__ == "__main__":
    sys.exit(main())
