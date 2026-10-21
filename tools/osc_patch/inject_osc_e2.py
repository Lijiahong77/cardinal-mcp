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

"""inject_osc_e2.py —— 把 E2（分页读出 /modules-page）注入 CardinalCommon.cpp

★ E2 做了什么（2026-10-21）
  旧 /modules 一次性回全量。模块一旦多了，payload 会逼近 OSC/UDP 上限。
  E2 新增只读端点 /modules-page "ii"（offset, limit），旧 /modules 原样保留 ⇒ 零破坏。

  - 入参：两个 int32（offset, limit），limit 上限 64。
  - 回包 payload：`<returned>/<total>|<items>`，items 与 /modules 同构
    （`id:plugin|model` 逗号分隔）。returned = 本页条数，total = 总数。
  - 越界行为：offset 超过 total → returned=0 但 total 仍报真实总数；
    offset<0 / limit<=0 / limit>64 → status = err:E_BAD_ARGS。

★ 安全设计（与 A/B/C/D 组注入器同规格）
  1. 幂等：每条规则的 new 已出现在文件里 ⇒ skip。
  2. 改前备份：.bak-<时间戳>-osc-e2。
  3. 改后校验：--check 确认 handler 实现 1 次 + 注册 2 次（thread/plain）。
  4. 可回滚：--rollback 用最近备份还原。

★ 关键前提（别踩）
  - 只改顶层 src/CardinalCommon.cpp。6 份变体（Cardinal/ CardinalNative/ Mini/
    FX/ Synth/）全是符号链接指向 ../CardinalCommon.cpp，改顶层即覆盖全部。
  - 依赖 E1 的 `cardinalOscReply`（三段式回包 helper）已注入。E2 必须在 E1 之后跑。
  - 依赖 A 组的 /modules handler 已注入（本脚本的锚点就在它的结尾和注册行上）。

用法（在 WSL 里跑，路径是 WSL 路径）:
    python3 inject_osc_e2.py
    python3 inject_osc_e2.py --check
    python3 inject_osc_e2.py --rollback
可复现验证（干净副本）：
    CARDINAL_SRC=/tmp/clean_src python3 inject_osc_e2.py
"""
import os
import shutil
import sys
import time

# 默认 WSL 内路径；可用 CARDINAL_SRC 环境变量覆盖，便于在干净副本上做可复现验证。
SRC = os.environ.get("CARDINAL_SRC", "/home/lijia/Cardinal/src")
TARGET_REL = "CardinalCommon.cpp"
MARKER = "// ==== CARDINAL-MCP-E2-MODULES-PAGE-BEGIN ===="


# ---------------------------------------------------------------- 替换规则
# 每条: (tag, old, new)。幂等判据：new 已出现在文件里 ⇒ skip。

