# 企划 2 · 内置编曲模块 —— 功能规格（草案 v0.1）

> 立项：2026-09-21　状态：**待李评审**　范围：只写规格，不含代码
> 上游依据：`STATUS-OVERVIEW.md` §1.2、`BISET-REFERENCE-MAP.md`、`ENV-READINESS-REPORT.md`
> 本条目的：把 12 个字（**"预设鼓组/琴组 + 手弹录制"**）展开成能在 Cardinal 里落地、可施工、可验收的东西。

---

## 0. 一页速览

**这个模块要干的事**：让你用键盘**弹进去**鼓和琴，把它**记下来**，然后**排进时间轴**回放、反复改。

**它不干的事**：不发明新音色（音色用 Cardinal 现成的）、不做音频处理、不做混音。

**一句话边界**：它是**"音符的记事本 + 时间轴"**，声音仍然是 Cardinal 里那些 VCO/采样器/鼓模块发的。

**当前最大未知**（见 §5）：①"预设鼓组/琴组"在 Cardinal 里没有对应物，必须先翻译；②"录制"录哪一层。

> ✅ **09-21 10:52 拍板进度：五问全部答完** —— ①鼓组 = **混搭** ②录制 = **L1 音符事件** ③时间轴 = **先自设计、再参考**
> ④**一个模块** ⑤名 = **`MiniArranger`**；形态 = **一块内装多条声部**（§4.3）；
> 轨数 = **扩展器架构，主 4 + 按需接**（§4.2.1；机制实证与代价见 **§11**）。
> ✅ **五问 + 两条结构参数全部拍板完毕**（§5 / §4.2.1 / §11.7）→ **`MiniArranger` 骨架已写出并编进 exe**（§12）。

> ⚠️ **09-21 二次调研后有重大修正**：L1 录制**不是空白** —— Cardinal 里已有一个完整可用的
> **`rcm-pianoroll`（Piano Roll）**，而且**已经在你手上那个 exe 里**。
> 读 §1 事实 2 与 §3 时请以 **§8** 为准（那两处在二次调研后已不准确）。

> ⚠️ **09-21 11:15 第三次调研（李发来截图）**：本机 86 个包 / **1424 个模块**里
> 确有多路编排音序器 —— `JW-Modules/Arrange`(16 行 × 64 步)、`CVfunk/Arrange`(7 通道 · **可录 · 可复音**)、
> `Phrase-Seq-32`、`NoteSeqFu`(**复音钢琴卷帘**)。
> **§4.3 / §8.3 / §11 里「多轨与复音无现成件」的说法均已作废** → 以 **§13** 为准。

---

## 1. 三个必须先把话说死的事实

### 事实 1 · Cardinal 里没有"音色库"这个概念

Cardinal 是**模块化合成器**，不是电子琴。它内部**不存在** GM 那套 128 种乐器的音色库 —— 声音永远等于「**模块 + 连线 + 参数值**」这三样的组合。

所以「预设鼓组 / 琴组」这四个字**没法直接落地**，必须先翻译成 Cardinal 的语言。三种翻译方式见 §2，代价差得很大。

### 事实 2 · "手弹录制"在 Cardinal 里是**空白区**

用三种方式把 1422 个模块（85 个包）查了一遍：

| 查法 | 结果 |
|---|---|
| `modsearch.py tag Recording` | **6 个**：Transport、Fax、Looper、IceTray、ReMOVE Lite、XY |
| `modsearch.py find record` | 9 个（含上面 6 个） |
| `modsearch.py find midi` | 22 个，**全部是 MIDI 映射/输入输出类**，无一录制 |

逐条看这 6 个"录音类"到底录什么：

| 模块 | 实际录的东西 | 是"录音符"吗 |
|---|---|---|
| `EnigmaCurry Transport` | 走带控制（播放/停止/录音状态） | ❌ 它只管指挥，不管录 |
| `FehlerFabrik Fax` | **CV 信号**（电压序列） | ⚠️ 最接近，但录的是电压不是音符 |
| `LilacLoop Looper` | **音频**（立体声多轨活循环） | ❌ 音频 |
| `PathSet IceTray` | 音频（磁带延迟式） | ❌ 音频 |
| `Stoermelder ReMove Lite` | **旋钮参数**的自动变化 | ❌ 参数，不是音符 |
| `voxglitch XY` | 手势（两路 CV） | ❌ CV |

> **结论（09-21 二次调研修正）**：这 6 个"录音类"里**确实没有**录音符的。**但排查方法有漏** ——
> 我只搜了 `Recording` 标签与 `record` 关键字，漏掉了 `rcm-modules` 包：
> 它的 **`rcm-pianoroll`** 就是一个完整的 L1 录制器，**只是标签里没写 Recording**。
> ⇒ **"空白区"这个结论不成立**，见 §8。企划 2 的价值需要重新定位。

### 事实 3 · 但"读 MIDI 文件弹出来"这件事，Cardinal 里**已经做过了**

这是本次调研最大的意外收获。

`BaconMusic` 包里的 **`PolyGenerator`** 模块，表面描述是"生成测试用复音 MIDI 序列"，但翻开源码（`plugins/BaconPlugs/src/PolyGenerator.hpp`）会发现它内部藏着一个 **`MidiFilePlayer`** 类：

- 真的读标准 MIDI 文件：`smf::MidiFile mf; mf.read(...); mf.doTimeAnalysis(); mf.linkNotePairs();`
- 输出 **3 路复音 CV**：`TONE_CV`(v/oct 音高) + `VEL_CV`(力度) + `GATE_CV`(门)
- 内置 **70 首古典 MIDI**（哥德堡变奏曲 30 段、贝多芬 13、肖邦 24、德彪西 2），打包在 `plugins/BaconPlugs/res/midi/`
- **代码量：约 90 行**（`MidiFilePlayer` 类，L215–311）
- 解析库 **`smf`（craigsapp/midifile）已在源码树**：`plugins/BaconPlugs/libs/midifile/`（含 `MidiFile.cpp`、`MidiEvent.cpp` 等 6 个实现 + 6 个头文件）

**三点推论，都指向降低成本：**

1. **不必从零发明**。"MIDI 文件 → 复音 CV"这条链，Cardinal 已有可运行、可照抄的样板。
2. **缺口 2（虚拟 MIDI 通路）有了第三条解法**：不装外部虚拟 MIDI 软件，也**不用**外部通路 —— 写一个"能加载**任意** MIDI 文件"的 Cardinal 模块，输出直接接 VCO/ADSR。全在 Cardinal 内部完成。
3. 现成模块的**短板**恰好是我们要补的：它的曲目**硬编码在代码里**（文件名写死 `res/midi/goldberg/...`），用户**没法指定自己的文件**；而且它**只能播不能录**。

> ⚠️ **修正记录**：本文档初稿曾把 `PolyGenerator` 描述当作"测试信号发生器"、判断 Cardinal 无 MIDI 解析能力 —— **错误**。以源码为准。

---

## 2. 「预设鼓组 / 琴组」的三种落地形态

三种都能做，代价与产出完全不同。**这是本企划第一个需要你拍板的分岔。**

### 形态 A · 模块片段预设（"patch 片段"）

- **是什么**：把"一组模块 + 它们之间的连线 + 每个旋钮的值"存成一个可复用的片段，一键铺到机架上
- **例**：「909 鼓组」= 一套 BassDrum9 + SnareDrumN + Hat + 音序器 + 它们之间的连线与参数
- **✅ 好处**：音色可以做得极复杂（不受单个模块限制）；随时可以微调；和现有工作流（手拧机架）完全一致
- **❌ 代价**：Cardinal **没有"模块内部嵌套 patch"的原生概念**。要么靠 OSC 从外部推（**要求你开着 Cardinal、我这边推**），要么自己写一个"片段加载器"模块（要动文件系统读写的代码）
- **现成参照**：无。容器格式要自己设计

### 形态 B · 单模块内置若干预设

- **是什么**：写**一个模块**，内部硬编码 N 套音色参数（比如 Kick / Snare / Hat 各一套），旋钮切档
- **例**：`WSTD-Drums` 整包就是这么干的（BassDrum9 是"基于 909 的底鼓"，一个模块一种鼓）
- **✅ 好处**：一个模块解决，接线极简；**完全自包含、离线可用**；不受外部文件影响
- **❌ 代价**：要自己写 DSP（振荡器、包络、噪声、可能的滤波器）；每加一种鼓都要改代码重编；音色变化不如 A 丰富
- **现成参照（可参考不可直接用）**：`WSTD-Drums` 整包 **17 个 Drum 模块**、`Autinn Kicker`(底鼓)/`Lurer`(军鼓)、`mscHack SynthDrums`(3 通道合成鼓)

### 形态 C · 采样器 + wav 文件

- **是什么**：用 Cardinal 现成的采样器模块，加载自己准备的 wav（底鼓一下、军鼓一下）
- **✅ 好处**：音色最真实最"像唱片"；**一行 DSP 都不用写**；换音色 = 换文件，零重编
- **❌ 代价**：**本机没有任何音色库**（见 `docs/SAMPLING-GUIDE.md`），wav 要你自己找/自己录；涉及素材来源与授权；采样器模块的复音/多垫控制要自己接线
- **现成参照**：`voxglitch SamplerX8`（8 个立体声采样播放器挤在一个模块里）、`voxglitch Sampler16P`、`Bidoo cANaRd`（带切片与瞬态检测）、`SonusModular Campione`

> **三条可以混用**：例如「鼓走 C（采样）、琴走 B（合成）」。不必三选一到底。

---

## 3. 「手弹录制」的三种落地层次

"录下来"录的是哪一层，决定它能被怎么改。**这是第二个要你拍板的分岔。**

| | **L1 · 录 MIDI 事件** | **L2 · 录 CV 电压** | **L3 · 录音频** |
|---|---|---|---|
| 存什么 | 音高 / 力度 / 起始时刻 / 时长 | 每个采样周期的电压值 | 波形 |
| 录完能改什么 | **全都能改**：改音、改速度、改力度、量化、换音色重放 | 只能整体处理（移调、拉伸） | **基本不能改**，只能剪 |
| 数据量 | 极小（一首曲子几十 KB） | 大 | 很大 |
| 实现难度 | 中（要定数据结构；现成件见 §8 / §13） | 中 | 低 |
| 现成参照 | ⚠️ **有：`rcm-pianoroll`**（见 §8；代价是**单声道 + 量化录制**） | `FehlerFabrik Fax`（CV Recording Sequencer） | `LilacLoop Looper` |
| 实现依赖 | 不需要外部通路 —— 键盘输入由 `HostMIDI` / `HostMIDIGate` 提供 | 同左 | 同左 |

**输入从哪来？** 这条已经通了 —— 你的 SMK-25 键盘 → Windows MIDI → Cardinal 的 `HostMIDI` 模块（今天实测出声）。所以**录制器的输入侧不缺任何东西**。

**一个对你演奏数据有用的事实**（今天实测）：你弹的音符时值 0.04–0.78 秒（均值 0.22 秒）、力度 32–107（均值 67）。**这些是"人弹得出来"的真实范围** —— 量化网格、默认力度这类参数，应该照你的习惯定，而不是拍一个教科书数字。

---

## 4. 模块边界（§4.1 §4.3 已拍板 · §4.2 结构草案）

> 下面是"如果做 L1 录制 + A/B/C 播放"，模块大致长什么样。
> **端口名与数量都可在评审时改。**

### 4.0 「一个模块还是两个模块」到底在问什么

> 李 2026-09-21 说「我没搞懂这个东西嘛」→ 本节专为解释，不是设计变更。

**先对齐一个词**：Cardinal 里的**"模块"** = 一块带面板和插孔的小盒子（通常是几 HP 宽、
一列旋钮加一排插孔）。所以这个问题就是：

> 把「录你手弹的东西」和「把录下来的东西排成歌播出来」这两件事，
> 装进**一块盒子**，还是分成**两块盒子**？

| | **一个盒子** | **两个盒子** |
|---|---|---|
| 长什么样 | 一块大面板：左边卷帘编辑器（音符），右边走带控制（播放/停/循环） | 盒子 1「录音器」只管听键盘、记下来、显示与编辑；盒子 2「播放器」只管把记下的音符按时序吐出去 |
| ✅ 好处 | **零接线**（自己跟自己连）；用时只放一个东西 | 面板清爽；**两件事的使用时机根本不同**（录的时候你在弹、播的时候机器在跑），可以只放当下要用的那块；以后升级只动其中一块 |
| ❌ 代价 | 面板会很挤；只想"播放"也得把整个盒子放进来；以后加功能只能往同一块面板上继续塞 | **两块盒子之间要接一根线**（音符数据得从录音器递给播放器） |
| 现成对应物 | ⭐ **`rcm-pianoroll` 就是这个形态** —— 录和播都在同一块盒子里 | 生态里也有先例：Biset 的 Tracker 拆成 8 块模块分工 |

**类比**：是买一台"能录能放"的机器，还是买"录音笔 + 播放器"两台。
功能上限一样，区别只在**东西分几件、机架长什么样、以后好不好扩展**。

**这个选择为什么必须先定**：它决定"你要自建的那个模块"是**一个**
（= 现有 Piano Roll 的加强版），还是**两个**（= 两块盒子要对齐接口）。

### 4.1 ✅ 拍板：**一个模块**（不拆两块）

李 2026-09-21 10:41：「Piano Roll 那个…一块那不就可以了吗？我觉得一块也不复杂呀，**你就一块呗**。」

⇒ **作废**本节早先版本的"拆成 `Recorder` + `Player` 两块"草案。
**录制与播放装在同一块模块内部。**

| | ✅ 好处 | ❌ 代价 |
|---|---|---|
| **一个模块** | **零接线**（自己跟自己连）；用时只放一块；所有东西都在视线里 | 面板要挤一点；只想"播放"也得整块放进来（可接受 —— 现成件本来就是这么做的） |
| ~~两个模块~~ | ~~面板各自清爽；可只放要用的那块~~ | ~~两块之间要接一根线、接口要自己对齐~~ |

### 4.2 一块模块的内部结构（多声部版 · 草案）

> 2026-09-21 10:43 李拍板「**乙 · 一块 = 多条声部**」后重写。
> 端口名与数量仍可在评审时改，但**下面标"拍板"的三条是结构定式**。

**关键结构决定 —— 键盘输入只有一组，不是每轨一组：**

| 类别 | 内容 | 说明 |
|---|---|---|
| 时钟输入（**全块共享**） | `CLOCK` / `RESET` / `RUN` | 照抄 `rcm-pianoroll` 语义（`RUN` 是**翻转**，见 §9.2） |
| 录制输入（**全块共享一组**） | `RECORD`（脉冲翻转）+ 键盘四路 `VOCT` / `GATE` / `RETRIGGER` / `VELOCITY` | ⚠️ **不是每轨一组**。见下方"为什么" |
| 输出（**每轨一组**） | 每轨 `VOCT` / `GATE` / `RETRIGGER` / `VELOCITY` × N 轨 | 这是面板变宽的主因 |
| 参数 · 全局 | 播放/停、循环开关、BPM、当前**编辑**轨、当前**录制**轨 | |
| 参数 · 每轨 | 量化网格（1/4 … 1/32）、移调、静音、独奏 | |
| 状态 | **N 条独立音符表**（起始时刻 / 音高 / 力度 / **时长**），每轨一张 | |
| 面板布局 | 上：卷帘编辑器（只画**当前选中轨**）；下：走带控制 + **轨道选择条**（1 2 3 4 …） | |

**为什么键盘输入只能一组**（这是个必须现在就定死的结构）：
如果"每轨一组键盘输入"，4 轨就是 16 个输入口 —— 面板塞不下，也没人这么接。
正解是：**一组共享输入 + 面板上一个"当前录制轨"选择**。
你弹之前先在面板上选好"这一遍录给第几轨"，弹完切轨再录下一轨。
→ 这与 `rcm-pianoroll` 的"录完接着弹就覆盖同一轨"习惯基本一致。

**⚠️ "轨道"和"复音"是两件不同的事，别混**（§4.3 拍板后才需要拆开讲）：

- **轨道** = 不同**声部**（鼓 / 琴 / 弦各一轨），每轨通常接一个不同音色；
- **复音** = **同一条轨里**同时响好几个音（弹和弦）。
- 李要的"鼓琴弦一起响"靠**轨道**；"录和弦"靠**复音**。**两者都要做，不是二选一。**

**与 `rcm-pianoroll` 的差异 —— 这就是自建模块要补的缺口**：

| # | 缺口 | 现成件现状 |
|---|---|---|
| 1 | **多声部（轨道）** | 一块只管一轨；多声部靠"并联多块" |
| 2 | **复音（和弦）** | 单声道，和弦录不进去 |
| 3 | **音符时长** | step 没有长度字段，每个音符长度固定 |
| 4 | **歌曲级时间轴** | 只有 pattern，没有"段落排成曲"这一层 |

