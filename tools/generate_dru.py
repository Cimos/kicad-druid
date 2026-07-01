#!/usr/bin/env python3
"""Generate KiCad .kicad_dru files from per-fab TOML source-of-truth files.

Reads every capabilities/<FAB>.toml and emits one .kicad_dru per variant into
<FAB>/. The default variant gets the plainly-named <FAB>/<FAB>.kicad_dru; the
others get <FAB>/<FAB>-<id>.kicad_dru.

Rule *structure* (names, conditions, order) lives here; rule *values* live in
the TOML. No third-party dependencies — TOML is read with the stdlib tomllib
(Python 3.11+).

Usage:
    python3 tools/generate_dru.py            # regenerate everything
    python3 tools/generate_dru.py --check    # fail if output is out of date
"""

from __future__ import annotations

import glob
import os
import sys

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    sys.exit("generate_dru.py needs Python 3.11+ (stdlib tomllib)")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Fab:
    def __init__(self, data: dict):
        self.name = data["fab"]["name"]
        self.prefix = data["fab"]["prefix"]
        self.url = data["fab"]["capabilities_url"]
        self.default_variant = data["fab"]["default_variant"]
        self.flags = data.get("flags", {})
        self.constants = data.get("constants", {})
        self.variants = data.get("variant", [])
        self.diffpairs = data.get("diffpair", [])


def make_val(constants: dict, over: dict):
    """Return a lookup that prefers the variant override, then the constant."""

    def val(key: str) -> str:
        if key in over:
            return over[key]
        if key in constants:
            return constants[key]
        raise KeyError(f"missing value for '{key}'")

    return val


def rule(name: str, condition: str, constraints: list, comment: str = "", layer: str = "") -> str:
    lines = []
    if comment:
        lines.extend(f"# {c}" for c in comment.splitlines())
    lines.append(f'(rule "{name}"')
    if layer:
        lines.append(f"\t(layer {layer})")
    if condition:
        lines.append(f'\t(condition "{condition}")')
    lines.extend(f"\t{c}" for c in constraints)
    lines.append(")")
    return "\n".join(lines)


