#!/usr/bin/env python3
"""Cardinal MCP server —— 让 AI 能直接操作 Cardinal standalone.

通过 stdio 说 MCP（JSON-RPC 2.0），背后用 OSC 跟 Cardinal 通讯。

工具:
  cardinal_ping              测试 OSC 连通性
  cardinal_list_patches      列出 patch 目录里的 .vcv
  cardinal_patch_info        查看某个 patch 的模块清单（含 moduleId，调参要用）
  cardinal_load_patch        加载 patch 到正在运行的 Cardinal
  cardinal_set_param         拧任意模块的旋钮
  cardinal_set_host_param    设置 Host Parameters 的 24 个宿主参数之一
  cardinal_read_live         读 Cardinal 当前运行中的机架（实时自动存档）
  cardinal_save_live         把当前状态存成 .vcv（界面上手改的内容关掉就没了）
  cardinal_module_params     查「参数名 -> 编号」，或按关键字搜
  cardinal_find_param        把人话（"滤波亮一点"）翻译成参数编号
  cardinal_music             节奏型 / 和弦进行 / 音色配方
  cardinal_apply_recipe      把音色配方写进机架

前提: Cardinal standalone 里必须手动打开 Engine -> Enable OSC remote control (默认端口 2228)。

自检:  python cardinal_mcp.py --selftest
"""
import io
import json
import os
import socket
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)

sys.path.insert(0, HERE)
import patchio  # noqa: E402

from pythonosc.osc_message_builder import OscMessageBuilder
from pythonosc.osc_message import OscMessage


# ---------------------------------------------------------------- 配置
# 三项都可以用环境变量覆盖（在 MCP 配置的 "env" 里写，见 mcp.example.json）

def _default_patch_dir():
    """patch 目录的解析顺序：

    1. 环境变量 CARDINAL_PATCH_DIR（推荐，指向你自己的机架目录）
    2. 仓库自带的 patches/ —— 这样 clone 下来不改任何配置就能跑示例
    3. 用户目录下的 Cardinal/patches（兜底）
    """
    env = os.environ.get("CARDINAL_PATCH_DIR")
    if env:
        return os.path.abspath(env)
    local = os.path.join(REPO_ROOT, "patches")
    if os.path.isdir(local):
        return local
    return os.path.join(os.path.expanduser("~"), "Cardinal", "patches")


CARDINAL_IP = os.environ.get("CARDINAL_IP", "127.0.0.1")      # Cardinal 所在主机
CARDINAL_PORT = int(os.environ.get("CARDINAL_PORT", "2228"))  # OSC 端口
TIMEOUT = float(os.environ.get("CARDINAL_TIMEOUT", "1.5"))    # 单条消息等待秒数
PATCH_DIR = _default_patch_dir()


# ---------------------------------------------------------------- OSC 层

def build_msg(address, args):
    """args: [(type_char, value), ...]，type 支持 i / h / f / b / s"""
    b = OscMessageBuilder(address=address)
    for typ, val in args:
        b.add_arg(val, typ)
    return b.build().dgram


class CardinalLink:
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("", 0))
        self.sock.settimeout(TIMEOUT)

    def send(self, address, args=()):
        # 对端没启动时，Windows 会在 sendto/recv 上抛 ConnectionResetError
        try:
            self.sock.sendto(build_msg(address, args), (CARDINAL_IP, CARDINAL_PORT))
            return True
        except OSError as e:
            raise RuntimeError(
                f"发送 OSC 失败（{e}）。确认 Cardinal standalone 已开启 "
                f"Engine -> Enable OSC remote control，端口 {CARDINAL_PORT}。") from e

    def ask(self, address, args=(), expect="/resp", timeout=None):
        """发一条消息并等待 /resp 回复。返回 params 列表；超时返回 None。"""
        self.sock.settimeout(timeout or TIMEOUT)
        # 先清掉残留数据报
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
                # 端口没人监听：Windows 会回 ICMP 不可达并抛 ConnectionResetError
                return None
            try:
                msg = OscMessage(data)
            except Exception:
                continue
            if msg.address == expect:
                return msg.params
        return None


LINK = None


def link():
    global LINK
    if LINK is None:
        LINK = CardinalLink()
    return LINK


# ---------------------------------------------------------------- 业务

