# Cardinal 采样艺术指南

> 目标：把「现成的声音」（自己录的 / 下载的采样包 / 任何音频片段）当原材料，
> 在 Cardinal 里切碎、拉伸、循环、再合成，做出新东西。
> 模块 slug 均经本机清单 + 源码核实（2026-09-14）。未核实处标 `[待验证]`。

---

## 〇、先懂一件事：采样在 Cardinal 里 ≠ 在 DAW 里

| | 传统 DAW（如 FL / Ableton） | Cardinal（模块化） |
|---|---|---|
| 音频进轨道 | 拖一个 wav 到轨道上 | **把 wav「喂」给采样器模块** |
| 变调变速 | 右键改属性 | 用 **CV 电压**去拧采样器的 pitch / position |
| 触发播放 | 点播放键 | 用 **门信号 / 时钟 / MIDI** 触发 |
| 做效果 | 挂插件 | 效果器也是模块，**用线接出来** |

一句话：**Cardinal 里没有"音频轨道"，只有"采样器模块 + 一堆用线连起来的加工模块"。**
你手里那个音源，是"喂进模块的原料"，不是"放在轨道上的文件"。

⚠️ **本机 Cardinal 不带任何音色库**（实测：安装目录 0 个 wav，`Documents/Cardinal` 空）。
**素材必须自备。** 见文末「素材从哪来」。

---

## 一、进料：三种把声音弄进来的方式

### 路线 A · 读文件（主力，最常用）
把磁盘上的 wav 加载进采样器模块。代表：

| 模块 | 包 | 干什么 |
|---|---|---|
| `Cardinal/AudioFile` | Cardinal 原生 | **最简单的播放器**：加载一个音频文件，可循环、可被宿主同步、调音量，输出左右声道 |
| `voxglitch/samplerx8` | voxglitch | 8 个独立采样槽，每槽有音量/声像，可分别触发 |
| `voxglitch/wavbank` / `wavbankmc` | voxglitch | 加载**整个文件夹**的 wav，用 CV 选播哪个 |
| `Bidoo/POUPRE` `MAGMA` `OAI` `eDsaroS` | Bidoo | Bidoo 系采样播放器（各有特色） |
| `cf/PLAYER` / `cf/PLAY` | cf | 极简播放器 |
| `JW-Modules/WavHead` | JW-Modules | 波形头显示 + 播放 |

### 路线 B · 实时输入（现场演奏 / 外部声音直入）
`Cardinal/HostAudio2`（或 `HostAudio8`）提供**宿主音频输入口**——外部声音（麦克风、其他软件输出）从这里进 Cardinal，
再串进效果链。⚠️ 独立版能否收音取决于运行时的音频设备设置，`[待验证]`。

### 路线 C · 现场录进内存（looper / 录音机）
不读文件，直接把实时声音录进模块的缓冲区：

| 模块 | 包 | 干什么 |
|---|---|---|
| `voxglitch/GrainEngineMK2Expander` | voxglitch | **外部音频录制器**，录进 Grain Engine 的颗粒引擎 |
| `voxglitch/looper` | voxglitch | 最简循环播放器（录制后自动循环） |
| `LilacLoop/Looper` | LilacLoop | **多轨现场循环站**（像 Boss RC-505 那种） |
| `SonusModular/Campione` | SonusModular | Live Sampler（现场采样） |
| `Biset/Biset-Igc` | Biset | Recorder / buffer playground（录制 + 播放头） |
| `PdArray/Array` | PdArray | 画或录制序列/包络/音频 |

---

## 二、七大采样手法 → Cardinal 模块对照

> 这是「采样艺术」的核心菜单。每一条都是音乐史上真实用过的手法，右边是对应模块。
>
> **2026-09-14 查证后修正**：业界教材一致把 **回录 Resampling** 列为现代声音设计的第一手法，
> 原稿误把它排在第 5 位，现已提到 0 号；并补上原稿漏掉的**波表化**路线。

