# Cardinal 音乐工具链 · 技术档案

> 生成：2026-09-12 15:50
> 范围：从「手点鼠标的模块化合成器」到「AI 能读写、能看见的工程化管线」——全部代码、数据、文档与踩坑记录
> 配套阅读：`HANDOFF.md`（当前状态 / 交接）、`~/.workbuddy/skills/cardinal-patch-authoring/SKILL.md`（权威技术细节）

---

## 0. 一句话总览

**这套东西解决的问题是：Cardinal 原本只能靠鼠标手搓，而手搓的东西没法版本管理、没法复查、AI 也看不见。**

所以我们在它外面搭了一层「工程化外壳」：

- 一个 **MCP 服务**（12 个工具）让我能直接操作它
- 一批 **零依赖探测工具** 让我能"看见"屏幕、听见 MIDI
- 一本 **参数字典 + 音乐知识库** 让我不用猜编号
- 一套 **排版门禁** 保证每次加模块都不跑偏

规模：**24 个 Python 文件 / 5080 行**，加 **2 个 JSON 数据库**、**20 个机架产物**、**6 份文档**。

---

## 1. 为什么需要写这些（五个障碍 → 五种手段）

| # | 障碍 | 具体表现 | 手段 |
|---|---|---|---|
| 1 | `.vcv` 文件是**二进制归档** | Cardinal 保存时压成 tar+zstd，普通 JSON 库读不了 | `patchio.py` 双格式读写 |
| 2 | 模块的**端口号和参数编号没人知道** | 想知道「VCF 的截止频率是第几号参数」得去翻 C++ 源码 | `paramlib.py` 抓源码生成字典；`vcvtool.py` 反推端口 |
| 3 | **AI 看不见屏幕** | 我算得再准也不知道模块到底显示在哪，只能靠你描述 | `shot.py`（截屏）+ `winprobe.py`（DPI/窗口） |
| 4 | 键盘**发什么 MIDI 不确定** | SMK25 有双层结构、通道还分散，厂商文档不全 | `winmidi.py` + `midiprobe.py` 实测采集 |
| 5 | Cardinal **没有可用的自动化接口** | 只有 4 个 OSC 消息，且只能写不能读 | `cardinal_mcp.py` 封装成 12 个工具 + 用自动存档做读回 |

---

## 2. 程序清单（24 个文件，分五层）

### 2.1 通信与文件层 —— 我和 Cardinal 之间的桥

#### `tools/cardinal_mcp.py` — 700 行 / 20 函数 / **12 个 MCP 工具**

这是整套东西的**主入口**。它把 Cardinal 的 OSC 接口（只有 4 个原始消息）包装成 12 个语义化工具，注册进 WorkBuddy 的 MCP 配置，我就能像调用普通工具一样操作合成器。

它同时还是个**命令行工具**（MCP 服务没重启时用它绕过）：

```bash
python cardinal_mcp.py --tools                     # 列工具
python cardinal_mcp.py --call cardinal_read_live   # 直调单个工具
python cardinal_mcp.py --selftest                  # 全链路自检
```

12 个工具分三类：

| 类别 | 工具 | 作用 |
|---|---|---|
| **看** | `cardinal_ping` | 测 OSC 通不通 |
| | `cardinal_list_patches` | 列机架文件 |
| | `cardinal_patch_info` | 查模块清单与 id |
| | `cardinal_read_live` | **读**运行中的机架状态（走自动存档，不打扰你） |
| | `cardinal_module_params` | 查某模块的参数表 / 按关键字搜 |
| | `cardinal_find_param` | 人话 → 参数编号（「VCF 滤波亮」→ `0`） |
| | `cardinal_music` | 查鼓型 / 和弦进行 / 音色配方 |
| **写** | `cardinal_load_patch` | 把 `.vcv` 加载进 Cardinal |
| | `cardinal_set_param` | 拧任意旋钮 |
| | `cardinal_set_host_param` | 设 Cardinal 对宿主暴露的 24 个参数 |
| | `cardinal_apply_recipe` | 把音色配方写进机架 |
| **存** | `cardinal_save_live` | 把 Cardinal 内存状态存成正式文件 |

