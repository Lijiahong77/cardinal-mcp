# 歌 / 音色 → Patch 复刻工作流

> 2026-09-14 修订。核心路线：**你说元素 → 我搜配方教程 → 翻译成 Cardinal 接线 → 你听**。
> 相关技能：`cardinal-patch-authoring`。选型工具：`D:\Cardinal\tools\modsearch.py`。

---

## 一句话流程

**你给我「哪首歌的哪个元素」（或干脆一句描述）→ 我搜教程/选模块 → 出方案 → 推给 Cardinal → 你听。**

你只需做两件事：**开个头，最后听一下**。

---

## 一、你需要给我什么

**必需：一句话。**

- ✅ 「《XXX》1:20 那个低音」
- ✅ 「像古筝的声音，但要更亮」
- ✅ 「老式电钢琴，带颤音」
- ❌ 「复刻这首歌」（范围太大，先锁定一个元素）

**可选但有用的：**

| 材料 | 价值 |
|---|---|
| 教程链接 | ⭐⭐⭐ 我直接读，省去我搜的时间 |
| 音频文件（WAV/FLAC） | ⭐⭐ 我可以对比"像不像"，但拿不到参数 |
| 时间戳 | ⭐⭐ 锁定片段 |
| MIDI 文件 | ⭐⭐ 跳过扒谱环节 |

> **不要给我纯流媒体链接**——有损压缩，而且我拿不到文件本体。

---

## 二、你该去网上搜什么

**关键词公式：`<歌名> + <元素> + <怎么做> + <合成器名>`**

**优先英文搜**——音色教学几乎全是英文做的，命中率高得多。

| 搜索式 | 例子 |
|---|---|
| `how to make <歌名> <元素>` | `how to make daft punk bass` |
| `<歌名> <元素> synth tutorial` | |
| `<歌名> <元素> remake` / `recreation` | 整首重做 + 逐步讲解 |
| `<元素> serum tutorial` | 不指定歌，只要那种音色 |
| `<风格> <元素> sound design` | `neurofunk bass sound design` |
| `<乐器> synth patch tutorial` | `koto synth patch tutorial`（**真实乐器也能这么搜**） |

**两个词表（拼进搜索式）：**

- **元素**：`lead` / `bass` / `sub` / `pad` / `pluck` / `arp` / `stab` / `chord` / `drone` / `riser` / `bell` / `keys` / `brass` / `flute`
- **合成器**：`Serum` / `Vital` / `Massive` / `Sylenth1` / `Pigments` / `Phase Plant`（Serum 教程最多、参数最规范，最好映射）

**资料有用程度排序：**

| 排序 | 类型 | 我能拿到多少 |
|---|---|---|
| ⭐⭐⭐ | **带数字的文字教程**（"cutoff 400Hz、共振 30%"） | 全部，直接映射 |
| ⭐⭐⭐ | **带参数截图的文章/论坛帖** | 我能读图 |
| ⭐⭐ | **现成预设文件**（`.fxp`） | 能读参数 |
| ⭐ | **视频教程** | ⚠️ 只能拿到标题/简介，**拿不到画面和声音**——需要你顺手记下关键参数 |
| ⭐ | 只说"我喜欢那个音色" | 我全靠自己搜，命中率低 |

**一句话：能给我"文字 + 数字"的就是好资料。**

---

## 三、我怎么选模块

Cardinal 本机装了 **1422 个模块**（85 个插件包）。选型不靠印象，靠一张**可查询的索引**。

### 工具

```bash
PY="<USERPROFILE>/.workbuddy/binaries/python/envs/music-ai/Scripts/python.exe"
cd /d/Cardinal/tools

python modsearch.py routes              # 音色 → 模块 速查表（带 ✓ 校验）
python modsearch.py find 古筝            # 关键词搜索（中文口语词也行）
python modsearch.py tag "Physical modeling"
python modsearch.py pkg AudibleInstruments
```