> ⚠️ `CLOCK` / `RESET` / `RUN` / `RECORD` 四个口的语义**直接照抄 `rcm-pianoroll`**（§9.1 §9.2），
> 这样现有接线方式、外部按钮模块的做法都能原样沿用，**不自创一套**。

#### 4.2.1 ✅ 拍板：**扩展器架构 —— 主 4 轨 + 按需接**（2026-09-21 10:52）

李 10:47 表态：「**取几轨…大点也没有关系**」（要求往大取）。⇒ 本节把**真实上限**摆出来供他挑。

**✅ 10:52 已拍板**：走**扩展器架构（主 4 + 按需接）** —— 结论见本节末，机制实证与代价见 **§11**。

**先给结论：真正的约束不是性能，是面板宽度。**

| 约束 | 实际情况 |
|---|---|
| 性能 / 代码 | **不是瓶颈** —— 每帧只是对 N 条轨循环一次；数据层是 `vector`，几百轨也无压力 |
| **面板宽度** | **真约束** —— 每轨要 3–4 个输出口；口区密度参照 `rcm-pianoroll`（40 HP 装 19 口 ≈ **2.1 口/HP**） |
| 一屏可读性 | Cardinal 在 100% 缩放下约能放 **100 HP**，超了要缩小或横向滚 |

**两种面板布局，宽度差近一倍：**

| 布局 | 面板上要放什么 | N 轨总宽估算 |
|---|---|---|
| **A · 编辑区在面板上**（`rcm-pianoroll` 那种） | 口区 + 一整块卷帘编辑区（编辑区本身 35 HP 起） | N=4 ≈ **45 HP** ｜ N=16 ≈ **70 HP** |
| ⭐ **B · 编辑区走弹窗**（Entrian 的做法，见 §10.2） | 口区 + 一块**小屏幕**（显示当前 song + 播放头） | N=4 ≈ **25 HP** ｜ N=16 ≈ **45 HP** ｜ N=32 ≈ **75 HP** |

⇒ **要轨数大，就必须走 B**（把编辑器从面板里拿出来）。这正是 Entrian Timeline 能塞下 10 轨的原因。

**生态档位（每个都有实物）**：

| N | 谁这么做 | 备注 |
|---|---|---|
| **4** | `ImpromptuModular/Foundry`（**已在你的 exe 里**）、`JP Four Track` | 最常见的档位 |
| 10 | `Entrian Timeline`（商业 $30） | 三列输出，每轨一组 |
| **16** | `Squarp Hapax`（硬件 $1299）、`VCV Rack` 复音上限、`JW NoteSeq*` | **生态里反复出现的数字** |

**★ 要"越大越好"的正解：扩展器架构（expander）**

主模块固定 **4–8 轨**（保证面板可读），不够就**接扩展器加轨**，理论上无上限。
生态先例：`FoundryExpander`、`JP Four Track Expander`（每接一个 +64 note block）。
⇒ 这比"一开始就画 100 轨"好：**面板不失控，需要多少加多少。**

**✅ 拍板（2026-09-21 10:52）：用扩展器架构 —— 主模块 4 轨 + 按需接扩展器**

李原话：「**扩展器　主 4 + 按需加　"越大越好"的正解，面板永不失控**」。

⇒ 主模块面板固定 **4 轨**；每接一块扩展器 **+4 轨**。
「这机制能不能用、怎么用、坑在哪」已做源码级核实，见 **§11**
（含一条必须避开的 VCV 已知 bug，以及一处与生态惯例不同的地方）。

**⚠️ 关于"100 轨"的实话（保留）**：代码层面做得到（就是个循环），但 100 轨 = **300 个插孔 = 200+ HP 宽**，
一屏放不下，接线要一直横向滚。**扩展器架构解决的正是这个 —— 面板宽度不随轨数增长。**

### 4.3 ✅ 拍板：一块内部装**多条声部**（乙）

李 2026-09-21 10:43 原话：「**乙 · 一块 = 多条声部**」

⇒ 与本轮 §4.1「一个模块」合并后的完整形态：
**一块模块，内部装 N 条独立声部（轨），一个面板看全。**

| | ~~甲 · 一块 = 一条声部~~ | ✅ **乙 · 一块 = 多条声部** |
|---|---|---|
| 形态 | ~~每轨放一块，靠并联多块凑~~ | **一块内部 N 轨，一个面板看全** |
| ✅ 好处 | ~~面板小、代码简单~~ | **不用挨台翻卷帘**；"混搭多音色"在一处就能编 |
| ❌ 代价 | ~~没有"一处看全"的界面~~ | **面板大很多**；内部数据结构与 UI 复杂度**上一个台阶**（⚠️ 但「无现成件可抄」已被 **§13 推翻**） |
| 现成参照 | `rcm-pianoroll` 一块管一轨 | **有** —— `JW-Modules/Arrange`(16×64 门控) · `CVfunk/Arrange`(7 通道·可录·可复音) · `PhraseSeq32`(2 轨多乐句) · `NoteSeqFu`(复音卷帘)，见 **§13** |

**这条决定连带出两点**（都已写进 §4.2）：

1. **键盘输入只能一组共享**（+ 面板选"当前录制轨"）—— 每轨一组的话 4 轨就是 16 个输入口，塞不下；
2. 新参数 **N 轨取几**（见 §4.2.1），文档暂按 4 起草。

**代价要说清楚**：选乙意味着面板与内部结构复杂度上一个台阶。
⚠️ **但「没有现成件可以直接抄」是我 09-21 的错误判断，已被 §13 的全量扫描推翻**：
`JW-Modules/Arrange`(16×64 门控) · `CVfunk/Arrange`(7 通道·可录·可复音) ·
`PhraseSeq32`(2 轨多乐句) 都是现成的多路音序器，`NoteSeqFu` 还是 32×32 复音卷帘。
**仍缺的只有 per-note 音符时长与「一处看全」的整合**（§13.4）。

---

## 5. 开放问题 —— 拍板记录

> 2026-09-21 10:37 李口头答复。**原话要点照录，别按我的理解改写成"更合理"的说法。**

| # | 问题 | 状态 | 李的答复 |
|---|---|---|---|
| **1** | 「预设鼓组 / 琴组」形态 | ✅ **混搭** | 「不用强去实现一个所谓的预设放在里面」；重点在**做歌时能把鼓、琴、弦乐都挂上去**；「你想混搭就混搭，那就混搭嘛」 |
| **2** | 「手弹录制」录哪一层 | ✅ **L1（录音符事件）** | 「L1 相对复杂一点，但是可编辑性强…更符合我的一个认知」；「能搞就搞」 |
| **3** | 一个模块还是两个模块 | ✅ **一个模块**，且**内部多声部** | ①「Piano Roll 那个…**一块那不就可以了吗**？**你就一块呗**」⇒ 见 §4.1；②「**乙 · 一块 = 多条声部**」⇒ 见 §4.3 |
| **4** | 包名与模块名 | ✅ **模块名 = `MiniArranger`** | 「那个名字当然是**我们自建模块的名字**，你就**改成英文的**吧」⇒ 中文名「迷你编曲机」的英文标识定为 **`MiniArranger`**；**插件包名仍是占位的 `Starsea`**（李未要求改） |
| **5** | 时间轴怎么做 | ✅ **先自己设计，再参考** | 「你先自己设计，然后去参考也行」⇒ 自己的设计为主导，Biset Tracker / `rcm-pianoroll` 作参照 |

### 5.1 Q1 的正确解读（别读偏）

李要的**不是**「内置一套音色库」，而是：**编曲器能把鼓、琴、弦乐同时挂上去并驱动它们。**
「你能加上去就行了」——诉求在**驱动**，不在**预置**。

⇒ 落地含义要分成两层看：

- **音色层**：A / B / C 按需混搭（鼓走采样、琴走合成…），**不追求统一形态**，也不必先建库。
- **编曲层**：要能**同时驱动多个声部**。现成件已经能做到 ——
  **并联多台 `rcm-pianoroll`，共用同一个 `Clocked` 的 CLOCK + RUN**，各弹各的、自动同步。
- **缺口**：现成件**没有"一处看全"的界面**（要挨台去看每块的卷帘）。
  这恰好是自建模块最该补的一块，也是"多声部编曲器"的核心价值。

### 5.2 Q2 的澄清：L1 **不等于** `.mid` 文件

李问「它是搞成 midi 文件是吧？」—— 这句需要纠正，否则后面会一路错下去：

- **L1 录的是"音符事件"**：什么时候、哪个键、多大力、按住多久 —— **四个数字**，不录声音本身。
- **类比**：**L1 = 乐谱**（可改音、可改快慢、可换乐器重放）；**L3 = 录音带**（只能剪）。
  李要的"可编辑性强"，选的就是乐谱那一层，**选对了**。
- **能不能存成 `.mid` 文件，是"存哪儿"的问题，不是"录哪一层"的问题。**
  现成的 `rcm-pianoroll` 就把 L1 数据**存成 `.vcv` 里的纯 JSON**（见 §8.4），**没走 `.mid`**。
- ⇒ 这个区别很要紧：既然数据是 `.vcv` 里的纯 JSON，
  **AI 可以直接把音符写进去** —— 李说的「你帮我敲打录进去就行」**不需要他手弹**（见 §8.4）。

### 5.3 Q3 的连带选择：已定（§4.3）

`rcm-pianoroll` 那种「一块 = 一轨」的形态，李**没有选**。
他选的是 **「乙 · 一块 = 多条声部」**，即一块模块内部装 N 条轨、一个面板看全 —— 见 §4.3。
连带新参数 N 见 §4.2.1。

---

## 6. 为什么不改造 Biset（回扣 09-21 的决定）

你的判断（"参考 Biset，但不要拿过来改造"）**有源码层面的硬证据支持**：

1. **Biset 没有"手弹录制"**。手册第 15 页原文：`recording mode (not available yet !)`；Matrix 视图标着 "Not handled yet"。
2. **体量悬殊**。Biset 全量 **20876 行**，Tracker 系列 **10691 行**（仅 Tracker 本体 7716 行）；而我们要参照的 `MidiFilePlayer` **约 90 行**。
3. **作者已停更**，上游不会修 bug，改造后要自己维护整条分支。

⇒ **做法**：Biset 只作**设计意图**的参照（"pattern 排进 timeline"这个形态成立），**代码不去动它**。

---

## 7. 施工前置与进展（2026-09-21 实测更新）

| 项 | 状态 |
|---|---|
| 交叉编译链（Windows 版） | ✅ 已通（09-20） |
| 单文件编译（抓语法错） | ✅ **数秒** |
| 交叉编译全量刷新（含 `plugins.cpp` 重编 + 432 MB 重新归档） | ✅ **17–20 秒** |
| 重新链接 100 MB 的 exe | ✅ **11 秒**（`xvfb-run -a make -C CardinalNative`） |
| 加模块要动的位置 | **4 处**：`plugins/新包/{plugin.json,src,res}` + `plugins/plugins.cpp` + `plugins/Makefile`　✅ **已实走一遍** |
| 最小可跑范例 | `plugins/Cardinal/src/Blank.cpp`，**103 行** |
| 键盘输入链路 | ✅ 实测打通（SMK-25 → Cardinal 出声，同时 AI 可旁听） |
| MIDI 解析库 | ✅ `plugins/BaconPlugs/libs/midifile/`（smf）已在源码树 |
| **A · 空壳跑通** | ✅ **完成** —— 自建包 `Starsea`，模块 `Starsea-Sketch`；已在 exe 里用字符串对照验证到（新 exe 6 处命中 / 旧 exe 0 处） |
| **C · 功能规格** | ✅ **本文件** |
| 待办 | ✅ ① 实机验收**已通过**（09-21 10:33 录放一致）　⏳ ② §5 剩 **2 题**待答（第 3、4 题） |

---

## 8. ⚠️ 09-21 二次调研：L1 录制不是"空白"，而是"已有但残缺"

起因：核对 §4.1 时顺手扫了 `rcm` 包，发现 **`rcm-pianoroll`**。以下**全部来自源码与产物的核验，不是推测**。

### 8.1 已实现、已启用、已在 exe 里：`rcm-pianoroll`

| 项 | 实据 |
|---|---|
| 源码 | `plugins/rcm-modules/src/PianoRoll/` —— **24 文件 / 2994 行**（含 MenuItems 8 文件 / 121 行） |
| 已启用 | `plugins/Makefile:1023` 显式 `$(wildcard rcm-modules/src/PianoRoll/*.cpp)`（**只收这一层 `.cpp`**） |
| 在产物里 | `D:\Cardinal\win64\CardinalNative.exe` 内 `rcm-pianoroll` **命中 1 处**（硬证据） |
| 在浏览器里 | `module_index.json` 已有 `pkg=rcm / slug=rcm-pianoroll / name=Piano Roll` |

**它已经能做这些**（读 `PianoRollModule.cpp` 原文）：

| 能力 | 源码实据 |
|---|---|
| **录音符（L1）** | `RECORD_IN` 触门 → `transport.toggleRecording()`；录制时从 **`VOCT_IN` / `GATE_IN` / `RETRIGGER_IN` / `VELOCITY_IN`** 采样（L189–243） |
| 数据模型 | 每个 step 存 `{pitch, velocity, retrigger, active}`（`PatternData.hpp:51-56`） |
| 存进 patch 文件 | `dataToJson()` 把整张 pattern 表存进 `.vcv`（L20–37） |
| 回放 | `VOCT_OUT` / `GATE_OUT` / `RETRIGGER_OUT` / `VELOCITY_OUT` + `END_OF_PATTERN_OUT` |
| 卷帘编辑 | `RollAreaWidget.cpp`（621 行）+ `DragModes.cpp`（259 行）+ **撤销/重做**（`history::ModuleAction`） |
| 试听 | `Auditioner`（47 行） |
| 多 pattern | `PATTERN_IN` 用 CV 选 pattern |

**接线前提**：录制条件是 `transport.isRecording() && transport.isRunning()` —— 三者缺一不可：
**`CLOCK_IN` 有时钟在跑 + `RUN_IN` 拉高 + `RECORD_IN` 触发一次**。

**四个硬限制**（同样来自源码，非猜测）：

| 限制 | 实据 | 影响 |
|---|---|---|
| **单声道** | 满篇 `setChannels(1)`（L259/290/296/304 等） | **和弦 / 复音录不了**，一次只一个音 |
| **量化录制** | 音高只在 `clockTick` 时写入当前 step（L196–216） | 弹的东西**吸附到时钟网格**，自由时值录不了 |
| **必须有时钟** | 无 `clockTick` 则不 `advanceStep()` | 得先给它一个时钟源 |
| **Step 无长度字段** | `Step{pitch,velocity,retrigger,active}` | 音符长短 = 门在几个 step 上持续（隐含表达） |

### 8.2 未实现、但设计已想好：`SongRoll`（歌曲级时间轴）

`plugins/rcm-modules/src/SongRoll/` —— **21 文件，实现部分仅 10 个 `.cppx` 共 595 行**
（`.cppx` = 被改名禁用的 `.cpp`），且 **`plugin.json` 未登记、`plugins.cpp` 未注册** ⇒ **编不出来、也看不到**。

但它的**数据结构已经把"编曲"想清楚了**（`SongRollData.hpp` 全文 33 行）：

```
SongRollData
  sections[]                    ← 一首歌切成若干「段」
    channels[]                  ← 每段有若干「通道」
      pattern     = 1           ← 这条通道播哪个 pattern
      repeats     = 1           ← 重复几遍
      repeat_mode = FREE / REPEATS / LIMIT
      clock_div   = 1
```

**这恰好回答 §4.1 的"为什么拆两个模块"** —— 而且现成的拆法比本文档初稿更对：

- 初稿拆的是「录」与「播」→ **拆错了**。PianoRoll 是实证：录和播本就该在一个模块里（录完要立刻听）。
- 正确的分层是 **「编 pattern」= PianoRoll** 与 **「排歌」= SongRoll** ——
  一个管"这一小节里是什么音符"，一个管"这些小节怎么排成一首歌"。

### 8.3 结论：企划 2 的形态要变了

| | 初稿假设 | 09-21 实情 |
|---|---|---|
| L1 录制 | **要自己写**（§3 写"无现成件"） | ✅ **已有，已在 exe 里** |
| 卷帘编辑 UI | 要自己画 | ✅ 已有（含拖拽、撤销、试听） |
| 歌曲级时间轴 | 未提 | ⚠️ **骨架在（595 行），实现要自己写** |
| 复音录制 | 未提 | ⚠️ `rcm-pianoroll` 无，但 **`JW-Modules/NoteSeqFu` 是 32×32 复音卷帘（POLY 16）** —— 见 §13 |

⇒ **第一步不该是"写模块"，而是"把现成的拖出来试一遍"。** 试完才知道短板是真短板、还是纸面短板。

### 8.4 附带发现：PianoRoll 的音符表是**纯 JSON**、存在 `.vcv` 里 ⇒ **AI 可直接灌音符**