### 0. 回录 Resampling（★ 现代声音设计公认第一手法）
「录下来 → 加工 → 再录下来 → 再加工」的循环。每轮把上一轮的决定**固化成一个新文件**，
产出合成器实时做不到的音色。原声越简单，加工后往往越有意思；**两轮足够，三轮是上限**，
再多就糊了。
- **录**：见上面路线 C（`voxglitch/GrainEngineMK2Expander` 外部音频录制、`LilacLoop/Looper`）
- **放**：`Cardinal/AudioFile`
- **加工**：随便挂——失真 / 滤波 / 混响 / 颗粒 / 磁带（下面 1-7 条全是加工手段）
- ⚠️ 这一条是**工作方法**不是模块，但它决定了整个采样工作流的形状

### 1. 切片 Chopping（切碎重排）
把音频按节拍切成小段，重新排列——hip-hop / breakbeat / disco 切碎的老手艺。
- `voxglitch/autobreak` / `voxglitch/AutobreakStudio` —— **自动 breakbeat 切碎器**（按步长自动切片）
- `Bidoo/cANARd` —— 采样器带 **切片工具 + 瞬态检测**（自动找到鼓点位置切开）
- `Bidoo/OUAIve` —— 采样播放器带 **beat slicing 网格**
- `FehlerFabrik-Suite/Nova` —— **Cut-up Sequenced Sampler**（切碎 + 音序）

### 2. 颗粒 Granular（把声音磨成颗粒云）
把音频切成毫秒级"粒子"，再随机/有序喷涂——氛围、音景、时间冻结感。
- `AudibleInstruments/Clouds` —— **Texture Synthesizer**（Mutable Clouds 移植，颗粒经典，**可吃实时输入**）
- `voxglitch/GrainEngineMK2` —— 颗粒 wav 播放器（参数最全：窗口/位置/音高±2 八度/抖动/密度/速率）
- `voxglitch/ghosts` —— 颗粒扫描 + 循环粒
- `voxglitch/grainfx` —— **对输入音频**做颗粒效果（不读文件，吃实时信号）

### 3. 变速 / 变调 Pitch & Time
- `voxglitch/Repeater` —— 循环播放器，带 **pitch ±2 八度** + 时钟分频
- `Bidoo/HCTIP` / `Bidoo/SPORE` —— 变调器
- `ihtsyn/PitchShifter` —— 独立变调
- ⚠️ **纯"时间拉伸不改变音高"** 在模块化里通常靠颗粒实现（改颗粒 rate），没有传统 DAW 那种一键 stretch。

### 4. 循环 Looping
- `voxglitch/looper` / `voxglitch/Repeater` —— 简单循环
- `SonusModular/Luppolo` / `Luppolo3` —— 简单循环 / Loop Station
- `LilacLoop/Looper` —— 多轨循环

### 5. 再合成 / 物理建模 Resynthesis
让采样"变成另一种乐器"——用采样当激励源，喂进物理建模器共振出新音色。
- `AudibleInstruments/Rings`（显示名 Resonator）—— 弦共振器，吃短激励
- `AudibleInstruments/Elements`（Modal Synthesizer）—— 模态体
- `SurgeXTRack/SurgeXTFXResonator` —— 共振器效果
- `CosineKitty-Sapphire/TubeUnit` —— 管波导

### 6. 磁带 / 退化 Tape & Degradation
老磁带、设备损耗、抖动、饱和——制造"旧"和"脏"。
- `ChowDSP/ChowTape` + `ChowTapeComp` / `ChowTapeChew` / `ChowTapeDegrade` / `ChowTapeLoss` —— **全套磁带模拟**（被嚼坏/老化/掉磁头/压缩）
- `rackwindows/tape` —— 万用磁带味
- `PathSet/IceTray` —— **变速 + 磁带延迟 + 选择性记忆**（"演奏进去的东西它永远不会忘记你的失误"）
- `SurgeXTRack/SurgeXTFXBonsai` —— 磁带失真模型

