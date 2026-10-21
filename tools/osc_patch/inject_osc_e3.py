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

"""inject_osc_e3.py —— 把 OSC 端点注册表抽成一个函数（E3 组最后一批）

★ E3 要解决什么（2026-10-21）
  现状：thread 版（lo_server_thread_add_method）与 plain 版（lo_server_add_method）
  **各写一遍**完整端点表（28 个端点 + 1 个 fallback）。加一个新端点必须记得改两处，
  漏一处 ⇒ **静默失效**：编译照过、运行时不报错，只是那个端点不存在。
  历史上 D 组加 /screenshot 时就踩过这类坑。

  改法：端点表抽成**单一真源**（X-macro），thread/plain 各自一个薄封装。

    #define CARDINAL_OSC_METHODS(REG) \
        REG("/hello", "", osc_hello_handler) \
        REG("/host-param", "if", osc_host_param_handler) \
        ...

    static void RegisterOscMethodsThread(lo_server_thread st, void* self) {
        #define REG(path, types, handler) lo_server_thread_add_method(st, path, types, handler, self);
        CARDINAL_OSC_METHODS(REG)
        #undef REG
        lo_server_thread_add_method(st, nullptr, nullptr, osc_fallback_handler, nullptr);
    }

  为什么用 X-macro 而不是「一个函数 + 布尔参数」：
  两个 liblo 入口的**第一个参数类型不同**（lo_server vs lo_server_thread），
  后三个完全一致。X-macro 让两个薄封装各自用正确类型 ⇒ **零类型强转**。

★ 🔴 关键安全设计：端点表**不手抄**
  本脚本从源码里**解析**出当前 thread 版和 plain 版的实际注册行，
  解析出 (path, types, handler) 三元组，再与硬编码的权威清单 EXPECTED_METHODS
  **逐条比对**（数量 + 顺序 + path + types + handler 全等）才允许注入。
  ⇒ 不可能抄错、漏抄、错序；也不可能把某个端点悄悄弄丢。

★ 幂等
  - 判据：X-macro 定义 `CARDINAL_OSC_METHODS(REG)` 已在文件里 ⇒ 已注入，skip。
  - 也可 --check 确认。

★ 备份 / 回滚
  - 写入前备份 .bak-<时间戳>-osc-e3
  - --rollback 用最近备份还原

★ 只改顶层
  6 份变体（Cardinal/ CardinalNative/ Mini/ FX/ Synth/）全是**符号链接**指向
  ../CardinalCommon.cpp，改顶层即覆盖全部（见 HANDOFF §4.2）。

用法（在 WSL 里跑）:
    python3 inject_osc_e3.py
    python3 inject_osc_e3.py --check
    python3 inject_osc_e3.py --rollback
可复现验证（干净副本）:
    CARDINAL_SRC=/tmp/clean_src python3 inject_osc_e3.py
"""
import os
import re
import shutil
import sys
import time

SRC = os.environ.get("CARDINAL_SRC", "/home/lijia/Cardinal/src")
TARGET_REL = "CardinalCommon.cpp"
MARKER = "// ==== CARDINAL-MCP-E3-METHOD-REGISTRY-BEGIN ===="

