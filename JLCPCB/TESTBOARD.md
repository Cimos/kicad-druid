# JLCPCB test board

`JLCPCB.kicad_pcb` pairs with `JLCPCB.kicad_dru`. Objects that should fail are in the left
column, objects that should pass are in the right; the two `FAIL` / `PASS` markers on F.Fab
at (121, 20) and (143, 20) label the columns, and a stack of F.Fab labels down the left edge
at x=61 names each section. Footprints carry no references (they all read `REF**`), so the
table below identifies each object by position in mm and by what it is.

Running KiCad 9.0 DRC over the board with these rules gives **36 violations and 1 unconnected
item**. The unconnected item is the micro via / blind via pair in the Via Support section and
is expected.

## Rule coverage

| Rule (`JLCPCB.kicad_dru`) | Object(s) on the board | Meant to |
|---|---|---|
| Drill Hole Size | none of its own — see PTH/NPTH Hole Size | never fires (see Gaps) |
| Via Hole Size | vias at (118, 126.5) and (142, 126.5), both 0.2mm drill | pass |
| Via Annular Ring | vias at (121, 129) 0.5/0.36mm and (141, 129) 0.5/0.35mm | both pass (pair built for a 0.075mm limit; at 0.05mm neither fails) |
| Via diameter < 0.45mm with hole < 0.3mm | via (118, 126.5) 0.4mm/0.2mm; via (142, 126.5) 0.45mm/0.2mm | fail / pass (DRC reports it against the matching board-setup minimum) |
| PTH Hole Size | pad (119, 99) drill 6.31mm; pad (146, 99) drill 6.30mm; pads (124, 99) drill 0.19mm and (141, 99) drill 0.20mm | fail / pass on the max; both pass on the min |
| NPTH Hole Size | pad (119, 110) drill 0.49mm; pad (146, 110) drill 0.50mm | fail / pass |
| Castellated Hole Size | castellated pads on the cutout edge at (128, 119) drill 0.59mm and (135, 119) drill 0.60mm | both pass (pair built for a 0.6mm limit; at 0.5mm neither fails) |
| PTH Annular Ring | pad (117, 129) 1.0mm/0.86mm ring 0.07mm; pad (145, 129) 1.0mm/0.85mm ring 0.075mm | fail / intended pass, but 0.075mm is under the current 0.15mm limit so it fails too. Also fires on the M2 mounting pads used by the clearance sections |
| NPTH Annular Ring | NPTH pads at (119, 110), (146, 110), (123, 159.8), (143, 159.9) | rule never fires on them (see Gaps) |
| Avoid 4-Wire Kelvin Test | via (118, 126.5) and pads (119, 126.5), (120, 126.5), all 0.4mm/0.2mm; via (142, 126.5) and pads (143, 126.5), (144, 126.5), all 0.45mm/0.2mm | fail / pass. The 0.45mm pads clear this rule but trip PTH Annular Ring |
| SMD Pad Size | none | see Gaps |
| Only Throughhole VIAs are supported | micro via (120.8, 198.6); blind/buried via (123, 198.6); through via (142.8, 198.6) | fail, fail / pass |
| Plated Slot Width | none | see Gaps |
| Plated Slot Length-to-width Ratio | none | see Gaps |
| Non-Plated Slot Width | none | see Gaps |
| Via Hole to Via Hole Clearance (Different Nets) | vias (129, 189) +5V and (129.9, 189) GND, hole gap 0.5mm | pass |
| Pad Hole to Pad Hole Clearance | PTH pads (120.9, 189) / (123, 189) and (143, 189) / (145.15, 189), hole gaps 1.1mm and 1.15mm | pass |
| Via/Pad to Via/Pad Clearance (Different Nets) | fail: SMD pad (120.9, 186.87) to PTH pad (120.9, 189) at 0.126mm; PTH pads (120.9, 189) / (123, 189) at 0.1mm; PTH pad (123, 189) to via (124.5, 189) at 0.1mm; vias (129, 189) / (129.9, 189) at 0.1mm. pass: PTH pads (143, 189) / (145.15, 189) at 0.15mm; SMD pad (145.15, 186.87) to PTH pad (145.15, 189) at 0.127mm; vias (136.05, 189) / (137, 189) at 0.15mm | fail / pass |
| Via/Pad Hole to Via/Pad Hole Clearance (Same Net) | pad (123, 149) with via (122.15, 149), hole gap 0.225mm; pad (143, 149) with via (142.1, 149), hole gap 0.275mm | fail / pass |
| Via Hole to Pad Hole Clearance (Different Nets, inferred) | pad (123, 139) GND with via (121.88, 139) +5V, hole gap 0.495mm; pad (143, 139) with via (141.8, 139), hole gap 0.575mm | both pass |
| Pad to Pad Clearance (Pad without Hole, Different Nets) | none | see Gaps |
| Via to Trace | none | see Gaps |
| PTH to Trace | pad (123, 169.8) against the GND track on y=169, hole clearance 0.275mm; pad (143, 169.9), 0.375mm | fail / pass |
| PTH to Trace (inner layer) | none | see Gaps |
| NPTH to Trace | NPTH pads (123, 159.8) and (143, 159.9) against the GND track on y=159, hole clearance 0.2mm and 0.3mm | both pass (the left one fails Pad to Trace instead) |
| NPTH to Copper (non-Track) | none | see Gaps |
| Pad to Trace | pad (123, 179.25) against the GND track on y=178 at 0.15mm; pad (143, 179.3) at 0.2mm. Also fires on NPTH pad (123, 159.8) at 0.1mm | fail / pass |
| BGA to Trace | none | see Gaps |
| Trace Width | F.Cu tracks on y=26: x=115–132 at 0.08mm, x=132–150 at 0.09mm. In1.Cu tracks on y=41: same pair | fail / pass on both layers (DRC reports it against the matching board-setup minimum) |
| Trace Spacing | F.Cu +5V/GND at (132, 33) and (130.7, 35), gap 0.08mm, against the 0.09mm pair to the right. In1.Cu at (132, 49) and (131, 51), same arrangement | fail / pass on both layers |
| 50R Single-Ended | none | see Gaps |
| 60R_Diff Differential Pair | none | see Gaps |
| 90R_Diff Differential Pair | none | see Gaps |
| 100R_Diff Differential Pair | none | see Gaps |
| 120R_Diff Differential Pair | none | see Gaps |
| Minimum Line Width | text 'Too thin' (115, 61) and text box 'Too thin' (115, 67), both 0.14mm; text (141, 61) and text box (140, 63) 'Just big and thick enough' | fail / pass |
| Minimum Text Height | text 'Too small' (115, 58) and text box 'Too small' (115, 63), both 0.9mm high; the same two 'Just big and thick enough' items | fail / pass |
| Pad to Silkscreen | R_0805 at (121, 79), silk to pad 0.145mm; R_0805 at (143, 79) | fail / pass |
| Trace to Board Edge | tracks on y=89 either side of the cutout at x=128–135, y=87–91: left ends at x=127.61 (0.29mm), right ends at x=135.4 (0.30mm) | both pass |