`PatternData::dataToJson()`（`PatternData.cpp:193–244`）逐字给出格式：

```json
"patterns": [
  {
    "numberOfMeasures": 1,
    "beatsPerMeasure": 4,
    "divisionsPerBeat": 4,
    "measures": [
      { "notes": [
          { "pitch": 48, "velocity": 0.8, "retrigger": false, "active": true },
          "…每一步一个对象…"
      ] }
    ]
  }
]
```

**三点意涵（都指向"李不必自己敲"）**：

1. `pitch` = **整数 MIDI 音高**（C4 = 60，由 `quantizePitch()` 换算）；
   `velocity` = **0–1 浮点**（源码里 `rescale(in, 0V..10V, 0..1)`）；`active` = 这一步有没有音。
2. 音符表**存在 `.vcv` patch 文件里** ⇒ 可用 Python **直接生成/改写**，
   走已有的 `patchio.py` + OSC `/load` 推进 Cardinal —— **零编译、不需要 MIDI 注入、不需要李动手**。
3. ⇒ **"AI 帮你把鼓点敲进去"不需要写任何 C++ 模块。**

**那两处也一并验证了**（同一轮读源码）：

- **`patterns` 长度固定**：`PatternData::PatternData()` → `patterns.resize(MAX_PATTERNS)`；
  且 `reset()` 把每个 pattern 统一设为 **1 小节 / 4 拍 / 4 格 = 每小节 16 步**。
  ⇒ 写 JSON 时长度与步数都要按这个给。
- **每个模块实例各自一份**：`patterns` 由模块自己的 `dataToJson()` 写入
  （`PianoRollModule.cpp:26`：`json_object_set_new(rootJ, "patterns", patternData.dataToJson())`）
  ⇒ 一个机架里放多个 PianoRoll 时，各实例的音符表**彼此独立**，挂在各自模块节点下。

⇒ **结论：格式已完全掌握。"AI 生成鼓点 → 写进 `.vcv` → OSC `/load` 推给 Cardinal"这条路成立，
且零编译、不需要任何 MIDI 注入。**

> **2026-09-21 补正（比上面更硬的一条）**：**`patterns` 整个字段可以直接省略**。
> 依据 `PatternData::PatternData()` → `patterns.resize(MAX_PATTERNS=64); reset();`
> 与 `dataFromJson()` 开头先 `reset()` —— **构造函数已经把 64 个 pattern 备好了**，
> 不写 `patterns` 就是一张空白谱纸，不会有"pattern 缺失导致越界"的风险。
> 所以最小写法只需要 `data = {"sequenceRunning": false, "lowestDisplayNote": 48, "notesToShow": 36}` 之类。

---

## 9. 第一次接线落地：`mini_arranger.vcv`（2026-09-21 生成 · 已实机验收通过）

**产物**：`D:\Cardinal\patches\mini_arranger.vcv`（11 模块 / 13 线）
**备份**：`D:\Cardinal\patches\live_before_miniarranger_09211020.vcv`（李原机架，7 模块 / 7 线）
**校验**：`validate.py` 0 问题；`layout_patch.py guard` PASS（无重叠 / 无输入口双接）

### 9.1 接线表（13 根，口编号全部来自源码 enum，非猜测）

| # | 从 | 到 | 为什么 |
|---|---|---|---|
| 1 | `Clocked` OUT1 | `PianoRoll` IN0 CLOCK | 走时钟；OUT1 = 子时钟 1 = **16 分音符**（见 9.3） |
| 2 | `Button`(RUN) OUT0 TRIG | `PianoRoll` IN1 RUN | RUN 是**边沿翻转**，按一次起、再按一次停 |
| 3 | `Button`(REC) OUT0 TRIG | `PianoRoll` IN4 RECORD | 同上，按一次开录、再按一次停录 |
| 4–7 | `HostMIDI` OUT0/1/6/2 | `PianoRoll` IN5/6/7/8 | 键盘的 音高/门/重触发/力度 → 录制输入 |
| 8–10 | `PianoRoll` OUT5/6/7 | `VCO` IN0、`ADSR` IN4/IN5 | 回放：音高 → VCO；门 → 包络；**重触发 → ADSR RETRIG**（关键，见 9.4） |
| 11–13 | VCO→VCA→HostAudio2 | | 发声链（沿用李原机架的音色，只换了驱动源） |

### 9.2 关键发现 1：**PianoRoll 面板上没有任何可点的按钮**

`PianoRollModule.hpp` 里虽然定义了 `RUN_BUTTON_PARAM` / `RESET_BUTTON_PARAM`，
但 `PianoRollWidget.cpp`（159 行）里**一个 `addParam` 都没有** —— 那两个 param 是遗留槽位。
⇒ **RUN / RECORD / RESET 三个动作只能靠 CV 输入口的上升沿**（`toggleRun()` / `toggleRecording()`）。

**所以"给它接线"的必配件是一个「手动按钮 → 门」模块**。选型 `LittleUtils/Button`（3 HP）：

```
OUT0 = TRIG（按下发一个脉冲）   ← 用它
OUT1 = GATE（按住期间高电平）
OUT2 = TOGGLE（自锁开关）
OUT3 = CONSTANT（恒定电压）
```
用 TRIG（脉冲）而不是 TOGGLE：RECORD 本身就是"边沿翻转"，脉冲按一次翻一次，语义正好对齐。

### 9.3 关键发现 2：时钟给多少，卷帘就走多快

`ImpromptuModular/Clocked` 的**主时钟 = 四分音符**（`101`：`masterLength = 120/BPM`，
源码注释写明 `a length is a double period`，故周期 = 60/BPM = 一拍）。
卷帘**一格 = 一个时钟脉冲**，它的默认格子是 4 拍 × 4 格 = 每小节 16 格 ⇒ 要 16 分音符。

**做法**：`ClockedCommon.hpp` 的 `ratioValues[] = {1, 1.5, 2, 2.5, 3, 4, …}`，
ratio 旋钮的**数值 = 这个数组的下标**（`getRatioDoubled()` 只做 `round()`）。
⇒ 要 ×4 就把 **Clk 1 ratio 写成 5**（`ratioValues[5] = 4`），并从 **OUT1** 取时钟。
本机架里已写死：`Clocked` params = `{"id":0,"value":120}`（BPM）+ `{"id":1,"value":5}`（×4）。

### 9.4 关键发现 3：录的时候是"直通"，不是"回放"

`PianoRollModule.cpp` 两处合起来决定这个手感：

- `274`：`if ((transport.isRunning() && clockTick) && !transport.isRecording())` —— **录制时图案不出声**
- `315–326`：`GATE_IN > 1V` 时把 **输入原样镜像到输出**

⇒ **边录边听**：你弹的键同时进录制缓冲和发声链。也解释了为什么要接 RETRIGGER：
门在"RUN 已接线"时会一直保持高电平，音符之间的断开**只能由重触发信号给包络**。

### 9.5 关键发现 4：串联（你说的"两个相连、播完一个接下一个"）**是原生功能**

`PianoRollModule.cpp:328` 的注释就是 `// Send our chaining outputs`：

| 输出口 | 作用 |
|---|---|
| OUT9 `END_OF_PATTERN` | 每图案**最后一步**发一个 1 ms 脉冲（`eopOutputPulse.trigger(1e-3f)`） |
| OUT0–OUT4 `CLOCK/RESET/PATTERN/RUN/RECORD` | 把上述信号**原样转发**给下游模块 |

⇒ **串联接法**：`A.OUT9(EOP) → B.RUN`（A 播完自动启动 B）+ `A.OUT0(CLOCK) → B.CLOCK`
（B 跟 A 同一个时钟）+ 需要的话 `A.OUT3(PATTERN) → B.PATTERN`。
**不需要写任何代码。**

### 9.6 关键发现 5：容量上限（回答"加大容纳量难不难"）

| 维度 | 上限 | 在哪 |
|---|---|---|
| 图案数 | **64** | `PatternData.cpp:7` `MAX_PATTERNS = 64`；面板菜单显示 `1/64` |
| 每图案小节数 | **1–16** | `PatternWidget.cpp:115` `for (int i = 1; i <= 16; i++)`（下拉菜单，**界面里就能改**） |
| 每小节步数 | `beatsPerMeasure × divisionsPerBeat`（默认 4×4=16） | `PatternData.cpp:58` |

⇒ **单模块理论容量 = 64 图案 × 16 小节 × 16 步 = 16384 格**。
数据层（`std::vector`）**没有任何硬上限**，"16 小节"只是菜单里写死的循环上界 ——
**"加大容纳量"在数据层是小改，真正的成本在编辑界面**（那么长的时间轴怎么画、怎么滚）。

### 9.7 `.vcv` 的一个必须知道的字段

`version` 要写 **Cardinal 自己保存时用的那个值**，实测 = **`2.1.2`**
（早期手写 patch 里常见 `2.0`；查法：读实时存档 `%TEMP%\Cardinal.XXXX\patch.json` 的 `version`）。

### 9.8 交付状态

| 项 | 状态 |
|---|---|
| 机架文件 | ✅ 已生成并通过校验 |
| 推送到 Cardinal | ✅ **已推**（09-21 10:28；李开 OSC 后 `/load` 回 `ok`，推前备份 `live_before_push_09211028.vcv`） |
| **实机验收** | ✅ **通过**（09-21 10:33 李回报：录时有声、录后播放一致）⇒ 13 根接线**全部正确** |
| 录音保命 | ⚠️ 录音**只在内存**，须李 `Ctrl+S` 才落盘；空白模板已另存 `mini_arranger_template.vcv`（防脚本重跑覆盖录音） |

---

## 10. 10:47 调研：**生态里其实有得抄**（推翻 §4.3 结尾"无现成件可抄"的说法）

> 李 10:47 指令：「想着没得抄，你拓宽自己的搜索面在网上…先把 Cardinal 相关的知识查一查，
> 如果查不到的话，就往其他设计角度去思考…反正你总得去找方案的」。
> 照做，结果如下 —— **上一节那句"无现成件可抄"是我的搜索面不够，不是事实。已作废。**

### 10.1 ★ 最大发现：Portable Sequence（剪贴板传音符的社区标准）

**是什么**：一段**纯 JSON 放进系统剪贴板**，支持的音序器就能把它变成音符。
由 Richie Hindle（Entrian）、Bruce Frazer（Squinky）、Marc Boulé（Impromptu）三人
于 **2020-02** 提出，非官方但被广泛支持。

```json
{ "vcvrack-sequence": {
    "length": 4.0,
    "notes": [ {"type":"note","start":0.0,"pitch":0.0,"length":0.25,"velocity":8.0} ] } }
```

| 字段 | 必填 | 单位 / 范围 |
|---|---|---|
| `start` | ✅ | **四分音符 = 1.0**（不是秒、不是 step） |
| `pitch` | ✅ | **V/Oct** |
| **`length`** | ✅ | 同 `start` —— **这就是"音符时长"缺口的现成解** |
| `velocity` | ✕ | 0–10 |
| `playProbability` | ✕ | 0–1 |

- **许可 = WTFPL** ⇒ **可随意抄进自建包**。
  实现：`plugins/AriaModules/src/portablesequence.hpp`（**170 行**，自带剪贴板读写）。
- **exe 实测**：字符串 `vcvrack-sequence` 命中 **12 处** ⇒ **现在就能用，不是将来时**。
- **支持者**：Aria 的 `Qqqq`/`Darius`/`Solomon`；Impromptu 的 `Foundry`/`PhraseSeq16`/`PhraseSeq32`/
  `WriteSeq32`/`WriteSeq64`/`FourView`/`BigButtonSeq2`/`ChordKey`/`ProbKey`/`SemiModularSynth`。

⇒ **李说的「你帮我敲打录进去就行，不用我手弹」从此有了标准通道**：
**我生成这段 JSON → 他粘贴进音序器 → 音符就进去了**，不碰 `.vcv`、不写模块。

### 10.2 Entrian Sequencers（商业 $30）—— 多轨形态与"面板太宽"的正解

- `Timeline` = **10 轨**；轨上是 **clip**，clip 里是 **note**（三层结构）。
- 输出 = 右侧**三列，每轨一组**：V/Oct · Gate · Velocity ⇒ **证明"每轨一组物理口"可行**。
- ★ **面板上只放一块小屏幕**（显示当前 song + 播放头竖线），**点屏幕 → 弹出可缩放的编辑器**。
  ⇒ 面板宽度**只由输出口决定，不被编辑区撑爆**。**这条要抄，且直接决定 §4.2.1 的 N 能取多大。**
- 音符有 `length`（拖右端改时长）、`velocity`、`probability`。
- 最多 **25 首命名 song**，CV 输入切换（C3–C5 选歌 / 触发下一首 / 随机）；
  `Song CV/menu = End of phrase` 解决切换时的同步问题。

### 10.3 本机现成件（**全部已在 exe 里，不需编译**）

exe 字符串命中（`D:/Cardinal/win64/CardinalNative.exe`）：
`Foundry` **60** · `Qqqq` **125** · `Darius` **49** · `Solomon` **144** · `PhraseSeq16` 17 ·
`NoteSeqFu` 9 · `NoteSeq16` 9 · `DigitalProgrammer` 11 · `vcvrack-sequence` **12**。

- ★ **`Foundry` = 4 轨音序器**（`FoundrySequencer.hpp:14` `NUM_TRACKS = 4`），
  每轨一个 `SequencerKernel`，用 **`trackIndexEdit`** 选"当前编辑 / 录制轨"
  ⇒ **§4.2 推导的"共享输入 + 面板选轨"是生态既有做法，不是自创。**
- 扩展器先例：`FoundryExpander`、`JP Four Track Expander`。

### 10.4 跨领域参照（硬件 / Dawless 生态）

**Squarp Hapax**（$1299）：**16 轨** × 每轨 16 pattern；**双工程同时跑**（无缝现场切换）；
轨有类型 **Poly / MPE / Drum**；**Step mode 就是钢琴卷帘视图**；每轨独立 length、播放方向、
time elasticity；pattern → section → chain 做编排。
⇒ 印证 **16 是生态的天然档位**（连同 VCV Rack 的复音上限也是 16）。

### 10.5 本轮对设计的三条修正

| # | 修正 |
|---|---|
| 1 | §4.3 结尾"**无现成件可抄**" **作废** —— 有得抄：Portable Sequence 的 `Note` 结构、Entrian 的 popup 方案、Foundry 的选轨法 |
| 2 | §4.2 的"**键盘输入一组共享 + 选轨**"**得到外部印证**，可放胆采用 |
| 3 | §4.2.1 的 N 轨数据**已按本次调研重算**（原估算偏保守，高估了面板宽度） |

---

## 11. 扩展器架构实证（2026-09-21 10:52 拍板后立即做的源码核实）

李在 §4.2.1 选了 **扩展器：主 4 + 按需加**。本节回答三件事：**这机制在 Cardinal 里能不能用 / 生态怎么用 / 坑在哪**。

### 11.1 机制是什么（三句话）

1. **只有紧邻的模块能通信。** 模块自带 `leftExpander` / `rightExpander` 两个接口，各自只连**左右紧挨着**的那一个模块。
   **Rack 不支持上下相邻** —— Bogaudio 文档原话：*"Rack doesn't support expanders above or below the expanded module."*
2. **靠交换内存指针通信，零拷贝。** 每个模块自己开两块缓冲（`float xxx[2][N]`），
   `producerMessage` 指 `[0]`、`consumerMessage` 指 `[1]`；写完消息设 `messageFlipRequested = true`，
   **引擎在时间步结束时 `std::swap` 这两个指针**（`src/Rack/src/engine/Engine.cpp:388-398`）。
3. **官方注释明说：1 采样延迟。** *"This means that message-passing has 1-sample latency."*

### 11.2 ✅ Cardinal 原样保留了这个机制

核实方式：Cardinal 用 `src/override/Engine.cpp` 整体覆盖了 Rack 引擎，但 **`messageFlipRequested` 的
`std::swap` 翻转逻辑一字未动**。⇒ **可以放心用原生机制。**

### 11.3 ⚠️ 生态里"扩展器"加的东西，和我们要的**不一样**

把本机 8 个扩展器逐个看了一遍：**全部是"给已有资源加端口 / CV / 调制"，没有一个在"加轨道数"**。

| 扩展器 | 加的是什么 | 证据 |
|---|---|---|
| `FoundryExpander` | 给**已有的 4 轨**每轨加 CV 输入（力度 CV2、seq# 选择） | `VEL_INPUTS`/`SEQCV_INPUTS` 都是 `ENUMS(..., NUM_TRACKS)`，**`NUM_TRACKS` 没变** |
| `ClockedExpander` | 8 个 CV 输入（脉宽 / 摇摆），**0 输出**；消息只传 panelTheme/Contrast | `config(0, NUM_INPUTS, 0, 0)`、`leftMessages[2][2]` |
| `ChordKeyExpander` | 4 个 CV 输入 + 4 个 CV 输出 | `ChordKeyExpander.cpp:20,24` |
| `MixMaster` / `AuxExpander` | aux send/return 的端口与档位（传结构体） | `MixMaster.cpp:162,524` |

