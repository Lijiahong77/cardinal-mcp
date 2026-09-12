#!/usr/bin/env python3
"""下载 Cardinal 官方示例机架并列出各自用到的模块（侦察用）。"""
import json
import os
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, r"D:\Cardinal\tools")
import patchio  # noqa: E402

BASE = "https://raw.githubusercontent.com/DISTRHO/Cardinal/main/patches/examples/"
OUT = r"D:\Cardinal\refs\examples"

NAMES = [
    "DRMR_-_BassGrowl.vcv", "DRMR_-_Etherpad.vcv", "DRMR_-_Gabberswing.vcv",
    "DRMR_-_Interverb.vcv", "JTB_-_Waves.vcv",
    "SpotlightKid_-_Classic-Polysynth.vcv", "SpotlightKid_-_Cringe-Synth.vcv",
    "VT_-_Jupiter_Ascent.vcv",
    "falkTX_-_Divide-no-Conquer.vcv", "falkTX_-_Mini-Arp-Seq.vcv",
    "falkTX_-_Random-Progress-Pluck-Rev.vcv", "falkTX_-_Salomonis-MonoRegen.vcv",
    "nooneknowspeter_-_Catalyst.vcv", "nooneknowspeter_-_Velour.vcv",
    "nooneknowspeter_-_Xmas.vcv",
]

os.makedirs(OUT, exist_ok=True)
got = []
for n in NAMES:
    p = os.path.join(OUT, n)
    if not os.path.exists(p):
        try:
            url = BASE + urllib.parse.quote(n)
            req = urllib.request.Request(url, headers={"User-Agent": "helm/1.0"})
            open(p, "wb").write(urllib.request.urlopen(req, timeout=40).read())
        except Exception as e:
            print("FAIL", n, type(e).__name__, e)
            continue
    got.append(p)
    print(f"OK  {os.path.getsize(p):>7} bytes  {n}")

print("\n" + "=" * 70)
for p in got:
    try:
        d = patchio.read_patch(p)
    except Exception as e:
        print("PARSE FAIL", os.path.basename(p), e)
        continue
    mods = d.get("modules", [])
    slugs = sorted({f'{m.get("plugin")}/{m.get("model")}' for m in mods})
    print(f'\n### {os.path.basename(p)}   '
          f'({len(mods)} modules / {len(d.get("cables", []))} cables)')
    for s in slugs:
        print("   ", s)
