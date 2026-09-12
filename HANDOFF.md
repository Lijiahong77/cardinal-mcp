# HANDOFF · Cardinal 音乐工具链（交接简报）

> 用途：上下文压缩后的续接入口。**新会话先读这份，再按需展开下面列的文件。**
> 想通读「整套东西是怎么搭起来的」→ 看 **`TECH_ARCHIVE.md`**（技术档案：24 个工具 / 12 个坑 / 全部文件总表）
> 最后更新：2026-09-12 15:52（**新增 `TECH_ARCHIVE.md` 技术档案**；OSC 打通 + `helm_full.vcv` 压成两行 +
> `zoom=0.75`；三个卡点全部解决）

---

## 0.0 当前状态快照（2026-09-12 15:45）★ 最优先读这段

**可用状态**：`helm_full.vcv` **两行布局**，Cardinal 里显示正常（**已截图确认**），
**8 个鼓垫实测全部有声**（前几轮「鼓垫无声」的修复**确认成功**）。旋钮、触控条早前也已实测生效。

**OSC 已打通（李已开启）——这是本阶段最大的能力升级**：
`/hello` 与 `/load` 均**实测可用**（`load` 回 `["load","ok"]`），我可以**直接推送机架 + 截图复验**，
不再依赖「关掉 Cardinal 改文件」或「让李手动 File → Open」。
⚠️ 两个注意：① OSC 开关**每次启动 Cardinal 都要重新点**（`Engine → Enable OSC remote control`），
`native.json` 里**没有**这个字段（无法程序化开启）；② 验证方法：`netstat -ano | findstr <Cardinal PID>`
应看到 `UDP 0.0.0.0:2228`。

**布局现状**（文件与 Cardinal 内存**完全一致**，20 模块 / 35 缆，**输入口双接 = 0**）：

| 行 | 内容 |
|---|---|
| 行 0 | HostMIDI(HELMKEYS) · VCO · VCF · ADSR · VCA-1 · Sum · Plateau · HostMIDIMap · HostMIDIGate · HostAudio2 |
| 行 1 | TextEditor 说明牌 · BD-9 · Snare-N · HHat · OpenHHat · Tomi · DMX · Mixer×2 · MixMasterJr |

`zoom = 0.75`，`gridOffset = [-5.8, -0.76]`。
**这两个字段也会被 `/load` 应用**（实测：改文件 → 推送 → 视图立刻变）→ 视图完全可控。
标定结果：`gridOffset` 增大 → 内容左上移；`zoom=0.75` 时 1 格 ≈ 21 物理px。

**三个卡点——全部已解决：**

1. ~~Cardinal 运行时会覆盖 `.vcv`~~ → 改走 OSC `/load` 推送，不再依赖改盘。
   （根因仍在：李一按 Ctrl+S 就把内存写回文件。所以**文件是唯一权威源**，改完必须推一次。）
2. ~~OSC 未开~~ → **已开**，`/hello` + `/load` 实测通过。
3. ~~`pos[1]` 单位存疑~~ → **已确认是「行号」**（合法值 `0 / 1 / 2`），不是「格」。
   实测：写 `y=0/1` 推送后两行正常分开显示，**无重叠风险**。
   （官方 20 个模板/示例的 y 值也全落在 -1~2 之间，交叉印证。）

**下一步候选**（等李选，别自作主张）：

- **A. 自动伴奏机架**：琶音器 / 音序器（`Clocked` + `SEQ3`），让键盘能自动伴奏
- **B. 音色 / 鼓声打磨**：换 VCO 波形组合、鼓采样细化
- **C. Transport 走带键**：SMK25 的播放/停止键接进 Cardinal
- **D. LMMS 录音闭环**：李说过「不着急」


---

## 0. 一句话现状

作者要在 Cardinal 模块化合成器里「用 MIDI 键盘弹 + 打鼓 + 调音」，并让 AI 能遥控它。
**Cardinal 这一半已全线打通**（机架能响、MCP 能遥控、参数字典和音乐库已建）。
LMMS 那一半（DAW 录音）李明确说「不着急」。

上次会话最后一句待办：李说「**我还有一个东西给你看**」——**已于 2026-09-12 16:40 确认：那就是 M-VAVE SMK25 的驱动软件 MidiSuite**。
此前已从 MidiSuite 的 11 张配置截图（Keybed / Knob1-16 / Pad1-16 / Strips&Pedal / Transport）完整分析出键盘的 MIDI 行为，
结论已写入 `docs/SMK25-midi-map.md`（双层的旋钮/鼓垫、通道分布、ARP/SC-CH 等）。该「待办」闭环。

---

## 1. 路径地图