⇒ **含义**：拿扩展器来"加轨"是**超出生态惯例的用法**。技术上完全可行（消息就是一块裸内存，装什么都行），
**但没有可以直接照抄的"加轨型扩展器"**。这是本项目第二块原创工作量。
（原文此处写「第一块是 §4.3 的多轨组织」—— **那一块已被 §13 推翻**：本机有多个现成多路音序器。剩余原创量见 §13.4。）

### 11.4 链式（挂多块）可行，但**不免费**

**① 通信有两条路，我们要选保守的那条：**

| 路 | 做法 | 评价 |
|---|---|---|
| 直读端口 | 主模块里直接 `rightModule->getInput(i).getVoltage()` / `setVoltage(...)` | 官方文档推荐（*"you can implement its entire DSP algorithm in the main module"*），**但多线程下有竞态** —— 官方警告对方 `process()` 可能 "before, after, or during"。**Cardinal 正是多线程引擎** ⇒ 不用 |
| ⭐ 双缓冲消息 | 走 `producerMessage` / `consumerMessage` | **有 1 帧延迟，但确定、安全** ⇒ 我们用这条 |

**② 链式确实存在，但主流不做：**

- Bogaudio 文档：*"**Some expanders may be chainable**: multiple instances can be added to continue expanding the base... expanders must all be to the right of the base, and all touching."*
- 完整链式范本：插件 `imDanSable/SIM`（音序器），它的定义是 *"A consecutive sequence of connected input Expanders, an Expandable and output Expanders is called a chain."*
- ⚠️ **但 Foundry / Clocked / ChordKey / MixMaster 的扩展器都只有 `leftExpander`，没有向下游转发的代码 ⇒ 挂不了第二块。**

⇒ **要"按需加 N 块"，必须自己写中继转发**（每块扩展器：收到上游消息 → 复制 → 写给右侧下游）。
**建议先做一级**（主 4 + 1 块 = 8 轨）跑通，再谈多级。

### 11.5 ⚠️ 一条必须避开的 VCV 已知 bug（删模块时回调不触发）

VCV Rack 2.4.1 实测存在 bug：**删除相邻模块时 `onExpanderChange()` 不会被调用**
（`removeModule_NoLock()` 直接置 `moduleId = -1`、`module* = NULL`，引擎的 `updateExpander_NoLock()`
检测不到不一致 ⇒ 回调丢失）。后果：**若代码缓存了扩展器指针，删模块后会访问野指针 → 崩溃。**

- workaround（Venom 作者给出）：在 `onRemove()` 里**手动清空邻居的扩展器指针并手工触发 `onExpanderChange()`**。
- **对我们的意义**：李在机架里删 / 挪模块是日常操作 ⇒ ①**绝不缓存扩展器指针**，每帧从 `rightExpander.module` 重新取；
  ②每次用前**先校验 `model`**（官方文档也这么要求）；③处理 `onRemove()`。

### 11.6 落到设计的四条硬约束

| # | 约束 | 对使用的影响 |
|---|---|---|
| 1 | 扩展器必须**紧贴**主模块、都在**同一侧** | 机架里排班时，扩展器与主模块**中间不能插别的模块** |
| 2 | **只能左右，不能上下** | 只能横向铺（与既有排班铁律一致） |
| 3 | 一级扩展器零通信成本；多级要写中继 | 建议先做一级 |
| 4 | 轨数据放哪要先定 | 决定"拔掉扩展器之后那几轨还在不在"，见 §11.7 |

### 11.7 ⏳ 需要李定：轨数据放哪（产品行为，不是技术选择）

| | **甲 · 数据集中** | **乙 · 数据分布** |
|---|---|---|
| 做法 | 所有轨的音符**全存主模块**；扩展器只是"接线板"，提供端口 | 每块扩展器**自存它那 4 轨**，靠消息与主模块同步播放 |
| 好处 | 数据结构只有一处；换 / 拔扩展器**不影响曲子内容** | 主模块负担轻；每块各自算自己的端口，主模块不必驱动远端 |
| 代价 | 主模块要驱动**够不着的那块**的端口 ⇒ **仍要写中继转发指令** | 数据分散在多块里；拔掉某块，那 4 轨就不在这套机架里了（重插要靠它自己带着状态） |

⇒ **两条都可行，无技术对错**；区别只在"拔掉扩展器之后那几轨还在不在"。**✅ 已拍板（2026-09-21 11:01）：乙 · 数据分散在各块。**

> 李原话：「那段录音不重要，**不留**（数据分散在各块上），A」

| 连带决定 | 内容 |
|---|---|
| 数据归属 | 每块扩展器**自存它那 4 轨**；主模块只存自己的 4 轨 |
| 拔插行为 | 拔掉某块 ⇒ **它那几轨跟着走**；重插靠它自己恢复状态 |
| 通信内容 | 只传「当前拍 / 时钟」，**不传音符** ⇒ 主模块不必驱动远端端口 |
| 好处 | 主模块轻、扩展器可热插拔 |
| 代价 | 曲子被拆散在多块里 —— 单独打开主模块 = 只剩 4 轨 |

> 至此「写代码前必须钉死」的结构项**全部定完**（面板 30HP / 口位 25 个 / 主 4 轨 / 数据归属乙），
> 所以紧接着就写出了骨架 —— 见 **§12**。

---

## 12. `MiniArranger` 骨架（2026-09-21 11:07 交付）

> ⚠️ **本节是骨架阶段（30 HP）的记录。骨架后来被扩到 40 HP 并加上了录制与编辑引擎 ——**
> **最新状态看 §15。本节保留，用来对照"形状先定死"这一决定是怎么执行的。**

> **状态**：已编译、已链接进 `CardinalNative.exe`，模块符号在 exe 里可见（实测见 §12.5）。
> **但它不是成品** —— DSP 只实现了「转发 4 路时钟信号」，录制 / 播放 / 编辑界面**都还没写**。
> 这一版的用途 = **把面板尺寸、端口编号、数据结构钉死**，此后写功能不再返工。

### 12.1 改了哪 6 个文件

| 文件 | 动作 |
|---|---|
| `plugins/Starsea/src/ArrangerData.hpp` | **新建** 数据模型（音符 / 轨 / 单元 + JSON 读写） |
| `plugins/Starsea/src/MiniArranger.cpp` | **新建** 模块类 + 面板 widget（端口定义、nvg 文字） |
| `plugins/Starsea/res/MiniArranger.svg` | **新建** 面板底图（30HP；纯几何，nansvg 不认 `<text>`） |
| `plugins/Starsea/src/plugin.hpp` | +1 行 `extern Model* modelStarseaMiniArranger;` |
| `plugins/Starsea/plugin.json` | +1 条 `modules[]`（slug `Starsea-MiniArranger`） |
| `plugins/plugins.cpp` | +1 行 extern（L204）+ 1 行 `addModel`（L1789） |

**`Makefile` 一行没动** —— 它用 `$(wildcard Starsea/src/*.cpp)` 自动发现源文件，
所以往 `src/` 丢新 `.cpp` 是**零构建配置改动**。（这是本次新确认的事实，值得记住。）

### 12.2 端口清单（25 个口）

**共享输入 · 8 个**（只一组，不按轨重复 —— 理由见 §4.2）

| # | 名 | 语义 |
|---|---|---|
| 0 | CLOCK | 时钟脉冲 |
| 1 | RESET | 脉冲复位到第 1 小节 |
| 2 | RUN | **脉冲翻转**运行/停止（照抄 rcm-pianoroll，非电平） |
| 3 | RECORD | **脉冲翻转**录音（照抄） |
| 4 | V/Oct | 键盘音高（录制源） |
| 5 | GATE | 键盘门（录制源） |
| 6 | RETRIGGER | 键盘重触发 |
| 7 | VELOCITY | 键盘力度 |

**共享输出 · 5 个**（串联下一台用）

| # | 名 | 语义 |
|---|---|---|
| 0 | CLOCK | 转发（串联时喂下一台的 CLOCK） |
| 1 | RESET | 转发 |
| 2 | RUN | 转发 |
| 3 | RECORD | 转发 |
| 4 | END_OF_SONG | 全曲播完脉冲（串联时驱动下一台的 RUN） |

**每轨输出 · 3 个 × 4 轨 = 12 个**

| 输出 # | 轨 | 名 |
|---|---|---|
| 5 / 6 / 7 | 1 | V/Oct / GATE / VELOCITY |
| 8 / 9 / 10 | 2 | 同上 |
| 11 / 12 / 13 | 3 | 同上 |
| 14 / 15 / 16 | 4 | 同上 |

**参数**：4 个静音开关（`MUTE1..4`）+ 1 个「当前编辑/录制轨」选择（`TRACK_EDIT`，0–3，照抄 Impromptu `Foundry` 的 `trackIndexEdit`）。
**灯**：`RUN`（绿）、`RECORD`（红）。

### 12.3 数据结构（`ArrangerData.hpp`）

```
MaNote   { step, length, pitch, velocity }          // 一个音符
MaTrack  { label, mute, measures, notes[] }         // 一条轨 = 一个声部
MaUnit   { tracks[4], tracksUsed, editTrack, stepsPerQuarter }  // 一台模块持有的全部轨
```

- **时间单位 = 格（step）**，和现成 `rcm-pianoroll` 的量化格一致 ⇒ 录制/量化逻辑能照它的路子走。
- **`length` 字段就是现成件缺的那个** —— Piano Roll 每个音符长度固定，我们的可以拉长。
- **`pitch` 存 MIDI 整数**（0–127），输出时转 V/Oct：`(pitch - 60) / 12`。
- **`velocity` 存 0–1**，导出 Portable Sequence 时 ×10。
- 整体可 `toJson` / `fromJson` 进出 `.vcv`（走 Rack 的 `dataToJson` / `dataFromJson`）。

### 12.4 面板布局（30 HP = 152.4 × 128.5 mm）

| 区域 | 坐标（mm） |
|---|---|
| 共享输入列（8 口） | x=12，y = 26 + 13·i |
| 共享输出列（5 口） | x=42，y = 26 + 13·i |
| 显示区（占位） | x 68–146，y 14–52 |
| 静音开关 ×4 | x = 76 + 15·t，y=64 |
| 编辑轨选择 | x=136，y=64 |
| 每轨输出（3 口 × 4 列） | x = 74 + 18·t，y = 86 + 16·o |

**关于文字**：面板 SVG 用 **nanosvg** 渲染，**不画 `<text>`** ⇒ 所有字母标记
（`CLOCK` / `TRK 1` / `V/OCT` 等）都在 `StarseaMiniArrangerWidget::draw()` 里用 **nvg** 画。
字体走 `APP->window->loadFont(asset::system("res/fonts/ShareTechMono-Regular.ttf"))`，**已做判空保护**。

### 12.5 编译与验证（实测）

| 步骤 | 结果 |
|---|---|
| 单文件语法检查 | 第 1 次报 1 个错（`module` 是基类指针，要 `dynamic_cast`）→ 修后通过 |
| 交叉编译 `cross_build_cardinal.sh 8 true` | **19 秒**；到 `CardinalMini.lv2` 时报 `collect2: error` 中止 —— **已知既有问题**（headless 归档缺 Bogaudio 的 GUI 符号，2026-09-20 起从未成功过，与新包无关） |
| 补编 `make -C CardinalNative` | ✅ 成功 |
| 产物 md5 | `7ef8e092e931a502eb87e9c19aa89b92` → **`403354bcb28f1b4ae06adf7c96b08219`**（变了） |
| 目标 `.o` | `MiniArranger.cpp.o` 新生成（231,917 字节） |
| 其他 `.o` | `Sketch.cpp.o` mtime 仍是 09:23:05 —— **未动** ✅ |
| exe 内符号 | `Starsea-MiniArranger` / `StarseaMiniArrangerModule` / `StarseaMiniArrangerWidget` 全部命中 ✅ |
| 静态库归档 | `plugins.a` 里含 `MiniArranger.cpp.o` ✅ |

### 12.6 尚未实现（后续工作的准确边界）

| # | 缺什么 | 难度 |
|---|---|---|
| 1 | **录制引擎** —— 把键盘输入按格落进 `MaNote`（含边沿翻转的 RUN/RECORD 处理） | 中，可直接照 `PianoRollModule.cpp:274–326` |
| 2 | **播放引擎** —— 按 CLOCK 推进、输出每轨 V/Oct + GATE + VELOCITY | 中 |
| 3 | **编辑界面** —— 屏上画卷帘、多轨切换、改音符 | 大，但**有多个现成件可参照**（§13）：`NoteSeqFu` 复音网格、`Arrange` 行名网格、`PhraseSeq` 乐句切换 |
| 4 | **扩展器模块** —— 加轨的那块，自存自己 4 轨（§11.7 拍板「数据分散在各块」） | 大（生态里没有先例可抄，要自己写链式中继） |
| 5 | **Portable Sequence 导入** —— 一段 JSON 灌进轨里（AI 造鼓点的通道） | 小（`AriaModules/src/portablesequence.hpp` 可直接拿，WTFPL 许可） |
| 6 | 每轨 `measures` 可调、`stepsPerQuarter` 走参数 | 小 |

### 12.7 部署状态

- ✅ `D:\Cardinal\win64\resources\Starsea\res\MiniArranger.svg` 已就位
- ✅ `D:\Cardinal\win64\resources\PluginManifests\Starsea.json` 已更新（2 个模块）
- ✅ `D:\Cardinal\win64\CardinalNative.exe` **已替换（11:11）** —— 李 11:10 关闭 Cardinal 后完成：
  指纹 `7ef8e092…` → `403354bc…`，旧 exe 备份 `CardinalNative.20260921-0927.exe`。
  拷贝走 UNC 通道 `\\wsl.localhost\<distro>\home\<user>\Cardinal\bin\CardinalNative.exe`
  （注意：发行版全名是 **`Ubuntu-26.04`**，用 `Ubuntu` / `wsl$` 都报 WinError 67）。
  重开 Cardinal 后，模块浏览器搜 `MiniArranger`（或看 `Starsea` 分组）即可看到面板。

---

## 13. 11:15 李的截图推翻我两轮结论 —— **本机就有多路编排音序器**

> 起因：李 11:15 发来截图 —— Cardinal 里有一个 **`JW-Modules / Arrange`** 模块，问我是不是漏了。
> **是的，漏得很彻底。** 这是第三次调研，也是第一次用对方法（全量列模块名，而不是 grep 关键词）。

### 13.1 ★ 全景：本机 86 个包 / 1424 个模块

**统计口径**：`plugins/*/plugin.json` 的 `modules[].slug` **全量提取**（经 UNC 直读），
从中筛出与「序列 / 编排 / 图案 / 歌曲 / 轨 / 卷帘 / 音符 / 步」相关的模块：

| 模块 | 包 | 形态 | 关键能力 | 源码 |
|---|---|---|---|---|
| **`Arrange`** | JW-Modules | **16 行 × 64 列门控网格** | 每行一路信号进出；5 种播放方向；5 种随机填充（含 Euclid）；**行可命名**；位置 / 密度 / EOC 输出 | `Arrange.cpp` 677 行 |
| **`Arrange`** | CVfunk | **7 通道序列器** | **有 `REC` 录制输入**；输出**可切复音**（`polyphonyChannels`）；MIT 许可 | `Arrange.cpp` 1013 行 |
| `Phrase-Seq-32` | ImpromptuModular | 2 轨 × 多乐句 | `Seq#` CV **选播哪个乐句**；每轨 CV + 2 Gate；有 Write 输入 | 2265 行 |
| `Phrase-Seq-16` | ImpromptuModular | 同上，16 步 | | 2149 行 |
| `Gate-Seq-64` | ImpromptuModular | 64 步门控 | | 1609 行 |
| **`NoteSeqFu`** | JW-Modules | **32 × 32 复音钢琴卷帘** | 复音数可调（`POLY` 上限 16）；`gateMode`；大量变换输入（旋转 / 翻转 / 移调 / 音阶 / 根音） | 1194 行 |
| `SEQ_6x32x16` | mscHack | **6 通道 × 32 步 × 16** | | |
| `Patterns` | JW-Modules | 16 路 pattern 合并 | 每路 OR / XOR 输出 + 合一复音 | 471 行 |
| `rcm-pianoroll` | rcm | 单音钢琴卷帘 | 已有，见 §8 | |
| `rcm-seq-adapter` | rcm | 序列适配器 | 与 pianoroll 配套 | |

⚠️ **反向教训**：`Arrange` 这个 slug **不含**我搜过的任何关键词
（`portablesequence` / `MAX_TRACKS` / `noteLength`），所以 grep **永远漏掉它**。

### 13.2 `JW-Modules/Arrange` 解剖（李截图里那块）

**它是"门控编排器"，不是音高序列器。**

