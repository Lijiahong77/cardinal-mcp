#!/usr/bin/env python3
"""Cardinal module picker.（2026-10-19 E10 裁决：本脚本降级为速查表 CLI。

主检索入口 = modbrowser.py（MCP 工具 cardinal_module_search），检索本体只走英文，
中文口语靠其内置词表翻译。本脚本的 `find` 中文匹配已被取代；`routes` 子命令
的音色速查表仍是有效资产，继续保留。

Builds a searchable index of every module bundled with Cardinal (1400+) and
lets you query it by keyword, manifest tag or package slug.

Why this exists: picking the *right* module for a requested timbre should be a
lookup, not a guess. Cardinal ships sampler, physical-modelling, FM, additive,
wavetable, neural-amp-model and plugin-host modules side by side; the index is
what lets us say "for a plucked string, start from Resonator" instead of
hand-waving.

Usage:
    python modsearch.py index                 rebuild the index from PluginManifests
    python modsearch.py find <kw> [<kw>...]   search name + description + tags
    python modsearch.py tag <tag> [...]       filter by manifest tag (OR)
    python modsearch.py pkg <package-slug>    list every module of one package
    python modsearch.py routes                print the timbre -> module cheat sheet
    python modsearch.py stats                 tag histogram

Index is cached at ../params/module_index.json (rebuild when Cardinal updates).
"""

import sys
import os
import json
import glob
import argparse
import collections

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX_PATH = os.path.join(HERE, os.pardir, "params", "module_index.json")

# Where Cardinal keeps its module manifests. First hit wins.
MANIFEST_CANDIDATES = [
    r"C:\Program Files\Cardinal-win64-26.02\Cardinal.lv2\resources\PluginManifests",
    r"C:\Program Files\Cardinal\Cardinal.lv2\resources\PluginManifests",
    r"C:\Program Files\Cardinal-win64\Cardinal.lv2\resources\PluginManifests",
]

# Timbre -> starting point. `pick` is the module to reach for first; `alt` is a
# fallback worth trying; `why` explains the choice in one line.
# Tags/ids are verified against the shipped manifests (see `python modsearch.py tag`).
ROUTES = [
    # --- real / acoustic instruments -------------------------------------
    ("快速原型：一个模块试出十几种真实乐器",
     "AudibleInstruments/Plaits", "AudibleInstruments/Braids",
     "Mutable Plaits/Braids 移植。宏振荡器内含几十种现成乐器模型（拨弦/簧片/钟/钢琴/人声/鼓），"
     "拨一下就能听出像不像，最适合“先确定方向再精修”"),
    ("拨弦：吉他 / 竖琴 / 钢琴 / 古筝",
     "AudibleInstruments/Rings", "SurgeXTRack/SurgeXTOSCString",
     "Mutable Rings 移植。物理建模共鸣器：给一个短激励,它自己共振出弦声。真实弦乐首选"),
    ("拨弦 / 打击的塑形（音头 + 衰减）",
     "Bogaudio/Bogaudio-LPG", "Fundamental/ADSR",
     "Low-pass gate = Buchla 式“先亮后暗”的自然衰减,拨弦/木琴/打击的经典包络"),
    ("模态体：马林巴 / 钟 / 木鱼 / 共鸣体",
     "AudibleInstruments/Elements", "CosineKitty-Sapphire/Elastika",
     "Mutable Elements 移植。模态合成,能调出“什么材质的物体在响”"),
    ("管乐：长笛 / 萨克斯 / 单簧管（吹奏感）",
     "CosineKitty-Sapphire/TubeUnit", "SurgeXTRack/SurgeXTOSCString",
     "Tube Unit 是管波导物理建模；String VCO 换成吹奏式激励也可"),
    ("管风琴 / 教堂管风琴（加法堆叠）",
     "Bogaudio/Bogaudio-Additator", "Befaco/Octaves",
     "加法合成：直接堆泛音列,管风琴就是这么发声的"),
    ("电钢琴 / 钟琴 / 金属敲击（FM）",
     "Bogaudio/Bogaudio-FMOp", "Valley/Dexter",
     "FM 合成。FM-OP 本身就是个完整 synth voice"),
    ("人声 / 元音 / 说话感",
     "PinkTrombone/PinkTrombone", "SurgeXTRack/SurgeXTFXVocoder",
     "声道物理模型,能做出元音滑动；Vocoder 用于人声合成效果"),
    # --- electronic ------------------------------------------------------
    ("经典减法：lead / bass / pad",
     "Fundamental/VCO", "Autinn/Saw2",
     "基础 VCO + VCF + ADSR。教程里 Serum/Massive 类音色大多落在这里"),
    ("波表（Serum / Massive 类）",
     "SurgeXTRack/SurgeXTOSCWavetable", "Valley/Terrorform",
     "波表振荡器。教程说 “load a wavetable” 就映射到这两个"),
    ("失谐堆叠 / supersaw / unison",
     "SurgeXTRack/SurgeXTUnisonHelper", "Bogaudio/Bogaudio-Unison",
     "★ 教程里的 “unison 2 voices, detune 0.15” 直接映射到一个模块,不用手搭一堆 VCO"),
    ("FM 贝斯 / neuro / 金属 bass",
     "SurgeXTRack/SurgeXTOSCFM2", "Venom/XM_OP",
     "FM2/FM3 振荡器；XM-OP 带整数比调制,适合做硬的 FM 音色"),
    ("鼓 / 打击垫",
     "WSTD-Drums/BassDrum9", "SurgeXTRack/SurgeXTOSCString",
     "WSTD-Drums 是完整鼓组；voxglitch/autobreak 做 breakbeat 切片"),
    ("颗粒 / 氛围 / 拖尾",
     "AudibleInstruments/Clouds", "voxglitch/ghosts",
     "★ Clouds 内置颗粒引擎,不需要外部采样文件；voxglitch 那组要你自己给 wav"),
    # --- sampler route ---------------------------------------------------
    ("任意真实乐器（有采样文件）",
     "voxglitch/samplerx8", "voxglitch/wavbank",
     "⚠️ 需要你自己提供 .wav。Cardinal 不带任何音色库"),
    # --- special ---------------------------------------------------------
    ("吉他音箱 / 失真踏板 / 整条效果链",
     "Cardinal/AIDA-X", "SurgeXTRack/SurgeXTFXDistortion",
     "★ AIDA-X 是神经网络音箱模型播放器,加载训练好的模型就能克隆真实设备"),
    ("兜底：任何第三方合成器插件",
     "Cardinal/Carla", "Cardinal/Ildaeil",
     "★ 插件宿主。LV2/VST 都能塞进 Cardinal —— 实在找不到内置模块就走这条"),
]


