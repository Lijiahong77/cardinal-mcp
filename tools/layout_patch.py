# -*- coding: utf-8 -*-
"""
layout_patch.py — the single source of truth for laying out modules in a
Cardinal patch (the "排班" / stage-blocking tool).

The layout rules are also mirrored in ~/.workbuddy/MEMORY.md ("Cardinal 机架排班铁律").
--------------------------------------------------------------------
1. `pos[0]` (x) is in "cells" (格), NOT pixels. 1 cell ≈ 1 HP ≈ 15 internal px.
   `pos[1]` (y) is a "row number" (0 / 1 / 2 …), NOT cells
   (corrected 2026-09-12 15:45).
2. Rows have meaning, top-to-bottom by signal flow:
      row 0  synth chain        | row 1  control map + drums
      row 2  mix output + label | row 3+ new / unregistered zone
3. Within a row, x starts at 0 and increases monotonically; column gap = module
   width + GAP cells.
4. When unsure of a module's width, overestimate (underestimating overlaps the
   right-hand neighbour).
5. ⚠️ Before editing a .vcv, make sure Cardinal is CLOSED — pressing Ctrl+S in
   Cardinal writes its in-memory state back to the file and overwrites your edits
   (observed 2026-09-12: a tidy layout was wiped by a later save).

The bug we hit (2026-09-12): writing a new module's pos as x=300~720 (treating
cells as pixels) placed it ~4500px off-screen — the GUI showed "wires but no
modules".

Severity tiers (to avoid false alarms — a false alarm is worse than no check)
--------------------------------------------------------------------
  HARD error (exit code 1): input port double-connected, obvious overlap (>2 cells),
                            coordinate outside the default view (|coord|>200 cells)
  SOFT warning (non-blocking): y not on an integer row grid, slight overlap,
                               slightly negative x, unregistered module
  `--strict` upgrades SOFT warnings to HARD errors

Subcommands
--------------------------------------------------------------------
  check  <patch>                      just print coordinates (diagnose, no edit)
  guard  <patch> [--strict]           GATE: layout + wiring double check; exit 1 on hard error
  widths [--fix]                      re-measure panel widths, verify WIDTH_BY_MODEL
  apply  <patch> [--push] [--strict] [--no-etext]
                                      re-layout and write back (auto-backup);
                                      unregistered modules auto-place
       --push      also push into Cardinal and verify the live autosave
       --strict    refuse to write if any module had to be auto-placed
       --no-etext  do not update the TextEditor label panel
"""

import json
import os
import re
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import patchio  # noqa: E402


# ================================================================ Layout constants
# [2026-09-12 15:45 correction: y's unit is "row number", NOT "cells".]
#   Evidence: all 20 official templates/examples on this machine — even a 39-module
#   multi-row rack — have y only in the range -1 ~ 2; after Cardinal saved
#   helm_full.vcv, its y is exactly 0/1/2.
#   => write y as 0 / 1 / 2 / 3… ; writing y=34/68 (treating it as cells) was WRONG.
#   ⚠️ Open question: earlier y=0/34/68 still rendered as normal 3 rows for the user
#      -> hypothesis: Cardinal does a "cells -> rows" snap on load (reads cells, writes
#      row numbers; read/write asymmetric). To be confirmed by experiment.
#
# [Screen capacity, 3200x2000 @ 200% DPI]
#   at zoom=1, 1 cell = 20 physical px; usable window ≈ 160 cells wide × 88 cells tall
#   (minus the toolbar). One row is ≈ 25.3 cells tall -> 3 rows ≈ 98 cells = 1960 px
#   fills the screen, pushing drums to the lower-middle ("all at the bottom").
#   => iron rule: keep it to 2 rows vertically. Spread out horizontally instead.
GAP = 2            # column gap (cells). 20 modules must fit in 2 rows, so keep it tight
ROW_H = 34         # [estimating screen occupancy ONLY] 1 row ≈ 34 cells;
                   #  **layout output uses the row number — do NOT multiply by this**
GRID_PER_ROW = 34  # row -> cells conversion factor (screen-height estimate only)
MAX_ROWS_FOR_SCREEN = 2   # max rows that fit comfortably on screen (more => zoom out)

# Gate thresholds
OVERLAP_TOL = 2    # cells. overlap ≤ this is treated as width-estimate error -> soft only
VIEW_LIMIT = 200   # cells. |x| or |y| beyond this = module off the default view
                   #  (200 cells ≈ 3000px)
NEG_X_TOL = 8      # cells. slightly negative x (e.g. TextEditor at -3) is acceptable

ROW_NAMES = {0: "synth chain + control + output", 1: "label + drums + mixer"}


def row_y(row):
    """Row number -> y coordinate (the unit IS the row number itself).

    ⚠️ 2026-09-12 15:45 correction: `pos[1]` in a .vcv is a ROW NUMBER, not cells.
    Evidence: all 20 official templates/examples have y only in -1 ~ 2, and after
    Cardinal saved helm_full.vcv its y is exactly 0/1/2.
    => just return `row`; DO NOT multiply by ROW_H (multiplying would drop the module
       into row 34's wilderness — more insidious than pixels, because the file "has a
       value" yet the GUI shows nothing).
    """
    return row


def row_name(row):
    return ROW_NAMES.get(row, "new zone")


# ================================================================ Width table
# [Measured, not guessed.] Source: the panel SVGs shipped inside Cardinal's install
# directory. Rack sizes a module from its panel SVG's physical dimensions:
# 1 HP = 5.08 mm, and 1 cell = 1 HP = 15 px.
# Re-measure with: `python layout_patch.py widths`
#
# The key MUST be "plugin/module" — different plugins reuse names (another plugin
# also has VCO.svg at 27 HP), so looking up by file name alone cross-contaminates.
#
# Measured corrections to earlier guesses (kept on record to avoid repeating):
#   HostMIDIGate  10 -> 14     HostMIDI        10 -> 9      MixMasterJr  60 -> 36
#   Plateau       16 -> 12     OpenHiHat        7 -> 9      Fundamental/Mixer 6 -> 3
#   drum modules  7 -> 6
RESOURCES = r"C:\Program Files\Cardinal-win64-26.02\Cardinal.lv2\resources"
HP_MM = 5.08        # millimetres per HP
PX_PER_HP = 15.0    # 1 HP = 1 cell = 15 px

