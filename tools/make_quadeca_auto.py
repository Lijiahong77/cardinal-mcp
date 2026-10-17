# -*- coding: utf-8 -*-
"""make_quadeca_auto.py —— 「我直接演奏」的两张机架。

李 10-17 要求：
  · 不要套在自建编曲器(Starsea)里
  · 要能直接放出来听，加载即自动演奏，不需要他敲任何东西
  · 另给一张他能自己弹的（键盘 + 他的鼓机，鼓机参数用足）

做法（全部有实测依据，不猜）：
  · 模板 A「自己演奏」= 官方 examples\\falkTX_-_Mini-Arp-Seq.vcv
      rcm-pianoroll(40HP) 的 data.patterns[].measures[].notes[] 存音符，
      sequenceRunning=true + HostTime 驱动 = 加载即自动放。
      —— 这是官方自走琶音机架，端口与数据结构均为实测。
  · 模板 B「你能弹」= 已验收的 mini_arranger_expanded.vcv 里的
      HostMIDI + WSTD-Drums 鼓机（32 参数 × 2 声部）。
"""
import copy
import json
import os
import sys

sys.path.insert(0, r"D:\Cardinal\tools")
import patchio

TPL_AUTO = r"C:\Program Files\Cardinal-win64-26.02\Cardinal.lv2\resources\patches\examples\falkTX_-_Mini-Arp-Seq.vcv"
TPL_KB = r"D:\Cardinal\patches\mini_arranger_expanded.vcv"
TPL_MIX = r"D:\Cardinal\patches\demo_S4_sampling.vcv"   # 唯一含 Fundamental/Mixer 的已验收机架

# 各模型真实 param 数量（本机实测，2026-10-17）—— 生成后自检用
PARAM_COUNT = {
    "VCO": 8, "ADSR": 9, "VCA-1": 2, "Mixer": 1,
    "Rings": 12, "LFO": 7, "HostAudio2": 1, "rcm-pianoroll": 2,
}

OUT_DIR = r"D:\Cardinal\patches"

# ------------------------------------------------------------ 加载后是否自动开播
# ★★ 李 12:39 的硬要求：「你每次做完，不要直接开播，你让我按一个按键再开播嘛……
#   你每次开始播，都不知道是从中间哪里开始播的。」
#
#   START_PAUSED = True（默认）⇒ Clocked.data.running = False
#     加载后**时钟静止**，播放头钉在第 1 小节。李在 Clocked 面板点一下 RUN
#     ⇒ 必定从**第 1 小节第 1 拍**开始。
#
#   🔴 记录一个反直觉的点：李原本提议「Mixer 全部 mute，我打开 mute 就开始播」。
#      这个做法**解决不了他的问题** —— mute 只归零音量，时钟仍在走，
#      pianoroll 播放头一直往前扫；等李打开 mute，播放头已在中间某处。
#      ⇒ 唯一根治是**按下之前时钟就不走**。
START_PAUSED = True

# ------------------------------------------------------------ 速度（BPM）
# ★ 李 12:47 亲手把 BPM 调到了 **120**（「节奏快一点」）。
#   写成常量的两个理由：
#     ① 旋钮改动**不写进 autosave** —— 我读 live 看到的仍是 90 而不是 120，
#        只活在界面内存里。所以必须固化进文件，否则下次加载又回到 90。
#     ② 以后调速只改这一行。
# ⚠️ 量纲是**绝对 BPM**（写 0.5 这类归一化值必崩）。
BPM = 120.0

# -------------------------------------------- 各机架的包络覆盖（默认空）
# ★ v5：音符密度不同，包络必须跟着变，不能全机架共用一套 ADSR。
#   例：scrapyard 的中音是**反拍切片**（6 音/小节打弱位），
#   用pad 默认的 Attack=0.55s 会全糊成一片 ⇒ 改成快起快落。
#   键 = 层名，值 = 要覆盖的 ADSR 字段（0=Attack 1=Decay 2=Sustain 3=Release）。
LAYER_ADSR_OVERRIDE = {}

# ---------------------------------------------------------------- 布局基准
# 🔴 李 12:27 硬要求：「我把这个 patch 挪了位置之后，你不要挪回来好吗？
#    视觉上看着舒服，是看我看得舒不舒服。」⇒ **布局主权归他**。
#    LAYOUT.json 由 extract_layout.py 从他手工调好的机架抽出，按角色索引
#    （pr.pad / voice.lead / ... / clock / mixer / reverb），与模块 id 无关。
#    表里没有的角色（scrapyard / life1 是 3 层，没有 decor）才回退默认值。
_LAYOUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "LAYOUT.json")
try:
    with open(_LAYOUT_PATH, encoding="utf-8") as _f:
        LAYOUT = json.load(_f)
except Exception:
    LAYOUT = {}

_HIT, _MISS = [], []


def place(role, default):
    """取模块坐标：李调过的用他的，没调过的用默认值。"""
    if role in LAYOUT:
        _HIT.append(role)
        return list(LAYOUT[role])
    _MISS.append(role)
    return list(default)


# ---------------------------------------------------------------- 音高工具
NOTE = {"C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4,
        "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8, "Ab": 8, "A": 9,
        "A#": 10, "Bb": 10, "B": 11, "Cb": 11, "Fb": 4}


def midi(name, octave):
    """'A#4' -> 音高数字（VCV 惯例 C4=60）；name 是不含八度的音名。"""
    return 12 * (octave + 1) + NOTE[name]


def build_notes(seq, vel=0.8, beats=4, divs=4):
    """把 ['D4', '-', ...] 转成官方那种 note 字典列表。

    ⚠️ 两条硬规则（来自官方 examples/falkTX_-_Mini-Arp-Seq.vcv 实测，2026-10-17）：
      1. 每小节音符数必须严格 = beatsPerMeasure × divisionsPerBeat（4×4=16），
         休止符要写成占位 note（pitch=0, velocity=0, active=false），
         **不能省掉** —— 省略会让后面所有音整体前移，节奏全错。
      2. 音高是绝对 MIDI 号（VCV 惯例 C4=60）；官方示例用 40~50 区间，
         lowestDisplayNote/notesToShow 也要跟着一起调，否则面板显示不出来。
    """
    total = beats * divs
    assert len(seq) == total, "每小节必须 %d 个位置，收到 %d" % (total, len(seq))
    out = []
    for token in seq:
        if token == "-":
            # 休止 = 占位 note，这是官方示例的写法
            out.append({"pitch": 0, "velocity": 0.0,
                        "retrigger": False, "active": False})
            continue
        name = token[:-1]
        octave = int(token[-1])
        out.append({"pitch": midi(name, octave),
                    "velocity": vel, "retrigger": True, "active": True})
    return out


def pattern(measures, beats=4, divs=4):
    return {
        "numberOfMeasures": len(measures),
        "beatsPerMeasure": beats,
        "divisionsPerBeat": divs,
        "measures": [{"notes": m} for m in measures],
    }


# ---------------------------------------------------------------- 音乐素材
# Quadeca 音乐的核心不是"一条旋律"，而是**分层织体**：
#   低音律动（律动骨架）+ 中音和声垫（和声色彩）+ 高音旋律（听感主线）
# 所以每张机架用 3 个独立 rcm-pianoroll 分别演奏这三层，
# 各自接不同音色（物理建模 / FM / 波表）+ 不同混响量，再混起来。
# —— 这也是李 10-17 的要求：「他的音乐难道那么简单的吗」→ 不用简单音色糊弄。


