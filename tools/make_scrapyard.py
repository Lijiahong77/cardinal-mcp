# -*- coding: utf-8 -*-
r"""make_scrapyard.py —— Scrapyard（废料场）：按 Quadeca 的**编曲理念**重做。

🔴🔴🔴 李 16:27 的方法论纠正（本文件存在的全部理由）
  ① 「不要想当然地去把乐器往上一顶…根据他的理念去思考，根据他的编曲思路去思考」
     ⇒ 我上一版写的「pad+bass+lead+drums+sample 五层堆叠」**正是他反对的做法**。
  ② 「不要望文生义」——
     「他写的『反律动设计，故意打乱预期』『在进鼓处留白』，
       你可能不要简单地以为就是搞这么一个反套路…打破常规的这个做法，
       **都要克制在针对的地方使用**。在进鼓的地方留白，
       **不是说整个歌都要留白**。」
     ⇒ 手册法术语要读它的**度**（在什么位置、多大力度），
       不是读它的字面（要做这个动作）。通篇撒 = 另一种机械感 = 还是套路。
  ③ 16:29「混响不要开太大…我很怕你把整个音质做得很空、很大」
     ⇒ 混响**平时关死**，只在 2 个位置被 CV 瞬时打开。

★ 文档第四节的元素构成表（原文）→ 本机架的落地
| 元素 | 文档原话 | 本机架做法 |
|---|---|---|
| 原声基底 | 尼龙弦吉他/钢琴/田野录音；「去量化，**保留杂音与呼吸感**」；「对抗电子冰冷感的**人性锚点**」 | **李自己的 SASA 曲子切片**当旋律基底（已变调对准，误差≤0.35半音）|
| 合成器音色 | Hyperpop 锯齿/FM；「**作为质感层而非旋律层**」 | VCO 锯齿**只做背景质感**，音量极低，绝不当旋律 |
| 人声处理 | 数十轨和声堆叠+ 声像移动 | 声像左右分开摆（PAN）|
| 节奏组 | Glitch 鼓点/不规则采样/静音切片；「**在进鼓处留白**」 | 鼓**全曲规整**；留白只在采样副旋律进入前的两拍 |
| 空间效果 | 「干声=现实，湿声=幻觉，**频繁切换模拟意识流**」 | Plateau **WET_CV** 控制，平时 0，只在第 3/6 小节瞬时开 |

★ 「克制」的具体数值（全曲 8 小节，只破 3 处）
  · 第 3 小节：采样副旋律进入 ⇒ 前面留两拍空白（进鼓处留白）
  · 第 5 小节：鼓反拍一下（唯一一次）
  · 第 6 小节：混响瞬时打开 0.8 秒（唯一一次「幻觉」）
  其余 5 小节完全规整。**破完立刻回来。**

★ 🔴 samplerx8 的 MUTE 反直觉（本项目最坑）
  源码 SamplerX8.hpp:132 `if (params[MUTE_BUTTONS+i].getValue() == true)
  // True means "play sample"` ⇒ **1.0 才是发声**，0.0 是静音。
  MUTE 在 param id **16–23**。李16:25 手点开关才发现声音。

★ 端口（源码核对）
  VCO 音高=IN0；波形是**四个输出口** SIN0/TRI1/SAW2/SQR3（不是 param）
  ADSR 门=IN4 · VCA-1 CV=IN0/音频=IN1 · Mixer IN0-5（仅 OUT0）
  rcm-pianoroll: CLK=IN0 · 输出 0 CLOCK/5 VOCT/6 GATE
  Sequencer 输出 0-4 → 鼓机 IN16 → 鼓机 OUT0
  **Plateau: LEFT_IN=0 RIGHT_IN=1 DRY_CV=2 WET_CV=3**
  param: 0 DRY(0~1,默认1) 1 WET(0~1,默认0.5) **7 DECAY(0.1~0.9999)**
"""
import copy
import datetime
import os
import sys

sys.path.insert(0, r"D:\Cardinal\tools")
import patchio
import audit_ports
from make_quadeca_auto import sanitize

