#!/usr/bin/env python3
"""shotcrop.py - crop a screen region 1:1, plus a quick Cardinal/OSC probe.

Why this exists
---------------
`shot.py` downsamples the whole desktop, which is fine for "what is on screen
in general" but useless for reading a module's panel labels or comparing a
single knob before/after. This tool grabs a rectangle at native resolution so
the result can be inspected pixel by pixel.

It also carries a tiny `probe` command that answers the two questions we ask
at the start of every Cardinal session:

    - is a Cardinal process running, and what is its PID?
    - is OSC listening on UDP 2228? (the OSC switch is NOT persistent:
      `Engine -> Enable OSC remote control` must be re-enabled after every
      Cardinal restart, so this needs checking before every push)

Zero third-party dependencies: it reuses `shot.grab()` (GDI BitBlt) and
`shot.write_png()` (hand-rolled PNG writer) and otherwise only uses ctypes,
so it runs under any Python 3 without a venv.

Usage
-----
    python shotcrop.py probe
    python shotcrop.py crop <out.png> <x> <y> <width> <height>
    python shotcrop.py full <out.png> [max_width]

Notes
-----
* Coordinates are PHYSICAL pixels of the virtual desktop (the whole multi
  monitor space), origin at the top-left of the leftmost monitor. On a
  200%-DPI display, 3200x2000 physical == 1600x1000 logical, and Cardinal's
  own zoom further scales the rack inside that.
* To find a module's rectangle, remember the two empirical constants for
  this machine (measured 2026-09-13, Cardinal zoom ~0.75):
      x_phys = X0 + 21 * pos_x        (1 grid unit == 21 physical px)
  and the row origin; X0 is read off any known module in a full screenshot.
  Guessing coordinates wastes round trips, so anchor on a known module first.
* A crop is a read-only screenshot: it never touches Cardinal's state.
"""
import ctypes
import os
import sys

# `shot` lives next to this file; import it by path so the tool works no
# matter which directory the caller happens to be in.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shot  # noqa: E402


def probe():
    """Print running Cardinal processes and whether UDP 2228 is listening."""
    k32 = ctypes.windll.kernel32
    TH32CS_SNAPPROCESS = 0x00000002

    class PROCESSENTRY32(ctypes.Structure):
        _fields_ = [
            ("dwSize", ctypes.c_ulong), ("cntUsage", ctypes.c_ulong),
            ("th32ProcessID", ctypes.c_ulong),
            ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
            ("th32ModuleID", ctypes.c_ulong), ("cntThreads", ctypes.c_ulong),
            ("th32ParentProcessID", ctypes.c_ulong),
            ("pcPriClassBase", ctypes.c_long), ("dwFlags", ctypes.c_ulong),
            ("szExeFile", ctypes.c_char * 260),
        ]

    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    pe = PROCESSENTRY32()
    pe.dwSize = ctypes.sizeof(PROCESSENTRY32)
    found = []
    if k32.Process32First(snap, ctypes.byref(pe)):
        while True:
            name = pe.szExeFile.decode("mbcs", "replace")
            if "cardinal" in name.lower():
                found.append((pe.th32ProcessID, name))
            if not k32.Process32Next(snap, ctypes.byref(pe)):
                break
    k32.CloseHandle(snap)
    print("Cardinal processes:", found if found else "NONE (Cardinal is not running)")

    # netstat output on Chinese Windows is not UTF-8; decode with errors=replace
    # so we never crash just because of a localised header line.
    try:
        import subprocess
        out = subprocess.run(["netstat", "-ano", "-p", "UDP"],
                             capture_output=True).stdout.decode("mbcs", "replace")
        lines = [l.strip() for l in out.splitlines() if ":2228" in l]
        print("UDP 2228:", lines if lines else "NOT LISTENING -> OSC remote control is OFF")
    except Exception as exc:  # netstat missing / blocked
        print("netstat failed:", exc)


def crop(out, x, y, w, h):
    """Write a 1:1 crop of the virtual desktop to `out` as a PNG.

    Coordinates are clamped so an over-large request degrades to "as much as
    fits" instead of raising - handy when probing near a screen edge.
    """
    W, H, bgra = shot.grab()
    x, y = max(0, x), max(0, y)
    w, h = min(w, W - x), min(h, H - y)
    rows = []
    for oy in range(h):
        base = (y + oy) * W * 4
        row = bytearray(w * 3)
        for ox in range(w):
            i = base + (x + ox) * 4
            row[ox * 3 + 0] = bgra[i + 2]   # BGRA -> RGB
            row[ox * 3 + 1] = bgra[i + 1]
            row[ox * 3 + 2] = bgra[i + 0]
        rows.append(bytes(row))
    n = shot.write_png(out, w, h, rows)
    print("crop %dx%d at (%d,%d) -> %s  %d bytes" % (w, h, x, y, out, n))


def full(out, max_width=1600):
    """Write the whole desktop, downsampled to at most `max_width` wide."""
    W, H, bgra = shot.grab()
    step = max(1, -(-W // max_width))          # ceil division
    ow, oh = W // step, H // step
    rows = []
    for oy in range(oh):
        base = (oy * step) * W * 4
        row = bytearray(ow * 3)
        for ox in range(ow):
            i = base + ox * step * 4
            row[ox * 3 + 0] = bgra[i + 2]
            row[ox * 3 + 1] = bgra[i + 1]
            row[ox * 3 + 2] = bgra[i + 0]
        rows.append(bytes(row))
    n = shot.write_png(out, ow, oh, rows)
    print("screen %dx%d -> %dx%d (step %d) -> %s  %d bytes"
          % (W, H, ow, oh, step, out, n))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    mode = sys.argv[1]
    if mode == "probe":
        probe()
    elif mode == "crop":
        crop(sys.argv[2], *[int(v) for v in sys.argv[3:7]])
    elif mode == "full":
        full(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 1600)
    else:
        print(__doc__)
        sys.exit(1)
