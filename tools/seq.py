"""seq: 读写机架里序列器的音符 —— 像人在 piano-roll 上点格子那样改

用户需求：「或者在序列器Sequencer 上编写（鼠标点击）……你不需要模拟人类
操作，但是你也需要进行这些行为，而不是遇到问题就去找代码，然后去重新生成。」

## 两种序列器，结构完全不同 —— 本文件同时支持

**rcm-pianoroll**（Cardinal 原生）
    data.patterns[i].measures[j].notes[]    ← 定长数组，下标即位置
    note = {pitch, velocity, retrigger, active}   ← 四字段全必写
    ⚠️ 内存里叫 steps[]（PatternData.hpp:59），但序列化成 JSON 时 key 是
       `notes`（PatternData.cpp:235）。别按 steps 找。
    ⚠️ **没有 length、没有 step 字段** —— 时值靠「相邻同 pitch 的 active 格串起来」
       （PianoRollModule.cpp:367 adjustVelocity 按组找）。改音高会切断延音。
    每小节格数 = beatsPerMeasure × divisionsPerBeat（PatternData.cpp:60），
    **不是固定 16** —— 3/4 拍是 12 格。
    休止符 = {"pitch":0,"velocity":0.0,"retrigger":false,"active":false}
    判定只看 active（isStepActive），pitch=0 纯占位。

**Starsea-MiniArranger**
    data.arranger.tracks[i].notes[]         ← 稀疏数组，按 step 定位
    track = {label, mute, measures, notes}
    note = {step, length, pitch, velocity}
    时值靠 length（单位=格）。**不用填空格**。
    ⚠️ **休止符约定不成立** —— 稀疏数组，「没有音符」就是休止。
      给它写 pitch=0 会被 clampValues 夹成 12（真实最低音）。
    轨道数固定 4（MA_TRACKS），上限 64 小节 / length 1..16 / pitch 12..108。

## 两条铁律
1. **写入前必须自检**：长度是否等于 beatsPerMeasure×divisionsPerBeat
   （rcm），pitch/length 是否越界（Starsea）。
2. **不静默失败**：改不动就说清为什么，别假装成功。
"""

from __future__ import annotations

import os
from typing import Any

import patchio

PATCH_DIR = os.environ.get("CARDINAL_PATCH_DIR") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "patches"
)

#: 支持的序列器：model 名 → 结构类型
KINDS = {
    "rcm-pianoroll": "rcm",
    "Pianoroll": "rcm",
    "Starsea-MiniArranger": "starsea",
    "MiniArranger": "starsea",
}

VOCT_BASE = {"rcm": -4.0, "starsea": -5.0}  # (pitch/12 - base)
#: 音高名（人看着比 MIDI 号强）
NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def note_name(pitch: int) -> str:
    return f"{NOTE_NAMES[pitch % 12]}{pitch // 12 - 1}"


def _resolve(name: str) -> str | None:
    if not name:
        return None
    if os.path.isfile(name):
        return name
    p = os.path.join(PATCH_DIR, name)
    for cand in (p, p + ".vcv" if not name.endswith(".vcv") else p):
        if os.path.isfile(cand):
            return cand
    return None


def _find_seq_modules(patch: dict[str, Any]) -> list[tuple[dict, str]]:
    """找出机架里所有带音符的模块 → [(模块, 结构类型)]"""
    out = []
    for m in patch.get("modules") or []:
        kind = KINDS.get(m.get("model", ""))
        if kind and m.get("data"):
            out.append((m, kind))
    return out


# ================================================================ 读取

