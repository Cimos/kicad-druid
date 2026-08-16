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
import re
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


def make_val(constants: dict, over: dict, label: str = ""):
    """Return a lookup that prefers the variant override, then the constant."""

    def val(key: str) -> str:
        if key in over:
            return over[key]
        if key in constants:
            return constants[key]
        where = f" for {label}" if label else ""
        raise KeyError(f"missing value '{key}'{where} — add it to the fab's TOML")

    return val


# Flags that, when set, require these value keys to be present.
FLAG_REQUIRES = {
    "avoid_kelvin_test": ["kelvin_annular"],
    "avoid_small_via_extra_cost": ["small_via_hole", "small_via_diameter"],
    "emit_implied_clearance": ["implied_diff", "implied_same_net"],
    "emit_bga": ["bga_to_trace"],
    "emit_same_net_trace_spacing": ["same_net_trace_spacing"],
}

# Every key that generate() consumes through val(...). Keep in sync with the
# val() calls below — validate() rejects anything outside this set, so a
# misspelled [constants] entry or [variant.over] override fails loudly instead
# of silently falling back to the constant it failed to override.
VALUE_KEYS = frozenset({
    "drill_hole_min", "drill_hole_max",
    "via_hole", "via_annular", "via_same_net", "via_to_trace",
    "small_via_hole", "small_via_diameter",
    "pth_hole_min", "pth_hole_max", "pth_annular", "pth_to_trace",
    "pth_to_trace_inner",
    "npth_hole_min", "npth_annular", "npth_to_trace", "npth_to_copper",
    "castellated_min", "kelvin_annular",
    "plated_slot_min", "nonplated_slot_min",
    "via_hole_diff", "via_pad_hole_diff", "pad_nohole_diff", "pad_hole_diff",
    "implied_diff", "implied_same_net",
    "pad_to_trace", "bga_to_trace",
    "trace_width_outer", "trace_spacing_outer",
    "trace_width_inner", "trace_spacing_inner",
    "same_net_trace_spacing",
    "text_thickness", "text_height", "silk_clearance", "edge_routed",
})

ALLOWED_FLAGS = frozenset({
    "avoid_kelvin_test", "avoid_small_via_extra_cost", "allow_blind_buried",
    "enforce_plated_slot_ratio", "emit_implied_clearance", "emit_bga",
    "merge_trace_layers", "emit_same_net_trace_spacing",
})
VARIANT_KEYS = frozenset({"id", "label", "layers", "over"})
DIFFPAIR_KEYS = frozenset({"name", "diff", "track_width", "gap"})

# Every value in [constants] and [variant.over] is a dimension. This repo's
# source of truth uses mm exclusively; a unit-less or malformed value is not a
# style problem — KiCad silently discards the ENTIRE rule file when a
# constraint carries a bare number, so it must never reach the output.
DIMENSION_RE = re.compile(r"^(\d+(?:\.\d+)?)mm$")


def check_dimension(owner: str, key: str, value) -> None:
    m = DIMENSION_RE.match(value) if isinstance(value, str) else None
    if not m:
        raise ValueError(
            f"{owner}: {key} = {value!r} is not a dimension — write a positive "
            f'size with its unit, e.g. "0.15mm"')
    if float(m.group(1)) == 0:
        raise ValueError(f"{owner}: {key} must be greater than zero")