- **数据**：`bool cells[1024]`（16 行 × 64 列）；JSON 存为 `"cells"`（1024 个 0/1 整数数组）
  \+ `"rowNames"`（16 个字符串，**行名可自定义**）
- **端口**：`MAIN_INPUT + i` / `MAIN_OUTPUT + i` 各 16 个（**成对**），加
  `CLOCK / RESET / CLEAR / RND TRIG / RND AMT / LENGTH / MODE / START`（8 输入）
  和 `EOC / POS / INTENSITY`（3 输出）
- **核心逻辑**（`process()` 里一句话）：
  ```cpp
  outputs[MAIN_OUTPUT+i].setVoltage(on ? inputs[MAIN_INPUT+i].getVoltage(c) : 0, c);
  ```
  ⇒ **输入什么原样输出什么，开则通、关则断**（且保持多通道 / 复音透传）
- **不产生音高** —— 官方文档图里行名是 `kick / snare / chat / ohat / ride / rim / fmop`，
  就是用户把鼓的触发源接进来、在网格上打点
- **三个辅助输出**：`POS` = 当前步位置 · `INTENSITY` = 当步开启的行数（0–16 → 0–10V）· `EOC` = 循环尾脉冲
- **面板即编辑器**：网格直接画在面板上（`CELLW 10 × CELLH 20`），点格子开关；
  另有 `STEP` 手动步进按钮、`START` / `LEN` 旋钮、`RND` 随机填充按钮

**⇒ 对企划 2 的意义**：它是**"鼓轨编排"的现成件**，**行可命名 + 16 行 × 64 步**
比我们规格里"主 4 轨 × measures"宽得多。李要的"预设鼓组"完全可以用它 + 一段 JSON 实现。

### 13.3 `CVfunk/Arrange` —— 同名，但不是同一个东西

作者 **Cody Geary**（Copyright 2024，**MIT**），文件头注释原文：*"Seven channel sequencer"*。
7 通道 + `RESET / FORWARD / BACKWARDS / **REC**` 输入，
`CHAN_1..7` 输出**在单音 / 复音之间动态切换**（`polyphonyChannels` 参数）。

⇒ **它比 JW 那个更接近 `MiniArranger` 的形态**：多通道 + **能录** + **能复音**。

### 13.4 修正后的「真缺口」表

| 我此前说的缺口 | 现成件实情 | 结论 |
|---|---|---|
| **多轨**要自己设计 | `JW/Arrange` 16 路 · `CVfunk/Arrange` 7 路 · `PhraseSeq32` 2 轨 · `SEQ_6x32x16` 6 路 | ❌ **不缺** |
| **复音**要自己写 | `NoteSeqFu` 32×32 复音卷帘（POLY 16）· `CVfunk/Arrange` 可切复音 | ❌ **不缺** |
| **录制引擎**要自己写 | `CVfunk/Arrange` 有 `REC` · `rcm-pianoroll` 有录制 | ❌ **不缺** |
| **per-note 音符时长** | `NoteSeqFu` 只有**全局** `gateMode` · `rcm-pianoroll` 每音等长 | ✅ **确实缺** |
| **"一处看全"的跨模块总表** | 每个现成件各管自己那一块 | ✅ **缺** |
| **扩展器"加轨"**（§11） | 生态仍无先例 | ✅ **缺** |

⇒ **`MiniArranger` 的原创价值从"三处缺口"缩到"一处半"**：per-note 时长 + 跨模块总表。
（**这只是事实陈述。要不要继续写模块、还是改用现成件拼，由李决定 —— 见 §5 追加项。**）

### 13.5 我为什么漏了（方法论，已写进技能）

**错误做法**：grep 源码关键词（`portablesequence` / `MAX_TRACKS` / `noteLength`）。
**为什么必然漏**：关键词只能命中**我已经知道名字**的东西；`Arrange` / `PhraseSeq` / `NoteSeqFu`
这些名字**不含**任何我搜的词。

**正确做法（本轮才用）**：

1. 先把**所有包的 `plugin.json` 全读出来**，提取 `modules[].slug` → 得到 1424 个名字；
2. **人工过一遍**这张表（按语义筛），而不是靠机器匹配；
3. 再对候选逐个读源码确认。

⇒ 已写进技能 `cardinal-module-dev` §0.1，并写入记忆。

---

## 14. 两个 `Arrange` 的架构解剖（2026-09-21 12:05 · 李要求"好好学习这个架构"）

李的批评：**「名字一样的都不去搜一下，你就跟我说找不到」**。⇒ 本轮不再把它们当"参照物"，
而是**逐行读源码**（CVfunk 那个 1014 行全读、JW 那个 677 行全读），目标是**能抄什么**。

两块都在你现在跑的 exe 里：`Arrange` 字符串命中 **31 次**、`CVfunk` **9 次**、`JW-Modules` **1 次**。

| | `CVfunk/Arrange` | `JW-Modules/Arrange` |
|---|---|---|
| 作者 / 许可 | Cody Geary · **MIT** | Jeremy Wentworth · MIT |
| 面板宽度 | **15 HP**（`box.size = Vec(15*RACK_GRID_WIDTH, …)`） | **48 HP**（`RACK_GRID_WIDTH*48`） |
| 源码规模 | `src/Arrange.cpp` **1014 行** | `src/Arrange.cpp` **677 行** |
| 一句话 | **7 通道步进序列器**（存 CV 值） | **16 行 × 64 步门控网格**（存 0/1） |
| 能录 | ✅ `REC` 输入/按钮 | ❌ 只能手点格子 |
| 复音 | ✅ 输入自动分配 + 输出可打包 | ⚠️ 只做透传（不产生音高） |

---

### 14.1 `CVfunk/Arrange` —— 七通道步进序列器

#### 14.1.1 数据模型：**步 × 通道的电压矩阵**

```cpp
float outputValues[2048][7] = {{0.0f}};   // Arrange.cpp:64
int   currentStage = 0;                    // 播放头
int   maxSequenceLength = 128;             // 默认 128，菜单可选 128/256/512/1024/2048
```

- **固定上限 2048 步**，实际用多少由 `maxSequenceLength` 决定（context menu 里改）。
- 每个单元存的是 **CV 电压**（-10…+10 V），**不是"音符"** —— 音高是它的一种解释（见 14.1.7）。
- 整个矩阵进 JSON：`{"outputValues": [[...7 个数], ...2048 行]}`（`dataToJson` 92–134 行）。

#### 14.1.2 ★「旋钮 = 当前步的编辑窗口」—— **本项目最该抄的一条**

这是它 15 HP 就能管 **7 轨 × 2048 步 = 14336 个值** 的原因：**面板上根本不画数据，只画"当前那一步"**。

```cpp
// ① 回灌：步变了 → 把存储值灌进旋钮的"显示值"（Arrange.cpp:384-390）
if ((currentStage != previousStage) || resizeEvent) {
    for (int i = 0; i < 7; i++) {
        float recalledValue = outputValues[currentStage][i];
        if (!isEditing[i])                                     // ← 关键保护
            paramQuantities[CHAN_1_KNOB + i]->setDisplayValue(recalledValue);
    }
}

// ② 回写：拧旋钮 → 存回当前步（Arrange.cpp:498-501）
if (currentStage >= 0 && currentStage < maxStages)
    outputValues[currentStage][i] = inputVal;
```

**三个必须照抄的细节：**

| 细节 | 为什么 |
|---|---|
| 用 `setDisplayValue()` 而**不是** `setValue()` | 前者只改"显示/量程映射"，不触发参数变化事件、不干扰用户输入 |
| `isEditing[i]` 用 **`std::atomic<bool>`**（51–53 行） | 非原子的会在音频线程与 UI 线程间产生竞态 |
| 谁维护 `isEditing`：`SmartKnob::onDragStart/onDragEnd`（619–659 行） | 「手还在拧时，不要被回灌覆盖」——**这个坑我们写模块时一定会遇到** |

⇒ **对我们的直接结论**：`MiniArranger` 的 4 轨编辑**不需要弹窗编辑器、也不需要画 4×N 网格**。
30 HP 里放「共享步进 + 每轨 1 个大旋钮 + 1 个数码显示 + 1 个输出口」就够 —— **面板宽度不是编辑能力的瓶颈。**

#### 14.1.3 播放头 `currentStage`：唯一的状态指针，三个来源驱动

```cpp
// 旋钮：归一化值 × (maxStages-1) → 步号。旋钮同时是"显示器"和"手选器"（315 行）
currentStage = std::roundf(params[STAGE_SELECT].getValue() * (maxStages - 1));
```

- **Forward / Backward / Reset** 三个按钮 **+** 三个输入口，各自 `SchmittTrigger` + **显式上升沿比较**
  （`forwardCurrentState && !prevForwardState`，336–348 行）—— 和 `rcm-pianoroll` 一样是**边沿触发**。
- 每次改完都 `paramQuantities[STAGE_SELECT]->setDisplayValue(currentStage+1)` ⇒ **面板上那个旋钮就是"当前步"指示器**，
  配合 `STAGE_SELECT->displayOffset = 1.0f`（262 行）显示成 1-based。
- `maxStages` 变化时用 `displayMultiplier` 动态改量程（317–323 行）——见 14.1.8。

#### 14.1.4 录制：翻转式 REC + 直通 + 录满一圈自动停

```cpp
if (recTrigger.process(params[REC_BUTTON].getValue())) {
    recordLatched = !recordLatched;                    // ← 翻转，不是电平（415 行）
} else if (inputs[REC_INPUT].isConnected()) {
    if (recCurrentState && !prevRecordState) { recordLatched = !recordLatched; recordStateChange = true; }
    prevRecordState = recCurrentState;
}
if (recordLatched || recordStateChange) { /* 扫描输入 + 存 + 直通输出 */ }
```

- 条件写成 `recordLatched || recordStateChange`：**"刚进入录制的那一瞬"也要处理**（因为 REC 是上升沿翻转）。
- 录制期间输入**直通输出**（478/482/486 行）⇒ **边录边听**，和 PianoRoll 的行为一致。
- `stopRecordAtEnd`：循环回到第 0 步时自动停（330–332、342–344 行）—— **「录一圈就停」**。

#### 14.1.5 ★ 复音阶梯算法 `activeInputChannel[7]` —— **一根复音线喂多轨**

```cpp
int activeInputChannel[7] = {-1};       // 每个通道"从哪一根输入线上取"
for (int i = 0; i < 7; i++) {
    if (inputs[CHAN_1_INPUT + i].isConnected()) {
        inputChannels[i] = inputs[CHAN_1_INPUT + i].getChannels();
        activeInputChannel[i] = i;                               // 自己接了就用自己的
    } else if (i > 0 && activeInputChannel[i-1] != -1) {
        if (inputChannels[activeInputChannel[i-1]] > (i - activeInputChannel[i-1]))
            activeInputChannel[i] = activeInputChannel[i-1];     // ← 接力：接管上一根的下一路声部
        else
            activeInputChannel[i] = -1;
    } else activeInputChannel[i] = -1;
}
// 取值（464-475 行）
int diffBetween = i - activeInputChannel[i];
inputVal = inputs[CHAN_1_INPUT + activeInputChannel[i]].getPolyVoltage(diffBetween);
```

**含义**：往 CH1 插一根 **4 声道复音线** ⇒ CH1/CH2/CH3/CH4 **同时被喂满**（各取 0/1/2/3 号声部），
后面几路**不接线也能取值**。

⇒ **这条正是我们"键盘输入只能一组"难题的现成答案**，而且比"面板上选轨录制"更强：
一根复音线（4 个声道）可以直接喂 4 轨，**一个输入口都不用抢**。

#### 14.1.6 输出侧复音打包 `polyphonyChannels`

```cpp
outputs[CHAN_1_OUTPUT].setChannels(polyphonyChannels);            // 548-555 行
for (int c = 0; c < polyphonyChannels; ++c)
    outputs[CHAN_1_OUTPUT].setVoltage((c == 0) ? outputs[0].getVoltage() : outputs[c].getVoltage(), c);
```

⇒ 7 个单声道输出可以**合并成一根 7 声道复音线**从 CH1 出。menu 里 `1…7 Channels` 可切（890 行）。
（工具提示会跟着改成 `"Polyphonic Channel 1 (4 channels)"`。）

#### 14.1.7 每通道三模式：**同一份数据、三种解释**

`channelButton[i]` 循环 0/1/2（406–408 行）：

| 模式 | 输出什么 | 显示什么 |
|---|---|---|
| **0 直通** | `inputVal` 原样 | `"3.142 V"` |
| **1 量化** | `std::roundf(inputVal * 12.f) / 12.f`（吸附半音） | `"C4"` |
| **2 概率门** | `(v+10)/20` 当概率，每步掷骰，命中发 **1 ms 脉冲** 10 V | `"37%"` |

⇒ **数据格式不变，语义靠模式切换**。这条对"音符时长"有个启发：
**门长也可以做成"每轨一个参数"**（像 `NoteSeqFu` 的 `gateMode`），而不必 per-note 存 ——
我们目前已拍板 per-note `length`，但这是**成本更低的备选**，值得记着。

#### 14.1.8 一个旋钮管 2048 步：`lengthMultiplier`

```cpp
lengthMultiplier = static_cast<int>(maxSequenceLength / 128);      // 306 行
maxNumStages = params[MAX_STAGES].getValue() * lengthMultiplier;
paramQuantities[MAX_STAGES]->displayMultiplier = lengthMultiplier; // 307 行
```

`MAX_STAGES` 参数本身量程固定（0…128），靠 `displayMultiplier` 乘出实际步数。
⇒ **"参数值不变、量程随配置缩放"** 的通用做法，适合任何"上限可配"的旋钮。

#### 14.1.9 编辑效率：Shift 刷全部 / Copy-Paste Layer

- `smartKnobStates[i]`（504–509 行）：**Shift + 拧旋钮 = 把当前值写满全部 2048 步**。写一次不用循环拧。
- 菜单：`Copy Layer` / `Paste Layer`（当前步）/ `Paste to All Layers`（977–992 行，整层刷满）。

#### 14.1.10 界面（15 HP）：数码显示 + 手绘进度点 + 双色面板

- 面板：`setPanel(createPanel(asset::plugin(…, "res/Arrange.svg"), asset::plugin(…, "res/Arrange-dark.svg")))`
  ⇒ **亮/暗两套 SVG**，`createPanel` 两个参数（670–672 行）。
- **数码显示 `DigitalDisplay`**（包内 `src/digital_display.hpp`，**仅 33 行**）：
  `APP->window->loadFont(fontPath)` → 判空 → `nvgFontFaceId/nvgFontSize/nvgText`。
  字体用**包内自带**的 `res/fonts/DejaVuSansMono.ttf`（1007 行）。
  对齐用 `NVG_ALIGN_CENTER | NVG_ALIGN_MIDDLE`，居中坐标在 `drawLayer` 里自己算。
- **`ProgressDisplay`**（565–617 行）：`nvgCircle` 手绘一排小圆点，当前步画成大白点（半径 4，其余 2）。
  ⇒ **状态显示可以完全手绘，不依赖 SVG**。
- 布局：7 行 × **35 px** 间距（711 行），每行 `输入口 / 模式按钮+双色灯 / 大旋钮 / 数码显示 / 输出口`
  （715–725 行）—— **15 HP 装得下**。

---

### 14.2 `JW-Modules/Arrange` —— 16 × 64 门控网格

#### 14.2.1 数据模型：1024 个 `bool` + 16 个行名

```cpp
#define ARRANGE_ROWS 16
#define ARRANGE_COLS 64
#define CELLS 1024
#define CELLW 10                    // 每格 10 px 宽
#define CELLH 20                    // 每格 20 px 高
bool*       cells = new bool[CELLS];      // 堆分配，析构里 delete[]（115-124 行）
bool*       dirtyNames = new bool[ARRANGE_ROWS];
std::string rowNames[16];
```

JSON：`{"cells":[...1024 个 0/1...], "rowNames":[16 个字符串]}`（139–155 行）。
`dataFromJson` **校验数组长度**（`json_array_size(cellsJ) == CELLS`）才读 —— 防脏数据。

#### 14.2.2 每行一对 In/Out：纯门控、**支持复音透传**

```cpp
int channels = inputs[MAIN_INPUT + i].getChannels();
bool on = isCellOn(pos, i);
for (int c = 0; c < channels; c++)
    outputs[MAIN_OUTPUT + i].setVoltage(on ? inputs[MAIN_INPUT + i].getVoltage(c) : 0, c);
outputs[MAIN_OUTPUT + i].setChannels(channels);          // 199-207 行
```

⇒ **开关一行 = 让这一路通过或变 0**。它**不产生音高**，音高听上游的。
（面板文档图里行名是 `kick/snare/chat/ohat/ride/rim/fmop` —— 一套鼓。）

#### 14.2.3 ★ RESET 与时钟对齐：两段式 `resetMode`

