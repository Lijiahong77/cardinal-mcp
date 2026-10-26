# OSC 改动重放 · patch 是唯一真相

> **2026-10-26 最终交付更新**：native17 已经许可构建/部署，当前事实、SHA、有限实机范围和待验项见 [DELIVERY-2026-10-26.md](../../docs/DELIVERY-2026-10-26.md)。下方“未部署”为集成当时记录。统一离线复跑使用 `python -B tools/run_safety_regression.py --out <仓库外新目录> --tmpdir <仓库外scratch> --wsl-source <WSL固定对象源码根> --jansson-include-dir <Linux开发头目录>`（从仓库根）；当前前提是 Windows + Ubuntu-26.04 WSL、python-osc/zstandard、g++ C++11/Jansson，不缺省 skip。头目录必须含 `jansson.h` 和 `jansson_config.h`，来自合法开发包/已配置依赖树；也可用进程级 `JANSSON_INCLUDE_DIR`，无配置/缺头必须失败，无旧 lab 默认回退。Windows 到 WSL 以独立 `env` argv 显式传值，不改全局环境。入口显式 15 suite，最后 295 唯一方法；不执行盲 discover，socket veto 在产品/测试导入前（不冒充 native 子进程网络/认证审计）。输出参数、可替换的本机头目录示例、standalone 命令、固定对象和 fixtures 来源详见交付页。

> 建立：2026-10-21 · 当前恢复契约：17 组 patch、33 个 OSC 端点；包含 SongRoll、rackwindows near/far 构建兼容、参数健壮性、SongRoll history/UI及停止首段规则。01–17 代码交付为 338a955，native17 已许可部署；以下阶段“未部署”保留原历史，当前验收边界见交付页。新增/修改文件是否已提交仍须另看 git status。

**测试入口：[TESTING.md](TESTING.md)**。区分生产恢复 patch、持久 fixtures、param/history/stopfirst 提取壳与第三方 reference；它们不是可直接运行的生产插件。文档总导航见 [docs/README.md](../../docs/README.md)。

---

## 一、为什么有这份东西

在 2026-10-21 之前，本项目对 Cardinal 源码的改动**只存在于 WSL 工作区**（`/home/lijia/Cardinal`），
**不在任何 git 仓库里**。后果：

- 一次 `git checkout .` ⇒ **30 个端点的实现全没了**（约 2100 行）。
- `src/override/MenuBar.cpp` 的「延后 120 帧自动开 OSC」补丁
  **不在任何注入器里** ⇒ 连「重跑注入器」都救不回来。
- 企划 2 的自建插件包 `plugins/Starsea/`（MiniArranger，10 个文件 2549 行）同样是未跟踪文件，
  一次误删就没了。

现在：改动的**真相**以 `patches/*.patch` 的形式存在本仓库（`Lijiahong77/cardinal-mcp`），
由 `replay_osc.py` 重放回源码树。

---

## 二、目录结构

