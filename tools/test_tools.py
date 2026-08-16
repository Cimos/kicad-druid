#!/usr/bin/env python3
"""Tests for the design-rule tooling. No dependencies — run directly:

    python3 tools/test_tools.py

Exits non-zero on the first failure.
"""

from __future__ import annotations

import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import generate_dru as g  # noqa: E402
import lint_dru as lint  # noqa: E402

PASSED = 0


def check(cond, msg):
    global PASSED
    if not cond:
        print(f"FAIL: {msg}", file=sys.stderr)
        raise SystemExit(1)
    PASSED += 1


def lint_text(text: str, name: str = "JLCPCB.kicad_dru"):
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, name)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(text)
        return lint.lint_file(p)


# --- linter: happy path ---
GOOD = (
    '(version 1)\n'
    '(rule "JLCPCB: Trace Width"\n'
    '\t(condition "A.Type == \'Track\'")\n'
    '\t(constraint track_width (min 0.09mm))\n)\n'
)
check(lint_text(GOOD) == [], "clean file should have no lint errors")

# --- linter: lowercase type literal ---
bad = GOOD.replace("'Track'", "'track'")
check(any("lowercase type literal" in m for _, m in lint_text(bad)),
      "lowercase 'track' should be flagged")

# --- linter: missing constraint ---
nocon = '(version 1)\n(rule "JLCPCB: X"\n\t(condition "A.Type == \'Via\'")\n)\n'
check(any("no (constraint" in m for _, m in lint_text(nocon)),
      "rule without a constraint should be flagged")

# --- linter: duplicate rule name ---
dup = GOOD + GOOD.split("\n", 1)[1]  # append the rule again (no second version line)
check(any("duplicate rule name" in m for _, m in lint_text(dup)),
      "duplicate rule name should be flagged")

# --- linter: unbalanced parens ---
check(any("unbalanced" in m for _, m in lint_text(GOOD[:-3])),
      "unbalanced parens should be flagged")

# --- linter: prefix must match filename (and tolerate hyphenated fab names) ---
check(any("does not match filename" in m for _, m in lint_text(GOOD, "PCBWay.kicad_dru")),
      "JLCPCB-prefixed rules in a PCBWay file should be flagged")
check(lint_text(GOOD, "JLCPCB-4L-2oz.kicad_dru") == [],
      "variant filename should accept the base fab prefix")
hyph = GOOD.replace("JLCPCB:", "Sierra-Circuits:")
check(lint_text(hyph, "Sierra-Circuits.kicad_dru") == [],
      "hyphenated fab name should not be falsely flagged")

# --- generator: validate() rejects bad config ---
BASE = {
    "fab": {"name": "X", "prefix": "X", "capabilities_url": "u", "default_variant": "a"},
    "flags": {}, "constants": {}, "variant": [{"id": "a", "layers": 2}], "diffpair": [],
}


def clone(**over):
    import copy
    d = copy.deepcopy(BASE)
    for k, v in over.items():
        d[k] = v
    return d


def rejects(data, needle):
    try:
        g.validate(g.Fab(data))
    except ValueError as e:
        check(needle in str(e), f"expected '{needle}' in: {e}")
        return
    check(False, f"validate should have rejected config for '{needle}'")


g.validate(g.Fab(BASE))  # baseline is valid
PASSED += 1
rejects(clone(fab={**BASE["fab"], "default_variant": "nope"}), "default_variant")
rejects(clone(variant=[]), "no [[variant]]")
rejects(clone(flags={"emit_bga": True}), "bga_to_trace")
rejects(clone(flags={"avoid_small_via_extra_cost": True}), "small_via_hole")
rejects(clone(flags={"emit_same_net_trace_spacing": True}), "same_net_trace_spacing")
rejects(clone(diffpair=[{"name": "100R_Diff", "diff": True, "track_width": "0.2mm"}]), "gap")

