"""Parameter dictionary: recover each Cardinal module's "param number -> human name".

WHY THIS FILE EXISTS
--------------------
A .vcv / patch.json stores parameters only as numbers and values
({"id": 7, "value": 0.62}) — no names. So a request like "make the envelope slower"
or "mute the drum" cannot be mapped to a concrete knob. This module parses the
module's C++ source (configParam / configSwitch / configButton) and produces the
parameter dictionary at D:\\Cardinal\\params\\modules.json.

Pitfalls hit while parsing (all handled)
---------------------------------------
1. Two enum-name styles: `enum ParamIds` (Fundamental) and `enum ParamId` (MixMaster).
2. One source file can contain several enum blocks (ParamIds / InputIds / OutputIds /
   LightIds). ONLY ParamId* entries are parameters; the others are ports/lights and
   would manufacture huge numbers of fake slots if mixed in.
3. Param numbers come from C++ constants and are heavily loop-generated:
   `for (int i = 0; i < N_TRK; i++) configParam(TRACK_PAN_PARAMS + i, ...)`
   — we MUST do block-structure scanning + loop unrolling, or we get 4 params
   instead of 72.
4. Rack's `ENUMS(NAME, n)` macro expands one name into n consecutive numbers:
   `ENUMS(RATIO_PARAMS, 4)` -> RATIO_PARAMS+0..3. Note `ENUMS(A, 4)` itself contains a
   comma, so splitting an enum body on commas must skip commas inside parentheses.
5. REMOVED-BUT-RESERVED params: VCO/VCF have `FINE_PARAM, // removed in 2.0` which
   still occupies a number but has no configParam. We must record it as "reserved"
   or "param #3" would point at the wrong slot.
6. The enum may live in a header (Plateau.hpp), qualified as `Plateau::DRY_PARAM`.
7. The enum may live in a PARENT class (drum modules' SampleController.hpp); the
   child .cpp only does configParam — so we must share one symbol table across files.

USAGE
----
    python paramlib.py build                 # scrape sources and write the dictionary
    python paramlib.py build --only Fundamental,Valley
    python paramlib.py show Fundamental VCF   # dump one module's param table
    python paramlib.py search cutoff          # search by name
    python paramlib.py verify                 # cross-check against real patches
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


# ================================================================ Source fetching

def fetch(url, use_cache=True):
    """Download a source file (with a local cache so we don't re-hit GitHub).

    Returns the text, or None on failure. The cache key is a URL-slugged name;
    cached files let `build` run fully offline after the first successful scrape.
    """
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
    """Try several candidate URLs; return (text, url) of the first that has real content."""
    for u in urls:
        t = fetch(u)
        if t and len(t) > 200 and "404: Not Found" not in t[:120]:
            return t, u
    return None, None


def match_brace(src, start):
    """Given `start` pointing at a '{', return the index of its matching '}'."""
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


# ================================================================ Lightweight C++ parsing

def strip_comments(src):
    """Remove /* */ and // comments so they can't fool the tokenisers."""
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    src = re.sub(r"//[^\n]*", "", src)
    return src


def split_args(inner):
    """Split a paren body on TOP-LEVEL commas (skip commas inside (), [], {}, strings)."""
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
    """Best-effort evaluation of a C++ constant expression; None if it can't be done.

    We strip type keywords and casts, resolve identifiers from `env`, drop float
    suffixes, then only accept a pure arithmetic expression before calling eval().
    This is intentionally conservative — anything that still contains a letter is
    refused rather than guessed wrong.
    """
    e = (expr or "").strip()
    if not e:
        return None
    e = re.sub(r"\b(?:float|double|int|uint8_t|uint16_t|uint32_t|uint64_t|size_t|unsigned)\b", "", e)
    e = re.sub(r"\([^()]*\)\s*(?=[\d+\-*/])", "", e)     # drop (float)-style casts
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
    """Collect #define macros whose value is a pure constant, into an env dict."""
    env = {}
    for m in re.finditer(r"^\s*#define\s+(\w+)\s+([^\n\\]+)", src, re.M):
        v = eval_const(m.group(2).strip(), {})
        if v is not None:
            env[m.group(1)] = v
    return env


def find_calls(src, name):
    """Find every `name(...)` call; return [(start_index, arg_text)]."""
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
    """Parse all enum blocks.

    Returns (symbol_env, param_syms). `param_syms` holds ONLY the symbols inside a
    ParamId / ParamIds block — port/light enums are excluded from the parameter set.
    Runs several passes so later blocks can reference earlier values.
    """
    env = dict(defines)
    blocks = []
    for m in re.finditer(r"enum\s+(\w+)\s*(?::\s*\w+\s*)?\{", src):
        name = m.group(1)
        start = m.end() - 1
        body = src[start + 1:match_brace(src, start)]
        blocks.append((name, body))

    param_syms = {}
    for _ in range(4):        # multiple passes let later blocks use earlier values
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
    """Find `for` loops; record their span and the loop variable + bounds."""
    loops = []
    for m in FOR_HEAD.finditer(src):
        loops.append({"start": m.end() - 1, "end": match_brace(src, m.end() - 1),
                      "var": m.group(1), "lo": m.group(2).strip(), "hi": m.group(3).strip()})
    loops.sort(key=lambda x: x["start"])
    return loops


def innermost_loop(loops, pos):
    """Return the innermost loop (smallest span) containing `pos`, or None."""
    hits = [l for l in loops if l["start"] <= pos <= l["end"]]
    return min(hits, key=lambda l: l["end"] - l["start"]) if hits else None


def num(expr, env):
    """Evaluate a numeric constant expression to float, or None."""
    v = eval_const(expr, env) if expr else None
    return None if v is None else float(v)


def label_of(expr):
    """Extract the first quoted string from an argument, or None."""
    if not expr:
        return None
    m = re.search(r'"([^"]*)"', expr)
    return m.group(1) if m else None


def parse_module(src, env):
    """Parse configParam / configSwitch / configButton calls in one source file.

    `env` is the cross-file shared symbol table (so a child .cpp sees its parent
    class's enums). Loop-generated params are unrolled by instantiating the loop
    variable over its [lo, hi) range.
    """
    src = strip_comments(src)
    env = dict(env)
    env.update(parse_defines(src))
    _, local_syms = parse_enums(src, env)
    loops = scan_loops(src)
    params = {}

    # The four Rack factory functions that register a param, with their "kind".
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
                    # configParam(name, min, max, default, label, unit?, ...)
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


# ================================================================ module -> source map

REPOS = {
    "Fundamental": ("CardinalModules/Fundamental", "master", "src"),
    "Cardinal": ("DISTRHO/Cardinal", "main", "plugins/Cardinal/src"),
    "ImpromptuModular": ("MarcBoule/ImpromptuModular", "master", "src"),
    "MindMeldModular": ("MarcBoule/MindMeldModular", "master", "src"),
    "Valley": ("ValleyAudio/ValleyRackFree", "main", "src"),
    "WSTD-Drums": ("Wasted-Audio/WSTD-Drums", "master", "src"),
}

# Exact (plugin, model) -> list of source-relative paths. Headers (.hpp) are added
# automatically later (the enum often lives there).
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
    """Build a raw.githubusercontent.com URL for a source file."""
    owner, branch, _ = REPOS[plugin]
    return "{}/{}/{}/{}".format(RAW, owner, branch, rel)


def guess_rels(plugin, model):
    """When SOURCES has no exact entry, guess candidate paths from the model name."""
    _owner, _branch, sub = REPOS[plugin]
    rels = []
    for n in (model, model.replace("-", ""), model.replace("-", "_")):
        rels += ["{}/{}.cpp".format(sub, n), "{}/{}/{}.cpp".format(sub, n, n)]
    return rels


# ---------------------------------------------- Manual rules (loop-gen + dynamic names)

def gen_mixmasterjr():
    """MixMasterJr: 8 tracks + 2 groups + master = 72 params.

    Numbers come from MixMaster.cpp's constructor loop structure + MixMaster.hpp's
    enum constants. Cross-check: 8*7 + 2*6 + 4 = 72, matching the param count
    measured in the real patch. Names come from the snprintf format strings in the
    constructor (e.g. "-%02i-: pan").
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
        "source": "hand-built (MixMaster.cpp constructor loops + MixMaster.hpp enum)",
        "params": gen_mixmasterjr(),
    },
}


def fill_drums(params, sample_max=15.0):
    """Backfill the drum module's slot map.

    The source configParam(DRUM_PARAM, ...) and DRUM_PARAM + 1 only enable 2 drum
    voices, but the parent class declares NUM_PARAMS = TUNE_PARAM + MAX_MODULES = 32 —
    all 32 slots exist in the patch. We fill by the MAX_MODULES=16 pattern so any
    number can be looked up.
    """
    out = {str(k): v for k, v in params.items()}
    for i in range(16):
        k = str(i)
        if k not in out:
            out[k] = {"kind": "knob", "enum": "DRUM_PARAM + {}".format(i), "name": "Sample",
                      "min": 0.0, "max": sample_max, "default": 7.0,
                      "note": "unused slot (only first 2 drum voices enabled)"}
    for i in range(16):
        k = str(16 + i)
        if k not in out:
            out[k] = {"kind": "knob", "enum": "TUNE_PARAM + {}".format(i),
                      "name": "Playback Speed", "min": 0.2, "max": 1.8,
                      "default": 1.0, "unit": "x",
                      "note": "unused slot (only first 2 drum voices enabled)"}
    return out


def fix_templated_names(params):
    """Repair printf-style placeholders left in names.

    Source names are often built at runtime: `string::f("Clk %i ratio", i + 1)`,
    `snprintf(strBuf, 32, "-%02i-: pan", i + 1)`. Static parsing only recovers the
    template string, so we group by the same enum base name and substitute the
    group index for %i / %02i.
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


# ================================================================ Build the dictionary

def plan_from_patches(patch_dir):
    """Decide which (plugin, model) pairs we need, from the patches on disk.

    Returns (sorted_needed, max_param_count_per_module). The max count tells us how
    many slots a module actually has, so we can drop phantom slots beyond it.
    """
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
    """Scrape sources for every module used in the patches and write modules.json."""
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
                print("  [manual] {:<34} {:>3} params".format(key, len(manual["params"])))
            continue

        if plugin not in REPOS:
            if not quiet:
                print("  [skip]   {:<34} no source URL".format(key))
            continue

        rels = SOURCES.get((plugin, model)) or guess_rels(plugin, model)
        # Auto-add the same-name header next to each .cpp (enums often live in .hpp).
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
                print("  [miss]   {:<34} source not found".format(key))
            continue

        # 1) Build a cross-file shared symbol table first (a parent class's enums in
        #    a .hpp must be visible to the child .cpp's configParam calls).
        shared = {}
        for _rel, t in files:
            body = strip_comments(t)
            shared.update(parse_defines(body))
            env, _ = parse_enums(body, shared)
            shared.update(env)

        # 2) Parse configParam per file, collecting param + enum symbols.
        params = {}
        syms = {}
        for _rel, t in files:
            p, s = parse_module(t, shared)
            for k, v in p.items():
                if k not in params or not params[k].get("name"):
                    params[k] = v
            for k, v in s.items():
                syms.setdefault(k, v)

        # 3) Enum entries with no configParam -> "reserved" (only ParamId* enums;
        #    skip _LEN / _LAST / NUM_ sentinels and anything beyond the module's real size).
        limit = sizes.get((plugin, model))
        for nm, (enum_name, idx) in syms.items():
            if re.search(r"_LEN$|_LAST$|^NUM_", nm):
                continue
            idx = int(idx)
            if limit is not None and idx >= limit:
                continue
            if idx not in params:
                params[idx] = {"kind": "reserved", "enum": nm, "name": None,
                               "note": "enum placeholder, no configParam (removed/unused)"}

        # 4) Drop empty slots beyond the module's actual param count.
        if limit is not None:
            params = {k: v for k, v in params.items()
                      if k < limit or (v.get("name") and v["kind"] != "reserved")}

        # 5) Post-process: backfill drum empty slots / fix printf placeholders in names.
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
            print("  [ok]     {:<34} {:>3} slots / {:>3} named  {}".format(
                key, len(params), named, "、".join(head)))

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(lib, f, ensure_ascii=False, indent=1, sort_keys=True)
    return lib


# ================================================================ Query interface

_CACHE = {"lib": None, "mtime": None}


def load():
    """Load modules.json, cached and invalidated by file mtime."""
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

# Chinese colloquial term -> English keywords that may appear in a param name.
# Param names are all English but the user speaks Chinese; without this table a
# request like "brighter filter" could not be translated.
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
    """Find a module's dictionary entry, trying plugin/model aliases and a
    model-only fallback."""
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
    """Return the human name of one param, or None."""
    e = lookup(plugin, model)
    if not e:
        return None
    p = e["params"].get(str(param_id))
    if not p:
        return None
    return p.get("name")


def describe(plugin, model, param_id):
    """Return the full param dict for one param id, or None."""
    e = lookup(plugin, model)
    return e["params"].get(str(param_id)) if e else None


def search(keyword, limit=40):
    """Fuzzy search the dictionary by param name or enum name."""
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
    """Map plain language to a param number. Returns [(score, number, name)].

    Param names are English (Cutoff frequency / Release / Wet level…) but the user
    speaks Chinese, so we first expand colloquial words into the English keywords
    they might map to, then match against param names.
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
    """Cross-check the dictionary against real patches: do every param id used in a
    patch exist in the dictionary? Returns a list of problems."""
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
                problems.append((fn, m["plugin"], m["model"], "module not in dictionary"))
                continue
            known = sorted(int(k) for k in e["params"])
            missing = [g for g in given if g not in known]
            if missing:
                problems.append((fn, m["plugin"], m["model"],
                                 "patch has but dict lacks: {}".format(missing)))
            if verbose:
                print("  {:<36} {:<20} patch {:>3} / dict {:>3}".format(
                    m["plugin"] + "/" + m["model"], fn[:18], len(given), len(known)))
    return problems


# ================================================================ CLI

def main(argv):
    if len(argv) < 2 or argv[1] == "build":
        only = set(argv[argv.index("--only") + 1].split(",")) if "--only" in argv else None
        lib = build(only=only)
        named = sum(1 for v in lib.values() for p in v["params"].values() if p.get("name"))
        print("\n{} modules / {} named params -> {}".format(len(lib), named, OUT_FILE))
        return 0

    if argv[1] == "show":
        e = lookup(argv[2], argv[3])
        if not e:
            print("not built:", argv[2], argv[3])
            return 1
        print("{}   source: {}".format(e["model"], e["source"]))
        for k, v in sorted(e["params"].items(), key=lambda x: int(x[0])):
            bits = []
            if v.get("min") is not None and v.get("max") is not None:
                bits.append("{}..{}".format(v["min"], v["max"]))
            if v.get("default") is not None:
                bits.append("def={}".format(v["default"]))
            if v.get("unit"):
                bits.append(v["unit"])
            print("  {:>3}  {:<24} {:<9} {}".format(
                k, v.get("name") or "(unused)", v["kind"], " ".join(bits)))
        return 0

    if argv[1] == "search":
        for h in search(argv[2]):
            print("  {:<34} {:>3}  {}".format(h["module"], h["param"], h["name"]))
        return 0

    if argv[1] == "verify":
        probs = verify()
        print()
        if probs:
            print("found {} mismatches:".format(len(probs)))
            for p in probs:
                print("  {} {} {} -> {}".format(*p))
            return 1
        print("all consistent")
        return 0

    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
