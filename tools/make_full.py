#!/usr/bin/env python3
"""把 SMK25 的全部控件一次接进 Cardinal —— 生成 helm_full.vcv。

在李的现役机架（键盘复音合成器 + 8 旋钮映射 + MixMasterJr）基础上追加：

  · Cardinal/HostMIDIGate   鼓垫 Note 48-55 → 门信号（18 门输出，音符写在 data.notes）
  · 6 个 WSTD-Drums 鼓机    8 个鼓声部（每模块 2 声部，各自可选采样）
  · 2 个 Fundamental/Mixer  8 路鼓声混成 2 条总线 → 汇入 MixMasterJr 轨道 2 / 轨道 3
  · HostMIDI.data 调整      inputChannel=1（只收 ch1 琴键，鼓垫不再误触发合成器）
                            pwRange=2（弯音范围 ±2 半音）
  · HostMIDIMap.data 扩充   保留 8 旋钮 + CC1（触控条上下）+ CC64（踏板）

为什么这么接线（源码核实结论，见 refs/drums_map.json 与 SKILL.md）：
  · WSTD-Drums 是「多声部鼓机」：第 i 声部触发口 = IN(16+i)，音频出 = OUT(i)
    （SampleController.hpp: GATE_INPUT=16, TUNE_CV=32；AUDIO_OUTPUT=0）
  · HostMIDIGate 的 notes 数组是 18 个整数，-1 = 未分配
  · Fundamental/Mixer 确认是 6 入 1 出、只有 1 个总音量参数（源码 Mixer.cpp）
  · ⚠️ Cardinal 同 VCV Rack：**一个输入口只能接一根线**，多接的被静默丢弃
    → 鼓总线必须进混音台的空闲轨道，绝不和合成器抢 HostAudio2 的输入口
    （2026-09-12 实测踩坑，详见 fix_drum_bus.py 头部注释）

用法:
  python make_full.py build  [--out helm_full.vcv] [--load]
  python make_full.py report <patch>
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import patchio                      # noqa: E402
import paramlib as pl               # noqa: E402
from make_knobs import (            # noqa: E402
    find_module, find_param_id, get_map_module, DEFAULT_MAP)

PATCH_DIR = r"D:\Cardinal\patches"
GATE_BASE = 16      # WSTD-Drums: 第 i 声部触发口 = IN(16+i)
AUDIO_BASE = 0      # WSTD-Drums: 第 i 声部音频出 = OUT(i)

# 鼓垫分配：(按键序号, MIDI 音符, 鼓模块 model, 声部号, 人话)
# SMK25 实测：8 个鼓垫 = Note 48~55，分散在 ch2~ch8 / ch10
PAD_MAP = [
    (1, 48, "BassDrum9",  0, "底鼓 A"),
    (2, 49, "BassDrum9",  1, "底鼓 B"),
    (3, 50, "SnareDrumN", 0, "军鼓 A"),
    (4, 51, "SnareDrumN", 1, "军鼓 B"),
    (5, 52, "ClosedHiHat", 0, "闭镲"),
    (6, 53, "OpenHiHat",  0, "开镲"),
    (7, 54, "Tomi",       0, "嗵鼓"),
    (8, 55, "DMX",        0, "DMX 打击"),
]

# 除 8 旋钮外的额外 CC 映射：(CC, 模块, 参数名关键字, 人话)
EXTRA_CC = [
    (1,  "Plateau", "Size",    "触控条上下滑 → 混响空间大小"),
    (64, "ADSR",    "Sustain", "踩踏板 → 持音（松踏板恢复）"),
]

DRUM_VOL = 0.35     # 鼓总线音量（李嫌吵过，给保守值）


def get_module(patch, model):
    """按 model 名取模块记录（注意 make_knobs.find_module 返回的是 id，不是记录）。"""
    for m in patch.get("modules", []):
        if m.get("model") == model:
            return m
    return None


def free_id_factory(used):
    box = {"n": 100}

    def nxt():
        while box["n"] in used:
            box["n"] += 1
        used.add(box["n"])
        return box["n"]
    return nxt


def build(out_name="helm_full.vcv", load=False):
    import cardinal_mcp as cm

    live, _base = cm.live_patch_path()
    if not live:
        return {"error": "找不到 Cardinal 实时存档 —— Cardinal 没在运行？"}
    d = patchio.read_patch(live)
    mods = d.setdefault("modules", [])
    cables = d.setdefault("cables", [])

    if not find_module(d, "HostMIDI"):
        return {"error": "当前机架里没有 HostMIDI 模块，先加载 helm_knobs.vcv"}
    if not find_module(d, "HostAudio2"):
        return {"error": "当前机架里没有 HostAudio2 模块"}

    # ---- 0. 先备份活机架（李的手工改动不能丢）----
    bak = os.path.join(PATCH_DIR, "helm_before_full.vcv")
    keep = {k: d[k] for k in ("version", "zoom", "modules", "cables") if k in d}
    if "path" in d:
        keep["path"] = d["path"]
    patchio.write_patch(bak, keep)

    used = {m["id"] for m in mods}
    new_id = free_id_factory(used)
    maxy = max((m.get("pos") or [0, 0])[1] for m in mods)
    rowy = maxy + 80
    log = []

    # ---- 1. HostMIDI：只收 ch1（琴键），鼓垫交给 HostMIDIGate ----
    hm = get_module(d, "HostMIDI")
    hm.setdefault("data", {})
    hm["data"]["inputChannel"] = 1        # 1 = ch1；0 = OMNI
    hm["data"]["pwRange"] = 2.0           # 弯音范围 ±2 半音
    log.append("HostMIDI: inputChannel → 1（只收 ch1 = 琴键，鼓垫不再弹响合成器）")
    log.append("HostMIDI: pwRange → 2.0（触控条弯音 ±2 半音）")

    # ---- 2. 鼓垫 → 门信号 ----
    gate = next((m for m in mods if m.get("model") == "HostMIDIGate"), None)
    if gate is None:
        notes = [-1] * 18
        for i, (_pad, note, _m, _v, _d) in enumerate(PAD_MAP):
            notes[i] = note
        gate = {
            "id": new_id(), "plugin": "Cardinal", "model": "HostMIDIGate",
            "version": "2.0.0", "params": [],
            "data": {"notes": notes, "velocity": False, "mpeMode": False,
                     "inputChannel": 0, "outputChannel": 0},
            "pos": [0, rowy],
        }
        mods.append(gate)
        log.append(f"新增 HostMIDIGate id={gate['id']}：OUT0-7 = Note 48-55 的门信号")
    else:
        gate.setdefault("data", {})["notes"] = (
            [PAD_MAP[i][1] if i < 8 else -1 for i in range(18)])
        gate["data"]["inputChannel"] = 0
        log.append(f"复用已有 HostMIDIGate id={gate['id']}，重写 notes")

    # ---- 3. 鼓机（按 model 去重，每个模块可挂 2 个声部）----
    drum_mods = {}
    x = 300
    for _pad, _note, model, _voice, _desc in PAD_MAP:
        if model in drum_mods:
            continue
        m = {
            "id": new_id(), "plugin": "WSTD-Drums", "model": model,
            "version": "2.0.0", "params": [], "pos": [x, rowy],
        }
        mods.append(m)
        drum_mods[model] = m
        x += 60
        log.append(f"新增鼓机 {model} id={m['id']}（触发口 IN16/IN17，音频出 OUT0/OUT1）")

    # 鼓垫 OUT i -> 第 voice 声部触发口
    for i, (pad, note, model, voice, desc) in enumerate(PAD_MAP):
        cables.append({"outputModuleId": gate["id"], "outputId": i,
                       "inputModuleId": drum_mods[model]["id"],
                       "inputId": GATE_BASE + voice})
        log.append(f"  接线 垫{pad}(Note{note}) → {model} 声部{voice} IN{GATE_BASE + voice}  [{desc}]")

    # ---- 4. 8 路鼓声 → 2 个 6 路混音器 → MixMasterJr 轨道 2 / 轨道 3 ----
    mixers = []
    for k in range(2):
        m = {
            "id": new_id(), "plugin": "Fundamental", "model": "Mixer",
            "version": "2.1.0", "params": [{"id": 0, "value": DRUM_VOL}],
            "data": {"average": False, "invert": False}, "pos": [x + k * 60, rowy],
        }
        mods.append(m)
        mixers.append(m)

    audio = [(drum_mods[mm]["id"], AUDIO_BASE + vv, pp)
             for (pp, _n, mm, vv, _d) in PAD_MAP]
    for idx, (mid, out, pad) in enumerate(audio):
        bus = mixers[0] if idx < 6 else mixers[1]
        tin = idx if idx < 6 else idx - 6
        cables.append({"outputModuleId": mid, "outputId": out,
                       "inputModuleId": bus["id"], "inputId": tin})

    # ⚠️ 鼓总线只能进「混音台的空闲轨道」，绝不能直接并到 HostAudio2 的输入口：
    # Cardinal 一个输入口只能被一根线占用，多接的被**静默丢弃**。
    # （2026-09-12 实测踩坑：鼓总线与合成器同抢 HostAudio2 IN0/IN1，
    #   结果合成器被保留、鼓被丢掉 → 鼓垫有 MIDI 反应但完全没声音）
    mmjr = find_module(d, "MixMasterJr")
    if mmjr is None:
        return {"error": "机架里没有 MixMasterJr，鼓总线无处安放（先让他在机架里加一个）"}
    # MixMasterJr = MixMaster<8,2>（MindMeldModular/MixMaster.cpp enum InputIds/OutputIds）：
    #   TRACK_SIGNAL_INPUTS 从 0 起、每轨 2 口 → Track1=IN0/1, Track2=IN2/3, Track3=IN4/5
    #   DIRECT_OUTPUTS 占 OUT0/OUT1 → 主输出 MAIN_OUTPUTS = OUT2/OUT3
    for k, mix in enumerate(mixers):
        base = 2 + k * 2                    # 第 1 条鼓总线 → Track2，第 2 条 → Track3
        for port in (base, base + 1):       # 鼓是单声道 → L/R 都接，居中
            cables.append({"outputModuleId": mix["id"], "outputId": 0,
                           "inputModuleId": mmjr["id"], "inputId": port})
    log.append(f"新增 2 个 Mixer id={mixers[0]['id']},{mixers[1]['id']}（音量 {DRUM_VOL}）"
               f"→ MixMasterJr(id={mmjr}) 轨道 2 / 轨道 3")

    # ---- 5. CC 映射：8 旋钮 + 触控条上下 + 踏板 ----
    mm = get_map_module(d)
    if mm is None:
        return {"error": "机架里没有 HostMIDIMap，先跑 make_knobs.py apply"}
    spec = list(DEFAULT_MAP) + list(EXTRA_CC)
    maps, report = [], []
    for row in spec:
        cc, model, pname = row[0], row[1], row[2]
        desc = row[3] if len(row) > 3 else ""
        mid = find_module(d, model)
        if mid is None:
            report.append(f"  [跳过] CC{cc}: 机架里没有 {model}")
            continue
        pid, real = find_param_id(model, pname)
        if pid is None:
            report.append(f"  [跳过] CC{cc}: {model} 里找不到「{pname}」")
            continue
        maps.append({"cc": int(cc), "moduleId": int(mid), "paramId": int(pid)})
        report.append(f"  [OK] CC{cc:<3} → {model:<10} param{pid:<3} {real:<24}{desc}")
    mm["data"] = {"maps": maps, "smooth": True, "channel": 0}
    log.append(f"HostMIDIMap: {len(maps)} 条映射（channel=0 全部通道，smooth 平滑）")

    # ---- 6. 落盘 ----
    out = os.path.join(PATCH_DIR, out_name)
    patchio.write_patch(out, {k: d[k] for k in ("version", "zoom", "modules", "cables")
                              if k in d})

    res = {"out": out, "backup": bak,
           "modules": len(mods), "cables": len(cables),
           "bytes": os.path.getsize(out), "log": log, "cc_report": report}

    # ---- 7. 校验 ----
    import validate
    res["validate"] = validate_check(out)

    if load:
        res["loaded"] = cm.load_patch(out)
    return res


def validate_check(path):
    """模块是否都存在 + 线缆两端 id 是否有效 + id 是否重复。"""
    import validate
    db = validate.build_db()
    d = patchio.read_patch(path)
    mods = d.get("modules", [])
    ids = [m["id"] for m in mods]
    problems = []
    for m in mods:
        key = (m["plugin"], m["model"])
        if key not in db:
            problems.append(f"未知模块 {key}")
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        problems.append(f"重复 id: {dup}")
    idset = set(ids)
    for c in d.get("cables", []):
        if c["outputModuleId"] not in idset or c["inputModuleId"] not in idset:
            problems.append(f"线缆端点无效: {c}")
    return {"ok": not problems, "problems": problems,
            "module_kinds": len(db)}


def report(path):
    d = patchio.read_patch(path)
    by = {m["id"]: m for m in d["modules"]}
    name = lambda i: f"{by[i]['model']}({i})" if i in by else f"<{i}?>"
    print(f"机架: {os.path.basename(path)}  模块 {len(d['modules'])}  线缆 {len(d['cables'])}")
    print("\n--- 键盘 → 机架 相关接线 ---")
    for c in d["cables"]:
        om, im = name(c["outputModuleId"]), name(c["inputModuleId"])
        if any(k in om + im for k in ("HostMIDIGate", "WSTD", "Mixer", "HostAudio")):
            print(f"  {om:<22}p{c['outputId']:<3} → {im:<22}p{c['inputId']}")
    mm = get_map_module(d)
    if mm:
        print(f"\n--- CC 映射（channel={mm['data'].get('channel')} "
              f"smooth={mm['data'].get('smooth')}）---")
        for e in mm["data"].get("maps", []):
            t = by.get(e["moduleId"], {})
            info = (pl.lookup(t.get("plugin", ""), t.get("model", "")) or {}) \
                .get("params", {}).get(str(e["paramId"]), {})
            print(f"  CC{e['cc']:<4}→ {t.get('model','?'):<12} "
                  f"param{e['paramId']:<3} {info.get('name')}")


if __name__ == "__main__":
    argv = sys.argv[1:]
    if not argv:
        print(__doc__)
        sys.exit(0)
    cmd = argv[0]
    flag = lambda k: k in argv
    val = lambda k, dflt: (argv[argv.index(k) + 1] if k in argv and len(argv) > argv.index(k) + 1 else dflt)
    if cmd == "build":
        r = build(val("--out", "helm_full.vcv"), flag("--load"))
        print(json.dumps(r, ensure_ascii=False, indent=2))
    elif cmd == "report":
        report(argv[1])
    else:
        print(__doc__)
