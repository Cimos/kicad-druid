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
for tp in glob.glob(os.path.join(g.ROOT, "capabilities", "*.toml")):
    import tomllib
    with open(tp, "rb") as fh:
        fab = g.Fab(tomllib.load(fh))
    g.validate(fab)
    for v in fab.variants:
        text = g.generate(fab, v)
        check(lint_text(text, f"{fab.name}.kicad_dru") == [],
              f"{fab.name} {v['id']}: generated file lints clean")
        # Inner-layer rules must track the validated layer count exactly.
        # Check the (layer inner) clauses themselves, not display text — and
        # read v["layers"] directly: a .get() default here would share the
        # very bug this guards against.
        if v["layers"] <= 2:
            check("(layer inner)" not in text,
                  f"{fab.name} {v['id']}: no inner-layer rules on 2L")
        else:
            check(text.count("(layer inner)") == 2,
                  f"{fab.name} {v['id']}: inner width and spacing rules present")

print(f"OK — {PASSED} checks passed")
