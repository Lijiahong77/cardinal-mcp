#!/usr/bin/env python3
"""Cardinal .vcv 机架文件检查器.

用法:
  python vcvtool.py inspect <file.vcv>          列出模块与连线（带模块名）
  python vcvtool.py ports   <file.vcv>          只列连线，压缩成一行一条
  python vcvtool.py find    <plugin> [model]    在示例库里找出用过该模块的 patch
  python vcvtool.py usage   <plugin> <model>    汇总该模块在所有示例里的端口使用情况
  python vcvtool.py db                          从 PluginManifests 生成模块字典
"""
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import patchio  # noqa: E402

CARDINAL_HOME = r"C:\Program Files\Cardinal-win64-26.02"
PATCH_DIR = os.path.join(CARDINAL_HOME, "Cardinal.lv2", "resources", "patches")
MANIFEST_DIR = os.path.join(CARDINAL_HOME, "Cardinal.lv2", "resources", "PluginManifests")


def load(path):
    """明文 JSON 和 Cardinal 的 tar+zstd 归档通吃。"""
    return patchio.read_patch(path)


def all_patches():
    out = []
    for root, _dirs, files in os.walk(PATCH_DIR):
        for fn in files:
            if fn.endswith(".vcv"):
                out.append(os.path.join(root, fn))
    return sorted(out)


def label(modules, mid):
    m = modules.get(mid)
    if not m:
        return f"<unknown#{mid}>"
    return f"{m['plugin']}:{m['model']}"


def inspect(path):
    d = load(path)
    modules = {m["id"]: m for m in d.get("modules", [])}
    print(f"=== {os.path.basename(path)}  version={d.get('version')} "
          f"modules={len(modules)} cables={len(d.get('cables', []))}")
    print("-- modules --")
    for mid, m in modules.items():
        p = m.get("params") or []
        pv = ",".join(f"{x.get('id')}={round(x.get('value', 0), 3)}" for x in p)
        print(f"  id={mid:<18} {m['plugin']}/{m['model']}"
              + (f"  params[{pv}]" if pv else ""))
    print("-- cables --")
    for c in d.get("cables", []):
        print(f"  {label(modules, c['outputModuleId'])}:OUT{c['outputId']:<3}"
              f" -> {label(modules, c['inputModuleId'])}:IN{c['inputId']:<3}"
              f"   (outMid={c['outputModuleId']}, inMid={c['inputModuleId']})")
    return d


def ports(path):
    d = load(path)
    modules = {m["id"]: m for m in d.get("modules", [])}
    for c in d.get("cables", []):
        print(f"{label(modules, c['outputModuleId'])}:OUT{c['outputId']} -> "
              f"{label(modules, c['inputModuleId'])}:IN{c['inputId']}")


def find(plugin, model=None):
    hits = []
    for p in all_patches():
        try:
            d = load(p)
        except Exception:
            continue
        for m in d.get("modules", []):
            if m.get("plugin", "").lower() == plugin.lower():
                if model is None or m.get("model", "").lower() == model.lower():
                    hits.append((p, m.get("model")))
                    break
    for p, mo in hits:
        print(f"{os.path.relpath(p, PATCH_DIR)}   [{mo}]")
    print(f"total: {len(hits)}")


def usage(plugin, model):
    """汇总某个模块在所有示例 patch 里每个端口都接了谁。"""
    agg = defaultdict(lambda: defaultdict(int))
    for p in all_patches():
        try:
            d = load(p)
        except Exception:
            continue
        modules = {m["id"]: m for m in d.get("modules", [])}
        for c in d.get("cables", []):
            om, im = modules.get(c["outputModuleId"]), modules.get(c["inputModuleId"])
            if not om or not im:
                continue
            if om["plugin"] == plugin and om["model"] == model:
                agg[("out", c["outputId"])][f"{im['plugin']}:{im['model']}:IN{c['inputId']}"] += 1
            if im["plugin"] == plugin and im["model"] == model:
                agg[("in", c["inputId"])][f"{om['plugin']}:{om['model']}:OUT{c['outputId']}"] += 1
    print(f"== {plugin}/{model} 端口使用统计 ==")
    for (direction, pid) in sorted(agg.keys()):
        peers = sorted(agg[(direction, pid)].items(), key=lambda x: -x[1])
        peers_txt = ", ".join(f"{n} x{v}" for n, v in peers[:6])
        print(f"  {direction.upper()} {pid:<3}: {peers_txt}")


def db():
    out = []
    for fn in sorted(os.listdir(MANIFEST_DIR)):
        if not fn.endswith(".json"):
            continue
        try:
            d = load(os.path.join(MANIFEST_DIR, fn))
        except Exception:
            continue
        for m in d.get("modules", []):
            out.append({
                "plugin": d.get("slug"),
                "model": m.get("slug"),
                "name": m.get("name"),
                "description": m.get("description", ""),
                "tags": m.get("tags", []),
            })
    print(f"total modules: {len(out)}, plugins: {len(set(m['plugin'] for m in out))}")
    return out


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "inspect":
        inspect(sys.argv[2])
    elif cmd == "ports":
        ports(sys.argv[2])
    elif cmd == "find":
        find(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
    elif cmd == "usage":
        usage(sys.argv[2], sys.argv[3])
    elif cmd == "db":
        db()
    else:
        print(__doc__)
