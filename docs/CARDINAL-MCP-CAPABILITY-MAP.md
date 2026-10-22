# Cardinal MCP 能力地图：对标研究 + 能力需求文档

> 作者：许清楚 (PM)｜架构复核：software-architect｜日期：2026-10-19｜状态：定稿 v3
> 目标：定义「一个合格的 DCC 宿主级 MCP」应该有什么，并给出 Cardinal 的完整能力路线。
> **第一部分的地基是「别人真的这么做了」，每个论断附链接；查不到就写「未查到」。

## ★ 路径约定（A5 修正，先读这条再查行号）

`src/Makefile:46` 会用 `override/` 下的同名文件**替换** `Rack/src/` 原件——**编译生效的是 override 版**。本仓库有**三个**容易混的同名文件：

| 文件名 | 编译生效版 | 另一份（不生效） |
|--------|-----------|----------------|
| `Engine.cpp` | `src/override/Engine.cpp` | `src/Rack/src/engine/Engine.cpp`（行号不同！）|
| `Window.cpp` | `src/override/Window.cpp` | `src/Rack/src/window/Window.cpp` |
| `MenuBar.cpp` | `src/override/MenuBar.cpp` | — |

本档引用规则：**未标路径的 Engine.cpp 一律指 `src/override/Engine.cpp`**；标了 `src/Rack/src/engine/Engine.cpp` 的才是 Rack 原版。⚠️ 两版行号不同（如 `Engine::fromJson`：override 版在 `:1241` 起，Rack 版在 `:1216` 起）。

## ★ v3 摘要：新增 OSC 响应契约层（架构层，PM 已逐条复核）

v3 把**「handler 之间怎么保持一致」**独立成第 2.3 节。这是**协议级**问题——编完再改意味着 C++ 与 MCP 侧 Python 同时返工，**必须在编译前定稿**。四条契约：统一三段式响应（2.3.1）／列表类分页（2.3.2）／**诚实的事务语义**（2.3.3）／注册表 2×2 变体矩阵（2.3.4）。

**⭐ 2.3.3 是本次最有价值的一环**：`/load` 返回 `applied:N skipped:M`，skipped 列表**直接就是「为什么不响」的第一候选原因**，纯 MCP 侧即可把「加载诊断」接进「静音诊断」——零新 hook，且正落在我们的差异化定位上。

**同时 v3 修正了 v2 的一个过度承诺**：`ComplexAction` **不保证原子性**（`ModuleAdd::redo()` 吞异常后继续 `addModule`；`ComplexAction::push()` 也不递归），所以不应宣称 all-or-nothing。

## ★ v2 修正摘要（经架构师源码级复核，两条我原判错误）

| # | v1 的说法 | v2 修正 | 依据 |
|---|----------|---------|------|
| 1 | 「截图白捡，`Window::screenshot()` 现成」 | **错。GUI 编的 `src/override/Window.cpp:753` 的 `screenshot()` 是空函数**。真正可用的是异步两段式 `rack::window::generateScreenshot()` → base64 回调 | `override/Window.cpp:748-751` 空；`CardinalCommon.hpp:26` 声明；`override/Window.cpp:906-910` 实现 |
| 2 | 「Engine 无 undo，撤销只能 MCP 侧自建快照栈」 | **错。`history::State` 完整可编程**，且 `ComplexAction` 天然是事务容器 | `history.cpp:234/260/267`；`history.hpp:52-60` |
| 3 | 探针「是否已编译」待确认 | **已确认：100% 未编译**。`bin/Cardinal` 的 `param-get=0`，且二进制（9/20）比源码（10/19）早一个月 | architect 实测 `strings` |
| 4 | MIDI「接口存在性未确认」 | **已确认**：MIDI OUT 可零 hook；MIDI IN 需加全局注册表 | `plugincontext.hpp:100` / `CardinalCommon.cpp:202` |
| 5 | 「`CARDINAL_OSC_AUTOSTART` 默认开」 | 半对。它是 `getenv` **运行期**读取（`MenuBar.cpp:741`），**不是编译期宏**，无定义处 | `MenuBar.cpp:738-741` |

---

## 第一部分：对标研究 —— DCC MCP 能力分类表

### 1.1 样本清单（4 个宿主，7 个主流实现）

| # | 实现 | 链接 | 脚本执行工具 |
|---|------|------|--------------|
| U1 | Unity MCP (coplaydev) | https://coplaydev.github.io/unity-mcp/reference/tools/scripting_ext/execute_code | ✅ `execute_code`，Roslyn/CodeDom 内存编译 C# |
| U2 | Unity MCP (joel-wehr) | https://glama.ai/mcp/servers/joel-wehr/unity-mcp/tools/execute_code | ✅ `execute_code`，完整 UnityEngine/UnityEditor + 反射 |
| U3 | Unity Code MCP Server (Signal-Loop) | https://mcpservers.org/servers/signal-loop/unitycodemcpserver | ✅ `execute_csharp_script_in_unity_editor`，含 reflection |
| B1 | Blender MCP (ahujasid, 事实标准, ~30.4k star) | https://mcp.so/server/blender/ahujasid ｜ https://mcp.film/mcps/blender/ | ✅ `execute_blender_code`，任意 Python |
| B2 | Blender-MCP (Aayushdubey101, 工程化分支) | https://glama.ai/mcp/servers/Aayushdubey101/Blender-MCP | ✅ `blender_execute_python` + **只读模式** |
| E1 | unreal-mcp (runreal) | https://npmjs.org/package/@runreal/unreal-mcp | ✅ `editor_run_python`（走 UE 官方 Python Remote Execution）|
| E2 | unreal-mcp (Christancho-co) | https://glama.ai/mcp/servers/Christancho-co/unreal-mcp | ✅ `unreal_execute_python` |
| E3 | unreal-mcp (chongdashu, C++ 插件版) | https://claudeskills.info/skills/aiskillstore/marketplace/unreal-engine-developer | ✅ Python + Blueprint 节点图操作 |
| G1 | godot-mcp (Bouelon, 18 工具) | https://github.com/Bouelon/godot-mcp | ✅ `execute_script`（GDScript）|
| G2 | godot-mcp (windseries69) | https://lobehub.com/en/mcp/windseries69-godot-mcp | ✅ `godot_execute` + `godot_call` 175+ 方法 |

### 1.2 ★ 关键结论：脚本执行是「标配」，不是加分项

**10 个实现里 10 个都有「在宿主进程里执行任意代码」的工具。** 这是 DCC MCP 与普通 REST 包装器的根本区别：

- **U1** 的实现细节最值得抄：代码作为**方法体**在内存中编译（Roslyn，回退 CodeDom），预导入 `UnityEngine`/`UnityEditor` 命名空间，`return` 作为回传通道。**不生成脚本文件**。带 `safety_checks` 开关（拦 `File.Delete`、`Process.Start`、死循环），文档明确写「不是完整沙箱，高级绕过可能成功」。
- **U1 还有历史栈**：`action` 支持 `get_history` / `replay` / `clear_history`。也就是**执行历史可回放**。
- **U3** 加了 `enter_play_mode` / `play_unity_game` / `get_unity_game_view_window_screenshot` / `exit_play_mode`，构成「执行 → 跑 → 截图 → 读日志」的**闭环验证**。
- **E1/E2** 的关键工程手法：代码被 harness 包装，输出用哨兵包裹后转 JSON，**编辑器里的异常被转成结构化错误**而不是裸 traceback 污染 stdout。
- **E2** 的安全声明很坦率：「`unreal_execute_python` 在编辑器解释器里无沙箱运行，拥有完整 `unreal` 模块权限，可修改或删除项目内容，请像对待编辑器里的 Python 控制台一样对待它。」
- **G1** 走了另一条路：**HTTP 服务跑在编辑器插件里**（127.0.0.1:6789），MCP server 做 stdio→HTTP 翻译。

**对 Cardinal 的直接含义**：如果 Cardinal MCP 只提供「调参数/存盘」这类窄工具，它在能力维度上比这 10 个实现都弱一个数量级。用户会问「为什么我不能像改 Unity 那样随便操作」。

### 1.3 危险操作保护：四种手法，各实现采用组合

