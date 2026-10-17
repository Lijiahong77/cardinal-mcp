# WSL2 安装 + Cardinal 编译 · 分步操作手册

> 生成：2026-09-20 ｜ 更新：2026-09-20 17:10
> 用法：**一次只做一步。** 每步做完把结果贴给我，我确认无误才给下一步。
> 为什么这样：避免"走到第 5 步才发现第 2 步错了"（李明确要求）
>
> **实际执行情况**：第 1 步（装 WSL2）由李执行（需管理员权限，我跑不了）。
> **第 2 步往后全部由 AI 执行**，目前已跑到第 6 步。
> 所以本手册现在更多是「**施工台账**」而不是「待办指南」——
> 记录**实际做过什么、踩过什么坑、还剩什么**。
>
> 前置阅读：`BUILD-NOTES.md`（为什么必须用 WSL2、编译规模多大）

---

## 全局地图（先看这个，知道要去哪）

```
第 1 步  装 WSL2 + Ubuntu          ✅ 完成（李执行）   WSL 2.7.14 / Ubuntu 26.04 LTS
第 2 步  进 Ubuntu，换国内源        ✅ 完成（我执行）   清华源，34 MB / 11 秒
第 3 步  装编译依赖（apt 一堆包）    ✅ 完成（我执行）   111 包 / 33.6 秒
第 4 步  装 ccache（提速）          ✅ 已并入第 3 步
第 5 步  clone Cardinal 源码        ✅ 完成（我执行）   158 子模块全部对版 / 3.2 GB
第 6 步  最小验证：编一个 hello     ✅ 完成（我执行）   make mini / 79 秒 / 0 错误
第 7 步  全量编译（首次，很久）      ✅ 完成（我执行）   make all / 209 秒 / 0 错误
第 8 步  产物取回 Windows           ⏸ 待编出产物       需先确认产物是 Linux 版还是 Win 版
```

**第 6 步是核心设计**——不直接冲第 7 步。先用**极小的编译任务**证明
「编译器能跑、依赖齐了、WSL 没坏」，**再**投入几十分钟的全量编译。
这样万一环境有问题，**10 分钟内就发现**，不会白等一小时。

---

## 风险与回滚（做之前先知道退路）

| 担心 | 实情 | 退路 |
|---|---|---|
| 会不会搞坏电脑？ | ❌ 不会。WSL2 是微软官方功能，**与 Windows 隔离** | `wsl --unregister Ubuntu` 一键删除 |
| 会不会搞坏现有 Cardinal？ | ❌ 不会。**官方 26.02 一个字节都不碰** | 新产物放别的目录 |
| 编译失败怎么办？ | 正常现象，不是灾难 | `make clean` 重来，或直接删掉 WSL 重装 |
| 占多少空间？ | WSL 虚拟磁盘，**按需增长**，不是一上来占几百 G | 删掉即释放 |

> **一句话**：这件事**风险极低、完全可逆**。最坏结果是"没编成，白花几小时"，
> 不会损坏任何现有东西。李的顾虑可以放下。

---

# 第 1 步：安装 WSL2 + Ubuntu

## 你要做什么

**1.1** 按 `Win` 键 → 输入 `powershell` → 右键「Windows PowerShell」→ **以管理员身份运行**
（必须管理员，否则装不了）

**1.2** 在黑窗口里粘贴这一行，回车：

```powershell
wsl --install -d Ubuntu-26.04 --location D:\WSL\Ubuntu-26.04
```

**1.3** 等它下载安装完（约 400 MB）。若提示需要重启，就重启。

> ⚠️ **这一步必须你来跑，我跑不了。** 实测：非管理员环境下这条命令会**静默挂死**
> （需要 UAC 提权弹窗，而我这边弹窗看不见，只能一直等）。见下方「附：为什么这步得你来」。

## 你会看到什么

类似这样的输出（具体文字可能略有不同）：

```
正在下载: Ubuntu 26.04 LTS
正在安装: Ubuntu 26.04 LTS
已成功安装分发。可以通过 "wsl.exe -d Ubuntu-26.04" 启动它。
```