| 路径 | 作用 |
|---|---|
| `D:\Cardinal\TECH_ARCHIVE.md` | **技术档案**（2026-09-12 新增）：整套工作流的完整解释——五个障碍与对应手段 / 24 个工具逐个说明 / 外部依赖 / 数据产物 / **12 个踩坑记录** / 五条可复用原则 / 全部有意义文件总表 / 未完成清单。**要理解全局看这份** |
| `D:\Cardinal\patches\helm_drums.vcv` | 鼓机架：Clocked 自走时钟(BPM100) → BassDrum9/ClosedHiHat/CR78 → Mixer(0.3) → HostAudio2 |
| `D:\Cardinal\patches\helm_keys.vcv` | 键盘机架：HostMIDI(复音8) → VCO → VCF → VCA-1 → Sum → Plateau 混响 → 输出 |
| `D:\Cardinal\patches\helm_keys_master.vcv` | **李手改的主机架**（他加了 MixMasterJr 8轨混音台，带 mute/solo） |
| `D:\Cardinal\patches\helm_keys_warm_pad.vcv` | warm_pad 音色配方预设，供试听对比 |
| `D:\Cardinal\patches\helm_knobs.vcv` | **旋钮映射版机架**：master 机架 + `HostMIDIMap`，8 个旋钮直控 8 个参数 |
| `D:\Cardinal\patches\helm_full.vcv` | **键盘全控件接入版**：上面全部 + `HostMIDIGate` + 6 个鼓机 + 2 个 Mixer（20 模块 / 35 缆） |
| `D:\Cardinal\patches\helm_before_full.vcv` | 生成 helm_full 前的活机架自动备份（保险，别删） |
| `D:\Cardinal\tools\make_full.py` | **生成/检查「键盘全控件接入」机架**：`build` / `report`，会自动先备份 |
| `D:\Cardinal\tools\fix_drum_bus.py` | **鼓总线接线修复 + 输入口冲突自查**：`report <patch>` 只检查；不带参数则修 `helm_full.vcv`（自动备份） |
| `D:\Cardinal\tools\state.py` | **状态诊断**（2026-09-12）：一屏打印「机架文件 vs 实时存档」的坐标差异、mtime、`zoom`/`gridOffset`、OSC 端口探活。**想知道"Cardinal 内存里到底是什么"就跑它** |
| `D:\Cardinal\tools\shot.py` | **GDI 截屏**（纯标准库，零依赖）：`python shot.py <输出png> [缩放宽]`，用来「让 AI 看见屏幕」 |
| `D:\Cardinal\tools\winprobe.py` | **窗口/DPI 探测**：屏幕缩放、Cardinal 窗口矩形与是否最大化；`--front` 置前 |
| `D:\Cardinal\tools\layout_patch.py` | **排班系统**（2026-09-12）：`check <patch>` 诊断坐标；**`guard <patch>` 门禁**（重叠/行不对齐/x<0/输入口双接，硬错误退出码 1）；`apply <patch> [--push] [--strict]` 按功能分行重排（自动备份、幂等、未登记模块自动落行）；`widths` 复测面板实测宽度。修「模块飞出视野」问题的正解 |
| `D:\Cardinal\refs\drums_map.json` | WSTD-Drums 各鼓模块的声部数 / 采样族（源码解析产物） |
| `D:\Cardinal\patches\helm_keys_live_backup.vcv` | 生成 helm_knobs 前的活机架快照（保险） |
| `D:\Cardinal\tools\cardinal_mcp.py` | **MCP 服务主体**，12 个工具 + 命令行入口 |
| `D:\Cardinal\tools\make_knobs.py` | **写 `HostMIDIMap` 映射表**：`show` / `apply` / `set`，支持 `--load` 直推 |
| `D:\Cardinal\tools\winmidi.py` | **Windows 原生 MIDI 工具**（winmm 封装，零依赖，列设备 + 监听） |
| `D:\Cardinal\tools\midiprobe.py` | MIDI 采集分析：`dump` 落盘 + `analyze` 自动分组、判端口镜像 |
| `D:\Cardinal\tools\watch_knobs.py` | 轮询存档比对参数（⚠️ 参数验证上**无效**，见约束 16） |
| `D:\Cardinal\tools\paramlib.py` | 从源码抓参数字典；含中文术语映射 `TERMS`；`verify` 子命令做对齐校验 |
| `D:\Cardinal\tools\musiclib.py` | 鼓型/和弦进行/音色配方；`apply_recipe` 把配方写进 .vcv |
| `D:\Cardinal\tools\patchio.py` | **双格式读写 .vcv**（明文 JSON / tar+zstd），所有工具都走它 |
| `D:\Cardinal\tools\vcvtool.py` `validate.py` | 查模块端口用法 / 校验机架合法性（模块字典 1422 个） |
| `D:\Cardinal\params\modules.json` | 参数字典：**15 模块 / 243 命名参数**，与三个机架 100% 对齐 |
| `D:\Cardinal\music\knowledge.json` | 音乐库：`drum_patterns`(9) / `progressions`(10) / `recipes`(8) |
| `C:\Users\<owner>\.workbuddy\mcp.json` | MCP 注册（server 名 `cardinal`，与 `其他 MCP server` 并存） |
| `D:\Cardinal\refs\FINDS.md` | **GitHub 仓库研究成果**：官方模板验证 / 漏用的模块 / 可抄范例 / OSC 边界 |
| `D:\Cardinal\refs\SMK25.md` | **李的键盘档案**：官方规格 / MidiSuite 挖掘 / MIDI 端口 / 六条链路 / 配置截图对照 |
| `D:\Cardinal\refs\smk25_config\*.png` | MidiSuite 11 个配置页截图（Keybed / Knob1-16 / Pad1-16 / Strips&Pedal / Transport） |
| `D:\Cardinal\refs\*.tpl.vcv` `refs\examples\*.vcv` | 官方 5 个模板 + 15 个示例机架（写新机架的照抄素材） |
| `~\.workbuddy\skills\cardinal-patch-authoring\SKILL.md` | **端口表 / 参数表 / 全部踩坑 / 官方资料索引**（权威版） |
| `.workbuddy\memory\2026-09-12.md` | 按时间线的详细工作日志 |

