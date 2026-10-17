#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
relocate_samples.py — 把机架里写死的采样绝对路径改成仓库相对路径。

为什么需要
----------
机架通过 `data.loaded_sample_path_N` 引用采样文件（`samplerx8` / `AudioFile`）。
这些字段之前写死成本机绝对路径（`D:\\Cardinal\\samples\\...`），别人 clone 下来
打开就是**哑的**——采样文件在仓库里有（`samples/` 已入库），但机架找不到它们。

这个工具只做一件事：把绝对路径改写成相对仓库根的路径。
**不碰 pos、不碰 modules 结构、不碰 cables**。

Cardinal 解析相对路径时以机架所在位置为基准，因此 `samples/xxx.wav` 与
`patches/../samples/xxx.wav` 都不可靠 —— 这里统一写成**仓库根起算**的
`samples/xxx.wav`，并在 README 说明这是「相对于仓库根」的约定。

用法
----
    python tools/relocate_samples.py --dry-run      # 只报告，不写盘
    python tools/relocate_samples.py                # 实际改写
    python tools/relocate_samples.py --root <dir>   # 指定仓库根（默认自动向上找 .git）

安全性
------
· 默认 --dry-run 关闭才会写盘，且写盘前自动备份为 *.vcv.bak-relocate
· 保留原压缩形态：原来是 archive 的改完仍是 archive，明文 JSON 的仍是明文
· 幂等：已经是相对路径的不会被重复改
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import patchio  # noqa: E402  复用工程自带的读写实现

# 匹配 Windows 绝对路径与 POSIX 绝对路径中指向「任意盘符/任意家目录」的采样引用。
# 只处理 load / path / dir 这类明显的文件字段，不做全局盲替换。
SAMPLE_KEYS = ("loaded_sample_path", "sample_path", "filename", "filepath", "file_path", "path")

# 匹配形如  D:\Cardinal\samples\...  或  C:/whatever/samples/...  的前缀
ABS_PREFIX = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\[^\\]+\\[^\\]+[\\/]|[\\/](?:home|Users|mnt|Users|opt|var)[\\/])", re.I)


def guess_root(start: str) -> str:
    """从 start 向上找含 .git 的目录作为仓库根。"""
    cur = os.path.abspath(start)
    while True:
        if os.path.isdir(os.path.join(cur, ".git")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            raise SystemExit("找不到仓库根（往上没有 .git），请用 --root 指定")
        cur = parent


def to_relative(value: str, root: str) -> str | None:
    """把绝对路径改成相对仓库根的 POSIX 风格路径；不需要改则返回 None。"""
    if not value or not ABS_PREFIX.match(value):
        return None
    norm = value.replace("\\", "/")
    root_norm = root.replace("\\", "/").rstrip("/")
    # 命中仓库根前缀 → 截断成相对路径
    if norm.lower().startswith(root_norm.lower() + "/"):
        return norm[len(root_norm) + 1:]
    # 不在仓库内：只要指向 samples/ 就保留相对形式，否则一律不动（避免改坏外部引用）
    idx = norm.lower().find("/samples/")
    if idx >= 0:
        return norm[idx + 1:]
    return None


def scan(patch: dict, root: str) -> list[tuple[str, str, str, str]]:
    """返回 [(module_slug, key, old, new), ...]"""
    hits = []
    for mod in patch.get("modules", []):
        data = mod.get("data")
        if not isinstance(data, dict):
            continue
        for key, val in list(data.items()):
            if not isinstance(val, str) or not val:
                continue
            if not any(key == sk or key.startswith(sk) for sk in SAMPLE_KEYS):
                continue
            new = to_relative(val, root)
            if new and new != val:
                hits.append((mod.get("slug") or mod.get("plugin") or "?", key, val, new))
    return hits


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", help="仓库根目录（默认自动向上找 .git）")
    ap.add_argument("--patches", help="机架目录（默认 <root>/patches）")
    ap.add_argument("--dry-run", action="store_true", help="只报告，不写盘")
    args = ap.parse_args()

    root = os.path.abspath(args.root) if args.root else guess_root(os.path.dirname(os.path.abspath(__file__)))
    pdir = os.path.abspath(args.patches) if args.patches else os.path.join(root, "patches")
    print(f"仓库根 : {root}")
    print(f"机架目录: {pdir}")
    print(f"模式   : {'DRY-RUN（不写盘）' if args.dry_run else '实际改写'}")
    print("-" * 72)

    files = sorted(f for f in os.listdir(pdir) if f.lower().endswith(".vcv"))
    total_hits, changed_files = 0, 0

    for fname in files:
        fpath = os.path.join(pdir, fname)
        try:
            raw = open(fpath, "rb").read()
            was_archive = patchio.is_archive(raw)
            patch = patchio.read_patch(fpath)
        except Exception as exc:
            print(f"  [跳过] {fname}: {exc}")
            continue

        hits = scan(patch, root)
        if not hits:
            continue

        total_hits += len(hits)
        print(f"{fname}  ({len(hits)} 处)")
        for slug, key, old, new in hits:
            print(f"    {slug}.{key}")
            print(f"      - {old}")
            print(f"      + {new}")

        if args.dry_run:
            changed_files += 1
            continue

        for slug, key, old, new in hits:
            for mod in patch["modules"]:
                data = mod.get("data")
                if isinstance(data, dict):
                    for key2, val in list(data.items()):
                        if val == old:
                            data[key2] = new

        backup = fpath + ".bak-relocate"
        shutil.copy2(fpath, backup)
        patchio.write_patch(fpath, patch, as_archive=was_archive)
        print(f"    -> 已写回（备份 {os.path.basename(backup)}，形态 {'archive' if was_archive else 'json'}）")
        changed_files += 1

    print("-" * 72)
    print(f"机架总数 {len(files)} · 需改动 {changed_files} · 路径 {total_hits} 处")
    if args.dry_run and total_hits:
        print("\n去掉 --dry-run 即可实际改写。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())