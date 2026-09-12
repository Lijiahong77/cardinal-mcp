# -*- coding: utf-8 -*-
"""
layout_patch.py —— Cardinal 机架「排班」工具（模块布局的唯一权威）

排班规则见 ~/.workbuddy/MEMORY.md「Cardinal 机架排班铁律」
--------------------------------------------------------------------
1. `pos[0]`（x）单位是「**格**」，不是像素。1 格 ≈ 1 HP ≈ 15px。
   `pos[1]`（y）单位是「**行号**」（写 `0 / 1 / 2 …`），**不是格**（2026-09-12 15:45 修正）。
2. 行有语义，按信号流自上而下：
      行0 合成器链 ｜ 行1 控制映射+鼓机 ｜ 行2 混音输出+说明牌 ｜ 行3+ 新增区
3. 同行内 x 从 0 起单调递增，列间距 = 模块宽度 + `GAP` 格。
4. 宽度不确定就估大（估小会压住右邻居）。
5. ⚠️ **改 `.vcv` 前必须确认 Cardinal 已关闭** —— 它一按 Ctrl+S 就会把内存状态写回文件，
   覆盖你的改动（2026-09-12 实录：排好的布局被一次保存整个盖掉）。

踩过的坑（2026-09-12）：把新模块 pos 写成 x=300~720（当成像素），
等于放到 4500px 外 —— 界面上「只看到线、看不到模块」。

严重度分级（避免门禁误报，误报比不查更糟）
--------------------------------------------------------------------
  硬错误（退出码 1）：输入口双接、明显重叠（>2 格）、坐标超出视野（|坐标|>200 格）
  提示（不影响退出码）：y 不在行网格上、轻微重叠、轻微负坐标、有模块未登记
  `--strict` 时提示升级为错误

子命令
--------------------------------------------------------------------
  check  <patch>                     只列坐标（诊断，不改文件）
  guard  <patch> [--strict]          【门禁】排班 + 接线双重体检，有硬错误则退出码 1
  widths [--fix]                     复测本机面板宽度，核对 WIDTH_BY_MODEL 是否失真
  apply  <patch> [--push] [--strict] [--no-etext]
                                     重排并写回（自动备份）；未登记模块自动落行
       --push      顺带推进 Cardinal 并复验实时存档
       --strict    出现「自动落行」的模块就拒绝写入（逼自己登记进 LAYOUT）
       --no-etext  不更新说明牌 TextEditor
"""
import json
import os
import re
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import patchio  # noqa: E402

# ---------------------------------------------------------------- 排班常量
# 【2026-09-12 15:45 修正：y 的单位是「行号」，不是「格」】
#   证据：本机 20 个官方模板/示例，**即便 39 模块的多行机架，y 也全落在 -1 ~ 2**；
#         Cardinal 保存 helm_full.vcv 后 y 正是 0/1/2。
#   → 写 y 就写 0 / 1 / 2 / 3…；早期写成 y=34/68（当格用）是**错的**。
#   ⚠️ 未解疑点：早期写 y=0/34/68 时李却看到正常三行 -> 推测 Cardinal 加载时会做
#      「格 -> 行」吸附（读格、写行号，读写不对称）。待实测确认（见 HANDOFF 约束 31）。
#
# 【屏幕容量，3200x2000 @200% DPI】
#   zoom=1 时 1 格 = 20 物理px，窗口可用约 160 格宽 x 88 格高（扣掉工具栏）。
#   1 行占高 ≈ 25.3 格（模块高）-> 3 行 ≈ 98 格 = 1960 物理px 会顶满屏幕，
#   于是鼓落到中下部、「全在很下面」。=> 铁律：纵向排 2 行以内。
GAP = 2            # 列间隙（格）。两行要装下 20 个模块，间隙必须收紧
ROW_H = 34         # 【只用于估屏幕占用】1 行 ≈ 34 格；**布局输出用行号，别乘它**
GRID_PER_ROW = 34  # 行 -> 格的换算系数（仅估算屏幕高度用）
MAX_ROWS_FOR_SCREEN = 2   # 一屏能舒服放下的行数上限（超过就要缩放视图）

