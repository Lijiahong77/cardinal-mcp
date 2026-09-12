"""params 字典：把 Cardinal 模块的「参数编号 -> 人类可读名字」抓下来。

为什么要这个文件
----------------
.vcv / patch.json 里参数只有编号和数值（{"id": 7, "value": 0.62}），没有名字。
所以「包络慢一点」「鼓闷一点」这种话落不到具体旋钮上。
这个模块从模块源码里解析 configParam / configSwitch / configButton，
产出参数字典 D:\\Cardinal\\params\\modules.json。

解析过程中踩到的坑（都已处理）
------------------------------
1. 枚举名有两种：`enum ParamIds`（Fundamental）和 `enum ParamId`（MixMaster）。
2. 一个源文件里可能有多个 enum 块（ParamIds / InputIds / OutputIds / LightIds），
   **只有 ParamId* 才是参数**，其余是端口/灯，混进来会造出大量假槽位。
3. 参数编号由 C++ 常量决定，且大量用循环生成：
   `for (int i = 0; i < N_TRK; i++) configParam(TRACK_PAN_PARAMS + i, ...)`
   —— 必须做块结构扫描 + 循环展开，否则只会得到 4 个参数而不是 72 个。
4. Rack 的 `ENUMS(NAME, n)` 宏把一个名字展开成 n 个连续编号：
   `ENUMS(RATIO_PARAMS, 4)` → RATIO_PARAMS+0..3。
   注意 `ENUMS(A, 4)` 自身含逗号，按逗号切分枚举体时必须跳过括号内逗号。
5. **废弃但占号**的参数：VCO/VCF 里写着 `FINE_PARAM, // removed in 2.0`，
   它仍然占一个编号，但没有 configParam。必须如实记录成 reserved，
   否则「第 3 号参数」会指错位置。
6. 枚举可能在头文件里（Plateau.hpp），且用 `Plateau::DRY_PARAM` 限定名。
7. 枚举可能在父类里（鼓模块的 SampleController.hpp），子类 .cpp 只做 configParam
   —— 所以要跨文件共享符号表。

用法
----
    python paramlib.py build                 # 抓取并写入字典
    python paramlib.py build --only Fundamental,Valley
    python paramlib.py show Fundamental VCF   # 看某个模块的参数表
    python paramlib.py search cutoff          # 按名字搜
    python paramlib.py verify                 # 用实际 patch 交叉验证
"""

import json
import os
import re
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(os.path.dirname(HERE), "params")
OUT_FILE = os.path.join(OUT_DIR, "modules.json")
CACHE_DIR = os.path.join(HERE, "_srccache")
RAW = "https://raw.githubusercontent.com"


# ================================================================ 源码抓取

def fetch(url, use_cache=True):
    os.makedirs(CACHE_DIR, exist_ok=True)
    key = re.sub(r"[^A-Za-z0-9]+", "_", url)[-140:]
    path = os.path.join(CACHE_DIR, key)
    if use_cache and os.path.exists(path) and os.path.getsize(path) > 0:
        with open(path, encoding="utf-8", errors="ignore") as f:
            return f.read()
    req = urllib.request.Request(url, headers={"User-Agent": "cardinal-paramlib"})
    try:
        text = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")
    except Exception:
        return None
    if text:
        with open(path, "w", encoding="utf-8", errors="ignore") as f:
            f.write(text)
    return text


def fetch_many(urls):
    for u in urls:
        t = fetch(u)
        if t and len(t) > 200 and "404: Not Found" not in t[:120]:
            return t, u
    return None, None


def match_brace(src, start):
    """从 start（指向 '{'）找到配对 '}' 的下标。"""
    depth, i = 0, start
    while i < len(src):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return len(src) - 1


# ================================================================ C++ 轻量解析

def strip_comments(src):
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    src = re.sub(r"//[^\n]*", "", src)
    return src


