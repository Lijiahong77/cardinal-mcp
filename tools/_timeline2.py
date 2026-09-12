#!/usr/bin/env python3
"""按 2 秒分桶拆解 MIDI 采集数据，用于区分"哪一段操作产生了什么消息"。"""
import json
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")

PATH = sys.argv[1] if len(sys.argv) > 1 else r"D:\Cardinal\refs\midi_dump_v2.json"
recs = json.load(open(PATH, encoding="utf-8"))
print(f"总消息 {len(recs)} 条   文件 {PATH}")
if not recs:
    sys.exit()

KIND = {0x90: "NOTE", 0x80: "OFF", 0xB0: "CC", 0xE0: "PBEND",
        0xA0: "PAT", 0xD0: "CAT", 0xF0: "SYSEX"}

devs = sorted({r["dev"] for r in recs})
print("活跃端口:", devs)

sig = {d: sorted((r["status"], r["d1"], r["d2"]) for r in recs if r["dev"] == d)
       for d in devs}
print("--- 端口关系 ---")
for i, a in enumerate(devs):
    for b in devs[i + 1:]:
        print(f"  dev{a} vs dev{b}: "
              f"{'镜像（同内容）' if sig[a] == sig[b] else '不同'} "
              f"[{len(sig[a])}/{len(sig[b])}]")

groups = defaultdict(list)
for r in recs:
    k = r["status"] & 0xF0
    groups[(r["dev"], KIND.get(k, hex(k)), (r["status"] & 0x0F) + 1, r["d1"])].append(
        (r["t"], r["d2"]))

print()
print("=" * 92)
print("全局控件清单（按端口）")
print("=" * 92)
for (dev, kind, ch, d1), vals in sorted(groups.items(),
                                        key=lambda x: (x[0][0], x[0][1], x[0][3])):
    vs = [v for _, v in vals]
    print(f"  dev{dev} {kind:<6} ch{ch:<3} d1={d1:<4} 次数={len(vals):<5} "
          f"值 {min(vs)}~{max(vs)}  不同值={len(set(vs))}")

t0 = recs[0]["t"]
B = 2
span = recs[-1]["t"] - t0
print()
print("=" * 92)
print(f"时间线（每 {B} 秒一格，只看 dev0；共 {span:.1f} 秒）")
print("=" * 92)
for i in range(int(span) // B + 1):
    a, b = i * B, (i + 1) * B
    sel = [r for r in recs if r["dev"] == 0 and a <= r["t"] - t0 < b]
    if not sel:
        print(f"  {a:>3}-{b:>3}s | （静）")
        continue
    c = defaultdict(list)
    for r in sel:
        k = r["status"] & 0xF0
        c[(KIND.get(k, hex(k)), (r["status"] & 0x0F) + 1, r["d1"])].append(r["d2"])
    parts = []
    for (kind, ch, d1), vs in sorted(c.items()):
        if kind in ("NOTE", "OFF"):
            parts.append(f"{kind} ch{ch} n{d1} v{min(vs)}~{max(vs)} x{len(vs)}")
        elif kind == "CC":
            tag = " *新*" if d1 not in range(20, 28) else ""
            parts.append(f"CC ch{ch} #{d1}={min(vs)}~{max(vs)} x{len(vs)}{tag}")
        elif kind == "PBEND":
            parts.append(f"PB ch{ch} {min(vs)}~{max(vs)} x{len(vs)}")
        else:
            parts.append(f"{kind} ch{ch} d1={d1} x{len(vs)}")
    print(f"  {a:>3}-{b:>3}s | " + " ; ".join(parts))