def list_patches():
    if not os.path.isdir(PATCH_DIR):
        return {"error": f"patch 目录不存在: {PATCH_DIR}"}
    out = []
    for fn in sorted(os.listdir(PATCH_DIR)):
        if fn.lower().endswith(".vcv"):
            p = os.path.join(PATCH_DIR, fn)
            out.append({"name": fn, "path": p, "bytes": os.path.getsize(p),
                        "mtime": time.strftime("%Y-%m-%d %H:%M:%S",
                                               time.localtime(os.path.getmtime(p)))})
    return {"patches": out, "dir": PATCH_DIR}


def resolve(name):
    if os.path.isabs(name) and os.path.exists(name):
        return name
    p = os.path.join(PATCH_DIR, name)
    if not p.lower().endswith(".vcv"):
        p += ".vcv"
    return p


def patch_info(name):
    p = resolve(name)
    if not os.path.exists(p):
        return {"error": f"找不到 patch: {p}"}
    d = patchio.read_patch(p)
    mods = [{"id": m["id"], "plugin": m["plugin"], "model": m["model"],
             "params": [{"id": q.get("id"), "value": q.get("value")}
                        for q in (m.get("params") or [])]}
            for m in d.get("modules", [])]
    return {"patch": os.path.basename(p), "format": patchio.describe(p)["format"],
            "modules": mods, "cables": len(d.get("cables", []))}


def load_patch(name):
    p = resolve(name)
    if not os.path.exists(p):
        return {"error": f"找不到 patch: {p}"}
    with open(p, "rb") as f:
        raw = f.read()
    # Cardinal 的 /load 走 rack::system::unarchiveToDirectory + loadAutosave，
    # 而 Rack 的归档格式是 pax tar + zstd，里面放 patch.json
    blob = patchio.archive_bytes(raw)
    extra = {"blob_bytes": len(blob)}
    res = link().ask("/load", [("b", blob)], timeout=6.0)
    if res is None:
        return {"ok": False, "sent": os.path.basename(p), **extra,
                "note": "已发送但没有收到回复（Cardinal 没开 OSC？端口不对？）"}
    reply = [str(x) for x in res]
    return {"ok": bool(reply and reply[-1] == "ok"),
            "sent": os.path.basename(p), "reply": reply, **extra}


def set_param(module_id, param_id, value):
    link().send("/param", [("h", int(module_id)), ("i", int(param_id)),
                           ("f", float(value))])
    return {"ok": True, "moduleId": int(module_id), "paramId": int(param_id),
            "value": float(value)}


def set_host_param(port, value):
    if not 0 <= int(port) <= 23:
        return {"error": "port 必须在 0-23"}
    link().send("/host-param", [("i", int(port)), ("f", float(value))])
    return {"ok": True, "port": int(port), "value": float(value)}


def ping():
    res = link().ask("/hello")
    if res is None:
        return {"ok": False, "target": f"{CARDINAL_IP}:{CARDINAL_PORT}",
                "note": "没收到 /resp。确认 Cardinal standalone 已开启 "
                        "Engine -> Enable OSC remote control，且端口一致。"}
    return {"ok": True, "reply": [str(x) for x in res]}


# ---------------------------------------------------------------- 实时存档
# Cardinal 会把当前机架不间断地自动存到 %TEMP%\Cardinal.XXXX\patch.json。
# 这条通道让「读」成为可能——OSC 只能写参数，读不了。

def live_patch_path():
    """找 Cardinal 的实时存档，返回最新的那个文件路径。"""
    import glob
    base = os.environ.get("TEMP") or os.path.join(
        os.path.expanduser("~"), "AppData", "Local", "Temp")
    cands = []
    for pat in ("Cardinal*/patch.json", "Cardinal*/*/patch.json"):
        cands += glob.glob(os.path.join(base, pat))
    if not cands:
        return None, base
    cands.sort(key=os.path.getmtime, reverse=True)
    return cands[0], base