# 门禁阈值
OVERLAP_TOL = 2    # 格。≤ 这个值的重叠视为宽度估值误差，只提示
VIEW_LIMIT = 200   # 格。|x| 或 |y| 超过它 = 模块在默认视野外（200 格 ≈ 3000px）
NEG_X_TOL = 8      # 格。x 轻微为负（如 TextEditor 挂 -3）可接受

ROW_NAMES = {0: "合成器链+控制+输出", 1: "说明牌+鼓机+混音台"}


def row_y(row):
    """行号 -> y 坐标（**单位就是行号本身**）。

    ⚠️ 2026-09-12 15:45 修正：`.vcv` 里 `pos[1]` 的单位是「行号」不是「格」。
    证据：本机 20 个官方模板/示例，**即便 39 模块的多行机架，y 也全落在 -1 ~ 2**；
         Cardinal 保存 helm_full.vcv 后 y 正是 **0/1/2**。
    → 直接返回 `row`，**不要乘 ROW_H**（乘了会把模块扔到第 34 行的荒野，
      比写成像素更隐蔽：文件里看着"有值"，界面上却什么都没有）。
    """
    return row


def row_name(row):
    return ROW_NAMES.get(row, "新增区")

# ---------------------------------------------------------------- 宽度表
# 【实测值，不是猜的】来源：Cardinal 安装目录里的**面板 SVG**。
# Rack 用面板 SVG 的物理尺寸决定模块宽度：1 HP = 5.08mm，而 1 格 = 1 HP = 15px。
# 复测命令：`python layout_patch.py widths`
#
# 键必须是「插件/模块」—— 不同插件会重名（别的插件也有 VCO.svg，宽 27 HP），
# 只按文件名查会串味，这个坑 2026-09-12 自检时踩到过。
#
# 实测纠正的早期误估（记档，避免再错）：
#   HostMIDIGate  10 → 14     HostMIDI        10 → 9      MixMasterJr  60 → 36
#   Plateau       16 → 12     OpenHiHat        7 → 9      Fundamental/Mixer 6 → 3
#   鼓模块通用     7 → 6
RESOURCES = r"C:\Program Files\Cardinal-win64-26.02\Cardinal.lv2\resources"
HP_MM = 5.08        # 1 HP 的毫米数
PX_PER_HP = 15.0    # 1 HP = 1 格 = 15px

# patch 里的 plugin slug ≠ 安装目录名，查到目录要过这一层
PLUGIN_DIR = {
    "Valley": "ValleyAudio",
    "rcm": "rcm-modules",
    "AriaSalvatrice": "AriaModules",
    "Bogaudio": "BogaudioModules",
    "Wasted_Audio": "WSTD-Drums",
}

WIDTH_BY_PLUGIN_MODEL = {
    # ---- Cardinal 自家 ----
    "Cardinal/HostMIDI": 9,
    "Cardinal/HostMIDIMap": 11,
    "Cardinal/HostMIDIGate": 14,
    "Cardinal/HostMIDICC": 14,
    "Cardinal/HostParameters": 9,
    "Cardinal/HostParametersMap": 11,
    "Cardinal/HostAudio": 8,
    "Cardinal/HostAudio2": 8,          # 与 HostAudio 共用面板
    "Cardinal/HostTime": 8,
    "Cardinal/HostCV": 8,
    "Cardinal/ExpanderMIDI": 3,
    "Cardinal/Blank": 9,
    "Cardinal/Carla": 9,
    # ---- Fundamental ----
    "Fundamental/VCO": 9,
    "Fundamental/WTVCO": 7,
    "Fundamental/VCF": 7,
    "Fundamental/ADSR": 9,
    "Fundamental/VCA-1": 3,
    "Fundamental/VCA": 5,
    "Fundamental/VCMixer": 9,
    "Fundamental/Sum": 3,
    "Fundamental/Mixer": 3,
    "Fundamental/Noise": 3,
    "Fundamental/LFO": 9,
    "Fundamental/WTLFO": 7,
    "Fundamental/8vert": 8,
    "Fundamental/Scope": 13,
    # ---- Valley ----
    "ValleyAudio/Plateau": 12,
    # ---- MindMeldModular ----
    "MindMeldModular/MixMasterJr": 36,
    "MindMeldModular/MixMaster": 61,
    # ---- WSTD-Drums ----
    "WSTD-Drums/BassDrum9": 6,
    "WSTD-Drums/SnareDrumN": 6,
    "WSTD-Drums/ClosedHiHat": 6,
    "WSTD-Drums/OpenHiHat": 9,
    "WSTD-Drums/Tomi": 6,
    "WSTD-Drums/DMX": 6,
    "WSTD-Drums/CR78": 6,
    "WSTD-Drums/Baronial": 6,
    "WSTD-Drums/SyntheticBassDrum": 9,
    "WSTD-Drums/Gnome": 9,
    "WSTD-Drums/MarionetteBass": 15,
    "WSTD-Drums/Sequencer": 32,
}

