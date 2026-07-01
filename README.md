# KiCad Custom Design Rules

Custom design rules for KiCad that match the manufacturing capabilities of common PCB fab houses. Rules are stored in `.kicad_dru` files and validated against a paired test board (`.kicad_pcb`) so each rule has at least one footprint that passes or fails as expected.

The rules are authored against the KiCad 8 custom-rules syntax and are forward-compatible with **KiCad 9 and 10** — every token used here is unchanged across those releases (KiCad 9/10 only add new constraints on top). If you're on KiCad 8, 9, or 10, they just work.

> Maintained fork of [labtroll/KiCad-DesignRules](https://github.com/labtroll/KiCad-DesignRules), which has been inactive since November 2024.

## Supported fabs

| Fab    | Folder                | Source of capabilities                            |
|--------|-----------------------|---------------------------------------------------|
| JLCPCB | [`JLCPCB/`](JLCPCB/)  | https://jlcpcb.com/capabilities/pcb-capabilities  |
| PCBWay | [`PCBWay/`](PCBWay/)  | https://www.pcbway.com/capabilities.html          |

Each folder contains one `.kicad_dru` per build variant, plus a small test board (`.kicad_pcb`, `.kicad_sch`, `.kicad_pro`) exercising the rules.

The rule files are **generated** from a single source of truth per fab (`capabilities/<FAB>.toml`) by `tools/generate_dru.py` — so there are no "uncomment the right variant" comment blocks to get wrong. Pick the whole file that matches what you're ordering:

| File | Layers | Copper |
|------|--------|--------|
| `<FAB>.kicad_dru` | 4 (recommended default) | 1oz |
| `<FAB>-2L-1oz.kicad_dru` | 1–2 | 1oz |
| `<FAB>-4L-2oz.kicad_dru` | 4 | 2oz |
| `<FAB>-6L-1oz.kicad_dru` | 6 | 1oz |

> **Editing rules:** change `capabilities/<FAB>.toml` and re-run `python3 tools/generate_dru.py`. Do **not** hand-edit the generated `.kicad_dru` files — CI regenerates and fails if they drift from the source.

## Use in your project

1. Copy the `.kicad_dru` matching your order from `JLCPCB/` or `PCBWay/` into your KiCad project folder.
2. Rename it to match your project: `your-project.kicad_dru`.
3. KiCad picks it up automatically. View under `File > Board Setup > Design Rules > Custom Rules`.
4. Run `Inspect > Design Rules Checker` (or press F8) to apply.

### Impedance-controlled routing

Every file ships net classes for impedance-controlled routing: `50R` (single-ended) and `60R_Diff` / `90R_Diff` / `100R_Diff` / `120R_Diff` (differential). Assign nets to the matching class in `Board Setup > Net Classes`; unassigned classes do nothing.

> ⚠️ The shipped width/gap values are **typical starting points for the fab's default stackup**. Impedance depends on your actual stackup — verify against the fab's impedance calculator and adjust the values for your order.

## Validation

CI does two checks (both dependency-free Python):

- **In-sync** — `python3 tools/generate_dru.py --check` fails if the committed `.kicad_dru` files don't match what `capabilities/*.toml` would generate.
- **Lint** — `tools/lint_dru.py` catches malformed s-expressions, missing `(version 1)` headers, rules with no constraint, duplicate names, wrong fab prefixes, and lowercase item-type literals (`'track'`/`'via'`/`'pad'`) that KiCad silently never matches.

Run them locally with:

```
python3 tools/generate_dru.py --check
python3 tools/lint_dru.py
```

The linter is a fast syntax/consistency gate — KiCad has no standalone `.kicad_dru` validator. For a full electrical DRC, KiCad 8+ can run the rules headlessly against the paired test board:

```
kicad-cli pcb drc --exit-code-violations --severity-error JLCPCB/JLCPCB.kicad_pcb
```

## KiCad documentation

- [Custom Design Rules (8.0)](https://docs.kicad.org/8.0/en/pcbnew/pcbnew.html#custom-design-rules) — the syntax these rules are written against
- [Design Rules Check (8.0)](https://docs.kicad.org/8.0/en/pcbnew/pcbnew.html#design_rule_checking)
- [KiCad CLI reference](https://docs.kicad.org/en/cli/cli.html) — `kicad-cli pcb drc` for headless checking

## Contributing

Bug reports, capability updates, and PRs are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for the conventions used in this repo.

## License

[MIT](LICENSE)
