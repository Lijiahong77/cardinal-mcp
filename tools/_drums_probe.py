#!/usr/bin/env python3
"""拉取 WSTD-Drums 全部鼓模块源码，解析出：声部数、触发口编号、音频出口、参数编号。

为什么需要：WSTD-Drums 每个模块是「多声部鼓机」，声部数因模块而异
（BD9 有 2 个声部，CR78 有 2 个…），触发口 = IN(16+i)，音频出 = OUT(i)。
写机架接线前必须知道每个模块到底有几路。
"""
import json
import os
import re
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

API = "https://api.github.com/repos/Wasted-Audio/WSTD-Drums/contents/src/controller"
RAW = "https://raw.githubusercontent.com/Wasted-Audio/WSTD-Drums/master/src/controller/"
CACHE = r"D:\Cardinal\tools\_srccache"


def get(url, binary=False):
    req = urllib.request.Request(url, headers={"User-Agent": "helm/1.0"})
    data = urllib.request.urlopen(req, timeout=30).read()
    return data if binary else data.decode("utf-8", "replace")


def main():
    os.makedirs(CACHE, exist_ok=True)
    listing = json.loads(get(API))
    cpps = [e["name"] for e in listing if e["name"].endswith(".cpp")]
    print("controller 目录下的 cpp:", cpps)
    print()

    rows = []
    for fn in cpps:
        try:
            src = get(RAW + fn)
        except Exception as e:
            print("FAIL", fn, e)
            continue
        # 缓存
        with open(os.path.join(CACHE, "wstd_" + fn), "w", encoding="utf-8") as f:
            f.write(src)

        if "SampleController" in fn:      # 基类，跳过
            continue

        # numModules = N
        m = re.search(r"numModules\s*=\s*(\d+)\s*;", src)
        nvoice = int(m.group(1)) if m else None

        # 模型名（构造函数 XXXModule::XXXModule）
        cls = re.search(r"(\w+Module)::\w+Module", src)
        cls = cls.group(1) if cls else fn

        # configParam 里带的显示名（第一个字符串参数）
        labels = re.findall(r'configParam\([^,]+,[^,]+,[^,]+,[^,]+,\s*"([^"]+)"', src)

        # 采样族（setupSamples 里 selectSample 的名字前缀）
        fams = re.findall(r'selectSample\("([^"]+)"\)', src)
        fam = fams[0].split("-")[0] if fams else "?"

        rows.append({"file": fn, "class": cls, "voices": nvoice,
                     "family": fam, "labels": labels[:3]})

    print("%-22s %-18s %-6s %-8s %s" % ("file", "class", "voices", "family", "labels"))
    print("-" * 90)
    for r in sorted(rows, key=lambda x: (x["voices"] is None, x["file"])):
        print("%-22s %-18s %-6s %-8s %s" % (
            r["file"], r["class"], r["voices"], r["family"], ",".join(r["labels"])))

    print()
    print("=== 可用的鼓音色（对应 patch 里的 model 名）===")
    print("触发口规律：第 i 个声部的触发口 = IN(%d+i)，音频出 = OUT(i)" % 16)
    print("参数规律：DRUM_PARAM+i = 第 i 声部采样选择（0-15），TUNE_PARAM+i = 播放速度")

    with open(r"D:\Cardinal\refs\drums_map.json", "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    print("\n已写入 D:\\Cardinal\\refs\\drums_map.json")


if __name__ == "__main__":
    main()