def compose_ghostfolk():
    """鬼魂民谣 / IDMTHY：D 小调多瑙利安，i–VI–III–VII。

    ★ v4（李 12:36「编得再密一点」）：**把织体加密一倍**。
      v3 的密度是 512 个音符槽位只用了 **88 个有效音（17%）** ——
      连八分音符的骨架都还没铺满，听起来是「一个音一个音地掉」而不是一条织体。
      v4 的手法（每层只加一样东西，不乱改）：
        · bass  根音走**八分音符脉冲** + 八度/五度跳进（64 音，原 28）
        · pad   每**四分音符**换一次和弦音（32 音，原 16）—— 变成脉动的垫
        · lead  加**经过音与八分音符流动**（~62 音，原 33）
        · decor 加密到每小节 3–4 个点（~28 音，原 9），第 4 小节仍留一口气
      ⇒ 总密度 17% → **36%**，仍留有呼吸，不是填满。
    """
    DIVS = 4          # 每拍 4 格 = 16 分音符网格，每小节 16 格

    # ============================ 低音：八分音符脉冲 + 八度跳进
    # 和声进行 i(Dm) – VI(Bb) – III(F) – VII(C)，每和弦两小节。
    bass_dm = ["D2", "-", "D2", "-", "A2", "-", "D3", "-",
               "D2", "-", "A2", "-", "F2", "-", "D2", "-"]
    bass_bb = ["Bb1", "-", "Bb1", "-", "F2", "-", "Bb2", "-",
               "Bb1", "-", "F2", "-", "D2", "-", "Bb1", "-"]
    bass_f = ["F2", "-", "F2", "-", "C3", "-", "F3", "-",
              "F2", "-", "C3", "-", "A2", "-", "F2", "-"]
    bass_c = ["C2", "-", "C2", "-", "G2", "-", "C3", "-",
              "C2", "-", "G2", "-", "E2", "-", "C2", "-"]
    BASS = {"Dm": bass_dm, "Bb": bass_bb, "F": bass_f, "C": bass_c}
    CHORD = ["Dm", "Bb", "F", "C"]

    # ============================ 中音和声垫：每四分音符换和弦音
    # ★ 不用十六分音符连打 —— pad 的 Attack=0.55s，16 分间隔（0.167s）根本起不来，
    #   全糊成一团。改成每拍一个音：每 0.667s 重触发一次，包络刚好走完 ⇒「脉动的垫」。
    pad_dm = ["D3", "-", "-", "-", "F3", "-", "-", "-",
              "A3", "-", "-", "-", "A3", "-", "-", "-"]
    pad_bb = ["Bb2", "-", "-", "-", "D3", "-", "-", "-",
              "F3", "-", "-", "-", "F3", "-", "-", "-"]
    pad_f = ["F2", "-", "-", "-", "A2", "-", "-", "-",
             "C3", "-", "-", "-", "C3", "-", "-", "-"]
    pad_c = ["C3", "-", "-", "-", "E3", "-", "-", "-",
             "G3", "-", "-", "-", "G3", "-", "-", "-"]
    PAD = {"Dm": pad_dm, "Bb": pad_bb, "F": pad_f, "C": pad_c}

    # ============================ 高音旋律：保留原旋律骨架，加经过音
    # 手法：原本每小节 5 个音、后面全空 ⇒ 现在让八分音符位置连续流动，
    #      并在级进处插入经过音（F-E、G-F）让线条不跳。
    lead = [
        # 1 · i：上行 D-F-A，然后 G-F-E-D 落回
        ["D4", "-", "F4", "-", "A4", "-", "G4", "F4",
         "-", "E4", "-", "D4", "-", "C4", "-", "-"],
        # 2 · VI：同骨架下移
        ["Bb3", "-", "D4", "-", "F4", "-", "E4", "D4",
         "-", "C4", "-", "Bb3", "-", "A3", "-", "-"],
        # 3 · III：低一个八度，色彩更暗
        ["F3", "-", "A3", "-", "C4", "-", "Bb3", "A3",
         "-", "G3", "-", "F3", "-", "E3", "-", "-"],
        # 4 · VII：回 C 小调，级进下行
        ["C4", "-", "E4", "-", "G4", "-", "F4", "E4",
         "-", "D4", "-", "C4", "-", "G3", "-", "-"],
        # 5 · i：留一口气的高点（原breath 小节在此加密）
        ["D5", "-", "-", "C5", "-", "A4", "-", "F4",
         "-", "E4", "-", "D4", "-", "A3", "-", "-"],
        # 6 · VI：上行到 Bb4，制造第一次小高潮
        ["D5", "-", "C5", "-", "Bb4", "-", "A4", "-",
         "F4", "-", "D4", "-", "F4", "-", "G4", "-"],
        # 7 · III：小二度 Eb 制造不安（延续 decor 的不安手法）
        ["A4", "-", "-", "G4", "-", "F4", "-", "Eb4",
         "-", "C4", "-", "A3", "-", "F3", "-", "-"],
        # 8 · VII：高潮 + 解决回 D，半音 Eb-D 收尾
        ["C5", "-", "G4", "-", "E4", "-", "C4", "-",
         "D4", "-", "Eb4", "-", "D4", "-", "C4", "-"],
    ]

    # ============================ 幽灵装饰层：点状音加密
    # 保持「点状、短、弱、右偏」的性格，只是从每小节 1–2 个变成 3–4 个 ⇒ 更 shimmer。
    decor = [
        ["-", "-", "Eb5", "-", "-", "D5", "-", "-",
         "-", "Eb5", "-", "-", "F5", "-", "-", "-"],
        ["-", "-", "A4", "-", "-", "Bb4", "-", "-",
         "C5", "-", "-", "-", "D5", "-", "-", "-"],
        ["-", "F5", "-", "-", "E5", "-", "-", "D5",
         "-", "-", "C5", "-", "-", "A4", "-", "-"],
        # 第 4 小节仍留一口气（只有 2 个点，力度也压到最低）
        ["-", "-", "-", "Eb5", "-", "-", "-", "-",
         "-", "G4", "-", "-", "-", "-", "-", "-"],
        ["-", "-", "G5", "-", "-", "F5", "-", "-",
         "Eb5", "-", "-", "D5", "-", "-", "-", "-"],
        ["-", "C5", "-", "-", "D5", "-", "-", "-",
         "Eb5", "-", "-", "-", "-", "-", "-", "-"],
        ["-", "-", "Eb5", "-", "-", "C5", "-", "-",
         "Bb4", "-", "-", "A4", "-", "-", "-", "-"],
        ["-", "-", "-", "-", "Eb5", "-", "-", "D5",
         "-", "-", "C5", "-", "-", "-", "-", "-"],
    ]

    B, L, PADm, DECOR, SUB = [], [], [], [], []
    # ★ 力度渐变：整首从亮到暗，装饰层从 0.46 一路降到 0.22（幽灵远去）
    VEL_LEAD = [0.72, 0.72, 0.70, 0.70, 0.66, 0.68, 0.64, 0.62]
    VEL_DEC = [0.46, 0.44, 0.40, 0.26, 0.36, 0.32, 0.28, 0.24]
    # ★ v5：sub 持续长音 = 每小节**一个音撑满整小节**（李选「持续长音铺底」）。
    #   音高比 bass 再低**一个八度** ⇒ 真正的下潜。频率实测：
    #     D1=36.7Hz / Bb1=58.3Hz / F1=43.7Hz / C1=32.7Hz
    #   ⚠️ Bb 最初写成 **Bb0=29.1Hz** —— 太低了！小音箱几乎放不出，
    #     还容易被音箱的低频截止频率直接切掉 ⇒ 听感上等于「那一拍没了」。
    #     统一提到 Bb1=58.3Hz，与其余三个音保持同一个音区。
    #   第 5 小节留白 —— 低频也要呼吸，不能全程压满。
    SUB_NOTE = ["D1", "Bb1", "F1", "C1", "-", "Bb1", "F1", "C1"]
    for bar in range(8):
        ch = CHORD[bar % 4]
        B.append(build_notes(BASS[ch], 0.75))
        PADm.append(build_notes(PAD[ch], 0.55))
        L.append(build_notes(lead[bar], VEL_LEAD[bar]))
        DECOR.append(build_notes(decor[bar], VEL_DEC[bar]))
        # sub：每小节一个长音（hold），占满 16 格；第 5 小节留白
        if SUB_NOTE[bar] == "-":
            SUB.append(build_notes(["-"] * 16, 0.0))
        else:
            SUB.append(build_notes([SUB_NOTE[bar]] + ["-"] * 15, 0.85))

    return [pattern(PADm, 4, DIVS), pattern(B, 4, DIVS),
            pattern(L, 4, DIVS), pattern(DECOR, 4, DIVS),
            pattern(SUB, 4, DIVS)]