### 7. 波表化 Wavetable（把采样变成可演奏乐器）
把一段音频（鸟叫、门响、一整个 break）当成**波表**，让振荡器在里面扫——采样于是在
"读文件"和"合成"之间搭起一座桥（资料里管这叫 *sampling as synthesis*，两者差别只在
**变形的程度**，不在类别）。
- `SurgeXTRack/SurgeXTOSCWavetable` —— 波表振荡器
- `Valley/Terrorform` —— 波表 VCO
- 做法：把音频切/导出成短片段 → 当波表加载 → 用 LFO / 包络扫位置

### 附：AI 克隆设备
- `Cardinal/AIDA-X` —— **神经网络音箱模型播放器**：加载训练好的模型，克隆真实吉他音箱 / 失真踏板 / 整条效果链（模型从 AIDA DSP 公开网盘下载）

---

## 三、最小起步 Patch（想试的时候照这个搭）

```
[Cardinal/AudioFile]                    ← 加载你的 wav，开 Looping
      │ Out L/R
      ▼
[效果链：按需挂]
   ├─ 颗粒：AudibleInstruments/Clouds
   ├─ 磁带：ChowDSP/ChowTape
   └─ 滤波：Fundamental/VCF
      │
      ▼
[Cardinal/HostAudio2]                   ← 输出到宿主 / 声卡
```

**上手顺序建议**：先只放 `AudioFile` → `HostAudio2`，确认声音能出来；
再逐个插入效果模块，每加一个听一次区别。**一次只加一样。**

---

## 四、素材从哪来

| 来源 | 说明 |
|---|---|
| **自己录** | 手机录音、麦克风、声卡 line-in —— 环境声、说话、敲打、乐器。**最有个人特色** |
| **Freesound.org** | 50 万+ 社区上传音效。⚠️ **每个声音的授权不一样**，必须逐个看 |
| **BBC Sound Effects** | 1.6 万+ 音效档案，公共领域（public domain） |
| **Internet Archive** | 公共领域 + CC 授权录音（老唱片、历史音频） |
| **ccMixter** | 可 remix 的音乐素材（CC 授权） |
| **Sample Focus / 99Sounds / Cymatics** | 厂商免费包，自有授权条款（多为免版税） |
| **自己合成** | 先用 Cardinal 合成器做个音，录下来再当采样用（"自己喂自己"） |
| **已有音频片段** | ⚠️ 见下面版权说明 |

### 版权三分法（必须记住）

| 授权 | 能商用吗 | 要署名吗 |
|---|---|---|
| **CC0**（公共领域） | ✅ 能 | ❌ 不用 —— **最省事，优先找这个** |
| **CC-BY**（署名） | ✅ 能 | ✅ 必须署名 |
| **CC-BY-NC**（署名-非商用） | ❌ 不能 | ✅ 必须 —— **别用在要发布的曲子里** |

**三条容易被忽略的事实**（都来自查证）：
1. **"改得够多就不算侵权"在法律上不存在。** 没有这条明确边界，法院一案一判；
   重度处理能降低被检测到的概率，但不免除责任。**只要还能听出原曲，就得授权。**
2. **"为练习自用"风险几乎为零**，因为没有商业损害。发布（含 YouTube 投稿）就有风险。
3. **授权是逐条而非逐站** —— 同一个 Freesound 上相邻两个声音，可能一个是 CC0、一个禁止商用。

**最实用的起步素材**：录一段**你自己的声音或环境**（走路声、敲桌子、说话），
切碎后放进切片器——采样艺术最原始也最能出效果的做法（这就是"具象音乐 musique concrète"）。

### 可直接拿来的现成 Patch

- **patchstorage.com/rack** —— VCV Rack 社区 patch 分享站，有现成的颗粒 / 切片 / 环境 patch 可下载。
  ⚠️ 加载别人的 patch 会**缺模块**（Cardinal 只收录了 VCV 的一部分，见下面「边界」）。
- **4ms MetaModule 论坛** —— 有可下载的 `.vcv`（如 Granular Scrambler）。同上，注意缺模块问题。

### 可拿来的技法教材（我翻译成参数时对照用）

