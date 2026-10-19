# 用 Cardinal 模拟真实乐器：方案与配方地图

> 2026-10-18 调研 + 整理。目的：回答「Cardinal 这种模块化合成器怎么把真实乐器做像」，
> 给出一套可落地的框架、分乐器族配方，以及 Cardinal 专属的坑。
> 结论放最前，细节在后。调研来源见末尾 §6。

---

## 0. 一句话结论

**Cardinal 不缺真实感，只是换了条路径——它靠「物理建模（physical modeling）」直接模拟
「激励源 + 共鸣体」这套物理结构，而不是录采样或硬凑波形。** 社区（VCV / Cardinal 生态）
在这条路上沉淀了非常成熟的模块与技法，而 Cardinal 恰好把最关键的几个打包进了内置模块：
**Audible Instruments（Mutable Instruments 官方移植）+ Surge XT**，再加 **Valley / Bogaudio**
做空间与混音。

真实感 = 一条完整信号链，而非单个神模块：

```
激励源(Exciter) → 共鸣体(Resonator) → 力度映射(Dynamics) → 演奏法(Articulation) → 空间(Space) → 母带(Master)
   噪声/锤/弓/呼气      模态/波导/采样       力度→亮度/衰减       连奏/颤音/滑音     箱体IR/短混响     饱和/EQ压毛刺
```

前两段造「声音本身」，后四段造「像人在演奏」。合成对音色只是 50 分，真实感全在后四段。

> **已验证**：Life1 机架（`patches/quadeca_life1_wdtg.vcv`）已经实测跑通了这个框架——
> Elements = 大提、Plaits PLUCK = 吉他、Bogaudio VCO+VCF+ADSR = 电钢，加载后有声。
> 所以下面不是理论，是已验证的方向。

---

## 1. 核心原理：所有真乐器都能拆成「激励源 + 共鸣体」

社区反复验证的一条铁律（Beat Kitchen、Avareth Taika 等）：**真实乐器的声音 =
一个激励源（exciter）撞上一个共鸣体（resonator）。** 不模仿「声音长什么样」，
而是模仿「声音是怎么被造出来的」。

| 真乐器 | 激励源 | 共鸣体 |
|---|---|---|
| 拨弦（吉他/竖琴） | 拨片 = 噪声爆冲 | 一根弦 = 延迟环 |
| 弓弦（小/大提琴） | 持续摩擦 = 持续激励 | 弦 + 琴体 |
| 管乐（长笛/单簧） | 气息/簧片 | 一根管 = 管状共鸣 |
| 鼓/镲 | 鼓槌 = 脉冲 | 膜/板 = 二维共鸣 |

Cardinal 内置的 **Audible Instruments** 正是按这个哲学设计的：Rings / Elements / Plaits /
Clouds 本质都是「可调共鸣体 + 可选激励」。这比 VCO→VCF→VCA 减法合成去硬凑音色，方向对得多。

---

## 2. 分乐器族落地配方（全部用 Cardinal 自带模块）

| 乐器族 | 首选技法 | Cardinal 内可用模块 | 关键要点 |
|---|---|---|---|
| **拨弦**（吉他/竖琴/拨奏） | Karplus-Strong / 弦模态 | **Plaits**（Extended KS 红 mode）、**Surge XT** String+Combulator、**Rings** 弦模式 | 激励=噪声爆冲，反馈里的低通决定尼龙/钢弦；拨弦位置影响谐波 |
| **弓弦**（小/大提琴/弦乐群） | 波导（双向）持续激励 | **Elements**（弓弦模式）、Rings 持续激励+弓噪、Plaits 模态 | **持续激励是命门**，单次触发做不出弓弦；必须叠弓噪 + 连奏 |
| **管乐/铜管**（长笛/单簧/小号/萨克斯） | 管模态 + 呼气噪 + 共振峰 | Rings 管模式、Plaits vowel、减法（2 失谐锯齿+VCF+ADSR）做铜管 | 共振峰 = 管乐的「嘴型」；铜管用 TrevoX 那类减法也很像 |
| **键盘**（钢琴/电钢/管风琴） | 钢琴=采样；电钢=FM；管风琴=加法 | **samplerx8**（采样）、Surge XT FM、Plaits additive/harmonic | 钢琴采样最真但静态；电钢 FM 极像 Rhodes；管风琴用谐波 drawbar |
| **打击/钟**（鼓/马林巴/钟/镲/锣） | 膜/板模态 + 金属带通 | Rings 膜/板模式、Plaits 鼓模型（kick/snare/hat）、Plaits 模态共鸣 | 马林巴/钟用模态共鸣；金属 = 反馈里加带通 |
| **人声/合唱** | 共振峰（声道建模） | Plaits vowel/speech、（Pink Trombone / Squinky Formants 若已打包）、激励+共振峰滤波器组 | 直接建模声道最像；否则用高 Q 带通滤波器组叠共振峰 |

> 关于 Karplus-Strong / 波导：Cardinal 不能装外部专用模块（见 §4），
> 但 **Plaits 自带 Extended KS 模式**、**Surge XT 有 String 振荡器 + Combulator（KS 共鸣组）**，
> 也可以自己用「噪声源 + 延迟 + 反馈低通」从零搭。足够覆盖拨弦与弓弦。

