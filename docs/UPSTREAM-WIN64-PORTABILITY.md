# Cardinal 在 Windows 上交叉编译：6 个可移植性缺陷与修法

> 记录时间：2026-09-20
> 环境：Ubuntu 26.04 (WSL2) → 交叉编译 Windows x64，mingw-w64 GCC 13
> 成果：成功产出 `Cardinal.exe` / `CardinalMini.exe` / `CardinalNative.exe`，实机启动验收通过
> 目的：这些缺陷目前**只有 Windows 目标会触发**，Linux/macOS 构建永远撞不到，因此长期无人修复。
> 本文按"根因 → 影响 → 最小修法"组织，可直接作为上游 issue / PR 的素材。

---

## 0. 根本原因：上游没有任何人对 Windows 平台负责

三条结构性事实，决定了这些坑为什么存在：

1. **Cardinal 本体 + 约 190 个第三方插件包，全部只在 Linux / macOS 上构建。** Windows 头文件里的那些"历史遗迹"（`near` 空宏、`TRANSPARENT` 宏）在 Linux 上永远不触发，所以永远没人去修。
2. **官方 CI 是封闭配方，隐含三条前提。** 官方 Windows 构建跑在 `ubuntu:22.04` 容器里，每天全新建环境 —— GCC 旧、没装 JACK、CMake 目录为空。本地复刻时**一条都不满足**，于是每个差异都变成一个坑。
3. **构建系统假设"一台机器只编一个平台"。** `.o` 文件、CMake 构建目录、静态库**全都不带平台标记**。先编 Linux 再编 Windows，`make` 认为"已最新"，直接把 Linux 产物拿去链接。同一个根因踩了 3 次。

---

## 1. C23 把 `bool` 变成关键字，撞死 2010 年的老 glib

**归属**：PawPaw 构建系统（第三方）

**报错**
```
goption.c:169: error: two or more data types in declaration specifiers
```

**根因**
Ubuntu 26.04 的宿主 GCC 15 默认 `-std=gnu23`（`__STDC_VERSION__=202311L`）。C23 把 `bool` 提升为关键字，而 2010 年前后的老 glib 源码里有 `gboolean bool;` —— 变量名撞关键字。

> 注意：mingw 交叉 GCC 13 默认 C17，**不受影响**。只有宿主侧工具链（bootstrap 阶段）会撞。

**最小修法**
给宿主侧 CFLAGS 追加 `-std=gnu17`：
```bash
# deps/PawPaw/bootstrap-common.sh 约第 250 行，EXTRA_CFLAGS 注入点
EXTRA_CFLAGS="... -Wno-int-conversion -std=gnu17"
```

---

## 2. simde 的 native alias 宏钻进 mingw 原生头，造成重定义

**归属**：**Cardinal 本体**（`include/simd-compat/immintrin.h`）

**报错**
```
simde/x86/sse2.h:3653: error: redefinition of '__m128i simde_mm_loadu_epi64(const void*)'
simde/x86/sse2.h:3628: 同 epi32
simde/x86/sse2.h:3603: 同 epi16
simde/x86/sse2.h:3578: 同 epi8
```

**根因链**
1. `include/simd-compat/tmmintrin.h` 定义了 `SIMDE_ENABLE_NATIVE_ALIASES`；
2. simde 因此为 AVX512VL 生成别名宏：
   ```c
   #define _mm_loadu_epi8(a)  simde_mm_loadu_epi8(a)
   #define _mm_loadu_epi16(a) simde_mm_loadu_epi16(a)
   #define _mm_loadu_epi32(a) simde_mm_loadu_epi32(a)
   #define _mm_loadu_epi64(a) simde_mm_loadu_epi64(a)
   ```
3. 之后 `simd-compat/immintrin.h` 执行 `#include_next <immintrin.h>` 进入 mingw 原生头；
4. mingw 的 `avx512vlintrin.h` 里有**同名函数定义**，被上面的宏替换掉 → 重定义。

**最小修法**
在 `include_next` 前后 undef / 恢复这 4 个宏：
```c
/* include/simd-compat/immintrin.h */
# define CARDINAL_INCLUDING_IMMINTRIN_H

# ifdef  _mm_loadu_epi8
#  undef  _mm_loadu_epi8
#  define CARDINAL_RESTORE_MM_LOADU_EPI8
# endif
/* ... epi16 / epi32 / epi64 同理 ... */

# include_next <immintrin.h>

# ifdef CARDINAL_RESTORE_MM_LOADU_EPI8
#  define _mm_loadu_epi8(a) simde_mm_loadu_epi8(a)
#  undef CARDINAL_RESTORE_MM_LOADU_EPI8
# endif
/* ... 其余三个同理 ... */

# undef CARDINAL_INCLUDING_IMMINTRIN_H
```
实测：文件 628 → 1802 字节，`plugins.cpp` 从 4 个 error 变为通过。