| 主题 | 出处 |
|---|---|
| 采样手法总览（切片/拉伸/变调/分层/回录） | plugg-supply.net、beatkitchen.io |
| 颗粒参数怎么调（粒长/密度/散布/扫描） | modwheel.net、violetrecording.com、toneandwire.com |
| 回录（resampling）工作流 | presetdrive.com、kansamples.com |
| 采样史（具象音乐 → hip-hop → jungle） | Britannica「musique concrète」、Wikipedia「Sampling (music)」 |
| 经典 break 出处（Amen / Funky Drummer 等） | groove 类音乐史站点 |

---

## 四·附、一个必须知道的**边界**

网上（含 VCV 官方博客 CDM）推荐最多的免费颗粒采样器 **JW-Modules 的 `Grains` 和 `Buffer`**，
**Cardinal 里没有**。Cardinal 是 VCV Rack 的精选 fork，只打包了一部分模块。

- **实测结论**（2026-09-14 用 `modsearch.py` 全清单核过）：
  Cardinal 的颗粒/采样能力靠 `voxglitch`（Ghosts / GrainFx / GrainEngineMK2 / SamplerX8 /
  WavBank / Autobreak）、`AudibleInstruments/Clouds`、`ArableInstruments/Joni`、
  `ParableInstruments/Neil`、`PathSet/IceTray`、`Bidoo` 采样器群、`SonusModular/Luppolo` 来覆盖。
  **够用，但网上教程里点名 JW-Modules 的要自行换算。**
- 真需要缺的模块 → 走 `Cardinal/Ildaeil` 或 `Cardinal/Carla`（**能跑第三方 LV2/VST**）。

---

## 五、GitHub 上能拿来的东西（2026-09-14 用 `gh` 实搜）

> 搜法：`gh search repos "<宽泛词>" --limit 10 --sort stars`，四轮共试 30+ 个关键词。
> **命中率最高**：`granular sampler` / `cc0 samples` / `awesome music` / `learn synthesis` / `vcv rack`。
> **噪音最大**：`sampling techniques`（全被机器学习重采样占了）、`sampler`（撞 shell 工具）。

### A. 素材：CC0 音色库（直接解决「本机没音色库」）

| 仓库 | 是什么 | 为什么有用 |
|---|---|---|
| **`sgossner/VCSL`** ★339 | Versilian Community Sample Library，通用 **CC0** 采样库（VSCO 2 CE 的扩展） | **可商用、免署名、免版税**；有 SFZ 版本可直接下 |
| **`NeoSoundFonts/CC0-Samples-List`** | **中文**的「已验证 CC0 音色库清单」 | **最实用的一张表**：按乐器分类（钢琴/竖琴/木琴/管风琴/吉他/贝斯/弦乐…），每个乐器后标注去哪里下（Salamander / VSCO-2 CE / Karoryfer / FreePats / Iowa / Freesound…） |
| `stargatedaw/stargate-sample-pack` | 公共领域采样包 | 可随 DAW 工程分发 |
| `MeadowlarkDAW/meadowlark-factory-library` | CC0 采样 + 预设 | 同上 |

> **用法**：拿到 wav → 喂 `voxglitch/samplerx8` 或 `Cardinal/AudioFile`。
> ⚠️ **SoundFont 走不通**：Cardinal **没有 SF2 播放器**（实测 `find soundfont` / `find sf2` 均 0 命中），
> 上面那些 `.sf2` 得先转成 wav（用 FluidSynth 等）才能进 Cardinal。

### B. 教程 / 教材

| 仓库 | 是什么 |
|---|---|
| `kunstmusik/learn-synthesis` | 「学习合成方法」教学网站源码（React，可本地跑） |
| **`MikeMorenoDSP/awesome-synthesis`** | 学合成用的**开源软件精选**，按合成法分类（减法 / FM / 波表 / 模块化…） |
| **`ad-si/awesome-music-production`** | 音乐制作资源大全：DAW / 合成器 / **Sound & Sample Providers** / 数据集 / **Knowledge（文章 + 研究）** |
| `olilarkin/awesome-musicdsp` ★3007 | 音乐 DSP / 音频编程资源精选（想读懂模块原理时看） |
| `Jumentous/audio-plugins-tutorial` | Martin Finke 的经典音频插件开发系列 |
| **`iPlug3/audio-plugin-dev-skills`** | ⭐ **给 AI 用的音频插件开发技能包**（Claude Code 市场）——可参考别人怎么把音频知识写成 AI 可执行的技能 |