# A patch's plugin slug ≠ its install directory name; this maps slug -> dir.
PLUGIN_DIR = {
    "Valley": "ValleyAudio",
    "rcm": "rcm-modules",
    "AriaSalvatrice": "AriaModules",
    "Bogaudio": "BogaudioModules",
    "Wasted_Audio": "WSTD-Drums",
}

# plugin/module -> width in HP (cells). Measured from panel SVGs.
WIDTH_BY_PLUGIN_MODEL = {
    # ---- Cardinal's own ----
    "Cardinal/HostMIDI": 9,
    "Cardinal/HostMIDIMap": 11,
    "Cardinal/HostMIDIGate": 14,
    "Cardinal/HostMIDICC": 14,
    "Cardinal/HostParameters": 9,
    "Cardinal/HostParametersMap": 11,
    "Cardinal/HostAudio": 8,
    "Cardinal/HostAudio2": 8,          # shares panel with HostAudio
    "Cardinal/HostTime": 8,
    "Cardinal/HostCV": 8,
    "Cardinal/ExpanderMIDI": 3,
    "Cardinal/Blank": 9,
    "Cardinal/Carla": 9,
    # ---- rcm-modules (piano roll) — measured 2026-09-21: panel px 600 / 15 ----
    "rcm/rcm-pianoroll": 40,
    # ---- ImpromptuModular — measured 2026-09-21: 101.6mm / 5.08 ----
    "ImpromptuModular/Clocked": 20,
    # ---- LittleUtils — measured 2026-09-21: ButtonModule.svg width 45px / 15 ----
    "LittleUtils/Button": 3,
    # ---- Starsea (own package) — 2026-09-21: MiniArranger.svg width 152.4mm / 5.08 ----
    "Starsea/MiniArranger": 40,
    "Starsea/MiniArrangerExpander": 24,
    # ---- Fundamental ----
    "Fundamental/VCO": 9,
    "Fundamental/SEQ3": 22,   # 330px / 15 (measured from SEQ3.svg)
    "Fundamental/WTVCO": 7,
    "Fundamental/VCF": 7,
    "Fundamental/ADSR": 9,
    "Fundamental/VCA-1": 3,
    "Fundamental/VCA": 5,
    "Fundamental/VCMixer": 9,
    "Fundamental/Sum": 3,
    "Fundamental/Mixer": 3,
    "Fundamental/Noise": 3,
    "Fundamental/LFO": 9,
    "Fundamental/WTLFO": 7,
    "Fundamental/8vert": 8,
    "Fundamental/Scope": 13,
    # ---- Valley ----
    "ValleyAudio/Plateau": 12,
    # ---- MindMeldModular ----
    "MindMeldModular/MixMasterJr": 36,
    "MindMeldModular/MixMaster": 61,
    # ---- WSTD-Drums ----
    "WSTD-Drums/BassDrum9": 6,
    "WSTD-Drums/SnareDrumN": 6,
    "WSTD-Drums/ClosedHiHat": 6,
    "WSTD-Drums/OpenHiHat": 9,
    "WSTD-Drums/Tomi": 6,
    "WSTD-Drums/DMX": 6,
    "WSTD-Drums/CR78": 6,
    "WSTD-Drums/Baronial": 6,
    "WSTD-Drums/SyntheticBassDrum": 9,
    "WSTD-Drums/Gnome": 9,
    "WSTD-Drums/MarionetteBass": 15,
    "WSTD-Drums/Sequencer": 32,
    # ---- measured 2026-10-17 from Cardinal 26.02 panels (Quadeca patches) ----
    # plugin slug is the manifest slug, NOT the install dir name
    # (dir BogaudioModules -> slug Bogaudio; dir surgext -> slug SurgeXTRack).
    "AudibleInstruments/Rings": 14,        # 71.12mm / 5.08
    "AudibleInstruments/Elements": 34,
    "AudibleInstruments/Clouds": 18,
    "AudibleInstruments/Plaits": 12,      # plaits.svg measured 2026-10-17
    "voxglitch/SamplerX8": 28,             # samplerx8_panel.svg 142.24mm
    "voxglitch/GrainEngineMK2": 20,        # grain_engine_mk2_panel.svg 101.6mm
    "voxglitch/Autobreak": 8,
    # 🔴 KEY = norm_plugin(slug) + "/" + model, and norm_plugin maps a patch's
    # plugin slug to its INSTALL DIRECTORY name. So the Bogaudio family (slug
    # `Bogaudio`, dir `BogaudioModules`) must be keyed "BogaudioModules/...".
    # Keying it "Bogaudio/..." silently falls through to DEFAULT_WIDTH=10 —
    # that is exactly how Bogaudio-ADSR (really 3 HP) ended up overlapping its
    # right-hand neighbour on 2026-10-17.
    "BogaudioModules/Bogaudio-VCO": 10,    # vco.svg 2026-10-17
    "BogaudioModules/Bogaudio-VCF": 10,    # vcf.svg 2026-10-17
    "BogaudioModules/Bogaudio-ADSR": 3,    # adsr.svg 2026-10-17 (only 3 HP!)
    "BogaudioModules/Bogaudio-LVCO": 3,
    "BogaudioModules/Bogaudio-LVCF": 3,
    "BogaudioModules/Bogaudio-SampleHold": 3,
    "BogaudioModules/Bogaudio-Unison": 3,  # Unison.svg 45px
    "BogaudioModules/Bogaudio-FMOp": 10,   # FMOp.svg
    "BogaudioModules/Bogaudio-Shaper": 10,
    "BogaudioModules/Bogaudio-ShaperPlus": 15,
    "BogaudioModules/Bogaudio-DADSRH": 10,
    "BogaudioModules/Bogaudio-DADSRHPlus": 15,
    "BogaudioModules/Bogaudio-Matrix44": 10,
    "BogaudioModules/Bogaudio-Matrix81": 6,
    "Fundamental/Split": 5,                # split.svg 2026-10-17
    # ---- code-drawn panels (no SVG) -> width inferred from coordinates in
    #      patches that actually load. Feline has no SVG and no same-row neighbour
    #      in any local patch, so it takes the Valley family value (Plateau=12).
    #      Rule (see header #4): when unsure, OVERESTIMATE.
    "HetrickCV/Waveshaper": 6,            # inferred: x=52 -> next x=58
    # ⚠️ 查表用的是 norm_plugin(slug) = 安装目录名，所以 Valley 家族的 key 必须写
    # `ValleyAudio/...`（不是 slug `Valley/...`），否则永远匹配不上、退化成 DEFAULT_WIDTH=10。
    "ValleyAudio/Feline": 12,             # no SVG, no neighbour; Valley family value
    "ValleyAudio/Terrorform": 12,
    "ValleyAudio/Interzone": 32,
    "ValleyAudio/Sequential": 12,
    "MindMeldModular/ShapeMaster": 38,     # 193mm
    # SurgeXTRack panels are code-drawn (no SVG) -> width inferred from
    # Final Patch Work.vcv coordinates (Distortion x=171 -> next x=183).
    "SurgeXTRack/SurgeXTFXDistortion": 12,
    # 2026-10-18: Surge XT FX 全家同面板尺寸（Distortion=12 已实测登记）；
    # Reverb2 = 12HP 由李的 Final Patch Work.vcv 中 Chorus→Reverb2 无缝相邻 gap=12 印证。
    "SurgeXTRack/SurgeXTFXReverb2": 12,
}

