# cardinal-mcp

> 一个让 AI 能直接操作 [Cardinal](https://github.com/DISTRHO/Cardinal) 模块化合成器的轻量外壳。
> **52 个 MCP 工具**（MCP 协议 2025-06-18：tool annotations + structured output）
> + 约 40 个零依赖 Python 小工具 = 一个能版本管理、自动化、远程控制的合成器工作流。

---

> [!CAUTION]
> **AI-Generated Project — Verify Before You Trust It.**
> This repository was produced almost entirely by an **AI Agent (WorkBuddy)**, not by a
> human typing every line. The code, docs, and param dictionaries were generated and
> self-reviewed by the agent. They are shared in the hope they help — but **treat them
> as unverified**: review, test, and audit anything you intend to run, especially the
> OSC / file-editing tools that touch your running Cardinal. The agent can be wrong,
> and it cannot hear your audio.
>
> **人工智能生成项目 —— 使用前请务必甄别。**
> 本仓库几乎全部由 **AI Agent（WorkBuddy）** 自动生成，并非人工逐行编写。代码、文档与
> 参数字典均由 AI 生成并自检。发布出来是希望能帮到人，但**请勿默认其正确**：凡打算运行
> 的内容（尤其是会改动你正在运行的 Cardinal 的 OSC / 文件类工具）请自行审查、测试、核对。
> AI 可能出错，也听不到你的声音。

---

## 这是什么 / 不是什么

**是什么**

Cardinal 是 VCV Rack 的硬分叉（DISTRHO 出品），本身是为了拿来做插件和独立合成器的。但如果你像作者一样想
「弹键盘 + 打鼓 + 调音」还想要一份「代码级」的副本让 AI 能帮你改，那它是黑盒——没有 MCP 接口、没有结构化输出，
模块位置参数全是 GUI 拖拽出来的。

`cardinal-mcp` 在它外面套了一层：
- **驱动**：Cardinal 的 **OSC**（原版 4 个只写 handler）+ **实时自动存档读回**，拼出
  **52 个语义化 MCP 工具**（`cardinal_load_patch` / `cardinal_set_param` / `cardinal_read_live` 等）。
- **看见**（原版 Cardinal 做不到的部分）：`tools/osc_patch/` 是一份幂等的 Cardinal
  源码补丁 + WSL2 交叉编译配方，给 Cardinal 注入 **22 个 OSC 端点**——5 个只读探针
  （`/modules` `/param-get` `/ports` `/signal` `/light`）+ 6 个运行期事实读取 + 10 个
  「模拟人类操作」端点 + QuickJS 绑定。AI 终于能**读**引擎状态（哪些模块真加载了、
  旋钮的真实显示值、每个口的电压——这机架到底在不在出声），也能像人一样**动手**（拧旋钮、
  拖接线、撤销、发 MIDI）。作者的 patched 构建已部署并实测；没打补丁的原版构建上，
  这类工具全部优雅降级为 `probe_not_supported`，其余工具照常工作。
- **在宿主里执行代码**：`cardinal_js_run` 让 JS（QuickJS）在 Cardinal 进程内跑——
  和 blender / godot / UE MCP 的「在宿主里执行代码」是同一件事。默认关闭、
  永不初始化 libc、2000ms 墙钟预算。
- **先审计再加载**：五道审计链（`validate` → `ports` → `chain` → `values` → `flow`）
  聚合成一个 `cardinal_audit` 工具——把「一加载就崩」和「加载了但不出声」两类问题
  拦在 `/load` 之前。
- **机架即代码**：生成器（`tools/make_*.py`，DSL 在 `tools/rackgen.py`）+ 排班门禁
  （`layout_patch.py`）——机架是可以 `git diff` 的纯文本。
- **乐谱导出**：序列器音符 → 可编辑的 `.abc` 文本谱（`tools/abc_export.py` +
  `cardinal_export_abc`），两大序列器家族都支持。
- **知识层**：`params/modules.json`（从模块 C++ 源码抽取的参数字典，数据驱动覆盖）
  + 112 条从真实源码 enum 抽出的端口语义 + `music/knowledge.json`
  （9 套节奏型 / 10 套和弦进行 / 8 套音色配方）+ 风格 schema
  （`docs/STYLE-SCHEMA.md`，样板用真机架实测回填）。

**不是什么**

- **主路径不是 Cardinal 插件**——52 个工具全部通过 OSC + 文件层在外部驱动 Cardinal，
  原版 Cardinal 上就能用。可选的 `tools/osc_patch/` 源码补丁**确实会改 Cardinal**
  （这是拿到「读回」能力的唯一出路——Cardinal 的 OSC 设计上就是只写的），
  但它 opt-in、幂等、自带 `--rollback`。
- **不是音乐教学项目**——只解决"工程化与可遥控"，音乐知识库是顺带的脚手架。
- **不带第三方作品**——把 Cardinal 官方示例机架、MidiSuite 配置截图、源码缓存都从仓库里排除掉了，
  这些是别人的资产，使用 `docs/ATTRIBUTION.md` 标注来源，需要的自己去下。

---

## 适合谁

- 已经装了 Cardinal standalone + MIDI 键盘，想用 Cursor / WorkBuddy / Claude Desktop 这类 MCP-aware AI 直接调参数、换音色、改连线的人。
- 想把"手点鼠标搭的合成器机架"变成可以 `git diff` 的纯文本的人。
- 想要在没有 GUI 的环境（远程、CI）里预生成、预校验机架的人。

### 拿到自己机器上用

这些工具本来就是打算让人拿去用的，所以先说清楚几件事：

- **没有写死任何个人路径。** `tools/cardinal_mcp.py` 从自身文件位置推导仓库根，
  `CARDINAL_IP` / `CARDINAL_PORT` / `CARDINAL_PATCH_DIR` 全是环境变量且有可用默认值。
  **clone 到哪都能跑。**
- **`mcp.example.json` 是模板**，把里面的 `<REPO>` 换成你的 clone 路径即可。
- **用采样的机架按"相对仓库根"解析采样路径。** 移动仓库位置后 `samples/` 仍然有效；
  但如果你**删掉 `samples/` 目录**，那几个用采样器的机架（`demo_S4`、`demo_S5`、
  `quadeca_scrapyard*`）会加载成功但**不出声**，其余部分不受影响。
  想把采样换成自己的素材时，用 `tools/relocate_samples.py` 批量重写路径。
- **硬性前提只有 Python 3.13 + 一个 Cardinal standalone 版本**，pip 依赖两个，都在
  `requirements.txt` 里。
- **只在 Windows 上完整测过。** `winmidi.py` / `winprobe.py` 用 Win32 API，截图工具假定
  Windows 桌面。机架生成那套工具本身跨平台，但 **MIDI 输入只在 Windows 上验证过**。
- **任何 MCP 客户端都能连。** 本 server 是规范实现的 MCP server
  （stdio + JSON-RPC 2.0，版本协商至 2025-06-18），不绑 WorkBuddy。

---

## 30 秒上手

### 1. 安装依赖

只需要两个 Python 包：

```bash
pip install -r requirements.txt
# 或者手动：python-osc + zstandard
```

依赖少是因为绝大多数工具都用标准库（`win32gui` / `ctypes` / `socket` / `tarfile` / `json`）。

### 2. 启动 Cardinal

```text
打开 CardinalNative.exe
OSC 远程控制默认自动开启（CARDINAL_OSC_AUTOSTART=1）。
原版构建也可以手动开：
菜单：Engine → Enable OSC remote control
```

验证 OSC 通了：

```bash
python tools/cardinal_mcp.py --selftest
# 期望最后一行：OK: All 52 tools reachable
```

如果不通，先用 PowerShell 跑：
```powershell
Get-NetUDPEndpoint -LocalPort 2228 -ErrorAction SilentlyContinue
```
应该看到 `CardinalNative.exe` 绑着这个端口。

### 3. 在 AI 工具里注册 MCP server

把 MCP 配置加到你的 MCP-aware 客户端（WorkBuddy / Claude Desktop / Cursor 都行）：

```json
{
  "mcpServers": {
    "cardinal": {
      "command": "python",
      "args": ["D:/Cardinal/tools/cardinal_mcp.py"],
      "env": {
        "CARDINAL_PATCH_DIR": "D:/Cardinal/patches",
        "CARDINAL_IP": "127.0.0.1",
        "CARDINAL_PORT": "2228"
      }
    }
  }
}
```

完整的字段示例见 `mcp.example.json`。所有环境变量都有合理默认值，不设也能跑。

### 4. 测试一下

在 AI 里输：`列出当前所有 patch 并告诉我 helm_full.vcv 里有几个模块。`

背后会自动调用 `cardinal_list_patches` + `cardinal_patch_info`。

---

## 它能做什么 —— 52 个 MCP 工具一览

### 驱动（写进运行中的 Cardinal）

| 工具 | 做什么 | 常用场景 |
|---|---|---|
| `cardinal_ping` | 发 `/hello` 检查 Cardinal 是否响应 OSC | 排查连通性 |
| `cardinal_load_patch` | 把某个 .vcv 推给 Cardinal（含 zoom + gridOffset） | 让 AI 切音色 |
| `cardinal_set_param` | 拧任意模块的旋钮：`moduleId + paramId + value` | 改 cutoff / release / 等 |
| `cardinal_set_param_by_name` | 按参数名设值，拒绝废弃槽，多实例精准分流 | 「设 VCF cutoff」不用先查编号 |
| `cardinal_set_params_batch` | 一次调用设多个旋钮（按参数名），只读一次盘只写一次盘，逐条回执 | 一次调一整条音色的旋钮 |
| `cardinal_set_host_param` | 改 Cardinal 内置的 24 个宿主参数 | 调音频接口/采样率等 |
| `cardinal_save_live` | 把当前 GUI 状态落盘成 .vcv | 用户手动改完不存档就丢 |

### 检查（读机架与运行状态）

| 工具 | 做什么 | 常用场景 |
|---|---|---|
| `cardinal_patch_info` | 看某个机架的模块清单（拿到 moduleId 才好调参） | 改参数前的必备查询 |
| `cardinal_list_patches` | 列 `patches/` 目录下所有 .vcv 机架 | 选要加载的机架 |
| `cardinal_read_live` | 读 Cardinal 正在运行的机架（走实时自动存档读回；带 `stale` 新鲜度标记） | 想看用户在 GUI 里改了啥 |
| `cardinal_module_params` | 列某模块的参数清单（名 → 编号） | 找参数编号 |
| `cardinal_find_param` | 把口语翻成参数编号（"亮一点"→Cutoff） | 让 AI 用自然语说话 |
| `cardinal_topology` | 接线 + 每模块角色 + 信号能否到达 HostAudio2 | 「这机架到底在干什么」 |

### 审计与部署（「永不加载坏机架」链）

| 工具 | 做什么 | 常用场景 |
|---|---|---|
| `cardinal_audit` | 一次调用跑完五道审计，给 FAIL/WARN/PASS 裁决 | 每次 `/load` 前的门禁 |
| `cardinal_deploy` | 备份 → 审计 → 加载 → 读回结构比对，FAIL 拒绝加载 | 一键安全部署 |
| `cardinal_diff` | 磁盘 .vcv vs 引擎实际实例化的模块**和旋钮值** | 抓被静默丢弃的模块，以及对不上的旋钮 |

### 实时只读探针（需 patched 构建；没有则优雅降级）

| 工具 | 做什么 | 常用场景 |
|---|---|---|
| `cardinal_live_modules` | 引擎实际加载的所有模块 | 加载后的 ground truth |
| `cardinal_get_param` | 某旋钮的真实**显示值**（275 ms，不是 0.275） | 验证 `set_param` 真的生效了 |
| `cardinal_module_ports` | 每个口的接线状态 + 实时电压 | 「没接线 / 接了没声 / 有声」三态 |
| `cardinal_scan_signal` | 全机架扫描：哪些模块此刻真的在输出电压 | 「到底响没响」的直接答案 |
| `cardinal_get_light` | LED 亮度（如 Clocked 的 RUN 灯） | 走带到底跑没跑 |

### 模块库浏览器（读 Cardinal 自己的 PluginManifests——1407 模块 / 85 品牌 / 104 标签）

| 工具 | 做什么 | 常用场景 |
|---|---|---|
| `cardinal_module_search` | 按英文关键词 / 官方标签 / 品牌搜模块库 | 从现实里选模块，不靠记忆 |
| `cardinal_module_tags` | 全部官方标签 + 计数 | 搜索没结果时来这挑标签 |
| `cardinal_module_brands` | 全部品牌 + 模块数 | 按厂商浏览 |
| `cardinal_module_detail` | 单模块完整 manifest 记录 | 说明书 URL、描述、同门模块 |
| `cardinal_port_semantics` | 每个口是 pitch/gate/audio/cv 的语义表（来自真实源码） | 照表接线，不靠猜 |

### 序列器与乐谱（钢琴卷帘等价物）

| 工具 | 做什么 | 常用场景 |
|---|---|---|
| `cardinal_seq_read` | 按小节/音名读序列器音符（两大家族都支持） | 把音乐看成文本 |
| `cardinal_seq_edit_note` | 改一个音符（音高/休止/力度），拒绝写坏数据 | 远程点一格钢琴卷帘 |
| `cardinal_seq_set_running` | 开/关序列器走带（RUN 键） | 开始播放 |
| `cardinal_export_abc` | 导出序列器音符为可编辑 `.abc` 文本谱 | 在 GUI 外编辑音乐 |

### 采样槽（右键「Load sample」等价物）

| 工具 | 做什么 | 常用场景 |
|---|---|---|
| `cardinal_samples_list` | 浏览采样库 | 从真实存在的文件里挑，不猜文件名 |
| `cardinal_sample_inspect` | 每槽当前采样 + 标记失效文件 | 找静默哑掉的采样器 |
| `cardinal_sample_load` | 把 wav 装进槽（路径风格感知，先备份） | 远程换采样 |
| `cardinal_sample_clear` | 清空一个槽 | 清理 |

### 音乐与风格知识

| 工具 | 做什么 | 常用场景 |
|---|---|---|
| `cardinal_music` | 节奏型 / 和弦进行 / 音色配方查询 | 让 AI 用知识库回答 |
| `cardinal_apply_recipe` | 把音色配方写进机架；`weight` 0..1 在当前值↔目标值间插值 | 一键换音色，或轻微推动 |

### 运行期事实读取（批次 B · 需要 patched 构建，原版优雅降级）

| 工具 | 做什么 | 常用场景 |
|---|---|---|
| `cardinal_build_info` | 变体 / GUI 版还是 thread 版 / 编译时间 / safeMode / 完整端点清单 | P0 诊断：把「OSC 根本没开」和「Cardinal 崩了」分开——只从客户端看，两者的表现都是超时 |
| `cardinal_cables` | 全机架接线：`id:输入(模块,口)←输出(模块,口)`，可按模块过滤 | 「到底接上了没」的权威答案 |
| `cardinal_transport` | playing / bar / beat / bpm / tick / bypassed（零 hook） | 音序器走带是不是真在跑 |
| `cardinal_engine_info` | 采样率 / buffer / CPU 平均与峰值，带 `cpu_refresh_ms` | CPU 表每秒才刷一次，回包自带数据年龄 |
| `cardinal_plugins` | 当前机架实际用了哪些 plugin slug + safeMode；可逐个查磁盘层装没装 | 「我拼写明明对却加载不上」——safeMode 为真意味着**一个插件都没加载** |

### 模拟人类操作（批次 C · 这些会**改**当前机架，但全部可 undo）

| 工具 | 做什么 | 常用场景 |
|---|---|---|
| `cardinal_set_param_by_display` | 按**显示值**写旋钮（写「275ms」而不是 0.275） | 像人一样输入，引擎负责换算 |
| `cardinal_cable_add` / `cardinal_cable_remove` | 拖一条线 / 右键断开 | 不重新生成机架就能改接线。⚠️ 同一输入口只能接一根线 |
| `cardinal_module_move` | 拖动模块；`x` 是格、`y` 是行号 | 精准挪位，绝不整版重排 |
| `cardinal_module_remove` | 选中 + Delete（模块连同它的线） | 可撤销，但更稳妥是先改保存好的副本 |
| `cardinal_undo` / `cardinal_redo` | Ctrl+Z / Ctrl+Shift+Z，返回被撤销动作的名字 | 别假定「撤销了什么」，先看返回的名字 |
| `cardinal_module_json` | 活的单个模块的完整 .vcv JSON | 改模块数据时的权威形状 |
| `cardinal_midi_out` | 注入原始 MIDI 消息（不用硬件键盘） | 让 agent 直接弹琴。bypassed 时如实回 `skipped:bypassed` |

### 进程内 JS（QuickJS · 和 blender/godot/UE MCP 同款的「宿主内执行代码」）

| 工具 | 做什么 | 常用场景 |
|---|---|---|
| `cardinal_js_list` | 列出可执行的 JS 脚本及 1-based 索引 | 脚本放 `js/` 目录，可 git 管理 |
| `cardinal_js_run` | 在**正在运行的** Cardinal 里执行脚本 | 需要自由文本 / JSON 的操作只能走这条路 |

**为什么需要 JS 这条路**：这个 Cardinal 版的 liblo **收不了** string 类型的 OSC 参数
（2026-10-20 实测：所有 string 输入端点全哑；**发**字符串正常）。所以要传任意文本的
操作改成「脚本文件 + 索引」——索引是纯数值。反倒更合李的工作流：机架配方是
git 可管的资产，不是一堆临时字符串。

**安全模型，三道独立闸门**：
1. **默认关闭**——`CARDINAL_JS_MODE` 不是 `read` / `write` 就回 `disabled`。
2. **永不初始化 libc**——没有 `std`、没有 `require`、没有 `exec`。runtime 就是裸的
   `JS_NewRuntime` + `JS_NewContext`，不存在任何外发执行路径。
3. **墙钟预算**——默认 2000ms（`CARDINAL_JS_BUDGET_MS` 可改）。死循环脚本被打断后
   回 `budget-exceeded ms=2001`，进程存活（用 `while (true)` 实测过）。

脚本契约：脚本被包在 IIFE 里，所以**用 `return` 交结果**——自己写
`globalThis.result = ...` 会被覆盖成 `undefined`。

| API（只读，read 和 write 模式都有） | API（写，需 `CARDINAL_JS_MODE=write`） |
|---|---|
| `cardinal.modules()` / `getParam(id, n)` / `ports(id)` / `cables()` / `transport()` / `moduleJson(id)` | `cardinal.setDisplayValue(id, n, v)` / `moduleFromJson(id, json)` / `addModule(slug, x, y)` / `cableAdd(...)` / `undo()` / `redo()` |

### 人类操作索引

| 工具 | 做什么 | 常用场景 |
|---|---|---|
| `cardinal_actions` | 23 条人类 UI 操作：代码在哪、哪个工具已覆盖、什么状态 | 写任何脚本+重载之前，先查人类按钮对应什么 |

---

## 项目结构

```
cardinal-mcp/
├── README.md                       ← 英文版（本文件是中文版）
├── README.zh-CN.md                 ← 本文件
├── LICENSE                         ← MIT
├── requirements.txt                ← python-osc + zstandard
├── mcp.example.json                ← MCP 配置示例
│
├── tools/                          ← 约 40 个 Python 工具
│   ├── cardinal_mcp.py             ← MCP 主入口（52 个工具）
│   ├── osc_patch/                  ← 3 套注入器，22 个 OSC 端点（读 + 操作 + JS）
│   │                               ← + 幂等注入器（备份/校验/回滚）
│   ├── patchio.py                  ← 双格式读写 .vcv（JSON / tar+zstd）
│   ├── layout_patch.py             ← 排班门禁 + 自动重排
│   ├── paramlib.py                 ← 从源码抓参数字典
│   ├── musiclib.py                 ← 音色配方 / 和弦进行 / 节奏型
│   ├── modbrowser.py               ← 模块库检索（读 PluginManifests）
│   ├── topology.py                 ← 机架接线 / 角色 / 可达性
│   ├── seq.py                      ← 序列器音符（钢琴卷帘等价物）
│   ├── abc_export.py               ← 序列器音符 → .abc 文本谱
│   ├── samplelib.py                ← 采样槽（右键「Load sample」等价物）
│   ├── interaction_map.py          ← 人类 UI 操作 → 源码索引
│   ├── style_schema.py             ← 风格 schema 校验 + 机架回填
│   ├── rackgen.py                  ← 机架生成 DSL（血泪注释逐字保留）
│   ├── audit_{ports,values,flow,chain}.py + validate.py  ← 审计链
│   ├── cross_build_cardinal.sh     ← WSL2 交叉编译配方（win64）
│   ├── wslrun.py / wslout.py       ← WSL2 助手（UTF-16 解码、路径安全）
│   ├── winprobe.py                 ← DPI / 窗口探测
│   ├── winmidi.py + midiprobe.py   ← Windows 原生 MIDI 工具
│   ├── shot.py                     ← GDI 截屏（零依赖）
│   └── make_*.py                   ← 各机架生成器（quadeca / yorushika / …）
│
├── params/
│   └── modules.json                ← 参数字典（数据驱动覆盖）
│
├── music/
│   └── knowledge.json              ← 节奏型 / 进行 / 配方
│
├── patches/
│   ├── helm_full.vcv               ← 主机架：琴键+旋钮+触控+鼓垫全套
│   ├── quadeca_life1_wdtg.vcv      ← 旗舰音乐机架（人耳验证有声）
│   ├── yorushika_shura/hana.vcv    ← 风格驱动机架（待验收）
│   └── ... （.gitignore 排除了个人备份）
│
└── docs/
    ├── DESIGN-NOTES.md             ← 技术档案：完整解释整套东西怎么搭起来的
    ├── CARDINAL-REPO-NOTES.md      ← 上游 Cardinal 仓库的关键发现
    ├── TODO-BACKLOG.md             ← 唯一待办总表（批次 A 已完成，B/C 待定）
    ├── CARDINAL-MCP-SPEC.md        ← 协议规格 + 源码核实事实
    ├── CARDINAL-MCP-CAPABILITY-MAP.md ← 引擎能/不能做什么，附源码行号
    ├── HUMAN-INTERACTION-MAP.md    ← 人类 UI 操作 → 源码函数映射
    ├── STYLE-SCHEMA.md             ← 风格数据化，样板用真机架实测
    ├── SMK25-midi-map.md           ← M-VAVE SMK25 键盘 MIDI 实测档案
    └── ATTRIBUTION.md              ← 第三方资源来源标注
```

---

## 工作流示例

> 下面几段是**「你可以怎么跟 AI 说话」的演示**，展示的是预期对话，不是验证过的执行记录。
>
> **实际在真机上跑过的东西**单独列在这里：
>
> | | |
> |---|---|
> | Quadeca 风格机架 | 5 张机架在 Cardinal 里实机加载通过（`docs/QUADECA-PATCHES-ACCEPTANCE.md`，2026-10-17 实机版）。那份验收单还记着它抓出的两个问题：端口越界会崩；时钟源选错则加载成功但不会播 |
> | `quadeca_life1_wdtg.vcv` | 已确认有声音（人耳确认） |
> | `mini_arranger_expanded.vcv` | MiniArranger 主模块 + 扩展器，已验收 |
> | `mini_arranger_8voice*.vcv` | 已生成，**待实机验收**（`docs/8VOICE-PATCH-ACCEPTANCE.md`） |
> | 全部机架 | 静态审计全部解析通过 |
> | OSC 只读探针 | 已交叉编译 + 部署；用 OSC 实测 interrogate 运行中的引擎验证过（如默认机架 VCO 在 `/signal` 上读数为 4.977 V） |

### "把合成器变亮一点"

```
你: 帮我把 Current Patch 的滤波器亮度调高一点
AI: → cardinal_patch_info  (拿到 VCF moduleId)
   → cardinal_find_param (口语 → "Cutoff")
   → cardinal_set_param (Cutoff value = 0.75)
   → cardinal_get_param (patched 构建：读回真实显示值，确认真的落了)
   → 告诉你人话：把 cutoff 从默认 0.5 提到 0.75，听感会更亮
```

### "这机架到底响没响"

```
你: 我加载了新 patch 但没声音，是不是坏了？
AI: → cardinal_audit (静态：ports/values/flow/chain/validate，FAIL 就不许加载)
   → cardinal_live_modules (每个模块都活着加载了吗)
   → cardinal_scan_signal (哪些模块此刻真的在输出电压)
   → cardinal_module_ports 查可疑模块 (没接线 / 接了没声 / 有声)
   → 给出真实原因，不是猜
```

### "换一首和弦进行"

```
你: 给我做个 ii-V-I 的爵士伴奏
AI: → cardinal_music (progressions) 拿 ii-V-I 的 voicings
   → cardinal_patch_info 看现在的 ADSR / VCO 配置
   → cardinal_apply_recipe 写新参数
   → 你按一个键就能听到 ii-V-I 了
```

---

## OSC 层：22 个端点是怎么进到 Cardinal 里的

原版 Cardinal 的 OSC server 是**只写的**（4 个 handler，没有一个回数据）——这是上游
项目的硬设计事实，不是 bug。`tools/osc_patch/` 补上这一层：

```
tools/osc_patch/
├── osc_read_handlers.cpp.inc    ← 批次 A：5 个只读探针
├── inject_osc_read.py           ← 幂等注入器：备份 → 注入 → 校验 →（--rollback）
├── osc_read_b_handlers.cpp.inc  ← 批次 B：6 个运行期事实读取
├── inject_osc_b.py              ← 同样四件套，锚点挂在批次 A 的标记上
├── osc_ops_c_handlers.cpp.inc   ← 批次 C：9 个模拟人类操作端点
├── osc_js_handlers.cpp.inc      ← QuickJS 绑定（进程内 JS）
└── inject_osc_c.py              ← 同样四件套，锚点挂在批次 A 的标记上
```

- 每个注入器都改 `src/CardinalCommon.cpp`（**thread 与非 thread 两处**注册点都改——
  只改一处会静默失效），改前备份，改后校验「实现数 × 注册数」。三个都支持
  `--check` 与 `--rollback`。
- 用 WSL2 交叉编译配方构建：`bash tools/cross_build_cardinal.sh 8 true`
  然后 `make -C CardinalNative`（第二条命令是绕开一个既有的 `CardinalMini_dsp.dll`
  链接失败所必需的补丁动作，详见 `docs/TODO-BACKLOG.md`）。
- **三批全部已落地并运行级实测**（2026-10-19/20）：
  - 批次 A — `/modules` `/param-get` `/ports` `/signal` `/light`
  - 批次 B — `/build-info` `/cables`（全量 + 单模块）`/transport` `/engine-info` `/plugins`
  - 批次 C — `/param-set-by-display` `/cable-add` `/cable-remove` `/undo` `/redo`
    `/module-json` `/module-remove` `/module-move` `/midi-out` + `/osc-js-run` `/osc-js-list`

  验收一律是**运行级**、绝不是文件级：真实进程在真实机架上回真实 OSC 消息。
  （文件级证据会骗人——exe 是 stripped to external PDB，`nm` 完全没用，
  连短路径串都会被 GCC 内联掉。）
- 没打补丁的构建上，这批工具返回 `probe_not_supported`，其余 52 个工具不受影响。
- 已实测：`/modules` 回引擎真实模块清单；`/signal` 报每模块峰值电压
  （默认机架的 VCO 读数 4.977 V）；C 组 undo 回来的动作名正确
  （`change parameter` / `add cable` / `move module`）；JS 预算把 `while (true)`
  脚本在 2001ms 打断且进程存活。

### 这一层的已知限制（是设计事实，不是 bug）

- **这个版本的 liblo 收不了 string 类型的 OSC 参数。** 2026-10-20 实测：所有
  string 输入端点全哑；**发**字符串正常（`/resp` 的内容全是字符串）。所以需要
  自由文本或 JSON 的操作改走「JS 脚本文件 + 数值索引」——见上面的 `cardinal_js_run`。
- **旋钮显示值域因模块而异，且常为非线性。** 显示值写 `0.8`、在 VCO 上回读
  `11.56 Hz` 是**正确换算**而不是 bug。要用 `cardinal_get_param` 验证，
  不要拿数字直接比。
- **CPU 表每秒才刷新一次**（`/engine-info` 自带 `cpuRefreshMs` 说明数据年龄），
  `/modules` 还没有分页——200 模块的机架会一个数据报回来，体积大但仍在 UDP 上限内。

---

## 硬件 / 软件环境（本项目在哪台机器上验证过）

> 这部分是给想自己复刻的人看的，告诉你要什么环境才能跑得起来。

### 软件

- **OS**：Windows 11（10.0.26200，64-bit）
- **Cardinal**：26.02（[DISTRHO/Cardinal](https://github.com/DISTRHO/Cardinal)）
  - 共 4 个变体：DISTRHO 本体 / FX / Mini / Synth
  - 启动用 `CardinalNative.exe`（≈100 MB，主 standalone）
  - 自带模块库（VCV Rack Fundamental + AudibleInstruments + 一众社区插件）
  - 作者另外跑一份**自编译的 patched CardinalNative**（WSL2 交叉编译 + OSC 探针注入），
    部署在 `D:/Cardinal/win64/`——构建配方在 `tools/`
- **Python**：3.13.12（managed 解释器，装在用户目录的隔离 venv 里）
- **AI 客户端**：WorkBuddy（用其 MCP 配置）——同理 Cursor / Claude Desktop 也可以用同一份 `mcp.example.json`
- **MIDI 配套软件**（用户私有，不随附）：M-VAVE MidiSuite，配 M-VAVE SMK25 时有用

### 硬件

- **CPU**：Intel(R) Core(TM) Ultra 9 275HX
- **屏幕**：
  - 逻辑分辨率 1600×1000
  - 物理分辨率 3200×2000（200% 缩放 = DPI 192）
  - 1 HP（Cardinal 模块宽单位）≈ 21 物理像素 @ zoom=0.75
- **MIDI 键盘**：[M-VAVE SMK25](https://www.m-vave.com/) —— 25 键 + 16 旋钮 + 16 鼓垫 + 触控条 + 踏板 + Transport
  - USB + BLE 双模
  - **完整 MIDI 映射实测档见 `docs/SMK25-midi-map.md`**

### 网络

- 不联网可用——所有工具都能脱机工作。
- 联网只用在一个地方：`tools/paramlib.py` 第一次启动会从 Cardinal 自带模块对应的 GitHub 仓库抓 C++ 源码做参数提取（产物缓存在 `tools/_srccache/`，**不进仓库**）。

---

## 已知限制 / 不支持的场景

| 不支持 | 原因 |
|---|---|
| 批量操作要原子生效 | OSC 没有 `/batch` 端点。`ComplexAction` 引擎里有，但 C 组各端点本身就走 history ⇒「做 N 步、一次 undo」已经能拼出来。真需要单端点批量时再补 C5 |
| 用 OSC 按 slug 加模块 | **这个版本的 liblo 收不了 string 参数**（2026-10-20 实测）。加模块要 `plugin\|model` slug，所以走 `cardinal_js_run` → `cardinal.addModule(slug, x, y)`，而不是普通 OSC 端点 |
| **原版**构建上参数变化自动回读 | 实时自动存档只在 `/load` 或 GUI 显式保存时写盘 —— **`/param` 改参数不写，也没有定时器**（26.02 实测）。用 **patched** 构建时，`cardinal_get_param` 走 `/param-get` 读真实显示值。详见 `docs/DESIGN-NOTES.md` 坑 8 |
| 直接信任 `read_live` 的结果 | 如果留下过多次会话的存档，最新那个文件可能属于**上一次**会话。`read_live` / `save_live` 现在会返回 `stale` / `age_seconds` / `note`，用之前先看这三个字段。详见 坑 8b |
| WSL2 里出声 | WSL2 构建能建窗口（软件 GL）也能应答 OSC，但 JACK 音频在 WSL 里不工作——WSL 只用于编译/验证，不用于演奏 |
| Linux/macOS 测试 | 本仓库只在 Windows 上跑通过；Python 工具都是跨平台的，但 `winmidi.py` / `winprobe.py` 用 Win32 API |
| LMMS / DAW 录音闭环 | 那是另一个项目（Cardinal.vst 装到 DAW 里），本仓库只到 standalone + OSC |

---

## 文档索引

| 文档 | 解决什么问题 |
|---|---|
| `README.md` | 我该不该装这个？装完怎么跑？（英文版） |
| `docs/DESIGN-NOTES.md` | 它是怎么搭起来的？全部工具逐个解释、踩坑记录、可复用原则 |
| `docs/CARDINAL-REPO-NOTES.md` | Cardinal 上游有什么值得抄的？OSC 边界 / 模块清单 / 不存在的功能 |
| `docs/TODO-BACKLOG.md` | 什么做完了、什么接着做（批次 A 已完成；B/C 待拍板） |
| `docs/CARDINAL-MCP-SPEC.md` | 协议规格 + 源码核实过的事实 |
| `docs/CARDINAL-MCP-CAPABILITY-MAP.md` | 引擎能力地图，附精确源码行号 |
| `docs/HUMAN-INTERACTION-MAP.md` | 人类 UI 操作 → 源码函数映射 |
| `docs/STYLE-SCHEMA.md` | 风格数据化，样板用真机架实测回填 |
| `docs/SMK25-midi-map.md` | M-VAVE SMK25 的 MIDI 实测数据：什么控件发什么消息、什么通道、什么坑 |
| `docs/ATTRIBUTION.md` | 用到了哪些第三方资源、怎么拿 |
| `AI-DISCLOSURE.md` | **本项目由 AI Agent 生成，使用前请务必甄别**（中英双语声明） |
| `HANDOFF.md` | 给续接的 AI 看的状态快照 |

---

## 致谢

- [DISTRHO/Cardinal](https://github.com/DISTRHO/Cardinal) —— 本项目操控的目标
- [VCV Rack](https://vcvrack.com/) —— Cardinal 是它的硬分叉，模块生态基于 Rack 社区
- [WorkBuddy](https://www.workbuddy.cn/) —— MCP host，本人在用的 AI 客户端
- python-osc / zstandard —— 两个唯一的 Python 第三方依赖

第三方资源的使用与版权见 `docs/ATTRIBUTION.md`。

---

## AI 生成声明（必读）

**本项目几乎全部由 AI Agent（WorkBuddy）自动生成，并非人工逐行编写。** 代码、文档与
参数字典均为 AI 自检产出，可能含有错误。运行任何会改动你机架 / 正在运行 Cardinal 的工具前，
请先备份与测试。

- 完整声明与「建议核对清单」见 **[`AI-DISCLOSURE.md`](AI-DISCLOSURE.md)**（中英双语）。
- 顶部横幅同样有醒目提示。

---

## License

MIT——见 `LICENSE`。