```
tools/osc_patch/
├── README.md                    ← 本文件
├── replay_osc.py                ⭐ 统一重放脚本（唯一入口）
├── patches/                     ⭐ 改动的真相（git 跟踪）
│   ├── 01-osc-core.patch          28 端点实现 + 注册 + MenuBar + 截图落盘
│   ├── 02-rack-osc.patch          Rack 子模块：oscLoadActive + fromJson 条件化
│   ├── 03-build-env.patch         构建环境：Starsea 注册 + Makefile + immintrin + 删 lv2export
│   ├── 04-starsea-plugin.patch    Starsea 插件包（10 个文件，新增）
│   ├── 05-b2-cables-page.patch    B2 /cables-page 分页端点（handler + 注册）
│   ├── 06-b3-module-copy.patch    B3 /module-copy 复制模块（handler + 注册）
│   ├── 07-c6-write-endpoints.patch C6 写端点修复（4 端点手动执行化）
│   ├── 08-c3-log-get.patch        C3 日志环形缓冲 + /log-get（含 Rack logger）
│   ├── 09-c2-load-skipped.patch   C2 /load skipped 收集器 + /load-skipped
│   ├── 10-module-add.patch       M1 /module-add（按 slug + 格坐标加模块）
│   ├── 11-songroll-build.patch    SongRoll 复活·注册链（Makefile wildcard + addModel）
│   ├── 12-songroll-module.patch   SongRoll 模块本体（引擎 + UI Rack 2 移植 + 胶文件）
│   ├── 13-songroll-panel.patch    SongRoll 新面板（res/SongRoll.svg 重画 600×380）
│   ├── 14-rackwindows-nearfar.patch rackwindows：条件 undef near/far（应用根 plugins/rackwindows）
│   ├── 15-param-write-safety.patch 参数边界及 OSC/JS 生命周期锁（应用根为空：main）
│   ├── 16-songroll-history-ui.patch SongRoll 完整history快照及UI权威数据（应用根 plugins/rcm-modules）
│   └── 17-songroll-stopfirst.patch SongRoll 编辑/载入/undo-redo停止首段、同步及event取消（应用根 plugins/rcm-modules）
├── inject_osc_read.py           ┐
├── inject_osc_b.py              │
├── inject_osc_c.py              ├─ 历史记录：记录每个批次当初改了什么
├── inject_osc_d.py              │  （**不再是重放路径**，见 §五；已知坑见
├── inject_osc_e2.py             │  `injectors-LEGACY-NOTES.md`）
├── inject_osc_e3.py             ┘
├── osc_read_handlers.cpp.inc    ┐
├── osc_read_b_handlers.cpp.inc  ├─ 各批次的 handler 源码片段
├── osc_ops_c_handlers.cpp.inc   │  （阅读价值，patch 里已含最终形态）
└── osc_js_handlers.cpp.inc      ┘
```

---

## 三、怎么用

### 3.1 日常：不要为验证而重放现役 dirty 树

本链的代码交付与 native17 本地部署已完成，详见页首交付记录；不据此推断任何 dirty 上游工作树都等同已恢复基线。日常无需为“验证一下”改写现役源码或加载机架。下方 §3.4–3.6 的“未部署”等是集成当时记录，不覆盖当前结果。

### 3.2 恢复入口：先备份并显式确认目标，勿清理现役 dirty 树

```bash
# 在已人工构造、核对固定对象的独立恢复树上执行；替换为已获准的真实路径。
export CARDINAL_ROOT=/path/to/isolated/source
export CARDINAL_PATCH_DIR=/mnt/d/Cardinal/tools/osc_patch/patches
python3 -B /mnt/d/Cardinal/tools/osc_patch/replay_osc.py --check
# --check 仅针对当前树逐组检查，不模拟前置补丁，不能代替完整顺序重放。
# 确认目标/备份与执行授权后，无参数才会真正写源码：
python3 -B /mnt/d/Cardinal/tools/osc_patch/replay_osc.py
# 只读诊断清单：
python3 -B /mnt/d/Cardinal/tools/osc_patch/replay_osc.py --verify
```

全链 apply 成功后仅追加 **33 个端点 + 当前 VERIFY_MARKS 清单（36 项）**诊断；`--verify` 不认证完整 patch、源码字节、恢复、构建、运行或听感。14、15、16、17 不新增认证标记、不改端点数。参数只允许无参数或单个 `--check` / `--verify` / `--help` / `-h`，其他组合在任何目标操作前以 rc=2 拒绝。

### 3.3 在干净副本上做可复现验证

必须从以下四仓库固定 Git tree/blob 对象构造**全新隔离树**，保留文件 bytes、可执行 mode、symlink 与 gitlinks；不要复制 dirty 生产源码、不要复用已 applied lab，也不要共享生产 worktree/index/object store。`git archive` 会受 export-ignore/export-subst 影响，不能替代逐 blob OID/mode 校验。

| 仓库/应用根 | 固定恢复 commit |
|---|---|
| main | `8aa0fc7552c80c464b8f1f87c3199ab3dfe4e40b` |
| `src/Rack` | `8c6f41b778b4bf8860b89b36d5503fd37924077f` |
| `plugins/rcm-modules` | `c4a243ec7089254aa19225c0666bb4bda2163a6a` |
| `plugins/rackwindows` | `60dfe5dff94b82fc42a43d971e41e64e296b0220` |

