#!/usr/bin/env python3
"""Generate COMPARISON.md — a side-by-side table of every fab's rule values,
read from the same capabilities/*.toml source of truth as the .kicad_dru files.

Usage:
    python3 tools/gen_comparison.py            # (re)write COMPARISON.md
    python3 tools/gen_comparison.py --check     # fail if COMPARISON.md is stale
"""

from __future__ import annotations

import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tomllib  # noqa: E402  (stdlib, 3.11+)
from generate_dru import Fab, ROOT, validate  # noqa: E402

OUT = os.path.join(ROOT, "COMPARISON.md")

# (toml key, human label) for values that don't vary by variant.
CONSTANT_ROWS = [
    ("drill_hole_max", "Drill hole — max"),
    ("via_annular", "Via annular ring — min"),
    ("pth_hole_min", "PTH hole — min"),
    ("pth_hole_max", "PTH hole — max"),
    ("npth_hole_min", "NPTH hole — min"),
    ("castellated_min", "Castellated hole — min"),
    ("pth_annular", "PTH annular ring — min"),
    ("npth_annular", "NPTH annular ring — min"),
    ("plated_slot_min", "Plated slot width — min"),
    ("nonplated_slot_min", "Non-plated slot width — min"),
    ("small_via_hole", "Small-via extra-cost hole threshold"),
    ("small_via_diameter", "Small-via diameter to avoid extra cost"),
    ("via_hole_diff", "Via hole-to-hole, different nets"),
    ("via_pad_hole_diff", "Via hole-to-pad hole, different nets"),
    ("via_same_net", "Via hole-to-hole, same net"),
    ("pad_nohole_diff", "Pad-to-pad (no hole), different nets"),
    ("pad_hole_diff", "Pad hole-to-hole (with hole), different nets"),
    ("via_to_trace", "Via hole to trace"),
    ("pth_to_trace", "PTH hole to trace"),
    ("pth_to_trace_inner", "PTH hole to trace (inner layer)"),
    ("npth_to_trace", "NPTH hole to trace"),
    ("npth_to_copper", "NPTH to copper (non-track)"),
    ("pad_to_trace", "Pad to trace"),
    ("bga_to_trace", "BGA to trace"),
    ("same_net_trace_spacing", "Same-net trace spacing (disabled workaround)"),
    ("text_thickness", "Silk line width — min"),
    ("text_height", "Silk text height — min"),
    ("silk_clearance", "Pad to silkscreen"),
    ("edge_routed", "Trace to board edge (routed)"),
]

# Values that vary by variant.
VARIANT_ROWS = [
    ("drill_hole_min", "Drill hole — min"),
    ("via_hole", "Via hole — min"),
    ("trace_width_outer", "Trace width (outer)"),
    ("trace_spacing_outer", "Trace spacing (outer)"),
    ("trace_width_inner", "Trace width (inner)"),
    ("trace_spacing_inner", "Trace spacing (inner)"),
]

FLAG_ROWS = [
    ("avoid_kelvin_test", "Avoids JLCPCB 4-wire Kelvin test"),
    ("avoid_small_via_extra_cost", "Avoids small-via extra cost"),
    ("allow_blind_buried", "Blind/buried vias allowed"),
    ("enforce_plated_slot_ratio", "Enforces plated-slot length/width ratio"),
    ("emit_bga", "Ships a BGA fan-out rule"),
    ("emit_implied_clearance", "Ships implied catch-all clearances"),
    ("merge_trace_layers", "Uses one trace limit for all copper layers"),
    ("emit_same_net_trace_spacing", "Documents disabled same-net spacing workaround"),
]


def load_fabs() -> list:
    fabs = []
    for tp in sorted(glob.glob(os.path.join(ROOT, "capabilities", "*.toml"))):
        with open(tp, "rb") as fh:
            fab = Fab(tomllib.load(fh))
        validate(fab)
        fabs.append(fab)
    return fabs


def merged(fab: Fab, variant: dict) -> dict:
    m = dict(fab.constants)
    m.update(variant.get("over", {}))
    # A merged, unlayered trace rule applies the same value to inner copper.
    # Reflect that effective value without storing unused inner overrides in TOML.
    if fab.flags.get("merge_trace_layers") and variant["layers"] > 2:
        m["trace_width_inner"] = m.get("trace_width_outer", "—")
        m["trace_spacing_inner"] = m.get("trace_spacing_outer", "—")
    return m