| 手法 | 谁在用 | 有效性 |
|------|--------|--------|
| 模式化只读开关 | **B2** `BLENDER_MCP_READ_ONLY=true` 全局开关 | ★★★★★ 最强，一键封死写工具 |
| 工具级只读标注 | E2 表格里有 `Read-only ✅` 列；G1 有 `destructiveHint` | ★★★★ 让 LLM 自己判断 |
| 危险模式标注 | U2 `execute_code` 标 `destructive=true`；E2 `unreal_delete_actor` 标 `Destructive` | ★★★ |
| 模式开关/参数检查 | U1 `safety_checks`（拦已知模式） | ★★ 明确自述「非沙箱」 |

**没有任何一个实现做了真正的沙箱。** 共识是：靠**模式开关 + 标注 + 隔离环境**（B2/U3 推荐用独立工程或 VM/容器）。

### 1.4 交互形态：5 种，MCP 全都支持

1. **一次性工具**（绝大多数）：`execute_code` / `set_param` / `delete_actor`
2. **长时任务 job + 轮询**：B1 的 `generate_hyper3d_model_via_text` → `poll_rodin_job_status` → `import_generated_asset`（生成→查询→导入三段式）
3. **资源型 resource**：G1 的 `preview_asset` 返回 base64 PNG
4. **图片内容**：B1 `get_viewport_screenshot`、`E2 unreal_take_screenshot`、`U3 get_unity_game_view_window_screenshot` —— MCP 的 image content 类型
5. **订阅/事件推送**：**未查到任何一个 DCC MCP 实现了事件订阅。** 全靠轮询。这是一个**行业空白**——也是 Cardinal 可以超越的点。

### 1.5 能力分类表（10 类，第二部分的骨架）

| 类别 | Unity | Blender | Unreal | Godot | 成熟度 |
|------|-------|--------|--------|-------|--------|
| 1 状态读回（层级/属性） | ✅ | ✅ | ✅ | ✅ | **成熟** |
| 2 场景构建（增删改/批处理） | ✅ | ✅ | ✅ | ✅ | **成熟** |
| 3 脚本/代码执行 | ✅ | ✅ | ✅ | ✅ | **成熟** |
| 4 资产/资源管理 | ✅ | ✅ | ✅ | ✅ | 成熟 |
| 5 截图/视口抓取 | ✅ | ✅ | ✅ | ✅ | 成熟（**高频使用**）|
| 6 运行态控制（play/stop/时间） | ✅ | ➖ | ✅ | ✅ | 成熟 |
| 7 日志/错误读回 | ✅ | ➖ | ✅ | ✅ | 成熟（U3 把它做成核心用例）|
| 8 物理/运行时状态 | ✅ | ➖ | ➖ | ➖ | **弱** |
| 9 性能 profiling | ✅ | ➖ | ✅（`stat unit`）| ➖ | **弱** |
| 10 撤销/事务 | ✅（Unity 原生 undo）| ➖ | ➖（C++ 插件版有）| ➖ | **几乎空白** |
| 11 事件订阅推送 | ❌ | ❌ | ❌ | ❌ | **全行业空白** |

### 1.6 五条可直接抄的结论

1. **必须有 code execution。** 10/10。没有它，MCP 就是个窄工具集合。
2. **必须有 screenshot。** 4/4 宿主都有，且都是「AI 迭代自己作品」的核心闭环。
3. **必须有日志/错误读回。** U3 的整个卖点就是「读错误 → 修 → 再读」闭环。
4. **必须有只读模式。** 全部采用。
5. **必须有执行历史。** 只有 U1 做了（`get_history`/`replay`）。但代价极低，强烈建议抄。

---

## 第二部分：Cardinal MCP 完整能力地图

### 2.0 先纠正三个前提事实（实测所得，与初始假设不同）

这三条改变了成本估算，**必须先说清楚**：

| 初始假设 | 实测结论 | 证据 |
|---------|---------|------|
| 「OSC 只有 4 个 handler，全单向写」 | **前半对后半错**。原版确实只有 `/hello` `/host-param` `/load` `/param` 且不回数据；但**工作区里已经有人加了 6 个只读探针**：`/modules` `/param-get` `/ports` `/signal` `/light` `/screenshot`，且 `/resp` 回复通道已实现 | `src/CardinalCommon.cpp:357-370`（`CARDINAL-MCP-READ-PROBES-BEGIN` 区块）、`1135-1160` 注册表 |
| 「GUI 版编译掉了所有能回复的 handler」 | **不成立**。GUI 版走 `#else` 分支，同样注册了全部只读探针，只是没有 `lo_server_thread` | `src/CardinalCommon.cpp:1148-1165` |
| 「`CARDINAL_INIT_OSC_THREAD` 需要 HEADLESS」 | 该宏只在初始化路径上有差异，但**GUI 版靠 `stepRemoteServer()` 每帧轮询**，功能等价 | `src/CardinalCommon.cpp:1192-1206`；`src/override/MenuBar.cpp:852` 每帧调用；`CARDINAL_OSC_AUTOSTART` 默认开 |

**⚠️ 已确认（架构师实测 `strings`）：这 6 个探针在源码里存在，但 100% 没编进当前二进制。**

```
bin/Cardinal:        param-get=0   /host-param=1   /screenshot=1
bin/CardinalNative:  param-get=0                  /host-param=1
bin/CardinalMini:    param-get=0                  /host-param=1
```
时间线解释原因：`src/CardinalCommon.cpp` = 2026-10-19 14:41（探针在此，modified 未提交，HEAD=`8aa0fc7`），而 `bin/Cardinal` = 2026-09-20 17:28，**比源码早一个月**。

**⇒ 结论：读侧能力从「已就绪」降级为「需编译一次」。但改动是纯增量的**——探针区块被 `CARDINAL-MCP-READ-PROBES-BEGIN`（`:357`）/ `END`（`:689`）包着，不碰原有 4 个 handler，编译风险低。

**🚨 给 engineer 的验证陷阱**：**不要用 `grep -c '/modules'` 判断**——它返回 11，但全是 JUCE 头文件路径（`../../modules/water/processors/...`）假阳性。**必须用带连字符的 `param-get` 或更唯一的函数名 `osc_modules_handler`。**

### 2.0.1 ⚠️ 三条易踩的实现约束（架构师补充）

| # | 约束 | 后果 |
|---|------|------|
| 1 | **handler 注册必须双写**：thread 版 `:1135-1145`，非 thread 版 `:1152-1160` | 只加一处会在切换构建配置时**静默失效**（不报错，只是收不到消息） |
| 2 | **`CARDINAL_OSC_AUTOSTART` 是 `getenv` 运行期读取**（`MenuBar.cpp:741`），不是编译期宏，全仓无 `-D` 定义 | 不能用它做 `#if` 分支判断 |
| 3 | `/ports` **只回前 4 个通道**（`CardinalCommon.cpp:544` 注释：poly 到 16 通道会撑爆 payload；`PORT_MAX_CHANNELS=16`，`engine/Port.hpp:11`） | poly 模块做完整声道分析时会**静默截断**，需告知 MCP 侧或加 depth 参数 |

### 2.1 逐类论证

图例：实现路径 = `MCP侧`（纯 Python，不需编译）｜`探针`（改 C++ 需编译）｜`引擎`（需改引擎/plugin API）

---

#### 类 1：状态读回 ★★★★★ P0

| 能力 | 需要 | 实现路径 | 风险 |
|------|------|---------|------|
| 列模块（id/plugin/model） | ✅ | 探针（`/modules` 已写） | 无 |
| 读参数显示值 | ✅ | 探针（`/param-get` 已写，走 `getDisplayValue`） | 无 |
| 读端口连接数 + 各通道电压 | ✅ | 探针（`/ports` 已写） | **DSP 线程并发读**，需确认不在音频线程直接遍历 |
| 读 LED 亮度 | ✅ | 探针（`/light` 已写） | 无 |
| **读完整机架 JSON（活的，非文件）** | ✅ | 探针：`Engine::toJson()` → OSC 回传 | ⚠️ **payload 可能几十 KB，会爆 OSC UDP 单包**。必须分页或改走文件+HTTP |
| 读模块参数**元数据**（名称/量纲/范围/枚举档位） | ✅ | `MCP侧`（解析 .vcv + 插件 dspec.json，离线） | 无 |
| 读当前 patch 路径/是否已加载 | ✅ | `MCP侧`（`read_live()` 已有） | 无 |

