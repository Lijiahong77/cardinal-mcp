#!/usr/bin/env python3
"""SMK25 MIDI 侦察 —— 采集全部消息落盘，然后自动分类分析。

用法：
  python midiprobe.py dump  <秒数> <输出json>
  python midiprobe.py analyze <输入json>

分析目标：把「哪个控件发哪个 CC」搞清楚。
  · 连续扫值（0->127 平滑变化）= 旋钮/触控条
  · 固定值反复出现            = 按键/鼓垫（触发型）
  · status 0x90/0x80          = 琴键或鼓垫音符
"""
import json
import sys
import time
from collections import defaultdict

import winmidi


def dump(seconds, path):
    ins, outs = winmidi.list_devices()
    print(f"输入设备: {ins}")
    idxs = list(range(len(ins)))
    print(f"监听 {idxs}，共 {seconds} 秒 —— 请操作键盘……")
    recs = winmidi.listen(idxs, seconds)
    data = [{"t": round(t, 4), "dev": d, "status": st, "d1": a, "d2": b}
            for t, d, st, a, b in recs]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    print(f"落盘 {len(data)} 条 -> {path}")


def analyze(path):
    recs = json.load(open(path, encoding="utf-8"))
    print(f"总消息 {len(recs)} 条")
    if not recs:
        return

    # 时间线切片：按 1 秒分桶，看每个dev在干什么
    devs = sorted({r["dev"] for r in recs})
    print(f"活跃端口: {devs}")

    # 每个 (dev, kind, ch, d1) 的统计
    groups = defaultdict(list)
    for r in recs:
        kind = r["status"] & 0xF0
        ch = (r["status"] & 0x0F) + 1
        groups[(r["dev"], kind, ch, r["d1"])].append((r["t"], r["d2"]))

    print("\n" + "=" * 78)
    print("按 (端口 / 类型 / 通道 / data1) 分组：")
    print("=" * 78)
    kindname = {0x90: "NOTE", 0x80: "NOTE_OFF", 0xB0: "CC", 0xE0: "PITCHBEND",
                0xA0: "POLY_AT", 0xD0: "CHAN_AT", 0xF0: "SYSEX"}
    rows = []
    for (dev, kind, ch, d1), vals in groups.items():
        vmin = min(v for _, v in vals)
        vmax = max(v for _, v in vals)
        uniq = len({v for _, v in vals})
        # 判断是不是"扫描型"（旋钮）：值变化多且覆盖范围大
        span = vmax - vmin
        if kind == 0xB0:
            typ = "旋钮" if (uniq >= 5 and span >= 8) else "触发/开关"
        elif kind in (0x90, 0x80):
            typ = "音符"
        elif kind == 0xE0:
            typ = "弯音/调制条"
        else:
            typ = "?"
        rows.append((dev, kindname.get(kind, hex(kind)), ch, d1, typ,
                     len(vals), vmin, vmax, uniq))
    rows.sort(key=lambda x: (x[0], x[1], x[3]))
    print(f"{'dev':<4}{'类型':<11}{'ch':<4}{'data1':<7}{'判定':<10}"
          f"{'次数':<7}{'最小':<6}{'最大':<6}{'不同值'}")
    for r in rows:
        print(f"{r[0]:<4}{r[1]:<11}{r[2]:<4}{r[3]:<7}{r[4]:<10}"
              f"{r[5]:<7}{r[6]:<6}{r[7]:<6}{r[8]}")

    # 端口去重判断：两个端口是否内容完全相同
    print("\n" + "=" * 78)
    print("端口关系检查（判断哪些端口是同一份数据的镜像）")
    print("=" * 78)
    sig = {}
    for d in devs:
        sig[d] = sorted((r["status"], r["d1"], r["d2"])
                        for r in recs if r["dev"] == d)
    for i, a in enumerate(devs):
        for b in devs[i + 1:]:
            same = sig[a] == sig[b]
            print(f"  dev{a} vs dev{b}: "
                  f"{'内容完全相同（镜像）' if same else '内容不同（各自独立）'}"
                  f"  [{len(sig[a])} / {len(sig[b])} 条]")

    # 只保留每个"内容组"的第一个端口，输出干净清单
    print("\n" + "=" * 78)
    print("去重后的控件清单（建议接线只看这一份）")
    print("=" * 78)
    seen_port = set()
    uniq_rows = []
    for d in devs:
        dup = None
        for p in seen_port:
            if sig[p] == sig[d]:
                dup = p
                break
        if dup is not None:
            continue
        seen_port.add(d)
        for r in rows:
            if r[0] == d:
                uniq_rows.append(r)
    for r in uniq_rows:
        print(f"  dev{r[0]}  {r[1]:<10} ch{r[2]:<3} data1={r[3]:<4} "
              f"{r[4]:<10} 出现{r[5]}次 值范围 {r[6]}~{r[7]}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "analyze"
    if cmd == "dump":
        secs = float(sys.argv[2]) if len(sys.argv) > 2 else 30
        out = sys.argv[3] if len(sys.argv) > 3 else r"D:\Cardinal\refs\midi_dump.json"
        dump(secs, out)
    else:
        p = sys.argv[2] if len(sys.argv) > 2 else r"D:\Cardinal\refs\midi_dump.json"
        analyze(p)
