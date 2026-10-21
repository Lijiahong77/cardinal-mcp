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

"""inject_osc_d.py —— 把 D 组（观察能力）注入 Cardinal 源码。

★ D 组做了什么（2026-10-20，WINE 运行级实测 + 真机验收）
  D1 `/screenshot`  —— 抓运行中 Cardinal 的窗口为 PNG。
       方案不是「base64 分块回传」：全尺寸 PNG 是 MB 级，分块必爆 OSC MTU；
       而 liblo 收不了 string 参数（同 B 批血泪）。故改为
       **触发 + 落盘 + 回传路径**：handler 无参触发 → Cardinal 渲染一帧后
       把**全尺寸** PNG 写到自己的临时目录 → 回包 ["screenshot", "<绝对路径>"]
       → MCP 轮询等文件出现。
  D2 `/load` 回 warningLog —— 加载 .vcv 时的静默诊断不再消失。
       上游 `Manager::fromJson` 遇到警告会弹模态窗并**立即清空** warningLog
       （读后即焚）；OSC 侧因此永远拿不到。改法：加 `settings::oscLoadActive`
       开关，OSC 加载时不弹窗不清空，handler 取走后回 `ok`/`warn <文本>`/`fail <文本>`。
       另外取消 `override/Engine.cpp` 两处 `APP->patch->log(e.what())` 的注释
       —— 模块级异常原本被完全静默，连 warningLog 都进不去。

★ 改动清单（6 个文件，注意副本同步！）
  src/CardinalCommon.cpp            2 处  handler 重写 + 注册（thread 与非 thread）
  src/CardinalCommon.hpp            +1  声明 generateScreenshotToFile
  src/override/Window.cpp           4 处  落盘回调 + 保存分支 + 入口
  src/override/Engine.cpp           2 处  取消两处 log 注释（同一锚点出现 2 次，一次性替换）
  src/Rack/include/settings.hpp     +1  extern bool oscLoadActive
  src/Rack/src/settings.cpp         +1  定义
  src/Rack/src/patch.cpp            1 处 fromJson 弹窗条件化

🔴 **副本同步（最大的坑）**：Cardinal 的变体目录里各有一份**内容相同**的副本
  （不是符号链接！md5 相同但独立文件）：
    CardinalCommon.cpp  × 6  （顶层 + Cardinal/ + CardinalNative/ + Mini/ + FX/ + Synth/）
    Window.cpp           × 6  （override/ + Cardinal/ + CardinalNative/ + Mini/ + FX/ + Synth/）
  只改一份 ⇒ 其余变体**静默失效**（编译得过、运行时不响应）。
  本脚本按「改模板 → 同步全部副本 → 校验全部一致」来做。

★ 安全设计（与 A/B/C 组注入器同规格）
  1. 幂等：每条规则用「已注入块是否在源码中」判别 —— 注入后的 `new` 文本若已
     出现在文件里则 skip。插入型规则（new 内含 old）也能正确判幂等，重复跑安全。
  2. 改前备份：写入前先 .bak-<时间戳>-osc-d 备份原始文件。
  3. 改后校验：--check 逐项检查每个规则的 new 已就位 + 插入型规则每文件恰好 1 次
     + 6 份副本内容一致（只改一份会静默失效）。
  4. 可回滚：--rollback 用每个文件最近的备份还原。

★ 可复现验证：可用 CARDINAL_SRC 环境变量把目标目录指到任意干净 upstream 副本，
  例如：  CARDINAL_SRC=/tmp/clean_src python3 inject_osc_d.py
  （配合 inject_osc_read.py / inject_osc_b.py / inject_osc_c.py 先把 A/B/C 注好，
   因为 D1-register-plain 依赖 C 组留下的 /osc-js-list 注册行。）

用法（在 WSL 里跑，路径是 WSL 路径）:
    python3 inject_osc_d.py
    python3 inject_osc_d.py --check
    python3 inject_osc_d.py --rollback
"""
import os
import shutil
import sys
import time

# ---------------------------------------------------------------- 路径

# 默认 WSL 内路径；可用 CARDINAL_SRC 环境变量覆盖，便于在干净副本上做可复现验证。
SRC = os.environ.get("CARDINAL_SRC", "/home/lijia/Cardinal/src")

