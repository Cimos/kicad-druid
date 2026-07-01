# Design: generated design-rule matrix

Status: **accepted** · Tracking branch: `claude/dru-generator-overhaul`

This document describes the overhaul from hand-maintained `.kicad_dru` files to a
set of files **generated** from a single sourced source-of-truth per fab.

## Why

The rule files are currently hand-edited. That has three problems:

1. **Drift.** JLCPCB and PCBWay files diverged; bugs (lowercase `'track'`,
   missing net tests, un-implemented TODO rules) sat unnoticed for months.
2. **The "Choose between" footgun.** Each file ships variants commented out and
   asks the user to uncomment the right one. Uncomment two and the rules
   silently fight; uncomment none and a rule is missing. None of it is
   DRC-validated because "which variant?" is undefined.
3. **Un-auditable values.** Every numeric limit is buried in an s-expression
   with no machine-readable link to the fab capability it came from.

Generation fixes all three: one reviewable data file per fab holds every value
with its source URL; concrete per-variant files are emitted with no editing
required; and every emitted file is independently lintable and DRC-testable.

## Architecture

```
capabilities/<FAB>.toml     # source of truth: values + source URLs, base + variants + diff pairs
tools/generate_dru.py       # reads TOML, emits concrete .kicad_dru files
tools/lint_dru.py           # existing linter, runs over the generated output
<FAB>/<FAB>-<variant>.kicad_dru   # GENERATED, committed
```

- **No separate template language.** Rule *structure* (names, conditions,
  order, source comments) lives in `generate_dru.py`; rule *values* live in the
  TOML. This keeps conditionals (inner-layer rules only when there are inner
  layers, diff-pair blocks, feature flags) in plain Python instead of inventing
  a mini template engine.
- **Dependency-free.** TOML is read with the stdlib `tomllib` (Python 3.11+);
  no Jinja, no PyYAML.
- **Generated files are committed.** Users (and KiCad) consume files directly
  from the repo; CI regenerates and asserts `git diff` is empty so the committed
  output can never drift from the source.

## Source-of-truth schema (per fab)

```toml
[fab]
name = "JLCPCB"
prefix = "JLCPCB"                 # rule-name prefix, e.g. "JLCPCB: "
capabilities_url = "https://jlcpcb.com/capabilities/pcb-capabilities"

[fab.flags]
avoid_kelvin_test = true          # emit the JLCPCB-specific Kelvin rule
allow_blind_buried = false        # emit the "only through-hole vias" assertion

# Values constant across every variant of this fab. Each may carry a `src`.
[constants]
drill_hole_min   = { v = "0.2mm", src = "…" }
drill_hole_max   = { v = "6.3mm" }
# … all non-varying limits …

# One block per generated file. `over` overrides constants for value-varying rules.
[[variant]]
id = "4L-1oz"
layers = 4
copper = "1oz"
label = "4-layer, 1oz outer"
[variant.over]
trace_width_outer  = { v = "0.09mm" }
trace_spacing_outer= { v = "0.09mm" }
trace_width_inner  = { v = "0.09mm" }
via_hole           = { v = "0.2mm" }

# Impedance-controlled net classes, baked into every generated file (see caveat).
[[diffpair]]
netclass = "100R_Diff"
track_width = "0.2mm"
gap = "0.2mm"
```

Every value is a `{ v, src }` object so the source URL travels with the number
and the eventual capability audit is a diff on one file.

## The matrix (initial scope: focused, ~4–6 per fab)

Only the combinations the fabs actually promote, standard tier:

| id        | layers | copper |
|-----------|--------|--------|
| `2L-1oz`  | 1–2    | 1oz    |
| `4L-1oz`  | 4      | 1oz    |
| `4L-2oz`  | 4      | 2oz    |
| `6L-1oz`  | 6      | 1oz    |

Widening later is data-only — add a `[[variant]]` block. 2-layer variants emit
no inner-layer trace rules.

## Impedance-controlled net classes

Baked into **every** generated file (inert until a user assigns nets to the
class, so they add no matrix dimension). Net-class names as requested plus a
single-ended default:

- `50R` (single-ended)
- `60R_Diff`, `90R_Diff`, `100R_Diff`, `120R_Diff`

Each emits `track_width` + `diff_pair_gap` scoped by `A.NetClass`.

> **Caveat — read this.** Trace width/gap for a target impedance is a function
> of the **stackup** (dielectric height, Dk, copper weight), not a fab-wide
> constant. The values shipped here are **typical starting points for the fab's
> default stackup** and are flagged in-file as such. Users must verify against
> the fab's controlled-impedance stackup table / impedance calculator for their
> actual order. Values will be refined from those tables when they can be
> sourced (the fab sites are currently egress-blocked from CI).

## Legacy files

**Fully replaced.** The hand-edited `JLCPCB/JLCPCB.kicad_dru` and
`PCBWay/PCBWay.kicad_dru` are removed; the generated files are the only
deliverable. Each fab keeps a plainly-named recommended file (an alias of the
most common variant) so existing copy-paste instructions keep working.

## Validation / CI

1. `tools/lint_dru.py` over all generated files (already in CI).
2. **Regeneration in-sync check:** run the generator, fail if `git diff` is
   non-empty — proves committed output matches the source.
3. (Later) optional `kicad-cli pcb drc` against a paired test board.

## Delivery plan

1. **This branch, foundation PR:** DESIGN.md + TOML for both fabs (values seeded
   from today's committed rules) + generator + generated matrix (incl. diff-pair
   classes) + CI in-sync check + README rewrite. Output is behaviour-equivalent
   to today's rules for the standard variant.
2. Refine diff-pair and per-variant values from sourced capability tables once
   reachable.
3. Optional `kicad-cli` DRC golden tests; tag a release.

## Non-goals (for now)

- Fetching live fab capability values in CI (egress-blocked).
- Populating the PCBWay test board (issue #16).
- Adding new fabs — the schema supports it; growth is a follow-up.
