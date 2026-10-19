"""topology: 读机架的接线关系，并尽量说清「这是在干什么」

对应用户的需求：「读取场景里patches之间的连接、各个patch的参数设置——
这些人类能在屏幕上看到的内容，你也要能看到，而不是又去翻代码」。

数据来源两条，按可用性自动降级：
  1. 运行中（编译后的探针 `/cables` + `/param-get`）—— 权威，含实时电压
  2. 磁盘上的 .vcv 文件 —— 未编译时可用，但只是结构，不含信号

**诚实边界**：这里能回答「谁接到谁」「参数现在是多少」，但回答不了
「这声音好不好听」。后者需要李自己听。
"""

from __future__ import annotations

import os
from typing import Any

import patchio

PATCH_DIR = os.environ.get("CARDINAL_PATCH_DIR") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "patches"
)

#: 角色识别 —— 把 plugin|model 映射到「这一块在人眼里是什么」。
#: 两级来源，先查表再用 manifest 官方标签兜底，最后才认 unknown。
#:
#: 🔴 教训（10-19 实测）：手写表必然漏。life1 用 Bogaudio-Unison（复音振荡器），
#: 表里没有 → 判 unknown → 音源检测误报「没找到音源模块」。
#: ⇒ 必须用官方 tags 兜底，且**宁可标 unknown 也不要猜错角色**——
#: 错角色会让「链路走不通」的结论完全失真。
ROLES: dict[str, str] = {
    # 音源
    "VCO": "oscillator", "Bogaudio-VCO": "oscillator",
    "Rings": "oscillator", "Wavetable": "oscillator",
    "2hp": "source",
    # 调制
    "LFO": "lfo", "ALO": "lfo", "Clocked": "clock",
    "Sequencer": "sequencer", "Gnome": "sequencer",
    "Pianoroll": "sequencer", "rcm-pianoroll": "sequencer",
    "MiniArranger": "sequencer", "HostMIDI": "midi-in",
    # 包络 / VCA
    "ADSR": "envelope", "ADSRH": "envelope",
    "Envelope": "envelope", "VCA-1": "vca", "VCAm": "vca",
    # 滤波
    "VCF": "filter", "SVF": "filter", "Ladder": "filter",
    "Filter": "filter",
    # 空间 / 效果
    "Plateau": "reverb", "Reverb": "reverb", "Delay": "delay",
    "Mixer": "mixer", "MixMasterJr": "mixer",
    # 输出
    "HostAudio2": "audio-out", "Audio2": "audio-out",
    "Bogaudio-Mix8": "mixer",
}

#: manifest 官方标签 → 角色。这是权威来源（Cardinal 自己写的），不是我的猜测。
TAG_ROLE: dict[str, str] = {
    "Oscillator": "oscillator", "VCO": "oscillator",
    "Sequencer": "sequencer",
    "Sampler": "sampler", "Granular": "sampler",
    "Envelope generator": "envelope", "VCA": "vca",
    "Filter": "filter",
    "LFO": "lfo", "Low-frequency oscillator": "lfo",
    "Reverb": "reverb", "Delay": "delay",
    "Effect": "effect", "Waveshaper": "effect", "Distortion": "effect",
    "Mixer": "mixer", "Attenuator": "vca",
    "Utility": "utility", "Clock modulator": "clock",
    "Noise": "noise",
    "Polyphonic": "poly-note",  # 只是修饰，不是角色本身
}

#: 这些模块名里带的关键词 → 角色。用于表和 tags 都认不出时，
#: 关键词**明确**才算（宁可漏判，不要错判）。
NAME_HINTS: list[tuple[str, str]] = [
    ("unison", "oscillator"), ("osc", "oscillator"), ("vco", "oscillator"),
    ("synth", "oscillator"), ("fm", "oscillator"),
    ("piano", "sampler"), ("sample", "sampler"), ("grain", "sampler"),
    ("drum", "sampler"), ("kick", "sampler"), ("snare", "sampler"),
    ("seq", "sequencer"), ("quant", "sequencer"), ("arp", "sequencer"),
    ("adsr", "envelope"), ("env", "envelope"),
    ("vca", "vca"), ("amp", "vca"),
    ("filter", "filter"), ("svf", "filter"), ("ladder", "filter"),
    ("lpf", "filter"), ("hpf", "filter"), ("bpf", "filter"),
    ("reverb", "reverb"), ("hall", "reverb"), ("plate", "reverb"),
    ("delay", "delay"), ("echo", "delay"),
    ("mix", "mixer"),
    ("clock", "clock"), ("lfo", "lfo"),
]