> 说明：WSL **平台/内核**部分你上次已经装好并重启了（实测版本 **2.7.14.0**），
> 所以这次**只会下载并安装 Ubuntu 发行版本体**，不会再走一遍平台安装。

## 可能出问题的地方

| 现象 | 原因 | 怎么办 |
|---|---|---|
| 卡在 `0.0%` / 卡在微型商店 | 下载源慢（国内商店常卡） | `Ctrl+C` 停掉，加 `--web-download` 绕开商店（见「方案 B」） |
| 命令**没有任何输出、一直不动** | 需要管理员权限（UAC 弹窗被忽略） | 确认窗口标题是「**管理员**」；不是就关掉重开 |
| 反复失败 | 商店 + 网络双卡 | 走「**方案 C：手动下载**」（最稳） |
| 提示 `wsl 不是内部或外部命令` | 系统太旧 | 你的 Build 26200 远超要求（19041），不会遇到 |
| 提示虚拟化未开启 | BIOS 里关了 VT-x | 你的 `HypervisorPresent: True`，**不会遇到** |
| 重启后自动弹出黑窗口要你设用户名 | **正常**，这是设 Ubuntu 账号 | 见第 2 步 |

## 三个方案（按顺序试，前面的不行再往下）

### 方案 A：一条命令（首选）

```powershell
wsl --install -d Ubuntu-26.04 --location D:\WSL\Ubuntu-26.04
```

### 方案 B：绕开微软商店

国内商店经常卡住。加 `--web-download` 直接从服务器下载：

```powershell
wsl --install -d Ubuntu-26.04 --location D:\WSL\Ubuntu-26.04 --web-download
```

### 方案 C：手动下载（最稳，推荐备选）

**已实测可用的直链**（HTTP 200，396 MB）：

```
https://releases.ubuntu.com/26.04/ubuntu-26.04-wsl-amd64.wsl
```

```powershell
# 1) 先建目录（手动下载这条路需要目录已存在）
mkdir D:\WSL -Force

# 2) 下载（约 396 MB）
curl.exe -L -o D:\WSL\ubuntu-26.04-wsl-amd64.wsl https://releases.ubuntu.com/26.04/ubuntu-26.04-wsl-amd64.wsl

# 3) 用下载好的文件安装到 D 盘
wsl --install --from-file D:\WSL\ubuntu-26.04-wsl-amd64.wsl --location D:\WSL\Ubuntu-26.04
```

> 注：阿里云镜像 `mirrors.aliyun.com/ubuntu-cdimage/ubuntu-wsl/` **只有 `daily-live/`，
> 没有正式版 `.wsl` 文件**，所以只能走官方源。
> （阿里云按 Ubuntu 代号分目录：`noble/`=24.04、`resolute/`=26.04、`stonking/`=26.10）

---

## ⚠️ 附：为什么这一步必须你来跑

**实测记录（2026-09-20）**：我尝试自己执行安装，结果是：

- **0 字节输出、没有任何下载痕迹、`D:\WSL` 目录没被创建**
- 一直卡住不动，76 秒后被强制终止

**原因**：`wsl --install` 需要**管理员权限**，会弹 UAC 授权框。我运行在非交互环境，
**弹窗我看不见**，于是无限等待 → 挂死。

**这不是能力缺陷，是 Windows 的安全设计** —— 任何程序都不能静默获取管理员权限。
你自己手动装也一样要点那一下授权。

> **分工**：**安装/提权类操作 = 你**；**之后的一切（装依赖、换源、clone、编译、改代码、迭代）= 我**。

## 装完后：设 Linux 账号

装完后通常会**自动弹出 Ubuntu 窗口**，让你：

```
Enter new UNIX username:      ← 随便起个名字，比如 <user>（小写字母）
New password:                 ← 设个密码（输入时不显示，正常）
Retype new password:          ← 再输一遍
```

> ⚠️ **密码记牢**，以后 `sudo` 要反复用。输入时**屏幕上不会有任何显示**，不是卡了。

如果**没有**自动弹窗，就跳到第 2 步手动启动。

## 这一步的验收标准

