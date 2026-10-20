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
import topology  # noqa: E402  (rack wiring / role recognition)
import seq  # noqa: E402  (sequencer notes = piano-roll equivalent)
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
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("", 0))
        self.sock.settimeout(TIMEOUT)

    def send(self, address, args=()):
        # On Windows, sending to a port with nobody listening raises
        # ConnectionResetError (ICMP unreachable) instead of failing silently.
        try:
            self.sock.sendto(build_msg(address, args), (CARDINAL_IP, CARDINAL_PORT))
            return True
        except OSError as e:
            raise RuntimeError(
                f"OSC send failed ({e}). Confirm Cardinal standalone has "
                f"Engine -> Enable OSC remote control on, port {CARDINAL_PORT}.") from e

    def ask(self, address, args=(), expect="/resp", timeout=None):
        """Send one message and wait for a `/resp` reply.

        Returns the reply params list, or None on timeout / no listener.
        We first drain any stale datagrams so a leftover reply from a previous
        call cannot be mistaken for the answer to this one.
        """
        self.sock.settimeout(timeout or TIMEOUT)
        # Drain leftover datagrams (best effort).
        try:
            while True:
                self.sock.recv(65535)
        except (socket.timeout, OSError):
            pass

        self.send(address, args)
        deadline = time.time() + (timeout or TIMEOUT)
        while time.time() < deadline:
            try:
                data, _addr = self.sock.recvfrom(65535)
            except socket.timeout:
                return None
            except OSError:
                # Port not listening: Windows returns an ICMP unreachable and
                # raises ConnectionResetError here.
                return None
            try:
                msg = OscMessage(data)
            except Exception:
                continue
            if msg.address == expect:
                return msg.params
        return None


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
    res = link().ask("/load", [("b", blob)], timeout=6.0)
    if res is None:
        # Reached Cardinal? The most common cause: OSC not enabled, or wrong port.
        return {"ok": False, "sent": os.path.basename(p), **extra,
                "note": "sent but no reply (Cardinal OSC off? wrong port?)"}
    reply = [str(x) for x in res]
    # D2: Cardinal answers ["load", "ok"|"warn <text>"|"fail <text>"].
    # "warn" = loaded but with diagnostics (fromJson/unarchive warnings),
    # now surfaced here instead of only popping a GUI dialog (or vanishing).
    last = reply[-1] if reply else ""
    if last == "ok":
        ok, warnings = True, []
    elif last.startswith("warn "):
        ok, warnings = True, [last[5:].strip()]
    else:
        ok, warnings = False, [last[5:] if last.startswith("fail ") else last]
    return {"ok": ok, "warnings": warnings,
            "sent": os.path.basename(p), "reply": reply, **extra}


def set_param(module_id, param_id, value):
    """Turn one knob on one module via OSC `/param`.

    Args:
      module_id  int64 module index (from patch_info)
      param_id   int   parameter slot, 0-based
      value      float target (typically 0.0 – 1.0, but some params use other
                ranges — e.g. VCF cutoff is in Hz-ish internal units).
    """
    link().send("/param", [("h", int(module_id)), ("i", int(param_id)),
                           ("f", float(value))])
    return {"ok": True, "moduleId": int(module_id), "paramId": int(param_id),
            "value": float(value)}


# ★ 2026-10-19 批次 A1：按名字设参数。
def _find_module_instances(d, module):
    """在 patch dict 里找某型号的全部模块实例（大小写不敏感；支持 plugin/model）。

    返回 (instances, all_modules)。instances 每项是 patch 里的原 module dict。
    机架里常有 2 个同型号（2 个 VCA-1 是常态），所以返回列表而不是单个，
    由调用方用 instance 序号挑 —— 永远把「有几个、挑了哪个」报出来。
    """
    if "/" in module:
        plug_want, model_want = module.split("/", 1)
        want = plug_want.lower() + "/" + model_want.lower()
    else:
        want = module.lower()
    hits = [m for m in d.get("modules", [])
            if want in (m["plugin"] + "/" + m["model"]).lower()]
    return hits, d.get("modules", [])


