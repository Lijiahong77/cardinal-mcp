#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================================
# ⚠️ 已降级为「历史记录」——**不是重放路径**（2026-10-21）
#
# 本脚本记录了当初这个批次改了什么、有哪些设计教训（血泪注释），有阅读价值。
# 但它**不再用于把改动放回源码树**。
#
# 原因（三条，实测）：
#   1. 注入器**覆盖不全** —— E1 的 `cardinalOscReply` helper 与
#      `src/override/MenuBar.cpp` 的自动开 OSC 补丁**不在任何注入器里**
#      ⇒ 跑完全部 6 个注入器也凑不出现在的树。
#   2. 依赖「唯一锚点」匹配，upstream 一改锚点就失效（patch 靠行号+上下文，
#      冲突时 git 明确报错，不会静默插错位置）。
#   3. 改动的**真相**现已以 `patches/*.patch` 进 git，
#      由 `replay_osc.py` 统一重放 —— 实测重放后与现状 22/22 文件逐字节一致。
#
# ⭐ 正确的重放方式：
#     python3 /mnt/d/Cardinal/tools/osc_patch/replay_osc.py
# 详见 `tools/osc_patch/README.md`。
# ============================================================================

"""inject_osc_b.py —— 把 B 组读数 handler 注入 CardinalCommon.cpp（依赖 A 组已在）

★ 注什么（2026-10-20）
  B 组 5 个读数端点（源码依据全部实测核实过，见 inc 文件头）：
    /build-info          构建指纹（P0：区分「OSC 没开」与「Cardinal 崩了」）
    /cables              全机架接线（无参）/ 单模块过滤（"h"）
    /transport           走带状态（playing/bar/beat/bpm/…）
    /engine-info         采样率/缓冲/CPU 负载
    /plugins             已安装插件查询（"s"）+ 机架内 slugs + safeMode 标志

★ 安全设计（与 A 组注入器同规格）
  1. 幂等：MARKER 判别，重复跑 skip。
  2. 改前备份：.bak-<时间戳>-osc-b
  3. 改后校验：7 个注册端点 × 实现 1 次 / 注册 2 次（thread + plain 两处）。
  4. 可回滚：--rollback 用最近备份还原。

★ 依赖
  A 组（osc_read_handlers.cpp.inc）必须已注入——锚点挂在 A 组的 END marker
  与 /light 注册行上。脚本会先检查，缺 A 组时报错退出。

用法（在 WSL 里跑，路径是 WSL 路径）:
    python3 inject_osc_b.py
    python3 inject_osc_b.py --check
    python3 inject_osc_b.py --rollback
"""
import os
import shutil
import sys
import time

# WSL 侧路径
TARGET = "/home/lijia/Cardinal/src/CardinalCommon.cpp"
INC = "/mnt/d/Cardinal/tools/osc_patch/osc_read_b_handlers.cpp.inc"
MARKER = "// ==== CARDINAL-MCP-READ-PROBES-B-BEGIN ===="

# A 组依赖的锚点（A 组注入器留下的结构）
ANCHOR_A_END = "// ==== CARDINAL-MCP-READ-PROBES-END ===="
ANCHOR_A_MARKER = "// ==== CARDINAL-MCP-READ-PROBES-BEGIN ===="

# 注册锚点（A 组最后注册的两个 /light 行）
ANCHOR_THREAD_REG = 'lo_server_thread_add_method(oscServerThread, "/light", "hi", osc_light_handler, this);'
ANCHOR_PLAIN_REG = 'lo_server_add_method(oscServer, "/light", "hi", osc_light_handler, this);'

# include 锚点（A 组补的 Model.hpp 行）
ANCHOR_INC = "#include <plugin/Model.hpp>"

# B 组注册表：(path, types, handler)
# 注：/plugins 单查（"s"）已下线——liblo string 接收不可靠，单查由 MCP 侧
# 读 PluginManifests 承担（2026-10-20 决策，见 TODO-BACKLOG B5）
REGISTRATIONS = [
    ("/build-info", "",  "osc_build_info_handler"),
    ("/cables",     "",  "osc_cables_all_handler"),
    ("/cables",     "h", "osc_cables_one_handler"),
    ("/transport",  "",  "osc_transport_handler"),
    ("/engine-info", "", "osc_engine_info_handler"),
    ("/plugins",    "",  "osc_plugins_list_handler"),
]


def die(msg):
    print("[FAIL] " + msg)
    sys.exit(1)


def latest_backup():
    d = os.path.dirname(TARGET)
    cands = [f for f in os.listdir(d) if ".bak-" in f and "osc-b" in f]
    if not cands:
        return None
    cands.sort()
    return os.path.join(d, cands[-1])