# When a panel file name differs from the model name (used by `widths` check).
SVG_ALIAS = {
    ("WSTD-Drums", "BassDrum9"): "bd9",
    ("WSTD-Drums", "SnareDrumN"): "snare",
    ("WSTD-Drums", "ClosedHiHat"): "closedhh",
    ("WSTD-Drums", "OpenHiHat"): "openhh",
    ("WSTD-Drums", "SyntheticBassDrum"): "sbd",
    ("WSTD-Drums", "MarionetteBass"): "marionette",
    ("Cardinal", "HostAudio2"): "hostaudio",
    ("Cardinal", "HostParametersMap"): "hostparamsmap",
    ("ValleyAudio", "Plateau"): "plateaupaneldark",
    ("MindMeldModular", "MixMasterJr"): "mixmaster-jr",
}

DRUM_WIDTH = 6      # fallback for unlisted WSTD drums (most are 6 HP)
DEFAULT_WIDTH = 10  # fallback when completely unknown (better too wide than too narrow)


def norm_plugin(p):
    """Map a patch's plugin slug to its install directory name."""
    return PLUGIN_DIR.get(p, p)


# Every WSTD-Drums model (used to recognise "this is a drum").
DRUM_MODELS = {
    "BassDrum9", "SyntheticBassDrum", "MarionetteBass", "SnareDrumN",
    "ClosedHiHat", "OpenHiHat", "Tomi", "Toms", "CR78", "DMX",
    "Baronial", "Gnome", "Sequencer",
}

# ================================================================ Registration table
# Registered modules: id -> (row, width). Registered ones are placed in listed order.
# Unregistered modules are not lost — `apply` auto-classifies them into a row and
# reports them.
#
# [2-row layout, recomputed 2026-09-12 from real screen measurements]
#   The old 3 rows (0/1/2) totalled 98 cells = 1960 px, filling the 2000px screen and
#   dropping drums to the lower-middle ("drums all at the bottom"). Flattened to 2 rows
#   = 64 cells = 1280 px, leaving headroom.
#   row 0 = synth + control map + output (x up to ~110 cells)
#   row 1 = label + drums + mixer     (x up to ~122 cells)
LAYOUT = [
    # ---------------- row 0: helm synth chain ----------------
    ("2",                  0, 9),    # HostMIDI      9 HP — keys on ch1 only
    ("3",                  0, 9),    # VCO           9
    ("4",                  0, 7),    # VCF           7
    ("5",                  0, 9),    # ADSR          9
    ("6",                  0, 3),    # VCA-1         3
    ("7",                  0, 3),    # Sum           3
    ("8",                  0, 12),   # Plateau      12
    ("799138358763949",    0, 11),   # HostMIDIMap  11 — CC20-27 -> 8 params
    ("100",                0, 14),   # HostMIDIGate 14 — pad Note -> gate
    ("9",                  0, 8),    # HostAudio2    8 — main output
    # ---------------- row 1: label + drums + mixer ----------------
    ("1",                  1, 26),   # TextEditor   26 (rack map)
    ("101",                1, 6),    # BassDrum9     6
    ("102",                1, 6),    # SnareDrumN    6
    ("103",                1, 6),    # ClosedHiHat   6
    ("104",                1, 9),    # OpenHiHat     9 (wider than other drums)
    ("105",                1, 6),    # Tomi          6
    ("106",                1, 6),    # DMX           6
    ("107",                1, 3),    # Mixer         3 (drum bus A)
    ("108",                1, 3),    # Mixer         3 (drum bus B)
    ("3130453735965577",   1, 36),   # MixMasterJr  36 (8-track mixer, measured 36 HP)
]

