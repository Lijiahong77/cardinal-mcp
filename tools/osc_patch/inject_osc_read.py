#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""inject_osc_read.py —— 把 OSC 只读探针注入 CardinalCommon.cpp

★ 为什么要注入（2026-10-19）
  Cardinal 的 OSC 服务器**只能写不能读**：原版只有 /hello /param /host-param /load
  四个 handler，且没有一个回数据。所以我的 MCP 只能盲写盲猜，
  **无法确认运行中的软件到底是什么状态**。

  本脚本向 `CardinalCommon.cpp` 注入 5 个只读端点：
    /modules  /param-get  /ports  /signal  /light
  并把它们注册进 startRemoteServer()。

★ 安全设计
  1. **幂等**：重复跑不会重复注入（靠 MARKER 判别）。
  2. **改前必备份**：.bak-<时间戳>-osc-read
  3. **改后自动校验**：确认 5 个 handler 都注册了、include 也加上了。
  4. **可回滚**：--rollback 用备份还原。

用法（在 WSL 里跑，路径是 WSL 路径）:
    python3 inject_osc_read.py
    python3 inject_osc_read.py --check     # 只看有没有注入过
    python3 inject_osc_read.py --rollback
"""
import os
import re
import shutil
import sys
import time

# WSL 侧路径
TARGET = "/home/lijia/Cardinal/src/CardinalCommon.cpp"
INC = "/mnt/d/Cardinal/tools/osc_patch/osc_read_handlers.cpp.inc"
MARKER = "// ==== CARDINAL-MCP-READ-PROBES-BEGIN ===="

# 要注入的三处（每处都用「唯一锚点」定位，避免误匹配）
ANCHOR_FALLBACK = 'static int osc_fallback_handler(const char* const path, const char* const types, lo_arg**, int, lo_message, void*)'
ANCHOR_THREAD_REG = 'lo_server_thread_add_method(oscServerThread, "/param", "hif", osc_param_handler, this);'
ANCHOR_PLAIN_REG = 'lo_server_add_method(oscServer, "/param", "hif", osc_param_handler, this);'


def die(msg):
    print("[FAIL] " + msg)
    sys.exit(1)


def main():
    if not os.path.exists(TARGET):
        die("找不到目标文件 %s" % TARGET)
    if not os.path.exists(INC):
        die("找不到 handler 源 %s" % INC)

    src = open(TARGET, encoding="utf-8").read()

    if "--check" in sys.argv:
        print("已注入: %s" % (MARKER in src))
        return 0

    if "--rollback" in sys.argv:
        bak = latest_backup()
        if not bak:
            die("找不到备份，无法回滚")
        shutil.copy2(bak, TARGET)
        print("已从 %s 回滚" % bak)
        return 0

    if MARKER in src:
        print("[skip] 已经注入过了（marker 存在）。要重做请先 --rollback。")
        return 0

    # ---- 备份 ----
    bak = TARGET + ".bak-%s-osc-read" % time.strftime("%Y%m%d-%H%M%S")
    shutil.copy2(TARGET, bak)
    print("[1/4] 已备份 -> %s" % bak)

    handlers = open(INC, encoding="utf-8").read()
    block = MARKER + "\n" + handlers + "\n// ==== CARDINAL-MCP-READ-PROBES-END ====\n"

    # ---- 2) 插入 handler 实现（在 fallback handler 之前）----
    if ANCHOR_FALLBACK not in src:
        die("锚点 1 未找到：osc_fallback_handler")
    src = src.replace(ANCHOR_FALLBACK, block + "\n" + ANCHOR_FALLBACK, 1)

    # ---- 3) 注册（thread 版 + plain 版，两处都要注册）----
    reg_thread = ANCHOR_THREAD_REG + (
        '\n        lo_server_thread_add_method(oscServerThread, "/modules", "", osc_modules_handler, this);'
        '\n        lo_server_thread_add_method(oscServerThread, "/param-get", "hi", osc_param_get_handler, this);'
        '\n        lo_server_thread_add_method(oscServerThread, "/ports", "h", osc_ports_handler, this);'
        '\n        lo_server_thread_add_method(oscServerThread, "/signal", "", osc_signal_handler, this);'
        '\n        lo_server_thread_add_method(oscServerThread, "/light", "hi", osc_light_handler, this);'
    )
    reg_plain = ANCHOR_PLAIN_REG + (
        '\n        lo_server_add_method(oscServer, "/modules", "", osc_modules_handler, this);'
        '\n        lo_server_add_method(oscServer, "/param-get", "hi", osc_param_get_handler, this);'
        '\n        lo_server_add_method(oscServer, "/ports", "h", osc_ports_handler, this);'
        '\n        lo_server_add_method(oscServer, "/signal", "", osc_signal_handler, this);'
        '\n        lo_server_add_method(oscServer, "/light", "hi", osc_light_handler, this);'
    )
    if ANCHOR_THREAD_REG not in src:
        die("锚点 2 未找到：thread 版 /param 注册")
    if ANCHOR_PLAIN_REG not in src:
        die("锚点 3 未找到：plain 版 /param 注册")
    src = src.replace(ANCHOR_THREAD_REG, reg_thread, 1)
    src = src.replace(ANCHOR_PLAIN_REG, reg_plain, 1)

    # ---- 4) include 补充（engine/Port.hpp、plugin/Model.hpp）----
    inc_anchor = "#include <engine/Engine.hpp>"
    if inc_anchor not in src:
        die("锚点 4 未找到：#include <engine/Engine.hpp>")
    need = ("#include <engine/Engine.hpp>\n"
            "#include <engine/Module.hpp>\n"
            "#include <engine/Port.hpp>\n"
            "#include <plugin/Model.hpp>")
    src = src.replace(inc_anchor, need, 1)

    open(TARGET, "w", encoding="utf-8").write(src)
    print("[2/4] 已插入 5 个 handler 实现")
    print("[3/4] 已注册到 thread 版与 plain 版两处 startRemoteServer")
    print("[4/4] 已补 include（Module/Port/Model）")

    # ---- 校验 ----
    chk = open(TARGET, encoding="utf-8").read()
    for name in ("osc_modules_handler", "osc_param_get_handler",
                 "osc_ports_handler", "osc_signal_handler",
                 "osc_light_handler"):
        impl = chk.count("static int %s(" % name)
        reg = chk.count(name + ", this)")
        if impl != 1:
            die("校验失败：%s 实现出现 %d 次（应为 1）" % (name, impl))
        if reg != 2:
            die("校验失败：%s 注册出现 %d 次（应为 2 = thread + plain）" % (name, reg))
    if MARKER not in chk:
        die("校验失败：marker 不在")
    print("\n✅ 注入完成并校验通过（5 handler × 实现 1 次 / 注册 2 次）")
    print("   接下来要 **重新编译** 才能生效：")
    print("   bash /mnt/d/Cardinal/tools/cross_build_cardinal.sh")
    print("   ⚠️ 编译前请先关掉正在运行的 Cardinal。")
    return 0


def latest_backup():
    d = os.path.dirname(TARGET)
    cands = [f for f in os.listdir(d) if ".bak-" in f and "osc-read" in f]
    if not cands:
        return None
    cands.sort()
    return os.path.join(d, cands[-1])


if __name__ == "__main__":
    sys.exit(main())