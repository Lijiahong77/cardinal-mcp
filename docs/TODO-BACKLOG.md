# 待办总表 · 统一开工用

> 建立：2026-10-19 · **最后更新：2026-10-20 17:05**
>
> **当前状态（别再看旧结论）：**
> - 批次 A（A1–A11）✅ 全部完成
> - 批次 B（B1–B5）✅ 完成 · C 组 ✅ 完成 · F 组 QuickJS ✅ 完成 · D 组（D1/D2）✅ 完成
> - **剩余：E 组（三段式响应 ✅ / 分页 ✅ / 注册表抽函数 ⏳）**、`.mid` 导出、段落编排规格
> - 开工入口 → 根目录 `HANDOFF.md`（状态 + 命令）；本文件只管「还有什么没做」
>
> 用途：把所有待办集中在这里。开工时按「批次」推进，每批做完整再进下一批。

---

## 一、当前资产（已完工，不是待办）

**MCP 工具 53 个**（`tools/cardinal_mcp.py`，截至 2026-10-20 D 组完工）
- 原有 17：连通/存档/按编号操作/音乐配方/5 个未编译探针
- 10-19 白天新增 13：4 个模块检索 · 1 个接线拓扑 · 3 个序列器音符 · 4 个采样槽 · 1 个交互索引
- 批次 A 新增 6：`set_param_by_name` · `cardinal_audit` · `cardinal_deploy`+`cardinal_diff` · `cardinal_port_semantics` · `cardinal_export_abc`
- 批次 B 第一批新增 5：`build_info` · `cables` · `transport` · `engine_info` · `plugins`
- 批次 B 第二批（C 组 + QuickJS）新增 11：`param_set_by_display` · `cable_add` · `cable_remove` · `undo` · `redo` · `module_json` · `module_remove` · `module_move` · `midi_out` · `js_run` · `js_list`
- D 组新增 1：`cardinal_screenshot`

**新写的 Python 模块**（`tools/`）
| 文件 | 作用 |
|---|---|
| `modbrowser.py` | 查本机 1407 个模块 / 85 品牌 / 104 标签（读 Cardinal 的 PluginManifests） |
| `topology.py` | 读机架接线 + 角色识别 + 信号能否到达主输出 |
| `seq.py` | 读写序列器音符（pianoroll / MiniArranger，规则相反） |
| `samplelib.py` | 采样槽装载（= 人右键 Load sample） |
| `interaction_map.py` | 23 个「人类可做的操作」索引 + 源码落点 |
| `rackgen.py` | 生成器 DSL（批次 A 提炼，血泪注释逐字保留；存量 12 个 make_* 不迁移） |
| `abc_export.py` | 序列器音符 → `.abc` 文本乐谱（rcm 稠密 + Starsea 稀疏两路线） |
| `style_schema.py` | 风格 schema 校验 + 机架实测回填 |

**文档**
- `docs/HUMAN-INTERACTION-MAP.md`（584 行，人类操作→源码函数映射）
- `docs/CARDINAL-MCP-SPEC.md`（540 行，✅ A5 已修：头部路径约定 + H9 重写）
- `docs/CARDINAL-MCP-CAPABILITY-MAP.md`（688 行，✅ A5 已修：行号标路径，override 版行号实锤修正）
- `docs/STYLE-SCHEMA.md`（A11：风格 schema 字段定义 + life1/hana 实测样板）

---

## 二、待办批次

### 批次 A · 零编译，立刻能做（不碰 Cardinal 源码）