# 权威端点清单（顺序 = 注册顺序，必须与源码现状逐条一致）
# 注意 /cables 注册了两次："" 与 "h" 两种类型串，liblo 按类型分派，两个都要。
EXPECTED_METHODS = [
    ("/hello", "", "osc_hello_handler"),
    ("/host-param", "if", "osc_host_param_handler"),
    ("/load", "b", "osc_load_handler"),
    ("/param", "hif", "osc_param_handler"),
    ("/modules", "", "osc_modules_handler"),
    ("/modules-page", "ii", "osc_modules_page_handler"),
    ("/param-get", "hi", "osc_param_get_handler"),
    ("/ports", "h", "osc_ports_handler"),
    ("/signal", "", "osc_signal_handler"),
    ("/light", "hi", "osc_light_handler"),
    ("/build-info", "", "osc_build_info_handler"),
    ("/cables", "", "osc_cables_all_handler"),
    ("/cables", "h", "osc_cables_one_handler"),
    ("/transport", "", "osc_transport_handler"),
    ("/engine-info", "", "osc_engine_info_handler"),
    ("/plugins", "", "osc_plugins_list_handler"),
    ("/param-set-by-display", "hif", "osc_param_set_display_handler"),
    ("/cable-add", "hihi", "osc_cable_add_handler"),
    ("/cable-remove", "h", "osc_cable_remove_handler"),
    ("/undo", "", "osc_undo_handler"),
    ("/redo", "", "osc_redo_handler"),
    ("/module-json", "h", "osc_module_json_handler"),
    ("/module-remove", "h", "osc_module_remove_handler"),
    ("/module-move", "hii", "osc_module_move_handler"),
    ("/midi-out", "iiii", "osc_midi_out_handler"),
    ("/osc-js-run", "i", "osc_js_run_handler"),
    ("/osc-js-list", "", "osc_js_list_handler"),
    ("/screenshot", "", "osc_screenshot_handler"),
]

# 注册行解析：lo_server_thread_add_method(oscServerThread, "/path", "types", handler, this);
RE_THREAD = re.compile(
    r'^\s*lo_server_thread_add_method\(\s*oscServerThread\s*,\s*'
    r'"(?P<path>[^"]*)"\s*,\s*"(?P<types>[^"]*)"\s*,\s*(?P<handler>\w+)\s*,\s*this\s*\);\s*$')
RE_PLAIN = re.compile(
    r'^\s*lo_server_add_method\(\s*oscServer\s*,\s*'
    r'"(?P<path>[^"]*)"\s*,\s*"(?P<types>[^"]*)"\s*,\s*(?P<handler>\w+)\s*,\s*this\s*\);\s*$')

# fallback 行（两个都要单独处理：user_data 是 nullptr 不是 this）
FALLBACK_THREAD = 'lo_server_thread_add_method(oscServerThread, nullptr, nullptr, osc_fallback_handler, nullptr);'
FALLBACK_PLAIN = 'lo_server_add_method(oscServer, nullptr, nullptr, osc_fallback_handler, nullptr);'


def die(msg):
    print("[FAIL] " + msg)
    sys.exit(1)


def target_path():
    return os.path.join(SRC, TARGET_REL)


def read(p):
    with open(p, encoding="utf-8", errors="replace") as f:
        return f.read()


def write(p, s):
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(s)


def find_registry_bounds(lines):
    """定位两个注册块的行范围（thread 版 / plain 版）。

    注册块 = 从该变体的第一条注册行，到其 fallback 行（**含**）。
    返回 (start, end)，其中 end 是**开区间终点**（= fallback 行索引 + 1），
    替换时用 lines[start:end] 即可把整块（含 fallback）一次换掉。
    """
    bounds = {}
    for name, fallback_marker, prefix in (
            ("thread", FALLBACK_THREAD, "lo_server_thread_add_method(oscServerThread"),
            ("plain", FALLBACK_PLAIN, "lo_server_add_method(oscServer")):
        fb_idx = None
        for i, ln in enumerate(lines):
            if fallback_marker in ln:
                fb_idx = i
                break
        if fb_idx is None:
            return None, "找不到 %s 版的 fallback 注册行" % name
        # 往上找该块的第一条注册行：从 fallback 行的**前一行**起，连续的注册行
        start = fb_idx
        while start - 1 >= 0:
            prev = lines[start - 1]
            if prefix in prev:
                start -= 1
                continue
            break
        if start == fb_idx:
            return None, "%s 版注册块里一条注册行都没有（只找到 fallback）" % name
        # 终点 = fallback 行之后一行 ⇒ lines[start:end] 覆盖整块（含 fallback）
        bounds[name] = (start, fb_idx + 1)
    return bounds, None


