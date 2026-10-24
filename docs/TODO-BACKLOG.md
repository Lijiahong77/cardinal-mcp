# 待办总表 · 统一开工用

> 建立：2026-10-19 · **最后更新：2026-10-21 10:50**
>
> **当前状态（别再看旧结论）：**
> - 批次 A（A1–A11）✅ 全部完成
> - 批次 B（B1–B5）✅ 完成 · C 组 ✅ 完成 · F 组 QuickJS ✅ 完成 · D 组（D1/D2）✅ 完成
> - **E 组三批（E1/E2/E3）✅ 全部完工**
> - **待办总表已清空** —— 原有三项待办（`.mid` 导出 / 段落编排规格 / life1 三修法）均已由李在 10-21 裁决结案，见第六节。
> - **但「后面还有的工作」不等于空** —— 10-21 11:20 重新盘点：协议层（A/B/C/D/E 五组）已全完工，剩下的全是「缺真机验收」或「缺李的拍板」或「我独立能做的收尾」。**完整清单见 `HANDOFF.md` §6.1b**（分 A 需要李在场 / B 我能独立做 / C 已知技术债 三栏）。
> - 开工入口 → 根目录 `HANDOFF.md`（状态 + 命令）；本文件只管「还有什么没做」
>
> 用途：把所有待办集中在这里。开工时按「批次」推进，每批做完整再进下一批。

---

## 一、当前资产（已完工，不是待办）

**MCP 工具 60 个**（`tools/cardinal_mcp.py`，截至 2026-10-22 E3+E8+B2+B3+C3+C2+M1 完工）
- 原有 17：连通/存档/按编号操作/音乐配方/5 个未编译探针
- 10-19 白天新增 13：4 个模块检索 · 1 个接线拓扑 · 3 个序列器音符 · 4 个采样槽 · 1 个交互索引
- 批次 A 新增 6：`set_param_by_name` · `cardinal_audit` · `cardinal_deploy`+`cardinal_diff` · `cardinal_port_semantics` · `cardinal_export_abc`
- 批次 B 第一批新增 5：`build_info` · `cables` · `transport` · `engine_info` · `plugins`
- 批次 B 第二批（C 组 + QuickJS）新增 11：`param_set_by_display` · `cable_add` · `cable_remove` · `undo` · `redo` · `module_json` · `module_remove` · `module_move` · `midi_out` · `js_run` · `js_list`
- D 组新增 1：`cardinal_screenshot`
- E8 解锁新增 1：`cardinal_set_params_batch`（批量按名设参）

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
| A10 | ~~乐谱导出~~ ✅ 完成（李授权选 .abc） | 读机架里的 pianoroll / MiniArranger 音符 → 导出可编辑乐谱。⭐ **`seq.py` 的 `read_notes` + `edit_note` 已在**，只差序列化器。格式已由李拍板为 `.abc`（`.mid` 作废） | 无 |
| A11 | ~~风格 schema 化~~ ✅ 完成 | 产出 `docs/STYLE-SCHEMA.md` + `tools/style_schema.py`。字段：BPM 区间 / **分层职责**（哪层担当鼓、贝斯、和声、旋律）/ 混响尺寸与衰减 / 滤波开合 / **参考模块选型**。样板验证：拿已验收的 `yorushika_shura/hana` + `quadeca_life1_wdtg` 回填两份，**验证 schema 装得下真实决策**。⚠️ 抄 YuE2 的关键：风格字段要**可编辑、可存 JSON 在工具间流转**，不是写死的散文 | 无 |

---

### 批次 B · 需要编译（一次打包做掉）

> **合并编译的理由**：探针是**一次性能力清单**（做完定稿），JS 绑定是**无上限能力**。分两次编则第一次编完到第二次编之间 MCP 侧全部不可用。合并后边际成本只有几十行，却**永久消除「补任何 handler」的需求**。
> 编译脚本：`bash tools/cross_build_cardinal.sh`（重编全量 102MB）
> **进度：B1-B5 已于 2026-10-20 第一批完工并运行级验证**（WINE+OSC 9/9 端点实测，
> 含 A 组 3 个带参端点首次验证）。**C 组 + F 组（QuickJS）已于 2026-10-20 第二批
> 完工并运行级验证**（R1 12/12、R2 5/5、R3 4/4）。⚠️ 坑 D 仍在：主构建断在
> CardinalMini_dsp.dll，须单独补 `make -C CardinalNative`（既有问题，2026-09-20 起）。
> ✅ **liblo 能正常接收 string 参数**（2026-10-21 深夜 C4 实验，推翻 10-20 旧结论）：
> 注册 `"s"` 类型 handler 即可——ASCII / 带 `|` 分隔符 / 200 字符长串全部正确收到，
> 类型不匹配时 liblo 正确忽略。🔴 旧结论实为**注册方式问题**（typespec 没注册 `"s"`
> ⇒ liblo 不派发 ⇒ 表现为全哑），10-20 三轮实测的 echo/module-add/js-eval 大概率都栽在这。
> ⇒ **文本类端点已解锁**：候选 `/module-add "ss"`（plugin|model slug + 位置）——
> C2 当年下线的理由已不成立，**待李拍板**。JS 脚本路径保留可用。