def compose_scrapyard():
    """废料场故障：C 小调。半音下行制造不安，反拍切分是核心。

    ★ v5 重写（李12:33 听完ghostfolk 认可「差不多了」⇒ 推广到这张）。
      旧版是三层、密度 21%，**完全没享受到李批准的改进**（sub 深沉低音层 /
      每层不同波形 / 密度加密）。现在按同一标准重写，同时**保留它自己的个性**：
        · 保留**半音下行** C–Bb–Ab–G（这是 scrapyard 的灵魂，不能改成别的东西）
        · 保留**反拍切分**（切音在弱位进，不在强位）
      新增：④ decor 幽灵点音 ⑤ sub 深沉正弦低音（每小节一音撑满）
      密度 21% → 约 40%。
    """
    DIVS = 4

    # ★★ 关键：这一张的「中音」是**反拍切片**，不是长音垫。
    #   默认 pad 的 Attack=0.55s —— 打这么密的弱位切片会全部糊在一起、听不出切分。
    #   ⇒ 覆盖成快起快落：Attack 0.004 / Decay 0.18 / Sustain 0.05 / Release 0.14。
    #   **音符密度决定包络形状，这是不能共用的参数。**
    LAYER_ADSR_OVERRIDE["pad"] = {0: 0.004, 1: 0.18, 2: 0.05, 3: 0.14}

    # ============================ 低音：八分音符脉冲 + 半音下行
    #★ 和声骨架 C–Bb–Ab–G 每个和弦两小节，最后回到 C（反拍收）。
    bass_c = ["C2", "-", "C2", "-", "G2", "-", "C2", "-",
              "C2", "-", "Ab2", "-", "Bb1", "-", "C2", "-"]
    bass_bb = ["Bb1", "-", "Bb1", "-", "F2", "-", "Bb1", "-",
               "Bb1", "-", "G2", "-", "Ab1", "-", "Bb1", "-"]
    bass_ab = ["Ab1", "-", "Ab1", "-", "Eb2", "-", "Ab1", "-",
               "Ab1", "-", "F2", "-", "G1", "-", "Ab1", "-"]
    bass_g = ["G1", "-", "G1", "-", "D2", "-", "G1", "-",
              "G1", "-", "D2", "-", "C2", "-", "G1", "-"]
    BASS = [bass_c, bass_bb, bass_ab, bass_g]
    CH = ["C", "Bb", "Ab", "G"]        # ← 半音下行的四个和弦

    # ============================ 中音切片：反拍切分（这张的招牌）
    # ★ **反拍 = 音符落在弱位**，格位 2/6/10/14（每拍的第二个十六分）。
    #   这就是「故障感」的来源 —— 正常旋律踩在 0/4/8/12（强位），它偏不。
    #   密度从原来的 3 个/小节 加到 6 个/小节，但仍全部落在弱位 ⇒ 更碎更不安。
    slice_c = ["-", "-", "C4", "-", "-", "G3", "-", "-",
               "-", "-", "C4", "-", "Ab3", "-", "-", "G3"]
    slice_bb = ["-", "-", "Bb3", "-", "-", "F3", "-", "-",
                "-", "-", "Bb3", "-", "G3", "-", "-", "F3"]
    slice_ab = ["-", "-", "Ab3", "-", "-", "Eb3", "-", "-",
                "-", "-", "Ab3", "-", "F3", "-", "-", "Eb3"]
    slice_g = ["-", "-", "G3", "-", "-", "D3", "-", "-",
               "-", "-", "G3", "-", "Bb2", "-", "-", "D3"]
    SLICE = [slice_c, slice_bb, slice_ab, slice_g]

    # ============================ 高音：断裂跳跃（保持「坏掉」的性格）
    # 保留大跳（C5→Ab4 这种六度跳），但尾音补上八分音符让线条不断。
    hi_c = ["C5", "-", "Ab4", "-", "-", "C5", "-", "G4",
            "C5", "-", "-", "Eb5", "-", "C5", "-", "G4"]
    hi_bb = ["Bb4", "-", "G4", "-", "-", "Bb4", "-", "F4",
             "Bb4", "-", "-", "D5", "-", "Bb4", "-", "F4"]
    hi_ab = ["Ab4", "-", "F4", "-", "-", "Ab4", "-", "Eb4",
             "Ab4", "-", "-", "G4", "-", "Eb4", "-", "C4"]
    hi_g = ["G4", "-", "D4", "-", "-", "G4", "-", "Bb3",
            "G4", "-", "-", "C5", "-", "G4", "-", "Bb3"]
    HI = [hi_c, hi_bb, hi_ab, hi_g]

    # ============================ 幽灵装饰层：故障的「碎屑」
    # 用**小九度/减五度**（Ab↔C 的三全音）制造不稳定感 —— 比 ghostfolk 的小二度更「坏」。
    decor = [
        ["-", "-", "Eb5", "-", "-", "-", "Ab4", "-", "-", "-", "-", "G4", "-", "-", "-", "-"],
        ["-", "-", "F4", "-", "-", "-", "Bb4", "-", "-", "-", "-", "Ab4", "-", "-", "-", "-"],
        ["-", "-", "Eb4", "-", "-", "-", "Ab4", "-", "-", "-", "-", "G4", "-", "-", "-", "-"],
        # 第 4 小节只留 1 个点 —— 喘息，也是全曲唯一的「安静」，故障停一拍
        ["-", "-", "-", "-", "-", "-", "-", "-", "-", "Ab4", "-", "-", "-", "-", "-", "-"],
        ["-", "-", "G4", "-", "-", "-", "C5", "-", "-", "-", "-", "Ab4", "-", "-", "-", "-"],
        ["-", "-", "Ab4", "-", "-", "-", "D5", "-", "-", "-", "-", "C5", "-", "-", "-", "-"],
        ["-", "-", "F4", "-", "-", "-", "Bb4", "-", "-", "-", "-", "G4", "-", "-", "-", "-"],
        # 收尾留白，让故障感慢慢消散
        ["-", "-", "-", "-", "-", "-", "G4", "-", "-", "-", "-", "-", "-", "-", "-", "-"],
    ]

    # ★ v5：sub 深沉低音 = 每小节一音撑满。频率已核算：
    #   C1=32.7Hz / Bb0太 low→ 用 Bb1=58.3 / Ab1=51.9 / G1=49.0 —— 全部在可用区。
    #   ⚠️ Ab1/G1 已接近 50Hz，小音箱可能偏弱；但比 Bb0=29Hz（等于没有）好。
    SUB_NOTE = ["C1", "Bb1", "Ab1", "G1", "-", "Bb1", "Ab1", "G1"]

    B, S, H, D, SUB = [], [], [], [], []
    VEL_HI = [0.68, 0.68, 0.66, 0.60, 0.64, 0.62, 0.58, 0.54]
    VEL_DEC = [0.42, 0.40, 0.36, 0.22, 0.34, 0.30, 0.26, 0.20]
    for bar in range(8):
        k = bar % 4
        B.append(build_notes(BASS[k], 0.78))
        S.append(build_notes(SLICE[k], 0.70))
        H.append(build_notes(HI[k], VEL_HI[bar]))
        D.append(build_notes(decor[bar], VEL_DEC[bar]))
        if SUB_NOTE[bar] == "-":
            SUB.append(build_notes(["-"] * 16, 0.0))
        else:
            SUB.append(build_notes([SUB_NOTE[bar]] + ["-"] * 15, 0.82))

    return [pattern(S, 4, DIVS), pattern(B, 4, DIVS), pattern(H, 4, DIVS),
            pattern(D, 4, DIVS), pattern(SUB, 4, DIVS)]


