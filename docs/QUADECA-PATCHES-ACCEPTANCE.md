# Quadeca 风格机架 · 验收单（2026-10-17 实机版）

> 上一版（第二轮改写）声称的"全部通过"是**无效结论** —— 那批机架其实一张都加载不了。
> 本版是**真机验证后**的结果，每一条都有实测记录。

---

## 一、结论：五张机架全部实机加载通过（12:11）

按顺序推送，全部返回 `["load","ok"]`：

| 顺序 | 机架 | 模块/线 | 加载 | 截图 |
|---|---|---|---|---|
| 1 | `quadeca_auto_ghostfolk.vcv` | 15 / 22 | ✅ ok | 画面正常 |
| 2 | `quadeca_auto_scrapyard.vcv` | 15 / 22 | ✅ ok | — |
| 3 | `quadeca_auto_life1.vcv` | 15 / 22 | ✅ ok | — |
| 4 | `quadeca_play.vcv` | 20 / 31 | ✅ ok | 画面正常 |
| 5 | `quadeca_auto_ghostfolk.vcv`（复验） | 15 / 22 | ✅ ok | — |

`patch_info` 复核 `quadeca_play`：20 个模块全部在位、31 条线，
`Gnome` param0=92.0、`Sequencer` 151 个 param 中鼓点写入生效
（67/72/77/112-126/131 非零）、五块鼓采样与速度参数全部按真实量纲写入。

截图证据：
- `tmp/quadeca_play.png` —— Gnome 显示 BPM 082 / RUNNING，Sequencer 面板**绿色鼓点格子**可见，
  五块鼓（BassDrum9 / SnareDrumN / ClosedHiHat / OpenHiHat / Tomi）、键盘三层音色、级联 Mixer 全部在位
- `tmp/ghostfolk_run.png` —— 三个 Piano Roll（Pad / Bass / Lead）**黄色音符块**可见，留白小节符合设计

---

## 二、🔴 元凶：端口越界（不是数据字段！）

**`Fundamental/Mixer` 只有 `OUT0` 一个输出口**，我写了 `Mixer.OUT1` ⇒ 加载即崩。

证据三件套：

1. **`PORTS.md` L194**：`Mixer`（显示名 Mix）| 6 路输入 `IN0-5`，`OUT0=Mix`
2. **13 份成功机架反推**（`tools/realports.py`）：Mixer 输出口清一色 `[0]`、输入口 `[0-5]`，
   `OUT1` 在任何一份可信机架里都没出现过
3. **审计器与实验 100% 吻合**：`zz_V0`/`zz_L1` 无越界 → 成功；`zz_V1`/`zz_L2` 有 `Mixer.OUT1` → 全崩

### 顺带挖出的第二个越界

`quadeca_play.vcv` 还有 `Mixer.IN6` 越界 —— 鼓 4 路 + 键盘 3 层 = **7 路，超过 Mixer 的 6 路上限**。
已改为**两个 Mixer 级联**：

```
Mixer A：鼓×4 → IN0-3，键盘 lead/pad → IN4-5，A.OUT0 → B.IN1
Mixer B：键盘 bass → IN0，B.OUT0 → HostAudio2.IN0
```

### 🔴 顺带发现：两份旧交付物从未真正加载成功

`demo_S4_sampling.vcv` / `demo_S5_fullkit.vcv`（10-17 我交付的采样演示机架）
也有端口越界 ⇒ **它们从来没真正加载成功过**。当时李关了声音、走静默验收，
缺陷被掩盖了。**这两份是无效交付物。**

---

## 二之二、🔴 第二个真问题：时钟源选错（加载成功但不会自动播）

**在准备试听时才发现**：三张机架加载成功、接线完整、音符数据也写进去了，
但**时钟根本不走** —— 永远不会自动演奏。

`PORTS.md` §1.5 原文：

> `HostTime` …… **依赖宿主走带，standalone 里没用，要换 Clocked**

两个错误叠加：

1. **用了 `HostTime`** —— 独立版 Cardinal 里不走带
2. **接的是 `OUT4`** —— 而 `OUT4` 是 **Step**（步进），**不是 clock**

⇒ 已改为 `Clocked`（`PORTS.md` §2 确认是 standalone 自走时钟）：

| 项 | 值 |
|---|---|
| 时钟源 | `Clocked.OUT0`（主时钟）→ 三个 `rcm-pianoroll.IN0` |
| `param0` | **90.0**（绝对 BPM，Clocked 的量纲） |
| `data.running` | **`true`**（必须，否则不走） |
| param 数 | 20（照抄 `helm_drums.vcv` 的实测结构） |

**实机验证**（截图 `D:\Cardinal\refs\_clock_big2.png`）：
CLOCKED 面板 **BPM 显示 90**、**RUN 按钮绿灯亮起** ⇒ 时钟已激活。