def build_registry_block(methods):
    """生成 X-macro 端点表 + 两个薄封装。"""
    out = []
    out.append(MARKER)
    out.append("// E3 (2026-10-21): OSC 端点注册表 —— 单一真源。")
    out.append("//")
    out.append("// 之前 thread 版与 plain 版各写一遍完整端点表，加端点要记得改两处，")
    out.append("// 漏一处就静默失效（编译过、运行时不报错、端点就是不存在）。")
    out.append("// 现在端点表只写这一份，两个薄封装各自展开成对应的 liblo 入口 ——")
    out.append("// 两个入口后三个参数类型一致、只有第一个不同 ⇒ 零类型强转。")
    out.append("//")
    out.append("// 用法：定义 REG(path, types, handler) 宏 → 展开 CARDINAL_OSC_METHODS(REG)")
    out.append("//       → #undef REG。REG 负责展开成具体的 add_method 调用。")
    out.append("#define CARDINAL_OSC_METHODS(REG) \\")
    for i, (path, types, handler) in enumerate(methods):
        tail = " \\" if i < len(methods) - 1 else ""
        out.append('    REG("%s", "%s", %s)%s' % (path, types, handler, tail))
    out.append("")
    # 两个薄封装各自放进对应的编译分支：CARDINAL_INIT_OSC_THREAD 决定用哪个
    # liblo 入口，两个入口互斥 ⇒ 编译期只存在需要的那一个 ⇒ 没有 unused 警告。
    out.append("#ifdef CARDINAL_INIT_OSC_THREAD")
    out.append("static void CardinalCommon_RegisterOscMethodsThread(lo_server_thread const st, void* const self)")
    out.append("{")
    out.append("    #define REG(path, types, handler) lo_server_thread_add_method(st, path, types, handler, self);")
    out.append("    CARDINAL_OSC_METHODS(REG)")
    out.append("    #undef REG")
    out.append("")
    out.append("    // fallback：未匹配路径的兜底（user_data 传 nullptr，与原实现一致）")
    out.append("    lo_server_thread_add_method(st, nullptr, nullptr, osc_fallback_handler, nullptr);")
    out.append("}")
    out.append("#else")
    out.append("static void CardinalCommon_RegisterOscMethodsPlain(lo_server const s, void* const self)")
    out.append("{")
    out.append("    #define REG(path, types, handler) lo_server_add_method(s, path, types, handler, self);")
    out.append("    CARDINAL_OSC_METHODS(REG)")
    out.append("    #undef REG")
    out.append("")
    out.append("    // fallback：未匹配路径的兜底（user_data 传 nullptr，与原实现一致）")
    out.append("    lo_server_add_method(s, nullptr, nullptr, osc_fallback_handler, nullptr);")
    out.append("}")
    out.append("#endif")
    out.append("// ==== CARDINAL-MCP-E3-METHOD-REGISTRY-END ====")
    return "\n".join(out)

