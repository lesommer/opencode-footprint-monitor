# OpenCode environmental footprint report

- Generated: 2026-09-28T23:18:54
- Source: `data/footprint.csv` (22215 requests, 22142 modeled, 73 unmodeled)
- Period: 2026-04-16 to 2026-09-28

## Totals

Over **22,142** modeled requests across **329** sessions:

| Impact | Total (min) | Total (max) | Unit |
|---|---:|---:|---|
| energy | 32.527 | 32.527 | kWh |
| gwp | 3,487.840 | 3,487.840 | gCO2eq |
| adpe | 0.121 | 0.121 | gSbeq |
| pe | 330.019 | 330.019 | MJ |
| wcf | 122.018 | 122.018 | L |

For context: the midpoint GWP estimate is equivalent to about **29.1 km** driven in a typical French car (~120 gCO2eq/km).

## Per model

| Model | Requests | Tokens (in/gen) | Energy (kWh) | GWP (gCO2eq) | Share of GWP | Mapping |
|---|---:|---:|---:|---:|---:|---|
| `glm-5.1` | 16,116 | 207,438,912 / 6,302,143 | 22.346 | 2,550.255 | 73.1% | sibling |
| `glm-5.3` | 4,338 | 126,006,898 / 3,082,217 | 9.484 | 875.944 | 25.1% | native |
| `glm-5.2` | 268 | 14,635,709 / 210,559 | 0.635 | 56.649 | 1.6% | native |
| `devstral-2512` | 1,220 | 42,488,121 / 307,166 | 0.026 | 2.547 | 0.1% | estimated-arch |
| `glm-5.3-flash` | 183 | 6,915,137 / 140,654 | 0.035 | 2.417 | 0.1% | estimated-arch |
| `glm-4.7-flash` | 4 | 39,352 / 608 | 2.06e-04 | 0.024 | 0.0% | estimated-arch |
| `qwen3-coder-30b` | 8 | 15,572 / 328 | 2.50e-05 | 0.003 | 0.0% | estimated-arch |
| `ministral-3-8b` | 1 | 3,085 / 1 | 1.37e-06 | 3.40e-04 | 0.0% | sibling |
| `gpt-oss-120b` | 3 | 9,460 / 7 | 2.23e-06 | 2.88e-04 | 0.0% | native |
| `mistral-small-3.2-24b` | 1 | 3,112 / 12 | 1.26e-06 | 1.61e-04 | 0.0% | estimated-arch |

## Per month

| Month | Requests | Tokens generated | Energy (kWh) | GWP (gCO2eq) |
|---|---:|---:|---:|---:|
| 2026-04-01 | 2,229 | 903,152 | 1.741 | 141.592 |
| 2026-05-01 | 3,917 | 1,688,957 | 5.429 | 539.576 |
| 2026-06-01 | 11,168 | 3,987,153 | 15.119 | 1,865.547 |
| 2026-09-01 | 4,828 | 3,464,433 | 10.239 | 941.125 |

## Per agent

| Agent | Requests | Tokens generated | GWP (gCO2eq) |
|---|---:|---:|---:|
| build | 14,453 | 5,469,119 | 2,000.769 |
| plan | 5,404 | 2,996,446 | 1,111.132 |
| explore | 1,404 | 1,114,696 | 245.464 |
| general | 801 | 307,093 | 90.492 |
| compaction | 68 | 150,130 | 38.452 |
| reviewer | 4 | 5,883 | 1.528 |
| gh | 8 | 328 | 0.003 |

## Unmodeled requests

No EcoLogits mapping available; excluded from the totals above.

| Model | Requests | Tokens generated | Status |
|---|---:|---:|---|
| `minimax-m2.5-free` | 21 | 2,649 | unmodeled |
| `<model-id>` | 33 | 1,808 | unmodeled |
| `big-pickle` | 15 | 1,543 | unmodeled |
| `minimax-m3-free` | 2 | 229 | unmodeled |
| `mimo-v2.6-flash-free` | 1 | 53 | unmodeled |
| `kimi-k2.6` | 1 | 36 | unmodeled |

## Notes

- All values are estimates from the [EcoLogits](https://ecologits.ai) methodology; see `docs/methodology.md`.
- Min/max intervals reflect uncertainty in model architectures (unreleased architectures).
- Energy is driven by *generated* tokens (output + reasoning) and request latency; input tokens do not enter the model.
- `estimated-arch` mappings rely on architecture guesses documented in `config/model_mapping.json`.