**关键设计**：`read_live` 走的是**实时自动存档**而不是 OSC——因为 OSC 只能写、不能读。这是绕过官方限制的巧劲。

#### `tools/patchio.py` — 74 行 / 5 函数

`.vcv` 有**两种磁盘格式**：明文 JSON（version 2.1）和 tar+zstd 归档（version 2.4.1）。Cardinal 保存时自动转归档格式。

提供 `is_archive` / `read_patch` / `write_patch` / `describe`。**所有其它工具都通过它读写文件**，不直接碰 JSON。

---

### 2.2 硬件探测层 —— 给我装上感官

#### `tools/winmidi.py` — 173 行

Windows 原生 MIDI 的**零依赖封装**（直接调 `winmm.dll`，不装任何第三方库）。功能：列设备、监听全部 MIDI 消息、解析 Note/CC/PitchBend 为可读格式。

为什么零依赖很重要：这台机器的 Bash 环境 PATH 是坏的，能少一层依赖就少一个坑。

#### `tools/midiprobe.py` — 127 行

MIDI 侦察兵。`dump <秒> <json>` 采集，`analyze` 自动分类分析（分组、判端口镜像）。

**三次实测（40s / 80s / 50s）就是靠它完成的**，产出 `refs/midi_dump*.json`，最终查明 SMK25 的全部消息映射。

#### `tools/winprobe.py` — 83 行

探测本机显示环境：**屏幕缩放（DPI）**、Cardinal 窗口矩形、是否最大化。

实测结果：**缩放 200%，物理分辨率 3200×2000**。这个数字是排版规则的基石——它决定了一屏能装多少模块。

#### `tools/shot.py` — 111 行

**纯标准库屏幕截图**（Windows GDI + 手写 PNG 编码器）。

写它是因为 PowerShell 的 `Add-Type` 被安全策略挡了，而 venv 里没装 PIL/mss。

```bash
python shot.py <输出.png> [缩放宽]
```

它是我"长眼睛"的关键——之前几轮我一直在靠推算布局，一直在错；截了几张图之后立刻定位了问题。

---

### 2.3 机架生成与修复层 —— 把接线从手搓变成代码

#### `tools/make_knobs.py` — 213 行 / 6 函数

写 `HostMIDIMap` 映射表（8 个旋钮 → 8 个参数）。子命令 `show` / `apply` / `set`，支持 `--load` 立即推送到运行中的 Cardinal。

#### `tools/make_full.py` — 297 行 / 5 函数

**生成 `helm_full.vcv`：把 SMK25 的全部控件一次接进 Cardinal。** `build` 生成、`report` 自查，**每次自动备份**。

这个文件经历了两次修正：一是「HostAudio2 是求和口」的错误假设，二是坐标单位错误。

#### `tools/fix_drum_bus.py` — 150 行 / 5 函数

修复鼓总线接线 + 输入口冲突自查。

`report <patch>` 只检查，不带参数则修 `helm_full.vcv`。**它解决了"鼓垫有 MIDI 反应但完全没声音"那个 bug。**

根因：Cardinal 铁律「**一个输入口只能接一根线，多接的被静默丢弃**」——合成器 + 鼓 A + 鼓 B 三根线抢 `HostAudio2` 的同一个输入口，鼓的两根被丢了。修法：鼓先进 `MixMasterJr` 的轨道 2/3，再由混音台主输出进 `HostAudio2`。

---

### 2.4 知识库层 —— 不用猜

#### `tools/paramlib.py` — 839 行 / 29 函数（**最大的一个文件**）

