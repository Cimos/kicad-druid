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
rejects(clone(flags={"emit_smd_pad_min": True}), "smd_pad_min")
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
fabs = g.load_fabs()
for fab in fabs:
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

        check(f'{fab.prefix}: Via Hole to Pad Hole Clearance (Different Nets, inferred)' in text,
              f"{fab.name} {v['id']}: mixed via/pad hole rule present")
        check("# NOTE: Inferred from the pad-to-pad hole figure; not documented by the fab."
              in text,
              f"{fab.name} {v['id']}: mixed via/pad hole rule is marked inferred")

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

        if fab.flags.get("emit_smd_pad_min"):
            smd = fab.constants["smd_pad_min"]
            check(f'(rule "{fab.prefix}: SMD Pad Size"' in text,
                  f"{fab.name} {v['id']}: SMD pad size rule present")
            check(f'(A.Size_X < {smd} || A.Size_Y < {smd})' in text and
                  f'"A.Size_X >= {smd} && A.Size_Y >= {smd}"' in text,
                  f"{fab.name} {v['id']}: SMD pad size rule uses the TOML value {smd}")
        else:
            check("SMD Pad Size" not in text,
                  f"{fab.name} {v['id']}: no unsourced SMD pad size rule")

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
    "Via Hole to Pad Hole Clearance (Different Nets, inferred)",
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
          pcbway, "PCBWay: Via Hole to Pad Hole Clearance (Different Nets, inferred)"),
      "PCBWay: split mixed-hole rule preserves prior 0.5mm generic clearance")
check("SMD Pad Size" not in pcbway,
      "PCBWay: no SMD pad size rule (figure not published)")
check("adds extra cost" not in pcbway and
      "Plated Slot Length-to-width Ratio" not in pcbway and
      "Same-net Trace Spacing" not in pcbway,
      "PCBWay: JLCPCB-only rules are not emitted")

# --- generator: orphan detection is repo-wide, not per fab directory ---
# A deleted or renamed fab TOML used to leave its published .kicad_dru files
# invisible to --check, because only directories of loadable TOMLs were
# scanned.
with tempfile.TemporaryDirectory() as d:
    os.makedirs(os.path.join(d, "Alive"))
    os.makedirs(os.path.join(d, "Deleted"))
    alive = os.path.join(d, "Alive", "Alive.kicad_dru")
    stale_file = os.path.join(d, "Deleted", "Deleted.kicad_dru")
    for p in (alive, stale_file):
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("(version 1)\n")
    check(g.find_orphans({alive}, d) == [stale_file],
          "orphan scan finds files of a deleted fab")
    check(g.find_orphans({alive, stale_file}, d) == [],
          "orphan scan is quiet when every file is generated")
    # nested files (e.g. tooling clutter) are out of scope for output_path
    deep = os.path.join(d, "Alive", "sub")
    os.makedirs(deep)
    with open(os.path.join(deep, "x.kicad_dru"), "w", encoding="utf-8") as fh:
        fh.write("(version 1)\n")
    check(g.find_orphans({alive, stale_file}, d) == [],
          "orphan scan only looks where output_path writes")

# End to end: on the real repo, --check must currently report no orphans.
check(g.find_orphans(set(g.output_path(f, v) for f in fabs for v in f.variants),
                     g.ROOT) == [],
      "repo has no orphaned .kicad_dru files")

# --- the derived Generic fab ---
generic = [f for f in fabs if f.name == g.GENERIC_NAME]
check(len(generic) == 1, "load_fabs() derives exactly one Generic fab")
generic = generic[0]
real_fabs = [f for f in fabs if f is not generic]

# Every value key must be classified as min-type or max-type, or the strictest
# value would be picked by whichever set happened to match first.
check(g.MIN_KEYS | g.MAX_KEYS == g.VALUE_KEYS,
      "every VALUE_KEYS entry is classified min or max")
check(not (g.MIN_KEYS & g.MAX_KEYS),
      "no value key is classified both min and max")
check(g.MAX_KEYS == {"drill_hole_max", "pth_hole_max"},
      "only the two hole_size upper bounds are max keys")

check(not os.path.exists(os.path.join(g.ROOT, "capabilities", "Generic.toml")),
      "Generic has no TOML — it is derived in code")