def compose_life1():
    """数字焦虑 / life1：A 小调。密集快速反复 + 大跳 + 几乎不留白。
    三层：低音持续轰鸣 + 中音密集琶音 + 高音尖锐快速反复。"""
    DIVS = 4
    # 低音：A 持续，偶而下行到 G 制造不稳
    bA = ["A1", "-", "-", "-", "-", "-", "A1", "-", "-", "-", "-", "-", "A1", "-", "-", "-"]
    bG = ["A1", "-", "-", "-", "-", "-", "G1", "-", "-", "-", "-", "-", "G1", "-", "-", "-"]
    # 中音密集琶音：A-C-E 循环，几乎不停
    pA = ["A3", "C4", "E4", "A4", "C5", "A4", "E4", "C4", "A3", "C4", "E4", "A4", "C5", "E5", "C5", "A4"]
    pB = ["G3", "B3", "D4", "G4", "B4", "G4", "D4", "B3", "G3", "B3", "D4", "G4", "B4", "D5", "B4", "G4"]
    # 高音尖锐快速反复（焦虑感的关键）
    hA = ["A5", "A4", "A5", "A4", "E5", "E4", "A5", "E5", "A5", "A4", "A5", "E5", "C5", "C5", "E5", "A5"]
    hB = ["G5", "G4", "G5", "G4", "D5", "D4", "G5", "D5", "G5", "G4", "G5", "D5", "B4", "B4", "D5", "G5"]

    B, P, H = [], [], []
    for bar in range(8):
        B.append(build_notes(bA if bar % 3 else bG, 0.8))
        P.append(build_notes(pA if bar % 2 == 0 else pB, 0.6))
        H.append(build_notes(hA if bar % 2 == 0 else hB, 0.55))
    return [pattern(P, 4, DIVS), pattern(B, 4, DIVS), pattern(H, 4, DIVS)]


# ---------------------------------------------------------------- 骨架
def sanitize(patch, path):
    """保存前清洗。

    ★ 真正元凶（2026-10-17 定位）：leftModuleId / rightModuleId 是 Rack 用来给
      模块排序的「面包屑」链。我 deepcopy 模板后改了 id，却没清这两个字段，
      它们仍指向源机架里已不存在的模块 → 链断裂 → 加载即崩。
      证据：五张机架各有 9~13 个悬空引用，成功加载的机架为 0。
      这就是「改一版试一版」永远找不到的原因 —— 它不在我改过的字段里。

    对照证据：
      ✅ ghostfolk / life1（0 个 color）、官方 demo（10 个真实色值）→ 能加载
      ❌ zz_probe(9 个空) / play(31 个空) / auto_*(23 个空)        → 全崩
    """
    for c in patch.get("cables", []):
        if "color" in c and (c["color"] == "" or c["color"] is None):
            del c["color"]
    live = set(m["id"] for m in patch.get("modules", []))
    for m in patch.get("modules", []):
        for key in ("leftModuleId", "rightModuleId"):
            if m.get(key) is not None and m[key] not in live:
                del m[key]
    patch["path"] = path
    _guard(patch, path)
    return patch


def _guard(patch, path):
    """门禁：拦住「静态看全绿、加载即崩 / 加载后不出声」的两类隐性缺陷。

    ★ 同口多线（18:05 踩到）：Rack 允许一个输入口接多根线，但**后一根会把前一根
      挤掉** —— 表现为接线看着在、声音断。scrapyard 的底鼓与军鼓原本都接 IN3。
      ⇒ 判据：同一个 (inputModuleId, inputId) 组合不得重复。

    ★ Bogaudio-Mix8：param 必须 27 个，且**每路 MUTE 必须是 0**（Unmuted）。
      它的 MUTE 是 configSwitch {0=Unmuted, 1=Muted, 2=Soloed}，写 1 就静音，
      与「静音键=1」的直觉相反。输入口是 3i+2，不是连续编号。
    """
    mods = patch.get("modules", [])
    ids = {m["id"]: m for m in mods}

    seen = {}
    for c in patch.get("cables", []):
        k = (c["inputModuleId"], c["inputId"])
        seen.setdefault(k, 0)
        seen[k] += 1
    for (mid, pid), n in seen.items():
        if n > 1:
            raise AssertionError("同口多线 %d 根 → 互相挤掉：模块 %s 的 IN%d"
                                 % (n, mid, pid))

    for m in mods:
        if m.get("model") != "Bogaudio-Mix8":
            continue
        if len(m.get("params") or []) != 27:
            raise AssertionError("Mix8 id=%s param 数 %d，应 27"
                                 % (m["id"], len(m.get("params") or [])))
        pv = {p["id"]: p["value"] for p in m["params"]}
        for i in range(8):
            if pv.get(3 * i + 1) != 0.0:
                raise AssertionError(
                    "Mix8 id=%s 通道%d MUTE=%s，应 0（0=Unmuted，1=Muted）"
                    % (m["id"], i + 1, pv.get(3 * i + 1)))
        if pv.get(25) != 0.0:
            raise AssertionError("Mix8 id=%s Master MUTE=%s，应 0"
                                 % (m["id"], pv.get(25)))
        for c in patch.get("cables", []):
            if c["outputModuleId"] == m["id"] and c["outputId"] > 1:
                raise AssertionError("Mix8 id=%s 只有 OUT0(L)/OUT1(R)，实得 OUT%d"
                                     % (m["id"], c["outputId"]))
            if c["inputModuleId"] != m["id"]:
                continue
            n = c["inputId"]
            if n != 24 and n not in [3 * i + 2 for i in range(8)]:
                raise AssertionError("Mix8 id=%s IN%d 不是音频/CV 口" % (m["id"], n))
    return patch

def load_tpl():
    return patchio.read_patch(TPL_AUTO)


# 官方模板模块缓存：按 model 名深拷贝（保证字段类型与取值真实，不靠猜）
_TPL = None


def _tpl():
    global _TPL
    if _TPL is None:
        _TPL = load_tpl()
    return _TPL


def _deep_tpl(model):
    m = find(_tpl(), model)
    return copy.deepcopy(m)


# Fundamental/VCO 不在官方自走琶音模板里 ⇒ 改从已验收机架取（字段真实、不越界）
_FUND = None


def _fund_tpl(model):
    """从已验收机架取 Fundamental 模块（VCO/ADSR/VCA-1）。"""
    global _FUND
    if _FUND is None:
        _FUND = patchio.read_patch(TPL_KB)
    m = find(_FUND, model)
    return copy.deepcopy(m)


def find(patch, model):
    for m in patch["modules"]:
        if m["model"] == model:
            return m
    raise KeyError(model)


def set_pianoroll_notes(pr, pattern_obj, running=True, lowest=None):
    d = pr.setdefault("data", {})
    d["patterns"] = [pattern_obj]
    d["sequenceRunning"] = running
    d["currentPattern"] = 0
    d["currentStep"] = 0
    d["currentMeasure"] = 0
    d["clockDelay"] = 0
    d["driverMode"] = False
    # ⚠️ 显示音域：sub 层的音低到 MIDI 24（33Hz），默认值 lowestDisplayNote=24 刚好压边。
    #   pianoroll 的 notesToShow 决定纵向可见的半音数；音太低会显示在可视区外。
    #   low 越低 = 显示区越往下。给 sub 单独调低 lowestDisplayNote 让低频音看得见。
    d.setdefault("lowestDisplayNote", 24 if lowest is None else lowest)
    d.setdefault("notesToShow", 48)
    return pr