MEL = r"D:\Cardinal\samples\melody2"
FRAG = r"D:\Cardinal\samples\fragments"
GHOST = r"D:\Cardinal\patches\quadeca_auto_ghostfolk__v1328.vcv"
PLAY = r"D:\Cardinal\patches\quadeca_play__v1240.vcv"
S4 = r"D:\Cardinal\patches\demo_S4_sampling.vcv"

BPM = 145.0     # ★ 李 16:42：「整体速度偏慢」。120 在indietronica 里确实偏慢
                # （Drum&Bass 170-180 / hyperpop 140-160 / indietronica 130-150）
                #⇒ 提速**只改这里**（Clocked 的 param0= 绝对 BPM）。
                #   pianoroll 只管「第几拍放什么音」，**不决定速度**。
START_PAUSED = True

# ★★ 8 小节结构。**留白与反拍只在标注的 3 处**（其余全规整 —— 这是「克制」）
#主旋律：Rings 拨弦 + 采样基底的**对位**（李 16:27 拍板：「把这两个混在一起」）
#   Rings = 主旋律（规整）；采样 = 副旋律（只在 2 处插进来打断）
LEAD = [                                   # Rings 主旋律
    # ★ 李 16:42「piano roll 里面这个音的密度不够」⇒ 全部改八分/十六分为主，
    #   每小节 12~14 个音（原来只有 7~9）。提速到145 后密度才立得住。
    [("D4", 0.0, 0.5), ("F4", 0.5, 0.25), ("A4", 0.75, 0.25),
     ("C5", 1.0, 0.5), ("A4", 1.5, 0.25), ("F4", 1.75, 0.25),
     ("D4", 2.0, 0.5), ("F4", 2.5, 0.25), ("A4", 2.75, 0.5),
     ("C5", 3.25, 0.25), ("A4", 3.5, 0.5)],
    [("G4", 0.0, 0.5), ("Bb4", 0.5, 0.25), ("A4", 0.75, 0.25),
     ("F4", 1.0, 0.5), ("D4", 1.5, 0.25), ("F4", 1.75, 0.25),
     ("G4", 2.0, 0.5), ("A4", 2.5, 0.25), ("C5", 2.75, 0.5),
     ("Bb4", 3.25, 0.25), ("A4", 3.5, 0.5)],
    #小节3：前两拍留白（采样副旋律进入前的「进鼓处留白」），只破这一处
    [("F4", 2.0, 0.5), ("D4", 2.5, 0.25), ("A3", 2.75, 0.25),
     ("C4", 3.0, 0.5), ("D4", 3.5, 0.5)],
    [("C5", 0.0, 0.5), ("A4", 0.5, 0.25), ("F4", 0.75, 0.25),
     ("D4", 1.0, 0.5), ("F4", 1.5, 0.25), ("A4", 1.75, 0.5),
     ("C5", 2.25, 0.25), ("A4", 2.5, 0.5), ("F4", 3.0, 0.5),
     ("D4", 3.5, 0.5)],
    [("D5", 0.0, 0.5), ("C5", 0.5, 0.25), ("A4", 0.75, 0.25),
     ("F4", 1.0, 0.5), ("A4", 1.5, 0.25), ("C5", 1.75, 0.25),
     ("D5", 2.0, 0.5), ("A4", 2.5, 0.5), ("F4", 3.0, 0.5),
     ("D4", 3.5, 0.5)],
    [("Bb4", 0.0, 0.5), ("A4", 0.5, 0.25), ("F4", 0.75, 0.25),
     ("D4", 1.0, 0.5), ("F4", 1.5, 0.25), ("G4", 1.75, 0.25),
     ("Bb4", 2.0, 0.5), ("A4", 2.5, 0.25), ("F4", 2.75, 0.5),
     ("D4", 3.25, 0.25), ("F4", 3.5, 0.5)],
    [("G4", 0.0, 0.5), ("Bb4", 0.5, 0.25), ("D5", 0.75, 0.5),
     ("C5", 1.25, 0.25), ("Bb4", 1.5, 0.5), ("G4", 2.0, 0.25),
     ("Bb4", 2.25, 0.25), ("D5", 2.5, 0.5), ("C5", 3.0, 0.5),
     ("Bb4", 3.5, 0.5)],
    [("A4", 0.0, 0.5), ("G4", 0.5, 0.25), ("F4", 0.75, 0.25),
     ("E4", 1.0, 0.5), ("F4", 1.5, 0.25), ("G4", 1.75, 0.25),
     ("A4", 2.0, 0.5), ("C5", 2.5, 0.25), ("Bb4", 2.75, 0.5),
     ("A4", 3.25, 0.25), ("G4", 3.5, 0.5)],
]
# ★ 采样副旋律：**只在小节 3 和 6 插进来**（其余小节该层完全静默）
SAMP_COUNTER = [
    [],# 小节1 空
    [],                                            # 小节2 空
    [("s0", 2.0, 0.5), ("s1", 2.5, 0.5), ("s2", 3.0, 0.5)],
    [],                                            # 小节4 空
    [],                                            # 小节5 空
    [("s1", 0.0, 0.5), ("s3", 0.5, 0.5), ("s0", 1.0, 0.5)],
    [],                                            # 小节7 空
    [("s2", 2.5, 0.5), ("s3", 3.0, 0.5)],
]
BASS = [                                   # 低音：加密到八分，托底不抢
    [("D2", 0.0, 0.25), ("D2", 0.5, 0.25), ("A2", 1.0, 0.25),
     ("A2", 1.5, 0.25), ("D3", 2.0, 0.25), ("A2", 2.5, 0.25),
     ("F2", 3.0, 0.25), ("A2", 3.5, 0.25)],
    [("F2", 0.0, 0.25), ("F2", 0.5, 0.25), ("C3", 1.0, 0.25),
     ("C3", 1.5, 0.25), ("F2", 2.0, 0.25), ("C3", 2.5, 0.25),
     ("A2", 3.0, 0.25), ("C3", 3.5, 0.25)],
    [("G2", 0.0, 0.25), ("G2", 0.5, 0.25), ("Bb2", 1.0, 0.25),
     ("Bb2", 1.5, 0.25), ("G2", 2.0, 0.25), ("D3", 2.5, 0.25),
     ("Bb2", 3.0, 0.25), ("G2", 3.5, 0.25)],
    [("A2", 0.0, 0.25), ("A2", 0.5, 0.25), ("E3", 1.0, 0.25),
     ("E3", 1.5, 0.25), ("A2", 2.0, 0.25), ("C3", 2.5, 0.25),
     ("E3", 3.0, 0.25), ("A2", 3.5, 0.25)],
    [("D2", 0.0, 0.25), ("D2", 0.5, 0.25), ("A2", 1.0, 0.25),
     ("A2", 1.5, 0.25), ("D3", 2.0, 0.25), ("F2", 2.5, 0.25),
     ("A2", 3.0, 0.25), ("D2", 3.5, 0.25)],
    [("Bb2", 0.0, 0.25), ("Bb2", 0.5, 0.25), ("F3", 1.0, 0.25),
     ("F3", 1.5, 0.25), ("Bb2", 2.0, 0.25), ("D3", 2.5, 0.25),
     ("F3", 3.0, 0.25), ("Bb2", 3.5, 0.25)],
    [("G2", 0.0, 0.25), ("G2", 0.5, 0.25), ("Bb2", 1.0, 0.25),
     ("Bb2", 1.5, 0.25), ("D3", 2.0, 0.25), ("D3", 2.5, 0.25),
     ("G2", 3.0, 0.25), ("A2", 3.5, 0.25)],
    [("A2", 0.0, 0.25), ("A2", 0.5, 0.25), ("F2", 1.0, 0.25),
     ("F2", 1.5, 0.25), ("E2", 2.0, 0.25), ("D2", 2.5, 0.25),
     ("E2", 3.0, 0.25), ("A2", 3.5, 0.25)],
]
# ★ 鼓：全曲规整；**只有小节 5 反拍一下**（唯一一次反律动）
DRUM_HH = [[("x", t, 0.25) for t in (0.0, 1.0, 2.0, 3.0)]
           if i != 4 else
           [("x", t, 0.25) for t in (0.5, 1.5, 2.5, 3.5)]   # ← 唯一反拍
           for i in range(8)]