def validate(fab: Fab) -> None:
    """Fail early and clearly on TOML mistakes rather than deep in generation."""
    if not fab.variants:
        raise ValueError(f"{fab.name}: no [[variant]] blocks defined")

    ids = [v.get("id") for v in fab.variants]
    if None in ids:
        raise ValueError(f"{fab.name}: every [[variant]] needs an id")
    if len(set(ids)) != len(ids):
        raise ValueError(f"{fab.name}: duplicate variant ids in {ids}")
    if fab.default_variant not in ids:
        raise ValueError(
            f"{fab.name}: default_variant '{fab.default_variant}' is not one of {ids}")

    for flag, keys in FLAG_REQUIRES.items():
        if fab.flags.get(flag):
            missing = [k for k in keys if k not in fab.constants]
            if missing:
                raise ValueError(
                    f"{fab.name}: flag '{flag}' is set but [constants] is missing {missing}")

    unknown = sorted(set(fab.flags) - ALLOWED_FLAGS)
    if unknown:
        raise ValueError(
            f"{fab.name}: unknown [flags] key(s) {unknown} — allowed: {sorted(ALLOWED_FLAGS)}")

    unknown = sorted(set(fab.constants) - VALUE_KEYS)
    if unknown:
        raise ValueError(
            f"{fab.name}: unknown [constants] key(s) {unknown} — see VALUE_KEYS in "
            f"tools/generate_dru.py for the full vocabulary")
    for key, value in fab.constants.items():
        check_dimension(f"{fab.name} [constants]", key, value)

    for v in fab.variants:
        vid = v.get("id")
        unknown = sorted(set(v) - VARIANT_KEYS)
        if unknown:
            raise ValueError(
                f"{fab.name} {vid}: unknown [[variant]] key(s) {unknown} — "
                f"allowed: {sorted(VARIANT_KEYS)}")
        layers = v.get("layers")
        if not isinstance(layers, int) or isinstance(layers, bool) or layers < 1:
            raise ValueError(
                f"{fab.name} {vid}: every [[variant]] needs 'layers' as a positive "
                f"integer (e.g. layers = 4) — without it a multilayer variant would "
                f"silently generate without its inner-layer rules")
        over = v.get("over", {})
        unknown = sorted(set(over) - VALUE_KEYS)
        if unknown:
            raise ValueError(
                f"{fab.name} {vid}: unknown [variant.over] key(s) {unknown} — a "
                f"misspelled override would silently fall back to the constant")
        for key, value in over.items():
            check_dimension(f"{fab.name} {vid} [variant.over]", key, value)

    for dp in fab.diffpairs:
        if "name" not in dp or "track_width" not in dp:
            raise ValueError(f"{fab.name}: every [[diffpair]] needs a name and track_width")
        if dp.get("diff") and "gap" not in dp:
            raise ValueError(
                f"{fab.name}: differential net class '{dp['name']}' needs a gap")
        unknown = sorted(set(dp) - DIFFPAIR_KEYS)
        if unknown:
            raise ValueError(
                f"{fab.name} {dp['name']}: unknown [[diffpair]] key(s) {unknown} — "
                f"allowed: {sorted(DIFFPAIR_KEYS)}")
        for key in ("track_width", "gap"):
            if key in dp:
                check_dimension(f"{fab.name} {dp['name']} [[diffpair]]", key, dp[key])


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
    val = make_val(fab.constants, over, f"{fab.name} {variant.get('id', '?')}")

    def has_val(key: str) -> bool:
        return key in over or key in fab.constants
    # validate() guarantees 'layers' is present and a positive integer; no
    # default here — a silent fallback is how a 4-layer variant once lost its
    # inner-layer rules.
    layers = variant["layers"]
    has_inner = layers > 2

    out: list = []
    out.append("(version 1)")
    out.append(f"# Custom Design Rules (DRC) for KiCad — {fab.name}: {variant['label']}")
    out.append("#")
    out.append(f"# Matching {fab.name} capabilities: {fab.url}")
    others = [v["id"] for v in fab.variants if v.get("id") != variant.get("id")]
    if others:
        out.append("#")
        out.append(f"# This is the '{variant['id']}' variant. If your order differs, use one of")
        out.append(f"# the other variants ({', '.join(others)}) — see the README table.")
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
    if fab.flags.get("avoid_small_via_extra_cost"):
        out.append("")
        out.append(rule(
            f"{p}: Via diameter < {val('small_via_diameter')} with hole < {val('small_via_hole')} adds extra cost",
            f"(A.Type == 'Via') && (A.Hole < {val('small_via_hole')})",
            [f"(constraint via_diameter (min {val('small_via_diameter')}))"],
            comment="Comment out if extra cost is OK."))
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
    if fab.flags.get("enforce_plated_slot_ratio"):
        out.append("")
        out.append(rule(
            f"{p}: Plated Slot Length-to-width Ratio",
            "(A.Type == 'Pad')",
            ['(constraint assertion "(A.Hole_Size_X == A.Hole_Size_Y) || (A.Hole_Size_X >= (2 * A.Hole_Size_Y)) || (A.Hole_Size_Y >= (2 * A.Hole_Size_X))")'],
            comment=f'{fab.name}: "The length of the slot should be at least 2 times of the width."'))
    out.append("")
    out.append(rule(f"{p}: Non-Plated Slot Width",
                    "A.Type == 'Pad' && (A.Hole_Size_X != A.Hole_Size_Y) && !A.isPlated()",
                    [f"(constraint hole_size (min {val('nonplated_slot_min')}))"]))

    # --- Minimum Clearance ---
    out.append("\n\n# --- Minimum Clearance ---\n")
    out.append(rule(f"{p}: Via Hole to Via Hole Clearance (Different Nets)",
                    "A.Type == 'Via' && B.Type == 'Via' && A.Net != B.Net",
                    [f"(constraint hole_to_hole (min {val('via_hole_diff')}))"]))
    out.append("")
    out.append(rule(f"{p}: Pad Hole to Pad Hole Clearance (Pad with Hole, Different Nets)",
                    "A.Type == 'Pad' && (A.Pad_Type == 'Through-hole' || A.Pad_Type == 'NPTH, mechanical') && B.Type == 'Pad' && (B.Pad_Type == 'Through-hole' || B.Pad_Type == 'NPTH, mechanical') && A.Net != B.Net",
                    [f"(constraint hole_to_hole (min {val('pad_hole_diff')}))"]))
    if fab.flags.get("emit_implied_clearance"):
        out.append("")
        out.append("# NOTE: KiCad applies the LAST matching rule, so the general \"implied\" rules below\n# must come before the specific ones they would otherwise override.")
        out.append("")
        out.append(rule(f"{p}: Via/Pad to Via/Pad Clearance (Different Nets)",
                        "(A.Type == 'Pad' || A.Type == 'Via') && (B.Type == 'Pad' || B.Type == 'Via') && A.Net != B.Net",
                        [f"(constraint clearance (min {val('implied_diff')}))"],
                        comment="NOTE: This is not stated specifically, but is implied by other rules."))
        out.append("")
        out.append(rule(f"{p}: Via/Pad Hole to Via/Pad Hole Clearance (Same Net)",
                        "(A.Type == 'Pad' || A.Type == 'Via') && (B.Type == 'Pad' || B.Type == 'Via') && A.Net == B.Net",
                        [f"(constraint hole_to_hole (min {val('implied_same_net')}))"],
                        comment="NOTE: This is not stated specifically, but is implied by other rules."))
    if has_val("via_same_net"):
        out.append("")
        out.append(rule(f"{p}: Via Hole to Via Hole Clearance (Same Net)",
                        "A.Type == 'Via' && B.Type == 'Via' && A.Net == B.Net",
                        [f"(constraint hole_to_hole (min {val('via_same_net')}))"]))
    out.append("")
    out.append(rule(
        f"{p}: Via Hole to Pad Hole Clearance (Different Nets)",
        "((A.Type == 'Via' && B.Type == 'Pad') || (A.Type == 'Pad' && B.Type == 'Via')) && A.Net != B.Net",
        [f"(constraint hole_to_hole (min {val('via_pad_hole_diff')}))"],
        comment=("NOTE: This is not stated specifically, but is implied by other rules.\n"
                 "A via and a plated pad on different nets are not covered by either the\n"
                 "via-to-via or the pad-to-pad hole spacing rule; the pair involves a pad\n"
                 "hole, so the pad figure applies."
                 if fab.flags.get("emit_implied_clearance") else "")))
    out.append("")
    out.append(rule(
        f"{p}: Pad to Pad Clearance (Pad without Hole, Different Nets)",
        "A.Type == 'Pad' && (A.Pad_Type != 'Through-hole' && A.Pad_Type != 'NPTH, mechanical') && B.Type == 'Pad' && (B.Pad_Type != 'Through-hole' && B.Pad_Type != 'NPTH, mechanical') && A.Net != B.Net",
        [f"(constraint clearance (min {val('pad_nohole_diff')}))"],
        comment=("Specific rule: must sit after the general clearance rule above to take effect."
                 if fab.flags.get("emit_implied_clearance") else "")))
    out.append("")
    out.append(rule(f"{p}: Via to Trace", "A.Type == 'Via' && B.Type == 'Track'",
                    [f"(constraint hole_clearance (min {val('via_to_trace')}))"]))
    out.append("")
    out.append(rule(f"{p}: PTH to Trace",
                    "A.Type == 'Pad' && A.Pad_Type == 'Through-hole' && A.isPlated() && B.Type == 'Track'",
                    [f"(constraint hole_clearance (min {val('pth_to_trace')}))"]))
    if has_inner and has_val("pth_to_trace_inner"):
        out.append("")
        out.append(rule(f"{p}: PTH to Trace (inner layer)",
                        "A.Type == 'Pad' && A.Pad_Type == 'Through-hole' && A.isPlated() && B.Type == 'Track'",
                        [f"(constraint hole_clearance (min {val('pth_to_trace_inner')}))"],
                        layer="inner"))
    out.append("")
    out.append(rule(f"{p}: NPTH to Trace",
                    "A.Type == 'Pad' && A.Pad_Type == 'NPTH, mechanical' && !A.isPlated() && B.Type == 'Track'",
                    [f"(constraint hole_clearance (min {val('npth_to_trace')}))"]))
    if has_val("npth_to_copper"):
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
    if fab.flags.get("merge_trace_layers"):
        out.append(rule(f"{p}: Trace Width", "A.Type == 'Track'",
                        [f"(constraint track_width (min {val('trace_width_outer')}))"]))
        out.append("")
        out.append(rule(f"{p}: Trace Spacing", "A.Type == 'Track' && B.Type == 'Track'",
                        [f"(constraint clearance (min {val('trace_spacing_outer')}))"]))
    else:
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
    if fab.flags.get("emit_same_net_trace_spacing"):
        out.append("")
        out.append("\n".join([
            "# As of KiCad 9.0.8, this incorrectly flags any kind of connection",
            "# between tracks (even if the track continues straight on and is just",
            "# split into two parts with \"Break Track\").",
            f'# (rule "{p}: Same-net Trace Spacing"',
            "# \t(condition \"A.Type == 'Track' && B.Type == 'Track'\")",
            f"# \t(constraint physical_clearance (min {val('same_net_trace_spacing')}))",
            "# )",
        ]))

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
                    [f"(constraint text_thickness (min {val('text_thickness')}))"], layer='"?.SilkS"'))
    out.append("")
    out.append(rule(f"{p}: Minimum Text Height", "A.Type == 'Text' || A.Type == 'Text Box'",
                    [f"(constraint text_height (min {val('text_height')}))"], layer='"?.SilkS"'))
    out.append("")
    out.append(rule(f"{p}: Pad to Silkscreen",
                    "A.Type == 'Pad' && ((A.existsOnLayer('F.Mask') && B.Layer == 'F.SilkS') || (A.existsOnLayer('B.Mask') && B.Layer == 'B.SilkS'))",
                    [f"(constraint silk_clearance (min {val('silk_clearance')}))"]))

    # --- Board Outlines ---
    out.append("\n\n# --- Board Outlines ---\n")
    out.append(rule(f"{p}: Trace to Board Edge", "A.Type == 'Track'",
                    [f"(constraint edge_clearance (min {val('edge_routed')}))"]))

    return "\n".join(out) + "\n"


