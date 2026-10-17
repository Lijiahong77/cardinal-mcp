# -*- coding: utf-8 -*-
"""端口越界审计器 —— Cardinal 机架加载前必跑。

★ 2026-10-17 立此工具的缘由：加载崩溃的真元凶是 **Mixer.OUT1**，
  而 Mixer 只有 OUT0 一个输出口（PORTS.md L194 + 13 份成功机架反推印证）。
  端口越界 ⇒ 加载即崩（GUI 消失 + OSC 失联），且**报错信息为空**，极难定位。

★ 上限表的来源（不要凭记忆改）：
  PORTS.md 明确记载的 优先；否则用 `tools/realports.py` 从
  「能正常加载的机架」反推，取���用到的最大编号作为上限。
  新增模块时务必先跑 realports.py 反推，再加进本表。
"""
import os
import sys

sys.path.insert(0, r"D:/Cardinal/tools")
import patchio

D = r"D:/Cardinal/patches"

# model -> (max_input_id, max_output_id)   None = 不限制
LIMITS = {
    # ---- Fundamental（PORTS.md §4 / PORTS.md L194）----
    "Mixer":        (5, 0),    # 6 路输入 IN0-5，只有 OUT0 ——★踩过这个坑
    "VCO":          (1, 3),    # IN0=音高 IN1=FM；**OUT0/1/2/3 四种波形**
                               # ★ 源码 Fundamental/src/VCO.cpp enum OutputIds:
                               #   SIN_OUTPUT=0 / TRI_OUTPUT=1 / SAW_OUTPUT=2 /
                               #   SQR_OUTPUT=3（波形是**输出口**，不是 param！）
                               #   ★ 我早期误记成「三种波形/OUT0-2」，导致审计
                               #     把合法的 OUT3（方波）误报越界。
    "ADSR":         (5, 0),    # IN4=gate IN5=retrig；OUT0=env
    "VCA-1":        (1, 0),    # IN0=CV IN1=audio（★顺序不是直觉那样）
    "VCF":          (3, 1),    # IN3=audio IN1=resCV；OUT0/1
    "Sum":          (0, 0),
    "Noise":        (None, 0),
    # ---- Cardinal 内建 ----
    "HostAudio2":   (1, 1),
    "HostMIDI":     (None, 7),  # OUT0=PITCH 1=GATE 2=VEL 6=RETRIG
    "HostTime":     (None, None),
    "HostMIDIMap":  (None, None),
    # ---- WSTD-Drums（通用公式：触发 IN(16+i)，音频 OUT(i)）----
    "BassDrum9":    (17, 1), "SnareDrumN": (17, 1), "ClosedHiHat": (16, 1),
    "OpenHiHat":    (16, 0), "Tomi": (16, 0),
    "Sequencer":    (5, 7),
    "Gnome":        (None, 6),
    "Clocked":      (None, 6),  # PORTS.md §2: OUT0主时钟 1/2/3子时钟 4=Reset 5=Run 6=BPM
    # ---- 其他（从成功机架反推）----
    "Rings":        (6, 0), "Plateau": (16, 1),   # PORTS.md §8: IN0/1=Left/Right, 2..16 是 CV/开关；OUT0/1
    "samplerx8":   (7, 17),   # OUT16/17 = 混音左右声道（PORTS.md §10 + 项目 memory）
    "rcm-pianoroll": (8, 7), "MixMaster": (13, 4), "MixMasterJr": (5, 3),
}


def audit(path, verbose=True):
    p = patchio.read_patch(path)
    by_id = {m["id"]: m.get("model") for m in p["modules"]}
    bad = []
    for c in p.get("cables", []):
        om = by_id.get(c["outputModuleId"])
        im = by_id.get(c["inputModuleId"])
        if om and om in LIMITS and LIMITS[om][1] is not None:
            if c["outputId"] > LIMITS[om][1]:
                bad.append("%s.OUT%d > 上限 %d" % (om, c["outputId"], LIMITS[om][1]))
        if im and im in LIMITS and LIMITS[im][0] is not None:
            if c["inputId"] > LIMITS[im][0]:
                bad.append("%s.IN%d > 上限 %d" % (im, c["inputId"], LIMITS[im][0]))
    if verbose:
        tag = "❌" if bad else "✅"
        print("%s %-30s %d 处越界" % (tag, os.path.basename(path), len(bad)))
        for b in sorted(set(bad)):
            print("      ", b)
    return bad


def main():
    names = sys.argv[1:]
    files = ([os.path.join(D, n) for n in names] if names else
             [os.path.join(D, f) for f in sorted(os.listdir(D)) if f.endswith(".vcv")])
    total = 0
    for f in files:
        total += len(audit(f))
    print("\n合计越界 %d 处" % total)
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