# CardinalCommon.cpp 的 6 份副本（顶层是模板）
COMMON_COPIES = [
    "CardinalCommon.cpp",
    "Cardinal/CardinalCommon.cpp",
    "CardinalNative/CardinalCommon.cpp",
    "CardinalMini/CardinalCommon.cpp",
    "CardinalFX/CardinalCommon.cpp",
    "CardinalSynth/CardinalCommon.cpp",
]

# Window.cpp 的 6 份副本（override/ 是模板）
WINDOW_COPIES = [
    "override/Window.cpp",
    "Cardinal/Window.cpp",
    "CardinalNative/Window.cpp",
    "CardinalMini/Window.cpp",
    "CardinalFX/Window.cpp",
    "CardinalSynth/Window.cpp",
]

# 只改一份（全局共享，不随变体复制）
SINGLE_FILES = [
    "CardinalCommon.hpp",
    "override/Engine.cpp",
    "Rack/include/settings.hpp",
    "Rack/src/settings.cpp",
    "Rack/src/patch.cpp",
]


# ---------------------------------------------------------------- 替换规则
# 每条规则: (文件名类别, 锚点 old, 新文本 new)
# 幂等判据：new 已出现在文件里 ⇒ 已注入，skip。因此 old 是否残留无关紧要
# （插入型规则 new 内就包含 old，原 count(old)==0 判据会失效，这里改用 new）。
# 锚点出现次数 >= 1 即替换全部（D2-engine 的锚点在 upstream 出现 2 次，一并处理）；
# 出现 0 次则报「锚点未找到」。

def rules_for_common():
    """src/CardinalCommon.cpp 的两处 D1 改动 + D2 的 load handler 重写。"""
    return [
        (
            "D1-handler",
            # 上游原文（含 # ifdef CARDINAL_INIT_OSC_THREAD 包裹）；new 去掉该包裹
            "# ifdef CARDINAL_INIT_OSC_THREAD\n"
            "static int osc_screenshot_handler(const char*, const char* types, lo_arg** argv, int argc, const lo_message m, void* const self)\n"
            "{\n"
            "    d_debug(\"osc_screenshot_handler()\");\n"
            "    DISTRHO_SAFE_ASSERT_RETURN(argc == 1, 0);\n"
            "    DISTRHO_SAFE_ASSERT_RETURN(types != nullptr && types[0] == 'b', 0);\n"
            "\n"
            "    const int32_t size = argv[0]->blob.size;\n"
            "    DISTRHO_SAFE_ASSERT_RETURN(size > 4, 0);\n"
            "\n"
            "    const uint8_t* const blob = (uint8_t*)(&argv[0]->blob.data);\n"
            "    DISTRHO_SAFE_ASSERT_RETURN(blob != nullptr, 0);\n"
            "\n"
            "    bool ok = false;\n"
            "\n"
            "    if (CardinalBasePlugin* const plugin = static_cast<Initializer*>(self)->remotePluginInstance)\n"
            "    {\n"
            "        if (char* const screenshot = String::asBase64(blob, size).getAndReleaseBuffer())\n"
            "        {\n"
            "            ok = plugin->updateStateValue(\"screenshot\", screenshot);\n"
            "            std::free(screenshot);\n"
            "        }\n"
            "    }\n"
            "\n"
            "    const lo_address source = lo_message_get_source(m);\n"
            "    const lo_server server = static_cast<Initializer*>(self)->oscServer;\n"
            "    lo_send_from(source, server, LO_TT_IMMEDIATE, \"/resp\", \"ss\", \"screenshot\", ok ? \"ok\" : \"fail\");\n"
            "    return 0;\n"
            "}\n"
            "# endif\n",
            # 新：无参触发 → 落盘 → 回传路径（去掉 # ifdef 包裹）
            "static int osc_screenshot_handler(const char*, const char*, lo_arg**, int, const lo_message m, void* const self)\n"
            "{\n"
            "    d_debug(\"osc_screenshot_handler()\");\n"
            "    std::string result;\n"
            "    const char* status = \"ok\";\n"
            "\n"
            "    if (CardinalBasePlugin* const plugin = static_cast<Initializer*>(self)->remotePluginInstance)\n"
            "    {\n"
            "        CardinalPluginContext* const context = plugin->context;\n"
            "        // D1: full-size PNG to the autosave dir (same folder MCP already finds\n"
            "        // for read_live). OSC handler returns the absolute path; MCP polls the\n"
            "        // file — thus no base64 over the OSC MTU.\n"
            "        const std::string path = rack::system::join(context->patch->autosavePath, \"screenshot.png\");\n"
            "        rack::window::generateScreenshotToFile(path);\n"
            "        result = path;\n"
            "    } else {\n"
            "        result = \"fail\";\n"
            "        status = \"err:E_INTERNAL\";\n"
            "    }\n"
            "\n"
            "    const lo_address source = lo_message_get_source(m);\n"
            "    const lo_server server = static_cast<Initializer*>(self)->oscServer;\n"
            "    cardinalOscReply(source, server, \"screenshot\", result, status);\n"
            "    return 0;\n"
            "}\n",
        ),
        (
            "D1-register-thread",
            # thread 版注册：签名 "b" → ""
            "    lo_server_thread_add_method(oscServerThread, \"/screenshot\", \"b\", osc_screenshot_handler, this);\n",
            "    lo_server_thread_add_method(oscServerThread, \"/screenshot\", \"\", osc_screenshot_handler, this);\n",
        ),
        (
            "D1-register-plain",
            # 非 thread 版：上游根本没有这一行 → 追加到 /osc-js-list 之后（C 组已注入该行）
            "        lo_server_add_method(oscServer, \"/osc-js-list\", \"\", osc_js_list_handler, this);\n",
            "        lo_server_add_method(oscServer, \"/osc-js-list\", \"\", osc_js_list_handler, this);\n"
            "        lo_server_add_method(oscServer, \"/screenshot\", \"\", osc_screenshot_handler, this);\n",
        ),
    ]