---

## 3. Windows 16 位遗留空宏 `near` / `far`

**归属**：Cardinal 内置插件 `rackwindows`（`src/rwlib.h`）

**报错**
```
error: expected identifier or '(' before '=' token
```
（源码是 `int near = ...;`，但预处理器把它变成了 `int = ...;`）

**根因**
`/usr/share/mingw-w64/include/minwindef.h:74` 附近有**无条件**定义：
```c
#define near
#define far
```
这是 Windows 16 位内存模型的遗留空宏。**`_NO_W32_PSEUDO_MODIFIERS` 管不住它们**（那是给 `IN`/`OUT`/`OPTIONAL` 用的）。

**最小修法**
把 `near` 变量改名（最干净），或在包含 `windows.h` 之前加护栏：
```c
#ifdef near
# undef near
#endif
#ifdef far
# undef far
#endif
```

**排查提示**：全仓库扫描时只有两处命中 —— `rackwindows/src/rwlib.h` 与 `HetrickCV/Gamma/Spatial.h:344`。后者经确认不在编译路径上（引它的 `HRFilter.h` 无人 include），可不动。

---

## 4. GDI 宏 `TRANSPARENT` / `ERROR` 撞枚举成员，一个 TU 炸出 2840 个错误

**归属**：`plugins/surgext`（随 Cardinal 分发的第三方插件）

**报错**（表面现象）
```
error: expected identifier before numeric constant
```
错误数：**2840**。但真正的根因点只有 **2 个**。

**根因**
`wingdi.h` 定义：
```c
#define TRANSPARENT 1
#define ERROR       0
```
而 surgext 里：
- `src/Delay.h:107` 枚举成员叫 `TRANSPARENT`
- `src/LayoutEngine.h:51` 枚举成员叫 `ERROR`

被替换后 `} type{ERROR};` 变成 `} type{0};`，枚举整体解析失败，**拖垮 2504 处引用** —— 所以看起来像"到处都错"，实际只有 2 行需要改。

**最小修法**
重命名枚举成员（如 `TRANSPARENT_` / `ERROR_`）。

**排查方法（值得复用）**
不要被错误数量吓住。正确做法是统计错误的**分布**，找出被引用的公共源头：
```bash
grep 'error:' build.log | grep -oE '^[^:]+' | sort | uniq -c | sort -rn | head
```
2840 个错误收敛到 2 个文件后，修复成本从"天"降到"分钟"。

---

## 5. surge 静态库平台串味：链接时拿到 ELF 归档

**归属**：**Cardinal 构建系统**（`deps/`）

