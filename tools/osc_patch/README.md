# OSC 改动重放 · patch 是唯一真相

> 建立：2026-10-21 · 用途：**把 30 个 OSC 端点的 C++ 改动从「只活在 WSL 工作区」变成「进 git、可重放、可审计」**

---

## 一、为什么有这份东西

在 2026-10-21 之前，本项目对 Cardinal 源码的改动**只存在于 WSL 工作区**（`/home/lijia/Cardinal`），
**不在任何 git 仓库里**。后果：

- 一次 `git checkout .` ⇒ **30 个端点的实现全没了**（约 2100 行）。
- `src/override/MenuBar.cpp` 的「延后 120 帧自动开 OSC」补丁
  **不在任何注入器里** ⇒ 连「重跑注入器」都救不回来。
- 企划 2 的自建插件包 `plugins/Starsea/`（MiniArranger，10 个文件 2549 行）同样是未跟踪文件，
  一次误删就没了。

现在：改动的**真相**以 `patches/*.patch` 的形式存在本仓库（`Lijiahong77/cardinal-mcp`），
由 `replay_osc.py` 重放回源码树。

---

## 二、目录结构

```
tools/osc_patch/
├── README.md                    ← 本文件
├── replay_osc.py                ⭐ 统一重放脚本（唯一入口）
├── patches/                     ⭐ 改动的真相（git 跟踪）
│   ├── 01-osc-core.patch          28 端点实现 + 注册 + MenuBar + 截图落盘
│   ├── 02-rack-osc.patch          Rack 子模块：oscLoadActive + fromJson 条件化
│   ├── 03-build-env.patch         构建环境：Starsea 注册 + Makefile + immintrin + 删 lv2export
│   ├── 04-starsea-plugin.patch    Starsea 插件包（10 个文件，新增）
│   ├── 05-b2-cables-page.patch    B2 /cables-page 分页端点（handler + 注册）
│   ├── 06-b3-module-copy.patch    B3 /module-copy 复制模块（handler + 注册）
│   ├── 07-c6-write-endpoints.patch C6 写端点修复（4 端点手动执行化）
│   ├── 08-c3-log-get.patch        C3 日志环形缓冲 + /log-get（含 Rack logger）
│   ├── 09-c2-load-skipped.patch   C2 /load skipped 收集器 + /load-skipped
│   ├── 10-module-add.patch       M1 /module-add（按 slug + 格坐标加模块）
│   ├── 11-songroll-build.patch    SongRoll 复活·注册链（Makefile wildcard + addModel）
│   ├── 12-songroll-module.patch   SongRoll 模块本体（引擎 + UI Rack 2 移植 + 胶文件）
│   └── 13-songroll-panel.patch    SongRoll 新面板（res/SongRoll.svg 重画 600×380）
├── inject_osc_read.py           ┐
├── inject_osc_b.py              │
├── inject_osc_c.py              ├─ 历史记录：记录每个批次当初改了什么
├── inject_osc_d.py              │  （**不再是重放路径**，见 §五；已知坑见
├── inject_osc_e2.py             │  `injectors-LEGACY-NOTES.md`）
├── inject_osc_e3.py             ┘
├── osc_read_handlers.cpp.inc    ┐
├── osc_read_b_handlers.cpp.inc  ├─ 各批次的 handler 源码片段
├── osc_ops_c_handlers.cpp.inc   │  （阅读价值，patch 里已含最终形态）
└── osc_js_handlers.cpp.inc      ┘
```

---

## 三、怎么用

### 3.1 日常：源码树已经是改好的状态，什么都不用做

改动的真相已在 git 里，源码树也已改好。**不需要重放。**

### 3.2 灾难恢复：源码树被 `git checkout .` 冲掉了

```bash
# ① 把 patch 拷进 WSL（Windows 侧仓库 → WSL）
mkdir -p /home/lijia/_patches
cp /mnt/d/Cardinal/tools/osc_patch/patches/*.patch /home/lijia/_patches/

# ② 预检（不改任何东西，看能不能干净应用）
cd /home/lijia
CARDINAL_ROOT=/home/lijia/Cardinal CARDINAL_PATCH_DIR=/home/lijia/_patches \
  python3 /mnt/d/Cardinal/tools/osc_patch/replay_osc.py --check

# ③ 真重放
CARDINAL_ROOT=/home/lijia/Cardinal CARDINAL_PATCH_DIR=/home/lijia/_patches \
  python3 /mnt/d/Cardinal/tools/osc_patch/replay_osc.py

# ④ 只校验现状（不重放）
CARDINAL_ROOT=/home/lijia/Cardinal CARDINAL_PATCH_DIR=/home/lijia/_patches \
  python3 /mnt/d/Cardinal/tools/osc_patch/replay_osc.py --verify
```

脚本会**自动校验** 30 个端点注册 + 18 个关键标记是否齐全，不齐就报错。

### 3.3 在干净副本上做可复现验证