def split_args(inner):
    """按顶层逗号切分（跳过括号/花括号/方括号/字符串里的逗号）。"""
    parts, cur = [], ""
    depth, in_str, quote, i = 0, False, "", 0
    while i < len(inner):
        c = inner[i]
        if in_str:
            cur += c
            if c == "\\":
                cur += inner[i + 1:i + 2]
                i += 2
                continue
            if c == quote:
                in_str = False
            i += 1
            continue
        if c in "\"'":
            in_str, quote = True, c
            cur += c
            i += 1
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        if c == "," and depth == 0:
            parts.append(cur.strip())
            cur = ""
            i += 1
            continue
        cur += c
        i += 1
    if cur.strip():
        parts.append(cur.strip())
    return parts


_CONST_OK = re.compile(r"[\d\s+\-*/()<>&|^%~.]*")


def eval_const(expr, env):
    """求 C++ 常量表达式，求不出来返回 None。"""
    e = (expr or "").strip()
    if not e:
        return None
    e = re.sub(r"\b(?:float|double|int|uint8_t|uint16_t|uint32_t|uint64_t|size_t|unsigned)\b", "", e)
    e = re.sub(r"\([^()]*\)\s*(?=[\d+\-*/])", "", e)     # 去掉 (float) 之类 cast
    e = re.sub(r"\b\w+::", "", e)                          # Plateau::DRY_PARAM -> DRY_PARAM
    e = re.sub(r"\b([A-Za-z_]\w*)\b",
               lambda m: str(env[m.group(1)]) if m.group(1) in env else m.group(1), e)
    e = re.sub(r"(\d)[fF]\b", r"\1", e)
    e = e.strip()
    if not e or not _CONST_OK.fullmatch(e):
        return None
    if re.search(r"[A-Za-z_]", e):
        return None
    try:
        return eval(e, {"__builtins__": {}}, {})
    except Exception:
        return None


def parse_defines(src):
    env = {}
    for m in re.finditer(r"^\s*#define\s+(\w+)\s+([^\n\\]+)", src, re.M):
        v = eval_const(m.group(2).strip(), {})
        if v is not None:
            env[m.group(1)] = v
    return env


def find_calls(src, name):
    """找出所有 name(...) 调用，返回 [(位置, 实参文本)]。"""
    out = []
    for m in re.finditer(r"\b" + name + r"\s*(<[^;(){}]*?>)?\s*\(", src):
        start = m.end() - 1
        depth, in_str, quote, i = 0, False, "", start
        while i < len(src):
            c = src[i]
            if in_str:
                if c == "\\":
                    i += 2
                    continue
                if c == quote:
                    in_str = False
                i += 1
                continue
            if c == '"':
                in_str, quote = True, '"'
                i += 1
                continue
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        out.append((start, src[start + 1:i]))
    return out


def parse_enums(src, defines):
    """解析所有 enum 块。

    返回 (符号表 env, 参数字典 param_syms)
    param_syms 只包含 ParamId / ParamIds 块里的符号 —— 端口/灯枚举不算参数。
    """
    env = dict(defines)
    blocks = []
    for m in re.finditer(r"enum\s+(\w+)\s*(?::\s*\w+\s*)?\{", src):
        name = m.group(1)
        start = m.end() - 1
        body = src[start + 1:match_brace(src, start)]
        blocks.append((name, body))

    param_syms = {}
    for _ in range(4):        # 多轮，让后面的块能引用前面的值
        param_syms = {}
        for name, body in blocks:
            is_param = name.startswith("ParamId")
            idx = 0
            for tok in split_args(body):
                tok = tok.strip()
                if not tok:
                    continue
                em = re.fullmatch(r"ENUMS\s*\(\s*(\w+)\s*,\s*([^()]+)\s*\)", tok)
                if em:
                    base = em.group(1)
                    cnt = eval_const(em.group(2), env)
                    if cnt is None:
                        continue
                    env[base] = idx
                    if is_param:
                        param_syms[base] = (name, idx)
                    idx += int(cnt)
                    continue
                if "=" in tok:
                    nm, val = tok.split("=", 1)
                    nm = nm.strip()
                    v = eval_const(val, env)
                    if v is None:
                        continue
                    idx = int(v)
                else:
                    nm = tok
                if re.fullmatch(r"\w+", nm):
                    env[nm] = idx
                    if is_param:
                        param_syms[nm] = (name, idx)
                    idx += 1
    return env, param_syms


