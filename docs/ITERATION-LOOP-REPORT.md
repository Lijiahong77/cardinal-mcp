# 迭代闭环验证报告 · 改代码 → 重编译 → 生效

> 日期：2026-09-20 17:20–17:35
> 目标：证明「我改一个模块 → 重编 → 产物真的变」，即**分钟级迭代循环**真实可用。
> 结论：**通过。** 且证明编译**可复现**、改动**可逆**。

---

## 一、结论先行（三条）

| # | 结论 | 证据强度 |
|---|---|---|
| 1 | **改单个模块只重编 18 条，耗时 ~35 秒** | 日志实测 |
| 2 | **编译可复现**：还原源码后，产物 md5 **精确回到原值** | 字节级 |
| 3 | **不能靠字符串搜索验证改动**（GCC 把短串内联成 `mov` 立即数） | hexdump |

**对项目的意义**：你改一个模块 → 重编 → 看效果，是**半分钟一轮**，不是「等一晚上」。
「改一次要重编整个 Cardinal」这个担心，**在改单模块时不成立**。

---

## 二、构建机制：一个模块 = 一个独立 `.o`

之前一直以为插件是「一个大编译单元」。实测**不是**：

```
plugins/Makefile:2134   $(BUILD_DIR)/21kHz/%.cpp.o: 21kHz/%.cpp     ← 每个插件、每个 .cpp 一条独立规则
plugins/Makefile:2074   plugins$(TARGET_SUFFIX).a: $(PLUGIN_OBJS)   ← 所有 .o 打成静态库
```

- `.o` 落在 **`build/plugins/<插件名>/src/`**
- 全仓 **2828 个 `.o`**
- 链接链：`改动 .cpp` → 重编**那一个** `.o` → 重打 `plugins.a` → 重链接各格式产物

---

## 三、实验设计与实测数据

### 改动内容（靶子：`plugins/Fundamental/src/LFO.cpp`）
```cpp
// 改前
configParam(PW_PARAM, 0.01f, 0.99f, 0.5f, "Pulse width", "%", 0.f, 100.f);
configOutput(SIN_OUTPUT, "Sine");
// 改后
configParam(PW_PARAM, 0.01f, 0.99f, 0.25f, "Pulse width", "%", 0.f, 100.f);
configOutput(SIN_OUTPUT, "Sine WB");
```

### 三阶段实测

| 阶段 | 产物 md5 | 重编条数 | 耗时 | 错误 |
|---|---|---|---|---|
| ① 基线 | `8ec47d3dbaed5ab860dfa8177e036f89` | — | — | — |
| ② 改动后 | `16c28bf2b40b94924405c1773155b043` | **18** | ~35s | 0 |
| ③ 还原后 | `8ec47d3dbaed5ab860dfa8177e036f89` | 18 | 34s | 0 |

**②→③ md5 精确复原** —— 同时证明：编译确定性、改动是唯一变量、循环可逆。

### 18 条的构成
```
Compiling Fundamental/src/LFO.cpp                                  ← 唯一的模块源文件
Compiling DistrhoPluginMain.cpp  (CLAP/JACK/LV2/VST2/VST3)  ×多份   ← 各插件格式入口
Compiling DistrhoUIMain.cpp      (LV2)
```
对照：**全量是 1931 条** → 增量范围 ≈ **0.9%**。

### 其他模块的 `.o` 完全没动 ✅
```
Octave.cpp.o   17:09:47   （未变）
Noise.cpp.o    17:02:10   （未变）
VCO.cpp.o      17:02:12   （未变）
LFO.cpp.o      17:02:10 → 17:26:07   （被重编）
```

---

## 四、踩到的坑（都记进技能了）

### 坑 1：`\\wsl$\...` UNC 路径**可读不可写**
- 读：Python / Read 工具都行
- 写：`PermissionError: [Errno 13] Permission denied`
- **正解**：Windows 侧生成 `.new` → `wslrun.py --sh "cp /mnt/d/... <WSL 目标>"`
- 注意用 `--sh`（<user> 身份）；用 `--root` 会把属主变成 root

### 坑 2（重要）：**别用字符串搜索验证改动**
GCC 把短字符串字面量**内联成 `mov` 立即数**，不再是 `.rodata` 里的连续串。
`LFO.cpp.o` 的 hexdump 里 `"Sine WB"` 的真身：

```
53 69 6e 65              "Sine"
c7 84 24 e3 00 00 00     movl $imm, 0xe3(%rsp)
65 20 57 42              "e WB"
c6 84 24 e7 00 00 00 00  movb $0, ...        ← NUL 结尾
```

所以 `strings` 只能看到 `SineH` / `WB` 这种碎片，**完整串永远搜不到**。
（`"Octave shift CV"` 同理，只搜到 `Octave sH`。）

**⇒ 正确判据三件套**：
1. **产物 md5 变化**（最硬）
2. **目标 `.o` 的 mtime 刷新**，且**其他 `.o` 未动**
3. **编译范围**（日志 `Compiling` 条数 ≈18）

### 附带排除的怀疑
`ccache` 装了但 **Makefile 根本没用**（`ccache -s` = 0.0 GiB，从未使用）—— 不是它的问题。

### 守卫机制两次生效（正面案例）
`apply_lfo_change.py` 的断言我写错两次（字节增量算错、断言字符串带反引号不匹配），
**因为断言都在写入之前，文件毫发无伤**，修正后重跑通过。

---

## 五、标准闭环 SOP

```
① 记基线    md5sum bin/Cardinal
② 改源码    生成 .new → WSL 内 cp 覆盖
            （锚点唯一断言 → 先断言 → 后写入 → 回读校验）
③ 重编      JOBS=12 bash tools/build_cardinal.sh full
④ 验证      md5 变了 + 目标 .o mtime 刷新 + 其他 .o 未动 + 0 错误
⑤ 可逆      改回原文件重编 → md5 应精确复原
```

---

## 六、下一步（路线 B：交叉编译 Windows 版）

探查发现一个好消息：**`deps/PawPaw` 已经在源码树里**（作为子模块），
官方交叉编译工具链脚本是现成的：

- `deps/PawPaw/build-plugins.sh` —— 构建脚本，内部用 **wine** 跑 Windows 侧校验（`WINEDEBUG=-all`）
- `deps/PawPaw/setup/env.sh` —— 环境配置

需要装的交叉编译依赖（已模拟验证存在）：`binutils-mingw-w64-x86-64`、
`g++-mingw-w64-x86-64`、`mingw-w64`、`wine`、`xvfb`、`zip`（共 131 个包）。

**目标**：产出能替换桌面 Cardinal 26.02 的 Windows `.dll` / `.exe`。

---

## 附：本报告涉及的命令与文件

- 靶子源码：`$HOME/Cardinal/plugins/Fundamental/src/LFO.cpp`（已还原）
- 备份：`D:\Cardinal\tmp\LFO.cpp.orig`（原始） / `LFO.cpp.new`（改动版）
- 脚本：`D:\Cardinal\tmp\{probe_octave,check_before,apply_lfo_change,verify_lfo_change,diag_stringpool}.py`
- 日志：`D:\Cardinal\tmp\build_full.log`（最近一次重编）