# 音色配方：每层给不同模块与不同关键参数（全部取自本机已验收机架的实测口径）
#
#   param 索引依据：
#     ADSR   0=Attack 1=Decay 2=Sustain 3=Release
#     VCA-1  0=Level  1=Pan
#     Rings  2=Structure(拨弦/模态) 3=Brightness 4=Frequency 5=Loudness 6=Position
#     VCO    0=Wave 1=Pitch(CV) 2=Level 3=Fine
#     VCF    0=Type 1=Frequency 2=Resonance 3=CV Amount 4=CV Input 5=Response
#     Mixer  0..5 = 各路电平
#     Plateau（混响）见 PORTS.md §8
# ⚠️ 2026-10-17 踩坑（代价：Cardinal GUI 崩溃、OSC 失联）：
#   Rings 的 data.model 是**整数**（模板实测 = 0），不是字符串。
#   我写了 "Modal" ⇒ 加载即崩。以后 data 一律照抄模板原值，不猜枚举名。
#   （已验收机架里 Rings 的 data={} 也能跑，说明缺省走默认 0。）
VOICE_LAYERS = {
    # 旋律层：Rings 物理建模拨弦，亮、衰减快 → 幽灵感
    # params 取自官方模板实测（12 个），只改 Structure/Brightness/Freq/Loud/Pos
    "lead":  dict(plugin="AudibleInstruments", model="Rings",
                  params={0: 0.0, 1: 0.0, 2: 30.0, 3: 0.55, 4: 0.5,
                          5: 0.62, 6: 0.45, 7: 0.0, 8: 0.0, 9: 0.0,
                          10: 0.2293335497379303, 11: 0.0},
                  data=None,   # 原样保留源机架的 data
                  adsr={0: 0.004, 1: 0.62, 2: 0.0, 3: 0.72},
                  rev=0.62, level=0.56, pan=-0.15),
    # 和声垫层：VCO 方波，缓起缓落，铺底。
    # ⚠️ VCO 实测只有 **8** 个 param（0..7），我曾写 id:8 越界 ⇒ 加载即崩。
    # ⚠️ v4：level 0.42→**0.30**。音符数翻倍（2→4 个/小节）且 Attack=0.55s
    #    ⇒ 每个新音都叠在上一音的尾巴上，实际能量接近翻倍 ⇒ 不降音量就糊。
    "pad":   dict(plugin="Fundamental", model="VCO",
                  params={0: 2.0, 1: 1.0, 2: 0.0, 3: 0.0,
                          4: 0.0, 5: 0.5, 6: 0.0, 7: 0.0},
                  data=None,
                  adsr={0: 0.55, 1: 0.4, 2: 0.7, 3: 0.9,
                        4: 0.0, 5: 0.0, 6: 0.0, 7: 0.0, 8: 0.0},
                  rev=0.5, level=0.30, pan=0.25,
                  # ⚠️ v5：给 **锯齿波 OUT2** —— 原来没写 wave_out，默认 0（正弦），
                  #   与 sub 层**撞音色**（两层的波形一模一样）。四层必须各有波形。
                  #   锯齿偏亮，正好让中音垫从低频里浮出来，形成对比。
                  wave_out=2),
    # 低音层：VCO 锯齿，短促、干
    # ⚠️ v4：level 0.72→**0.60**。八分音符脉冲比原来的四分音符密一倍。
    # ⚠️ v5：走**三角波 OUT1**（wave_out=1）—— 锯齿太亮太冲，在李要的「深沉」里不合适；
    #   三角波无二次谐波、比正弦多一点厚度，适合做律动骨架。真正的低频下潜交给 sub 层。
    "bass":  dict(plugin="Fundamental", model="VCO",
                  params={0: 0.0, 1: 1.0, 2: 0.0, 3: 0.0,
                          4: 0.0, 5: 0.5, 6: 0.0, 7: 0.0},
                  data=None,
                  adsr={0: 0.002, 1: 0.28, 2: 0.15, 3: 0.18,
                        4: 0.0, 5: 0.0, 6: 0.0, 7: 0.0, 8: 0.0},
                  rev=0.1, level=0.60, pan=0.0,
                  wave_out=1),
    # ★ v2 新增「幽灵装饰」层：高八度短促点状音，弱音量、右偏。
    #   动机 = Quadeca 常用的「一个音突然飘过去」—— 不承担旋律，只制造不安。
    "decor": dict(plugin="Fundamental", model="VCO",
                  # param0 =音高偏移（半音）。+19 ≈ 高八度多一个大二度，比纯八度更刺
                  params={0: 19.0, 1: 1.0, 2: 0.0, 3: 0.0,
                          4: 0.0, 5: 0.62, 6: 0.0, 7: 0.0},
                  data=None,
                  adsr={0: 0.001, 1: 0.5, 2: 0.02, 3: 0.05,   # 极短 = 点状
                        4: 0.0, 5: 0.0, 6: 0.0, 7: 0.0, 8: 0.0},
                  rev=0.9, level=0.26, pan=0.55,
                  wave_out=0),
    # ★★ v5 新增「sub 深沉低音」层（李 12:47：「缺乏厚度…要一个与众不同的深沉音色，
    #   低频重一点」）—— 这是李明确点名要的东西。
    #   动机：原来四层里 bass 用**锯齿**(OUT2)，lead 用**物理建模拨弦**，
    #   pad 用方波 —— 全是带谐波的音色，听感都偏「轻飘」。缺的是**纯低频下潜**。
    #   做法（源码核实，见 Fundamental/src/VCO.cpp: enum OutputIds）：
    #     SIN_OUTPUT=0 / TRI_OUTPUT=1 / SAW_OUTPUT=2 / SQR_OUTPUT=3
    #     —— 波形是**四个独立输出口**，不是 param0 枚举！（param0 是 Frequency 半音偏移）
    #     这一层专走 **OUT0 正弦波**：无谐波、纯净，就是「沉」本身。
    "sub":   dict(plugin="Fundamental", model="VCO",
                  # ★ 正弦波走 OUT0（wave_out=0）
                  params={0: 0.0, 1: 1.0, 2: 0.0, 3: 0.0,
                          4: 0.0, 5: 0.5, 6: 0.0, 7: 0.0},
                  data=None,
                  # 长音铺底：Attack 快(0.06) 免得糊，Decay 0 但 **Sustain 满 (0.92)**
                  #，Release 中等(0.45)⇒ 一个音稳稳撑满整小节，这就是「厚度」。
                  adsr={0: 0.06, 1: 0.0, 2: 0.92, 3: 0.45,
                        4: 0.0, 5: 0.0, 6: 0.0, 7: 0.0, 8: 0.0},
                  rev=0.0, level=0.78, pan=0.0,
                  wave_out=0),
}