**为什么 `getDisplayValue` 而非 `getValue`（这条设计已被前人写进注释，值得保留）**：
Cardinal 旋钮绝大多数存归一化 0..1，但面板显示物理量（ADSR 存 0.275 = 275ms；Bogaudio-VCO 存 6.0 八度 = 220Hz）。`getValue()` 对外部工具无意义。

**结论：类 1 是 Cardinal MCP 的地基，且已实现约 70%。剩余工作是「验证 + 补 toJson 分页」。**

---

#### 类 2：场景/机架构建 ★★★★★ P0 —— **用户的核心需求**

用户的原话是「**用代码生成 patch**」。所以这不是附属功能，**这是主战场**。

| 能力 | 需要 | 实现路径 | 风险 |
|------|------|---------|------|
| 加模块 | ✅ | **`MCP侧`** — 改 .vcv JSON + `/load` | ⚠️ **module id 分配冲突** |
| 删模块 | ✅ | `MCP侧` — 改 JSON | ⚠️ 需同步清理 cables 里的悬空引用 |
| 改接线（cable） | ✅ | `MCP侧` — 改 JSON | ⚠️ **端口编号不连续，各插件不同**，必须查 dspec |
| 批量操作（一次加 N 个模块） | ✅ | `MCP侧` — 单次改 JSON | ⚠️ **非原子**（见 2.3.3）：引擎语义是尽力而为 |
| 自动排版（模块位置不重叠） | ✅ | `MCP侧` — 纯算法 | 无 |
| 撤销 / 重做 | ✅ | 探针 — **原生 `history::State`**（不是 MCP 侧快照栈，见类 9） | GUI only（依赖 `APP->scene`）|

**★ 重大发现 —— 这条路是通的，且是 Cardinal 独有的优势：**
`Engine` 公开 API 有完整的 `addModule` / `removeModule` / `addCable` / `removeCable` / `setParamValue`（`src/Rack/include/engine/Engine.hpp:108-186`）。
→ **不需要模拟鼠标点击去拖线**。JSON 路线（离线改 + `/load`）和引擎 API 路线（探针直接调）都可行，**JSON 路线成本低一个数量级，且天然支持撤销**。

**建议主路线 = JSON 离线改写 + `/load`；引擎 API 探针留作「不中断运行态的活体修改」（如运行中改参数而不重载整个 patch）。**

**风险点必须写清楚：**
- `.vcv` 是 JSON，模块是 **plugin/model 二元组**标识
- **端口编号不连续**：输入 1、输出 1、输入 2…… 各插件顺序不同，**必须查插件 dspec.json**，不能假设
- 参数是**不同量纲**：归一化值 / 半音 / 八度 / Hz / ms 混杂

---

#### 类 3：代码执行 ★★★★★ P0 —— **可行性已验证**

**★ 结论：可以做，而且成本比想象低。**

实测证据：
```
src/Makefile.cardinal.mk:153
    RACK_EXTRA_LIBS += $(DEP_LIB_PATH)/libquickjs.a
```
`deps/QuickJS/` 源码完整，`libquickjs.a` **已经被链接进 Cardinal 全量构建**（非 mini 变体）。

**但有个关键缺口**：`libquickjs.a` 链接了却**没有任何宿主绑定**——
- `grep JSEngine` 在 `src/Rack/src/` `src/Rack/include/` → **零命中**
- `grep 'JS_NewRuntime|JS_Eval' src/` → 只命中 `quickjs.h` 头文件本身
- `plugin.hpp` 里**零个** JS 相关符号

即：Cardinal **链接了 QuickJS，但没暴露脚本引擎**。Rack v2 移除了 v1 的 `JSEngine` 机制。

**因此「执行任意代码」有两条路：**

| 路线 | 做法 | 工作量 | 能力 | 风险 |
|------|------|-------|------|------|
| **A. 补 JS 宿主绑定** | 新建 `src/cardinal_js.cpp`，用已链接的 `libquickjs.a` 建一个 `JSRuntime`，把 Engine/Module/ParamQuantity/Cable **绑定成 JS 对象**（`engine.getModules()` / `module.params` / `engine.portsVoltage(id)`），加 `/eval "js"` handler | **中**（约 300-500 行绑定 + 编译） | ★★★★★ 真正的万能遥控器：一条工具解决类 1/2/4/6/7/8 全部读+写 | 需绑线程模型（DSP 线程 vs UI 线程）；QuickJS 无沙箱（同 Unity/Blender） |
| **B. 定向 C++ 探针** | 逐能力加 handler（现有 6 个就是这个思路） | **小**，每个 30-80 行 | ★★★ 够用但扩展性差，加一个能力就要编译一次 | **编译成本会持续累积** |

**★ 强烈建议路线 A。** 理由：
1. **编译是 Cardinal 最贵的成本**（102MB 二进制，全量重编）。路线 B 每加一个能力就编一次；路线 A **一次编译换来无限能力**，且能**消灭绝大部分探针需求**。
2. **引擎写 API 已齐全**（`addModule`/`addCable`/`setParamValue`…），绑定工作量主要是胶水。
3. 直接消灭「静音检测/信号流追踪」这类逻辑——**不再需要在 C++ 里写算法，在 JS 里写一次就够**。
4. 现有 `/param-get` 的注释显示前人已经踩过量纲的坑，JS 层正好承载 `getDisplayValue` 这类语义。

**Cardinal 有 Lua 吗？没有。有 ChakraCore 吗？没有。** → **只有 QuickJS 这一个现成选择**，别去找 Lua。

**★ 快速路线（架构师补充，我已核实）：不要从零写绑定。**
`plugins/AriaModules/src/javascript.hpp`（85 行，完整 RAII：`JS_NewRuntime`/`JS_NewContext`/`JS_Eval`/`JS_ToCString`/`JS_ToInt32`）就是现成封装，使用者 `plugins/AriaModules/src/Qqqq.cpp:287-307`。**作者注释里自述「这就是 VCV Prototype 用的同一个引擎」。**

**★ 能力比 v1 描述的更完整**：`libquickjs.a` 含 `quickjs-libc.o`，即 **`os` 模块**（`exec/kill/open/pipe`，`deps/QuickJS/quickjs-libc.c:2591`）和 **`std` 模块**（`popen/getenv/exit`，`:1241`）。已验证编进产物：`strings bin/Cardinal | grep -c leadsheetToQqqq` = 2，能捞到完整 JS 源码。

**★ 线程模型结论（架构师查证，我采纳）**：**handler 只入队，实际 eval 在宿主音频 `run()` 回调里按预算执行。**
- 理由：GUI 版 OSC 本身就在 UI 线程被 pump（`MenuBar.cpp:852`），所以「放 OSC handler」= UI 线程；但 **JS GC/分配耗时不可控**，跑带运行时可能触发 xrun（`Engine::getMeterMax()` `Engine.hpp:88` 会飙升，能测出来）
- 推荐形态：`std::deque<std::string>` + 标志位入队，每 N 个 block 或超总耗时预算就延后。**OSC 线程永不阻塞、音频线程永不被打断**
- DSP 回调点：`CardinalPluginContext::processCounter`（`include/plugincontext.hpp:82`），在 `src/CardinalUI.cpp:649` / `src/CardinalPlugin.cpp:1288` 自增

**安全姿态**（对标 B2 的 `BLENDER_MCP_READ_ONLY`）：
`CARDINAL_MCP_READ_ONLY=1` → 剥离 `Engine` 的写方法绑定（`addModule`/`setParamValue`/`loadPatch`…），JS 层只剩读。这是**机制性封死**，比 U1 的模式匹配可靠得多。

**★ 执行历史**（抄 U1）：`/eval` 顺带把每段代码 + 返回值追加到环形缓冲，提供 `js_history()` / `js_replay(i)`。成本几乎为零，价值明确。

---

