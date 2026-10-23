# -*- coding: utf-8 -*-
"""把 demo 采样机架的相对采样路径改回绝对路径（修 10-17 884d89a 埋的 bug）。

根因：samplerx8 的 AudioFile::load() 用 `std::ifstream file(filePath)` 直接按
当前进程 cwd 解析相对路径，而 exe 从 win64/ 启动 ⇒ cwd 不在仓库根 ⇒
`samples/kick.wav` 解析到 win64/samples/… 不存在 ⇒ 加载静默失败（empty）。

正确形态 = 绝对路径 `D:\\Cardinal\\samples\\xxx.wav`（9cec2e3 时期就是这样，
128 个 wav 已随仓库入库，绝对路径在本机最稳；跨机器可移植性靠 relocate_samples.py
或改用 cwd 无关的绝对路径，但那不是本脚本职责）。

只改 samples_root_dir 与 loaded_sample_path_N，不碰 pos/modules/cables。
幂等：已经是绝对路径或空值的槽不动。
"""
import io
import json
import os
import sys
import tarfile

import zstandard as zstd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import patchio  # noqa: E402

SAMPLES_DIR = os.path.abspath(os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "samples"))

TARGETS = [
    "D:/Cardinal/patches/demo_S4_sampling.vcv",
    "D:/Cardinal/patches/demo_S5_fullkit.vcv",
]


def fix_one(path):
    d = patchio.read_patch(path)
    n_changed = 0
    for m in d.get("modules", []):
        if m.get("model", "").lower() != "samplerx8":
            continue
        data = m.setdefault("data", {})
        for k in sorted(data):
            if not k.startswith("loaded_sample_path_"):
                continue
            v = data[k]
            if not v:
                continue
            # 已是绝对路径（D:\ 或 C:/）跳过
            vn = v.replace("\\", "/")
            if len(vn) >= 2 and vn[1] == ":":
                continue
            base = os.path.basename(vn)
            abs_p = os.path.join(SAMPLES_DIR, base)
            if not os.path.isfile(abs_p):
                print("  ⚠️ 找不到采样 %s（槽 %s）→ 跳过" % (abs_p, k))
                continue
            data[k] = abs_p.replace("/", "\\")
            n_changed += 1
        # root_dir 清空（绝对路径不需要 root 参与加载）
        if data.get("samples_root_dir"):
            data["samples_root_dir"] = ""
            n_changed += 1
    if n_changed:
        patchio.write_patch(path, d, as_archive=True)
    print("  %s → 改 %d 处" % (os.path.basename(path), n_changed))
    return n_changed


def verify(path):
    d = patchio.read_patch(path)
    for m in d.get("modules", []):
        if m.get("model", "").lower() != "samplerx8":
            continue
        data = m.get("data", {})
        for k in sorted(data):
            if k.startswith("loaded_sample_path_") and data[k]:
                v = data[k].replace("\\", "/")
                ok = len(v) >= 2 and v[1] == ":" and os.path.isfile(v)
                print("    %s = %s  %s" % (k, data[k],
                      "✅存在" if os.path.isfile(data[k]) else "❌缺失"))
        if data.get("samples_root_dir"):
            print("    ⚠️ root_dir 仍非空: %r" % data["samples_root_dir"])


if __name__ == "__main__":
    total = 0
    for t in TARGETS:
        print("== %s ==" % t)
        total += fix_one(t)
        verify(t)
    print("总改动 %d 处" % total)