# ★ v2 新增：Plateau 混响参数（量纲全部来自 PORTS.md §8 源码表，**不是猜的**）
# ⚠️ Plateau 实测有 **31** 个 param（PORTS.md 只列了前 16 个 configParam），
#    所以必须克隆模板保留完整结构，只覆盖前 16 个。
# ⚠️ v3 修正（12:26 李试听反馈「轰隆隆，太过了」）：
#    隆隆声不是湿声量本身，而是**混响把低频一起放大了** ——
#    送进去的 pad 是方波（低频能量极足），而 Rev low cut 只给 3.0 ≈ 没切，
#    于是低频在混响里堆成轰鸣。
#    对策：① 大幅提高两个低切 ② 收小尺寸与衰减 ③ 降低湿声比例。
#    目标 = 混响只留高频泛音，做「空气感」而不是「地鸣」。
PLATEAU_PARAMS = {
    0: 0.78,     # Dry level    0~1  —— 直达声为主（v2 是 0.62，偏湿）
    1: 0.24,     # Wet level    0~1  —— 湿声减半（v2 是 0.42，太满）
    2: 0.020,    # Pre-delay    0~0.5 秒 —— 一点延迟 = 空间感（略收）
    3: 7.5,      # In low cut   0~10 —— ★3.0→7.5：送进混响前先砍掉大部分低频
    4: 8.5,      # In high cut  0~10 —— 高频通透
    5: 0.64,     # Size         0~1  —— 0.82→0.64，房间小一点更聚焦
    6: 4.5,      # Diffusion    0~10
    7: 0.62,     # Decay        0.1~0.9999 —— ★0.86→0.62，长尾巴是轰的关键
    8: 7.0,      # Reverb high cut 0~10
    9: 9.0,      # Reverb low cut  0~10 —— ★3.0→9.0，混响里几乎不保留低频
    10: 0.16,    # Mod rate  0~1
    11: 0.55,    # Mod shape 0~1
    12: 1.6,     # Mod depth 0~16 —— 2.4→1.6，轻微摇曳即可
}


def build_layer(patch, base_x, base_y, tid, layer_key, pattern_obj,
                pitch_in=5, gate_in=6, retrig_in=7):
    """从模板克隆一条完整音轨：pianoroll → 音色 → ADSR → VCA →（留空，由调用方接混音）。

    返回 (voice_module_id, vca_module_id)。
    所有端口号均来自官方模板实测：
      pianoroll OUT5=PITCH / OUT6=GATE / OUT7=RETRIG
      ADSR IN4=GATE, ADSR OUT0=ENV
      VCA-1 IN0=音量包络, IN1=音频
    """
    import copy as _c

    cfg = VOICE_LAYERS[layer_key]

    # --- 1. pianoroll：克隆模板那一个 ---
    tpl_pr = find(patch, "rcm-pianoroll")
    pr = _c.deepcopy(tpl_pr)
    pr["id"] = tid
    pr["pos"] = [base_x, base_y]
    set_pianoroll_notes(pr, pattern_obj)
    patch["modules"].append(pr)

    # --- 2. 音色模块 ---
    tpl_voice = None
    for m in patch["modules"]:
        if m["model"] in ("Rings", "VCO"):
            tpl_voice = m
            break
    if tpl_voice is None:
        raise RuntimeError("模板里找不到可克隆的音色模块")

    voice = _c.deepcopy(tpl_voice)
    voice["id"] = tid + 1
    voice["plugin"] = cfg["plugin"]
    voice["model"] = cfg["model"]
    voice["pos"] = [base_x + 42, base_y]
    voice["params"] = [{"id": k, "value": float(v)}
                       for k, v in cfg["params"].items()]
    voice["data"] = _c.deepcopy(cfg["data"])
    patch["modules"].append(voice)

    # --- 3. ADSR ---
    tpl_adsr = find(patch, "ADSR")
    adsr = _c.deepcopy(tpl_adsr)
    adsr["id"] = tid + 2
    adsr["pos"] = [base_x + 47, base_y]
    adsr["params"] = [{"id": k, "value": float(v)}
                      for k, v in cfg["adsr"].items()]
    patch["modules"].append(adsr)

    # --- 4. VCA ---
    tpl_vca = find(patch, "VCA-1")
    vca = _c.deepcopy(tpl_vca)
    vca["id"] = tid + 3
    vca["pos"] = [base_x + 51, base_y]
    vca["params"] = [{"id": 0, "value": 0.75}, {"id": 1, "value": 0.0}]
    patch["modules"].append(vca)

    def cab(a, ao, b, bi, color=""):
        patch["cables"].append({
            "id": max([c["id"] for c in patch["cables"]] or [0]) + 1,
            "outputModuleId": a, "outputId": ao,
            "inputModuleId": b, "inputId": bi, "color": color})

    cab(tid, pitch_in, voice["id"], 0 if cfg["model"] == "VCO" else 6)  # 音高
    cab(tid, gate_in, adsr["id"], 4)        # 门 → ADSR
    cab(tid, retrig_in, adsr["id"], 5)      # retrig → ADSR
    cab(adsr["id"], 0, vca["id"], 0)        # 包络 → VCA 音量
    cab(voice["id"], 0, vca["id"], 1)       # 音频 → VCA 输入

    return voice["id"], vca["id"]