**Python 环境**：venv 在 `C:\Users\<owner>\.workbuddy\binaries\python\envs\music-ai`
（装了 `python-osc` + `zstandard`），解释器 `...\python\versions\3.13.12\python.exe`。

**⚠️ 本机 Bash 工具的 PATH 是坏的**，每条命令前要加：
```bash
export PATH="/c/Windows/System32:/c/Windows:/usr/bin:/bin:$PATH"
```
或者直接用 PowerShell / Read / Write 工具绕开。

---

## 2. 12 个 MCP 工具

`cardinal_ping` · `cardinal_list_patches` · `cardinal_patch_info` · `cardinal_load_patch` ·
`cardinal_set_param` · `cardinal_set_host_param` · `cardinal_read_live` · `cardinal_save_live` ·
`cardinal_module_params` · `cardinal_find_param` · `cardinal_music` · `cardinal_apply_recipe`

**新加的工具要重启 WorkBuddy 才进工具列表**。在那之前用命令行绕过：
```bash
python cardinal_mcp.py --tools                       # 列工具
python cardinal_mcp.py --call cardinal_read_live     # 直调
python cardinal_mcp.py --selftest                    # 全链路自检
```

---

## 3. 必须遵守的技术约束（踩过的坑）

1. **`.vcv` 有两种磁盘格式**：明文 JSON（version 2.1）和 tar+zstd 归档（version 2.4.1）。
   Cardinal 保存时**自动转成归档格式**。→ 读写一律走 `patchio.py`。
2. **OSC `/load` 只吃 pax tar + zstd**（从 Rack `system.cpp` 确认）。gzip、zip 都会被拒。
3. **Cardinal 有实时自动存档，可读回**：`%TEMP%\Cardinal.0001\patch.json`（明文 JSON）。
   → 李在界面上改动的**结构**（加模块、接线）能直接读出来。
   **但见约束 16 —— 它不记录参数变化，别拿它当参数监视器。**
4. **OSC `/param`**：`moduleId` 必须是 int64。
5. **参数编号有「废弃占位」**：`VCF` 的 1 号是 removed in 2.0 的空槽，`Clocked` 的 14 号是未使用槽。
   → 按编号猜名字会指错位置，**查 `modules.json` 或 `cardinal_module_params`**。
6. **复音开关**：Rack 2 的 Fundamental 模块全是复音的，「能不能弹和弦」唯一开关是
   `HostMIDI.data.channels`（**=1 就是单音**）。
7. **`Fundamental/Sum` 是复音→单声道折叠器**，不是混音器；6 路混音要用 `Fundamental/Mixer`。
8. **插件名可能和清单 slug 不一致**：patch 里写 `DrumKit`，清单里叫 `WSTD-Drums`。以示例 patch 为准。
9. **standalone 没有 DAW 时钟**，必须用 `ImpromptuModular/Clocked`（data 里 `running: true`）。
10. `HostMIDI` OUT2 是**力度（VELOCITY）**不是调制——官方模板接 VCO FM 是「力度→FM 深度」。
11. **`set_host_param` 此前是空转的**：机架里没有 `Cardinal/HostParametersMap` 时，
    OSC `/host-param` 发出去没人接收。要生效必须加该模块并写好 `maps`（格式见 SKILL.md）。