每个应用根须有**自身**有效 `.git`/gitfile，真实顶层必须等于该根；普通子目录继承父仓库不合格。隔离 fixture 可人工建立独立元数据并核 tree OID，但 fixture commit 不是原 commit 身份。脚本不自动 init/add，也不核 HEAD 固定 SHA 或完整文件 hash，故真实验收须另核对象、pre/post bytes、old/new union 全路径以及 mode/删除/rename。仅取恢复所需四仓库不等于完整可构建依赖树。

14 固定 `src/rwlib.h` pre SHA256 为 `52ead73b28a7f6305c0360793040a7cf403d425032affea1f9e729de0d64868d`，post 为 `6b6bbd83e978db09e1121db3c5a800bc2994802781fd91f926f8c93ab33681a1`；仅取消已定义的 near/far 宏，不改变 DSP 算法，不能阻止后续头重新定义。错误 SHA 但 hunk 匹配不等于通过固定基线验收。

---

### 3.4 第15组参数健壮性（未部署）与离线复跑

`Engine_writeParamById` 是 OSC/JS 控制入口：不能已持 Engine 锁；lookup、边界检查、display虚转换及写入在同一生命周期锁内完成。旧指针式API仍不加锁，依赖既有线程/所有权契约；并非全面线程安全，也不保护非法直接delete或Engine并发析构。未来可达ParamQuantity override若调用加锁Engine接口须重审锁顺序。持锁执行自定义转换/远端lo_send可能延长DSP等待，延迟/爆音未验收。

raw保持无回执、不新增clamp；display保持原虚转换、错误码及锁外history push。raw NaN/Inf与display NaN政策未变，不能推论所有插件对非有限值都安全。本次只集成恢复链，未改现役C++/EXE/resources，未部署、未启动或加载机架；以前的两个真实TU对象编译不等于本轮完整链接。

15的基线严格为§3.3四固定对象完整应用01–14后：Common pre `c365c8cb27c3f22a081f5a6aa1f2a7ebddb9073ef15e5dc69ec30e27362609f7`，Engine pre `5fd2fdf78a45d847bf4ef10d88123800f132055ffde27df97a0ff2c625ac8a33`；header原不存在。patch SHA256 `51639209029a95a0fcd112dcd1195532a060bb086354b38ceedb74262ea3fe30`。post Common `e1c21935deee6190e4fdd28560a3f234c6681e492d09e3072f08e9a458ada300`，Engine `28e85b60cdf7be0ee364327e1efa213019f2033d43ad6cdd69598deff9e004f3`，header `73e104be6be7f4dc23e405d7e32054ffa6232fd34864d2fb747485e9e0f285e9`，三文件mode均100644。

持久测试：`test_replay_param_safety.py`复用现有独立Git fixture idiom；`fixtures/param-safety-after14.json`封装真实14后两源码（gzip/base64，解压后固定hash校验），不依赖24小时scratch。此fixture来自已验证14lab，新15集成再次从固定对象全链生成并核pre相等，不复制dirty现役树冒充基线。正常Windows离线运行：在本目录使用已配置Python `-B -m unittest -v test_replay_param_safety test_replay_compat test_replay_safety`。

C++56场景及独审10组的原提取harness已持久化到 `param_safety_harness/`，未重写候选C++。在WSL、已授权的独立15后lab上复跑（输出目录必须全新、持久、与源码分离；不连接软件）：

```bash
python3 -B /mnt/d/Cardinal/tools/osc_patch/param_safety_harness/run_56.py /path/to/isolated/after15 /home/lijia/param-regression-unique/56
python3 -B /mnt/d/Cardinal/tools/osc_patch/param_safety_harness/run_review_10.py /path/to/isolated/after15 /home/lijia/param-regression-unique/review10
```