def read_live():
    """读 Cardinal 当前正在运行的机架状态。"""
    path, base = live_patch_path()
    if not path:
        return {"error": "没找到 Cardinal 的实时存档，Cardinal 可能没在运行。",
                "searched_in": base}
    last_err = None
    for _ in range(3):
        try:
            d = patchio.read_patch(path)
            break
        except Exception as e:          # Cardinal 正在写文件时可能读到半截
            last_err = e
            time.sleep(0.15)
    else:
        return {"error": f"实时存档读不出来（Cardinal 正在写？）: {last_err}",
                "path": path}

    import paramlib as pl
    mods = []
    for m in d.get("modules", []):
        entry = {"id": m["id"], "plugin": m["plugin"], "model": m["model"],
                 "params": [{"id": q.get("id"), "value": q.get("value")}
                            for q in (m.get("params") or [])]}
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
    """把 Cardinal 当前状态存成正式 .vcv 文件，避免界面上的改动丢失。"""
    path, base = live_patch_path()
    if not path:
        return {"error": "没找到 Cardinal 的实时存档，Cardinal 可能没在运行。",
                "searched_in": base}
    d = patchio.read_patch(path)
    keep = {k: d[k] for k in ("version", "zoom", "modules", "cables") if k in d}
    if "path" in d:
        keep["path"] = d["path"]
    fn = name if name.lower().endswith(".vcv") else name + ".vcv"
    out = os.path.join(PATCH_DIR, fn)
    if os.path.exists(out) and not overwrite:
        return {"error": f"{fn} 已存在（overwrite=false）", "path": out}
    os.makedirs(PATCH_DIR, exist_ok=True)
    patchio.write_patch(out, keep)
    return {"ok": True, "saved": out, "modules": len(keep.get("modules", [])),
            "cables": len(keep.get("cables", [])), "bytes": os.path.getsize(out)}


# ---------------------------------------------------------------- 参数查询