def variant_by_id(fab: Fab, vid: str) -> dict:
    for v in fab.variants:
        if v["id"] == vid:
            return v
    return fab.variants[0]


def table(headers: list, rows: list) -> str:
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join("---" for _ in headers) + "|"]
    for r in rows:
        out.append("| " + " | ".join(r) + " |")
    return "\n".join(out)


def render(fabs: list) -> str:
    names = [f.name for f in fabs]
    doc = []
    doc.append("# Fab capability comparison")
    doc.append("")
    doc.append("<!-- GENERATED FILE — do not edit by hand. -->")
    doc.append("<!-- Run tools/gen_comparison.py after editing capabilities/*.toml. -->")
    doc.append("")
    doc.append("Side-by-side of the design-rule values each fab enforces, read from "
               "`capabilities/*.toml`. All values in mm unless noted.")
    doc.append("")

    # Constants (resolved at each fab's default variant so variant-only keys fill in).
    defaults = {f.name: merged(f, variant_by_id(f, f.default_variant)) for f in fabs}
    doc.append("## Fixed limits")
    doc.append("")
    doc.append(f"Shown at each fab's default variant "
               + ", ".join(f"**{f.name}**: `{f.default_variant}`" for f in fabs) + ".")
    doc.append("")
    rows = []
    for key, label in CONSTANT_ROWS:
        cells = [defaults[n].get(key, "—") for n in names]
        if all(c == "—" for c in cells):
            continue
        rows.append([label] + cells)
    doc.append(table(["Parameter"] + names, rows))
    doc.append("")

    # Per-variant values.
    doc.append("## By build variant")
    doc.append("")
    for f in fabs:
        doc.append(f"### {f.name}")
        doc.append("")
        headers = ["Variant"] + [lbl for _, lbl in VARIANT_ROWS]
        rows = []
        for v in f.variants:
            m = merged(f, v)
            marker = " (default)" if v["id"] == f.default_variant else ""
            rows.append([f"`{v['id']}`{marker}"] + [m.get(k, "—") for k, _ in VARIANT_ROWS])
        doc.append(table(headers, rows))
        doc.append("")

    # Impedance-controlled net classes.
    doc.append("## Impedance-controlled net classes")
    doc.append("")
    doc.append("> Typical starting values for each fab's default stackup — **verify against "
               "the fab's impedance calculator for your actual stackup.**")
    doc.append("")
    class_names = []
    for f in fabs:
        for dp in f.diffpairs:
            if dp["name"] not in class_names:
                class_names.append(dp["name"])
    headers = ["Net class"] + [f"{n} (width / gap)" for n in names]
    rows = []
    for cn in class_names:
        cells = []
        for f in fabs:
            dp = next((d for d in f.diffpairs if d["name"] == cn), None)
            if dp is None:
                cells.append("—")
            elif dp.get("diff"):
                cells.append(f"{dp['track_width']} / {dp['gap']}")
            else:
                cells.append(f"{dp['track_width']} / n/a")
        rows.append([f"`{cn}`"] + cells)
    doc.append(table(headers, rows))
    doc.append("")

    # Process notes / flags.
    doc.append("## Process notes")
    doc.append("")
    rows = []
    for key, label in FLAG_ROWS:
        rows.append([label] + ["yes" if f.flags.get(key) else "no" for f in fabs])
    doc.append(table(["", *names], rows))
    doc.append("")

    return "\n".join(doc) + "\n"


def main(argv: list) -> int:
    check = "--check" in argv[1:]
    fabs = load_fabs()
    if not fabs:
        print("no capabilities/*.toml files found", file=sys.stderr)
        return 1
    text = render(fabs)

    existing = None
    if os.path.exists(OUT):
        with open(OUT, "r", encoding="utf-8") as fh:
            existing = fh.read()

    if check:
        if existing != text:
            print("COMPARISON.md is out of date; run tools/gen_comparison.py", file=sys.stderr)
            return 1
        print("COMPARISON.md is up to date.")
        return 0

    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(f"wrote {os.path.relpath(OUT, ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