def rules():
    """E2 的三处改动：handler 实现 1 处 + 注册 2 处（thread/plain）。"""
    return [
        (
            "E2-handler",
            # 锚点：/modules handler 结尾 + /param-get 段注释首行
            '    cardinalOscReply(source, server, "modules", out, "ok");\n'
            '    return 0;\n'
            '}\n'
            '\n'
            '// ------------------------------------------------------------ /param-get\n',
            # 新：把 handler 插在 /modules 之后、/param-get 之前
            '    cardinalOscReply(source, server, "modules", out, "ok");\n'
            '    return 0;\n'
            '}\n'
            '\n'
            '// ==== CARDINAL-MCP-E2-MODULES-PAGE-BEGIN ====\n'
            '// ------------------------------------------------------------ /modules-page\n'
            '// E2 (2026-10-21): 分页版 /modules。入参 "ii" = offset, limit。\n'
            '// 回复: /resp "modules-page" "<returned>/<total>|id:plugin/model,..."\n'
            '// limit 上限 64；offset 越界返回空 items 但 total 仍报真实总数。\n'
            'static int osc_modules_page_handler(const char*, const char* types, lo_arg** argv, int argc, const lo_message m, void* const self)\n'
            '{\n'
            '    d_debug("osc_modules_page_handler()");\n'
            '    DISTRHO_SAFE_ASSERT_RETURN(argc == 2, 0);\n'
            '\n'
            '    const lo_address source = lo_message_get_source(m);\n'
            '    const lo_server server = static_cast<Initializer*>(self)->oscServer;\n'
            '\n'
            '    CardinalBasePlugin* const plugin = static_cast<Initializer*>(self)->remotePluginInstance;\n'
            '    if (plugin == nullptr)\n'
            '    {\n'
            '        cardinalOscReply(source, server, "modules-page", "", "err:E_NO_PLUGIN");\n'
            '        return 0;\n'
            '    }\n'
            '\n'
            '    const int64_t offset = argv[0]->i;\n'
            '    const int64_t limit = argv[1]->i;\n'
            '    if (offset < 0 || limit <= 0 || limit > 64)\n'
            '    {\n'
            '        cardinalOscReply(source, server, "modules-page", "", "err:E_BAD_ARGS");\n'
            '        return 0;\n'
            '    }\n'
            '\n'
            '    CardinalPluginContext* const context = plugin->context;\n'
            '\n'
            '#ifdef CARDINAL_INIT_OSC_THREAD\n'
            '    rack::contextSet(context);\n'
            '#endif\n'
            '\n'
            '    const std::vector<int64_t> ids = context->engine->getModuleIds();\n'
            '    const size_t total = ids.size();\n'
            '    std::string items;\n'
            '    size_t count = 0;\n'
            '    const size_t start = static_cast<size_t>(offset);\n'
            '\n'
            '    if (start < total)\n'
            '    {\n'
            '        for (size_t n = start; n < total && count < static_cast<size_t>(limit); ++n)\n'
            '        {\n'
            '            rack::engine::Module* const module = context->engine->getModule(ids[n]);\n'
            '            if (module == NULL)\n'
            '                continue;\n'
            '            rack::plugin::Model* const model = module->getModel();\n'
            '            if (model == NULL)\n'
            '                continue;\n'
            '\n'
            '            if (!items.empty())\n'
            '                items += ",";\n'
            '            items += std::to_string(ids[n]);\n'
            '            items += ":";\n'
            '            items += model->plugin != NULL ? model->plugin->slug : std::string("?");\n'
            '            items += "|";\n'
            '            items += model->slug;\n'
            '            ++count;\n'
            '        }\n'
            '    }\n'
            '\n'
            '#ifdef CARDINAL_INIT_OSC_THREAD\n'
            '    rack::contextSet(nullptr);\n'
            '#endif\n'
            '\n'
            '    const std::string payload = std::to_string(count) + "/" + std::to_string(total) + "|" + items;\n'
            '    cardinalOscReply(source, server, "modules-page", payload, "ok");\n'
            '    return 0;\n'
            '}\n'
            '// ==== CARDINAL-MCP-E2-MODULES-PAGE-END ====\n'
            '\n'
            '// ------------------------------------------------------------ /param-get\n',
        ),
        (
            "E2-register-thread",
            # 锚点：thread 版的 /modules 注册行（A 组注入时带 8 空格缩进）
            '        lo_server_thread_add_method(oscServerThread, "/modules", "", osc_modules_handler, this);\n',
            '        lo_server_thread_add_method(oscServerThread, "/modules", "", osc_modules_handler, this);\n'
            '        lo_server_thread_add_method(oscServerThread, "/modules-page", "ii", osc_modules_page_handler, this);\n',
        ),
        (
            "E2-register-plain",
            # 锚点：plain 版的 /modules 注册行
            '        lo_server_add_method(oscServer, "/modules", "", osc_modules_handler, this);\n',
            '        lo_server_add_method(oscServer, "/modules", "", osc_modules_handler, this);\n'
            '        lo_server_add_method(oscServer, "/modules-page", "ii", osc_modules_page_handler, this);\n',
        ),
    ]