#### 类 4：诊断 ★★★★★ P0 —— **用户的核心痛点**

用户痛点原话：「**机架加载了但不响 / 静音**」。这是最高价值的能力，也是**当前 MCP 完全没有的**。

| 能力 | 需要 | 实现路径 | 优先级 |
|------|------|---------|--------|
| **静音检测**（某模块输入有连接但电压恒为 0） | ✅ | 探针 `/ports` 已提供电压数据 → **分析在 `MCP侧` 做** | P0 |
| **信号流追踪**（从模块 A 的输出一路追踪到模块 Z 的输入） | ✅ | 拓扑分析放 `MCP侧`（需读活的 cable 列表 → 需探针） | P0 |
| **音频线程断链检测**（模块 process 被调用但无输出） | ✅ | 探针 + JS（路线 A 下最自然） | P1 |
| **静音原因分类**（无输出 / 被 bypass / 增益为 0 / 上游无信号 / 模块加载失败） | ✅ | `MCP侧` 读 `/light` + `bypass` 状态 | P0 |
| 模块加载失败原因 | ✅ | 探针（需捕获 plugin load 错误） | P0 |
| **模块黑名单**（加载失败的插件） | ✅ | `MCP侧`（读 plugin 目录 + dspec 校验） | P1 |
| CPU / DSP 负载 | ✅ | `Engine::getMeterAverage()/getMeterMax()`（**API 已存在，Engine.hpp:87-90**） | P1 |
| 线程数 / 采样率 | ✅ | 探针（`Engine::getSampleRate()` Engine.hpp:50） | P1 |

**★ 线程安全结论（架构师查证 + 我复核）：`/ports` 读电压在音频线程是真并发，但不崩，可接受——前提是文档标注。**

- Engine 有 `SharedMutex`（`src/Rack/src/engine/Engine.cpp:227`，⚠️ Rack 版非 override 版），`stepBlock` 持 `blockMutex` + `SharedLock`（`:537-538`）
- **但这把锁不保护 Port 电压**：`Module::doProcess()`（`engine/Module.cpp:335-370`）在音频线程直接写 `outputs`/`lights`，全程在 share-lock 区间内，**不额外加锁**
- ⇒ OSC 线程 share-lock 拿 module 指针后直接读 `port.getPolyVoltage()`，与音频线程**真并发**。两线程都持锁 ⇒ **锁形同虚设**
- **可接受依据**：Cardinal 自己的 `PortWidget::step()` / `LightWidget::step()` 也在 UI 线程无锁读同一份数据，这是 Rack 的既定设计
- **实际风险**：单个对齐 float 读在 x86/ARM 上不会撕裂，最坏是读到 block 边界附近的旧值或新值。**不会崩**

**⇒ 给 engineer 的三条要求**：① 保留现有实现；② MCP 文档标注「返回值是瞬时采样，可能来自上一次 block」；③ `/signal` 的 1e-4V 阈值本身有迟滞容忍度，不受影响。

**⚠️ CPU meter 轮询必须节流**：`getMeterAverage()` 的对外值**每 1 秒才刷新一次**（`src/Rack/src/engine/Engine.cpp:576` `meterUpdateDuration = 1.0`）。MCP 侧 1 秒内轮询全是同一个值。

**★ 让 `confidence` 字段真正有据可依的三个额外数据源（架构师补充，我已核实）：**

| 数据源 | 坐标 | 价值 |
|--------|------|------|
| **`Module::isBypassed()`** | `engine/Module.hpp:465`，实现 `engine/Module.cpp:286-288` | **引擎自 bypass 判定的权威值**。接进 `/modules` 后能区分「被 bypass 了」vs「没 bypass 但真的没输出」——**这两者在纯 `/signal` 视角下长得一模一样（都是 0V）**，confidence 可显著拉开 |
| **`ParamQuantity::getDisplayValue()`** | `engine/ParamQuantity.hpp:97` | 直接判断「增益旋钮拧到 0 了」——`增益0` 这一类诊断靠的就是它 |
| **`Cable` public 字段** | `engine/Cable.hpp:15-19`：`inputModule/inputId/outputModule/outputId` 全部 public | 配 `Engine::getCableIds()`（`Engine.hpp:163`）即可，**`signal_flow` 拓扑追踪零 hook** |

**★ 强推一个 Cardinal 独有的诊断能力 —— `diagnose_silence(patch?)`：**
一个工具，输入机架，输出**有序的问题清单**：「模块 X 的输入 2 有 cable 来自模块 Y，但两者电压均为 0 → 疑似 Y 未输出或 X 输入被占用」。
**理由**：这是用户唯一的真实痛点，而且**完全可以在 MCP 侧基于 `/ports` + `/light` + JSON 实现，零新增编译**。
诊断结果应该是**结构化的**（`{module, issue, confidence, evidence}`），不是一段自然语言——让 LLM 能据此决定下一步调什么。

---

#### 类 5：资产与文件 ★★★★☆ P1

| 能力 | 需要 | 实现路径 | 说明 |
|------|------|---------|------|
| 列出/搜索 patch | ✅ | `MCP侧` ✅ 已实现 | `list_patches()` |
| patch 元信息解析 | ✅ | `MCP侧` ✅ 已实现 | `patch_info()` |
| 加载 patch | ✅ | `MCP侧` ✅ 已实现 | `load_patch()` |
| 保存活体 patch | ✅ | `MCP侧` ✅ 已实现 | `save_live()` |
| 导出/导入 | ✅ | `MCP侧` | `read_live()` 已实现读 |
| **preset 读写**（单模块 preset） | ✅ | `MCP侧` | 解析插件 `presets/` 目录 |
| **插件元数据查询**（某 slug 有哪些 model） | ✅ | `MCP侧` | 读 `plugins/<slug>/plugin.json` + `dspec.json` |
| **samples 管理** | ⚠️ 部分 | `MCP侧` | 只能列目录、查存在；**加载 sample 到模块做不到**（需模块私有 API） |
| **音频录制导出** | ❌ | — | 需要录音引擎，Cardinal 无此能力 |

**插件元数据是类 2 的隐形依赖**：`add_module(plugin, model)` 和 `patch_connect` 都必须先知道有哪些 model、哪些端口、什么参数量纲。建议做成一个 `plugin_catalog()` 工具 + MCP **resource**（可被 `resources/list` 发现），而不是每次现查。

---

#### 类 6：时间与传输控制 ★★★☆☆ P2

| 能力 | 需要 | 实现路径 | 说明 |
|------|------|---------|------|
| play / pause / stop | ✅ | 探针 | 经 `host-param` 或直接调 Transport |
| tempo 读写 | ✅ | 探针 | 同上 |
| **MIDI OUT**（Cardinal → 宿主） | ✅ **零 hook** | `CardinalPluginContext::writeMidiMessage(const rack::midi::Message&, uint8_t channel)`，声明 `include/plugincontext.hpp:100`，实现 `src/CardinalCommon.cpp:202`。⚠️ 两个 assert：`message.frame >= 0`（`:208`，**必须自己设 frame**）、`size > 0`；开头 `if (bypassed) return;`（`:204`） |
| **MIDI IN**（外部 → 模块） | ⚠️ **需加 hook** | `midi::InputQueue::onMessage()` 是 public virtual（`include/midi.hpp:265`），理论上可直接调。但**无全局注册表能枚举「当前所有 InputQueue」**——`midi::Port::driverId/deviceId`（`:203-205`）private 无遍历接口；`midiloopback::Context`（`include/midiloopback.hpp:14-19`）只有 device 粒度。⇒ 需在 `midi::Input` 侧建全局注册表（约 30 行，`src/Rack/src/midi.cpp`） |
| **MIDI 映射表读取** | ❌ **不存在** | Cardinal 已删 MIDI 面板：`src/app/` 下只有 `MidiDisplay.hpp` 无 `MidiPanel`；`override/MenuBar.cpp:805` 只剩 "Enable/Reconnect MIDI" 开关。**别写进能力矩阵** |
| MIDI 录制 / 音频录制 | ❌ 做不到 | 无录音引擎 |

