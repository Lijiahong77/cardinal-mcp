# 音色审美资源地图（Cardinal）

> 2026-09-13 调研。目的：搞清楚「音色怎么做得好听」，以及「哪里能找到参考」。
> 结论放最前，细节在后。

---

## 0. 一句话结论

**你现有的机架里就藏着一份最好的教材** —— `refs/examples/` 那 15 个官方示例，
它们和你用的是同一套模块，接线方式却比我们的讲究。先读它们，再谈找资源。

**最该先改的一件事**：混响的接法。我们现在是「整个信号串进混响」（insert），
专业做法是「只抽一部分信号送进混响」（send / return）。这是听感差异最大的一处。

> **2026-09-13 更新：已经照着上面的方向实机调完了**，参数表、接线理由、
> Plateau 全部 31 个控件的含义和两个新踩的坑，见 §6。备份在
> `patches/helm_full_before_reverb_122611.vcv`。

---

## 1. 先看你自己的机架：混响为什么「不好听」

### 1.1 事实（从 `patches/helm_full.vcv` 读出来的）

**你关掉混响前的接法**（35 缆版本，git HEAD）：

```
Sum[0] ──► Plateau 输入 0        ← 整个合成器信号送进混响
Sum[0] ──► Plateau 输入 1
Plateau 输出 0 ──► MixMasterJr 输入 0   ← 混响输出直接当主输出
Plateau 输出 1 ──► MixMasterJr 输入 1
```

**你现在的接法**（33 缆版本，混响已旁通）：

```
Sum[0] ──► MixMasterJr 输入 0
Sum[0] ──► MixMasterJr 输入 1
（Plateau 悬空，0 条线）
```

### 1.2 为什么原来那个接法容易不好听

三个原因叠在一起，不是混响模块本身的问题：

1. **100% 串联 = 干声被淹没。** 信号全部经过混响再出来，没有一路「干净的原声」托底。
   听起来就像所有音符都泡在水里 —— 这正是「糊」「不好听」的典型症状。
2. **没有低切。** 低频进混响会迅速堆积成一片雾。混音圈的共识是
   **混响返回必须做 100–200 Hz 低切**，否则低频浑浊、整个声场失去轮廓。
3. **Plateau 在纯湿信号下本来就会有声像漂移。** 这是模块作者 Dale Johnson 亲自解释过的：
   Dattorro 板式混响算法左右两路的延迟时间必须不同才能产生宽度，
   于是纯湿信号下会形成驻波、左右不对称。**解法就是保留一部分干信号**
   （利用 Haas 效应让大脑补上定位）。

> 一句话：**不是 Plateau 难听，是「全湿串联 + 无低切」这套接法难听。**

### 1.3 零风险验证（想试的话）

恢复接线后，先把 Plateau 的 **Dry 开到 0.8 / Wet 开到 0.2**（干声为主），
不动任何接线，听感立刻会不一样。这一步能证明「问题在比例，不在模块」。

---

## 2. 从 15 个官方示例里提炼的 4 种效果链接法

我把 `refs/examples/` 全部 15 个机架的接线扫了一遍，
效果器（混响 / 延迟 / Clouds / 合唱）的接法可以归成 4 类：

| 模式 | 接法 | 代表机架 | 什么时候用 |
|---|---|---|---|
| **A. 单路串联** | 音源 → 效果 → 输出 | `falkTX_-_Random-Progress-Pluck-Rev`（Plaits → Plateau → 输出） | 只有**一路**音色时。简单，但没法单独调干湿 |
| **B. 辅助发送（推荐）** | 混音台某路 → 效果 → 回到混音台另一路 | `nooneknowspeter_-_Catalyst`、`_Xmas`、`_Velour` | **多路音源时**。主干保持干净，只抽一部分进效果 |
| **C. 串联链 + VCA 控量** | 音源 → 效果1 → 效果2 → VCA → 输出 | `VT_-_Jupiter_Ascent`（Feline → Clouds → VCAmp → DualDelay） | 想做**音色设计**（效果本身是音色的一部分） |
| **D. 全家桶串联** | 一个厂商的效果模块首尾相接 | `JTB_-_Waves`、`SpotlightKid_-_Cringe-Synth`（SurgeXT Chorus → Delay → Reverb） | 用同一个厂商的效果链，音色统一 |