def module_params(patch=None, module=None, module_id=None, keyword=None):
    """查参数：某个模块的参数表 / 按关键字搜 / 把人话翻译成参数编号。"""
    import paramlib as pl

    # 情况 1：给了 patch，就在这个机架的模块里查
    if patch:
        p = resolve(patch)
        if not os.path.exists(p):
            return {"error": f"找不到 patch: {p}"}
        d = patchio.read_patch(p)
        targets = d.get("modules", [])
        if module_id is not None:
            targets = [m for m in targets if m["id"] == int(module_id)]
        elif module:
            targets = [m for m in targets
                       if module.lower() in (m["model"] + "/" + m["plugin"]).lower()]
        if not targets:
            return {"error": "机架里没找到匹配的模块",
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

    # 情况 2：按关键字在字典里搜
    if keyword:
        return {"keyword": keyword, "hits": pl.search(keyword)}

    # 情况 3：字典里查某模块完整表
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
            return {"error": f"参数字典里没有 {module}",
                    "known": sorted(pl.load().keys())}
        return {"module": e["model"], "source": e["source"], "params": e["params"]}

    return {"known_modules": sorted(pl.load().keys()),
            "hint": "传 patch+module 查机架里的实际参数，或 keyword 搜名字"}


def find_param(module, human):
    """把「人话」映射到参数编号。如 ('VCF', '滤波 亮') -> param 0。"""
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
        return {"error": f"参数字典里没有 {module}"}
    cands = pl.resolve_name(e["plugin"], e["model"], human)
    return {"module": e["model"], "query": human,
            "candidates": [{"param_id": pid, "name": nm, "score": sc}
                           for sc, pid, nm in cands]}


# ---------------------------------------------------------------- 音乐知识库

def music(what="styles", arg=None, key=None):
    """查节奏型 / 和弦进行 / 音色配方。"""
    import musiclib as ml
    if what == "styles":
        return {k: {"name": v["name"], "bpm": v["bpm"], "mood": v["mood"],
                    "desc": v["desc"]} for k, v in ml.DRUM_PATTERNS.items()}
    if what == "drums":
        if not arg:
            return {"error": "要指定风格名，如 lofi_hiphop"}
        p = ml.drum_pattern(arg)
        return p or {"error": f"没有这个节奏型: {arg}",
                     "available": list(ml.DRUM_PATTERNS)}
    if what == "chords":
        if not arg:
            return {k: {"name": v["name"], "degrees": v["degrees"], "mood": v["mood"]}
                    for k, v in ml.PROGRESSIONS.items()}
        pr = ml.progression(arg, key or "C major")
        if not pr:
            return {"error": f"没有这个进行: {arg}",
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
        return r or {"error": f"没有这个配方: {arg}",
                     "available": list(ml.RECIPES)}
    if what == "suggest":
        return {"query": arg,
                "hits": [{"kind": kind, "key": k, "name": nm, "mood": mood}
                         for _sc, kind, k, nm, mood in ml.suggest(arg or "")]}
    return {"error": f"不认识的查询类型: {what}",
            "valid": ["styles", "drums", "chords", "recipes", "recipe", "suggest"]}


def apply_recipe(patch, recipe_name, load_after=False):
    """把音色配方写进机架；可选立即加载到 Cardinal。"""
    import musiclib as ml
    p = resolve(patch)
    if not os.path.exists(p):
        return {"error": f"找不到 patch: {p}"}
    res = ml.apply_recipe(p, recipe_name)
    if res.get("error"):
        return res
    if load_after and res.get("written"):
        res["loaded"] = load_patch(p)
    return res


# ---------------------------------------------------------------- MCP 协议

TOOLS = [
    {
        "name": "cardinal_ping",
        "description": "测试与 Cardinal standalone 的 OSC 连接是否正常。"
                       "Cardinal 必须先手动开启 Engine -> Enable OSC remote control。",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "cardinal_list_patches",
        "description": "列出 patch 目录里的所有 .vcv 机架文件。",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "cardinal_patch_info",
        "description": "查看某个 patch 的模块清单，含每个模块的 moduleId 和参数 id——"
                       "调参数前先用它查 id。",
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "文件名或完整路径"}},
            "required": ["name"],
        },
    },
    {
        "name": "cardinal_load_patch",
        "description": "把一个 .vcv 机架加载进正在运行的 Cardinal。",
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "文件名或完整路径"}},
            "required": ["name"],
        },
    },
    {
        "name": "cardinal_set_param",
        "description": "拧任意模块的旋钮。moduleId 用 cardinal_patch_info 查（注意是 int64）。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "module_id": {"type": "integer", "description": "模块 id"},
                "param_id": {"type": "integer", "description": "参数序号，从 0 开始"},
                "value": {"type": "number", "description": "目标值，通常 0.0 - 1.0"},
            },
            "required": ["module_id", "param_id", "value"],
        },
    },
    {
        "name": "cardinal_set_host_param",
        "description": "设置 Cardinal 对宿主暴露的 24 个参数之一（port 0-23），"
                       "配合机架里的 Host Parameters / Host Parameters Map 使用。",
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
        "description": "读 Cardinal 当前正在运行的机架状态（含每个模块的命名参数）。"
                       "OSC 只能写不能读，这条路走的是 Cardinal 的实时自动存档，"
                       "所以能在不打扰用户的情况下看到界面上的东西。",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "cardinal_save_live",
        "description": "把 Cardinal 当前状态存成正式 .vcv 文件。用户在界面上手改的"
                       "内容只活在进程里，关掉就没了——用这个保住。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "文件名，如 my_patch.vcv"},
                "overwrite": {"type": "boolean", "description": "默认 true"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "cardinal_module_params",
        "description": "查参数的「名字 -> 编号」对照。三种用法：① patch+module 查"
                       "某个机架里该模块的实际参数（含当前值和名字）；② module 查"
                       "参数字典里的完整表；③ keyword 按名字模糊搜。"
                       "调参之前先查，免得拧错旋钮——注意有些编号是废弃槽位。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "patch": {"type": "string", "description": "机架文件名（可选）"},
                "module": {"type": "string", "description": "模块名如 VCF、Clocked"},
                "module_id": {"type": "integer", "description": "或直接用模块 id"},
                "keyword": {"type": "string", "description": "按参数名搜，如 cutoff"},
            },
        },
    },
    {
        "name": "cardinal_find_param",
        "description": "把「人话」翻译成参数编号。比如 module=VCF、human='滤波 亮度' "
                       "会返回 Candidates: param 0 = Cutoff frequency。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "module": {"type": "string", "description": "模块名，如 VCF"},
                "human": {"type": "string", "description": "要表达的意思，如 '明亮'/'混响多少'"},
            },
            "required": ["module", "human"],
        },
    },
    {
        "name": "cardinal_music",
        "description": "音乐知识库：鼓节奏型（16 分网格）、和弦进行（可指定调）、"
                       "音色配方。what 取 styles/drums/chords/recipes/recipe/suggest。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "what": {"type": "string",
                         "enum": ["styles", "drums", "chords", "recipes", "recipe", "suggest"]},
                "arg": {"type": "string", "description": "风格名/进行名/配方名/查询词"},
                "key": {"type": "string", "description": "调，如 'D minor'、'F major'"},
            },
            "required": ["what"],
        },
    },
    {
        "name": "cardinal_apply_recipe",
        "description": "把音色配方写进机架文件（可选立即加载到 Cardinal）。"
                       "配方里的参数名会被翻译成编号，找不到的会明确报出来。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "patch": {"type": "string", "description": "机架文件名"},
                "recipe": {"type": "string", "description": "配方名，如 warm_pad"},
                "load_after": {"type": "boolean",
                               "description": "写完是否立刻加载（会替换 Cardinal 当前机架）"},
            },
            "required": ["patch", "recipe"],
        },
    },
]

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
                "content": [{"type": "text", "text": f"未知工具: {name}"}],
                "isError": True}}
        try:
            data = fn(args)
            text = json.dumps(data, ensure_ascii=False, indent=2)
            return result({"content": [{"type": "text", "text": text}], "isError": False})
        except Exception as e:
            return result({"content": [{"type": "text", "text": f"执行失败: {e}"}],
                           "isError": True})
    if method == "ping":
        return result({})
    if rid is None:
        return None
    return {"jsonrpc": "2.0", "id": rid,
            "error": {"code": -32601, "message": f"不支持的方法: {method}"}}