**诚实结论：这一类大部分「做不到」或「勉强可做」，不应作为 v1 目标。** 但 play/pause 是诊断的前提（很多模块要在 running 状态才出声），所以 **play/pause 是 P2 里唯一值得做的**。**MIDI OUT 可零 hook 纳入 P2；MIDI IN 推到 P3。**

---

#### 类 7：视口/截图 ★★★★★ P0 —— **机制比 v1 判断复杂，但价值不变**

**★ v2 修正：v1 说「白捡」是错的。** 我当时读到的是 Rack 原版 `Window::screenshot()`，但 **GUI 构建根本不编它**。

**为什么**（`src/Makefile.cardinal.mk:85-95`）：
```make
ifeq ($(DSP_UI_SPLIT),true)
FILES_DSP += RemoteNanoVG.cpp / RemoteWindow.cpp      # 空 stub
else ifeq ($(HEADLESS),true)
FILES_DSP += RemoteNanoVG.cpp / RemoteWindow.cpp      # 空 stub
else
FILES_UI  = CardinalUI.cpp / glfw.cpp / MenuBar.cpp / Window.cpp   # ← GUI 走这条
endif
```
GUI 编译的是 **`src/override/Window.cpp`**（Cardinal 自己那份），而那里：
```cpp
// src/override/Window.cpp:748-751
void Window::screenshotModules(const std::string& screenshotsDir, float zoom) {
}
```
`src/custom/RemoteWindow.cpp:111/115` 同样是空 stub。→ **v1 结论作废。**

**⭐ 但 GUI 有一套完全不同的、更完整的截图机制，这才是对标的：**

| 环节 | 坐标 |
|------|------|
| 能力开关 | `src/override/Window.cpp:47` `#define CARDINAL_WINDOW_CAN_GENERATE_SCREENSHOTS` |
| **不写文件** | `:51` `#define STBI_WRITE_NO_STDIO` → 走 `stbi_write_png_to_func` 回调 |
| 多趟状态机 | `:706-747`（Started→SecondPass→FirstPass→Saving），`:722` `glReadPixels` 读 GL 前缓冲 |
| **入口** | `rack::window::generateScreenshot()` — 声明 `src/CardinalCommon.hpp:26`（⚠️ 不在 `Rack/include/window/Window.hpp`，难找），实现 `src/override/Window.cpp:906-910`，仅一行 |
| **回调落点** | `:588-592` `String::asBase64` → `ui->setState("screenshot", ...)` |
| 现有触发点 | `src/override/Scene.cpp:225/341/348`（F7 推远端、F9 本地） |

**实现路径**：新增 1 个 OSC handler 调 `generateScreenshot()`，并在 `override/Window.cpp:734` 回调处多推一条 OSC 消息。**约 2 个文件。**

**⚠️ 三个约束（必须写进 MCP 文档，不能当成同步工具用）**：
1. **异步两段式**，要等 ~4 帧。设计成「请求 → 回调」，**不能同步阻塞等结果**
2. **GUI only**。`CARDINAL_WINDOW_CAN_GENERATE_SCREENSHOTS` 被 `#if !(defined(DGL_USE_GLES) || CARDINAL_VARIANT_MINI)` 包住（`override/Window.cpp:45`）→ **headless 与 Mini 变体都没有**
3. 返回 base64 而非文件路径，MCP 侧需按 image content 组织

**结论修正**：截图仍是 **P0**（4/4 宿主都有，且是自验证闭环的关键），但**从「零编译白捡」降级为「需编译，2 文件，GUI only，异步」**。

---

#### 类 8：可观测性 / 事件 ★★☆☆☆ P2

**★ 这是全行业空白** —— 1.6 节第 5 条：10 个 DCC MCP **无一实现事件订阅**，全靠轮询。

对标 MCP 协议本身是**基于请求-响应**的，标准 `resources/notify` + `subscriptions` 可以做，但生态里没人用。

| 能力 | 需要 | 实现路径 | 判断 |
|------|------|---------|------|
| 模块加载事件 | ⚠️ | 探针 + 推送端口 | 超纲 |
| 参数变化订阅 | ⚠️ | 探针（需 hook `setParamValue`） | 超纲 |
| 日志环形缓冲 + 增量拉取 | ✅ | 探针（log buffer）+ `MCP侧` 轮询 | **这是「订阅」的实用替代**：不需要真推送，只需**增量**读而非全量重读 |
| 错误日志读回 | ✅ | 探针 + `MCP侧` | ✅ **P0**，抄 U3 的核心用例 |

**建议：不做真事件订阅，做「增量日志缓冲」。** 收益 90%，复杂度 10%。

---

#### 类 9：撤销/事务 ★★★☆☆ P2 —— **★ v2 重大修正：宿主原生支持，且支持事务**

**v1 说「撤销只能 MCP 侧自建快照栈」是错的。** 架构师复核后我查证确认：

`history::State` 的 undo/redo **完整可编程**，全部 public：
```
src/Rack/src/history.cpp:234  void State::push(Action*)
src/Rack/src/history.cpp:260  void State::undo()      { if (canUndo()) { actionIndex--; actions[actionIndex]->undo(); } }
src/Rack/src/history.cpp:267  void State::redo()
src/Rack/src/history.cpp:274  bool State::canUndo()
src/Rack/src/history.cpp:278  bool State::canRedo()
```
→ **`APP->history->undo()` 就是 `/undo` handler 的全部实现。**

**现成的 Action 类型已覆盖我们要的全套**（`history.hpp`）：
`ModuleAdd:71` / `ModuleRemove:85` / `ModuleMove:92` / `ModuleBypass:103` / `ModuleChange:113` / **`ParamChange:125`（含 oldValue/newValue）** / `CableAdd:137` / `CableRemove` / **`ComplexAction:52`**

**⭐ 两个直接可用的关键点：**

1. **`ComplexAction`（`history.hpp:52-60`）就是天然的事务容器** —— N 个 Action 塞进 `actions` vector（`:54`），`push()` 递归 push 子 action（`history.cpp:258`）。**一次 push = 一个可整体撤销的原子操作。** 这正好满足「批量操作要能整体回滚」的需求，v1 只能靠 MCP 侧自己造。

2. **`ModuleAdd::redo()` 已经把完整链条写好了** —— `model->createModule()` → `module->fromJson()` → `engine->addModule()` → `model->createModuleWidget()` → `scene->rack->addModule()`。**照抄即可，不要自己拼。**

**⚠️ 但有一个硬门槛（这解释了为什么主路线仍应是 JSON + `/load`）**：
`RackWidget::addModule` 依赖 `APP->scene`（`RackWidget.cpp:594-607` 用 `internal->moduleContainer`）。**headless 构建里 `scene == NULL`，动态加模块在 headless 下不可做，GUI 下可做。**

**⇒ 修正后的路线判断**：
- **主路线仍是「生成整份 patch JSON 走 `/load`」**——它是唯一被完整验证过的全量写路径，且不依赖 scene
- 但 **undo/redo 应该走 `history::State` 原生**，而不是 MCP 侧快照栈——因为 snapshot 栈只能撤销 MCP 自己的改动，用户在 GUI 里手动操作无法追踪；而 `history` 是**宿主统一的真相源**
- **批量操作必须包在 `ComplexAction` 里**，否则部分失败会留下不一致状态

---

## 2.2 汇总：不需要 / 做不到的

| 项| 结论 | 理由 |
|---|------|------|
| Lua 脚本执行 | **做不到** | Cardinal 无 Lua |
| ChakraCore / V8 | **做不到** | 无依赖 |
| 音频录制 / 音频导出 | **做不到** | 无录音引擎 |
| MIDI 录制 | **做不到** | 无录制引擎 |
| MIDI 映射表读取 | **做不到** | Cardinal 已删 MIDI 面板 |
| MIDI IN（外部 → 模块） | ⚠️ 需加 hook | 无全局注册表可枚举 InputQueue |
| 撤销（宿主原生） | **✅ 能做（v2 修正）** | **`history::State` 完整可编程 + `ComplexAction` 支持事务** |
| headless 下动态加模块 | **做不到** | `RackWidget::addModule` 依赖 `APP->scene`，headless 下 `scene == NULL` |
| headless / Mini 下截图 | **做不到** | `CARDINAL_WINDOW_CAN_GENERATE_SCREENSHOTS` 被 `#if !(DGL_USE_GLES \|\| MINI)` 包住（`override/Window.cpp:45`） |
| **JavaScript 执行** | **✅ 能做，强烈推荐** | `libquickjs.a` **已链接**（含 os/std 模块），只缺宿主绑定；且有现成 RAII 封装可抄 |
| **GUI 视口截图** | **✅ 能做，需编译** | 异步两段式 `generateScreenshot()` → base64，GUI only |
| DSP 负载 metering | **✅ 能做** | `Engine::getMeterAverage/Max()` 已存在（注意 1s 刷新节流）|
| MIDI OUT | **✅ 能做，零 hook** | `writeMidiMessage()` 已存在 |
| 实时改接线（不重载 patch） | ⚠️ 可做 | `Engine::addCable` 存在，但依赖 `APP->scene` → GUI only |