---

## 3. 真实感层（§0 后四段，决定「像不像人拉的/吹的」）

音色合成对了只是 50 分，剩下 50 分在这一层：

1. **力度映射（Dynamics）**：Velocity → 激励电平 / 亮度 / 衰减长度。轻 = 暗且短，重 = 亮且长。
   这是区分「真乐器」和「静态合成音」的最大开关。
2. **演奏法（Articulation）**：弦乐/铜管要连奏（legato）+ 滑音（portamento）；
   持续音加颤音 LFO（频率微扰）。断奏/连奏靠 gate 长度切换。
3. **空间（Space）**：别用大混响糊住。用**乐器箱体 IR 卷积**（木制乐器箱体 IR 极提味，
   VCV 社区验证过）或 **Valley Plateau** 短混响 / **Sound Stage** 3D 房间。
4. **母带（Master）**：金属建模容易在 2–6 kHz 发毛刺，用动态 EQ 压一下；
   加一档温和饱和补「箱体木头感」。

---

## 4. Cardinal 专属注意事项（别踩坑）

- **模块集是固定的**：Cardinal **不能装外部模块**，也不连官方模块商店。
  所以 Frozen Wasteland 的 String Theory、Wallenda、KSDelay、NYSTHI、Vult **都不在**。
  好消息：核心需求全在 **Audible Instruments（Mutable 全家桶）+ Surge XT + Valley + Bogaudio**，
  KS 用 Plaits / Surge 代替专用模块即可。
- **表现力靠 MPE**：MIDI-CV 模块右键把 Polyphony 设 >1、Polyphony mode 设 MPE，
  再用支持复音的 VCO/VCF/VCA（Fundamental、Bogaudio、Surge）。
  配 Roli Seaboard / LinnStrument 这类控制器，真实感质变。
- **延迟**：作 DAW 插件用 ASIO，现场演奏 <10ms；**standalone 在 Windows 上音频输入有 bug**，
  演奏建议插件形态。
- **CPU**：反馈共鸣器（Rings / Elements）吃负载，定稿后冻结 / 打印音轨。
- **微音律**：Cardinal 的调律系统弱于 Rack Pro，微分音 / 非十二平均律用 CV / scale 处理。

---

## 5. 下一步（待李拍板）

- **A｜机架模板包**：做一套「按乐器族分类的可演奏 .vcv 模板」（每个族一个，
  统一 MPE + §3 真实感层），拿来就能弹。
- **B｜单点精调**：先挑最常用的 1–2 个乐器（比如钢琴 / 弦乐）深做，给具体参数与接线。
- **C｜本表即长期查阅**：本文档已可直接当「乐器 → 模块 → 参数映射」查阅表用。

---

## 6. 调研来源（2026-10-18）

- Audible Instruments 官方说明（Mutable 移植：Rings/Elements/Plaits/Clouds）：https://vcvrack.com/AudibleInstruments
- Beat Kitchen《Physical Modeling》—— 激励源+共鸣体原理、Karplus-Strong 搭法：https://beatkitchen.io/guides/synthesist/12-physical-modeling
- Avareth Taika《Waveguide Synthesis》—— 波导/模态合成，Elements 实战：https://avarethtaika.com/2021/09/28/waveguide-synthesis/
- VCV Community：Rack 里 Objekt / Rings / Waveguide Delay 物理建模讨论：https://community.vcvrack.com/t/is-there-a-vcv-rack-equivalent-of-reasons-objekt/20070
- VCV Community：Karplus-Strong 模块与调音坑（StudioSixPlusOne KSDelay、Frozen Wasteland String Theory）：https://community.vcvrack.com/t/karplus-strong-string-synthesis/10150/2
- Mutable Instruments Plaits 手册（16 个模型含 Extended KS / 模态共鸣 / 鼓模型）：https://www.mutable-instruments.net/modules/plaits/manual
- Cardinal 官方说明（固定模块集、不能装外部模块、自带 1200+ 模块）：https://cardinal.kx.studio/about.php
- SynthAndSoftware Cardinal 评测（打包品牌含 AS/Audible/Bogaudio/Impromptu/MindMeld/ML/Stoermelder/Surge XT/Valley）：https://synthandsoftware.com/2025/02/cardinal-software-modular-synth-the-synth-and-software-review/amp
- CDM：VCV Rack 的 MPE / 复音玩法：https://cdm.link/?p=128301
- OpGuides VCV Tips（复音/MPE 接线）：https://opguides.info/music/vcv
- SonusGearFlow《Building a Modular Physical Modeling Signal Chain》（真实感链、常见错误）：https://sonusgearflow.com/sounddesign/building-a-modular-physical-modeling-signal-chain
- VCV Community：纯模块做真实人声（Formants / Pink Trombone）：https://community.vcvrack.com/t/choirs-with-realistic-human-voices/25787
- PatchStorage：TrevoX-VCV-Brass（减法做小号，Minimoog 式）：https://patchstorage.com/?p=124540
