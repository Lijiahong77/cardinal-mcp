# Biset 拆解 · 参考地图

> 2026-09-21 · **目的**：落实李的决定 ——「**参考 Biset 的模块，但不拿过来改造**」
> 依据：Biset **2.0.13** 源码（WSL `$HOME/Cardinal/plugins/Biset`）+ 官方手册 26 页
> 手册已归档：`D:\Cardinal\refs\biset-doc\*.pdf`（5 份，原为 .odp 导出）

---

## 0. 三条结论（先说结果）

**① Biset 的"参考"必须是拆开参考，不能整体照搬。**
它是 **20876 行**的成熟套件，其中 **Tracker 系列 55 个文件 / 10691 行**。
（对照：官方最小模块范例 `Cardinal/src/Blank.cpp` 只有 **103 行**。）

**② Biset 恰好缺你最想要的那个功能。**
手册第 15 页原文：录制模式指示灯 —— **"recording mode (not available yet !)"**；
Matrix 视图同样标着 **"Not handled yet"**。而你要的是「预设鼓组/琴组 + **手弹录制**」。
⇒ **"参考 Biset"能覆盖"编曲器"那半边，覆盖不了"录制"那半边。**

**③ 这反过来验证了"不改造"的决定是对的。**
想在 Biset 里加录制，得在它 7716 行的 Tracker 里挖开数据模型；自己写则可以从第一天
就把"录制"当第一公民。加上作者**已停更**（上游不会修 bug），"不改造"在维护上也更省事。

---

## 1. Biset 的整体架构（三层）

| 层 | 内容 | 体量 |
|---|---|---|
| **共享基础** | `components.hpp`(632) / `scales.cpp`(801) / `plugin.hpp`(136) / `types.hpp`(115) / `data.cpp`(43) / `plugin.cpp`(33) / `tools.cpp`(33) | **1793 行** |
| **模块** | 20 个模块，每个占一个目录 | ~19000 行 |
| **资源** | `res/`（面板与按钮 SVG）、`doc/`（手册） | — |

`plugin.hpp` 是它的"总头文件"：一次 include 全部模块，并 `extern` 全部 model 与数据表
（12 平均律表、30+ 种音阶表、多个律制表）。

---

## 2. Tracker 套装：7 个模块协同（手册权威说明）

| 模块 | 职责 | 体量 |
|---|---|---|
| **Tracker** | **主编曲**：编辑 timeline / patterns / synths / tuning 并播放 | **27 文件 7716 行** |
| T-Synth | 输出某 synth 的 pitch / gate / velocity / panning + 最多 8 路调制（**复音**） | 5 文件 692 行 |
| T-Drum | 同 T-Synth，但输出**单音、拆成 12 条线**（每个半音一条）→ 当鼓触发用 | 5 文件 688 行 |
| T-Control | 控制器 | 3 文件 410 行 |
| T-Phase | 同步 LFO（/32 ~ x32） | 4 文件 378 行 |
| T-Clock | 时钟分频/倍频（/96 ~ x96）+ 相位 + 脉宽 + swing | 4 文件 332 行 |
| T-State | 可视化 + 播放状态输出 | 4 文件 238 行 |
| T-Quant | 量化器 / 调音器 | 3 文件 237 行 |
| | **合计** | **55 文件 10691 行** |

### 2.1 值得注意的架构决策：隐式互联

> 手册原文：「The modules of the suite are **implicitly interconnected**. Tracker,
> at the center of this connection, **should only be present once in the patch**.」

即：**模块之间不靠接线，靠共享的实例状态**。Tracker 整个 patch 只能有一个，其余模块去"取"它的数据。
（唯一例外：同一个 synth 可挂多个 T-Synth，以获得不同的 CV 量程。）

> **这个思路值得借鉴** —— 一个"编曲器 + 若干输出端"的套件，用共享状态比拉一堆线清爽得多。
> Cardinal 里已有先例：`HostMIDIMap` 就是"无端口、读实例级数据"的模块。