# 面板文件名与 model 不同名时的对照（自检 `widths` 用）
SVG_ALIAS = {
    ("WSTD-Drums", "BassDrum9"): "bd9",
    ("WSTD-Drums", "SnareDrumN"): "snare",
    ("WSTD-Drums", "ClosedHiHat"): "closedhh",
    ("WSTD-Drums", "OpenHiHat"): "openhh",
    ("WSTD-Drums", "SyntheticBassDrum"): "sbd",
    ("WSTD-Drums", "MarionetteBass"): "marionette",
    ("Cardinal", "HostAudio2"): "hostaudio",
    ("Cardinal", "HostParametersMap"): "hostparamsmap",
    ("ValleyAudio", "Plateau"): "plateaupaneldark",
    ("MindMeldModular", "MixMasterJr"): "mixmaster-jr",
}

DRUM_WIDTH = 6      # 未列出的 WSTD 鼓模块兜底（实测多数 6 HP）
DEFAULT_WIDTH = 10  # 完全未知时的兜底（宁大不小）


def norm_plugin(p):
    """patch 里的 plugin slug -> 安装目录名。"""
    return PLUGIN_DIR.get(p, p)

# WSTD-Drums 全部 model（用于判断「鼓」）
DRUM_MODELS = {
    "BassDrum9", "SyntheticBassDrum", "MarionetteBass", "SnareDrumN",
    "ClosedHiHat", "OpenHiHat", "Tomi", "Toms", "CR78", "DMX",
    "Baronial", "Gnome", "Sequencer",
}

# ---------------------------------------------------------------- 登记表
# 已登记的模块：id -> (行号, 宽度)。登记过的按表中顺序落位。
# 没登记的不会丢，apply 会自动分类落行（并把它们报出来）。
#
# 【2 行布局，2026-09-12 依据屏幕实测重排】
#   原来 3 行（0/1/2）总高 98 格 = 1960 物理px，把 2000px 高的屏幕顶满，
#   鼓落在中下部，用户反馈「鼓什么的还是全在很下面」。
#   压成 2 行后总高 64 格 = 1280 物理px，留出余量。
#   行0 = 合成器 + 控制映射 + 输出（x 到 110 格）
#   行1 = 说明牌 + 鼓机 + 混音台    （x 到 122 格）
LAYOUT = [
    # ---------------- 第 0 行：合成器链 + 控制 + 输出 ----------------
    ("2",                  0, 9),    # HostMIDI      9 HP —— 只收 ch1 琴键
    ("3",                  0, 9),    # VCO           9
    ("4",                  0, 7),    # VCF           7
    ("5",                  0, 9),    # ADSR          9
    ("6",                  0, 3),    # VCA-1         3
    ("7",                  0, 3),    # Sum           3
    ("8",                  0, 12),   # Plateau      12
    ("799138358763949",    0, 11),   # HostMIDIMap  11 —— CC20-27 -> 8 个参数
    ("100",                0, 14),   # HostMIDIGate 14 —— 鼓垫 Note -> 门
    ("9",                  0, 8),    # HostAudio2    8 —— 主输出
    # ---------------- 第 1 行：说明牌 + 鼓机 + 混音台 ----------------
    ("1",                  1, 26),   # TextEditor   26（机架地图）
    ("101",                1, 6),    # BassDrum9     6
    ("102",                1, 6),    # SnareDrumN    6
    ("103",                1, 6),    # ClosedHiHat   6
    ("104",                1, 9),    # OpenHiHat     9（比其它鼓宽）
    ("105",                1, 6),    # Tomi          6
    ("106",                1, 6),    # DMX           6
    ("107",                1, 3),    # Mixer         3（鼓总线 A）
    ("108",                1, 3),    # Mixer         3（鼓总线 B）
    ("3130453735965577",   1, 36),   # MixMasterJr  36（8 轨混音台，实测 36 HP）
]