def main():
    if not os.path.exists(TARGET):
        die("找不到目标文件 %s" % TARGET)
    if not os.path.exists(INC):
        die("找不到 handler 源 %s" % INC)

    src = open(TARGET, encoding="utf-8").read()

    if "--check" in sys.argv:
        print("A 组已注入: %s" % (ANCHOR_A_MARKER in src))
        print("B 组已注入: %s" % (MARKER in src))
        return 0

    if "--rollback" in sys.argv:
        bak = latest_backup()
        if not bak:
            die("找不到 B 组备份，无法回滚")
        shutil.copy2(bak, TARGET)
        print("已从 %s 回滚（B 组）" % bak)
        return 0

    if MARKER in src:
        print("[skip] B 组已经注入过了（marker 存在）。要重做请先 --rollback。")
        return 0

    # ---- 依赖检查：A 组必须在 ----
    if ANCHOR_A_MARKER not in src:
        die("A 组未注入（找不到 %s）。先跑 inject_osc_read.py。" % ANCHOR_A_MARKER)
    for anchor in (ANCHOR_A_END, ANCHOR_THREAD_REG, ANCHOR_PLAIN_REG, ANCHOR_INC):
        if anchor not in src:
            die("A 组锚点缺失：%s" % anchor)

    # ---- 备份 ----
    bak = TARGET + ".bak-%s-osc-b" % time.strftime("%Y%m%d-%H%M%S")
    shutil.copy2(TARGET, bak)
    print("[1/5] 已备份 -> %s" % bak)

    # ---- 1b) 全局前置声明（必须放在 namespace CardinalDISTRHO 之外！）----
    # rack::plugin::getPlugin 在 plugin.cpp:373 定义但 Plugin.hpp 未导出声明。
    # ⚠️ 这个声明只能出现在全局作用域：写在 namespace CardinalDISTRHO 内会
    # 变成 CardinalDISTRHO::rack，把后续所有 rack:: 引用毒化（10-20 实测）。
    ANCHOR_TOP = '#include "CardinalCommon.hpp"'
    if ANCHOR_TOP not in src:
        die("锚点 0 未找到：#include \"CardinalCommon.hpp\"")
    top_decl = ANCHOR_TOP + (
        '\n\n// B 组前置声明（全局作用域；由 inject_osc_b.py 插入）\n'
        'namespace rack { namespace plugin {\n'
        'struct Plugin;\n'
        'Plugin* getPlugin(const std::string& pluginSlug);\n'
        '} }'
    )
    src = src.replace(ANCHOR_TOP, top_decl, 1)

    # ---- 2) 插入 handler 实现（A 组 END marker 之后）----
    handlers = open(INC, encoding="utf-8").read()
    block = MARKER + "\n" + handlers + "\n// ==== CARDINAL-MCP-READ-PROBES-B-END ====\n"
    src = src.replace(ANCHOR_A_END, ANCHOR_A_END + "\n" + block, 1)

    # ---- 3) 注册（thread 版 + plain 版，两处）----
    def build_reg(server_expr, add_fn):
        lines = []
        for path, types, handler in REGISTRATIONS:
            lines.append('        %s(%s, "%s", "%s", %s, this);'
                         % (add_fn, server_expr, path, types, handler))
        return "\n".join(lines)

    reg_thread = ANCHOR_THREAD_REG + "\n" + build_reg("oscServerThread", "lo_server_thread_add_method")
    reg_plain = ANCHOR_PLAIN_REG + "\n" + build_reg("oscServer", "lo_server_add_method")
    src = src.replace(ANCHOR_THREAD_REG, reg_thread, 1)
    src = src.replace(ANCHOR_PLAIN_REG, reg_plain, 1)

    # ---- 4) include 补充（Plugin.hpp 给 B5、Cable.hpp 给 B2）----
    src = src.replace(
        ANCHOR_INC,
        ANCHOR_INC + "\n#include <plugin/Plugin.hpp>\n#include <engine/Cable.hpp>",
        1)

    open(TARGET, "w", encoding="utf-8").write(src)
    print("[2/5] 已插入 B 组 handler 实现（A 组 END marker 之后）")
    print("[3/5] 已注册 7 个端点到 thread 版与 plain 版两处")
    print("[4/5] 已补 include（plugin/Plugin.hpp + engine/Cable.hpp）")

    # ---- 校验 ----
    chk = open(TARGET, encoding="utf-8").read()
    for _, _, handler in REGISTRATIONS:
        impl = chk.count("static int %s(" % handler)
        reg = chk.count(handler + ", this)")
        if impl != 1:
            die("校验失败：%s 实现出现 %d 次（应为 1）" % (handler, impl))
        if reg != 2:
            die("校验失败：%s 注册出现 %d 次（应为 2 = thread + plain）" % (handler, reg))
    # 共用实现只应出现 1 次且不被直接注册
    if chk.count("static int osc_cables_handler_impl(") != 1:
        die("校验失败：osc_cables_handler_impl 实现不是 1 次")
    if chk.count("osc_cables_handler_impl, this)") != 0:
        die("校验失败：osc_cables_handler_impl 不应被直接注册")
    if chk.count("#include <plugin/Plugin.hpp>") != 1:
        die("校验失败：Plugin.hpp include 不是 1 次")
    if chk.count("#include <engine/Cable.hpp>") != 1:
        die("校验失败：Cable.hpp include 不是 1 次")
    if chk.count("Plugin* getPlugin(const std::string& pluginSlug);") != 1:
        die("校验失败：全局前置声明不是 1 次")
    if MARKER not in chk:
        die("校验失败：marker 不在")
    print("\n✅ B 组注入完成并校验通过（7 端点 × 实现 1 次 / 注册 2 次）")
    print("   接下来要 **重新编译** 才能生效：")
    print("   bash /mnt/d/Cardinal/tools/cross_build_cardinal.sh 8 true")
    print("   然后 make -C CardinalNative（坑 D：CardinalMini_dsp.dll 会断主构建）")
    print("   ⚠️ 编译前请先关掉正在运行的 Cardinal。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
