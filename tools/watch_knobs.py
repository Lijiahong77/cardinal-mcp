#!/usr/bin/env python3
"""轮询 Cardinal 实时存档，检测 8 个旋钮映射的目标参数有没有变化。

因为 OSC 只能写不能读，验证只能走实时存档这条路。
用法: python watch_knobs.py [秒数]
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import patchio                    # noqa: E402
import cardinal_mcp as cm         # noqa: E402
from make_knobs import get_map_module   # noqa: E402


def snapshot():
    path, _ = cm.live_patch_path()
    if not path:
        return None
    d = patchio.read_patch(path)
    by_id = {m["id"]: m for m in d.get("modules", [])}
    mm = get_map_module(d)
    if not mm:
        return None
    out = {}
    for e in mm.get("data", {}).get("maps", []):
        cc = e.get("cc")
        if cc is None or cc < 0:
            continue
        tgt = by_id.get(e.get("moduleId"))
        if not tgt:
            continue
        cur = next((q.get("value") for q in (tgt.get("params") or [])
                    if q.get("id") == e.get("paramId")), None)
        out[cc] = (tgt.get("model"), e.get("paramId"), cur)
    return out


def main():
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 30
    base = snapshot()
    if base is None:
        print("读不到实时存档 —— Cardinal 在运行吗？")
        return
    print("当前目标参数值：")
    for cc in sorted(base):
        m, pid, v = base[cc]
        print(f"  CC{cc}  {m} param{pid} = {v}")
    print(f"\n开始监视 {secs} 秒 —— 请拧旋钮……\n")

    last = dict(base)
    changed = set()
    t0 = time.time()
    while time.time() - t0 < secs:
        time.sleep(0.6)
        cur = snapshot()
        if cur is None:
            continue
        for cc in sorted(cur):
            if cc in last and cur[cc][2] is not None and last[cc][2] is not None:
                if abs(cur[cc][2] - last[cc][2]) > 1e-6:
                    m, pid, v = cur[cc]
                    print(f"  [{time.time()-t0:5.1f}s] CC{cc} {m} "
                          f"param{pid}: {last[cc][2]:.3f} -> {v:.3f}")
                    changed.add(cc)
        last = dict(cur)

    print(f"\n结果：{len(changed)} 个旋钮产生变化 -> "
          f"{sorted('CC'+str(c) for c in changed) if changed else '（无变化）'}")
    if not changed:
        print("提示：如果确实拧了旋钮但没反应，可能原因：")
        print("  1. Cardinal Engine 菜单里没选 MIDI 输入设备")
        print("  2. 旋钮的 CC 号不是 20~27（可以在 MidiSuite 里改）")
        print("  3. 实时存档写入有延迟，可再试一次")


if __name__ == "__main__":
    main()