def rules_for_window():
    """src/override/Window.cpp 的四处 D1 改动。"""
    return [
        (
            "D1-include-cstdio",
            "#include <map>\n#include <queue>\n#include <thread>\n",
            "#include <cstdio>\n#include <map>\n#include <queue>\n#include <thread>\n",
        ),
        (
            "D1-globals-dump",
            "static void Window__writeImagePNG(void* context, void* data, int size) {\n",
            "// D1: full-size screenshot dump —— MCP 走「触发 + 落盘 + 回传路径」，绕开 base64 分块\n"
            "// 与 340x210 remote 预览压缩。Path 由 OSC handler 经 generateScreenshotToFile 设置。\n"
            "static std::string g_screenshotFilePath;\n"
            "\n"
            "static void Window__writePngDump(void* context, void* data, int size) {\n"
            "\tif (context != nullptr)\n"
            "\t\tstd::fwrite(data, 1, size, static_cast<FILE*>(context));\n"
            "}\n"
            "\n"
            "static void Window__writeImagePNG(void* context, void* data, int size) {\n",
        ),
        (
            "D1-save-branch",
            # 上游保存分支的两行（位于 #ifdef STBI_WRITE_NO_STDIO 内部）
            "\t\t\tWindow__downscaleBitmap(pixelsWithOffset, winWidth, winHeight);\n"
            "\t\t\tstbi_write_png_to_func(Window__writeImagePNG, internal->ui,\n"
            "\t\t\t                       winWidth, winHeight, depth, pixelsWithOffset, stride);\n",
            # 新：全尺寸落盘优先，否则维持原 remote 预览（与上游 #else stbi_write_png 并列）
            "if (!g_screenshotFilePath.empty()) {\n"
            "\t\t\t\t// D1: full-size PNG (no downscale). MCP polls the returned path.\n"
            "\t\t\t\tFILE* const f = std::fopen(g_screenshotFilePath.c_str(), \"wb\");\n"
            "\t\t\t\tif (f) {\n"
            "\t\t\t\t\tstbi_write_png_to_func(Window__writePngDump, f,\n"
            "\t\t\t\t\t                       winWidth, winHeight, depth, pixelsWithOffset, stride);\n"
            "\t\t\t\t\tstd::fclose(f);\n"
            "\t\t\t\t}\n"
            "\t\t\t\tg_screenshotFilePath.clear();\n"
            "\t\t\t} else {\n"
            "\t\t\t\tWindow__downscaleBitmap(pixelsWithOffset, winWidth, winHeight);\n"
            "\t\t\t\tstbi_write_png_to_func(Window__writeImagePNG, internal->ui,\n"
            "\t\t\t\t                       winWidth, winHeight, depth, pixelsWithOffset, stride);\n"
            "\t\t\t}\n",
        ),
        (
            "D1-entrypoint",
            "void generateScreenshot() {\n"
            "#ifdef CARDINAL_WINDOW_CAN_GENERATE_SCREENSHOTS\n"
            "\tAPP->window->internal->generateScreenshotStep = kScreenshotStepStarted;\n"
            "#endif\n"
            "}\n",
            "void generateScreenshot() {\n"
            "#ifdef CARDINAL_WINDOW_CAN_GENERATE_SCREENSHOTS\n"
            "\tAPP->window->internal->generateScreenshotStep = kScreenshotStepStarted;\n"
            "#endif\n"
            "}\n"
            "\n"
            "// D1: 全尺寸落盘入口。设置目标路径后触发截图，Window__writePngDump 会把\n"
            "// 原始分辨率 PNG 写到该路径（保存分支见上）。\n"
            "void generateScreenshotToFile(const std::string& path) {\n"
            "\tg_screenshotFilePath = path;\n"
            "#ifdef CARDINAL_WINDOW_CAN_GENERATE_SCREENSHOTS\n"
            "\tAPP->window->internal->generateScreenshotStep = kScreenshotStepStarted;\n"
            "#endif\n"
            "}\n",
        ),
    ]


