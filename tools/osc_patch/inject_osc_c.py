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

"""inject_osc_c.py —— 把 C 组（模拟人类操作）+ QuickJS 绑定注入 CardinalCommon.cpp

★ 注什么（2026-10-20，李拍板 "3" = 做 C 组 + QuickJS）
  C 组 11 个端点（全部走 history API，可 undo）：
    /param-set-by-display h i f   右键旋钮输数值（setDisplayValue + ParamChange）
    /module-add       s i i       右键 Add module（plugin|model 全称 + x + y）
    /cable-add h i h i            拖线（查重挤掉旧线，replaced=N 回显）
    /cable-remove     h           选中线 Delete
    /undo  /redo                  Ctrl+Z / Ctrl+Shift+Z
    /module-json      h           读模块 data（toJson；写方向归 JS API）
    /module-remove     h          右键 Remove
    /module-move h i i            拖动（ModuleMove history）
    /midi-out i i i i             弹 MIDI（channel+3 字节；bypassed 回显）
    /osc-echo-string   s          ★ string 接收探针（B5 止损案的重新验证）
  JS 绑定 1 个端点：
    /osc-js-eval       s          进程内 JS（对标 Unity/UE/Blender/Godot MCP）

★ 安全设计（JS）
  默认 off（CARDINAL_JS_MODE=off|read|write）；裸 JS_NewContext 不初始化 libc
  ⇒ JS 里没有 std/os ⇒ 没有任意命令执行；2000 万指令预算防卡 UI；read/write
  模式分级 API。详见 osc_js_handlers.cpp.inc 头注释。

★ 注入规格（同 A/B 组）
  幂等（MARKER）/ 备份 / 校验（实现×1 注册×2）/ --rollback。
  依赖 A、B 组已注入（锚点挂 B 组 END marker 与最后一个 B 组注册行）。

用法（WSL 内）:
    python3 inject_osc_c.py [--check | --rollback]
"""
import os
import shutil
import sys
import time

TARGET = "/home/lijia/Cardinal/src/CardinalCommon.cpp"
INC_C = "/mnt/d/Cardinal/tools/osc_patch/osc_ops_c_handlers.cpp.inc"
INC_JS = "/mnt/d/Cardinal/tools/osc_patch/osc_js_handlers.cpp.inc"
MARKER = "// ==== CARDINAL-MCP-C-GROUP-BEGIN ===="
MARKER_END = "// ==== CARDINAL-MCP-C-GROUP-END ===="

# A/B 组依赖锚点
ANCHOR_B_END = "// ==== CARDINAL-MCP-READ-PROBES-B-END ===="
ANCHOR_B_MARKER = "// ==== CARDINAL-MCP-READ-PROBES-B-BEGIN ===="
# B 组最后一个注册行（thread 与 plain 两版各一条）
ANCHOR_THREAD_REG = 'lo_server_thread_add_method(oscServerThread, "/plugins", "", osc_plugins_list_handler, this);'
ANCHOR_PLAIN_REG = 'lo_server_add_method(oscServer, "/plugins", "", osc_plugins_list_handler, this);'

# C 组 + JS 注册表：(path, types, handler)
# ⚠️ 2026-10-20 实测：liblo string 接收在本 Cardinal 版上确认不通（echo /
#   module-add / js-eval 三个 string 输入端点全部无回复，两种 oscArgStr 偏移
#   读法均失败）⇒ 所有需要任意 string 输入的端点下线，string 类能力由 JS API
#   承载（JS 侧无 liblo 问题）。JS 源码走「脚本文件+索引」（/osc-js-run i），
#   脚本目录 CARDINAL_JS_DIR（默认 D:/Cardinal/js，可 git 管理）。
REGISTRATIONS = [
    ("/param-set-by-display", "hif",  "osc_param_set_display_handler"),
    ("/cable-add",            "hihi", "osc_cable_add_handler"),
    ("/cable-remove",         "h",    "osc_cable_remove_handler"),
    ("/undo",                 "",     "osc_undo_handler"),
    ("/redo",                 "",     "osc_redo_handler"),
    ("/module-json",          "h",    "osc_module_json_handler"),
    ("/module-remove",        "h",    "osc_module_remove_handler"),
    ("/module-move",          "hii",  "osc_module_move_handler"),
    ("/midi-out",             "iiii", "osc_midi_out_handler"),
    ("/osc-js-run",           "i",    "osc_js_run_handler"),
    ("/osc-js-list",          "",     "osc_js_list_handler"),
]