| # | 事项 | 说明 | 依赖 |
|---|---|---|---|
| A1 | `set_param_by_name` | 按名字设参数，**必须拒绝 `kind=="reserved"` 废弃槽**（VCF 1 号、Clocked 14 号）——设进去不报错但没效果 | 无 |
| A2 | `cardinal_audit` | 聚合 5 个审计脚本（ports/values/flow/chain/validate）成一个工具 | 无 |
| A3 | `cardinal_deploy` + `cardinal_diff` | 生成→加载→**读回比对**的闭环。🔴 **死锁，见 E8** | 无 |
| A4 | `cardinal_port_semantics` | 端口语义表（哪个口是 gate/pitch/audio）。**前置：扩 `paramlib` 加 InputIds/OutputIds 抽取**（它已在解析同一 enum 块，只是丢弃了非 ParamId 部分） | 无 |
| A5 | ~~修两份规格文档的已知错误~~ ✅ 完成 | ① H9「约 3 行回传 warningLog」判断错误 —— `Makefile:46` 用 `override/Engine.cpp` 替换原件，而 override 版里 `patch->log()` **两行被注释掉** ⇒ warningLog 恒为空，改 3 行仍读到空。正确是**两处**：恢复 override 两行 + 加 `lastLoadWarnings` 字段。② 全文档 `Engine.cpp/Window.cpp` 行号**未标路径**，读的人会读错文件（编译生效的是 `src/override/` 版） | 无 |
| A6 | ~~`cardinal_find_module` 增强~~ ✅ 完成（E10 落地）| modbrowser.py 成为唯一检索入口：内置中文词表 ZH_VOCAB（40+ 词，来自 modsearch.ROUTES 实测校准，「古筝」→plucked+resonator 命中 Rings 第 1）+ 新增终端 CLI（search/tags/brands/detail）；modsearch.py 降级为速查表 CLI（routes 保留）；SONG-TO-PATCH-WORKFLOW.md 已标「已并入本表」 | 无 |
| A7 | ~~`tools/rackgen.py`~~ ✅ 完成 | 已提炼：cable/mod/clone/note/track/Row/save + place/LAYOUT（布局主权归李）+ midi/build_notes/pattern + sanitize/_guard（血泪注释逐字保留）。验收 8 项全绿：与 make_quadeca(_auto) 原实现逐字段等价、悬空面包屑清除、空色值清除、同口多线拦截、Mix8 MUTE 拦截、save 写 tmp 回读。测试在 `tools/_test_rackgen.py`。**存量 12 个 make_* 不迁移**（已验收，宪法：改错比不改更糟）；新机架一律走 rackgen | 无 |
| A8 | ~~修 `apply_recipe` 的 `mods[0]` 缺陷~~ ✅ 完成 | 🔴 `musiclib.py:544` 是 `mod = mods[0]` ⇒ **同型号模块只改第一个**。机架里常有 2 个 VCA-1。不修就做 A9 的强度混合，会改错模块。⚠️ 宪法：「绝不覆盖李手工调的机架布局」——改错模块比不改更糟 | 无 |
| A9 | ~~recipe 强度混合~~ ✅ 完成（weight 0..1 插值 + clamp 已验证） | `apply_recipe` 从「整套套用」升级为**带权重的参数目标**：weight 0..1 在「当前值 ↔ recipe 目标值」间插值（0.5 = 各半），越界自动 clamp 并报告实际生效值。⚠️ 借鉴 YuE2 的 LoRA 权重思想（-10..+10），但我们用 0..1 更直观。**必须先做 A8** | 无 |
| A10 | ~~乐谱导出~~ ✅ 完成（李授权选 .abc） | 读机架里的 pianoroll / MiniArranger 音符 → 导出可编辑乐谱。⭐ **`seq.py` 的 `read_notes` + `edit_note` 已在**，只差序列化器。格式待李拍板（见第六节） | 无 |
| A11 | ~~风格 schema 化~~ ✅ 完成 | 产出 `docs/STYLE-SCHEMA.md` + `tools/style_schema.py`。字段：BPM 区间 / **分层职责**（哪层担当鼓、贝斯、和声、旋律）/ 混响尺寸与衰减 / 滤波开合 / **参考模块选型**。样板验证：拿已验收的 `yorushika_shura/hana` + `quadeca_life1_wdtg` 回填两份，**验证 schema 装得下真实决策**。⚠️ 抄 YuE2 的关键：风格字段要**可编辑、可存 JSON 在工具间流转**，不是写死的散文 | 无 |

