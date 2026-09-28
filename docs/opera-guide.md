# OPERA guide: monitor the footprint of your OpenCode usage

This guide takes you from zero to a footprint report of your own OpenCode
usage in about ten minutes. You need:

- a machine where you use [OpenCode](https://opencode.ai) regularly
  (its local database must exist: `~/.local/share/opencode/opencode.db`)
- [uv](https://docs.astral.sh/uv/) (or Python ≥ 3.11 with pip)
- an internet connection for the first install (EcoLogits is fetched from
  GitHub; requests are *not* sent anywhere — all computation is local)

## 1. Get the tool

```bash
git clone <this-repo-url>
cd opencode-footprint-monitor
uv sync          # creates .venv and installs ecologits (pinned commit)
```

(With plain pip instead of uv: `python -m venv .venv && source .venv/bin/activate && pip install "ecologits @ git+https://github.com/mlco2/ecologits.git@5d40d5316cb3b8da0b5267d9786c4c04585d0929"`.)

## 2. Check the model mapping

Open `config/model_mapping.json` and look for the model IDs you use
(in a session, `/models` shows them; or peek at the report of step 3 —
unmapped models appear in the "Unmodeled requests" table).

- Your model is listed → nothing to do.
- Not listed but you know a registered EcoLogits model with the same
  architecture → add an entry with `"mapping": "sibling"`.
- Not listed and unregistered anywhere → add an entry with
  `"mapping": "estimated-arch"` and a `custom_architecture` guess, and note
  your source in the `note` field.

To discover what EcoLogits knows:

```bash
uv run python - <<'EOF'
from ecologits.model_repository import ModelRepository
for m in ModelRepository.from_json().list_models():
    print(m.provider.value, m.name)
EOF
```

## 3. Run the pipeline

```bash
uv run scripts/extract_usage.py      # OpenCode DB  → data/requests.jsonl
uv run scripts/compute_footprint.py  # + EcoLogits  → data/footprint.csv
uv run scripts/report.py             # aggregates   → data/report.md
```

The database is opened read-only via a snapshot copy; your live OpenCode
data is never touched.

Useful options:

- `--zone FRA` on `compute_footprint.py` — electricity mix
  (default `FRA` from the mapping config; `WOR` = world average).
- `--db PATH` on `extract_usage.py` — non-default OpenCode install.
- `--out` on each script — write elsewhere.

## 4. Read the report

`data/report.md` contains:

- **Totals** with min/max intervals and a car-km communication aid;
- **Per model** breakdown (requests, tokens, energy, GWP, share);
- **Per month** and **per agent** breakdowns;
- **Unmodeled requests** — anything excluded, with token counts.

Interpretation rules of thumb:

- Compare *relative* changes (month over month, model swaps) rather than
  absolute values; the absolute scale relies on generic datacenter
  assumptions (see `docs/methodology.md`).
- Inputs dominate your token counts but are not in the energy model —
  the estimates are best read as a lower bound for input-heavy workflows.
- When you switch models, check both the GWP column *and* the mapping
  column: a fancy new model mapped with `estimated-arch` carries extra
  uncertainty.

## 5. Share your results with the group

Once a month, turn your results into a **snapshot** — a small JSON file with
aggregate numbers only (no project paths, no session IDs, no costs):

```bash
uv run scripts/snapshot.py --member <your-name>   # last month found in your data
# or: uv run scripts/snapshot.py --member <your-name> --all   (backfill every month)
```

Then commit `snapshots/YYYY-MM/<your-name>-<machine>.json` and open a pull
request (or send the file to the maintainer). The naming, cadence and
privacy rules are described in `snapshots/README.md`.

Anyone can produce the group report from all contributed snapshots:

```bash
uv run scripts/aggregate_group.py   # → data/group-report.md
```

Use a neutral `--machine` name (e.g. `laptop`, `office-desktop`): the
default is your hostname, which may be more identifying than you want.

## 6. Repeat / automate

Re-run the three scripts whenever you want a fresh picture (they are
idempotent and cheap: ~25k requests take a few seconds). A minimal cron /
launchd wrapper or a git hook is enough to keep monthly snapshots; storing
dated copies of `report.md` lets you track trends.

## FAQ

**Does this send my data anywhere?** No. Everything runs locally; the only
network access is the initial `uv sync` install of the EcoLogits library.

**Why are glm-5.1 totals "modeled" although glm-5.1 is not in EcoLogits?**
It is mapped to the registered GLM-5 sibling with the same published
architecture; the report labels this `sibling` so readers can see it.

**Why is my usage 0 for months where I used OpenCode?** The extractor reads
the local database of the machine you run it on. Multiple workstations =
multiple databases; run it on each — the snapshots sum correctly at the
group level.

**Can I trust the car-km comparison?** As a communication aid only. It
converts the midpoint GWP estimate at ~120 gCO2eq/km (typical French car,
well-to-wheel). Its purpose is to make orders of magnitude tangible, not to
provide a precise equivalence.
