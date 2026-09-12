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
    # ---- Fundamental ----
    "Fundamental/VCO": 9,
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
    # ---------------- row 0: synth chain + control + output ----------------
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

def do_layout(d):
    """Compute the new coordinates.

    Returns (new_pos {id: [x, y]}, registered_id_set, unregistered_modules, log_lines).
    """
    mods = d.get("modules", [])
    by = {sid(m["id"]): m for m in mods}
    widths = {mid: estimate_width(m) for mid, m in by.items()}

    declared = {}          # id -> (row, width)
    missing = []
    for mid, row, w in LAYOUT:
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


def check_view(pos):
    """Check whether any module is off the default view. Returns (hard, soft)."""
    hard, soft = [], []
    for mid, (x, y) in pos.items():
        if abs(x) > VIEW_LIMIT or abs(y) > VIEW_LIMIT:
            hard.append("%s pos=(%.0f, %.0f) outside default view (|coord|>%d cells ≈ %dpx) "
                        "— module not visible"
                        % (mid, x, y, VIEW_LIMIT, VIEW_LIMIT * 15))
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


def analyze(d, strict=False):
    """Unified layout + wiring health check. Returns (hard_errors, soft_warnings).

    Rationale for tiers: HARD = will definitely break (invisible / overlapping /
    dropped cable); SOFT = non-conforming but currently usable (row misalignment,
    slight overlap, unregistered). `--strict` upgrades SOFT to HARD.
    """
    mods = d.get("modules", [])
    by = {sid(m["id"]): m for m in mods}
    widths = {sid(m["id"]): estimate_width(m) for m in mods}
    pos = {sid(m["id"]): resolved_pos(m) for m in mods}

    hard, soft = [], []

    vh, vs = check_view(pos)
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
    declared = {mid for mid, _r, _w in LAYOUT}
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
        stem = SVG_ALIAS.get((plugin, model), model.lower())
        got = tree.get(plugin, {}).get(stem)
        if got is None:
            print("   %-34s table %5.1f   panel not found (panel name may be %s.svg; add to SVG_ALIAS)"
                  % (key, want, stem))
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
    hard, soft = analyze(d, strict=strict)

    target, _declared, _unreg, log = do_layout(d)
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

    pos, _declared, unreg, log = do_layout(d)
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