# ================================================================
# LAYOUT per patch (2026-10-17)
# =================================================================
# 🔴 THE iron rule, restated because it was violated twice:
#   `pos[1]` (y) is a ROW NUMBER, not cells. Keep the rack to<= 2 rows
#   (screen is ~88 cells tall; 3 rows already fill it and force dragging).
#   Modules in a row MUST sit shoulder-to-shoulder: x += width + GAP(2).
#   Never hand-write pos by "looks about right" — add the row here and run
#   `apply`. `guard` fails the build if the file drifts from this table.
#
# ---------------- quadeca_life1_wdtg ----------------
#   TWO rows. Row 0 alone was 309 cells ≈ 4635 px — nearly 2 screens wide, so it
#   still forced horizontal dragging. Split by voice so each row fits the view:
#     row 0 = 时钟 + 大提琴声部 + 混音/混响/输出  (≈ 158 cells ≈ 2370 px)
#     row 1 = 电钢声部 + 吉他声部                    (≈ 152 cells ≈ 2280 px)
#   Within a row, x always increases: `do_layout` computes x += width + GAP(2),
#   so the list order below IS the left-to-right order. Never hand-write pos.
WDTG_LAYOUT = [
    # ---------------- row 0: clock + cello + master ----------------
    ("9000000000000002",   0, 20),   # Clocked     20HP — RUN key lives here
    ("9000000000000010",   0, 40),   # pianoroll  40HP — cello note layer
    ("9000000000000013",   0, 34),   # Elements   34HP — bowed-string physical model
    ("9000000000000003",   0, 36),   # MixMasterJr 36HP — 8-track mixer
    ("9000000000000004",   0, 12),   # Feline      12HP — send reverb
    ("9000000000000005",   0, 8),    # HostAudio2   8HP — main output
    # ---------------- row 1: electric piano + flamenco guitar ----------------
    ("9000000000000019",   1, 40),   # pianoroll  40HP — EP note layer
    ("9000000000000022",   1, 10),   # Bogaudio-VCO 10HP
    ("9000000000000024",   1, 10),   # Bogaudio-VCF 10HP
    ("9000000000000027",   1, 3),    # Bogaudio-ADSR 3HP
    ("9000000000000030",   1, 5),    # Split       5HP — mono -> L/R
    ("9000000000000035",   1, 40),   # pianoroll  40HP — guitar note layer
    ("9000000000000038",   1, 12),   # Plaits      12HP — PLUCK
    ("9000000000000041",   1, 6),    # Waveshaper  6HP — light grit
    ("9000000000000043",   1, 5),    # Split       5HP
]

    # ---------------- yorushika (shura / hana) ----------------
#   TWO rows, zoom 0.7 (209 cells visible at 1.0 -> ~298 at 0.7).
#     row 0 = transport/control/arranger      (~200 cells)
#     row 1 = voice chains + drums + master   (~273 cells)
#   🔴 MiniArranger MUST be immediately left of the Expander (Rack rightExpander
#      only recognises physical adjacency; wrong placement = LINK dark + no rec).
#   2026-10-18 鼓组重选型：BassDrum9(909 电子底鼓)/DMX(Oberheim 电子鼓机) →
#   CR78(Roland CompuRhythm 1978 模拟电路鼓, 温暖圆润更贴修羅的原声鼓组);
#   混响 Plateau → SurgeXTFXReverb2（李自己 Final Patch Work 在用的 Surge XT 系）。
YORUSHIKA_LAYOUT = [
    # ---------------- row 0: clock + MIDI in + arranger ----------------
    ("7200000000000001",   0, 20),   # Clocked     20HP — RUN key on panel
    ("7200000000000002",   0, 9),    # HostMIDI     9HP — keys, OMNI, 8-voice
    ("7200000000000003",   0, 11),   # HostMIDIMap 11HP — CC20-27 + CC1
    ("7200000000000004",   0, 14),   # HostMIDIGate 14HP — pads 48-55 + transport 93-95
    ("7200000000000005",   0, 40),   # MiniArranger 40HP — 4-track chord recorder
    ("7200000000000006",   0, 24),   # Expander    24HP — MUST sit right of MiniArranger
    ("7200000000000007",   0, 32),   # Sequencer   32HP — style drum pattern
    ("7200000000000008",   0, 26),   # TextEditor  26HP — instructions
    ("7200000000000041",   0, 8),    # HostAudio2   8HP — main output (kept on row0 so
                                     #   row1 stays under the 3000px view limit)
    # ---------------- row 1: voice chains + drums + master ----------------
    ("7200000000000009",   1, 9),    # EP VCO       9HP — live key voice (saw)
    ("7200000000000010",   1, 10),   # EP VCF      10HP — Bogaudio width (NOT 7=Fundamental)
    ("7200000000000011",   1, 3),    # EP ADSR      3HP
    ("7200000000000012",   1, 3),    # EP VCA-1     3HP
    ("7200000000000013",   1, 3),    # EP Sum       3HP — poly -> mono (0.5)
    ("7200000000000014",   1, 9),    # bass VCO     9HP — track1
    ("7200000000000015",   1, 3),    # bass ADSR    3HP
    ("7200000000000016",   1, 3),    # bass VCA-1   3HP
    ("7200000000000017",   1, 3),    # bass Sum     3HP
    ("7200000000000018",   1, 9),    # pad VCO      9HP — track2
    ("7200000000000019",   1, 10),   # pad VCF     10HP — Bogaudio width
    ("7200000000000020",   1, 3),    # pad ADSR     3HP
    ("7200000000000021",   1, 3),    # pad VCA-1    3HP
    ("7200000000000022",   1, 3),    # pad Sum      3HP
    ("7200000000000023",   1, 12),   # Plaits      12HP — arp track3 (PLUCK)
    ("7200000000000024",   1, 3),    # arp ADSR     3HP
    ("7200000000000025",   1, 3),    # arp VCA-1    3HP
    ("7200000000000026",   1, 3),    # arp Sum      3HP
    ("7200000000000027",   1, 9),    # lead VCO     9HP — track4
    ("7200000000000028",   1, 3),    # lead ADSR    3HP
    ("7200000000000029",   1, 3),    # lead VCA-1   3HP
    ("7200000000000030",   1, 3),    # lead Sum     3HP
    ("7200000000000031",   1, 6),    # CR78         6HP — kick(auto trk1) + latin perc(pad)
    ("7200000000000032",   1, 6),    # SnareDrumN   6HP — snare (sequencer)
    ("7200000000000033",   1, 6),    # ClosedHiHat  6HP — closed hat (sequencer)
    ("7200000000000034",   1, 9),    # OpenHiHat    9HP — pad 3
    ("7200000000000035",   1, 6),    # Tomi         6HP — pad 2
    ("7200000000000036",   1, 3),    # Mixer        3HP — drum bus
    ("7200000000000037",   1, 3),    # drum Sum     3HP
    ("7200000000000038",   1, 3),    # send Mixer   3HP — reverb sends (EP+pad+arp)
    ("7200000000000039",   1, 12),   # SurgeXTReverb2 12HP — send reverb
    ("7200000000000040",   1, 36),   # MixMasterJr 36HP — 8-track master
]

