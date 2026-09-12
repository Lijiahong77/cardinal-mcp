#!/usr/bin/env python3
"""Cardinal MCP server — let an AI agent drive Cardinal standalone directly.

This is the entry point of the `cardinal-mcp` project. It speaks MCP
(JSON-RPC 2.0) over stdio, and behind that talks to Cardinal via OSC.

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
import socket
import sys
import time

# --- Path setup: make sibling modules importable regardless of CWD ---------
# HERE   = .../tools      (this file's directory)
# REPO_ROOT = parent of tools/  (used to locate the bundled patches/ dir)
HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)

sys.path.insert(0, HERE)
import patchio  # noqa: E402  (local helper, imported after sys.path fix)

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
    # Cardinal answers ["load", "ok"] on success.
    return {"ok": bool(reply and reply[-1] == "ok"),
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


def set_host_param(port, value):
    """Set one of Cardinal's 24 host parameters via OSC `/host-param` (port 0-23).

    Host parameters drive things like audio device, sample rate, and the knobs
    exposed by the Host Parameters / Host Parameters Map modules.
    """
    if not 0 <= int(port) <= 23:
        return {"error": "port must be 0-23"}
    link().send("/host-param", [("i", int(port)), ("f", float(value))])
    return {"ok": True, "port": int(port), "value": float(value)}


def ping():
    """Send OSC `/hello` and expect a `/resp` back — pure connectivity probe."""
    res = link().ask("/hello")
    if res is None:
        return {"ok": False, "target": f"{CARDINAL_IP}:{CARDINAL_PORT}",
                "note": "no /resp received. Confirm Cardinal OSC enabled + port matches."}
    return {"ok": True, "reply": [str(x) for x in res]}


# ================================================================ Live autosave
# Cardinal continuously mirrors its running patch to %TEMP%\Cardinal.XXXX\patch.json.
# THIS is how we "read" the live state — OSC can only WRITE parameters, never
# read them. So read_live()/save_live() read this file instead of talking OSC.

def live_patch_path():
    """Find Cardinal's live autosave file; return (newest_path, temp_base).

    Cardinal makes a folder like `Cardinal.0001` (or `Cardinal.0001/autosave`).
    We glob for `Cardinal*/patch.json` (and one nested variant) and pick the
    most recently modified. Returns (None, base) if nothing is found.
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
            "mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(path))),
            "modules": mods, "cables": len(d.get("cables", []))}


def save_live(name, overwrite=True):
    """Persist Cardinal's current in-memory state to a real .vcv file.

    Anything the user tweaks in the GUI lives only in Cardinal's process memory
    until they save. If they close without saving, it's gone — call this to keep it.
    """
    path, base = live_patch_path()
    if not path:
        return {"error": "no Cardinal live autosave found; Cardinal may not be running.",
                "searched_in": base}
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
            "cables": len(keep.get("cables", [])), "bytes": os.path.getsize(out)}


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


def apply_recipe(patch, recipe_name, load_after=False):
    """Write a tone recipe into a patch; optionally load it into Cardinal after."""
    import musiclib as ml
    p = resolve(patch)
    if not os.path.exists(p):
        return {"error": f"patch not found: {p}"}
    res = ml.apply_recipe(p, recipe_name)
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
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "cardinal_list_patches",
        "description": "List all .vcv patch files in the patch directory.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "cardinal_patch_info",
        "description": "Inspect a patch's module list, including each module's moduleId and "
                       "param ids — call this BEFORE setting a param to learn the ids.",
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "file name or full path"}},
            "required": ["name"],
        },
    },
    {
        "name": "cardinal_load_patch",
        "description": "Load a .vcv patch into the running Cardinal (includes zoom + gridOffset).",
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "file name or full path"}},
            "required": ["name"],
        },
    },
    {
        "name": "cardinal_set_param",
        "description": "Turn any module's knob. Get moduleId from cardinal_patch_info "
                       "(note: it is int64).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "module_id": {"type": "integer", "description": "module id"},
                "param_id": {"type": "integer", "description": "param slot, 0-based"},
                "value": {"type": "number", "description": "target value, usually 0.0 - 1.0"},
            },
            "required": ["module_id", "param_id", "value"],
        },
    },
    {
        "name": "cardinal_set_host_param",
        "description": "Set one of Cardinal's 24 host parameters (port 0-23), used with the "
                       "Host Parameters / Host Parameters Map modules.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "port": {"type": "integer", "description": "0-23"},
                "value": {"type": "number", "description": "0.0 - 1.0"},
            },
            "required": ["port", "value"],
        },
    },
    {
        "name": "cardinal_read_live",
        "description": "Read the patch Cardinal is currently running (including each module's "
                       "named params). OSC can only write, not read — this path uses Cardinal's "
                       "live autosave file, so it sees the GUI without disturbing the user.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "cardinal_save_live",
        "description": "Persist Cardinal's current state to a .vcv file. GUI tweaks only live in "
                       "the process and vanish on close — use this to keep them.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "file name, e.g. my_patch.vcv"},
                "overwrite": {"type": "boolean", "description": "default true"},
            },
            "required": ["name"],
        },
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
                "module_id": {"type": "integer", "description": "or use module id directly"},
                "keyword": {"type": "string", "description": "search by param name, e.g. cutoff"},
            },
        },
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
        },
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
        },
    },
    {
        "name": "cardinal_apply_recipe",
        "description": "Write a tone recipe into a patch file (optionally load it into Cardinal "
                       "after). Recipe param names are translated to numbers; anything unfound is "
                       "reported explicitly.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "patch": {"type": "string", "description": "patch file name"},
                "recipe": {"type": "string", "description": "recipe name, e.g. warm_pad"},
                "load_after": {"type": "boolean",
                               "description": "load immediately after writing (replaces current rack)"},
            },
            "required": ["patch", "recipe"],
        },
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
    "cardinal_set_host_param": lambda a: set_host_param(a["port"], a["value"]),
    "cardinal_read_live": lambda a: read_live(),
    "cardinal_save_live": lambda a: save_live(a["name"], a.get("overwrite", True)),
    "cardinal_module_params": lambda a: module_params(
        a.get("patch"), a.get("module"), a.get("module_id"), a.get("keyword")),
    "cardinal_find_param": lambda a: find_param(a["module"], a["human"]),
    "cardinal_music": lambda a: music(a.get("what", "styles"), a.get("arg"), a.get("key")),
    "cardinal_apply_recipe": lambda a: apply_recipe(
        a["patch"], a["recipe"], a.get("load_after", False)),
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
        return result({
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "cardinal", "version": "0.1.0"},
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
            return result({"content": [{"type": "text", "text": text}], "isError": False})
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
