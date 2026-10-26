#!/usr/bin/env python3
"""Cardinal MCP server — let an AI agent drive Cardinal standalone directly.

This is the entry point of the `cardinal-mcp` project. It speaks MCP
(JSON-RPC 2.0) over stdio, and behind that talks to Cardinal via OSC.

Protocol level: handshake with version negotiation (server supports up to
2025-06-18 — tool annotations + structured tool output; older clients are
honored at their own version). capabilities advertises tools only.

What it exposes (12 semantic tools)
------------------------------------
  cardinal_ping               check OSC connectivity to Cardinal
  cardinal_list_patches       list .vcv patches in the patch directory
  cardinal_patch_info         inspect a patch's module list (you need moduleId
                              to set any parameter)
  cardinal_load_patch         load a .vcv into the running Cardinal
  cardinal_set_param          turn any module's knob (moduleId + paramId + value)
  cardinal_set_params_batch   set MANY knobs in one call (by param name)
  cardinal_set_host_param     set one of Cardinal's 24 host parameters
  cardinal_read_live          read the patch Cardinal is currently running
                              (via the live autosave file, NOT OSC)
  cardinal_save_live          persist the current GUI state to a .vcv file
  cardinal_module_params      look up "param name -> number" (or search by keyword)
  cardinal_find_param         translate plain language ("brighter filter") into a
                              param number
  cardinal_music              drum patterns / chord progressions / tone recipes
  cardinal_apply_recipe       write a tone recipe into a patch

Prerequisite
------------
Cardinal standalone must have OSC enabled manually:
   Engine -> Enable OSC remote control  (default UDP port 2228).
This toggle is NOT persisted across restarts — the user has to click it every
time they launch Cardinal. See `state.py` / `tools/winprobe.py` for how to
verify the port is listening.

Run modes
---------
  python cardinal_mcp.py --selftest   self-check (OSC reachable? tools listed?)
  python cardinal_mcp.py --call <tool> ['{...}']   call one tool without MCP
  python cardinal_mcp.py --tools       print the tool table
  python cardinal_mcp.py               normal: serve MCP over stdio
"""

import io
import json
import math
import os
import re
import shutil
import socket
import struct
import sys
import time

# --- Path setup: make sibling modules importable regardless of CWD ---------
# HERE   = .../tools      (this file's directory)
# REPO_ROOT = parent of tools/  (used to locate the bundled patches/ dir)
HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)

sys.path.insert(0, HERE)
import patchio  # noqa: E402  (local helper, imported after sys.path fix)
import modbrowser  # noqa: E402  (module library, reads Cardinal's PluginManifests)
import modresolve  # noqa: E402  (plain-language module name -> candidates/unique hit)
import topology  # noqa: E402  (rack wiring / role recognition)
import seq  # noqa: E402  (sequencer notes = piano-roll equivalent)
import editor_contracts as contracts
import songroll  # noqa: E402  (SongRoll sections = song arrangement table)
import abc_export  # noqa: E402  (sequencer notes -> .abc text score)
import samplelib  # noqa: E402  (sampler slots = right-click 'Load sample' equivalent)
import interaction_map  # noqa: E402  (human UI operation -> source code index)
import paramlib as pl  # noqa: E402  (param name -> number dictionary)

from pythonosc.osc_message_builder import OscMessageBuilder
from pythonosc.osc_message import OscMessage


# ================================================================ Config
# All three are overridable via environment variables so the same code works
# on any machine. The MCP client config (see mcp.example.json) sets these in
# the "env" block; sensible defaults below mean it also runs with no config.

def _default_patch_dir():
    """Resolve where patches live, in priority order:

    1. CARDINAL_PATCH_DIR env var (recommended — point at YOUR patches/ dir)
    2. the repo's own patches/  (so a fresh clone runs the examples unchanged)
    3. ~/Cardinal/patches       (last-resort fallback)
    """
    env = os.environ.get("CARDINAL_PATCH_DIR")
    if env:
        return os.path.abspath(env)
    local = os.path.join(REPO_ROOT, "patches")
    if os.path.isdir(local):
        return local
    return os.path.join(os.path.expanduser("~"), "Cardinal", "patches")


CARDINAL_IP = os.environ.get("CARDINAL_IP", "127.0.0.1")      # host running Cardinal
CARDINAL_PORT = int(os.environ.get("CARDINAL_PORT", "2228"))  # OSC UDP port
TIMEOUT = float(os.environ.get("CARDINAL_TIMEOUT", "1.5"))    # wait seconds per msg
PATCH_DIR = _default_patch_dir()


# ================================================================ OSC layer
# Cardinal speaks OSC over UDP. We keep one shared socket for both send and
# receive. Note: OSC has no reply-correlation id, so we just clear the socket
# before each request and read the next datagram that comes back.

def build_msg(address, args):
    """Build a raw OSC datagram (bytes).

    `args` is a list of (type_char, value) tuples. Supported types:
      'i' int32, 'h' int64, 'f' float32, 'b' blob, 's' string.
    We use 'h' (int64) for moduleId because Cardinal indexes modules as int64
    and a plain 'i' would overflow/truncate on large module ids.
    """
    b = OscMessageBuilder(address=address)
    for typ, val in args:
        b.add_arg(val, typ)
    return b.build().dgram


class CardinalLink:
    """A thin wrapper around a UDP socket to Cardinal's OSC receiver."""

    def __init__(self):
        # Bind to an ephemeral local port ("" , 0); we only send to Cardinal
        # and receive its replies on this same socket.
        self.target = (socket.gethostbyname(CARDINAL_IP), CARDINAL_PORT)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("", 0))
        self.sock.settimeout(TIMEOUT)

    def send(self, address, args=()):
        # On Windows, sending to a port with nobody listening raises
        # ConnectionResetError (ICMP unreachable) instead of failing silently.
        try:
            self.sock.sendto(build_msg(address, args), self.target)
            return True
        except OSError as e:
            raise RuntimeError(
                f"OSC send failed ({e}). Confirm Cardinal standalone has "
                f"Engine -> Enable OSC remote control on, port {CARDINAL_PORT}.") from e

    def ask(self, address, args=(), expect="/resp", timeout=None, reply_tag=None):
        """Wait for a reply from the configured peer and, optionally, a tag.

        Drain without blocking and ignore diagnostics/foreign packets until
        the monotonic deadline. The legacy protocol still has no request ID:
        a delayed same-tag reply cannot be fully disambiguated here.
        """
        budget = TIMEOUT if timeout is None else timeout
        if not math.isfinite(budget) or budget <= 0:
            raise ValueError("OSC timeout must be finite and positive")
        self.sock.settimeout(0.0)
        try:
            for _ in range(256):
                self.sock.recv(65535)
        except (BlockingIOError, socket.timeout, OSError):
            pass

        self.sock.settimeout(budget)
        deadline = time.monotonic() + budget
        self.send(address, args)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            self.sock.settimeout(remaining)
            try:
                data, peer = self.sock.recvfrom(65535)
            except (socket.timeout, OSError):
                return None
            if peer != self.target:
                continue
            try:
                msg = OscMessage(data)
            except Exception:
                continue
            if (msg.address == expect and
                    (reply_tag is None or (msg.params and str(msg.params[0]) == reply_tag))):
                return msg.params


# Module-level singleton: one socket for the process lifetime.
LINK = None


def link():
    """Lazily create (and reuse) the shared CardinalLink socket."""
    global LINK
    if LINK is None:
        LINK = CardinalLink()
    return LINK


# ================================================================ Patch I/O

def list_patches():
    """List every .vcv in PATCH_DIR with size + mtime."""
    if not os.path.isdir(PATCH_DIR):
        return {"error": f"patch dir does not exist: {PATCH_DIR}"}
    out = []
    for fn in sorted(os.listdir(PATCH_DIR)):
        if fn.lower().endswith(".vcv"):
            p = os.path.join(PATCH_DIR, fn)
            out.append({"name": fn, "path": p, "bytes": os.path.getsize(p),
                        "mtime": time.strftime("%Y-%m-%d %H:%M:%S",
                                               time.localtime(os.path.getmtime(p)))})
    return {"patches": out, "dir": PATCH_DIR}


def resolve(name):
    """Turn a user-supplied patch name into an absolute path.

    Accepts an absolute path directly, or a bare file name / name without the
    .vcv extension inside PATCH_DIR.
    """
    if os.path.isabs(name) and os.path.exists(name):
        return name
    p = os.path.join(PATCH_DIR, name)
    if not p.lower().endswith(".vcv"):
        p += ".vcv"
    return p


def patch_info(name):
    """Inspect one patch: every module (id / plugin / model) and its params.

    This is the tool to call BEFORE setting a parameter — you need the module's
    numeric id. We return a compact shape (ids + values) to keep tokens small.
    """
    p = resolve(name)
    if not os.path.exists(p):
        return {"error": f"patch not found: {p}"}
    d = patchio.read_patch(p)
    mods = [{"id": m["id"], "plugin": m["plugin"], "model": m["model"],
             "params": [{"id": q.get("id"), "value": q.get("value")}
                        for q in (m.get("params") or [])]}
            for m in d.get("modules", [])]
    return {"patch": os.path.basename(p), "format": patchio.describe(p)["format"],
            "modules": mods, "cables": len(d.get("cables", []))}


def load_patch(name):
    """Push a .vcv into the running Cardinal via OSC `/load`.

    Cardinal's `/load` internally calls rack::system::unarchiveToDirectory +
    loadAutosave, and Rack's archive format is exactly pax tar + zstd (one
    `patch.json` inside). So we run `patchio.archive_bytes()` first — this is the
    reason plain JSON patches still need to be wrapped before they can be loaded.
    """
    p = resolve(name)
    if not os.path.exists(p):
        return {"error": f"patch not found: {p}"}
    with open(p, "rb") as f:
        raw = f.read()
    blob = patchio.archive_bytes(raw)
    extra = {"blob_bytes": len(blob)}
    res = link().ask("/load", [("b", blob)], timeout=6.0, reply_tag="load")
    if res is None:
        # Reached Cardinal? The most common cause: OSC not enabled, or wrong port.
        return {"ok": False, "sent": os.path.basename(p), **extra,
                "note": "sent but no reply (Cardinal OSC off? wrong port?)"}
    reply = [str(x) for x in res]
    # D2: Cardinal answers ["load", "ok"|"warn <text>"|"fail <text>"].
    # "warn" = loaded but with diagnostics (fromJson/unarchive warnings),
    # now surfaced here instead of only popping a GUI dialog (or vanishing).
    if len(reply) not in (2, 3) or reply[0] != "load":
        return {"ok": False, "error": "invalid_load_reply", "reply": reply, **extra}
    payload = reply[1]
    status = reply[2] if len(reply) == 3 else "ok"
    if payload == "ok":
        ok, warnings = True, []
    elif payload.startswith("warn "):
        ok, warnings = True, [payload[5:].strip()]
    else:
        ok, warnings = False, [payload[5:] if payload.startswith("fail ") else payload]
    return {"ok": ok and status == "ok", "warnings": warnings, "status": status,
            "sent": os.path.basename(p), "reply": reply, **extra}


def _parameter_input_error(module_id, param_id, value):
    """Reject unsafe OSC integer/float values before even a preflight read."""
    if type(module_id) is not int or not 0 <= module_id < 2 ** 63:
        return {"ok": False, "sent": False, "error": "module_id must be a nonnegative int64"}
    if type(param_id) is not int or not 0 <= param_id < 2 ** 31:
        return {"ok": False, "sent": False, "error": "param_id must be a nonnegative int32"}
    try:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("value must be numeric")
        if not math.isfinite(struct.unpack("f", struct.pack("f", value))[0]):
            raise ValueError("value must be finite")
    except (ValueError, OverflowError, struct.error):
        return {"ok": False, "sent": False, "error": "value must fit a finite OSC float32"}
    return None


def set_param(module_id, param_id, value):
    """Turn one knob on one module via OSC `/param`.

    Args:
      module_id  int64 module index (from patch_info)
      param_id   int   parameter slot, 0-based
      value      finite raw storage value; units/ranges are module-specific.
                A live read probe must validate the slot before raw sending.
    """
    invalid = _parameter_input_error(module_id, param_id, value)
    if invalid:
        return invalid
    validation = get_param(module_id, param_id)
    if validation.get("ok") is not True or validation.get("status") != "ok":
        return {"ok": False, "sent": False, "error": "parameter_validation_failed",
                "validation": validation}
    link().send("/param", [("h", int(module_id)), ("i", int(param_id)),
                           ("f", float(value))])
    return {"ok": True, "sent": True, "verified": False,
            "moduleId": int(module_id), "paramId": int(param_id), "value": float(value),
            "note": "Raw /param has no acknowledgement; read back to verify. C++ still needs bounds checks."}


# ★ 2026-10-19 批次 A1：按名字设参数。
def _find_module_instances(d, module):
    """在 patch dict 里找某型号的全部模块实例（大小写不敏感；支持 plugin/model）。

    返回 (instances, all_modules)。instances 每项是 patch 里的原 module dict。
    机架里常有 2 个同型号（2 个 VCA-1 是常态），所以返回列表而不是单个，
    由调用方用 instance 序号挑 —— 永远把「有几个、挑了哪个」报出来。
    """
    qualified = module.replace('|', '/')
    if '/' in qualified:
        plug_want, model_want = qualified.casefold().split('/', 1)
        hits = [m for m in d.get('modules', [])
                if m['plugin'].casefold() == plug_want and m['model'].casefold() == model_want]
    else:
        want = module.casefold()
        hits = [m for m in d.get('modules', [])
                if want in (m['plugin'] + '/' + m['model']).casefold()]
    return hits, d.get("modules", [])


def _resolve_param_id(entry, param):
    """把「参数名或数字」翻成 param_id。返回 (param_id, info, note) 或 (None, None, err)。

    - 数字       -> 直接当 id 用（调用方会再做 reserved 检查）
    - 名字       -> 先精确匹配再子串匹配；多个同名槽返回第一个并在 note 里说明
    - 匹配只认有名字的槽 —— reserved 槽 name=None，天然不会被名字命中
    """
    params = entry["params"]
    if type(param) not in (str, int) or (type(param) is int and param < 0):
        return None, None, "param must be a name or nonnegative integer (not bool)"
    if re.fullmatch(r"\d+", str(param).strip()):
        pid = int(param)
        info = params.get(str(pid))
        if info is None:
            return None, None, f"param {pid} 不在本字典里（共 {len(params)} 槽）"
        return pid, info, None
    want = str(param).strip().lower()
    exact = [int(pid) for pid, v in params.items()
             if (v.get("name") or "").lower() == want]
    if exact:
        note = None
        if len(exact) > 1:
            note = f"有 {len(exact)} 个同名参数槽，取最小的 id {min(exact)}；" \
                   f"要选别的请用数字 param。全部同名 id: {sorted(exact)}"
        return min(exact), params.get(str(min(exact))), note
    # 🔴 2026-10-21 修：子串匹配分支原先写 `min(exact or partial)`，
    # 但 partial 从未定义 ⇒ 任何「非精确名」的按名字设参都会抛 NameError
    # （例：param="level" 匹配 "Channel 1 level"）。此路径此前从未被测到。
    partial = [int(pid) for pid, v in params.items()
               if want in (v.get("name") or "").lower()]
    if not partial:
        return None, None, f"找不到参数「{param}」"
    pid = min(partial)
    info = params.get(str(pid))
    note = "没有精确同名参数，按子串匹配命中"
    return pid, info, note


def set_param_by_name(patch, module, param, value, instance=0, load_after=False):
    """按「型号名 + 参数名」设参数，写 .vcv 文件（可选 /load 热加载）。

    与 cardinal_set_param（按编号、走 OSC 实时）互补。关键防线：
    🔴 **拒绝废弃槽**（kind=="reserved"，如 VCF 1 号、Clocked 14 号）——
    这些槽是 enum 占位（2.0 版移除但保留编号），`/param` 设进去不报错
    但永远没效果；写进文件比报错更隐蔽，所以在这里直接拦下。
    机架里有多个同型号模块时，用 instance（0 起）挑第几个，返回里
    永远带「共几个 / 挑了哪个 / 它的位置」。
    """
    import paramlib as pl
    error = contracts.input_error(bools=dict(load_after=load_after))
    if error:
        return error
    p = resolve(patch)
    if not os.path.exists(p):
        return {"error": f"patch not found: {p}"}
    error = contracts.input_error(ints=dict(instance=instance), numbers=dict(value=value))
    if error:
        return error
    d = patchio.read_patch(p)

    hits, all_mods = _find_module_instances(d, module)
    if not hits:
        return {"error": f"机架里没有「{module}」",
                "available": sorted({m["model"] for m in all_mods})}
    if not 0 <= instance < len(hits):
        return {"error": f"机架里有 {len(hits)} 个 {module}，instance={instance} 越界",
                "instances": [{"instance": i, "module_id": m["id"],
                               "pos": (m.get("pos") or [None, None])[0]}
                              for i, m in enumerate(hits)]}
    mod = hits[instance]

    entry = pl.lookup(mod["plugin"], mod["model"])
    if not entry:
        return {"error": f"{mod['plugin']}/{mod['model']} 不在参数字典里"}
    pid, info, note = _resolve_param_id(entry, param)
    if pid is None:
        return {"error": note}

    # 🔴 核心守门：reserved 槽拒绝写。设进去不报错但没效果，是静默失败。
    if (info or {}).get("kind") == "reserved":
        return {"error": f"param {pid} 是废弃占位槽（{info.get('enum')}），"
                         f"写了也没有任何效果，已拒绝",
                "module": f"{mod['plugin']}/{mod['model']}",
                "hint": "用 cardinal_module_params 看有效参数表"}

    lo, hi = (info or {}).get("min"), (info or {}).get("max")
    warnings = []
    if lo is not None and hi is not None and not (lo <= float(value) <= hi):
        warnings.append(f"值 {value} 超出该参数范围 {lo}..{hi}，照写不裁剪")
    if note:
        warnings.append(note)

    params = mod.setdefault("params", [])
    for q in params:
        if q.get("id") == pid:
            q["value"] = float(value)
            break
    else:
        params.append({"id": pid, "value": float(value)})

    out = {"ok": True, "patch": os.path.basename(p),
           "module": f"{mod['plugin']}/{mod['model']}",
           "module_id": mod["id"], "param_id": pid,
           "param_name": (info or {}).get("name"), "kind": (info or {}).get("kind"),
           "value": float(value)}
    if len(hits) > 1:
        out["note_instances"] = f"机架里有 {len(hits)} 个 {mod['model']}，本次改的是 instance={instance}"
    if warnings:
        out["warnings"] = warnings
    out = contracts.save_edit(out, p, d, ".bak-param", load_after, load_patch)
    return out