# ---------------- Charli XCX / A.G. Cook trio (2026-10-18) ----------------
#   Shared by all three patches (identical module ids by design, only BPM /
#   harmony / timbre differ). TWO rows, total 323 cells:
#     row 0 = transport + arranger + drums + master ................ 149
#     row 1 = voices + hand-play control .......................... 174
#   🔴 MiniArranger (40) and Expander (24) MUST stay adjacent, gap exactly 2:
#      Rack's rightExpander only recognises physical adjacency, and the
#      generator asserts gap == 42 (40 + GAP).
BRAT_LAYOUT = [
    # ---------------- row 0: transport / arranger / drums / master ----------------
    ("8400000000000001",   0, 20),   # Clocked       20HP — RUN key here
    ("8400000000000002",   0, 40),   # MiniArranger  40HP — 4 tracks
    ("8400000000000003",   0, 24),   # Expander      24HP — MUST be adjacent
    ("8400000000000004",   0, 6),    # BassDrum9
    ("8400000000000005",   0, 6),    # SnareDrumN
    ("8400000000000006",   0, 6),    # ClosedHiHat
    ("8400000000000023",   0, 36),   # MixMasterJr   36HP
    ("8400000000000024",   0, 12),   # Plateau       12HP
    ("8400000000000025",   0, 8),    # HostAudio2     8HP
    ("8400000000000029",   0, 26),   # TextEditor    26HP
    # ---------------- row 1: voices + hand-play ----------------
    ("8400000000000007",   1, 10),   # bass VCO
    ("8400000000000008",   1, 10),   # bass VCF
    ("8400000000000009",   1, 3),    # bass ADSR
    ("8400000000000010",   1, 3),    # bass VCA
    ("8400000000000011",   1, 10),   # chord VCO 1
    ("8400000000000012",   1, 10),   # chord VCO 2
    ("8400000000000013",   1, 10),   # chord VCO 3
    ("8400000000000014",   1, 3),    # chord Mix
    ("8400000000000015",   1, 10),   # chord VCF
    ("8400000000000016",   1, 3),    # chord ADSR
    ("8400000000000017",   1, 3),    # chord VCA
    ("8400000000000018",   1, 10),   # lead VCO
    ("8400000000000019",   1, 10),   # lead VCF
    ("8400000000000020",   1, 3),    # lead ADSR
    ("8400000000000021",   1, 3),    # lead VCA
    ("8400000000000022",   1, 3),    # manual drum bus
    ("8400000000000026",   1, 9),    # HostMIDI
    ("8400000000000027",   1, 14),   # HostMIDIGate
    ("8400000000000028",   1, 11),   # HostMIDIMap
]

# Which layout table applies to which patch (basename match).
LAYOUT_FOR_PATCH = {
    "quadeca_life1_wdtg.vcv": WDTG_LAYOUT,
    "yorushika_shura.vcv": YORUSHIKA_LAYOUT,
    "yorushika_hana.vcv": YORUSHIKA_LAYOUT,
    "charli_360.vcv": BRAT_LAYOUT,
    "charli_party4u.vcv": BRAT_LAYOUT,
    "charli_wytam.vcv": BRAT_LAYOUT,
}

# The label-panel text (written into TextEditor's data.etext). Width 26 cells ≈ 65
# chars — keep it under that.
ETEXT = """HELM FULL - keyboard fully wired
================================

[ROW 1] SYNTH + CONTROL
HostMIDI(ch1 keys) -> VCO -> VCF
  -> VCA -> Sum -> Plateau
  -> HostAudio2 (main out)
HostMIDIMap  CC20-27 -> 8 params
HostMIDIGate pad Note48-55 -> gates
ADSR opens VCA + sweeps filter

[ROW 2] DRUMS + MIX
6 drums -> MixerA/B -> MixMaster
  trk2 / trk3
MixMasterJr trk1 = synth
MixMasterJr -> HostAudio2

KNOBS  1 bright  2 reso  3 wet
       4 decay  5 attack  6 release
       7 pulse  8 drive
PADS   1 BD-A  2 BD-B  3 SD-A  4 SD-B
       5 CH  6 OH  7 tom  8 DMX

! Do NOT press KNOB-B before
  turning knobs. It switches to
  pitch-bend, which Cardinal
  cannot map.
"""


# ================================================================ Basic helpers

def sid(x):
    """Normalise a module id to str (ids may be int or str in a patch)."""
    return str(x)


def estimate_width(m):
    """Look up a module's width (cells) from the measured table.

    TextEditor reads its own data.width (so its label box can be wider than a
    default module).
    """
    model = m.get("model", "")
    plugin = norm_plugin(m.get("plugin", ""))
    if model == "TextEditor":
        try:
            return float((m.get("data") or {}).get("width") or 26)
        except (TypeError, ValueError):
            return 26
    w = WIDTH_BY_PLUGIN_MODEL.get(plugin + "/" + model)
    if w is not None:
        return w
    if plugin == "WSTD-Drums" or model in DRUM_MODELS:
        return DRUM_WIDTH
    return DEFAULT_WIDTH


def classify_row(m):
    """Decide which row an unregistered module belongs to (by its role)."""
    model = m.get("model", "")
    if model in ("HostMIDIMap", "HostParametersMap", "HostMIDIGate"):
        return 1
    if m.get("plugin") == "WSTD-Drums" or model in DRUM_MODELS:
        return 1
    if model in ("TextEditor", "MixMasterJr", "MixMaster"):
        return 1
    if model in ("HostAudio", "HostAudio2"):
        return 1
    return 0


def on_grid(y):
    """Is y on an integer row number (0/1/2…)?

    ⚠️ 2026-09-12 correction: y's unit is "row", not "cells"; the old test (multiple
    of 34) was wrong.
    """
    return abs(y - round(y)) < 1e-3


def resolved_pos(m):
    """Return a module's (x, y) as floats, tolerating missing/bad pos fields."""
    p = m.get("pos") or [0, 0]
    try:
        return float(p[0]), float(p[1])
    except (TypeError, ValueError, IndexError):
        return 0.0, 0.0