```cpp
if (resetTrig.process(params[RESET_BTN_PARAM].getValue() + inputs[RESET_INPUT].getVoltage()))
    resetMode = true;                                      // ① 只置标志，不动位置（183-185 行）

if (clockTrig.process(inputs[CLOCK_INPUT].getVoltage() + params[STEP_BTN_PARAM].getValue())) {
    if (resetMode) { resetMode = false; hitEnd = false;
                     resetSeqToEnd(); }                    // ② 等下一个时钟才复位
    clockStep();                                           //    "退到末尾"⇒步进一步正好落在起点
}
```

`resetSeqToEnd()`（276–283 行）按播放方向把位置放到**末尾**，这样紧接着的 `clockStep()` 正好走到起点。

⇒ **这条很重要**：如果 RESET 当场改 `seqPos`，那**当时那一拍就丢了**。**"复位必须与时钟同拍"** 是序列器的通用正确做法。

#### 14.2.4 时钟输入与手动步进按钮**共用**一个触发器

```cpp
clockTrig.process(inputs[CLOCK_INPUT].getVoltage() + params[STEP_BTN_PARAM].getValue())
```

⇒ 面板上的 `STEP` 按钮就是"手动打一拍"。**不用写两套逻辑**，加法即可（按钮给 0/1 ⇒ 加 10 V 的那一路等价于脉冲）。
（同样的加法写法出现在 RESET/CLEAR/RND_TRIG —— 180–187 行。）

#### 14.2.5 所有参数可 CV 叠加：统一写在 getter 里

```cpp
int getSeqStart() {
    int inputOffset = int(rescalefjw(inputs[START_INPUT].getVoltage(), 0, 10.0, 0.0, ARRANGE_COLS-1));
    return clampijw(params[START_PARAM].getValue() + inputOffset, 0.0, ARRANGE_COLS-1);
}
```

`getSeqStart/getSeqLen/getPlayMode` 三个 getter 同构（285–306 行）：
**旋钮值 + CV 输入映射值 → clamp**。⇒ 「面板给默认、CV 给偏移」的通用范式。

#### 14.2.6 `EOC` 只在**跑满一圈之后**才发

```cpp
if (seqPos > seqEnd) { seqPos = seqStart; if (hitEnd) { eocOn = true; } hitEnd = true; }
```

第一圈不发（`hitEnd` 初始 false），**第二圈起每圈发一次**（226–264 行）。
⇒ 避免"刚启动就报结束"，也是我们做 `END_OF_SONG` 时的正确语义。

#### 14.2.7 ★ 自绘**可点击**网格（要画网格才用）

```cpp
struct ArrangeDisplay : Widget {
    void onDragStart(const event::DragStart& e) override {
        dragPos = e.mousePos;
        currentlyTurningOn = !module->isCellOnByDisplayPos(dragPos.x, dragPos.y);  // 拖拽 = 批量置位
        module->setCellOnByDisplayPos(dragPos.x, dragPos.y, currentlyTurningOn);
    }
    void onDragMove(const event::DragMove& e) override {
        dragPos = dragPos.plus(e.mouseDelta.div(getAbsoluteZoom()));   // ★ 必须除以缩放
        module->setCellOnByDisplayPos(dragPos.x, dragPos.y, currentlyTurningOn);
    }
    void drawLayer(const DrawArgs& args, int layer) override {
        // 网格线：每 4 格加粗（459-472 行）
        // 格子：colors[y%4] 四色循环（477-486 行）
        // 起点蓝线 / 终点紫线 / 播放头白框（490-511 行）
    }
};
```

- **`e.mouseDelta.div(getAbsoluteZoom())`** —— 缩放后鼠标位移要还原，否则拖拽错位。
- 拖拽语义：**按下时决定"要开还是要关"**（反相），拖动过程中统一刷成那个状态 ⇒ 可一笔画一排。
- 面板 `48 HP`（`RACK_GRID_WIDTH*48`），网格实际 `64×10 = 640 px × 16×20 = 320 px`。

#### 14.2.8 可编辑行名：`LedDisplayTextField` + `dirtyNames`

```cpp
struct RowTextField : LedDisplayTextField {
    void step() override {                                  // 553-559 行
        if (module && module->dirtyNames) { setText(module->rowNames[i]); module->dirtyNames[i] = false; }
    }
    void onChange(const ChangeEvent& e) override { module->rowNames[i].assign(getText()); }
};
```

⇒ **单向同步 + 脏标志**：模块侧改了才刷界面，界面改了写回模块。**不每帧 setText**（否则光标被打断）。
`LedDisplay` 是 Rack 内置控件，可直接用。

#### 14.2.9 Euclid 随机填充（8 行）

```cpp
int div = int(random::uniform() * ARRANGE_COLS * 0.5) + 1;
for (int x = 0; x < ARRANGE_COLS; x++) setCellOn(x, y, x % div == 0);
```

⇒ 生成"均匀分布"节奏型的最简实现（325–333 行）。另有 BASIC / SIN_WAVE / MIRROR_X / MIRROR_Y 共 5 种。

---

### 14.3 能直接搬进 `MiniArranger` 的清单（按优先级）

| # | 我们要解决的问题 | 抄谁 | 具体机制 | 代码位置 |
|---|---|---|---|---|
| **1** | **多轨编辑界面**（原本估为"最大工作量"） | `CVfunk/Arrange` | **旋钮 = 当前步**；步进 + 每轨 1 旋钮 1 显示 | `Arrange.cpp:384-401, 455-496, 619-659` |
| **2** | 键盘输入只能一组（原方案：面板选轨） | `CVfunk/Arrange` | **复音阶梯**：一根 4 声道线自动喂 4 轨 | `Arrange.cpp:430-475` |
| **3** | 复音输出（多轨打包成一根线） | `CVfunk/Arrange` | `setChannels(n)` + 逐声道 `setVoltage(v,c)` | `Arrange.cpp:548-555` |
| **4** | RESET 会吃掉一拍 | `JW-Modules/Arrange` | **两段式 `resetMode`**：置标志、下个时钟才复位 | `Arrange.cpp:183-195, 276-283` |
| **5** | 面板文字（SVG 不能写 text） | `CVfunk` | `DigitalDisplay` 33 行 + 包内字体 | `digital_display.hpp`、`Arrange.cpp:1001-1010` |
| **6** | 手动步进按钮 | `JW-Modules/Arrange` | 与时钟**共用**触发器（加法） | `Arrange.cpp:187` |
| **7** | 每轨参数也想吃 CV | `JW-Modules/Arrange` | getter 里 `旋钮 + rescale(CV)` 再 clamp | `Arrange.cpp:285-306` |
| **8** | 「一次刷满所有步」这类编辑效率操作 | `CVfunk/Arrange` | Shift+拧 = 刷全部；Copy/Paste Layer | `Arrange.cpp:504-509, 931-997` |
| **9** | 参数上限可配（一个旋钮管 N 步） | `CVfunk/Arrange` | `displayMultiplier` 缩放量程 | `Arrange.cpp:299-323` |
| **10** | 亮/暗双主题面板 | 两家都有 | `createPanel(svg, svg-dark)` | `Arrange.cpp:669-672` |
| **11** | 状态显示（当前步 / 进度） | `CVfunk` | `nvgCircle` 手绘一排点 | `Arrange.cpp:565-617` |
| **12** | 一次性模式 | `CVfunk/Arrange` | 每轨三模式：直通 / 量化 / 概率门 | `Arrange.cpp:477-490` |

**⚠️ 一个要留意的反例**：`CVfunk/Arrange` 把 2048×7 的矩阵**全量写进 JSON**
（14336 个 float，机架文件会变大）。我们的 `ArrangerData` 目前**只存非空音符**，这点不要学它。

---

### 14.4 三套数据格式对比（决定我们存什么）

| | `CVfunk/Arrange` | `JW-Modules/Arrange` | **我们 `ArrangerData`（现状）** | `Portable Sequence` |
|---|---|---|---|---|
| 存什么 | CV 电压矩阵 | 0/1 门控 | `step / length / pitch / velocity` | `start / pitch / length / velocity` |
| 步数 | 128–2048 | 64 | 由 `length` 决定（数据层 vector 无上限） | 不限 |
| 音高 | 靠"量化模式"解释 | 无（透传） | 原生字段 | 原生字段 |
| **音符时长** | 无（步为单位） | 无（格为单位） | ✅ **per-note `length`** | ✅ `length` |
| 复音 | 靠多声道 | 靠透传 | 待做（见 §14.3 #3） | 多个 note 重叠即可 |
| 轨数 | 7 | 16 | 4 + 扩展器 | — |
| 体积 | ⚠️ 全量存（大） | 1024 个整数 | ✅ 只存非空 | 只存有音符 |

⇒ **结论：我们的数据模型方向是对的，不需要改。** 要补的是**编辑手段**（#1）与**复音输入输出**（#2 #3）。

---

### 14.5 方法论补记：为什么我两次漏掉它们

两位作者的模块名是 `Arrange` —— **就是"编排"二字**。而我搜的是
`sequencer` / `portablesequence` / `MAX_TRACKS` / `noteLength` 这些**我以为会出现在源码里的技术词**。

- **搜索的盲区**：关键词只能命中**我已经知道存在**的东西。**我没想到"编曲"这个功能可能就叫 `Arrange`。**
- **本轮的补救**：全量列出 86 包 / 1424 个模块名**人工过一遍**（已写进技能 `cardinal-module-dev` §0.1）。
- **再加一条（本轮新增）**：**同名/近名模块必须逐个打开看源码** ——
  本机两个 `Arrange`，一个是门控网格、一个是七通道序列器，**功能完全不同**。
  ⇒ 判断依据只能是「**包名 + 源码**」，不能只看 slug 或名字。

---

## 15. `MiniArranger` 录制与编辑落地（2026-09-21 12:41 编译 · 已替换 exe）

李 12:34 的指令：「**要我按这套机制去补 MiniArranger 的编辑与录制**」——
即把 §14.3 那十二条可搬清单落成真代码。本节是结果。

### 15.1 一句话

`MiniArranger` 从"只画得出来"变成"**能录、能放、能改**"：
面板自带 RUN / REC 按钮，弹键盘就把音符录进当前轨，音符**带 per-note 时长**（现成件缺的那个字段），
并且用「旋钮 = 当前步」的范式实现编辑，**不用画网格、不用弹窗**。

### 15.2 面板与端口（40 HP 定稿）

**面板 203.2mm × 128.5mm = 40 HP**（骨架版是 30 HP，本轮扩宽）。

扩宽的两个硬理由：
1. 编辑区要放 **7 个旋钮**（STEP / LAYER / EDIT + 4 个轨值旋钮）+ 一条 **100mm 宽的时间轴**；
   30 HP 的主区只剩 84mm，7 个旋钮平分间隔不到 12mm（旋钮本身就有 8mm），排不下。
2. 骨架 30 HP 布局里有一个**暗伤**：共享输入的标签文字（如 `VELOCITY`）
   在端口右侧 7mm 起写，会压到共享输出那一列 —— 扩宽后标签区有 56mm，不再重叠。

**分区**（坐标单位 mm，与 `res/MiniArranger.svg` 的 viewBox 同系）：

| 区 | 范围 | 内容 |
|---|---|---|
| 标题条 | y 0–13 | 标题 + RUN/REC 按钮 + 两盏灯 |
| 共享输入 | x 14，y 26–117 | 8 个口（一列） |
| 共享输出 | x 44，y 26–78 | 5 个口（一列） |
| 静音列 | x 79，y 17–53 | 4 个 CKSS（每轨一个） |
| **总览时间轴** | x 92–196，y 17–53 | 4 行 × N 格点阵，红游标 = 当前步 |
| **编辑区** | y ≈ 74 | STEP / LAYER / EDIT + 4 个轨值旋钮 |
| 轨道输出 | x 104+24·t，y 96+13·o | 4 轨 × 3 口 |

**端口编号表**（`MiniArranger.cpp` 里的枚举顺序，接线时按这个数）：

| 口 | 编号 | 说明 |
|---|---|---|
| `CLOCK` / `RESET` / `RUN` / `RECORD` | IN 0–3 | RUN 与 RECORD 是**边沿翻转**（照抄 rcm-pianoroll） |
| `VOCT` / `GATE` / `RETRIGGER` / `VELOCITY` | IN 4–7 | **只有一组**；`VOCT` 支持复音阶梯 |
| `CLOCK` / `RESET` / `RUN` / `RECORD` / `END_OF_SONG` | OUT 0–4 | 前四个原样转发；END_OF_SONG 在回卷时发 1ms 脉冲 |
| TRACK1 `VOCT`/`GATE`/`VEL` | OUT 5–7 | 每轨独立一组 |
| TRACK2 / TRACK3 / TRACK4 | OUT 8–10 / 11–13 / 14–16 | 同上 |

**参数编号表**：

| 参数 | 编号 | 范围 | 说明 |
|---|---|---|---|
| `MUTE1..4` | 0–3 | 0/1 | 每轨静音 |
| `TRACK_EDIT` | 4 | 0–3 snap | 录给哪一轨（**也决定面板上哪一行高亮**） |
| `STEP` | 5 | 0–1 | 归一化，映射到 `0..songSteps-1` |
| `LAYER` | 6 | 0–2 snap | PITCH / LENGTH / VELOCITY |
| `VALUE1..4` | 7–10 | 0–1 | 每轨「当前步 + 当前层」的值 |
| `RUN` / `REC` | 11–12 | 按钮 | 面板自带，不用再外接 Button 模块 |

### 15.3 数据结构

沿用 §14.4 的结论（**只存非空音符**，不学期 CVfunk 的全量矩阵）：

```cpp
MaNote  { int step; int length; int pitch; float velocity; }   // length 就是现成件缺的那个
MaTrack { string label; bool mute; int measures; vector<MaNote> notes; }  // notes 恒按 step 排序
MaUnit  { MaTrack tracks[4]; int editTrack; float stepsPerQuarter; }
```

尺寸常量：`MA_TRACKS=4`、`MA_MAX_MEASURES=64`、`MA_STEPS_PER_MEASURE=16`、
**`MA_MAX_LENGTH=16`**（单音符最长一小节）。整首歌长度 = 最长那条轨。

存取：`dataToJson()` 存 `{"arranger": {...}, "running": bool, "currentStep": n}`；
`fromJson` 后置 `dirty=true` + `lastEditTrack=-1` 强制下一帧回灌。

### 15.4 录制语义（本轮的核心）

| 环节 | 做法 |
|---|---|
| 进入录制 | `RUN` 与 `RECORD` **都**要按过；面板按钮与外部输入**各自检测边沿再合并**（不共用触发器，避免短路吃掉边沿） |
| 音符开始 | `GATE` **上升沿** → 记下 `step = currentStep`、音高（`VOCT` 换算）、力度 |
| 音符结束 | `GATE` **下降沿** → `length = currentStep - startStep + 1` ⇒ **按住几格就是几格** |
| 覆盖 | 写入前对该位置执行 `clearAt(step)`（删掉所有覆盖该步的音符），重录同一处 = 覆盖 |
| 按住中改音高 | 允许——取松手时的最终音高 |
| 退出录制 | `finishAllRecordings()` 收尾所有按着的音符，并 `reset()` 全部 GATE 触发器 |
| 跨回卷 | 走带绕回 0 时先 `finishAllRecordings(steps)`（收到歌尾），避免 length 变负数 |
| **复音阶梯** | `VOCT` 的声道数 N>1 时，第 c 声道录到第 c 轨；N=1 时录到 `TRACK_EDIT` 选的轨 |

**录制期间输出直通**：录的时候 `refreshOutputs()` 照跑，所以**边录边出声**（和 rcm-pianoroll 一致）。

### 15.5 编辑语法：旋钮 = 当前步（§14.3 #1 的落地）

面板**不画 N×M 网格**。数据在内存里是整首歌，面板上只有「当前那一步」：

- **回灌**：位置（step / 轨 / 层）一变，就把那一格的值送进 4 个旋钮 ——
  `unit.readLayerNorm(track, layer, step)` → `params[VALUE1+t].setValue(v)`。
- **写回**：用**旋钮值变化检测**（不是只靠拖拽事件）——
  `fabs(params[].getValue() - lastKnobValue[t]) > 1e-6` 就写回。
  这样**鼠标滚轮、自动化**也能编辑，不只是拖拽。
- **自动创建**：写回时该步没有音符，`ensureNoteAt()` 就现造一个（默认 C4、长 1 格）。
  ⇒ **拧旋钮就是写下第一个音符**，不需要"先新建再编辑"。
- **层映射**：PITCH → MIDI 12..108；LENGTH → 1..16 格；VELOCITY → 0..1。
- **步进跟随**：播放时 `STEP` 旋钮随走带刷新；手动拧 `STEP` 即跳步（`stepJump` 走原子变量交给音频线程消费）。
- **点击交互**：面板时间轴上点击 = 跳到那一格 + 把编辑轨切到点中的那一行。