### 关键样本拆解：`nooneknowspeter_-_Catalyst` 的 send / return

这是最值得抄的一个。它用 `mscHack/Mix_4_0_4`（一个 4 路混音台）当总线：

```
mscHack/Mix_4_0_4[3] ──► Valley/Plateau[0]     ← 混音台第 3 路"送出"给混响
Valley/Plateau[0]    ──► mscHack/Mix_4_0_4[5]  ← 混响结果"返回"混音台第 5 路
```

**同一张混音台既当主干又当效果返回** —— 这就是硬件调音台上
「AUX SEND / RETURN」的经典玩法。`_Xmas` 和 `_Velour` 用的是同一套手法
（分别对 Plateau 和 Clouds）。

> **我们该抄的就是这个。** 你的 `MindMeldModular/MixMasterJr` 是同一类混音台，
> 理论上支持多路输入 + 效果返回。

### 另一个值得看的：`DRMR_-_Etherpad`（李可能听过这个）

这是官方宣传里那个"简单 pad 但很好听"的 demo，也是 Bonedo 评测里点名的例子。
它的结构极简，却用了一条**调制混响的 CV**：

```
Bogaudio-Matrix81[0] ──► Plateau[0]        ← 信号进混响
Bogaudio-EightFO[0]  ──► Plateau[12]       ← LFO 调制混响参数
Plateau[0]/[1]       ──► HostAudio2[0]/[1] ← 直接出
```

**启发**：让混响的参数（比如 ModSpeed / Size）被 LFO 缓慢调制，
声音会"活"起来 —— 这是静态混响和"好听"混响的差别之一。

---

## 3. 混响的 5 条硬规矩（来自混音教材，可直接背）

调研了多个混音教程后，这几条是反复出现的共识：

1. **用 send / return，不要用 insert。** 主干保持干净，用送出量控制空间感。
   多个音源共用同一个混响 = 它们处在同一个空间里，听起来更"融合"。
2. **混响返回低切 100–200 Hz。** 这是最立竿见影的一招，防止低频糊掉。
3. **加 pre-delay（预延迟）。** 让原声先出来、混响后到，声音才清晰。
   起步值：**歌曲速度下的一个十六分音符**（120 BPM ≈ 125 ms）。
4. **decay（衰减时间）跟速度匹配。** 尾巴在 1–2 拍内基本消失，
   否则上一个音还没散、下一个音就来了，越堆越糊。
5. **混响本身设 100% wet，用送出量控制多少。**
   这样"干湿比"和"总音量"是两个独立旋钮，不会互相打架。

对应到 Plateau 的参数：
`PreD`（预延迟，0–500 ms）、`Low` / `High`（输入与混响体的滤波，就是低切）、
`Size`（空间大小）、`Decay`（衰减）、`Diffusion`（扩散度）、`Dry` / `Wet`。

> 官方文档：https://valleyaudio.github.io/rack/plateau/
> 视频：Omri Cohen 有一期 Plateau 入门讲解（文档页有链接）。

---

## 4. 资源地图：去哪找

按「上手优先级」排序。

### 4.1 第一优先：本机已有的东西（不用下载）