重启后，**以管理员身份**开 PowerShell，运行：

```powershell
wsl --list --verbose
```

应该看到类似：

```
  NAME      STATE           VERSION
* Ubuntu    Running         2
```

**关键点**：`VERSION` 那列必须是 **2**，不是 1。

把这条命令的**完整输出**贴给我。

---

# 第 2 步：切换国内源 —— ✅ 已完成（我执行）

**做法**：Ubuntu 26.04 用的是**新版 deb822 格式**源文件
（`/etc/apt/sources.list.d/ubuntu.sources`），**不是**老的 `/etc/apt/sources.list`。

```bash
cp -a /etc/apt/sources.list.d/ubuntu.sources /etc/apt/sources.list.d/ubuntu.sources.orig
cp /mnt/d/Cardinal/tmp/ubuntu.sources /etc/apt/sources.list.d/ubuntu.sources
apt-get update
```

**实测**：34.2 MB / **11 秒**（约 3 MB/s）。原文件已备份为 `ubuntu.sources.orig`。

> 已确认清华源对 `resolute`（26.04 代号）返回 200。
> 另外：**WSL 里不需要密码就能拿到 root** —— `wsl -u root` 即可（`sudo` 反而要密码，
> 我拿不到）。这条是整个接管方案的关键突破口。

---

# 第 3 步：安装编译依赖 —— ✅ 已完成（我执行）

**做法**：先 `apt-get install -s`（**模拟安装**）验货，确认 26.04 里这些包都存在、
没有改名缺件，再真装。

**实测**：111 个包，**33.6 秒**。

```
build-essential cmake pkg-config wget ccache
libdbus-1-dev libgl1-mesa-dev liblo-dev libfftw3-dev libmagic-dev libsndfile1-dev
libx11-dev libxcursor-dev libxext-dev libxrandr-dev
autoconf automake libtool meson ninja-build gperf
```

**工具链版本 —— 这是本项目最大的技术风险点：**

| 工具 | 版本 |
|---|---|
| **gcc / g++** | **15.2.0** ⚠️ |
| make / cmake / ccache / pkg-config | 均已就位 ✅ |

> ⚠️ **GCC 15 vs 官方 CI 的 GCC 11**：Cardinal 官方 CI 跑在 Ubuntu 22.04（GCC 11）上，
> 我们用的是新了 4 代的 GCC 15。**新编译器 + 老代码 = 可能报编译错误**。
> 退路：换 Ubuntu 24.04（GCC 13）重装，**约 10 分钟**，不必害怕。

---

# 第 4 步：装 ccache —— ✅ 已并入第 3 步

不单独做。

---

# 第 5 步：clone Cardinal 源码 —— ✅ 已完成（我执行）

**位置**：`$HOME/Cardinal` —— **必须在 WSL 内部，不能放 `/mnt/d/`**
（跨文件系统访问会慢到不可用）。

**版本**：标签 `26.02`，与你现装的 Cardinal **完全对版**。

**实测**：**158 个子模块（含嵌套）全部对版**，0 空壳，0 未初始化，3.2 GB。

**这一步踩了三个坑：**

1. **GitHub 国内会间歇性掐长连接** —— 短请求（`ls-remote`）能通，长下载（`clone`）443 超时。
   解法：**开 VPN**。实测 **WSL2 走宿主机网络栈**，Windows 侧开代理即可，
   Linux 里不用再配一遍。
2. **浅克隆的嵌套子模块要跑多遍才浮现** —— 父级是空壳时，它自己的 `.gitmodules`
   不存在，递归更新**发现不了下一层**。解法：`fetch_src.sh` 改成**最多 4 遍 + 提前跳出**。
   实测递归总数：134 → 158。
3. **我误判并掐断过一次任务**（见下方「元教训」）—— 后果是 37 个子模块变空壳，
   需 `repair_subs.sh` 修回。

**新增工具**：`fetch_src.sh`（幂等拉取 + 三项校验）、`repair_subs.sh`（修空壳）。