需要本机g++、pthread、ASan/UBSan；输入lab含固定Rack源码。生成/编译/执行只在指定输出目录，不能传现役源码为输出。reference中保留审查使用的真实history.cpp与AddrSeq.hpp（来自此前成功buildlab，按原提取方式使用），不是新生产源。56是场景数、10是补测组数，**不重复计入unittest方法数**。壳限制保留：56的getValue非虚、history仅计数、默认线性metadata；10组补充真实undo/redo、虚getValue、量纲/snap与AddrSeq内层锁，但仍非GUI/liblo/QuickJS/完整插件运行认证。

### 3.5 第16组 SongRoll history/UI（未部署）

`16-songroll-history-ui.patch` 精确复用独审候选，SHA256 `9a005a3a850c0b9cbb3c55e44f650d4f1269d06fe7b63817cfade44355488b73`。基线为四固定对象完整应用01–15后，应用根 `plugins/rcm-modules`。只改 `src/SongRoll/` 下 PatternControlWidget.cpp、RepeatControlWidget.cpp、ClockDivControlWidget.cpp、PatternControllerSlice.cpp：完整 Module JSON history 快照、每step单向data→display，以及点击时读取权威数据。无新端点/布局/端口/DSP或播放规则改动。

**仅到第16组的历史恢复副作用（不是01–17规则）：**快照包含 running/currentSection；当时 restore 经 dataFromJson→enterSection 重置 repeatsLeft 和该段进度并刷新输出，可能恢复历史运行标记与段位，不精确恢复剩余拍数，缺currentSection的既有分支不改。第17组明确替代这一运行恢复规则，见§3.6；完整Module快照本身仍保留。完整快照/共享锁/串行测试不构成线程安全证明。

仅恢复链集成；未改现役源码/EXE/resources，未部署，未启动/操作当前Cardinal，未完成Native链接、真正GUI或音频试听。

持久测试复用 `test_replay_songroll_history_candidate.py` 的29个方法（其中22个真实提取C++场景已包含在29内，不能重复累计）；原方法ID保留，候选文件名不注册、正式16唯一第16项且bytes相等。`test_replay_songroll_history_integration.py` 的2个方法保留。原16历史runner记录236个唯一方法，不覆盖17；历史测试仍验证16独立fixture的运行恢复规则，不能用17规则删除旧回归。真实Jansson及C++11/ASan/UBSan壳限制同候选报告，并非真实Rack窗口或音频并发验收。

```bash
# WSL 离线串行C++复跑，输出必须使用新的隔离目录：
python3 -B /mnt/d/Cardinal/tools/osc_patch/songroll_history_harness/run.py --out /path/to/new/serial-history-output --jansson-include-dir /path/to/jansson-development/include
```

### 3.6 第17组 SongRoll 停止首段规则（未部署）

`17-songroll-stopfirst.patch` 精确采用B1复审passed候选bytes，SHA256 `3a76957569a39344f8e322a2f72e4dded607587ad42aedcbb210630d2c8ec3a4`，根 `plugins/rcm-modules`，基线为四固定对象完整应用01–16后；只改七个既有源码，不改01–16 payload、replay函数、36个VERIFY_MARKS或33端点。

用户规则：所有编辑/替表、非null完整或partial load、undo/redo均停止推进并回第一段从段头计数，需手动RUN；完整history仍保存Module JSON，但不恢复历史running/currentSection。旧高RUN/EOP必须先low再new rise。null data为no-op；Module根本没有data不调用dataFromJson。RESET输入仍仅回首段而不强停正常running，正常RUN toggle、FREE/LIMIT及pattern `(pattern-1)/12` 保留。

每实例recursive_mutex保护UI/JSON配置/runtime，DSP try_lock失败不读配置/vector。只读争锁冻结event电平及pulse计时，避免制造低缝；真实编辑在锁内清pulse并原子发布取消，失败DSP不消费取消，成功持锁样本消费取消。UI不写outputs，不引入模块锁→Engine反锁；依赖原有单实例非重入process契约，不是普遍线程安全保证。

边界：只读长锁可延长脉宽、冻结PATTERN/SECTION_NUM并漏短输入边沿；取消发布前已在途的旧sample可以完成旧高，编辑返回不保证所有端口瞬间0。release/acquire不规定第N个失败sample可见性时限，两event端口不是跨端口原子事务。不保证硬实时，也不停止PianoRoll/键盘或保证下游静音。