```bash
cd /home/lijia/Cardinal
mkdir -p /home/lijia/_replay
git archive 8aa0fc7 | tar -x -C /home/lijia/_replay   # 干净 upstream 树
cd /home/lijia/_replay && git init -q .
mkdir -p src/Rack
cd /home/lijia/Cardinal/src/Rack && git archive HEAD | tar -x -C /home/lijia/_replay/src/Rack

CARDINAL_ROOT=/home/lijia/_replay CARDINAL_PATCH_DIR=/home/lijia/_patches \
  python3 /home/lijia/_replay_osc.py
```

---

## 四、patch 的基线

| patch | 基线 | 说明 |
|---|---|---|
| `01-osc-core.patch` | Cardinal `8aa0fc7`（"Fix build"） | 主树 |
| `02-rack-osc.patch` | Rack 子模块当前 HEAD | ⚠️ 路径**相对子模块根**（`include/settings.hpp` 而非 `src/Rack/include/settings.hpp`）⇒ 必须在 `src/Rack/` 里 apply |
| `03-build-env.patch` | Cardinal `8aa0fc7` | 含一个**文件删除**（`lv2export/plugins/aubileinstruments-macro-osc-2.cpp`） |
| `04-starsea-plugin.patch` | Cardinal `8aa0fc7` | 纯新增（10 个文件） |
| `05-b2-cables-page.patch` | Cardinal `8aa0fc7` + 01-04 应用后 | B2 `/cables-page` 分页端点（handler + X-macro 注册） |
| `06-b3-module-copy.patch` | Cardinal `8aa0fc7` + 01-05 应用后 | B3 `/module-copy` 复制模块（handler + X-macro 注册） |
| `07-c6-write-endpoints.patch` | Cardinal `8aa0fc7` + 01-06 应用后 | C6：`/cable-add` `/cable-remove` `/module-move` `/module-remove` 修成「手动执行 + push 记录」+ `/module-move` 格→px 单位换算 |
| `08-c3-log-get.patch` | Cardinal `8aa0fc7` + 01-07 应用后 | C3：`src/CardinalCommon.cpp`（`/log-get` 端点）+ `src/Rack/src/logger.cpp` + `src/Rack/include/logger.hpp`（进程内日志环形缓冲，2000 条） |
| `09-c2-load-skipped.patch` | Cardinal `8aa0fc7` + 01-08 应用后 | C2：`src/override/Engine.cpp`（**Cardinal 真正编译的 Engine 副本**）+ `src/Rack/include/engine/Engine.hpp` + `src/Rack/src/patch.cpp` + `src/CardinalCommon.cpp`（`/load` skipped 收集器 + `/load-skipped` 端点） |
| `10-module-add.patch` | Cardinal `8aa0fc7` + 01-09 应用后 | M1：`src/CardinalCommon.cpp`——`/module-add "sii"`（plugin\|model slug + 格坐标 → 手动执行加模块 + push 记录可 undo）+ 顺带修 JS `cardinal.addModule` 的 push-only 缺陷 |
| `11-songroll-build.patch` | Cardinal `8aa0fc7` + 01-10 应用后 | SongRoll 复活·注册链：`plugins/Makefile`（SongRoll wildcard）+ `plugins/plugins.cpp`（`addModel(modelSongRollModule)`） |
| `12-songroll-module.patch` | rcm-modules 子模块 HEAD `c4a243e` | SongRoll 模块本体（**应用根 `plugins/rcm-modules`**）：`.cppx`→`.cpp` 复活 + Rack 2 API 修 + 阶段2 引擎（10/11 端口、EOP 推进、JSON）+ 阶段3 UI 移植 + 胶文件 |
| `13-songroll-panel.patch` | rcm-modules 子模块 HEAD `c4a243e` + 12 应用后 | SongRoll 新面板（**应用根 `plugins/rcm-modules`**）：`res/SongRoll.svg` 重画 600×380（旧 Inkscape 面板整file替换），端口圆圈图案与真 PortWidget 坐标一一对应 |

⚠️ **upstream 变了 patch 可能失效**。届时 `git apply --check` 会明确报冲突，
脚本**立刻停下**（绝不 `--reject` 硬塞）—— 需人工看差异。

---

## 五、为什么用 patch 而不是那 6 个注入器

1. **注入器覆盖不全**。E1 的 `cardinalOscReply` helper（`src/CardinalCommon.cpp:406`）
   和 `MenuBar.cpp` 的自动开 OSC 补丁**都不在任何注入器里** ⇒ 跑完 6 个注入器也凑不出现在的树。
   （实测：patch 重放后 22/22 文件与现状**逐字节一致**。）
2. **注入器依赖「唯一锚点」匹配**，upstream 一改锚点就失效；patch 靠行号 + 上下文，
   冲突时 git 明确报错而不是静默插错位置。
3. **patch 可审计**：是纯文本 diff，能在 PR 里逐行 review、能 `git apply -R` 回滚。

⇒ 6 个注入器**保留但降级**为「历史记录」：它们记录了每个批次当初改了什么、有哪些设计教训
（血泪注释），有阅读价值，但**不再是重放路径**。

---

## 六、🔴 三个踩过的坑（写在这里免得重犯）