# ★ 2026-10-21 批次 A12：批量设参。
# 为什么需要：set_param_by_name 一次只能改一个旋钮。改一台 MiniArranger
# 的 8 轨音色链（每轨 3-4 个旋钮）= 30+ 次调用，每次都要重新读文件、
# 重新写文件、重新备份 —— 慢，且中途失败会留下半改状态。
# 批量版：一次读盘、一次备份、一次写盘，逐条独立回执。
#
# 🔴 沿用 set_param_by_name 的全部防线，一条都不许放松：
#   1. reserved 废弃槽拒绝写（写进去不报错但没效果 = 静默失败）
#   2. 同型号多实例必须显式 instance，且回执里永远报「共几个/挑了哪个」
#   3. 越界值照写不裁剪，但必须警告
#   4. 某一条失败**不影响其它条**（逐条独立），但整体 ok 字段如实反映
#   5. 全部条目都失败 ⇒ 不写盘（避免把好文件改成空）
def set_params_by_name_batch(patch, sets, load_after=False):
    """一次改多个旋钮（按名字），逐条独立回执。

    Args:
      patch  patch 文件名
      sets   list of {module, param, value, instance?}
             module  = 型号名，如 "VCO" 或 "plugin/model"
             param   = 参数名（如 "Cutoff frequency"）或数字 param_id
             value   = 目标值
             instance= 同型号的第几个（0 起），默认 0
      load_after  改完是否 /load 热加载

    失败策略：**部分成功也是成功**。每条独立 try/except，一条挂了就
    记 failed，其余照改。全部失败时**不写盘**（防止把好文件写坏）。
    """
    import paramlib as pl
    error = contracts.input_error(bools=dict(load_after=load_after))
    if error:
        return error
    p = resolve(patch)
    if not os.path.exists(p):
        return {"error": f"patch not found: {p}"}
    if not isinstance(sets, list) or not sets:
        return {"error": "sets must be a non-empty list",
                "expected": '[{"module": "VCO", "param": "Frequency", "value": 0.5}]'}

    d = patchio.read_patch(p)
    results = []
    applied = 0

    for idx, item in enumerate(sets):
        rec = {"index": idx}
        try:
            if not isinstance(item, dict):
                raise ValueError("条目必须是对象")
            module = item.get("module")
            param = item.get("param")
            value = item.get("value")
            instance = contracts.integer(item.get("instance", 0), "instance")
            if module is None or param is None or value is None:
                raise ValueError("缺 module / param / value")
            value = contracts.number(value, "value")

            hits, all_mods = _find_module_instances(d, module)
            if not hits:
                raise ValueError(f"机架里没有「{module}」")
            if not 0 <= instance < len(hits):
                raise ValueError(
                    f"机架里有 {len(hits)} 个 {hits[0]['model']}，instance={instance} 越界")
            mod = hits[instance]

            entry = pl.lookup(mod["plugin"], mod["model"])
            if not entry:
                raise ValueError(f"{mod['plugin']}/{mod['model']} 不在参数字典里")
            pid, info, note = _resolve_param_id(entry, param)
            if pid is None:
                raise ValueError(note)

            # 🔴 核心守门：reserved 槽拒绝写（与单条版同一把锁）
            if (info or {}).get("kind") == "reserved":
                raise ValueError(
                    f"param {pid} 是废弃占位槽（{info.get('enum')}），"
                    f"写了也没有任何效果，已拒绝")

            lo, hi = (info or {}).get("min"), (info or {}).get("max")
            warnings = []
            if lo is not None and hi is not None and not (lo <= value <= hi):
                warnings.append(f"值 {value} 超出该参数范围 {lo}..{hi}，照写不裁剪")
            if note:
                warnings.append(note)

            params = mod.setdefault("params", [])
            for q in params:
                if q.get("id") == pid:
                    q["value"] = value
                    break
            else:
                params.append({"id": pid, "value": value})

            rec.update({"ok": True,
                        "module": f"{mod['plugin']}/{mod['model']}",
                        "module_id": mod["id"], "param_id": pid,
                        "param_name": (info or {}).get("name"),
                        "kind": (info or {}).get("kind"),
                        "value": value})
            if len(hits) > 1:
                rec["note_instances"] = (
                    f"机架里有 {len(hits)} 个 {mod['model']}，本次改的是 instance={instance}")
            if warnings:
                rec["warnings"] = warnings
            applied += 1
        except Exception as e:  # noqa: BLE001 — 一条失败不影响其余
            rec.update({"ok": False, "error": str(e),
                        "requested": item if isinstance(item, dict) else str(item)})
        results.append(rec)

    # 全部失败 ⇒ 不写盘（别把好文件写坏）
    if applied == 0:
        return {"ok": False, "patch": os.path.basename(p),
                "written": False, "applied": 0, "requested": len(sets),
                "results": results,
                "note": "没有一条成功 ⇒ 未写盘（原文件未改动）"}

    out = {"ok": True, "patch": os.path.basename(p),
           "written": True, "applied": applied, "requested": len(sets),
           "failed": len(sets) - applied, "results": results}
    if applied != len(sets):
        out["note"] = f"{applied} 条成功、{len(sets) - applied} 条失败 —— 成功的已写入，失败的见对应条目"
    out = contracts.save_edit(out, p, d, ".bak-param", load_after, load_patch)
    if out.get("written"):
        out["written"] = True
    return out


# ================================================================ Audit (A2)
# ★ 2026-10-19 批次 A2：聚合 5 个审计脚本成一个工具。
#   会崩：ports（接口越界）→ chain（音高/门接错+死胡同）
#   会哑：values（量纲护栏）→ flow（信号流可达性）
#   validate（结构）兜底。少跑一个就可能放过「加载即崩」或「永哑」机架。

def _audit_validate(p):
    """结构校验（validate.py 的无打印版）：JSON 可读、模块 id 不重复、
    线缆两端存在、模块在 PluginManifests 里（Starsea 自建包同规则放行）。"""
    known_extra = {("Starsea", "Starsea-MiniArranger"),
                   ("Starsea", "Starsea-MiniArrangerExpander")}
    problems = []
    try:
        d = patchio.read_patch(p)
    except Exception as e:  # noqa: BLE001
        return [f"读取失败: {e}"]
    mods = d.get("modules", [])
    ids = [m["id"] for m in mods]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        problems.append(f"重复模块 id: {sorted(dup)}")

    known = None
    try:
        lib = modbrowser.LIB.load()
        if not lib.error:
            known = {(m["plugin"], m["model"]) for m in lib.modules}
    except Exception:  # noqa: BLE001
        known = None
    if known is not None:
        for m in mods:
            key = (m["plugin"], m["model"])
            if key not in known and key not in known_extra:
                problems.append(f"未知模块: {m['plugin']}/{m['model']}")
    for c in d.get("cables", []):
        for key in ("outputModuleId", "inputModuleId"):
            if c.get(key) not in {m["id"] for m in mods}:
                problems.append(f"线缆 {c.get('id')} 端点模块 {c.get(key)} 不存在")
    cids = [c.get("id") for c in d.get("cables", [])]
    if len(set(cids)) != len(cids):
        problems.append("线缆 id 重复")
    return problems


def cardinal_audit(name, checks=None):
    """Run the pre-load audits on one patch (aggregates the 5 offline scripts).

    checks: subset of [ports, values, flow, chain, validate]; default = all five.
    verdict: FAIL = hard failures — do NOT load into Cardinal (端口越界类加载即崩);
             WARN = only soft warnings; PASS = clean.
    ⚠️ Static audits can never prove a rack actually sounds — pair with
    cardinal_scan_signal on the running rack for that.
    """
    p = resolve(name)
    if not os.path.exists(p):
        return {"error": f"patch not found: {p}"}
    import audit_ports   # noqa: E402
    import audit_values  # noqa: E402
    import audit_flow    # noqa: E402
    import audit_chain   # noqa: E402
    import contextlib as _cctxlib
    import io as _cio

    checks = checks or ["ports", "values", "flow", "chain", "validate"]
    out = {"patch": os.path.basename(p), "checks": {}}

    if "ports" in checks:
        try:
            bad = audit_ports.audit(p, verbose=False)
            out["checks"]["ports"] = {"ok": not bad, "hard": len(bad),
                                      "violations": sorted(set(bad))}
        except Exception as e:  # noqa: BLE001
            out["checks"]["ports"] = {"ok": False, "error": f"audit_ports crashed: {e}"}

    if "values" in checks:
        try:
            # audit_values 返回 (硬否决数, 告警数) —— 两个 int，不是列表
            with _cctxlib.redirect_stdout(_cio.StringIO()):
                hard, soft = audit_values.audit(p, verbose=False)
            hard, soft = int(hard or 0), int(soft or 0)
            out["checks"]["values"] = {"ok": hard == 0, "hard": hard,
                                       "warnings": soft}
        except Exception as e:  # noqa: BLE001
            out["checks"]["values"] = {"ok": False, "error": f"audit_values crashed: {e}"}

    if "flow" in checks:
        try:
            with _cctxlib.redirect_stdout(_cio.StringIO()):
                n_flow = audit_flow.audit(p)
            out["checks"]["flow"] = {"ok": n_flow == 0, "hard": n_flow}
        except Exception as e:  # noqa: BLE001
            out["checks"]["flow"] = {"ok": False, "error": f"audit_flow crashed: {e}"}

    if "chain" in checks:
        try:
            with _cctxlib.redirect_stdout(_cio.StringIO()):
                n_chain = audit_chain.audit(p, os.path.basename(p))
            out["checks"]["chain"] = {"ok": n_chain == 0, "hard": n_chain}
        except Exception as e:  # noqa: BLE001
            out["checks"]["chain"] = {"ok": False, "error": f"audit_chain crashed: {e}"}

    if "validate" in checks:
        try:
            problems = _audit_validate(p)
            out["checks"]["validate"] = {"ok": not problems, "problems": problems}
        except Exception as e:  # noqa: BLE001
            out["checks"]["validate"] = {"ok": False, "error": f"audit_validate crashed: {e}"}

    # FAIL = 任一检查 ok=False；WARN = 全 ok 但有软告警
    fail = any(not v.get("ok", True) for v in out["checks"].values())
    soft_total = (out["checks"].get("values", {}).get("warnings", 0)
                  + len(out["checks"].get("validate", {}).get("problems") or []))
    out["verdict"] = "FAIL" if fail else ("WARN" if soft_total else "PASS")
    return out


def set_host_param(port, value):
    """Set one of Cardinal's 24 host parameters via OSC `/host-param` (port 0-23).

    Host parameters drive things like audio device, sample rate, and the knobs
    exposed by the Host Parameters / Host Parameters Map modules.
    """
    invalid = _tool_input_error("cardinal_set_host_param", {"port": port, "value": value})
    if invalid:
        return invalid
    link().send("/host-param", [("i", int(port)), ("f", float(value))])
    return {"ok": True, "port": int(port), "value": float(value)}


# ================================================================ Deploy + diff (A3)
# ★ 2026-10-19 批次 A3：生成→加载→读回比对闭环。
#   E8 死锁（李拍板降级）：/param 改动永不落盘、/param-get 探针未编译
#   ⇒ 本闭环只验结构（模块集合 + 接线表），参数验证等批次 B 编译后补全。

# ================================================================ Port semantics (A4)
# 语义分类只认词根，不硬造。audit_chain.py 手工核实的口（Rings PITCH=6、
# ADSR 门=4、鼓 IN16=触发…）是权威 —— 它们直接来自源码 enum，优先级最高。

# 手工核实的语义（audit_chain.py 的表，来自源码逐个核对）
_PORT_AUTHORITY = {
    ("AudibleInstruments/Rings", "in", 6): "pitch",   # Rings PITCH_INPUT（0-5 是各种 MOD）
    ("Fundamental/VCO", "in", 0): "pitch",
    ("Fundamental/ADSR", "in", 4): "gate",
    ("WSTD-Drums/BassDrum9", "in", 16): "gate",
    ("WSTD-Drums/SnareDrumN", "in", 16): "gate",
    ("WSTD-Drums/ClosedHiHat", "in", 16): "gate",
    ("WSTD-Drums/OpenHiHat", "in", 16): "gate",
    ("WSTD-Drums/SnareDrumN", "in", 16): "gate",
    ("WSTD-Drums/Tomi", "in", 16): "gate",
    ("WSTD-Drums/CR78", "in", 16): "gate",
    ("WSTD-Drums/DMX", "in", 16): "gate",
    ("ImpromptuModular/Clocked", "out", 0): "clock",
    ("ImpromptuModular/Clocked", "out", 5): "run",
}


def _classify_port(direction, enum, name):
    """端口语义分类：只认词根，不猜。认不出就标 cv/other，绝不硬标 audio。"""
    text = ((enum or "") + " " + (name or "")).upper()
    if "GATE" in text or "TRIG" in text:
        return "gate/trig"
    if "PITCH" in text or "V/OCT" in text or "VOCT" in text:
        return "pitch"
    if "CLOCK" in text or "CLK" in text:
        return "clock"
    if "SIGNAL" in text or "ENVELOPE" in text or "AUDIO" in text:
        return "audio/env"
    if direction == "out" and re.search(r"(LPF|HPF|FILTER|MAIN|LEFT|RIGHT)", text):
        return "audio"          # VCF 的 LPF/HPF 输出口是音频
    if re.search(r"\b(SIN|SAW|TRI|SQR|SINE|SAWTOOTH|SQUARE|TRIANGLE)\b", text):
        return "audio"          # VCO 的波形是输出口
    return "cv/other"


def _lookup_module_entry(module):
    """Dictionary queries share fail-closed identity resolution, never first-match."""
    if not isinstance(module, str):
        return None
    qualified = module.replace('|', '/')
    plugin, model = qualified.split('/', 1) if '/' in qualified else (None, module)
    return pl.lookup(plugin, model)


def cardinal_port_semantics(module=None, patch=None, module_id=None):
    """查一个模块的端口语义表：每个口是 pitch/gate/clock/audio/cv。

    数据源（两层）：
      1. paramlib 从源码解析的 configInput/configOutput label + enum 名
         （Bogaudio 与 Fundamental 同名模块端口完全不同 —— 本表按真实插件区分）
      2. 手工核实的权威覆盖（audit_chain 的 PITCH/GATE 表）
    用在接线前：把线接到哪个口，靠这张表不靠猜。
    """
    entry = None
    if patch and (module or patch):
        if not os.path.exists(resolve(patch)):
            return {"error": f"patch not found: {resolve(patch)}"}
        d = patchio.read_patch(resolve(patch))
        mod, err = contracts.select_target(d.get('modules', []), d.get('modules', []),
                                           module, module_id)
        if err:
            return err
        plugin, model = mod["plugin"], mod["model"]
        entry = pl.lookup(plugin, model)
    elif module:
        entry = _lookup_module_entry(module)
    if not entry:
        return {"error": f"{module} not in param dictionary",
                "known": sorted(pl.load().keys())}
    plugin, model = entry["plugin"], entry["model"]
    ports = entry.get("ports") or {}

    def rows(direction):
        field = "inputs" if direction == "in" else "outputs"
        out = []
        for x in ports.get(field, []):
            auth = _PORT_AUTHORITY.get((f"{plugin}/{model}", direction, x["id"]))
            sem = auth or _classify_port(direction, x.get("enum"), x.get("name"))
            out.append({"id": x["id"], "name": x.get("name"),
                        "enum": x.get("enum"), "semantic": sem})
        return out

    ins, outs = rows("in"), rows("out")
    if not ins and not outs:
        note = ("本模块端口表为空（源码不在字典覆盖内，如 WSTD-Drums 的父类动态注册）"
                "—— 用 audit_ports LIMITS / PORTS.md 手工表兜底")
    else:
        note = None
    return {"module": f"{plugin}/{model}", "inputs": ins, "outputs": outs,
            **({"note": note} if note else {})}


def _params_map(module):
    """把一个 module 的 params 列表压成 {param_id: value}。

    .vcv 与引擎 autosave 的 params 都是 [{"id":N,"value":V}, ...] 形态，
    且 value 同量纲（都是 ParamQuantity::getValue() 的存储值，非显示值），
    所以可以直接逐项比。
    """
    out = {}
    params = module.get("params", [])
    if not isinstance(params, list):
        raise ValueError("params must be a list")
    for index, q in enumerate(params):
        if not isinstance(q, dict):
            raise ValueError("params[%d] must be an object" % index)
        pid = q.get("id")
        if not isinstance(pid, int) or isinstance(pid, bool) or pid < 0:
            raise ValueError("params[%d] requires a nonnegative integer id" % index)
        if pid in out:
            raise ValueError("duplicate param id: %d" % pid)
        if "value" not in q:
            raise ValueError("param %d is missing value" % pid)
        value = q["value"]
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError("param %d value must be numeric" % pid)
        try:
            value = float(value)
        except (ValueError, OverflowError) as exc:
            raise ValueError("param %d value must be finite" % pid) from exc
        if not math.isfinite(value):
            raise ValueError("param %d value must be finite" % pid)
        out[pid] = value
    return out


def _diff_params(d_file, d_live, tol=1e-4):
    """逐模块比对参数值。返回 (mismatch 列表, 统计 dict)。

    🔴 误报防护（这条项目上栽过多次，务必守住）：
    1. **文件里有、引擎里没有的槽，不算错** —— 引擎 `paramsToJson()`
       明确跳过「无界参数」（`!isBounded()`），那类槽本就不该被序列化。
       引擎侧没有 ⇒ 归为 `unserialized`（不判错、不算 mismatch）。
    2. **值比较必须带容差** —— 引擎 `setImmediateValue` 会按 min/max
       归一化并量化，文件里写的 0.4 回读可能是 0.4000000059604645。
       没有容差会把「引擎正常量化」误报成「参数没生效」。
    3. **模块整体缺失**归结构层（missing_modules），这里不重复报。
    """
    live_by_id = {m["id"]: m for m in d_live.get("modules", [])}
    mismatches = []
    compared = 0
    unserialized = 0
    for mf in d_file.get("modules", []):
        ml = live_by_id.get(mf["id"])
        if ml is None:
            continue                      # 模块没加载 ⇒ 结构层已报
        pf = _params_map(mf)
        pl = _params_map(ml)
        for pid, vfile in pf.items():
            if pid not in pl:
                unserialized += 1           # 无界参数被引擎跳过，不算错
                continue
            compared += 1
            vlive = pl[pid]
            if not math.isfinite(vfile) or not math.isfinite(vlive):
                mismatches.append({"module_id": mf["id"], "param_id": pid,
                                   "file_value": str(vfile), "live_value": str(vlive),
                                   "reason": "nonfinite_value", "delta": None})
                continue
            if abs(vfile - vlive) > tol:
                mismatches.append({
                    "module_id": mf["id"],
                    "module": "%s/%s" % (mf.get("plugin"), mf.get("model")),
                    "param_id": pid,
                    "file_value": vfile,
                    "live_value": vlive,
                    "delta": round(vlive - vfile, 6),
                })
    stats = {"params_compared": compared,
             "params_unserialized": unserialized,
             "params_mismatched": len(mismatches),
             "tolerance": tol}
    return mismatches, stats


def cardinal_diff(name, check_params=True):
    """比对磁盘上的 .vcv 与运行中 Cardinal（模块 + 接线 + 参数值）。

    两个结论**分开报告**，因为可信度不同：
    - `match`            结构层：模块集合 + 接线表一致
    - `params_match`     参数层：旋钮值一致（E8 已解锁，2026-10-21）

    ⚠️ stale=true 说明 autosave 是上一会话的残留，结果不可当真 ——
    绝不用空数据掩盖。
    """
    p = resolve(name)
    if not os.path.exists(p):
        return {"error": "patch not found: %s" % p}
    live_path, _base = live_patch_path()
    if not live_path:
        return {"error": "no Cardinal live autosave found; Cardinal may not be running.",
                "searched_in": _base}
    d_file = patchio.read_patch(p)
    d_live = patchio.read_patch(live_path)

    mods_f = {(m["id"], m["plugin"], m["model"]) for m in d_file.get("modules", [])}
    mods_l = {(m["id"], m["plugin"], m["model"]) for m in d_live.get("modules", [])}
    cab_f = {(c.get("outputModuleId"), c.get("outputId"),
              c.get("inputModuleId"), c.get("inputId"))
             for c in d_file.get("cables", [])}
    cab_l = {(c.get("outputModuleId"), c.get("outputId"),
              c.get("inputModuleId"), c.get("inputId"))
             for c in d_live.get("cables", [])}
    miss_m = mods_f - mods_l      # 文件里有、引擎没加载 —— 静默丢弃类 bug
    miss_c = cab_f - cab_l
    extra_m = mods_l - mods_f
    extra_c = cab_l - cab_f
    started = cardinal_proc_start()
    stale = (os.path.getmtime(live_path) + 1.0 < started) if started is not None else None

    # --- 参数层（E8 解锁：/param-get 探针已编译，可读实时值） -------------
    param_mismatches, param_stats = ([], {"params_compared": 0,
                                           "params_unserialized": 0,
                                           "params_mismatched": 0,
                                           "tolerance": 1e-4})
    params_checked = False
    if check_params:
        try:
            param_mismatches, param_stats = _diff_params(d_file, d_live)
            params_checked = True
        except Exception as e:  # noqa: BLE001 — 参数层失败不许连累结构层
            param_stats = {"error": "参数比对失败: %s" % e}

    note = ("autosave 比进程还旧 ⇒ 上一会话残留，结果不可当真" if stale else
            "结构比对基于 live autosave")
    if not check_params:
        note += "；参数层未检查（check_params=False）"
    else:
        note += ("；参数层已检查（%d 项比对，%d 项不一致，%d 项因引擎不序列化无界参数而跳过）"
                 % (param_stats.get("params_compared", 0),
                    param_stats.get("params_mismatched", 0),
                    param_stats.get("params_unserialized", 0)))
    if started is None:
        note += "；⚠️ 未检测到运行中的 Cardinal 进程 —— 比对对象可能是残留 autosave"
    return {
        "patch": os.path.basename(p),
        "match": not (miss_m or extra_m or miss_c or extra_c),
        "params_match": (not param_mismatches) if params_checked else None,
        "params_checked": params_checked,
        "params": param_stats,
        "param_mismatches": param_mismatches,
        "modules_file": len(mods_f), "modules_live": len(mods_l),
        "cables_file": len(cab_f), "cables_live": len(cab_l),
        "missing_modules": sorted("%s/%s(#%s)" % (pl, md, i) for i, pl, md in miss_m),
        "extra_modules": sorted("%s/%s(#%s)" % (pl, md, i) for i, pl, md in extra_m),
        "missing_cables": ["%s#%s -> %s#%s" % c for c in sorted(miss_c)],
        "extra_cables": ["%s#%s -> %s#%s" % c for c in sorted(extra_c)],
        "stale": stale,
        "freshness_known": started is not None,
        "source": "autosave_snapshot", "note": note}