---

### 批次 B · 需要编译（一次打包做掉）

> **合并编译的理由**：探针是**一次性能力清单**（做完定稿），JS 绑定是**无上限能力**。分两次编则第一次编完到第二次编之间 MCP 侧全部不可用。合并后边际成本只有几十行，却**永久消除「补任何 handler」的需求**。
> 编译脚本：`bash tools/cross_build_cardinal.sh`（重编全量 102MB）
> **进度：B1-B5 已于 2026-10-20 第一批完工并运行级验证**（WINE+OSC 9/9 端点实测，
> 含 A 组 3 个带参端点首次验证）。**C 组 + F 组（QuickJS）已于 2026-10-20 第二批
> 完工并运行级验证**（R1 12/12、R2 5/5、R3 4/4）。⚠️ 坑 D 仍在：主构建断在
> CardinalMini_dsp.dll，须单独补 `make -C CardinalNative`（既有问题，2026-09-20 起）。
> ⚠️ **liblo 接收 string 参数在本 Cardinal 版上确认不通**（10-20 三轮实测：echo /
> module-add / js-eval 全无应答）⇒ 需自由文本/JSON 的操作改走 JS 脚本路径。

**B 组 · 零 hook 读数（数据全现成，只差 OSC 入口）**

| # | handler | 源码依据 |
|---|---|---|
| B1 | ✅ `/build-info`（variant/mode/build/safeMode/caps；WINE+OSC 实测） | 版本/变体/是否 thread/编译时间/**caps 清单**。**P0**：OSC 开不开由**运行期 getenv** 决定（`MenuBar.cpp:741`），没开则所有工具超时，现象上与「Cardinal 崩了」无法区分 |
| B2 | ✅ `/cables`（全量+单模块双模式；默认机架实测 6 条线） | `Cable` 四字段全 public（`Cable.hpp:15-19`）+ `Engine::getCableIds()`（`:163`） |
| B3 | ✅ `/transport`（零 hook；playing/bar/beat/bpm/tick/bypassed 实测） | `plugincontext.hpp:82-90` 已有 `playing/bar/beat/bpm/tick/tickClock` ⇒ 零 hook |
| B4 | ✅ `/engine-info`（带 cpuRefreshMs=1000 诚实标注，age 不假装知道） | `getSampleRate`/`getMeterAverage`/`getMeterMax`。⚠️ CPU 值**每 1 秒才刷新**（`Engine.cpp:576`）⇒ 必须带 `cpuAgeMs` |
| B5 | ✅ `/plugins`（运行列表+safeMode；单查移师 MCP 侧 PluginManifests——liblo string 接收不可靠，10-20 决策） | 「我拼写的 plugin 存不存在」的权威答案。⚠️ **必须同时暴露 `settings::safeMode`** —— 为 true 时 `plugin::init()`（`plugin.cpp:273-275`）直接 return，**零插件加载** |

**C 组 · 模拟人类操作（李定的核心方向）** —— 10-20 第二批全部 ✅，WINE 运行级实测

| # | handler | 人类操作 | 实测结果 |
|---|---|---|---|
| C1 | ✅ `/param-set-by-display` | 右键旋钮输数值 | WINE 实测 `old=0 new=-54`。⚠️ **显示值域因模块而异且常为指数**（VCO 写 0.8 → 回读 11.56Hz 是正确换算），验收只能「回读值≠原值」，不能写死数字 |
| C2 | ⛔ `/module-add` **下线，改走 JS `cardinal.addModule(slug,x,y)`** | 右键 Add module → 拖进机架 | OSC 版需 string 参数（plugin\|model slug）⇒ **liblo 收不了 string**。JS API 已实测 `addModule=[ok]` + undo 生效 |
| C3 | ✅ `/cable-add` `/cable-remove` | 从输出口拖一条线到输入口 | WINE 实测 cable-add ok + undo 回 "add cable"。⚠️ **同一输入口只能接一根线** |
| C7 | ✅ `/module-remove` | 右键模块 → Remove | 走 history，可 undo |
| C8 | ✅ `/module-move` | 拖动模块改位置 | WINE 实测 ok + undo 回 "move module"。⚠️ **单位：x 是格、y 是行号**（.vcv 的 pos[0]/pos[1]） |
| C9 | ✅ `/midi-out` | 在 DAW 里弹 MIDI 键盘 | WINE 实测回 "sent"。⚠️ bypassed 时回显 `skipped:bypassed`（不假装送达） |
| C4 | ✅ `/undo` `/redo` | Ctrl+Z | WINE 实测 undo 名正确（change parameter / add cable / move module）+ 值回退。⭐ GUI 版 OSC 每帧在 UI 线程 pump ⇒ handler 里调 history 安全 |
| C5 | ⚠️ `/batch` **未单做**：`cardinal_music`/现有工具已能批量 | 批量操作 | `ComplexAction` 已在库内。C 组九个端点各自走 history，本身已可「批量 + 一次 undo」；真需要单端点再说 |
| C6 | ✅ 读 `/module-json`（整模块 .vcv JSON）· 写走 JS `moduleFromJson(id,json)` | 通用改任意模块数据 | ⭐ 拆成两半的原因：读只需 int64 参数（OSC 可发），写要 JSON 字符串（OSC 收不了） |

**D 组 · 观察**

| # | handler | 说明 |
|---|---|---|
| D1 | `/screenshot` | ✅ 2026-10-20 完工并 WINE 运行级实测。**改法与原设想不同**：不走「base64 分块回传」，而是**落盘 + 回传路径**——① `CardinalCommon.hpp` 加 `generateScreenshotToFile(path)` 声明；② `CardinalNative/Window.cpp` 加 `g_screenshotFilePath` 全局 + `Window__writePngDump`（`fwrite` 回调，用 `<cstdio>` 避开 `<fstream>` 的 ios_base 坑）+ 保存分支改成「落盘请求时走**全尺寸** dump，否则维持原 340x210 remote 预览」；③ `osc_screenshot_handler` 重写为**无参**触发（`/screenshot ""`），回 `["screenshot", "<绝对路径>"]`；④ 非 thread 注册区补 `/screenshot`、thread 版签名 `"b"`→`""`。**MCP 侧**新增 `cardinal_screenshot` 工具（53 个）：OSC 触发 → **轮询等文件落盘**（渲染异步，回复先给的是目标路径）→ 读 PNG 头取宽高 → 可选 `save_to` 拷贝。🔴 **WINE 下画面全黑是环境限制不是代码 bug**：同一时刻 X11 抓屏有 22.76% 非黑像素（完整 Cardinal 界面），而 `glReadPixels(GL_FRONT)` 读回 0% ⇒ **llvmpipe 软渲染的 GL 前缓冲读回限制**（读像素那段是上游原有代码，D1 没碰）。真机（硬件 GL）需李验收画面内容 |
| D2 | `/load` 回 warningLog | ✅ 2026-10-20 完工并 WINE 运行级实测。**四处改动**：① `settings.hpp/.cpp` 加 `oscLoadActive` 开关（不进 settings.json）；② `patch.cpp fromJson` 末尾弹窗+清空改条件化（OSC 模式保留 warningLog 不弹窗）；③ `override/Engine.cpp:1260/:1289` 取消两处 `APP->patch->log(e.what())` 注释（A5 实锤的「两处」——模块级异常原本被静默）；④ `osc_load_handler` 置位开关 + 回 `ok`/`warn <文本>`/`fail <文本>`，回完清空。回包契约：`ok` / `warn <文本>` / `fail <文本>`（截断 400B）。MCP 侧 `load_patch` 已同步解析 `warnings` 字段。⚠️ 只改了 `src/CardinalNative/CardinalCommon.cpp` 一份，其余两份 CardinalCommon.cpp 待 E 组注册表抽函数时收敛 |

**E 组 · 协议级（编完再改要 C++ + Python 双返工，必须一次定死）**

- **E1 · 三段式响应 ✅ 2026-10-21 完工并 WINE 运行级验证**
  - **采用「追加式」而不是原规格的顺序**：`/resp` 从 `(tag, payload)` 变为 `(tag, payload, status)`。
    status 放**第三段**，payload 位置不变 ⇒ 现有 53 个工具零改动即可继续工作，新旧 exe/MCP 混用也不会炸。
  - status 取值：`"ok"` 或 `"err:<CODE>"`。错误码共 9 个（8 语义 + 1 兜底）：
    `E_NO_PLUGIN` / `E_NO_MODULE` / `E_BAD_PARAM` / `E_NO_CABLE` / `E_BAD_PORT`
    / `E_NOTHING` / `E_BAD_ARGS` / `E_DISABLED` / `E_INTERNAL`
  - C++ 侧：A 组 inc 里新增 `cardinalOscReply(source, server, tag, payload, status)`，全部 handler 改走它（共 42 处调用）。
  - MCP 侧：新增 `_ask_status()`（两段旧包自动视为 `ok`）、`_STATUS_NOTES`；`get_param` / `get_light` / `get_ports` 现在能区分
    「模块不存在」「参数越界」「值就是空」。
  - **验证**：WINE 探针 14/14 PASS；Windows MCP → WSL Cardinal 端到端也通过（`err:E_BAD_PARAM` / `err:E_NO_MODULE` 正确）。
  - ⚠️ **坑（已修）**：MenuBar 的「启动自动开 OSC」原来在首帧调 `startRemoteServer()`，Wine 下会撞 glibc robust mutex 断言崩溃。
    已改为**约 120 帧（≈2s）后**再启动。补丁原文见 `HANDOFF.md` §2.3.1。
- **E2 · 分页 ✅ 2026-10-21 完工并 WINE 运行级验证**
  - **新增端点 `/modules-page "ii"`（offset, limit）**，旧 `/modules` 保留全量 ⇒ 零破坏。
  - 回包 payload = `"<returned>/<total>|<items>"`，items 与 `/modules` 同构（`id:plugin|model`）；limit 上限 64。
  - 越界语义：offset 超 total → returned=0 但 total 仍报真实总数（status=ok）；
    offset<0 / limit<=0 / limit>64 → status=err:E_BAD_ARGS。
  - 注入器：`tools/osc_patch/inject_osc_e2.py`（依赖 E1 的 `cardinalOscReply` + A 组的 `/modules`，只改顶层 CardinalCommon.cpp，6 变体是符号链接）。
  - MCP 侧：新增 `cardinal_modules_page`（offset/limit）工具 + `modules_page()`，工具数 53→54。
  - **验证**：WINE 探针 15/15 PASS（分页不重叠/可拼全集/越界/三种非法参数/limit=64）；
    Windows MCP → WSL Cardinal 端到端也通过（`returned/total/has_more` 全对、`err:E_BAD_ARGS` 正确）。
  - ⚠️ 实测校正：当前 `modules` 217 条 ≈ 4 KB、`cables` 307 条 ≈ 5 KB，**离 UDP 65 KB 上限很远**，
    所以分页是防未来，不是救火。
- **E3 · 注册表抽函数 ⏳ 未做（风险最高）**：`CardinalCommon_RegisterOscMethods(server, self)`，一处实现两处调用。
  现状 thread 版 + 非 thread 版各写一遍，× build 变体 = 2×2，只改一处会**静默失效**。
  要删掉现有 2×21 行注册，删错不报错、只是端点消失 ⇒ 必须靠计数断言验证。
- `/screenshot` 注册必须包在 `#ifdef CARDINAL_WINDOW_CAN_GENERATE_SCREENSHOTS` 内（`override/Window.cpp:45`）否则 Mini/GLES 编不过 —— ✅ **D 组已做到**

**F 组 · QuickJS 绑定** —— ✅ 2026-10-20 完工并运行级实测

- `libquickjs.a` 已静态链入（`Makefile.cardinal.mk:152-154`）⇒ 实测 exe 体积 +21KB 即 JS 代码量
- **实际实现与原设想的三处偏差**（都是实测逼出来的）：
  1. **不跑在 DSP 回调**。原计划「入队 + DSP 回调里 eval」是为了躲 GC 抖动；实际 OSC handler 已在 UI 线程串行 pump，直接在 handler 里同步 eval 更简单、且不存在并发问题（代价：UI 线程最多卡 2 秒 = 预算上限）
  2. **输入改「脚本文件 + 索引」**（`/osc-js-run i` + `/osc-js-list`）而非即时字符串——liblo 收不了 string。且脚本放 `js/` 可 git 管理，反倒更合李的工作流
  3. **预算是墙钟不是指令数**。🔴 血泪：原先只数指令、上限 2000 万，实测死循环 **40 秒没被打断、UI 线程被永久卡死**。根因是 quickjs 只在 `interrupt_counter`（`JS_INTERRUPT_COUNTER_INIT=10000`，`deps/QuickJS/quickjs.c:316`）递减到 0 时才调 handler ⇒ 2000 万次 handler 调用 ≈ **2000 亿条指令**，差 5 个数量级。更根本的是**单位错了**：安全目标是「不卡 UI」，量纲必须是时间——同一指令数在真机和 WINE 上差几个数量级。⇒ 现为墙钟 2000ms（`CARDINAL_JS_BUDGET_MS` 可覆盖）+ 100 万次 handler 兜底，超时回 `budget-exceeded ms=2001`，实测**准点打断且进程存活**
- ✅ 安全模型三门全落地并实测：**默认 off**（`CARDINAL_JS_MODE` 未设即拒绝）·**绝不初始化 libc**（无 std/os ⇒ 无 exec）·**墙钟预算**
- 脚本契约：包成 `globalThis.result = (function(){ <脚本> })();` ⇒ **用 `return` 交结果**。🔴 血泪：脚本若自己 `globalThis.result = ...`，会被 IIFE 的 undefined 覆盖（实测踩过）
- 实测数据（WINE 默认机架）：read API `modules_len=217 param2=261.626 ports_len=147 cables_len=307`；write API `setDisplay=[old=0 new=-54] addModule=[ok]` + undo 回 "add module"
- 对标：Unity/Blender/UE/Godot MCP **10/10 都有「宿主内执行任意代码」工具** —— 本项是本项目唯一的硬差距，**现已补齐**

---

### 批次 C · 创作能力（李明确要「搞的是创作能力」）

| # | 事项 | 说明 |
|---|---|---|
| C-a | **风格参考 → 候选机架方案** | 借用 bilibili 教程的「参考驱动，不凭空生成」：接到「做 XX 风格」时，先检索参考 → 拆成音乐元素 → **摆候选给你点头** → 再动手。⚠️ 这是补上「我替你决定了风格」这个缺失 |
| C-b | 风格知识库 | 抄 bitwize 仓库结构：`genres/<风格>.md` 存该风格的元素拆解。⚠️ 李的原话：「重点是怎么建立对**一位制作人**风格的理解」——这要跟他学 |
| C-c | 「这个机架在干什么」翻译层 | `[VCO, ADSR, VCF, VCA]` → 「一个带包络的减法合成器，声部 lead」。现有 `by_role` 是查表（12 个角色），不是理解 |
| C-d | 母带处理机架（**新发现**） | 实测 Cardinal 里有：压缩器 Zod/PRESSOR/baR(10)、限幅器 CLPR/Stereo Strip(17)、母带总线 BUS DEPOT / Enter-Exit Mixer Bus。⇒ **合成器可以做母带链**，这条路我们之前默认「不可能」 |

---

## 三、⚠️ 已知错误与待澄清（开工前要知道）

| # | 内容 | 状态 |
|---|---|---|
| E1 | `docs/CARDINAL-MCP-SPEC.md` H9 节的 warningLog 判断错误（见 A5） | ✅ 已修 |
| E2 | 两份文档的 `Engine.cpp`/`Window.cpp` 行号未标路径 | ✅ 已修（两文档头部均加路径约定） |
| E3 | 探针**在源码里但不在二进制里**（`param-get` 实测 = 0）⇒ 必须编译才可用 | 确认 |
| E4 | `/load` 的 `skipped` 列表：接线侧**拿不到**，且是有意为之（`override/Engine.cpp:1323` 注释明说刻意避免 "missing modules create unnecessary complaining"）⇒ P0 只做模块侧，cable 留 P2 | 确认 |
| E5 | Cardimal 日志**进程内读不到**（`logger.cpp:110` 直接 fprintf，Cardinal 走 DPF 路径 `logPath` 为空 ⇒ 输出到 stderr）。要读必须加环形缓冲 hook | 确认 |
| E6 | XRUN/getCpuLoad **完全不存在**（Cardinal 不用 JACK，跑在宿主回调里）；替代 = `processCounter` 增长速率 | 确认 |
| E7 | 电压读数**可能撕裂**：Engine 的 SharedMutex（`Engine.cpp:227`）**不保护 Port 电压**，音频线程无锁直写。但 Cardinal 自己 UI 线程也是无锁读，属既定设计，不会崩 | 确认 |
| **E8** | 🔴 **死锁：A3 的验证闭环被编译阻塞** | 已核实。链条：`apply_recipe`/OSC 改的是 **param** → 改完读回来验证 → 唯一能读 param 实时值的探针是 `get_param`（走 `getDisplayValue()`）→ **该探针未编译**（`param-get` 在二进制里 = 0）。`read_live` 也不行：它读 autosave，而 autosave **只在 `/load` 和 GUI Ctrl+S 落盘，`/param` 改动永不落盘** ⇒ 读到的永远是旧值。<br>⇒ **要么把 A3 降级为「只验证结构不验证参数」，要么把它推到编译之后。** 我倾向后者——**验证闭环本来就是编译才有意义的**。<br>⚠️ 注意：绝不可以用「返回成功但数据为空」来掩盖（会变成假阳性诊断） | **需李定** |
| **E9** | 🟡 **YuE2 计划里的样板机架路径写错** | 计划第 78 行写 `yorushika_shura/hana`，实际文件是 `patches/yorushika_hana.vcv`（无目录层级）。已核对全部样板机架的真实文件名（见第四节），**开工时按实际路径用**。**记忆（MEMORY.md）里也有一处同类写法**（写 `yorushika_shura/hana`），建议一并订正 | 已核实 |
| **E10** | ~~与 SONG-TO-PATCH-WORKFLOW.md 重叠/矛盾~~ ✅ 已裁决已落地（李 10-19：统一英文） | ① SONG-TO-PATCH-WORKFLOW.md 头部已标「已并入本表，不再单独维护」② 选型段落改为 modbrowser 英文用法 ③ modbrowser 内置中文词表做翻译层（一个入口），modsearch 降级为速查表 CLI | 已闭环 |

---

## 四、不该走的路（避免返工）

### 已核对的机架真实文件名（A11 样板验证用）
```
yorushika_hana.vcv            ✅ 存在（计划里写成 yorushika_shura/hana 是错的）
quadeca_life1_wdtg.vcv        ✅ 存在
demo_S4_sampling.vcv          ✅ 存在
demo_S5_fullkit.vcv           ✅ 存在（记忆里写的 demo_S5_fullkit 正确）
quadeca_scrapyard.vcv         ✅ 存在（另有 quadeca_scrapyard_final.vcv）
```

- ❌ **别往 patch 里塞 VU/示波器当电平探针**：Bogaudio-VU 读数在私有成员（`tmp/BogaudioModules.src/src/VU.cpp:31-32` 的 `_lLevel/_rLevel`），既无 configParam 也无 light，画在 NanoVG 上 ⇒ **引擎数据模型里根本不存在**。`/ports`+`/signal` 已是更好的电平表
- ❌ **别用 `/load` 做细粒度**（加一个旋钮）：整体替换 + 抹掉 GUI 手改 + 打断音频。细粒度走 `param-set`，中间层靠 handler
- ❌ **别把 `paramlib.build()` 变成 MCP 工具**：要抓 GitHub 几分钟起，只能是离线显式命令
- ❌ **别照搬 bilibili 教程的流程**：它是「AI 生成成品」（SUNO 出整首歌 → 混音母带 → 交付），我们是「AI 造合成器」（无渲染、无成品、李全程接管）。**可借鉴的是方法论（参考驱动 / 多参考融合 / 顾问式解释），不是流程**

---

## 五、工具数演进（便于回溯）

```
17（原有）
  → 22  +4 modbrowser        +1 topology
  → 25  +3 seq
  → 29  +4 samplelib
  → 30  +1 cardinal_actions
```

---

## 六、待李拍板（YuE2 计划第 8 节的三个问题）

### ① 乐谱导出的格式（A10）
| 选项 | 优点 | 缺点 |
|---|---|---|
| **A. `.mid`** | 任何 DAW 都能开；手写标准 MIDI 约 100 行、零新依赖 | 看不出「这是人写的还是 AI 写的」，不好 diff |
| **B. `.abc`** | **纯文本，能直接读能直接 diff**；YuE2 原生格式，将来进 YuE 生态零转换 | 本地没有可视化编辑器打开 |
| **C. 两个都出** | 只需多一个序列化器 | — |

> 我的看法（供李判断，非推荐）：**B 更符合「在软件里看和改」这条原则** —— `.abc` 是纯文本，李能用任何编辑器直接看、直接改、diff 也清楚。代价是本地没可视化工具。
> 注：`.mid` 的价值是「能喂给 DAW 做专业编辑」，但李的流程是「在 Cardinal 里改」，不一定需要 DAW。

### ② recipe 权重语义（A9）
默认方案：**weight 0..1 在「当前值 ↔ recipe 目标值」之间插值**（0.5 = 各半），越界自动 clamp 并报告实际生效值。
待确认：这是否 OK？

### ③ 开工顺序
YuE2 计划建议 ①→②→③。合并后本表建议 **A 批次按 A1→A11 顺序**（A8 必须先于 A9）。
待确认。

---

## 七、来源与去重说明（避免下次再散出多份计划）

| 来源 | 贡献了什么 | 去向 |
|---|---|---|
| **2026-10-19 三人盘点**（PM 对标 / 架构师源码 / 工程师缺口） | 能力地图 + 规格 + 源码坐标 | 本表批次 B + `CARDINAL-MCP-SPEC.md` |
| **YuE2-Studio 借鉴计划** | 风格 schema 化 / recipe 强度混合 / 乐谱导出 | A11 / A9 / A10 |
| **bilibili 词曲编混教程** | 方法论（参考驱动 / 多参考融合 / 顾问式解释） | C-a（**不是**流程，见第四节） |
| **SONG-TO-PATCH-WORKFLOW.md（09-14 已有）** | 「你说元素 → 我搜配方 → 翻译接线 → 你听」 | ⚠️ 与 C-b/C-a **可能重复**，待体检确认 |
| **今天新增的 5 个 Python 模块** | 已是成品 | 第一节「当前资产」 |

> 🔴 **教训**：今天一天散出了 3 份计划文档（能力地图 / 规格 / 待办），加上早已存在的
> SONG-TO-PATCH-WORKFLOW 和今天的 YuE2 计划 —— **同一件事被写了多遍**。
> 今后新增待办一律改这份 `TODO-BACKLOG.md`，别再新建计划文件。