def build_one(name, patterns, chain=None):
    """以官方自走琶音机架为模板，扩成多层织体。

    ★ v2（12:20 李试听后要求「再加小巧思、再复杂点」）在原三层上补了：
      ④ decor 装饰层 —— 高八度点状音，小二度制造不安，力度渐变
      ⑤ Plateau 混响 —— lead/pad 送进去做湿声（音频输入是**求和**输入）

    布局（李这台机器 3200x2000，zoom 0.62 → 每行约 155 格，两行约 50 格高）：
      行 0：Clocked + N 个 rcm-pianoroll（各 40HP，只做音符发生，不占横向太多）
      行 1：音色链（VCO/Rings + ADSR + VCA）+ Plateau + Mixer + HostAudio2
    ⚠️ 三个 pianoroll 的 IN0 都必须接时钟。输出可分叉（一个输出接多处合法），
       受限的只有**输入口**（一个输入口只能接一根线）。
    """
    p = load_tpl()
    p["version"] = "2.4.1"
    p["zoom"] = 0.62
    p["gridOffset"] = [0, 0]

    # 保留 HostTime（时钟源），其余模板旧模块全删
    host_audio = find(p, "HostAudio2")
    host_audio["id"] = 9000000000000002
    host_audio["pos"] = place("host", [70, 1])

    # ★ 时钟源：必须用 Clocked，不能用 HostTime。
    #   PORTS.md §1.5 原文：「HostTime……**依赖宿主走带，standalone 里没用，要换 Clocked**」。
    #   我原来接的是 HostTime.OUT4，而 OUT4 是 **Step**（不是 clock）——
    #   在独立版 Cardinal 里时钟根本不走 ⇒ 加载成功但**永远不自动演奏**。
    #   正确：Clocked.OUT0 = 主时钟（PORTS.md §2）。
    #   ⚠️ running 语义：**True = 正在放**（不是"允许播放"）。所以
    #      要「加载即静止」必须写 running=False，见下面 START_PAUSED。
    clock_tpl = None
    for _m in patchio.read_patch(r"D:\Cardinal\patches\helm_drums.vcv")["modules"]:
        if _m["model"] == "Clocked":
            clock_tpl = copy.deepcopy(_m)
            break
    if clock_tpl is None:
        raise RuntimeError("在 helm_drums.vcv 里找不到 Clocked 可克隆")
    clock = clock_tpl
    clock["id"] = 9000000000000001
    clock["pos"] = place("clock", [0, 0])
    clock.pop("leftModuleId", None)
    clock.pop("rightModuleId", None)
    clock["data"] = dict(clock.get("data") or {})
    # ★★ 李 12:39 的要求：「你每次做完，不要直接开播，让我按一个按键再开播」
    #    running = **false** ⇒ 加载后时钟静止，播放头钉在第 1 小节不动。
    #    李在 Clocked 面板上点一下 RUN ⇒ 从**第 1 小节第 1 拍**准时开始。
    #
    # 🔴 为什么不能用 Mixer mute 代替（李原本的想法，我查过后改了做法）：
    #   mute 只把音量归零，**时钟照样在走** —— pianoroll 的播放头一直在往前扫。
    #   等李解除mute 时，播放头已经停在中间某处 ⇒ 「不知道从中间哪里开始」照旧。
    #   唯一的根治办法是**让时钟在按下之前根本不走**，即 data.running = false。
    clock["data"]["running"] = not START_PAUSED  # ★ START_PAUSED=True ⇒ running=False
    # param0 = **绝对 BPM**（Clocked 的量纲，写 0.5 这类归一化值必崩）
    clock["params"] = [dict(q, value=BPM) if q["id"] == 0 else q
                       for q in clock.get("params", [])]

    p["modules"] = [clock, host_audio]
    p["cables"] = []

    cid = 9000000000001000

    def cab(a, ao, b, bi, color=""):
        nonlocal cid
        cid += 1
        p["cables"].append({
            "id": cid, "outputModuleId": a, "outputId": ao,
            "inputModuleId": b, "inputId": bi, "color": color})

    # --- 行 0：pianoroll（每个 40HP 宽）。层数由传入的 pattern 数决定 ---
    # ghostfolk 传 4 个 pattern（多了 decor），其余仍是 3 个 —— 保持已验证的结构不变。
    # ★ v5：pattern 数决定层数 —— 4=pad/bass/lead/decor，5=再加 sub（深沉低音）。
    # ⚠️ **层数上限是 5** —— Mixer 只有 6 路输入（IN0-5），混响改走lead 链路后
    #   不再占一路，所以 Mixer 能容 5 层 + 余量。这是硬约束，别再加第 6 层。
    if len(patterns) == 5:
        keys = ["pad", "bass", "lead", "decor", "sub"]
    else:
        keys = ["pad", "bass", "lead"] + (["decor"] if len(patterns) == 4 else [])
    pr_ids = []
    tid = 9000000000000100
    for i, key in enumerate(keys):
        pr_id = tid
        pr = _deep_tpl("rcm-pianoroll")
        pr["id"] = pr_id
        # 4 层时 decor 放行 2（第三行），避免四个 40HP 模块横排超出屏幕
        pr["pos"] = place("pr." + key,
                          [4 + i * 41, 0] if i < 3 else [4, 2])
        # ★ v5：sub 的音低到 MIDI 24（33Hz）⇒ 显示音域要往下挪，否则面板上看不到音
        set_pianoroll_notes(pr, patterns[i],
                            lowest=(12 if key == "sub" else None))
        p["modules"].append(pr)
        pr_ids.append(pr_id)
        cab(clock["id"], 0, pr_id, 0)   # Clocked OUT0(主时钟) → pianoroll IN0(clock)
        tid += 10

    # --- 行 1：音色链，x = 4 / 22 / 40（4 层时 decor 排到 x=58，避开混响与 Mixer）---
    vca_ids = []
    tid = 9000000000000200
    for i, key in enumerate(keys):
        cfg = VOICE_LAYERS[key]

        # 音色模块：Rings 从官方模板克隆（字段真实）；VCO 从已验收机架克隆
        # ⚠️ 不可用 Rings 的克隆改 model 顶替 VCO —— param 个数不同会越界崩溃。
        if cfg["model"] == "VCO":
            voice = _fund_tpl("VCO")
        else:
            voice = _deep_tpl("Rings")
        voice["id"] = tid
        voice["plugin"] = cfg["plugin"]
        voice["model"] = cfg["model"]
        # 4 层时 decor 链整条挪到行 2（x=45 起，跳过同行的 40HP pianoroll），
        # 这样行 1 的三链 + Mixer 布局与已验证版本完全一致，不动它。
        bx = 45 if key == "decor" else 4 + i * 18
        by = 2 if key == "decor" else 1
        voice["pos"] = place("voice." + key, [bx, by])
        voice["params"] = [{"id": k, "value": float(v)}
                           for k, v in sorted(cfg["params"].items())]
        # ⚠️ data 原样保留（源机架为 None）。改成 {} ⇒ 反序列化失败 ⇒ 崩。
        voice["data"] = voice.get("data")

        adsr = _fund_tpl("ADSR")
        adsr["id"] = tid + 1
        adsr["pos"] = place("adsr." + key, [bx + 9, by])
        ap = {k: float(v) for k, v in cfg["adsr"].items()}
        # ★ v5：允许 compose 函数按机架覆盖某层的包络（LAYER_ADSR_OVERRIDE）。
        #   起因：scrapyard 的中音是**反拍切片**（6 个音/小节打在弱位），
        #   而 pad 默认 Attack=0.55s —— 这么密的切片用这么慢的起音会全糊成一片。
        #   ⇒ 音符密度不同，包络就必须跟着变，不能全机架共用一套。
        ov = LAYER_ADSR_OVERRIDE.get(key)
        if ov:
            ap.update(ov)
        for k in range(9):                 # ADSR 实测 9 个 param，写满更稳
            ap.setdefault(k, 0.0)
        adsr["params"] = [{"id": k, "value": ap[k]} for k in range(9)]

        vca = _fund_tpl("VCA-1")
        vca["id"] = tid + 2
        vca["pos"] = place("vca." + key, [bx + 13, by])
        vca["params"] = [{"id": 0, "value": cfg["level"]},
                         {"id": 1, "value": cfg["pan"]}]

        p["modules"] += [voice, adsr, vca]

        # 接线（端口号全部来自官方模板实测）
        pr_id = pr_ids[i]
        pitch_in = 0 if cfg["model"] == "VCO" else 6   # VCO 音高=IN0；Rings 音高=IN6
        cab(pr_id, 5, voice["id"], pitch_in)   # OUT5=PITCH
        cab(pr_id, 6, adsr["id"], 4)            # OUT6=GATE → ADSR IN4
        cab(pr_id, 7, adsr["id"], 5)            # OUT7=RETRIG → ADSR IN5
        cab(adsr["id"], 0, vca["id"], 0)        # ADSR OUT0 → VCA 音量
        # ★波形出口：VCO 有四个输出口 SIN/TRI/SAW/SQR（源码 enum OutputIds
        #   0/1/2/3），**波形是选输出口，不是选 param**。
        #   各层选不同波形 = 「音色不同」的根本手段：
        #     sub=0 正弦(纯) · bass=1 三角(柔厚) · pad=2 锯齿(亮) · decor=3 方波(粗)
        cab(voice["id"], cfg.get("wave_out", 0), vca["id"], 1)
        vca_ids.append(vca["id"])
        tid += 10

    # --- 混响（李 12:47 拍板）：从 Mixer 里**撤出**，改成串在 lead 链路上 ---
    #
    # ★ v2 旧做法：lead 分叉进 Plateau，湿声再占 Mixer 一路（IN4）。
    #   问题：Mixer 只有 6 路（IN0-5），加了 sub 低音层后**位置不够**。
    # ★ v5 新做法（李拍板「混响移到 lead 链路上」）：
    #   lead.VCA → Plateau.IN0 → Plateau.OUT0 → Mixer 的 lead 那一路
    #   ⇒ ① 湿声不再单独占 Mixer 一路，腾出位置给 sub
    #     ② 更重要的是**低频完全不进混响** —— 「轰隆隆」的根治：
    #        低频一旦进混响就会被整体放大。sub 是纯正弦低频，绝不能进混响。
    #   Plateau 的 Dry level=0.78 / Wet=0.24（见 PLATEAU_PARAMS），
    #   所以湿声里本身就含干声 ⇒ 串在lead 后面不会丢声音，反而更自然。
    reverb_out = None
    reverb_lead = False
    if len(keys) >= 4:
        rev_tpl = None
        for m in patchio.read_patch(r"D:\Cardinal\patches\helm_full.vcv")["modules"]:
            if m["model"] == "Plateau":
                rev_tpl = m
                break
        if rev_tpl is None:
            raise RuntimeError("在 helm_full.vcv 里找不到 Plateau 可克隆")
        rev = copy.deepcopy(rev_tpl)
        rev["id"] = 9000000000000950
        rev["pos"] = place("reverb", [58, 3])
        rev.pop("leftModuleId", None)
        rev.pop("rightModuleId", None)
        rev["data"] = rev_tpl.get("data")     # 原样保留
        # ★ Plateau 实测 31 个 param（PORTS.md 只列了前 16 个）⇒ 必须克隆模板
        #   保留完整结构，只覆盖前 16 个已知量纲的值。
        pmap = {q["id"]: q["value"] for q in (rev_tpl.get("params") or [])}
        pmap.update(PLATEAU_PARAMS)
        rev["params"] = [{"id": k, "value": float(pmap[k])}
                         for k in sorted(pmap)]
        p["modules"].append(rev)

        # lead（第 3 路，索引 2）→ 混响；湿声再串回Mixer 的 lead 那一路
        cab(vca_ids[2], 0, rev["id"], 0)       # lead.VCA → Plateau.IN0(Left)
        # ⚠️ pad / sub 都**不进混响**：
        #   · pad 是方波，低频能量极足（李 12:27 手工拔掉过这根线）
        #   · sub 是纯正弦低频，低频进混响必被放大 ⇒ 「轰隆隆」的根源
        #   · lead 是Rings 拨弦，频谱均衡，湿声只留它就够
        reverb_out = rev["id"]
        reverb_lead = True      # 标记：lead 要改走「VCA→混响→Mixer」而不是直连

    mixer_tpl = None
    for m in patchio.read_patch(TPL_MIX)["modules"]:
        if m["model"] == "Mixer":
            mixer_tpl = m
            break
    if mixer_tpl is None:
        raise RuntimeError("在 %s 里找不到 Mixer 可克隆" % TPL_MIX)

    mixer = copy.deepcopy(mixer_tpl)
    mixer["id"] = 9000000000000900
    mixer["pos"] = place("mixer", [58, 1])
    mixer["params"] = [{"id": 0, "value": 0.9}]     # Mixer 只有 1 个总电平 param
    mixer["data"] = mixer_tpl.get("data")   # 原样保留
    p["modules"].append(mixer)

    # ★ v5：lead 不再直连 Mixer，而是「lead.VCA → 混响 → 混响.OUT0 → Mixer.lead路」。
    #   其余各层（pad/bass/decor/sub）**全部不碰混响**，直接进各自 Mixer 路。
    lead_idx = 2
    for i, vca in enumerate(vca_ids):
        src_id = vca
        if i == lead_idx and reverb_lead:
            src_id = reverb_out      # lead 改从混响输出取音
        cab(src_id, 0, mixer["id"], i)   # Mixer 6 路 IN0-5（5 层时用满 5 路）
    # ★ Mixer **只有 OUT0 一个输出口**（PORTS.md L194 + 13 份成功机架反推）。
    #   写 OUT1 = 端口越界 ⇒ 加载即崩（这就是 10-17 崩了 6 次的真元凶）。
    cab(mixer["id"], 0, host_audio["id"], 0)

    out = "%s\\%s.vcv" % (OUT_DIR, name)
    sanitize(p, out)
    patchio.write_patch(out, p)
    return out, len(p["modules"]), len(p["cables"]), vca_ids