def rules_for_hpp():
    """src/CardinalCommon.hpp 的声明。"""
    return [
        (
            "D1-decl",
            "namespace window {\nvoid generateScreenshot();\n}\n",
            "namespace window {\nvoid generateScreenshot();\n"
            "void generateScreenshotToFile(const std::string& path);\n}\n",
        ),
    ]


def rules_for_engine():
    """src/override/Engine.cpp：取消两处 log 注释（同一锚点在 upstream 出现 2 次，一次性替换）。"""
    return [
        (
            "D2-engine-log",
            "\t\t\t// APP->patch->log(e.what());\n",
            "\t\t\tAPP->patch->log(e.what()); // D2: keep the diagnostic (was silenced upstream)\n",
        ),
    ]


def rules_for_settings_hpp():
    return [
        (
            "D2-settings-decl",
            "extern bool safeMode;\n",
            "extern bool safeMode;\n"
            "// OSC load in progress: suppress GUI warning dialog, keep warningLog for the OSC consumer\n"
            "extern bool oscLoadActive;\n",
        ),
    ]


def rules_for_settings_cpp():
    return [
        (
            "D2-settings-def",
            "bool safeMode = false;\n",
            "bool safeMode = false;\n"
            "bool oscLoadActive = false; // OSC/MCP loads never pop the GUI warning dialog\n",
        ),
    ]


def rules_for_patch_cpp():
    return [
        (
            "D2-fromjson-dialog",
            "\tif (warningLog != \"\") {\n"
            "\t\tosdialog_message(OSDIALOG_WARNING, OSDIALOG_OK, warningLog.c_str());\n"
            "\t}\n"
            "\twarningLog = \"\";\n",
            "\t// OSC/MCP loads keep warningLog intact so osc_load_handler can send it back (D2).\n"
            "\tif (warningLog != \"\" && !settings::oscLoadActive) {\n"
            "\t\tosdialog_message(OSDIALOG_WARNING, OSDIALOG_OK, warningLog.c_str());\n"
            "\t\twarningLog = \"\";\n"
            "\t}\n",
        ),
    ]