### 6.1 `git apply` 在非 git 目录里会「静默跳过」

Rack 是 git 子模块。在「干净副本」里它可能只是个普通目录（没有 `.git`）⇒
`git apply` 把它当 gitlink，输出 `Skipped patch 'include/settings.hpp'` 并**返回 0（假装成功）**。

**⇒ 脚本现在会为应用根自动 `git init`，并显式检测 "skipped patch" 字样 ⇒ 当失败处理。**

### 6.2 幂等判据不能用报错文本

`git apply` 对「已经应用过」和「真冲突」报**同样的** `patch does not apply`。
靠文本判断会把「已应用」误报成「冲突」。

**⇒ 脚本用反向检查判幂等**：`git apply --check -R` 成功 ⇒ 说明改动已在文件里 ⇒ 跳过。

### 6.3 E3 之后端点数不能数 `add_method`

E3 把端点注册改成 X-macro `REG("/path", "types", handler)`，
不再是一行一个 `lo_server_add_method(...)`。
**⇒ 数 `REG("` 开头（且排除 `#define REG(` 那一行）才等于 30。**

---

## 七、当前状态（2026-10-21 实测）

| 验证项 | 结果 |
|---|---|
| 干净 upstream 副本上重放 | ✅ 10 组全部应用（01-04 实测；05-10 见下） |
| 应用后端点数 | ✅ **33 / 33** |
| 关键标记 | ✅ 29 项全齐 |
| **与 WSL 现状树逐字节比对** | ✅ **22 / 22 一致，0 不一致**（含 Starsea 10 文件 + 1 个删除文件状态） |
| 幂等重跑 | ✅ 10 组全部「已存在」跳过，**零破坏**（真实树 git status 前后完全一致） |
| 在真实 WSL 树上跑 | ✅ 零破坏（17 项改动状态不变） |
| **B2 patch（2026-10-21 下午）** | ✅ 反打当前树 + 正打 before 副本**双向** `git apply --check` 通过；WINE 探针 **11/11**；MCP 层端到端 **8/8**；exe 已部署（MD5 `32d3cfbc…`） |
| **B3 patch（2026-10-21 下午）** | ✅ 双向 `git apply --check` 通过；WINE 探针 **12/13**（唯一 FAIL 是 T8：既有 `/cable-add` 不生效的实锤，非 B3 问题）；MCP 层端到端 **7/7**；exe 已部署（MD5 `751cdaea…`） |
| **M1 patch（2026-10-22 早上）** | ✅ 双向 `git apply --check` 通过；WINE 探针 **10/10**（41→42 模块、undo/redo 闭环、未知插件/未知型号/无分隔符三种错法全 `err:E_NO_MODEL`、失败调用零副作用）；MCP 层端到端 **5/5**；exe 已部署（MD5 `2c2ce802…`）。🔴 坑：typespec 必须与参数顺序一致（`"sii"` 不是 `"ssi"`，不匹配 ⇒ liblo 不派发 ⇒ 端点全哑）；🔴 `loadTemplate()` 不能在 OSC 侧调（人类路径独有，preset 应用碰 UI ⇒ undo 后 OSC 失联） |
| **C2 patch（2026-10-22 早上）** | ✅ 双向 `git apply --check` 通过（4 文件段：override/Engine.cpp + Rack Engine.hpp/patch.cpp + CardinalCommon）；WINE 探针 **6/6**；MCP 层端到端 **5/5**（损坏 patch ⇒ 1 module + 16 cable = 17 条 skip，逐条 reason 齐）；exe 已部署（MD5 `bf55806b…`）。🔴 关键点：**Cardinal 编译的是 `src/override/Engine.cpp` 而非 Rack 原版**（改错文件 ⇒ 链接期 undefined reference） |
| **C3 patch（2026-10-22 早上）** | ✅ 双向 `git apply --check` 通过（3 文件段：CardinalCommon + Rack logger.cpp/hpp）；WINE 探针 **8/8**（最老读/增量不重叠/非法参数/limit 64/超界 from）；MCP 层端到端 **5/5**；exe 已部署（MD5 `d17ab013…`）。⚠️ Rack 层改动 ⇒ 需 `make rack.a` 重编 |
| **C6 patch（2026-10-21 深夜）** | ✅ 双向 `git apply --check` 通过；WINE 探针 **14/14**（4 端点全部真实生效 + undo/redo 闭环 + B3 回归）；MCP 层端到端 **7/7**；exe 已部署（MD5 `836aea28…`）。🔴 附带修掉 `/module-move` 单位语义 bug（文档说格、实现当 px，差 15 倍——该端点此前从不生效故零兼容负担）；🔴 module-move 的位置真值 WINE 下不可直验（autosave 周期落盘在 WINE 不触发，已实验证实）⇒ 归真机 A1 |

---

## 八、相关文档

- 编译步骤：`HANDOFF.md` §2.4
- 端点清单与分组：`docs/TODO-BACKLOG.md` 第三章
- MCP 侧工具：`tools/cardinal_mcp.py`（55 个工具）