def cardinal_deploy(name, load_after=True):
    """Audit, optionally load, then compare the limited autosave snapshot.

    load_after=False must never load or diff. A source-file backup is NOT a
    backup of unsaved GUI state. Successful snapshot checks do not verify
    live memory, sequencer data, layout or sound; missing evidence fails closed.
    """
    invalid = _tool_input_error("cardinal_deploy", {"name": name, "load_after": load_after})
    if invalid:
        return invalid
    p = resolve(name)
    if not os.path.exists(p):
        return {"error": "patch not found: %s" % p}
    bak = p + ".bak-deploy"
    shutil.copy2(p, bak)
    au = cardinal_audit(name)
    if not isinstance(au, dict) or au.get("error") or au.get("verdict") not in ("PASS", "WARN"):
        return {"ok": False, "deployed": False, "backup": bak,
                "why": "Audit failed or did not provide a valid verdict; refusing to load.", "audit": au}
    if not load_after:
        return {"ok": True, "deployed": False, "loaded": False,
                "verified": False, "stage": "audited", "backup": bak,
                "audit": au, "note": "Audit only; the running rack was not loaded or verified."}
    loaded = load_patch(p)
    if not isinstance(loaded, dict) or not loaded.get("ok"):
        return {"ok": False, "deployed": False, "backup": bak,
                "why": "/load failed（Cardinal 开着吗？OSC 开了吗）",
                "load_result": loaded}
    out = {"ok": False, "deployed": os.path.basename(p), "loaded": True,
           "verified": False, "stage": "loaded", "load_association_proven": False,
           "verification_scope": "autosave_structure_and_params",
           "live_verified": False, "backup": bak, "load_result": loaded,
           "audit_verdict": au.get("verdict"),
           "note": "Autosave comparison is not current-memory, module-data or audio verification."}
    if loaded.get("warnings"):
        out.update(stage="loaded_with_warnings",
                   why="Load warnings require inspection before verification.")
        return out
    try:
        time.sleep(1.0)  # A delay alone is not evidence of autosave completion.
        diff = cardinal_diff(name)
        param_stats = diff.get("params") if isinstance(diff, dict) else None
        snapshot_complete = (isinstance(diff, dict) and not diff.get("error")
                    and diff.get("match") is True
                    and diff.get("params_checked") is True
                    and diff.get("params_match") is True
                    and diff.get("freshness_known") is True
                    and diff.get("stale") is False
                    and isinstance(param_stats, dict)
                    and param_stats.get("params_unserialized") == 0)
        # No request-linked autosave evidence exists in this protocol. Even a
        # changed file cannot establish load causality, instance ownership or
        # current memory. Deliberately fail closed for every deploy this batch.
        out.update(stage="compared", diff=diff,
                   snapshot_comparison_complete=snapshot_complete)
        out["why"] = ("Loaded, but this load's snapshot association is unproven; "
                      "autosave comparison alone cannot verify deployment.")
    except Exception as exc:  # Never erase a confirmed /load side effect.
        out.update(stage="verification_failed", error=str(exc),
                   why="Load succeeded; snapshot verification failed. Do not blindly retry load.")
    return out


def ping():
    """Send OSC `/hello` and expect a `/resp` back — pure connectivity probe."""
    res = link().ask("/hello")
    if res is None:
        return {"ok": False, "target": f"{CARDINAL_IP}:{CARDINAL_PORT}",
                "note": "no /resp received. Confirm Cardinal OSC enabled + port matches."}
    return {"ok": True, "reply": [str(x) for x in res]}


# ============================================================ OSC read probes
# ★ 2026-10-19：Cardinal 原版 OSC **只能写不能读**（只有 /hello /param /
#   /host-param /load，且都不回数据）。下面这组工具依赖**李本机编译的**
#   打了补丁的 Cardinal（tools/osc_patch/），它新增了 5 个只读端点：
#     /modules  /param-get  /ports  /signal  /light
#   无应答只说明未收到有效响应，不能据此认定构建缺端点或建议重编。

PROBE_UNSUPPORTED = {
    "ok": False, "error": "probe_no_response",
    "note": "No valid probe reply received. Check process, target, OSC and timeout; "
            "this does not establish that the build lacks the endpoint. Do not retry writes blindly.",
}


def _ask_status(tag, address, args=(), timeout=None):
    """Send one probe and parse `/resp` ("tag", "payload"[, "status"]).

    E1 (2026-10-21) appended a third string: "ok" or "err:<CODE>". Builds that
    predate E1 send only two strings; those are treated as "ok", so old and new
    exe both work with this client.

    Returns (payload, status), or (None, None) when the peer did not answer.
    """
    res = link().ask(address, args, timeout=timeout, reply_tag=tag)
    if res is None:
        return None, None
    if not isinstance(res, (list, tuple)) or len(res) not in (2, 3):
        return "malformed probe reply", "err:E_INTERNAL"
    if str(res[0]) != tag:
        return None, None
    payload = str(res[1])
    status = str(res[2]) if len(res) > 2 else "ok"
    if status != "ok" and status not in _STATUS_NOTES:
        return "unknown probe status: %s" % status, "err:E_INTERNAL"
    return payload, status


def _ask(tag, address, args=()):
    """Payload-only view of `_ask_status` (keeps existing call sites unchanged)."""
    payload, _status = _ask_status(tag, address, args)
    return payload


_STATUS_NOTES = {
    "err:E_NO_PLUGIN": "Cardinal's OSC bridge has no plugin instance yet (still starting up?)",
    "err:E_NO_MODULE": "no module with that id exists in the running rack",
    "err:E_BAD_PARAM": "module exists but the param/light index is out of range",
    "err:E_NO_CABLE": "no cable with that id exists",
    "err:E_NO_MODEL": "no plugin|model matches that slug (check the slugs with cardinal_plugins)",
    "err:E_BAD_PORT": "port index out of range",
    "err:E_NOTHING": "nothing to undo/redo",
    "err:E_BAD_ARGS": "bad request arguments (e.g. script index)",
    "err:E_DISABLED": "feature disabled by environment (CARDINAL_JS_MODE)",
    "err:E_INTERNAL": "Cardinal internal failure",
}


def _status_note(status):
    return _STATUS_NOTES.get(status, "unexpected status: %s" % status)


def live_modules():
    """List every module currently instantiated in the RUNNING Cardinal.

    This is the ground truth of what the engine really loaded — it catches the
    class of bug where a .vcv file is fine on disk but the engine silently
    dropped a module (e.g. wrong plugin slug).
    """
    payload, status = _ask_status("modules", "/modules")
    if payload is None:
        return dict(PROBE_UNSUPPORTED)
    if status != "ok":
        return _hist_status(payload, status)
    mods = []
    for item in payload.split(","):
        if not item.strip():
            continue
        try:
            mid, rest = item.split(":", 1)
            plug, model = rest.split("|", 1)
            mods.append({"module_id": int(mid), "plugin": plug, "model": model})
        except ValueError:
            continue
    return {"ok": True, "count": len(mods), "modules": mods}


def modules_page(offset=0, limit=32):
    """Read one PAGE of running modules (E2, 2026-10-21).

    `/modules` returns everything in one datagram; this is the paged twin for
    when a rack grows large. Wire payload is `<returned>/<total>|<items>` where
    items use the same `id:plugin|model` shape as live_modules.

      offset  — 0-based start index into the module list
      limit   — page size, capped at 64 by the server

    Overshooting offset returns empty items but still reports the real total.
    """
    payload, status = _ask_status(
        "modules-page", "/modules-page",
        [("i", int(offset)), ("i", int(limit))])
    if payload is None:
        return dict(PROBE_UNSUPPORTED)
    if status.startswith("err"):
        return {"ok": False, "offset": int(offset), "limit": int(limit),
                "status": status, "raw": payload, "note": _status_note(status)}
    # payload = "<returned>/<total>|<items>"
    try:
        head, items = payload.split("|", 1)
        returned_s, total_s = head.split("/", 1)
        returned, total = int(returned_s), int(total_s)
    except ValueError:
        return {"ok": False, "offset": int(offset), "limit": int(limit),
                "status": status, "raw": payload, "note": "unparseable page payload"}
    mods = []
    for item in items.split(","):
        if not item.strip():
            continue
        try:
            mid, rest = item.split(":", 1)
            plug, model = rest.split("|", 1)
            mods.append({"module_id": int(mid), "plugin": plug, "model": model})
        except ValueError:
            continue
    return {"ok": True, "offset": int(offset), "limit": int(limit),
            "returned": returned, "total": total,
            "has_more": int(offset) + returned < total,
            "count": len(mods), "modules": mods, "status": status}


def get_param(module_id, param_id):
    """Read back one knob's DISPLAY value (the physical number, not the stored one).

    Display mappings are module-specific (ADSR.Attack stores 0.5 and shows
    100 ms; Bogaudio VCO also depends on its Slow mode). The
    patched build returns getDisplayValue(), i.e. the number a human can judge.
    """
    payload, status = _ask_status(
        "param", "/param-get", [("h", int(module_id)), ("i", int(param_id))])
    if payload is None:
        return dict(PROBE_UNSUPPORTED)
    if status.startswith("err"):
        return {"ok": False, "module_id": int(module_id), "param_id": int(param_id),
                "status": status, "raw": payload, "note": _status_note(status)}
    try:
        val = float(payload)
    except (TypeError, ValueError):
        return {"ok": False, "module_id": module_id, "param_id": param_id,
                "status": status, "raw": payload,
                "note": "the slot exists but reports no numeric display value"}
    return {"ok": True, "module_id": int(module_id), "param_id": int(param_id),
            "display_value": val, "status": status}


def _parse_ports(payload):
    """Parse the /ports payload into a list of port dicts.

    Wire format per port: `<dir>:<index>:<channels>:<v0>:<v1>:<v2>:<v3>`
    where dir is `in` or `out`.
    """
    out = []
    for item in payload.split("|"):
        if not item.strip():
            continue
        f = item.split(":")
        if len(f) < 4:
            continue
        try:
            volts = [float(x) for x in f[3:7]]
        except ValueError:
            volts = []
        out.append({
            "direction": f[0],
            "index": int(f[1]),
            "channels": int(f[2]),
            "connected": int(f[2]) > 0,
            "voltages": volts,
            "peak": max((abs(v) for v in volts), default=0.0),
        })
    return out


def module_ports(module_id):
    """Read a module's live port state: is each port wired, and is there signal NOW?

    This directly answers "does this patch actually make sound?" without any
    offline rendering — it asks the engine what is on each port right now.
    Three distinct states are separable:
        channels == 0     -> port isn't wired at all (statically dead)
        channels > 0, all voltages 0 -> wired but silent at this instant
        any voltage != 0   -> signal present
    """
    payload, status = _ask_status("ports", "/ports", [("h", int(module_id))])
    if payload is None:
        return dict(PROBE_UNSUPPORTED)
    if status.startswith("err"):
        return {"ok": False, "module_id": int(module_id), "status": status,
                "note": _status_note(status)}
    ports = _parse_ports(payload)
    wired = [p for p in ports if p["connected"]]
    live = [p for p in wired if p["peak"] > 1e-4]
    return {
        "ok": True,
        "module_id": int(module_id),
        "ports": ports,
        "wired": len(wired),
        "live": len(live),
        "silent": len(wired) - len(live),
        "status": status,
    }


def scan_signal(threshold=1e-4):
    """Scan the whole rack and report which modules currently emit a non-zero voltage.

    The direct answer to "is anything actually sounding right now". A module whose
    every connected output sits at 0 V is producing no sound at this instant.
    """
    payload, status = _ask_status("signal", "/signal")
    if payload is None:
        return dict(PROBE_UNSUPPORTED)
    if status != "ok":
        return _hist_status(payload, status)
    hits = {}
    for item in payload.split(","):
        if not item.strip():
            continue
        try:
            mid, peak = item.split(":", 1)
            hits[int(mid)] = float(peak)
        except ValueError:
            continue
    return {"ok": True, "threshold": threshold,
            "emitting": len(hits), "peaks": hits}


def get_light(module_id, light_id):
    """Read an LED's brightness — e.g. Clocked's RUN lamp tells you if it is running."""
    payload, status = _ask_status(
        "light", "/light", [("h", int(module_id)), ("i", int(light_id))])
    if payload is None:
        return dict(PROBE_UNSUPPORTED)
    if status.startswith("err"):
        return {"ok": False, "module_id": int(module_id), "light_id": int(light_id),
                "status": status, "raw": payload, "note": _status_note(status)}
    try:
        return {"ok": True, "module_id": int(module_id), "light_id": int(light_id),
                "brightness": float(payload), "status": status}
    except (TypeError, ValueError):
        return {"ok": False, "module_id": module_id, "light_id": light_id,
                "status": status, "raw": payload}


# ============================================================ B 组读数（2026-10-20）
# 第二批注入的只读端点（源码依据见 tools/osc_patch/osc_read_b_handlers.cpp.inc，
# 构建与验收见 docs/TODO-BACKLOG.md 批次 B）：/build-info /cables /transport
# /engine-info /plugins。同样依赖打过补丁的 Cardinal，未打补丁时优雅降级。

def _parse_kv(payload):
    """Parse a "k=v|k=v" payload into a dict (values stay strings)."""
    out = {}
    for part in payload.split("|"):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def build_info():
    """Build fingerprint of the RUNNING Cardinal (TODO-BACKLOG P0).

    variant/mode/build/safeMode/caps. `caps` lists every read endpoint this
    build actually serves. Combined with a process check on the MCP side, a
    timeout becomes diagnosable: process gone = crashed; process alive but no
    reply = OSC not started (they look identical from the client alone).
    """
    payload, status = _ask_status("build-info", "/build-info")
    if payload is None:
        return dict(PROBE_UNSUPPORTED)
    if status != "ok":
        return _hist_status(payload, status)
    info = _parse_kv(payload)
    caps = [c for c in info.pop("caps", "").split(",") if c]
    return {"ok": True, "variant": info.get("variant"), "mode": info.get("mode"),
            "build": info.get("build"),
            "safe_mode": info.get("safeMode") == "1", "caps": caps, **info}


def cables(module_id=None):
    """Every cable in the running rack: id, input (module,port), output (module,port).

    Pass module_id to filter to just that module's cables. This is the wiring
    ground truth — the same connections a human sees dragged on screen.
    """
    args = () if module_id is None else [("h", int(module_id))]
    payload, status = _ask_status("cables", "/cables", args)
    if payload is None:
        return dict(PROBE_UNSUPPORTED)
    if status != "ok":
        return _hist_status(payload, status)
    if payload == "none":
        return {"ok": True, "count": 0, "cables": []}
    out = []
    for item in payload.split(","):
        f = item.split(":")
        if len(f) != 5:
            continue
        try:
            cid, im, ip, om, op = (int(x) for x in f)
        except ValueError:
            continue
        out.append({"cable_id": cid, "input_module": im, "input_port": ip,
                    "output_module": om, "output_port": op})
    return {"ok": True, "count": len(out), "cables": out}


def cables_page(offset=0, limit=32):
    """Read one PAGE of the running rack's cables (B2, 2026-10-21).

    Paged twin of `cables()` for when a rack grows large — `/cables` returns
    everything in one datagram, and a poly-16 rack's cable list can blow up
    the payload. Wire payload is `<returned>/<total>|id:inMod:inId:outMod:outId,...`
    where items use the same shape as `cables()`.

      offset  — 0-based start index into the cable list
      limit   — page size, capped at 64 by the server

    Overshooting offset returns empty items but still reports the real total.
    """
    payload, status = _ask_status(
        "cables-page", "/cables-page",
        [("i", int(offset)), ("i", int(limit))])
    if payload is None:
        return dict(PROBE_UNSUPPORTED)
    if status.startswith("err"):
        return {"ok": False, "offset": int(offset), "limit": int(limit),
                "status": status, "raw": payload, "note": _status_note(status)}
    # payload = "<returned>/<total>|<items>"
    try:
        head, items = payload.split("|", 1)
        returned_s, total_s = head.split("/", 1)
        returned, total = int(returned_s), int(total_s)
    except ValueError:
        return {"ok": False, "offset": int(offset), "limit": int(limit),
                "status": status, "raw": payload, "note": "unparseable page payload"}
    out = []
    for item in items.split(","):
        f = item.split(":")
        if len(f) != 5:
            continue
        try:
            cid, im, ip, om, op = (int(x) for x in f)
        except ValueError:
            continue
        out.append({"cable_id": cid, "input_module": im, "input_port": ip,
                    "output_module": om, "output_port": op})
    return {"ok": True, "offset": int(offset), "limit": int(limit),
            "returned": returned, "total": total,
            "has_more": int(offset) + returned < total,
            "count": len(out), "cables": out, "status": status}


def log_get(from_index=0, limit=32):
    """Read Cardinal's in-process log ring buffer (C3, 2026-10-22).

    Cardinal's own logger writes to stderr, which a GUI standalone has nowhere
    to send — until now nothing was readable in-process. This reads the ring
    buffer incrementally: pass `next` back in to get only what is new.

      from_index  — sequence number to start from (0 = oldest available)
      limit       — page size, capped at 64 by the server

    Returns first/next + the lines. `first` may exceed from_index if older
    entries were evicted (2000-line ring) — the reply says so honestly.
    """
    payload, status = _ask_status(
        "log-get", "/log-get",
        [("i", int(from_index)), ("i", int(limit))])
    if payload is None:
        return dict(PROBE_UNSUPPORTED)
    if status.startswith("err"):
        return {"ok": False, "from_index": int(from_index), "limit": int(limit),
                "status": status, "raw": payload, "note": _status_note(status)}
    # payload = "<first>/<next>|<lines, \\n separated>"
    try:
        head, items = payload.split("|", 1)
        first_s, next_s = head.split("/", 1)
        first, nxt = int(first_s), int(next_s)
    except ValueError:
        return {"ok": False, "from_index": int(from_index), "limit": int(limit),
                "status": status, "raw": payload, "note": "unparseable payload"}
    lines = items.split("\n") if items else []
    return {"ok": True, "from_index": int(from_index), "limit": int(limit),
            "first": first, "next": nxt, "has_more": nxt > first + len(lines),
            "count": len(lines), "lines": lines, "status": status}


def add_module(plugin, model, x, y):
    """Add a module to the running rack, like right-click -> Add module.

    `plugin` and `model` are the two slugs Cardinal uses (e.g. "Bogaudio-VCO"
    and "VCO-2"); x/y are GRID CELLS (1 cell = 15 px wide, 1 row = 380 px).
    The new module lands in the rack and can be undone with cardinal_undo.

    Slugs are not guessable — list the running ones first with
    cardinal_plugins (or cardinal_module_search) to get them right.
    """
    payload, status = _ask_status("module-add", "/module-add",
                                   (("s", "%s|%s" % (plugin, model)),
                                    ("i", int(x)), ("i", int(y))))
    if payload is None:
        return dict(PROBE_UNSUPPORTED)
    if status.startswith("err"):
        # note: the older write tools use _hist(), which drops the status and
        # would report ok=True for a rejected slug. This one keeps it honest.
        return {"ok": False, "status": status, "raw": payload,
                "note": _status_note(status)}
    return {"ok": True, "result": payload, "status": status}