def _resolve_param_id(entry, param):
    """把「参数名或数字」翻成 param_id。返回 (param_id, info, note) 或 (None, None, err)。

    - 数字       -> 直接当 id 用（调用方会再做 reserved 检查）
    - 名字       -> 先精确匹配再子串匹配；多个同名槽返回第一个并在 note 里说明
    - 匹配只认有名字的槽 —— reserved 槽 name=None，天然不会被名字命中
    """
    params = entry["params"]
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
                   f"要选别的请用数字 param。全部同名 id: {sorted(except0) if False else sorted(exact)}"
        return min(exact), params.get(str(min(exact))), note
    part = [int(pid) for pid, v in params.items()
            if want in (v.get("name") or "").lower()]
    if not exact and not [pid for pid, v in params.items() if want in (v.get("name") or "").lower()]:
        return None, None, f"找不到参数「{param}」"
    pid = min(exact or partial)
    info = params.get(str(pid))
    note = (f"没有精确同名参数，按子串匹配命中" if not exact else None)
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
    p = resolve(patch)
    if not os.path.exists(p):
        return {"error": f"patch not found: {p}"}
    d = patchio.read_patch(p)

    hits, all_mods = _find_module_instances(d, module)
    if not hits:
        return {"error": f"机架里没有「{module}」",
                "available": sorted({m["model"] for m in all_mods})}
    if not 0 <= int(instance) < len(hits):
        return {"error": f"机架里有 {len(hits)} 个 {module}，instance={instance} 越界",
                "instances": [{"instance": i, "module_id": m["id"],
                               "pos": (m.get("pos") or [None, None])[0]}
                              for i, m in enumerate(hits)]}
    mod = hits[int(instance)]

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

    bak = p + ".bak-param"
    shutil.copy2(p, bak)
    patchio.write_patch(p, d)

    out = {"ok": True, "patch": os.path.basename(p), "backup": bak,
           "module": f"{mod['plugin']}/{mod['model']}",
           "module_id": mod["id"], "param_id": pid,
           "param_name": (info or {}).get("name"), "kind": (info or {}).get("kind"),
           "value": float(value)}
    if len(hits) > 1:
        out["note_instances"] = f"机架里有 {len(hits)} 个 {mod['model']}，本次改的是 instance={instance}"
    if warnings:
        out["warnings"] = warnings
    if load_after:
        out["loaded"] = load_patch(p)
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
        except Exception as e:  # noqa: BLE001
            bad = [f"audit_ports crashed: {e}"]
        out["checks"]["ports"] = {"ok": not bad, "hard": len(bad),
                                  "violations": sorted(set(bad))}

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
        problems = _audit_validate(p)
        out["checks"]["validate"] = {"ok": not problems, "problems": problems}

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
    if not 0 <= int(port) <= 23:
        return {"error": "port must be 0-23"}
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
        hits = [m for m in d.get("modules", [])
                if not module or module.lower() in (m["plugin"] + "/" + m["model"]).lower()]
        if not hits:
            return {"error": f"patch has no module {module}"}
        mod = hits[0]
        plugin, model = mod["plugin"], mod["model"]
        entry = pl.lookup(plugin, model)
    elif module:
        if "/" in module:
            plugin, model = module.split("/", 1)
        else:
            plugin, model = None, module
        entry = pl.lookup(plugin, model)
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