def main():
    jobs = [
        ("quadeca_auto_ghostfolk", compose_ghostfolk),
        ("quadeca_auto_scrapyard", compose_scrapyard),
        ("quadeca_auto_life1", compose_life1),
    ]
    # ★ 李 12:27 的硬要求：**绝不要把他手工挪好的布局覆盖回去**。
    #   做法：每次生成都带版本号后缀 ⇒ 新文件新名字，永远不会撞上他改过的那个。
    #   （他挪过的 quadeca_auto_ghostfolk.vcv 保留原样，我不再写它。）
    import datetime
    _ver = datetime.datetime.now().strftime("%H%M")
    made = []                     # 实际生成的带版本号文件名，供下面的自检用
    for nm, fn in jobs:
        nm = "%s__v%s" % (nm, _ver)          # 例：quadeca_auto_ghostfolk__v1258
        # ⚠️ 必须**先清空**再调 compose()：LAYER_ADSR_OVERRIDE 是模块级字典，
        #   scrapyard 设的覆盖会**漏到后面生成的机架**（ghostfolk 先跑所以没事，
        #   但顺序一变就会出错）。每张机架都从干净状态开始。
        LAYER_ADSR_OVERRIDE.clear()
        pats = fn()
        path, nm_mod, nc, _ = build_one(nm, pats)
        total = sum(len(m["notes"]) for p in pats for m in p["measures"])
        print("%-26s modules=%d cables=%d notes=%d -> %s"
              % (nm, nm_mod, nc, total, path))
        made.append((nm, path))

    # --- 参数量自检：param id 不得超过该模型的真实数量 ---
    # 2026-10-17 实测：写越界 param（VCO id:8 只有 8 个）⇒ 加载即崩。
    ok = True
    for nm, path in made:
        p = patchio.read_patch(path)
        for m in p["modules"]:
            cnt = PARAM_COUNT.get(m["model"])
            if cnt is None:
                continue
            bad = [q["id"] for q in m.get("params", []) if q["id"] >= cnt]
            if bad:
                ok = False
                print("  [X] %s %s param id 越界（真实 %d 个）：%s"
                      % (nm, m["model"], cnt, bad))
    print("参数量自检:", "全部通过" if ok else "有问题")

    # --- 端口越界自检（★ 10-17 加载崩溃的真元凶，比 param 越界更隐蔽）---
    import audit_ports
    bad_total = 0
    for nm, path in made:
        bad_total += len(audit_ports.audit(path, verbose=True))
    print("端口越界自检:", "全部通过" if not bad_total
          else "❌ 有 %d 处，必须修完再加载" % bad_total)

    # --- 布局基准自检：确认生成用的是李调过的坐标 ---
    print("布局基准: 采用李的坐标 %d 项 / 回退默认 %d 项%s"
          % (len(set(_HIT)), len(set(_MISS)),
             ("（%s）" % ",".join(sorted(set(_MISS)))) if _MISS else ""))

    # --- 开播状态自检（李 12:39：不要直接开播，要他按一下）---
    # ⚠️ 这里我犯过一次低级错：把 START_PAUSED 直接赋给 running，
    #   START_PAUSED=True 反倒生成了 running=True（照旧自动播）。
    #   ⇒ 生成后必须**回读文件**核对，不能只看代码「我写了」。
    want = not START_PAUSED                # START_PAUSED=True ⇒ 期望 running=False
    bad = []
    for nm, path in made:
        pp = patchio.read_patch(path)
        for m in pp["modules"]:
            if m["model"] != "Clocked":
                continue
            got = (m.get("data") or {}).get("running")
            if got != want:
                bad.append("%s Clocked.running=%s（应为 %s）" % (nm, got, want))
    print("开播状态: %s —— 全部正确"
          % ("加载即静止（李点 RUN 才开播）" if START_PAUSED else "加载即自动开播")
          if not bad else "❌ " + "; ".join(bad))

    # --- BPM 与层数自检 ---
    bad2 = []
    for nm, path in made:
        pp = patchio.read_patch(path)
        for m in pp["modules"]:
            if m["model"] != "Clocked":
                continue
            bpm = next((q["value"] for q in m.get("params", []) if q["id"] == 0), None)
            if bpm != BPM:
                bad2.append("%s BPM=%s（应为 %s）" % (nm, bpm, BPM))
    print("BPM: %s —— 全部正确" % BPM if not bad2 else "❌ " + "; ".join(bad2))


if __name__ == "__main__":
    main()
