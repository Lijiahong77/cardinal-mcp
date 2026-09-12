#!/usr/bin/env python3
"""把 SMK25 的 8 个旋钮接到 Cardinal 参数上。

做法：在机架里加一个 Cardinal/HostMIDIMap 模块，写它的 data.maps 表。
映射表结构（源码 HostMIDI-Map.cpp 确认）：
    {"cc": 0-119, "moduleId": <机架里的模块 id>, "paramId": <参数号>}
    channel = 0 表示接收所有 MIDI 通道（OMNI）
    smooth  = true 时参数变化走指数平滑，不会跳变

用法:
  python make_knobs.py show   <patch>        看当前映射
  python make_knobs.py apply  <patch> [--load]  写入 8 条映射
  python make_knobs.py set    <patch> <cc> <模块名> <参数名>  [--load]
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import patchio            # noqa: E402
import paramlib as pl     # noqa: E402

MODEL = "HostMIDIMap"
KNOB_CC = list(range(20, 28))       # SMK25 实测：8 个旋钮 = CC20~CC27

# 默认映射：(CC, 目标模块 model, 参数名关键字, 人话说明)
DEFAULT_MAP = [
    (20, "VCF",     "Cutoff frequency",  "亮度 / 明暗"),
    (21, "VCF",     "Resonance",         "共振 / 尖锐度"),
    (22, "Plateau", "Wet level",         "混响湿度"),
    (23, "Plateau", "Decay",             "混响尾巴长短"),
    (24, "ADSR",    "Attack",            "起音快慢"),
    (25, "ADSR",    "Release",           "松手后余音"),
    (26, "VCO",     "Pulse width",       "脉宽 / 音色胖瘦"),
    (27, "VCF",     "Drive",             "过载 / 脏度"),
]


def find_module(patch, model):
    """按 model 名找模块 id（同名取第一个）。"""
    for m in patch.get("modules", []):
        if m.get("model") == model:
            return m["id"]
    return None


def find_param_id(model, name_kw):
    """在参数字典里按名字找参数号。

    打分制，避免踩坑：
      · 完全同名      最高分
      · 以关键字开头  次之
      · 含关键字      最低
      · 'xxx CV' 结尾 扣分（那是 CV 输入深度，不是本体）
      · reserved 槽位 直接排除（废弃编号，写了不生效）
    """
    e = None
    for v in pl.load().values():
        if v["model"].lower() == model.lower():
            e = v
            break
    if not e:
        return None, None

    kw = name_kw.lower()
    cands = []
    for pid, info in e.get("params", {}).items():
        if info.get("kind") == "reserved":
            continue
        nm = (info.get("name") or "").lower()
        if kw not in nm:
            continue
        if nm == kw:
            score = 100
        elif nm.startswith(kw):
            score = 50
        else:
            score = 10
        if nm.endswith(" cv"):
            score -= 40
        cands.append((score, int(pid), info.get("name")))
    if not cands:
        return None, None
    cands.sort(key=lambda x: (-x[0], x[1]))
    return cands[0][1], cands[0][2]


def get_map_module(patch):
    for m in patch.get("modules", []):
        if m.get("model") == MODEL:
            return m
    return None


def show(path):
    d = patchio.read_patch(path)
    mm = get_map_module(d)
    print(f"机架: {os.path.basename(path)}")
    print(f"模块数: {len(d.get('modules', []))}  线缆: {len(d.get('cables', []))}")
    if not mm:
        print("\n[没有 HostMIDIMap 模块] —— 旋钮 CC 目前没人接收")
        return
    data = mm.get("data", {})
    print(f"HostMIDIMap: channel={data.get('channel')} "
          f"(0=全部通道) smooth={data.get('smooth')}")
    print("\n映射表:")
    print(f"  {'CC':<6}{'目标模块':<14}{'参数':<28}{'当前值'}")
    by_id = {m["id"]: m for m in d.get("modules", [])}
    for e in data.get("maps", []):
        cc, mid, pid = e.get("cc"), e.get("moduleId"), e.get("paramId")
        if cc is None or cc < 0 or mid is None or mid < 0:
            continue
        tgt = by_id.get(mid, {})
        info = (pl.lookup(tgt.get("plugin", ""), tgt.get("model", "")) or {}) \
            .get("params", {}).get(str(pid), {})
        cur = next((q.get("value") for q in (tgt.get("params") or [])
                    if q.get("id") == pid), None)
        print(f"  CC{cc:<4}{tgt.get('model', '?'):<14}"
              f"{info.get('name') or f'param{pid}':<28}{cur}")


def apply_map(path, spec=None, load=False):
    d = patchio.read_patch(path)
    spec = spec or DEFAULT_MAP

    mm = get_map_module(d)
    if not mm:
        # 新增模块。id 用一个不与现有冲突的大数。
        used = {m["id"] for m in d.get("modules", [])}
        new_id = 799138358763949
        while new_id in used:
            new_id += 1
        mm = {
            "id": new_id, "plugin": "Cardinal", "model": MODEL,
            "version": "2.0", "params": [],
            "data": {"maps": [], "smooth": True, "channel": 0},
            "pos": [46, 0],
        }
        d.setdefault("modules", []).append(mm)
        print(f"新增 HostMIDIMap 模块 id={new_id}")

    maps, report = [], []
    for row in spec:
        cc, model, pname = row[0], row[1], row[2]
        desc = row[3] if len(row) > 3 else ""
        mid = find_module(d, model)
        if mid is None:
            report.append(f"  [跳过] CC{cc}: 机架里没有 {model} 模块")
            continue
        pid, real = find_param_id(model, pname)
        if pid is None:
            report.append(f"  [跳过] CC{cc}: {model} 里找不到参数「{pname}」")
            continue
        maps.append({"cc": int(cc), "moduleId": int(mid), "paramId": int(pid)})
        report.append(f"  [OK]   CC{cc} -> {model}(id={mid}) param{pid} "
                      f"= {real}" + (f"   （{desc}）" if desc else ""))

    mm["data"] = {"maps": maps, "smooth": True, "channel": 0}
    patchio.write_patch(path, d)

    print(f"写入 {os.path.basename(path)}：{len(maps)} 条映射")
    print("\n".join(report))

    if load:
        import cardinal_mcp as cm
        r = cm.load_patch(path)
        print("\n推到 Cardinal:", json.dumps(r, ensure_ascii=False))
    return maps


def set_one(path, cc, model, pname, load=False):
    d = patchio.read_patch(path)
    mm = get_map_module(d)
    if not mm:
        return {"error": "机架里没有 HostMIDIMap，先跑 apply"}
    mid = find_module(d, model)
    if mid is None:
        return {"error": f"机架里没有 {model}"}
    pid, real = find_param_id(model, pname)
    if pid is None:
        return {"error": f"{model} 里找不到参数「{pname}」"}
    maps = [e for e in mm["data"]["maps"] if e.get("cc") != int(cc)]
    maps.append({"cc": int(cc), "moduleId": int(mid), "paramId": int(pid)})
    maps.sort(key=lambda e: e["cc"])
    mm["data"]["maps"] = maps
    patchio.write_patch(path, d)
    out = {"ok": True, "cc": cc, "target": f"{model} param{pid} ({real})"}
    if load:
        import cardinal_mcp as cm
        out["loaded"] = cm.load_patch(path)
    return out


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(0)
    cmd, path = sys.argv[1], sys.argv[2]
    load = "--load" in sys.argv
    if cmd == "show":
        show(path)
    elif cmd == "apply":
        apply_map(path, load=load)
    elif cmd == "set":
        args = [a for a in sys.argv[3:] if not a.startswith("--")]
        if len(args) < 3:
            print("用法: set <patch> <cc> <模块名> <参数名关键字>")
            sys.exit(1)
        print(json.dumps(set_one(path, args[0], args[1], args[2], load),
                         ensure_ascii=False, indent=2))
    else:
        print(__doc__)