12. **厂商目录名 ≠ patch 里的 slug**：`Valley`→`ValleyAudio`、`rcm`→`rcm-modules`、
    `AriaSalvatrice`→`AriaModules`、`Bogaudio`→`BogaudioModules`、`Wasted_Audio`→`WSTD-Drums`。
    校验模块存在性时按 slug 比对，别按安装目录名。
13. **OSC 总共只有 4 个消息**（`/hello` `/param` `/host-param` `/load`），
    **没有 MIDI 注入、没有读回、没有 CV 注入**，且只有 standalone 有。
    → 实时演奏只能走 MIDI 键盘或虚拟 MIDI 端口；参数是否生效只能靠人眼看 GUI。
14. **headless 只有 Linux 版**，Windows 版必须带 GUI → 做不了无人值守渲染。
    **Cardinal 有意不自动保存**（与 VCV Rack 不同）→ `cardinal_save_live` 是必需品。
15. **写新机架前先对照 `refs\native.tpl.vcv`**（官方 standalone 启动机架），别凭空造。
16. **实时存档不随参数变化重写（2026-09-12 实测）**：发 OSC `/param` 改 VCF cutoff，
    3 秒后文件的 **mtime 和内容都不变**。写盘时机是 `/load` 这类结构性事件。
    → **改了参数之后无法程序化回读**，验证只能靠人眼看 GUI 旋钮位置。
    `tools/watch_knobs.py` 因此在参数验证上无效。
17. **`HostMIDIMap` 是 MIDI CC → 任意参数 的唯一通道**（VCV Rack 没有这个模块）：
    `data.maps = [{cc, moduleId, paramId}]`，`cc` 上限 **119**，`channel: 0` = OMNI，
    `smooth: true` 走指数平滑。**只写 `data` 即可，不需要参数列表**（`params: []`）。
    源码文件是 `plugins/Cardinal/src/HostMIDI-Map.cpp`（注意中间的连字符）。
18. **SMK25 通道极不统一（配置截图已确认）**：琴键+旋钮5 走 ch1、旋钮1-4/6-8 走 ch10、
    鼓垫 1-8 走 ch10/ch2/ch3/ch4/ch5/ch6/ch7/ch8、触控条+踏板走 ch9 —— **共占 9 个通道**。
    → `HostMIDIMap.channel` 与 `HostMIDI.inputChannel` 都设 **0（OMNI）**，否则收不全。
    `HostMIDIMap` 只做 CC→参数；`HostMIDI` 管 CV（音高/门/力度），两者**独立订阅宿主 MIDI**。
19. **SMK25 的旋钮与鼓垫是「双层」的**（官方手册确认；此前判断为"空槽位"是错的）：
    按 `KNOB-B` 切到 Knob 9-16、按 `PAD-B` 切到 Pad 9-16。**`KNOB-B` 是 toggle**（再按一次切回）。
    **✅ 2026-09-12 分离测试已实证**：
    - **第 1 层（默认）= CC 20–27，走 `[0]/[1]` 端口** ← 这是唯一能用于 `HostMIDIMap` 的一层
    - **第 2 层（按过 `KNOB-B`）= Pitch Bend，走 `[2]` 端口，每旋钮独占 ch1~ch8**，
      另有 Note **104~111** 作活动标记（旋钮 n → Note 103+n + 弯音通道 n）
    - ⇒ **`HostMIDIMap`（只认 CC）对第 2 层完全无效**；`HostMIDI` 的弯音输出口也分不清是哪颗旋钮。
      想用满 16 个旋钮，必须回 MidiSuite 把旋钮 9–16 的 Type 从 `MCP` 改成 `CC`（如 CC28–35）。
    - ⚠️ **这是「映射写对了、旋钮却毫无反应」的头号陷阱** —— 先确认没按到 `KNOB-B`。
20. **USB 复合设备端口 `[0]` 与 `[1]` 是镜像**（实测 483/483 条完全相同），监听只挂 `[0]`；
    **`[2] MIDIIN3` 平时静默，只在旋钮切到第 2 层时才发**（已实证）。
21. **SMK25 自带演奏引擎，不依赖软件**：`ARP` 琶音器（7 模式 + Latch + TAP）、
    `SC/CH` 智能音阶·和弦（单键出和弦）。→ "自动伴奏"未必要在 Cardinal 里搭。
22. **键盘没有内置音源**（官方规格与手册均无 sound engine 条目），
    声音必须来自 Cardinal / DAW / 外部音源。`SUSTAIN` 口是**踏板 + MIDI OUT 二合一**。
