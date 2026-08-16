# Altium rule generation and the shared capability source

**Date:** 2026-08-16
**Status:** design agreed, not yet implemented
**Affects:** a new `fab-capabilities` repo, a new `altium-druid` repo, and `kicad-druid` (phase 1 only)

## Problem

`kicad-druid` generates KiCad `.kicad_dru` files from per-fab TOML describing what a PCB house can actually build. The same data should drive Altium Designer rule files, so a board team on either tool gets limits that track the fab's published page.

Two things make this worth doing rather than hand-maintaining a second set:

- Every Altium fab rule set in circulation is a hand-exported static file. OSH Park publishes theirs with a written warning that drill size, trace width, spacing and polygon clearance contain known discrepancies. No project generates Altium rules from live capability data.
- The values are already maintained, reviewed and validated once. A second hand-maintained copy would drift the first time only one is updated.

## Decisions

Four forks were settled before this document.

| Decision | Choice | Why |
|---|---|---|
| Where values live | A new `fab-capabilities` repo is the editing desk | One direction, one owner, no sync machinery |
| Contributor flow | Value changes are one PR against `fab-capabilities` | Accepted cost: PRs will still land on `kicad-druid` and need redirecting |
| How consumers get data | Vendored copy plus a pinned upstream tag, checked in CI | A submodule leaves `capabilities/` empty on a plain clone and breaks the generator |
| Emitter approach | Generate from the documented grammar, verified against a real exported fixture | Fully data-driven, with a known-good reference guarding the grammar |

## Architecture

```
fab-capabilities/                  the editing desk
  capabilities/JLCPCB.toml
  capabilities/PCBWay.toml
  fabdata/loader.py                Fab, load(), validate(), VALUE_KEYS
  tests/
  tagged releases: v1.0.0, v1.1.0, ...

        |                                  |
        v                                  v

kicad-druid/                        altium-druid/            (new)
  capabilities/*.toml   vendored      capabilities/*.toml  vendored
  capabilities/UPSTREAM pin           capabilities/UPSTREAM pin
  tools/generate_dru.py               tools/generate_rul.py
  tools/lint_dru.py                   tools/lint_rul.py
  JLCPCB/*.kicad_dru                  tests/fixtures/golden-*.RUL
  PCBWay/*.kicad_dru                  JLCPCB/*.RUL
```

### fab-capabilities

Holds the data and the code that loads and validates it. The loader is lifted from `kicad-druid/tools/generate_dru.py` as it stands after the hardening work of 2026-08-16: `Fab`, `make_val`, `validate`, `check_dimension`, `VALUE_KEYS`, `ALLOWED_FLAGS`, `VARIANT_KEYS`, `DIFFPAIR_KEYS`.

Moving the validator rather than copying it means the Altium emitter inherits, on day one, the protections that took a review cycle to find: dimensional values must be a positive number with an `mm` suffix, `layers` is required as a positive integer, and unknown keys are rejected in every table.

Rule *structure* does not move. Rule names, scopes and ordering are properties of the target tool, so each emitter owns its own.

Releases are tagged. Consumers pin a tag, never a branch.

### Consumer contract

Each consumer commits a copy of the TOML files and records the upstream tag it came from:

```
kicad-druid/capabilities/
  JLCPCB.toml         committed copy — a plain clone works
  PCBWay.toml
  UPSTREAM            v1.2.0
```

`UPSTREAM` is a one-line text file holding nothing but the `fab-capabilities` tag name. A CI job clones that repo at that tag, diffs its `capabilities/*.toml` against the vendored copies, and fails on any difference. Updating is a mechanical PR: bump `UPSTREAM`, copy the files, regenerate, commit.

This keeps `git clone` working for anyone downloading rules or running tests, gives an explicit and readable version pin, and reuses the drift-gate pattern the project already runs for generated output.

## The Altium emitter

### File format

A `.RUL` file is plain 8-bit text. One rule per line; each line is a flat list of `KEY=VALUE` pairs joined by `|`, terminated by a literal pilcrow (`¶`, byte `0xB6`) and CRLF. Keys are uppercase and exact.

Verified against two independently authored real files — a JLCPCB set and a PCBWay set — which share the grammar and differ only in values.

Import path: `Design » Rules` → right-click the rule tree → **Import Rules** → choose rule types → select file. Altium's documentation for this was last updated 5 August 2026.

### Priority inversion

Altium walks rules from highest priority to lowest and applies **the first** whose scope matches, with `PRIORITY=1` being highest. KiCad applies **the last** matching rule.

The emitter therefore cannot mirror KiCad's file order. It assigns explicit priorities from a declared ordering table, placing specific rules ahead of the catch-alls they must beat. A test asserts that a specific rule outranks the catch-all which would otherwise shadow it.

This is stated prominently because the same class of fault — a specific rule silently losing to a general one — was found twice in `kicad-druid` during review. It is handled deliberately, not left to emission order.

### Unit encoding

Two encodings appear on the same line:

- Most dimensions are unit-suffixed strings: `GAP=5mil`, `MINLIMIT=5mil`.
- `OBJECTCLEARANCES` uses raw integers in Altium's internal unit of 1/10000 mil: `98425` is 9.8425 mil, which is 0.25 mm.