**B 组 · 零 hook 读数（数据全现成，只差 OSC 入口）**

| # | handler | 源码依据 |
|---|---|---|
| B1 | ✅ `/build-info`（variant/mode/build/safeMode/caps；WINE+OSC 实测） | 版本/变体/是否 thread/编译时间/**caps 清单**。**P0**：OSC 开不开由**运行期 getenv** 决定（`MenuBar.cpp:741`），没开则所有工具超时，现象上与「Cardinal 崩了」无法区分 |
| B2 | ✅ `/cables`（全量+单模块双模式；默认机架实测 6 条线） | `Cable` 四字段全 public（`Cable.hpp:15-19`）+ `Engine::getCableIds()`（`:163`） |
| B3 | ✅ `/transport`（零 hook；playing/bar/beat/bpm/tick/bypassed 实测） | `plugincontext.hpp:82-90` 已有 `playing/bar/beat/bpm/tick/tickClock` ⇒ 零 hook |
| B4 | ✅ `/engine-info`（带 cpuRefreshMs=1000 诚实标注，age 不假装知道） | `getSampleRate`/`getMeterAverage`/`getMeterMax`。⚠️ CPU 值**每 1 秒才刷新**（`Engine.cpp:576`）⇒ 必须带 `cpuAgeMs` |
| B5 | ✅ `/plugins`（运行列表+safeMode；单查走 MCP 侧 PluginManifests 仍是合理选择，但「liblo string 不可靠」的旧理由已推翻，见文首 C4 订正） | 「我拼写的 plugin 存不存在」的权威答案。⚠️ **必须同时暴露 `settings::safeMode`** —— 为 true 时 `plugin::init()`（`plugin.cpp:273-275`）直接 return，**零插件加载** |

**C 组 · 模拟人类操作（李定的核心方向）** —— 10-20 第二批全部 ✅，WINE 运行级实测

| # | handler | 人类操作 | 实测结果 |
|---|---|---|---|
| C1 | ✅ `/param-set-by-display` | 右键旋钮输数值 | WINE 实测 `old=0 new=-54`。⚠️ **显示值域因模块而异且常为指数**（VCO 写 0.8 → 回读 11.56Hz 是正确换算），验收只能「回读值≠原值」，不能写死数字 |
| C2 | ⛔ `/module-add` **下线，改走 JS `cardinal.addModule(slug,x,y)`** | 右键 Add module → 拖进机架 | OSC 版需 string 参数（plugin\|model slug）——旧理由「liblo 收不了 string」**已推翻**（见文首 C4 订正）⇒ **OSC 版可复活，待李拍板**。JS API 已实测 `addModule=[ok]` + undo 生效（保留路径） |
| C3 | 🔴 `/cable-add` `/cable-remove` **实际不生效**（2026-10-21 下午实锤） | 从输出口拖一条线到输入口 | ⚠️ **历史验收是缺口**：当时只验「回包 ok + undo 名正确」，没验线真的加了。10-21 B3 排查实测：回包 `ok replaced=0` 但 `/cables` 数量不变 ⇒ **只 push 不手动执行**（`State::push` 只入栈不 redo）。✅ **已修**（2026-10-21 深夜 C6 批，见 `/module-copy` 记录下方的 C6 段） |
| C7 | ✅ `/module-remove`（2026-10-21 深夜 C6 批修复） | 右键模块 → Remove | 手动级联删（线→模块，一个 ComplexAction）+ push 记录。WINE 实测 41→40 模块 + 4 根级联线删，undo 完全恢复 |
| C8 | ✅ `/module-move`（2026-10-21 深夜 C6 批修复 + 单位语义修正） | 拖动模块改位置 | 手动设 `box.pos` + `updateExpanders`。🔴 **附带修掉单位 bug**：文档说「x 格 y 行」，旧实现直接当 px（差 15 倍）——该端点此前从不生效故零兼容负担。⚠️ 位置真值归真机 A1 |
| C9 | ✅ `/midi-out` | 在 DAW 里弹 MIDI 键盘 | WINE 实测回 "sent"。⚠️ bypassed 时回显 `skipped:bypassed`（不假装送达） |
| C4 | ✅ `/undo` `/redo` | Ctrl+Z | WINE 实测 undo 名正确 + 值回退（param 类）。⭐ GUI 版 OSC 每帧在 UI 线程 pump ⇒ handler 里调 history 安全。⚠️ 10-21 下午订正：当时的「add cable / move module」undo 名只证明 action 入了栈，**操作本身从未生效**（见 C3/C7/C8） |
| C5 | ⚠️ `/batch` **未单做**：`cardinal_music`/现有工具已能批量 | 批量操作 | `ComplexAction` 已在库内。C 组九个端点各自走 history，本身已可「批量 + 一次 undo」；真需要单端点再说 |
| C6 | ✅ 读 `/module-json`（整模块 .vcv JSON）· 写走 JS `moduleFromJson(id,json)` | 通用改任意模块数据 | ⭐ 拆成两半的原因：读只需 int64 参数（OSC 可发），写要 JSON 字符串（OSC 收不了） |

- **C3 · 日志环形缓冲 + `/log-get` ✅ 2026-10-22 早上完工并 WINE 运行级验证**
  - **动机**：Cardinal 日志走 `logger.cpp` 的 `logVa()` 直 fprintf stderr——GUI standalone 无 console ⇒ 进程内什么都读不到。
  - **实现**：`logVa()` 里附加推入 2000 条环形缓冲（ring mutex 保护；行格式 = 文件日志同款但**无 ANSI 色码、文件名只留 basename**）；新端点 `/log-get "ii"`（from, limit≤64）增量读，回包 `"<first>/<next>|<行>\\n<行>"`。MCP 工具 `cardinal_log_get`（57→58）。
  - **验证**：WINE 探针 **8/8**（最老 5 行 / 增量读 first==上次 next 且含 load 新日志 / 无重叠 / 四种非法参数全 `err:E_BAD_ARGS` / limit=64 / 超界 from 空返回）；MCP 层端到端 **5/5**。
  - 🔴 **过程坑（三个，都记入日志）**：① `logRingPush` 初版忘加锁（UI 线程刷日志 vs OSC 线程读 deque 竞态）⇒ 补 ring mutex；② `firstOut` 语义初版永远报 ring 最老条 ⇒ 改为 max(from, oldest)；③ **探针索引抄错**（c3 探针 ask 返回 aargs 列表而非 (payload,status) 元组，T2 按元组索引取 ⇒ 假失败三轮）⇒ 教训：新探针先 dump 原始回包对齐语义再写断言。
  - patch = `tools/osc_patch/patches/08-c3-log-get.patch`（3 文件段：CardinalCommon.cpp + Rack logger.cpp/hpp；logger 两文件相对 Rack 子模块 HEAD）；replay 第 8 组，端点 30→31。⚠️ 动 Rack 层 ⇒ 重编需 `make rack.a`。exe 已部署：MD5 `d17ab013…`。
- **C2 · `/load` skipped 列表可见化 ✅ 2026-10-22 早上完工并 WINE 运行级验证**（C 栏收官）
  - **问题**：加载时插件缺失的模块被跳过只进 warningLog（**无 id 上下文**），接不上的线则是**故意完全静默**（upstream 注释：missing modules 造成多余抱怨）⇒ 接线侧失败不可见。
  - **实现**：`rack::LoadSkip{id,kind,reason}` 收集器（mutex 保护），在 **`src/override/Engine.cpp` 的 `Engine::fromJson` 三个跳过点**插桩（model 加载失败 / module 装配失败 / cable 装配失败），`Manager::fromJson` 开头清空；新端点 `/load-skipped`（无参，回包 `<n>|kind:id:reason,...`，reason 已消毒+截 80）；MCP 工具 `cardinal_load_skipped`（58→59）。
  - 🔴 **踩坑：Cardinal 编译的是 `src/override/Engine.cpp`，不是 Rack 原版** ⇒ 改错文件 ⇒ 链接期 `undefined reference to rack::getLoadSkips()`。判定法：`nm -C src/rack.a | grep LoadSkip` 查不到定义 + `find build -name 'Engine.cpp.o'` 只找到 `build/rack/override/Engine.cpp.o`。
  - **验证**：WINE 探针 **6/6**（损坏 patch：MiniArranger 的 plugin slug 改成不存在的 ⇒ 1 module + 16 cable = 17 条 skip，逐条带 id 与 reason；干净 patch ⇒ 0；重载 ⇒ 归零）；MCP 层端到端 **5/5**。
  - patch = `tools/osc_patch/patches/09-c2-load-skipped.patch`（4 文件段；before/after 副本法造基线，避免把 D2 的 oscLoadActive 等既有未提交改动混进去）；replay 第 9 组，端点 31→32。exe 已部署：103,013,888 B，MD5 `bf55806b…`。
- **M1 · `/module-add` 加模块端点 ✅ 2026-10-22 早上完工并 WINE 运行级验证**（李选方案 A）
  - **由来**：C2 当年因「liblo 收不了 string」下线；C4 实验推翻旧结论 ⇒ 文字类端点解锁 ⇒ 把这项能力正式补上（李 10-22 拍板方案 A）。
  - **端点**：`/module-add "sii"` = plugin\|model slug + x(格) + y(格)。手动执行（照抄人类右键 Add module：`Rack/src/app/Browser.cpp` 的 addModuleAction：createModule → engine->addModule → createModuleWidget → setModulePosForce → rack->addModule）+ push `ModuleAdd` 记录 ⇒ **可 undo**（undo 名 = `add module`）。回包 = 新模块 id；错误码 `err:E_NO_MODEL`（slug/型号不存在）。MCP 工具 `cardinal_add_module(plugin, model, x, y)`（59→60）。
  - **顺带修 JS 那条路**：`cardinal.addModule(slug,x,y)`（JS API）此前与 C6 修掉的四个端点同病——**只 push 不执行 ⇒ 回 ok 但模块没加**（当年「undo 生效」的验收只证明了 action 入栈）。现已改为手动执行 + push 记录。
  - **验证**：WINE 探针 **10/10**（41→42 模块、新 id 与型号正确、undo→41、redo→42、未知插件/未知型号/无分隔符三种错法全 `err:E_NO_MODEL`、失败调用零副作用）；MCP 层端到端 **5/5**。
  - 🔴 **两个新坑**：① **typespec 必须与参数顺序一致**——我先写成 `"ssi"`（s+s+i）而实际是 slug+int+int ⇒ liblo 不派发 ⇒ 端点永远哑（探针一眼看出）；② **`loadTemplate()` 不能在 OSC 侧调**（人类右键路径独有的「出厂预设」加载，`ModuleAdd::redo` 并不做；preset 应用会碰 UI 菜单/参数 ⇒ 调了之后 undo 就让 OSC 失联）。
  - patch = `tools/osc_patch/patches/10-module-add.patch`（基线取 C2 后状态，只含本批改动）；replay 第 10 组，端点 32→33。exe 已部署：103,015,424 B，MD5 `2c2ce802…`。
- **M2 · 按名字加模块（`cardinal_add_module_named`）✅ 2026-10-24 完工**（李拍板：仅唯一命中直加 + 中文词表加前缀匹配）
  - **由来**：M1 之后「加模块不用背 slug 对照表」的增强（PROGRESS §5 C 栏两项合一）。李 10-24 裁决：① 直加门槛 = **仅唯一命中**（零猜测，多个一律列候选）② 中文词表**修前缀匹配**。
  - **实现**（纯 Python 层，**零 C++ / 零编译 / exe 不动**）：新文件 `tools/modresolve.py`（口语 query → 候选 / 唯一命中）：分词 → **品牌归一**（brand「VCV」→ plugin「Fundamental」，85 品牌映射从 manifest 现生成）→ 池内打分（复用 `modbrowser._score`）→ 三态判定 unique / ambiguous / no_match；`tools/modbrowser.py` 的 `_expand` 加 `_zh_lookup`（整词优先 + **最长前缀**，「滤波器」→「滤波」→ filter）；`cardinal_mcp.py` 注册 `cardinal_add_module_named`（60→61，TOOLS/DISPATCH 双注册）+ **无状态两段式**（query → 直加 / 列候选；pick=N → 落地第 N 个）。
  - **为什么品牌词必须摘除**：`_score` 多词取 max，品牌词（0.45 分）被 tag 命中（1.2 分）淹没 —— 实测「Bogaudio VCO」直接喂 search 返回 **157 个且正确排 20 名开外**；摘除后收敛到 2 个。
  - **停用词坑**：垃圾输入「xyzzy not a module」靠 "module" 的描述词频刷出 **1363 个假命中** ⇒ resolve 加 `_STOPWORDS`（剔完只剩虚词且无品牌词 → 诚实 no_match）。
  - **验证**：单测 **21/21**（原 13 + 新 8：品牌归一 / 唯一直加喂对的 slug / 歧义不碰 OSC / pick 越界 / 停用词回归 / 中文前缀）；CLI 端到端：`--tools` 61、歧义路径回完整候选（带 manualUrl）、unique 路径在 OSC 不通时**如实报 `add_failed` + probe_not_supported**（无假 ok）。
  - **真机落地验收 ✅ 2026-10-24（李在场，空白模板机架）**：`add_module_named("VCV VCF", 4, 2)` → `added=True`（新 id 7796350873299777，品牌归一 vcv→[Fundamental]）；数据层 7→8→7（undo 闭环）；截图确认 VCF 面板完整落位、不堆叠、原有模块完好；两次 undo 语义清晰（`move module` / `add module`）。机架恢复 7 模块原状，零残留。观察：(24,10)/(50,4) 落在当前视口外，(4,2) 可见（A1 同位置）——格坐标屏幕映射与左上直觉不同，非功能问题。
- **M3 · SongRoll 复活（Song 模式工程 · 阶段 1：引擎进 exe）✅ 2026-10-24 完工**（李 10-24 拍板：C++ 路线、复活 SongRoll）
  - **参考代码实查结论**：SongRoll 骨架 = 数据类（SongRollData/Section/ChannelConfig）完整 + UI 控件半成品，但**端口全 0 / `step()` 空 / JSON 存取空壳 / Transport 只剩 `currentSection` 游标** ⇒ 引擎逻辑从零写；可依靠件 = `PhraseSeq32/PhraseSeqUtil`（乐句 `Seq#` CV 选段的最直接参照）· `rcm-pianoroll`（PATTERN_IN 消费端 + JSON 样板）· `JW/Arrange`（16×64 门控 = 音色路由现成件）· `MiniArranger.cpp`（项目内同环境三件套模式）。
  - **阶段 1 做了什么**：`.cppx`→`.cpp` 复活 3 个引擎文件（SongRollData / SongRollModule / Transport）+ 注册链三处（Makefile wildcard / `plugin.json` 条目 `rcm-songroll` / plugins.cpp addModel）+ Rack 2 API 修（`rack::SchmittTrigger`/`rack::RingBuffer` 在 Rack 2 不存在 ⇒ `rack::dsp::` **全限定**——裸 `dsp::` 在 `namespace SongRoll` 内解析失败，MiniArranger 能用是因它的 .cpp 有 `using namespace rack`）+ UI 七文件暂存 `.bak`（Rack 1 代码：`EventDragMove` / `VirtualWidget` / `BaseWidget::dataToJson` 在 Rack 2 全不存在）+ 胶文件重写（最简 SVG Widget 挂 `res/SongRoll.svg`，面板资源现成）。
  - 🔴 **部署链路坑（10-24 实炸过一次）**：SongRoll 复活后**只拷 exe 没同步 manifest ⇒ 真机只有进程没窗口**。根因 = Rack 2 `Plugin.cpp:158` 硬校验：代码里 `addModel` 注册的 Model 必须在 manifest 里，否则启动抛 `rack::Exception` 终止。运行时 manifest 唯一来源 = `win64/resources/PluginManifests/<插件目录名>.json`（`bin/` 不生成；WINE 实验 4 秒退出 EXIT=3 复现，异常文本实锤）。⇒ **plugins 层改动后部署三件套**：exe + PluginManifests/<slug>.json（源 = WSL `plugins/<dir>/plugin.json`）+ res/ 新 SVG。流程已补进 HANDOFF §2.5。另踩：plugin.json 插条目插进了模块对象内部（slug 行后）⇒ JSON 语法坏（dpf 解析报错，编译不读 json 不暴露）⇒ 正确位置 = 条目对象闭合 `}` 之后。
  - **真机验证 ✅ 2026-10-24（李在场）**：`add_module("rcm", "rcm-songroll", 4, 2)` → 新 id `1352659662496187`；`/modules` 确认 `rcm/rcm-songroll` 在列（7→8）；截图确认深色 SongRoll 面板完整落位不堆叠、原有模块完好；undo 后精确回 7。中途踩部署链路坑（见上条），修复后复验通过。exe 现役 = 103,025,152 B。
  - **patch 记账**：`11-songroll-build.patch`（父仓库：Makefile + plugins.cpp）+ `12-songroll-module.patch`（rcm-modules 子模块，应用根 `plugins/rcm-modules`：复活 + rename + UI 暂存 .bak + 胶文件）进 git；`replay_osc.py --check` **12/12 已存在**。
  - **顺带修 replay_osc.py 幂等判据缺陷**：01/06/08/09 四组的反 apply 被后续 patch 叠加推挤（CardinalCommon.cpp `:180`/`:1592`/`:1664`，全是后续组追加区）⇒ 误报冲突（该场景自 10-21 起从未被全量跑过）⇒ 加 `PATCH_MARKS` 独有标记兜底，重跑 12/12 全跳过。
  - **阶段 2 · 引擎逻辑 ✅ 2026-10-24**（WINE 运行级验证）：端口 10 in（RESET/RUN/EOP1-8）/ 11 out（PATTERN1-8/SECTION_END/SECTION_NUM/SONG_END）+ Transport 推进（**EOP 事件驱动**：每通道 repeats 递减、全通道完成→段边界发脉冲、回卷发 SONG_END）+ JSON 存取（dataToJson/dataFromJson + SongRollData::toJson/fromJson）+ 胶文件端口墩子（Rack 2 API：`createInput/createOutput` + `helpers.hpp`；🔴 **没墩子 OSC `/cable-add` 接不了线**——CableWidget::setCable 按 ModuleWidget 端口子控件定位，这是阶段 1「先保引擎」砍 UI 的到期代价）。**验证**（WINE + probe3：LFO 广播 8 个 EOP 口 + 预置双段 data）：电压贯通（LFO 2.7V→EOP 口 3.4V）、repeats 递减实锤（SR-DIAG left 2→1）、t+12s **SECTION_NUM 0→1 + out0 4.0→4.167V**（pattern 1→3）+ `ADVANCE sec=1` 日志。🔴 中途修：**枚举偏移寻址越界**（NUM_INPUTS=3 但 inputs[EOP+c] 到 9——`module_ports` 报 3/4 一眼看穿：Rack 端口数 = NUM_* 枚举值，必须展开列）。
  - **下一步（未做）**：阶段 3 UI Rack 2 适配（七个 `.bak`）；阶段 4 MCP 段落表工具（参照 `seq.py`）；阶段 5 联合 demo 机架（Clocked→SongRoll→PianoRoll×N + JW/Arrange 音色路由 + MiniArranger 和弦层）+ 真机试听。exe（11:04 构建）**未部署**——等李发话。
- **C5 · 注入器遗留问题清理 ✅ 2026-10-22 深夜完工**（纯文档，零代码）
  - 6 个 `inject_osc_*.py` 的降级标记 B1 时已加齐；本次把散落各处的已知坑（e2 漏 `+` / e3 块边界 off-by-one + 探针选错基线 exe + 端口残留 / d 两个已修 bug / 三条通用坑：幂等判据、端点数数法、git apply 静默跳过）集中成 `tools/osc_patch/injectors-LEGACY-NOTES.md`，各注入器头部加指向行。
  - `__pycache__` 已清（本就已被 .gitignore 排除）。注入器仅剩考古价值，日常重放一律走 `replay_osc.py` + `patches/*.patch`。

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
- **`/cables-page` · cables 分页（HANDOFF §6.1b B2 项）✅ 2026-10-21 下午完工并 WINE 运行级验证**
  - **动机**：`/cables` 全量返回，`CardinalCommon.cpp:544` 注释明说 poly 16 通道能撑爆 payload（同 E2 校正：防未来，不是救火）。
  - **新增端点 `/cables-page "ii"`（offset, limit）**，旧 `/cables`（全量 + `"h"` 单模块过滤）保留 ⇒ 零破坏。
  - 回包 payload = `"<returned>/<total>|id:inMod:inId:outMod:outId,..."`，items 与 `/cables` 同构；limit 上限 64；
    越界 offset → returned=0 但 total 仍报真实数；offset<0 / limit<=0 / limit>64 → `err:E_BAD_ARGS`。
  - **单模块过滤不做分页**（`/cables "h"` 场景线少）——组合需求将来再说。
  - 实现：`osc_cables_page_handler`（`CardinalCommon.cpp`，B3 /transport 之前）+ X-macro 表注册；
    导出为 `tools/osc_patch/patches/05-b2-cables-page.patch`（相对 01-04 应用后），`replay_osc.py` 第 5 组，
    校验端点总数 28→29。
  - MCP 侧：新增 `cardinal_cables_page`（offset/limit）工具 + `cables_page()`，工具数 55→56。
  - **验证**：WINE 探针 **11/11**（hello / load tar.zst blob / 全量 72 条合法 / (0,64)→64/72 / (64,64)→8/72 /
    (70,10)→2/72 / offset==total→0/72 / 越界→0/72 / 四种非法参数全 `err:E_BAD_ARGS` /
    步进拼接==全量逐条一致 / `/cables "h"` 零破坏）；MCP 层端到端 **8/8**（load→page→has_more→bad args→stepped）。
  - 🔴 **WINE/测试里 `/load` 必须发 tar.zst**：Rack 2 的 .vcv 是纯 JSON（legacy V1）或 zstd tar（V2），
    `/load` 只吃后者 ⇒ 裸 JSON 必 fail（且 128 KB 超 UDP 单包上限）。
    MCP 侧 `load_patch()` 用 `patchio.archive_bytes()` 包装（6513 B）；探针/测试必须照做。
- **`/module-copy` · 复制模块（HANDOFF §6.1b B3 项，李选方案 B）✅ 2026-10-21 下午完工并 WINE 运行级验证**
  - **语义 = 原生 `ModuleWidget::cloneAction(cloneCables=true)` 的 OSC 孪生**（不发明语义）：新 id = `random::u64() % (1<<53)`（避撞现有）；模块 JSON deepcopy + 存储目录 copy；`cloneCables=1` 只复制**输入侧**的线（上游 → 新模块同输入口；自 patch 连到自己）⇒ 不可能违反「同一输入口一根线」；位置 = 源右侧 1 HP（`setModulePosNearest`）；全程一个 ComplexAction ⇒ undo 一次全撤。
  - 🔴 **实现铁律（WINE 实测教训）**：`rack::history::State::push()` **只入栈不执行**！VCV 惯例 = 「先手动改引擎+UI，再 push 供 undo」。第一版照 cable-add 的「只 push」模式写 ⇒ 回包 ok 但 engine 毫无变化（手动 `/redo` 才生效）⇒ 重写为「手动执行 + push 记录」。
  - 入参 `"hi"`（moduleId, cloneCables）；回包 `"<newModuleId> copied_cables=<n>"`。MCP 工具 `cardinal_module_copy`（56→57）。
  - **验证**：WINE 探针 **12/13**（T3：41→42 模块 / 72→86 线 / 14 根新线全部落在克隆输入侧 / 上游保持 / 参数零差异；T6 undo×2 完全恢复基线；T7 redo×2；T5 坏 id → `err:E_NO_MODULE`）。唯一 FAIL = T8：**顺带实锤 `/cable-add` 不生效**（见 C3 订正）。MCP 层端到端 **7/7**。
  - patch = `tools/osc_patch/patches/06-b3-module-copy.patch`（相对 01-05 应用后）；`replay_osc.py` 第 6 组，端点 29→30。
  - exe 已部署：103,005,184 B，MD5 `751cdaea…`，13:47 构建。
- **C6 · 写端点修复（4 个）✅ 2026-10-21 深夜完工并 WINE 运行级验证**
  - **修的对象**：`/cable-add` `/cable-remove` `/module-move` `/module-remove` —— 全部「只 push 不手动执行」⇒ 回包 ok 但机架毫无变化（B3 排查时 T8 实锤：cable-add 后线数 86→86）。历史验收只验了回包 + undo 名，是 A1 缺口的深层案例。
  - **修法（对齐原生人类路径）**：cable-add = 手动 addCable + CableWidget（+ 同输入口旧线挤掉，CableRemove 先 setCable 提取）；cable-remove = setCable 提取后 removeCable + delete（析构联动 engine->removeCable）；module-move = `box.pos = newPos` + updateExpanders；module-remove = 一个 ComplexAction（级联 CableRemove 们 + ModuleRemove）+ 手动 removeModule + delete。
  - 🔴 **`/module-move` 单位语义 bug 一并修掉**：文档/工具说「x 格 y 行」，旧 handler 直接 `Vec(px, py)` 当 px 用（`box.pos` 是 px 且带 `RACK_OFFSET` 2000×100 格大偏移）⇒ 按格传只动 1/15。现按 `RACK_GRID_SIZE`(15×380)/`RACK_OFFSET` 换算。该端点此前从不生效，零兼容负担。
  - ⚠️ **module-move 位置真值 WINE 下不可直验**：autosave 只由 Scene 周期 step 触发，WINE 下实测 35s 不落盘（exp_move.py 证实）⇒ 位置归真机 A1 验收。
  - **验证**：WINE 探针 **14/14**（cable-add 72→73 + undo/redo 闭环；cable-remove 闭环；module-move 拓扑不变 + undo 名；module-remove 41→40 + 4 根级联删 + undo 完全恢复 41/72；B3 回归）；MCP 层端到端 **7/7**（四端点 + undo×4 恢复基线）。
  - patch = `tools/osc_patch/patches/07-c6-write-endpoints.patch`（相对 01-06 应用后）；`replay_osc.py` 第 7 组。exe 已部署：103,006,208 B，MD5 `836aea28…`。
- **E3 · 注册表抽函数 ✅ 2026-10-21 完工并运行级验证**（E 组收官）
  - **原问题**：thread 版（`lo_server_thread_add_method`）与 plain 版（`lo_server_add_method`）**各写一遍**
    完整端点表（28 端点 + fallback）。加一个新端点必须记得改两处，漏一处 ⇒ **静默失效**
    （编译照过、运行时不报错、端点就是不存在）。D 组加 `/screenshot` 时就踩过同类坑。
  - **改法（X-macro 单一真源）**：端点表只写一份 `CARDINAL_OSC_METHODS(REG)`，
    thread/plain 各自一个薄封装展开成对应 liblo 入口。两个入口后 3 参类型一致、
    只有第 1 参不同（`lo_server` vs `lo_server_thread`）⇒ **零类型强转**。
    两个薄封装各包在 `#ifdef CARDINAL_INIT_OSC_THREAD` / `#else` 里 ⇒ 编译期互斥、零 unused 警告。
  - **🔴 端点表不手抄**：注入器从源码**解析**两版实际注册行 → 与硬编码权威清单
    （数量+顺序+path+types+handler 全等）**逐条比对**才允许注入 ⇒ 不可能抄错/漏抄/错序。
  - **验证（E3 是纯重构，判据 = 行为不变）**：
    - WINE 全端点普查 30/30 PASS，**27 端点行为指纹与重构前基线版逐条一致**（diff 无差异）。
    - 端到端（Windows MCP → WSL Cardinal）14/14 PASS。
    - 编译零新增警告（消掉了 E3 初版的 misleading-indentation + unused-function）。
  - **顺带查清的事实**：4 个上游老端点（`/hello` `/param` `/host-param` `/load` `/midi-out`）
    **设计上就不回包**（`DISTRHO_SAFE_ASSERT_RETURN` 静默返回），E1 三段式没覆盖它们 —— 既有行为，非 bug。
- `/screenshot` 注册必须包在 `#ifdef CARDINAL_WINDOW_CAN_GENERATE_SCREENSHOTS` 内（`override/Window.cpp:45`）否则 Mini/GLES 编不过 —— ✅ **D 组已做到**

**F 组 · QuickJS 绑定** —— ✅ 2026-10-20 完工并运行级实测

- `libquickjs.a` 已静态链入（`Makefile.cardinal.mk:152-154`）⇒ 实测 exe 体积 +21KB 即 JS 代码量
- **实际实现与原设想的三处偏差**（都是实测逼出来的）：
  1. **不跑在 DSP 回调**。原计划「入队 + DSP 回调里 eval」是为了躲 GC 抖动；实际 OSC handler 已在 UI 线程串行 pump，直接在 handler 里同步 eval 更简单、且不存在并发问题（代价：UI 线程最多卡 2 秒 = 预算上限）
  2. **输入改「脚本文件 + 索引」**（`/osc-js-run i` + `/osc-js-list`）——「liblo 收不了 string」是当时的误判（已推翻，见文首 C4 订正），但脚本放 `js/` 可 git 管理，仍是更合李工作流的方案
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
| **E8** | 🔴 **死锁：A3 的验证闭环被编译阻塞** | 已核实。链条：`apply_recipe`/OSC 改的是 **param** → 改完读回来验证 → 唯一能读 param 实时值的探针是 `get_param`（走 `getDisplayValue()`）→ **该探针未编译**（`param-get` 在二进制里 = 0）。`read_live` 也不行：它读 autosave，而 autosave **只在 `/load` 和 GUI Ctrl+S 落盘，`/param` 改动永不落盘** ⇒ 读到的永远是旧值。<br>⇒ **要么把 A3 降级为「只验证结构不验证参数」，要么把它推到编译之后。** 我倾向后者——**验证闭环本来就是编译才有意义的**。<br>⚠️ 注意：绝不可以用「返回成功但数据为空」来掩盖（会变成假阳性诊断） | ✅ **已解（10-21 零编译绕过）**：`/param-get` 探针仍未编进 exe，但**引擎 `Manager::saveAutosave()` 用 `toJson()` 落盘 ⇒ autosave 必然带 params**，`/load` 会触发落盘 ⇒ 可用「文件 vs autosave」做**参数级 diff**。已落地为 `cardinal_diff` 的参数层 + `cardinal_deploy` 的参数级读回（工具 55）。⚠️ autosave 只在 `/load` 与 GUI Ctrl+S 落盘 ⇒ **纯 `/param` 改动仍不落盘**，参数级 diff 只在「部署后」有意义 |
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

## 六、已由李结案的事项（2026-10-21 裁决，**不是待办，别再开工**）

| 事项 | 裁决 | 理由与后续 |
|---|---|---|
| **`.mid` 导出** | ⛔ **作废** | 李 10-21：「废了就不管它」。乐谱导出已由 **A10 `.abc`** 覆盖（`tools/abc_export.py` + MCP `cardinal_export_abc`，实测 life1 三轨 / hana 四声部）。`.mid` 只是当初 A/B/C 三选一里**没被选中的那个**，不是欠的活。⚠️ 若将来真要喂 DAW，再从 `tools/abc_export.py` 派生一个序列化器（约 100 行、零新依赖） |
| **段落编排规格（Song 模式）** | ⏸ **暂缓，但三问已答（10-23 李拍板）** | 李 10-21：「Pattern 循环还是什么 Song 模式，暂时也不用管；后面需要的时候我会再让你做」。⇒ 现状 = MiniArranger 只有 pattern 循环，**没有 Song 模式**（`PROJECT2-SPEC.md` §15.9 第 3 条仍然成立）。**10-23 李对三问已拍板（可据此写规格，但仍等他再下令才开工）**：① 段落表 = 沿用 `SongRoll` 骨架（`sections[] → channels[] → (pattern / repeats / repeat_mode)`，每段点名用哪个 pattern、重复几遍，对标 Squarp Hapax 的 `pattern → section → chain`）② 和弦 = **独立层**（和弦进行不随段落切走，一直走到下一段；段落只切节奏/音色）③ 音色轨 = **每段独立**（切段 = 换音色，每段各轨指定自己的模块链）<br>🔨 **10-24 工程方案预研（李倾向 C++ 路线，等开工令）**：**参考代码实查**（WSL `~/Cardinal/plugins/`）：SongRoll 骨架 = 数据类（SongRollData/Section/ChannelConfig）完整 + UI Widget 半成品（Pattern/Repeat/ClockDiv 控制件、RollArea、DragModes），但**端口全 0 / `step()` 空 / dataToJson 空壳 / Transport 只有 `currentSection` 游标** ⇒ 引擎逻辑（端口+推进+存取）从零写，UI 待编译验证。**可依靠件**：`ImpromptuModular/src/PhraseSeq32.cpp` + `PhraseSeqUtil`（乐句 `Seq#` CV 选段的最直接参照）· `rcm-modules/src/PianoRoll/`（PATTERN_IN 消费端 + JSON 存取样板）· `JW-Modules/Arrange`（16×64 门控 + EOC 尾脉冲，音色路由现成件）· `ImpromptuModular/src/Clocked.cpp`（子时钟链，clock_div 参照）· `Starsea/src/MiniArranger.cpp`（项目内同环境三件套模式：端口/step/存取）。**联合架构（四层）**：Clocked → SongRoll（新写）→ `PATTERN#` CV → PianoRoll×N（pattern 层，音符表纯 JSON 可灌）；SongRoll 段号/边界脉冲 → JW/Arrange（音色路由层）；MiniArranger 和弦层独立时钟、**不参与段切换**。**岔路待拍**：复活 SongRoll vs 新建模块 vs 并入 MiniArranger（并入=动他调过的 40HP 面板，有布局风险，不推荐）；UI 保留 vs 先砍 UI 保引擎。 |
| **life1 音符密度三修法** | ⛔ **不修** | 李 10-21：「Life1 那个不用修了」。且这事**本来就已落地**：10-17 李按 Quadeca 权威原文第 65/68/51 行选了**方案 B**（休止符 + 短时值），新机架 `patches/quadeca_life1_wdtg.vcv` 已交付并经李确认有声。⇒ 记账上的「待选」是过时条目。⚠️ 残留（本批**不做**，仅备案）：实测三层密度均 50%（休止符已落），但 `duration` 字段全为 `None` ⇒ 方案 B 的「短时值」那半未做；混响仍是 `Valley/Feline`（10-18 起项目纪律 = 混响统一用 `Plateau`）。若将来要修，动这两个点即可，**不要重跑生成器**（会冲掉李手工调的布局） |

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
