#!/usr/bin/env python3
"""实时监听 MIDI 输入 —— 每收到一条立刻打印，不用等窗口结束。

用法：
    winmidi_live.py <秒数> [端口逗号列表]

例：winmidi_live.py 60 0,1,2     # 听 60 秒，三个端口全听
     winmidi_live.py 30           # 听 30 秒，听所有输入端口（Ctrl+C 可提前停）

结束时打一份汇总：哪个端口真的有数据、收到多少条、音域范围、跑了多久。
"""
import sys
from collections import Counter

import winmidi


def main():
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 30.0
    ins, _outs = winmidi.list_devices()
    if not ins:
        print("没有 MIDI 输入设备 —— 键盘没插？")
        return 1

    if len(sys.argv) > 2:
        idxs = [int(x) for x in sys.argv[2].split(",")]
    else:
        idxs = list(range(len(ins)))

    print("输入端口：")
    for i, n in enumerate(ins):
        print(f"  [{i}] {n}{'   <- 监听' if i in idxs else ''}")
    print(f"监听 {secs:.0f} 秒，实时输出（现在就可以弹）：\n", flush=True)

    stats = Counter()
    pitches = []
    t_last = [0.0]

    def show(rec):
        t, idx, st, d1, d2 = rec
        kind, ch, a, b, extra = winmidi.decode(st, d1, d2)
        stats[(idx, kind)] += 1
        if kind in ("NOTE_ON", "NOTE_OFF"):
            pitches.append(a)
        t_last[0] = t
        print(f"  [{t:7.3f}s] dev{idx} ch{ch:<2} {kind:<9} "
              f"d1={a:<4} d2={b:<4} {extra}", flush=True)

    try:
        recs = winmidi.listen(idxs, secs, on_message=show)
    except KeyboardInterrupt:
        print("\n(手动中断)", flush=True)
        recs = []

    print(f"\n=== 汇总 ===")
    print(f"共 {len(recs)} 条消息")
    if not recs:
        print("一条都没收到 —— 是没弹，还是端口选错了？")
        return 2

    by_dev = Counter(r[1] for r in recs)
    print("按端口：")
    for i, n in enumerate(ins):
        if by_dev.get(i):
            print(f"  [{i}] {n} —— {by_dev[i]} 条  <= 有数据")

    print("按类型：")
    for (idx, kind), c in stats.most_common():
        print(f"  dev{idx} {kind:<10} {c} 条")

    if pitches:
        print(f"音域：{winmidi.note_name(min(pitches))} ~ "
              f"{winmidi.note_name(max(pitches))}"
              f"（{len(set(pitches))} 个不同音高）")
        print(f"最后一条消息在 {t_last[0]:.3f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