### C. 算法 / 代码（想懂原理、或想自己写工具时）

| 仓库 | 是什么 | 能借鉴什么 |
|---|---|---|
| **`bencodec/BBenCut`** | 把 **BBCut**（Nick Collins，SuperCollider）的 **breakbeat 切片算法**移植成 Ableton 扩展（TypeScript） | ⭐ 业界最经典的**算法化切片**思路——它的「phrase → cut procedure」正是 `Autobreak` 那类模块背后的逻辑 |
| `algorifer/cassetter` ★72 | MIDI 控制的颗粒采样器 | 颗粒引擎结构 |
| `christian-grothe/grainiac` ★60 | Rust 写的颗粒采样器 | 同上，代码干净 |
| `yannseznec/Granular-Sampler-MICA` | **教学参考用**颗粒采样器 | ⭐ 专为教学做的，最容易读懂 |
| `yannseznec/Granular-Sampler` | Pure Data 颗粒乐器补丁 | PD 侧实现，可对照 Cardinal 的 `Clouds` |
| `linuxmao-org/Frontieres` | 交互式颗粒采样器 | |
| `FluidSynth/fluidsynth` ★2488 / `SchellingB/TinySoundFont` | SF2 音源合成器（C/C++） | 想自己搭音源 / 转 sf2→wav 时用 |

### D. 一个最对口、但 Cardinal 里没有的

**`shortwavlabs/vcv-tapestry`** —— 简介原文：*"A granular microsound processor for VCV Rack
**inspired by musique concrète**"*。它就是你问的「采样艺术」在 VCV 生态里的**旗舰实现**：
录 2.9 分钟立体声、打 300 个 marker、颗粒播放重塑；另有扩展器（位压缩 + Moog 式低通）、
`Wyrd`（非线性 drone / echo）、`Korupt`（PLL 和声 + 方波 fuzz）。

**实测：Cardinal 里没有它**（`find tapestry` / `find shortwav` 均 0 命中）。
→ 想用只能装**独立版 VCV Rack**；在 Cardinal 内只能用 `Clouds` + `voxglitch` 系列逼近（见「二、手法」）。

---

## 六、已核实 / 待验证

- ✅ 已核实：模块 slug、SamplerX8 / Autobreak / GrainEngineMK2 / Looper / Repeater 的端口与参数、
  `Cardinal/AudioFile` 的端口（循环 / 宿主同步 / 音量 / 左右输出）。
- ✅ 已核实（2026-09-14 网络查证）：**Cardinal 无 JW-Modules**（网上最常被推荐的 Grains/Buffer 不在
  打包内）；颗粒/采样模块的可用清单见「四·附」；素材站授权规则见「版权三分法」。
- ✅ 已核实：本机 Cardinal **不含任何音色库文件**（安装目录与 `Documents/Cardinal` 均无 wav/wt）。
- ✅ 已核实（2026-09-14 GitHub 实搜，`gh search repos`）：**Cardinal 无 `shortwavlabs/vcv-tapestry`**、
  **无 SoundFont(SF2) 播放器**；CC0 素材库清单与教程/算法仓库见「五」。
- ⏳ 待验证：独立版（非插件）下的音频输入路径；`Bidoo` / `SonusModular` 各模块的详细端口；
  VCV Rack 的 `.vcv` patch 在 Cardinal 中的实际加载兼容度（理论上同格式，缺模块会报错）。
- ❌ 不做：stem 分离 / 频谱测量 / 降噪对齐那套重工程（用户 2026-09-14 明确否掉，采样工作流不需要）。
