# OSC 改动重放 · patch 是唯一真相

> 建立：2026-10-21 · 用途：**把 28 个 OSC 端点的 C++ 改动从「只活在 WSL 工作区」变成「进 git、可重放、可审计」**

---

## 一、为什么有这份东西

在 2026-10-21 之前，本项目对 Cardinal 源码的改动**只存在于 WSL 工作区**（`/home/lijia/Cardinal`），
**不在任何 git 仓库里**。后果：

- 一次 `git checkout .` ⇒ **28 个端点的实现全没了**（约 2100 行）。
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
│   └── 04-starsea-plugin.patch    Starsea 插件包（10 个文件，新增）
├── inject_osc_read.py           ┐
├── inject_osc_b.py              │
├── inject_osc_c.py              ├─ 历史记录：记录每个批次当初改了什么
├── inject_osc_d.py              │  （**不再是重放路径**，见 §五）
├── inject_osc_e2.py             │
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

脚本会**自动校验** 28 个端点注册 + 14 个关键标记是否齐全，不齐就报错。

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
**⇒ 数 `REG("` 开头（且排除 `#define REG(` 那一行）才等于 28。**

---

## 七、当前状态（2026-10-21 实测）

| 验证项 | 结果 |
|---|---|
| 干净 upstream 副本上重放 | ✅ 4 组全部应用 |
| 应用后端点数 | ✅ **28 / 28** |
| 关键标记 | ✅ 14 项全齐 |
| **与 WSL 现状树逐字节比对** | ✅ **22 / 22 一致，0 不一致**（含 Starsea 10 文件 + 1 个删除文件状态） |
| 幂等重跑 | ✅ 4 组全部「已存在」跳过，**零破坏**（真实树 git status 前后完全一致） |
| 在真实 WSL 树上跑 | ✅ 零破坏（17 项改动状态不变） |

---

## 八、相关文档

- 编译步骤：`HANDOFF.md` §2.4
- 端点清单与分组：`docs/TODO-BACKLOG.md` 第三章
- MCP 侧工具：`tools/cardinal_mcp.py`（55 个工具）