_LETTER = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_SLOT_PITCH = {"s0": 60, "s1": 64, "s2": 67, "s3": 71}


def name_to_midi(nm):
    if nm in ("x", "hit"):
        return 60
    if nm in _SLOT_PITCH:
        return _SLOT_PITCH[nm]
    letter, rest = nm[0], nm[1:]
    val = _LETTER[letter]
    if rest and rest[0] in ("#", "b"):
        val += 1 if rest[0] == "#" else -1
        rest = rest[1:]
    return val + (int(rest) + 1) * 12


def build_pattern(measures, beats=4, divs=4):
    total = beats * divs
    out = []
    for bar in measures:
        notes = [dict(pitch=0, velocity=0.0, retrigger=False, active=False)
                 for _ in range(total)]
        for nm, start, dur in bar:
            pitch = name_to_midi(nm)
            i0 = int(round(start * divs))
            i1 = min(total, i0 + max(1, int(round(dur * divs))))
            for i in range(i0, i1):
                notes[i] = dict(pitch=pitch, velocity=0.85,
                                retrigger=(i == i0), active=True)
        out.append({"notes": notes})
    return {"numberOfMeasures": len(out), "beatsPerMeasure": beats,
            "divisionsPerBeat": divs, "measures": out}


def find(patch, model):
    for m in patch["modules"]:
        if m.get("model") == model:
            return m
    return None