def check():
    """校验 E3 是否就位。返回问题列表。"""
    problems = []
    p = target_path()
    if not os.path.isfile(p):
        return ["%s 缺失" % TARGET_REL]
    s = read(p)

    if MARKER not in s:
        problems.append("E3 registry marker 不在（未注入？）")
        return problems

    # 1) 端点表条数与内容
    got = []
    for ln in s.splitlines():
        m = re.match(r'^\s*REG\("(?P<path>[^"]*)",\s*"(?P<types>[^"]*)",\s*(?P<handler>\w+)\)', ln)
        if m:
            got.append((m.group("path"), m.group("types"), m.group("handler")))
    if got != EXPECTED_METHODS:
        problems.append("端点表与权威清单不一致：期望 %d 条，实际 %d 条" % (len(EXPECTED_METHODS), len(got)))
        if len(got) == len(EXPECTED_METHODS):
            for i, (a, b) in enumerate(zip(EXPECTED_METHODS, got)):
                if a != b:
                    problems.append("  第 %d 条不同：期望 %r 实际 %r" % (i + 1, a, b))
                    break

    # 2) 两个薄封装各恰好 1 次（源码里都在，只是编译期由 #ifdef 二选一）
    if s.count("static void CardinalCommon_RegisterOscMethodsThread(") != 1:
        problems.append("RegisterOscMethodsThread 定义次数异常（应为 1）")
    if s.count("static void CardinalCommon_RegisterOscMethodsPlain(") != 1:
        problems.append("RegisterOscMethodsPlain 定义次数异常（应为 1）")
    # 2b) 两个薄封装必须被 #ifdef CARDINAL_INIT_OSC_THREAD / #else / #endif 分开
    #     （否则编译期会多出一个未使用函数 ⇒ -Wunused-function 警告）
    if "#ifdef CARDINAL_INIT_OSC_THREAD" not in s:
        problems.append("缺少 #ifdef CARDINAL_INIT_OSC_THREAD 包裹")
    else:
        reg_block = s[s.index(MARKER):s.index("CARDINAL-MCP-E3-METHOD-REGISTRY-END")]
        t_pos = reg_block.find("RegisterOscMethodsThread(")
        p_pos = reg_block.find("RegisterOscMethodsPlain(")
        e_pos = reg_block.find("#else")
        if not (0 <= t_pos < e_pos < p_pos):
            problems.append("两个薄封装未被 #ifdef/#else 正确分隔（会触发 unused-function 警告）")

    # 3) 两个调用点各恰好 1 次
    if s.count("CardinalCommon_RegisterOscMethodsThread(oscServerThread, this);") != 1:
        problems.append("thread 版调用点次数异常（应为 1）")
    if s.count("CardinalCommon_RegisterOscMethodsPlain(oscServer, this);") != 1:
        problems.append("plain 版调用点次数异常（应为 1）")

    # 4) 旧的散装注册行必须已消失（否则就是没抽干净）
    for ln in s.splitlines():
        if RE_THREAD.match(ln) or RE_PLAIN.match(ln):
            problems.append("仍有散装注册行未抽取：%s" % ln.strip()[:100])
            break

    # 4b) fallback 注册必须恰好 2 次（两个薄封装内各一次）
    #     少了 = 端点消失；多了 = 重复注册（liblo 同名覆盖，行为不干净）
    fb_thread = sum(1 for ln in s.splitlines()
                    if "osc_fallback_handler, nullptr);" in ln
                    and "lo_server_thread_add_method" in ln)
    fb_plain = sum(1 for ln in s.splitlines()
                   if "osc_fallback_handler, nullptr);" in ln
                   and "lo_server_add_method" in ln)
    if fb_thread != 1:
        problems.append("thread 版 fallback 注册次数异常（应为 1），实际 %d" % fb_thread)
    if fb_plain != 1:
        problems.append("plain 版 fallback 注册次数异常（应为 1），实际 %d" % fb_plain)

    # 5) 宏定义 / undef 配对（按整行精确匹配，避免数到注释里的说明文字）
    if s.count("#define CARDINAL_OSC_METHODS(REG)") != 1:
        problems.append("CARDINAL_OSC_METHODS 宏定义次数异常（应为 1）")
    undef_reg = sum(1 for ln in s.splitlines() if ln.strip() == "#undef REG")
    if undef_reg != 2:
        problems.append("#undef REG 次数异常（应为 2 = 两个薄封装各一），实际 %d" % undef_reg)
    def_reg = sum(1 for ln in s.splitlines() if ln.strip().startswith("#define REG("))
    if def_reg != 2:
        problems.append("#define REG 次数异常（应为 2 = 两个薄封装各一），实际 %d" % def_reg)
    return problems