# ================================================================ Layout core

def pick_layout(filename):
    """Choose the layout table for a patch by its basename."""
    base = os.path.basename(filename or "")
    if base in LAYOUT_FOR_PATCH:
        return LAYOUT_FOR_PATCH[base]
    # Also accept a versioned sibling, e.g. foo__v1955.vcv -> foo.vcv
    stem = base.split('__v')[0] + '.vcv'
    if stem in LAYOUT_FOR_PATCH:
        return LAYOUT_FOR_PATCH[stem]
    return LAYOUT


def do_layout(d, layout=None):
    """Compute the new coordinates.

    Returns (new_pos {id: [x, y]}, registered_id_set, unregistered_modules, log_lines).
    """
    layout = layout if layout is not None else LAYOUT
    mods = d.get("modules", [])
    by = {sid(m["id"]): m for m in mods}
    widths = {mid: estimate_width(m) for mid, m in by.items()}

    declared = {}          # id -> (row, width)
    missing = []
    for mid, row, w in layout:
        if mid not in by:
            missing.append(mid)
            continue
        declared[mid] = (row, w)

    # Unregistered modules: place by role, preserving their original relative order
    # (sorted by y, then x, then id) so the result is stable.
    unregistered = [m for m in mods if sid(m["id"]) not in declared]
    unregistered.sort(key=lambda m: (resolved_pos(m)[1], resolved_pos(m)[0],
                                     sid(m["id"])))

    rows = {}              # row -> [(id, width, is_registered)]
    for mid, (row, w) in declared.items():
        rows.setdefault(row, []).append((mid, w, True))
    for m in unregistered:
        mid = sid(m["id"])
        rows.setdefault(classify_row(m), []).append((mid, widths[mid], False))

    out = {}
    log = []
    if missing:
        log.append("  [warn] %d modules in LAYOUT not in patch: %s" % (len(missing), missing))

    for row in sorted(rows):
        x = 0.0
        auto_here = []
        for mid, w, is_declared in rows[row]:
            out[mid] = [x, row_y(row)]
            if not is_declared:
                auto_here.append(mid)
            x += w + GAP
        span = x - GAP if rows[row] else 0
        note = "  <- auto-placed: %s" % auto_here if auto_here else ""
        log.append("  row %d (%s): %d modules, span 0 ~ %.0f cells%s"
                   % (row, row_name(row), len(rows[row]), span, note))

    return out, set(declared), unregistered, log


# ================================================================ Overlap / view checks

def check_overlap(pos, widths, tol=0):
    """Same-row overlap check. tol = tolerance (cells). Returns (hard, soft)."""
    hard, soft = [], []
    rows = {}
    for mid, (x, y) in pos.items():
        rows.setdefault(y, []).append((x, widths.get(mid, DEFAULT_WIDTH), mid))
    for y in sorted(rows):
        items = sorted(rows[y])
        for i in range(1, len(items)):
            px, pw, pm = items[i - 1]
            cx, cw, cm = items[i]
            over = px + pw - cx
            if over > tol:
                hard.append("y=%.0f row %s(x=%.0f,w≈%.0f) overlaps %s(x=%.0f) by %.0f cells ≈ %.0f px"
                            % (y, pm, px, pw, cm, cx, over, over * 15))
            elif over > 0:
                soft.append("y=%.0f row %s and %s only %.0f cells apart (likely width estimate error)"
                            % (y, pm, cm, over))
    return hard, soft


def check_view(pos, zoom=1.0):
    """Check whether any module is off the default view. Returns (hard, soft).

    🔴 2026-10-18: the 200-cell limit is a *physical* 3000px budget (window is
    ~3129px wide on 李's machine). It was calibrated at zoom=1; a zoomed-out
    patch legitimately fits more cells. The limit is now divided by zoom so the
   判据回归本意: |x| beyond 3000px of visible width.
    """
    hard, soft = [], []
    limit = VIEW_LIMIT / max(float(zoom or 1.0), 0.01)
    for mid, (x, y) in pos.items():
        if abs(x) > limit or abs(y) > limit:
            hard.append("%s pos=(%.0f, %.0f) outside default view (|coord|>%.0f cells at zoom %.2f ≈ %dpx) "
                        "— module not visible"
                        % (mid, x, y, limit, zoom, VIEW_LIMIT * 15))
        elif x < -NEG_X_TOL:
            hard.append("%s x=%.0f is %.0f px left of the view's left edge" % (mid, x, -x * 15))
        elif x < 0 or y < 0:
            soft.append("%s pos=(%.0f, %.0f) has a small negative component (usually harmless)"
                        % (mid, x, y))
    return hard, soft


def check_grid(pos):
    """Check that every y is on an integer row number (0/1/2…)."""
    return ["%s y=%.2f is not an integer row (y unit is 'row' not 'cells'; write 0/1/2…)"
            % (mid, y)
            for mid, (x, y) in sorted(pos.items()) if not on_grid(y)]


# ================================================================ Wiring self-check

def check_input_dupes(d):
    """List input ports occupied by more than one cable (Cardinal keeps only the
    first; the rest are silently dropped)."""
    from collections import defaultdict
    ins = defaultdict(list)
    for c in d.get("cables", []):
        ins[(sid(c["inputModuleId"]), c["inputId"])].append(
            (sid(c["outputModuleId"]), c["outputId"]))
    return {k: v for k, v in ins.items() if len(v) > 1}


def report_input_dupes(d, by):
    dup = check_input_dupes(d)
    lines = []
    for (mid, port), srcs in sorted(dup.items(), key=lambda x: str(x[0])):
        name = by.get(mid, {}).get("model", mid)
        lines.append("  %s(id=%s) IN%s <- %d cables: %s"
                     % (name, mid, port, len(srcs), srcs))
    return lines