FOR_HEAD = re.compile(
    r"for\s*\(\s*(?:int|unsigned|uint8_t|uint16_t|uint32_t|size_t|auto)\s+(\w+)\s*=\s*([^;]+);"
    r"\s*\1\s*<\s*([^;]+);\s*\1\s*\+\+\s*\)\s*\{")


def scan_loops(src):
    loops = []
    for m in FOR_HEAD.finditer(src):
        loops.append({"start": m.end() - 1, "end": match_brace(src, m.end() - 1),
                      "var": m.group(1), "lo": m.group(2).strip(), "hi": m.group(3).strip()})
    loops.sort(key=lambda x: x["start"])
    return loops


def innermost_loop(loops, pos):
    hits = [l for l in loops if l["start"] <= pos <= l["end"]]
    return min(hits, key=lambda l: l["end"] - l["start"]) if hits else None


def num(expr, env):
    v = eval_const(expr, env) if expr else None
    return None if v is None else float(v)


def label_of(expr):
    if not expr:
        return None
    m = re.search(r'"([^"]*)"', expr)
    return m.group(1) if m else None


def parse_module(src, env):
    """解析一个源文件里的 configParam 调用。env 为跨文件共享符号表。"""
    src = strip_comments(src)
    env = dict(env)
    env.update(parse_defines(src))
    _, local_syms = parse_enums(src, env)
    loops = scan_loops(src)
    params = {}

    specs = [("configParam", "knob"), ("configParamNoRand", "knob"),
             ("configSwitch", "switch"), ("configButton", "button")]
    for fname, kind in specs:
        for pos, inner in find_calls(src, fname):
            args = split_args(inner)
            if len(args) < 2:
                continue
            loop = innermost_loop(loops, pos)
            envs = [{}]
            if loop:
                lo = eval_const(loop["lo"], env)
                hi = eval_const(loop["hi"], env)
                if lo is not None and hi is not None and 0 <= hi - lo <= 128:
                    envs = [{loop["var"]: k} for k in range(int(lo), int(hi))]
            for extra in envs:
                e = dict(env)
                e.update(extra)
                pid = eval_const(args[0], e)
                if pid is None:
                    continue
                pid = int(pid)
                if pid in params and params[pid].get("name"):
                    continue
                entry = {"kind": kind, "enum": args[0].strip(), "name": None,
                         "min": None, "max": None, "default": None}
                if kind == "button":
                    entry["name"] = label_of(args[1])
                elif len(args) > 4:
                    entry["name"] = label_of(args[4])
                    entry["min"] = num(args[1], e)
                    entry["max"] = num(args[2], e)
                    entry["default"] = num(args[3], e)
                    unit = label_of(args[5]) if len(args) > 5 else None
                    if unit:
                        entry["unit"] = unit
                    if kind == "switch":
                        opts = [x for x in (label_of(a) for a in args[5:]) if x]
                        if opts:
                            entry["options"] = opts
                params[pid] = entry
    return params, local_syms


# ================================================================ 模块 -> 源码

REPOS = {
    "Fundamental": ("CardinalModules/Fundamental", "master", "src"),
    "Cardinal": ("DISTRHO/Cardinal", "main", "plugins/Cardinal/src"),
    "ImpromptuModular": ("MarcBoule/ImpromptuModular", "master", "src"),
    "MindMeldModular": ("MarcBoule/MindMeldModular", "master", "src"),
    "Valley": ("ValleyAudio/ValleyRackFree", "main", "src"),
    "WSTD-Drums": ("Wasted-Audio/WSTD-Drums", "master", "src"),
}

