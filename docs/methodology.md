# Methodology

This document explains what `opencode-footprint-monitor` measures, how the
numbers are produced, and — just as importantly — what it does *not* measure.
It is aimed at OPERA members who want to understand the assumptions before
quoting the numbers.

## Overview

The tool is a post-hoc ("approach A") monitor: it does not intercept requests.
It reads usage records that OpenCode already stores locally, then feeds them
to the open-source [EcoLogits](https://ecologits.ai) library (by the
[CodeCarbon](https://codecarbon.io) non-profit) to estimate environmental
impacts of the inference requests made through OpenCode.

```
OpenCode (SQLite)          extract_usage.py          compute_footprint.py         report.py
┌──────────────────┐  →   ┌───────────────┐   →    ┌───────────────┐    →    ┌─────────┐
│ per-message rows │      │ requests.jsonl │        │ footprint.csv  │         │ report  │
│ tokens, latency  │      │ (one/request)  │        │ + EcoLogits   │         │ (md)    │
└──────────────────┘      └───────────────┘        └───────────────┘         └─────────┘
```

## Data source

OpenCode persists every message in a local SQLite database
(`~/.local/share/opencode/opencode.db`). For each assistant message it stores,
among other things:

- `modelID`, `providerID` (e.g. `glm-5.3`, `cortecs`)
- token counters: `input`, `output`, `reasoning`, `cache.read`, `cache.write`
- `cost` (USD, as billed by the router)
- `time.created` / `time.completed` (ms) → measured request latency

Two facts we verified in the OpenCode source (`packages/core/src/session/runner/publish-llm-event.ts`)
matter for the accounting:

1. `tokens.output` counts **visible output tokens only**; chain-of-thought
   tokens are counted separately in `tokens.reasoning`.
2. `tokens.input` counts **non-cached** input tokens; cached prompt tokens are
   in `tokens.cache.read`.

**Which tokens drive the estimate.** The EcoLogits energy model is driven by
*generated* tokens: we pass `output + reasoning` as the generated-token count.
Prompt tokens are *not* part of the EcoLogits inference-energy model (they are
only reported for information). This is a known limitation of the
methodology (see below).

The extractor keeps only messages that have at least one generated token, no
error, and a completion timestamp; everything else is counted and reported as
skipped (typically failed requests and aborted turns).

## EcoLogits impact model

For each request, EcoLogits computes (see
[their methodology](https://ecologits.ai/latest/methodology/)):

**GPU energy** — a regression on the number of *active* model parameters:

```
E_gpu_per_token = α·exp(β·batch)·N_active + γ     [Wh/token, batch = 64]
```

**Server (idle) energy** — driven by the measured request latency and the
number of GPUs needed to host the model (derived from total parameter count,
16-bit weights, 80 GB GPUs, rounded up to a power of two), divided by the
batch size.

**Datacenter overhead** — multiplication by the provider's PUE (for the
`mistralai` provider profile used for GLM: 1.16) and, for water, the WUE.

**Usage-phase impacts** — electricity consumption multiplied by impact
factors of the electricity mix of a chosen zone. We use **FRA** by default:
GWP = 0.04144 kgCO2eq/kWh, PE = 9.3135 MJ/kWh, ADPe = 4.858e-8 kgSbeq/kWh,
WUE = 3.6737 L/kWh.

**Embodied impacts** — manufacturing of GPUs and servers amortized over a
3-year lifetime, prorated by generation latency and batch size.

The reported impact metrics are:

| Metric | Unit | Meaning |
|---|---|---|
| Energy | kWh | electricity consumed by the request (usage phase) |
| GWP | kgCO2eq | greenhouse gas emissions |
| ADPe | kgSbeq | abiotic depletion of mineral/metal resources |
| PE | MJ | primary energy consumed |
| WCF | L | fresh water consumed and not returned to the source |

When a model's architecture is only partially known (e.g. Claude active
parameter range), EcoLogits propagates the uncertainty: all metrics are
given as **min–max intervals**, not points.

## Model mapping

EcoLogits only knows a fixed list of providers (anthropic, mistralai, openai,
huggingface_hub, cohere, google_genai) and models registered in its
`models.json`. Our models are reached through the cortecs router and the
Albert API, which EcoLogits knows nothing about. `config/model_mapping.json`
therefore declares, for each OpenCode modelID:

- `native` — the exact model exists in the EcoLogits registry
  (e.g. `glm-5.3` → `mistralai/zai-glm-5-3`, registered as a MoE with
  744 B total / 40 B active parameters, tps 119.5, ttft 708 ms);
- `sibling` — the model is not registered, but a registered sibling with the
  same publicly documented architecture is (e.g. `glm-5.1` → `zai-glm-5`);
- `estimated-arch` — the model is not registered at all; we register a custom
  entry with a best-known architecture guess
  (e.g. `devstral-2512` → dense 24 B, `qwen3-coder-30b` → MoE 30.5 B/3.3 B active).

Anything not in the mapping (e.g. `big-pickle`) is reported as **unmodeled**
with its token counts, and excluded from impact totals. Nothing is silently
dropped.

Two provider-level consequences of the mapping are worth knowing:

- The `mistralai` provider profile supplies the datacenter assumptions
  (PUE 1.16, WUE 0.09 L/kWh) used for all GLM/Devstral/Qwen entries.
- The electricity mix zone is *not* taken from the provider profile: we set
  it explicitly (default `FRA` — see `electricity_mix_zone` in the mapping
  config, overridable with `--zone`). This is a deliberate choice: we report
  impacts "as if the inference ran on the French grid". If you prefer the
  provider's own location (Sweden for the mistralai profile, USA for
  anthropic/openai), pass `--zone SWE`/`--zone USA` or `WOR` for the world
  average.

## Assumptions and limitations

Be aware of these when quoting numbers; they are the price of having *any*
number at all.

1. **Routed inference, not owned infrastructure.** The models run on
   third-party infrastructure (cortecs, Albert). We do not know its real PUE,
   WUE, batch size, or hardware; EcoLogits' generic assumptions stand in.
2. **Batch size 64** is assumed for every request. EcoLogits' regression
   shows per-token energy decreases with batch size; real deployments may
   differ substantially.
3. **Prompt processing is not modeled.** Energy scales with generated tokens
   and latency only. Long-context requests are thus *underestimated*
   relative to generation-heavy ones. Our usage is extremely input-heavy
   (hundreds of millions of input tokens), so treat the totals as a lower
   bound of inference energy. Cache reads/writes are recorded in the CSV for
   future refinement.
4. **Architecture guesses** for `estimated-arch` models. The mapping file is
   the single place to correct them; corrections are straightforward.
5. **Latency as measured by the client** includes network and queueing; the
   model uses `min(measured, mode-estimated)` generation latency, so part of
   the measured latency can inflate the server-idle energy term. The default
   `tps`/`ttft` values registered for GLM limit this effect.
6. **Embodied impacts are generic** (H100-class GPU, 3-year amortization)
   and not specific to the actual serving hardware.
7. **The min/max intervals** only capture architecture uncertainty, not the
   other unknowns above. For GLM the registered architecture is a point
   estimate, hence min = max.

In short: the numbers are **order-of-magnitude estimates with transparent
assumptions**, suitable for awareness-raising and tracking relative changes
over time (per month, per model, per agent), rather than audit-grade
accounting.

## Why pin EcoLogits to a git commit?

The PyPI release (0.11.1 at the time of writing) does not include the GLM-5
model family; the GitHub `main` branch does. `pyproject.toml` pins the
library to a specific commit so results are reproducible. When a new PyPI
release catches up, switch the dependency to a version number.

## Sharing at the group level: snapshots

Personal `data/` outputs stay local (they contain per-request detail and
project paths). What is shared is a **monthly snapshot** per member and
machine: aggregate request/token counts, the five impact metrics as
min–max intervals, the electricity mix zone used, the mapping-mode
breakdown and the list of unmodeled models. USD costs, project paths and
session identifiers are deliberately excluded. The format and rules are
documented in `snapshots/README.md`; `scripts/aggregate_group.py` merges
all snapshots into a group report. Snapshots are the stable interchange
format between approach A and future tooling: anything that can produce
the same aggregate (e.g. the live monitoring of approach B) can feed the
same aggregation.

## Related tools

- [CodeCarbon](https://github.com/mlco2/codecarbon) — measures *local*
  compute emissions (your laptop/workstation), not API inference.
- [EcoLogits Calculator](https://calculator.ecologits.ai/) — web UI for
  one-off estimates.
- [ecologits-statusline](https://github.com/DuarteVi/ecologits-statusline),
  [ecologits-vscode](https://github.com/marmelab/ecologits-vscode) —
  community integrations for other coding assistants.