显式offline矩阵为既有294＋1个最小集成方法＝295唯一方法：236原回归＋58 stopfirst方法＋1注册契约。58已包含52真实提取C++场景和6 artifact方法，不再加52；TSan17场景及额外probe另列分层，不灌入unittest计数。runner `audit/songroll_stopfirst_integration_tests.py` 在测试导入前安装Python socket veto，loader errors=0，禁止-O，缺前提不skip。原B1失败证据保留。

仅恢复链集成；未写现役C++，未构建EXE、链接full Native、部署、启动或操作当前软件、GUI、音频/下游实测。此前8个完整生产TU对象与本轮提取壳也不等于full Native验证。完整重放及保护证据见工作区 `audit/songroll-stopfirst-integration.md`。

## 四、patch 的基线

| patch | 基线 | 说明 |
|---|---|---|
| `01-osc-core.patch` | Cardinal `8aa0fc7`（"Fix build"） | 主树 |
| `02-rack-osc.patch` | Rack `8c6f41b778b4bf8860b89b36d5503fd37924077f` | ⚠️ 路径**相对子模块根**（`include/settings.hpp` 而非 `src/Rack/include/settings.hpp`）⇒ 必须在 `src/Rack/` 里 apply |
| `03-build-env.patch` | Cardinal `8aa0fc7` | 含一个**文件删除**（`lv2export/plugins/aubileinstruments-macro-osc-2.cpp`） |
| `04-starsea-plugin.patch` | Cardinal `8aa0fc7` | 纯新增（10 个文件） |
| `05-b2-cables-page.patch` | Cardinal `8aa0fc7` + 01-04 应用后 | B2 `/cables-page` 分页端点（handler + X-macro 注册） |
| `06-b3-module-copy.patch` | Cardinal `8aa0fc7` + 01-05 应用后 | B3 `/module-copy` 复制模块（handler + X-macro 注册） |
| `07-c6-write-endpoints.patch` | Cardinal `8aa0fc7` + 01-06 应用后 | C6：`/cable-add` `/cable-remove` `/module-move` `/module-remove` 修成「手动执行 + push 记录」+ `/module-move` 格→px 单位换算 |
| `08-c3-log-get.patch` | Cardinal `8aa0fc7` + 01-07 应用后 | C3：`src/CardinalCommon.cpp`（`/log-get` 端点）+ `src/Rack/src/logger.cpp` + `src/Rack/include/logger.hpp`（进程内日志环形缓冲，2000 条） |
| `09-c2-load-skipped.patch` | Cardinal `8aa0fc7` + 01-08 应用后 | C2：`src/override/Engine.cpp`（**Cardinal 真正编译的 Engine 副本**）+ `src/Rack/include/engine/Engine.hpp` + `src/Rack/src/patch.cpp` + `src/CardinalCommon.cpp`（`/load` skipped 收集器 + `/load-skipped` 端点） |
| `10-module-add.patch` | Cardinal `8aa0fc7` + 01-09 应用后 | M1：`src/CardinalCommon.cpp`——`/module-add "sii"`（plugin\|model slug + 格坐标 → 手动执行加模块 + push 记录可 undo）+ 顺带修 JS `cardinal.addModule` 的 push-only 缺陷 |
| `11-songroll-build.patch` | Cardinal `8aa0fc7` + 01-10 应用后 | SongRoll 复活·注册链：`plugins/Makefile`（SongRoll wildcard）+ `plugins/plugins.cpp`（`addModel(modelSongRollModule)`） |
| `12-songroll-module.patch` | rcm-modules 子模块 HEAD `c4a243e` | SongRoll 模块本体（**应用根 `plugins/rcm-modules`**）：`.cppx`→`.cpp` 复活 + Rack 2 API 修 + 阶段2 引擎（10/11 端口、EOP 推进、JSON）+ 阶段3 UI 移植 + 胶文件 |
| `13-songroll-panel.patch` | rcm-modules 子模块 HEAD `c4a243e` + 12 应用后 | SongRoll 新面板（**应用根 `plugins/rcm-modules`**）：`res/SongRoll.svg` 重画 600×380（旧 Inkscape 面板整file替换），端口圆圈图案与真 PortWidget 坐标一一对应 |
| `14-rackwindows-nearfar.patch` | rackwindows `60dfe5dff94b82fc42a43d971e41e64e296b0220` | 应用根 `plugins/rackwindows`；`src/rwlib.h` 条件 undef near/far；追加于13之后，不改01–13 payload |
| `15-param-write-safety.patch` | 上述四个固定对象完整应用01–14后 | main根（空字符串）；仅 `src/CardinalCommon.cpp`、`src/override/Engine.cpp`、新增 `src/ParamWriteSafety.hpp`；不改01–14 payload |
| `16-songroll-history-ui.patch` | 上述四个固定对象完整应用01–15后 | `plugins/rcm-modules` 根；仅上述四个UI源码；不改01–15 payload |
| `17-songroll-stopfirst.patch` | 上述四个固定对象完整应用01–16后 | `plugins/rcm-modules` 根；七个既有源码；不改01–16 payload |