SOURCES = {
    ("Fundamental", "VCA-1"): ["src/VCA.cpp"],
    ("Fundamental", "VCF"): ["src/VCF.cpp"],
    ("Fundamental", "VCO"): ["src/VCO.cpp"],
    ("Fundamental", "ADSR"): ["src/ADSR.cpp"],
    ("Fundamental", "Mixer"): ["src/Mixer.cpp"],
    ("Fundamental", "Sum"): ["src/Sum.cpp"],
    ("Cardinal", "HostMIDI"): ["plugins/Cardinal/src/HostMIDI.cpp"],
    ("Cardinal", "HostAudio2"): ["plugins/Cardinal/src/HostAudio.cpp"],
    ("Cardinal", "TextEditor"): ["plugins/Cardinal/src/TextEditor.cpp"],
    ("ImpromptuModular", "Clocked"): ["src/Clocked.cpp"],
    ("MindMeldModular", "MixMasterJr"): ["src/MixMaster/MixMaster.cpp"],
    ("Valley", "Plateau"): ["src/Plateau/Plateau.cpp"],
    ("WSTD-Drums", "BassDrum9"): ["src/controller/BD9.cpp", "src/controller/SampleController.hpp"],
    ("WSTD-Drums", "ClosedHiHat"): ["src/controller/ClosedHH.cpp", "src/controller/SampleController.hpp"],
    ("WSTD-Drums", "CR78"): ["src/controller/CR78.cpp", "src/controller/SampleController.hpp"],
    ("WSTD-Drums", "SnareDrumN"): ["src/controller/Snare.cpp", "src/controller/SampleController.hpp"],
    ("WSTD-Drums", "OpenHiHat"): ["src/controller/OpenHH.cpp", "src/controller/SampleController.hpp"],
    ("WSTD-Drums", "Tomi"): ["src/controller/Tomi.cpp", "src/controller/SampleController.hpp"],
    ("WSTD-Drums", "DMX"): ["src/controller/DMX.cpp", "src/controller/SampleController.hpp"],
    ("WSTD-Drums", "Sequencer"): ["src/controller/Sequencer.cpp"],
}


def raw_url(plugin, rel):
    owner, branch, _ = REPOS[plugin]
    return "{}/{}/{}/{}".format(RAW, owner, branch, rel)


def guess_rels(plugin, model):
    _owner, _branch, sub = REPOS[plugin]
    rels = []
    for n in (model, model.replace("-", ""), model.replace("-", "_")):
        rels += ["{}/{}.cpp".format(sub, n), "{}/{}/{}.cpp".format(sub, n, n)]
    return rels


# ---------------------------------------------- 手工规则（循环生成 + 动态名字）

def gen_mixmasterjr():
    """MixMasterJr：8 轨 + 2 编组 + master，共 72 个参数。

    编号来源：MixMaster.cpp 构造函数里的循环结构 + MixMaster.hpp 的枚举常量。
    交叉验证：8*7 + 2*6 + 4 = 72，与 patch 里实测参数个数完全一致。
    名字来源：构造函数里 snprintf 的格式串（如 "-%02i-: pan"）。
    """
    p = {}

    def add(i, name, lo, hi, d, kind="knob", unit=None):
        e = {"kind": kind, "name": name, "min": lo, "max": hi, "default": d}
        if unit:
            e["unit"] = unit
        p[str(i)] = e

    def block(base, suffix, lo, hi, d, unit, count, fmt):
        for i in range(count):
            add(base + i, fmt.format(i + 1, suffix), lo, hi, d,
                "switch" if suffix in ("mute", "solo") else "knob", unit)

    for suffix, base, lo, hi, d, unit in [
            ("pan", 0, 0.0, 1.0, 0.5, "%"),
            ("level", 8, 0.0, 2.0, 1.0, "dB"),
            ("mute", 16, 0.0, 1.0, 0.0, None),
            ("solo", 24, 0.0, 1.0, 0.0, None),
            ("group", 32, 0.0, 2.0, 0.0, None),
            ("HPF cutoff", 40, 13.0, 1000.0, 20.0, "Hz"),
            ("LPF cutoff", 48, 1000.0, 21000.0, 20000.0, "Hz")]:
        block(base, suffix, lo, hi, d, unit, 8, "-{:02d}-: {}")

    for suffix, base, lo, hi, d, unit in [
            ("pan", 56, 0.0, 1.0, 0.5, "%"),
            ("level", 58, 0.0, 2.0, 1.0, "dB"),
            ("mute", 60, 0.0, 1.0, 0.0, None),
            ("solo", 62, 0.0, 1.0, 0.0, None),
            ("HPF cutoff", 64, 13.0, 1000.0, 20.0, "Hz"),
            ("LPF cutoff", 66, 1000.0, 21000.0, 20000.0, "Hz")]:
        block(base, suffix, lo, hi, d, unit, 2, "GRP{}: {}")

    add(68, "MASTER: level", 0.0, 2.0, 1.0, "knob", "dB")
    add(69, "MASTER: mute", 0.0, 1.0, 0.0, "switch")
    add(70, "MASTER: dim", 0.0, 1.0, 0.0, "switch")
    add(71, "MASTER: mono", 0.0, 1.0, 0.0, "switch")
    return p