从 GitHub 上的模块 C++ 源码里**自动解析出参数字典**。含中文术语映射 `TERMS`，能把「滤波 亮」翻译成参数编号。`verify` 子命令做对齐校验。

产出：`params/modules.json` —— **15 个模块 / 248 个命名参数**。

工作原理：抓 `.cpp` 源码 → 剥离注释 → 匹配 `createParam(...)` 调用 → 解析枚举常量 → 展开循环 → 得到「编号 → 名字 + 单位 + 范围」。

#### `tools/musiclib.py` — 661 行 / 11 函数

音乐知识库三合一：

| 库 | 条数 | 内容 |
|---|---|---|
| `drum_patterns` | 9 | four_on_floor / rock_basic / lofi_hiphop / trap / breakbeat / ballad / bossa / halftime … |
| `progressions` | 10 | pop_1564 / canon / jazz_251 / lofi_2516 / andalusian / blues_12 … |
| `recipes` | 8 | warm_pad / bright_pluck / lofi_keys / dark_bass / bell / lead_saw … |

还带 `voice_lead`（声部引导）、`apply_recipe`（把配方写进 `.vcv`）等落地工具。产出 `music/knowledge.json`。

#### `tools/vcvtool.py` — 151 行 / `tools/validate.py` — 85 行

`vcvtool.py` 反推模块端口用法（含 1422 个模块的字典）；`validate.py` 校验机架合法性。

---

### 2.5 排版与质量层 —— 把纪律变成卡口

#### `tools/layout_patch.py` — 708 行 / 20 函数

**机架排版的唯一权威。** 这是我为「每次加模块都别跑偏」这个问题写的总答案。

| 子命令 | 作用 |
|---|---|
| `check <patch>` | 只诊断坐标，不改文件 |
| `guard <patch>` | **门禁**：重叠 / 行不对齐 / x<0 / 输入口双接，有硬错误则**退出码 1** |
| `apply <patch> [--push] [--strict]` | 重排 + 自动备份 + **幂等**；未登记模块自动落行 |
| `widths` | 复测本机面板 SVG，核对宽度表是否失真（42 项） |

**一个被逼出来的设计**：门禁第一版在 10 个旧文件上全部报 FAIL。一查发现 `TextEditor` 的 `x=-3` 和 1 格的重叠都是**估值误差**，不是真故障。

**总在喊狼来了的门禁比没有还糟。** 所以我把严重度分成两级：**硬错误**（一定坏，必须修）vs **提示**（不合规范但能用）。

#### `tools/state.py` — 91 行

状态诊断。一条命令看清「机架文件 vs Cardinal 内存」的差异、mtime、`zoom`/`gridOffset`、OSC 端口探活。

**想知道"Cardinal 内存里到底是什么"就跑它。**

#### `tools/watch_knobs.py` — 80 行

早期工具，轮询存档比对参数。**已确认在参数验证上无效**（存档更新速率太低），保留作历史。

---

### 2.6 一次性侦察脚本（8 个，`_` 前缀，非正式工具）

| 文件 | 行数 | 用途 |
|---|---|---|
| `_drums_probe.py` | 84 | 拉取 WSTD-Drums 全部鼓模块源码，解析声部数/触发口/音频出口/参数编号 |
| `_fetch_examples.py` | 54 | 下载 Cardinal 官方示例机架并列出各自用到的模块 |
| `_tpl_probe.py` | 37 | 探查官方模板的模块与接线结构 |
| `_mcp_test.py` | 66 | 给 `cardinal_mcp.py` 做冒烟测试（模拟 MCP 客户端走握手） |
| `_verify.py` | 52 | 端到端验证 MCP ↔ Cardinal 链路 |
| `_abtest.py` | 70 | 分离测试分析：对比「未按 KNOB-B」与「按过 KNOB-B」两种状态的差异 |
| `_timeline.py` | 99 | 按时间线拆解 MIDI 采集数据 |
| `_timeline2.py` | 75 | 按 2 秒分桶拆解，区分"哪一段操作产生了什么消息" |