def main():
    p = target_path()

    if "--check" in sys.argv:
        problems = check()
        if problems:
            print("E3 注入检查：发现 %d 个问题" % len(problems))
            for x in problems:
                print("  - %s" % x)
            return 1
        print("E3 注入检查：端点表 %d 条与权威清单一致、两处调用点就位、无散装残留 ✔"
              % len(EXPECTED_METHODS))
        return 0

    if "--rollback" in sys.argv:
        d = os.path.dirname(p)
        try:
            names = os.listdir(d)
        except FileNotFoundError:
            print("没有目录 %s" % d)
            return 1
        cands = [os.path.join(d, fn) for fn in names
                 if fn.startswith(os.path.basename(p) + ".bak-") and fn.endswith("-osc-e3")]
        if not cands:
            print("没有找到 .bak-*-osc-e3 备份")
            return 1
        cands.sort(key=os.path.getmtime)
        newest = cands[-1]
        shutil.copyfile(newest, p)
        print("已回滚 %s <- %s" % (p, os.path.basename(newest)))
        return 0

    if not os.path.isfile(p):
        die("找不到目标文件 %s（CARDINAL_SRC=%s）" % (p, SRC))

    s = read(p)

    if MARKER in s:
        print("[skip] 已经注入过了（marker 存在）。")
        return 0

    lines = s.splitlines()

    # ---- 1) 解析两处注册块的端点 ----
    bounds, err = find_registry_bounds(lines)
    if err:
        die(err)

    t_start, t_end = bounds["thread"]
    p_start, p_end = bounds["plain"]
    if t_end >= p_start:
        die("thread 版与 plain 版注册块顺序异常（thread 块 %d-%d 未能与 plain 块 %d-%d 分开）"
            % (t_start, t_end, p_start, p_end))

    thread_methods = []
    for ln in lines[t_start:t_end]:
        m = RE_THREAD.match(ln)
        if m:
            thread_methods.append((m.group("path"), m.group("types"), m.group("handler")))
    plain_methods = []
    for ln in lines[p_start:p_end]:
        m = RE_PLAIN.match(ln)
        if m:
            plain_methods.append((m.group("path"), m.group("types"), m.group("handler")))

    # ---- 2) 交叉校验：两版必须一致，且等于权威清单 ----
    if thread_methods != plain_methods:
        die("两版端点表本来就不一致，拒绝注入：\n  thread=%r\n  plain =%r" % (thread_methods, plain_methods))
    if thread_methods != EXPECTED_METHODS:
        die("源码端点表与权威清单不一致，拒绝注入（防抄错/漏抄）：\n  源码=%r\n  清单=%r"
            % (thread_methods, EXPECTED_METHODS))
    print("[1/4] 端点表解析并校验通过：%d 条（两版一致 == 权威清单）" % len(thread_methods))

    # ---- 3) 构造新代码 ----
    registry = build_registry_block(thread_methods)

    # 替换 plain 块（先替换后面的，避免行号偏移）
    # 调用点缩进用 4 空格：紧跟在 `if (...) return false;` 之后时，
    # 8 空格会被 gcc 判成 -Wmisleading-indentation（看起来像被 if 管辖）。
    new_lines = list(lines)
    new_lines[p_start:p_end] = [
        "    CardinalCommon_RegisterOscMethodsPlain(oscServer, this);",
    ]
    new_lines[t_start:t_end] = [
        "    CardinalCommon_RegisterOscMethodsThread(oscServerThread, this);",
    ]

    # 插入注册表：放在 startRemoteServer 之前（#ifdef HAVE_LIBLO 块内、函数定义之前）
    anchor = "bool Initializer::startRemoteServer(const char* const port)"
    try:
        a_idx = new_lines.index(anchor)
    except ValueError:
        die("找不到插入锚点：%s" % anchor)
    # 回退到 #ifdef HAVE_LIBLO 那一行，插在它之后
    if_idx = a_idx
    while if_idx > 0 and new_lines[if_idx].strip() != "#ifdef HAVE_LIBLO":
        if_idx -= 1
    if new_lines[if_idx].strip() != "#ifdef HAVE_LIBLO":
        die("找不到 #ifdef HAVE_LIBLO 锚点")
    insert_at = if_idx + 1
    new_lines[insert_at:insert_at] = [""] + registry.split("\n") + [""]

    out = "\n".join(new_lines) + "\n"

    # ---- 4) 备份 + 写入 + 校验 ----
    stamp = time.strftime("%Y%m%d-%H%M%S")
    shutil.copyfile(p, "%s.bak-%s-osc-e3" % (p, stamp))
    write(p, out)
    print("[2/4] 已写入注册表（X-macro %d 条 + 两个薄封装）" % len(thread_methods))
    print("[3/4] 两处散装注册块已替换为调用")

    problems = check()
    if problems:
        print()
        print("注入后校验发现 %d 个问题：" % len(problems))
        for x in problems:
            print("  - %s" % x)
        return 1
    print("[4/4] 注入后校验通过 ✔")
    print("备份后缀：.bak-%s-osc-e3" % stamp)
    print("接下来要 **重新编译** 才能生效。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