# 说明牌文本（写进 TextEditor 的 data.etext）。宽度 26 格 ~ 65 字符，别超。
ETEXT = """HELM FULL - keyboard fully wired
================================

[ROW 1] SYNTH + CONTROL
HostMIDI(ch1 keys) -> VCO -> VCF
  -> VCA -> Sum -> Plateau
  -> HostAudio2 (main out)
HostMIDIMap  CC20-27 -> 8 params
HostMIDIGate pad Note48-55 -> gates
ADSR opens VCA + sweeps filter

[ROW 2] DRUMS + MIX
6 drums -> MixerA/B -> MixMaster
  trk2 / trk3
MixMasterJr trk1 = synth
MixMasterJr -> HostAudio2

KNOBS  1 bright  2 reso  3 wet
       4 decay  5 attack  6 release
       7 pulse  8 drive
PADS   1 BD-A  2 BD-B  3 SD-A  4 SD-B
       5 CH  6 OH  7 tom  8 DMX

! Do NOT press KNOB-B before
  turning knobs. It switches to
  pitch-bend, which Cardinal
  cannot map.
"""


# ================================================================ 基础工具
def sid(x):
    """模块 id 在 patch 里可能是 int 也可能是 str，统一成 str 比较。"""
    return str(x)


def estimate_width(m):
    """查「插件/模块」宽度表（实测值）。TextEditor 读它自己的 data.width。"""
    model = m.get("model", "")
    plugin = norm_plugin(m.get("plugin", ""))
    if model == "TextEditor":
        try:
            return float((m.get("data") or {}).get("width") or 26)
        except (TypeError, ValueError):
            return 26
    w = WIDTH_BY_PLUGIN_MODEL.get(plugin + "/" + model)
    if w is not None:
        return w
    if plugin == "WSTD-Drums" or model in DRUM_MODELS:
        return DRUM_WIDTH
    return DEFAULT_WIDTH


def classify_row(m):
    """未登记模块该放哪一行（按模块角色猜）。只有 2 行。"""
    model = m.get("model", "")
    if model in ("HostMIDIMap", "HostParametersMap", "HostMIDIGate"):
        return 1
    if m.get("plugin") == "WSTD-Drums" or model in DRUM_MODELS:
        return 1
    if model in ("TextEditor", "MixMasterJr", "MixMaster"):
        return 1
    if model in ("HostAudio", "HostAudio2"):
        return 1
    return 0


def on_grid(y):
    """y 是否落在整数行号上（0/1/2…）。

    ⚠️ 2026-09-12 修正：y 的单位是「行号」不是「格」，旧版按 34 的倍数判断是错的。
    """
    return abs(y - round(y)) < 1e-3


def resolved_pos(m):
    p = m.get("pos") or [0, 0]
    try:
        return float(p[0]), float(p[1])
    except (TypeError, ValueError, IndexError):
        return 0.0, 0.0


