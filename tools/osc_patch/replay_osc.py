#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""replay_osc.py —— 把全部 OSC 改动一次性重放到 Cardinal 源码树

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

★ 覆盖范围（4 组 patch，按依赖顺序）
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

★ 幂等
  每一组都先 `git apply --check`：能干净应用 ⇒ 跳过（已应用过）；
  报 "already applied" ⇒ 也跳过；**报冲突 ⇒ 立刻停下报错**，绝不 `--reject` 硬塞。

用法（在 WSL 里跑；patch 文件在 Windows 侧仓库，需要先拷过去）:
    # 0) 把 patch 拷进 WSL
    cp /mnt/d/Cardinal/tools/osc_patch/patches/*.patch /tmp/cardinal-patches/

    # 1) 预检：看能不能干净应用（不改任何东西）
    python3 replay_osc.py --check

    # 2) 真正重放
    python3 replay_osc.py

    # 3) 只重放到某个目录（干净副本验证用）
    CARDINAL_SRC=/tmp/clean python3 replay_osc.py

    # 4) 校验现状（不重放，只报告端点是否齐全）
    python3 replay_osc.py --verify

★ 为什么脚本在 Windows 侧仓库、却要在 WSL 里跑
  patch 的目标路径是 Linux 路径（`src/CardinalCommon.cpp` 相对 Cardinal 源码树根），
  且 `git apply` 必须在真实 git 仓库里跑。Windows 侧仓库 `D:/Cardinal` 只是
  **patch 的存放处**，不是应用目标。
"""

import os
import shutil
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
]

# 幂等兜底标记：多层 patch 叠同一文件时（01/05/06/07/09/10 全改
# CardinalCommon.cpp），早期 patch 的**反 apply 会被后期 patch 的叠加
# 推挤破坏**（2026-10-24 实测：01 失败在 :180、06 在 :1592、08/09 在 :1664，
# 全是后续组追加区）⇒ 反 apply 判据对这些组误报冲突。
# 兜底 = 该组的**独有标记**全部在树里 ⇒ 改动确实在，判 skipped。
# 路径相对 CARDINAL_ROOT（同 VERIFY_MARKS）。只给实测有叠加的组配。
PATCH_MARKS = {
    "01-osc-core.patch": [
        ("src/CardinalCommon.cpp", "CARDINAL-MCP-READ-PROBES-BEGIN"),
        ("src/override/MenuBar.cpp", "oscAutostartEnabled"),
    ],
    "06-b3-module-copy.patch": [
        ("src/CardinalCommon.cpp", 'REG("/module-copy"'),
    ],
    "08-c3-log-get.patch": [
        ("src/CardinalCommon.cpp", 'REG("/log-get"'),
    ],
    "09-c2-load-skipped.patch": [
        ("src/override/Engine.cpp", "addLoadSkip"),
    ],
}

# 校验点：应用完后这些标记必须存在（防止 patch 被裁剪/漏 apply）
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
    ("plugins/rcm-modules/src/SongRoll/SongRollModule.cpp", "modelSongRollModule", "SongRoll 引擎实现"),
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
    die("找不到 patch 目录。已查：\n  " + "\n  ".join(
        c for c in PATCH_SEARCH if c) +
        "\n请先 `cp /mnt/d/Cardinal/tools/osc_patch/patches/*.patch /tmp/cardinal-patches/`")
    return None


def run_git(args, cwd):
    """跑 git，返回 (rc, stdout+stderr)。"""
    p = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


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
    ppath = os.path.join(patch_dir, name)
    if not os.path.exists(ppath):
        return "conflict", "patch 文件不存在：%s" % ppath

    apply_root = os.path.join(root, apply_root_rel) if apply_root_rel else root
    if not os.path.isdir(apply_root):
        return "conflict", "应用根不存在：%s" % apply_root

    # 🔴 git apply 需要在 **git 仓库** 里跑。Rack 是子模块；在"干净副本"里它可能
    #    只是一个普通目录（没有 .git）⇒ 此时 git apply 会把它当 gitlink，
    #    输出 "Skipped patch 'include/settings.hpp'" 并**静默跳过**（rc=0，假装成功！）
    #    ⇒ 必须先给它建个仓库，否则 patch 悄悄没生效。
    if not os.path.exists(os.path.join(apply_root, ".git")):
        if not dry_run:
            rc0, out0 = run_git(["init", "-q", "."], apply_root)
            if rc0 != 0:
                return "conflict", "无法在 %s 建 git 仓库：\n%s" % (apply_root, out0)
            run_git(["add", "-A"], apply_root)
            print("           （已为 %s 建 git 仓库，Rack 子模块必需）"
                  % apply_root_rel)

    rc, out = run_git(["apply", "--check", "-v", ppath], apply_root)
    # 🔴 假成功检测：git apply 在某些情况下会输出 "Skipped patch 'xxx'" 并返回 0，
    #    实际什么都没改。必须当成失败，否则 patch 悄悄丢失。
    if "skipped patch" in out.lower():
        return "conflict", ("git apply 跳过了部分文件（假成功）：\n%s\n"
                           "通常是该目录被当成 gitlink；给它建个 git 仓库即可。" % out)

    if rc == 0:
        if dry_run:
            return "would_apply", desc
        rc2, out2 = run_git(["apply", "-v", ppath], apply_root)
        if rc2 != 0:
            return "conflict", "apply 失败：\n%s" % out2
        return "applied", desc

    # ---- 幂等：正向 apply 失败，可能是"已经应用过了" ----
    # 🔴 判据不能用报错文本（git 对"已应用"和"真冲突"报同样的
    #    "patch does not apply"）。可靠办法 = **反向检查**：
    #    patch 能否被 reverse-apply ⇒ 说明改动已在文件里。
    rc_rev, _ = run_git(["apply", "--check", "-R", ppath], apply_root)
    if rc_rev == 0:
        return "skipped", "已应用过（反向检查确认，幂等跳过）"

    # ---- 幂等兜底：反 apply 被后续 patch 叠加推挤时（PATCH_MARKS 注释），
    #      用该组独有标记判定「改动是否确实在树里」
    marks = PATCH_MARKS.get(name, [])
    if marks:
        missing = [(rel, mk) for rel, mk in marks
                   if mk not in read_text(os.path.join(root, rel))]
        if not missing:
            return "skipped", "已应用过（标记兜底：反 apply 被后续叠加推挤，但独有标记俱在）"

    # 真的冲突
    low = out.lower()
    if "already exists" in low or "already applied" in low:
        return "skipped", "已应用过（幂等跳过）"
    return "conflict", "冲突，未应用：\n%s" % out


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
    dry_run = "--check" in argv
    do_verify_only = "--verify" in argv

    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0

    root = CARDINAL_ROOT
    if not os.path.isdir(os.path.join(root, ".git")):
        # git worktree / 裸 .git 文件都算
        if not os.path.exists(os.path.join(root, ".git")):
            die("目标不是 git 仓库：%s\n用 CARDINAL_ROOT=... 指定。" % root)

    patch_dir = find_patch_dir()
    print("目标源码树 : %s" % root)
    print("patch 目录 : %s" % patch_dir)
    print("")

    if do_verify_only:
        ok, problems, n_ep = verify(root)
        print("端点数     : %d / %d" % (n_ep, EXPECTED_ENDPOINTS))
        if ok:
            print("\n✅ 校验通过：33 端点 + 所有标记齐全")
            return 0
        print("\n❌ 校验不通过：")
        for p in problems:
            print("  - %s" % p)
        return 1

    # ---- 重放 ----
    results = []
    for name, desc, apply_root_rel in PATCHES:
        status, detail = apply_one(root, patch_dir, name, desc, apply_root_rel,
                                   dry_run=dry_run)
        results.append((name, desc, status, detail))
        icon = {"applied": "✔ 已应用", "would_apply": "○ 可应用",
                "skipped": "= 已存在", "conflict": "✘ 冲突"}.get(status, status)
        scope = ("[%s] " % apply_root_rel) if apply_root_rel else ""
        print("%-10s %-28s %s%s" % (icon, name, scope, desc))
        if status == "conflict":
            print("           %s" % detail)

    print("")
    conflicts = [r for r in results if r[2] == "conflict"]
    if conflicts:
        print("❌ %d 组冲突，**未强行应用**（避免把源码搞坏）。"
              "请人工检查上面的详情。" % len(conflicts))
        return 1

    applied = [r for r in results if r[2] in ("applied", "would_apply")]
    skipped = [r for r in results if r[2] == "skipped"]
    print("合计：%d 组应用 / %d 组已存在" % (len(applied), len(skipped)))

    if dry_run:
        print("\n（--check 模式：未真正改动任何文件）")
        return 0

    # ---- 应用后自动校验 ----
    ok, problems, n_ep = verify(root)
    print("")
    print("端点数     : %d / %d" % (n_ep, EXPECTED_ENDPOINTS))
    if ok:
        print("✅ 校验通过：33 端点 + 所有标记齐全")
        print("\n下一步：编译（见 HANDOFF.md §2.4）")
        return 0
    print("❌ 校验不通过：")
    for p in problems:
        print("  - %s" % p)
    return 1


if __name__ == "__main__":
    sys.exit(main())
