# M-VAVE SMK25 键盘档案

日期：2026-09-12　来源：官网规格 + 本机 `<键盘驱动目录>` 驱动软件 + winmm 设备枚举

---

## 1. 官方规格（m-vave.com / sincoaudio.com）

| 项目 | 参数 |
|---|---|
| 型号 | M-VAVE SMK25（别名 SMK-25；官网产品页 `m-vave.com/product.html?id=smk25`） |
| **定位** | 官方归类 **Beginner's Keyboard（入门级 MIDI 控制器）**，产地中国大陆 |
| 琴键 | **25 个全尺寸力度感应键**（`OCT+` / `OCT-` 移八度，同按复位） |
| 打击垫 | **8 个 RGB 背光垫**，力度 + 触后；**按 `PAD-B` 切到第二层 Pad 9-16** |
| 旋钮 | **8 个可分配 360° 无限编码器**；**按 `KNOB-B` 切到第二层 Knob 9-16** |
| 触控条 | 弯音（Pitch Bend）+ 调制（Modulation，默认 CC1） |
| **内置演奏引擎** | **ARP 琶音器**（7 种模式 + Latch + TAP 定速）｜**SC/CH 智能音阶·和弦** |
| 按钮区 | `PLAY` `STOP` `REC` `BT` `ARP` `SC/CH` `KNOB-B` `PAD-B` |
| 连接 | **BLE MIDI / USB-B MIDI**；**`SUSTAIN` 口 = 延音踏板 + MIDI OUT 二合一（1/4"）** |
| 电池 | 2000mAh Li-ion（或 USB 总线供电）；Power 灯绿=满、红=充电 |
| 尺寸/重量 | 321 × 178 × 46 mm / 750 g |
| 价格 | 约 ¥390–432 |

**关键澄清：键盘没有内置音源。** 官方规格表与用户手册均无 sound engine 条目 ——
所有声音必须由 Cardinal / DAW / 外部音源产生。（`rom1b\*.syx` 的用途仍然无解释，见第 2 节。）

**配套软件**：MidiSuite V1.3.7（PC）｜CubeSuite（手机 App）｜Sinco Connector（Windows BLE 连接）｜
固件 `SMK25V22024_10_17`

---

## 2. 本机驱动目录 `<键盘驱动目录>`

```
<键盘驱动目录>\
  MidiSuite.exe          ← 官方编辑器（Qt5 构建）
  bin\                   ← 各型号配置文件
    SMKB.bin  (6282 B)   ← SMK 系列配置（SMK25 用）
    SSM.bin   (6282 B)   ← 同尺寸，疑为 SMK 变体
    MKB.bin   (4096 B)   ← 含 "usrdata" 字样（用户数据区）
    MMKB.bin  (109 B)
    SPB.bin   (28312 B)
    SIIB.bin  (20032 B)
    Synth.bin (294912 B)
  rom1b\                 ← 32 个 Roland 格式 SysEx 音色库
```

### 关于 `rom1b\*.syx`（值得注意）

- 每个 4104 字节，文件头 `f0 43 00 09 20 00 ... f7`
  → `f0` = SysEx 开始，**`43` = Roland 厂商 ID**，标准 Roland 音色 SysEx 结构
- 内含补丁名：`BRASS 1/2/3`、`PIANO 4/5`、`E.PIANO 2`、`PICCOLO`、`FLUTE 2`、`OBOE`…
- 命名规律：`rom1a~rom4b`（8 个 = 4 个库 × 双面）+ `vrc101a~vrc112b`（24 个 = 12 张卡 × 双面）
  → `VRC` = Virtual Roland Card，对应 Roland 的 SR-JV80 系列扩展卡编号
- **结论**：这是 **Roland JV/XP 系列的 ROM 卡音色数据**。
- ⚠️ **SMK25 官方规格里没有内置音源**，所以这批文件更可能是
  MidiSuite 作为「M-VAVE 通用编辑器」为**带音源的其它型号**（如 SMK-37 Pro/Elite）准备的资源，
  或用于把音色发送到外部 Roland 设备。**实际用途待确认，不要臆断。**