# ================================================================ 排班核心
def do_layout(d):
    """算出新坐标。

    返回 (新坐标表 {id: [x, y]}, 已登记 id 集合, 未登记模块列表, 日志行)
    """
    mods = d.get("modules", [])
    by = {sid(m["id"]): m for m in mods}
    widths = {mid: estimate_width(m) for mid, m in by.items()}

    declared = {}          # id -> (行, 宽度)
    missing = []
    for mid, row, w in LAYOUT:
        if mid not in by:
            missing.append(mid)
            continue
        declared[mid] = (row, w)

    # 未登记模块：按角色分行，行内保持原来的相对次序（y 再 x 再 id）
    unregistered = [m for m in mods if sid(m["id"]) not in declared]
    unregistered.sort(key=lambda m: (resolved_pos(m)[1], resolved_pos(m)[0],
                                     sid(m["id"])))

    rows = {}              # 行号 -> [(id, 宽度, 是否登记)]
    for mid, (row, w) in declared.items():
        rows.setdefault(row, []).append((mid, w, True))
    for m in unregistered:
        mid = sid(m["id"])
        rows.setdefault(classify_row(m), []).append((mid, widths[mid], False))

    out = {}
    log = []
    if missing:
        log.append("  [警告] 登记表里有 %d 个模块不在机架中: %s" % (len(missing), missing))

    for row in sorted(rows):
        x = 0.0
        auto_here = []
        for mid, w, is_declared in rows[row]:
            out[mid] = [x, row_y(row)]
            if not is_declared:
                auto_here.append(mid)
            x += w + GAP
        span = x - GAP if rows[row] else 0
        note = "  ← 自动落行: %s" % auto_here if auto_here else ""
        log.append("  行 %d（%s）: %d 个模块, 跨度 0 ~ %.0f 格%s"
                   % (row, row_name(row), len(rows[row]), span, note))

    return out, set(declared), unregistered, log


# ================================================================ 对比检查
def check_overlap(pos, widths, tol=0):
    """同行重叠检查。tol = 容差（格），返回 (严重, 轻微)。"""
    hard, soft = [], []
    rows = {}
    for mid, (x, y) in pos.items():
        rows.setdefault(y, []).append((x, widths.get(mid, DEFAULT_WIDTH), mid))
    for y in sorted(rows):
        items = sorted(rows[y])
        for i in range(1, len(items)):
            px, pw, pm = items[i - 1]
            cx, cw, cm = items[i]
            over = px + pw - cx
            if over > tol:
                hard.append("y=%.0f 行 %s(x=%.0f,w≈%.0f) 压住 %s(x=%.0f)，重叠 %.0f 格 ≈ %.0f px"
                            % (y, pm, px, pw, cm, cx, over, over * 15))
            elif over > 0:
                soft.append("y=%.0f 行 %s 与 %s 仅隔 %.0f 格（可能是宽度估值误差）"
                            % (y, pm, cm, over))
    return hard, soft


def check_view(pos):
    """检查是否跑出默认视野。返回 (严重, 轻微)。"""
    hard, soft = [], []
    for mid, (x, y) in pos.items():
        if abs(x) > VIEW_LIMIT or abs(y) > VIEW_LIMIT:
            hard.append("%s 的 pos=(%.0f, %.0f) 超出默认视野（|坐标|>%d 格 ≈ %dpx）"
                        "—— 界面上看不到这个模块"
                        % (mid, x, y, VIEW_LIMIT, VIEW_LIMIT * 15))
        elif x < -NEG_X_TOL:
            hard.append("%s 的 x=%.0f 偏出视野左侧 %.0f px" % (mid, x, -x * 15))
        elif x < 0 or y < 0:
            soft.append("%s 的 pos=(%.0f, %.0f) 有负分量（幅度小，一般无碍）"
                        % (mid, x, y))
    return hard, soft


def check_grid(pos):
    """检查 y 是否都在整数行号上（0/1/2…）。"""
    return ["%s 的 y=%.2f 不是整数行号（y 单位是「行」不是「格」，写 0/1/2…）"
            % (mid, y)
            for mid, (x, y) in sorted(pos.items()) if not on_grid(y)]