def add_module_named(query, x, y, pick=None):
    """Add a module by PLAIN-LANGUAGE name (2026-10-24, 李拍板组合方案).

    You say "VCV VCF" or "Bogaudio VCO"; this resolves the exact
    plugin|model slugs for you — no slug table memorization.

    Stateless two-stage (no server-side session):
      stage 1: resolve(query)
                 unique hit   -> added directly (zero guessing)
                 multiple     -> candidate list, you pick a number
                 none         -> honest miss + suggestions
      stage 2: call again with pick=N (1-based index from the list)
                 -> lands candidate N; out-of-range re-lists candidates

    李's ruling (10-24): direct add ONLY on a unique hit — never guess
    among several. Undo is always available via cardinal_undo.
    """
    r = modresolve.resolve(query)
    if r["status"] == "no_match":
        return {"ok": False, "error": "no_match", "query": query,
                "hint": r.get("hint"),
                "brand_resolved": r.get("brand_resolved"),
                "untranslated_zh": r.get("untranslated_zh")}

    cands = r["candidates"]
    if pick is not None:
        pick = int(pick)
        if not 1 <= pick <= len(cands):
            return {"ok": False, "error": "bad_pick", "pick": pick,
                    "n_candidates": r["matched"],
                    "candidates": cands, "has_more": r.get("has_more"),
                    "hint": "pick 须在 1..%d；候选列表原样重列，重挑一个"
                            % len(cands)}
        chosen = cands[pick - 1]
    elif r["status"] == "unique" and len(cands) == 1:
        chosen = cands[0]
    else:
        # 歧义不是错误：调用成功了，只是需要李点一个序号。
        return {"ok": True, "added": False, "needs_pick": True,
                "query": query, "n_candidates": r["matched"],
                "candidates": cands, "has_more": r.get("has_more"),
                "brand_resolved": r.get("brand_resolved"),
                "hint": r.get("hint")}

    # 落地：复用老工具的精确 slug 路径（_ask_status，err 如实报不假 ok）
    res = add_module(chosen["plugin"], chosen["model"], x, y)
    if not res.get("ok"):
        return {"ok": False, "error": "add_failed", "chosen": chosen,
                "add_result": res,
                "hint": "slug 在 manifest 里存在但引擎拒绝了（插件未加载？）"
                        "——可 cardinal_undo，或从候选里换一个 pick"}
    return {"ok": True, "added": True, "query": query,
            "matched_via": {
                "brand_resolved": r.get("brand_resolved"),
                "expanded_terms": r.get("expanded_terms"),
                "match_score": chosen.get("match_score"),
                "matched_terms": chosen.get("matched_terms"),
            },
            "picked": chosen, "add_result": res,
            "note": "不满意可 cardinal_undo 撤销；位置不满意可 cardinal_module_move"}


def load_skipped():
    """List modules/cables the last /load skipped (C2, 2026-10-22).

    Missing plugins and broken cables used to vanish silently — cable skips
    are deliberately not even logged upstream, and module skips only reached
    warningLog without ids. Each entry carries kind ("module"/"cable"), the
    id from the patch file, and a sanitized reason.
    """
    payload, status = _ask_status("load-skipped", "/load-skipped", [])
    if payload is None:
        return dict(PROBE_UNSUPPORTED)
    if status.startswith("err"):
        return {"ok": False, "status": status, "raw": payload,
                "note": _status_note(status)}
    # payload = "<n>|kind:id:reason,kind:id:reason,..."
    try:
        head, items = payload.split("|", 1)
        n = int(head)
    except ValueError:
        return {"ok": False, "status": status, "raw": payload,
                "note": "unparseable payload"}
    skips = []
    if items:
        for entry in items.split(","):
            f = entry.split(":", 2)
            if len(f) == 3:
                try:
                    skips.append({"kind": f[0], "id": int(f[1]), "reason": f[2]})
                except ValueError:
                    skips.append({"kind": f[0], "id": None, "reason": f[2]})
    return {"ok": True, "count": n, "skips": skips, "status": status}


def transport():
    """Transport state: playing / bar / beat / bpm / tick / bypassed.

    Zero-hook — CardinalPluginContext already carries all of it.
    """
    payload, status = _ask_status("transport", "/transport")
    if payload is None:
        return dict(PROBE_UNSUPPORTED)
    if status != "ok":
        return _hist_status(payload, status)
    info = _parse_kv(payload)
    return {"ok": True,
            "playing": info.get("playing") == "1",
            "bar": int(info.get("bar", 0)), "beat": int(info.get("beat", 0)),
            "beats_per_bar": int(info.get("bpb", 0)),
            "beat_type": int(info.get("beatType", 0)),
            "bpm": float(info.get("bpm", 0) or 0),
            "tick": float(info.get("tick", 0) or 0),
            "ticks_per_beat": float(info.get("ticksPerBeat", 0) or 0),
            "bypassed": info.get("bypassed") == "1"}


def engine_info():
    """Engine facts: sample rate, buffer size, CPU load average/max.

    ⚠️ CPU meters refresh only once per second (Engine.cpp:576). The reply
    carries cpuRefreshMs=1000 so callers know the data can be up to 1 s old —
    the exact age is private engine state we refuse to fake.
    """
    payload, status = _ask_status("engine-info", "/engine-info")
    if payload is None:
        return dict(PROBE_UNSUPPORTED)
    if status != "ok":
        return _hist_status(payload, status)
    info = _parse_kv(payload)
    try:
        return {"ok": True,
                "sample_rate": float(info.get("sampleRate", 0) or 0),
                "buffer_size": int(info.get("bufferSize", 0) or 0),
                "cpu_avg": float(info.get("cpuAvg", 0) or 0),
                "cpu_max": float(info.get("cpuMax", 0) or 0),
                "cpu_refresh_ms": int(info.get("cpuRefreshMs", 1000) or 1000)}
    except ValueError:
        return {"ok": False, "raw": info}


def plugins(plugin=None):
    """Plugin facts, split by layer (B5):
    - runtime: which plugin slugs appear in the CURRENT rack (engine truth)
    - disk: is a given slug installed at all (PluginManifests — the layer that
      answers 'my spelling looks right but it won't load')
    - safeMode: when true, NO plugin loaded at all — first suspect for that case
    """
    payload, status = _ask_status("plugins", "/plugins")
    if payload is None:
        return dict(PROBE_UNSUPPORTED)
    if status != "ok":
        return _hist_status(payload, status)
    info = _parse_kv(payload)
    slugs = [s for s in info.get("plugins", "").split(",") if s and s != "none"]
    out = {"ok": True, "safe_mode": info.get("safeMode") == "1",
           "rack_plugins": slugs}
    if plugin:
        p = str(plugin)
        out["query"] = p
        out["in_rack"] = p in slugs
        hit = None
        d = modbrowser._manifest_dir()
        if d:
            for fn in sorted(os.listdir(d)):
                if not fn.endswith(".json"):
                    continue
                try:
                    with open(os.path.join(d, fn), "r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception:
                    continue
                if (data.get("slug") or "").lower() == p.lower():
                    hit = {"slug": data.get("slug"),
                           "brand": data.get("brand"),
                           "version": data.get("version"),
                           "modules": len(data.get("modules") or [])}
                    break
        out["installed"] = hit is not None
        out["manifest"] = hit
    return out


# ================================================================ C 组：模拟人类操作
# 这些端点对应李在 GUI 里真实会做的动作（拖模块、连线、拧旋钮、Ctrl+Z），
# 与 A/B 组的区别：前两组只读，C 组**改状态**。全部走 history API ⇒ 可 undo。
#
# ⚠️ 为什么 module-add 之类「需要任意字符串参数」的操作只有 JS 路径：
# 本 Cardinal 版的 liblo **接收 string 参数确认不通**（2026-10-20 实测：echo /
# module-add / js-eval 三个 string 输入端点全部无应答，两种偏移读法都试过）。
# liblo 的「发送 string」正常（所有 /resp 都是字符串）⇒ 只接收坏了。
# 所以：数值参数类操作走下面的 OSC 端点；需要自由文本/JSON 的走 JS 脚本。

def _hist(what):
    """Wrap a history-mutating probe result into the common shape."""
    if what is None:
        return dict(PROBE_UNSUPPORTED)
    return {"ok": True, "result": what}


def _hist_status(payload, status):
    """Like _hist() but keeps the error status.

    _hist() reports ok=True for everything the OSC bridge answered, including
    err:<CODE> replies — so a rejected edit (unknown module id, nothing to
    undo, ...) looked successful. Write tools use this instead (2026-10-22).
    """
    if payload is None:
        return dict(PROBE_UNSUPPORTED)
    if status != "ok":
        return {"ok": False, "status": status, "raw": payload,
                "note": _status_note(status)}
    return {"ok": True, "result": payload, "status": status}


def set_param_by_display(module_id, param, value):
    """Set a knob the way a HUMAN sets it — by its DISPLAYED value.

    This is the crucial difference from set_param (which writes the raw 0..1
    normalized storage value). A knob's display domain is module-specific and
    often non-linear or non-0..1: a VCO frequency shows Hz, an ADSR attack
    shows seconds, and the frequency scale is exponential. Writing 0.8 "as a
    display value" and getting back 11.56 Hz is CORRECT behaviour — the engine
    converts it. So verify with get_param, not by comparing to the input.

    Returns the old/new storage values (a human sees the display value move).
    """
    invalid = _parameter_input_error(module_id, param, value)
    if invalid:
        return invalid
    payload, status = _ask_status("param-set", "/param-set-by-display",
                   (("h", int(module_id)), ("i", int(param)), ("f", float(value))))
    if payload is None:
        return dict(PROBE_UNSUPPORTED)
    if status != "ok":
        return _hist_status(payload, status)
    if not payload.startswith("ok"):
        return {"ok": False, "raw": payload}
    m = re.match(r"ok old=(\S+) new=(\S+)", payload)
    if not m:
        return {"ok": True, "raw": payload}
    return {"ok": True, "module_id": int(module_id), "param": int(param),
            "display_value": float(value),
            "old_storage": float(m.group(1)), "new_storage": float(m.group(2)),
            "history": "change parameter"}


def cable_add(module_id, input_port, target_module_id, output_port):
    """Drag a cable: connect output (module, port) -> input (module, port).

    The reverse of what a human does (they pull from a widget port to a widget
    port) but the same wire. Goes through history, so /undo removes it.

    ⚠️ One input accepts ONE cable — a second connection on the same input
    displaces the first. That is a hard engine rule, not a tool choice.
    """
    invalid = _tool_input_error("cardinal_cable_add", {
        "module_id": module_id, "input_port": input_port,
        "target_module_id": target_module_id, "output_port": output_port})
    if invalid:
        return invalid
    payload, status = _ask_status("cable-add", "/cable-add",
                   (("h", int(target_module_id)), ("i", int(output_port)),
                    ("h", int(module_id)), ("i", int(input_port))))
    return _hist_status(payload, status)


def cable_remove(cable_id):
    """Right-click a cable -> Disconnect."""
    payload, status = _ask_status("cable-remove", "/cable-remove", (("h", int(cable_id)),))
    return _hist_status(payload, status)


def undo():
    """Ctrl+Z on the running rack. Returns the name of the action undone."""
    payload, status = _ask_status("undo", "/undo")
    return _hist_status(payload, status)


def redo():
    """Ctrl+Shift+Z on the running rack."""
    payload, status = _ask_status("redo", "/redo")
    return _hist_status(payload, status)


def module_json(module_id):
    """Read one live module's full .vcv JSON (params, data, slots, version).

    The live counterpart of patch_info's per-module view, and the ground truth
    for editing a module properly: hand the JSON to module_from_json (JS API) or
    edit it and deploy the patch.
    """
    payload, status = _ask_status("module-json", "/module-json", (("h", int(module_id)),))
    if payload is None:
        return dict(PROBE_UNSUPPORTED)
    if status != "ok":
        return _hist_status(payload, status)
    try:
        data = json.loads(payload)
    except ValueError:
        return {"ok": False, "raw": payload[:400]}
    return {"ok": True, "module_id": int(module_id), "module": data}


def module_remove(module_id):
    """Select a module and press Delete — removes it and its cables."""
    payload, status = _ask_status("module-remove", "/module-remove", (("h", int(module_id)),))
    return _hist_status(payload, status)


def module_move(module_id, x, y):
    """Drag a module to grid position (x, y).

    ⚠️ Units follow the .vcv file: x is in GRID cells, y is a ROW INDEX
    (VCV stores pos[0] as cell x and pos[1] as row y). Same as the file format.
    """
    payload, status = _ask_status("module-move", "/module-move",
                   (("h", int(module_id)), ("i", int(x)), ("i", int(y))))
    return _hist_status(payload, status)


def module_copy(module_id, with_cables=True):
    """Duplicate a module in the running rack (B3, 2026-10-21).

    The OSC twin of the human right-click "Duplicate" / "Duplicate with
    cables" action (ModuleWidget::cloneAction). Returns the NEW module's id.

      with_cables=True (default) — cables on the source's INPUT ports are
      cloned onto the new module (upstream fans out; a self-patch reconnects
      to the clone). Same semantics as the human action, and it can never
      violate the one-cable-per-input-port rule.

    The whole duplication is ONE history entry, so cardinal_undo reverts the
    module and its cloned cables in a single step.
    """
    payload, status = _ask_status(
        "module-copy", "/module-copy",
        [("h", int(module_id)), ("i", 1 if with_cables else 0)])
    if payload is None:
        return dict(PROBE_UNSUPPORTED)
    if status.startswith("err"):
        return {"ok": False, "module_id": int(module_id),
                "with_cables": bool(with_cables),
                "status": status, "raw": payload, "note": _status_note(status)}
    # payload = "<newModuleId> copied_cables=<n>"
    try:
        id_part, cables_part = payload.split(" ", 1)
        new_id = int(id_part)
        copied = int(cables_part.split("=", 1)[1]) if "=" in cables_part else None
    except ValueError:
        return {"ok": False, "module_id": int(module_id),
                "status": status, "raw": payload,
                "note": "unparseable payload"}
    return {"ok": True, "module_id": int(module_id),
            "with_cables": bool(with_cables),
            "new_module_id": new_id, "cables_copied": copied,
            "status": status}


def midi_out(port, status, data1, data2=0, frame=-1):
    """Inject a MIDI message into the running rack (what a hardware keyboard sends).

    ⚠️ port must be 0..15 (DPF MIDI channel) and status 0x80..0xEF. Only
    frame=-1 (send now) is supported by the current four-argument endpoint.
    Deferred frames are rejected without sending. If the sequencer
    transport is bypassed, the reply reports skipped:bypassed — the message was
    accepted but NOT delivered, and we say so rather than pretending it worked.
    """
    invalid = _tool_input_error("cardinal_midi_out", {
        "port": port, "status": status, "data1": data1, "data2": data2, "frame": frame})
    if invalid:
        return {**invalid, "delivered": False}
    if frame != -1:
        return {"ok": False, "delivered": False, "error": "deferred_midi_unsupported"}
    payload, osc_status = _ask_status("midi-out", "/midi-out",
                   (("i", int(port)), ("i", int(status)),
                    ("i", int(data1)), ("i", int(data2))))
    if payload is None:
        return dict(PROBE_UNSUPPORTED)
    if osc_status != "ok":
        return {**_hist_status(payload, osc_status), "delivered": False}
    out = {"ok": True, "port": int(port), "status": int(status),
           "data1": int(data1), "data2": int(data2), "frame": int(frame),
           "reply": payload}
    if payload.startswith("skipped"):
        out["delivered"] = False
        out["reason"] = payload
    elif payload == "sent":
        out["delivered"] = True
    else:
        out.update(ok=False, delivered=False, error="unexpected_midi_reply")
    return out


# ------------------------------------------------------------ QuickJS 绑定
# 进程内 JS 执行 —— 对标 blender/godot/UE MCP 的「宿主内执行代码」，是这批
# 唯一能自由表达复杂操作的通路。
#
# 安全模型（三重门，缺一不可）：
#   1. **默认关闭**：CARDINAL_JS_MODE 未设或非 read/write ⇒ /osc-js-run 直接
#      回 disabled。李必须显式 export 才生效。
#   2. **不初始化 libc**：只 JS_NewRuntime + JS_NewContext，绝不
#      addQuickJSModule / JS_AddIntrinsic* 的 std/os ⇒ 没有 std、没有 require、
#      没有 exec 任意命令。（lethal trifecta：外发能力直接砍掉）
#   3. **墙钟预算**：执行超 2000ms（CARDINAL_JS_BUDGET_MS 可覆盖）即被 quickjs
#      中断，回 budget-exceeded。死循环脚本实测 2001ms 准点打断、进程存活。
#
# 脚本契约：被包成 globalThis.result = (function(){ <脚本> })(); 所以用
# `return` 交结果。脚本目录 CARDINAL_JS_DIR（默认 D:/Cardinal/js，可 git
# 管理——比每次传字符串更工程化）。

JS_DEFAULT_DIR = r"D:/Cardinal/js"


def js_list():
    """List the JS scripts available to /osc-js-run (1-based indexes)."""
    payload, status = _ask_status("js-list", "/osc-js-list")
    if payload is None:
        return dict(PROBE_UNSUPPORTED)
    if status != "ok":
        return _hist_status(payload, status)
    items = []
    for entry in payload.split(","):
        if ":" in entry:
            i, name = entry.split(":", 1)
            items.append({"index": int(i), "name": name})
    return {"ok": True, "count": len(items), "scripts": items,
            "script_dir": JS_DEFAULT_DIR}


def js_run(index):
    """Execute a JS script by index (from js_list) inside the RUNNING Cardinal.

    The script runs synchronously on Cardinal's UI thread with a wall-clock
    budget. Available API:

      read  (CARDINAL_JS_MODE=read or write): cardinal.modules() / getParam(id, n)
            / ports(id) / cables() / transport() / moduleJson(id)
      write (CARDINAL_JS_MODE=write only):       cardinal.setDisplayValue(id, n, v)
            / moduleFromJson(id, json) / addModule(slug, x, y)
            / cableAdd(...) / undo() / redo()

    Return contract: the script is wrapped in an IIFE — use `return "..."`.
    Over budget returns {"budget_exceeded_ms": N}; a JS error returns
    {"error": "..."}. Write-mode failures are reported, never swallowed.
    """
    payload, status = _ask_status("js", "/osc-js-run", (("i", int(index)),),
                                  timeout=max(TIMEOUT, 3.0))
    if payload is None:
        return dict(PROBE_UNSUPPORTED)
    if status != "ok":
        return _hist_status(payload, status)
    out = {"ok": True, "script_index": int(index), "result": payload}
    if payload.startswith("disabled"):
        out["ok"] = False
        out["enabled"] = False
        out["hint"] = ("JS is disabled by default (safety). Set CARDINAL_JS_MODE=read "
                       "or =write in Cardinal's environment, then restart it.")
    elif payload.startswith("budget-exceeded"):
        out["ok"] = False
        out["budget_exceeded_ms"] = int(payload.split("ms=")[-1])
        out["hint"] = "The script ran past its wall-clock budget and was interrupted."
    elif payload.startswith("error"):
        out["ok"] = False
        out["error"] = payload[6:].strip()
    elif payload.startswith("no-script"):
        out["ok"] = False
        out["error"] = payload
    return out


# ================================================================ Live autosave
# Cardinal mirrors its running patch to %TEMP%\Cardinal.XXXX\patch.json, and THIS
# is the only way to "read" live state — OSC can only WRITE, never read.
#
# IMPORTANT — the mirror is NOT continuous (measured 2026-09-13 on 26.02):
#   * flushed on /load                 -> yes, verified
#   * flushed on a /param change       -> NO. knob tweaks never reach the file.
#   * flushed on a timer               -> NO. 20 s idle left mtime untouched.
#   * flushed on explicit GUI save     -> yes (Ctrl+S rewrites it)
# Consequences to keep in mind:
#   1. Right after launching Cardinal the newest file on disk may belong to a
#      PREVIOUS session, so treat the read as "last known state", not "current".
#   2. Because /param writes are invisible here, verify a set_param() by
#      looking at the GUI (screenshot), not by re-reading this file.
# `stale` / `age_seconds` in the return value of read_live() flag case 1.

# ---- Cardinal process introspection: lets us judge autosave freshness -------
# We cannot ask Cardinal for the time, but we CAN ask Windows when the running
# Cardinal.exe started. If the autosave predates that, it cannot describe the
# current session. Pure ctypes so the repo stays dependency-free.

def cardinal_proc_start():
    """Epoch seconds at which Cardinal.exe started; None if unknown/not running."""
    if not sys.platform.startswith("win"):
        return None
    try:
        import ctypes
        import ctypes.wintypes as wintypes

        TH32CS_SNAPPROCESS = 0x00000002
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

        class PROCESSENTRY32(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
                ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long),
                ("dwFlags", wintypes.DWORD),
                ("szExeFile", ctypes.c_char * 260),
            ]

        class FILETIME(ctypes.Structure):
            _fields_ = [("dwLowDateTime", wintypes.DWORD),
                        ("dwHighDateTime", wintypes.DWORD)]

        k32 = ctypes.windll.kernel32

        # 1. walk the process list looking for Cardinal.exe
        snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if snap in (0, -1):
            return None
        pid = None
        try:
            e = PROCESSENTRY32()
            e.dwSize = ctypes.sizeof(PROCESSENTRY32)
            ok = k32.Process32First(snap, ctypes.byref(e))
            while ok:
                if e.szExeFile.lower() == b"cardinal.exe":
                    pid = e.th32ProcessID
                    break
                ok = k32.Process32Next(snap, ctypes.byref(e))
        finally:
            k32.CloseHandle(snap)
        if pid is None:
            return None

        # 2. ask for that process' creation time
        h = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h:
            return None
        try:
            creation, exit_, kernel, user = FILETIME(), FILETIME(), FILETIME(), FILETIME()
            ok = k32.GetProcessTimes(h, ctypes.byref(creation), ctypes.byref(exit_),
                                     ctypes.byref(kernel), ctypes.byref(user))
            if not ok:
                return None
        finally:
            k32.CloseHandle(h)

        # FILETIME = 100-ns ticks since 1601-01-01 UTC -> epoch seconds
        ticks = (creation.dwHighDateTime << 32) | creation.dwLowDateTime
        return ticks / 1e7 - 11644473600.0
    except Exception:
        return None


