# Footprint snapshots

This directory holds the **monthly footprint snapshots** shared at the
OPERA group level. One snapshot = one member + one machine + one month.

## How to contribute

1. Run the pipeline on your machine (see `docs/opera-guide.md`):

   ```bash
   uv sync
   uv run scripts/extract_usage.py
   uv run scripts/compute_footprint.py
   ```

2. Create your snapshot(s):

   ```bash
   # last month found in your data:
   uv run scripts/snapshot.py --member <your-name>

   # or backfill every month in your OpenCode history:
   uv run scripts/snapshot.py --member <your-name> --all
   ```

3. Commit the generated `snapshots/YYYY-MM/<your-name>-<machine>.json`
   and open a pull request (or send the file to the repository maintainer).

Cadence: **once a month** is enough (snapshot the last month). Re-running
`--all` also works: re-generated snapshots replace the previous ones since
the pipeline recomputes from the full history.

## File format

`<member>-<machine>.json` in a `YYYY-MM/` directory. The file contains
aggregate numbers only:

- requests (total / modeled / unmodeled) and token counts
- the five impact metrics as min–max intervals:
  energy (kWh), GWP (kgCO2eq), ADPe (kgSbeq), PE (MJ), WCF (water, L)
- the electricity mix zone used, the mapping-mode breakdown, and the list
  of models that could not be modeled

It deliberately contains **no** personal content: no project paths, no
session IDs, no prompts, no USD costs.

## Aggregation

Anyone can produce the group report by running:

```bash
uv run scripts/aggregate_group.py   # → data/group-report.md
```

## Notes

- Snapshots are estimates under generic assumptions (see
  `docs/methodology.md`); they are meant for awareness and relative
  trends, not audit-grade accounting.
- If you use several machines, produce one snapshot per machine
  (`--machine <name>`); they sum correctly at the group level.
- The schema is versioned (`schema_version`); incompatible versions are
  skipped by the aggregator with a warning.
