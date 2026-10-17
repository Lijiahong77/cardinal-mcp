# -*- coding: utf-8 -*-
"""从可信机架反推每个模块真实用到的端口集合（ground truth）。"""
import sys, os, collections
sys.path.insert(0, r"D:/Cardinal/tools")
import patchio
D = r"D:/Cardinal/patches"
TRUST = ["Final Patch Work.vcv","helm_drums.vcv","helm_full.vcv","helm_keys.vcv",
         "mini_arranger.vcv","mini_arranger_expanded.vcv","live_before_quadeca_1017.vcv",
         "quadeca_ghostfolk.vcv","quadeca_scrapyard.vcv","quadeca_life1.vcv",
         "demo_S1_8tracks.vcv","helm_knobs.vcv","helm_keys_master.vcv"]
USE = collections.defaultdict(lambda: (set(), set()))
for f in TRUST:
    fp = os.path.join(D, f)
    if not os.path.exists(fp): continue
    p = patchio.read_patch(fp)
    by = {m["id"]: m.get("model") for m in p["modules"]}
    for c in p.get("cables", []):
        om = by.get(c["outputModuleId"]); im = by.get(c["inputModuleId"])
        if om: USE[om][1].add(c["outputId"])
        if im: USE[im][0].add(c["inputId"])
for model in sorted(USE):
    i, o = USE[model]
    print("%-22s IN=%-26s OUT=%s" % (model, sorted(i), sorted(o)))