---

## ★ 2.3 OSC 响应契约层（v3 新增｜架构师设计，PM 已逐条复核）

> **为什么这一节独立于能力矩阵**：能力矩阵回答「要什么」，本节回答「handler 之间怎么保持一致」。
> 这三类问题是**协议级**的——编完再改意味着 C++ 和 MCP 侧 Python **同时返工**。**必须在编译前定稿。**

### 2.3.1 统一响应格式 —— 现有探针有一处不一致（已核实）

现有 5 个探针回的都是 `/resp "tag" "payload"`，但**失败路径不一致**：

| 情况 | 现有行为（已核实坐标） | 问题 |
|------|---------------------|------|
| 参数类型错 | `DISTRHO_SAFE_ASSERT_RETURN(argc == 2, 0)`（`CardinalCommon.cpp:453-454`）| **不回复任何东西** → MCP 只能靠超时，白等一个 RTT |
| moduleId 查不到 | 回**空 payload**（`:463` `plugin == NULL` → `""`；`/ports:525`、`/light:673` 同）| 与「真的没数据」**无法区分** |
| `/load` 失败 | 回 `"load" "fail"`（`:714`）| 只有 ok/fail，**丢掉全部诊断文本**——这正是用户「load 成功但没画面」的根因 |

**★ 契约（三段：tag 固定 + status 固定 + payload）**：
```
/resp "tag" "ok"  "<payload>"
/resp "tag" "err" "<code>|<human readable>"
```
- **所有 assert 分支必须回一条 err**，MCP 侧不再依赖超时
- **`<code>` 固定小写标识符**，供程序化分支；**MCP 侧程序不得解析 human readable 部分**（否则措辞一变就崩）
- 建议码表：`bad_args` / `no_such_module` / `no_such_param` / `no_such_port` / `index_out_of_range` / `not_supported_in_this_build` / `engine_error` / `patch_load_failed`

**⚠️ 这会改动现有 5 个探针的回复格式，但必须照做**：不改的话 `/param-get` 对不存在的 module 回空串，MCP 无法区分「模块没这个参数」和「模块存在但值为空」，**`confidence` 字段就无从谈起**——而 confidence 正是我们差异化的核心。

### 2.3.2 分页 —— 大机架必须解决（已核实 `/modules` 确实无上限）

`/modules`（`CardinalCommon.cpp:393` 起）一次性把整个机架塞进一个 UDP payload，**逐条 `out += ...` 拼接、没有任何上限**。

- UDP practical 上限 ~1500 字节（`/ports` 已踩过，`:544` 注释明说「poly 到 16 通道会让 payload 爆掉」）
- Cardinal 自带 `plugins/` 就有 200+ 插件目录，真实机架 200+ 模块很常见
- 超 MTU 后 liblo 可能返回 `EMSGSIZE` 或**静默丢包** → MCP 侧表现为超时，**无法区分「机架太大」和「Cardinal 挂了」**

**落地方式（2026-10-21）**：契约不变，但**不改造旧端点**，而是加**分页孪生端点** ⇒ 旧客户端零破坏：
`/modules-page "ii"`（E2）+ `/cables-page "ii"`（B2，10-21 下午）。payload = `"<returned>/<total>|<items>"`，
limit 上限 64；越界 offset → returned=0 但 total 真实；非法参数 → `err:E_BAD_ARGS`。MCP 侧对应
`cardinal_modules_page` / `cardinal_cables_page`。

**契约**：所有列表类 handler（`/modules` `/cables`）支持 `offset`/`limit`，回复固定带 `count` 和 `total`：
```
/modules          → 第一页（默认 limit）
/modules 0 50     → offset=0, limit=50
/resp "modules" "ok" "3/217,0:Bogaudio-VCO|...,1:..."
```
- **`limit` 上限硬编码（如 64）**，防止外部塞爆 payload
- **MCP 侧自动翻页**；engineer 不需写分页逻辑，只提供 offset/limit

### 2.3.3 事务边界 —— ★ 诚实契约是「尽力而为」，不是 all-or-nothing

**这一条修正了 v2 的一个过度承诺。** v2 类 9 写「批量操作包 `ComplexAction` 即可原子回滚」——**只对了一半**。

已核实的三个事实：
1. **`ComplexAction::push()`（`history.cpp:31-33`）只做 `actions.push_back`，不递归**
2. **`ModuleAdd::redo()`（`history.cpp:63-73`）是「吞异常 + 尽力而为」**：
```cpp
try { module->fromJson(moduleJ); }
catch (Exception& e) { WARN("%s", e.what()); }   // ← 吞掉，继续往下
APP->engine->addModule(module);                  // ← 仍然加入
```
3. **`Engine::fromJson`（`src/override/Engine.cpp:1241` 起，WARN 在 `:1259`；⚠️ Rack 原版在 `src/Rack/src/engine/Engine.cpp:1216` 起——旧档写的 1216-1240 是 Rack 版行号）同样是 catch + continue**：`WARN("Cannot load model: %s", ...)` 后继续遍历下一个

⇒ **失败路径没有原子性保证**：第 3 个子 action 出错时前 2 个已生效，history 栈与实际状态会不一致。

**⇒ 诚实的契约**：`/load` / `/patch-transact` 返回 **`applied:N skipped:M` + 每个 skipped 的原因**，**不要宣称事务原子性**。
**这不是缺陷，是引擎既有语义**（与 UI 手动加载 patch 的行为一致）。

**⭐ 但这带来一个漂亮的闭环**：加载时哪些模块被 skipped，**正是「为什么不响」的第一候选原因**。

```
用户：「patch 加载了但不响」
  ↓ MCP 第 1 步：/load → resp "applied:15 skipped:2 (Could not find module Foo/Bar)"
  ↓ MCP 第 2 步：diagnose_silence ← 把 skipped 列表直接喂进去
```
**这条链路不需要任何新 hook，纯 MCP 侧就能做**，且正好落在我们的差异化定位上。
**我已把它列为 P0 诊断链路的第 0 步**（见 3.1 表 #7）。

### 2.3.4 build-time 约束 —— 注册表 2×2 矩阵（已核实，含一个当前隐患）

`/screenshot` 的**实现**被 `#if !(defined(DGL_USE_GLES) || CARDINAL_VARIANT_MINI)` 包住（`override/Window.cpp:45`），但**注册是无条件的**（`CardinalCommon.cpp:1144`）：
```cpp
lo_server_thread_add_method(oscServerThread, "/screenshot", "b", osc_screenshot_handler, this);
```
⇒ **Mini / GLES 构建会编译或链接失败。** 当前代码之所以没炸，是因为该变体没在编。

叠加 v2 已知的「thread / 非 thread 两份注册表」，注册表现在是 **2×2 矩阵**（thread × build variant）。

**⇒ 契约要求（已提级为编译组前置条件）**：
- `/screenshot` 注册**必须在 `#ifdef` 内**
- **注册表抽成一个函数**：`CardinalCommon_RegisterOscMethods(lo_server server, Initializer* self)`，一处定义、两处条件调用
- **收益**：根治 v2 提到的「双写静默失效」；以后加 handler 只改一行

**这条再次修正了截图的成本**：v1 说「零编译白捡」（错，实现是空函数），v2 说「2 文件」（偏乐观，**还要动注册表 + 处理 2×2 条件**）。真实约 3 处，但都在同一次编译里。