23. **WSTD-Drums 每个模块是「多声部鼓机」，不是单个鼓**（2026-09-12 读源码更正早期片面结论）：
    `SampleController.hpp` → `GATE_INPUT=16`、`TUNE_CV=32`、`AUDIO_OUTPUT=0`、`DRUM_PARAM=0`、`TUNE_PARAM=16`。
    ⇒ **第 i 声部**：触发口 `IN(16+i)`｜音频出 `OUT(i)`｜采样选择 `param(i)`（0-15）｜速度 `param(16+i)`。
    `BassDrum9 / SnareDrumN / ClosedHiHat / OpenHiHat / CR78 / DMX / Tomi` **各 2 个声部**（同族 16 个采样任选）；
    `SyntheticBassDrum / Gnome / Baronial / MarionetteBass` 是合成音、端口编号另说；`Sequencer` 是鼓用步进音序器。
    写 patch 时 `params: []` 走默认即可（默认 7 号采样），不用手填 32 个值。
    触发判据是 `SynthDevKit::CV(0.5f)` **0.5V 上升沿**。
24. **`HostMIDIGate`**（18 门入/18 门出，无参数）= MIDI 音符→门信号，鼓垫触发的正解：
    `data.notes[18]`（-1 = 未分配，默认 36..53）、`inputChannel`（0=OMNI）、
    **`velocity` 要设 false**，否则门电压随力度缩放，轻敲可能到不了 0.5V 阈值。
25. **`HostMIDICC`**（16 个 CC 单元 + OUT16 通道压力 + **OUT17 弯音**，无参数）：
    `data.ccs[16]`（默认 1..16，-1 = 未分配）、`inputChannel`（0=OMNI）、`lsbMode`、`smooth`。
26. **`HostMIDI.data.pwRange` 默认 0 ⇒ 弯音完全不生效**。弯音是直接叠加在 `PITCH_OUTPUT` 上的
    （`pitch = (notes-60 + pw*pwRange)/12`），所以放行通道 + pwRange>0 就自动有弯音，不用另接线。
27. **`Fundamental/Mixer` 是 6 入 1 出、只有 1 个参数（总音量，默认 1.0）**（源码 `Mixer.cpp` 核实），
    没有分路音量。8 路鼓要 2 个 Mixer。
28. **⚠️ 一个输入口只能接一根线，多接的被静默丢弃**（**不是求和口 —— 2026-09-12 实测推翻本条旧结论**）：
    加载不报错、实时存档也看不到，所以极难发现。踩坑实录：鼓总线与合成器同抢 `HostAudio2` IN0/IN1，
    结果合成器保留、鼓被丢 → **鼓垫有 MIDI 反应但完全没有声音**。
    ⇒ 要并流就**进混音台空闲轨道**（`MixMasterJr` 有 8 轨），别抢同一个输入口。
    另：只接左(IN0)时右会自动镜像；**IN1 已接线则不镜像，须两边都接**。
29. **`MixMasterJr` = `MixMaster<8,2>`，端口表已查清**（源码 `MixMaster.cpp` 的 `enum InputIds`）：
    输入每轨 2 口，索引 = `2*i + (0=L, 1=R)` → Track1=IN0/IN1、**Track2=IN2/IN3**、Track3=IN4/IN5
    … Track8=IN14/IN15；之后依次是各轨音量 CV、分组音量、各轨 pan CV 等。
    主输出 = **OUT2/OUT3**（`DIRECT_OUTPUTS` 占了 OUT0/OUT1）。推子默认 1.0（0dB）、pan 默认 0.5（居中）。
30. **敲鼓垫会同时弹响合成器** —— 因为琴键(ch1)与鼓垫(ch2-8/ch10)共用宿主 MIDI 入口。
    解法：`HostMIDI.inputChannel = 1`（只收琴键），鼓垫交给 `HostMIDIGate`(OMNI)。
    **代价**：触控条与踏板在 ch9，被 ch1 过滤掉 ⇒ 弯音失效（CC1/CC64 仍走 `HostMIDIMap` 的 OMNI 正常）。
    正解是回 MidiSuite 把「Strips & Pedal」通道 9 → 1。