def _role(plugin: str, model: str, tags: list[str] | None = None) -> tuple[str, str]:
    """返回 (role, 判定依据)。依据要如实透出，别装得很确定。"""
    if model in ROLES:
        return ROLES[model], "table:model"
    if plugin in ROLES:
        return ROLES[plugin], "table:plugin"
    key = f"{plugin}|{model}"
    if key in ROLES:
        return ROLES[key], "table:pairs"

    low = (model or "").lower()
    for hint, r in NAME_HINTS:
        if hint in low:
            return r, f"name_hint:{hint}"

    for t in tags or []:
        r = TAG_ROLE.get(t)
        if r and r != "poly-note":
            return r, f"tag:{t}"
    return "unknown", "unrecognized"


def _resolve(name: str) -> str | None:
    """patch 名 → 路径。容忍省略 .vcv 后缀。"""
    if not name:
        return None
    if os.path.isfile(name):
        return name
    p = os.path.join(PATCH_DIR, name)
    if os.path.isfile(p):
        return p
    if not name.endswith(".vcv"):
        p2 = p + ".vcv"
        if os.path.isfile(p2):
            return p2
    return None


def _mod_key(m: dict[str, Any]) -> str:
    return f"{m.get('plugin')}|{m.get('model')}"


def analyze(name: str, depth: int = 2) -> dict[str, Any]:
    """读一份机架，给出接线拓扑 + 每个模块的角色与参数。

    name   patch 名（可省略 .vcv）
    depth  沿信号流往下追几层（目前只做结构，不追）
    """
    path = _resolve(name)
    out: dict[str, Any] = {
        "patch": name,
        "source": None,
        "modules": [],
        "edges": [],
        "by_role": {},
        "counts": {},
    }
    if not path:
        out["error"] = f"找不到机架 {name}"
        out["patch_dir"] = PATCH_DIR
        out["hint"] = "先用 list_patches 看有哪些。"
        return out

    try:
        d = patchio.read_patch(path)
    except Exception as e:  # noqa: BLE001
        out["error"] = f"解析失败：{e}"
        return out

    out["source"] = "vcv_file"
    out["path"] = path
    out["source_note"] = (
        "读的是磁盘文件。若 Cardinal 开着且你手改过未保存，"
        "这里看不到 —— 用 read_live 或（编译后）live_modules 看运行中状态。"
    )

    mods = d.get("modules") or []
    cables = d.get("cables") or []
    by_id: dict[Any, dict[str, Any]] = {}

    # 从 manifest 库取官方 tags（角色识别的权威兜底）。读不到就空列表，
    # 不是错误 —— 只是角色判定退化成只看名字。
    tags_of: dict[str, list[str]] = {}
    tag_src = "unavailable"
    try:
        import modbrowser as mb

        mb.LIB.load()
        tag_src = mb.LIB.dir or "not_found"
        tags_of = {(m["plugin"], m["model"]): m["tags"] for m in mb.LIB.modules}
    except Exception as e:  # noqa: BLE001
        tag_src = f"error: {e}"

    for m in mods:
        mid = m.get("id")
        by_id[mid] = m
        pl, mo = m.get("plugin", ""), m.get("model", "")
        role, how = _role(pl, mo, tags_of.get((pl, mo)))
        pos = m.get("pos") or [0, 0]
        out["modules"].append(
            {
                "id": mid,
                "key": f"{pl}|{mo}",
                "plugin": pl,
                "model": mo,
                "name": m.get("alias") or mo,
                "role": role,
                "role_source": how,
                "official_tags": tags_of.get((pl, mo), []),
                "grid_pos": {"x": pos[0] if pos else None, "y": pos[1] if len(pos) > 1 else None},
                "params_set": len(m.get("params") or []),
            }
        )
        out["by_role"].setdefault(role, []).append(mid)

    for c in cables:
        # 🔴 字段名必须用 outputModuleId / inputModuleId（不是 outputModule）。
        # 10-19 实测：用错名字 ⇒ 所有边的两端都是 None ⇒ 24 条线全报 dangling，
        # 而机架其实是好的 —— 典型的「误报比漏报更伤」。
        om = c.get("outputModuleId", c.get("outputModule"))
        im = c.get("inputModuleId", c.get("inputModule"))
        src = by_id.get(om)
        dst = by_id.get(im)
        out["edges"].append(
            {
                "from": [om, c.get("outputId")],
                "to": [im, c.get("inputId")],
                "from_key": _mod_key(src) if src else None,
                "to_key": _mod_key(dst) if dst else None,
                "from_role": _role(src.get("plugin", ""), src.get("model", ""),
                                    tags_of.get((src.get("plugin", ""), src.get("model", ""))))[0] if src else "missing",
                "to_role": _role(dst.get("plugin", ""), dst.get("model", ""),
                                 tags_of.get((dst.get("plugin", ""), dst.get("model", ""))))[0] if dst else "missing",
                "dangling": bool(src is None or dst is None),
            }
        )

    out["role_tag_source"] = tag_src
    out["unknown_role_count"] = sum(1 for x in out["modules"] if x["role"] == "unknown")

    for r, ids in out["by_role"].items():
        out["counts"][r] = len(ids)

    out["dangling_edges"] = sum(1 for e in out["edges"] if e["dangling"])

    # 粗略的链路梳理：从音源到音频输出，看能不能走通
    out["_path"] = _trace_path(out, by_id)

    out["note"] = (
        "这里只回答「谁接到谁」。参数的真实显示值（275ms / 440Hz）需要编译后的 "
        "/param-get；这里只有 params 数组的长度，不含数值语义。"
    )
    return out