def read_notes(patch_name: str, module: str | None = None,
               pattern: int = 0, track: int = 0) -> dict[str, Any]:
    """读出机架里的音符（用音乐记谱法展示，不是裸 MIDI 号）。"""
    path = _resolve(patch_name)
    out: dict[str, Any] = {"patch": patch_name, "module": module}
    if not path:
        out["error"] = f"找不到机架 {patch_name}"
        out["patch_dir"] = PATCH_DIR
        return out

    try:
        d = patchio.read_patch(path)
    except Exception as e:  # noqa: BLE001
        out["error"] = f"解析失败：{e}"
        return out

    seqs = _find_seq_modules(d)
    if not seqs:
        out["error"] = "这份机架里没有带音符的序列器模块"
        out["available_models"] = sorted(KINDS)
        out["modules_in_patch"] = [
            f"{m.get('plugin')}|{m.get('model')}"
            for m in (d.get("modules") or [])
        ][:40]
        return out

    targets = [s for s in seqs if not module or module.lower() in s[0].get("model", "").lower()
               or module.lower() in f"{s[0].get('plugin')}|{s[0].get('model')}".lower()]
    if not targets:
        out["error"] = f"机架里没有名为 {module} 的序列器"
        out["found"] = [f"{m.get('plugin')}|{m.get('model')}" for m, _ in seqs]
        return out

    out["source"] = "vcv_file"
    out["module_count"] = len(targets)
    out["sequences"] = [_read_one(m, kind, pattern, track) for m, kind in targets]
    out["note"] = (
        "读的是磁盘文件。Cardinal 开着且你手改过未保存的话看不到 —— "
        "保存后，或编译后用 /param-get 读运行中状态。"
    )
    return out