MANUAL = {
    "MindMeldModular/MixMasterJr": {
        "source": "手工整理（MixMaster.cpp 构造函数循环 + MixMaster.hpp 枚举）",
        "params": gen_mixmasterjr(),
    },
}


def fill_drums(params, sample_max=15.0):
    """鼓模块的槽位补全。

    源码里 `configParam(DRUM_PARAM, ...)` 和 `DRUM_PARAM + 1` 只配置了 2 个鼓声，
    但父类声明了 `NUM_PARAMS = TUNE_PARAM + MAX_MODULES = 32`——patch 里 32 个槽位
    全都在。按 MAX_MODULES=16 的规律补全，让任何编号都能查到含义。
    """
    out = {str(k): v for k, v in params.items()}
    for i in range(16):
        k = str(i)
        if k not in out:
            out[k] = {"kind": "knob", "enum": "DRUM_PARAM + {}".format(i), "name": "Sample",
                      "min": 0.0, "max": sample_max, "default": 7.0,
                      "note": "未使用槽位（本模块只启用前 2 个鼓声）"}
    for i in range(16):
        k = str(16 + i)
        if k not in out:
            out[k] = {"kind": "knob", "enum": "TUNE_PARAM + {}".format(i),
                      "name": "Playback Speed", "min": 0.2, "max": 1.8,
                      "default": 1.0, "unit": "x",
                      "note": "未使用槽位（本模块只启用前 2 个鼓声）"}
    return out


def fix_templated_names(params):
    """修掉名字里的 printf 占位符。

    源码里名字常是运行时拼的：`string::f("Clk %i ratio", i + 1)`、
    `snprintf(strBuf, 32, "-%02i-: pan", i + 1)`。静态解析只能拿到模板串，
    这里按「同一个枚举基名」分组，用组内序号把 %i / %02i 填成真实数字。
    """
    groups = {}
    for pid, p in params.items():
        nm = p.get("name") or ""
        if "%" not in nm:
            continue
        m = re.match(r"([A-Za-z_]\w*)", p.get("enum") or "")
        base = m.group(1) if m else nm
        groups.setdefault(base, []).append(pid)
    for _base, pids in groups.items():
        for n, pid in enumerate(sorted(pids, key=lambda x: int(x)), 1):
            params[pid]["name"] = re.sub(r"%0?\d*[ids]", str(n), params[pid]["name"])
    return params


# ================================================================ 建档

def plan_from_patches(patch_dir):
    sys.path.insert(0, HERE)
    import patchio
    need, size = set(), {}
    if not os.path.isdir(patch_dir):
        return [], {}
    for fn in sorted(os.listdir(patch_dir)):
        if not fn.endswith(".vcv"):
            continue
        try:
            d = patchio.read_patch(os.path.join(patch_dir, fn))
        except Exception:
            continue
        for m in d.get("modules", []):
            key = (m["plugin"], m["model"])
            need.add(key)
            ids = [q.get("id") for q in (m.get("params") or []) if q.get("id") is not None]
            if ids:
                size[key] = max(size.get(key, 0), max(ids) + 1)
    return sorted(need), size


