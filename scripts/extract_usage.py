#!/usr/bin/env python3
"""Extract per-request LLM usage data from the local OpenCode database.

Scans the OpenCode SQLite database (read-only) and writes one JSON record
per assistant message with token usage, latency and metadata. The output is
the input of `compute_footprint.py`.

Usage:
    uv run scripts/extract_usage.py [--db PATH] [--out PATH]
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = Path.home() / ".local" / "share" / "opencode" / "opencode.db"
DEFAULT_OUT = Path(__file__).resolve().parent.parent / "data" / "requests.jsonl"

SKIP_REASON_HELP = {
    "not_assistant": "message is not an assistant message",
    "error": "request failed (error field present)",
    "no_tokens": "zero generated tokens (output + reasoning)",
    "no_completion_time": "request never completed",
}


def open_readonly(db_path: Path) -> tuple[sqlite3.Connection, Path]:
    """Connect to a snapshot copy of the database to never touch the live file."""
    tmpdir = Path(tempfile.mkdtemp(prefix="opencode-fm-"))
    snapshot = tmpdir / "opencode.db"
    shutil.copy2(db_path, snapshot)
    for suffix in ("-wal", "-shm"):
        extra = db_path.with_name(db_path.name + suffix)
        if extra.exists():
            shutil.copy2(extra, snapshot.with_name(snapshot.name + suffix))
    conn = sqlite3.connect(f"file:{snapshot}?mode=ro", uri=True)
    return conn, snapshot


def to_iso(ms: int | None) -> str | None:
    if ms is None:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def extract(db_path: Path, out_path: Path) -> dict:
    conn, snapshot = open_readonly(db_path)
    try:
        rows = conn.execute(
            "SELECT id, session_id, data FROM message ORDER BY time_created, id"
        ).fetchall()
    finally:
        conn.close()
        shutil.rmtree(snapshot.parent, ignore_errors=True)

    stats = Counter()
    per_model_tokens: dict[str, dict[str, float]] = {}
    records = []
    for msg_id, session_id, raw in rows:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            stats["not_assistant"] += 1
            continue

        if data.get("role") != "assistant":
            stats["not_assistant"] += 1
            continue

        tokens = data.get("tokens") or {}
        output = tokens.get("output") or 0
        reasoning = tokens.get("reasoning") or 0
        generated = output + reasoning
        if data.get("error"):
            stats["error"] += 1
            continue
        if generated <= 0:
            stats["no_tokens"] += 1
            continue

        time = data.get("time") or {}
        completed = time.get("completed")
        if completed is None:
            stats["no_completion_time"] += 1
            continue

        created = time.get("created")
        latency_s = (completed - created) / 1000.0 if created else None
        if latency_s is not None and latency_s < 0:
            latency_s = None

        model = data.get("modelID") or "<unknown>"
        m = per_model_tokens.setdefault(model, Counter())
        m["requests"] += 1
        m["tokens_out"] += output
        m["tokens_reasoning"] += reasoning
        m["tokens_in"] += tokens.get("input") or 0

        cache = tokens.get("cache") or {}
        records.append(
            {
                "msg_id": msg_id,
                "session_id": session_id,
                "ts": to_iso(created),
                "model": model,
                "opencode_provider": data.get("providerID"),
                "agent": data.get("agent"),
                "mode": data.get("mode"),
                "project": (data.get("path") or {}).get("cwd"),
                "tokens_input": tokens.get("input") or 0,
                "tokens_cache_read": cache.get("read") or 0,
                "tokens_cache_write": cache.get("write") or 0,
                "tokens_output": output,
                "tokens_reasoning": reasoning,
                "tokens_generated": generated,
                "latency_s": latency_s,
                "cost_usd": data.get("cost") or 0.0,
            }
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as fd:
        for rec in records:
            fd.write(json.dumps(rec) + "\n")

    return {
        "db_path": str(db_path),
        "out_path": str(out_path),
        "total_messages": len(rows),
        "kept": len(records),
        "skipped": dict(stats),
        "per_model": per_model_tokens,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="OpenCode SQLite database")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Output JSONL file")
    args = parser.parse_args()

    if not args.db.exists():
        print(f"error: database not found: {args.db}", file=sys.stderr)
        return 1

    result = extract(args.db, args.out)

    print(f"Database      : {result['db_path']}")
    print(f"Output        : {result['out_path']}")
    print(f"Messages      : {result['total_messages']} total")
    print(f"Kept          : {result['kept']} usable requests")
    if result["skipped"]:
        print("Skipped       :")
        for reason, count in sorted(result["skipped"].items()):
            print(f"  - {reason:20s} {count:6d}  ({SKIP_REASON_HELP.get(reason, '')})")
    print()
    print(f"{'model':24s} {'requests':>9s} {'in':>10s} {'out':>10s} {'reasoning':>10s}")
    for model, m in sorted(result["per_model"].items(), key=lambda kv: -kv[1]["tokens_out"]):
        print(f"{model:24s} {m['requests']:9d} {m['tokens_in']:10.0f} {m['tokens_out']:10.0f} {m['tokens_reasoning']:10.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