def _read_one(m: dict[str, Any], kind: str, pattern: int, track: int) -> dict[str, Any]:
    data = m.get("data") or {}
    base = {
        "module": f"{m.get('plugin')}|{m.get('model')}",
        "module_id": m.get("id"),
        "kind": kind,
    }
    if kind == "rcm":
        pats = data.get("patterns") or []
        base["pattern_count"] = len(pats)
        base["current_pattern"] = data.get("currentPattern")
        base["sequence_running"] = data.get("sequenceRunning")
        if pattern >= len(pats):
            base["error"] = f"pattern {pattern} 不存在（共 {len(pats)} 个）"
            return base
        p = pats[pattern]
        bpm_ = p.get("beatsPerMeasure", 4)
        dpb = p.get("divisionsPerBeat", 4)
        spm = bpm_ * dpb
        base.update({
            "beats_per_measure": bpm_,
            "divisions_per_beat": dpb,
            "steps_per_measure": spm,
            "number_of_measures": p.get("numberOfMeasures"),
            "current_step": data.get("currentStep"),
        })
        grid = []
        for mi, meas in enumerate(p.get("measures") or []):
            notes = meas.get("notes") or []
            if len(notes) != spm:
                base.setdefault("warnings", []).append(
                    f"小节 {mi} 有 {len(notes)} 个格子，应为 {spm}"
                    f"（{bpm_}拍 × {dpb}分音符）—— 长度不对引擎会错位"
                )
            row = []
            for si, n in enumerate(notes):
                act = bool(n.get("active"))
                row.append(
                    {
                        "step": si,
                        "pitch": n.get("pitch"),
                        "note": note_name(n.get("pitch", 0)) if act else None,
                        "velocity": round(n.get("velocity", 0.0), 3),
                        "retrigger": bool(n.get("retrigger")),
                        "active": act,
                    }
                )
            grid.append(row)
        base["grid"] = grid
        base["grid_note"] = "每行一小节，每格一格；active=false 是休止格（不要省）。"

    else:  # starsea
        arr = data.get("arranger") or {}
        tracks = arr.get("tracks") or []
        base.update({
            "running": data.get("running"),
            "current_step": data.get("currentStep"),
            "steps_per_quarter": arr.get("stepsPerQuarter", 4.0),
            "edit_track": arr.get("editTrack"),
            "track_count": len(tracks),
        })
        base["tracks"] = []
        for ti, t in enumerate(tracks):
            ns = t.get("notes") or []
            base["tracks"].append(
                {
                    "track": ti,
                    "label": t.get("label", ""),
                    "mute": bool(t.get("mute")),
                    "measures": t.get("measures"),
                    "note_count": len(ns),
                    "notes": [
                        {
                            "step": n.get("step"),
                            "measure": (n.get("step", 0) // (int(t.get("measures") or 4) * 16)),
                            "length": n.get("length"),
                            "pitch": n.get("pitch"),
                            "note": note_name(n.get("pitch", 60)),
                            "velocity": round(n.get("velocity", 0.5), 3),
                        }
                        for n in sorted(ns, key=lambda x: x.get("step", 0))
                    ],
                }
            )
        base["grid_note"] = (
            "稀疏数组：只列实际存在的音符。没有音符就是休止，不用填占位。"
            "length 单位是格，会跨格延音。"
        )
    return base


# ================================================================ 写入

def edit_note(
    patch_name: str,
    module: str,
    measure: int,
    step: int,
    pitch: int | None = None,
    length: int | None = None,
    velocity: float | None = None,
    retrigger: bool | None = None,
    active: bool | None = None,
    pattern: int = 0,
    track: int = 0,
    clear: bool = False,
    backup: bool = True,
    load_after: bool = False,
) -> dict[str, Any]:
    """改一个音符 —— 相当于人在 piano-roll 上点一格。

    rcm-pianoroll：measure+step 定位，改字段即改。
    Starsea：按 step 找（跨 measure 的全局步号），length 改了会截断重叠音符。
    clear=True  且 pitch 给 None ⇒ 删掉这个音符（rcm 写成休止格）。
    """
    path = _resolve(patch_name)
    out: dict[str, Any] = {"patch": patch_name, "module": module,
                           "target": {"measure": measure, "step": step}}
    if not path:
        out["error"] = f"找不到机架 {patch_name}"
        return out

    try:
        d = patchio.read_patch(path)
    except Exception as e:  # noqa: BLE001
        out["error"] = f"解析失败：{e}"
        return out

    seqs = _find_seq_modules(d)
    targets = [s for s in seqs if module.lower() in s[0].get("model", "").lower()
               or module.lower() in f"{s[0].get('plugin')}|{s[0].get('model')}".lower()]
    if not targets:
        out["error"] = f"机架里没有名为 {module} 的序列器"
        out["found"] = [f"{m.get('plugin')}|{m.get('model')}" for m, _ in seqs]
        return out
    m, kind = targets[0]
    data = m["data"]

    if kind == "rcm":
        r = _edit_rcm(data, measure, step, pitch, velocity, retrigger, active,
                      clear, pattern)
    else:
        r = _edit_starsea(data, track, measure, step, pitch, length,
                          velocity, clear)

    if not r.get("ok"):
        out.update(r)
        return out

    if backup:
        import shutil

        bak = path + ".bak-seq"
        shutil.copy2(path, bak)
        out["backup"] = bak
        out["backup_note"] = "⚠️ Cardinal 若开着，之后在它里 Ctrl+S 会覆盖这次改动。"

    try:
        patchio.write_patch(path, d)
    except Exception as e:  # noqa: BLE001
        out["error"] = f"写盘失败（已备份，可回滚）：{e}"
        return out
    out.update(r)
    out["written"] = path
    out["note"] = (
        "文件已改。若 Cardinal 开着，要看到效果需重新加载"
        "（load_patch 会中断音频，先确认）。"
    )
    if load_after:
        import cardinal_mcp as cm

        out["loaded"] = cm.load_patch(os.path.basename(path))
    return out


def _edit_rcm(data, measure, step, pitch, velocity, retrigger, active,
              clear, pattern) -> dict[str, Any]:
    pats = data.get("patterns") or []
    if pattern >= len(pats):
        return {"ok": False, "error": f"pattern {pattern} 不存在（共 {len(pats)}）"}
    p = pats[pattern]
    spm = p.get("beatsPerMeasure", 4) * p.get("divisionsPerBeat", 4)
    measures = p.get("measures") or []
    if measure >= len(measures):
        return {"ok": False,
                "error": f"小节 {measure} 不存在（共 {len(measures)} 小节）",
                "number_of_measures": p.get("numberOfMeasures")}
    notes = measures[measure].setdefault("notes", [])
    if len(notes) != spm:
        return {"ok": False,
                "error": f"小节 {measure} 长度是 {len(notes)}，应为 {spm}"
                         f"（{p.get('beatsPerMeasure',4)}拍 × {p.get('divisionsPerBeat',4)}分音符）。"
                         f"结构不对，先别改 —— 硬写会导致音符错位。",
                "refuse": "length_mismatch"}
    if step >= spm or step < 0:
        return {"ok": False, "error": f"step {step} 超出小节范围 0..{spm - 1}"}

    before = dict(notes[step]) if notes[step] else {}
    n = notes[step]
    if clear and pitch is None:
        n["pitch"] = 0
        n["velocity"] = 0.0
        n["retrigger"] = False
        n["active"] = False
    else:
        if pitch is not None:
            n["pitch"] = int(pitch)
        if velocity is not None:
            n["velocity"] = float(velocity)
        if retrigger is not None:
            n["retrigger"] = bool(retrigger)
        if active is not None:
            n["active"] = bool(active)
        else:
            n.setdefault("active", True)
            if not n.get("active"):
                n["active"] = bool(n.get("pitch", 0) > 0)
        # 四字段全必写（PatternData.cpp:214-241 dataToJson 会逐字段输出）
        for k, dv in (("pitch", 0), ("velocity", 0.0), ("retrigger", False), ("active", False)):
            n.setdefault(k, dv)

    after = dict(n)
    warns = []
    # ⚠️ rcm **不做 pitch clamp**（不同于 Starsea 的 clampValues 12..108）。
    # 引擎侧有 quantizePitch（PianoRollModule.cpp:131）会把音高量化到有效范围，
    # 所以越界不会崩，但**存进去的值和实际听到的可能不是一回事** ⇒ 必须警告。
    if after.get("pitch", 0) > 127 or after.get("pitch", 0) < 0:
        warns.append(
            f"pitch={after['pitch']} 超出 MIDI 0..127。rcm 不做 clamp，"
            f"引擎只在播放时量化（PianoRollModule.cpp:131 quantizePitch），"
            f"所以不会崩，但存的值和听到的音可能不一致。"
        )
    if before.get("pitch") is not None and after.get("pitch") != before.get("pitch"):
        nxt = notes[step + 1] if step + 1 < len(notes) else None
        if nxt and nxt.get("active") and nxt.get("pitch") == before.get("pitch"):
            warns.append(
                "下一格是同音高的延音格，现在音高改了会把延音切断"
                "（rcm 的时值靠相邻同 pitch 格串联，没有 length 字段）。"
                f"需要的话请把第 {step+1} 格的 pitch 也改成 {after['pitch']}。"
            )
    return {
        "ok": True, "kind": "rcm", "pattern": pattern,
        "before": {**before, "note": note_name(before.get("pitch", 0)) if before.get("active") else None},
        "after": {**after, "note": note_name(after.get("pitch", 0)) if after.get("active") else None},
        "warnings": warns,
    }


def _edit_starsea(data, track, measure, step, pitch, length, velocity, clear) -> dict[str, Any]:
    arr = data.setdefault("arranger", {})
    tracks = arr.setdefault("tracks", [])
    if track >= len(tracks):
        return {"ok": False, "error": f"轨道 {track} 不存在（共 {len(tracks)} 轨）"}
    t = tracks[track]
    notes = t.setdefault("notes", [])
    # ⚠️ Starsea 的每小节格数：源码 songSteps()/soundingAt() 按
    #    MA_STEPS_PER_MEASURE 推算（ArrangerData.hpp:78），每轨 measures 可不同。
    #    实测轨0 measures=8、64 个音符、step 间隔 2 ⇒ 每小节 16 格（4/4 × 4分音符）。
    #    这里与真实数据对齐；万一引擎改了会退化为 16 并在 notes 里注明。
    measures = int(t.get("measures") or 4)
    spm = int(t.get("stepsPerMeasure") or 16)
    global_step = measure * spm + step
    if global_step >= measures * spm:
        return {"ok": False,
                "error": f"小节 {measure} 第 {step} 格超出该轨范围"
                         f"（共 {measures} 小节 × {spm} 格）",
                "refuse": "out_of_song"}

    # ⚠️ 必须拿列表里的**真实引用**，不能用 dict(n) 造副本 ——
    #    改副本不写回列表，随后 append 会变成「同一个 step 有两条音符」。
    #    10-19 实测踩过：原始 1 条 → 改完变 2 条，且重叠警告把自己报成冲突。
    #    报告用的快照另取 snapshot = dict(before)。
    before = next((n for n in notes if n.get("step") == global_step), None)
    snapshot = dict(before) if before is not None else None

    if clear or (pitch is None and length is None and velocity is None):
        # Starsea 有正规删法：删掉所有覆盖该 step 的音符（ArrangerData.hpp:148-176）
        removed = [n for n in notes
                   if n.get("step") <= global_step < n.get("step", 0) + max(1, n.get("length", 1))]
        for n in removed:
            notes.remove(n)
        return {"ok": True, "kind": "starsea", "track": track,
                "removed": removed, "action": "cleared"}

    if before is None:
        # 新建并挂进列表（此处 before 是新对象，引用唯一）
        before = {"step": global_step, "length": 1, "pitch": 60, "velocity": 0.5}
        notes.append(before)
        snapshot = dict(before)
    else:
        snapshot = dict(before)
    if pitch is not None:
        if not (12 <= int(pitch) <= 108):
            return {"ok": False,
                    "error": f"pitch {pitch} 越界，Starsea 会 clamp 到 12..108",
                    "refuse": "pitch_out_of_range"}
        before["pitch"] = int(pitch)
    if length is not None:
        if not (1 <= int(length) <= 16):
            return {"ok": False,
                    "error": f"length {length} 越界，Starsea 会 clamp 到 1..16",
                    "refuse": "length_out_of_range"}
        before["length"] = int(length)
    if velocity is not None:
        before["velocity"] = float(velocity)

    warns = []
    end = before["step"] + before.get("length", 1)
    # ⚠️ 必须按身份排除自己（`n is not before`），不能只比字段 ——
    #    否则 pitch 改完后自己的旧字段与新字段不匹配，会把自己报成冲突。
    clashes = [n for n in notes if n is not before
               and n.get("step", -1) < end and before["step"] < n.get("step", 0) + max(1, n.get("length", 1))]
    if clashes:
        warns.append(
            f"与 {len(clashes)} 个音符时间重叠（长音符会跨格延音）："
            + ", ".join(f"step{n.get('step')} pitch{n.get('pitch')} len{n.get('length')}" for n in clashes[:4])
            + "。Starsea 里重叠的音符会同时发声，确认这是你要的。"
        )
    return {
        "ok": True, "kind": "starsea", "track": track,
        "before": {**snapshot, "note": note_name(snapshot.get("pitch", 60))},
        "after": {**before, "note": note_name(before.get("pitch", 60))},
        "warnings": warns,
    }


def set_running(patch_name: str, module: str, running: bool,
                pattern: int = 0, track: int = 0, load_after: bool = False) -> dict[str, Any]:
    """让序列器跑起来 / 停下来（对应人按 RUN 按钮）。"""
    path = _resolve(patch_name)
    out: dict[str, Any] = {"patch": patch_name, "module": module, "running": running}
    if not path:
        out["error"] = f"找不到机架 {patch_name}"
        return out
    try:
        d = patchio.read_patch(path)
    except Exception as e:  # noqa: BLE001
        out["error"] = f"解析失败：{e}"
        return out

    seqs = _find_seq_modules(d)
    targets = [s for s in seqs if module.lower() in s[0].get("model", "").lower()
               or module.lower() in f"{s[0].get('plugin')}|{s[0].get('model')}".lower()]
    if not targets:
        out["error"] = f"机架里没有 {module}"
        out["found"] = [f"{m.get('plugin')}|{m.get('model')}" for m, _ in seqs]
        return out

    m, kind = targets[0]
    data = m["data"]
    key = "sequenceRunning" if kind == "rcm" else "running"
    before = data.get(key)
    data[key] = bool(running)
    if kind == "rcm":
        data["currentPattern"] = pattern
    else:
        data.setdefault("arranger", {})["editTrack"] = track

    import shutil

    bak = path + ".bak-seq"
    shutil.copy2(path, bak)
    try:
        patchio.write_patch(path, d)
    except Exception as e:  # noqa: BLE001
        out["error"] = f"写盘失败（已备份）：{e}"
        return out
    out.update({"ok": True, "field": key, "before": before, "after": bool(running),
                "backup": bak, "written": path})
    if load_after:
        import cardinal_mcp as cm

        out["loaded"] = cm.load_patch(os.path.basename(path))
    return out


# ================================================================ 自检

if __name__ == "__main__":
    import json
    import sys

    cmd = sys.argv[1] if len(sys.argv) > 1 else "read"
    if cmd == "read":
        print(json.dumps(read_notes(sys.argv[2]), ensure_ascii=False, indent=2)[:3000])
    else:
        print(json.dumps(edit_note(sys.argv[2], sys.argv[3], int(sys.argv[4]), int(sys.argv[5]),
                                   pitch=int(sys.argv[6]) if len(sys.argv) > 6 else None),
                         ensure_ascii=False, indent=2))