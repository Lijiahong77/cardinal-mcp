#!/usr/bin/env python3
"""把 winmidi_live.py 的输出日志解析成「音符事件表」。

用途：企划 3（跟弹判定）与编曲模块的公共数据地基 ——
     把「什么时候、哪个音、多响、多长」变成结构化数据。

用法：
    midi_events.py <日志文件> [--dev N] [--ch N] [--json 输出路径]

⚠️ SMK-25 的 dev0 / dev1 完全镜像（同一动作各发一条）。
   必须用 --dev 只取一个端口，否则每个音符会被记两遍。
"""
import argparse
import json
import re
import sys
from collections import Counter, defaultdict

LINE_RE = re.compile(
    r"^\s*\[\s*([\d.]+)s\]\s+dev(\d+)\s+ch(\d+)\s+([A-Z_]+)\s+"
    r"d1=(\d+)\s+d2=(\d+)"
)

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def note_name(n):
    return f"{NOTE_NAMES[n % 12]}{n // 12 - 1}"


def parse(path):
    """返回 [(t, dev, ch, kind, d1, d2), ...]"""
    events = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            m = LINE_RE.match(line)
            if m:
                t, dev, ch, kind, d1, d2 = m.groups()
                events.append((float(t), int(dev), int(ch), kind,
                               int(d1), int(d2)))
    return events


def pair_notes(events):
    """把 Note on/off 配对成音符。

    返回 (notes, dangling)，notes 元素为
    {start, end, dur, pitch, name, vel, ch, dev}
    """
    open_notes = defaultdict(list)   # (ch, pitch) -> [音符 dict]
    notes = []
    unmatched_off = 0

    for t, dev, ch, kind, d1, d2 in events:
        key = (ch, d1)
        if kind == "NOTE_ON" and d2 > 0:
            open_notes[key].append(
                {"start": t, "pitch": d1, "name": note_name(d1),
                 "vel": d2, "ch": ch, "dev": dev})
        elif kind == "NOTE_OFF" or (kind == "NOTE_ON" and d2 == 0):
            if open_notes[key]:
                n = open_notes[key].pop(0)
                n["end"] = t
                n["dur"] = round(t - n["start"], 4)
                notes.append(n)
            else:
                unmatched_off += 1

    dangling = [n for lst in open_notes.values() for n in lst]
    for n in dangling:
        n["end"] = None
        n["dur"] = None

    notes.sort(key=lambda n: n["start"])
    return notes, dangling, unmatched_off


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("logfile")
    ap.add_argument("--dev", type=int, default=0,
                    help="只取这个端口（默认 0；-1 = 全部，会有镜像重复）")
    ap.add_argument("--ch", type=int, default=None, help="只看某个通道")
    ap.add_argument("--json", default=None, help="把音符表写成 JSON")
    args = ap.parse_args()

    events = parse(args.logfile)
    if not events:
        print("没解析到任何消息 —— 日志格式对不上？")
        return 1

    raw = len(events)
    if args.dev >= 0:
        events = [e for e in events if e[1] == args.dev]
    if args.ch is not None:
        events = [e for e in events if e[2] == args.ch]

    print(f"解析 {raw} 行，过滤后 {len(events)} 条"
          f"（dev={args.dev}，ch={args.ch}）")

    by_ch = Counter(e[2] for e in events)
    print("按通道：" + "  ".join(f"ch{c}:{n}" for c, n in sorted(by_ch.items())))

    notes, dangling, unmatched = pair_notes(events)
    if not notes:
        print("没有配对出音符")
        return 2

    total = notes[-1]["end"] - notes[0]["start"]
    pitches = [n["pitch"] for n in notes]
    vels = [n["vel"] for n in notes]
    durs = [n["dur"] for n in notes]

    print(f"\n=== 音符事件表（{len(notes)} 个音符）===")
    print(f"时间跨度 {total:.2f}s   音域 {note_name(min(pitches))} ~ "
          f"{note_name(max(pitches))}（{len(set(pitches))} 个不同音高）")
    print(f"力度 {min(vels)} ~ {max(vels)}（均值 {sum(vels) / len(vels):.1f}）")
    print(f"时值 {min(durs):.3f}s ~ {max(durs):.3f}s"
          f"（均值 {sum(durs) / len(durs):.3f}s）")
    if dangling:
        print(f"⚠️  {len(dangling)} 个音符没等到 Note Off（悬空）")
    if unmatched:
        print(f"⚠️  {unmatched} 个 Note Off 没有对应的 On（孤儿）")

    # 估算节奏：音符起始间隔的中位数
    gaps = [notes[i + 1]["start"] - notes[i]["start"]
            for i in range(len(notes) - 1)]
    if gaps:
        gaps_sorted = sorted(gaps)
        med = gaps_sorted[len(gaps_sorted) // 2]
        if med > 0:
            print(f"起始间隔中位数 {med * 1000:.0f} ms → 约 "
                  f"{60 / med:.0f} BPM（四分音符计）")

    print("\n  起始     时长    音高      力度  通道")
    for n in notes[:40]:
        print(f"  {n['start']:7.3f}s {n['dur']:6.3f}s  "
              f"{n['name']:<4} (midi {n['pitch']:<3}) {n['vel']:>3}  ch{n['ch']}")
    if len(notes) > 40:
        print(f"  ... 其余 {len(notes) - 40} 个略")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({
                "source": args.logfile,
                "device_port": args.dev,
                "note_count": len(notes),
                "span_seconds": round(total, 3),
                "notes": notes,
                "dangling": dangling,
            }, f, ensure_ascii=False, indent=1)
        print(f"\n已写出 {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
