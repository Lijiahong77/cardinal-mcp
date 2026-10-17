# -*- coding: utf-8 -*-
"""density.py —— 报告一张机架各层的音符密度（有效音 / 总槽位）。

李12:36 要求「编得再密一点」—— 这脚本用来**量化**密没密，别靠感觉。
用法: python density.py <xxx.vcv> [另一个.vcv ...]
"""
import sys

import patchio

LAYERS = ["pad", "bass", "lead", "decor", "sub"]
#★ v5：层数由 patch 实际模块数决定，LAYERS 只是显示用的名字表。


def density(path):
    p = patchio.read_patch(path)
    print("\n=== %s ===" % path.split("\\")[-1].split("/")[-1])
    # pianoroll 的角色：从它 OUT5 往下游走回自己不方便，改用模块 id 大小规律
    # 生成器里 pr_id = tid+0/10/20/30，四层依序 ⇒ 按 id 排序即 pad,bass,lead,decor
    prs = sorted([m for m in p["modules"] if m["model"] == "rcm-pianoroll"],
                 key=lambda m: m["id"])
    grand_on = grand_tot = 0
    for i, pr in enumerate(prs):
        name = LAYERS[i] if i < len(LAYERS) else "layer%d" % i
        pat = pr["data"]["patterns"][0]
        on = tot = 0
        bar_on = []
        for meas in pat["measures"]:
            c = sum(1 for n in meas["notes"] if n.get("active"))
            on += c
            tot += len(meas["notes"])
            bar_on.append(c)
        grand_on += on
        grand_tot += tot
        print("  %-6s %3d/%3d = %4.1f%%  逐小节 %s"
              % (name, on, tot, 100.0 * on / max(tot, 1), bar_on))
    print("  %-6s %3d/%3d = %4.1f%%  ★总密度"
          % ("全部", grand_on, grand_tot, 100.0 * grand_on / max(grand_tot, 1)))
    return grand_on, grand_tot


if __name__ == "__main__":
    for a in sys.argv[1:]:
        density(a)