def find_orphans(expected_paths: set, root: str) -> list:
    """Every .kicad_dru one directory below root that no fab generates.

    One level deep is where output_path() writes; scanning from root rather
    than per fab directory means files survive detection even when their fab
    TOML was deleted or renamed.
    """
    on_disk = set(glob.glob(os.path.join(root, "*", "*.kicad_dru")))
    return sorted(on_disk - expected_paths)


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
    expected_all: dict = {}
    for tp in toml_paths:
        with open(tp, "rb") as fh:
            fab = Fab(tomllib.load(fh))
        validate(fab)

        expected = {}
        for variant in fab.variants:
            expected[output_path(fab, variant)] = generate(fab, variant)
        expected_all.update(expected)

        for path, text in expected.items():
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

    # Orphans: any .kicad_dru no loaded TOML generates. Scanned repo-wide, not
    # per fab directory — a per-fab scan misses files left behind when a whole
    # fab TOML is deleted or its [fab].name changes, leaving stale rules
    # published while --check reports everything current.
    for orphan in find_orphans(set(expected_all), ROOT):
        rel = os.path.relpath(orphan, ROOT)
        if check:
            stale.append(f"{rel} (orphaned — no fab TOML generates it)")
        else:
            os.remove(orphan)
            print(f"removed orphan {rel}")

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
