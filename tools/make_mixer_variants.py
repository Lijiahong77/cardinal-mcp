# -*- coding: utf-8 -*-
"""Mixer 字段变体探针 —— 定位 L2 崩溃的具体字段。

二分结论（11:57 实测）：
    zz_L1 (只有 HostAudio2)                        → 加载 ok
    zz_L2 (+ Mixer + 2 条线)                        → 崩
⇒ 元凶落在「Mixer 模块本身」或「那两条连线」上。

本轮要分离三个变量：
  A. 是 Mixer 模块本身崩，还是加上连线才崩      → V0（Mixer 无连线）
  B. data={} 是否合法（vs 完整 {"average","invert"}）→ V1/V3
  C. params 键「缺失」与「存在但空 data」的差别    → V2

四张：
  V0  Mixer（照抄 demo_S4 原样）+ 无连线
  V1  Mixer 照抄 Final Patch Work（data 完整 + params=1.0）
  V2  Mixer data={} 且 params 键整体缺失（照抄 quadeca_ghostfolk，那个成功加载过）
  V3  Mixer data 完整 + params=0.82（V1 与 V2 的混血，用来确认是哪个字段在起作用）
"""
import copy
import sys

sys.path.insert(0, r"D:\Cardinal\tools")
import patchio

OUT_DIR = r"D:\Cardinal\patches"
ID_BASE = 9710000000000000
CID_BASE = 9710000000009000

S4 = patchio.read_patch(r"D:\Cardinal\patches\demo_S4_sampling.vcv")
FPW = patchio.read_patch(r"D:\Cardinal\patches\Final Patch Work.vcv")
QG = patchio.read_patch(r"D:\Cardinal\patches\quadeca_ghostfolk.vcv")


def find(patch, model):
    for m in patch["modules"]:
        if m["model"] == model:
            return m
    raise KeyError(model)


def mk_ha():
    m = copy.deepcopy(find(S4, "HostAudio2"))
    m["id"] = ID_BASE + 1
    m["pos"] = [0, 0]
    m.pop("leftModuleId", None)
    m.pop("rightModuleId", None)
    return m


def mk_mixer(src, uid, pos, mode):
    """mode: 'asis' | 'full' | 'nodata_noparams' | 'full_param082'"""
    m = copy.deepcopy(find(src, "Mixer"))
    m["id"] = ID_BASE + uid
    m["pos"] = pos
    m.pop("leftModuleId", None)
    m.pop("rightModuleId", None)

    if mode == "asis":            # 原样（demo_S4 的 data={} + params=0.82）
        pass
    elif mode == "full":          # data 补齐 + params=1.0
        m["data"] = {"average": False, "invert": False}
        m["params"] = [{"id": 0, "value": 1.0}]
    elif mode == "nodata_noparams":  # data={} 且整个 params 键删掉
        m["data"] = {}
        m.pop("params", None)
    elif mode == "full_param082":    # data 补齐 + params=0.82
        m["data"] = {"average": False, "invert": False}
        m["params"] = [{"id": 0, "value": 0.82}]
    return m


def sanitize(patch, path):
    for c in patch.get("cables", []):
        if "color" in c and (c["color"] == "" or c["color"] is None):
            del c["color"]
    patch["path"] = path
    return patch


VARIANTS = [
    ("V0", S4, "asis", False, "Mixer 原样 · 无连线"),
    ("V1", FPW, "full", True, "data 完整 + params=1.0 · 有连线"),
    ("V2", QG, "nodata_noparams", True, "data={} 且无 params · 有连线"),
    ("V3", FPW, "full_param082", True, "data 完整 + params=0.82 · 有连线"),
]


def main():
    for tag, src, mode, wired, desc in VARIANTS:
        ha = mk_ha()
        mx = mk_mixer(src, 2, [10, 0], mode)
        mods = [ha, mx]
        cabs = []
        if wired:
            cabs = [
                {"id": CID_BASE + 1, "outputModuleId": mx["id"], "outputId": 0,
                 "inputModuleId": ha["id"], "inputId": 0},
                {"id": CID_BASE + 2, "outputModuleId": mx["id"], "outputId": 1,
                 "inputModuleId": ha["id"], "inputId": 1},
            ]
        patch = {"version": "2.4.1", "zoom": 0.7, "gridOffset": [0, 0],
                 "modules": mods, "cables": cabs}
        out = OUT_DIR + ("\\zz_%s.vcv" % tag)
        sanitize(patch, out)
        patchio.write_patch(out, patch)
        print("%s  %-34s Mixer data=%-42s params=%s  cables=%d"
              % (tag, desc, json_d(mx), json_p(mx), len(cabs)))


def json_d(m):
    import json
    return json.dumps(m.get("data"), ensure_ascii=False)


def json_p(m):
    import json
    return json.dumps(m.get("params", "<键缺失>"), ensure_ascii=False)


if __name__ == "__main__":
    main()