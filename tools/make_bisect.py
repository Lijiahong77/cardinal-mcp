# -*- coding: utf-8 -*-
"""生成 6 张「逐层剥离」探针，用二分法一次锁定崩溃模块。

背景（2026-10-17）：静态推断已连续四次猜错元凶
（空 color / data={} / Rings.model / 悬空面包屑），
而悬空面包屑在成功加载的机架里同样普遍存在 ⇒ 该方向已排除。
所以改用实验法：让机架逐层长起来，看哪一层开始崩。

层级设计（每层只比上一层多一个东西，便于归因）：
  L1  HostAudio2 单独                        —— 基线，最小可能
  L2  + Mixer                                   —— 加混音
  L3  + BassDrum9                              —— 加第一块鼓（无连线）
  L4  + Sequencer                              —— 加音序器（无连线）
  L5  + Gnome                                  —— 加时钟
  L6  + Snare + ClosedHiHat + 全套连线          —— = 完整探针

若 L1 崩 ⇒ 问题在顶层字段 / 输出模块 / 与机架体积无关的根本项
若 L6 才崩 ⇒ 逐层排除后即为前五层中某个（需 L2~L5 的结果交叉比对）
中间某层崩 ⇒ 该层新增的那个模块就是元凶

用法：生成后由用户重启 Cardinal + 开 OSC，一次连推 6 张。
"""
import copy
import sys

sys.path.insert(0, r"D:\Cardinal\tools")
import patchio

CLOCK = patchio.read_patch(r"D:\Cardinal\patches\Final Patch Work.vcv")
DRUM = patchio.read_patch(r"D:\Cardinal\patches\helm_full.vcv")
MIX = patchio.read_patch(r"D:\Cardinal\patches\demo_S4_sampling.vcv")

OUT_DIR = r"D:\Cardinal\patches"

# 所有 id 用一个不撞车的高位前缀
ID_BASE = 9700000000000000
CID_BASE = 9700000000009000


def find(patch, model):
    for m in patch["modules"]:
        if m["model"] == model:
            return m
    raise KeyError(model)


def clone(src_patch, model, uid, pos):
    m = copy.deepcopy(find(src_patch, model))
    m["id"] = ID_BASE + uid
    m["pos"] = pos
    return m


def drum_pattern():
    """17 图案 × 16 步 × 8 轨。底鼓四踩 + 军鼓 2 拍 + 闭镲 8 分。"""
    t = [[[False] * 8 for _ in range(16)] for _ in range(17)]
    p0 = t[0]
    for s in (0, 4, 8, 12):
        p0[s][0] = True
    p0[4][1] = True
    for s in range(0, 16, 2):
        p0[s][2] = True
    return t


def build(level):
    """返回 (modules, cables)。level ∈ 1..6"""
    mods, cabs = [], []

    def add(m):
        mods.append(m)
        return m

    def cab(om, oi, im, ii, cid):
        cabs.append({"id": CID_BASE + cid, "outputModuleId": om,
                     "outputId": oi, "inputModuleId": im, "inputId": ii})

    ha = add(clone(MIX, "HostAudio2", 1, [0, 0]))
    if level == 1:
        return mods, cabs

    mx = add(clone(MIX, "Mixer", 2, [10, 0]))
    cab(mx["id"], 0, ha["id"], 0, 1)
    cab(mx["id"], 1, ha["id"], 1, 2)
    if level == 2:
        return mods, cabs

    bd = add(clone(DRUM, "BassDrum9", 3, [20, 0]))
    if level == 3:
        return mods, cabs

    seq = add(clone(CLOCK, "Sequencer", 4, [30, 0]))
    if level == 4:
        return mods, cabs

    gn = add(clone(CLOCK, "Gnome", 5, [30, -1]))
    cab(gn["id"], 6, seq["id"], 0, 3)          # OUT6 → IN0
    if level == 5:
        return mods, cabs

    # --- L6：补齐鼓组与全部连线 ---
    sn = add(clone(DRUM, "SnareDrumN", 6, [20, 1]))
    hh = add(clone(DRUM, "ClosedHiHat", 7, [30, 1]))

    # WSTD 鼓机通用式：第 i 声部触发 IN(16+i)，音频 OUT(i)
    for i, drum in enumerate((bd, sn, hh)):
        cab(seq["id"], i, drum["id"], 16 + i, 10 + i)
        cab(drum["id"], 0, mx["id"], i, 20 + i)
    return mods, cabs


def sanitize(patch, path):
    """删空 color（成功机架都没有空值）+ 补 path。
    悬空面包屑**故意保留** —— 已证实它不是元凶，成功机架里也普遍存在。
    """
    for c in patch.get("cables", []):
        if "color" in c and (c["color"] == "" or c["color"] is None):
            del c["color"]
    patch["path"] = path
    return patch


DESCR = {
    1: "只有 HostAudio2",
    2: "+ Mixer",
    3: "+ BassDrum9",
    4: "+ Sequencer",
    5: "+ Gnome→Sequencer",
    6: "+ Snare/ClosedHiHat + 全连线",
}


def main():
    for lv in range(1, 7):
        mods, cabs = build(lv)
        patch = {"version": "2.4.1", "zoom": 0.7, "gridOffset": [0, 0],
                 "modules": mods, "cables": cabs}
        out = OUT_DIR + ("\\zz_L%d.vcv" % lv)
        sanitize(patch, out)
        patchio.write_patch(out, patch)
        print("L%d  %-32s modules=%d cables=%d"
              % (lv, DESCR[lv], len(mods), len(cabs)))

    print("\n★ 推法：zz_L1 → zz_L6，从 L1 逐级往上。")
    print("  哪一级开始不回 ok，哪一级新增的模块就是元凶。")
    print("  若 L1 就崩 ⇒ 与模块无关，问题在顶层字段或 HostAudio2。")


if __name__ == "__main__":
    main()