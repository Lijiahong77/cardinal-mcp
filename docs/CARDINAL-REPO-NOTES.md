# Cardinal 仓库研究笔记

日期：2026-09-12　研究范围：DISTRHO/Cardinal 仓库 + 本地安装 `C:\Program Files\Cardinal-win64-26.02\docs\`

---

## 一、一句话结论

**我们之前的技术判断基本都对**（端口表被官方模板逐条验证），
**但漏用了两样东西**：Cardinal 官方提供的「宿主参数映射」和「MIDI CC 映射」模块，
以及一整套**现成的自动音乐范例机架**和**高质量音源模块**。

---

## 二、验证：我们做对了什么

官方 standalone 启动模板 `patches/templates/native.vcv`（已存 `refs/native.tpl.vcv`）的接线：

```
Cardinal/HostMIDI OUT0 -> Fundamental/VCO  IN0    (音高)
Cardinal/HostMIDI OUT1 -> Fundamental/ADSR IN4    (门)
Cardinal/HostMIDI OUT2 -> Fundamental/VCO  IN1    (力度 -> FM)
Cardinal/HostMIDI OUT6 -> Fundamental/ADSR IN5    (重触发)
Fundamental/ADSR OUT0  -> Fundamental/VCA-1 IN0
Fundamental/VCO  OUT0  -> Fundamental/VCA-1 IN1
Fundamental/VCA-1 OUT0 -> Cardinal/HostAudio2 IN0
```

对照我们的 `helm_keys.vcv` —— **七条线一模一样**。
说明技能库里那张端口表是权威正确的，不用再怀疑。

另：官方模板 `HostMIDI.data.channels` 默认是 `1`（单音），我们改成 `8` 才是弹和弦的关键，这个改动是对的。

---

## 三、发现的问题：`set_host_param` 一直在空转

官方模板里有两个我们没用的模块：

| 模块 | 作用 | data 结构（官方模板原样） |
|---|---|---|
| `Cardinal/HostParametersMap` | 把 24 个宿主参数映射到模块参数 | `{"maps":[{"hostParamId":255,"inverted":false,"smooth":true,"moduleId":-1,"paramId":0}]}` |
| `Cardinal/HostMIDIMap` | 把 MIDI CC 映射到模块参数 | `{"maps":[{"cc":-1,"moduleId":-1,"paramId":0}],"smooth":true,"channel":0}` |

- `hostParamId` / `cc` / `moduleId` 为 `-1` 或 `255` = **未映射哨兵值**
- 两个模块都带 `smooth: true`（内置平滑，参数不会跳变，适合做自动化）

**影响**：我们的 MCP 工具 `cardinal_set_host_param` 是往 OSC `/host-param` 发消息，
但机架里没有 `HostParametersMap` 接收并转发，所以**这个功能此前完全没生效**。
要生效必须：机架里有该模块 + `maps` 里建好 `hostParamId -> moduleId/paramId` 的映射。

---

## 四、可用的新能力（全部本地已确认存在）

### 4.1 音源升级 —— Mutable Instruments 全套（`AudibleInstruments`）

我们现在用的 `Fundamental/VCO` 是最基础的。本地已有：

| 模块 | 特点 |
|---|---|
| `AudibleInstruments/Plaits` | 宏振荡器，几十种合成模型 |
| `AudibleInstruments/Braids` | 数字振荡器，音色库极广 |
| `AudibleInstruments/Rings` | 物理建模谐振器，拨弦/铃声/共鸣 |
| `AudibleInstruments/Elements` | 模态合成，打击/弦乐 |
| `AudibleInstruments/Clouds` | 粒子合成，做氛围铺垫 |
| `AudibleInstruments/Marbles` | 随机序列生成（音高+门） |
| `AudibleInstruments/Warps` | 频率变换器 |
| `AudibleInstruments/Veils` | 多通道 VCA |

### 4.2 音序器 —— 把「写文件」变成「画界面」

| 模块 | 用途 |
|---|---|
| `rcm-modules/PianoRoll` | 钢琴卷帘，直接画音符 |
| `JW-Modules/GridSeq` | 网格音序器，适合和弦进行/旋律 |
| `JW-Modules/NoteSeqFu` | 多功能音符音序器 |
| `JW-Modules/NoteSeq16` | 16 步音符音序器 |
| `JW-Modules/DivSeq` / `EightSeq` | 分频/八步序列 |
| `WSTD-Drums/Sequencer` | 鼓专用步进音序器 |
| `BogaudioModules/AddrSeq` | 地址序列器 |

### 4.3 生成式 / 随机模块

`AriaModules`（含 Darius 宏音序器）、`BogaudioModules/Bogaudio-Walk2`（随机漫步）、
`AudibleInstruments/Marbles`、`Fundamental/LFO`（我们已用）

### 4.4 在 Cardinal 内部托管第三方插件

`Cardinal/Carla`（支持 LV2/VST2/JSFX）与 `Cardinal/Ildaeil`（Carla 精简版）。
**含义**：Cardinal 自己就能挂外部 VST，不必非用 LMMS 才能扩展音源。

---

## 五、可以照抄的官方范例机架（已下载到 `refs/examples/`）

| 文件 | 模块构成 | 对我们价值 |
|---|---|---|
| `falkTX_-_Mini-Arp-Seq.vcv` | PianoRoll + Rings + LFO + ADSR + VCA-1 + HostTime | **琶音/音符自动演奏**，最贴近下一步 |
| `falkTX_-_Random-Progress-Pluck-Rev.vcv` | GridSeq + Plaits + LFO + Plateau + rackwindows/mv | **随机和弦进行 + 拨弦 + 混响**，即「AI 生成和弦」的现成实现 |
| `SpotlightKid_-_Classic-Polysynth.vcv` | 经典复音合成器 | 复音键盘音色的参考做法 |
| `falkTX_-_Salomonis-MonoRegen.vcv` | Braids + Plaits + Veils + AddrSeq + EqMaster | 多音源叠加 + 均衡 |
| `nooneknowspeter_-_Catalyst.vcv` | Darius + Clouds + Walk2 + Clocked + DualDelay | 生成式氛围 |
| `DRMR_-_*` 4 个 | 鼓/贝斯/失真 | 节奏与低频处理参考 |

共 15 个，全部在 `refs/examples/`。**写新机架前先看这里，不要凭空造。**

---

## 六、OSC 能力边界（确认，别再白费力气）

官方 `docs/OSC-REMOTE-CONTROL.md` 明确列出**只有 4 个消息**：

| 消息 | 作用 | 有无回复 |
|---|---|---|
| `/hello` | 连接测试 | 有 `/resp hello` |
| `/param h:moduleId i:paramId f:value` | 改任意模块参数 | 无 |
| `/host-param i:port f:value` | 改 24 个宿主参数之一 | 无 |
| `/load b:blob` | 加载 patch（pax tar+zstd） | 有 `/resp load` |

**结论**：
- ❌ 没有 MIDI 注入 → **AI 实时演奏只能走虚拟 MIDI 端口**（Python mido → 虚拟端口 → HostMIDI 模块），不能靠 OSC
- ❌ 没有读回 → 读回的唯一路径仍是 `%TEMP%\Cardinal.0001\patch.json`
- ❌ 没有 CV 注入
- ✅ 只有 standalone 有 OSC；插件形态没有

---

## 七、环境细节与坑

1. **不能装额外模块**（FAQ）。Cardinal 是自包含的，1400+ 模块就是全部。
   例外：Carla/Ildaeil 可托管外部 LV2/VST2。
2. **headless 只有 Linux 版**（`DIFFERENCES.md`: "Proper Linux headless mode: Yes"）。
   Windows 版必须带 GUI → **Windows 上做无人值守渲染/录音不可行**，录音得靠 LMMS 或其他 DAW。
3. **Cardinal 有意不自动保存**（与 VCV Rack 不同），且不同变体（main/FX/Synth）用不同配置文件。
   → 我们的 `cardinal_save_live` 工具不是可有可无，是必需品。
4. **UI 缩放**可用环境变量强制：`DPF_SCALE_FACTOR=1.5`
5. **厂商目录名 ≠ patch 里的 plugin slug**：
   `Valley`→`ValleyAudio`｜`rcm`→`rcm-modules`｜`AriaSalvatrice`→`AriaModules`｜
   `Bogaudio`→`BogaudioModules`｜`Wasted_Audio`→`WSTD-Drums`
   → 校验脚本必须按 slug（patch 内写法）比对，不能按目录名。
6. **插件形态的音频 IO 只有 2 进 2 出**（synth/fx），standalone 才有 8 IO。

---

## 八、建议的下一步（按性价比排序）

1. **修 `set_host_param`**：给机架加 `Cardinal/HostParametersMap` 并把映射写进 data，
   让 24 个宿主参数真正能控制模块参数（带平滑）。
2. **做「自动伴奏」机架**：抄 `falkTX_-_Mini-Arp-Seq.vcv` 的思路，
   用 `PianoRoll` 或 `GridSeq` + `Plaits`/`Rings`，让 Cardinal 自己演奏和弦/琶音，
   人只管弹旋律。这是「AI 辅助创作」最快见效的一步。
3. **升级键盘音色**：`Fundamental/VCO` → `Plaits` 或 `Rings`，音色档次立刻不同。
4. **MIDI 实时注入通道**：venv 装 `mido` + `python-rtmidi`，
   配虚拟 MIDI 端口，实现「AI 直接弹奏 Cardinal」。
5. 鼓组扩充：`WSTD-Drums/Sequencer` 做能点格子的鼓机。

---

## 附：本笔记涉及的文件

- 官方模板 → `D:\Cardinal\refs\*.tpl.vcv`（5 个）
- 官方示例 → `D:\Cardinal\refs\examples\*.vcv`（15 个）
- 侦察脚本 → `D:\Cardinal\tools\_tpl_probe.py`、`_fetch_examples.py`
- 本地文档 → `C:\Program Files\Cardinal-win64-26.02\docs\`
