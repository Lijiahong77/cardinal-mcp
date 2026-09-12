#!/usr/bin/env python3
"""给 cardinal_mcp.py 做冒烟测试：模拟 MCP 客户端走一遍握手和工具调用。"""
import json
import os
import subprocess
import sys

PY = sys.executable
SERVER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cardinal_mcp.py")

proc = subprocess.Popen([PY, SERVER], stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                        encoding="utf-8", bufsize=1)


def call(method, params=None, mid=None):
    req = {"jsonrpc": "2.0", "id": mid, "method": method, "params": params or {}}
    proc.stdin.write(json.dumps(req, ensure_ascii=False) + "\n")
    proc.stdin.flush()
    if mid is None:
        return None
    line = proc.stdout.readline()
    return json.loads(line) if line.strip() else None


ok = True
r = call("initialize", {}, 1)
print("initialize ->", json.dumps(r, ensure_ascii=False)[:200])
assert r and "result" in r and r["result"]["serverInfo"]["name"] == "cardinal"

call("notifications/initialized", {}, None)

r = call("tools/list", {}, 2)
tools = [t["name"] for t in r["result"]["tools"]]
print("tools ->", tools)
assert len(tools) == 6

r = call("tools/call", {"name": "cardinal_list_patches", "arguments": {}}, 3)
print("list_patches ->", r["result"]["content"][0]["text"][:300])
assert "helm_drums.vcv" in r["result"]["content"][0]["text"]

r = call("tools/call", {"name": "cardinal_patch_info",
                        "arguments": {"name": "helm_keys.vcv"}}, 4)
txt = r["result"]["content"][0]["text"]
info = json.loads(txt)
print("patch_info ->", [(m["id"], m["model"]) for m in info["modules"]])
assert any(m["model"] == "HostMIDI" for m in info["modules"])

# Cardinal 没开时应该优雅报错，而不是崩掉
r = call("tools/call", {"name": "cardinal_ping", "arguments": {}}, 5)
print("ping(未启动) ->", r["result"]["content"][0]["text"][:200])
assert r["result"]["isError"] is False

r = call("tools/call", {"name": "cardinal_set_param",
                        "arguments": {"module_id": 10, "param_id": 0, "value": 92.0}}, 6)
print("set_param(未启动) ->", r["result"]["content"][0]["text"][:200])

# 服务器还活着吗
r = call("tools/list", {}, 7)
assert r and "result" in r
print("\n服务器在多次调用后仍存活: OK")

proc.stdin.close()
proc.terminate()
print("全部通过" if ok else "有失败")