def build(patch_dir=None, only=None, quiet=False):
    patch_dir = patch_dir or os.path.join(os.path.dirname(HERE), "patches")
    targets, sizes = plan_from_patches(patch_dir)
    lib = {}
    if os.path.exists(OUT_FILE):
        try:
            lib = json.load(open(OUT_FILE, encoding="utf-8"))
        except Exception:
            lib = {}

    for plugin, model in targets:
        key = "{}/{}".format(plugin, model)
        if only and plugin not in only and model not in only:
            continue

        manual = MANUAL.get(key)
        if manual:
            lib[key] = {"plugin": plugin, "model": model, "source": manual["source"],
                        "params": manual["params"]}
            if not quiet:
                print("  [manual] {:<34} {:>3} 个参数".format(key, len(manual["params"])))
            continue

        if plugin not in REPOS:
            if not quiet:
                print("  [skip]   {:<34} 无源码地址".format(key))
            continue

        rels = SOURCES.get((plugin, model)) or guess_rels(plugin, model)
        # 自动补同目录同名头文件（枚举常在 .hpp 里）
        expanded = []
        for rel in rels:
            expanded.append(rel)
            if rel.endswith(".cpp"):
                expanded.append(rel[:-4] + ".hpp")
        files = []
        for rel in expanded:
            t = fetch(raw_url(plugin, rel))
            if t:
                files.append((rel, t))
        if not files:
            if not quiet:
                print("  [miss]   {:<34} 找不到源文件".format(key))
            continue

        # 1) 先建立跨文件共享符号表（父类头文件里的枚举要能被子类 cpp 用上）
        shared = {}
        for _rel, t in files:
            body = strip_comments(t)
            shared.update(parse_defines(body))
            env, _ = parse_enums(body, shared)
            shared.update(env)

        # 2) 再逐文件解析 configParam，并收集参数枚举符号
        params = {}
        syms = {}
        for _rel, t in files:
            p, s = parse_module(t, shared)
            for k, v in p.items():
                if k not in params or not params[k].get("name"):
                    params[k] = v
            for k, v in s.items():
                syms.setdefault(k, v)

        # 3) 枚举里有、但没 configParam 的编号 -> reserved（只取参数枚举）
        limit = sizes.get((plugin, model))
        for nm, (enum_name, idx) in syms.items():
            if re.search(r"_LEN$|_LAST$|^NUM_", nm):
                continue
            idx = int(idx)
            if limit is not None and idx >= limit:
                continue
            if idx not in params:
                params[idx] = {"kind": "reserved", "enum": nm, "name": None,
                               "note": "枚举占位，无 configParam（废弃或未使用）"}

        # 4) 超出该模块实际参数个数的空槽位一律丢掉
        if limit is not None:
            params = {k: v for k, v in params.items()
                      if k < limit or (v.get("name") and v["kind"] != "reserved")}

        # 5) 后处理：补全鼓模块的空槽 / 修掉名字里的 printf 占位符
        if plugin == "WSTD-Drums":
            params = fill_drums(params)
        params = fix_templated_names(params)

        lib[key] = {"plugin": plugin, "model": model,
                    "source": ", ".join(r for r, _ in files),
                    "params": {str(k): v for k, v in sorted(params.items(),
                                                             key=lambda x: int(x[0]))}}
        named = sum(1 for v in params.values() if v.get("name"))
        if not quiet:
            head = [v["name"] for k, v in sorted(params.items(), key=lambda x: int(x[0]))
                    if v.get("name")][:4]
            print("  [ok]     {:<34} {:>3} 槽 / {:>3} 有名  {}".format(
                key, len(params), named, "、".join(head)))

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(lib, f, ensure_ascii=False, indent=1, sort_keys=True)
    return lib


