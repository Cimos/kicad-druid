# Fab capability comparison

<!-- GENERATED FILE — do not edit by hand. -->
<!-- Run tools/gen_comparison.py after editing capabilities/*.toml. -->

Side-by-side of the design-rule values each fab enforces, read from `capabilities/*.toml`. All values in mm unless noted.

## Fixed limits

Shown at each fab's default variant **JLCPCB**: `4L-1oz`, **PCBWay**: `4L-1oz`.

| Parameter | JLCPCB | PCBWay |
|---|---|---|
| Drill hole — max | 6.3mm | 6.3mm |
| Via annular ring — min | 0.05mm | 0.15mm |
| PTH hole — min | 0.2mm | 0.2mm |
| PTH hole — max | 6.3mm | 6.35mm |
| NPTH hole — min | 0.5mm | 0.5mm |
| Castellated hole — min | 0.6mm | 0.6mm |
| PTH annular ring — min | 0.15mm | 0.15mm |
| NPTH annular ring — min | 0.45mm | 0.25mm |
| Plated slot width — min | 0.5mm | 0.5mm |
| Non-plated slot width — min | 1.0mm | 0.8mm |
| Small-via extra-cost hole threshold | 0.3mm | — |
| Small-via diameter to avoid extra cost | 0.45mm | — |
| Via hole-to-hole, different nets | 0.2mm | 0.5mm |
| Via hole-to-pad hole, different nets | 0.45mm | 0.5mm |
| Via hole-to-hole, same net | — | 0.254mm |
| Pad-to-pad (no hole), different nets | 0.15mm | 0.127mm |
| Pad hole-to-hole (with hole), different nets | 0.45mm | 0.5mm |
| Via hole to trace | 0.2mm | 0.254mm |
| PTH hole to trace | 0.28mm | 0.33mm |
| PTH hole to trace (inner layer) | 0.3mm | — |
| NPTH hole to trace | 0.2mm | 0.254mm |
| NPTH to copper (non-track) | 0.2mm | 0.20mm |
| Pad to trace | 0.2mm | 0.2mm |
| BGA to trace | 0.1mm | — |
| Same-net trace spacing (disabled workaround) | 0.25mm | — |
| Silk line width — min | 0.15mm | 0.15mm |
| Silk text height — min | 1mm | 0.8mm |
| Pad to silkscreen | 0.15mm | 0.15mm |
| Trace to board edge (routed) | 0.3mm | 0.3mm |

## By build variant

### JLCPCB

| Variant | Drill hole — min | Via hole — min | Trace width (outer) | Trace spacing (outer) | Trace width (inner) | Trace spacing (inner) |
|---|---|---|---|---|---|---|
| `2L-1oz` | 0.3mm | 0.3mm | 0.1mm | 0.1mm | — | — |
| `4L-1oz` (default) | 0.2mm | 0.2mm | 0.09mm | 0.09mm | 0.09mm | 0.09mm |
| `4L-2oz` | 0.2mm | 0.2mm | 0.15mm | 0.15mm | 0.15mm | 0.15mm |
| `6L-1oz` | 0.2mm | 0.2mm | 0.09mm | 0.09mm | 0.09mm | 0.09mm |

### PCBWay

| Variant | Drill hole — min | Via hole — min | Trace width (outer) | Trace spacing (outer) | Trace width (inner) | Trace spacing (inner) |
|---|---|---|---|---|---|---|
| `2L-1oz` | 0.15mm | 0.3mm | 0.127mm | 0.127mm | — | — |
| `4L-1oz` (default) | 0.15mm | 0.2mm | 0.09mm | 0.09mm | 0.1mm | 0.1mm |
| `4L-2oz` | 0.15mm | 0.2mm | 0.1524mm | 0.1778mm | 0.1524mm | 0.1778mm |
| `6L-1oz` | 0.15mm | 0.2mm | 0.09mm | 0.09mm | 0.1mm | 0.1mm |

## Impedance-controlled net classes

> Typical starting values for each fab's default stackup — **verify against the fab's impedance calculator for your actual stackup.**

| Net class | JLCPCB (width / gap) | PCBWay (width / gap) |
|---|---|---|
| `50R` | 0.2mm / n/a | 0.2mm / n/a |
| `60R_Diff` | 0.3mm / 0.15mm | 0.3mm / 0.15mm |
| `90R_Diff` | 0.2mm / 0.13mm | 0.2mm / 0.13mm |
| `100R_Diff` | 0.2mm / 0.2mm | 0.2mm / 0.2mm |
| `120R_Diff` | 0.15mm / 0.2mm | 0.15mm / 0.2mm |

## Process notes

|  | JLCPCB | PCBWay |
|---|---|---|
| Avoids JLCPCB 4-wire Kelvin test | yes | no |
| Avoids small-via extra cost | yes | no |
| Blind/buried vias allowed | no | yes |
| Enforces plated-slot length/width ratio | yes | no |
| Ships a BGA fan-out rule | yes | no |
| Ships implied catch-all clearances | yes | no |
| Uses one trace limit for all copper layers | yes | no |
| Documents disabled same-net spacing workaround | yes | no |

