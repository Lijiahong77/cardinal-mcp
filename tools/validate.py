#!/usr/bin/env python3
"""校验 .vcv 机架文件。

检查项:
  1. JSON 是否合法
  2. 每个模块的 plugin/model 是否在本版本 Cardinal 的模块字典里
  3. 每根线缆的两端模块 id 是否存在
  4. 是否有重复 id

用法: python validate.py <file.vcv> [更多文件]
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import patchio  # noqa: E402

MANIFEST_DIR = r"C:\Program Files\Cardinal-win64-26.02\Cardinal.lv2\resources\PluginManifests"

# patch 里可能出现的 plugin 别名 -> 清单里的 slug
ALIAS = {"DrumKit": "WSTD-Drums", "WSTD-Drums": "WSTD-Drums"}


def build_db():
    db = {}
    for fn in os.listdir(MANIFEST_DIR):
        if not fn.endswith(".json"):
            continue
        with open(os.path.join(MANIFEST_DIR, fn), encoding="utf-8") as f:
            d = json.load(f)
        for m in d.get("modules", []):
            db[(d["slug"], m["slug"])] = m
    return db


def main(paths):
    db = build_db()
    print(f"模块字典: {len(db)} 个模块\n")
    bad = 0
    for path in paths:
        print(f"--- {os.path.basename(path)} ---")
        try:
            d = patchio.read_patch(path)
        except Exception as e:
            print(f"  [FAIL] 读取失败: {e}")
            bad += 1
            continue
        fmt = patchio.describe(path)["format"]
        print(f"  {fmt}, version={d.get('version')}")

        mods = d.get("modules", [])
        ids = [m["id"] for m in mods]
        dup = {i for i in ids if ids.count(i) > 1}
        if dup:
            print(f"  [FAIL] 重复模块 id: {dup}")
            bad += 1

        byid = {m["id"]: m for m in mods}
        for m in mods:
            plugin = ALIAS.get(m["plugin"], m["plugin"])
            if (plugin, m["model"]) not in db:
                print(f"  [FAIL] 未知模块: {m['plugin']}/{m['model']}")
                bad += 1

        for c in d.get("cables", []):
            for key, kind in (("outputModuleId", "源"), ("inputModuleId", "目标")):
                if c[key] not in byid:
                    print(f"  [FAIL] 线缆 {c.get('id')} 的{kind}模块 {c[key]} 不存在")
                    bad += 1

        cids = [c.get("id") for c in d.get("cables", [])]
        if len(set(cids)) != len(cids):
            print("  [FAIL] 线缆 id 重复")
            bad += 1

        print(f"  模块 {len(mods)} 个, 线缆 {len(d.get('cables', []))} 根 -> "
              f"{'OK' if bad == 0 else '有问题'}")
    print(f"\n总计问题数: {bad}")
    return bad


if __name__ == "__main__":
    sys.exit(0 if main(sys.argv[1:]) == 0 else 1)