def analyze(d, strict=False, layout=None):
    """Unified layout + wiring health check. Returns (hard_errors, soft_warnings).

    `layout` = the coordinate table in force for this patch (see `pick_layout`).

    Rationale for tiers: HARD = will definitely break (invisible / overlapping /
    dropped cable); SOFT = non-conforming but currently usable (row misalignment,
    slight overlap, unregistered). `--strict` upgrades SOFT to HARD.
    """
    mods = d.get("modules", [])
    by = {sid(m["id"]): m for m in mods}
    widths = {sid(m["id"]): estimate_width(m) for m in mods}
    pos = {sid(m["id"]): resolved_pos(m) for m in mods}

    hard, soft = [], []

    vh, vs = check_view(pos, zoom=d.get("zoom", 1.0))
    hard += vh
    soft += vs

    soft += check_grid(pos)

    oh, os_ = check_overlap(pos, widths, tol=OVERLAP_TOL)
    hard += oh
    soft += os_

    # Input-port double-connect is a real bug (silently drops cables) — always HARD.
    for line in report_input_dupes(d, by):
        hard.append("input port double-connect: " + line.strip())

    # Unregistered modules.
    declared = {mid for mid, _r, _w in (layout if layout is not None else LAYOUT)}
    unreg = [m for m in mods if sid(m["id"]) not in declared]
    if unreg:
        names = ["%s(%s)" % (m.get("model"), m["id"]) for m in unreg]
        soft.append("have %d module(s) not in LAYOUT (apply auto-places them, but order is "
                    "unstable): %s" % (len(unreg), names))

    if strict:
        hard += soft
        soft = []
    return hard, soft


# ================================================================ Panel measurement

def scan_panel_svgs(resources=RESOURCES):
    """Scan this machine's panel SVGs; return {plugin_dir: {lower_panel_name: width_HP}}.

    Principle: Rack sizes a module from its panel SVG's physical size (1 HP = 5.08 mm).
    MUST group by plugin — different plugins reuse names (several have VCO.svg).
    """
    out = {}
    if not os.path.isdir(resources):
        return out
    for plugin in sorted(os.listdir(resources)):
        pdir = os.path.join(resources, plugin)
        if not os.path.isdir(pdir):
            continue
        panels = {}
        for dp, _dn, fn in os.walk(pdir):
            for f in fn:
                if not f.lower().endswith(".svg"):
                    continue
                try:
                    with open(os.path.join(dp, f), encoding="utf-8",
                              errors="replace") as fh:
                        head = fh.read(2000)
                except OSError:
                    continue
                m = re.search(r"<svg[^>]*>", head, re.S)
                if not m:
                    continue
                tag = m.group(0)
                mm = re.search(r'width="([0-9.]+)\s*mm"', tag)
                px = re.search(r'width="([0-9.]+)\s*(?:px)?"', tag)
                if mm:
                    panels[f[:-4].lower()] = float(mm.group(1)) / HP_MM
                elif px:
                    panels[f[:-4].lower()] = float(px.group(1)) / PX_PER_HP
        if panels:
            out[plugin] = panels
    return out


def resolve_panel_width(panels, model):
    """Find a model's panel width in a plugin's panel dict. Three-tier fallback.

    Exact match first, then strip common decorations (`_panel`, `Panel`/`PanelDark`,
    `-dark`/`-lowcontrast`, `Module`), then substring. Without the fallbacks the
    `widths` self-check reported27 legit entries as "panel not found", i.e. a
    self-check that checks nothing.
    """
    stem = model.lower()
    if stem in panels:
        return stem
    stripped = re.sub(r"(module|panel|_panel|-panel|dark|light|lowcontrast|"
                      r"latif|plastic|_white|_dark)$", "", stem)
    stripped = stripped.strip("_-")
    if stripped in panels:
        return stripped
    cands = [k for k in panels if stripped and stripped in k]
    if len(cands) == 1:
        return cands[0]
    if cands:
        # Prefer the shortest candidate: `ADSR.svg` over `ADSR-dark.svg`.
        return min(cands, key=len)
    # Last resort: drop a vendor prefix baked into the model name
    # (`rcm-pianoroll` -> PianoRoll.svg, `Bogaudio-ADSR` -> ADSR.svg).
    # Only accept a UNIQUE hit, otherwise we would silently guess.
    if "-" in stripped:
        tail = stripped.rsplit("-", 1)[1]
        if tail in panels:
            return tail
        cands = [k for k in panels if tail and tail in k]
        if len(cands) == 1:
            return cands[0]
    return None


def cmd_widths():
    """Re-measure panel widths and verify the table values are still accurate."""
    tree = scan_panel_svgs()
    print("=" * 66)
    print("measured panel widths (1 HP = %.2fmm = 1 cell = %.0fpx)" % (HP_MM, PX_PER_HP))
    print("source:", RESOURCES)
    if not tree:
        print("  [error] no panel SVGs scanned (path changed?)")
        return 1
    total = sum(len(v) for v in tree.values())
    print("  scanned %d plugins / %d panels" % (len(tree), total))
    print("-" * 66)
    bad, missing = 0, 0
    for key, want in sorted(WIDTH_BY_PLUGIN_MODEL.items()):
        plugin, model = key.split("/", 1)
        stem = SVG_ALIAS.get((plugin, model))
        got = tree.get(plugin, {}).get(stem) if stem else None
        if got is None:
            stem = resolve_panel_width(tree.get(plugin, {}), model)
            got = tree.get(plugin, {}).get(stem) if stem else None
        if got is None:
            print("   %-34s table %5.1f   panel not found (no SVG under %s/res; "
                  "code-drawn panel, width came from real patch coordinates)"
                  % (key, want, plugin))
            missing += 1
        elif abs(got - want) > 0.05:
            print("   %-34s table %5.1f   !! panel measured %.1f — table stale, update it"
                  % (key, want, got))
            bad += 1
    print("-" * 66)
    if not bad and not missing:
        print("verdict: all consistent (%d entries)" % len(WIDTH_BY_PLUGIN_MODEL))
        return 0
    print("verdict: %d stale, %d not found" % (bad, missing))
    return 1 if bad else 0


# ================================================================ Subcommands