⚠️ **upstream 变了 patch 可能失效**。届时 `git apply --check` 会明确报冲突，
脚本**立刻停下**（绝不 `--reject` 硬塞）—— 需人工看差异。

---

## 五、为什么用 patch 而不是那 6 个注入器

1. **注入器覆盖不全**。E1 的 `cardinalOscReply` helper（`src/CardinalCommon.cpp:406`）
   和 `MenuBar.cpp` 的自动开 OSC 补丁**都不在任何注入器里** ⇒ 跑完 6 个注入器也凑不出现在的树。
   （实测：patch 重放后 22/22 文件与现状**逐字节一致**。）
2. **注入器依赖「唯一锚点」匹配**，upstream 一改锚点就失效；patch 靠行号 + 上下文，
   冲突时 git 明确报错而不是静默插错位置。
3. **patch 可审计**：是纯文本 diff，能在 PR 里逐行 review、能 `git apply -R` 回滚。

⇒ 6 个注入器**保留但降级**为「历史记录」：它们记录了每个批次当初改了什么、有哪些设计教训
（血泪注释），有阅读价值，但**不再是重放路径**。

---

## 六、🔴 三个踩过的坑（写在这里免得重犯）

### 6.1 `git apply` 在非 git 目录里会「静默跳过」

Rack 是 git 子模块。在「干净副本」里它可能只是个普通目录（没有 `.git`）⇒
`git apply` 把它当 gitlink，输出 `Skipped patch 'include/settings.hpp'` 并**返回 0（假装成功）**。

**⇒ 现行脚本拒绝没有自身有效仓库的应用根，不自动初始化/暂存。** 各阶段任一输出流出现跳过/路径筛选均当失败，即使 rc=0；不允许继承环境 GIT_* 把目录绑定到别的仓库。Git 命令级固定空白/换行策略，不改全局或用户配置，不使用 reject/3way/忽略空白绕过。

### 6.2 幂等判据不能用报错文本

`git apply` 对「已经应用过」和「真冲突」报**同样的** `patch does not apply`。
靠文本判断会把「已应用」误报成「冲突」。

**⇒ 正向失败仅在严格反向检查成功且无跳过/路径筛选时才 skipped。** 不凭文件存在/标记成功。后续叠加可能使早期组不可反证，届时保守停止，不代表应该重新应用；不承诺整链第二次运行全部跳过。首个 conflict/unknown/意外状态即停止，列出已完成/失败/未尝试，不自动回滚。

### 6.3 E3 之后端点数不能数 `add_method`

E3 把端点注册改成 X-macro `REG("/path", "types", handler)`，
不再是一行一个 `lo_server_add_method(...)`。
**⇒ 数 `REG("` 开头（且排除 `#define REG(` 那一行）；当前期望是 33。**

---

## 七、历史状态（2026-10-21/22 记录，不代表当前严格恢复契约验收）

以下旧 10 组/幂等/部署记录仅为历史；当前17组须独立首次完整apply并核bytes。`--verify` 清单通过不得替代该验收。