# --- generator: value validation — every fault below once passed silently ---
# A unit-less dimension makes KiCad discard the ENTIRE rule file (measured),
# so validate() must refuse to emit one.
rejects(clone(constants={"pth_annular": "0.15"}), "not a dimension")
rejects(clone(constants={"pth_annular": "-0.09mm"}), "not a dimension")
rejects(clone(constants={"pth_annular": "0.09mn"}), "not a dimension")
rejects(clone(constants={"pth_annular": "0mm"}), "greater than zero")
rejects(clone(constants={"pth_annular": 0.15}), "not a dimension")  # bare TOML float

# Missing or misspelled 'layers' used to silently generate a multilayer
# variant as 2-layer, dropping its inner-layer rules.
rejects(clone(variant=[{"id": "a"}]), "layers")
rejects(clone(variant=[{"id": "a", "layer": 4}]), "unknown [[variant]] key")
rejects(clone(variant=[{"id": "a", "layers": 0}]), "positive integer")
rejects(clone(variant=[{"id": "a", "layers": True}]), "positive integer")

# Unknown keys used to be silently ignored — a misspelled override fell back
# to the constant it was meant to replace.
rejects(clone(constants={"pth_hole_mni": "9.9mm"}), "unknown [constants] key")
rejects(clone(variant=[{"id": "a", "layers": 2, "over": {"pth_hole_mni": "9.9mm"}}]),
        "unknown [variant.over] key")
rejects(clone(flags={"emit_bag": True}), "unknown [flags] key")
rejects(clone(diffpair=[{"name": "50R", "track_width": "0.2mm", "gpa": "0.15mm"}]),
        "unknown [[diffpair]] key")
rejects(clone(diffpair=[{"name": "50R", "track_width": "0.2"}]), "not a dimension")

# Valid values must still pass: overrides, flags with their required keys.
g.validate(g.Fab(clone(
    flags={"avoid_kelvin_test": True},
    constants={"kelvin_annular": "0.125mm"},
    variant=[{"id": "a", "layers": 6, "over": {"trace_width_inner": "0.09mm"}}])))
PASSED += 1

# --- generator: round-trip — every generated file lints clean and balances parens ---
import glob  # noqa: E402
generated = {}
for tp in glob.glob(os.path.join(g.ROOT, "capabilities", "*.toml")):
    import tomllib
    with open(tp, "rb") as fh:
        fab = g.Fab(tomllib.load(fh))
    g.validate(fab)
    for v in fab.variants:
        text = g.generate(fab, v)
        generated[(fab.name, v["id"])] = text
        check(lint_text(text, f"{fab.name}.kicad_dru") == [],
              f"{fab.name} {v['id']}: generated file lints clean")

        # Inner-layer clauses track both the validated layer count and the
        # fab's rule structure. JLCPCB has one unlayered trace rule plus an
        # inner-only PTH clearance; PCBWay retains separate inner trace rules.
        expected_inner = 0
        if v["layers"] > 2:
            if "pth_to_trace_inner" in fab.constants or "pth_to_trace_inner" in v.get("over", {}):
                expected_inner += 1
            if not fab.flags.get("merge_trace_layers"):
                expected_inner += 2
        check(text.count("(layer inner)") == expected_inner,
              f"{fab.name} {v['id']}: expected {expected_inner} inner-layer clauses")

        check(f'{fab.prefix}: Via Hole to Pad Hole Clearance (Different Nets)' in text,
              f"{fab.name} {v['id']}: mixed via/pad hole rule present")

        if fab.flags.get("avoid_small_via_extra_cost"):
            check("Via diameter < 0.45mm with hole < 0.3mm adds extra cost" in text,
                  f"{fab.name} {v['id']}: small-via cost guard present")
        else:
            check("adds extra cost" not in text,
                  f"{fab.name} {v['id']}: no unsourced small-via cost guard")

        if fab.flags.get("enforce_plated_slot_ratio"):
            check("Plated Slot Length-to-width Ratio" in text,
                  f"{fab.name} {v['id']}: plated-slot ratio rule present")
        else:
            check("Plated Slot Length-to-width Ratio" not in text,
                  f"{fab.name} {v['id']}: no unsourced plated-slot ratio rule")

        if fab.flags.get("merge_trace_layers"):
            check(f'(rule "{fab.prefix}: Trace Width"' in text and
                  f'(rule "{fab.prefix}: Trace Spacing"' in text,
                  f"{fab.name} {v['id']}: merged trace rules present")
            check("Trace Width (Outer Layer)" not in text and
                  "Trace Width (Inner Layer)" not in text,
                  f"{fab.name} {v['id']}: split trace rules absent")
        else:
            check("Trace Width (Outer Layer)" in text,
                  f"{fab.name} {v['id']}: outer trace rule retained")
            check(("Trace Width (Inner Layer)" in text) == (v["layers"] > 2),
                  f"{fab.name} {v['id']}: inner trace rule follows layer count")

        check(("# (rule \"%s: Same-net Trace Spacing\"" % fab.prefix in text) ==
              bool(fab.flags.get("emit_same_net_trace_spacing")),
              f"{fab.name} {v['id']}: disabled same-net block follows flag")