def live_patch_path():
    """Find Cardinal's live autosave file; return (newest_path, temp_base).

    Cardinal makes a folder like `Cardinal.0001` (or `Cardinal.0001/autosave`).
    We glob for `Cardinal*/patch.json` (and one nested variant) and pick the
    most recently modified. Returns (None, base) if nothing is found.

    NOTE: "most recently modified" is a heuristic, and it can pick the wrong
    slot — a fresh Cardinal that has not been written to yet leaves the newest
    file belonging to the previous session. Callers should check staleness.
    """
    import glob
    base = os.environ.get("TEMP") or os.path.join(
        os.path.expanduser("~"), "AppData", "Local", "Temp")
    cands = []
    for pat in ("Cardinal*/patch.json", "Cardinal*/*/patch.json"):
        cands += glob.glob(os.path.join(base, pat))
    if not cands:
        return None, base
    # Newest first — in case several Cardinal instances left stale autosaves.
    cands.sort(key=os.path.getmtime, reverse=True)
    return cands[0], base


def read_live():
    """Read the patch Cardinal is currently running, with named params filled in.

    Cardinal rewrites this file on structural events; reading it mid-write can
    yield a half-written JSON, so we retry a few times with a short sleep.

    The result carries `stale` / `age_seconds` / `note`. Read those before
    trusting the payload: the autosave is only flushed on /load or a GUI save,
    so (a) a freshly launched Cardinal may leave a stale file from a previous
    session behind, and (b) parameter tweaks made through OSC are never
    reflected here at all.
    """
    path, base = live_patch_path()
    if not path:
        return {"error": "no Cardinal live autosave found; Cardinal may not be running.",
                "searched_in": base}
    last_err = None
    for _ in range(3):
        try:
            d = patchio.read_patch(path)
            break
        except Exception as e:          # file being written right now
            last_err = e
            time.sleep(0.15)
    else:
        return {"error": f"live autosave unreadable (Cardinal writing?): {last_err}",
                "path": path}

    # --- freshness check -------------------------------------------------
    # The autosave is only flushed on structural events (see the section note
    # above). If the file predates the running Cardinal process, it describes an
    # earlier session and must not be presented as the current state.
    mtime = os.path.getmtime(path)
    started = cardinal_proc_start()
    stale = bool(started and mtime + 1.0 < started)
    if stale:
        stale_note = ("autosave PREDATES the running Cardinal process (file %s vs "
                      "process start %s) — treat this as LAST KNOWN state, not what "
                      "is on screen. Cardinal only flushes the autosave on /load or "
                      "a GUI save; /param tweaks never appear here. Verify params "
                      "with a screenshot."
                      % (time.strftime("%H:%M:%S", time.localtime(mtime)),
                         time.strftime("%H:%M:%S", time.localtime(started))))
    else:
        stale_note = ("autosave is not older than the running process, so the "
                      "module/cable structure should match the GUI. Caveat: /param "
                      "tweaks are NOT written to the autosave — verify those with "
                      "a screenshot.")

    import paramlib as pl
    mods = []
    for m in d.get("modules", []):
        entry = {"id": m["id"], "plugin": m["plugin"], "model": m["model"],
                 "params": [{"id": q.get("id"), "value": q.get("value")}
                            for q in (m.get("params") or [])]}
        # Enrich each param with its human name from the param dictionary.
        en = pl.lookup(m["plugin"], m["model"])
        named = []
        for q in (m.get("params") or []):
            nm = (en or {}).get("params", {}).get(str(q.get("id")), {}).get("name")
            if nm:
                named.append({"id": q["id"], "name": nm, "value": q.get("value")})
        entry["named_params"] = named
        mods.append(entry)
    return {"live": True, "file": path,
            "mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime)),
            "age_seconds": int(time.time() - mtime),
            "stale": stale,
            "note": stale_note,
            "modules": mods, "cables": len(d.get("cables", []))}


def save_live(name, overwrite=True):
    """Persist Cardinal's current in-memory state to a real .vcv file.

    Anything the user tweaks in the GUI lives only in Cardinal's process memory
    until they save. If they close without saving, it's gone — call this to keep it.

    CAUTION: this reads the autosave file, which is NOT refreshed on /param
    changes. The saved .vcv therefore reflects the last structural event (a
    /load or a GUI save), not necessarily the knob positions visible right now.
    Use the GUI's own Save, or re-load the patch, if you need those captured.
    Returns a `stale` flag so callers can tell.
    """
    path, base = live_patch_path()
    if not path:
        return {"error": "no Cardinal live autosave found; Cardinal may not be running.",
                "searched_in": base}
    mtime = os.path.getmtime(path)
    started = cardinal_proc_start()
    stale = bool(started and mtime + 1.0 < started)
    d = patchio.read_patch(path)
    # Keep only the fields that form a valid patch; drop runtime-only keys.
    keep = {k: d[k] for k in ("version", "zoom", "modules", "cables") if k in d}
    if "path" in d:
        keep["path"] = d["path"]
    fn = name if name.lower().endswith(".vcv") else name + ".vcv"
    out = os.path.join(PATCH_DIR, fn)
    if os.path.exists(out) and not overwrite:
        return {"error": f"{fn} already exists (overwrite=false)", "path": out}
    os.makedirs(PATCH_DIR, exist_ok=True)
    patchio.write_patch(out, keep)
    return {"ok": True, "saved": out, "modules": len(keep.get("modules", [])),
            "cables": len(keep.get("cables", [])), "bytes": os.path.getsize(out),
            "source_mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime)),
            "stale": stale}


# ================================================================ Screenshot

def _screenshot_target(reply):
    """Extract the PNG path from a `/screenshot` reply.

    reply = ["screenshot", "<absolute path>", "ok"]  (E1+ three-segment)
          = ["screenshot", "<absolute path>"]        (pre-E1 two-segment)

    The path is ALWAYS reply[1]; the optional status is reply[2]. (A 2026-10-22
    bug took reply[-1] here and read the "ok" status as the path — this is the
    extracted, regression-tested form.)

    Returns (target_path, status) or (None, None) when the reply is malformed
    or the capture itself failed.
    """
    if not reply or len(reply) < 2 or reply[0] != "screenshot":
        return None, None
    target = reply[1]
    status = reply[2] if len(reply) > 2 else "ok"
    if target == "fail" or not target:
        return None, None
    return target, status


def _wine_candidates(win_path):
    """Map a Windows path that Cardinal reported to paths we can actually open.

    Cardinal always reports a Windows-style path (C:/Users/...). Normally the
    MCP server runs on the same machine and can open it directly. But when
    Cardinal lives in WSL (cross-build smoke tests) the same path exists under
    the WINE prefix instead, and MCP on Windows cannot see it. So we offer both
    spellings and let the caller pick the one that exists.
    """
    cands = [win_path]
    p = win_path.replace("\\", "/")
    if len(p) > 2 and p[1] == ":":
        rest = p[2:].lstrip("/")
        # WINE prefixes, most common first.
        for prefix in (os.path.expanduser("~/.wine/drive_c"),
                       os.path.expanduser("~/.wine/dosdevices/c")):
            cands.append(os.path.join(prefix, rest))
        # WSL can also reach the Windows side: /mnt/c/...
        cands.append("/mnt/" + p[0].lower() + "/" + rest)
        # Windows reaching INTO WSL: \\wsl$\<distro>\... (cross-build tests
        # where Cardinal runs in WSL but the MCP server runs on Windows).
        for distro in ("Ubuntu-26.04", "Ubuntu", "Ubuntu-24.04", "Debian"):
            cands.append(r"\\wsl$\%s\home\lijia\.wine\drive_c\%s"
                         % (distro, rest.replace("/", "\\")))
    return cands


def screenshot(save_to=None, timeout=8.0):
    """Capture the running Cardinal's window as a PNG.

    How it works: OSC `/screenshot` (no args) makes Cardinal render one extra
    frame and write a FULL-SIZE PNG into its own temp dir, then reply with
    the absolute path. The write is ASYNC (the render happens a few frames
    later), so the reply carries the *destination* — we poll until the file
    actually appears.

    Why a file and not base64 over OSC: a full-size PNG is megabytes, which
    would have to be chunked across many OSC packets (and liblo cannot carry
    string args reliably — see the js-run endpoint). A file sidesteps both.

    The file lands in Cardinal's temp dir (`%TEMP%\\Cardinal.XXXX\\`), which
    disappears when Cardinal exits. Pass `save_to` to keep a copy somewhere
    stable.

    NOTE: the capture reads the GL front buffer. Under software rendering
    (WINE/llvmpipe) that read comes back empty and the PNG is all black —
    on a real GPU it is fine. If you get an all-black PNG, check the renderer
    before assuming the patch is wrong.
    """
    res = link().ask("/screenshot", [], timeout=timeout, reply_tag="screenshot")
    if res is None:
        return {"ok": False,
                "note": "sent but no reply (Cardinal OSC off? wrong port? "
                        "is this a build with the /screenshot endpoint?)"}
    reply = [str(x) for x in res]
    target, _status = _screenshot_target(reply)
    if target is None:
        return {"ok": False, "reply": reply,
                "note": "Cardinal could not capture (or malformed reply)"}

    cands = _wine_candidates(target)

    # The render is async: poll until the file lands and stops growing.
    deadline = time.time() + timeout
    last_size = -1
    found = None
    while time.time() < deadline:
        for c in cands:
            if os.path.isfile(c):
                size = os.path.getsize(c)
                if size > 0 and size == last_size:
                    found = c
                    break
                last_size = size
        if found:
            break
        time.sleep(0.15)

    if not found:
        return {"ok": False, "reply": reply, "path": target,
                "tried": cands,
                "note": f"no PNG at the reported path within {timeout}s "
                        f"(Cardinal not rendering? OSC-driven load needed?)"}

    out = {"ok": True, "path": found, "bytes": os.path.getsize(found),
           "reply": reply}
    if found != target:
        out["reported_path"] = target

    # PNG header sanity: 8-byte magic + IHDR width/height.
    try:
        with open(found, "rb") as f:
            head = f.read(24)
        if head[:8] == b"\x89PNG\r\n\x1a\n":
            out["format"] = "png"
            out["width"] = struct.unpack(">I", head[16:20])[0]
            out["height"] = struct.unpack(">I", head[20:24])[0]
        else:
            out["format"] = "unknown"
    except OSError as e:
        out["header_error"] = str(e)

    if save_to:
        dst = os.path.abspath(save_to)
        if not dst.lower().endswith(".png"):
            dst += ".png"
        try:
            os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
            shutil.copyfile(found, dst)
            out["saved_to"] = dst
        except OSError as e:
            out["copy_error"] = str(e)
    return out


# ================================================================ Param queries

def module_params(patch=None, module=None, module_id=None, keyword=None):
    """Look up parameters: a module's param table / search by keyword / translate.

    Three independent modes (whichever inputs are given):
      1. patch given  -> query modules INSIDE that patch (uses their real ids/values)
      2. keyword given -> fuzzy-search the param dictionary by name
      3. module given  -> full param table for that module from the dictionary
    """
    import paramlib as pl

    # Case 1: scope is a specific patch file.
    if patch:
        p = resolve(patch)
        if not os.path.exists(p):
            return {"error": f"patch not found: {p}"}
        d = patchio.read_patch(p)
        targets = d.get("modules", [])
        if module_id is not None:
            selected, err = contracts.select_target(targets, targets, module, module_id)
            if err:
                return err
            targets = [selected]
        elif module:
            targets, _ = _find_module_instances(d, module)
        if not targets:
            return {"error": "no matching module in patch",
                    "available": [{"id": m["id"], "model": m["model"]}
                                  for m in d.get("modules", [])]}
        out = []
        for m in targets:
            en = pl.lookup(m["plugin"], m["model"])
            rows = []
            for q in (m.get("params") or []):
                info = (en or {}).get("params", {}).get(str(q.get("id")), {})
                rows.append({"id": q["id"], "value": q.get("value"),
                             "name": info.get("name"), "kind": info.get("kind"),
                             "min": info.get("min"), "max": info.get("max"),
                             "unit": info.get("unit")})
            out.append({"module_id": m["id"], "plugin": m["plugin"],
                        "model": m["model"], "params": rows})
        return {"patch": os.path.basename(p), "modules": out}

    # Case 2: keyword search across the whole dictionary.
    if keyword:
        return {"keyword": keyword, "hits": pl.search(keyword)}

    # Case 3: a single module's full dictionary entry.
    if module:
        e = _lookup_module_entry(module)
        if not e:
            return {"error": f"{module} not in param dictionary",
                    "known": sorted(pl.load().keys())}
        return {"module": e["model"], "source": e["source"], "params": e["params"]}

    return {"known_modules": sorted(pl.load().keys()),
            "hint": "pass patch+module to query real params, or keyword to search names"}


def find_param(module, human):
    """Translate plain language into a parameter number for a module.

    Example: ('VCF', 'brighter cutoff') -> param 0 (Cutoff frequency).
    See paramlib.resolve_name for the Chinese->English keyword expansion.
    """
    import paramlib as pl
    e = _lookup_module_entry(module)
    if not e:
        return {"error": f"{module} not in param dictionary (unknown, invalid or ambiguous)",
                "known": sorted(pl.load().keys())}
    cands = pl.resolve_name(e["plugin"], e["model"], human)
    return {"module": e["model"], "query": human,
            "candidates": [{"param_id": pid, "name": nm, "score": sc}
                           for sc, pid, nm in cands]}


# ================================================================ Music knowledge base

def music(what="styles", arg=None, key=None):
    """Query drum patterns / chord progressions / tone recipes.

    `what` selects the category:
      styles    list all drum-pattern styles
      drums     one pattern's 16-step grid
      chords    list or transpose a chord progression (needs `key`)
      recipes   list all tone recipes
      recipe    one recipe's settings
      suggest   free-text -> candidate recipes/drums/chords
    """
    import musiclib as ml
    if what == "styles":
        return {k: {"name": v["name"], "bpm": v["bpm"], "mood": v["mood"],
                    "desc": v["desc"]} for k, v in ml.DRUM_PATTERNS.items()}
    if what == "drums":
        if not arg:
            return {"error": "specify a style name, e.g. lofi_hiphop"}
        p = ml.drum_pattern(arg)
        return p or {"error": f"no such pattern: {arg}",
                     "available": list(ml.DRUM_PATTERNS)}
    if what == "chords":
        if not arg:
            return {k: {"name": v["name"], "degrees": v["degrees"], "mood": v["mood"]}
                    for k, v in ml.PROGRESSIONS.items()}
        pr = ml.progression(arg, key or "C major")
        if not pr:
            return {"error": f"no such progression: {arg}",
                    "available": list(ml.PROGRESSIONS)}
        return {"name": pr["name"], "key": pr["key"], "desc": pr["desc"],
                "chords": [{"degree": c["degree"], "quality": c["quality"] or "major",
                            "notes": c["notes"], "root_pc": c["root"]}
                           for c in pr["chords"]]}
    if what == "recipes":
        return {k: {"name": v["name"], "mood": v["mood"], "target": v["target"],
                    "desc": v["desc"]} for k, v in ml.RECIPES.items()}
    if what == "recipe":
        r = ml.recipe(arg) if arg else None
        return r or {"error": f"no such recipe: {arg}",
                     "available": list(ml.RECIPES)}
    if what == "suggest":
        return {"query": arg,
                "hits": [{"kind": kind, "key": k, "name": nm, "mood": mood}
                         for _sc, kind, k, nm, mood in ml.suggest(arg or "")]}
    return {"error": f"unknown query type: {what}",
            "valid": ["styles", "drums", "chords", "recipes", "recipe", "suggest"]}


def apply_recipe(patch, recipe_name, load_after=False, weight=1.0):
    """Write a tone recipe into a patch; optionally load it into Cardinal after."""
    import musiclib as ml
    error = contracts.input_error(bools=dict(load_after=load_after), numbers=dict(weight=weight))
    if error:
        return error
    p = resolve(patch)
    if not os.path.exists(p):
        return {"error": f"patch not found: {p}"}
    try:
        res = ml.apply_recipe(p, recipe_name, weight=weight)
    except Exception as exc:
        # musiclib delegates its sole file mutation to atomic patchio.write_patch.
        return {"ok": False, "written": False, "written_path": None,
                "load_requested": bool(load_after), "loaded": False,
                "load_succeeded": None, "verified": False, "stage": "write_failed",
                "error": f"Recipe preparation/write failed: {exc}"}
    if res.get("error"):
        return res
    if res.get("written"):
        return contracts.after_write(res, p, load_after, load_patch)
    res.update(ok=False, written_path=None, load_requested=bool(load_after),
               loaded=False, load_succeeded=None, verified=False, stage="not_written")
    return res


# ================================================================ MCP protocol