---

## 第三部分：优先级与编译分组

### 3.1 P0/P1/P2 排序表

| # | 能力 | 类 | 路径 | 编译? | 风险 |
|---|------|-----|------|-------|------|
| 1 | ~~确认探针是否已编译~~ **✅ 已完成：未编译** | 1 | 检查 | — | 已闭环 |
| 2 | `list_modules`（`/modules` + **`isBypassed`**） | 1/4 | 探针✅有 | 第1次 | 无 |
| 3 | `get_param_display`（`/param-get`） | 1 | 探针✅有 | 第1次 | 无 |
| 4 | `module_ports`（`/ports`，含电压） | 1/4 | 探针✅有 | 第1次 | **DSP 真并发读→需文档标注** |
| 5 | `get_light`（`/light`） | 1 | 探针✅有 | 第1次 | 无 |
| 6 | **`take_screenshot`** ← 高价值 | 7 | 需接 `generateScreenshot()` | **第1次** | ⚠️ **异步两段式；GUI only** |
| 7 | **`diagnose_silence`** ← **用户核心痛点** | 4 | MCP 侧（基于 2/4/5） | **无需** | 无 |
| 7b | **⭐ `/load` 返回 `applied/skipped` → 直接喂 7** | 4/5 | 探针改格式 | 第1次 | ⭐ **打通「加载诊断→静音诊断」，零新 hook** |
| 7c | **统一三段式响应 + 错误码表** | 契约 | 探针 | 第1次 | ⚠️ 协议级，**编译前必须定稿** |
| 7d | **列表类分页（offset/limit）** | 契约 | 探针 | 第1次 | ⚠️ 协议级，否则大机架超时 |
| 8 | `signal_flow` 拓扑追踪 | 4 | MCP 侧（`Cable` public 字段，零 hook） | 无 | ⚠️ `/ports` 只回前 4 通道 |
| 9 | patch 写操作全套（增删模块/接线/排版） | 2 | MCP 侧 | 无 | 端口编号/量纲 |
| 10 | `plugin_catalog` / 插件元数据 | 5 | MCP 侧 | 无 | 无 |
| 11 | 活体机架 JSON（**分页**） | 1 | 探针 | 第1次 | payload 爆 UDP |
| 12 | **`/cables` 拓扑数据源** | 1/4 | 探针 | 第1次 | 无（字段全 public）|
| 13 | **QuickJS 绑定 + `/eval`** ← **战略项** | 3 | 探针（抄 `AriaModules/src/javascript.hpp`）| **第2次** | ⚠️ **JS GC 不可控→必须入队+预算** |
| 14 | 日志环形缓冲 + 增量读 | 8 | 探针 | 第1次 | 无 |
| 15 | CPU/DSP 负载 + 采样率 + 线程数 | 4 | 探针（**API 已存在**）| 第1次 | ⚠️ **1s 刷新，轮询须节流** |
| 16 | **`/undo` `/redo`（原生 history）** | 9 | 探针 | 第1次 | ⚠️ **批量须包 `ComplexAction`** |
| 17 | play/pause/stop | 6 | 探针 | 第1次 | 无 |
| 18 | preset 读写 | 5 | MCP 侧 | 无 | 无 |
| 19 | MIDI OUT 注入 | 6 | 探针 | 第2次 | ⚠️ 必须自设 `frame >= 0` |
| 20 | `CARDINAL_MCP_READ_ONLY` 只读模式 | 安全 | MCP 侧 + JS 绑定 | 随 #13 | 无 |
| 21 | `js_history` / `js_replay` | 3 | 探针 | 随 #13 | 无 |
| 22 | ~~MIDI IN~~ | 6 | 需全局注册表 | **P3** | 推到 P3 |

### 3.2 ★ 编译分组（把探针打包进同一次编译）

**编译是 Cardinal 最贵的操作（102MB 二进制）。所有需编译项必须打包。**
**⚠️ 每条新 handler 必须双写两处注册表**（thread `:1135-1145` / 非 thread `:1152-1160`），否则切换构建配置时**静默失效**。

#### 第 0 次编译 —— ✅ **已完成**（架构师）
`strings bin/Cardinal | grep -c 'param-get'` = **0** → 探针未编译。**已闭环。**
🚨 **不要用 `/modules` 判断**——返回 11 但是 JUCE 路径假阳性。必须用 `param-get` 或 `osc_modules_handler`。

#### 第 1 次编译 ——「Read Probe 打包」（P0 主战场）
| 探针 | 目的 | 备注 |
|------|------|------|
| `/modules` | 列模块 | **加上 `isBypassed()`**，喂 diagnose_silence |
| `/param-get` | 参数显示值 | 已实现 |
| `/ports` | 连接 + 电压 | 已实现；**文档标注瞬时采样** |
| `/light` | LED | 已实现 |
| `/signal` | 全机架扫描 | 已实现 |
| `/cables` | 拓扑 | 新增，`Cable` 字段全 public，零 hook |
| `/screenshot` | **改为调 `generateScreenshot()`** | ⚠️ 不是 `Window::screenshot()`（空函数）|
| `/patch-json` | 活体机架 JSON | **必须分页**（如 `?page=0&n=32`）|
| `/log-get` | 日志环形缓冲（增量）| 新增 |
| `/engine-info` | 采样率/线程数/CPU meter | **API 已存在，只差探针** |
| `/transport` | play/pause/stop | 新增 |
| `/undo` `/redo` | **原生 history + ComplexAction** | v2 修正 |

→ 约 500-700 行，一次编译换来 **12 个能力**。**这才是「白捡」的真正形态。**

#### 第 2 次编译 ——「JS 引擎」（战略项）
- `src/cardinal_js.cpp`：抄 `plugins/AriaModules/src/javascript.hpp` 的 RAII 封装
- 绑定 Engine/Module/ParamQuantity/Cable（**写 API 已齐全**：`Engine.hpp:108-190`）
- `/eval "js"` handler，**入队 + 预算执行**（不在 OSC 线程直接 eval）
- `CARDINAL_MCP_READ_ONLY` 支持
- 执行历史环形缓冲（抄 U1 的 `get_history`/`replay`）
- MIDI OUT 注入（零 hook 顺手做）

**★ 合并决策：架构建议「合并」，非待拍板。**（v3 已改为架构背书）

**架构师补了一条我漏掉的硬理由**：探针是**一次性能力清单**（有上限，做完定稿），JS 绑定是**无上限能力**。
**若分两次编，第一次编完的产物在第二次编之前，MCP 侧所有工具都不可用**（因为探针没编进去，工具全瞎）。
合并后，第二次编译的边际成本只有 JS 那几十行，却把「补任何 handler」的需求**永久消除**。

**⭐ 技术收益（我原先没想到）**：探针 + JS 绑定一起进 `CardinalCommon.cpp` 后，**JS 侧能包住 engine API**（`context->engine->getModuleIds()` 这类在 JS 里直接调）。
⇒ **handler 数量反而可能变少：12 个原生可能收敛成 5 个原生 + N 个 JS 工具**（读侧用 JS 实现更短）。

#### 第 3 次编译（P3，可选）
- MIDI IN 全局注册表（`src/Rack/src/midi.cpp`，约 30 行）
- 实时改接线（`Engine::addCable`，GUI only）

### 3.2.1 ★ 编译前置条件（v3 新增，缺一不可）

| # | 前置条件 | 依据 |
|---|---------|------|
| 1 | **注册表抽成 `CardinalCommon_RegisterOscMethods(server, self)`**，一处定义两处调用 | 根治双写静默失效 + 处理 2×2 变体矩阵（2.3.4）|
| 2 | **每条新 handler 双写两处注册表**（若未做 #1）| thread `:1135-1145` / 非 thread `:1152-1160` |
| 3 | **`/screenshot` 注册放 `#ifdef` 内** | `CARDINAL_WINDOW_CAN_GENERATE_SCREENSHOTS`（2.3.4）|
| 4 | **统一响应格式为三段式**，所有 assert 分支回 err | 2.3.1；否则 MCP 只能靠超时 |
| 5 | **列表类 handler 支持 offset/limit，limit 上限硬编码** | 2.3.2；否则大机架超时不可诊断 |
| 6 | **`/load` 返回 `applied:N skipped:M`**，不宣称原子性 | 2.3.3 |
| 7 | **不得用 `/modules` 做 strings 验证**（用 `param-get`/`osc_modules_handler`）| JUCE 路径假阳性 |

