#!/usr/bin/env python3
"""按时间线拆解 MIDI 采集数据，弄清「哪个控件发什么」。"""
import json
import sys
from collections import OrderedDict

recs = json.load(open(sys.argv[1] if len(sys.argv) > 1
                      else r"D:\Cardinal\refs\midi_dump.json", encoding="utf-8"))
# 只用 dev0（dev1 是镜像）
recs = [r for r in recs if r["dev"] == 0]
recs.sort(key=lambda r: r["t"])
print(f"dev0 消息 {len(recs)} 条，时间跨度 {recs[-1]['t']:.1f}s\n")

KIND = {0x90: "NOTE", 0x80: "NOTEOFF", 0xB0: "CC", 0xE0: "PITCHBEND"}

# ---- 1. 按秒分桶，看操作节奏 ----
print("=" * 76)
print("① 时间线（每秒内的活动摘要）")
print("=" * 76)
buckets = OrderedDict()
for r in recs:
    s = int(r["t"])
    k = KIND.get(r["status"] & 0xF0, hex(r["status"] & 0xF0))
    ch = (r["status"] & 0x0F) + 1
    buckets.setdefault(s, []).append((k, ch, r["d1"], r["d2"]))

for s in sorted(buckets):
    ev = buckets[s]
    # 归并同类
    summary = OrderedDict()
    for k, ch, d1, d2 in ev:
        key = f"{k}/ch{ch}/d{d1}"
        summary.setdefault(key, []).append(d2)
    parts = []
    for key, vals in summary.items():
        if len(vals) == 1:
            parts.append(f"{key}={vals[0]}")
        else:
            parts.append(f"{key}[{len(vals)}次 {min(vals)}~{max(vals)}]")
    print(f"  {s:>3}s | " + "  ".join(parts[:6]))

# ---- 2. CC1 完整序列（判断是不是触控条）----
print("\n" + "=" * 76)
print("② CC1 (ch9) 的完整值序列 —— 判断是否连续滑动")
print("=" * 76)
s1 = [(round(r["t"], 2), r["d2"]) for r in recs
      if (r["status"] & 0xF0) == 0xB0 and (r["status"] & 0x0F) == 8 and r["d1"] == 1]
print(f"共 {len(s1)} 条：")
seq = [v for _, v in s1]
print("  值序列:", seq[:100])
if len(seq) > 100:
    print("  ...", seq[100:])
# 单调性检查
up = sum(1 for i in range(1, len(seq)) if seq[i] > seq[i - 1])
dn = sum(1 for i in range(1, len(seq)) if seq[i] < seq[i - 1])
eq = sum(1 for i in range(1, len(seq)) if seq[i] == seq[i - 1])
print(f"  变化统计: 上升 {up} / 下降 {dn} / 不变 {eq}")

# ---- 3. CC20~27 各自的序列（疑似 8 个旋钮）----
print("\n" + "=" * 76)
print("③ CC20~27 序列 —— 疑似 8 个旋钮")
print("=" * 76)
for cc in range(20, 28):
    hits = [(round(r["t"], 2), (r["status"] & 0x0F) + 1, r["d2"]) for r in recs
            if (r["status"] & 0xF0) == 0xB0 and r["d1"] == cc]
    if hits:
        chset = sorted({h[1] for h in hits})
        print(f"  CC{cc}: 通道{chset}  {len(hits)}条  值={[h[2] for h in hits]}")
        print(f"        时间={[h[0] for h in hits]}")
    else:
        print(f"  CC{cc}: 无数据")

# ---- 4. 全部 CC 编号总览 ----
print("\n" + "=" * 76)
print("④ 全部 CC 编号总览")
print("=" * 76)
ccc = {}
for r in recs:
    if (r["status"] & 0xF0) == 0xB0:
        key = ((r["status"] & 0x0F) + 1, r["d1"])
        ccc.setdefault(key, []).append(r["d2"])
for (ch, cc), vals in sorted(ccc.items()):
    print(f"  ch{ch:<3} CC{cc:<4} {len(vals):>4}条  值 {min(vals)}~{max(vals)}"
          f"  不同{len(set(vals))}")

# ---- 5. 音符总览（琴键 vs 鼓垫）----
print("\n" + "=" * 76)
print("⑤ 音符总览（按通道分：琴键 vs 鼓垫）")
print("=" * 76)
notes = {}
for r in recs:
    k = r["status"] & 0xF0
    if k in (0x90, 0x80):
        ch = (r["status"] & 0x0F) + 1
        notes.setdefault(ch, []).append((r["d1"], r["d2"], "ON" if k == 0x90 else "OFF"))
for ch in sorted(notes):
    print(f"  ch{ch}: " + " | ".join(
        f"note{a}({b},{c})" for a, b, c in notes[ch]))