Source data is in millimetres. Conversion lives in one module with tests pinning known pairs in both directions. Output uses `mil`, matching both observed real files; `mm` acceptance in `.RUL` is unverified and not relied upon.

### Rule identity

`UNIQUEID` is eight uppercase letters, distinct per rule. The emitter derives it deterministically from the rule name so that regenerating produces byte-identical output. The `--check` drift gate depends on that stability, exactly as `kicad-druid` does.

### Rule mapping

| Capability limit | Altium `RULEKIND` |
|---|---|
| Trace width minimum | `Width` |
| Copper clearance, different nets | `Clearance` |
| Hole size min/max | `HoleSize` |
| Via diameter and hole | `RoutingVias` |
| Annular ring | `MinimumAnnularRing` — one value per rule, so PTH and via need separate scoped rules |
| Pad to pad clearance | `Clearance`, scoped or through the object-clearance matrix |
| Hole to hole clearance | `HoleToHoleClearance` |
| Silk to solder mask clearance | `SilkToSolderMaskClearance` |
| Board edge clearance | `BoardOutlineClearance` |
| Plated slot width | `HoleSize` scoped with `HasSlotHole` — partial |
| Silkscreen text height | none |
| Silkscreen stroke width | none |
| Plated slot length-to-width ratio | none |

Altium offers three rule types the KiCad files do not currently emit: `SilkToSilkClearance`, `MinimumSolderMaskSliver`, and acute angle. These need values the TOML does not hold today, so adding them means sourcing three new figures from each fab's page — not free, and out of scope for the first release. Tracked as follow-up.

### Coverage gaps

Three limits cannot be expressed. Each generated `.RUL` carries a header comment naming them, the README documents them, and a test asserts every value in the TOML either maps to an emitted rule or appears on the documented exception list.

The test is the part that matters: it prevents a value being silently dropped when the emitter changes later.

## Validation and error handling

Three layers, each catching what the one before cannot.

1. **Shared validation**, from `fab-capabilities`: unit format, positive values, required `layers`, unknown-key rejection. Runs before any emission.
2. **`lint_rul.py`**, mirroring `lint_dru.py`: key names checked against a known vocabulary, pilcrow termination, CRLF line endings, unique `UNIQUEID` values, and correct unit encoding per field. The key-vocabulary check exists because Altium's own spelling includes `PREFEREDWIDTH`; a near-miss key would otherwise pass silently.
3. **Golden fixture comparison**: generated output is asserted against a real Altium export field-for-field.

## Testing

- **Golden fixture** — a real `.RUL` exported from Altium, committed to `tests/fixtures/`.
- **Manual import test** — one round-trip into real Altium, confirming a generated file imports and the values land correctly. Recorded as a short note in `tests/fixtures/` giving the Altium version, the date, the file tested and the result. Required once before the first release; CI guards the grammar afterwards.
- **Unit conversion** — known mm/mil/internal triples in both directions.
- **Priority ordering** — a specific rule outranks the catch-all it must beat.
- **Determinism** — byte-identical output across repeated runs and across `PYTHONHASHSEED` values.
- **Coverage** — every TOML value mapped or explicitly excepted.
- **Drift** — `generate_rul.py --check` fails when committed output does not match the source.
- **Upstream pin** — vendored capabilities match the tag in `UPSTREAM`.

## Phases

Each phase has a success test; none starts before the previous one passes. Phases 1 and 2 are separately substantial, so each gets its own implementation plan rather than one plan spanning the lot. The first plan covers phase 1 only.

**Phase 1 — extract `fab-capabilities`.**
Create the repo with the data and loader. Point `kicad-druid` at a vendored copy with an `UPSTREAM` pin and the CI diff job.
*Success:* `kicad-druid` regenerates byte-identical output to what it ships today, and all existing gates pass unchanged.

**Phase 2 — `altium-druid`, JLCPCB default variant only.**
Emitter, grammar linter, golden fixture, the CI gates above, and the manual Altium import test.
*Success:* a generated `.RUL` imports into Altium and its values match the TOML.

**Phase 3 — release and document.**
Tagged release with `.RUL` files attached as assets, gap list in the README, cross-links between the repos.
*Success:* a user can download a rules file without cloning anything.

**Phase 4 — expand.**
PCBWay, then the remaining variants.
*Success:* the full matrix generates and lints, with no manual step per variant.

## Known limitations

- **Constraint Manager flow.** Altium 25 and later can migrate a project to Constraint Manager, which is one-way. Whether `.RUL` import works inside a migrated project is unverified, and could not be settled without running Altium. Documented in the README as a known limitation until tested on a real project.
- **From-scratch identity tokens.** Whether Altium accepts generated `UNIQUEID` values without complaint is unverified until the phase 2 import test runs. The golden fixture reduces the risk; the import test closes it.
- **Contribution redirects.** `kicad-druid` holds the stars and issue history, so capability PRs will keep arriving there. Mitigated by pointers in its CONTRIBUTING file, its `capabilities/` directory, and its capability-change issue template — reduced, not eliminated.

## Non-goals

- Replacing Altium's own DRC. These rules add fab capability limits on top of it.
- Guaranteeing manufacturability. Fabs change capabilities; the published page is the source of truth.
- Shipping stackup or layer setup. `.RUL` carries rules only; a template `PcbDoc` would be a separate piece of work.
- Generating rules for tools beyond KiCad and Altium.