def cardinal_diff(name):
    """比对磁盘上的 .vcv 与运行中 Cardinal 的结构（模块 + 接线）。

    只验结构不验参数（E8 降级）。stale=true 说明 autosave 是上一会话
    的残留，结果不可当真 —— 绝不用空数据掩盖。
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
    stale = bool(started and os.path.getmtime(live_path) + 1.0 < started)
    note = ("autosave 比进程还旧 ⇒ 上一会话残留，结果不可当真" if stale else
            "结构比对基于 live autosave；参数值不在比对范围（E8 降级）")
    if started is None:
        note += "；⚠️ 未检测到运行中的 Cardinal 进程 —— 比对对象可能是残留 autosave"
    return {
        "patch": os.path.basename(p),
        "match": not (miss_m or extra_m or miss_c or extra_c),
        "modules_file": len(mods_f), "modules_live": len(mods_l),
        "cables_file": len(cab_f), "cables_live": len(cab_l),
        "missing_modules": sorted("%s/%s(#%s)" % (pl, md, i) for i, pl, md in miss_m),
        "extra_modules": sorted("%s/%s(#%s)" % (pl, md, i) for i, pl, md in extra_m),
        "missing_cables": ["%s#%s -> %s#%s" % c for c in sorted(miss_c)],
        "extra_cables": ["%s#%s -> %s#%s" % c for c in sorted(extra_c)],
        "stale": stale,
        "note": note}


def cardinal_deploy(name, load_after=True):
    """一键部署：备份 → 五项审计（FAIL 拒发）→ /load → 结构读回比对。

    顺序即防线：崩类问题被审计拦在加载前；diff 证明「文件里的东西
    引擎真的都装上了」。参数值不在比对范围（E8 降级，编译后补全）。
    """
    p = resolve(name)
    if not os.path.exists(p):
        return {"error": "patch not found: %s" % p}
    bak = p + ".bak-deploy"
    shutil.copy2(p, bak)
    au = cardinal_audit(name)
    if au.get("verdict") == "FAIL":
        return {"ok": False, "deployed": False, "backup": bak,
                "why": "audit FAIL —— 加载即崩类问题，先修再部署", "audit": au}
    loaded = load_patch(p)
    if not isinstance(loaded, dict) or not loaded.get("ok"):
        return {"ok": False, "deployed": False, "backup": bak,
                "why": "/load failed（Cardinal 开着吗？OSC 开了吗）",
                "load_result": loaded}
    time.sleep(1.0)          # 引擎装载 + autosave 落盘需要一点时间
    diff = cardinal_diff(name)
    return {"ok": True, "deployed": os.path.basename(p), "backup": bak,
            "audit_verdict": au.get("verdict"), "diff": diff}


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
#   ⚠️ 若返回 {"error": "probe_not_supported"}，说明跑的是**未打补丁的 exe**。
#   重编译：bash tools/cross_build_cardinal.sh（先关掉 Cardinal）

PROBE_UNSUPPORTED = {
    "error": "probe_not_supported",
    "note": "This Cardinal build has no read probes. Rebuild with "
            "tools/osc_patch/inject_osc_read.py applied, or run "
            "tools/cross_build_cardinal.sh. Original Cardinal OSC can only write.",
}


def _ask(tag, address, args=()):
    """Send one probe and parse the two-string `/resp` ("tag", "payload").

    Returns None when the peer did not answer, which is how we detect an
    unpatched build (its fallback handler silently drops unknown paths).
    """
    res = link().ask(address, args, timeout=1.5)
    if res is None or len(res) < 2:
        return None
    if str(res[0]) != tag:
        return None
    return str(res[1])


def live_modules():
    """List every module currently instantiated in the RUNNING Cardinal.

    This is the ground truth of what the engine really loaded — it catches the
    class of bug where a .vcv file is fine on disk but the engine silently
    dropped a module (e.g. wrong plugin slug).
    """
    payload = _ask("modules", "/modules")
    if payload is None:
        return dict(PROBE_UNSUPPORTED)
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


def get_param(module_id, param_id):
    """Read back one knob's DISPLAY value (the physical number, not the stored one).

    Cardinal stores most knobs normalized (ADSR.Attack stores 0.275 but shows
    275 ms; Bogaudio-VCO.Frequency stores 6.0 octaves but shows 220 Hz). The
    patched build returns getDisplayValue(), i.e. the number a human can judge.
    """
    payload = _ask("param", "/param-get", [("h", int(module_id)), ("i", int(param_id))])
    if payload is None:
        return dict(PROBE_UNSUPPORTED)
    try:
        val = float(payload)
    except (TypeError, ValueError):
        return {"ok": False, "module_id": module_id, "param_id": param_id,
                "raw": payload, "note": "empty = module or param slot not found"}
    return {"ok": True, "module_id": int(module_id), "param_id": int(param_id),
            "display_value": val}


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
    payload = _ask("ports", "/ports", [("h", int(module_id))])
    if payload is None:
        return dict(PROBE_UNSUPPORTED)
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
    }


def scan_signal(threshold=1e-4):
    """Scan the whole rack and report which modules currently emit a non-zero voltage.

    The direct answer to "is anything actually sounding right now". A module whose
    every connected output sits at 0 V is producing no sound at this instant.
    """
    payload = _ask("signal", "/signal")
    if payload is None:
        return dict(PROBE_UNSUPPORTED)
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
    payload = _ask("light", "/light", [("h", int(module_id)), ("i", int(light_id))])
    if payload is None:
        return dict(PROBE_UNSUPPORTED)
    try:
        return {"ok": True, "module_id": int(module_id), "light_id": int(light_id),
                "brightness": float(payload)}
    except (TypeError, ValueError):
        return {"ok": False, "module_id": module_id, "light_id": light_id,
                "raw": payload}


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
    payload = _ask("build-info", "/build-info")
    if payload is None:
        return dict(PROBE_UNSUPPORTED)
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
    payload = _ask("cables", "/cables", args)
    if payload is None:
        return dict(PROBE_UNSUPPORTED)
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


def transport():
    """Transport state: playing / bar / beat / bpm / tick / bypassed.

    Zero-hook — CardinalPluginContext already carries all of it.
    """
    payload = _ask("transport", "/transport")
    if payload is None:
        return dict(PROBE_UNSUPPORTED)
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
    payload = _ask("engine-info", "/engine-info")
    if payload is None:
        return dict(PROBE_UNSUPPORTED)
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
    payload = _ask("plugins", "/plugins")
    if payload is None:
        return dict(PROBE_UNSUPPORTED)
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
    payload = _ask("param-set", "/param-set-by-display",
                   (("h", int(module_id)), ("i", int(param)), ("f", float(value))))
    if payload is None:
        return dict(PROBE_UNSUPPORTED)
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
    payload = _ask("cable-add", "/cable-add",
                   (("h", int(module_id)), ("i", int(input_port)),
                    ("h", int(target_module_id)), ("i", int(output_port))))
    return _hist(payload)


def cable_remove(cable_id):
    """Right-click a cable -> Disconnect."""
    payload = _ask("cable-remove", "/cable-remove", (("h", int(cable_id)),))
    return _hist(payload)


def undo():
    """Ctrl+Z on the running rack. Returns the name of the action undone."""
    payload = _ask("undo", "/undo")
    return _hist(payload)


def redo():
    """Ctrl+Shift+Z on the running rack."""
    payload = _ask("redo", "/redo")
    return _hist(payload)


def module_json(module_id):
    """Read one live module's full .vcv JSON (params, data, slots, version).

    The live counterpart of patch_info's per-module view, and the ground truth
    for editing a module properly: hand the JSON to module_from_json (JS API) or
    edit it and deploy the patch.
    """
    payload = _ask("module-json", "/module-json", (("h", int(module_id)),))
    if payload is None:
        return dict(PROBE_UNSUPPORTED)
    try:
        data = json.loads(payload)
    except ValueError:
        return {"ok": False, "raw": payload[:400]}
    return {"ok": True, "module_id": int(module_id), "module": data}


def module_remove(module_id):
    """Select a module and press Delete — removes it and its cables."""
    payload = _ask("module-remove", "/module-remove", (("h", int(module_id)),))
    return _hist(payload)


def module_move(module_id, x, y):
    """Drag a module to grid position (x, y).

    ⚠️ Units follow the .vcv file: x is in GRID cells, y is a ROW INDEX
    (VCV stores pos[0] as cell x and pos[1] as row y). Same as the file format.
    """
    payload = _ask("module-move", "/module-move",
                   (("h", int(module_id)), ("i", int(x)), ("i", int(y))))
    return _hist(payload)


def midi_out(port, status, data1, data2=0, frame=-1):
    """Inject a MIDI message into the running rack (what a hardware keyboard sends).

    ⚠️ port must be 0..15 (DPF MIDI channel) and status 0x80..0xEF. frame=-1
    means "send now"; a real frame number is honoured too. If the sequencer
    transport is bypassed, the reply reports skipped:bypassed — the message was
    accepted but NOT delivered, and we say so rather than pretending it worked.
    """
    payload = _ask("midi-out", "/midi-out",
                   (("i", int(port)), ("i", int(status)),
                    ("i", int(data1)), ("i", int(data2)), ("i", int(frame))))
    if payload is None:
        return dict(PROBE_UNSUPPORTED)
    out = {"ok": True, "port": int(port), "status": int(status),
           "data1": int(data1), "data2": int(data2), "frame": int(frame),
           "reply": payload}
    if payload.startswith("skipped"):
        out["delivered"] = False
        out["reason"] = payload
    else:
        out["delivered"] = True
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
    payload = _ask("js-list", "/osc-js-list")
    if payload is None:
        return dict(PROBE_UNSUPPORTED)
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
    payload = _ask("js", "/osc-js-run", (("i", int(index)),))
    if payload is None:
        return dict(PROBE_UNSUPPORTED)
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
    res = link().ask("/screenshot", [], timeout=timeout)
    if res is None:
        return {"ok": False,
                "note": "sent but no reply (Cardinal OSC off? wrong port? "
                        "is this a build with the /screenshot endpoint?)"}
    reply = [str(x) for x in res]
    if len(reply) < 2:
        return {"ok": False, "reply": reply, "note": "unexpected reply shape"}
    # Cardinal answers ["screenshot", "<absolute path>"] (or "fail").
    target = reply[-1]
    if target == "fail" or not target:
        return {"ok": False, "reply": reply, "note": "Cardinal could not capture"}

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
            targets = [m for m in targets if m["id"] == int(module_id)]
        elif module:
            targets = [m for m in targets
                       if module.lower() in (m["model"] + "/" + m["plugin"]).lower()]
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
        if "/" in module:
            plugin, model = module.split("/", 1)
        else:
            plugin, model = None, module
        e = pl.lookup(plugin, model) if plugin else None
        if not e:
            for v in pl.load().values():
                if v["model"].lower() == module.lower():
                    e = v
                    break
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
    if "/" in module:
        plugin, model = module.split("/", 1)
    else:
        plugin, model = None, module
    e = pl.lookup(plugin, model) if plugin else None
    if not e:
        for v in pl.load().values():
            if v["model"].lower() == module.lower():
                e = v
                break
    if not e:
        return {"error": f"{module} not in param dictionary"}
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
    p = resolve(patch)
    if not os.path.exists(p):
        return {"error": f"patch not found: {p}"}
    res = ml.apply_recipe(p, recipe_name, weight=weight)
    if res.get("error"):
        return res
    if load_after and res.get("written"):
        res["loaded"] = load_patch(p)
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
                "weight": {"type": "number", "minimum": 0, "maximum": 1,
                           "description": "0..1 blend: 1 = fully recipe "
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
        "description": "One-click deploy: backup the .vcv, run all five audits (refuse to "
                       "load on FAIL — crash-class problems are stopped BEFORE /load), push "
                       "into the running Cardinal, wait, then read back and diff STRUCTURE "
                       "(modules + cables). Parameter values are NOT compared (E8: /param "
                       "writes never reach the autosave until the patched build exists).",
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
        "description": "Compare the on-disk .vcv against what Cardinal is actually running "
                       "(module set + every cable endpoint). missing_modules = present in the "
                       "file but silently dropped by the engine. Structure only — parameter "
                       "values are excluded by design (E8), and the result carries a `stale` "
                       "flag because the autosave only flushes on /load or a GUI save.",
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "patch file name or path"}},
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
                       "first, and writes the path style already used by that module so other "
                       "slots keep resolving. Pass load_after=true to hot-reload.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "patch": {"type": "string"},
                "file": {"type": "string", "description": "e.g. melody2/m_D4.wav (relative to samples/)"},
                "slot": {"type": "integer", "minimum": 1, "maximum": 8,
                         "description": "1-based, NOT 0-based"},
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
                "slot": {"type": "integer", "minimum": 1, "maximum": 8,
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
                "module": {"type": "string"},
                "measure": {"type": "integer", "minimum": 0},
                "step": {"type": "integer", "minimum": 0},
                "pitch": {"type": "integer", "minimum": 0, "maximum": 127,
                          "description": "MIDI note number, omit to rest a cell. "
                          "Starsea tracks accept 12..108 only (engine clamps); rcm stores 0..127"},
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
                "input_port": {"type": "integer", "minimum": 0, "maximum": 23,
                               "description": "port index on the INPUT module"},
                "target_module_id": {"type": "integer", "description": "module owning the OUTPUT port"},
                "output_port": {"type": "integer", "minimum": 0, "maximum": 23,
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
                "frame": {"type": "integer", "minimum": -1,
                          "description": "-1 = send now; a real frame number defers it"},
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
                       "capability blender/godot/UE MCPs have). This is the only path "
                       "for operations needing free text or JSON, because this build's "
                       "liblo cannot RECEIVE string OSC arguments (verified 2026-10-20: "
                       "all string-input endpoints are dead; sending strings still "
                       "works). API: read — cardinal.modules()/getParam(id,n)/ports(id)/"
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
    "cardinal_diff": lambda a: cardinal_diff(a["name"]),
    "cardinal_port_semantics": lambda a: cardinal_port_semantics(
        a.get("module"), a.get("patch")),
    # --- OSC read probes (patched build only; see live_modules docstring) ---
    "cardinal_live_modules": lambda a: live_modules(),
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
        a.get("clear", False), True, a.get("load_after", False)),
    "cardinal_seq_set_running": lambda a: seq.set_running(
        a["patch"], a["module"], a["running"],
        a.get("pattern", 0), a.get("track", 0), a.get("load_after", False)),
    # --- sampler slots (equivalent of right-click -> Load sample) ---
    "cardinal_samples_list": lambda a: samplelib.list_samples(
        a.get("subdir", ""), a.get("limit", 300)),
    "cardinal_sample_inspect": lambda a: samplelib.inspect(a["patch"]),
    "cardinal_sample_load": lambda a: samplelib.load_sample(
        a["patch"], a["file"], a["slot"], a.get("module"),
        True, a.get("load_after", False)),
    "cardinal_sample_clear": lambda a: samplelib.clear_slot(
        a["patch"], a["slot"], a.get("module")),
    # ---------------- B 组读数（第二批注入的只读端点，2026-10-20）----------
    "cardinal_build_info": lambda a: build_info(),
    "cardinal_cables": lambda a: cables(a.get("module_id")),
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


def handle(req):
    """Handle one JSON-RPC request and return a response dict (or None for a
    notification that needs no reply).

    Implements just enough of MCP (initialize / tools/list / tools/call / ping)
    over stdio. Every tool call is wrapped in try/except so a single tool error
    becomes an `isError` result instead of killing the server.
    """
    method, rid = req.get("method"), req.get("id")
    params = req.get("params") or {}

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
        args = params.get("arguments") or {}
        fn = DISPATCH.get(name)
        if fn is None:
            return {"jsonrpc": "2.0", "id": rid, "result": {
                "content": [{"type": "text", "text": f"unknown tool: {name}"}],
                "isError": True}}
        try:
            data = fn(args)
            text = json.dumps(data, ensure_ascii=False, indent=2)
            payload = {"content": [{"type": "text", "text": text}], "isError": False}
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
        fn = DISPATCH.get(tool) or DISPATCH.get("cardinal_" + tool.lstrip("_"))
        if fn is None:
            print("unknown tool:", tool)
            print("available:", ", ".join(sorted(DISPATCH)))
            sys.exit(1)
        try:
            out = fn(json.loads(raw))
        except Exception as e:
            out = {"error": str(e)}
        print(json.dumps(out, ensure_ascii=False, indent=2))
    elif "--tools" in sys.argv:
        for t in TOOLS:
            print("  {:<28} {}".format(t["name"], t["description"].split(".")[0]))
    else:
        serve()