### 3.3 推荐执行顺序

```
① 只读诊断                     ← ✅ 已完成（探针未编译）
② 出实现规格（工具名+schema+验收+本节契约）  ← ★ 建议插在这里，编译前定稿
③ 一次合并编译：Read Probes + QuickJS 绑定 + 只读模式 + 原生 undo
④ MCP 侧封装：screenshot(异步) / diagnose_silence / signal_flow / patch 写操作 / plugin_catalog
⑤ MCP 侧加固：CPU meter 节流、瞬时采样文档标注、skipped→诊断链路
⑥ P2：transport、MIDI OUT
```

**★ 为什么②要在③之前**：响应格式、分页、注册表重构这三条都是**协议级**，编完再改 = C++ 与 Python 同时返工。
（**C++ 签名不现在定**，留给 engineer 照着 `history::ModuleAdd::redo()` 自己设计——架构师第一轮曾把 `getMinDisplayValue`/`getValueAsString` 报成存在、实际不存在，拍签名已翻过一次车。）

### 3.4 与竞品的能力差距（一句话总结）

| 维度 | Unity/Blender/UE/Godot MCP | Cardinal MCP 目标 |
|------|--------------------------|------------------|
| 脚本执行 | ✅ 10/10 | ✅ QuickJS（**待绑定，已有封装可抄**）|
| 截图 | ✅ 4/4 | ✅ **GUI only、异步；需接 `generateScreenshot()`** |
| 日志读回 | ✅ 3/4 | ✅ 待做 |
| 只读模式 | ✅ | ✅ 待做（**机制性剥离，强于同行**）|
| 执行历史 | ✅ 1/10 | ✅ 待做 |
| 撤销/事务 | ✅ 仅 Unity | ✅ **v2 修正：原生 history + `ComplexAction`，能超过 Unity** |
| **信号流诊断** | ❌ **无人做** | ✅ **差异化优势，用户核心痛点** |
| **事件订阅** | ❌ 全行业空白 | ➖ 本轮不做，做增量日志 |

**战略结论**：
1. **补齐脚本执行 + 截图 + 日志 + 只读模式 → 追平行业标准**
2. **信号流/静音诊断 → 无人做，是我们的差异化**（且用户的真实痛点就是它）
3. **QuickJS 绑定不只是补短板，是把 Cardinal MCP 从「窄工具」变成「万能遥控器」的杠杆**
4. **★ 新增**：撤销/事务原为行业空白（仅 Unity 有），但 Cardinal 的 `history::State` + `ComplexAction` **已完整支持批量事务**——v1 误判为「做不到」，**可反向做成宣传点**（批量生成 patch 一步撤销）

---

## 附录：关键源码坐标（WSL `/home/lijia/Cardinal`）

| 内容 | 坐标 |
|------|------|
| 现有只读探针区块（6 handler + 回复约定） | `src/CardinalCommon.cpp:357-380`（END 在 `:689`）|
| OSC handler 注册表（**thread + 非 thread 两份，必须双写**）| `src/CardinalCommon.cpp:1135-1145` / `:1152-1160` |
| `stepRemoteServer()`（GUI 每帧轮询） | `src/CardinalCommon.cpp:1192-1206` |
| GUI 每帧调用 OSC step | `src/override/MenuBar.cpp:852` |
| `CARDINAL_OSC_AUTOSTART`（**运行期 getenv，非宏**）| `src/override/MenuBar.cpp:738-741` |
| **`generateScreenshot()` 入口** | 声明 `src/CardinalCommon.hpp:26`；实现 `src/override/Window.cpp:906-910` |
| 截图状态机 + `glReadPixels` | `src/override/Window.cpp:706-747`（`:722` 读 GL 前缓冲）|
| 截图 base64 回调落点 | `src/override/Window.cpp:588-592`（`STBI_WRITE_NO_STDIO` 在 `:51`）|
| 截图能力开关 / 变体限制 | `src/override/Window.cpp:47` / `:45` |
| ⚠️ **`Window::screenshot()` 是空函数** | `src/override/Window.cpp:748-751`；`src/custom/RemoteWindow.cpp:111/115` |
| 构建分支（哪份 Window 被编） | `src/Makefile.cardinal.mk:85-95` |
| **原生 undo/redo** | `src/Rack/src/history.cpp:234/260/267/274/278` |
| **`ComplexAction`（事务容器）** | `src/Rack/include/history.hpp:52-60` |
| 现成 Action 类型（ParamChange 含 old/new）| `history.hpp`：`ModuleAdd:71`/`ModuleRemove:85`/`ModuleMove:92`/`ModuleBypass:103`/`ParamChange:125`/`CableAdd:137` |
| `ModuleAdd::redo()` 完整链条（照抄）| `src/Rack/src/history.cpp` |
| Engine 写 API | `src/Rack/include/engine/Engine.hpp:108-190` |
| Engine CPU meter / 采样率 | `Engine.hpp:50, 87-90`；刷新节流 `src/Rack/src/engine/Engine.cpp:576` |
| `Module::isBypassed()` | `engine/Module.hpp:465`；`engine/Module.cpp:286-288` |
| `Cable` public 拓扑字段 | `engine/Cable.hpp:15-19` |
| `ParamQuantity::getDisplayValue()` | `engine/ParamQuantity.hpp:97` |
| DSP 线程写 outputs/lights（无额外锁）| `engine/Module.cpp:335-370` |
| `RackWidget::addModule` 依赖 `APP->scene`（headless 门槛）| `src/Rack/src/app/RackWidget.cpp:594-607` |
| **QuickJS 已被链接** | `src/Makefile.cardinal.mk:153` |
| QuickJS 源码 / 产物 | `deps/QuickJS/`；`src/Rack/dep/lib/libquickjs.a` |
| ⭐ **现成 JS RAII 封装（照抄，勿从零写）** | `plugins/AriaModules/src/javascript.hpp`；用例 `plugins/AriaModules/src/Qqqq.cpp:287-307` |
| QuickJS `os` / `std` 模块 | `deps/QuickJS/quickjs-libc.c:2591` / `:1241` |
| `JSEngine` 宿主绑定（**不存在，需新建**）| 全仓零命中 |
| **MIDI OUT**（零 hook）| `include/plugincontext.hpp:100`；`src/CardinalCommon.cpp:202` |
| MIDI IN（需 hook）| `include/midi.hpp:257/265`；需建全局注册表 `src/Rack/src/midi.cpp` |
| 现有 MCP | `D:\Cardinal\tools\cardinal_mcp.py`（约 20 个工具，含 6 个只读封装）|

## 附录：待确认项（交给架构师/工程师）

4. ~~运行中的二进制是否含探针~~ ✅ **已确认：未编译**（`param-get=0`）
2. ~~`midi.hpp` 是否有 MIDI 注入接口~~ ✅ **已确认**：OUT 可零 hook；IN 需 hook，推 P3
3. ~~`/ports` 线程安全~~ ✅ **已确认**：真并发但不崩，保留实现 + 文档标注瞬时采样
4. ~~QuickJS 绑定的线程模型~~ ✅ **已定**：入队 + DSP 回调预算执行
5. ~~第 1/2 次编译是否合并~~ ✅ **架构建议：合并**（v3 已改为架构背书，非待拍板）
6. ~~`/patch-json` 分页粒度~~ ✅ **已定**：offset/limit，limit 上限硬编码（2.3.2）
7. **`/load` 的 `skipped` 列表如何取** —— 引擎是否已记录「哪些 model 找不到」？（2.3.3 闭环的关键，**建议 engineer 编译时一并确认**；若引擎未暴露，可能需要从 `Engine::fromJson` 的 WARN 里取）
8. **错误码表需与 MCP 侧 Python 对齐**（2.3.1 建议的 8 个码，engineer 可增删，但**改了要同步**）