# ================================================================ 查询接口

_CACHE = {"lib": None, "mtime": None}


def load():
    if not os.path.exists(OUT_FILE):
        return {}
    mtime = os.path.getmtime(OUT_FILE)
    if _CACHE["lib"] is None or _CACHE["mtime"] != mtime:
        _CACHE["lib"] = json.load(open(OUT_FILE, encoding="utf-8"))
        _CACHE["mtime"] = mtime
    return _CACHE["lib"]


ALIAS = {"DrumKit": "WSTD-Drums"}
MODEL_ALIAS = {"BD9": "BassDrum9", "ClosedHH": "ClosedHiHat", "Snare": "SnareDrumN",
               "OpenHH": "OpenHiHat"}

# 中文口语 -> 参数名里可能出现的英文关键词。
# 参数名全是英文，但用户说中文；没有这张表，「滤波亮一点」就翻译不出来。
TERMS = {
    "亮": ["cutoff", "freq", "bright", "tone", "high"],
    "暗": ["cutoff", "freq", "low", "damp"],
    "闷": ["cutoff", "freq", "low", "damp", "drive"],
    "截止": ["cutoff", "freq"],
    "滤波": ["cutoff", "freq", "filter", "drive", "resonance"],
    "共振": ["resonance", "reso"],
    "尖": ["resonance", "drive"],
    "起音": ["attack"],
    "起手": ["attack"],
    "衰减": ["decay"],
    "保持": ["sustain"],
    "释放": ["release"],
    "尾巴": ["release", "decay", "size"],
    "混响": ["wet", "size", "decay", "dry", "diffusion"],
    "空间": ["wet", "size", "diffusion"],
    "干": ["dry"],
    "湿": ["wet"],
    "音量": ["level", "volume", "gain", "fader"],
    "响": ["level", "volume", "gain", "fader"],
    "静音": ["mute"],
    "独奏": ["solo"],
    "声像": ["pan"],
    "左右": ["pan"],
    "编组": ["group"],
    "深度": ["depth", "modulation", "cv"],
    "速度": ["speed", "rate", "bpm", "clock", "ratio", "delay"],
    "快": ["speed", "rate", "ratio", "bpm"],
    "慢": ["speed", "rate", "ratio", "delay"],
    "延迟": ["delay", "pre-delay"],
    "摆动": ["swing"],
    "脉冲": ["pulse", "width"],
    "采样": ["sample"],
    "音高": ["pitch", "frequency"],
    "调制": ["modulation", "mod", "cv", "fm"],
    "大小": ["size"],
    "扩散": ["diffusion"],
    "高通": ["hpf", "low cut"],
    "低通": ["lpf", "high cut"],
    "输入": ["input"],
    "包络": ["attack", "decay", "sustain", "release"],
    "力度": ["velocity", "modulation"],
    "长度": ["pulse", "width", "size", "decay"],
    "压缩": ["compress", "dim", "level"],
    "调性": ["bpm", "clock"],
    "节拍": ["bpm", "clock", "swing"],
    "分频": ["ratio", "div"],
}


def lookup(plugin, model):
    lib = load()
    for p in (plugin, ALIAS.get(plugin, plugin)):
        for m in (model, MODEL_ALIAS.get(model, model)):
            hit = lib.get("{}/{}".format(p, m))
            if hit:
                return hit
    for v in lib.values():
        if v.get("model") == model:
            return v
    return None


def name_of(plugin, model, param_id):
    e = lookup(plugin, model)
    if not e:
        return None
    p = e["params"].get(str(param_id))
    if not p:
        return None
    return p.get("name")


def describe(plugin, model, param_id):
    e = lookup(plugin, model)
    return e["params"].get(str(param_id)) if e else None