def rule_block(text: str, name: str) -> str:
    start = text.index(f'(rule "{name}"')
    end = text.index("\n)\n", start) + 3
    return text[start:end]


# --- generator: JLCPCB target structure and variant values ---
jlc = generated[("JLCPCB", "4L-1oz")]
ordered = [
    "Via Hole to Via Hole Clearance (Different Nets)",
    "Pad Hole to Pad Hole Clearance (Pad with Hole, Different Nets)",
    "Via/Pad to Via/Pad Clearance (Different Nets)",
    "Via/Pad Hole to Via/Pad Hole Clearance (Same Net)",
    "Via Hole to Pad Hole Clearance (Different Nets)",
    "Pad to Pad Clearance (Pad without Hole, Different Nets)",
]
positions = [jlc.index(f'(rule "JLCPCB: {name}"') for name in ordered]
check(positions == sorted(positions),
      "JLCPCB: general implied rules precede specific clearance rules")

pth_outer = jlc.index('(rule "JLCPCB: PTH to Trace"')
pth_inner = jlc.index('(rule "JLCPCB: PTH to Trace (inner layer)"')
check(pth_outer < pth_inner, "JLCPCB: inner PTH clearance follows general PTH rule")
check("PTH to Trace (inner layer)" not in generated[("JLCPCB", "2L-1oz")],
      "JLCPCB 2L-1oz: no inapplicable inner PTH rule")

check("(min 0.18mm)" in rule_block(generated[("JLCPCB", "2L-1oz")],
                                    "JLCPCB: PTH Annular Ring"),
      "JLCPCB 2L-1oz: PTH annular ring is 0.18mm")
check("(min 0.254mm)" in rule_block(generated[("JLCPCB", "4L-2oz")],
                                     "JLCPCB: PTH Annular Ring"),
      "JLCPCB 4L-2oz: PTH annular ring is 0.254mm")
check("(min 0.15mm)" in rule_block(generated[("JLCPCB", "4L-2oz")],
                                    "JLCPCB: Trace Width") and
      "(min 0.15mm)" in rule_block(generated[("JLCPCB", "4L-2oz")],
                                    "JLCPCB: Trace Spacing"),
      "JLCPCB 4L-2oz: unified trace width and spacing are 0.15mm")
# Deliberate additions beyond the hand-maintained file: the NPTH-to-copper
# clearance and the impedance net classes (see DESIGN.md) are features of the
# generated matrix, not migration leftovers.
check("NPTH to Copper (non-Track)" in jlc,
      "JLCPCB: NPTH-to-copper rule present")
check("50R Single-Ended" in jlc and "100R_Diff Differential Pair" in jlc,
      "JLCPCB: impedance net classes present")

pcbway = generated[("PCBWay", "4L-1oz")]
check("(min 0.5mm)" in rule_block(
          pcbway, "PCBWay: Via Hole to Pad Hole Clearance (Different Nets)"),
      "PCBWay: split mixed-hole rule preserves prior 0.5mm generic clearance")
check("adds extra cost" not in pcbway and
      "Plated Slot Length-to-width Ratio" not in pcbway and
      "Same-net Trace Spacing" not in pcbway,
      "PCBWay: JLCPCB-only rules are not emitted")

print(f"OK — {PASSED} checks passed")