# The tool catalog the MCP client sees. Each entry has a JSON-Schema
# `inputSchema`. Descriptions here are what the AI reads to decide which tool to
# call, so they name the practical "when to use this" along with the gotchas
# (e.g. moduleId is int64, some param slots are reserved/empty).
TOOLS = [
    {
        "name": "cardinal_ping",
        "description": "Test OSC connectivity to Cardinal standalone. "
                       "Cardinal must first manually enable Engine -> Enable OSC remote control.",
        "inputSchema": {"type": "object", "properties": {},
                        "additionalProperties": False},
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "cardinal_list_patches",
        "description": "List all .vcv patch files in the patch directory.",
        "inputSchema": {"type": "object", "properties": {},
                        "additionalProperties": False},
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "cardinal_patch_info",
        "description": "Inspect a patch's module list, including each module's moduleId and "
                       "param ids — call this BEFORE setting a param to learn the ids.",
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "file name or full path"}},
            "required": ["name"],
            "additionalProperties": False,
        },
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "cardinal_load_patch",
        "description": "Load a .vcv patch into the running Cardinal (includes zoom + gridOffset). "
                       "Replaces whatever rack is currently open — unsaved GUI edits are lost.",
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "file name or full path"}},
            "required": ["name"],
            "additionalProperties": False,
        },
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": False, "destructiveHint": True,
                        "idempotentHint": False, "openWorldHint": False},
    },
    {
        "name": "cardinal_set_param",
        "description": "Turn any module's knob. Get moduleId from cardinal_patch_info "
                       "(note: it is int64).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "module_id": {"type": "integer", "minimum": 0, "description": "module id"},
                "param_id": {"type": "integer", "minimum": 0, "description": "param slot, 0-based"},
                "value": {"type": "number", "description": "target value, usually 0.0 - 1.0"},
            },
            "required": ["module_id", "param_id", "value"],
            "additionalProperties": False,
        },
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": False, "destructiveHint": True,
                        "idempotentHint": True, "openWorldHint": False},
    },
    {
        "name": "cardinal_set_param_by_name",
        "description": "Set one knob by PARAM NAME on a patch file (then optionally "
                       "hot-reload). 'module' selects by model, 'instance' picks which one "
                       "when the rack has several of the same model (always reported). "
        "🔴 REFUSES reserved/removed slots (e.g. VCF param 1, Clocked param 14): "
                       "writing them succeeds silently but does NOTHING — that silence is "
                       "the trap this tool exists to close.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "patch": {"type": "string", "description": "patch file name"},
                "module": {"type": "string", "description": "model name, e.g. VCF (or plugin/model)"},
                "param": {"type": "string", "description": "param name like 'Cutoff frequency', or a number"},
                "value": {"type": "number"},
                "instance": {"type": "integer", "minimum": 0,
                             "description": "which of several same-model modules (0-based, default 0)"},
                "load_after": {"type": "boolean", "default": False},
            },
            "required": ["patch", "module", "param", "value"],
            "additionalProperties": False,
        },
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": False, "destructiveHint": True,
                        "idempotentHint": True, "openWorldHint": False},
    },
    {
        "name": "cardinal_set_params_batch",
        "description": "Set MANY knobs on a patch in one call (by param name), with a "
                       "per-item receipt. Use this instead of calling "
                       "cardinal_set_param_by_name in a loop: one file read, one backup, "
                       "one write. Each item is independent — one failure does not abort "
                       "the others, and every item gets its own ok/error receipt. "
                       "🔴 Refuses reserved/removed slots per item (writing them succeeds "
                       "silently but does NOTHING). If the rack has several modules of the "
                       "same model, pass 'instance' (0-based) — the count is always reported. "
                       "If EVERY item fails, nothing is written.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "patch": {"type": "string", "description": "patch file name"},
                "sets": {
                    "type": "array", "minItems": 1,
                    "description": "list of knob changes, applied in order",
                    "items": {
                        "type": "object",
                        "properties": {
                            "module": {"type": "string",
                                       "description": "model name, e.g. VCO (or plugin/model)"},
                            "param": {"type": "string",
                                      "description": "param name like 'Cutoff frequency', or a number"},
                            "value": {"type": "number"},
                            "instance": {"type": "integer", "minimum": 0,
                                         "description": "which of several same-model modules (0-based, default 0)"},
                        },
                        "required": ["module", "param", "value"],
                        "additionalProperties": False,
                    },
                },
                "load_after": {"type": "boolean", "default": False},
            },
            "required": ["patch", "sets"],
            "additionalProperties": False,
        },
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": False, "destructiveHint": True,
                        "idempotentHint": True, "openWorldHint": False},
    },
    {
        "name": "cardinal_set_host_param",
        "description": "Set one of Cardinal's 24 host parameters (port 0-23), used with the "
                       "Host Parameters / Host Parameters Map modules.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "port": {"type": "integer", "minimum": 0, "maximum": 23, "description": "0-23"},
                "value": {"type": "number", "minimum": 0, "maximum": 1, "description": "0.0 - 1.0"},
            },
            "required": ["port", "value"],
            "additionalProperties": False,
        },
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": False, "destructiveHint": True,
                        "idempotentHint": True, "openWorldHint": False},
    },
    {
        "name": "cardinal_read_live",
        "description": "Read the patch Cardinal is currently running (including each module's "
                       "named params). OSC can only write, not read — this path uses Cardinal's "
                       "live autosave file, so it sees the GUI without disturbing the user. "
                       "The autosave is only flushed on /load or a GUI save, so check the "
                       "returned `stale` flag; and note that /param tweaks never appear here "
                       "(verify those with a screenshot).",
        "inputSchema": {"type": "object", "properties": {},
                        "additionalProperties": False},
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "cardinal_save_live",
        "description": "Persist Cardinal's current state to a .vcv file. GUI tweaks only live in "
                       "the process and vanish on close — use this to keep them. Reads the "
                       "autosave file, so it returns a `stale` flag too.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "file name, e.g. my_patch.vcv"},
                "overwrite": {"type": "boolean", "description": "default true"},
            },
            "required": ["name"],
            "additionalProperties": False,
        },
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": False, "destructiveHint": True,
                        "idempotentHint": False, "openWorldHint": False},
    },
    {
        "name": "cardinal_screenshot",
        "description": "Capture the running Cardinal's window as a PNG. This is the only way "
                       "to SEE the rack: OSC parameter writes are never reflected in the "
                       "autosave file, so read_live cannot confirm a knob move — this can. "
                       "The capture is async (Cardinal renders an extra frame) and lands in "
                       "Cardinal's temp dir, which is deleted when Cardinal exits — pass "
                       "`save_to` to keep a copy. Returns the PNG path plus width/height. "
                       "If the PNG comes back all black, the GL front-buffer read failed "
                       "(happens under software rendering); the patch itself may be fine.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "save_to": {"type": "string",
                            "description": "optional path to copy the PNG to (e.g. D:/Cardinal/tmp/shot.png)"},
                "timeout": {"type": "number", "default": 8.0,
                            "description": "seconds to wait for the PNG to be written"},
            },
            "additionalProperties": False,
        },
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "cardinal_module_params",
        "description": "Look up param name -> number. Three uses: 1) patch+module to see a "
                       "module's real params inside a patch (with current values + names); "
                       "2) module to see the full dictionary entry; 3) keyword to fuzzy-search "
                       "by name. Always check before turning a knob — some slots are reserved.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "patch": {"type": "string", "description": "patch file name (optional)"},
                "module": {"type": "string", "description": "module name like VCF or Clocked"},
                "module_id": {"type": "integer", "minimum": 0,
                              "description": "or use module id directly"},
                "keyword": {"type": "string", "description": "search by param name, e.g. cutoff"},
            },
            "additionalProperties": False,
        },
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "cardinal_find_param",
        "description": "Translate plain language into a param number. e.g. module=VCF, "
                       "human='brighter cutoff' returns Candidates: param 0 = Cutoff frequency.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "module": {"type": "string", "description": "module name, e.g. VCF"},
                "human": {"type": "string", "description": "intent, e.g. 'brighter' / 'more reverb'"},
            },
            "required": ["module", "human"],
            "additionalProperties": False,
        },
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "cardinal_music",
        "description": "Music knowledge base: drum patterns (16-step grid), chord progressions "
                       "(transposable), tone recipes. `what` in styles/drums/chords/recipes/"
                       "recipe/suggest.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "what": {"type": "string",
                         "enum": ["styles", "drums", "chords", "recipes", "recipe", "suggest"]},
                "arg": {"type": "string", "description": "style/progression/recipe name or query"},
                "key": {"type": "string", "description": "key, e.g. 'D minor', 'F major'"},
            },
            "required": ["what"],
            "additionalProperties": False,
        },
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "cardinal_apply_recipe",
        "description": "Write a tone recipe into a patch file (optionally load it into Cardinal "
                       "after). Recipe param names are translated to numbers; anything unfound is "
                       "reported explicitly. ALL same-model modules in the rack are updated "
                       "(e.g. both VCA-1s), and a `weight` 0..1 blends between each knob's "
                       "current value and the recipe target (0.5 = halfway; out-of-range "
                       "values are clamped and the effective value reported). NOT idempotent: "
                       "re-applying the same weight<1 recipe blends AGAIN from the new current "
                       "values.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "patch": {"type": "string", "description": "patch file name"},
                "recipe": {"type": "string", "description": "recipe name, e.g. warm_pad"},
                "weight": {"type": "number",
                           "description": "Finite weight clamped to 0..1: 1 = fully recipe "
                           "(default), 0.5 = halfway between current and recipe"},
                "load_after": {"type": "boolean",
                               "description": "load immediately after writing (replaces current rack)"},
            },
            "required": ["patch", "recipe"],
            "additionalProperties": False,
        },
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": False, "destructiveHint": True,
                        "idempotentHint": False, "openWorldHint": False},
    },
    # ---------------- OSC read probes (need the patched Cardinal build) -------
    {
        "name": "cardinal_audit",
        "description": "Run ALL five pre-load audits on a patch in one call: ports "
                       "(socket index overrun = crash on load) / values (dimensions and numeric "
                       "guardrails = silent or crash) / flow (signal-flow reachability = mute) / "
                       "chain (pitch/gate wiring + dead-end modules) / validate (structure: "
                       "duplicate ids, dangling cables, unknown modules). verdict FAIL = do not "
                       "load into Cardinal; WARN = soft warnings only; PASS = clean. "
        "⚠️ Static audits can never prove a rack actually sounds — pair with "
                       "cardinal_scan_signal on the running rack.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "patch file name or full path"},
                "checks": {"type": "array", "items": {"type": "string",
                           "enum": ["ports", "values", "flow", "chain", "validate"]},
                           "description": "default: all five"},
            },
            "required": ["name"],
            "additionalProperties": False,
        },
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "cardinal_deploy",
        "description": "Audit a .vcv and optionally replace the running rack. "
                       "load_after=false performs audit only, with no OSC load or diff. "
                       "Loading loses unsaved rack edits and needs user approval. "
                       "Warnings, failed/missing structure or parameter evidence, skipped "
                       "parameters and unknown/stale autosave freshness cannot pass. "
                       "Verification is limited to autosave_structure_and_params, NOT "
                       "current memory, sequencer data or user listening (live_verified=false).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "patch file name or full path"},
                "load_after": {"type": "boolean", "default": True,
                               "description": "load into running Cardinal after auditing"},
            },
            "required": ["name"],
            "additionalProperties": False,
        },
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": False, "destructiveHint": True,
                        "idempotentHint": False, "openWorldHint": False},
    },
    {
        "name": "cardinal_diff",
        "description": "Compare the on-disk .vcv against what Cardinal is actually running. "
                       "Reports TWO verdicts separately, because they differ in trustworthiness: "
                       "`match` = structure (module set + every cable endpoint; "
                       "missing_modules = present in the file but silently dropped by the "
                       "engine) and `params_match` = knob values (param_mismatches lists every "
                       "knob whose live value differs from the file, with file_value / "
                       "live_value / delta). The result carries a `stale` flag because the "
                       "autosave only flushes on /load or a GUI save — check it before "
                       "trusting either verdict. Set check_params=false to skip the knob "
                       "comparison.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "patch file name or path"},
                "check_params": {"type": "boolean", "default": True,
                                 "description": "also compare knob values (default true)"},
            },
            "required": ["name"],
            "additionalProperties": False,
        },
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "cardinal_port_semantics",
        "description": "Look up a module's PORT semantics: which socket is pitch / gate / "
                       "clock / audio / cv, per id. Data comes from the module's real source "
                       "code (configInput/configOutput labels + InputIds/OutputIds enums) — "
                       "Bogaudio and Fundamental modules with the SAME NAME have completely "
                       "different sockets, and this table knows the difference. Use BEFORE "
                       "wiring: route cables by this table, not by guessing.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "module": {"type": "string", "description": "module name, e.g. 'VCF' or 'Bogaudio/Bogaudio-VCF'"},
                "patch": {"type": "string", "description": "optional: query as used inside this patch"},
            },
            "additionalProperties": False,
        },
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "cardinal_live_modules",
        "description": "★ READ the RUNNING Cardinal: list every module the engine actually "
                       "instantiated (module_id + plugin + model). This is ground truth — it "
                       "catches modules that were silently dropped from the patch. "
                       "Use this instead of guessing ids from the file. "
                       "Returns error=probe_not_supported on an unpatched build.",
        "inputSchema": {"type": "object", "properties": {},
                        "additionalProperties": False},
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "cardinal_modules_page",
        "description": "★ READ one PAGE of running modules (offset + limit) instead of the "
                       "whole list at once — the counterpart to cardinal_live_modules for a "
                       "large rack. Returns returned/total/has_more + the page's modules. "
                       "If the running Cardinal predates this endpoint it degrades to "
                       "probe_not_supported (fall back to cardinal_live_modules).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "offset": {"type": "integer", "minimum": 0, "default": 0,
                           "description": "0-based start index into the module list"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 64, "default": 32,
                          "description": "page size (server caps at 64)"},
            },
            "additionalProperties": False,
        },
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "cardinal_get_param",
        "description": "★ READ one knob's current DISPLAY value from the running Cardinal "
                       "(the physical number shown on the panel, e.g. 275 for 275 ms — not the "
                       "normalized 0.275 stored in the file). Use it to VERIFY that a "
                       "cardinal_set_param actually landed.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "module_id": {"type": "integer", "minimum": 0,
                              "description": "from cardinal_live_modules"},
                "param_id": {"type": "integer", "minimum": 0,
                             "description": "from cardinal_module_params"},
            },
            "required": ["module_id", "param_id"],
            "additionalProperties": False,
        },
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "cardinal_module_ports",
        "description": "★ READ a module's live port state: for every input/output port, whether "
                       "it is wired (channels>0) and its current voltage. Separates three cases: "
                       "not wired / wired but silent right now / signal present. "
                       "This is how you answer 'does this patch actually make sound?' "
                       "WITHOUT offline rendering.",
        "inputSchema": {
            "type": "object",
            "properties": {"module_id": {"type": "integer", "minimum": 0,
                                         "description": "from cardinal_live_modules"}},
            "required": ["module_id"],
            "additionalProperties": False,
        },
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "cardinal_scan_signal",
        "description": "★ Scan the WHOLE running rack and report which modules are emitting a "
                       "non-zero voltage right now (module_id -> peak). A module absent from the "
                       "result is producing no sound at this instant. "
                       "This is the direct answer to 'is it actually sounding?' — call it twice "
                       "a second apart to tell a steady tone from silence.",
        "inputSchema": {"type": "object", "properties": {},
                        "additionalProperties": False},
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "cardinal_get_light",
        "description": "★ READ an LED's brightness in the running rack — e.g. Clocked's RUN lamp "
                       "tells you whether the transport is actually running.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "module_id": {"type": "integer", "minimum": 0},
                "light_id": {"type": "integer", "minimum": 0},
            },
            "required": ["module_id", "light_id"],
            "additionalProperties": False,
        },
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "cardinal_module_search",
        "description": "Search the installed module library — the same data behind the human's "
                       "right-click 'Add module' browser (1407 modules / 85 brands / 104 official tags "
                       "read live from Cardinal's PluginManifests). Query in ENGLISH: matches "
                       "name, slug, official tags, description. Use this BEFORE picking modules, "
                       "never from memory. Every hit carries manualUrl so Li can judge; ports "
                       "and params are NOT here (use cardinal_module_params for those).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "English keywords, e.g. 'warm pad'"},
                "tags": {"type": "array", "items": {"type": "string"},
                         "description": "Exact official tags, e.g. ['Oscillator']"},
                "brand": {"type": "string", "description": "Brand filter, e.g. 'SurgeXTRack'"},
                "limit": {"type": "integer", "minimum": 1, "default": 20},
            },
            "additionalProperties": False,
        },
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "cardinal_module_tags",
        "description": "List all official module tags with counts (the human's Tags filter menu), "
                       "plus every brand. Use when cardinal_module_search returns nothing useful — "
                       "pick a tag from here and retry.",
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1}},
            "additionalProperties": False,
        },
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "cardinal_module_brands",
        "description": "List all module brands with module counts.",
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1}},
            "additionalProperties": False,
        },
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "cardinal_module_detail",
        "description": "Full manifest record for one module (name/description/tags/manualURL) plus "
                       "sibling modules from the same brand. Does NOT include port or param "
                       "definitions — those are not in the manifest.",
        "inputSchema": {
            "type": "object",
            "properties": {"plugin": {"type": "string"}, "model": {"type": "string"}},
            "required": ["model"],
            "additionalProperties": False,
        },
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "cardinal_topology",
        "description": "Read a rack's wiring the way Li sees it on screen: which module feeds which, "
                       "each module's role (oscillator/filter/envelope/vca/reverb/…), official tags, "
                       "and whether signal can reach HostAudio2. Answers 'what is this rack actually "
                       "doing' WITHOUT re-reading the generator code. Reads the .vcv file; after a "
                       "patched build, pair with cardinal_scan_signal for live voltage.",
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "patch name (omit .vcv)"}},
            "required": ["name"],
            "additionalProperties": False,
        },
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "cardinal_seq_read",
        "description": "Read sequencer notes the way Li sees them on the piano-roll — measures as "
                       "rows, notes by name (C5/F3), not raw MIDI numbers. Handles both sequencer "
                       "families with different rules: rcm-pianoroll (fixed grid, rests written as "
                       "pitch=0/active=false) and Starsea-MiniArranger (sparse, rests = absent, "
                       "length spans cells). Start here before editing notes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "patch": {"type": "string"},
                "module": {"type": "string", "description": "e.g. pianoroll / MiniArranger"},
                "pattern": {"type": "integer", "minimum": 0, "default": 0},
                "track": {"type": "integer", "minimum": 0, "default": 0},
            },
            "required": ["patch"],
            "additionalProperties": False,
        },
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "cardinal_songroll_read",
        "description": "Read a SongRoll section table (song arrangement: how many sections, "
                       "which pattern each channel plays in each section, how many repeats). "
                       "Returns a human summary plus the raw JSON. SongRoll = the song-level "
                       "arranger: sections advance on end-of-pattern events, so a section is "
                       "'which pattern + how many times', not a list of notes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "patch": {"type": "string"},
                "module_id": {"type": "integer", "minimum": 0, "maximum": 2**63 - 1,
                              "description": "Exact module ID; if module name is given both must match"},
                "module": {"type": "string", "description": "e.g. songroll; must match exactly one module"},
            },
            "required": ["patch"],
            "additionalProperties": False,
        },
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "cardinal_songroll_write",
        "description": "Write a whole SongRoll section table (full replacement, validated "
                       "before touching disk). Each section needs exactly 8 channels, each "
                       "channel: pattern 1..64 (1-based), repeats 1..4096 (panel limit 64), repeat_mode "
                       "0=no limit / 1=at least / 2=at most, clock_div 0=off / 1..64.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "patch": {"type": "string"},
                "module_id": {"type": "integer", "minimum": 0, "maximum": 2**63 - 1,
                              "description": "Exact module ID; if module name is given both must match"},
                "module": {"type": "string"},
                "sections": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "channels": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "pattern": {"type": "integer", "minimum": 1, "maximum": 64},
                                        "repeats": {"type": "integer", "minimum": songroll.REPEATS_MIN, "maximum": songroll.REPEATS_MAX},
                                        "repeat_mode": {"type": "integer", "minimum": 0, "maximum": 2},
                                        "clock_div": {"type": "integer", "minimum": 0, "maximum": 64},
                                    },
                                },
                            },
                        },
                    },
                },
                "load_after": {"type": "boolean", "default": False,
                               "description": "Reload the patch in Cardinal so the change takes effect (interrupts audio)"},
            },
            "required": ["patch", "sections"],
            "additionalProperties": False,
        },
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": False, "openWorldHint": False},
    },
    {
        "name": "cardinal_songroll_edit",
        "description": "Edit a SongRoll section table with one human-level operation: add / "
                       "remove / duplicate / move a section, change one channel's pattern / "
                       "repeats / repeat mode / clock division, or set the run switch. "
                       "E.g. 'play the chorus twice more' = op=set_channel, section=<chorus>, "
                       "channel=1, repeats=<n+2>.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "patch": {"type": "string"},
                "module_id": {"type": "integer", "minimum": 0, "maximum": 2**63 - 1,
                              "description": "Exact module ID; if module name is given both must match"},
                "module": {"type": "string"},
                "op": {"type": "string",
                       "enum": ["add_section", "remove_section", "duplicate_section",
                                "move_section", "set_channel", "set_running"]},
                "section": {"type": "integer", "minimum": 0, "description": "0-based section index"},
                "channel": {"type": "integer", "minimum": 1, "maximum": 8},
                "pattern": {"type": "integer", "minimum": 1, "maximum": 64},
                "repeats": {"type": "integer", "minimum": songroll.REPEATS_MIN, "maximum": songroll.REPEATS_MAX},
                "mode": {"type": "integer", "minimum": 0, "maximum": 2,
                         "description": "0=no limit 1=at least 2=at most"},
                "clock_div": {"type": "integer", "minimum": 0, "maximum": 64},
                "index": {"type": "integer", "minimum": 0, "description": "0-based section index (remove/duplicate)"},
                "after": {"type": "integer", "minimum": 0, "description": "insert after this 0-based section (add)"},
                "src": {"type": "integer", "minimum": 0},
                "dst": {"type": "integer", "minimum": 0},
                "running": {"type": "boolean"},
                "load_after": {"type": "boolean", "default": False},
            },
            "required": ["patch", "op"],
            "additionalProperties": False,
        },
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": False, "openWorldHint": False},
    },
    {
        "name": "cardinal_export_abc",
        "description": "Export sequencer notes (rcm-pianoroll or Starsea-MiniArranger) to an "
                       "editable .abc text score — the 'see and edit music as text' deliverable. "
                       "Pure text: note names + durations, renderable by EasyABC/abcjs. Writes "
                       "<patch>.abc next to the .vcv by default (overwrites a previous export).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "patch": {"type": "string"},
                "module": {"type": "string", "description": "filter by sequencer model name"},
                "pattern": {"type": "integer", "minimum": 0, "default": 0},
                "out_path": {"type": "string", "description": "optional .abc path"},
            },
            "required": ["patch"],
            "additionalProperties": False,
        },
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": False, "destructiveHint": True,
                        "idempotentHint": True, "openWorldHint": False},
    },
    {
        "name": "cardinal_samples_list",
        "description": "Browse the sample library (86+ wavs under samples/) — the AI equivalent of Li "
                       "opening a file dialog. Use BEFORE loading a sample so you pick from what "
                       "actually exists instead of guessing filenames.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "subdir": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "default": 300},
            },
            "additionalProperties": False,
        },
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "cardinal_sample_inspect",
        "description": "Show which samples each sampler slot currently holds, and flag slots whose "
                       "file no longer exists on disk (a silently dead sampler). Equivalent to "
                       "reading the slots off the panel.",
        "inputSchema": {
            "type": "object",
            "properties": {"patch": {"type": "string"}},
            "required": ["patch"],
            "additionalProperties": False,
        },
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "cardinal_sample_load",
        "description": "Load a wav into a sampler slot — the AI equivalent of right-click → "
                       "'Load sample'. Refuses missing files and out-of-range slots, backs up "
                       "first, and stores the existing canonical absolute file path without changing other "
                       "slots. Existence is not audio decoding verification. Pass load_after=true to reload.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "patch": {"type": "string"},
                "module_id": {"type": "integer", "minimum": 0, "maximum": 2**63 - 1,
                              "description": "Exact module ID; if module name is given both must match"},
                "file": {"type": "string", "description": "e.g. melody2/m_D4.wav (relative to samples/)"},
                "slot": {"type": "integer", "minimum": 1, "maximum": 16,
                         "description": "1-based; business validates actual samplerx8 (8) or sampler16p (16) slots"},
                "module": {"type": "string", "description": "disambiguates when several samplers"},
                "load_after": {"type": "boolean", "default": False},
            },
            "required": ["patch", "file", "slot"],
            "additionalProperties": False,
        },
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": False, "destructiveHint": True,
                        "idempotentHint": True, "openWorldHint": False},
    },
    {
        "name": "cardinal_sample_clear",
        "description": "Empty one sampler slot (clear the loaded sample).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "patch": {"type": "string"},
                "module_id": {"type": "integer", "minimum": 0, "maximum": 2**63 - 1,
                              "description": "Exact module ID; if module name is given both must match"},
                "slot": {"type": "integer", "minimum": 1, "maximum": 16,
                         "description": "1-based"},
                "module": {"type": "string"},
            },
            "required": ["patch", "slot"],
            "additionalProperties": False,
        },
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": False, "destructiveHint": True,
                        "idempotentHint": True, "openWorldHint": False},
    },
    {
        "name": "cardinal_seq_edit_note",
        "description": "Edit ONE sequencer note — the equivalent of clicking a cell on the piano-roll. "
                       "Change a pitch, or clear a cell to a rest. Refuses out-of-range and "
                       "wrong-length writes instead of writing corrupt data, always backs up, and "
                       "warns when a pitch change will cut a sustained note. Writes the .vcv file; "
                       "pass load_after=true to hot-reload into running Cardinal.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "patch": {"type": "string"},
                "module_id": {"type": "integer", "minimum": 0, "maximum": 2**63 - 1,
                              "description": "Exact module ID; if module name is given both must match"},
                "module": {"type": "string"},
                "measure": {"type": "integer", "minimum": 0},
                "step": {"type": "integer", "minimum": 0},
                "pitch": {"type": "integer", "minimum": -2**31, "maximum": 2**31 - 1,
                          "description": "MIDI pitch as int32. Starsea accepts 12..108 only; "
                          "rcm preserves finite out-of-MIDI pitches with an explicit warning"},
                "length": {"type": "integer", "minimum": 1, "maximum": 16,
                           "description": "Starsea only, cells"},
                "velocity": {"type": "number", "minimum": 0, "maximum": 1},
                "retrigger": {"type": "boolean", "description": "rcm only"},
                "active": {"type": "boolean", "description": "rcm only; omit to keep current"},
                "clear": {"type": "boolean", "description": "delete the note instead of editing"},
                "pattern": {"type": "integer", "minimum": 0, "default": 0},
                "track": {"type": "integer", "minimum": 0, "default": 0},
                "load_after": {"type": "boolean", "default": False},
            },
            "required": ["patch", "module", "measure", "step"],
            "additionalProperties": False,
        },
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": False, "destructiveHint": True,
                        "idempotentHint": True, "openWorldHint": False},
    },
    {
        "name": "cardinal_seq_set_running",
        "description": "Start or stop a sequencer's transport (the RUN button). Note: patches "
                       "loaded with running=false stay silent by design — Li presses play himself.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "patch": {"type": "string"},
                "module_id": {"type": "integer", "minimum": 0, "maximum": 2**63 - 1,
                              "description": "Exact module ID; if module name is given both must match"},
                "module": {"type": "string"},
                "running": {"type": "boolean"},
                "pattern": {"type": "integer", "minimum": 0, "default": 0},
                "track": {"type": "integer", "minimum": 0, "default": 0},
                "load_after": {"type": "boolean", "default": False},
            },
            "required": ["patch", "module", "running"],
            "additionalProperties": False,
        },
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": False, "destructiveHint": True,
                        "idempotentHint": True, "openWorldHint": False},
    },
    # ---------------- B 组读数（第二批注入的只读端点，2026-10-20）----------
    {
        "name": "cardinal_build_info",
        "description": "★ Build fingerprint of the RUNNING Cardinal: variant / mode "
                       "(gui or thread) / build timestamp / safeMode / the full caps list "
                       "of read endpoints this build serves. P0 diagnostic: with a process "
                       "check it separates 'OSC never started' from 'Cardinal crashed' — "
                       "from the client alone a timeout looks identical.",
        "inputSchema": {"type": "object", "properties": {},
                        "additionalProperties": False},
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "cardinal_cables",
        "description": "★ READ the running rack's wiring: every cable as "
                       "id:input(module,port):output(module,port) — the same connections a "
                       "human sees dragged on screen. Pass module_id to filter to one "
                       "module's cables. Ground truth for 'is it actually wired'.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "module_id": {"type": "integer", "minimum": 0,
                              "description": "optional: only cables touching this module"},
            },
            "additionalProperties": False,
        },
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "cardinal_cables_page",
        "description": "★ READ one PAGE of the running rack's wiring (B2, 2026-10-21): "
                       "same cable shape as cardinal_cables (id:input(module,port):"
                       "output(module,port)) but paged — a poly-16 rack's full cable list "
                       "can blow up a single datagram. offset = 0-based start, limit = page "
                       "size (server caps at 64). Overshooting offset returns empty items "
                       "but the real total; has_more tells you whether to fetch the next "
                       "page. If the running Cardinal predates this endpoint it degrades "
                       "to probe_not_supported (fall back to cardinal_cables).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "offset": {"type": "integer", "minimum": 0, "default": 0,
                           "description": "0-based start index into the cable list"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 64, "default": 32,
                          "description": "page size (server caps at 64)"},
            },
            "additionalProperties": False,
        },
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "cardinal_transport",
        "description": "★ READ the transport: playing / bar / beat / beats-per-bar / bpm / "
                       "tick / bypassed. Zero-hook — the data is already in the plugin "
                       "context. Answers 'is the sequencer transport actually running'.",
        "inputSchema": {"type": "object", "properties": {},
                        "additionalProperties": False},
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "cardinal_engine_info",
        "description": "★ READ engine facts: sample rate, buffer size, CPU load "
                       "average/max. ⚠️ CPU meters refresh only once per second — the "
                       "reply carries cpuRefreshMs so you know the data's age.",
        "inputSchema": {"type": "object", "properties": {},
                        "additionalProperties": False},
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "cardinal_plugins",
        "description": "★ Plugin facts by layer: which plugin slugs the CURRENT rack "
                       "actually uses (engine truth) + safeMode flag. Pass plugin=<slug> "
                       "to also check whether that plugin is INSTALLED at all (reads "
                       "PluginManifests — the disk layer). safeMode=true means NO plugin "
                       "loaded: the first suspect when a correct-looking slug won't load.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "plugin": {"type": "string",
                           "description": "optional slug, e.g. Bogaudio — adds the installed check"},
            },
            "additionalProperties": False,
        },
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    # ---------------- C 组：模拟人类操作（改状态，全部可 undo）---------------
    {
        "name": "cardinal_set_param_by_display",
        "description": "★ Set a knob BY ITS DISPLAYED VALUE — the way a human turns it. "
                       "set_param writes raw normalized 0..1 storage; this writes what "
                       "the panel shows (Hz, seconds, semitones) and lets the engine "
                       "convert. A knob's display domain is module-specific and often "
                       "exponential: setDisplayValue(id,2,0.8) reading back as 11.56 Hz "
                       "on a VCO is CORRECT. Verify with cardinal_get_param, not by "
                       "comparing the number to the input. Undoable.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "module_id": {"type": "integer", "description": "live module id"},
                "param": {"type": "integer", "minimum": 0, "description": "param index"},
                "value": {"type": "number", "description": "value in the knob's DISPLAY domain"},
            },
            "required": ["module_id", "param", "value"],
            "additionalProperties": False,
        },
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": False, "destructiveHint": False,
                        "idempotentHint": True, "openWorldHint": False},
    },
    {
        "name": "cardinal_cable_add",
        "description": "★ Drag a cable in the live rack: connect "
                       "input(module_id, input_port) <- output(target_module_id, "
                       "output_port). Goes through engine history so cardinal_undo "
                       "removes it. ⚠️ ONE cable per input port — a second connection "
                       "on the same input displaces the first (engine rule, not a "
                       "tool limitation).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "module_id": {"type": "integer", "description": "module owning the INPUT port"},
                "input_port": {"type": "integer", "minimum": 0, "maximum": 2147483647,
                               "description": "port index on the INPUT module"},
                "target_module_id": {"type": "integer", "description": "module owning the OUTPUT port"},
                "output_port": {"type": "integer", "minimum": 0, "maximum": 2147483647,
                                "description": "port index on the OUTPUT module"},
            },
            "required": ["module_id", "input_port", "target_module_id", "output_port"],
            "additionalProperties": False,
        },
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": False, "destructiveHint": True,
                        "idempotentHint": False, "openWorldHint": False},
    },
    {
        "name": "cardinal_cable_remove",
        "description": "★ Right-click a cable -> Disconnect, in the live rack. "
                       "Get the cable id from cardinal_cables first. Undoable.",
        "inputSchema": {
            "type": "object",
            "properties": {"cable_id": {"type": "integer",
                                  "description": "from cardinal_cables"}},
            "required": ["cable_id"],
            "additionalProperties": False,
        },
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": False, "destructiveHint": True,
                        "idempotentHint": True, "openWorldHint": False},
    },
    {
        "name": "cardinal_undo",
        "description": "★ Ctrl+Z on the running rack. Returns the name of the action "
                       "undone ('change parameter', 'add cable', 'add module', "
                       "'move module'...). Undo actions are themselves re-doable, so "
                       "check the returned name before assuming what changed.",
        "inputSchema": {"type": "object", "properties": {},
                        "additionalProperties": False},
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": False, "destructiveHint": False,
                        "idempotentHint": False, "openWorldHint": False},
    },
    {
        "name": "cardinal_redo",
        "description": "★ Ctrl+Shift+Z on the running rack. Returns the name of the "
                       "action redone.",
        "inputSchema": {"type": "object", "properties": {},
                        "additionalProperties": False},
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": False, "destructiveHint": False,
                        "idempotentHint": False, "openWorldHint": False},
    },
    {
        "name": "cardinal_module_json",
        "description": "★ Read one LIVE module's complete .vcv JSON — params, data, "
                       "slots, version, leftModuleId/rightModuleId. This is the "
                       "authoritative shape for editing a module: use it to build a "
                       "correct replacement and hand it to the JS moduleFromJson API. "
                       "⚠️ Audit the neighbours: a dangling leftModuleId/rightModuleId "
                       "is THE crash cause on load.",
        "inputSchema": {
            "type": "object",
            "properties": {"module_id": {"type": "integer", "description": "live module id"}},
            "required": ["module_id"],
            "additionalProperties": False,
        },
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": True, "destructiveHint": False,
                        "idempotentHint": True, "openWorldHint": False},
    },
    {
        "name": "cardinal_module_remove",
        "description": "★ Select a module in the live rack and press Delete — the "
                       "module AND its cables are removed. Undoable, but prefer "
                       "editing a saved .vcv copy first: this mutates what is on "
                       "screen right now.",
        "inputSchema": {
            "type": "object",
            "properties": {"module_id": {"type": "integer",
                                   "description": "live module to delete"}},
            "required": ["module_id"],
            "additionalProperties": False,
        },
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": False, "destructiveHint": True,
                        "idempotentHint": True, "openWorldHint": False},
    },
    {
        "name": "cardinal_module_move",
        "description": "★ Drag a live module to a grid position. ⚠️ UNITS: x is in "
                       "GRID CELLS, y is a ROW INDEX — the .vcv file stores pos[0] "
                       "as cell x and pos[1] as row y. Undoable. Remember the project "
                       "rule: never regenerate a layout wholesale; move only what was "
                       "asked.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "module_id": {"type": "integer", "description": "live module to drag"},
                "x": {"type": "integer", "description": "grid cell x"},
                "y": {"type": "integer", "description": "row index y"},
            },
            "required": ["module_id", "x", "y"],
            "additionalProperties": False,
        },
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": False, "destructiveHint": False,
                        "idempotentHint": True, "openWorldHint": False},
    },
    {
        "name": "cardinal_log_get",
        "description": "★ READ Cardinal's in-process log (C3, 2026-10-22): the standalone's "
                       "stderr goes nowhere, so this reads the 2000-line ring buffer that "
                       "the engine now feeds. Incremental: pass the previous reply's `next` "
                       "as from_index to get only what is new. from_index=0 starts at the "
                       "oldest available line. Answers 'what did the engine just complain "
                       "about' without a console window.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "from_index": {"type": "integer", "minimum": 0, "default": 0,
                               "description": "sequence number to start from (0 = oldest)"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 64, "default": 32,
                          "description": "page size (server caps at 64)"},
            },
            "additionalProperties": False,
        },
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "cardinal_add_module",
        "description": "★ WRITE add a module to the running rack (2026-10-22): the OSC twin "
                       "of right-click -> Add module. Give the plugin slug and model slug "
                       "(e.g. 'Bogaudio-VCO' + 'VCO-2') plus grid coordinates x/y in cells. "
                       "The module is really instantiated (not just recorded) and can be "
                       "removed again with cardinal_undo. Slugs are not guessable — list "
                       "them first with cardinal_plugins or cardinal_module_search. "
                       "🔴 plugin must be the PLUGIN slug, not the brand: cardinal_module_search "
                       "returns BOTH a 'plugin' and a 'brand' field and they can differ "
                       "(e.g. Fundamental has plugin=Fundamental but brand=VCV) — feed "
                       "add_module the 'plugin' value, the 'brand' value will E_NO_MODEL.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "plugin": {"type": "string", "description": "plugin slug (NOT brand) — "
                            "use the 'plugin' field from cardinal_module_search, e.g. 'Fundamental'"},
                "model": {"type": "string", "description": "model slug, e.g. 'VCO' or 'VCO-2'"},
                "x": {"type": "integer", "description": "grid cell column (1 cell = 15 px)"},
                "y": {"type": "integer", "description": "grid row (1 row = 380 px)"},
            },
            "required": ["plugin", "model", "x", "y"],
            "additionalProperties": False,
        },
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": False, "destructiveHint": False,
                        "idempotentHint": False, "openWorldHint": False},
    },
    {
        "name": "cardinal_add_module_named",
        "description": "★ WRITE add a module by PLAIN-LANGUAGE name (2026-10-24): "
                       "say 'VCV VCF' or 'Bogaudio VCO' instead of slugs. "
                       "Stateless two-stage: a UNIQUE match is added directly "
                       "(zero guessing); multiple matches return a numbered "
                       "candidate list — call again with pick=N to land one; "
                       "no match returns an honest miss with suggestions. "
                       "Brand words are normalized for you: the 'VCV' brand's "
                       "plugin slug is 'Fundamental', and the candidates carry "
                       "the exact plugin|model slugs cardinal_add_module needs. "
                       "Undo with cardinal_undo. Keep cardinal_add_module for "
                       "scripted exact-slug use.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "plain-language module name, "
                          "e.g. 'VCV VCF', 'Bogaudio VCO', 'Fundamental 滤波'"},
                "x": {"type": "integer", "description": "grid cell column (1 cell = 15 px)"},
                "y": {"type": "integer", "description": "grid row (1 row = 380 px)"},
                "pick": {"type": "integer", "description": "1-based index from the "
                         "candidate list (stage 2). Omit for stage 1."},
            },
            "required": ["query", "x", "y"],
            "additionalProperties": False,
        },
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": False, "destructiveHint": False,
                        "idempotentHint": False, "openWorldHint": False},
    },
    {
        "name": "cardinal_load_skipped",
        "description": "★ READ what the last load SKIPPED (C2, 2026-10-22): modules whose "
                       "plugin/model is missing, and cables that failed to connect. Upstream "
                       "Rack drops these silently (cable skips aren't even logged). Each entry "
                       "has kind ('module'/'cable'), the patch-file id, and a reason. Call it "
                       "right after cardinal_load_patch when a rack loads 'fine' but modules "
                       "or wiring are missing.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "cardinal_module_copy",
        "description": "★ WRITE duplicate a module in the running rack — the OSC twin of "
                       "the human right-click \"Duplicate\" / \"Duplicate with cables\". "
                       "Returns the NEW module id. with_cables=true (default) also clones "
                       "the cables on the source's INPUT ports (upstream fans out; a "
                       "self-patch reconnects to the clone) — it can never violate the "
                       "one-cable-per-input-port rule. ONE history entry: cardinal_undo "
                       "reverts module + cloned cables in a single step.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "module_id": {"type": "integer", "minimum": 0,
                              "description": "source module id (from cardinal_patch_info / live_modules)"},
                "with_cables": {"type": "boolean", "default": True,
                                "description": "also clone cables on the source's input ports"},
            },
            "required": ["module_id"],
            "additionalProperties": False,
        },
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": False, "destructiveHint": False,
                        "idempotentHint": False, "openWorldHint": False},
    },
    {
        "name": "cardinal_midi_out",
        "description": "★ Inject a raw MIDI message into the live rack — what a "
                       "hardware keyboard sends, without needing the keyboard. "
                       "status is the status byte (0x90 note-on, 0x80 note-off, "
                       "0xB0 CC, ...). ⚠️ If the sequencer transport is bypassed the "
                       "reply reports skipped:bypassed: the message was accepted but "
                       "NOT delivered, and we say so instead of pretending.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "port": {"type": "integer", "minimum": 0, "maximum": 15,
                         "description": "DPF MIDI channel"},
                "status": {"type": "integer", "minimum": 128, "maximum": 239,
                           "description": "status byte, e.g. 144 for 0x90"},
                "data1": {"type": "integer", "minimum": 0, "maximum": 127,
                         "description": "first data byte, e.g. note number"},
                "data2": {"type": "integer", "minimum": 0, "maximum": 127,
                          "description": "second data byte, e.g. velocity"},
                "frame": {"type": "integer", "enum": [-1], "default": -1,
                          "description": "Only -1 (send now) is supported; deferred frames are rejected"},
            },
            "required": ["port", "status", "data1"],
            "additionalProperties": False,
        },
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": False, "destructiveHint": False,
                        "idempotentHint": False, "openWorldHint": False},
    },
    {
        "name": "cardinal_js_list",
        "description": "List the JS scripts available to cardinal_js_run, with their "
                       "1-based indexes. Scripts live in Cardinal's script dir "
                       "(CARDINAL_JS_DIR, default D:/Cardinal/js) — files are "
                       "git-tracked, which suits a workflow where the rack recipes "
                       "are versioned assets rather than ad-hoc strings.",
        "inputSchema": {"type": "object", "properties": {},
                        "additionalProperties": False},
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": True, "destructiveHint": False,
                        "idempotentHint": True, "openWorldHint": False},
    },
    {
        "name": "cardinal_js_run",
        "description": "★ Run JS INSIDE the running Cardinal (the host-code-execution "
                       "capability blender/godot/UE MCPs have). Scripts support compound "
                       "operations and module JSON; use ordinary OSC tools for single actions. "
                       "API: read — cardinal.modules()/getParam(id,n)/ports(id)/"
                       "cables()/transport()/moduleJson(id); write (CARDINAL_JS_MODE=write "
                       "only) — cardinal.setDisplayValue(id,n,v)/moduleFromJson(id,json)/"
                       "addModule(slug,x,y)/cableAdd(...)/undo()/redo(). CONTRACT: the "
                       "script is wrapped in an IIFE, so RETURN your result; assigning "
                       "globalThis.result does not work. SAFETY: disabled unless "
                       "CARDINAL_JS_MODE is read/write, libc is never initialized (no "
                       "std, no require, no exec), and a 2000ms wall-clock budget "
                       "interrupts runaway scripts (replies budget-exceeded ms=N).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "index": {"type": "integer", "minimum": 1,
                          "description": "1-based script index from cardinal_js_list"},
            },
            "required": ["index"],
            "additionalProperties": False,
        },
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": False, "destructiveHint": True,
                        "idempotentHint": False, "openWorldHint": False},
    },
    {
        "name": "cardinal_actions",
        "description": "List every operation the human can perform in Cardinal's UI, and for each: "
                       "where its UI entry point lives in the source, whether it can be called "
                       "programmatically, and which MCP tool already covers it. Use this BEFORE "
                       "deciding to write a script + reload — the principle is: find the code path "
                       "the human's button triggers and call that, instead of regenerating a patch. "
                       "Filter by status: ready / partial / planned / blocked.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "status": {"type": "string",
                           "enum": ["ready", "partial", "planned", "blocked"]},
                "id": {"type": "string", "description": "single action detail, e.g. load-sample"},
                "only_ready": {"type": "boolean",
                               "description": "shortcut: what can I do right now"},
            },
            "additionalProperties": False,
        },
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
]



