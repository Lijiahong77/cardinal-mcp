#!/usr/bin/env python3
"""分离测试分析：对比「未按 KNOB-B」与「按过 KNOB-B」两种状态下拧同一个旋钮的差异。"""
import json
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")

PATH = sys.argv[1] if len(sys.argv) > 1 else r"D:\Cardinal\refs\midi_dump_v3.json"
recs = json.load(open(PATH, encoding="utf-8"))
print(f"总消息 {len(recs)} 条")
t0 = recs[0]["t"]
span = recs[-1]["t"] - t0
print(f"时长 {span:.1f} 秒")

cnt = defaultdict(int)
for r in recs:
    cnt[(r["dev"], r["status"] & 0xF0)] += 1
print()
print("端口 × 消息类型 计数：")
for (d, k), n in sorted(cnt.items()):
    name = {0x80: "NOTE_OFF", 0x90: "NOTE_ON", 0xB0: "CC",
            0xD0: "AFTERTOUCH", 0xE0: "PITCHBEND", 0xA0: "POLY_AT"}.get(k, hex(k))
    print(f"  dev{d}  {name:<11} {n} 条")

print()
print("=" * 100)
print("逐秒活动（每行 1 秒；dev0/1 = 主端口，dev2 = MIDIIN3）")
print("=" * 100)
for i in range(int(span) + 1):
    a, b = i, i + 1
    sel0 = [r for r in recs if r["dev"] == 0 and a <= r["t"] - t0 < b]
    sel2 = [r for r in recs if r["dev"] == 2 and a <= r["t"] - t0 < b]
    if not sel0 and not sel2:
        continue
    p0 = []
    cc = defaultdict(list)
    pb0 = defaultdict(list)
    no = defaultdict(list)
    for r in sel0:
        k = r["status"] & 0xF0
        ch = (r["status"] & 0x0F) + 1
        if k == 0xB0:
            cc[(ch, r["d1"])].append(r["d2"])
        elif k == 0xE0:
            pb0[ch].append(r["d2"])
        elif k == 0x90 and r["d2"] > 0:
            no[ch].append((r["d1"], r["d2"]))
    for (ch, d1), vs in sorted(cc.items()):
        p0.append(f"CC ch{ch} #{d1}={min(vs)}~{max(vs)} x{len(vs)}")
    for ch, vs in sorted(pb0.items()):
        p0.append(f"PB ch{ch} {min(vs)}~{max(vs)} x{len(vs)}")
    for ch, vs in sorted(no.items()):
        p0.append(f"Note ch{ch} " + ",".join(f"n{n}v{v}" for n, v in vs[:6]))
    p2 = []
    pb2 = defaultdict(list)
    for r in sel2:
        k = r["status"] & 0xF0
        ch = (r["status"] & 0x0F) + 1
        if k == 0xE0:
            pb2[ch].append(r["d2"])
        else:
            p2.append(f"st{r['status']:02X} ch{ch} d1={r['d1']} d2={r['d2']}")
    for ch, vs in sorted(pb2.items()):
        p2.append(f"PB ch{ch} d2={min(vs)}~{max(vs)} x{len(vs)}")
    print(f"  {a:>3}-{b:>3}s")
    print(f"        dev0/1: {' ; '.join(p0) if p0 else '—'}")
    if p2:
        print(f"        dev2  : {' ; '.join(p2)}")