### 2.2 数据模型

- **track** = patterns + synths
- **pattern** = **note columns**（音高 / 八度 / 力度 / 声像 / synth id / 延迟 / 滑音 / 效果）
  + **CV columns**（手绘调制曲线）
- **容量**：**100 synths / 1000 patterns**
- **存储**：JSON（`Tracker-dataToJson.cpp` 386 行 / `Tracker-dataFromJson.cpp` 240 行）

### 2.3 四个视图

| 视图 | 作用 | 状态 |
|---|---|---|
| Pattern | 编辑选中的 pattern、增删改 synth | ✅ |
| Timeline | 排列 pattern | ✅ |
| **Matrix** | 面向现场演出 | ❌ **未实现** |
| Tuning | 调律（参考频率、每音音分、律制/音阶预设） | 🟡 "in construction" |

---

## 3. 你要的东西 vs Biset 有什么

| 你要的（2026-09-20 原话） | Biset 里有吗 |
|---|---|
| **预设鼓组** | 🟡 有 `T-Drum` + "synth 定义"，但**没有独立的鼓组预设库**概念 |
| **预设琴组** | 🟡 同上（synth + `T-Synth`） |
| **手弹录制** | ❌ **完全没有** —— 手册明写 recording mode `not available yet` |

⇒ **"参考 Biset" = 参考它的编曲器骨架；"录制"这块要我们自己设计。**

---

## 4. 参考地图（哪些值得看、看到什么程度）

| 参考对象 | 位置 | 价值 | 说明 |
|---|---|---|---|
| **模块骨架三段式** | 官方 `Cardinal/src/Blank.cpp`（**103 行**） | ⭐⭐⭐ | `Module` 结构体 + `Widget` 结构体 + `createModel<...>()` |
| **注册与命名冲突处理** | `plugins/plugins.cpp` | ⭐⭐⭐ | 两个真实的坑，见 §5 |
| **构建配置写法** | `plugins/Makefile` | ⭐⭐⭐ | 见 §5、§6 |
| **隐式互联架构** | 手册 p4 | ⭐⭐⭐ | **设计思路**，不是代码 |
| **UI 组件库** | `Biset/src/components.hpp`（632 行） | ⭐⭐ | 全是 10–20 行的小组件（按钮 / 开关 / LED / 端口），写法可借 |
| **音阶与律制数据表** | `Biset/src/scales.cpp`（801 行） | ⭐⭐ | 纯数据表，可直接参考有哪些音阶/律制 |
| **多文件切分手法** | `Tracker/` 共 27 个文件 | ⭐ | 为绕开单文件过大而拆；知道即可，不必学 |
| **Tracker 本体实现** | `Tracker/` 7716 行 | ⭐ | 参考成本极高；价值在"看它怎么组织"，不在抄 |

---

## 5. 落地时必然会撞的两个坑（源码实据）

### 坑 1 · 不要 include 自己包的 `plugin.hpp`

```cpp
// Biset
/* NOTE too much noise in original include, do this a different way
// #include "Biset/src/plugin.hpp"
*/
```

原因：插件自己的 `plugin.hpp` 里通常有 `using namespace rack;` 之类，会**污染全局命名空间**，
与其它 90 多个包打架。Cardinal 的解法 = **手工 `extern Model*` 每个模块**（`plugins.cpp` L179–198）。

### 坑 2 · model 变量名会撞车

```cpp
#define modelBlank modelBisetBlank     // plugins.cpp L177
#define modelTree  modelBisetTree
```
以及编译期的 `` -DpluginInstance=pluginInstance__Biset ``（`Makefile` L2285）。

⇒ **我们的新包从一开始就让 model 名带包前缀，就不需要这套宏了。**

---

## 6. 加一个新包要动的地方（修正一处旧笔误）

