"""修复 helm_full.vcv 的鼓总线接线（2026-09-12）。

【问题】
鼓的两条总线（Fundamental/Mixer 各一路）和合成器（MixMasterJr 主输出）
都接到了 HostAudio2 的 IN0 / IN1。

但 Cardinal（同 VCV Rack）**一个输入口只能被一根线连接** ——
多接的那些线会被静默丢弃。于是：
  · IN0/IN1 保留了先出现的 MixMasterJr（合成器正常出声）
  · 鼓的两条总线被丢掉 → 鼓垫敲了有 MIDI、但声音根本到不了输出

【修法】
鼓总线改接 MixMasterJr 的**轨道 2 / 轨道 3**，由混音台统一汇到主输出。

MixMasterJr = MixMaster<8, 2>（8 轨 + 2 编组）。
端口定义见 MindMeldModular/MixMaster.cpp 的 enum InputIds / OutputIds：
  输入  TRACK_SIGNAL_INPUTS 从 0 起、每轨 2 口
        → Track1 = IN0/IN1、Track2 = IN2/IN3、Track3 = IN4/IN5 … Track8 = IN14/IN15
  输出  DIRECT_OUTPUTS 占 OUT0/OUT1（N_TRK/8+1 = 2 个）
        → 主输出 MAIN_OUTPUTS = OUT2/OUT3

用法:
  python fix_drum_bus.py                     # 修 helm_full.vcv（自动备份）
  python fix_drum_bus.py report <patch>      # 只检查输入口冲突
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import patchio                      # noqa: E402

PATCH_DIR = r"D:\Cardinal\patches"
DEFAULT_PATCH = os.path.join(PATCH_DIR, "helm_full.vcv")
BACKUP = os.path.join(PATCH_DIR, "helm_full_before_drumfix.vcv")

# MixMasterJr 端口（MixMaster<8,2>）
TRACK_IN_BASE = 2      # Track 2 的 L 口
TRACK_IN_STEP = 2      # 每轨 2 个口（L/R）


def sid(x):
    """模块 id 在 patch 里可能是 int 也可能是 str，统一成 str 比较。"""
    return str(x)


def find(mods, model, plugin=None):
    for m in mods:
        if m.get("model") == model and (plugin is None or m.get("plugin") == plugin):
            return m
    return None


def check_dupes(d):
    """列出所有被多根线占用的输入口。"""
    from collections import defaultdict
    ins = defaultdict(list)
    for c in d.get("cables", []):
        ins[(sid(c["inputModuleId"]), c["inputId"])].append(
            (sid(c["outputModuleId"]), c["outputId"]))
    return {k: v for k, v in ins.items() if len(v) > 1}


def report(patch_path):
    d = patchio.read_patch(patch_path)
    by = {sid(m["id"]): m for m in d["modules"]}
    dup = check_dupes(d)
    print(f"文件: {patch_path}")
    print(f"模块 {len(d['modules'])}  线缆 {len(d['cables'])}")
    print()
    if not dup:
        print("[OK] 没有输入口冲突")
        return
    print("[!!] 以下输入口被多根线占用（Cardinal 只会保留第一根）:")
    for (mid, port), srcs in sorted(dup.items(), key=lambda x: str(x[0])):
        name = by.get(mid, {}).get("model", mid)
        print(f"  {name}(id={mid}) IN{port} ← {len(srcs)} 根: {srcs}")


def fix(patch_path=DEFAULT_PATCH):
    d = patchio.read_patch(patch_path)
    mods = d.setdefault("modules", [])
    cables = d.setdefault("cables", [])

    mixers = [m for m in mods
              if m.get("model") == "Mixer" and m.get("plugin") == "Fundamental"]
    mmjr = find(mods, "MixMasterJr")
    ha = find(mods, "HostAudio2")

    if not mixers:
        return {"error": "机架里没有 Fundamental/Mixer（鼓总线）"}
    if mmjr is None:
        return {"error": "机架里没有 MixMasterJr，鼓总线无处安放"}
    if ha is None:
        return {"error": "机架里没有 HostAudio2"}

    # 按 id 排序，保证「Mixer1 → Track2、Mixer2 → Track3」稳定可复现
    mixers = sorted(mixers, key=lambda m: str(m["id"]))
    mix_ids = {sid(m["id"]) for m in mixers}
    ha_id = sid(ha["id"])

    # ---- 0. 备份（李的手工改动不能丢）----
    keep = {k: d[k] for k in ("version", "zoom", "modules", "cables") if k in d}
    if "path" in d:
        keep["path"] = d["path"]
    patchio.write_patch(BACKUP, keep)
    print(f"已备份 → {BACKUP}")

    # ---- 1. 删掉「鼓 Mixer → HostAudio2」的冲突线 ----
    before = len(cables)
    cables[:] = [
        c for c in cables
        if not (sid(c["outputModuleId"]) in mix_ids and sid(c["inputModuleId"]) == ha_id)
    ]
    removed = before - len(cables)
    print(f"[1] 删除冲突线 {removed} 根（鼓 → HostAudio2）")

    # ---- 2. 鼓总线 → MixMasterJr 轨道 2 / 轨道 3 ----
    added = 0
    for k, mix in enumerate(mixers):
        base = TRACK_IN_BASE + k * TRACK_IN_STEP
        for port in (base, base + 1):
            cables.append({
                "outputModuleId": mix["id"], "outputId": 0,
                "inputModuleId": mmjr["id"], "inputId": port,
            })
            added += 1
            print(f"[2] Mixer(id={mix['id']}) OUT0 → MixMasterJr IN{port}")
    print(f"    共新增 {added} 根")

    # ---- 3. 复检冲突 ----
    dup = check_dupes(d)
    if dup:
        return {"error": f"仍有输入口冲突: {dup}"}

    patchio.write_patch(patch_path, keep)
    print()
    print(f"[OK] 已写入 {patch_path}")
    print(f"     模块 {len(d['modules'])}  线缆 {len(d['cables'])}")
    return {"removed": removed, "added": added, "cables": len(d["cables"])}


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "report":
        report(args[1] if len(args) > 1 else DEFAULT_PATCH)
    else:
        res = fix()
        print()
        print("结果:", res)