def find_manifest_dir():
    for d in MANIFEST_CANDIDATES:
        if os.path.isdir(d):
            return d
    # last resort: walk Program Files looking for a PluginManifests folder
    for root in (r"C:\Program Files", r"C:\Program Files (x86)", r"D:\\"):
        if not os.path.isdir(root):
            continue
        hits = glob.glob(os.path.join(root, "*Cardinal*", "**", "PluginManifests"), recursive=True)
        if hits:
            return hits[0]
    return None


def build_index():
    base = find_manifest_dir()
    if not base:
        sys.exit("ERROR: cannot locate Cardinal PluginManifests folder")
    packages, modules = {}, []
    for fp in sorted(glob.glob(os.path.join(base, "*.json"))):
        try:
            d = json.load(open(fp, encoding="utf-8"))
        except Exception as e:
            print(f"  skip {os.path.basename(fp)}: {e}", file=sys.stderr)
            continue
        slug = d.get("slug") or os.path.splitext(os.path.basename(fp))[0]
        packages[slug] = {
            "name": d.get("name") or slug,
            "author": d.get("author"),
            "version": d.get("version"),
            "license": d.get("license"),
            "source": d.get("sourceUrl") or d.get("manualUrl"),
        }
        for m in d.get("modules") or []:
            modules.append({
                "pkg": slug,
                "pkgName": packages[slug]["name"],
                "slug": m.get("slug"),
                "name": m.get("name") or m.get("slug"),
                "tags": m.get("tags") or [],
                "desc": (m.get("description") or "").strip(),
            })
    idx = {
        "manifestDir": base,
        "packageCount": len(packages),
        "moduleCount": len(modules),
        "packages": packages,
        "modules": modules,
    }
    os.makedirs(os.path.dirname(INDEX_PATH), exist_ok=True)
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False, indent=1)
    return idx


def load_index(auto_build=True):
    if os.path.exists(INDEX_PATH):
        try:
            return json.load(open(INDEX_PATH, encoding="utf-8"))
        except Exception:
            pass
    if auto_build:
        return build_index()
    sys.exit("ERROR: no index yet — run `python modsearch.py index` first")


def fmt_mod(m):
    line = f"  [{m['pkg']}] {m['slug']}  «{m['name']}»"
    if m["tags"]:
        line += f"\n        tags: {','.join(m['tags'])}"
    if m["desc"]:
        line += f"\n        {m['desc'][:170]}"
    return line


def cmd_index(_a):
    idx = build_index()
    print(f"indexed {idx['moduleCount']} modules from {idx['packageCount']} packages")
    print(f"  source: {idx['manifestDir']}")
    print(f"  cached: {os.path.normpath(INDEX_PATH)}")