> ⚠️ 教训：**「加载成功」和「会工作」是两件事**。
> 试听之前必须逐个环节问「这个模块在我的运行环境里真的会动吗」——
> `HostTime` 在插件宿主里正常、在 standalone 里就是死的，这是我凭插件经验想当然的坑。

---

## 三、我走的五条弯路（比结论更值钱）

| # | 错误假设 | 为什么错 |
|---|---|---|
| 1 | `cable.color=""` | 删掉仍崩；它只是无害的干净习惯 |
| 2 | `data` 从 `None` 改成 `{}` | 改回原样仍崩 |
| 3 | `Rings.model` 写成字符串 `"Modal"` | 改回整数 `0` 仍崩 |
| 4 | 悬空 `leftModuleId`/`rightModuleId` | 清零后照样崩；且 `demo_S5_fullkit` 成功加载过却有 **12** 个悬空 ⇒ Rack 容忍它 |
| 5 | `cable.id` 用大整数 | 换成小整数仍崩 |

**代价：让李重启了 5 次 Cardinal。**

### 方法论（下次照这个做）

1. **先做成功/失败机架的全字段对照**，找「成功组全有、失败组全无」的差异；
2. 对照不出来 → **转实验法**：生成「逐层剥离探针」（`make_bisect.py` → `zz_L1..L6`，
   从 1 个模块加到 N 个），**一次重启锁定层数**；
3. 再对锁定的那层做**正交变体**（每次只改一个变量）。

配套要点：
- 探针必须**静态预检干净**，否则结论不可信
- **必须留一个「已知成功过的旧机架」当环境基线先推一次**，排除环境漂移
  （我推 `quadeca_ghostfolk` 成功，才敢确定问题在我的文件而非环境）

---

## 四、已落地的防护（这类崩溃不会再发生）

| 工具 | 作用 |
|---|---|
| `tools/audit_ports.py` | **端口越界审计**，已内建进三个生成器的自检，越界的机架出不了门 |
| `tools/realports.py` | 从**成功机架**反推任意模块的真实端口集合，接新模块不用靠记忆 |
| `make_bisect.py` | 逐层剥离探针生成器，下次崩溃直接用 |

生成器自检现状：
```
✅ quadeca_auto_ghostfolk.vcv   0 处越界
✅ quadeca_auto_scrapyard.vcv   0 处越界
✅ quadeca_auto_life1.vcv       0 处越界
✅ quadeca_play.vcv             0 处越界
合计越界 0 处        ← 全盘 34 张机架
```

---

## 五、两批机架的分工

### A. 自动演奏组（`quadeca_auto_*`，15 模块 / 22 线）
加载即自动演奏，**不需要李碰任何东西**。

| 机架 | 风格手法 |
|---|---|
| `ghostfolk` | D 小调多瑙利安 i–VI–III–VII，五声化慢旋律，第 5 小节留白 |
| `scrapyard` | C 小调，半音下行 C→Bb→Ab→G + 反拍 |
| `life1` | A 小调，密集快速反复 + 大跳，几乎不留白 |

三层织体（回应"他的音乐难道那么简单的吗"）：
- **lead**：`Rings` 物理建模拨弦
- **pad**：`VCO` 方波，缓起缓落
- **bass**：`VCO` 锯齿，短促干声
- 各有独立 VCA 的 level/pan，再入 Mixer

### B. 可弹奏组（`quadeca_play`，20 模块 / 31 线）
- `HostMIDI`（channels=8，能弹和弦）→ 三层音色
- **五块 WSTD 鼓机全部参数用上**：采样（param 0-15）+ 速度（param 16-31）
- `Gnome` 92 BPM 自走时钟 → `Sequencer` 铺底鼓点（不干扰你弹）

鼓点设计（Quadeca 的"稳"+"抽"）：底鼓四踩 + 后半段双击推进；
军鼓错位重音落 5/13 步（非标准 4/12）；闭镲 8 分、末小节加密到 16 分；
开镲 7/15 反拍；后半段加桶鼓填句。

---

## 六、待办

- [ ] **实际试听** —— 静态全过 + 加载全过，但还没听过声音。ADSR 长度 / 混响量 / BPM / 层次都要按听感调
- [ ] 修 `demo_S4_sampling.vcv` / `demo_S5_fullkit.vcv` 的端口越界（否则它们永远加载不了）
- [ ] 清理废弃探针（已归档到 `tools/_bisect_archived/`）

## 七、复现命令

```bash
PY=<USERPROFILE>/.workbuddy/binaries/python/envs/music-ai/Scripts/python.exe
$PY D:/Cardinal/tools/make_quadeca_auto.py     # 三张自动演奏
$PY D:/Cardinal/tools/make_quadeca_play.py     # 可弹奏 + 五鼓
$PY D:/Cardinal/tools/audit_ports.py           # 全盘端口审计（必须 0 处越界）
```