这些是**研究过程的化石**，刻意保留——下次遇到同类问题可以直接改。

---

## 3. 外部程序与资源（不是我写的，但依赖它）

| 项 | 位置 | 作用 |
|---|---|---|
| **Cardinal standalone 26.02** | `C:\Program Files\Cardinal-win64-26.02` | 模块化合成器本体（Vulkan 无关，音频宿主） |
| **面板 SVG 资源** | `...\Cardinal.lv2\resources\` | **模块宽度的权威源**——1 HP = 5.08mm |
| **官方示例机架（15 个）** | `D:\Cardinal\refs\examples\` | 写新机架时照抄的素材；也是坐标单位的交叉验证样本 |
| **官方模板（5 个）** | `D:\Cardinal\refs\*.tpl.vcv` | 同上 |
| **模块源码缓存（37 个）** | `D:\Cardinal\tools\_srccache\` | 从 GitHub 抓的 `.cpp/.hpp`，端口与参数的原始依据 |
| **M-VAVE SMK25 + MidiSuite** | 键盘 + `<键盘驱动目录>` | 硬件与它的配置软件（11 张配置截图存 `refs/smk25_config/`） |
| **Python venv** | `<你的 venv 路径>` | 装了 `python-osc` + `zstandard` |
| **MCP 注册** | `<WorkBuddy 配置目录>\mcp.json` | server 名 `cardinal` |

---

## 4. 数据与产物

### 4.1 `params/modules.json` — 参数字典（47 KB）

15 个模块 / 248 个命名参数。每条形如：

```json
"Cardinal/HostAudio2": {
  "model": "HostAudio2",
  "params": { "0": { "name": "Level", "unit": " dB", "kind": "knob" } },
  "source": "plugins/Cardinal/src/HostAudio.cpp"
}
```

### 4.2 `music/knowledge.json` — 音乐库（15 KB）

覆盖的模块：`HostAudio2` `HostMIDI` `TextEditor` `ADSR` `Mixer` `Sum` `VCA-1` `VCF` `VCO` `Clocked` `MixMasterJr` `Plateau` `BassDrum9` `CR78` `ClosedHiHat`。

### 4.3 `patches/` — 20 个机架文件

**在用的：**

| 文件 | 说明 |
|---|---|
| `helm_full.vcv` | **主产物**：键盘全控件接入版，20 模块 / 35 缆，两行布局 |
| `helm_knobs.vcv` | 旋钮映射版（master + HostMIDIMap） |
| `helm_keys_master.vcv` | 你手改的主机架（加了 MixMasterJr 8 轨混音台） |
| `helm_keys.vcv` | 键盘机架：HostMIDI(复音8) → VCO → VCF → VCA-1 → Sum → Plateau |
| `helm_drums.vcv` | 鼓机架：Clocked 自走时钟(BPM100) → BassDrum9/ClosedHiHat/CR78 → Mixer |
| `helm_keys_warm_pad.vcv` | warm_pad 音色预设，供试听对比 |

**备份（保险，别删）：** `helm_before_full.vcv`、`helm_keys_live_backup.vcv`、以及 `helm_full_before_*` / `helm_full_3row_*` 系列共 12 个（对应每次重排/修复前的时间点）。

### 4.4 `refs/` — 参考与证据

| 文件 | 大小 | 内容 |
|---|---|---|
| `SMK25.md` | 24 KB | **键盘档案**：官方规格 / MidiSuite 挖掘 / MIDI 端口 / 六条链路 / 11 张配置截图对照 / 分离测试实证 |
| `FINDS.md` | 7.9 KB | **GitHub 仓库研究**：官方模板验证 / 漏用的模块 / 可抄范例 / OSC 边界 |
| `midi_dump.json` `_v2` `_v3` | 58~66 KB | 三次 MIDI 实测原始数据 |
| `drums_map.json` | 2.1 KB | WSTD-Drums 各鼓模块的声部数 / 采样族 |
| `_*.png`（8 张） | — | 诊断截图（含最终布局 `_g_centered.png`） |
| `smk25_config/*.png`（11 张） | — | 你提供的 MidiSuite 配置页截图 |

---

## 5. 我踩过的坑（经验）

按「**我错在哪 → 怎么发现的 → 学到的规矩**」排列。这部分是这份档案里最值钱的。

### 坑 1：端口编号靠记忆，结果记错了

**错**：早期笔记写「BassDrum9 的触发口固定是 IN17」。
**发现**：读 `WSTD-Drums` 源码（`_drums_probe.py`）后，发现真相是**通用公式 `IN(16 + 声部号)`**，不同鼓模块声部数不同，编号自然不同。
**规矩**：**端口和参数编号一律查源码，不许猜。** 这也催生了 `paramlib.py` 和 `_srccache/`。

### 坑 2：模块宽度也是猜的，而且错得离谱

**错**：宽度表靠目测估。`MixMasterJr` 估 60 格、`HostMIDIGate` 估 10 格。
**发现**：查下去发现 **Rack 是用面板 SVG 的物理尺寸决定模块宽度的：1 HP = 5.08mm**，而 SVG 就在本机。
**结果**：`mixmaster-jr.svg` 182.88mm ÷ 5.08 = **36 格**（多估了 24）；`HostMIDIGate` 实为 **14 格**。共纠正 6 处误估。
**规矩**：**能测量的就别估。** 并加了 `widths` 子命令做持续复测。
**附带的坑**：宽度表第一版按**文件名**做键，结果 `VCO.svg` 匹配到了别的插件的 27 HP（Fundamental 的只有 9）。键必须写「**插件/模块**」。

### 坑 3：坐标系认知错了三次（最惨的一个）

**第一次**：把 `pos` 当**像素**写，新模块 `pos=[300, 80]` 等于放到 4500px 外——你界面上「只看到线、看不到模块」。
**第二次**：改成「格」后写 `y=34/68`（当成格距）。
**第三次**：发现 `y` 的合法值其实只有 `0/1/2`——**它是行号，不是坐标**。
**怎么才查清的**：本机 20 个官方模板/示例，**哪怕是 39 个模块的多行大机架，y 值也全落在 −1 ~ 2 之间**。这是决定性证据。
**规矩**：**单位问题必须拿官方样本做交叉验证，不能靠推理自洽。**

### 坑 4：门禁第一版是"狼来了"

**错**：`guard` 在 10 个旧文件上全报 FAIL，看着很"严格"。
**发现**：那些"错误"其实是宽度估值误差导致的假阳性。
**规矩**：**分级告警——硬错误（一定坏）vs 提示（不合规范但能用）。** 一个总在报警的门禁会让人直接忽略它。

### 坑 5：光写规则没用，得写成卡口

**背景**：你要求「排班规则写到一个根深蒂固的地方，每次加东西都注意排班」。
**做法**：规则写进四处文档，**同时把 `layout_patch.py` 升级成带退出码的门禁**。
**规矩**：**纪律要靠工具强制，不能靠自觉。** 文档是给人看的，退出码是给流程看的。

### 坑 6：Cardinal 会覆盖我改的文件

**现象**：14:25 我排好的两行布局，15:28 被整个覆盖回三行。
**原因**：**你一按 Ctrl+S，Cardinal 把内存状态写回 `.vcv`**。
**规矩**：外部改文件必须在 Cardinal 关闭时做；或先开 OSC 走 `/load` 推送。

### 坑 7：我误判过「OSC 没开」

**现象**：`load_patch` 返回「已发送但没有收到回复」，我以为 OSC 没启用。
**真相**：**这台机器的 Git Bash 里 `head` 命令不存在**，我用 `| head -20` 截输出把结果全吞了。
**规矩**：**别用管道截断来判断"有没有结果"。** 一律用 python 过滤。

### 坑 8：用错了读回手段

**错**：想用 `watch_knobs.py` 轮询存档来验证旋钮映射是否生效。
**真相**：**自动存档的写入速率太低，它不是参数监视器。** 能读到"结构"，读不到"实时值"。
**规矩**：**先确认一个通道的能力边界，再决定用它做什么。**

### 坑 9：Add-Type 被安全策略挡了

**现象**：PowerShell 截图用 `Add-Type -AssemblyName System.Windows.Forms` 直接被拦。
**做法**：改用纯标准库 + Windows GDI 手写 PNG 编码器（`shot.py`）。
**规矩**：**环境限制不是终点，是换实现的信号。** 而且换出来的东西零依赖、可移植。

### 坑 10：格式假设导致一次返工

**现象**：用 `json.load()` 直接读 `helm_full.vcv` 报错。
**原因**：Cardinal 保存时把文件压成了 **tar+zstd 归档**。
**规矩**：**所有 .vcv 读写一律走 `patchio.py`。**

### 坑 11：OSC 的能力边界比想象中小得多

**事实**：Cardinal 的 OSC **只有 4 个消息**（`/hello` `/param` `/host-param` `/load`），**没有 MIDI 注入、没有参数读回**。
**规矩**：**读回改用自动存档 + 界面截图两条腿走路。**

### 坑 12：厂商目录名 ≠ patch 里的 slug

**现象**：源码在 `ValleyRackFree`，但 patch 里写的是 `Valley`；`Wasted_Audio/WSTD_Drums` 存下来变成 `WSTD-Drums`。
**规矩**：**写机架时以 patch 文件里的实际 slug 为准。**

---

## 6. 沉淀下来的五条原则（可复用）

1. **权威源优先** —— 官方示例 > 源码 > 面板资源 > 我的推理。你立的规矩「动手前先查仓库」是这条的起点。
2. **可执行 > 口头纪律** —— 能用退出码表达的规则，就不要只写在文档里。
3. **给 AI 装上感官** —— 截屏和实测数据的价值远高于反复推算。我在这上面错了至少三轮。
4. **分级告警** —— 硬错误和提示必须分开，否则门禁会被忽略。
5. **落盘即压缩** —— 每完成一个阶段就把状态写进 `HANDOFF.md` + 记忆，这样上下文丢了也不怕。

---

## 7. 文档与记忆的落盘位置（四层）

| 层 | 路径 | 作用 |
|---|---|---|
| **交接文档** | `D:\Cardinal\HANDOFF.md` | 新会话最先读的一份：路径地图 + 技术约束 + 当前状态快照 |
| **技能库** | `~\.workbuddy\skills\cardinal-patch-authoring\SKILL.md` | **权威技术细节**：端口表 / 参数表 / 全部踩坑 / 官方资料索引 |
| **用户级记忆** | `~\.workbuddy\MEMORY.md` | 每轮自动注入系统提示词 → 排班铁律写在这里才"根深蒂固" |
| **项目记忆** | `docs/DEVLOG.md` + `2026-09-12.md` | 长期项目笔记 + 按时间线的详细工作日志 |

---

## 8. 全部有意义文件总表（速查）

### Python 工具（`D:\Cardinal\tools\`）— 24 个 / 5080 行

```
[通信]   cardinal_mcp.py   700   12 个 MCP 工具 + 命令行入口
[文件]   patchio.py         74   .vcv 双格式读写（所有工具的地基）
[探测]   winmidi.py        173   Windows MIDI 零依赖封装
         midiprobe.py      127   MIDI 采集 + 自动分类分析
         winprobe.py        83   DPI / 窗口矩形探测
         shot.py           111   GDI 截屏（纯标准库 + 手写 PNG）
[生成]   make_full.py      297   生成「键盘全控件接入」机架
         make_knobs.py     213   写 HostMIDIMap 旋钮映射表
         fix_drum_bus.py   150   修鼓总线接线 + 输入口冲突自查
[知识]   paramlib.py       839   源码 → 参数字典（最大文件）
         musiclib.py       661   鼓型 / 和弦进行 / 音色配方
         vcvtool.py        151   模块端口反推（1422 模块字典）
         validate.py        85   机架合法性校验
[排版]   layout_patch.py   708   排班 + guard 门禁 + apply 重排
         state.py           91   文件 vs 内存 差异诊断
         watch_knobs.py     80   早期轮询工具（已确认无效，留档）
[侦察]   _drums_probe.py    84   \
         _fetch_examples.py 54   |
         _tpl_probe.py      37   |  8 个一次性研究脚本
         _mcp_test.py       66   |  刻意保留作化石
         _verify.py         52   |
         _abtest.py         70   |
         _timeline.py       99   |
         _timeline2.py      75   /
```

### 数据

```
D:\Cardinal\params\modules.json     47 KB   15 模块 / 248 命名参数
D:\Cardinal\music\knowledge.json    15 KB   9 鼓型 + 10 进行 + 8 配方
D:\Cardinal\refs\drums_map.json    2.1 KB   鼓模块声部数 / 采样族
D:\Cardinal\tools\_srccache\  (37 个 .cpp/.hpp)  端口与参数的原始依据
```

### 机架产物

```
D:\Cardinal\patches\helm_full.vcv          ★ 主产物（两行布局，20 模块 / 35 缆）
                    helm_knobs.vcv            旋钮映射版
                    helm_keys_master.vcv      你手改的主机架
                    helm_keys.vcv             键盘机架
                    helm_drums.vcv            鼓机架
                    helm_keys_warm_pad.vcv    warm_pad 音色预设
                    + 12 个时间点备份 + 2 个实时存档快照
```

### 文档与证据

```
D:\Cardinal\HANDOFF.md              29 KB   交接简报（含当前状态快照）
D:\Cardinal\refs\SMK25.md           24 KB   键盘档案（规格 / 挖掘 / 实测）
D:\Cardinal\refs\FINDS.md          7.9 KB   GitHub 仓库研究成果
C:\...\skills\cardinal-patch-authoring\SKILL.md  43 KB  权威技术细节
C:\...\.workbuddy\MEMORY.md        4.6 KB   跨项目长期规则
C:\...\memory\MEMORY.md            7.2 KB   项目长期笔记
C:\...\memory\2026-09-12.md         44 KB   今日工作日志
```

### 配置

```
<WorkBuddy 配置目录>\mcp.json          MCP 注册
<你的文档目录>\Cardinal
ative.json   Cardinal 设置
<键盘驱动目录>\                                键盘驱动与配置软件
```

---

## 9. 未完成 / 搁置

| 项 | 状态 |
|---|---|
| **LMMS 录音闭环** | 未做。目标是让 Cardinal 的输出能被 DAW 录下来 |
| **旋钮第 2 层（KNOB-B）** | 接不进。它发的是 Pitch Bend，而 `HostMIDIMap` 只认 CC。需要在 MidiSuite 里把旋钮 9-16 的 Type 从 MCP 改成 CC（图形界面操作，只能你做） |
| **触控条左右弯音** | 失效。ch9 需要你在 MidiSuite 里改成通道 1 |
| **踏板（CC64）** | 已配好 ADSR Sustain，但你无硬件 |
| **自动伴奏机架** | 候选方案：`Clocked` + `SEQ3` 琶音器/音序器 |
| **走带键（Transport）** | SMK25 上的播放/停止键目前完全没接 |

---

*本档案由舵手整理。技术细节以 `SKILL.md` 为准，当前状态以 `HANDOFF.md` 为准。*