def generate(fab: Fab, variant: dict) -> str:
    p = fab.prefix
    over = variant.get("over", {})
    val = make_val(fab.constants, over)
    layers = variant.get("layers", 2)
    has_inner = layers > 2

    out: list = []
    out.append("(version 1)")
    out.append(f"# Custom Design Rules (DRC) for KiCad — {fab.name}: {variant['label']}")
    out.append("#")
    out.append(f"# Matching {fab.name} capabilities: {fab.url}")
    out.append("#")
    out.append("# GENERATED FILE — do not edit by hand.")
    out.append(f"# Edit capabilities/{fab.name}.toml and run tools/generate_dru.py instead.")
    out.append("#")
    out.append("# KiCad documentation: https://docs.kicad.org/8.0/en/pcbnew/pcbnew.html#custom-design-rules")

    # --- Drill/Hole Size ---
    out.append("\n\n# --- Drill/Hole Size ---\n")
    out.append(rule(f"{p}: Drill Hole Size", "",
                    [f"(constraint hole_size (min {val('drill_hole_min')}) (max {val('drill_hole_max')}))"]))
    out.append("")
    out.append(rule(f"{p}: Via Hole Size", "A.Type == 'Via'",
                    [f"(constraint hole_size (min {val('via_hole')}))"]))
    out.append("")
    out.append(rule(f"{p}: Via Annular Ring", "A.Type == 'Via'",
                    [f"(constraint annular_width (min {val('via_annular')}))"]))
    out.append("")
    out.append(rule(f"{p}: PTH Hole Size",
                    "A.Type == 'Pad' && A.Pad_Type == 'Through-hole' && A.isPlated()",
                    [f"(constraint hole_size (min {val('pth_hole_min')}) (max {val('pth_hole_max')}))"]))
    out.append("")
    out.append(rule(f"{p}: NPTH Hole Size",
                    "A.Type == 'Pad' && A.Pad_Type == 'NPTH, mechanical' && !A.isPlated()",
                    [f"(constraint hole_size (min {val('npth_hole_min')}))"]))
    out.append("")
    out.append(rule(f"{p}: Castellated Hole Size",
                    "A.Type == 'Pad' && A.Fabrication_Property == 'Castellated pad'",
                    [f"(constraint hole_size (min {val('castellated_min')}))"],
                    layer="outer"))
    out.append("")
    out.append(rule(f"{p}: PTH Annular Ring",
                    "A.Type == 'Pad' && A.Pad_Type == 'Through-hole' && A.isPlated()",
                    [f"(constraint annular_width (min {val('pth_annular')}))"]))
    out.append("")
    out.append(rule(f"{p}: NPTH Annular Ring",
                    "A.Type == 'Pad' && A.Pad_Type == 'NPTH, mechanical' && !A.isPlated()",
                    [f"(constraint annular_width (min {val('npth_annular')}))"]))
    if fab.flags.get("avoid_kelvin_test"):
        out.append("")
        out.append(rule(
            f"{p}: Avoid 4-Wire Kelvin Test",
            "(A.Type == 'Via' && A.Hole < 0.3mm && A.Diameter <= 0.4mm) || (A.Type == 'Pad' && ((A.Hole_Size_X < 0.3mm && A.Size_X <= 0.4mm) || (A.Hole_Size_Y < 0.3mm && A.Size_Y <= 0.4mm)))",
            [f"(constraint annular_width (min {val('kelvin_annular')}))"],
            comment="An expensive 4-Wire Kelvin Test is auto-added for holes < 0.3mm with diameter <= 0.4mm."))

    # --- VIA Support Rules ---
    if not fab.flags.get("allow_blind_buried"):
        out.append("\n\n# --- VIA Support Rules ---\n")
        out.append(rule(f"{p}: Only Throughhole VIAs are supported", "A.Type == 'Via'",
                        ['(constraint assertion "!(A.isBlindBuriedVia() || A.isMicroVia())")']))

    # --- Slot Width ---
    out.append("\n\n# --- Slot Width ---\n")
    out.append(rule(f"{p}: Plated Slot Width",
                    "A.Type == 'Pad' && (A.Hole_Size_X != A.Hole_Size_Y) && A.isPlated()",
                    [f"(constraint hole_size (min {val('plated_slot_min')}))"]))
    out.append("")
    out.append(rule(f"{p}: Non-Plated Slot Width",
                    "A.Type == 'Pad' && (A.Hole_Size_X != A.Hole_Size_Y) && !A.isPlated()",
                    [f"(constraint hole_size (min {val('nonplated_slot_min')}))"]))

    # --- Minimum Clearance ---
    out.append("\n\n# --- Minimum Clearance ---\n")
    out.append(rule(f"{p}: Hole to Hole Clearance (Different Nets)", "A.Net != B.Net",
                    [f"(constraint hole_to_hole (min {val('hole_to_hole_diff')}))"]))
    out.append("")
    out.append(rule(f"{p}: Via Hole to Via Hole Clearance (Same Net)",
                    "A.Type == 'Via' && B.Type == 'Via' && A.Net == B.Net",
                    [f"(constraint hole_to_hole (min {val('via_same_net')}))"]))
    out.append("")
    out.append(rule(f"{p}: Pad to Pad Clearance (Pad without Hole, Different Nets)",
                    "A.Type == 'Pad' && (A.Pad_Type != 'Through-hole' && A.Pad_Type != 'NPTH, mechanical') && B.Type == 'Pad' && (B.Pad_Type != 'Through-hole' && B.Pad_Type != 'NPTH, mechanical') && A.Net != B.Net",
                    [f"(constraint clearance (min {val('pad_nohole_diff')}))"]))
    out.append("")
    out.append(rule(f"{p}: Pad Hole to Pad Hole Clearance (Pad with Hole, Different Nets)",
                    "A.Type == 'Pad' && (A.Pad_Type == 'Through-hole' || A.Pad_Type == 'NPTH, mechanical') && B.Type == 'Pad' && (B.Pad_Type == 'Through-hole' || B.Pad_Type == 'NPTH, mechanical') && A.Net != B.Net",
                    [f"(constraint hole_to_hole (min {val('pad_hole_diff')}))"]))
    if fab.flags.get("emit_implied_clearance"):
        out.append("")
        out.append(rule(f"{p}: Via/Pad to Via/Pad Clearance (Different Nets)",
                        "(A.Type == 'Pad' || A.Type == 'Via') && (B.Type == 'Pad' || B.Type == 'Via') && A.Net != B.Net",
                        [f"(constraint clearance (min {val('implied_diff')}))"],
                        comment="Not stated specifically, but implied by other rules."))
        out.append("")
        out.append(rule(f"{p}: Via/Pad Hole to Via/Pad Hole Clearance (Same Net)",
                        "(A.Type == 'Pad' || A.Type == 'Via') && (B.Type == 'Pad' || B.Type == 'Via') && A.Net == B.Net",
                        [f"(constraint hole_to_hole (min {val('implied_same_net')}))"],
                        comment="Not stated specifically, but implied by other rules."))
    out.append("")
    out.append(rule(f"{p}: Via to Trace", "A.Type == 'Via' && B.Type == 'Track'",
                    [f"(constraint hole_clearance (min {val('via_to_trace')}))"]))
    out.append("")
    out.append(rule(f"{p}: PTH to Trace",
                    "A.Type == 'Pad' && A.Pad_Type == 'Through-hole' && A.isPlated() && B.Type == 'Track'",
                    [f"(constraint hole_clearance (min {val('pth_to_trace')}))"]))
    out.append("")
    out.append(rule(f"{p}: NPTH to Trace",
                    "A.Type == 'Pad' && A.Pad_Type == 'NPTH, mechanical' && !A.isPlated() && B.Type == 'Track'",
                    [f"(constraint hole_clearance (min {val('npth_to_trace')}))"]))
    out.append("")
    out.append(rule(f"{p}: NPTH to Copper (non-Track)",
                    "A.Type == 'Pad' && A.Pad_Type == 'NPTH, mechanical' && !A.isPlated() && B.Type != 'Track'",
                    [f"(constraint hole_clearance (min {val('npth_to_copper')}))"]))
    out.append("")
    out.append(rule(f"{p}: Pad to Trace",
                    "A.Type == 'Pad' && (A.Pad_Type == 'Through-hole' || A.Pad_Type == 'NPTH, mechanical') && B.Type == 'Track' && A.Net != B.Net",
                    [f"(constraint clearance (min {val('pad_to_trace')}))"]))
    if fab.flags.get("emit_bga"):
        out.append("")
        out.append(rule(f"{p}: BGA to Trace",
                        "A.NetClass == 'BGA' && B.Type == 'Track' && A.Net != B.Net",
                        [f"(constraint clearance (min {val('bga_to_trace')}))"],
                        comment="BGA fan-out clearance. Assign BGA fan-out nets to a 'BGA' net class."))

    # --- Minimum Trace Width and Spacing ---
    out.append("\n\n# --- Minimum Trace Width and Spacing ---\n")
    out.append(rule(f"{p}: Trace Width (Outer Layer)", "A.Type == 'Track'",
                    [f"(constraint track_width (min {val('trace_width_outer')}))"], layer="outer"))
    out.append("")
    out.append(rule(f"{p}: Trace Spacing (Outer Layer)", "A.Type == 'Track' && B.Type == 'Track'",
                    [f"(constraint clearance (min {val('trace_spacing_outer')}))"], layer="outer"))
    if has_inner:
        out.append("")
        out.append(rule(f"{p}: Trace Width (Inner Layer)", "A.Type == 'Track'",
                        [f"(constraint track_width (min {val('trace_width_inner')}))"], layer="inner"))
        out.append("")
        out.append(rule(f"{p}: Trace Spacing (Inner Layer)", "A.Type == 'Track' && B.Type == 'Track'",
                        [f"(constraint clearance (min {val('trace_spacing_inner')}))"], layer="inner"))

    # --- Impedance-Controlled Net Classes ---
    if fab.diffpairs:
        out.append("\n\n# --- Impedance-Controlled Net Classes ---")
        out.append("#")
        out.append("# WARNING: trace width/gap for a target impedance depend on YOUR stackup")
        out.append("# (dielectric height, Dk, copper weight). The values below are typical")
        out.append(f"# starting points for {fab.name}'s default stackup — verify against")
        out.append(f"# {fab.name}'s impedance calculator for your actual order. Constraints use")
        out.append("# (opt ...) so they guide the router without raising nuisance DRC errors;")
        out.append("# tighten to (min/max) once tuned. Assign nets to these classes in")
        out.append("# Board Setup > Net Classes.\n")
        for dp in fab.diffpairs:
            if dp.get("diff"):
                out.append(rule(f"{p}: {dp['name']} Differential Pair",
                                f"A.NetClass == '{dp['name']}'",
                                [f"(constraint track_width (opt {dp['track_width']}))",
                                 f"(constraint diff_pair_gap (opt {dp['gap']}))"]))
            else:
                out.append(rule(f"{p}: {dp['name']} Single-Ended",
                                f"A.NetClass == '{dp['name']}'",
                                [f"(constraint track_width (opt {dp['track_width']}))"]))
            out.append("")
        out.pop()  # drop trailing blank

    # --- Legend ---
    out.append("\n\n# --- Legend ---\n")
    out.append(rule(f"{p}: Minimum Line Width", "A.Type == 'Text' || A.Type == 'Text Box'",
                    [f"(constraint text_thickness (min {val('text_thickness')}))"], layer='"?.Silkscreen"'))
    out.append("")
    out.append(rule(f"{p}: Minimum Text Height", "A.Type == 'Text' || A.Type == 'Text Box'",
                    [f"(constraint text_height (min {val('text_height')}))"], layer='"?.Silkscreen"'))
    out.append("")
    out.append(rule(f"{p}: Pad to Silkscreen",
                    "A.Type == 'Pad' && ((A.existsOnLayer('F.Mask') && B.Layer == 'F.Silkscreen') || (A.existsOnLayer('B.Mask') && B.Layer == 'B.Silkscreen'))",
                    [f"(constraint silk_clearance (min {val('silk_clearance')}))"]))

    # --- Board Outlines ---
    out.append("\n\n# --- Board Outlines ---\n")
    out.append(rule(f"{p}: Trace to Board Edge", "A.Type == 'Track'",
                    [f"(constraint edge_clearance (min {val('edge_routed')}))"]))

    return "\n".join(out) + "\n"