def read_message(stream):
    """同时支持换行分隔的 JSON 和带 Content-Length 头的分帧。"""
    line = stream.readline()
    if not line:
        return None
    if line.lstrip().startswith(b"{"):
        return line
    if line.lower().startswith(b"content-length:"):
        length = int(line.split(b":", 1)[1].strip())
        while True:
            hdr = stream.readline()
            if hdr in (b"\r\n", b"\n", b"", None):
                break
        return stream.read(length)
    return None


def serve():
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
    print(f"目标: {CARDINAL_IP}:{CARDINAL_PORT}   patch 目录: {PATCH_DIR}")
    print("patch 列表:", json.dumps(list_patches(), ensure_ascii=False, indent=2))
    print("OSC ping:", json.dumps(ping(), ensure_ascii=False))

    print("\n--- 实时存档 ---")
    live = read_live()
    if live.get("error"):
        print("  没读到:", live["error"])
    else:
        print("  {}  {} 个模块 {} 根线".format(live["file"], len(live["modules"]),
                                                live["cables"]))
        for m in live["modules"][:4]:
            named = m.get("named_params") or []
            sample = ", ".join("{}={}".format(p["name"], p["value"]) for p in named[:3])
            print("    id={:<4} {:<28} {}".format(m["id"], m["model"], sample))

    print("\n--- 参数查询 ---")
    r = module_params(module="VCF")
    if r.get("params"):
        for pid, p in sorted(r["params"].items(), key=lambda x: int(x[0])):
            print("    VCF param {:<3} {}".format(pid, p.get("name") or "(废弃/未用)"))
    print("  人话翻译:", json.dumps(find_param("VCF", "滤波 亮 截止"), ensure_ascii=False))
    print("  关键字搜:", json.dumps(
        module_params(keyword="mute").get("hits", [])[:3], ensure_ascii=False))

    print("\n--- 音乐库 ---")
    import musiclib as ml
    print("  节奏型:", len(ml.DRUM_PATTERNS), "和弦进行:", len(ml.PROGRESSIONS),
          "配方:", len(ml.RECIPES))
    pr = ml.progression("minor_epic", "D minor")
    print("  D 小调 i-VI-III-VII:", [c["notes"] for c in pr["chords"]])

    # 离线验证 OSC 报文编码（int64 是否可用）
    dgram = build_msg("/param", [("h", 1234567890123), ("i", 3), ("f", 0.5)])
    m = OscMessage(dgram)
    print("\n编码自检:", m.address, m.params)
    print("工具总数:", len(TOOLS))


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    elif "--call" in sys.argv:
        # 命令行调单个工具，绕过 MCP 连接（服务改过之后不用重启 WorkBuddy 就能验证）
        i = sys.argv.index("--call")
        if len(sys.argv) < i + 2:
            print("用法: --call <工具名> ['{\"参数\": ...}']")
            sys.exit(1)
        tool = sys.argv[i + 1]
        raw = sys.argv[i + 2] if len(sys.argv) > i + 2 else "{}"
        fn = DISPATCH.get(tool) or DISPATCH.get("cardinal_" + tool.lstrip("_"))
        if fn is None:
            print("未知工具:", tool)
            print("可用:", ", ".join(sorted(DISPATCH)))
            sys.exit(1)
        try:
            out = fn(json.loads(raw))
        except Exception as e:
            out = {"error": str(e)}
        print(json.dumps(out, ensure_ascii=False, indent=2))
    elif "--tools" in sys.argv:
        for t in TOOLS:
            print("  {:<28} {}".format(t["name"], t["description"].split("。")[0]))
    else:
        serve()
