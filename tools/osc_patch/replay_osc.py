#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""replay_osc.py —— 把全部 OSC 改动一次性重放到 Cardinal 源码树

★ 为什么有这个脚本（2026-10-21）
  在此之前，33 个 OSC 端点的 C++ 改动**只存在于 WSL 工作区**（不在 git 里）。
  ⇒ 一次 `git checkout .` 就全没了；`MenuBar.cpp` 的自动开 OSC 补丁更是
    **不在任何注入器里**，连"重跑注入器"都救不回来。

  现在改动的**真相**以 `patches/*.patch` 形式存进本仓库（`Lijiahong77/cardinal-mcp`），
  本脚本负责把它们重放回源码树。**patch 是唯一真相**，注入器脚本降级为
  "历史过程记录"（保留用于阅读每个批次改了什么，但不再作为重放路径）。

★ 为什么用 patch 而不是注入器
  1. 注入器依赖"唯一锚点"匹配，upstream 一改锚点就失效；patch 靠行号+上下文，
     冲突时 git 会明确报错而不是静默插错位置。
  2. 注入器**覆盖不全**（E1 的 `cardinalOscReply` helper、MenuBar 补丁都不在里面），
     跑完 6 个注入器也凑不出现在的树 —— 实测已由 patch 逐字节一致验证。
  3. patch 可 `git apply --check` 预检、可回滚（反向 apply）、可 diff。

★ 覆盖范围（17 组 patch，按依赖顺序）
  | # | patch | 内容 | 基线 |
  |---|-------|------|------|
  | 1 | 01-osc-core.patch | `src/CardinalCommon.cpp`（28 端点全部实现 + 注册）<br>`src/CardinalCommon.hpp`（+1 声明）<br>`src/override/Engine.cpp`（恢复 2 处 `patch->log`）<br>`src/override/MenuBar.cpp`（**延后 120 帧自动开 OSC**）<br>`src/override/Window.cpp`（截图落盘 + 保存分支） | Cardinal `8aa0fc7` |
  | 2 | 02-rack-osc.patch | `src/Rack/`：`settings.hpp` / `settings.cpp`（`oscLoadActive`）<br>`src/patch.cpp`（fromJson 弹窗条件化） | Rack 子模块当前 HEAD |
  | 3 | 03-build-env.patch | `plugins/plugins.cpp`（注册 Starsea）<br>`plugins/Makefile`（Starsea 目标）<br>`include/simd-compat/immintrin.h`（编译兼容）<br>删除 `lv2export/plugins/aubileinstruments-macro-osc-2.cpp` | Cardinal `8aa0fc7` |
  | 4 | 04-starsea-plugin.patch | 新增 `plugins/Starsea/`（**10 个文件**：MiniArranger 骨架 + 扩展器 + 3 个面板 SVG） | Cardinal `8aa0fc7` |
  | 5 | 05-b2-cables-page.patch | `src/CardinalCommon.cpp`（B2 `/cables-page` 分页端点：handler + X-macro 注册） | Cardinal `8aa0fc7` + 01-04 应用后 |
  | 6 | 06-b3-module-copy.patch | `src/CardinalCommon.cpp`（B3 `/module-copy` 复制模块：**手动执行 + push 记录**，对齐原生 `cloneAction`） | Cardinal `8aa0fc7` + 01-05 应用后 |
  | 7 | 07-c6-write-endpoints.patch | `src/CardinalCommon.cpp`（C6：4 个写端点修为「手动执行 + push 记录」+ `/module-move` 单位语义修正） | Cardinal `8aa0fc7` + 01-06 应用后 |
  | 8 | 08-c3-log-get.patch | `src/CardinalCommon.cpp`（C3 `/log-get` 端点）+ `src/Rack/src/logger.cpp` + `src/Rack/include/logger.hpp`（进程内日志环形缓冲） | Cardinal `8aa0fc7` + 01-07 应用后（logger 两文件相对 Rack 子模块 HEAD） |
  | 9 | 09-c2-load-skipped.patch | `src/override/Engine.cpp` + `src/Rack/include/engine/Engine.hpp` + `src/Rack/src/patch.cpp` + `src/CardinalCommon.cpp`（C2 `/load` skipped 收集器 + `/load-skipped` 端点） | Cardinal `8aa0fc7` + 01-08 应用后 |
  | 10 | 10-module-add.patch | `src/CardinalCommon.cpp`（`/module-add` 端点：按 plugin\|model slug + 格坐标加模块；顺带修 JS `addModule` 的 push-only 缺陷） | Cardinal `8aa0fc7` + 01-09 应用后 |