索引缓存在 `params/module_index.json`。**Cardinal 升级后跑一次 `modsearch.py index` 重建。**

### 六条路线（按"这个音色是怎么发出来的"分）

| 路线 | 什么时候用 | 代表模块 |
|---|---|---|
| **① 物理建模** | 真实乐器的**共鸣体**（弦、管、木、金属） | `AudibleInstruments/Rings`（弦）、`Elements`（模态体）、`Sapphire/TubeUnit`（管） |
| **② 宏振荡器** | 快速试出"像不像"——一个模块内含几十种乐器模型 | `AudibleInstruments/Plaits`、`Braids` |
| **③ FM / 加法** | 电钢、钟、金属敲击、管风琴 | `Bogaudio-FMOp`、`Bogaudio-Additator`、`Valley/Dexter` |
| **④ 波表 / 减法** | 电子音色主体（lead / bass / pad / supersaw） | `SurgeXT Wavetable VCO`、`Fundamental VCO`、`SurgeXT UnisonHelper` |
| **⑤ 采样** | 有现成 `.wav` 时最直接 | `voxglitch/samplerx8`、`wavbank` ⚠️ 需你提供文件 |
| **⑥ 特殊武器** | 内置模块搞不定的 | `Cardinal/AIDA-X`（神经网络音箱模型）、`Carla` / `Ildaeil`（**能跑第三方 LV2/VST 插件**） |

### 速查表（完整版用 `modsearch.py routes` 看）

| 你要的音色 | 首选 | 备选 |
|---|---|---|
| 快速试十几种真实乐器 | `Plaits`（宏振荡器 2） | `Braids` |
| 拨弦 / 吉他 / 钢琴 / 古筝 | `Rings`（显示名 Resonator） | `SurgeXT String VCO` |
| 拨弦打击的塑形（音头+衰减） | `Bogaudio-LPG` | `Fundamental ADSR` |
| 马林巴 / 钟 / 木鱼 | `Elements`（Modal Synthesizer） | `Sapphire/Elastika` |
| 长笛 / 萨克斯（吹奏感） | `Sapphire/TubeUnit` | `SurgeXT String VCO` |
| 管风琴（加法堆叠） | `Bogaudio-Additator` | `Befaco/Octaves` |
| 电钢琴 / 钟琴（FM） | `Bogaudio-FMOp` | `Valley/Dexter` |
| 人声 / 元音 | `PinkTrombone` | `SurgeXT Vocoder` |
| 经典减法 lead/bass/pad | `Fundamental VCO` | `Autinn/Saw2` |
| 波表（Serum 类） | `SurgeXT Wavetable VCO` | `Valley/Terrorform` |
| 失谐堆叠 / supersaw | `SurgeXT UnisonHelper` | `Bogaudio-Unison` |
| FM 贝斯 / neuro | `SurgeXT FM2 VCO` | `Venom/XM-OP` |
| 鼓 / 打击垫 | `WSTD-Drums/BassDrum9` | `voxglitch/autobreak` |
| 颗粒 / 氛围 | `AudibleInstruments/Clouds`（**不需要外部文件**） | `voxglitch/ghosts` |
| 吉他音箱 / 失真链 | `Cardinal/AIDA-X`（神经模型） | `SurgeXT Distortion` |
| 兜底：第三方插件 | `Cardinal/Carla` | `Ildaeil` |

> ⚠️ **本机 Cardinal 不带任何音色库文件**（实测：安装目录 0 个 wav/wt/fxp）。
> 所以走采样路线必须你自备素材；走 ①②③④ 路线则完全不需要文件。

---

## 四、我给你的验收单

每次推给 Cardinal 之后，我会附一张**验收单**，长这样：