# ================================================================ 接线自查
def check_input_dupes(d):
    """列出被多根线占用的输入口（Cardinal 只保留第一根，其余静默丢弃）。"""
    from collections import defaultdict
    ins = defaultdict(list)
    for c in d.get("cables", []):
        ins[(sid(c["inputModuleId"]), c["inputId"])].append(
            (sid(c["outputModuleId"]), c["outputId"]))
    return {k: v for k, v in ins.items() if len(v) > 1}


def report_input_dupes(d, by):
    dup = check_input_dupes(d)
    lines = []
    for (mid, port), srcs in sorted(dup.items(), key=lambda x: str(x[0])):
        name = by.get(mid, {}).get("model", mid)
        lines.append("  %s(id=%s) IN%s ← %d 根: %s"
                     % (name, mid, port, len(srcs), srcs))
    return lines


def analyze(d, strict=False):
    """排班 + 接线统一体检。返回 (硬错误列表, 提示列表)。

    分级依据：硬错误 = 一定会坏（看不到 / 压住 / 丢线）；
    提示 = 不合规范但暂时能用（行不对齐、轻微重叠、未登记）。strict 把提示升级为错误。
    """
    mods = d.get("modules", [])
    by = {sid(m["id"]): m for m in mods}
    widths = {sid(m["id"]): estimate_width(m) for m in mods}
    pos = {sid(m["id"]): resolved_pos(m) for m in mods}

    hard, soft = [], []

    vh, vs = check_view(pos)
    hard += vh
    soft += vs

    soft += check_grid(pos)

    oh, os_ = check_overlap(pos, widths, tol=OVERLAP_TOL)
    hard += oh
    soft += os_

    # 输入口双接 = 真 bug（静默丢线），无论如何都是硬错误
    for line in report_input_dupes(d, by):
        hard.append("输入口双接: " + line.strip())

    # 未登记模块
    declared = {mid for mid, _r, _w in LAYOUT}
    unreg = [m for m in mods if sid(m["id"]) not in declared]
    if unreg:
        names = ["%s(%s)" % (m.get("model"), m["id"]) for m in unreg]
        soft.append("有 %d 个模块未登记进 LAYOUT（apply 会自动落行，但顺序不稳定）: %s"
                    % (len(unreg), names))

    if strict:
        hard += soft
        soft = []
    return hard, soft


# ================================================================ 面板实测
def scan_panel_svgs(resources=RESOURCES):
    """扫本机面板 SVG，返回 {插件目录名: {小写面板名: 宽度HP}}。

    原理：Rack 用面板 SVG 的物理尺寸决定模块宽度（1 HP = 5.08mm）。
    **必须按插件分组** —— 不同插件会重名（多个插件都有 VCO.svg）。
    """
    out = {}
    if not os.path.isdir(resources):
        return out
    for plugin in sorted(os.listdir(resources)):
        pdir = os.path.join(resources, plugin)
        if not os.path.isdir(pdir):
            continue
        panels = {}
        for dp, _dn, fn in os.walk(pdir):
            for f in fn:
                if not f.lower().endswith(".svg"):
                    continue
                try:
                    with open(os.path.join(dp, f), encoding="utf-8",
                              errors="replace") as fh:
                        head = fh.read(2000)
                except OSError:
                    continue
                m = re.search(r"<svg[^>]*>", head, re.S)
                if not m:
                    continue
                tag = m.group(0)
                mm = re.search(r'width="([0-9.]+)\s*mm"', tag)
                px = re.search(r'width="([0-9.]+)\s*(?:px)?"', tag)
                if mm:
                    panels[f[:-4].lower()] = float(mm.group(1)) / HP_MM
                elif px:
                    panels[f[:-4].lower()] = float(px.group(1)) / PX_PER_HP
        if panels:
            out[plugin] = panels
    return out