> **元教训**：长任务跑着的时候看到"不一致"，**先问一句「它是不是还没走到这儿？」**。
> 判据 = 进程还在不在（`ps`）+ 隔一会儿再采样看**趋势**。
> 我当时拿"跑到一半的快照"当结论，把正在正常工作的任务掐了。

---

# 第 6 步：最小验证 —— ✅ 完成（2026-09-20 17:08，用时 79 秒）

**靶子**：`make mini` —— 官方 Makefile 里现成的目标，只编少量插件的最小可用版。
（`make mini` 比"自己编个 hello world"更好：**它走的是完整链路**，
只是模块少。全通了就等于真环境通了。）

这是**第一次真正跑通全链路**：`carla → deps → dgl → plugins → src`。

**已完成的前置**：
- `make deps` —— ✅ **90 秒**通过，6 个静态库全部落地
  （含 **`libzstd`** —— Cardinal 的 tar+zstd 存档格式要靠它）
- `carla`（整个插件宿主框架）—— ✅ 编译通过

**已踩的坑（两次失败，都已修复）**：

| 次序 | 报错 | 根因 |
|---|---|---|
| 第 1 次 | `Fundamental/src/plugin.hpp: No such file or directory` | **空壳子模块**（被掐断的后果） |
| 第 2 次 | `plaits/dsp/voice.h` 缺失 | **嵌套子模块未初始化**（父级修好后才浮现） |

**结果 —— 决定性通过：**

```
退出码    : 0
用时      : 79 秒
真实错误  : 0
产物      : bin/CardinalMini          16,347,744 字节
            bin/CardinalMini.lv2/     插件目录
BUILD_OK
```

**产物健康度已逐项验证（不能只看「文件存在」）：**

| 检查 | 结果 |
|---|---|
| 文件类型 | `ELF 64-bit LSB pie executable, x86-64` ✅ |
| 未解析动态库 | **0** ✅（liblo / libGL / libX11 / libstdc++ 全部可解析） |
| 符号表 | 654 个动态符号（不是空壳）✅ |
| LV2 插件 | `_dsp.so` 13 MB + `_ui.so` 16 MB + modgui + resources ✅ |
| 试运行 | 起来了。报 `Failed to load JACK DLL` —— **不是错误**：headless 环境没有音频服务器，程序初始化后优雅退出（exit=0）✅ |

> ⭐ **最大的好消息**：**GCC 15.2.0 一个真错误都没报**（只有警告）。
> 此前最担心的「新编译器挑老代码的刺」**没有发生**。

**内存实测**：`-j8` 编 mini 峰值仅 **约 900 MB**（11 GiB 上限下毫无压力）。

---

# 第 7 步：全量编译 —— ✅ 完成（2026-09-20 17:12，用时 209 秒）

**结果 —— 一次通过：**

```
退出码    : 0
用时      : 209 秒（3 分 29 秒）
真实错误  : 0
编译模块  : 1931 个源文件
BUILD_OK
```

> ⚡ **远快于预期**（原估 15–30 分钟）。原因：24 核 + `-j12` + 模块多为小编译单元。
> **修正认知：在这台机器上，Cardinal 全量编译是「分钟级」，不是「小时级」。**

**产物（`$HOME/Cardinal/bin/`）—— 全套插件格式都编出来了：**

| 产物 | 大小 | 说明 |
|---|---|---|
| `Cardinal` | **97 MB** | 独立版主程序（静态链入全部模块） |
| `CardinalNative` | 97 MB | 原生版 |
| `Cardinal.lv2` / `.clap` / `.vst` / `.vst3` | — | 四种插件格式 |
| `CardinalFX.lv2` / `.vst3` | — | 效果器变体 |
| `CardinalSynth.lv2` / `.vst3` | — | 合成器变体 |
| `CardinalMini` + `.lv2` | 16 MB | mini 版 |

**健康度**：`ELF 64-bit` / 未解析动态库 **0** / 880 个动态符号 / 试运行正常。

> ⭐ **一个意外的强验证**：编译过程本身**真的运行了 Cardinal** —— LV2 TTL 生成阶段
> 它创建了窗口、场景、引擎，加载了 SVG 资源，列出了 `DISTRHO Host MIDI/Time/Parameters`
> 等模块控件，然后优雅销毁。**GUI/GL 层确实能跑**，这比 `file`/`ldd` 更有说服力。

