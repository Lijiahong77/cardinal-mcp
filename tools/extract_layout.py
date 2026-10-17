# -*- coding: utf-8 -*-
"""extract_layout.py —— 把李手工调好的机架布局抽成生成器的坐标基准。

★ 为什么不按 x 排序编号
  李把 decor 链从第三行 [4,2] 挪到了第一行 [60,1]（插在 lead 和其它链中间）。
  如果按 pos[0] 排序编号，decor 会被排成「第 3 个」，与生成顺序（pad/bass/lead/decor）
  对不上 ⇒ 坐标张冠李戴。
  ⇒ 本脚本**按角色**认模块：从 Mixer 的输入口反查 VCA ← ADSR ← 音色 ← pianoroll，
      Mixer 的第 i 路就对应 keys[i]（pad/bass/lead/decor）。

输出 tools/LAYOUT.json，键名形如：
    clock / host / mixer / reverb
    pr.pad / voice.pad / adsr.pad / vca.pad
    ...同理 bass / lead / decor
"""
import collections
import json
import os

import patchio

BASE = r"D:\Cardinal\patches\quadeca_auto_ghostfolk.vcv"
OUT = r"D:\Cardinal\tools\LAYOUT.json"

KEYS = ["pad", "bass", "lead", "decor"]


def main():
    p = patchio.read_patch(BASE)
    mods = {m["id"]: m for m in p["modules"]}
    cables = p["cables"]

    # 从某模块的某个输入口反查「谁接在上面」
    src = {}
    for c in cables:
        src.setdefault((c["inputModuleId"], c["inputId"]), []).append(
            (c["outputModuleId"], c["outputId"]))

    out = {}

    def out_id(m, port=0):
        return src.get((m["id"], port), [None])[0]

    # --- 找到 Mixer（唯一）---
    mixer = next(m for m in p["modules"] if m["model"] == "Mixer")
    host = next(m for m in p["modules"] if m["model"] == "HostAudio2")
    clock = next(m for m in p["modules"] if m["model"] == "Clocked")
    out["mixer"] = list(mixer["pos"])
    out["host"] = list(host["pos"])
    out["clock"] = list(clock["pos"])

    # 混响：Plateau（若有），它的输入接的是哪一层
    rev = None
    for m in p["modules"]:
        if m["model"] == "Plateau":
            rev = m
    if rev is not None:
        out["reverb"] = list(rev["pos"])

    # --- 从 Mixer 各输入口逐层回溯 ---
    for i in range(6):
        got = src.get((mixer["id"], i), [])
        if not got:
            break
        vca = mods.get(got[0][0])
        if vca is None or vca["model"] != "VCA-1":
            break
        # 回声支路（Plateau 在混音链里，不属于任何一层）会被上面 model 检查挡掉
        if i >= len(KEYS):
            break
        key = KEYS[i]

        adsr = mods.get(out_id(vca, 0)[0])          # VCA.IN0 = 音量包络 ← ADSR.OUT0
        voice = mods.get(out_id(vca, 1)[0])         # VCA.IN1 = 音频 ← 音色.OUT0
        pr = None
        if voice is not None:
            pitch_in = 0 if voice["model"] == "VCO" else 6
            g = out_id(voice, pitch_in)
            pr = mods.get(g[0]) if g else None

        if adsr is None or voice is None or pr is None:
            print("  ⚠ 第 %d 路（%s）回溯不全，跳过" % (i, key))
            continue

        out["pr." + key] = list(pr["pos"])
        out["voice." + key] = list(voice["pos"])
        out["adsr." + key] = list(adsr["pos"])
        out["vca." + key] = list(vca["pos"])

    # 没接上的层（3 层机架）也允许缺键，生成器会回退默认值

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    print("已提取 %d 个坐标 -> %s\n来源: %s\n" % (len(out), OUT, BASE))
    for k in sorted(out):
        print("   %-14s %s" % (k, out[k]))


if __name__ == "__main__":
    main()