### MidiSuite 支持的型号（从 exe 字符串提取）

`SMK25`｜`SMK25Mini`｜`SMK25II`｜`SMK25V2`｜`SMK25_II`｜`SMK-37 Pro`｜`SMK-37 Elite`｜
`SMK37`｜`SMK_PAD_POCKET`

配置可导出（存在 `/Config/SMK25_EXPORT_DIR`，界面有 Export Config / Export successfully!）。

### 从 exe 里挖到的功能控件（UI 内部名）

| 字符串 | 含义 |
|---|---|
| `Knob[1]` … `Knob[8]`、`Knob1`…`Knob8` | 8 个旋钮的配置项 |
| `Fader[1]`、`Fader[%1]` | 推子/CC 值设定 |
| `Sustain Pedal On/Off`、`Sustain Pedal Mode`、`m_sbSustainCc`、`m_cbSustainType`、`m_cbSustainChan` | **踏板可设 CC 号/类型/通道** |
| `m_sbKeybedOctave` | 键盘八度可调 |
| `Chord`、`m_cbChord` | **和弦模式**（一键出和弦） |
| `Scale`、`m_cbScale` | **音阶模式**（锁定音阶） |
| `High Res. Velocity` | 高精度力度 |
| `Poly Aftertouch`、`Channel Aftertouch`、`PadAftertouch` | 触后支持（键盘 + 垫） |
| `Export Config` | 配置导出 |

→ 由 Sustain CC 可配置可推断：**8 个旋钮同样可自定义 CC 号**（这正是 MidiSuite 的核心用途）。

---

## 3. 本机 MIDI 端口 + 实测映射表（2026-09-12 实测，40 秒采集 966 条）

```
输入:  [0] SMK25        [1] MIDIIN2 (SMK25)     [2] MIDIIN3 (SMK25)
输出:  [0] Microsoft GS Wavetable Synth
       [1] SMK25        [2] MIDIOUT2 (SMK25)    [3] MIDIOUT3 (SMK25)
```

**端口去重结论（实测）**：
- `[0]` 与 `[1]` 收到的数据**逐字节完全相同（483/483 条镜像）** → 是同一份数据的两个视图
- `[2]` 第一轮 **全程 0 条**；第二轮收到 **71 条**（全部是音符 104–111 + 弯音，见 3.4 节）
  → 不是"没有数据"，而是**只在特定状态下才发**（疑似第二层控件专走此端口）
- → **监听只需要挂 `[0]`**，重复监听 `[0,1]` 会让每条消息出现两遍

### 3.1 各控件的真实 MIDI 消息（实测，权威）

| 控件 | 消息 | 通道 | 值域 | 备注 |
|---|---|---|---|---|
| **旋钮 1** | CC **20** | 10 | 0–127 | 绝对值模式 |
| **旋钮 2** | CC **21** | 10 | 0–127 | |
| **旋钮 3** | CC **22** | 10 | 0–127 | |
| **旋钮 4** | CC **23** | 10 | 0–127 | |
| **旋钮 5** | CC **24** | **1** ⚠️ | 0–127 | **通道与其它 7 个不同** |
| **旋钮 6** | CC **25** | 10 | 0–127 | |
| **旋钮 7** | CC **26** | 10 | 0–127 | |
| **旋钮 8** | CC **27** | 10 | 0–127 | |
| **琴键** | Note On/Off | **1** | 力度 1–127 | 实测 note 60/62/65/66，力度 73/72/98/55 |
| **鼓垫 1** | Note **48** | **10** | 力度 | 走通道 10 |
| **鼓垫 2** | Note **49** | **2** | 力度 | |
| **鼓垫 3** | Note **50** | **3** | 力度 | |
| **鼓垫 4** | Note **51** | **4** | 力度 | |
| **鼓垫 5** | Note **52** | **5** | 力度 | |
| **鼓垫 6** | Note **53** | **6** | 力度 | |
| **鼓垫 7** | Note **54** | **7** | 力度 | |
| **鼓垫 8** | Note **55** | **8** | 力度 | |
| **触控条（左右）** | Pitch Bend | **9** | 14 位 | |
| **触控条（上下）** | CC **1**（调制） | **9** | 0–127 平滑连续 | 实测 0→86→0 往返两次 |