**总览时间轴**（这是 §14 里点名的两个真缺口之一「跨模块看不到总表」的直接答案）：
4 行点阵，每轨一色（青/琥珀/绿/紫），带小节分隔线与红色播放游标；
静音的轨画成暗灰（一眼看出它不出声）；当前编辑轨那一行有青色底。

### 15.6 竞态保护（最容易出玄学 bug 的地方）

| 竞态 | 处理 |
|---|---|
| 回灌把用户正在拧的旋钮弹回去 | `std::atomic<bool> isEditing[4]`，由 `SmartKnob::onDragStart/onDragEnd` 置位（抄 CVfunk），回灌时跳过 |
| 回灌本身被误判成"用户在拧" | 回灌后**同步更新** `lastKnobValue[t]`，下一帧比较就不会自触发 |
| UI 线程读音频线程正在改的 `vector` | **不直读**。音频线程把结果写进一组 POD 快照（`snapStep` / `snapPitch[]` / `overview[][]` 等），UI 只读快照；最坏读到上一帧的值，不崩 |
| UI 写 `currentStep` | 走 `std::atomic<int> stepJump`（UI 写、音频线程 `exchange(-1)` 消费） |
| 每帧扫音符太重 | 只在 `stepChanged / trackChanged / layerChanged / dataChanged` 时才 `refreshOutputs()` + `updateSnapshot()` |

### 15.7 本轮照抄了 §14.3 的哪几条

| # | 内容 | 落地位置 |
|---|---|---|
| 1 | 旋钮 = 当前步 | `readLayerNorm` / `writeLayerNorm` + 4 个 VALUE 旋钮 |
| 2 | 复音阶梯 | `recTrackFor()` + `getPolyVoltage(c)` |
| 4 | RESET 两段式 | `resetPending` 标志，等下一个时钟才复位 |
| 5 | 面板文字 | 沿用原有 nvg 方案（`asset::system("res/fonts/ShareTechMono-Regular.ttf")`），字体失败也不中断绘制 |
| 6 | 按钮与输入共用触发器 | `runButtonTrig` / `runTrig` 各自检测再 OR（比 CVfunk 的相加写法更稳，不会短路） |
| 9 | 分层编辑 | `LAYER` 旋钮 + 三档映射 |
| 11 | 状态显示 | 总览点阵 + 游标 + `noteNameOf()` 音名 |

**没抄的**：`displayMultiplier`（#9 的缩放量程）、Shift 刷全部（#8）、亮暗双主题（#10）、
每轨三模式（#12）—— 都不影响"能录能放能改"，留作后续。

### 15.8 编译与部署实测

| 步骤 | 结果 |
|---|---|
| 单文件语法检查 | **2 个错误**（第 1 次：`ModuleWidget` 里没有 `params`，要写 `m->params`）→ 修好第 2 次**零错零警告** |
| 全量交叉编译 | 17 秒；`CardinalMini.lv2` 链接失败（**09-20 起的已知问题**，Bogaudio widgets 缺图形符号，与本次改动无关） |
| 单独编 `CardinalNative` | ✅ 成功 |
| 产物 md5 | `403354bc…` → `06d93edb9b6ba9c6df9575e0d7c6b4af` |
| 大小 | 102,912,000 → 102,926,336（+14,336 字节，符合"只加了一点逻辑"） |
| 目标 `.o` | `MiniArranger.cpp.o` 306,536 字节（12:40 刷新）✅ |
| 对照组 `.o` | `Blank.cpp.o` 09-20 19:13、`Clocked.cpp.o` 09-20 19:34、`PianoRollModule.cpp.o` 09-20 19:35 —— **均未动** ✅ |
| 归档 | `plugins.a` 内含 `MiniArranger.cpp.o` ✅ |
| exe 符号 | `Starsea-MiniArranger` ×1、`...Module` ×2、`...Widget` ×3、`Starsea-Sketch` ×1、`MiniArranger.svg` ×1 |
| **新参数进 exe** | `Edit layer` ×1、`Edit step` ×2 ⇒ **证明新代码真编进去了**（不是旧版） |
| 部署 | 备份旧版 `CardinalNative.20260921-1112.exe` → 拷 `.new` → 校验 md5 → 原子改名 |
| 面板 | 40 HP / XML 合法 / **零个 `<text>`**（nanosvg 不画 text）/ PE 头 x86-64 GUI ✅ |

### 15.9 尚未实现（明确清单，免得当成 bug）

1. **扩展器**：`MaUnit` 已为"每块扩展器自带一份数据"留好结构，但**扩展器模块本身还没写**；
   目前只有主模块这 4 轨。
2. **Portable Sequence 导入 / 导出**：§10 发现的那条"AI 直接灌音符"的通道，还没接。
3. **歌曲级段落编排**：没有 Song 模式（A A B A 那种段落表）。目前是"一遍到底再循环"。
4. **撤销 / 复制粘贴**：没有。
5. **每轨独立长度**：`MaTrack::measures` 字段在，但**面板上没有改它的入口**（要改得进 JSON 或加旋钮）。
6. **复音输出**：每轨仍是单声道 3 口；`setChannels()` 打包没做。

### 15.10 已知限制（使用时会撞到的）

- **量化到格**：音符起始与时长都被对齐到时钟格，弹得比格子细会被抹平（这是设计，不是 bug）。
- **同一格只能一个音符**：`clearAt` 会把该格原有音符删掉 ⇒ **暂时录不了和弦**（复音要看 §15.9 第 6 条）。
- **时钟比决定分辨率**：`CLOCK` 接 16 分 ⇒ 一格 = 16 分；想更细得喂更快的时钟。
  16 格/小节是硬编码的（`MA_STEPS_PER_MEASURE=16`），喂 8 分时钟就是 2 拍一小节。
- **录音必须 RUN + REC 都在**：只按 REC 不按 RUN，时钟不走，录不进东西。
- **面板宽 40 HP**：比 `rcm-pianoroll` 还宽，一屏放两块就有点满。

### 15.11 待李实机验收（我做不到的部分）

我改不了他的操作，也跑不了 GUI。要他确认：

1. 模块列表里搜 `MiniArranger`，拖出来是否**不再是 30HP 的旧面板**（应宽一圈，多了 7 个旋钮 + 时间轴）；
2. 按 RUN → 按 REC → 接键盘弹几下 → 再按 REC 停 → 是否听到刚才那段；
3. 拧 STEP 旋钮跳步，看总览游标是否跟着走；
4. 切 LAYER 到 PITCH / LENGTH，拧某轨旋钮，看能否改音高与时长（**这是"音符时长"缺口有没有补上的直接验证**）。


---

## 16. `MiniArrangerExpander` + Portable Sequence（2026-09-21 13:0x 交付 · 已部署待验收）

李一句「这俩你一起做吧」同时拍了两件：① **扩展器加轨**（§11 拍板后的落地）
② **Portable Sequence 导入导出**（§10 发现的那条"AI 直接灌音符"的通道）。

### 16.1 新模块 `Starsea-MiniArrangerExpander`（24 HP）

**职责**：给主模块再加 4 条轨。每块扩展器**自带自己那 4 轨的数据**（乙案），
自带 12 个输出口、4 个编辑旋钮、TRACK / LAYER 选择、3 个状态灯。

| 项 | 值 |
|---|---|
| 面板 | **121.92 × 128.5 mm = 24 HP**（`res/MiniArrangerExpander.svg`） |
| 参数 | 6 个：`VALUE1..4`（4 个编辑旋钮）+ `TRACK_EDIT` + `LAYER` |
| 输出 | **12 个**：轨 t 的 VOCT/GATE/VEL 占 `TRACK1_*_OUTPUT + t*3 + o`（t=0..3） |
| **输入** | **0 个** —— 走带与键盘都从消息来，**这块模块不用接任何线** |
| 灯 | `LINK`（左边找到主模块）/ `RUN` / `REC` |
| 面板分区 | 左 x 20..62：4 列 × 3 行输出；右 x 88/106：2×2 编辑旋钮 + TRACK/LAYER |

### 16.2 通信协议（`ArrangerData.hpp` 的 `MaMsgIndex`）

走 Rack 原生扩展器双缓冲消息：**零拷贝、1 个时间步延迟**。缓冲长度
`MA_MSG_SIZE = 8 + 16 × 5 = 88` 个 float（两边**必须等长** —— 对方直接往我的 producer 那块内存写）。

| 索引 | 方向 | 含义 |
|---|---|---|
| `MA_MSG_STEP` | 主 → 扩 | 当前步号（**扩展器直接跟随，不自己步进**） |
| `MA_MSG_LOOP` | 主 → 扩 | 一圈多少步 |
| `MA_MSG_RUN` / `MA_MSG_REC` | 主 → 扩 | 走带 / 录音状态（点灯与录制门槛） |
| `MA_MSG_NCHAN` | 主 → 扩 | 键盘 VOCT 的声道数（复音阶梯用） |
| `MA_MSG_EVCOUNT` | 主 → 扩 | 本时间步带了几条键盘事件 |
| `MA_MSG_EV_BASE + i*5 + {0..4}` | 主 → 扩 | 事件：`type, chan, pitch, velocity, step` |
| `MA_MSG_TOTALNOTES` | 扩 → 主 | 我这边有多少音符（主模块面板显示 `EXT: n NOTES`） |

事件只有两种：`MA_EV_NOTE_ON`（带起始步）/ `MA_EV_NOTE_OFF`（带结束步，`length = step - onStep`）。

### 16.3 三条设计决定（都不是随手选的）

1. **不走"扩展器自己接时钟线"这条路。**
   起初想过让扩展器面板带 CLOCK 输入口、自己步进。**否掉了** —— 消息延迟是
   **时间步级**（不是采样级），把时钟边沿发过去会被吞步。改成**主模块把算好的步号直接发过去**，
   扩展器只跟随 ⇒ 不会跑偏，而且**省掉 4 根接线**。
2. **不缓存 `leftExpander.module` 指针。** 每帧重取 + 用前校验 `model`
   —— 规避 Rack 2.4.1「删邻居模块时 `onExpanderChange()` 不触发」那个野指针 bug（§11.3 ④）。
   主模块被拔掉时，扩展器把 `recActive[]` 清空、`remoteStep` 归零、写出 0V。
3. **录制逻辑两边各跑一份，而不是主模块替扩展器存。**
   主模块负责采样键盘、判音符边界，把**事件**发过去；扩展器用**和主模块同一套规则**
   （`recTrackFor`：单声道录面板选定的轨，多声道第 c 声道录第 c 轨）落到**自己的** `MaUnit`。
   ⇒ 数据始终在自己那块，符合乙案。

### 16.4 ★ 使用侧硬约束（必须转告李）

**扩展器必须紧贴主模块、中间不能插别的模块、且在主模块右侧。**
原因：Rack 的 `leftExpander` / `rightExpander` 只认**空间上相邻**的模块（**不支持上下相邻**）。
中间插一个模块 = 消息断路 = 扩展器看起来"坏了"（症状：`LINK` 灯不亮、录不进、不出声）。

### 16.5 Portable Sequence 导入 / 导出

新增 `src/PortableSequence.hpp`（抄自 `AriaModules/src/portablesequence.hpp`，**WTFPL** 可自由使用；
本文件做了 4 处改动：不 include 别家 `plugin.hpp` 以免污染命名空间 / 加 `toString`·`fromString` /
`length` 用 `double` 防长曲子累积误差 / 用 `json_object_set_new` 修掉原版的引用泄漏）。

**右键菜单**（`MiniArranger` 面板上）：

```
Portable Sequence (system clipboard)
  Import clipboard -> track 1  (replaces it)
  ...                                     ×4
  Track 1 -> clipboard  (n notes)
  ...                                     ×4
  Clear all notes
```

**换算**（单位不同，这是最容易错的地方）：

| 方向 | 公式 |
|---|---|
| 导入 `step` | `round(start × stepsPerQuarter)`（`stepsPerQuarter` 默认 4 ⇒ 1 个四分音符 = 4 格） |
| 导入 `pitch` | `round(pitch_VOct × 12) + 60` |
| 导入 `velocity` | `velocity / 10`（对方 0–10 → 我们 0–1；缺省给 0.8） |
| 导出 | 全部反过来；`length` = `songSteps / stepsPerQuarter` |

**线程安全**：剪贴板只能在 UI 线程碰（GLFW 要求），所以菜单回调负责**解析**，
把结果塞进 `importNotes` + 置 `importTarget`；音频线程在 `process()` 开头消费。
导出反向：音频线程在数据变化时把音符灌进**定长 POD 快照** `noteSnap[4][512]`，
UI 线程只读快照 —— **绝不跨线程读 `std::vector`**。

导入语义 = **替换该轨**（不是叠加）；`Clear all notes` 走 `clearRequest` 标志，同样交音频线程执行。

### 16.6 编译与部署（实测）

| 项 | 结果 |
|---|---|
| 单文件语法检查 | 扩展器 **一次通过零警告**；主模块也一次通过 |
| 全量交叉编译 | 18 秒；`CardinalMini.lv2` 仍是 09-20 起的既有链接错（无关） |
| 补编 | `cd src && xvfb-run -a make -C CardinalNative` ✅ |
| 产物 md5 | `06d93edb9b6ba9c6df9575e0d7c6b4af` → **`bad3dee1b9ce1e894f0c72c7abdbbdca`** |
| 大小 | 102,926,336 → **102,963,200**（+36,864 字节） |
| 目标 `.o` | `MiniArranger.cpp.o` 13:03:29、`MiniArrangerExpander.cpp.o` **新建** 13:03:20、`plugins.cpp.o` 13:03:40 ✅ |
| 对照 `.o` | `Blank.cpp.o` / `Clocked.cpp.o` / `PianoRollModule.cpp.o` **均停在 09-20** ✅ |
| exe 内符号 | `Starsea-MiniArrangerExpander` ×1、`StarseaMiniArrangerExpanderWidget` ×1、`MiniArrangerExpander.svg` ×1、`Import clipboard` ×1、`MINI ARRANGER EXP` ×1、`NO MASTER` ×1；`vcvrack-sequence` **12 → 13 处** |
| 部署 | 备份 `CardinalNative.20260921-1242.exe` → 拷 `.new` → md5 三处一致 → 原子改名 |
| 资源 | `win64/resources/Starsea/res/MiniArrangerExpander.svg` + `PluginManifests/Starsea.json`（现 3 模块） |

⚠️ 顺手修掉一处旧错误：`tools/layout_patch.py` 的 `WIDTH_BY_PLUGIN_MODEL` 里
`Starsea/MiniArranger` 还写着 **30**（那是骨架期的尺寸，早已改 40），已修正并登记
`Starsea/MiniArrangerExpander: 24`。

### 16.7 演示机架 `patches/mini_arranger_expanded.vcv`

12 模块 / 14 线 / version `2.1.2` / zoom 0.75。生成脚本 `tmp/build_mini_arranger_expanded.py`（含自检）。

```
row0: Clocked | HostMIDI | MiniArranger(40) | MiniArrangerExpander(24) | VCO ADSR VCA -> audio L
                                                                            VCO ADSR VCA -> audio R
row1: TextEditor（贴在面板上的使用说明）
```

自检断言：线缆端点齐全 ✅ / 无输入口双接 ✅ / **主模块右边缘 x=74，扩展器 x=74，间隙 0 格，中间无模块** ✅
（最后这条是扩展器能不能通的**必要条件**，所以写成了 `assert`）。

### 16.8 §15.9「尚未实现」的更新

- ~~1. 扩展器~~ → ✅ **本条已实现**（本节）
- ~~2. Portable Sequence 导入 / 导出~~ → ✅ **本条已实现**（本节）
- 3. 歌曲级段落编排 · 4. 撤销/复制粘贴 · 5. 每轨长度入口 · 6. 复音输出 —— **仍未做**
- 新增未做：**多块扩展器串联**（第二块的左边是另一个扩展器，需要写转发中继；本轮只做了一级）

### 16.9 待李实机验收

1. 打开 `patches/mini_arranger_expanded.vcv`（**打开前先存盘你现在的机架**），
   看 `MiniArrangerExpander` 的 **LINK 灯是否亮**（亮 = 跟主模块通上了）。
2. 主模块按 RUN → REC → 弹键 → 再按 REC 停 → RUN 播放，**听左声道**（主模块轨 1）。
3. 把扩展器的 `TRACK` 旋钮拧到 1，再录一遍（主模块的 REC 状态是共享的），
   **听右声道**（扩展器轨 1）—— 这就是"加轨"生效的直接验证。
4. 拧扩展器的 4 个编辑旋钮（默认层 PITCH），看它显示的轨号下方的值有没有跟着变。
5. 右键 `MiniArranger` → `Track 1 -> clipboard`，再粘到记事本里，应当看到
   `{"vcvrack-sequence": {...}}` 的 JSON。

## 17. `Mute` 不生效修复（2026-09-21 15:3x，李实机反馈）

**李的反馈**：左右声道都通了（验收项 ②③ 通过）· 导出剪贴板正常（项 ⑤ 通过）· 编辑旋钮有效（项 ④ 通过）；
**但拨 `MUTE` 到 On 后 Track 1 没被彻底静音。**

