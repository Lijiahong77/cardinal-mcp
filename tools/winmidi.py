#!/usr/bin/env python3
"""Windows 原生 MIDI（winmm.dll）最小封装 —— 不依赖第三方库。

用途：
  1. 列出系统 MIDI 输入/输出设备
  2. 监听若干输入端口，解码 Note/CC/PitchBend/Aftertouch
  3. （后续）往输出端口发消息，做 AI 演奏注入

注意：winmm 的回调是 C 函数指针，Python 侧必须保持引用，否则会被 GC 掉导致崩溃。
"""
import ctypes
import sys
import time
from ctypes import wintypes

winmm = ctypes.WinDLL("winmm")

MAXPNAMELEN = 32
MIM_DATA = 0x3C3
MIM_LONGDATA = 0x3C4
CALLBACK_FUNCTION = 0x00030000

CC_NAMES = {
    0: "Bank Select", 1: "Mod Wheel", 2: "Breath", 4: "Foot", 5: "Portamento Time",
    6: "Data Entry", 7: "Volume", 8: "Balance", 10: "Pan", 11: "Expression",
    64: "Sustain Pedal", 65: "Portamento", 66: "Sostenuto", 67: "Soft Pedal",
    71: "Resonance", 74: "Cutoff/Brightness", 84: "Portamento Ctl", 91: "Reverb",
    92: "Tremolo", 93: "Chorus", 94: "Detune", 95: "Phaser",
    120: "All Sound Off", 121: "Reset All Ctl", 123: "All Notes Off",
}

_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def note_name(n):
    return f"{_NOTE_NAMES[n % 12]}{n // 12 - 1}"


class MIDIINCAPSW(ctypes.Structure):
    _fields_ = [
        ("wMid", wintypes.WORD),
        ("wPid", wintypes.WORD),
        ("vDriverVersion", wintypes.UINT),
        ("szPname", wintypes.WCHAR * MAXPNAMELEN),
        ("dwSupport", wintypes.DWORD),
    ]


class MIDIOUTCAPSW(ctypes.Structure):
    _fields_ = [
        ("wMid", wintypes.WORD),
        ("wPid", wintypes.WORD),
        ("vDriverVersion", wintypes.UINT),
        ("szPname", wintypes.WCHAR * MAXPNAMELEN),
        ("wTechnology", wintypes.WORD),
        ("wVoices", wintypes.WORD),
        ("wNotes", wintypes.WORD),
        ("wChannelMask", wintypes.WORD),
        ("dwSupport", wintypes.DWORD),
    ]


winmm.midiInGetNumDevs.restype = wintypes.UINT
winmm.midiOutGetNumDevs.restype = wintypes.UINT
winmm.midiInGetDevCapsW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT]
winmm.midiOutGetDevCapsW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT]

_MIDIINPROC = ctypes.WINFUNCTYPE(None, ctypes.c_void_p, wintypes.UINT,
                                 ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
winmm.midiInOpen.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p,
                             _MIDIINPROC, ctypes.c_void_p, wintypes.DWORD]
winmm.midiInOpen.restype = wintypes.UINT
for _fn in ("midiInStart", "midiInStop", "midiInReset", "midiInClose"):
    getattr(winmm, _fn).argtypes = [ctypes.c_void_p]


def list_devices():
    """返回 (inputs, outputs)，元素为设备名。索引即 winmm 设备 ID。"""
    ins = []
    for i in range(winmm.midiInGetNumDevs()):
        caps = MIDIINCAPSW()
        r = winmm.midiInGetDevCapsW(ctypes.c_void_p(i), ctypes.byref(caps),
                                    ctypes.sizeof(caps))
        ins.append(caps.szPname if r == 0 else f"<err {r}>")
    outs = []
    for i in range(winmm.midiOutGetNumDevs()):
        caps = MIDIOUTCAPSW()
        r = winmm.midiOutGetDevCapsW(ctypes.c_void_p(i), ctypes.byref(caps),
                                     ctypes.sizeof(caps))
        outs.append(caps.szPname if r == 0 else f"<err {r}>")
    return ins, outs


def decode(status, d1, d2):
    """把 3 字节 MIDI 消息翻译成 (类型, 通道, 数据1, 数据2, 说明)。"""
    kind = status & 0xF0
    ch = (status & 0x0F) + 1
    if kind == 0x90:
        t = "NOTE_ON" if d2 > 0 else "NOTE_OFF"
        return t, ch, d1, d2, note_name(d1) + (f" vel={d2}" if d2 else "")
    if kind == 0x80:
        return "NOTE_OFF", ch, d1, d2, note_name(d1)
    if kind == 0xB0:
        return "CC", ch, d1, d2, CC_NAMES.get(d1, "")
    if kind == 0xE0:
        return "PITCHBEND", ch, d1, d2, str((d2 << 7 | d1) - 8192)
    if kind == 0xA0:
        return "POLY_AT", ch, d1, d2, note_name(d1)
    if kind == 0xD0:
        return "CHAN_AT", ch, d1, d2, ""
    if kind == 0xF0:
        return "SYSTEM", ch, d1, d2, ""
    return "UNKNOWN", ch, d1, d2, ""


def listen(device_indices, seconds=8.0):
    """监听若干输入端口，返回 [(相对秒, 设备idx, status, d1, d2), ...]。"""
    records = []
    handles, procs = [], []
    t0 = time.monotonic()

    def make_cb(idx):
        def _cb(hmi, msg, inst, p1, p2):
            if msg == MIM_DATA:
                b = p1 & 0xFFFFFFFF
                records.append((time.monotonic() - t0, idx,
                                b & 0xFF, (b >> 8) & 0xFF, (b >> 16) & 0xFF))
        return _MIDIINPROC(_cb)

    for idx in device_indices:
        h = ctypes.c_void_p()
        cb = make_cb(idx)
        r = winmm.midiInOpen(ctypes.byref(h), ctypes.c_void_p(idx), cb,
                             None, CALLBACK_FUNCTION)
        if r != 0:
            print(f"  打开输入设备 [{idx}] 失败，返回码 {r}")
            continue
        procs.append(cb)          # 保持回调引用，防止 GC
        handles.append(h)
        winmm.midiInStart(h)

    try:
        while time.monotonic() - t0 < seconds:
            time.sleep(0.03)
    finally:
        for h in handles:
            winmm.midiInStop(h)
            winmm.midiInReset(h)
            winmm.midiInClose(h)
    return records


if __name__ == "__main__":
    ins, outs = list_devices()
    print(f"MIDI 输入设备 {len(ins)} 个:")
    for i, n in enumerate(ins):
        print(f"  [{i}] {n}")
    print(f"MIDI 输出设备 {len(outs)} 个:")
    for i, n in enumerate(outs):
        print(f"  [{i}] {n}")

    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 0
    if secs > 0:
        idxs = [int(x) for x in sys.argv[2].split(",")] if len(sys.argv) > 2 \
            else list(range(len(ins)))
        print(f"\n监听端口 {idxs}，共 {secs} 秒 —— 请操作键盘……")
        recs = listen(idxs, secs)
        print(f"收到 {len(recs)} 条消息：")
        for t, idx, st, d1, d2 in recs[:120]:
            kind, ch, a, b, extra = decode(st, d1, d2)
            print(f"  [{t:6.2f}s] dev{idx} ch{ch:<2} {kind:<9} "
                  f"data1={a:<4} data2={b:<4} {extra}")