The 1k THT resistor R1 at (129, 17) is the only footprint with a real reference. It feeds the
+5V and GND rails that the clearance sections hang off; it is not a test object.

## Gaps

Rules with nothing on the board placed to exercise them.

| Rule | Why it is a gap | To close it |
|---|---|---|
| Drill Hole Size | KiCad applies the last matching rule, and PTH Hole Size / NPTH Hole Size both come later and match the same pads, so this rule never decides anything | needs a hole that is neither a plated through-hole pad nor an NPTH pad |
| NPTH Annular Ring | NPTH pads are on the board with rings of 0.1mm and 0.255mm, well under the 0.45mm minimum, and KiCad 9 raises no violation for any of them | check whether KiCad applies `annular_width` to NPTH pads at all before adding an object |
| SMD Pad Size | the smallest SMD pad on the board is 1.025mm x 1.4mm; nothing is near the 0.125mm limit | add an SMD pad under 0.125mm in one dimension and one just over |
| Plated Slot Width | every pad hole on the board is round | add a plated pad with an oval hole under and over 0.35mm wide |
| Plated Slot Length-to-width Ratio | same — no oval holes | add an oval hole shorter than twice its width, and one longer |
| Non-Plated Slot Width | same — no oval holes | add an NPTH oval hole under and over 1.0mm wide |
| Pad to Pad Clearance (Pad without Hole, Different Nets) | the only SMD pads with nets are both GND; the R_0805 pads have no net | add two SMD pads on different nets under and over 0.15mm apart |
| Via to Trace | no via is placed near a track of another net; the incidental spacings are all well clear of 0.2mm | add a via with hole-to-track clearance under and over 0.2mm |
| PTH to Trace (inner layer) | the inner-layer tracks are in the trace width and spacing sections, with no PTH pad near them | add an inner-layer track past a PTH pad at under and over 0.3mm |
| NPTH to Copper (non-Track) | no NPTH pad sits near a pad, via or zone | add an NPTH pad near non-track copper, under and over 0.2mm |
| BGA to Trace | the board only uses the Default net class | add a `BGA` net class with a fan-out net |
| 50R Single-Ended | Default net class only | assign a net to `50R` |
| 60R_Diff Differential Pair | Default net class only | assign a pair to `60R_Diff` |
| 90R_Diff Differential Pair | Default net class only | assign a pair to `90R_Diff` |
| 100R_Diff Differential Pair | Default net class only | assign a pair to `100R_Diff` |
| 120R_Diff Differential Pair | Default net class only | assign a pair to `120R_Diff` |

The five impedance rules use `(opt ...)`, so they guide the router and never raise a violation.
An object for them proves the net class resolves, not that DRC reports anything.

Three more rules have a passing object but no failing one, because the rule value moved after
the board was drawn: Via Annular Ring (pair built for 0.075mm, now 0.05mm), Castellated Hole
Size (pair built for 0.6mm, now 0.5mm) and PTH Hole Size on its minimum (0.19mm and 0.20mm
against a 0.15mm limit). PTH Annular Ring has the opposite problem — its intended pass object
at 0.075mm now fails the 0.15mm limit.

## Editing the board

KiCad 9 or later is needed to open the board; the file is format version 20241229 and KiCad 8
cannot read it. The rules themselves still work on KiCad 8, 9 and 10.

Keep the pass and fail objects when you edit. Adding a rule means adding an object that fails
it and, where it makes sense, one that passes, in the matching column with an F.Fab label.

To see what fires:

```
kicad-cli pcb drc --format json --output drc.json --severity-error --severity-warning JLCPCB/JLCPCB.kicad_pcb
```

The report names the rule and lists the items that tripped it with their positions, which is
how the table above was built. Compare the violation count and the rule names before and after
your change.