### 17.1 根因（读码定位，不是猜）

`refreshOutputs()` 里 mute 的逻辑**本身是对的**（mute ⇒ `outGate = 0` / `outVel = 0`，
VOCT 刻意保留 —— 门关了但音高不断，免得外部 VCO 每次跳音）。

问题在**触发时机**。`unit.tracks[i].mute` 在 `process()` 开头由面板开关写入，但刷新条件只有：

```cpp
if (stepChanged || trackChanged || layerChanged || dataChanged) { refreshOutputs(); updateSnapshot(); }
```

**没有包含「mute 变化」** ⇒

| 情形 | 现象 |
|---|---|
| 播放中拨 mute | 要等**下一个时钟边沿**才静音（延迟一拍） |
| **停止中拨 mute（没有时钟）** | **永远不刷新 ⇒ 门保持 10V 挂着，音一直响** ← 李遇到的 |
| 面板总览「静音轨画暗灰」（读 `snapMute`） | 同样只在 `updateSnapshot()` 里更新 ⇒ **拨开关时面板也无即时反应** |

最后一条正好解释李说的「点了那个 On 好像也没有反应」。

### 17.2 三处修复

1. **写入时检测变化** —— `unit.tracks[i].mute` 与面板值比较，不同才置 `muteChanged = true`。
2. **刷新条件加 `|| muteChanged`** —— 输出与面板快照都即时跟上。
3. **输出段再判一次 mute**（`muted ? 0.f : outGate[t]`）—— **硬保证**，不依赖任何刷新时机；
   走带停着、没有任何 step 变化时也不会漏。**这条是关键：前两条都可能被将来的人改回去，
   有了它「拨下开关立刻静音」永远成立。**

### 17.3 遗留（未擅自做，等李定）

- **扩展器那 4 轨没有 Mute 开关** —— 它只有 6 个参数（4 编辑旋钮 + TRACK + LAYER）。
  想静音扩展器的轨目前只能拔线。
- **停止（RUN 关）时门保持不落** —— 这是既有设计（JW Modules 的 Arrange 也这样，便于调音色），
  但它意味着「按 RUN 停」不会让音停。**要不要改成「停 = 门落」？等李拍板。**

### 17.4 编译与部署（实测）

- 路径：单文件语法检查 → `make plugins` → `cd src && make -C CardinalNative`
  （只改 1 个模块**不需要全量重编**）
- **`.o` 尺寸随源码变**：修复版 `MiniArranger.cpp.o` = **390,389** ⇄ 还原版 = **390,325**
  （**差 64 字节**，正是新增代码量）
- md5：旧 `bad3dee1…` → 新 **`026a838146c12829dbdab32e80f2c6e7`**；体积三次都是 102,963,200
- 对照 `.o`（`Cardinal/Blank.cpp.o`、`ImpromptuModular/Clocked.cpp.o`）停在 09-20；
  同包其他 `.o`（`MiniArrangerExpander` / `Sketch`）停在 13:03 —— **都没动** ✅
- 部署：三步式原子替换（暂存 → 挪开旧 → 放新的，失败自动回滚），复核 md5 通过
- 回滚点：`win64/CardinalNative.20260921-154206.exe`（= 旧版 `bad3dee1…`）

### 17.5 ⚠️ 重要方法论更正：`CardinalNative.exe` 的 md5 **不可复现**

| 源码状态 | exe md5 |
|---|---|
| 旧源（改动前） | `bad3dee1b9ce1e894f0c72c7abdbbdca` |
| 改源 → 编译 | `4f7e90ea9160546dadc8dd81f0cc167b` |
| **还原源码** → 编译 | `fa1a63e3fb150493d494a7bbceee1790` ← **回不到 `bad3dee1`** |
| 再改源 → 编译 | `026a838146c12829dbdab32e80f2c6e7` |

**同一份源码连编两次 md5 就已经不同** ⇒ 「产物 md5 变化」**不能证明改动生效**，
「还原能精确复原」也不成立。体积三次**一模一样**（102,963,200）；逐节比对
`.text` / `.rdata` / `.data` / `.pdata` / `.xdata` **全变**，24 MB 字节不同 / 157 万个差异区间
—— 典型的「链接布局整体位移」。怀疑源：链接时每次都要重编的 `DistrhoPluginMain.cpp`
带了时间戳常量，字符串一挪位，后面所有 RIP 相对引用全部改变（**未最终定论**）。

⇒ **可靠判据 = 目标 `.o` 的尺寸/md5 随源码变**（本法已实测）。
已更正技能 `cardinal-wsl2-build`（原写「md5 最硬、本机可复现」）与 `cardinal-module-dev` §1.4。

**过程中的教训**：我第一版验证拿 exe md5 当硬证据，差点直接收工；
是因为「**体积一字节不差**」这个反常点起疑，才补做「还原 → 重编」测试 ——
结果**推翻了我自己的假设**。⇒ **当证据与预期不符（此处：尺寸完全相同），别忽略它，去查。**

### 17.6 部署时发现的两条环境事实

1. **Windows 允许「重命名」正在运行的 exe** ⇒ `os.replace(旧的, 备份)` 在 Cardinal 开着时也能过；
   但**直接覆盖目标会 `ACCESS_DENIED`**。⇒ 正确姿势是「先把旧的挪走 → 再把新的放进来」。
2. **宿主的安全删除会拦 `os.remove`**：它把删除转投回收站，而**被进程映射着的 exe 回收站操作被中止**
   ⇒ 报 `[safe-delete] ... trash-failed`。**这不影响替换**，只留一个 `CardinalNative.exe.bak-tmp`
   需等 Cardinal 关掉后再删。⇒ **替换脚本要把清理放最后并允许它失败。**

（两条都已写进技能 `cardinal-module-dev` §1.4。）

---

## 18. 键盘直通（手弹优先）：让「弹下去就出声」（2026-09-21 16:35 李要求）

### 18.1 起因

李报告：录 track 2 / track 3 后播放无声，**录音时弹键也无音**，但面板显示有键录进去。
排查结论（详见日志第三十节，三条，均非代码 bug）：

1. **轨 2/3/4 的输出口空悬** —— 机架里只有轨 1（out5+out6）与扩展器的轨 1（out0+out1）接了发声链；
2. **模块没有输入直通** —— 键盘进来只被**记录**，不发声；
3. 存盘时 **Track 1 处于 mute**，而它恰好是唯一接了声的轨。

李的诉求（原话）：「我没有录的时候，我现在就都听不到我弹的声音了，这肯定不太好……你最好改一下」。

### 18.2 设计决定（四条）

| 决定 | 选择 | 理由 |
|---|---|---|
| 直通送到哪个口 | **只送「当前编辑轨」**（TRACK 旋钮选的那轨） | 送到全部 4 轨的话，4 轨各接音色时会「齐奏」（按一个键响 4 遍）|
| 与回放冲突 | **手弹优先**：手弹期间该口输出输入电压，松手立刻回到回放 | CV 口是单路，不能把「手弹」与「回放」相加（V/Oct 相加 = 跑调）|
| 与静音冲突 | **静音优先**：mute 的轨不直通 | 与 mute 语义一致 |
| 何时计算 | **每帧在输出段重算、不缓存** | 同 mute 那次的教训：走条件刷新会让门「卡在 10V 不落」|

### 18.3 实现（`MiniArranger.cpp` §7 输出段，+168 字节指令）

```cpp
const bool  thruDown  = inputs[GATE_INPUT].isConnected() &&
                        (inputs[GATE_INPUT].getVoltage() > 1.f);
const int   thruTrack = clamp(unit.editTrack, 0, MA::MA_TRACKS - 1);
const float thruVoct  = inputs[VOCT_INPUT].getVoltage();
const float thruVel   = inputs[VELOCITY_INPUT].isConnected()
                        ? inputs[VELOCITY_INPUT].getVoltage() : 10.f;

for (int t = 0; t < MA::MA_TRACKS; ++t) {
    const bool muted = unit.tracks[t].mute;
    const bool thru  = thruDown && (t == thruTrack) && !muted;
    outputs[TRACK1_VOCT_OUTPUT + t * 3].setVoltage(thru ? thruVoct : outVoct[t]);
    outputs[TRACK1_GATE_OUTPUT + t * 3].setVoltage(muted ? 0.f : (thru ? 10.f : outGate[t]));
    outputs[TRACK1_VEL_OUTPUT  + t * 3].setVoltage(muted ? 0.f : (thru ? thruVel : outVel[t]));
}
```

### 18.4 行为表

| 状态 | 当前编辑轨那个口输出什么 |
|---|---|
| 手按住键（录音中或没录音，都一样） | **手弹的 V/Oct + gate 10V + 力度电压** |
| 手松开 | 该轨回放内容（走到音符那步有 gate，否则 0） |
| 该轨被 mute | 全部 0（静音优先） |
| 手弹 + 该步本来有音符 | 手弹内容（手弹优先） |

### 18.5 编译实测

- 单文件零警告；全量 `make plugins` 与 `make -C CardinalNative` 均 exit 0（`Creating JACK standalone`）。
- **`.o` 尺寸单调递增**（本机可复现的硬判据）：
  `390,325`（原版）→ `390,389`（+64，mute 修复）→ **`390,557`（+168，本节）**。
- exe md5 `026a8381…` → **`6c8c0db7bc54a744c91a931033ad85cd`**；对照 `.o`（Blank/Clocked）停在 09-20 未动。
- 部署：回滚点 = `CardinalNative.20260921-163750.exe`（mute 修复版）。

### 18.6 ★ 概念澄清：输出口是「控制电压」，不是「音频」

李问过：「你那个上面也有一个音频的 output 口吧，把它接到 Mixer 上行不行」——**不行**。
面板上 17 个输出口（Clock/Reset/Run/Record thru、End of song、4 轨 × V/Oct+gate+velocity）
**全部是控制电压（CV）或门（Gate）**，一个音频口都没有。正确信号路径：

```
键盘(CV/Gate) → MiniArranger(记录/输出 CV/Gate) → VCO(V/Oct→音高) → ADSR(Gate→包络) → VCA → Mixer → HostAudio2
```

**只有 VCO 之后才是音频**。把 MiniArranger 的口直接接 Mixer，只会得到直流电压/噪声。

⇒ 想同时听 4 条轨，标准接法是**每轨各一条发声链**（VCO+ADSR+VCA），再汇到一个 Mixer：
轨 1 → 链 A、轨 2 → 链 B …… 4 条链 → Mixer 4 个输入 → HostAudio2。这样的额外好处是
**每轨能用不同音色**（鼓/贝斯/琴/弦），这正是多轨音序器的意义。

### 18.7 验收清单

1. **重开 Cardinal**（新 exe 才生效），加载机架。
2. 把 **TRACK 旋钮拧到 1**，并确认 **Track 1 的 Mute 已关**。
3. **不录音，直接弹键盘** → 应当**立刻**听到声音（本节新增的行为）；松手立刻停。
4. 按 REC 再弹 → 同样立刻有声，同时音符照样被录进去。
5. 把 TRACK 拧到 2 再弹 → **听不到**（轨 2 的口还没接发声链）—— 这是接线的正常表现，不是故障。

---

## 19. 试听输出口：一条发声链听任意轨（2026-09-23 交付 · 已部署）

**背景**：§18.6 已澄清「17 个输出口全是 CV/Gate，要听 4 轨就得接 4 条发声链」。
但每条链要 VCO + ADSR + VCA 三个模块，4 轨 = 12 个模块，面板根本放不下。
2026-09-23 李选定方向：**加一对「试听输出口」**，固定输出「当前编辑轨」。

### 19.1 设计：试听口 = 编辑轨那一组的镜像

两个新口（V/Oct + gate），输出内容与 `TRACK1_*_OUTPUT + editTrack*3` **同一份值**，
**含手弹直通与静音判定**（§18 的键盘直通在试听口上同样有效）。

⇒ 效果：把**一条** VCO+ADSR+VCA 链接到试听口，**拧 TRACK 旋钮就能听主模块任意一轨**。

### 19.2 ⚠️ 端口编号必须追加在末尾（这条是铁律）

| 编号 | 含义 |
|---|---|
| 0–4 | Clock / Reset / Run / Record (thru) / End of song |
| 5–16 | 4 轨 × (V/Oct, gate, velocity) |
| **17 / 18** | **`AUDITION_VOCT_OUTPUT` / `AUDITION_GATE_OUTPUT`**（本轮新增）|

**新口一律追加在 `NUM_OUTPUTS` 之前、所有老口之后。** 插到中间会让后面所有口的编号
整体位移 ⇒ **老机架的接线全部错位**（Rack 按数字编号还原线缆，不认名字）。
本轮据此把 17/18 放在最后 ⇒ 李现有那份 `mini_arranger_expanded.vcv` 的 14 条线一条不受影响。

### 19.3 面板改动（仍是 40 HP，未变宽）

试听口放在左侧「OUT」列（x=44）的下方两格（y=91 / 104），紧跟共享输出 `END`（y=78）之后
—— 视觉上归入「共享输出」组，用**琥珀色描边**与灰蓝色的共享输出区分，标签 `AUD V` / `AUD G`
（琥珀色，同样由 `draw()` 用 nvg 画，因为 nanosvg 不渲染 `<text>`）。
面板脚本 `tmp/gen_mini_arranger_svg.py` 新增常量 `AUD_Y0 = 91.0`。

### 19.4 编译与部署实测

| 判据 | 结果 |
|---|---|
| 目标 `.o` | `MiniArranger.cpp.o` 390,557 → **391,331**（+774 字节，正是这段代码）|
| 对照 `.o` | `Blank.cpp.o` 停在 09-20 19:13、`Clocked.cpp.o` 停在 09-20 19:34（未动）|
| 同包其他 `.o` | `MiniArrangerExpander.cpp.o` / `Sketch.cpp.o` 停在 09-21 13:03（未动）|
| **字符串取证（决定性）** | 旧备份 exe 里 `AUD V` 命中 **0**；新 exe 命中 **1**（另 `Audition` ×6）|
| exe md5 | `6c8c0db7…` → **`ecb000c63b4657e6390c6b38c7e3234a`** |
| 体积 | 102,963,200 → 102,963,712（+512 字节）|
| `make plugins` | `Creating plugins.a` ✓ · `[plugins exit=0]` · `[native exit=0]` |

> ⚠️ 方法论：本轮把「exe 内新字符串命中数」当成**决定性判据**（旧 0 → 新 1），
> 因为 md5 在本项目**不可复现**（见 `cardinal-wsl2-build`）。
> `Audition V/Oct (follows current edit track)` 这类长字符串不会被 GCC 内联成 `mov`
> 立即数，所以 `grep -a` 能搜到 —— **但要拿旧 exe 做对照**，否则无法排除"本来就有"。

### 19.5 部署与回滚点

- 回滚点：`win64\CardinalNative.20260923-110349.exe`（键盘直通版，md5 `6c8c0db7…`）
- 面板 SVG 同步：`win64\resources\Starsea\res\MiniArranger.svg`（9358 字节）
- 部署脚本：`tmp/deploy_audition.py`（`.new` 暂存 → md5 校验 → `os.replace` 原子替换 → 失败自动回滚）

### 19.6 新演示机架 `patches/mini_arranger_audition.vcv`

由李那份 `mini_arranger_expanded.vcv` **派生**（**不覆盖原件**），只改两处：

1. 主模块那条发声链的源：`out5/out6` → **`out17/out18`（试听口）**
2. 主模块 4 轨 `mute`：`[True, True, False, False]` → 全 `False`
   （该机架唯一目的就是「让你听到」，静音着就失去意义）

其余**原样保留**：李的 23 / 9 / 6 / 0 个音符、扩展器那条链、时钟、键盘接线。
自检：12 模块 / 14 线不变、回读校验通过、`layout_patch.py guard` 无错误。

### 19.7 已知边界（如实记录，未美化）

- **试听口只覆盖主模块 4 轨**。扩展器的 4 轨**没有**试听口 —— 它目前靠 E1 的输出口直连
  右声道。要不要给扩展器也加一对，**待李定**（会再动一次 24 HP 面板 + 一轮编译）。
- 试听口**不输出 velocity**（只 V/Oct + gate）—— 左侧那一列只剩 2 格可用位置
  （y=117 会撞上底部散热线 y=118），第三个口放不下。

### 19.8 验收清单

1. 开新 exe，加载 **`patches/mini_arranger_audition.vcv`**（**打开前先存盘你现在的机架**）。
2. **不录音，直接弹键** → 左声道应立刻有声（试听口默认跟编辑轨 = 轨 1；该机架里 mute 已全关）。
3. **拧 TRACK 旋钮到 2 / 3** → 继续弹键或按 RUN 播放，**左声道应跟着换轨**
   —— 这就是「一条链听任意轨」生效的直接验证。
4. 拧 TRACK 到 4（空轨）→ 没声，这也是对的（轨 4 没有音符）。