**两个必须记住的坑**：

1. **鼓垫不走统一通道** —— 8 个垫各自占用 ch2~ch8 和 ch10。
   Cardinal 的 `HostMIDI` 若设 `channels: 1`，只能收到 ch1 的琴键，**鼓垫会全部丢失**。
   解法：把 `HostMIDI` 的 `inputChannel` 设为 0（= 全部通道），
   或在 MidiSuite 里把所有垫改成同一通道。
2. **旋钮 5（CC24）走 ch1，其余旋钮走 ch10** —— 出厂配置不一致。
   解法：`HostMIDIMap` 的 `channel` 设为 **0（OMNI）**，一条设置覆盖全部。
   （源码确认：`channel != 0` 时才做通道过滤）

**NOTE_OFF 力度恒为 64**（release velocity），不是随手写的数，属正常现象。

⚠️ **Cardinal 的 `HostMIDI` 模块要选对输入端口**，否则收不到数据。

---

## 3.2 MidiSuite 配置对照（2026-09-12，李提供截图）

李发来 MidiSuite 编辑器的 11 个配置页截图，已归档到 `D:\Cardinal\refs\smk25_config\`。
**核心结论：截图与实测逐项吻合，实测数据可靠**；同时补齐了实测没覆盖的两个控件。

### A. 交叉验证：配置 vs 实测

| 控件 | MidiSuite 配置 | 实测结果 | 一致 |
|---|---|---|---|
| 琴键 | Channel 1，Octave 0，Transpose 0，力度 0–127 | Note On/Off，ch1 | ✅ |
| 旋钮 1–4 | Type=CC，CC **20/21/22/23**，Channel 10 | CC20–23，ch10 | ✅ |
| 旋钮 5 | Type=CC，CC **24**，**Channel 1** ⚠️ | CC24，**ch1** | ✅ |
| 旋钮 6–8 | Type=CC，CC **25/26/27**，Channel 10 | CC25–27，ch10 | ✅ |
| 鼓垫 1–8 | Type=Note，Note **48–55**，Channel **10/2/3/4/5/6/7/8** | Note48–55，同通道 | ✅ |
| 触控条（上下） | CC **1**（Modulation Wheel MSB），Channel 9 | CC1，ch9 | ✅ |
| 触控条（左右） | Pitch Bend，Channel 9 | Pitch Bend，ch9 | ✅ |
| **踏板** | Type=Sustain，CC **64**，Channel 9 | **未实测**（李没踩） | — |

所有旋钮 Speed 均为 `Normal`，Min=0 / Max=127。

### B. 截图新增的三个事实

**1. 踏板 = ch9 / CC64（延音），踩下 127 / 松开 0**
→ 可接 Cardinal 做「音符保持」开关，或映射成任意二值参数。

**2. Transport 三个按钮 = Note 93 / 94 / 95**

| 按钮 | Note | 音名 |
|---|---|---|
| PLAY | 94 | A#6 |
| STOP | 93 | A6 |
| REC | 95 | B6 |

→ **这是天然的走带控制**：接到 `ImpromptuModular/Clocked` 的 Run / Reset 端口，
键盘上按一下就能让自走时钟启停。
⚠️ 键盘实物上这三个按钮的位置/是否需要组合键**待核实**（官网规格没提 Transport）。

**3. Keybed 可调参数**：Channel 1 ｜ Octave 0 ｜ Transpose 0 ｜ MinVel 0 ｜ MaxVel 127
- 八度与移调**在键盘端就能调**，不必进 Cardinal
- 25 键有逐键映射网格（默认 C(-1) 起的半音阶；每键 Type=OFF 表示不额外发 CC/PC）

### C. ⚠️ 重要修正：旋钮/鼓垫 9–16 **不是空槽位，是「第二层」**

**此前判断错误，官方手册推翻了它：**

> **KNOB-B**：按下可把旋钮从 Knob 1-8 切换到 **Knob 9-16**
> **PAD-B**：按下可把打击垫从 Pad 1-8 切换到 **Pad 9-16**

所以旋钮和垫都是**双层（bank）**的，合计 **16 个旋钮功能 + 16 个垫功能**。

| 第二层 | Type | 配置 |
|---|---|---|
| 旋钮 9–12 | `MCP` | Channel 1 / 2 / 3 / 4，**无 CC 字段** |
| 旋钮 13–16 | `MCP` | Channel 5 / 6 / 7 / 8，**无 CC 字段** |
| 鼓垫 9–12 | `MCP` | Note 96–99（C7–D#7） |
| 鼓垫 13–16 | `MCP` | Note 91 / 92 / 87 / 85（G6 / G#6 / D#6 / C#6） |

**`MCP` 是什么**：MidiSuite 程序内部，控件类别只有三种 —— `Knob[%1]`、`Pad[%1]`、**`MCP[%1]`**；
Transport 的 PLAY/STOP/REC 同样归在 `MCP` 档，而它发出的就是 Note 93/94/95。
→ 推断 `MCP` 是**「非 CC 类控件」的通用档**。

⚠️ **第二层旋钮实际发什么消息，尚未实测**（它没有 CC 字段）——
按 `KNOB-B` 切换后拧一下就能测出来，见第 5 节待办。

### D. 通道分散的全貌（必须在 Cardinal 端用 OMNI）

| 控件群 | 使用通道 |
|---|---|
| 琴键、旋钮 5 | ch1 |
| 旋钮 1–4、6–8 | ch10 |
| 鼓垫 1–8 | ch10 / ch2 / ch3 / ch4 / ch5 / ch6 / ch7 / ch8 |
| 触控条、踏板 | ch9 |

**总共用满了 ch1–ch10 里的 9 个通道。**
⇒ `HostMIDI.inputChannel = 0`（OMNI）+ `HostMIDIMap.channel = 0`（OMNI）
是**唯一省事的解法**；想让 Cardinal 只认一个通道，只能回 MidiSuite 逐个改（见第 6 节建议）。

---

## 3.3 键盘自身的音乐能力（重大发现：不依赖任何软件）

**这把键盘不只是控制器 —— 它自己就会生成音乐。** 两个内置引擎此前完全被我遗漏：

### ARP —— 琶音器
| 项 | 内容 |
|---|---|
| 开关 | 按 `ARP` 键 |
| 设置 | **按住 `ARP` + 按琴键**（ARP 模式下琴键变成功能选择键） |
| 7 种模式 | `Up` / `Down` / `Incl`（含首尾音） / `Excl`（不含首尾音） / `Random` / `Order`（按按下顺序） / `Repeat` |
| 速度 | `TAP` 功能定 BPM |
| **Latch** | 松手后琶音**继续跑** |

（模式名由官方手册与 `MidiSuite.exe` 内部字符串双向印证。）

### SC/CH —— 智能音阶 / 和弦
| 项 | 内容 |
|---|---|
| 开关 | 按 `SC/CH` 键；**按住 `SC/CH` + 按琴键**选具体模式 |
| Smart Scale | 把你弹的音**约束在指定音阶内**，弹不跑调 |
| Smart Chord | **按一个键 → 出一个完整和弦**（按下的键作根音） |

### 其它键盘端功能
| 组合键 | 功能 |
|---|---|
| `KNOB-B` + `PAD-B` | 编辑**力度曲线**（垫 4 种 + 琴键 4 种） |
| `BT` + `PAD-B` | 选择**键盘内部预设** |

## 3.4 第二轮实测（80 秒 / 1047 条）—— 两个大发现

2026-09-12 下午第二轮采集，数据落 `refs\midi_dump_v2.json`，分析脚本 `tools\_timeline2.py`。

### 发现一：`[2] MIDIIN3` 端口活了，而且它发的是**弯音**

上一轮 `[2]` 全程 0 条，本轮却收到 **71 条**，全部集中在 **33.2s ~ 41.3s**：

```
33.23s  Note ch1 n104 v127   →  PB ch1 (0xE0) 值 1→4     →  Note ch1 n104 v0
34.23s  Note ch1 n105 v127   →  PB ch2 (0xE1) 值 1→4     →  Note ch1 n105 v0
35.28s  Note ch1 n106 v127   →  PB ch3 (0xE2) 值 1→5     →  Note ch1 n106 v0
36.23s  Note ch1 n107 v127   →  PB ch4 (0xE3) 值 1→8     →  Note ch1 n107 v0
37.53s  Note ch1 n108 v127   →  PB ch5 (0xE4) 值 1→7     →  Note ch1 n108 v0
38.43s  Note ch1 n109 v127   →  PB ch6 (0xE5) 值 1→8     →  Note ch1 n109 v0
39.44s  Note ch1 n110 v127   →  PB ch7 (0xE6) 值 1→11    →  Note ch1 n110 v0
40.59s  Note ch1 n111 v127   →  PB ch8 (0xE7) 值 1→11    →  Note ch1 n111 v0
```

**8 组、每组间隔约 1 秒、通道严格递增 1→8** —— 与「依次拧 8 个旋钮各一下」的动作完全吻合。

**这与 3.2-C 节的配置截图对上了**：旋钮 9–16 在 MidiSuite 里的通道正是 **1/2/3/4/5/6/7/8**、
Type=`MCP`、**无 CC 字段**。

> **推断（强，但待实证）**：
> **第二层旋钮（`KNOB-B` 之后）= 用 Pitch Bend 发送，每个旋钮独占一个通道 ch1~ch8；**
> **`MCP` 就是「不走 CC、走弯音」的那一档控件类型。**
> Note 104–111 则是旋钮的「活动标记」（开始拧 → Note On 127，松手 → Note Off 0）。
>
> ✅ **该推断已由第 3.5 节的分离测试完全证实。**

⚠️ **这条推断成立的话，会直接解释本轮"零 CC"**（见发现二）。

### 发现二：本轮 80 秒 **一条 CC 都没有**

| 端口 | 0x80 OFF | 0x90 NOTE | 0xB0 CC | 0xD0 触后 | 0xE0 弯音 |
|---|---|---|---|---|---|
| dev0 | 242 | 243 | **0** | 3 | 0 |
| dev1 | 242 | 243 | **0** | 3 | 0 |
| dev2 | 0 | 16 | **0** | 0 | 55 |

对照上一轮（`midi_dump.json`）：`CC20~CC27` 正常出现、`CC1`（触控条）出现 183 次。
→ **旋钮上一轮走 CC，这一轮走弯音。差异只能来自键盘侧的模式/层切换。**

**最可能的解释**：李在这一轮里按过 `KNOB-B`（我给的测试清单里第 6 步就是它），
旋钮切到第二层，于是改走 dev2 的弯音，dev0 上自然一条 CC 都没有。

**这条必须实证**，见第 5 节的新增待办。

### 顺带确认的两件事

1. **鼓垫工作正常且带触后**：10~18s 依次收到 8 个 Note，通道分散
   （ch2 n49 / ch10 n48 / ch3 n50 / ch4 n51 / ch5 n52 / ch6 n53 / ch7 n54 / ch8 n55），
   力度 43/44/45/43/48/56/74/89（力度感应生效），并伴随 3 条 `0xD0` Channel Aftertouch。
2. **60~69s 出现密集重复音符**（n48/52/55/56/59/62，每 2 秒内重复 4~11 次）
   → 形态像**琶音**，但无法确定出自 `ARP` 还是 `SC/CH`，且与我的时间表错位，**待单独实测**。

---

## 3.5 分离测试结论（2026-09-12，决定性实证）

数据 `refs\midi_dump_v3.json`（1082 条 / 40.6 秒），分析脚本 `tools\_abtest.py`。
操作：**只拧 1 号旋钮**，分三段，段间按两次 `KNOB-B`。

| 段 | 时间 | 操作 | `[0]/[1]` 主端口 | `[2]` MIDIIN3 |
|---|---|---|---|---|
| 1 | 0–11s | 拧 1 号旋钮（**未按** `KNOB-B`） | **CC ch10 #20**，值 3→118→10 平滑扫 | 静 |
| 2 | 18–26s | 按 `KNOB-B` 后拧 1 号旋钮 | **静（0 条）** | **Note 104 + Pitch Bend ch1**，值 5→113→34 |
| 3 | 35–41s | 再按 `KNOB-B` 后拧 1 号旋钮 | **CC ch10 #20 恢复**，值 11→116→25 | 静 |

### 结论（已成定论）

1. **`KNOB-B` 是切换开关（toggle）** —— 按一次切第二层，再按一次切回（段 1 与段 3 表现一致，互为印证）。
2. **旋钮第 1 层 = CC 20–27，走 `[0]/[1]` 端口**（与首轮实测一致）。
3. **旋钮第 2 层 = Pitch Bend，走 `[2]` 端口，每个旋钮独占一个 MIDI 通道 ch1~ch8**，
   并伴随 Note **104~111** 作为「该旋钮正在被转动」的活动标记（转动期间反复 On/Off）。
   → 编号规律：**旋钮 n → Note (103+n) + 弯音通道 n**。
   本轮只拧 1 号旋钮 → 只出现 Note 104 + PB ch1；上轮拧 8 个 → 出现 Note 104–111 + PB ch1–ch8。**两轮数据完全自洽。**
4. **`MCP` 的含义确定：MidiSuite 里 Type=`MCP` = 用 Pitch Bend 发送**（而不是 CC）。

### 对 Cardinal 的三个直接影响

- ❌ **第二层旋钮无法用 `HostMIDIMap` 映射** —— 该模块只认 CC，Pitch Bend 接不住。
- ❌ 即便改用 `HostMIDI` 的弯音输出口，8 个旋钮的弯音会挤在同一路输出上**互相覆盖**，
  分不清是哪个旋钮转的（除非给每个旋钮设定不同输入通道并开 8 个 `HostMIDI`，代价过大）。
- ✅ **想用满 16 个旋钮的正解**：回 MidiSuite 把旋钮 9–16 的 Type 从 `MCP` 改成 `CC`，
  分一组新 CC 号（如 **CC28–35**），**Export Config** 存档。这样两层都发 CC，
  `HostMIDIMap` 就能映射 16 个参数（它本身不限条数）。

### 同时解开「上一轮零 CC」之谜

李当时按过 `KNOB-B`（我给的测试清单第 6 步就是它），旋钮切到第二层改走弯音，
所以 `[0]` 上一条 CC 都没有 —— **不是故障，是层切换。**

---

### 这对「AI 辅助创作」意味着什么

**"自动伴奏"这件关键的事，键盘自己就能做** —— 不一定要在 Cardinal 里搭 PianoRoll。
`ARP`（`Latch` + 7 模式）按住和弦就自动琶音；`SC/CH` 单键出和弦。

→ 所以下一步建议**先摸清 ARP**：它打开后，发给 Cardinal 的是**琶音序列**而不是原始音符，
这会直接改变 `HostMIDI → VCO/ADSR` 的听觉效果。这是验证成本很低、收益很高的一步。

---

## 4. 与 Cardinal 结合的完整链路

| 键盘部件 | → Cardinal | 需要的模块/设置 | 状态 |
|---|---|---|---|
> 以下状态对应成品机架 **`helm_full.vcv`**（20 模块 / 35 缆，已推送进 Cardinal）。

| 键盘部件 | → Cardinal | 实现方式 | 状态 |
|---|---|---|---|
| **旋钮第 1 层**（8 个） | 实时控制 8 个模块参数 | `HostMIDIMap`：**CC20–27** → VCF Cutoff/Reso、Plateau Wet/Decay、ADSR A/R、VCO PW、VCF Drive | ✅ 已接入，待肉眼验证 |
| **旋钮第 2 层**（`KNOB-B`） | ⚠️ **接不进 Cardinal 参数** | 已实证：走 **Pitch Bend / ch1~ch8 / `[2]` 端口**，`HostMIDIMap` 接不住（见 3.5） | ❌ 需改 MidiSuite 配置 |
| **鼓垫第 1 层**（8 个） | 触发鼓机 | `HostMIDIGate`：`notes=[48..55]`、`inputChannel=0` → 8 路门 → 8 个鼓 | ✅ 已接入，待测 |
| **鼓垫第 2 层**（`PAD-B`） | 触发更多音 | Note 96–99 / 91、92、87、85 | ❓ 未实测 |
| **踏板** | 延音 | `HostMIDIMap`：**CC64 → ADSR Sustain**（param2） | ⏸ **李暂无硬件**；机架侧已配好，插上即用 |
| **触控条（上下）** | 调制 | `HostMIDIMap`：**CC1 → Plateau Size**（param5） | ✅ 已接入，待测 |
| **触控条（左右）** | 弯音 | `HostMIDI.pwRange=2.0`（±2 半音），但走 ch9 被 `inputChannel=1` 过滤 | ❌ 需把 MidiSuite 通道改 ch1 |
| **Transport 键** | 走带控制（启停） | Note 93/94/95 → `Clocked` 的 Run / Reset | ❌ 未做 |
| **ARP 琶音器** | 自动琶音 | **键盘端生成**，Cardinal 只收结果 | 键盘端 |
| **SC/CH 音阶和弦** | 弹不跑调 / 单键出和弦 | **键盘端生成**，Cardinal 只收结果 | 键盘端 |
| **ARP 琶音器** | 自动琶音 | **键盘端生成**，Cardinal 只收结果 | 键盘端 |
| **SC/CH 音阶和弦** | 弹不跑调 / 单键出和弦 | **键盘端生成**，Cardinal 只收结果 | 键盘端 |

### 4.1 已实现的旋钮映射（`D:\Cardinal\patches\helm_knobs.vcv`）

`HostMIDIMap` 配置：`channel = 0`（OMNI）、`smooth = true`（指数平滑，不跳变）

| 旋钮 | CC | 目标模块 | 参数 | 作用 |
|---|---|---|---|---|
| 1 | 20 | VCF | param0 `Cutoff frequency` | 亮度 / 明暗 |
| 2 | 21 | VCF | param2 `Resonance` | 共振 / 尖锐度 |
| 3 | 22 | Plateau | param1 `Wet level` | 混响湿度 |
| 4 | 23 | Plateau | param7 `Decay` | 混响尾巴长短 |
| 5 | 24 | ADSR | param0 `Attack` | 起音快慢 |
| 6 | 25 | ADSR | param3 `Release` | 松手后余音 |
| 7 | 26 | VCO | param5 `Pulse width` | 脉宽 / 音色胖瘦 |
| 8 | 27 | VCF | param4 `Drive` | 过载 / 脏度 |

**改映射不用手改文件**：
```bash
python make_knobs.py apply <patch>            # 重写整套默认映射
python make_knobs.py set  <patch> 21 Bogaudio LFO   # 单条改
python make_knobs.py show <patch>             # 看当前映射
# 加 --load 可立即推送到运行中的 Cardinal
```

**`HostMIDIMap` 源码关键事实**（`plugins/Cardinal/src/HostMIDI-Map.cpp`）：
- `maps` 条目只有三个键：`{cc, moduleId, paramId}`；`cc` 有效范围 **0–119**
- `-1` = 未分配；`paramId` 必须小于目标模块的参数总数
- `channel = 0` 表示**接收所有通道**（OMNI）
- CC 值 `0–127` 先归一化成 `0.0–1.0`，再通过 `setScaledValue()` 写入目标参数
  → **自动适配任何参数的量程**，但也是**线性**映射
- `smooth = true` 走指数滤波（tau = 1/30 s）；值跳变幅度 ≥1.0 时仍会瞬跳

**关键价值**：`HostMIDIMap` 这条路让 **8 个物理旋钮 = 8 个可实时拧的 Cardinal 参数**，
比 OSC 更适合演奏场景（无网络延迟、手感直接）。

---

## 5. 实测进度

- [x] 键盘三个端口各自发什么 —— 已测，见第 3 节
- [x] 8 个旋钮的默认 CC 号 —— **CC20~CC27**
- [x] 鼓垫的 Note 编号分配 —— **48~55，但分散在 ch10/2/3/4/5/6/7/8**
- [x] 触控条 —— Pitch Bend + CC1，均在 ch9
- [x] **MidiSuite 配置对照** —— 李提供截图，与实测 100% 吻合（见 3.2 节）
- [x] **键盘型号与能力确认** —— 已查官网 + 官方手册，补出 ARP / SC-CH / 双层结构（见 3.3 节）
- [x] 第二轮实测（80 秒 / 1047 条）—— 见 3.4 节：dev2 端口活了、本轮零 CC
- [x] **✅ 分离测试「第一层 vs 第二层」—— 已实证，见 3.5 节**
      （第 1 层 = CC20–27 走 `[0]`；第 2 层 = 弯音 ch1~ch8 走 `[2]`；`KNOB-B` 是 toggle）
- [ ] **旋钮映射是否真的生效（等李看 GUI / 听声音确认）** —— 段 1 与段 3 期间 CC20 已确认发出
- [ ] **鼓垫第二层（`PAD-B`）实际发什么** —— Note 96–99 / 91、92、87、85 待验证
- [ ] **ARP 打开后的 MIDI 输出** —— 发给 Cardinal 的是琶音序列还是原始音符？
- [ ] **SC/CH 输出的和弦内容** —— 单键出和弦，具体是哪几个音？
- [ ] 踏板 CC64 与 Transport Note 93–95 的实测（配置已知，仍未出现）
- [ ] **可选优化：把旋钮 9–16 的 Type 从 `MCP` 改成 `CC`（CC28–35）**，让第二层也能被 `HostMIDIMap` 映射
- [ ] `rom1b\*.syx` 的实际用途
- [ ] BLE 模式下端口名是否变化

---

## 6. 可选优化：把通道统一（需在 MidiSuite 里改）

当前 9 个通道混用，Cardinal 端只能靠 OMNI 兜住。如果想更"干净"（比如以后接 DAW、
或想在 Cardinal 里按通道区分不同控件），可在 MidiSuite 里这样改：

| 改什么 | 从 | 改成 | 好处 |
|---|---|---|---|
| 旋钮 1–8 的 Channel | 10 / **1** / 10… | **统一 ch1** | 8 个旋钮一条通道，`HostMIDIMap` 也无需 OMNI |
| 鼓垫 1–8 的 Channel | 10/2/3/4/5/6/7/8 | **统一 ch10** | GM 鼓组标准通道，DAW 里最好认 |
| 保留 ch9 | 触控条 + 踏板 | 不动 | 演奏控制独立通道，便于单独映射 |

改完记得在 MidiSuite 里 **Export Config** 存一份，改名 `smk25_unified.txt` 放 `refs\`，
便于以后一键恢复。
**注意**：这只是"可选优化"。不改也能用 —— Cardinal 端 OMNI 已经覆盖全部控件。

### 验证手段的限制（重要）

Cardinal 的**实时存档 `%TEMP%\Cardinal.XXXX\patch.json` 不随参数变化重写** ——
实测：发 OSC `/param` 改参数后，文件的 mtime 和内容都不变（只在 `/load` 等时机写）。

加上 OSC **只有 4 个消息、没有读回**，所以：

> **参数值无法程序化回读。验证旋钮映射只能靠人眼看 GUI 上旋钮是否转动。**

`watch_knobs.py`（轮询实时存档）因此在参数验证上无效 —— 保留它只用于确认映射表结构。

---

## 附：相关文件

- MIDI 工具：`D:\Cardinal\tools\winmidi.py`（winmm 封装，零依赖，含监听）
- 用法：`<venv>/Scripts/python.exe winmidi.py [秒数] [端口号逗号分隔]`