def cmd_widths():
    """复测面板宽度，核对表里的值是否还准。"""
    tree = scan_panel_svgs()
    print("=" * 66)
    print("面板实测宽度（1 HP = %.2fmm = 1 格 = %.0fpx）" % (HP_MM, PX_PER_HP))
    print("来源:", RESOURCES)
    if not tree:
        print("  [错误] 没扫到面板 SVG（路径变了？）")
        return 1
    total = sum(len(v) for v in tree.values())
    print("  扫到 %d 个插件 / %d 个面板" % (len(tree), total))
    print("-" * 66)
    bad, missing = 0, 0
    for key, want in sorted(WIDTH_BY_PLUGIN_MODEL.items()):
        plugin, model = key.split("/", 1)
        stem = SVG_ALIAS.get((plugin, model), model.lower())
        got = tree.get(plugin, {}).get(stem)
        if got is None:
            print("   %-34s 表内 %5.1f   面板未找到（面板名可能是 %s.svg，加进 SVG_ALIAS）"
                  % (key, want, stem))
            missing += 1
        elif abs(got - want) > 0.05:
            print("   %-34s 表内 %5.1f   !! 面板实测 %.1f —— 表已失真，请更新"
                  % (key, want, got))
            bad += 1
    print("-" * 66)
    if not bad and not missing:
        print("结论: 全部一致（%d 项）" % len(WIDTH_BY_PLUGIN_MODEL))
        return 0
    print("结论: 失真 %d 项，未找到 %d 项" % (bad, missing))
    return 1 if bad else 0


# ================================================================ 子命令
def check_file(path):
    """只列坐标，不改文件。"""
    d = patchio.read_patch(path)
    mods = d.get("modules", [])
    widths = {sid(m["id"]): estimate_width(m) for m in mods}
    print("=" * 66)
    print("%s | 模块 %d | zoom %s" % (os.path.basename(path), len(mods), d.get("zoom")))
    for m in sorted(mods, key=lambda x: (resolved_pos(x)[1], resolved_pos(x)[0])):
        print("   pos=%-14s %-34s w≈%-3.0f %s"
              % (json.dumps(m.get("pos")), m["plugin"] + "/" + m["model"],
                 widths[sid(m["id"])], m["id"]))
    xs = [resolved_pos(m)[0] for m in mods]
    ys = [resolved_pos(m)[1] for m in mods]
    if xs:
        print("   x 范围 %.0f ~ %.0f (跨 %.0f 格 ≈ %.0f px)"
              % (min(xs), max(xs), max(xs) - min(xs), (max(xs) - min(xs)) * 15))
        print("   y 范围 %.0f ~ %.0f" % (min(ys), max(ys)))
    return 0


def guard_file(path, strict=False):
    """门禁：排班 + 接线双重体检。有硬错误 -> 返回 1。"""
    d = patchio.read_patch(path)
    mods = d.get("modules", [])
    hard, soft = analyze(d, strict=strict)

    target, _declared, _unreg, log = do_layout(d)
    actual = {sid(m["id"]): resolved_pos(m) for m in mods}
    drift = [mid for mid in target
             if mid not in actual
             or abs(target[mid][0] - actual[mid][0]) > 0.5
             or abs(target[mid][1] - actual[mid][1]) > 0.5]

    print("=" * 66)
    print("排班门禁 | %s | 模块 %d | 线缆 %d"
          % (os.path.basename(path), len(mods), len(d.get("cables", []))))
    print("重排目标（跑 apply 会得到这个）:")
    for line in log:
        print(line)
    if drift:
        print("当前文件与重排目标相差 %d 个模块的位置（不算错，跑 apply 可对齐）:"
              % len(drift))
        for mid in drift:
            name = next((m.get("model") for m in mods if sid(m["id"]) == mid), mid)
            print("   %s(%s): 现在 %s → 目标 [%.0f, %.0f]"
                  % (name, mid, list(actual.get(mid, [])), target[mid][0], target[mid][1]))
    else:
        print("当前文件与重排目标：完全一致")
    print("-" * 66)
    for w in soft:
        print("[提示] " + w)
    if hard:
        for e in hard:
            print("[不过] " + e)
        print("-" * 66)
        print("结论: 不通过（硬错误 %d 项，提示 %d 项）" % (len(hard), len(soft)))
        return 1
    print("结论: 通过" + ("（有 %d 项提示）" % len(soft) if soft else ""))
    return 0