def search(keyword, limit=40):
    kw = keyword.lower()
    hits = []
    for key, mod in load().items():
        for pid, p in mod["params"].items():
            nm = p.get("name") or ""
            if kw in nm.lower() or kw in (p.get("enum") or "").lower():
                hits.append({"module": key, "param": int(pid), "name": nm,
                             "kind": p.get("kind"), "min": p.get("min"),
                             "max": p.get("max"), "default": p.get("default")})
            if len(hits) >= limit:
                return hits
    return hits


def resolve_name(plugin, model, human):
    """把「人话」映射到参数编号，返回 [(匹配分, 编号, 名字)]。

    参数名都是英文（Cutoff frequency / Release / Wet level…），但用户说中文。
    所以先把口语词展开成可能对应的英文关键词，再去匹配参数名。
    """
    e = lookup(plugin, model)
    if not e:
        return []
    words = [w for w in re.split(r"[\s,，/]+", human.lower()) if w]

    terms = set(words)
    for w in words:
        for cn, syns in TERMS.items():
            if cn in w or w in cn:
                terms.update(syns)

    scored = []
    for pid, p in e["params"].items():
        nm = (p.get("name") or "").lower()
        if not nm:
            continue
        score = sum(1 for t in terms if t and t in nm)
        if score:
            scored.append((score, int(pid), p.get("name")))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return scored


def verify(patch_dir=None, verbose=True):
    sys.path.insert(0, HERE)
    import patchio
    patch_dir = patch_dir or os.path.join(os.path.dirname(HERE), "patches")
    problems = []
    if not os.path.isdir(patch_dir):
        return problems
    for fn in sorted(os.listdir(patch_dir)):
        if not fn.endswith(".vcv"):
            continue
        try:
            d = patchio.read_patch(os.path.join(patch_dir, fn))
        except Exception:
            continue
        for m in d.get("modules", []):
            given = sorted(q.get("id") for q in (m.get("params") or []))
            if not given:
                continue
            e = lookup(m["plugin"], m["model"])
            if not e:
                problems.append((fn, m["plugin"], m["model"], "字典里没有这个模块"))
                continue
            known = sorted(int(k) for k in e["params"])
            missing = [g for g in given if g not in known]
            if missing:
                problems.append((fn, m["plugin"], m["model"],
                                 "patch 有字典缺: {}".format(missing)))
            if verbose:
                print("  {:<36} {:<20} patch {:>3} / 字典 {:>3}".format(
                    m["plugin"] + "/" + m["model"], fn[:18], len(given), len(known)))
    return problems


# ================================================================ CLI

def main(argv):
    if len(argv) < 2 or argv[1] == "build":
        only = set(argv[argv.index("--only") + 1].split(",")) if "--only" in argv else None
        lib = build(only=only)
        named = sum(1 for v in lib.values() for p in v["params"].values() if p.get("name"))
        print("\n{} 个模块建档 / {} 个命名参数 -> {}".format(len(lib), named, OUT_FILE))
        return 0

    if argv[1] == "show":
        e = lookup(argv[2], argv[3])
        if not e:
            print("没有建档:", argv[2], argv[3])
            return 1
        print("{}  来源: {}".format(e["model"], e["source"]))
        for k, v in sorted(e["params"].items(), key=lambda x: int(x[0])):
            bits = []
            if v.get("min") is not None and v.get("max") is not None:
                bits.append("{}..{}".format(v["min"], v["max"]))
            if v.get("default") is not None:
                bits.append("def={}".format(v["default"]))
            if v.get("unit"):
                bits.append(v["unit"])
            print("  {:>3}  {:<24} {:<9} {}".format(
                k, v.get("name") or "(未使用)", v["kind"], " ".join(bits)))
        return 0

    if argv[1] == "search":
        for h in search(argv[2]):
            print("  {:<34} {:>3}  {}".format(h["module"], h["param"], h["name"]))
        return 0

    if argv[1] == "verify":
        probs = verify()
        print()
        if probs:
            print("发现 {} 处不一致:".format(len(probs)))
            for p in probs:
                print("  {} {} {} -> {}".format(*p))
            return 1
        print("全部一致")
        return 0

    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
