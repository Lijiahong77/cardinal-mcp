# -*- coding: utf-8 -*-
"""连线崩溃的收窄探针（12:00 实测后的第三轮二分）。

已确立的事实（全部实测，非推断）：
  zz_L1  只有 HostAudio2                          -> ok
  zz_L2  + Mixer + 2 线                           -> 崩
  zz_V0  HostAudio2 + Mixer（无连线）              -> ok    ← Mixer 模块本身无害
  zz_V1  HostAudio2 + Mixer + 2 线（data 完整）    -> 崩    ← 加上连线就崩

⇒ 变量只剩「连线」。但成功机架（quadeca_ghostfolk，32 条线）能加载，
  cable 字段集合也完全一致 ⇒ 差别只能在**被连线的模块的 id**。

★ 头号嫌疑：HostAudio2 的 id。所有用户成品机架里它是 **1 / 9 / 7100000000000008**，
  而我一直用 97… 大数。Cardinal 的 Host* 是引擎内建模块，
  引擎可能在连线/启动阶段按 id 反查模块，找不到就崩。
  且 V0（无连线）能过，与「连线时才激活」的行为吻合。

三张正交探针：
  P1  直接加载 quadeca_ghostfolk.vcv —— 环境基线。它第一轮成功加载过（32 条线）。
      若它现在也崩 ⇒ 是环境/加载路径变了，与我的字段无关。
  P2  HostAudio2.id=1 + Mixer(FPW) + 2 线 —— 只改 HostAudio2 的 id，其余同 V1
      P2 过而 V1 崩 ⇒ **HostAudio2 的 id 必须是小整数**，全项目生成器统一改。
  P3  HostAudio2.id=大数 + Mixer(FPW) + 仅 1 条线 —— 只改线数
      P3 也崩 ⇒ 与线数无关，坐实是 id；P3 过 ⇒ 与 id 无关而是线的条数。
"""
import copy
import sys

sys.path.insert(0, r"D:\Cardinal\tools")
import patchio

OUT_DIR = r"D:\Cardinal\patches"
ID_BASE = 9720000000000000
CID_BASE = 9720000000009000

S4 = patchio.read_patch(r"D:\Cardinal\patches\demo_S4_sampling.vcv")
FPW = patchio.read_patch(r"D:\Cardinal\patches\Final Patch Work.vcv")


def find(patch, model):
    for m in patch["modules"]:
        if m["model"] == model:
            return m
    raise KeyError(model)


def mk(model, src, uid, pos, ha_id=None):
    m = copy.deepcopy(find(src, model))
    m["id"] = ha_id if ha_id is not None else ID_BASE + uid
    m["pos"] = pos
    m.pop("leftModuleId", None)
    m.pop("rightModuleId", None)
    return m


def sanitize(patch, path):
    for c in patch.get("cables", []):
        if "color" in c and (c["color"] == "" or c["color"] is None):
            del c["color"]
    patch["path"] = path
    return patch


def save(tag, mods, cabs, desc):
    patch = {"version": "2.4.1", "zoom": 0.7, "gridOffset": [0, 0],
             "modules": mods, "cables": cabs}
    out = OUT_DIR + ("\\zz_%s.vcv" % tag)
    sanitize(patch, out)
    patchio.write_patch(out, patch)
    print("%s  %-46s modules=%d cables=%d" % (tag, desc, len(mods), len(cabs)))


def main():
    # --- P2：HostAudio2.id = 1 ---
    ha = mk("HostAudio2", S4, 1, [0, 0], ha_id=1)
    mx = mk("Mixer", FPW, 2, [10, 0])
    cabs = [
        {"id": CID_BASE + 1, "outputModuleId": mx["id"], "outputId": 0,
         "inputModuleId": ha["id"], "inputId": 0},
        {"id": CID_BASE + 2, "outputModuleId": mx["id"], "outputId": 1,
         "inputModuleId": ha["id"], "inputId": 1},
    ]
    save("P2", [ha, mx], cabs, "HostAudio2.id=1 + Mixer + 2线（其余同 V1）")

    # --- P3：HostAudio2.id 保持大数，只接 1 条线 ---
    ha2 = mk("HostAudio2", S4, 1, [0, 0])
    mx2 = mk("Mixer", FPW, 2, [10, 0])
    cabs2 = [
        {"id": CID_BASE + 1, "outputModuleId": mx2["id"], "outputId": 0,
         "inputModuleId": ha2["id"], "inputId": 0},
    ]
    save("P3", [ha2, mx2], cabs2, "HostAudio2.id=大数 + Mixer + 仅1条线")

    # --- P4：HostAudio2.id=1 且用 S4 版 Mixer，双保险交叉验证 ---
    ha3 = mk("HostAudio2", S4, 1, [0, 0], ha_id=1)
    mx3 = mk("Mixer", S4, 2, [10, 0])
    cabs3 = [
        {"id": CID_BASE + 1, "outputModuleId": mx3["id"], "outputId": 0,
         "inputModuleId": ha3["id"], "inputId": 0},
        {"id": CID_BASE + 2, "outputModuleId": mx3["id"], "outputId": 1,
         "inputModuleId": ha3["id"], "inputId": 1},
    ]
    save("P4", [ha3, mx3], cabs3, "HostAudio2.id=1 + S4版Mixer + 2线")

    print("\n★ 推法：zz_P2 -> zz_P3 -> zz_P4（外加先试 quadeca_ghostfolk.vcv 做环境基线）")
    print("  P2 过  ⇒ HostAudio2 的 id 必须是小整数（十拿九稳是这个）")
    print("  P2 崩 + P3 过 ⇒ 与 id 无关，是线的条数")
    print("  P2/P3/P4 全崩 ⇒ 三者共有因素另有其人，回头看 quadeca_ghostfolk 能否加载")


if __name__ == "__main__":
    main()