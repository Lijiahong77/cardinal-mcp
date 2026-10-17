# -*- coding: utf-8 -*-
"""生成一张极简探针机架：Gnome + Sequencer + 1 块鼓 + Mixer + 输出。
只用于验证「WSTD 鼓机 + Sequencer 自动演奏」这条链本身安全，
避免拿完整机架去试错导致 Cardinal 反复崩溃。
所有模块从已验收机架原样克隆，只改 id / pos / tracks。
"""
import copy
import sys

sys.path.insert(0, r"D:\Cardinal\tools")
import patchio

CLOCK = patchio.read_patch(r"D:\Cardinal\patches\Final Patch Work.vcv")
DRUM = patchio.read_patch(r"D:\Cardinal\patches\helm_full.vcv")
MIX = patchio.read_patch(r"D:\Cardinal\patches\demo_S4_sampling.vcv")


def find(p, model):
    for m in p["modules"]:
        if m["model"] == model:
            return m
    raise KeyError(model)


gnome = copy.deepcopy(find(CLOCK, "Gnome"))
gnome["id"] = 9600000000000001
gnome["pos"] = [0, 0]

seq = copy.deepcopy(find(CLOCK, "Sequencer"))
seq["id"] = 9600000000000002
seq["pos"] = [20, 0]
d = dict(seq["data"])
t = [[[False] * 8 for _ in range(16)] for _ in range(17)]
p0 = t[0]
for s in (0, 4, 8, 12):
    p0[s][0] = True          # 底鼓四踩
p0[4][1] = True              # 军鼓第 2 拍
for s in range(0, 16, 2):
    p0[s][2] = True          # 闭镲 8 分
d["tracks"] = t
d["running"] = True
d["cycling"] = True
seq["data"] = d

bd = copy.deepcopy(find(DRUM, "BassDrum9"))
bd["id"] = 9600000000000003
bd["pos"] = [40, 0]
bd["data"] = bd.get("data")            # 原样保留（关键）

sn = copy.deepcopy(find(DRUM, "SnareDrumN"))
sn["id"] = 9600000000000004
sn["pos"] = [40, 1]
sn["data"] = sn.get("data")

hh = copy.deepcopy(find(DRUM, "ClosedHiHat"))
hh["id"] = 9600000000000005
hh["pos"] = [54, 1]
hh["data"] = hh.get("data")

mx = copy.deepcopy(find(MIX, "Mixer"))
mx["id"] = 9600000000000006
mx["pos"] = [68, 1]
mx["data"] = mx.get("data")

from_final = copy.deepcopy(find(CLOCK, "HostAudio2")) \
    if any(m["model"] == "HostAudio2" for m in CLOCK["modules"]) else None
if from_final is None:
    ha = {"id": 9600000000000007, "plugin": "Cardinal", "model": "HostAudio2",
          "version": "2.1.2", "params": [{"id": 0, "value": 0.0}],
          "data": {"dcFilter": True}, "pos": [72, 1]}
else:
    ha = from_final
    ha["id"] = 9600000000000007
    ha["pos"] = [72, 1]

modules = [gnome, seq, bd, sn, hh, mx, ha]
ids = {gnome["id"]: "Gnome", seq["id"]: "Sequencer", bd["id"]: "BassDrum9",
       sn["id"]: "SnareDrumN", hh["id"]: "ClosedHiHat",
       mx["id"]: "Mixer", ha["id"]: "HostAudio2"}
rev = {v: k for k, v in ids.items()}

cables = [
    {"id": 9600000000001001, "outputModuleId": rev["Gnome"],
     "outputId": 6, "inputModuleId": rev["Sequencer"], "inputId": 0, "color": ""},
    {"id": 9600000000001002, "outputModuleId": rev["Sequencer"],
     "outputId": 0, "inputModuleId": rev["BassDrum9"], "inputId": 16, "color": ""},
    {"id": 9600000000001003, "outputModuleId": rev["Sequencer"],
     "outputId": 1, "inputModuleId": rev["SnareDrumN"], "inputId": 16, "color": ""},
    {"id": 9600000000001004, "outputModuleId": rev["Sequencer"],
     "outputId": 2, "inputModuleId": rev["ClosedHiHat"], "inputId": 16, "color": ""},
    {"id": 9600000000001005, "outputModuleId": rev["BassDrum9"],
     "outputId": 0, "inputModuleId": rev["Mixer"], "inputId": 0, "color": ""},
    {"id": 9600000000001006, "outputModuleId": rev["SnareDrumN"],
     "outputId": 0, "inputModuleId": rev["Mixer"], "inputId": 1, "color": ""},
    {"id": 9600000000001007, "outputModuleId": rev["ClosedHiHat"],
     "outputId": 0, "inputModuleId": rev["Mixer"], "inputId": 2, "color": ""},
    {"id": 9600000000001008, "outputModuleId": rev["Mixer"],
     "outputId": 0, "inputModuleId": rev["HostAudio2"], "inputId": 0, "color": ""},
    {"id": 9600000000001009, "outputModuleId": rev["Mixer"],
     "outputId": 1, "inputModuleId": rev["HostAudio2"], "inputId": 1, "color": ""},
]

patch = {"version": "2.4.1", "zoom": 0.7, "gridOffset": [0, 0],
         "modules": modules, "cables": cables}
out = r"D:\Cardinal\patches\zz_probe_drums.vcv"
# 空 color 会崩；★ 悬空的 leftModuleId/rightModuleId（Rack 模块排序面包屑）才是元凶
for _c in patch["cables"]:
    if "color" in _c and (_c["color"] == "" or _c["color"] is None):
        del _c["color"]
_live = set(m["id"] for m in modules)
for _m in modules:
    for _k in ("leftModuleId", "rightModuleId"):
        if _m.get(_k) is not None and _m[_k] not in _live:
            del _m[_k]
patch["path"] = out
patchio.write_patch(out, patch)
print("探针机架 modules=%d cables=%d -> %s"
      % (len(modules), len(cables), out))
