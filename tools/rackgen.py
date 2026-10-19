# -*- coding: utf-8 -*-
"""
rackgen.py — 12 个 make_* 生成器共用的 DSL（批次 A7 提炼）。

来源（函数体逐字取自原文件，血泪注释原样保留，不凭记忆重写逻辑）：
  * cable / mod / clone / note / track / Row / save      ← make_quadeca.py:30-108
  * place / LAYOUT（布局主权归李）                         ← make_quadeca_auto.py:67-91
  * midi / build_notes / pattern（休止符占位两条硬规则）     ← make_quadeca_auto.py:93-136
  * sanitize / _guard（悬空面包屑 + 同口多线两大血泪）       ← make_quadeca_auto.py:388-462

迁移约定：**新的** make_* 一律 `import rackgen`；存量 12 个 make_* 已验收，
等各自下次被改动时再迁，不一次性改写（宪法：改错比不改更糟）。
"""
import copy
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import patchio  # noqa: E402  (同目录 .vcv 读写)

OUTDIR = r"D:\Cardinal\patches"
GAP = 2
ZOOM = 0.75
VERSION_TOP = "2.4.1"   # 顶层 version（与 Cardinal 本机存档一致）
VERSION_MODULE = "2.0"  # 模块 version，必须是字符串

# ---------------------------------------------------------------- 基础件
# （原 make_quadeca.py:31-78，逐字保留）
_cable_id = [900000000]


def reset_ids(start=900000000):
    """新机架开头调一次：线缆 id 从 start 重新编号（同进程连生成多张防撞）。"""
    _cable_id[0] = start


def cable(out_m, out_p, in_m, in_p, color=None):
    _cable_id[0] += 1
    c = {
        "id": _cable_id[0],
        "outputModuleId": out_m,
        "outputId": out_p,
        "inputModuleId": in_m,
        "inputId": in_p,
    }
    if color:
        c["color"] = color
    return c


def mod(plugin, model, mid, pos, params=None, data=None, version=VERSION_MODULE):
    m = {"id": mid, "plugin": plugin, "model": model, "version": version,
         "params": [], "data": {}, "pos": pos}
    if params is not None:
        m["params"] = [{"id": i, "value": float(v)} for i, v in enumerate(params)]
    if data is not None:
        m["data"] = data
    return m


def clone(src, model, mid, pos, params=None, data_patch=None, keep_data=True):
    """从已验收机架 deepcopy 一个模块，只改 id/pos，可选覆盖 params / 增量改 data。

    🔴 deepcopy 后残留的 leftModuleId/rightModuleId 面包屑由 sanitize() 统一清洗
    （血泪：id 改了面包屑还指旧 id → 链断裂 → 加载即崩，见 sanitize 注释）。
    """
    m = copy.deepcopy(next(x for x in src["modules"] if x["model"] == model))
    m["id"] = mid
    m["pos"] = list(pos)
    if params is not None:
        m["params"] = [{"id": i, "value": float(v)} for i, v in enumerate(params)]
    if data_patch is not None:
        if not keep_data:
            m["data"] = dict(data_patch)
        else:
            m["data"].update(data_patch)
    return m


def note(step, pitch, length=1, vel=0.5):
    return {"step": step, "length": length, "pitch": pitch, "velocity": vel}


def track(label, notes, mute=False, measures=4):
    return {"label": label, "mute": mute, "measures": measures, "notes": notes}


class Row:
    """行排班器：x 单调递增，间距 = 宽 + GAP。"""

    def __init__(self, row):
        self.row = row
        self.x = 0.0

    def place(self, width):
        pos = [self.x, self.row]
        self.x += width + GAP
        return pos


def save(name, modules, cables, etext_id=None, etext=None, zoom=ZOOM,
         outdir=OUTDIR, version=VERSION_TOP):
    d = {
        "version": version,
        "path": os.path.join(outdir, name + ".vcv"),
        "zoom": zoom,
        "gridOffset": [0.0, 0.0],
        "modules": modules,
        "cables": cables,
    }
    if etext_id is not None:
        # TextEditor 说明牌
        te = next(m for m in modules if m["id"] == etext_id)
        te["data"] = {"filepath": "", "lang": "None", "etext": etext, "width": 26}
    path = os.path.join(outdir, name + ".vcv")
    sanitize(d, path)
    patchio.write_patch(path, d)
    return path


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


def layout_report():
    """本次生成的布局命中报告：{'his': [...], 'default': [...]}。"""
    return {"his": list(_HIT), "default": list(_MISS)}


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


# ---------------------------------------------------------------- 骨架
def sanitize(patch, path):
    """保存前清洗。

    ★ 真正元凶（2026-10-17 定位）：leftModuleId / rightModuleId 是 Rack 用来给
      模块排序的「面包屑」链。deepcopy 模板后改了 id，却没清这两个字段，
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