# D2 的 osc_load_handler（较长，单独放）
D2_LOAD_HANDLER_OLD = (
    "static int osc_load_handler(const char*, const char* types, lo_arg** argv, int argc, const lo_message m, void* const self)\n"
    "{\n"
    "    d_debug(\"osc_load_handler()\");\n"
    "    DISTRHO_SAFE_ASSERT_RETURN(argc == 1, 0);\n"
    "    DISTRHO_SAFE_ASSERT_RETURN(types != nullptr && types[0] == 'b', 0);\n"
    "\n"
    "    const int32_t size = argv[0]->blob.size;\n"
    "    DISTRHO_SAFE_ASSERT_RETURN(size > 4, 0);\n"
    "\n"
    "    const uint8_t* const blob = (uint8_t*)(&argv[0]->blob.data);\n"
    "    DISTRHO_SAFE_ASSERT_RETURN(blob != nullptr, 0);\n"
    "\n"
    "    bool ok = false;\n"
    "\n"
    "    if (CardinalBasePlugin* const plugin = static_cast<Initializer*>(self)->remotePluginInstance)\n"
    "    {\n"
    "        CardinalPluginContext* const context = plugin->context;\n"
    "        std::vector<uint8_t> data(size);\n"
    "        std::memcpy(data.data(), blob, size);\n"
    "\n"
    "       #ifdef CARDINAL_INIT_OSC_THREAD\n"
    "        rack::contextSet(context);\n"
    "       #endif\n"
    "\n"
    "        rack::system::removeRecursively(context->patch->autosavePath);\n"
    "        rack::system::createDirectories(context->patch->autosavePath);\n"
    "        try {\n"
    "            rack::system::unarchiveToDirectory(data, context->patch->autosavePath);\n"
    "            context->patch->loadAutosave();\n"
    "            ok = true;\n"
    "        }\n"
    "        catch (rack::Exception& e) {\n"
    "            WARN(\"%s\", e.what());\n"
    "        }\n"
    "\n"
    "       #ifdef CARDINAL_INIT_OSC_THREAD\n"
    "        rack::contextSet(nullptr);\n"
    "       #endif\n"
    "    }\n"
    "\n"
    "    const lo_address source = lo_message_get_source(m);\n"
    "    const lo_server server = static_cast<Initializer*>(self)->oscServer;\n"
    "    lo_send_from(source, server, LO_TT_IMMEDIATE, \"/resp\", \"ss\", \"load\", ok ? \"ok\" : \"fail\");\n"
    "    return 0;\n"
    "}\n"
)

D2_LOAD_HANDLER_NEW = (
    "static int osc_load_handler(const char*, const char* types, lo_arg** argv, int argc, const lo_message m, void* const self)\n"
    "{\n"
    "    d_debug(\"osc_load_handler()\");\n"
    "    DISTRHO_SAFE_ASSERT_RETURN(argc == 1, 0);\n"
    "    DISTRHO_SAFE_ASSERT_RETURN(types != nullptr && types[0] == 'b', 0);\n"
    "\n"
    "    const int32_t size = argv[0]->blob.size;\n"
    "    DISTRHO_SAFE_ASSERT_RETURN(size > 4, 0);\n"
    "\n"
    "    const uint8_t* const blob = (uint8_t*)(&argv[0]->blob.data);\n"
    "    DISTRHO_SAFE_ASSERT_RETURN(blob != nullptr, 0);\n"
    "\n"
    "    bool ok = false;\n"
    "    std::string diag; // load diagnostics (D2): json warnings or unarchive exception\n"
    "    std::string warn; // D2: warningLog snapshot from Manager::fromJson\n"
    "\n"
    "    if (CardinalBasePlugin* const plugin = static_cast<Initializer*>(self)->remotePluginInstance)\n"
    "    {\n"
    "        CardinalPluginContext* const context = plugin->context;\n"
    "        std::vector<uint8_t> data(size);\n"
    "        std::memcpy(data.data(), blob, size);\n"
    "\n"
    "       #ifdef CARDINAL_INIT_OSC_THREAD\n"
    "        rack::contextSet(context);\n"
    "       #endif\n"
    "\n"
    "        rack::system::removeRecursively(context->patch->autosavePath);\n"
    "        rack::system::createDirectories(context->patch->autosavePath);\n"
    "        try {\n"
    "            rack::system::unarchiveToDirectory(data, context->patch->autosavePath);\n"
    "            rack::settings::oscLoadActive = true; // D2: no GUI dialog, keep warningLog\n"
    "            context->patch->loadAutosave();\n"
    "            rack::settings::oscLoadActive = false;\n"
    "            warn = context->patch->warningLog; // take it before anything else\n"
    "            context->patch->warningLog = \"\";\n"
    "            ok = true;\n"
    "        }\n"
    "        catch (rack::Exception& e) {\n"
    "            rack::settings::oscLoadActive = false;\n"
    "            WARN(\"%s\", e.what());\n"
    "            diag = e.what();\n"
    "        }\n"
    "\n"
    "       #ifdef CARDINAL_INIT_OSC_THREAD\n"
    "        rack::contextSet(nullptr);\n"
    "       #endif\n"
    "    }\n"
    "\n"
    "    std::string payload;\n"
    "    if (ok) {\n"
    "        // D2: 「加载诊断 → 静音诊断」闭环 —— warningLog 已在 try 内取走并清空。\n"
    "        if (warn.empty())\n"
    "            payload = \"ok\";\n"
    "        else {\n"
    "            if (warn.size() > 400)\n"
    "                warn = warn.substr(0, 400) + \"...trunc\";\n"
    "            payload = \"warn \" + warn;\n"
    "        }\n"
    "    } else {\n"
    "        payload = diag.empty() ? \"fail\" : \"fail \" + (diag.size() > 400 ? diag.substr(0, 400) + \"...trunc\" : diag);\n"
    "    }\n"
    "\n"
    "    const lo_address source = lo_message_get_source(m);\n"
    "    const lo_server server = static_cast<Initializer*>(self)->oscServer;\n"
    "    cardinalOscReply(source, server, \"load\", payload, ok ? \"ok\" : \"err:E_INTERNAL\");\n"
    "    return 0;\n"
    "}\n"
)