| 资源 | 位置 | 说明 |
|---|---|---|
| **15 个官方示例机架** | `D:\Cardinal\refs\examples\` | 和官方仓库同步的全套。**最好的教材**，同模块、可直接拆 |
| 5 个官方模板 | `D:\Cardinal\refs\*.tpl.vcv` | `main` / `fx` / `mini` / `native` / `synth`，起手骨架 |
| Cardinal 官方文档 | `C:\Program Files\Cardinal-win64-26.02\docs\` | 含 OSC 远程控制等权威说明 |
| 我们自己的踩坑笔记 | `docs/DESIGN-NOTES.md` | 12+ 条实测坑，别重复踩 |

> **怎么用**：我们已经有 `tools/patchio.py` 可以把这些 `.vcv` 直接拆开看接线。
> 想学哪个机架，我随时可以 dump 出它的完整接线 + 参数值。

### 4.2 官方仓库与文档

| 资源 | 链接 | 说明 |
|---|---|---|
| Cardinal 主仓库 | https://github.com/DISTRHO/Cardinal | `patches/examples/` 就是上面那 15 个 |
| 官方 `patches/templates/` | 同上仓库 | 插件骨架模板（main / fx / synth / mini / native） |
| 官方 `patches/mini/` | 同上仓库 | 精简版模块集的示例 |
| Valley Plateau 官方文档 | https://valleyaudio.github.io/rack/plateau/ | **混响参数逐个解释**，含算法原理图 |
| ValleyRackFree 源码 | https://github.com/ValleyAudio/ValleyRackFree | 想看混响内部实现就读这个 |

### 4.3 社区 patch 库（最大的素材库）

| 资源 | 链接 | 规模 |
|---|---|---|
| **Patchstorage · Cardinal 专区** | https://patchstorage.com/platform/cardinal/ | 14 页，数百个 Cardinal 专属机架 |
| Patchstorage · VCV Rack 专区 | https://patchstorage.com/platform/vcv-rack/ | **8000+** 个机架，大部分 Cardinal 能直接开 |
| VCV 社区论坛 | https://community.vcvrack.com/ | 提问 / 找谱例 / 官方人员常驻 |
| VCV 官方 patch 库索引 | https://community.vcvrack.com/t/beginners-guide-to-vcv-rack/747 | 一篇帖子把入门资料全列了 |

> **注意**：Cardinal 内置模块集是 VCV 的子集，且**不联网装模块**。
> 下载别人的 VCV 机架时，**缺模块会打不开或丢模块** —— 遇到就打不开的那个别硬试。

几个在 patchstorage 上有名字的创作者（做 ambient / generative 的）：
`lucy_blake`（Bonedo 评测里点名的音色设计师）、`virtual-modular`（有系列教程机架）、
`indeterminacy`、`fstateaudio`。

### 4.4 教材与课程（想系统学）

**免费 · 经典**

| 资源 | 说明 |
|---|---|
| **Sound on Sound《Synth Secrets》63 篇** | 1999–2004 年连载，被大学当教材用。**有全本 PDF（约 40 MB）和 EPUB**。https://www.soundonsound.com/series/synth-secrets-sound-sound |
| VCV Rack Manual | https://vcvrack.com/manual/ 官方手册，模块逐个讲 |
| Howard Scarr《Programming Analog Synths》 | Access Virus 官方教程，公认的音色编程经典 |

**免费 · 视频**

| 资源 | 说明 |
|---|---|
| **Omri Cohen**（YouTube） | VCV 圈教程第一人。有「基础模块」和「实战接线」两个系列，从零讲到生成式。https://www.youtube.com/c/omricohen-music |
| VCV Rack Ideas | 偏音乐性机架，经常拆解自己的 patch |
| Red Means Recording「Let's Learn Eurorack」 | 从 Eurorack 硬件视角讲，概念通用 |
| 社区视频教程索引帖 | https://community.vcvrack.com/t/getting-started-with-vcv-rack-video-tutorials/11204 |

**付费 · 如果想更深**

| 资源 | 说明 |
|---|---|
| Omri Cohen 的 Gumroad 课程 | 「基础合成」+「实战接线」两套，作者自述是给初学者到进阶 |
| 书《Developing Virtual Synthesizers with VCV Rack》 | Leonardo Gabrielli，偏工程实现 |

**混音 / 审美类**（这一块决定"好不好听"，比合成技术更关键）

| 资源 | 说明 |
|---|---|
| Understanding Reverb（musictech.blog） | 混响类型与用法，讲透了 send/insert 的区别 |
| Get That Pro Sound《The Ultimate Guide to Reverb》 | 混响参数设置的完整方法论 |

---

## 5. 建议的下手顺序

按「投入产出比」排：

1. **先拆 3 个官方示例**（半天）
   `falkTX_-_Random-Progress-Pluck-Rev`（最简）、`DRMR_-_Etherpad`（pad + 调制混响）、
   `nooneknowspeter_-_Catalyst`（send/return 总线）。
   我把接线 dump 给你，你对着 GUI 看。
   → 目的：建立「别人怎么接」的直觉。

2. **修混响接法**（1 小时）
   把 `Sum → Plateau → MixMasterJr` 改成 send/return 结构 + 返回低切。
   这是立刻能听出差别的一步。

3. **抄一个 patchstorage 机架**（半天）
   挑一个你喜欢的风格，下载 → 用 Cardinal 打开 → 拆。
   遇到缺模块就换一个。
   → 目的：扩大审美样本量。

4. **读 Synth Secrets 的相关篇章**（长期）
   不必通读 63 篇。按需查：
   - 滤波器 → Part 4/5/6
   - 包络 → Part 7/8
   - 效果与延迟 → Part 60/61/62
   - 具体乐器音色 → Part 24 起（管乐 / 弦乐 / 打击乐 / 钢琴）

---

## 6. 已落地的混响设置（2026-09-13 实机调完）

> **⚠️ 本章有两轮，最新生效的是第二轮（13:29 李拍板）：Wet 0.16 / Decay 0.35 /
> Reverb high cut 6 / Mod depth 0.3 —— 见 6.1b。下面的 6.1 是第一轮记录，数值已不是现状。**

### 6.1b 第二轮：改成「短、暗、少」（2026-09-13 13:29）

李的反馈原话：「绝大部分流行歌曲不会加这么大的混响，我平常听到的歌里几乎没有这么空大的混响」。

**结论：他的耳朵对，但这是「不要大混响」而不是「不要混响」。** 流行歌的混响一点不少，
只是清一色用**短尾巴**（房间/板式，0.3~1s）做厚度 —— 「听不出尾巴」≠「没有混响」。

| Plateau 控件 | 参数# | 第一轮 | **现在生效** | 为什么 |
|---|---|---|---|---|
| Wet level | 1 | 0.32 | **0.16** | 少 —— 湿度砍半 |
| Decay | 7 | 0.62 | **0.35** | 短 —— 尾巴约 2.5s → 约 0.7s |
| Reverb high cut | 8 | 10 | **6** | **暗** —— 这是「空」的主因 |
| Modulation depth | 12 | 1.0 | **0.3** | 亮 + 晃 = 又空又飘，先把晃动压下去 |

Size 0.55 / Diffusion 9.0 / Pre-delay 0.025 / Dry 1.0 **未动**。

> **为什么「暗」比「少」更关键**：录音混缩里的混响几乎都要切掉高频，尾巴变暗才能退到干声
> **后面**；亮尾巴会跟干声抢位置，听起来又空又吵。原来 `Reverb high cut = 10` = 完全不过滤。
> 注意这里的 6 / 10 是**真值**，不是 0~1 旋钮位置（`.vcv` 里存的是真实值）。

**执行与验证**：备份 → `patchio` 改文件（保持 tar+zstd 原生格式）→ OSC `/load` → 回 `["load","ok"]`
→ **回读实时存档逐项核对，4 个值全部一致**，模块 20 / 线缆 35 未被破坏。

> ⚠️ **`/load` 是整机替换** —— 李试拧的 VCF Cutoff 因此回到文件里的 0.5（中间值）。
> 记住：**整机推送 = 放弃所有「只在内存里」的手动改动。**

### 6.1 第一轮记录（改前 → 改后）

| Plateau 控件 | 参数# | 改前 | 改后 | 依据 |
|---|---|---|---|---|
| Dry level | 0 | 1.0 | **1.0** | 干声一点不动（DRMR 两个示例都是 1.0） |
| Wet level | 1 | 0.5 | **0.32** | 听得出空间感但不淹。falkTX 只给 0.106（太干），Catalyst 给 0.5（那是纯湿发送） |
| Pre-delay | 2 | 0 | **0.025** | 25 ms。保住起音清晰度，同时把空间推到后面 |
| Input low cut | 3 | 10 | 10 | 不动（见 6.3 的坑） |
| Input high cut | 4 | 10 | 10 | 不动 |
| **Size** | 5 | 0.75 | **0.55** | 内部尺度 2.25 → 1.22。官方示例全在 0.48~0.61，我们原来比最长的还大一半 |
| Diffusion | 6 | 10 | **9.0** | 官方：无扩散会听到离散回声。留一点余量 |
| **Decay** | 7 | 0.8 | **0.62** | 衰减系数 0.96 → 0.856。官方示例在 0.48~0.59 |
| Reverb high cut | 8 | 10 | 10 | 不动 |
| Reverb low cut | 9 | 10 | 10 | 不动 |
| Modulation rate | 10 | 0.15 | **0.30** | Etherpad 用 0.329。内部速率约 3.2 → 9.9 |
| Modulation shape | 11 | 0.5 | 0.5 | 默认 |
| Modulation depth | 12 | 0.5 | **1.0** | 默认 0.5（满量程 16）太浅；给一点运动会压掉金属振铃 |
| **Diffuse input** | 30 | **关** | **开** | 官方原话：旁通这一级会让输入变「尖锐」。所有示例都是开 |

一句话概括：**瘦身**。原来那条混响同时踩了「太大（Size 0.75）」「太长（Decay 0.8）」「太湿（Wet 0.5）」「输入太尖锐（Diffuse input 关）」四个坑，叠起来就是一片糊。

### 6.2 接线：还是 inline，但理由和之前不同

先用 `Sum[0] → Plateau[0]/[1]`，再从 `Plateau[0]/[1] → MixMasterJr[0]/[1]` 回混音台第 1 路。
两个口就是原来用的那两个，**没有猜任何新端口**。

为什么没做 Catalyst 那种 AUX 发送？因为 `MixMasterJr` 的 AUX 口需要另装 `AuxSpanderJr` 扩展模块（我们机架里没有），
而它自带的 2 条 GROUP 总线的端口顺序我没能从源码里确认（端口在别的头文件里）。
「不确定端口就不动它」—— 这是本项目的铁律。

代价与好处：

- **只有合成器有混响，鼓保持干爽紧凑**。对「键盘现场弹 + 打鼓」这套玩法，这个分工通常是对的。
- Dry 保持 1.0，所以合成器的原声一点没损失，混响是**加在上面**而不是替换。

> 如果之后想让**鼓也带一点混响**，那才需要真发送。到时候我去把 `MixMasterJr` 的端口表查实，再做。

### 6.3 Plateau 的坑（这次新发现的）

**坑 A：四个滤波旋钮被 `+5` 偏移压扁了。**
源码 `Plateau::getParameters()` 里，输入/混响的低切高切都是
`damp += params[...].getValue() + 5.f;` 然后再 `clamp(0, 10)`。
等于把整个旋钮行程挤进很窄的一小段。5 个官方示例里 4 个都把这四个旋钮留在出厂值 10 没动过。
**所以：没有试听之前不要碰它们。** 真要调，一次降 1，从 10 → 9 开始试。

**坑 B：`Diffuse input` 存了两份。**
它既在 `params[30]`，又单独存在模块的 `data.diffuseInput` 里。
只改 `params` 的话，面板上的灯可能不跟着变 —— 两边都要写。
（同理还有 `Tuned mode` 对应 `data.tuned`、`Hold toggle` 对应 `data.freezeToggle`。）

### 6.4 怎么微调（一次只动一个，动完听 10 秒）

下面箭头的**起点是现在生效的值**（见 6.1b）。

| 你的感受 | 动这个 |
|---|---|
| 太湿 / 糊 | Wet 0.16 → 0.10 |
| 太干、听不出混响 | Wet 0.16 → 0.26（**别超过 0.30**，超过就回到「大混响」） |
| 尾巴太长、盖住下一个音 | Decay 0.35 → 0.28 |
| 想要更大更宽 | Size 0.55 → 0.65（**别超过 0.70**，示例最大 0.606） |
| 太亮 / 刺 | Reverb high cut 6 → 5 → 4（一次一步；**调回 10 就又变「空」**） |
| 低频发浑 | Reverb low cut 10 → 9 → 8 |
| 想更「飘」一点 | Mod rate 0.30 → 0.45 |

### 6.5 怎么回退

两份备份，按时间倒序：

| 备份文件 | 回到哪个状态 |
|---|---|
| `patches/helm_full_before_shortverb_09131329.vcv` | **第二轮之前** —— 即第一轮那版「大混响」 |
| `patches/helm_full_before_reverb_122611.vcv` | 第一轮之前 —— 最原始的混响 |

回退就是把它 `/load` 进去，或者直接用它覆盖 `helm_full.vcv`。

### 6.6 ⚠️ 已作废的旧结论：曾以为「8 个旋钮没接上」

**这段推断是错的，2026-09-13 已实证推翻，保留在此只为防止重复犯错。**

当时的错误推理：看到 `HostMIDIMap` 在机架里「0 条缆」，就断定它的映射没生效、
8 个物理旋钮不影响任何声音。

**真相**：`HostMIDIMap` **一个端口都没有** —— 源码里 `NUM_INPUTS` / `NUM_OUTPUTS` 都是空枚举，
官方面板图上也确实没有插孔，所以它**永远不需要接线**。它读的是 Cardinal **实例级**的 MIDI 事件流，
直接写目标参数。在机架里看到它 0 条缆是**设计如此**，不是故障。

**实证**：李拧 1 号旋钮「有反应的」⇒ `CC20 → VCF Cutoff` 链路确认打通；
表里 10 条映射（CC20–27 给 8 个旋钮、CC1 触控条、CC64 踏板）**全部有效**。
逐条对照见 `docs/SMK25-midi-map.md` §4.2。

> **教训：「0 条缆 = 没工作」这个推论不成立。**
> Cardinal 的 `HostMIDIMap` / `HostParametersMap` 属于「**无端口、纯参数写入**」型模块。
> 判断一个模块有没有生效，要看源码里它靠什么拿数据，**不能只看缆数**。

> 另：当时顺手列出的 Plateau CV 输入顺序（Left=0 … Clear=16）本身没错，
> 但**用它去接 `HostMIDIMap` 输出是走不通的 —— 因为它根本没有输出口**。这张表只在
> 「从别的模块（如 LFO / 包络）手接 CC/CV 进 Plateau」时才有用。

---

## 附：本次调研的来源

- Bonedo 评测（点名了 `DRMR_-_Etherpad` 和设计师 Lucy Blake）：
  https://www.bonedo.de?p=1733124/
- Valley Plateau 官方文档：https://valleyaudio.github.io/rack/plateau/
- Plateau 声像问题作者答疑：
  https://community.vcvrack.com/t/valley-plateau-balance-issues/1349/6
- Synth Secrets 全 63 篇目录：https://www.soundonsound.com/series/synth-secrets-sound-sound
- Synth Secrets 全本 PDF（第三方整理）：
  https://sonicbloom.net/?p=12696
- Omri Cohen 官方介绍：https://vcvrack.com/news/Featured-Artist-Omri-Cohen
- Patchstorage Cardinal 专区：https://patchstorage.com/platform/cardinal/
- 混响用法（send vs insert）：
  https://musictech.blog/understanding-reverb-how-it-works-and-how-to-use-it-in-a-mix/
- 混响操作步骤（电子音乐）：
  https://sonusgearflow.com/musicproduction/reverb-for-electronic-music-production
