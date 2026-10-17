# -*- coding: utf-8 -*-
r"""make_probe_sy.py —— 排除法探针：GrainEngineMK2 到底出不出声？

★ 为什么不用「改一版试一版」：每次猜错都要李重启（MEMORY 铁律）。
  这次做**一次装三组对照**，只变一个变量，李按一次 RUN 就能判断：

  组A「裸引擎」：Clocked → GrainEngine（**不接时钟，用内部 RATE 自跑**）
      测：模块自己能不能出声音（采样加载成功？颗粒逻辑正常？）
      ★ 源码：`if (inputs[SPAWN_TRIGGER_INPUT].isConnected()) {...} else if
        (spawn_throttling_countdown == 0) { addGrain(...) }`
        —— 不接外部触发时走**内部速率**，这条最可靠。

  组B「CV 音高」：A + 接一个 1V 恒定 CV（VCO 方波 0V 当 CV 源）
      测：PITCH 输入接了会不会反而没声（排除 PITCH 接线问题）

  组C「全链路」：pianoroll(PITCH+GATE) → GrainEngine
      测：外部触发 + CV 是否工作（= 正式机架的接法）

★ 三组共用同一个采样文件与同一套 layout 坐标逻辑。
"""
import copy
import datetime
import os
import sys

sys.path.insert(0, r"D:\Cardinal\tools")
import patchio
import audit_ports
from make_quadeca_auto import sanitize
from make_scrapyard import (make_grain, clone_mod, FRAG, GRAINS,
                            set_pr, build_pattern, MELODY)

GHOST = r"D:\Cardinal\patches\quadeca_auto_ghostfolk__v1328.vcv"
BPM = 120.0
SAMPLE = os.path.join(FRAG, GRAINS[0])      # heli_03.wav


def main():
    ghost = patchio.read_patch(GHOST)
    mods, cables = [], []
    cid = [9900000000001000]

    def cab(a, ao, b, bi, color=""):
        cid[0] += 1
        cables.append({"id": cid[0], "outputModuleId": a, "outputId": ao,
                       "inputModuleId": b, "inputId": bi, "color": color})

    def new_clock(nid, x):
        c = clone_mod(ghost, "Clocked", nid, [x, 0])
        c["params"] = [dict(q, value=BPM) if q["id"] == 0 else q
                       for q in c.get("params", [])]
        c["data"]["running"] = not True      # 静止，由李点 RUN
        mods.append(c)
        return c

    # ---- 组A：裸引擎（内部 RATE 自跑，不接任何输入）----
    ca = new_clock(9900000000000001, -30)
    ga = make_grain(9900000000000101, [4, 1],
                    [SAMPLE] * 5,          # 5 个槽都放同一文件，排除选槽问题
                    window=0.30, trim=1.0, jitter=0.0, grains=0.8, rate=0.25)
    mods.append(ga)

    # ---- 组B：A + PITCH 接 1V（用 rcm-pianoroll 的 VOCT 恒定输出最稳）----
    cb = new_clock(9900000000000002, 60)
    # 用 Clocked 自己的 GATE? 不行。改用 pianoroll 常驻高音符 → VOCT 恒定 1V
    pb = clone_mod(ghost, "rcm-pianoroll", 9900000000000201, [60, 0])
    # 每格都放 C5 ⇒ 音高恒定；只在第1 格给 gate
    pat = {"numberOfMeasures": 1, "beatsPerMeasure": 4, "divisionsPerBeat": 4,
           "measures": [{"notes": [
               dict(pitch=72, velocity=0.9, retrigger=True, active=True),
           ] + [dict(pitch=0, velocity=0.0, retrigger=False, active=False)
                for _ in range(15)]}]}
    set_pr(pb, pat, lowest=64, show=12)
    gb = make_grain(9900000000000102, [64, 1], [SAMPLE] * 5,
                    window=0.30, trim=1.0, jitter=0.0, grains=0.8, rate=0.5)
    mods += [pb, gb]
    cab(cb["id"], 0, pb["id"], 0)
    cab(pb["id"], 5, gb["id"], 3)      # VOCT → PITCH_INPUT
    cab(pb["id"], 6, gb["id"], 4)      # GATE → SPAWN_TRIGGER

    # ---- 组C：完整旋律链（VOCT + GATE 都接，内部 RATE 也开）----
    cc = new_clock(9900000000000003, 120)
    pc = clone_mod(ghost, "rcm-pianoroll", 9900000000000202, [120, 0])
    set_pr(pc, build_pattern(MELODY), lowest=57, show=24)
    gc = make_grain(9900000000000103, [124, 1], [SAMPLE] * 5,
                    window=0.30, trim=1.0, jitter=0.0, grains=0.8, rate=0.5)
    mods += [pc, gc]
    cab(cc["id"], 0, pc["id"], 0)
    cab(pc["id"], 5, gc["id"], 3)
    cab(pc["id"], 6, gc["id"], 4)

    # ---- 三路各自直出 HostAudio2，方便单独听 ----
    ha = []
    for i, g in enumerate([ga, gb, gc]):
        h = clone_mod(ghost, "HostAudio2", 9900000000002000 + i, [4 + i * 56, 4])
        mods.append(h)
        ha.append(h)
    cab(ga["id"], 0, ha[0]["id"], 0)
    cab(gb["id"], 0, ha[1]["id"], 0)
    cab(gc["id"], 0, ha[2]["id"], 0)

    p = {"version": "2.4.1", "zoom": 0.5, "gridOffset": [0, 0],
         "modules": mods, "cables": cables}
    ver = datetime.datetime.now().strftime("%H%M")
    out = r"D:\Cardinal\patches\probe_sy__v%s.vcv" % ver
    sanitize(p, out)
    patchio.write_patch(out, p)

    print("生成 %s：模块 %d / 连线 %d"
          % (os.path.basename(out), len(mods), len(cables)))
    print("采样文件:", SAMPLE,
          "存在" if os.path.exists(SAMPLE) else "❌ 不存在")
    print()
    print("★ 李按 RUN 后请分别听三个 HostAudio2：")
    print("  A（x=-30 组的引擎，最左）裸引擎·内部RATE自跑 → 采样加载成功吗")
    print("  B（中）VOCT+GATE → PITCH·内部 RATE 也开")
    print("  C（右）VOCT+GATE → PITCH·正式旋律")
    print()
    for m in q_modules(out):
        if m["model"] == "GrainEngineMK2":
            v = {x["id"]: x["value"] for x in m["params"]}
            print("   GrainEngine id=%d pos=%s WINDOW=%.2f TRIM=%.2f "
                  "GRAINS=%.2f RATE=%.2f 槽=%d"
                  % (m["id"], m["pos"], v[0], v[5], v[7], v[9], len(m["data"])))
    bad = audit_ports.audit(out, verbose=True)
    print("端口越界自检:", "全部通过" if not bad else "❌ %d 处" % len(bad))
    return out


def q_modules(path):
    return patchio.read_patch(path)["modules"]


if __name__ == "__main__":
    main()