def die(msg):
    print("[FAIL] " + msg)
    sys.exit(1)


def latest_backup():
    d = os.path.dirname(TARGET)
    cands = [f for f in os.listdir(d) if ".bak-" in f and "osc-c" in f]
    if not cands:
        return None
    cands.sort()
    return os.path.join(d, cands[-1])


def main():
    if not os.path.exists(TARGET):
        die("找不到目标文件 %s" % TARGET)
    for inc in (INC_C, INC_JS):
        if not os.path.exists(inc):
            die("找不到 handler 源 %s" % inc)

    src = open(TARGET, encoding="utf-8").read()

    if "--check" in sys.argv:
        print("A 组已注入: %s" % ("// ==== CARDINAL-MCP-READ-PROBES-BEGIN ====" in src))
        print("B 组已注入: %s" % (ANCHOR_B_MARKER in src))
        print("C 组已注入: %s" % (MARKER in src))
        return 0

    if "--rollback" in sys.argv:
        bak = latest_backup()
        if not bak:
            die("找不到 C 组备份，无法回滚")
        shutil.copy2(bak, TARGET)
        print("已从 %s 回滚（C 组）" % bak)
        return 0

    if MARKER in src:
        print("[skip] C 组已经注入过了（marker 存在）。要重做请先 --rollback。")
        return 0

    # ---- 依赖检查：A、B 组必须在 ----
    if ANCHOR_B_MARKER not in src:
        die("B 组未注入。先跑 inject_osc_read.py（A）和 inject_osc_b.py（B）。")
    for anchor in (ANCHOR_B_END, ANCHOR_THREAD_REG, ANCHOR_PLAIN_REG):
        if anchor not in src:
            die("B 组锚点缺失：%s" % anchor)

    # ---- 备份 ----
    bak = TARGET + ".bak-%s-osc-c" % time.strftime("%Y%m%d-%H%M%S")
    shutil.copy2(TARGET, bak)
    print("[1/5] 已备份 -> %s" % bak)

    # ---- 2) 插入 handler 实现（B 组 END marker 之后，C 组再 JS 组）----
    handlers_c = open(INC_C, encoding="utf-8").read()
    handlers_js = open(INC_JS, encoding="utf-8").read()
    block = MARKER + "\n" + handlers_c + "\n" + handlers_js + "\n" + MARKER_END + "\n"
    src = src.replace(ANCHOR_B_END, ANCHOR_B_END + "\n" + block, 1)

    # ---- 3) 注册（thread + plain 两处；挂在 B 组最后一条 /plugins 注册之后）----
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

    open(TARGET, "w", encoding="utf-8").write(src)
    print("[2/5] 已插入 C 组 + JS handler 实现")
    print("[3/5] 已注册 12 个端点到 thread 版与 plain 版两处")

    # ---- 校验 ----
    chk = open(TARGET, encoding="utf-8").read()
    for _, _, handler in REGISTRATIONS:
        impl = chk.count("static int %s(" % handler)
        reg = chk.count(handler + ", this)")
        if impl != 1:
            die("校验失败：%s 实现出现 %d 次（应为 1）" % (handler, impl))
        if reg != 2:
            die("校验失败：%s 注册出现 %d 次（应为 2）" % (handler, reg))
    # 跨 inc 共享符号只定义一次
    if chk.count("static std::string fmtB(double v)") != 1:
        die("校验失败：fmtB 定义不是 1 次")
    if chk.count("static std::string fmtC(double v)") != 1:
        die("校验失败：fmtC 定义不是 1 次")
    if chk.count("static void* g_osc_js_self") != 1:
        die("校验失败：g_osc_js_self 定义不是 1 次")
    if chk.count('#include "Rack/dep/include/quickjs.h"') != 1:
        die("校验失败：quickjs.h include 不是 1 次")
    if MARKER not in chk or MARKER_END not in chk:
        die("校验失败：marker 缺失")
    print("[4/5] 校验通过（12 端点 × 实现 1 / 注册 2；共享符号唯一）")
    print("\n✅ C 组 + JS 注入完成")
    print("   编译：bash /mnt/d/Cardinal/tools/cross_build_cardinal.sh 8 true")
    print("   然后 make -C CardinalNative（坑 D：CardinalMini_dsp.dll 会断主构建）")
    print("   ⚠️ 编译前请先关掉正在运行的 Cardinal。")
    print("   ⚠️ JS 默认关闭：要试它先 export CARDINAL_JS_MODE=read（或 =write）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
