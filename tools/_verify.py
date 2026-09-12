#!/usr/bin/env python3
"""端到端验证 MCP <-> Cardinal 链路。

思路：Cardinal 在 patch 变动后会把它存回磁盘（改成它自己的 tar+zstd 格式），
所以我们可以改完参数后重新读文件来反查是否真的生效。
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cardinal_mcp as m
import patchio


def clocked_bpm(patch_path, module_id=10):
    d = patchio.read_patch(patch_path)
    for mod in d.get("modules", []):
        if mod["id"] == module_id:
            for q in mod.get("params") or []:
                if q["id"] == 0:
                    return q["value"]
    return None


p = os.path.join(m.PATCH_DIR, "helm_drums.vcv")

print("1) 文件格式 :", patchio.describe(p))
print("2) OSC ping :", m.ping())
print("3) patch_info:", json.dumps(m.patch_info("helm_drums.vcv")["modules"], ensure_ascii=False))
print("4) 加载前磁盘里的 BPM :", clocked_bpm(p))

print("5) load     :", m.load_patch("helm_drums.vcv"))
time.sleep(0.5)
print("6) 加载后磁盘里的 BPM :", clocked_bpm(p))

TARGET = 137.0
print(f"7) set_param(module=10, param=0, value={TARGET}) ->",
      m.set_param(10, 0, TARGET))

# 等 Cardinal 把它写回磁盘（自动保存），再反查
for i in range(10):
    time.sleep(1.0)
    v = clocked_bpm(p)
    if v is not None and abs(v - TARGET) < 0.01:
        print(f"8) 反查成功：{i+1}s 后磁盘里的 BPM 变成 {v}  -> /param 生效")
        break
else:
    print(f"8) 反查未通过：磁盘里仍是 {clocked_bpm(p)}（可能只是没自动存盘，"
          f"需人工看 Cardinal 里的 BPM 旋钮）")