| 验证项 | 结果 |
|---|---|
| 干净 upstream 副本上重放 | ✅ 10 组全部应用（01-04 实测；05-10 见下） |
| 应用后端点数 | ✅ **33 / 33** |
| 关键标记 | ✅ 29 项全齐 |
| **与 WSL 现状树逐字节比对** | ✅ **22 / 22 一致，0 不一致**（含 Starsea 10 文件 + 1 个删除文件状态） |
| 幂等重跑 | ✅ 10 组全部「已存在」跳过，**零破坏**（真实树 git status 前后完全一致） |
| 在真实 WSL 树上跑 | ✅ 零破坏（17 项改动状态不变） |
| **B2 patch（2026-10-21 下午）** | ✅ 反打当前树 + 正打 before 副本**双向** `git apply --check` 通过；WINE 探针 **11/11**；MCP 层端到端 **8/8**；exe 已部署（MD5 `32d3cfbc…`） |
| **B3 patch（2026-10-21 下午）** | ✅ 双向 `git apply --check` 通过；WINE 探针 **12/13**（唯一 FAIL 是 T8：既有 `/cable-add` 不生效的实锤，非 B3 问题）；MCP 层端到端 **7/7**；exe 已部署（MD5 `751cdaea…`） |
| **M1 patch（2026-10-22 早上）** | ✅ 双向 `git apply --check` 通过；WINE 探针 **10/10**（41→42 模块、undo/redo 闭环、未知插件/未知型号/无分隔符三种错法全 `err:E_NO_MODEL`、失败调用零副作用）；MCP 层端到端 **5/5**；exe 已部署（MD5 `2c2ce802…`）。🔴 坑：typespec 必须与参数顺序一致（`"sii"` 不是 `"ssi"`，不匹配 ⇒ liblo 不派发 ⇒ 端点全哑）；🔴 `loadTemplate()` 不能在 OSC 侧调（人类路径独有，preset 应用碰 UI ⇒ undo 后 OSC 失联） |
| **C2 patch（2026-10-22 早上）** | ✅ 双向 `git apply --check` 通过（4 文件段：override/Engine.cpp + Rack Engine.hpp/patch.cpp + CardinalCommon）；WINE 探针 **6/6**；MCP 层端到端 **5/5**（损坏 patch ⇒ 1 module + 16 cable = 17 条 skip，逐条 reason 齐）；exe 已部署（MD5 `bf55806b…`）。🔴 关键点：**Cardinal 编译的是 `src/override/Engine.cpp` 而非 Rack 原版**（改错文件 ⇒ 链接期 undefined reference） |
| **C3 patch（2026-10-22 早上）** | ✅ 双向 `git apply --check` 通过（3 文件段：CardinalCommon + Rack logger.cpp/hpp）；WINE 探针 **8/8**（最老读/增量不重叠/非法参数/limit 64/超界 from）；MCP 层端到端 **5/5**；exe 已部署（MD5 `d17ab013…`）。⚠️ Rack 层改动 ⇒ 需 `make rack.a` 重编 |
| **C6 patch（2026-10-21 深夜）** | ✅ 双向 `git apply --check` 通过；WINE 探针 **14/14**（4 端点全部真实生效 + undo/redo 闭环 + B3 回归）；MCP 层端到端 **7/7**；exe 已部署（MD5 `836aea28…`）。🔴 附带修掉 `/module-move` 单位语义 bug（文档说格、实现当 px，差 15 倍——该端点此前从不生效故零兼容负担）；🔴 module-move 的位置真值 WINE 下不可直验（autosave 周期落盘在 WINE 不触发，已实验证实）⇒ 归真机 A1 |

---

## 八、相关文档

- 当前交付/构建前提：[DELIVERY-2026-10-26.md](../../docs/DELIVERY-2026-10-26.md)
- 测试目录导航：[TESTING.md](TESTING.md)
- 接手历史：[HANDOFF.md](../../HANDOFF.md)；唯一待办：[TODO-BACKLOG.md](../../docs/TODO-BACKLOG.md)
- MCP 侧真实工具表：[cardinal_mcp.py](../cardinal_mcp.py)（64 个工具，TOOLS/DISPATCH）