| 11 | 11-songroll-build.patch | `plugins/Makefile`（SongRoll wildcard）+ `plugins/plugins.cpp`（`addModel(modelSongRollModule)`） | Cardinal `8aa0fc7` + 01-10 应用后 |
| 12 | 12-songroll-module.patch | SongRoll 复活+阶段2/3（**rcm-modules 子模块**，应用根 `plugins/rcm-modules`）：`.cppx` 复活为 `.cpp`（Data/Module/Transport）+ Rack 2 API 修（`rack::dsp::` 全限定）+ 阶段2引擎（10/11 端口+EOP 推进+JSON）+ 阶段3 UI 移植（Rack 1→2：VirtualWidget→Widget、onMouseDown→onButton、SequentialLayout Vec spacing、事件直改 data+push undo）+ 胶文件重写 | 子模块 HEAD `c4a243e` |
| 13 | 13-songroll-panel.patch | SongRoll **新面板**（**rcm-modules 子模块**，应用根 `plugins/rcm-modules`）：`res/SongRoll.svg` 重画为 600×380（旧 Inkscape 面板整file替换）——端口圆圈图案与真 PortWidget 坐标一一对应，消除「图案与端口不符 + 底部截断」 | 子模块 HEAD `c4a243e` + 12 应用后 |

| 14 | 14-rackwindows-nearfar.patch | rackwindows：条件 undef near/far，修复 MinGW 头宏冲突，不改 DSP 算法；应用根 plugins/rackwindows | rackwindows `60dfe5dff94b82fc42a43d971e41e64e296b0220` |
| 15 | 15-param-write-safety.patch | 参数边界与 OSC/JS 控制入口生命周期锁；两个源码和新增内部头；应用根为空（main） | 四仓库固定对象完整应用01–14后；未部署 |
| 16 | 16-songroll-history-ui.patch | SongRoll 四UI：完整 Module history 快照、同段单向显示刷新、点击读取权威数据；应用根 plugins/rcm-modules | 四仓库固定对象完整应用01–15后；未部署 |

| 17 | 17-songroll-stopfirst.patch | SongRoll 编辑/替表/非null完整或partial load/undo-redo 停推进并回第一段计数；同步及event取消 | 四固定对象完整应用01–16后；根 plugins/rcm-modules；未部署 |

第16组单独应用的历史行为：完整 undo/redo 恢复历史 running/currentSection，
并经 enterSection 重置 repeatsLeft 与该段进度；缺currentSection分支当时未改。
第17组明确覆盖该运行恢复规则：保留完整Module history快照，但编辑/替表/
非null完整或partial load/undo-redo 均停止推进，回第一段从段头计数，需手动RUN。
旧高RUN/EOP必须先low再new rise；null data不改，根本没有data不触发restore。
UI/JSON recursive_mutex与DSP try_lock协调；只读竞争冻结event电平与pulse计时，
编辑发布取消，不由UI写outputs。可延长脉宽、漏短输入边沿；在途旧sample可完成，
原子可见性不保证第N个失败sample的硬时限；两event端口不是原子事务。
不承诺硬实时、普遍线程安全或下游静音。第15、16、17组仅恢复链集成；
现役源码/EXE/resources未更新，未部署或运行验收。

★ 保守幂等与失败停止
  正向检查成功才应用；正向失败仅当严格反向检查成功且无跳过/路径筛选时
  判为 skipped。不凭错误文本、文件存在或标记认定完整安装。
  后续叠加可能令反向检查失败，此时停止待人工核对，不是要求重新应用。
  第一个 conflict/unknown/意外状态即停止；已完成组不自动回滚。
  不自动 git init/add，应用根须为真实 Git 工作树顶层（支持子模块/gitfile）。