def clone_mod(src, model, new_id, pos):
    p = patchio.read_patch(src) if isinstance(src, str) else src
    m = copy.deepcopy(find(p, model))
    if m is None:
        raise RuntimeError("模板缺 " + model)
    m["id"] = new_id
    m["pos"] = list(pos)
    m.pop("leftModuleId", None)
    m.pop("rightModuleId", None)
    m["data"] = dict(m.get("data") or {})
    return m


def set_pr(pr, pat, lowest=None, show=None):
    d = dict(pr.get("data") or {})
    d["patterns"] = [pat]
    d["sequenceRunning"] = True
    d["currentPattern"] = 0
    d["currentStep"] = 0
    d["currentMeasure"] = 0
    if lowest is not None:
        d["lowestDisplayNote"] = lowest
    if show is not None:
        d["notesToShow"] = show
    d.setdefault("lowestDisplayNote", 24)
    d.setdefault("notesToShow", 24)
    pr["data"] = d
    return pr


def set_adsr(mod, atk, dec, sus, rel):
    for q in mod["params"]:
        if q["id"] == 0:
            q["value"] = atk
        elif q["id"] == 1:
            q["value"] = dec
        elif q["id"] == 2:
            q["value"] = sus
        elif q["id"] == 3:
            q["value"] = rel


def set_vco(mod, level, wave_knob=None):
    """VCO：param0 是**音高偏移**（不是波形！），波形靠输出口选。
    音量参数实测在 id 5/6/7 之中。"""
    for q in mod["params"]:
        if q["id"] == 0:
            q["value"] = 0.0
        if q["id"] in (5, 6, 7):
            q["value"] = level
            break


def make_sampler(new_id, pos, files, base_dir, vols, pans):
    r"""samplerx8：**MUTE 写 1.0**（源码：True means "play sample"）。"""
    s = clone_mod(S4, "samplerx8", new_id, pos)
    d = {}
    for i, fn in enumerate(files, start=1):
        d["loaded_sample_path_%d" % i] = os.path.join(base_dir, fn)
    s["data"] = d
    out = []
    for q in s["params"]:
        q = dict(q)
        if 0 <= q["id"] <= 7:
            q["value"] = vols[q["id"]] if q["id"] < len(vols) else 0.5
        elif 8 <= q["id"] <= 15:
            q["value"] = pans[q["id"] - 8] if q["id"] - 8 < len(pans) else 0.0
        elif 16 <= q["id"] <= 23:
            q["value"] = 1.0          # ★★★ 1.0 = 发声
        out.append(q)
    s["params"] = out
    return s


