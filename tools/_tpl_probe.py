#!/usr/bin/env python3
"""探查官方模板机架的模块与接线结构（侦察用，非正式工具）。"""
import json
import sys

sys.path.insert(0, r"D:\Cardinal\tools")
import patchio  # noqa: E402

NAMES = ["native", "synth", "main", "fx", "mini"]
DETAIL = {"native", "synth"}

for n in NAMES:
    path = rf"D:\Cardinal\refs\{n}.tpl.vcv"
    p = patchio.read_patch(path)
    mods = p.get("modules", [])
    cabs = p.get("cables", [])
    print("=" * 66)
    print(f'{n}.vcv   version={p.get("version")}  '
          f'modules={len(mods)}  cables={len(cabs)}')
    idmap = {}
    for m in mods:
        slug = f'{m.get("plugin")}/{m.get("model")}'
        idmap[m["id"]] = slug
        if n in DETAIL:
            print(f'  id={m["id"]:<6} {slug}')
            d = m.get("data")
            if d:
                print(f'          data={json.dumps(d, ensure_ascii=False)[:170]}')
    if n not in DETAIL:
        print("  modules:", ", ".join(sorted(set(idmap.values()))))
        continue
    print("  -- cables --")
    for c in cabs:
        om = idmap.get(c["outputModuleId"], "?")
        im = idmap.get(c["inputModuleId"], "?")
        print(f'  {om} OUT{c["outputId"]:<3} -> {im} IN{c["inputId"]}')