# Map each tool name to a lambda that calls the underlying Python function.
# Keeps the JSON-RPC dispatch table tiny and obvious.
DISPATCH = {
    "cardinal_ping": lambda a: ping(),
    "cardinal_list_patches": lambda a: list_patches(),
    "cardinal_patch_info": lambda a: patch_info(a["name"]),
    "cardinal_load_patch": lambda a: load_patch(a["name"]),
    "cardinal_set_param": lambda a: set_param(a["module_id"], a["param_id"], a["value"]),
    "cardinal_set_param_by_name": lambda a: set_param_by_name(
        a["patch"], a["module"], a["param"], a["value"],
        a.get("instance", 0), a.get("load_after", False)),
    "cardinal_set_params_batch": lambda a: set_params_by_name_batch(
        a["patch"], a["sets"], a.get("load_after", False)),
    "cardinal_set_host_param": lambda a: set_host_param(a["port"], a["value"]),
    "cardinal_read_live": lambda a: read_live(),
    "cardinal_save_live": lambda a: save_live(a["name"], a.get("overwrite", True)),
    "cardinal_screenshot": lambda a: screenshot(a.get("save_to"), a.get("timeout", 8.0)),
    "cardinal_module_params": lambda a: module_params(
        a.get("patch"), a.get("module"), a.get("module_id"), a.get("keyword")),
    "cardinal_find_param": lambda a: find_param(a["module"], a["human"]),
    "cardinal_music": lambda a: music(a.get("what", "styles"), a.get("arg"), a.get("key")),
    "cardinal_apply_recipe": lambda a: apply_recipe(
        a["patch"], a["recipe"], a.get("load_after", False), a.get("weight", 1.0)),
    "cardinal_audit": lambda a: cardinal_audit(
        a["name"], a.get("checks")),
    "cardinal_deploy": lambda a: cardinal_deploy(
        a["name"], a.get("load_after", True)),
    "cardinal_diff": lambda a: cardinal_diff(a["name"], a.get("check_params", True)),
    "cardinal_port_semantics": lambda a: cardinal_port_semantics(
        a.get("module"), a.get("patch")),
    # --- OSC read probes (patched build only; see live_modules docstring) ---
    "cardinal_live_modules": lambda a: live_modules(),
    "cardinal_modules_page": lambda a: modules_page(
        a.get("offset", 0), a.get("limit", 32)),
    "cardinal_get_param": lambda a: get_param(a["module_id"], a["param_id"]),
    "cardinal_module_ports": lambda a: module_ports(a["module_id"]),
    "cardinal_scan_signal": lambda a: scan_signal(),
    "cardinal_get_light": lambda a: get_light(a["module_id"], a["light_id"]),
    # --- module library browser (reads Cardinal's own PluginManifests) ---
    "cardinal_module_search": lambda a: modbrowser.search(
        a.get("query", ""), a.get("tags"), a.get("brand"), a.get("limit", 20)),
    "cardinal_module_tags": lambda a: modbrowser.list_tags(a.get("limit", 120)),
    "cardinal_module_brands": lambda a: modbrowser.list_brands(a.get("limit", 120)),
    "cardinal_module_detail": lambda a: modbrowser.detail(a.get("plugin", ""), a["model"]),
    "cardinal_topology": lambda a: topology.analyze(a["name"]),
    # --- sequencer notes (piano-roll equivalent) ---
    "cardinal_seq_read": lambda a: seq.read_notes(
        a["patch"], a.get("module"), a.get("pattern", 0), a.get("track", 0)),
    "cardinal_export_abc": lambda a: abc_export.export_abc(
        a["patch"], a.get("module"), a.get("pattern", 0),
        out_path=a.get("out_path")),
    "cardinal_seq_edit_note": lambda a: seq.edit_note(
        a["patch"], a["module"], a["measure"], a["step"],
        a.get("pitch"), a.get("length"), a.get("velocity"), a.get("retrigger"),
        a.get("active"), a.get("pattern", 0), a.get("track", 0),
        a.get("clear", False), True, a.get("load_after", False), module_id=a.get("module_id")),
    "cardinal_seq_set_running": lambda a: seq.set_running(
        a["patch"], a["module"], a["running"],
        a.get("pattern", 0), a.get("track", 0), a.get("load_after", False), module_id=a.get("module_id")),
    # --- song arrangement table (SongRoll sections) ---
    "cardinal_songroll_read": lambda a: songroll.read_sections(
        a["patch"], a.get("module"), module_id=a.get("module_id")),
    "cardinal_songroll_write": lambda a: songroll.write_sections(
        a["patch"], a.get("module"), a["sections"],
        True, a.get("load_after", False), module_id=a.get("module_id")),
    "cardinal_songroll_edit": lambda a: songroll.edit(
        a["patch"], a.get("module"), a["op"],
        section=a.get("section"), channel=a.get("channel"),
        pattern=a.get("pattern"), repeats=a.get("repeats"),
        mode=a.get("mode"), clock_div=a.get("clock_div"),
        index=a.get("index"), after=a.get("after"),
        src=a.get("src"), dst=a.get("dst"), running=a.get("running"),
        backup=True, load_after=a.get("load_after", False), module_id=a.get("module_id")),
    # --- sampler slots (equivalent of right-click -> Load sample) ---
    "cardinal_samples_list": lambda a: samplelib.list_samples(
        a.get("subdir", ""), a.get("limit", 300)),
    "cardinal_sample_inspect": lambda a: samplelib.inspect(a["patch"]),
    "cardinal_sample_load": lambda a: samplelib.load_sample(
        a["patch"], a["file"], a["slot"], a.get("module"),
        True, a.get("load_after", False), module_id=a.get("module_id")),
    "cardinal_sample_clear": lambda a: samplelib.clear_slot(
        a["patch"], a["slot"], a.get("module"), module_id=a.get("module_id")),
    # ---------------- B 组读数（第二批注入的只读端点，2026-10-20）----------
    "cardinal_build_info": lambda a: build_info(),
    "cardinal_cables": lambda a: cables(a.get("module_id")),
    "cardinal_cables_page": lambda a: cables_page(
        a.get("offset", 0), a.get("limit", 32)),
    "cardinal_transport": lambda a: transport(),
    "cardinal_engine_info": lambda a: engine_info(),
    "cardinal_plugins": lambda a: plugins(a.get("plugin")),
    # ---- C 组：模拟人类操作（改状态）----
    "cardinal_set_param_by_display": lambda a: set_param_by_display(
        a["module_id"], a["param"], a["value"]),
    "cardinal_cable_add": lambda a: cable_add(
        a["module_id"], a["input_port"], a["target_module_id"], a["output_port"]),
    "cardinal_cable_remove": lambda a: cable_remove(a["cable_id"]),
    "cardinal_undo": lambda a: undo(),
    "cardinal_redo": lambda a: redo(),
    "cardinal_module_json": lambda a: module_json(a["module_id"]),
    "cardinal_module_remove": lambda a: module_remove(a["module_id"]),
    "cardinal_module_move": lambda a: module_move(
        a["module_id"], a["x"], a["y"]),
    "cardinal_module_copy": lambda a: module_copy(
        a["module_id"], a.get("with_cables", True)),
    "cardinal_log_get": lambda a: log_get(
        a.get("from_index", 0), a.get("limit", 32)),
    "cardinal_load_skipped": lambda a: load_skipped(),
    "cardinal_add_module": lambda a: add_module(
        a["plugin"], a["model"], a["x"], a["y"]),
    "cardinal_add_module_named": lambda a: add_module_named(
        a["query"], a["x"], a["y"], a.get("pick")),
    "cardinal_midi_out": lambda a: midi_out(
        a["port"], a["status"], a["data1"],
        a.get("data2", 0), a.get("frame", -1)),
    # ---- QuickJS 绑定 ----
    "cardinal_js_list": lambda a: js_list(),
    "cardinal_js_run": lambda a: js_run(a["index"]),
    "cardinal_actions": lambda a: interaction_map.list_actions(
        a.get("status"),
    ) if not a.get("id") and not a.get("only_ready") else (
        interaction_map.detail(a["id"]) if a.get("id")
        else interaction_map.find_ready()),
}