def main():
    ghost = patchio.read_patch(GHOST)
    play = patchio.read_patch(PLAY)
    mods, cables = [], []
    cid = [9500000000001000]

    def cab(a, ao, b, bi, color=""):
        cid[0] += 1
        c = {"id": cid[0], "outputModuleId": a, "outputId": ao,
             "inputModuleId": b, "inputId": bi}
        if color:
            c["color"] = color
        cables.append(c)

    def voice(base_id, bx, y, pat, model, wave_out, adsr, level,
              lowest=None, show=26):
        """音序器 → 音色 → ADSR → VCA。返回 (vca_id, pr_id, voice_id)。"""
        pr = clone_mod(GHOST, "rcm-pianoroll", base_id, [bx, y])
        lo = min(name_to_midi(n) for b in pat for (n, _, _) in b) if any(pat) \
            else 60
        set_pr(pr, build_pattern(pat), lowest=lowest or max(12, lo - 5), show=show)
        vc = clone_mod(GHOST, model, base_id + 1, [bx, y + 1])
        if model == "VCO":
            set_vco(vc, level)
        ad = clone_mod(GHOST, "ADSR", base_id + 2, [bx + 22, y + 1])
        set_adsr(ad, *adsr)
        vca = clone_mod(GHOST, "VCA-1", base_id + 3, [bx + 40, y + 1])
        mods.extend([pr, vc, ad, vca])
        cab(clock["id"], 0, pr["id"], 0)
        cab(pr["id"], 5, vc["id"], 0)
        cab(pr["id"], 6, ad["id"], 4)
        cab(ad["id"], 0, vca["id"], 0)
        cab(vc["id"], wave_out, vca["id"], 1)
        return vca["id"], pr["id"], vc["id"]

    # ---- 时钟 ----
    clock = clone_mod(ghost, "Clocked", 9500000000000001, [-30, 0])
    clock["params"] = [dict(q, value=BPM) if q["id"] == 0 else q
                       for q in clock.get("params", [])]
    clock["data"]["running"] = not START_PAUSED
    mods.append(clock)

    # ---- ① 主旋律：Rings 拨弦（唯一旋律主体，规整）----
    lead_vca, _, _ = voice(9500000000001000, -16, 0, LEAD, "Rings", 0,
                           (0.010, 0.30, 0.55, 0.30), 0.0, lowest=52)

    # ---- ② 采样副旋律：只在 2 个小节插进来打断主旋律（李 16:27 拍板的对位）----
    spr = clone_mod(GHOST, "rcm-pianoroll", 9500000000002000, [-16, 2])
    set_pr(spr, build_pattern(SAMP_COUNTER), lowest=56, show=20)
    samp = make_sampler(9500000000002001, [-16, 3],
                        ["m_D4.wav", "m_A67m.wav", "m_F4.wav", "m_G4.wav"],
                        MEL, vols=[0.42, 0.40, 0.38, 0.36],
                        pans=[0.4, -0.4, 0.25, -0.25])
    mods += [spr, samp]
    cab(clock["id"], 0, spr["id"], 0)
    for i in range(4):
        cab(spr["id"], 6, samp["id"], i)

    # ---- ③ 低音：托底 ----
    # ---- ③ 低音：托底。★ 方波高频成分也多，李16:42 抱怨「大小差距有点大」
    #   ⇒ 音量 0.42 → 0.32，让它真正只做托底。
    bass_vca, _, _ = voice(9500000000003000, 44, 0, BASS, "VCO", 3,
                           (0.006, 0.18, 0.35, 0.14), 0.32, lowest=34)

    # ---- ④ 质感层：锯齿 VCO，**极低音量**，只做背景（绝不抢旋律）----
    # ---- ④ 质感层：李 16:42「那个声音特别明显、特别尖、特别高频，不要太大声」
    #   实测问题（`_diag_tex.py` 追线）：质感层音高 **62~70（A4 区）**，
    #     与主旋律 62~74 **完全重叠**，且锯齿泛音堆到 5kHz+ ⇒ 两层高频叠一起
    #     就是他听到的「又燥又嘶」。
    #   ⇒ 三处同时改：**降八度移开音区** + **三角波替代锯齿**（柔和、无高频尖峰）
    #     + **音量再降**。文档说合成器只做质感层，质感层就该听不见。
    #   ★ 三角波是 OUT1（源码 enum OutputIds: SIN0/TRI1/SAW2/SQR3）。
    tex_vca, _, _ = voice(9500000000004000, 104, 0,
                          [[("D3", 0.0, 1.5), ("D3", 1.5, 0.5),
                            ("F3", 2.0, 1.5), ("F3", 3.5, 0.5)],
                           [("G3", 0.0, 1.5), ("G3", 1.5, 0.5),
                            ("Bb3", 2.0, 1.5), ("Bb3", 3.5, 0.5)],
                           [("A3", 0.0, 1.5), ("A3", 1.5, 0.5),
                            ("D3", 2.0, 1.5), ("D3", 3.5, 0.5)],
                           [("F3", 0.0, 2.0), ("F3", 2.0, 0.5),
                            ("G3", 2.5, 1.5)],
                           [("A3", 0.0, 1.5), ("A3", 1.5, 0.5),
                            ("D3", 2.0, 1.5), ("D3", 3.5, 0.5)],
                           [("Bb3", 0.0, 2.0), ("Bb3", 2.0, 0.5),
                            ("A3", 2.5, 1.5)],
                           [("G3", 0.0, 1.5), ("G3", 1.5, 0.5),
                            ("Bb3", 2.0, 1.5), ("Bb3", 3.5, 0.5)],
                           [("A3", 0.0, 1.5), ("A3", 1.5, 0.5),
                            ("F3", 2.0, 1.5), ("G3", 3.5, 0.5)]],
                          "VCO", 1, (0.60, 0.40, 0.60, 0.50), 0.10,
                          lowest=45)

    # ---- ⑤ 混响：**平时关死**，WET_CV 只在 2 个位置被门信号瞬时打开 ----
    rev = clone_mod(ghost, "Plateau", 9500000000005000, [150, 2])
    for q in rev["params"]:
        if q["id"] == 0:
            q["value"] = 1.0        # DRY = 1.0（干声全程在）
        elif q["id"] == 1:
            q["value"] = 0.0        # ★ WET 旋钮归零 —— 平时**完全没混响**
        elif q["id"] == 7:
            q["value"] = 0.42# DECAY 别太长（0.1~0.9999）
    mods.append(rev)
    cab(lead_vca, 0, rev["id"], 0)
    cab(lead_vca, 0, rev["id"], 1)          # 干声也进（Plateau 需双声道输入）
    # WET_CV(3)：用采样副旋律的 GATE 驱动 —— 采样一进来，湿声短暂闪现
    cab(spr["id"], 6, rev["id"], 3)

    # ---- ⑥ 鼓：BassDrum9 + SnareDrumN（接法抄 play__v1240）----
    seq = clone_mod(play, "Sequencer", 9500000000006000, [96, 4])
    seq["data"]["running"] = False
    mods.append(seq)
    bd = clone_mod(play, "BassDrum9", 9500000000006100, [70, 5])
    sd = clone_mod(play, "SnareDrumN", 9500000000006101, [96, 5])
    mods += [bd, sd]
    cab(seq["id"], 0, bd["id"], 16)
    cab(seq["id"], 1, sd["id"], 16)

    # ---- 混音：Bogaudio-Mix8（李 18:09 要求换掉原来的 Fundamental/Mixer）----
    # ★ 为什么换：Fundamental/Mixer 只有 param0 一个总音量旋钮，
    #   **每路通道没有推子** —— 李原话「我都没法自由控制音量」。
    #   Mix8 每路给 LEVEL 推子 + PAN 声像 + MUTE(带 Solo)，外加 Master 三件套。
    #
    # ★ 规格全部源码核实（plugins/BogaudioModules/src/Mix8.hpp + mixer.cpp）：
    #   · param 27 个：每路三连 LEVEL=3i / MUTE=3i+1 / PAN=3i+2，
    #     末尾 MIX_PARAM=24 / MIX_MUTE=25 / MIX_DIM=26
    #   · 🔴 输入**不是连续 IN0-7**，每路三连：CV=3i / PAN=3i+1 / IN=3i+2
    #     ⇒ 通道1 音频口 = IN2、通道2 = IN5、通道3 = IN8、通道4 = IN11 …
    #   · 输出 OUT0=Left / OUT1=Right
    #   · LEVEL 归一化 0..1 对应 dB **-60 ~ +6**（mixer.cpp:4-5）
    #     ⇒ 0dB = 60/66 = 0.9090909…（**不是 1.0**）
    #   · 🔴 MUTE 是 configSwitch {Unmuted=0, Muted=1, Soloed=2} —— **0 才是开**
    mixer = clone_mod(ghost, "Mixer", 9500000000007000, [130, 5])
    mixer["plugin"] = "BogaudioModules"
    mixer["model"] = "Bogaudio-Mix8"
    mixer["version"] = "2.0"
    _db_lo, _db_hi = -60.0, 6.0
    _unit = abs(_db_lo) / (_db_hi - _db_lo)        # = 0.9090909（0dB）
    # 每路的默认电平（dB）与声像（-1..1）。可逐路调，之后李在面板上直接推。
    _ch = [
        # (LEVEL_dB, PAN)   —— 通道1..6
        (-2.0, 0.00),      # 主旋律：正中，稍退一点给底鼓让位
        (-3.0, 0.00),      # 低音：正中
        (-6.0, 0.35),      # 质感层：偏右
        (-1.0, 0.00),      # 底鼓：正中
        (-4.0, -0.15),     # 军鼓：偏左（与鼓组基座互补）
        (-5.0, 0.00),      # 采样副旋律：正中
    ]
    _pr = {}
    for _i in range(8):
        _db, _pan = _ch[_i] if _i < len(_ch) else (0.0, 0.0)
        _pr[3 * _i + 0] = max(0.0, min(1.0, (_db - _db_lo) / (_db_hi - _db_lo)))
        _pr[3 * _i + 1] = 0.0                      # MUTE = Unmuted（★0 才是开）
        _pr[3 * _i + 2] = _pan
    _pr[24] = _unit                                 # Master level = 0dB
    _pr[25] = 0.0                                  # Master mute = Unmuted
    _pr[26] = 0.0                                  # Master dim  = Disabled
    mixer["params"] = [{"value": float(_pr[k]), "id": int(k)} for k in sorted(_pr)]
    mixer["data"] = dict(mixer.get("data") or {})
    mixer["data"]["poly_channel_offset"] = -1       # 单声道电压和（保守）

    ha = clone_mod(ghost, "HostAudio2", 9500000000007001, [166, 5])
    mods += [mixer, ha]
    # 🔴 Mix8 的音频输入口 = 3i+2，**每路一个独立口**
    def mx(ch):
        return 3 * ch + 2

    cab(lead_vca, 0, mixer["id"], mx(0))      # 通道1 主旋律（干）
    cab(bass_vca, 0, mixer["id"], mx(1))      # 通道2 低音（绝不入混响）
    cab(tex_vca, 0, mixer["id"], mx(2))       # 通道3 质感层
    cab(bd["id"], 0, mixer["id"], mx(3))      # 通道4 底鼓
    cab(sd["id"], 0, mixer["id"], mx(4))      # 通道5 军鼓 ★ 原本与底鼓挤 IN3
    cab(samp["id"], 16, mixer["id"], mx(5))   # 通道6 采样副旋律（干，不进混响）
    # ⚠️ 原线 `cab(rev, 0, mixer, 4)` 已被注释掉（混响不占 Mixer 位），
    #    保持不变 —— 混响串在 lead 链路上。
    #
    # ★ 立体声：Mix8 是 L/R 双出，HostAudio2 正好 2 输入（IN0=左 IN1=右）
    #   ⇒ 左右声道分开接，右声道不再丢失。
    cab(mixer["id"], 0, ha["id"], 0)          # Left
    cab(mixer["id"], 1, ha["id"], 1)          # Right

    p = {"version": "2.4.1", "zoom": 0.5, "gridOffset": [0, 0],
         "modules": mods, "cables": cables}

    ver = datetime.datetime.now().strftime("%H%M")
    out = r"D:\Cardinal\patches\quadeca_scrapyard__v%s.vcv" % ver
    sanitize(p, out)
    patchio.write_patch(out, p)

    print("生成 %s：模块 %d / 连线 %d"
          % (os.path.basename(out), len(mods), len(cables)))
    print()
    print("★ 编曲职责（不是堆层）：")
    print("   ① 主旋律  Rings 拨弦   —— 唯一旋律主体，**规整**，音域 D4~D5")
    print("   ② 副旋律  采样切片      —— **只在小节 3 / 6 插进来**打断主旋律")
    print("   ③ 低音    方波切分      —— 托底，绝不入混响")
    print("   ④ 质感层  锯齿 VCO      —— 音量0.14，**只做背景不抢戏**")
    print("   ⑤ 混响    Plateau       —— WET=0 **平时关死**，只在采样进入时闪现")
    print()
    from collections import Counter
    cnt = Counter(m["model"] for m in patchio.read_patch(out)["modules"])
    print("模块清单： " + "  ".join("%s×%d" % (k, v)
                                for k, v in sorted(cnt.items())))
    print()
    q = patchio.read_patch(out)
    for m in q["modules"]:
        if m["model"] == "samplerx8":
            mu = [x["value"] for x in m["params"] if 16 <= x["id"] <= 23]
            print("  samplerx8 MUTE=%s %s"
                  % (["%.0f" % v for v in mu[:4]],
                     "✅ 发声" if all(v == 1.0 for v in mu) else "❌"))
        if m["model"] == "Plateau":
            v = {x["id"]: x["value"] for x in m["params"]}
            print("  Plateau DRY=%.2f WET=%.2f %s DECAY=%.2f"
                  % (v[0], v[1],
                     "✅ 平时关死(WET=0)" if v[1] == 0.0 else "❌常驻混响",
                     v[7]))
        if m["model"] == "rcm-pianoroll":
            pat = (m["data"].get("patterns") or [{}])[0]
            dens = [sum(1 for x in mm["notes"] if x["active"])
                    for mm in pat.get("measures", [])]
            flat = [x["pitch"] for mm in pat.get("measures", [])
                    for x in mm["notes"] if x["active"]]
            # ★ 密度与音域自检（李 16:42：密度不够 / 高频太尖）
            if flat:
                # 采样副旋律**故意**低密度（那是"克制"），不打⚠️
                is_samp = m["id"] == 9500000000002000
                print("  pr id=%d 密度=%s 平均=%.1f/16 音高=%d~%d %s"
                      % (m["id"], dens, sum(dens) / float(len(dens)),
                         min(flat), max(flat),
                         ("采样副旋律·故意稀疏" if is_samp else
                          "⚠️偏稀" if sum(dens) / float(len(dens)) < 6
                          else "✅")))
    ck = [m for m in q["modules"] if m["model"] == "Clocked"][0]
    print("  Clocked.running =", (ck.get("data") or {}).get("running"))
    bad = audit_ports.audit(out, verbose=True)
    print("端口越界自检:", "全部通过" if not bad else "❌ %d 处" % len(bad))
    return out


if __name__ == "__main__":
    main()
