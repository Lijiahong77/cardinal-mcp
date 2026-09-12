# cardinal-mcp

> 一个让 AI 能直接操作 [Cardinal](https://github.com/DISTRHO/Cardinal) 模块化合成器的轻量外壳。
> 12 个 MCP 工具 + 24 个零依赖 Python 小工具 = 一个能版本管理、自动化、远程控制的合成器工作流。

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
- 用 **Cardinal 的 OSC（4 条消息）** + **Windows 屏幕截图** + **实时自动存档读回** 拼出一套
  **12 个语义化 MCP 工具**（`cardinal_load_patch` / `cardinal_set_param` / `cardinal_read_live` 等等）。
- 配套一组**零依赖的探测工具**：DPI 探测、MIDI 抓包、GDI 截屏、实时存档读回、布局门禁。
- 一本 `params/modules.json`：**15 模块 / 248 命名参数**，从 Cardinal 自带模块的 C++ 源码里抽取。
- 一本 `music/knowledge.json`：9 套节奏型 / 10 套和弦进行 / 8 套音色配方。
- 一套**排班门禁**：每次加新模块、重新接线，必须过一次 `layout_patch.py guard` 才准推送。

**不是什么**

- **不是 Cardinal 插件**——不修改 Cardinal 本身，仅在外部通过 OSC + 文件层操控。
- **不是音乐教学项目**——只解决"工程化与可遥控"，音乐知识库是顺带的脚手架。
- **不带第三方作品**——把 Cardinal 官方示例机架、MidiSuite 配置截图、源码缓存都从仓库里排除掉了，
  这些是别人的资产，使用 `docs/ATTRIBUTION.md` 标注来源，需要的自己去下。

---

## 适合谁

- 已经装了 Cardinal standalone + MIDI 键盘，想用 Cursor / WorkBuddy 这类 MCP-aware AI 直接调参数、换音色、改连线的人。
- 想把"手点鼠标搭的合成器机架"变成可以 `git diff` 的纯文本的人。
- 想要在没有 GUI 的环境（远程、CI）里预生成、预校验机架的人。

---

## 30 秒上手

### 1. 安装依赖

只需要两个 Python 包：

```bash
pip install -r requirements.txt
# 或者手动：python-osc + zstandard
```

依赖少是因为绝大多数工具都用标准库（`win32gui` / `ctypes` / `socket` / `tarfile` / `json`）。

### 2. 启动 Cardinal 并打开 OSC 通道

```text
打开 CardinalNative.exe
菜单：Engine → Enable OSC remote control   （顶部菜单，⚠️ 每次启动都要重新点）
```

验证 OSC 通了：

```bash
python tools/cardinal_mcp.py --selftest
# 期望最后一行：OK: All 12 tools reachable
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

## 它能做什么 —— 12 个 MCP 工具一览

| 工具 | 做什么 | 常用场景 |
|---|---|---|
| `cardinal_ping` | 发 `/hello` 检查 Cardinal 是否响应 OSC | 排查连通性 |
| `cardinal_list_patches` | 列 `patches/` 目录下所有 .vcv 机架 | 选要加载的机架 |
| `cardinal_patch_info` | 看某个机架的模块清单（拿到 moduleId 才好调参） | 改参数前的必备查询 |
| `cardinal_load_patch` | 把某个 .vcv 推给 Cardinal（含 zoom + gridOffset） | 让 AI 切音色 |
| `cardinal_set_param` | 拧任意模块的旋钮：`moduleId + paramId + value` | 改 cutoff / release / 等 |
| `cardinal_set_host_param` | 改 Cardinal 内置的 24 个宿主参数 | 调音频接口/采样率等 |
| `cardinal_read_live` | 读 Cardinal 正在运行的机架（走实时自动存档读回） | 想看用户在 GUI 里改了啥 |
| `cardinal_save_live` | 把当前 GUI 状态落盘成 .vcv | 用户手动改完不存档就丢 |
| `cardinal_module_params` | 列某模块的参数清单（名 → 编号） | 找参数编号 |
| `cardinal_find_param` | 把口语翻成参数编号（"亮一点"→Cutoff） | 让 AI 用自然语说话 |
| `cardinal_music` | 节奏型 / 和弦进行 / 音色配方查询 | 让 AI 用知识库回答 |
| `cardinal_apply_recipe` | 把音色配方写进当前机架 | 让 AI 一键换音色 |

---

## 项目结构

```
cardinal-mcp/
├── README.md                       ← 本文件
├── LICENSE                         ← MIT
├── requirements.txt                ← python-osc + zstandard
├── mcp.example.json                ← MCP 配置示例
│
├── tools/                          ← 24 个 Python 工具
│   ├── cardinal_mcp.py             ← MCP 主入口（1200 行）
│   ├── patchio.py                  ← 双格式读写 .vcv（JSON / tar+zstd）
│   ├── layout_patch.py             ← 排班门禁 + 自动重排
│   ├── paramlib.py                 ← 从源码抓参数字典
│   ├── musiclib.py                 ← 音色配方 / 和弦进行 / 节奏型
│   ├── make_full.py                ← 生成"键盘全控件"机架
│   ├── make_knobs.py               ← 写 HostMIDIMap 映射
│   ├── fix_drum_bus.py             ← 鼓总线修复 + 输入口自查
│   ├── winprobe.py                 ← DPI / 窗口探测
│   ├── winmidi.py + midiprobe.py   ← Windows 原生 MIDI 工具
│   ├── shot.py                     ← GDI 截屏（零依赖）
│   └── ... 更多辅助脚本
│
├── params/
│   └── modules.json                ← 15 模块 / 248 命名参数
│
├── music/
│   └── knowledge.json              ← 节奏型 / 进行 / 配方
│
├── patches/
│   ├── helm_full.vcv               ← 主机架：琴键+旋钮+触控+鼓垫全套
│   ├── helm_keys.vcv               ← 纯合成器机架
│   ├── helm_drums.vcv              ← 鼓机架
│   └── ... （.gitignore 排除了个人备份）
│
└── docs/
    ├── DESIGN-NOTES.md             ← 技术档案：完整解释整套东西怎么搭起来的
    ├── CARDINAL-REPO-NOTES.md      ← 上游 Cardinal 仓库的关键发现
    ├── SMK25-midi-map.md           ← M-VAVE SMK25 键盘 MIDI 实测档案
    └── ATTRIBUTION.md              ← 第三方资源来源标注
```

---

## 工作流示例

### "把合成器变亮一点"

```
你: 帮我把 Current Patch 的滤波器亮度调高一点
AI: → cardinal_patch_info  (拿到 VCF moduleId)
   → cardinal_find_param (口语 → "Cutoff")
   → cardinal_set_param (Cutoff value = 0.75)
   → 告诉你人话：把 cutoff 从默认 0.5 提到 0.75，听感会更亮
```

### "换一首和弦进行"

```
你: 给我做个 ii-V-I 的爵士伴奏
AI: → cardinal_music (progressions) 拿 ii-V-I 的 voicings
   → cardinal_patch_info 看现在的 ADSR / VCO 配置
   → cardinal_apply_recipe 写新参数
   → 你按一个键就能听到 ii-V-I 了
```

### "把鼓垫 3 的音色换成 Snare-B"

```
你: 第三号鼓垫想换成短一点的军鼓
AI: → cardinal_patch_info 找 SnareDrumN
   → 看到第 i 个声部的采样由 param(i) 控制
   → cardinal_set_param 把 SnareDrumN 的 param(2) 改成更"短"的采样编号
   → 让你敲一下键盘验证
```

---

## 硬件 / 软件环境（本项目在哪台机器上验证过）

> 这部分是给想自己复刻的人看的，告诉你要什么环境才能跑得起来。

### 软件

- **OS**：Windows 11（10.0.26200，64-bit）
- **Cardinal**：26.02（[DISTRHO/Cardinal](https://github.com/DISTRHO/Cardinal) 26.02 发行版 standalone，安装在 `C:\Program Files\Cardinal-win64-26.02\`）
  - 共 4 个变体：DISTRHO 本体 / FX / Mini / Synth
  - 启动用 `CardinalNative.exe`（≈100 MB，主 standalone）
  - 自带模块库（VCV Rack Fundamental + AudibleInstruments + 一众社区插件）
- **Python**：3.13.12（managed 解释器，装在用户目录的隔离 venv 里）
- **AI 客户端**：WorkBuddy（用其 MCP 配置）——同理 Cursor / Claude Desktop 也可以用同一份 `mcp.example.json`
- **MIDI 配套软件**（用户私有，不随附）：M-VAVE MidiSuite，配 M-VAVE SMK25 时有用

### 硬件

- **CPU**：AMD64（x86-64）
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
| 实时 MIDI/CV 注入 | Cardinal OSC 只有 `/load /param /host-param /hello` 四条消息，没有 MIDI 注入 |
| 参数变化自动回读 | 实时自动存档只在结构性事件后写盘（详见 DESIGN-NOTES 约束 16）。参数改变了看不见，只能人眼看 GUI |
| 无人值守（headless）运行 | Cardinal standalone 没有 headless 版本（VCV Rack Pro 才有，Cardinal 不带）|
| Linux/macOS 测试 | 本仓库只在 Windows 上跑通过；Python 工具都是跨平台的，但 `winmidi.py` / `winprobe.py` 用 Win32 API |
| LMMS / DAW 录音闭环 | 那是另一个项目（Cardinal.vst 装到 DAW 里），本仓库只到 standalone + OSC |

---

## 文档索引

| 文档 | 解决什么问题 |
|---|---|
| `README.md` | 我该不该装这个？装完怎么跑？ |
| `docs/DESIGN-NOTES.md` | 它是怎么搭起来的？24 个工具逐个解释、12 个踩坑、五条可复用原则 |
| `docs/CARDINAL-REPO-NOTES.md` | Cardinal 上游有什么值得抄的？OSC 边界 / 模块清单 / 不存在的功能 |
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