# ---------------------------------------------------------------- 工具

def target_path():
    return os.path.join(SRC, TARGET_REL)


def read(p):
    with open(p, encoding="utf-8", errors="replace") as f:
        return f.read()


def write(p, s):
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(s)


def backup(path, stamp):
    bak = "%s.bak-%s-osc-e2" % (path, stamp)
    shutil.copyfile(path, bak)
    return bak


def check():
    """校验 E2 改动是否就位、无重复。返回问题列表。"""
    problems = []
    p = target_path()
    if not os.path.isfile(p):
        return ["%s 缺失" % TARGET_REL]
    s = read(p)

    for tag, old, new in rules():
        if new not in s:
            problems.append("[%s] new 未注入" % tag)

    # handler 实现恰好 1 次
    if s.count("static int osc_modules_page_handler(") != 1:
        problems.append("osc_modules_page_handler 实现次数异常（应为 1）")
    # 注册恰好 2 次（thread + plain）
    if s.count('"/modules-page", "ii"') != 2:
        problems.append('"/modules-page" 注册次数异常（应为 2 = thread + plain）')
    # marker 恰好 1 次
    if s.count(MARKER) != 1:
        problems.append("E2 marker 次数异常（应为 1）")
    return problems


def main():
    p = target_path()

    if "--check" in sys.argv:
        problems = check()
        if problems:
            print("E2 注入检查：发现 %d 个问题" % len(problems))
            for x in problems:
                print("  - %s" % x)
            return 1
        print("E2 注入检查：全部就位、无重复 ✔")
        return 0

    if "--rollback" in sys.argv:
        d = os.path.dirname(p)
        try:
            names = os.listdir(d)
        except FileNotFoundError:
            print("没有目录 %s" % d)
            return 1
        cands = [os.path.join(d, fn) for fn in names
                 if fn.startswith(os.path.basename(p) + ".bak-") and fn.endswith("-osc-e2")]
        if not cands:
            print("没有找到 .bak-*-osc-e2 备份")
            return 1
        cands.sort(key=os.path.getmtime)
        newest = cands[-1]
        shutil.copyfile(newest, p)
        print("已回滚 %s <- %s" % (p, os.path.basename(newest)))
        return 0

    if not os.path.isfile(p):
        print("[FAIL] 找不到目标文件 %s（CARDINAL_SRC=%s）" % (p, SRC))
        return 1

    s = read(p)

    # 前置校验：E1 的 cardinalOscReply 与 A 组的 /modules 必须在
    if "cardinalOscReply" not in s:
        print("[FAIL] 依赖缺失：cardinalOscReply（E1）尚未注入，请先注入 E1。")
        return 1
    if '"/modules", "", osc_modules_handler' not in s:
        print("[FAIL] 依赖缺失：A 组 /modules handler 尚未注入。")
        return 1

    stamp = time.strftime("%Y%m%d-%H%M%S")
    applied = skipped = 0
    failed = []
    backed_up = False

    for tag, old, new in rules():
        if new in s:
            skipped += 1
            continue
        n = s.count(old)
        if n == 0:
            failed.append("[%s] 锚点未找到（且 new 也不在）" % tag)
            continue
        if not backed_up:
            backup(p, stamp)
            backed_up = True
        s = s.replace(old, new, 1)
        applied += 1

    if applied:
        write(p, s)

    print("应用 %d 条，跳过 %d 条，失败 %d 条" % (applied, skipped, len(failed)))
    if failed:
        for f in failed:
            print("  ! %s" % f)
        return 1

    problems = check()
    if problems:
        print()
        print("注入后校验发现 %d 个问题：" % len(problems))
        for x in problems:
            print("  - %s" % x)
        return 1
    print()
    print("E2 注入后校验：全部就位、无重复 ✔")
    if applied:
        print("备份后缀：.bak-%s-osc-e2" % stamp)
    else:
        print("（幂等：目标已就位，无改动）")
    return 0


if __name__ == "__main__":
    sys.exit(main())