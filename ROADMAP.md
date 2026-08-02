# Roadmap

Where this project is and what is next. Status keys: **Done**, **In progress**, **Next**, **Later**.

## Where we are

Two fabs supported (JLCPCB, PCBWay), each with a rule file and a paired test board. Rules target KiCad 8 syntax and work unchanged on 9 and 10. CI lints every `.kicad_dru` on push. The rules have been checked against real DRC runs on KiCad 9.0.6 and 10.0.5, not just read.

## Done

| Area | What shipped | What got better |
|---|---|---|
| Versions | KiCad 8 retarget | Off KiCad 7 syntax, re-checked against current JLCPCB capabilities. |
| Structure | Rule refactor, fab-prefixed names | One rule per constraint, each named `JLCPCB: …`, so a violation names the limit it broke. |
| Clearance | Track-to-via split from track-to-PTH | Removed a false-failure class where via clearance was judged by the stricter PTH number. |
| Vias | No blind, buried or micro vias | Catches a via type the standard service cannot build, at design time rather than at quote time. |
| Fabs | PCBWay support, then restructured to mirror JLCPCB | A second fab, and the two files can now be diffed line for line. |
| BGA | Pad-to-trace clearance, net-class scoped | Keyed off a net class after review found the original matched every SMD pad on the board. |
| Tooling | `tools/lint_dru.py` + CI | Structural gate on every push: paren balance, version header, missing constraints, duplicate names, fab prefix, lowercase type literals. |
| Correctness | Silkscreen layer names use `F.SilkS` | Rules survive imported and pre-KiCad-6 boards. Previously a display-name spelling made KiCad discard the whole rule file, silently disabling every rule. |
| Tooling | Linter layer vocabulary | Checks layer names in `(layer …)` clauses, `.Layer` comparisons and `existsOnLayer()`. The only gate that catches this class, since `kicad-cli` reports a rejected rules file as a clean run. |
| Docs | Layer-name section in the README | Documents the display-name trap and the silent-CI warning that hid it. |
| Repo | LICENSE, CONTRIBUTING, issue templates, README rewrite | Basic hygiene for outside contributors. |

## In progress

| Item | Notes |
|---|---|
| Generated rule matrix from per-fab TOML | Move from hand-maintained `.kicad_dru` files to files generated from a single source of truth per fab: 4 variants per fab (2L-1oz, 4L-1oz, 4L-2oz, 6L-1oz), impedance-controlled net classes, and a `--check` drift gate in CI. |

## Next

| Item | Notes |
|---|---|
| PCBWay test cases | PCBWay has no pass/fail example board yet. JLCPCB's is what made the silkscreen bug reproducible, so this is the real coverage gap. |
| Tagged releases | Give people a version to cite and pin. |

## Later

| Item | Notes |
|---|---|
| More fabs | The generator makes a third fab cheap once the TOML format settles. |
| Per-variant test boards | Today one board per fab covers the default variant only. |

## Non-goals

- Replacing KiCad's built-in DRC. These rules add fab capability limits on top of it.
- Guaranteeing a board is manufacturable. Fabs change capabilities; always check the current capability page before ordering.
- Stackup-specific impedance values as gospel. Impedance rules are typical starting points and depend on the stackup you actually order.