# ---------------------------------------------------------------- 工具

def read(p):
    with open(p, encoding="utf-8", errors="replace") as f:
        return f.read()


def write(p, s):
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(s)


def build_plan():
    """返回 [(rel, rules), ...]，注入主流程与 --check 共用。"""
    plan = []
    for rel in COMMON_COPIES:
        plan.append((rel, rules_for_common() + [("D2-load-handler", D2_LOAD_HANDLER_OLD,
                                                  D2_LOAD_HANDLER_NEW)]))
    for rel in WINDOW_COPIES:
        plan.append((rel, rules_for_window()))
    plan.append(("CardinalCommon.hpp", rules_for_hpp()))
    plan.append(("override/Engine.cpp", rules_for_engine()))
    plan.append(("Rack/include/settings.hpp", rules_for_settings_hpp()))
    plan.append(("Rack/src/settings.cpp", rules_for_settings_cpp()))
    plan.append(("Rack/src/patch.cpp", rules_for_patch_cpp()))
    return plan


def apply_rules(path, rules, tag_prefix, stamp):
    """对单个文件应用规则。返回 (applied, skipped, failed)。

    幂等：若某条规则的 new 已出现在文件里，说明已注入过 → skip。
    备份：在真正写盘前对原文件做备份（保证备份的是干净原始内容）。
    替换：old 出现次数 >= 1 即替换全部（D2-engine 锚点出现 2 次也一并处理）。
    """
    if not os.path.isfile(path):
        return 0, 0, ["文件不存在: %s" % path]
    s = read(path)
    applied = skipped = 0
    failed = []
    backed_up = False
    for tag, old, new in rules:
        if new in s:
            skipped += 1              # 已注入（new 已在）→ 幂等 skip
            continue
        n = s.count(old)
        if n == 0:
            failed.append("[%s/%s] 锚点未找到（且 new 也不在）" % (tag_prefix, tag))
            continue
        if not backed_up:
            backup(path, stamp)
            backed_up = True
        s = s.replace(old, new)       # 替换全部（含出现 2 次的引擎锚点）
        applied += n
    if applied:
        write(path, s)
    return applied, skipped, failed


def backup(path, stamp):
    bak = "%s.bak-%s-osc-d" % (path, stamp)
    shutil.copyfile(path, bak)
    return bak