**⚠️ 产物性质**：以上是 **Linux 版（路线 A）**。要替换李现有的 **Windows** Cardinal 26.02，
必须先走**路线 B（PawPaw 交叉编译 → Windows DLL/EXE）**。

> **`make` 默认目标 = `all`**：`cardinal carla deps dgl plugins gen resources`，
> 即「Cardinal 本体 + Carla + 全部依赖 + **1400 多个模块**」一次编完。
>
> **并行度**：先从 `-j8` 起步，稳了再往上加。**不上一来 `-j24`** ——
> 官方 CI 里两处写着 `-j 1` + 注释 `otherwise we might get killed due to OOM`。
> 我们的内存上限现在是 11 GiB（`.wslconfig` 限的），更要留神。

---

# 第 8 步：产物取回 Windows —— ⏸ 待编出产物

> **关键待确认：编出来是 Linux 版还是 Windows 版？** 两条路产物完全不同：

| 路线 | 怎么编 | 产物 | 在哪跑 |
|---|---|---|---|
| **A. 原生 Linux 版** | WSL 里直接 `make` | Linux 格式 | **在 WSL 里跑** |
| **B. Windows 交叉编译** | PawPaw 配环境后编 | Windows `.dll`/`.exe` | 复制到 Windows 替换现有 Cardinal |

> **建议先用 A** —— 简单、快、编完立刻能看到结果，用来验证"环境通了、我改的代码生效了"。
> 确认无误再上 B，那才是能替换你现有 Cardinal 的正式产物。

---

## 附：WSL 资源配置（`<USERPROFILE>\.wslconfig`）

2026-09-20 创建（李同意）。**三个已核实的要点：**

```ini
[wsl2]
memory=12GB                 # 默认是宿主的 50%(约15.7GB)，压到 12GB 给 Windows 留余量
swap=8GB                    # 默认 4GB → 8GB，兜编译时的内存尖峰

[experimental]
autoMemoryReclaim=gradual   # 默认 dropCache(立即清缓存)，改成温和回收
```

1. **`autoMemoryReclaim` / `sparseVhd` 属于 `[experimental]` 段，不是 `[wsl2]`。**
   写在 `[wsl2]` 下会被**静默忽略**（我一开始就写错了，查官方文档才发现）。
2. **`sparseVhd=true` 只对「新建」VHD 生效** —— 我们的 `ext4.vhdx` 已经存在，
   所以**没写进配置**（写了不生效只会误导）。现有盘要缩容得用：
   `wsl --manage Ubuntu-26.04 --set-sparse true`
   （语法已用 `wsl --help` 实测确认：`--set-sparse, -s <true|false>`）
3. **注释全用 ASCII** —— 部分 WSL 版本对本文件的非 ASCII 字节解析会出错。
   实测：非 ASCII 字节 **0**、**无 BOM**、1582 字节。

**生效方式**：`wsl --shutdown`（会关掉所有 WSL 实例，**别在长任务跑着的时候做**）。
**验证结果**：内存上限 15 GiB → **11 GiB**（配 12GB，内核自身占一部分）；
swap 4 → **8 GiB**；24 核未动。

**基线**：`D:\WSL\Ubuntu-26.04\ext4.vhdx` = **5.92 GB**（2026-09-20 17:05，编译前）。

---

## 附：为什么是这个顺序（设计说明）

李的核心诉求是「**把编译这件不熟的事先做掉，降低心理风险**」。所以手册的设计是：

1. **每一步都可独立验收** —— 做完立刻知道对错，不带病前进
2. **把"验证"前置到第 6 步** —— 用小任务探路，而不是直接压上全量编译
3. **风险全部可逆** —— 任何一步炸了都能干净回退
4. **官方 Cardinal 全程不动** —— 随时有"回到熟悉状态"的退路

> 这个顺序本身也是**可复用的方法论**：面对不熟的复杂系统，
> **先设哨兵、再上主力**，而不是一路莽到底。