31. **`pos[0]`（x）单位是「格」；`pos[1]`（y）单位是「行」**（2026-09-12 15:45 修正）——
    - **x = 格**：1 格 = 1 HP = 15px，模块宽 = 面板 SVG 毫米数 ÷ 5.08
    - **y = 行号**：写 **0 / 1 / 2 / 3…**，1 行 ≈ 380px（Rack 的 `RACK_GRID_HEIGHT`，≈ 25.3 格）。
      **证据**：本机 20 个官方模板/示例，**即便 39 模块的多行机架，y 也全部落在 -1 ~ 2**；
      Cardinal 保存 `helm_full.vcv` 后 y 也正是 **0/1/2**。→ **别写 34、68**，那是「格」，
      会把模块扔到第 34 行的荒野（比写成像素更隐蔽：文件看着"有值"，界面上却什么都没有）
    - ⚠️ **遗留疑点（最高优先验证）**：早期我把 y 写成 0/34/68，李当时**却看到了正常三行**
      → 推测 Cardinal **加载时做了「格 → 行」吸附**（读格、写行号，读写不对称）。
      若吸附不成立，**李下次打开现在的文件（y=0/1/2）可能看到行 1 与行 2 重叠**。
      **验证方法**：让李 `File → Open` 重开 `helm_full.vcv`，确认仍是三行分离（1 分钟，零成本）
    - 写错会让模块飞出视野（2026-09-12 实录：新模块写成 `pos=[300, 80]`，
    等于放到 4500px 外，李界面上「只看到线、看不到模块」）。
    **李要求把排班规则固化：「你得把排班规则写到一个根生蒂固的地方，系统提示词里，每次加东西都注意排班。」**
    → 规则已写入 `~/.workbuddy/MEMORY.md`（该文件每轮自动注入系统提示词）
    - **坐标系权威依据**：Rack 用**面板 SVG 的物理尺寸**决定模块宽度，**1 HP = 5.08mm**。
      实证 `mixmaster-jr.svg` 182.88mm ÷ 5.08 = 36 HP；`mixmaster.svg` 309.88mm ÷ 5.08 = 61 HP
    - **模块高 25.3 格（371px）→ 行距必须 ≥ 26 格**，实践用 34；**列间距 = 模块宽 + 6**
    - **宽度不要猜，量面板**：`python tools\layout_patch.py widths` 复测（核对 42 项实测值）
    - **新增/移动模块四步（不可跳）**：接线 → 登记 `LAYOUT` → 过门禁 → 推送复验
    - 工具 `tools/layout_patch.py`：
      `check <patch>` 诊断坐标 ｜ **`guard <patch>` 门禁**（重叠/行不对齐/x<0/输入口双接，不过退出码 1）
      ｜ `apply <patch> [--push] [--strict]` 重排+自动备份+幂等，未登记模块自动落行
      ｜ `widths` 复测面板宽度
    - 当前 `helm_full.vcv` 已按实测宽度对齐（文件与实时存档一致）：
      **行 0** 合成器链（0~88 格）/ **行 1** 控制映射+鼓机（0~124）/ **行 2** 混音输出+说明牌（0~82）
    - `TextEditor` 模块是**可写文本备忘牌**（`data.etext` 存文本、`data.width` 定宽），
      已用来写「机架地图」，改机架时顺手同步它

---

## 3.5 李的键盘：M-VAVE SMK25（型号能力与配置已查清）

| 部件 | 实测消息 | 状态 |
|---|---|---|
| 25 键 | Note On/Off，**ch1**，力度 1–127（Octave 0 / Transpose 0，键盘端可调） | ✅ |
| **8 旋钮（第 1 层）** | CC **20–27**（**第 5 个走 ch1，其余 ch10**） | ✅ **已接到 Cardinal 参数** |
| 8 鼓垫（第 1 层） | Note **48–55**，**分散在 ch10/ch2/ch3/ch4/ch5/ch6/ch7/ch8** | ⚠️ 通道不统一，待处理 |
| 触控条 | Pitch Bend + CC1（调制轮），均在 **ch9** | ✅ |
| **踏板** | **CC64（延音），ch9**，踩下 127 / 松开 0 | 配置已知，未实测 |
| **Transport 键** | PLAY=Note**94** / STOP=Note**93** / REC=Note**95** | 配置已知，未实测 |
| **旋钮第 2 层**（按 `KNOB-B`） | **Pitch Bend，每旋钮独占 ch1~ch8，走 `[2]` 端口**（✅ 已实证） | ❌ **`HostMIDIMap` 接不住** |
| **鼓垫第 2 层**（按 `PAD-B`） | Note 96–99 / 91、92、87、85 | ❓ 未实测 |
| **ARP 琶音器** | 7 种模式 + Latch + TAP 定速，**键盘端生成** | ✅ 手册确认 |
| **SC/CH 音阶和弦** | Smart Scale 约束音阶 / Smart Chord 单键出和弦 | ✅ 手册确认 |

### ✅ 已完成的「键盘全控件接入」（`helm_full.vcv`，2026-09-12）

**分工靠通道**：`HostMIDI` 收 **ch1**（琴键）｜`HostMIDIGate` 收 **OMNI**（鼓垫）｜`HostMIDIMap` 收 **OMNI**（旋钮/触控/踏板）