def output_path(fab: Fab, variant: dict) -> str:
    if variant["id"] == fab.default_variant:
        fname = f"{fab.name}.kicad_dru"
    else:
        fname = f"{fab.name}-{variant['id']}.kicad_dru"
    return os.path.join(ROOT, fab.name, fname)


def main(argv: list) -> int:
    check = "--check" in argv[1:]
    toml_paths = sorted(glob.glob(os.path.join(ROOT, "capabilities", "*.toml")))
    if not toml_paths:
        print("no capabilities/*.toml files found", file=sys.stderr)
        return 1

    stale = []
    written = []
    for tp in toml_paths:
        with open(tp, "rb") as fh:
            fab = Fab(tomllib.load(fh))
        for variant in fab.variants:
            text = generate(fab, variant)
            path = output_path(fab, variant)
            existing = None
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as fh:
                    existing = fh.read()
            if check:
                if existing != text:
                    stale.append(os.path.relpath(path, ROOT))
            else:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(text)
                written.append(os.path.relpath(path, ROOT))

    if check:
        if stale:
            print("Generated files are out of date; run tools/generate_dru.py:", file=sys.stderr)
            for s in stale:
                print(f"  {s}", file=sys.stderr)
            return 1
        print("All generated files are up to date.")
        return 0

    for w in written:
        print(f"wrote {w}")
    print(f"\n{len(written)} file(s) generated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