def check():
    """校验 D 组改动是否在所有文件里就位、无重复、且副本一致。返回问题列表。"""
    problems = []
    plan = build_plan()

    for rel, rules in plan:
        p = os.path.join(SRC, rel)
        if not os.path.isfile(p):
            problems.append("%s 缺失" % rel)
            continue
        s = read(p)
        for tag, old, new in rules:
            if new not in s:
                problems.append("%s [%s] new 未注入" % (rel, tag))

    # 副本一致性（关键：只改一份会静默失效）
    for group, name in ((COMMON_COPIES, "CardinalCommon.cpp"),
                        (WINDOW_COPIES, "Window.cpp")):
        contents = {}
        for rel in group:
            p = os.path.join(SRC, rel)
            if os.path.isfile(p):
                contents[rel] = read(p)
        if len(set(contents.values())) > 1:
            problems.append("%s 的 %d 份副本内容不一致（只改一份会静默失效）"
                            % (name, len(contents)))

    # 插入型规则每文件恰好 1 次（防重复注入导致编译/运行异常）
    for rel in COMMON_COPIES:
        s = read(os.path.join(SRC, rel))
        if s.count('lo_server_add_method(oscServer, "/screenshot", "", osc_screenshot_handler, this);') != 1:
            problems.append("%s /screenshot 注册次数异常（应为 1）" % rel)
    for rel in WINDOW_COPIES:
        s = read(os.path.join(SRC, rel))
        if s.count("static std::string g_screenshotFilePath;") != 1:
            problems.append("%s g_screenshotFilePath 次数异常（应为 1）" % rel)
        if s.count("static void Window__writePngDump") != 1:
            problems.append("%s Window__writePngDump 次数异常（应为 1）" % rel)
    sh = read(os.path.join(SRC, "Rack/include/settings.hpp"))
    if sh.count("extern bool oscLoadActive;") != 1:
        problems.append("settings.hpp oscLoadActive 声明次数异常（应为 1）")
    sc = read(os.path.join(SRC, "Rack/src/settings.cpp"))
    if sc.count("bool oscLoadActive = false;") != 1:
        problems.append("settings.cpp oscLoadActive 定义次数异常（应为 1）")
    return problems


def main():
    if "--check" in sys.argv:
        problems = check()
        if problems:
            print("D 组注入检查：发现 %d 个问题" % len(problems))
            for p in problems:
                print("  - %s" % p)
            return 1
        print("D 组注入检查：全部就位、无重复、副本一致 ✔")
        return 0

    if "--rollback" in sys.argv:
        # 按原始文件（stem）分组，每组取修改时间最新的备份还原
        by_stem = {}
        for rel in COMMON_COPIES + WINDOW_COPIES + SINGLE_FILES:
            d = os.path.dirname(os.path.join(SRC, rel))
            base = os.path.basename(os.path.join(SRC, rel))
            try:
                names = os.listdir(d)
            except FileNotFoundError:
                continue
            for fn in names:
                if fn.startswith(base + ".bak-") and fn.endswith("-osc-d"):
                    full = os.path.join(d, fn)
                    stem = full.split(".bak-")[0]
                    by_stem.setdefault(stem, []).append((os.path.getmtime(full), full))
        if not by_stem:
            print("没有找到 .bak-*-osc-d 备份")
            return 1
        restored = 0
        for stem, lst in sorted(by_stem.items()):
            lst.sort()
            newest = lst[-1][1]
            shutil.copyfile(newest, stem)
            restored += 1
            print("  回滚 %s  <-  %s" % (stem, os.path.basename(newest)))
        print("已回滚 %d 个文件" % restored)
        return 0

    # ---- 执行注入 ----
    stamp = time.strftime("%Y%m%d-%H%M%S")
    total_applied = total_skipped = 0
    all_failed = []

    for rel, rules in build_plan():
        p = os.path.join(SRC, rel)
        if not os.path.isfile(p):
            all_failed.append("%s 不存在" % rel)
            continue
        a, s, f = apply_rules(p, rules, rel, stamp)
        total_applied += a
        total_skipped += s
        all_failed += f
        if a:
            print("  %-42s 应用 %d 条（跳过 %d）" % (rel, a, s))
        else:
            print("  %-42s 无需改动（跳过 %d）" % (rel, s))

    print()
    print("合计：应用 %d 条，跳过 %d 条（已注入），失败 %d 条"
          % (total_applied, total_skipped, len(all_failed)))
    if all_failed:
        for f in all_failed:
            print("  ! %s" % f)
        return 1

    problems = check()
    if problems:
        print()
        print("注入后校验发现 %d 个问题：" % len(problems))
        for p in problems:
            print("  - %s" % p)
        return 1
    print()
    print("注入后校验：全部就位、无重复、副本一致 ✔")
    print("备份后缀：.bak-%s-osc-d" % stamp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
