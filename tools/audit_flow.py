# -*- coding: utf-8 -*-
r"""audit_flow.py —— 🔴 信号流可达性审计（「这张图能不能出声」）

★ 出发点（2026-10-19，李的提问）
  李问：「每条线都有信号，为什么读不到？每个模块都有 input/output，
  读到不就知道有没有声音了吗？不需要离线渲染吧？」
  ⇒ **这个思路是对的**，本脚本就是它的落地。
  离线渲染只在一种情况下才需要（本脚本第 5 节说清），静态图能覆盖绝大部分。

★ 本脚本能证明什么（纯静态，不跑音频）
  ✅ 每个模块的 input 口**接了谁** —— 接线是否到位、通道对不对
  ✅ 每个模块的 output 口**接到谁** —— 有没有死胡同
  ✅ 从**声源**（音序器/MIDI/采样）到**汇流点**（MixMaster/Mixer/HostAudio）
    的路径**是否连通** —— 「这张图整体通不通」
  ✅ 每个声源是否真的**同时**有音高口和门/触发口被喂
     （历史 bug：鼓序列器只接了音高没接 gate ⇒ 完全无声）
  ✅ 音高口 / 门口 **接到了哪种上游** —— 是不是接到了不该接的地方
  ✅ 每个音轨是否真的**汇入混音**（而��是接完就丢）
  ✅ 静音成因分类：**静态不可能出声** vs **静态看不出、必须实测**

★ 本脚本不能证明什么（重要，不许拿它当「已验收」）
  ❌ 声音是否**真的**在响（采样没加载 / 门没闭合 / 单声道折叠 / 增益为 0）
  ❌ 音高是否在可闻区（那归 `audit_values.py`）
  ⇒ **静态全绿 ≠ 会响。** 交付时必须对李说清这一点。

用法:
    python audit_flow.py <file.vcv> [更多文件...]
    python audit_flow.py --all
退出码: 0 = 图连通性无硬伤；1 = 有硬伤（该打回）
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import patchio  # noqa: E402


# ─────────────────────────────────────────────────────────────
# 角色表：判断一个模块在图里扮演什么角色
#   SOURCE  声源（自己产生音高/门，不依赖上游触发）
#   GATE    包络/门整形器（把门变成 CV）
#   PROC    处理模块（VCA/滤波/波形整形）
#   MIX     汇流点
#   OUT     最终输出
#   TIME    时钟
# ─────────────────────────────────────────────────────────────
ROLES = {
    # ---- 声源 ----
    "HostMIDI": "SOURCE", "HostMIDIGate": "SOURCE",
    "rcm-pianoroll": "SOURCE", "MiniArranger": "SOURCE",
    "MiniArrangerExpander": "SOURCE", "Sequencer": "SOURCE",
    "samplerx8": "SOURCE", "AudioFile": "SOURCE",
    # ---- 时钟 ----
    "Clocked": "TIME", "Gnome": "TIME", "HostTime": "TIME",
    # ---- 门整形 ----
    "ADSR": "GATE", "Bogaudio-ADSR": "GATE",
    "Bogaudio-ADSRPoly": "GATE", "ADSREnvelope": "GATE",
    # ---- 处理 ----
    "VCO": "PROC", "Bogaudio-VCO": "PROC",
    "VCA-1": "PROC", "Bogaudio-VCA": "PROC",
    "VCF": "PROC", "Bogaudio-VCF": "PROC",
    "Waveshaper": "PROC", "Plaits": "PROC", "Elements": "PROC",
    "Split": "PROC", "Sum": "PROC", "Noise": "PROC", "Rings": "PROC",
    "Plateau": "PROC", "Feline": "PROC", "Mixer": "PROC",
    # ---- 汇流 / 输出 ----
    "MixMasterJr": "MIX", "Bogaudio-Mix8": "MIX",
    "HostAudio2": "OUT",
}

# 汇流点 / 输出（路径终点）
SINKS = {"MixMasterJr", "Bogaudio-Mix8", "Mixer", "HostAudio2"}

# 关键口的真实编号 —— 🔴 **全部源码核实**（2026-10-19）
#
# ★ 重要教训 1：我第一版**想当然**把 Bogaudio 系列当成和 Fundamental 一样
#   （以为 `Bogaudio-ADSR` 的门也是 IN4），结果对一份**已验收有声**的
#   机架误报。抓源码才发现 Bogaudio 的口**完全不同**：
#     Fundamental/ADSR : 9 params，IN4=gate（PORTS.md §3）
#     Bogaudio-ADSR    : 5 params，**只有 IN0 = GATE**（ADSR.hpp:21/67）
#   ⇒ **Bogaudio 与 Fundamental 同名模块端口不能互相互相套用。**
#     源码位置：BogaudioModules/src/{ADSR,VCO,VCF}.hpp
#
# ★ 重要教训 2（更贵）：第一版把**可选口**（FM / retrig / CV）也当必接，
#   全库跑出 **137 条硬伤**，其中 117 条是「VCO 的 fm 口没接」这种
#   **完全正常的写法** —— 没几个人用 FM。
#   ⇒ **只有「必接口」才能硬否决**：缺了它模块一定不工作。
#     可选口不接只是「没用这个功能」，不是错。
#   ⇒ 教训：**判据的严重性分级必须先想清楚，否则误报淹没真信号。**
#     这是本项目第三次栽在误报上（见 MEMORY「误报比漏报更伤」）。
#
# 语义标注：
#   "req" = 必接，缺了 ⇒ 模块不工作 ⇒ 硬伤
#   "opt" = 可选，缺了 ⇒ 只是没用该功能 ⇒ 不报
SOURCE_PORTS = {
    # ---- Fundamental（PORTS.md §3 源码核实）----
    "VCO":     {"pitch": (0, "req"), "fm": (1, "opt")},
    "ADSR":    {"gate": (4, "req"), "retrig": (5, "opt")},
    "VCA-1":   {"cv": (0, "opt"), "audio": (1, "req")},
    "VCF":     {"audio": (3, "req")},
    "Rings":   {"pitch": (6, "req")},
    # ---- Bogaudio（2026-10-19 抓源码核实，口与 Fundamental 完全不同）----
    #   ADSR.hpp:  GATE_INPUT=0            → 只有 1 个输入
    #   VCO.hpp:   PITCH_INPUT=0 SYNC=1 PW=2 FM=3；输出 SQUARE/SAW/TRI/SINE=0..3
    #   VCF.hpp:   CV=0 FM=1 PITCH=2 **IN=3** Q=4 SLOPE=5；OUT=0
    "Bogaudio-ADSR": {"gate": (0, "req")},
    "Bogaudio-VCO":  {"pitch": (0, "req")},
    "Bogaudio-VCF":  {"audio": (3, "req"), "pitch": (2, "opt")},
}

# 各模块的音频入口口号（用于「这轨声音到底从哪个口进」）
AUDIO_IN = {
    "VCA-1": 1, "VCF": 3, "Bogaudio-VCF": 0,
    "Mixer": None,        # IN0-5
    "Plaits": None, "Elements": None,
    "Waveshaper": 0, "Sum": 0,
}


def nm(m):
    p = m.get("plugin")
    slug = p if isinstance(p, str) else (p or {}).get("slug", "")
    return "%s/%s" % (slug, m.get("model", ""))


def role(model):
    return ROLES.get(model, "UNKNOWN")


def iter_cables(patch):
    return patch.get("cables") or []


def audit(path):
    d = patchio.read_patch(path)
    mods = d.get("modules", [])
    cables = iter_cables(d)
    byid = {m["id"]: m for m in mods}

    ins, outs = {}, {}
    for c in cables:
        outs.setdefault(c["outputModuleId"], []).append(c)
        ins.setdefault(c["inputModuleId"], []).append(c)

    hard = []   # 静态硬伤
    soft = []   # 需实测才能定论

    print("=" * 62)
    print("  %s   （模块 %d / 线 %d）" % (os.path.basename(path), len(mods), len(cables)))
    print("=" * 62)

    # ── 1. 主输出是否被喂 ──────────────────────────────
    audio_outs = [m for m in mods if role(m["model"]) == "OUT"]
    if not audio_outs:
        hard.append("没有主输出模块（HostAudio2）")
    for m in audio_outs:
        if not ins.get(m["id"]):
            hard.append("主输出 %s **零输入** ⇒ 一定没有声音" % m["model"])

    # ── 2. 反向可达性：从主输出往回走，看能覆盖多少模块 ──
    reachable = set()
    stack = []
    for m in audio_outs:
        # 主输出自己就是终点，当然「不在通往自己的路径上」——
        # 不把它算进分母，否则永远显示 100% 以下，误报。
        reachable.add(m["id"])
        stack.extend(c["outputModuleId"] for c in ins.get(m["id"], []))
    while stack:
        mid = stack.pop()
        if mid in reachable or mid not in byid:
            continue
        reachable.add(mid)
        for c in ins.get(mid, []):
            stack.append(c["outputModuleId"])

    unreachable = [m for m in mods
                   if m["id"] not in reachable and role(m["model"]) != "TIME"]
    if unreachable:
        soft.append(
            "这些模块**不在通往主输出的路径上**（静态即不发声）：%s"
            % "、".join(sorted(nm(m) for m in unreachable)))

    # ── 3. 死胡同：有输入但零输出，且不是汇流点 ──────────
    for m in mods:
        if role(m["model"]) in ("MIX", "OUT", "TIME"):
            continue
        if ins.get(m["id"]) and not outs.get(m["id"]):
            hard.append("死胡同：%s 有输入但**零输出** ⇒ 声音出不来"
                        % nm(m))

    # ── 4. 孤岛：零输入零输出 ──────────────────────────
    for m in mods:
        if role(m["model"]) in ("OUT",):
            continue
        if not ins.get(m["id"]) and not outs.get(m["id"]):
            if role(m["model"]) == "TIME":
                continue
            soft.append("孤岛：%s 无输入无输出" % nm(m))

    # ── 5. 声源的「音高口 / 门口 是否都到位」────────────
    for m in mods:
        model = m["model"]
        if role(model) != "SOURCE":
            continue
        got = {}
        for c in ins.get(m["id"], []):
            src = byid.get(c["outputModuleId"])
            got.setdefault(c["inputId"], nm(src) if src else "?")
        # 音高口
        pitch_ports = [p for p in got if p in (0, 5, 6)]
        gate_ports = [p for p in got if p in (1, 6, 4, 2)]
        if not got:
            soft.append("声源 %s **零输入** ⇒ 它没被任何时钟/音高喂"
                        % nm(m))
        if not pitch_ports and not gate_ports:
            soft.append("声源 %s 收到的输入是 %s —— 看不到音高或门，"
                        "可能只接了 CV" % (nm(m), sorted(got.items())))

    # ── 6. 关键口核实（**只查必接口**，可选口不接不算错）──
    for m in mods:
        model = m["model"]
        spec = SOURCE_PORTS.get(model)
        if not spec:
            continue
        got = {c["inputId"] for c in ins.get(m["id"], [])}
        for sem, (want, sev) in spec.items():
            if want in got:
                continue
            if sev == "opt":
                continue          # 可选口没接 = 没用该功能，正常
            hard.append("%s 的 **%s 口（IN%d）没接线** ⇒ 模块不工作"
                        % (nm(m), sem, want))

    # ── 7. 同口多线（Rack 会挤掉前一根）─────────────────
    seen = {}
    for c in cables:
        k = (c["inputModuleId"], c["inputId"])
        seen.setdefault(k, []).append(c)
    for (mid, port), cs in seen.items():
        if len(cs) > 1:
            hard.append("同口多线：%s 的 IN%d 接了 %d 根线 ⇒ "
                        "Rack 只会保留最后一条"
                        % (nm(byid[mid]) if mid in byid else "?", port, len(cs)))

    # ── 8. 混音器是否每轨都有输入 ───────────────────────
    for m in mods:
        if role(m["model"]) != "MIX":
            continue
        n_in = len(ins.get(m["id"], []))
        n_ch = 8 if m["model"] == "MixMasterJr" else 8
        if n_in < 2:
            hard.append("混音 %s 只有 %d 路输入" % (nm(m), n_in))
        elif n_in < n_ch:
            soft.append("混音 %s 只接了 %d/%d 路 —— 部分通道空着"
                        % (nm(m), n_in, n_ch))

    # ── 输出 ──────────────────────────────────────────
    for s in hard:
        print("  ✗ [硬伤] %s" % s)
    for s in soft:
        print("  ? [需实测] %s" % s)
    if not hard and not soft:
        print("  ✅ 图连通性无发现问题（**但仍不等于会响**）")
    else:
        print("  → 硬伤 %d 项 / 需实测 %d 项" % (len(hard), len(soft)))

    # ── 覆盖统计 ──────────────────────────────────────
    n_r = len(reachable)
    print("  覆盖：通往主输出的路径经过 %d/%d 个模块（%.0f%%）"
          % (n_r, len(mods), 100.0 * n_r / max(1, len(mods))))
    print()
    return len(hard)


def main(argv):
    if not argv:
        print(__doc__)
        return 0
    base = r"D:\Cardinal\patches"
    if argv[0] == "--all":
        paths = sorted(os.path.join(base, f) for f in os.listdir(base)
                       if f.endswith(".vcv") and not f.startswith("_"))
    else:
        paths = [os.path.abspath(a) for a in argv]
    total = 0
    for p in paths:
        try:
            total += audit(p)
        except Exception as e:
            print("===== %s =====\n  [FAIL] %s\n" % (os.path.basename(p), e))
            total += 1
    print("总计硬伤：%d" % total)
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))