def apply_file(path, push=False, strict=False, write_etext=True):
    if not os.path.exists(path):
        print("[错误] 文件不存在:", path)
        return 1
    d = patchio.read_patch(path)
    mods = d.get("modules", [])
    widths = {sid(m["id"]): estimate_width(m) for m in mods}

    # 备份
    bak = path[:-4] + "_before_layout_%s.vcv" % time.strftime("%H%M%S")
    shutil.copy2(path, bak)
    print("[备份]", os.path.basename(bak))

    pos, _declared, unreg, log = do_layout(d)
    print("布局计算:")
    for line in log:
        print(line)

    # 排班自己产的坐标一定是网格对齐的，这里查的是「还有没有残留问题」
    hard, soft = check_overlap(pos, widths, tol=OVERLAP_TOL)
    soft += check_grid(pos)
    if hard:
        print("[重叠错误]")
        for b in hard:
            print("   ", b)
    else:
        print("[重叠检查] 通过，无重叠")

    if unreg and strict:
        print("[不过 --strict] 有 %d 个模块未登记进 LAYOUT，拒绝写入:" % len(unreg))
        for m in unreg:
            print("   %s/%s id=%s" % (m.get("plugin"), m.get("model"), m["id"]))
        print("   请把它们加进 layout_patch.py 的 LAYOUT 表（id, 行, 宽度）")
        return 1

    by = {sid(m["id"]): m for m in mods}
    for mid, p in pos.items():
        by[mid]["pos"] = p

    # 更新说明牌（只动我们自己的牌子，不覆盖别人写的笔记）
    te = next((m for m in mods if m.get("model") == "TextEditor"), None)
    if te is not None:
        if not write_etext:
            print("[说明牌] 按 --no-etext 跳过")
        else:
            old = (te.get("data") or {}).get("etext") or ""
            if old and "HELM FULL" not in old:
                print("[说明牌] 检测到非本机架的自定义文本，保持不动（%d 字符）" % len(old))
            else:
                te.setdefault("data", {})
                te["data"]["etext"] = ETEXT
                te["data"]["width"] = 26
                print("[说明牌] TextEditor(id=%s) 文本已更新，%d 字符"
                      % (te["id"], len(ETEXT)))

    patchio.write_patch(path, d)
    print("[写入]", path, "(%d 模块)" % len(mods))

    dup = report_input_dupes(d, by)
    if dup:
        print("[!!] 输入口双接未解决（Cardinal 会丢掉多余的线）:")
        for line in dup:
            print("   ", line)
        print("     → 接线不归排班工具管，用 fix_drum_bus.py report 定位后手工改线")
    else:
        print("[接线检查] 通过，没有输入口双接")

    if push:
        import cardinal_mcp as cm
        name = os.path.basename(path)
        print("[推送] load_patch", name)
        print("   ", cm.load_patch(name))
        time.sleep(4)
        live, _ = cm.live_patch_path()
        d2 = patchio.read_patch(live)
        print("[验证] 实时存档模块数 =", len(d2["modules"]))
        for m in sorted(d2["modules"], key=lambda x: (resolved_pos(x)[1], resolved_pos(x)[0])):
            print("   pos=%-14s %-34s %s"
                  % (json.dumps(m["pos"]), m["plugin"] + "/" + m["model"], m["id"]))
    return 1 if dup else 0


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)
    cmd = args[0]
    if cmd == "widths":
        sys.exit(cmd_widths())
    if len(args) < 2:
        print(__doc__)
        sys.exit(1)
    target = args[1]
    if cmd == "check":
        sys.exit(check_file(target))
    elif cmd == "guard":
        sys.exit(guard_file(target, strict="--strict" in args))
    elif cmd == "apply":
        sys.exit(apply_file(target,
                            push="--push" in args,
                            strict="--strict" in args,
                            write_etext="--no-etext" not in args))
    else:
        print(__doc__)
        sys.exit(1)