**报错**
```
undefined reference to `SurgeStorage::getPatch()'
```

**根因**
- `deps/Makefile:290` 定义 `SURGE_LIB = deps/surge-build/src/common/libsurge-common.a`；
- `deps/surge-build` 是一个 **CMake 构建目录**，之前 Linux 版编译时留下的（`CMakeCache.txt` 里写着 `/usr/bin/g++`）；
- 交叉编译时 `make deps` 认为它"已最新"，直接跳过；
- 链接阶段于是拿 **ELF 格式的 `libsurge-common.a`** 去链 PE 目标 → 符号全找不到。

**决定性证据**
```bash
ar p libsurge-common.a <member>.o | file -
# → ELF 64-bit LSB relocatable, x86-64        （应该是 PE/COFF）
```

**最小修法**
让 CMake 目录在交叉编译环境下重建：
```bash
mv deps/surge-build deps/surge-build.linux-bak
```
重跑后 `CMakeCache` 正确写入 `CMAKE_CXX_COMPILER=/usr/bin/x86_64-w64-mingw32-g++`、
`CMAKE_SYSTEM_NAME=Windows`。（该目录约 29 MB，改名可逆。）

---

## 6. `.o` 与依赖就绪的竞态：`cannot find libarchive_static.a`

**归属**：**Cardinal 构建系统**

**报错**
```
cannot find libarchive_static.a        （27 秒即快速失败）
```

**根因（两个叠加）**
1. **`.o` 不区分目标平台** —— 之前 Linux 版编译留下的 2832 个 `.o` 被复用，直接进链接；
2. **依赖不跨 make 进程传递** —— `src/Cardinal` 与 `src/Rack/dep` 由**不同的 make 进程**驱动，`-j8` 下前者会抢在 dep 就绪之前进入链接。

**最小修法**
- 交叉编译前清理 Linux 版产物（`.o`、`src/Rack/dep/lib/*.a`）；
- 把依赖构建**串成一步**：
  ```makefile
  # 关键：先单独编完 Rack 全部依赖，避免并行竞争
  xvfb-run make deps -j$(nproc)
  xvfb-run make NOOPT=true -j$(nproc)
  ```

---

## 7. 给上游的建议（按优先级）

| 优先级 | 建议 | 归属 |
|---|---|---|
| 高 | `include/simd-compat/immintrin.h` 加 include_next 前后的宏 undef/恢复（第 2 条） | Cardinal 本体 |
| 高 | `deps/` 让 CMake 中间目录带平台后缀，或在交叉编译时强制重建（第 5 条） | Cardinal 构建系统 |
| 中 | `rackwindows/src/rwlib.h` 的 `near` 改名（第 3 条） | 内置插件 |
| 中 | `surgext` 的 `TRANSPARENT` / `ERROR` 枚举改名（第 4 条） | 分发的第三方插件 |
| 中 | `.o` 按目标平台分目录（第 6 条，根治） | Cardinal 构建系统 |
| 低 | `bootstrap-common.sh` 追加 `-std=gnu17`（第 1 条） | PawPaw |

---

## 8. 附：一个容易误导人的点（非缺陷，但值得写进文档）

`make` 默认产出的 `Cardinal.exe` 是 **main 变体**，而它：

```makefile
# src/Makefile.cardinal.mk:59-65
ifeq ($(CARDINAL_VARIANT),main)
  SKIP_NATIVE_AUDIO_FALLBACK = true     # 不走原生音频回退 → 只能用 JACK
else ifneq ($(CARDINAL_VARIANT),mini)
  FORCE_NATIVE_AUDIO_FALLBACK = true    # native 变体 → 走系统原生音频
endif
```

**后果**：自己编出一个 `Cardinal.exe` 后启动，在没装 JACK 的 Windows 上会弹
`Failed to create JACK client`，且没有声音 —— 很容易被误判为"编译失败"。

**而官方发给 Windows 用户的是 `CardinalNative.exe`**（native 变体），它不碰 JACK。
官方 Windows 发布目录里也只有 `CardinalNative.exe` / `CardinalJACK.exe`，**没有 `Cardinal.exe`**。

**建议**：在构建文档里明确标注"Windows 用户请用 `CardinalNative.exe`"，或让默认目标按平台自动选择变体。

### 另一个部署陷阱：`resources/` 目录

`CardinalNative.exe` 启动时会找系统目录 `C:\Program Files\Common Files\Cardinal`；
找不到就弹框提示，且**模块面板无法渲染**（只有空机架）。

便携式部署需要在 exe 同级放 `resources/`：
```bash
# 资源已由构建生成在 bin/Cardinal.lv2/resources/（约 253 MB / 6500 个文件）
# 注意：该目录里大量条目是符号链接，直接拷到 NTFS 会失效，必须解引用
tar -czhf resources.tar.gz resources      # -h = 解引用符号链接
```

---

## 附录：本地复刻官方 CI 的完整步骤（Windows 交叉编译）

```bash
# 前置：Ubuntu 24.04+（26.04 需先打第 1 条补丁）、mingw-w64、wine、xvfb-run
#       wine 在 26.04 上没有 wine-stable 包，装 wine 元包；需先 dpkg --add-architecture i386

CARDINAL_ROOT=~/Cardinal
cd $CARDINAL_ROOT

# 1) 构建 PawPaw 交叉工具链与 Windows 静态库（约 26 分钟，产出约 50 个 .a）
./deps/PawPaw/bootstrap-cardinal.sh win64

# 2) 载入交叉编译环境
source deps/PawPaw/local.env win64
#    校验：日志开头应为 WINDOWS: Yes / LINUX: No，CC/CXX/AR 均为 mingw，EXE_WRAPPER=wine

# 3) 编译（部分步骤需要 xvfb：wine 跑 Windows 工具需要 X display）
xvfb-run -a make features -j$(nproc)
xvfb-run -a make deps -j$(nproc)          # 关键：先编完 Rack 全部依赖
xvfb-run -a make NOOPT=true -j$(nproc)
xvfb-run -a make carla-win32 -j$(nproc)

# 4) 产物：bin/Cardinal.exe、bin/CardinalMini.exe、bin/CardinalNative.exe
#    部署：exe 同级放 resources/（从 bin/Cardinal.lv2/resources/ 解引用拷贝）
```
