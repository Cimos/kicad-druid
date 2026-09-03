# Fab capability comparison

<!-- GENERATED FILE — do not edit by hand. -->
<!-- Run tools/gen_comparison.py after editing capabilities/*.toml. -->

Side-by-side of the design-rule values each fab enforces, read from `capabilities/*.toml`. All values in mm unless noted.

`Generic` is not a fab and has no TOML: it is derived from the others by taking the harder limit of each pair, for boards designed before the fab is chosen.

## Fixed limits

Shown at each fab's default variant **JLCPCB**: `4L-1oz`, **PCBWay**: `4L-1oz`, **Generic**: `4L-1oz`.

| Parameter | JLCPCB | PCBWay | Generic |
|---|---|---|---|
| Drill hole — max | 6.3mm | 6.3mm | 6.3mm |
| Via annular ring — min | 0.05mm | 0.15mm | 0.15mm |
| PTH hole — min | 0.15mm | 0.2mm | 0.2mm |
| PTH hole — max | 6.3mm | 6.35mm | 6.3mm |
| NPTH hole — min | 0.5mm | 0.5mm | 0.5mm |
| Castellated hole — min | 0.5mm | 0.6mm | 0.6mm |
| PTH annular ring — min | 0.15mm | 0.15mm | 0.15mm |
| NPTH annular ring — min | 0.45mm | 0.25mm | 0.45mm |
| Plated slot width — min | 0.35mm | 0.5mm | 0.5mm |
| Non-plated slot width — min | 1.0mm | 0.8mm | 1.0mm |
| Small-via extra-cost hole threshold | 0.3mm | — | 0.3mm |
| Small-via diameter to avoid extra cost | 0.45mm | — | 0.45mm |
| Via hole-to-hole, different nets | 0.2mm | 0.5mm | 0.5mm |
| Via hole-to-pad hole, different nets | 0.45mm | 0.5mm | 0.5mm |
| Via hole-to-hole, same net | — | 0.254mm | 0.254mm |
| Pad-to-pad (no hole), different nets | 0.15mm | 0.127mm | 0.15mm |
| Pad hole-to-hole (with hole), different nets | 0.45mm | 0.5mm | 0.5mm |
| Via hole to trace | 0.2mm | 0.254mm | 0.254mm |
| PTH hole to trace | 0.28mm | 0.33mm | 0.33mm |
| PTH hole to trace (inner layer) | 0.3mm | — | 0.3mm |
| NPTH hole to trace | 0.2mm | 0.254mm | 0.254mm |
| NPTH to copper (non-track) | 0.2mm | 0.20mm | 0.2mm |
| Pad to trace | 0.2mm | 0.2mm | 0.2mm |
| SMD pad size — min | 0.125mm | — | 0.125mm |
| BGA to trace | 0.1mm | — | 0.1mm |
| Same-net trace spacing (disabled workaround) | 0.25mm | — | 0.25mm |
| Silk line width — min | 0.15mm | 0.15mm | 0.15mm |
| Silk text height — min | 1mm | 0.8mm | 1mm |
| Pad to silkscreen | 0.15mm | 0.15mm | 0.15mm |
| Trace to board edge (routed) | 0.2mm | 0.3mm | 0.3mm |

## By build variant

### JLCPCB

| Variant | Drill hole — min | Via hole — min | Trace width (outer) | Trace spacing (outer) | Trace width (inner) | Trace spacing (inner) |
|---|---|---|---|---|---|---|
| `2L-1oz` | 0.3mm | 0.3mm | 0.1mm | 0.1mm | — | — |
| `4L-1oz` (default) | 0.15mm | 0.15mm | 0.09mm | 0.09mm | 0.09mm | 0.09mm |
| `4L-2oz` | 0.15mm | 0.15mm | 0.15mm | 0.15mm | 0.15mm | 0.15mm |
| `6L-1oz` | 0.15mm | 0.15mm | 0.09mm | 0.09mm | 0.09mm | 0.09mm |

### PCBWay

| Variant | Drill hole — min | Via hole — min | Trace width (outer) | Trace spacing (outer) | Trace width (inner) | Trace spacing (inner) |
|---|---|---|---|---|---|---|
| `2L-1oz` | 0.15mm | 0.3mm | 0.127mm | 0.127mm | — | — |
| `4L-1oz` (default) | 0.15mm | 0.2mm | 0.09mm | 0.09mm | 0.1mm | 0.1mm |
| `4L-2oz` | 0.15mm | 0.2mm | 0.1524mm | 0.1778mm | 0.1524mm | 0.1778mm |
| `6L-1oz` | 0.15mm | 0.2mm | 0.09mm | 0.09mm | 0.1mm | 0.1mm |

### Generic

| Variant | Drill hole — min | Via hole — min | Trace width (outer) | Trace spacing (outer) | Trace width (inner) | Trace spacing (inner) |
|---|---|---|---|---|---|---|
| `2L-1oz` | 0.3mm | 0.3mm | 0.127mm | 0.127mm | — | — |
| `4L-1oz` (default) | 0.15mm | 0.2mm | 0.09mm | 0.09mm | 0.1mm | 0.1mm |
| `4L-2oz` | 0.15mm | 0.2mm | 0.1524mm | 0.1778mm | 0.1524mm | 0.1778mm |
| `6L-1oz` | 0.15mm | 0.2mm | 0.09mm | 0.09mm | 0.1mm | 0.1mm |

## Impedance-controlled net classes

> Typical starting values for each fab's default stackup — **verify against the fab's impedance calculator for your actual stackup.**

| Net class | JLCPCB (width / gap) | PCBWay (width / gap) | Generic (width / gap) |
|---|---|---|---|
| `50R` | 0.2mm / n/a | 0.2mm / n/a | 0.2mm / n/a |
| `60R_Diff` | 0.3mm / 0.15mm | 0.3mm / 0.15mm | 0.3mm / 0.15mm |
| `90R_Diff` | 0.2mm / 0.13mm | 0.2mm / 0.13mm | 0.2mm / 0.13mm |
| `100R_Diff` | 0.2mm / 0.2mm | 0.2mm / 0.2mm | 0.2mm / 0.2mm |
| `120R_Diff` | 0.15mm / 0.2mm | 0.15mm / 0.2mm | 0.15mm / 0.2mm |

## Process notes

|  | JLCPCB | PCBWay | Generic |
|---|---|---|---|
| Avoids JLCPCB 4-wire Kelvin test | yes | no | yes |
| Avoids small-via extra cost | yes | no | yes |
| Blind/buried vias allowed | no | yes | no |
| Enforces plated-slot length/width ratio | yes | no | yes |
| Ships a BGA fan-out rule | yes | no | yes |
| Ships implied catch-all clearances | yes | no | yes |
| Uses one trace limit for all copper layers | yes | no | no |
| Documents disabled same-net spacing workaround | yes | no | yes |
| Ships a minimum SMD pad size rule | yes | no | yes |