def _validate_arguments(value, schema, path="arguments"):
    """Validate the JSON-Schema subset used by TOOLS, without coercion/defaults."""
    typ = schema.get("type")
    valid = {"object": isinstance(value, dict), "array": isinstance(value, list),
             "string": isinstance(value, str), "boolean": isinstance(value, bool),
             "integer": isinstance(value, int) and not isinstance(value, bool),
             "number": isinstance(value, (int, float)) and not isinstance(value, bool)}
    if typ is not None and not valid.get(typ, False):
        raise ValueError("%s must be %s" % (path, typ))
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("%s must be finite" % path)
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError("%s is not an allowed value" % path)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise ValueError("%s is below minimum" % path)
        if "maximum" in schema and value > schema["maximum"]:
            raise ValueError("%s is above maximum" % path)
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                raise ValueError("%s.%s is required" % (path, key))
        properties = schema.get("properties", {})
        for key, item in value.items():
            if key not in properties and schema.get("additionalProperties") is False:
                raise ValueError("%s.%s is not allowed" % (path, key))
            _validate_arguments(item, properties.get(key, {}), "%s.%s" % (path, key))
    elif isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            raise ValueError("%s has too few items" % path)
        for index, item in enumerate(value):
            _validate_arguments(item, schema.get("items", {}), "%s[%d]" % (path, index))


def _tool_input_error(name, arguments):
    """Use the published schema for direct Python helpers as well as MCP."""
    spec = next((tool for tool in TOOLS if tool["name"] == name), None)
    if spec is None:
        return {"ok": False, "error": "unknown tool: %s" % name}
    try:
        _validate_arguments(arguments, spec["inputSchema"])
    except ValueError as exc:
        return {"ok": False, "error": "invalid_arguments", "note": str(exc)}
    return None


def _call_tool(name, arguments):
    """Shared validated entry for MCP and CLI; direct Python writes also guard inputs."""
    spec = next((tool for tool in TOOLS if tool["name"] == name), None)
    if spec is None or name not in DISPATCH:
        raise ValueError("unknown tool: %s" % name)
    _validate_arguments(arguments, spec["inputSchema"])
    return DISPATCH[name](arguments)


def _tool_failed(data):
    """Preserve failures from the business result and requested load stage."""
    if not isinstance(data, dict):
        return False
    checks = data.get("checks")
    audit_crashed = (isinstance(checks, dict) and any(
        isinstance(checks.get(name), dict) and bool(checks[name].get("error"))
        for name in ("ports", "values", "flow", "chain", "validate")))
    return (data.get("ok") is False or bool(data.get("error")) or audit_crashed
            or (isinstance(data.get("loaded"), dict) and _tool_failed(data["loaded"])))


def handle(req):
    """Handle one JSON-RPC request and return a response dict (or None for a
    notification that needs no reply).

    Implements just enough of MCP (initialize / tools/list / tools/call / ping)
    over stdio. Every tool call is wrapped in try/except so a single tool error
    becomes an `isError` result instead of killing the server.
    """
    if not isinstance(req, dict):
        return {"jsonrpc": "2.0", "id": None,
                "error": {"code": -32600, "message": "request must be an object"}}
    method, rid = req.get("method"), req.get("id")
    params = req.get("params", {})
    if not isinstance(params, dict):
        return {"jsonrpc": "2.0", "id": rid,
                "error": {"code": -32602, "message": "params must be an object"}}

    def result(payload):
        return {"jsonrpc": "2.0", "id": rid, "result": payload}

    if method == "initialize":
        # Version negotiation (MCP spec): the server answers with the version
        # it supports; the client may counter-offer an older one it knows.
        # We implement everything through 2025-06-18 (tool annotations +
        # structured tool output). Elicitation / tasks / streamable-HTTP are
        # NOT implemented, so we never claim a newer version than that.
        client_v = str(params.get("protocolVersion") or "").strip()
        ours = "2025-06-18"
        use = ours if (not client_v or client_v > ours) else client_v
        return result({
            "protocolVersion": use,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "cardinal", "version": "0.2.0"},
        })
    if method in ("notifications/initialized", "initialized"):
        return None
    if method == "tools/list":
        return result({"tools": TOOLS})
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments", {})
        fn = DISPATCH.get(name) if isinstance(name, str) else None
        if fn is None:
            return {"jsonrpc": "2.0", "id": rid, "result": {
                "content": [{"type": "text", "text": f"unknown tool: {name}"}],
                "isError": True}}
        try:
            data = _call_tool(name, args)
            text = json.dumps(data, ensure_ascii=False, indent=2)
            payload = {"content": [{"type": "text", "text": text}], "isError": _tool_failed(data)}
            # structured tool output (MCP 2025-06-18): a machine-readable twin
            # of the text content, conforming to the tool's outputSchema.
            # Guarded by isinstance so the declared schema stays honest even if
            # a future tool returns a non-object.
            if isinstance(data, dict):
                payload["structuredContent"] = data
            return result(payload)
        except Exception as e:
            return result({"content": [{"type": "text", "text": f"execution failed: {e}"}],
                           "isError": True})
    if method == "ping":
        return result({})
    if rid is None:
        return None
    return {"jsonrpc": "2.0", "id": rid,
            "error": {"code": -32601, "message": f"unsupported method: {method}"}}


def read_message(stream):
    """Read one JSON-RPC message from a stream, supporting BOTH framing styles:

    - newline-delimited JSON (the simple case)
    - Content-Length: N header framing (some MCP clients send this)

    Returns the raw bytes of one message, or None on EOF.
    """
    line = stream.readline()
    if not line:
        return None
    if line.lstrip().startswith(b"{"):
        return line
    if line.lower().startswith(b"content-length:"):
        length = int(line.split(b":", 1)[1].strip())
        # Consume the remaining header lines (up to the blank line).
        while True:
            hdr = stream.readline()
            if hdr in (b"\r\n", b"\n", b"", None):
                break
        return stream.read(length)
    return None


def serve():
    """The main stdio loop: read a message, handle it, write the response.

    Uses the raw binary buffers (stdin.buffer / stdout.buffer) so UTF-8 and
    framing are handled correctly. One message per iteration; flush after each.
    """
    inp, out = sys.stdin.buffer, sys.stdout.buffer
    while True:
        raw = read_message(inp)
        if raw is None:
            return
        raw = raw.strip()
        if not raw:
            continue
        try:
            req = json.loads(raw)
        except Exception:
            continue
        resp = handle(req)
        if resp is None:
            continue
        out.write(json.dumps(resp, ensure_ascii=False).encode("utf-8") + b"\n")
        out.flush()


def selftest():
    """Offline-ish self check used by `python cardinal_mcp.py --selftest`.

    Prints patch list, OSC reachability, live state (if Cardinal running),
    param lookups, and a music-lib sanity check. Also verifies the OSC int64
    encoding works by building a `/param` datagram and re-parsing it.
    """
    print(f"target: {CARDINAL_IP}:{CARDINAL_PORT}   patch dir: {PATCH_DIR}")
    print("patch list:", json.dumps(list_patches(), ensure_ascii=False, indent=2))
    print("OSC ping:", json.dumps(ping(), ensure_ascii=False))

    print("\n--- live autosave ---")
    live = read_live()
    if live.get("error"):
        print("  not read:", live["error"])
    else:
        print("  {}  {} modules {} cables".format(live["file"], len(live["modules"]),
                                                  live["cables"]))
        for m in live["modules"][:4]:
            named = m.get("named_params") or []
            sample = ", ".join("{}={}".format(p["name"], p["value"]) for p in named[:3])
            print("    id={:<4} {:<28} {}".format(m["id"], m["model"], sample))

    print("\n--- param queries ---")
    r = module_params(module="VCF")
    if r.get("params"):
        for pid, p in sorted(r["params"].items(), key=lambda x: int(x[0])):
            print("    VCF param {:<3} {}".format(pid, p.get("name") or "(reserved/unused)"))
    print("  plain-language:", json.dumps(find_param("VCF", "brighter cutoff"), ensure_ascii=False))
    print("  keyword search:", json.dumps(
        module_params(keyword="mute").get("hits", [])[:3], ensure_ascii=False))

    print("\n--- music lib ---")
    import musiclib as ml
    print("  patterns:", len(ml.DRUM_PATTERNS), "progressions:", len(ml.PROGRESSIONS),
          "recipes:", len(ml.RECIPES))
    pr = ml.progression("minor_epic", "D minor")
    print("  D minor i-VI-III-VII:", [c["notes"] for c in pr["chords"]])

    # Offline check that the OSC int64 encoding round-trips.
    dgram = build_msg("/param", [("h", 1234567890123), ("i", 3), ("f", 0.5)])
    m = OscMessage(dgram)
    print("\nencode self-check:", m.address, m.params)
    print("total tools:", len(TOOLS))


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    elif "--call" in sys.argv:
        # Call a single tool directly, bypassing MCP — handy to verify a change
        # without having to restart the MCP host (WorkBuddy).
        i = sys.argv.index("--call")
        if len(sys.argv) < i + 2:
            print("usage: --call <tool> ['{\"args\": ...}']")
            sys.exit(1)
        tool = sys.argv[i + 1]
        raw = sys.argv[i + 2] if len(sys.argv) > i + 2 else "{}"
        name = tool if tool in DISPATCH else "cardinal_" + tool.lstrip("_")
        if name not in DISPATCH:
            print("unknown tool:", tool)
            print("available:", ", ".join(sorted(DISPATCH)))
            sys.exit(1)
        try:
            out = _call_tool(name, json.loads(raw))
        except Exception as e:
            out = {"error": str(e)}
        print(json.dumps(out, ensure_ascii=False, indent=2))
        sys.exit(1 if _tool_failed(out) else 0)
    elif "--tools" in sys.argv:
        for t in TOOLS:
            print("  {:<28} {}".format(t["name"], t["description"].split(".")[0]))
    else:
        serve()