```
【验收单 · <元素名>】
■ 这次做的是什么
   一句话说明我按哪个配方做的、改了什么。

■ 请重点听
   1–2 个具体听感点（比如"尾巴是不是太长""低音糊不糊"）。

■ 可调参数（在 Cardinal 界面上能直接搜到）
   ① <模块名> · <旋钮名> = 当前值
        调大 → 效果 A
        调小 → 效果 B
   ② ...

■ 想更 ___ 就动 ①；想更 ___ 就动 ②
■ 回退：<备份文件名>.vcv
```

**要点：**
- 参数用**你在界面上能看到的模块名 + 旋钮名**，不写内部 id
- 每个参数只说**一个方向上的听感变化**，不说废话
- 一定给**回退文件名**

**示例（真实施工里的样子）：**

```
【验收单 · 失谐低音】
■ 按 Reese Bass 配方搭的：两个锯齿波 ±30 音分 + 低八度正弦 sub + 24dB 低通。
■ 请重点听：① 低频是否够厚不糊；② 失谐的"晃动感"够不够。

■ 可调参数
   ① VCO 2 · Freq = +0.025 八度
        调大 → 失谐更宽、晃动更明显（太大会变"跑调"）
        调小 → 更干净、更接近单音
   ② VCF · FREQ = 400Hz 档
        调大 → 更亮更开
        调小 → 更闷更暗
   ③ VCF · RES = 0.30
        调大 → 共振峰更突出（超过 0.5 会自激尖叫）
        调小 → 更平滑

■ 想要更"脏"就动 ② 往上 + 加一点 SurgeXT Distortion；
   想要更"干净低沉"就动 ① 往下。
■ 回退：helm_full_before_reese_0914.vcv
```

---

## 五、我怎么做（执行步骤）

1. **搜配方** —— 用第二节的关键词搜，挑 2–3 篇交叉比对（不同教程参数常有出入，取共识）
2. **选模块** —— `modsearch.py routes` / `find` 定起点（第三节）
3. **翻译** —— 教程的合成器 → Cardinal 模块（附录 A），数值换算成 Cardinal 单位
4. **过门禁** —— `layout_patch.py guard` 检查接线与排班
5. **推送** —— `.vcv` → OSC `/load` → 你立刻能弹
6. **给你验收单** —— 附可调参数（第四节）
7. **你听 → 说感受 → 我改** —— 循环到你说"就这个"

---

## 附录 A：合成器 → Cardinal 映射表

| 教程里说的（Serum / Vital 等） | Cardinal 对应 |
|---|---|
| OSC A / OSC B（波形选择） | `Fundamental VCO`；波表用 `SurgeXT Wavetable VCO` |
| **Detune / Unison / Voices（失谐、齐奏）** | **`SurgeXT UnisonHelper`**（一个模块搞定）或 `Bogaudio-Unison`；手搭就是多个 VCO + 微偏移 |
| Sub Oscillator | 再来一个 VCO，降一个八度 |
| Noise Oscillator | `Fundamental Noise` |
| Sub / Noise 的 Direct Out（不进 FX） | 单独接线直连混音台，绕开效果链 |
| Filter（LP12/LP24/BP/HP + Cutoff + Resonance） | `Fundamental VCF`（`in0`=FREQ / `in1`=RES / `in2`=DRIVE / `in3`=音频）或 `Bogaudio-VCF` |
| Low-pass Gate（Buchla 式打击感） | `Bogaudio-LPG` |
| Env 1 / 2 / 3（ADSR） | `Fundamental ADSR` |
| LFO（波形 + 速率 + 深度） | `Fundamental LFO` → 接目标模块的 CV 输入 |
| **Modulation Matrix** | ⚠️ Cardinal 里"矩阵"**就是接线本身**——一根线 = 一条调制路由（例外：Surge 有独立的 `SurgeXTModMatrix` 模块） |
| Wavetable Position / Morph | 波表模块的 position 输入 + LFO/ENV |
| FX: Chorus / Hyper / Dimension | `SurgeXT FXChorus` |
| FX: Reverb | `Plateau` 或 `SurgeXT FXReverb2` |
| FX: Distortion / Saturation | `SurgeXT FXDistortion`、`ChowDSP ChowTape` |
| FX: Phaser / Flanger | `SurgeXT FXPhaser` / `FXFlanger` |
| FX: Delay / Ping-Pong | `SurgeXT Delay` |
| FX: Resonator / Combulator | `SurgeXT FXResonator` / `FXCombulator` |
| FX: Vocoder | `SurgeXT FXVocoder`、`Bogaudio-PEQ14` |
| FX: Amp / Cab / 整条吉他链 | **`Cardinal/AIDA-X`**（神经网络模型，比参数堆叠真实得多） |
| EQ（含 Post EQ） | `SurgeXT EQ`、`MindMeldModular EqMaster` |
| Compressor | `Bogaudio-Pressor`、`Bogaudio-Lmtr` |
| Mono Legato / Glide / Portamento | pitch 输入 + slew（`Bogaudio-Slew`） |
| Stereo Width | 立体声 VCA 双路增益差，或 Mid/Side 处理 |
| Arpeggiator | `Bogaudio-Arp` |
| 琶音 / 音序 | `ImpromptuModular/Clocked` + `Bogaudio-AddrSeq` |

