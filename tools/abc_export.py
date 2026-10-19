# -*- coding: utf-8 -*-
"""
abc_export.py — 把机架里的序列器音符导出成 .abc 纯文本乐谱（批次 A10）。

格式裁决（李 10-19 授权）：选 .abc —— 纯文本、能直接读改 diff，符合
「在软件里看和改」原则；EasyABC / abcjs 可直接渲染成五线谱。

数据来源：`seq.read_notes`（rcm = 稠密网格 active/retrigger；
starsea = 稀疏 notes 带 step/length）。本模块只做序列化，不重复解析 .vcv。

映射规则：
  * 音高：VCV C4=60 ↔ ABC 的 'C'（中音区）。高八度加 ' ，低八度加 , ，升音加 ^。
  * rcm：每小节 spm 格 → L:1/spm；连续 active 且 retrigger=False 的同音格
    合并为一个长音（legato），retrigger=True 断开成新音；休止格合并成 z。
  * starsea：音长 = length（格）→ L:1/<stepsPerQuarter> 的倍数；空档补休止；
    每轨一个 ABC 声部（V:1 / V:2 …）。
"""
import os
from typing import Any

import seq  # noqa: E402  (同目录；音符读取与音名转换都在那)

_SHARP_TO_ABC = {
    "C": "C", "C#": "^C", "D": "D", "D#": "^D", "E": "E", "F": "F",
    "F#": "^F", "G": "G", "G#": "^G", "A": "A", "A#": "^A", "B": "B",
}


def _abc_pitch(pitch: int) -> str:
    """MIDI 号 → ABC 音名。C4(60)='C'，C5(72)="C'"，C3(48)="C,"。"""
    name = seq.note_name(int(pitch))          # 如 "C#4"
    letter, octave = name[:-1], int(name[-1])
    token = _SHARP_TO_ABC[letter]
    if octave >= 4:
        return token + "'" * (octave - 4)
    return token + "," * (4 - octave)


def _dur(d: int) -> str:
    """ABC 时值后缀：1 倍省略，其余写倍数。"""
    return "" if d == 1 else str(int(d))


def _grid_to_body(grid: list[list[dict[str, Any]]]) -> tuple[str, int]:
    """rcm 稠密网格 → 单声部旋律。返回 (body, spm)。"""
    spm = max(1, len(grid[0])) if grid else 16
    tokens: list[str] = []
    for row in grid:
        i = 0
        while i < len(row):
            n = row[i]
            if not n["active"]:
                j = i
                while j < len(row) and not row[j]["active"]:
                    j += 1
                tokens.append("z" + _dur(j - i))
                i = j
                continue
            pitch = n["pitch"]
            length = 1
            j = i + 1
            # 后续格 active、非 retrigger、同音高 → 延音并入同一音符
            while (j < len(row) and row[j]["active"]
                   and not row[j]["retrigger"]
                   and row[j]["pitch"] == pitch):
                length += 1
                j += 1
            tokens.append(_abc_pitch(pitch) + _dur(length))
            i = j
        tokens.append("|")
    body = f"L:1/{spm}\n" + " ".join(t for t in tokens if t)
    return body, spm


def _tracks_to_body(tracks: list[dict[str, Any]], spq: float) -> tuple[str, int]:
    """starsea 稀疏音符 → 多声部。返回 (body, unit)。

    unit = 每个四分音符的步数（L:1/unit，音符倍数 = length 步）。
    """
    unit = int(spq) if float(spq).is_integer() else 4
    lines = [f"L:1/{unit}"]
    for t in tracks:
        label = t.get("label") or f"track{t['track'] + 1}"
        mute = " (mute)" if t.get("mute") else ""
        lines.append(f"V:{t['track'] + 1} {label}{mute}")
        toks: list[str] = []
        cursor = 0
        for n in sorted(t.get("notes") or [], key=lambda x: x.get("step", 0)):
            step = int(n.get("step") or 0)
            length = max(1, int(n.get("length") or 1))
            gap = step - cursor
            if gap > 0:
                toks.append("z" + _dur(gap))
            toks.append(_abc_pitch(int(n.get("pitch", 60))) + _dur(length))
            cursor = step + length
        toks.append("|")
        lines.append(" ".join(toks))
    return "\n".join(lines), unit


def export_abc(
    patch_name: str,
    module: str | None = None,
    pattern: int = 0,
    track: int = 0,
    out_path: str | None = None,
    bpm: int = 120,
) -> dict[str, Any]:
    """机架序列器音符 → .abc 文本乐谱。

    out_path 缺省写到机架同目录同名 .abc。
    返回 {"ok", "out", "abc"(全文), "stats", ...}。
    """
    r = seq.read_notes(patch_name, module, pattern, track)
    if r.get("error"):
        return {"error": r["error"], "detail": r}

    tunes: list[str] = []
    stats: list[dict[str, Any]] = []
    for s in r["sequences"]:
        if s.get("error"):
            stats.append({"module": s.get("module"), "error": s["error"]})
            continue
        title = f"{r['patch']} -- {s['module']} (id {s.get('module_id')})"
        if s["kind"] == "rcm":
            body, unit = _grid_to_body(s.get("grid") or [])
            bpm_pm = int(s.get("beats_per_measure", 4))
            dpb = int(s.get("divisions_per_beat", 4))
            meter = f"{bpm_pm}/{dpb}"
            n_notes = sum(1 for row in s.get("grid") or []
                          for c in row if c.get("active"))
        else:
            body, unit = _tracks_to_body(s.get("tracks") or [],
                                         float(s.get("steps_per_quarter", 4.0)))
            meter = "4/4"  # starsea 无 per-pattern 拍号，按 4/4 约定
            n_notes = sum(len(t.get("notes") or [])
                          for t in s.get("tracks") or [])
        head = "\n".join([
            "X:1",
            f"T:{title}",
            f"M:{meter}",
            f"Q:1/4={bpm}",
            "K:C",
        ])
        tunes.append(head + "\n" + body)
        stats.append({"module": s["module"], "kind": s["kind"],
                      "meter": meter, "notes": n_notes})

    if not tunes:
        return {"error": "没有可导出的序列器内容", "stats": stats}

    abc_text = "\n\n".join(tunes) + "\n"
    if not out_path:
        base = seq._resolve(patch_name) or patch_name
        out_path = os.path.splitext(str(base))[0] + ".abc"
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(abc_text)
    return {
        "ok": True,
        "out": out_path,
        "tune_count": len(tunes),
        "stats": stats,
        "abc": abc_text,
        "how_to_edit": (
            ".abc 是纯文本：改音名/时值数字即可改谱（^C, = 低两个八度的升C）。"
            "EasyABC / abcjs 可渲染五线谱；要改回机架用 seq.edit_note。"
        ),
    }