def _trace_path(out: dict[str, Any], by_id: dict[Any, dict[str, Any]]) -> dict[str, Any]:
    """从音源模块出发，走到音频输出。走不通就说走不通在哪。"""
    edges = out["edges"]
    # ⚠️ e["from"] / e["to"] 是 [moduleId, portId] 二元组，
    #    比较时必须取 [0]（10-19 实测踩过：拿二元组直接跟整数比，
    #    永远不等 ⇒ 误报「没找到音源模块」）。
    #
    # ⚠️ 音源角色不能只列 oscillator/sequencer。实测 demo_S5_fullkit 是
    #    一个**鼓组**机架（4 VCA + 2 filter + 1 envelope + 3 mixer + audio-out，
    #    无振荡器），音源在 sampler 上 —— 只认振荡器会误报「没找到音源」。
    src_roles = {
        "oscillator", "source", "sequencer", "sampler", "midi-in", "lfo",
        "noise", "physical-model",
    }
    dst_roles = {"audio-out"}

    starts = [e["from"][0] for e in edges if e["from_role"] in src_roles]
    ends = {e["to"][0] for e in edges if e["to_role"] in dst_roles}

    if not starts:
        return {
            "reachable": False,
            "reason": "没找到音源模块（oscillator/sequencer/sampler…）的输出线",
        }
    if not ends:
        return {
            "reachable": False,
            "reason": "没有线接到 HostAudio2（主输出）—— 机架不会出声",
        }

    # 有向可达性（BFS），用邻接表
    adj: dict[Any, list[Any]] = {}
    for e in edges:
        adj.setdefault(e["from"][0], []).append(e["to"][0])
    seen: set[Any] = set()
    stack = list(starts)
    while stack:
        n = stack.pop()
        if n in seen:
            continue
        seen.add(n)
        stack.extend(adj.get(n, []))
    hit = seen & ends
    return {
        "reachable": bool(hit),
        "reached_output_via": sorted(hit)[:5],
        "source_modules": starts[:8],
        "note": "静态连通性。信号是否真的在走，静态看不出 —— 用 scan_signal（编译后）。",
    }


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) < 2:
        print("usage: topology.py <patch>")
        sys.exit(1)
    print(json.dumps(analyze(sys.argv[1]), ensure_ascii=False, indent=2))