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
        # Header text. A fab read from TOML points at its own TOML; a derived
        # fab (see build_generic) replaces these with where it really came from.
        self.intro_lines = [f"Matching {self.name} capabilities: {self.url}"]
        self.edit_note = [
            f"Edit capabilities/{self.name}.toml and run tools/generate_dru.py instead."]
        self.notes: list = []
        # Who a quoted capability line and the impedance warning name. For a
        # derived fab these are not the fab itself.
        self.flag_sources: dict = {}
        self.impedance_owner = self.name
        # variant id -> lines naming the fab behind each value.
        self.value_sources: dict = {}


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
    "emit_smd_pad_min": ["smd_pad_min"],
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
    "smd_pad_min",
    "trace_width_outer", "trace_spacing_outer",
    "trace_width_inner", "trace_spacing_inner",
    "same_net_trace_spacing",
    "text_thickness", "text_height", "silk_clearance", "edge_routed",
})

ALLOWED_FLAGS = frozenset({
    "avoid_kelvin_test", "avoid_small_via_extra_cost", "allow_blind_buried",
    "enforce_plated_slot_ratio", "emit_implied_clearance", "emit_bga",
    "merge_trace_layers", "emit_same_net_trace_spacing",
    "emit_smd_pad_min",
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


# --- The derived "Generic" fab ---------------------------------------------
#
# Generic is not a fab and has no capabilities/Generic.toml: it is computed
# from the fab TOMLs every time the generator runs. For each limit it keeps
# whichever fab is harder to satisfy, so a board that passes the Generic rules
# passes at either fab. That is what a board designed before the fab is picked
# needs; the cost is that no limit is ever relaxed to the easier fab's figure.

GENERIC_NAME = "Generic"

# How each value key combines across fabs. A key that feeds a `(min ...)`
# constraint is strictest at its LARGEST value; a key that feeds a `(max ...)`
# constraint is strictest at its SMALLEST. Only two keys feed a max: the upper
# end of the two hole_size ranges.
#
# small_via_hole feeds no constraint — it is the hole size below which JLCPCB
# charges extra, used in a condition. A larger threshold catches more vias, so
# it behaves like a min key. Everything else is a plain `(min ...)`.
MAX_KEYS = frozenset({"drill_hole_max", "pth_hole_max"})
MIN_KEYS = frozenset(VALUE_KEYS - MAX_KEYS)

# When a fab publishes one trace limit for every copper layer, that limit is
# also what it allows on inner copper — so it still has a say in the inner
# value even though it carries no inner key of its own.
MERGED_INNER_SOURCE = {
    "trace_width_inner": "trace_width_outer",
    "trace_spacing_inner": "trace_spacing_outer",
}

# Flags are combined so Generic emits every rule that either fab emits. Most
# flags add a rule when true, so they are OR-ed. These two take rules away:
# allow_blind_buried drops the through-hole-only assertion, and
# merge_trace_layers replaces the outer/inner trace rules with one unlayered
# rule that cannot carry a separate, stricter inner limit. They are only kept
# when every fab sets them.
FLAGS_KEPT_ONLY_IF_ALL = frozenset({"allow_blind_buried", "merge_trace_layers"})

# Ranges whose two ends can now come from different fabs.
RANGE_PAIRS = [("drill_hole_min", "drill_hole_max"), ("pth_hole_min", "pth_hole_max")]


def mm(value: str) -> float:
    m = DIMENSION_RE.match(value)
    if not m:
        raise ValueError(f"{value!r} is not a dimension")
    return float(m.group(1))


def variant_by_id(fab: Fab, vid: str):
    for v in fab.variants:
        if v["id"] == vid:
            return v
    return None


def resolve(fab: Fab, variant: dict) -> dict:
    """Every value one variant of one fab ends up with."""
    m = dict(fab.constants)
    m.update(variant.get("over", {}))
    return m


def strictest(key: str, candidates: list):
    """Return (value, [fab names]) for the harder-to-satisfy candidate."""
    pick = max if key in MIN_KEYS else min
    best = pick(mm(v) for _, v in candidates)
    winners = [(n, v) for n, v in candidates if mm(v) == best]
    return winners[0][1], [n for n, _ in winners]


def build_generic(fabs: list) -> Fab:
    """Combine the loaded fabs into the Generic pseudo-fab."""
    if len(fabs) < 2:
        raise ValueError("Generic needs at least two fabs to combine")
    names = [f.name for f in fabs]

    # Only the variants every fab offers; order follows the first fab.
    ids = [v["id"] for v in fabs[0].variants
           if all(variant_by_id(f, v["id"]) for f in fabs[1:])]
    if not ids:
        raise ValueError("Generic: the fabs share no variant id")

    flags = {}
    for flag in sorted(ALLOWED_FLAGS):
        set_by = [bool(f.flags.get(flag)) for f in fabs]
        flags[flag] = all(set_by) if flag in FLAGS_KEPT_ONLY_IF_ALL else any(set_by)

    chosen_by_variant = {}  # variant id -> {key: (value, [fab names])}
    for vid in ids:
        maps = {f.name: resolve(f, variant_by_id(f, vid)) for f in fabs}
        keys = set()
        for m in maps.values():
            keys |= set(m)
        chosen = {}
        for key in sorted(keys):
            candidates = []
            for f in fabs:
                m = maps[f.name]
                if key in m:
                    candidates.append((f.name, m[key]))
                elif (key in MERGED_INNER_SOURCE
                      and f.flags.get("merge_trace_layers")
                      and MERGED_INNER_SOURCE[key] in m):
                    candidates.append((f.name, m[MERGED_INNER_SOURCE[key]]))
            chosen[key] = strictest(key, candidates)
        for lo, hi in RANGE_PAIRS:
            if lo in chosen and hi in chosen and mm(chosen[lo][0]) > mm(chosen[hi][0]):
                raise ValueError(
                    f"Generic {vid}: {lo} ({chosen[lo][0]}) is above {hi} "
                    f"({chosen[hi][0]}) — the fabs leave no usable range")
        chosen_by_variant[vid] = chosen

    # A key with the same value in every variant is a constant; the rest are
    # per-variant overrides, the same split the fab TOMLs use.
    shared = set.intersection(*(set(chosen_by_variant[i]) for i in ids))
    constants = {}
    for key in sorted(shared):
        values = {chosen_by_variant[i][key][0] for i in ids}
        if len(values) == 1:
            constants[key] = values.pop()

    variants = []
    for vid in ids:
        layers = {variant_by_id(f, vid)["layers"] for f in fabs}
        if len(layers) != 1:
            raise ValueError(
                f"Generic {vid}: fabs disagree on the layer count {sorted(layers)}")
        variants.append({
            "id": vid,
            "label": variant_by_id(fabs[0], vid)["label"],
            "layers": layers.pop(),
            "over": {k: v for k, (v, _) in sorted(chosen_by_variant[vid].items())
                     if k not in constants},
        })

    class_names = []
    for f in fabs:
        for dp in f.diffpairs:
            if dp["name"] not in class_names:
                class_names.append(dp["name"])
    diffpairs = []
    for cn in class_names:
        entries = [dp for f in fabs for dp in f.diffpairs if dp["name"] == cn]
        merged = {
            "name": cn,
            "diff": any(dp.get("diff") for dp in entries),
            "track_width": max((dp["track_width"] for dp in entries), key=mm),
        }
        if merged["diff"]:
            merged["gap"] = max((dp["gap"] for dp in entries if "gap" in dp), key=mm)
        diffpairs.append(merged)

    default = fabs[0].default_variant if fabs[0].default_variant in ids else ids[0]
    generic = Fab({
        "fab": {"name": GENERIC_NAME, "prefix": GENERIC_NAME,
                "capabilities_url": "", "default_variant": default},
        "flags": flags,
        "constants": constants,
        "variant": variants,
        "diffpair": diffpairs,
    })
    generic.intro_lines = [
        "The strictest of " + " and ".join(names) + ". Every limit is the harder of",
        "the two, so a board that passes these rules passes at either fab. Use it",
        "while the fab is still open. Nothing is relaxed to the easier figure, so a",
        "board built to it can cost more than one built to a single fab's file.",
    ] + [f"{f.name} capabilities: {f.url}" for f in fabs]
    generic.edit_note = [
        "Derived in code from "
        + " and ".join(f"capabilities/{f.name}.toml" for f in fabs) + " by",
        "tools/generate_dru.py. There is no capabilities/Generic.toml.",
    ]
    # A quoted capability line belongs to the fab that published it, not to
    # Generic, and the impedance figures suit neither fab's stackup in
    # particular.
    for flag in flags:
        setters = [f.name for f in fabs if f.flags.get(flag)]
        if setters:
            generic.flag_sources[flag] = " and ".join(setters)
    generic.impedance_owner = "your fab"
    generic.notes = [
        "Where the fabs give a different width or gap for the same impedance net",
        "class, the wider track and the larger gap are used.",
    ]
    for vid in ids:
        generic.value_sources[vid] = [
            f"{key}: {value} ({', '.join(src)})"
            for key, (value, src) in sorted(chosen_by_variant[vid].items())
        ]
    validate(generic)
    return generic


def load_fabs(root: str = ROOT) -> list:
    """Every fab TOML, plus the Generic fab derived from them."""
    fabs = []
    for tp in sorted(glob.glob(os.path.join(root, "capabilities", "*.toml"))):
        with open(tp, "rb") as fh:
            fab = Fab(tomllib.load(fh))
        validate(fab)
        fabs.append(fab)
    if len(fabs) > 1:
        fabs.append(build_generic(fabs))
    return fabs


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
    out.extend(f"# {line}" for line in fab.intro_lines)
    others = [v["id"] for v in fab.variants if v.get("id") != variant.get("id")]
    if others:
        out.append("#")
        out.append(f"# This is the '{variant['id']}' variant. If your order differs, use one of")
        out.append(f"# the other variants ({', '.join(others)}) — see the README table.")
    out.append("#")
    out.append("# GENERATED FILE — do not edit by hand.")
    out.extend(f"# {line}" for line in fab.edit_note)
    if fab.notes:
        out.append("#")
        out.extend(f"# {line}" for line in fab.notes)
    sources = fab.value_sources.get(variant["id"])
    if sources:
        out.append("#")
        out.append("# Where each value came from:")
        out.extend(f"# {line}" for line in sources)
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
                    [f"(constraint hole_size (min {val('castellated_min')}))"]))
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

    # --- Pad Size ---
    if fab.flags.get("emit_smd_pad_min"):
        out.append("\n\n# --- Pad Size ---\n")
        out.append(rule(
            f"{p}: SMD Pad Size",
            f"A.Type == 'Pad' && A.Pad_Type == 'SMD' && (A.Size_X < {val('smd_pad_min')} || A.Size_Y < {val('smd_pad_min')})",
            [f'(constraint assertion "A.Size_X >= {val("smd_pad_min")} && A.Size_Y >= {val("smd_pad_min")}")'],
            comment=(f"{fab.name}'s hard lower limit for an SMD pad. Their recommended\n"
                     "minimum is larger; this only catches pads the fab cannot make.")))

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
            comment='%s: "The length of the slot should be at least 2 times of the width."'
                    % fab.flag_sources.get("enforce_plated_slot_ratio", fab.name)))
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
        f"{p}: Via Hole to Pad Hole Clearance (Different Nets, inferred)",
        "((A.Type == 'Via' && B.Type == 'Pad') || (A.Type == 'Pad' && B.Type == 'Via')) && A.Net != B.Net",
        [f"(constraint hole_to_hole (min {val('via_pad_hole_diff')}))"],
        comment=("NOTE: Inferred from the pad-to-pad hole figure; not documented by the fab.\n"
                 "A via and a plated pad on different nets are covered by neither the\n"
                 "via-to-via nor the pad-to-pad hole spacing rule; the pair involves a pad\n"
                 "hole, so the pad figure applies.")))
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
        out.append(f"# starting points for {fab.impedance_owner}'s default stackup — verify against")
        out.append(f"# {fab.impedance_owner}'s impedance calculator for your actual order. Constraints use")
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
    fabs = load_fabs()
    if not fabs:
        print("no capabilities/*.toml files found", file=sys.stderr)
        return 1

    stale = []
    written = []
    expected_all: dict = {}
    for fab in fabs:
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