| 键盘控件 | 进 Cardinal 的路 | 落到哪 |
|---|---|---|
| 25 琴键 | HostMIDI → VCO/ADSR | 合成器（复音 8） |
| 8 旋钮 CC20-27 | HostMIDIMap | VCF 亮度/共振/Drive、Plateau 湿度/尾巴、ADSR 起音/余音、VCO 脉宽 |
| **触控条上下（CC1）** | HostMIDIMap | **Plateau Size（混响空间）** ← 新增 |
| **踏板（CC64）** | HostMIDIMap | **ADSR Sustain** ← 新增（⚠️ 李**暂无踏板硬件**，机架侧已配好，买来插上即用） |
| **8 鼓垫（Note 48-55）** | **HostMIDIGate OUT0-7** | **8 个鼓声部** ← 新增 |

鼓垫分配（每模块 2 声部，触发口 IN16/IN17）：

| 垫 | Note | 声部 | 音色 |
|---|---|---|---|
| 1 | 48 | BassDrum9 v0 | 底鼓 A |
| 2 | 49 | BassDrum9 v1 | 底鼓 B |
| 3 | 50 | SnareDrumN v0 | 军鼓 A |
| 4 | 51 | SnareDrumN v1 | 军鼓 B |
| 5 | 52 | ClosedHiHat v0 | 闭镲 |
| 6 | 53 | OpenHiHat v0 | 开镲 |
| 7 | 54 | Tomi v0 | 嗵鼓 |
| 8 | 55 | DMX v0 | DMX 打击 |

鼓声汇聚：6 路 → `Mixer(107)`、2 路 → `Mixer(108)`（音量各 0.35），两条总线 → **`MixMasterJr` 轨道 2 / 轨道 3**（`IN2/IN3`、`IN4/IN5`），由混音台统一汇到主输出 `OUT2/OUT3` → `HostAudio2`。

> ⚠️ **2026-09-12 修正（重要）**：初版把两条鼓总线**直接并进 `HostAudio2` 的 IN0/IN1**，结果**鼓完全没声音**。
> 根因：**Cardinal 一个输入口只能被一根线占用**（**不是求和口**），鼓总线与合成器抢同一对输入时，
> 后者被**静默丢弃**（加载不报错、实时存档也看不到）→ 鼓垫有 MIDI 反应但音频到不了输出。
> 已改为进混音台空闲轨道。工具：`tools/fix_drum_bus.py`（`report` 子命令可自查输入口冲突）。
改映射一行搞定：`python make_knobs.py set helm_full.vcv 1 Bogaudio LFO --load`

**通道全貌：琴键(ch1)、旋钮5(ch1)、旋钮1-4/6-8(ch10)、鼓垫(ch10,2-8)、触控/踏板(ch9)
—— 9 个通道混用。** ⇒ Cardinal 端必须用 OMNI，别无选择。

配置截图的权威对照见 `refs\SMK25.md` 第 3.2 节（截图与实测 100% 吻合）。

### 已落地的旋钮映射（`helm_knobs.vcv` 里的 `HostMIDIMap`）

`channel: 0`（OMNI）+ `smooth: true`

| 旋钮 | CC | 目标 | 作用 |
|---|---|---|---|
| 1 | 20 | VCF param0 Cutoff | 亮度 |
| 2 | 21 | VCF param2 Resonance | 共振 |
| 3 | 22 | Plateau param1 Wet | 混响湿度 |
| 4 | 23 | Plateau param7 Decay | 混响尾巴 |
| 5 | 24 | ADSR param0 Attack | 起音 |
| 6 | 25 | ADSR param3 Release | 余音 |
| 7 | 26 | VCO param5 Pulse width | 脉宽 |
| 8 | 27 | VCF param4 Drive | 过载 |

改映射：`python make_knobs.py set helm_knobs.vcv 21 Bogaudio LFO --load`

- 连接：BLE MIDI / USB MIDI；本机端口 `SMK25` / `MIDIIN2 (SMK25)` / `MIDIIN3 (SMK25)`
- 配套软件 `D:\MidiSuite`（可配 CC、有 Chord/Scale 模式、可导出配置）
- 完整实测表见 `refs\SMK25.md`
- ⚠️ **Cardinal 的 `HostMIDI` 要选对输入端口**，否则收不到数据
- ✅ **2026-09-12 复核：Cardinal 侧完全就绪** —— 运行中的 `HostMIDIMap` 8 条映射完好、
  `smooth=true`、`channel=0`，`HostMIDI.inputChannel` 也已是 **0（OMNI）**。
  （`read_live` 曾显示 `data=null` 是**工具没提取 data 字段**，不是数据丢 —— 已确认）
- ✅ **键盘侧之谜已解**：第二轮「80 秒零 CC」是**按过 `KNOB-B` 切到第 2 层**所致，非故障。
  **拧旋钮前别碰 `KNOB-B`**，CC20–27 就正常发出（2026-09-12 分离测试实证）。
- ✅ **旋钮映射已由李实测确认生效**（2026-09-12）：拧 6 号（Release）旋钮声音有变化、触控条上下也生效
  → **CC→参数整条链路全通**（这一条此前一直无法自动验证）