用法（运行前显式确认目标；唯一源码根覆盖名是 CARDINAL_ROOT）:
    CARDINAL_ROOT=/path/to/isolated/source python3 replay_osc.py --check
    CARDINAL_ROOT=/path/to/isolated/source python3 replay_osc.py
    CARDINAL_ROOT=D:/Cardinal python replay_osc.py --verify

--check 仅逐组针对当前树检查，不修改目标/索引，不是依赖序列模拟；
不能据全绿推断干净树完整重放。--verify 仅端点计数与标记清单，
不认证完整 patch、源码一致性、重放、构建、运行或试听。
补丁搜索使用 CARDINAL_PATCH_DIR（可选）及脚本旁 patches/。
未显式覆盖时目标仍为 /home/lijia/Cardinal；不要把默认目标当授权。
Windows/WSL 均需目标自身的有效 Git 仓库；此脚本不自动创建仓库或改索引。
Git 子进程移除全部继承 GIT_*，仅经目标自身 .git/gitfile 发现仓库并核对顶层；
合法 separate-git-dir/submodule gitfile 可用，不接受环境绑定的外置仓库。
所有 Git 命令以 -c 固定 apply.whitespace=nowarn、apply.ignorewhitespace=no、
core.autocrlf=false、core.eol=lf、core.safecrlf=false，不改用户配置；
不自动修空白/忽略上下文空白，不经 autocrlf 隐式改换行。这仍是 Git apply
判据而非全树字节认证（例如仓库自身 attributes/filter 语义不在此作全面认证）。
CLI 仅接受无参数（原实际 apply 入口），或单个 --check / --verify / --help / -h；
未知、带值、重复或矛盾参数在任何目标操作前以退出码 2 拒绝。
"""

import os
import re
import json
import subprocess
import sys
import tempfile

# --------------------------------------------------------------------------
# 定位
# --------------------------------------------------------------------------

# 脚本自身所在目录（Windows 侧仓库里的 tools/osc_patch/）
HERE = os.path.dirname(os.path.abspath(__file__))
PATCH_DIR = os.path.join(HERE, "patches")

# 目标源码树：默认 WSL 里的 /home/lijia/Cardinal，可用环境变量覆盖
CARDINAL_ROOT = os.environ.get("CARDINAL_ROOT", "/home/lijia/Cardinal")

# patch 也可以放在别处（WSL 侧跑时通常从 /tmp/cardinal-patches/ 读）
PATCH_SEARCH = [os.environ.get("CARDINAL_PATCH_DIR", ""), PATCH_DIR]

# --------------------------------------------------------------------------
# patch 清单（顺序 = 应用顺序，不可乱）
#
# 每项 = (文件名, 描述, 应用根相对路径)
#   应用根 ""  ⇒ 在 Cardinal 源码树根应用
#   应用根 "src/Rack" ⇒ 在 Rack **子模块自己的根**应用
#     ⚠️ Rack 是 git 子模块，patch 里的路径是相对子模块根的
#        （`include/settings.hpp` 而不是 `src/Rack/include/settings.hpp`），
#        所以必须在子模块目录里跑 `git apply`，不能拿到主树跑。
# --------------------------------------------------------------------------

PATCHES = [
    ("01-osc-core.patch", "OSC 核心：28 端点实现 + 注册 + MenuBar 自动开 OSC + 截图落盘", ""),
    ("02-rack-osc.patch", "Rack 子模块：oscLoadActive + fromJson 弹窗条件化", "src/Rack"),
    ("03-build-env.patch", "构建环境：Starsea 注册 + Makefile + immintrin 兼容 + 删 lv2export", ""),
    ("04-starsea-plugin.patch", "Starsea 自建插件包（10 个文件，新增）", ""),
    ("05-b2-cables-page.patch", "B2 /cables-page 分页端点（handler + X-macro 注册）", ""),
    ("06-b3-module-copy.patch", "B3 /module-copy 复制模块（手动执行 + push 记录，对齐原生 cloneAction）", ""),
    ("07-c6-write-endpoints.patch", "C6 写端点修复（手动执行 + push 记录 + module-move 单位换算）", ""),
    ("08-c3-log-get.patch", "C3 日志环形缓冲 + /log-get 端点（含 Rack logger.cpp/hpp）", ""),
    ("09-c2-load-skipped.patch", "C2 /load skipped 收集器 + /load-skipped 端点（override/Engine + Rack + CardinalCommon）", ""),
    ("10-module-add.patch", "M1 /module-add 端点（slug + 格坐标加模块）+ JS addModule 修复", ""),
    ("11-songroll-build.patch", "SongRoll 复活·注册链：Makefile wildcard + plugins.cpp addModel", ""),
    ("12-songroll-module.patch", "SongRoll 复活+阶段2/3·模块本体（rcm-modules 子模块）：引擎（10/11 端口+EOP 推进+JSON）+ UI Rack 2 移植 + 胶文件", "plugins/rcm-modules"),
    ("13-songroll-panel.patch", "SongRoll 新面板（rcm-modules 子模块）：res/SongRoll.svg 重画 600×380，端口图案与真 PortWidget 坐标一一对应", "plugins/rcm-modules"),
    ("14-rackwindows-nearfar.patch", "rackwindows：条件 undef near/far，修复 MinGW 头宏冲突（无 DSP 算法改动）", "plugins/rackwindows"),
    ("15-param-write-safety.patch", "参数边界检查与 OSC/JS 控制入口生命周期锁（固定01–14之后，未部署）", ""),
    ("16-songroll-history-ui.patch", "SongRoll history/UI：完整快照、单向显示刷新、点击权威数据（固定01–15之后，未部署）", "plugins/rcm-modules"),
    ("17-songroll-stopfirst.patch", "SongRoll 编辑/载入/撤销重做停止首段、同步及event取消（固定01–16之后，未部署）", "plugins/rcm-modules"),
]

# 标记只供清单诊断，不参与 applied/skipped 的判定。
VERIFY_MARKS = [
    ("src/CardinalCommon.cpp", "// ==== CARDINAL-MCP-READ-PROBES-BEGIN ====", "A 组只读探针"),
    ("src/CardinalCommon.cpp", "static void cardinalOscReply(", "E1 三段式回包 helper"),
    ("src/CardinalCommon.cpp", "// ==== CARDINAL-MCP-READ-PROBES-B-BEGIN ====", "B 组读数"),
    ("src/CardinalCommon.cpp", "// ==== CARDINAL-MCP-C-GROUP-BEGIN ====", "C 组操作 + JS"),
    ("src/CardinalCommon.cpp", "// ==== CARDINAL-MCP-E2-MODULES-PAGE-BEGIN ====", "E2 分页"),
    ("src/CardinalCommon.cpp", "// ==== CARDINAL-MCP-E3-METHOD-REGISTRY-BEGIN ====", "E3 注册表抽函数"),
    ("src/CardinalCommon.cpp", "CARDINAL_OSC_METHODS(REG)", "E3 X-macro 单一真源"),
    ("src/CardinalCommon.cpp", 'REG("/modules-page"', "E2 分页端点已注册"),
    ("src/CardinalCommon.cpp", 'REG("/screenshot"', "D1 截图端点已注册"),
    ("src/CardinalCommon.cpp", 'REG("/osc-js-run"', "C 组 JS 端点已注册"),
    ("src/CardinalCommon.cpp", "osc_modules_page_handler", "E2 handler 实现"),
    ("src/CardinalCommon.cpp", "// ==== CARDINAL-MCP-B2-CABLES-PAGE-BEGIN ====", "B2 /cables-page"),
    ("src/CardinalCommon.cpp", 'REG("/cables-page"', "B2 分页端点已注册"),
    ("src/CardinalCommon.cpp", "osc_cables_page_handler", "B2 handler 实现"),
    ("src/CardinalCommon.cpp", "// ==== CARDINAL-MCP-B3-MODULE-COPY-BEGIN ====", "B3 /module-copy"),
    ("src/CardinalCommon.cpp", 'REG("/module-copy"', "B3 复制端点已注册"),
    ("src/CardinalCommon.cpp", "osc_module_copy_handler", "B3 handler 实现"),
    ("src/CardinalCommon.cpp", "// ==== CARDINAL-MCP-C3-LOG-GET-BEGIN ====", "C3 /log-get"),
    ("src/CardinalCommon.cpp", 'REG("/log-get"', "C3 日志端点已注册"),
    ("src/CardinalCommon.cpp", "osc_log_get_handler", "C3 handler 实现"),
    ("src/Rack/src/logger.cpp", "logRingPush", "C3 环形缓冲"),
    ("src/CardinalCommon.cpp", "// ==== CARDINAL-MCP-C2-LOAD-SKIPPED-BEGIN ====", "C2 /load-skipped"),
    ("src/CardinalCommon.cpp", 'REG("/load-skipped"', "C2 skipped 端点已注册"),
    ("src/override/Engine.cpp", "addLoadSkip", "C2 收集器插桩"),
    ("src/CardinalCommon.cpp", "// ==== CARDINAL-MCP-MODULE-ADD-BEGIN ====", "M1 /module-add"),
    ("src/CardinalCommon.cpp", 'REG("/module-add"', "M1 加模块端点已注册"),
    ("src/override/MenuBar.cpp", "startRemoteServer", "MenuBar 自动开 OSC"),
    ("src/override/Window.cpp", "g_screenshotFilePath", "截图落盘"),
    ("src/Rack/src/settings.cpp", "oscLoadActive", "Rack oscLoadActive 定义"),
    ("src/Rack/src/patch.cpp", "oscLoadActive", "Rack fromJson 条件化"),
    ("plugins/Starsea/src/MiniArranger.cpp", "StarseaMiniArranger", "MiniArranger 模块"),
    ("plugins/Starsea/src/MiniArrangerExpander.cpp", "MiniArrangerExpander", "扩展器模块"),
    ("plugins/Makefile", "rcm-modules/src/SongRoll/*.cpp", "SongRoll 编译规则"),
    ("plugins/plugins.cpp", "addModel(modelSongRollModule)", "SongRoll addModel"),
    ("plugins/rcm-modules/plugin.json", '"rcm-songroll"', "SongRoll manifest 条目"),
    ("plugins/rcm-modules/src/SongRollModule.cpp", "modelSongRollModule", "SongRoll Model 定义（胶文件）"),
]

# OSC 端点总数（M1 后 = 33）
EXPECTED_ENDPOINTS = 33


# --------------------------------------------------------------------------
# 工具
# --------------------------------------------------------------------------

def die(msg, code=1):
    sys.stderr.write("ERROR: %s\n" % msg)
    sys.exit(code)


def find_patch_dir():
    """找到装着 .patch 文件的目录。"""
    for cand in PATCH_SEARCH:
        if not cand:
            continue
        if os.path.isdir(cand) and any(
                os.path.exists(os.path.join(cand, n)) for n, _, _ in PATCHES):
            return cand
    raise FileNotFoundError("找不到 patch 目录。已查：\n  " + "\n  ".join(
        c for c in PATCH_SEARCH if c) + "\n用 CARDINAL_PATCH_DIR 指定补丁目录。")


def run_git(args, cwd):
    """Run read/check/apply commands, retaining complete diagnostics per stream."""
    # Command-scoped policy, identical for check/reverse/actual; never rewrite
    # whitespace, relax context, or normalize LF through user autocrlf settings.
    policy = ["-c", "apply.whitespace=nowarn", "-c", "apply.ignorewhitespace=no",
              "-c", "core.autocrlf=false", "-c", "core.eol=lf", "-c", "core.safecrlf=false"]
    result = {"command": ["git"] + policy + args, "cwd": str(cwd), "returncode": None,
              "stdout": "", "stderr": "", "exception": None}
    try:
        # Discover only from cwd's own .git/gitfile, not an inherited repository,
        # index, config injection, ceiling, or alternate object store binding.
        env = {key: value for key, value in os.environ.items()
               if not key.upper().startswith("GIT_")}
        env.update(LC_ALL="C", LANG="C")
        p = subprocess.run(result["command"], cwd=cwd, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", env=env)
        result.update(returncode=p.returncode, stdout=p.stdout or "", stderr=p.stderr or "")
    except Exception as exc:
        result["exception"] = repr(exc)
        for field in ("stdout", "stderr"):
            value = getattr(exc, field, None)
            if value is not None:
                result[field] = value.decode("utf-8", errors="replace") if isinstance(value, bytes) else str(value)
    return result


def read_text(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def endpoint_count(root):
    """数一下注册了多少个 OSC 端点。

    ⚠️ E3 之后端点注册走 **X-macro** `REG("/path", "types", handler)`，
    不再是一行一个 `lo_server_add_method(...)` ⇒ 只能数 `REG("` 调用。
    （旧写法数 add_method 会得到 0 或 2，不是 28。）
    """
    path = os.path.join(root, "src", "CardinalCommon.cpp")
    if not os.path.exists(path):
        return 0
    src = read_text(path)
    n = 0
    for line in src.splitlines():
        s = line.strip()
        # 只认注册表里的行：REG("/xxx", ...)，排除 #define REG(...) 那一行
        if s.startswith("REG(\""):
            n += 1
    return n


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------

def apply_one(root, patch_dir, name, desc, apply_root_rel, dry_run=False):
    """应用一个 patch。返回 (状态, 详情)。状态 ∈ applied / skipped / conflict。

    apply_root_rel = "" 表示在 root 应用；否则在 root/apply_root_rel 应用
    （Rack 子模块的情况）。
    """
    detail = {"message": desc, "commands": [], "apply_attempted": False}

    def failure(message):
        detail["message"] = message
        return "conflict", detail

    def command(args):
        result = run_git(args, apply_root)
        detail["commands"].append(result)
        return result

    def unsafe(result):
        # Output is a veto, never positive evidence of success. Check both streams
        # at every phase, including rc=0 partial/path-filtered operations.
        output = result["stdout"] + "\n" + result["stderr"]
        # Match diagnostic records, never words inside "Checking patch <path>"
        # or hunk contents. Preserve vetoes for both real Git and explicit
        # partial/filter diagnostics from wrappers, at the start of a line.
        diagnostic = r"^(?:error: |warning: )?(?:Skipped patch |Skipping (?:patch |path )|" \
                     r"excluded path |including only |path[- ]filtered(?: |$)|partially applied(?:[ .]|$))"
        return result.get("exception") or re.search(diagnostic, output, re.I | re.M)

    ppath = os.path.abspath(os.path.join(patch_dir, name))
    if not os.path.isfile(ppath):
        return failure("patch 文件不存在：%s" % ppath)
    apply_root = os.path.abspath(os.path.join(root, apply_root_rel))
    if not os.path.isdir(apply_root):
        return failure("应用根不存在：%s" % apply_root)

    if not os.path.exists(os.path.join(apply_root, ".git")):
        return failure("应用根须有自身 .git 目录或 gitfile；不接受继承环境绑定的仓库。")
    repo = command(["rev-parse", "--show-toplevel"])
    if (repo["returncode"] != 0 or repo.get("exception") or repo["stderr"] or
            os.path.normcase(os.path.realpath(repo["stdout"].strip())) !=
            os.path.normcase(os.path.realpath(apply_root))):
        return failure("应用根必须是实际 Git 工作树顶层；不自动 init/add，用户索引不作初始化。")

    forward = command(["apply", "--check", "-v", ppath])
    if unsafe(forward):
        return failure("正向检查异常或跳过/筛选部分路径；不能证明完整应用。")
    if forward["returncode"] == 0:
        if dry_run:
            return "would_apply", detail
        detail["apply_attempted"] = True
        actual = command(["apply", "-v", ppath])
        if unsafe(actual) or actual["returncode"] != 0:
            return failure("实际 apply 失败或部分跳过；此组可能已部分改动，未自动回滚。")
        return "applied", detail
    if forward["returncode"] != 1:
        return failure("git 正向检查执行失败；停止，不尝试后续操作。")

    reverse = command(["apply", "--check", "-R", "-v", ppath])
    if unsafe(reverse):
        return failure("反向检查异常或部分跳过；不能证明已完整应用。")
    if reverse["returncode"] == 0:
        detail["message"] = "已应用过（严格反向检查确认，幂等跳过）"
        return "skipped", detail
    return failure("正反向检查均不能证明此组状态。后续叠加可能破坏反向检查；"
                   "这不是要求重新应用，请人工核对完整差异。")


def verify(root):
    """校验端点与标记是否齐全。返回 (ok, 问题列表, 端点数)。"""
    problems = []
    for rel, mark, desc in VERIFY_MARKS:
        path = os.path.join(root, rel)
        if not os.path.exists(path):
            problems.append("缺文件：%s（%s）" % (rel, desc))
            continue
        if mark not in read_text(path):
            problems.append("缺标记：%s 里的 %r（%s）" % (rel, mark, desc))

    n_ep = endpoint_count(root)
    if n_ep != EXPECTED_ENDPOINTS:
        problems.append("端点数 = %d，期望 %d" % (n_ep, EXPECTED_ENDPOINTS))

    return (not problems), problems, n_ep


def main():
    argv = sys.argv[1:]
    # Only the documented zero-value modes are accepted. No abbreviations,
    # ignored positionals, conflicting modes, or duplicate flags may reach apply.
    if len(argv) > 1 or (argv and argv[0] not in ("--check", "--verify", "--help", "-h")):
        sys.stderr.write("ERROR: expected no arguments, --check, --verify, or --help (one mode only)\n")
        return 2
    dry_run = "--check" in argv
    do_verify_only = "--verify" in argv

    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0

    root = CARDINAL_ROOT
    print("目标源码树 : %s" % root)
    print("清单验收范围：仅端点计数与标记清单；不认证完整 patch、重放、构建或运行。")
    if dry_run:
        print("注意：--check 逐组检查当前树，不是依赖序列模拟；不能据全绿推断干净树完整重放。")

    if do_verify_only:
        try:
            ok, problems, n_ep = verify(root)
        except Exception as exc:
            print("清单检查执行异常：%r；未验收。" % exc)
            return 1
        print("端点数     : %d / %d" % (n_ep, EXPECTED_ENDPOINTS))
        print("标记清单检查：%s" % ("通过" if ok else "失败"))
        for problem in problems:
            print("  - %s" % problem)
        return 0 if ok else 1

    resolution_error = None
    try:
        patch_dir = find_patch_dir()
    except Exception as exc:
        patch_dir, resolution_error = None, repr(exc)
    print("patch 目录 : %s" % patch_dir)
    groups = {key: [] for key in ("applied", "skipped", "failed", "notattempted", "would_apply")}
    for index, (name, desc, apply_root_rel) in enumerate(PATCHES):
        try:
            if resolution_error is not None:
                status, detail = "conflict", {"message": "补丁目录查找失败", "exception": resolution_error}
            else:
                status, detail = apply_one(root, patch_dir, name, desc, apply_root_rel,
                                           dry_run=dry_run)
        except Exception as exc:
            status, detail = "unknown", {"message": "组执行异常；副作用未知", "exception": repr(exc)}
        allowed = ("would_apply", "skipped") if dry_run else ("applied", "skipped")
        print("%s %s [%s]" % (name, status, apply_root_rel or "."))
        if status not in allowed:
            groups["failed"].append(name)
            groups["notattempted"] = [p[0] for p in PATCHES[index + 1:]]
            print(json.dumps(detail, ensure_ascii=False, indent=2))
            break
        groups[status].append(name)

    for key, names in groups.items():
        print("%s (%d): %s" % (key, len(names), ", ".join(names) or "-"))
    if groups["failed"]:
        if dry_run:
            print("--check 已停止：未真正改动目标文件或索引；不能证明完整重放。")
        else:
            print("停止：先前组可能已生效，失败组副作用须核对；未自动回滚，未验收。")
        return 1
    if dry_run:
        print("--check 模式：未真正改动目标文件或索引。")
        return 0

    try:
        ok, problems, n_ep = verify(root)
    except Exception as exc:
        print("校验执行异常：%r；先前组可能已生效，未验收；未自动回滚。" % exc)
        return 1
    print("端点数     : %d / %d" % (n_ep, EXPECTED_ENDPOINTS))
    if ok:
        print("端点与标记清单检查通过。")
        return 0
    print("清单校验失败：先前组可能已生效但未验收；未自动回滚。")
    for problem in problems:
        print("  - %s" % problem)
    return 1


if __name__ == "__main__":
    sys.exit(main())