> ⚠️ `ENV-READINESS-REPORT.md` §2.2 写的是 `Makefile.base.mk`，**实际不是** ——
> 那个文件在 `dpf/` 和仓库根目录，与插件无关。正确的文件是 **`plugins/Makefile`**。

| # | 位置 | 动作 |
|---|---|---|
| **1** | `plugins/我们的包名/` | 建目录：`src/`（模块 + 包级 `plugin.hpp/.cpp`）+ `res/`（面板 SVG）+ `plugin.json` |
| **2** | `plugins/plugins.cpp` | ① `extern Model* modelXxx;` ② 写 `static void initStatic__我们的包()` ③ 在初始化链里调用它 |
| **3** | `plugins/Makefile` | ① `PLUGIN_FILES += $(filter-out 我们的包/src/plugin.cpp,$(wildcard 我们的包/src/*.cpp))` ② 加包专属编译规则块（形如 L2280–2285） |

> ⚠️ **2026-09-21 二次修正（本报告原表述有误，勿再引用旧版）**
>
> `PLUGIN_FILES` **不是全局统一用 `$(wildcard ...)`**。实测 `plugins/Makefile`：
> - **官方内置包 = 显式逐行列文件**。`Cardinal` 段（L226–239）一行一个 `.cpp`
>   （`PLUGIN_FILES += Cardinal/src/Blank.cpp` ……），**新加文件必须手工补一行**。
> - **只有一部分第三方包用 wildcard**：Biset（L581–582）、BogaudioModules（L590–592）等。
>
> ⇒ **规则**：**新建自己的包**照 Biset 写 wildcard，才能享受"新增源文件不用改列表"；
> **往官方 `Cardinal` 包里加文件，必须手工加行**。

Biset 现成的两行（可照抄结构）：
```make
PLUGIN_FILES += $(filter-out Biset/src/plugin.cpp,$(wildcard Biset/src/*.cpp))
PLUGIN_FILES += $(wildcard Biset/src/*/*.cpp)
```
（第一行的 `filter-out .../plugin.cpp` 是为了**排除包自己的 plugin.cpp** —— 每个包只需一个入口。）

---

## 7. 第一个模块的起点（三选一，决定权在李）

| | 起点 | 规模 | 产出什么 |
|---|---|---|---|
| **A** | **空壳跑通** —— 基于官方 `Blank.cpp` 改一个自己的模块 | ~100 行 | 验证「写码 → 重编（约 35 秒）→ 在 Windows 上看见它」整条链 |
| **B** | **最小发声音序器** —— 8 步 + 时钟输入 + pitch/gate 输出 | 300–500 行 | 一个能驱动 VCO 的模块，是编曲器的原子 |
| **C** | **先定功能规格** —— 把「预设鼓组/琴组 + 手弹录制」展开成可评审的设计 | 0 行代码 | 一张功能清单，避免"先写后想" |

> **A 与 C 可以同时做**（A 验证链路、C 定方向），B 是前两者合流后的第一步。

---

## 8. 许可证

- **Biset**：`GPL-3.0-or-later`（`plugin.json` 明写）。
- **Cardinal 本体**：同样是 GPL 系。
- ⇒ 新包若**随 Cardinal 一起重编**，GPL 是既定事实，**不构成额外约束**。
- 但「参考」与「抄代码」是两件事：
  - **抄代码 = 衍生作品**（须保留版权与许可声明）
  - **自己重写 = 只受思路启发**，干净
- ⇒ 李那句"**不拿过来改造**"在许可证这一层也是省事的。

---

## 附：本报告的数据来源

| 数据 | 怎么来的 |
|---|---|
| 所有行数 / 文件数 | 遍历 WSL 里 Biset 2.0.13 源码实测 |
| 功能模型与"未实现"结论 | 官方手册 PDF 26 页正文（已归档 `refs/biset-doc/`） |
| 注册与构建机制 | 直读 `plugins/plugins.cpp`、`plugins/Makefile` 对应行 |
| 最小范例 | 直读 `plugins/Cardinal/src/Blank.cpp`（103 行） |