# Generic offers exactly the variants every fab offers.
generic_ids = [v["id"] for v in generic.variants]
shared_ids = [v["id"] for v in real_fabs[0].variants
              if all(g.variant_by_id(f, v["id"]) for f in real_fabs[1:])]
check(generic_ids == shared_ids, "Generic offers the variants every fab shares")

# Sample values: min keys take the largest across fabs, max keys the smallest.
for vid, key, expected in [
    ("4L-1oz", "via_hole", "0.2mm"),            # JLCPCB 0.15, PCBWay 0.2
    ("4L-1oz", "castellated_min", "0.6mm"),     # JLCPCB 0.5, PCBWay 0.6
    ("4L-1oz", "nonplated_slot_min", "1.0mm"),  # JLCPCB 1.0, PCBWay 0.8
    ("4L-1oz", "edge_routed", "0.3mm"),         # JLCPCB 0.2, PCBWay 0.3
    ("4L-1oz", "text_height", "1mm"),           # JLCPCB 1, PCBWay 0.8
    ("4L-1oz", "pth_hole_max", "6.3mm"),        # max key: JLCPCB 6.3, PCBWay 6.35
    ("4L-1oz", "drill_hole_max", "6.3mm"),      # max key: equal either way
    ("2L-1oz", "via_hole", "0.3mm"),            # JLCPCB 0.15, PCBWay 0.3
    ("2L-1oz", "trace_width_outer", "0.127mm"),  # JLCPCB 0.1, PCBWay 0.127
    ("4L-2oz", "trace_spacing_outer", "0.1778mm"),
    ("6L-1oz", "kelvin_annular", "0.125mm"),    # JLCPCB only — carried over
    ("6L-1oz", "via_same_net", "0.254mm"),      # PCBWay only — carried over
]:
    got = g.resolve(generic, g.variant_by_id(generic, vid)).get(key)
    others = [g.resolve(f, g.variant_by_id(f, vid)).get(key) for f in real_fabs]
    check(got == expected,
          f"Generic {vid} {key}: expected {expected}, got {got} (fabs: {others})")

# A merged, unlayered trace rule is also what that fab allows on inner copper,
# so it still has a say in Generic's inner limit.
check(g.resolve(generic, g.variant_by_id(generic, "4L-1oz"))["trace_width_inner"]
      == "0.1mm",
      "Generic inner trace width beats the merged JLCPCB limit")

# Generic must emit every rule either fab emits. JLCPCB publishes one unlayered
# trace rule where PCBWay splits outer from inner; Generic keeps the split, so
# the merged name maps onto the outer rule (the inner rule is emitted too
# whenever the variant has inner layers).
SPLIT_FOR = {
    "Trace Width": "Trace Width (Outer Layer)",
    "Trace Spacing": "Trace Spacing (Outer Layer)",
}


def rule_names(text: str, prefix: str) -> set:
    import re as _re
    return {m.group(1)[len(prefix) + 2:]
            for m in _re.finditer(r'\(rule "([^"]*)"', text)
            if m.group(1).startswith(prefix + ": ")}


for vid in generic_ids:
    mine = rule_names(generated[(generic.name, vid)], generic.prefix)
    for f in real_fabs:
        theirs = rule_names(generated[(f.name, vid)], f.prefix)
        missing = sorted(n for n in theirs if SPLIT_FOR.get(n, n) not in mine)
        check(not missing,
              f"Generic {vid}: rules missing from {f.name}: {missing}")

# Deriving and generating twice must give the same bytes — the output is
# committed, so any ordering wobble would show up as a phantom diff.
again = g.load_fabs()
again = [f for f in again if f.name == g.GENERIC_NAME][0]
for v in again.variants:
    check(g.generate(again, v) == generated[(generic.name, v["id"])],
          f"Generic {v['id']}: regenerating gives identical bytes")

# The committed files match what the generator produces right now.
for v in generic.variants:
    with open(g.output_path(generic, v), "r", encoding="utf-8") as fh:
        check(fh.read() == generated[(generic.name, v["id"])],
              f"Generic {v['id']}: committed file matches the generator")

print(f"OK — {PASSED} checks passed")