> 映射是"**功能等价**"，不是"逐参数同构"。教程里的 Serum 滤波器型号（如 "Diode Ladder"）
> 未必和 Cardinal 的 VCF 曲线一样——**这种差异最终靠你耳朵定**。

---

## 附录 B：一个真实例子（Reese Bass 教程）

| 教程说的 | 我翻成 |
|---|---|
| OSC A/B 锯齿，A −30 cents，B +30 cents | 两个 `VCO`，Freq ∓0.025 八度 |
| Sub 正弦低一 octave | 第三个 `VCO`（正弦），Freq −1.0 八度 |
| Lowpass 24dB，cutoff 400Hz，共振 30% | `VCF`，`p0(FREQ)` 按 400Hz 换算，`p2(RES)`=0.3 |
| ENV 1 → pitch +7 半音 | `ADSR` → `VCO in1(FM)`，深度 0.583 八度 |
| LFO 0.25Hz 正弦 → cutoff，深度 150Hz | `LFO` 周期 4 秒 → `VCF in0(FREQ)` |
| Chorus rate 0.12Hz/depth 10%/mix 20% | `SurgeXT FXChorus` |
| Tube Distortion Drive 100% | `SurgeXT FXDistortion` |

**换算规律（通用）：**
- **cents（音分）→ 八度**：`八度 = cents ÷ 100 ÷ 12`
- **半音 → 八度**：`八度 = 半音 ÷ 12`
- **LFO 速率 Hz → 周期**：`秒 = 1 ÷ Hz`
- **百分比 → 0–1**：30% → 0.3
- **Hz 的 cutoff → Cardinal VCF 参数**：查 `paramlib.py` 的映射表

---

## 附录 C：背景结论（查证过，压缩保留）

- **全自动「音频 → 参数」不成立**：学术界叫 Synthesizer Inversion，只做到单合成器，
  且有泛化鸿沟（随机预设训练的模型遇人类预设准确率掉 85%+）、参数一对多无唯一解。
  → 所以"教程"路线（已给参数）远优于"音频分析"路线（要从声音反推）。
- 音频分析工具（Demucs / Basic Pitch / librosa）**未安装，本流程不需要**。
- 参考链接：
  - Serum 教程示例：https://www.presetdrive.com/how-to-make-reese-bass-in-serum/
  - 合成器逆向研究：https://www.emergentmind.com/topics/automatic-synthesizer-programming-asp
  - AIDA-X 模型下载：https://drive.google.com/drive/folders/18MwNhuo9fjK8hlne6SAdhpGtL4bWsVz-