- ❌ **鼓垫无声** —— 已定位并修复，详见下方「鼓垫无声的根因与修复」

---

## 4. 下一步候选（等李选）

0. **✅ 分离测试已完成**（2026-09-12，见约束 19 与 `refs\SMK25.md` 3.5 节）——
   第 1 层 = CC20–27 走 `[0]`；第 2 层 = 弯音 ch1~ch8 走 `[2]`；`KNOB-B` 是 toggle。
   **遗留已解除**：2026-09-12 李实测确认——拧旋钮有反应、触控条上下生效，映射链路全通。
0b. **ARP / SC-CH / Transport** 仍未实测
   （第二轮数据里 60~69s 有密集重复音符，疑似琶音但不确定出自哪个引擎）。
0c. **让弯音生效（小改动，等李做）**：MidiSuite 的「Strips & Pedal」页，把通道 **9 → 1**。
   `helm_full.vcv` 里 `pwRange` 已设 2.0（±2 半音），通道一改，触控条左右立刻有弯音。
0d. **可选优化**：MidiSuite 里把旋钮 9–16 的 Type 从 `MCP` 改成 `CC`（如 CC28–35），
   这样第 2 层也能被 `HostMIDIMap` 映射，16 个旋钮全部可编程。
1. ✅ **「键盘全控件接入」已完成** → `helm_full.vcv`（2026-09-12，见 3.5 节）。
   **实测结果（2026-09-12）**：旋钮 ✅ 生效、触控条 ✅ 生效、**鼓垫 ❌ 无声 → 已定位并修复**。

   > **鼓垫无声的根因与修复（2026-09-12）**
   > **根因**：鼓的两条总线（`Mixer` 107/108）与合成器（`MixMasterJr`）都接到了 `HostAudio2` 的 IN0/IN1。
   > 而 **Cardinal 一个输入口只能接一根线**，多接的被**静默丢弃**（合成器保留、鼓被扔掉）
   > → 鼓垫有 MIDI 反应，但音频根本到不了输出口。
   > **修复**：鼓总线改接 `MixMasterJr` 的**轨道 2 / 轨道 3**（`IN2/IN3`、`IN4/IN5`），由混音台汇到主输出 `OUT2/OUT3`。
   > **工具** `tools/fix_drum_bus.py`（`report` 可自查输入口冲突）；**备份** `helm_full_before_drumfix.vcv`。
   > 已推送进 Cardinal（20 模块 / 35 缆、**零输入口冲突**）。
   > **待李复测：敲 8 个鼓垫是否有声。**
1b. **鼓声细化**：每个声部的采样选择（`param(i)`，0-15）还没调，默认都是 7 号采样；
   想让 8 个垫音色更分明，可以逐个试采样。也可以把 `Mixer` 音量再按李的听感调。
1c. **加 Transport 走带键**：Note 93/94/95 → `ImpromptuModular/Clocked` 的 Run/Reset
   （需要机架里加一个 Clocked，且要有东西被它驱动才有意义）。
2. **修 `set_host_param`**：机架加 `Cardinal/HostParametersMap` 并写映射，让 24 个宿主参数真正生效
3. **做「自动伴奏」机架**：抄 `refs/examples/falkTX_-_Mini-Arp-Seq.vcv` 的思路，
   用 `rcm-modules/PianoRoll` 或 `JW-Modules/GridSeq` + `Plaits`/`Rings`，
   让 Cardinal 自己演奏和弦/琶音，人只管弹旋律 —— **AI 辅助创作最快见效的一步**
4. **升级音色**：`Fundamental/VCO` → `AudibleInstruments/Plaits` 或 `Rings`（本地已有）
5. **做 MCP 工具**：把 `make_knobs` 的能力包成 MCP 工具，
   让「把 3 号旋钮改成控混响」变成一句话的事
6. **鼓 + 键盘合并机架**（"伴奏"雏形）——需重做音量平衡
7. LMMS 侧（装 1.3.0-alpha.2 + 挂 `Cardinal.vst`，LMMS 只吃 VST2）与录音闭环 —— 李说不急

---

## 5. 李的偏好（协作约定）

- 中文沟通，参数名却全是英文 → 用 `cardinal_find_param` 做中文口语翻译（"亮一点"→Cutoff、"尾巴"→Release）
- 要他做决定时**列选项让他挑**，别直接替他落地
- 文字要说人话：结论放最前、术语第一次出现给解释、多用短句和条目
- 改机架前**先存盘**，他的手工改动不能丢
- **动手做东西前先查资料**（李 2026-09-12 明确要求）：① GitHub 仓库 `patches/`
  ② 本机 `docs/` ③ 已归档 `refs/`。那里有社区资源，别凭空造
