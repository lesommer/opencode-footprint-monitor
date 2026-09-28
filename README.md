# opencode-footprint-monitor

Documentation + code for monitoring the environmental footprint of querying
LLMs through [OpenCode](https://opencode.ai), using the open-source
[EcoLogits](https://ecologits.ai) library.

**Approach A (this repo):** post-hoc analysis. The scripts read the usage
data OpenCode already stores locally (token counts, model, latency per
request), run it through EcoLogits' impact model, and produce a Markdown
report with totals and breakdowns. All computation is local; nothing is
sent anywhere.

**Approach B (planned):** live monitoring via a LiteLLM proxy with
EcoLogits OpenTelemetry export — see *Roadmap* below.

## Quickstart

Requires [uv](https://docs.astral.sh/uv/) (or Python ≥ 3.11 + pip, see the
[guide](docs/opera-guide.md)):

```bash
uv sync
uv run scripts/extract_usage.py      # ~/.local/share/opencode/opencode.db → data/requests.jsonl
uv run scripts/compute_footprint.py  # + EcoLogits → data/footprint.csv
uv run scripts/report.py             # → data/report.md
```

See a real output in [docs/example-report.md](docs/example-report.md).

## Repository layout

```
config/model_mapping.json   OpenCode modelIDs → EcoLogits registry entries
                            (native / sibling / estimated-arch mappings)
scripts/extract_usage.py    read-only extraction from the OpenCode DB
scripts/compute_footprint.py  EcoLogits impact computation per request
scripts/report.py           aggregation into a Markdown report + totals.json
scripts/snapshot.py         monthly personal snapshot for group sharing
scripts/aggregate_group.py  merge member snapshots into a group report
snapshots/                  shared monthly member snapshots (see snapshots/README.md)
docs/methodology.md         what is measured, assumptions, limitations
docs/opera-guide.md         step-by-step guide for OPERA members
```

## Group sharing

Members run the pipeline locally and contribute one small JSON snapshot per
month (aggregate numbers only — no paths, no costs); `aggregate_group.py`
produces the group report. See [snapshots/README.md](snapshots/README.md).

## What it reports

Per request and aggregated (min–max intervals): **energy** (kWh), **GWP**
(greenhouse gases), **ADPe** (mineral resource depletion), **PE** (primary
energy), **WCF** (water) — plus per model / per month / per agent breakdowns,
and an explicit list of requests that could not be modeled.

The methodology, assumptions and their limits are detailed in
[docs/methodology.md](docs/methodology.md). Short version: order-of-magnitude
estimates with transparent assumptions, ideal for tracking *relative*
changes over time; not audit-grade accounting.

## Roadmap

- [x] Approach A — post-hoc footprint from local OpenCode history
- [x] Monthly snapshots + group aggregation
- [ ] Approach B — live monitoring: LiteLLM proxy + EcoLogits OpenTelemetry
      export, Prometheus/Grafana dashboard (see open issues)
- [ ] Wiki section in the OPERA knowledge base (content pending review)
- [ ] Trend tracker (compare dated report snapshots)

## References

- EcoLogits: https://ecologits.ai — library by the
  [CodeCarbon](https://codecarbon.io) non-profit (MPL-2.0), pinned to a git
  commit in `pyproject.toml` (the PyPI release lags behind the model
  registry).
- OpenCode local data: `~/.local/share/opencode/opencode.db` (SQLite,
  `message` table).