def check_file(path):
    """Just print coordinates, do not edit the file."""
    d = patchio.read_patch(path)
    mods = d.get("modules", [])
    widths = {sid(m["id"]): estimate_width(m) for m in mods}
    print("=" * 66)
    print("%s | %d modules | zoom %s" % (os.path.basename(path), len(mods), d.get("zoom")))
    for m in sorted(mods, key=lambda x: (resolved_pos(x)[1], resolved_pos(x)[0])):
        print("   pos=%-14s %-34s w≈%-3.0f %s"
              % (json.dumps(m.get("pos")), m["plugin"] + "/" + m["model"],
                 widths[sid(m["id"])], m["id"]))
    xs = [resolved_pos(m)[0] for m in mods]
    ys = [resolved_pos(m)[1] for m in mods]
    if xs:
        print("   x range %.0f ~ %.0f (span %.0f cells ≈ %.0f px)"
              % (min(xs), max(xs), max(xs) - min(xs), (max(xs) - min(xs)) * 15))
        print("   y range %.0f ~ %.0f" % (min(ys), max(ys)))
    return 0


def guard_file(path, strict=False):
    """GATE: layout + wiring double check. Returns 1 if any HARD error."""
    d = patchio.read_patch(path)
    mods = d.get("modules", [])
    lay = pick_layout(path)
    hard, soft = analyze(d, strict=strict, layout=lay)

    target, _declared, _unreg, log = do_layout(d, lay)
    actual = {sid(m["id"]): resolved_pos(m) for m in mods}
    drift = [mid for mid in target
             if mid not in actual
             or abs(target[mid][0] - actual[mid][0]) > 0.5
             or abs(target[mid][1] - actual[mid][1]) > 0.5]

    print("=" * 66)
    print("layout gate | %s | %d modules | %d cables"
          % (os.path.basename(path), len(mods), len(d.get("cables", []))))
    print("re-layout target (what `apply` would produce):")
    for line in log:
        print(line)
    if drift:
        print("current file differs from target at %d module(s) (not an error; run apply to align):"
              % len(drift))
        for mid in drift:
            name = next((m.get("model") for m in mods if sid(m["id"]) == mid), mid)
            print("   %s(%s): now %s -> target [%.0f, %.0f]"
                  % (name, mid, list(actual.get(mid, [])), target[mid][0], target[mid][1]))
    else:
        print("current file vs target: identical")
    print("-" * 66)
    for w in soft:
        print("[warn] " + w)
    if hard:
        for e in hard:
            print("[FAIL] " + e)
        print("-" * 66)
        print("verdict: FAIL (%d hard errors, %d warnings)" % (len(hard), len(soft)))
        return 1
    print("verdict: PASS" + (" (%d warnings)" % len(soft) if soft else ""))
    return 0


def apply_file(path, push=False, strict=False, write_etext=True):
    if not os.path.exists(path):
        print("[error] file not found:", path)
        return 1
    d = patchio.read_patch(path)
    mods = d.get("modules", [])
    widths = {sid(m["id"]): estimate_width(m) for m in mods}

    # Backup before mutating.
    bak = path[:-4] + "_before_layout_%s.vcv" % time.strftime("%H%M%S")
    shutil.copy2(path, bak)
    print("[backup]", os.path.basename(bak))

    pos, _declared, unreg, log = do_layout(d, pick_layout(path))
    print("layout computed:")
    for line in log:
        print(line)

    # Coordinates we just produced are always grid-aligned; this checks for any
    # residual problem.
    hard, soft = check_overlap(pos, widths, tol=OVERLAP_TOL)
    soft += check_grid(pos)
    if hard:
        print("[overlap error]")
        for b in hard:
            print("   ", b)
    else:
        print("[overlap check] pass, no overlaps")

    if unreg and strict:
        print("[FAIL --strict] %d module(s) not in LAYOUT, refusing to write:" % len(unreg))
        for m in unreg:
            print("   %s/%s id=%s" % (m.get("plugin"), m.get("model"), m["id"]))
        print("   add them to LAYOUT in layout_patch.py (id, row, width)")
        return 1

    by = {sid(m["id"]): m for m in mods}
    for mid, p in pos.items():
        by[mid]["pos"] = p

    # Update the label panel (only our own panel; never overwrite a user's notes).
    te = next((m for m in mods if m.get("model") == "TextEditor"), None)
    if te is not None:
        if not write_etext:
            print("[label] skipped per --no-etext")
        else:
            old = (te.get("data") or {}).get("etext") or ""
            if old and "HELM FULL" not in old:
                print("[label] detected non-rack custom text, left untouched (%d chars)" % len(old))
            else:
                te.setdefault("data", {})
                te["data"]["etext"] = ETEXT
                te["data"]["width"] = 26
                print("[label] TextEditor(id=%s) text updated, %d chars"
                      % (te["id"], len(ETEXT)))

    patchio.write_patch(path, d)
    print("[write]", path, "(%d modules)" % len(mods))

    dup = report_input_dupes(d, by)
    if dup:
        print("[!!] input-port double-connect unresolved (Cardinal drops the extra cables):")
        for line in dup:
            print("   ", line)
        print("     -> wiring is not this tool's job; use fix_drum_bus.py report then edit cables")
    else:
        print("[wiring check] pass, no input-port double-connect")

    if push:
        import cardinal_mcp as cm
        name = os.path.basename(path)
        print("[push] load_patch", name)
        print("   ", cm.load_patch(name))
        time.sleep(4)
        live, _ = cm.live_patch_path()
        d2 = patchio.read_patch(live)
        print("[verify] live autosave module count =", len(d2["modules"]))
        for m in sorted(d2["modules"], key=lambda x: (resolved_pos(x)[1], resolved_pos(x)[0])):
            print("   pos=%-14s %-34s %s"
                  % (json.dumps(m["pos"]), m["plugin"] + "/" + m["model"], m["id"]))
    return 1 if dup else 0


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)
    cmd = args[0]
    if cmd == "widths":
        sys.exit(cmd_widths())
    if len(args) < 2:
        print(__doc__)
        sys.exit(1)
    target = args[1]
    if cmd == "check":
        sys.exit(check_file(target))
    elif cmd == "guard":
        sys.exit(guard_file(target, strict="--strict" in args))
    elif cmd == "apply":
        sys.exit(apply_file(target,
                            push="--push" in args,
                            strict="--strict" in args,
                            write_etext="--no-etext" not in args))
    else:
        print(__doc__)
        sys.exit(1)