def cmd_find(a):
    idx = load_index()
    kws = [k.lower() for k in a.keywords]

    # 0) spoken-language entry point: "古筝" / "拨弦" / "长笛" only exist in the
    #    cheat sheet, not in the English manifest text. Surface those first.
    route_hits = [r for r in ROUTES if any(k in r[0].lower() for k in kws)]
    if route_hits:
        print("★ 速查表命中（口语描述词 → 起点模块）：")
        for target, pick, alt, why in route_hits:
            print(f"  ● {target}")
            print(f"      → {pick}   （备选 {alt}）")
            print(f"      {why}")
        print()

    hits = []
    for m in idx["modules"]:
        name = (str(m["name"]) + " " + str(m["slug"])).lower()
        desc = m["desc"].lower()
        tags = " ".join(m["tags"]).lower()
        score = 0
        for k in kws:
            if k in name:
                score += 10
            if k in tags:
                score += 6
            if k in desc:
                score += 3
        if score and all((k in name or k in desc or k in tags) for k in kws):
            hits.append((score, m))
    hits.sort(key=lambda x: (-x[0], len(str(x[1]["desc"]))))
    print(f"{len(hits)} hit(s) for {' '.join(a.keywords)}\n")
    for _, m in hits[: a.limit]:
        print(fmt_mod(m))
    if len(hits) > a.limit:
        print(f"\n  ... {len(hits) - a.limit} more (use --limit)")


def cmd_tag(a):
    idx = load_index()
    want = [t.lower() for t in a.tags]
    hits = [m for m in idx["modules"]
            if any(t.lower() in [x.lower() for x in m["tags"]] for t in want)]
    print(f"{len(hits)} module(s) tagged {' | '.join(a.tags)}\n")
    for m in hits[: a.limit]:
        print(fmt_mod(m))
    if len(hits) > a.limit:
        print(f"\n  ... {len(hits) - a.limit} more (use --limit)")


def cmd_pkg(a):
    idx = load_index()
    hits = [m for m in idx["modules"] if m["pkg"].lower() == a.package.lower()]
    if not hits:
        print(f"no package named {a.package!r}. known slugs:")
        print("  " + ", ".join(sorted(idx["packages"])))
        return
    p = idx["packages"][hits[0]["pkg"]]
    print(f"### {hits[0]['pkgName']} ({hits[0]['pkg']})  v{p.get('version')}  by {p.get('author')}")
    if p.get("source"):
        print(f"    source: {p['source']}")
    print(f"    {len(hits)} modules\n")
    for m in hits:
        print(f"  {str(m['slug']):32} «{m['name']}»" + (f"  [{','.join(m['tags'])}]" if m["tags"] else ""))
        if m["desc"]:
            print(f"        {m['desc'][:150]}")


def cmd_routes(_a):
    """Print the cheat sheet, verifying every recommendation against the index.

    A wrong module id is worse than no recommendation, so each entry is looked
    up live: ✓ means it ships with this Cardinal build, ✗ means the id is stale
    and needs fixing in ROUTES.
    """
    idx = load_index()
    bykey = {f"{m['pkg']}/{m['slug']}": m for m in idx["modules"]}
    missing = 0
    print("音色 → 模块 速查表（✓ = 本机 Cardinal 确认存在）\n")
    for target, pick, alt, why in ROUTES:
        print(f"● {target}")
        for label, key in (("首选", pick), ("备选", alt)):
            m = bykey.get(key)
            if m:
                print(f"    {label}: {key}  ✓ «{m['name']}»")
            else:
                missing += 1
                print(f"    {label}: {key}  ✗ 索引中不存在，需修正")
        print(f"    原因: {why}\n")
    if missing:
        print(f"⚠️  {missing} 条推荐 ID 有误 —— 用 `python modsearch.py find <关键词>` 找正确 slug")
    else:
        print("✅ 全部推荐已对着本机模块清单核验")


def cmd_stats(_a):
    idx = load_index()
    c = collections.Counter()
    for m in idx["modules"]:
        for t in m["tags"]:
            c[t] += 1
    print(f"{idx['moduleCount']} modules / {idx['packageCount']} packages")
    print(f"index built from: {idx['manifestDir']}\n")
    for t, n in c.most_common(60):
        print(f"  {n:5d}  {t}")


def main():
    ap = argparse.ArgumentParser(description="Cardinal module picker")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("index", help="rebuild index").set_defaults(func=cmd_index)

    p = sub.add_parser("find", help="search name/desc/tags")
    p.add_argument("keywords", nargs="+")
    p.add_argument("--limit", type=int, default=40)
    p.set_defaults(func=cmd_find)

    p = sub.add_parser("tag", help="filter by manifest tag")
    p.add_argument("tags", nargs="+")
    p.add_argument("--limit", type=int, default=60)
    p.set_defaults(func=cmd_tag)

    p = sub.add_parser("pkg", help="list one package")
    p.add_argument("package")
    p.set_defaults(func=cmd_pkg)

    sub.add_parser("routes", help="timbre -> module cheat sheet").set_defaults(func=cmd_routes)
    sub.add_parser("stats", help="tag histogram").set_defaults(func=cmd_stats)

    a = ap.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
