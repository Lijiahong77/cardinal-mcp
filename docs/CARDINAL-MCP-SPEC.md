# Cardinal MCP 实现规格（SPEC）v2

> 状态：**待施工**。只定义「要什么」与「怎么验」。源码树：WSL `/home/lijia/Cardinal`（所有 `文件:行号` 均指此树）。
> MCP 侧：`D:\Cardinal\tools\`（`cardinal_mcp.py` 1231 / `paramlib.py` 948 / `patchio.py` 134 / `modsearch.py` 321 / `audit_*.py`）。
> 端口 2228（`src/CardinalRemote.hpp:9`，MCP 侧 `cardinal_mcp.py:83` 已对齐）。重编成本：全量 102MB，`tools/cross_build_cardinal.sh`。
> **v2**：并入协议层设计（统一响应契约 / 分页 / 事务诚实语义 / build-time 约束）；新增 P0 `/build-info`；**删除全部 C++ 签名**（见第二部分开头）；按「一次编译」重组。
>
> ⚠️ **路径约定（A5 修正，2026-10-19）**：`src/Makefile:46` 用 `src/override/` 下的同名文件**替换** `Rack/src/` 原件 —— `Engine.cpp` / `Window.cpp` / `Browser.cpp` / `plugin.cpp` 均被替换，**编译生效的是 override 版**。本文凡写 `Engine.cpp` / `Window.cpp` / `plugin.cpp` 而未标路径的行号，**一律指 `src/override/` 版**（行号也是 override 版的行号，与 Rack/src 原件**不同**）；`patch.cpp` 指 `src/Rack/src/patch.cpp`（不在 override 列表里，原件生效）。读行号先按此约定定位文件，别读错。

---

## 0. 全局约束

### 0.1 OSC 传输层

| 约束 | 依据 | 影响 |
|---|---|---|
| **无请求-应答关联 id** | `cardinal_mcp.py:90-92` | ⛔ **禁止并发**。`ask()` 靠 `:136-139` 排空陈旧 datagram 防串台 |
| `ask()` 超时 1.5s | `cardinal_mcp.py:84` | 工具内多次往返要算总预算 |
| UDP practical ~1500B | `/ports` 已踩过 `CardinalCommon.cpp:544` | 列表类必须分页（0.3） |
| 未打补丁构建**静默丢弃**未知路径 | fallback `CardinalCommon.cpp:690-693` 只 `d_stderr` | ⇒ **超时 = 未编译**，绝不能当"没数据"。沿用 `PROBE_UNSUPPORTED`（`cardinal_mcp.py:293-299`） |

### 0.2 统一响应契约（协议级，**照做**）

现有 5 探针回 `/resp "tag" "payload"`，**失败路径不一致**，MCP 无法程序化判断：

| 现状 | 位置 | 后果 |
|---|---|---|
| 参数类型错 → `DISTRHO_SAFE_ASSERT_RETURN(...,0)` **完全不回复** | `CardinalCommon.cpp:451/505/651/760` 各 handler 头 | 白等一个 RTT，无法区分「错」与「没编」 |
| moduleId 查不到 → 回**空 payload** | `/ports` `:525`、`/light` `:673`、`/param` `:788` | 「模块没这个参数」与「值就是空」不可区分 ⇒ T2 的 `confidence` 无从谈起 |
| `/load` 失败 → `"load" "fail"` | `:737-748` | 丢掉全部诊断文本 |

```
成功： /resp "<tag>" "ok"  "<payload>"
失败： /resp "<tag>" "err" "<code>|<human readable>"
```
- 所有 assert 分支**必须回 err**，MCP 不依赖超时
- `<code>` 固定小写标识符供程序分支；⛔ **禁止把自然语言当错误码**
- human readable 仅供人看，MCP 侧程序**不得解析**
- 空数据**不是错误**：回 `"ok"` + 空 payload 且带 `count:0`

**码表（封闭）**：`bad_args` / `no_such_module` / `no_such_param` / `no_such_port` / `index_out_of_range` / `not_supported_in_this_build` / `engine_error` / `patch_load_failed`

⚠️ **这是对现有 5 探针的行为变更**。不改的话 `/param-get` 对不存在的 module 回空串，`diagnose_silence` 的 `confidence` 字段无从谈起。**建议照做。**

### 0.3 分页契约

`/modules`（`CardinalCommon.cpp:395`）把整机架塞进一个 UDP payload，`out += id:plugin|model,` 逐条拼接，**无任何上限**；Cardinal 自带 `plugins/` 就有 200+ 目录。超 MTU 后 liblo 可能 EMSGSIZE 或静默丢包 ⇒ MCP 只能超时，**无法区分「机架太大」和「Cardinal 挂了」**。

- 列表类（`/modules` `/cables` `/plugins`）统一支持 `<path> <offset> <limit>`，回复带 `/resp "<tag>" "ok" "<returned>/<total>,<items>"`
- `limit` 硬上限 **64**；不传时默认 `0 64`（**向后兼容现有 `/modules` 调用方**）
- MCP 侧自动翻页到 `returned < limit` 或 `offset >= total`，**规格里不写翻页逻辑**
- 原生未实现分页时 MCP 可自行切片，但 `total` 必须如实上报

### 0.4 「未编译」的判定与降级（硬要求）

未打补丁时 `_ask()`（`cardinal_mcp.py:301-313`）返回 `None`。依赖探针的工具**必须**返回：
`{"error":"probe_not_supported","note":"...","requires":"rebuild","cmd":"bash tools/cross_build_cardinal.sh"}`
⛔ **绝不返回空数组 / 空对象 / "成功但无数据"。** 这是本项目最容易产生「假阴性诊断」的根源（`diagnose_silence` 会把「探针没编」报成「全机架静音」）。

### 0.5 引擎侧读的一致性（写进用户文档）

`Engine` 的 `SharedMutex`（`Engine.cpp:227`）**不保护 Port 电压**。`Module::doProcess()`（`Module.cpp:335-370`）在音频线程无锁写 `outputs`/`lights` ⇒ 所有电压返回值都是**瞬时采样，可能来自上一次 block**。不会崩，但不要用于精密测量。依据：Cardinal 自己的 `PortWidget::step()` 也无锁读同一份数据，是既定设计。

### 0.6 CPU meter 节流

`getMeterAverage()/getMeterMax()`（`Engine.hpp:87-88`）对外值**每 1 秒才刷新一次**（`Engine.cpp:576` `meterUpdateDuration = 1.0`）⇒ MCP 侧读 CPU **必须缓存 1 秒**，1 秒内重复调用返回缓存并带 `"cached":true`。

### 0.7 `read_live()` 的已知不可靠性

`read_live()`（`cardinal_mcp.py:561`）读 autosave 文件，三条局限（源码注释已列）：① autosave **只在 `/load` 或 GUI 保存时**才刷 ⇒ 通过 OSC 改的参数**永不反映**；② 刚启动可能读到**上一会话**残留；③ 写入中途可能读到半截 JSON（`:566-567` 已重试）。
⇒ 所有以它为输入的工具**必须先查 `stale`/`age_seconds`**（`:571-576`）并透出。**绝不因为旧了就断言机架内容错误。**

### 0.8 「一次编译」假设

探针与 QuickJS 绑定**合并为一次编译**：探针是**一次性能力清单**（做完定稿），JS 是**无上限能力**；分两次编 ⇒ 第一次编完到第二次编之间 MCP 侧全部不可用。JS 侧能直接调 `context->engine->getModuleIds()` 等 API，很多读侧工具用 JS 实现更短 ⇒ **12 个 handler 可能收敛成 5 原生 + N JS**。边际成本几十行 JS，却**永久消除「补任何 handler」的需求**。
⇒ 原生只做**引擎侧无 API 可用**或**必须在音频/DSP 上下文执行**的事；纯遍历/聚合/格式化走 JS（清单见 2.9）。

### 0.9 具名能力：「加载诊断 → 静音诊断」（零新 hook）

用户说「patch 加载了但不响」的完整链路：
```
MCP /load → 引擎回 applied:N skipped:M + warningLog      （H9，两处修复：恢复 override/Engine.cpp 两行 log + lastLoadWarnings 字段）
   ↓ 同一份 skipped 列表
与 patch JSON 的 modules[] 比对 → 缺失者
   ↓
T2 diagnose_silence → issue:"load_failed", confidence:1.0, evidence.source:"load_warning_log"
```
这是本项目**差异化定位的具名表达**，应写进对外介绍，且**零新 hook**。
静默丢弃因果链（全部有据）：`plugin::modelFromJson`（`override/plugin.cpp`）抛 `"Could not find module %s/%s"` → `Engine::fromJson`（`override/Engine.cpp:1229-1236/1247-1260`）catch 后 log + `continue`（⚠️ override 版 :1260/:1289 的 `patch->log` 被注释掉 ⇒ warningLog 恒空，见 H9） → 但 `patch.cpp:478` 与 `:534` **前后各清一次 `warningLog`** ⇒ 现有 `/load` 恰好丢掉全部诊断，根因在 `:534`。

---

# 第一部分：MCP 侧工具规格（零编译，今天可写）

## T1. `cardinal_health(target)` — 机架总健康度

**入参** `{ "target": "live"|"<patch_name>"（默认 live）, "checks": ["ports","values","flow","chain","validate"]（可选，默认全跑）, "_guard": true }`

**返回**
```json
{ "target":"live", "stale":false, "age_seconds":2.1,
  "build": {"reachable":true,"variant":"main","osc_thread":true,"caps":["modules","cables"]},
  "hard": [ {"check":"ports","module":"Bogaudio-VCO","detail":"OUT3 > 上限 2"} ],
  "soft": [ {"check":"flow","module":"VCF","detail":"CV 输入未接线"} ],
  "silent_modules": [ {"id":42,"plugin":"...","model":"VCO","peak":0.0,"reason":"bypassed|zero_gain|upstream_silent|no_output|load_failed"} ],
  "unwired_inputs": [ {"id":42,"port":3,"name":"Pitch CV"} ], "probe_ok": true }
```

**实现要点**
- ⭐ **第一个 OSC 调用永远是 `/build-info`**（H0）⇒ 环境问题在第一次调用暴露，而非所有工具一起超时。`build.reachable:false` 时其余检查全部跳过并返回 `probe_not_supported`。
- 静态部分**复用四个审计脚本，不要重写**：`audit_ports.audit()`（`audit_ports.py:66`，`LIMITS` 表驱动 `:70-84`）→ `hard`；`audit_flow.audit()`（`:134`，内部已分 hard/soft）；`audit_values.audit()`（`:282`，L1 `:296-300` 进 hard，末尾 `return sorted(out)` `:448`）；`audit_chain.audit()`（`:41`，`PITCH_IN` 等语义表 `:57`）。
- ⭐ **实时部分必须「一次往返拿全机架」**：`scan_signal(threshold=1e-4)`（`cardinal_mcp.py:411`）内部调一次 `/signal`（`CardinalCommon.cpp:583-648`）返回全机架 `id:peak`。**严禁逐模块循环调 `/ports`** —— 200 模块 = 200 次串行 OSC，爆预算。
- 判定顺序：① `/signal` 一次 → 有信号集合；② 只对不在集合里的调 `/ports`（`cardinal_mcp.py:385`）细查 → 区分 `no_output`/`upstream_silent`；③ `bypassed` 见 T2。
- `_guard=true` 时任一 `hard` 非空 → `"verdict":"reject"`，否则 `"pass"`。

**验收**：未编译 → `build.reachable:false` + `probe_not_supported`，**不是** `silent_modules:[]`；空机架 → 四数组全空且 `probe_ok:true`；单 VCO 无接线 → `reason:"no_output"`。

## T2. `cardinal_diagnose_silence(scope)` — 静音根因分类

**用途**：本项目**对标 10 个宿主 MCP 都没有的差异化能力**（Unity/Blender/UE/Godot 全无信号流诊断）。⛔ 输出必须结构化供 LLM 决策，不要自然语言散文。

**入参** `{ "scope": "live"|"<patch>"|{"modules":[42,43]}, "threshold": 0.0001, "max_modules": 50 }`

**返回**
```json
{ "issues": [
  { "module":{"id":42,"plugin":"Bogaudio-VCO","model":"VCO"}, "issue":"bypassed", "confidence":1.0,
    "evidence":{"source":"isBypassed","value":true,"also":{"peak":0.0,"channels":1}},
    "fix":{"action":"param_or_bypass","hint":"Engine::bypassModule / ModuleWidget::bypassAction"} },
  { "module":{"id":57,"plugin":"VCF","model":"VCF"}, "issue":"upstream_silent", "confidence":0.85,
    "evidence":{"source":"ports","inputs":[{"id":0,"channels":1,"voltage":0.0}],
                "upstream":[{"id":42,"peak":0.0,"reason":"bypassed"}]}, "fix":{"action":"fix_upstream","ref":42} },
  { "module":{"id":63,"plugin":"Mixer","model":"Mixer"}, "issue":"zero_gain", "confidence":0.6,
    "evidence":{"source":"displayValue","params":[{"pid":2,"name":"Volume","value":0.0}]},
    "fix":{"action":"set_param","module":63,"param":2} },
  { "module":{"id":9,"plugin":"Foo","model":"Bar"}, "issue":"load_failed", "confidence":1.0,
    "evidence":{"source":"load_warning_log","line":"Could not find module Foo/Bar"},
    "fix":{"action":"install_plugin_or_fix_slug","ref":"Foo/Bar"} } ],
  "summary": {"total_silent":4,"by_issue":{"bypassed":1,"upstream_silent":1,"zero_gain":1,"load_failed":1}},
  "probe_ok": true }
```

**`issue` 枚举（封闭 5 类）**

| issue | 判定依据 | confidence 上限 |
|---|---|---|
| `bypassed` | `Module::isBypassed()`（`Module.hpp:465` → `Module.cpp:286-288`）为 true | **1.0**（权威值） |
| `zero_gain` | `ParamQuantity::getDisplayValue()`（`ParamQuantity.hpp:97`）落在「增益类参数名 + 值≈0」；复用 `audit_values.is_bypass_zero()`（`audit_values.py:264`） | 0.6（启发式，非权威） |
| `upstream_silent` | `/ports` 输入口 `channels>0` 但 `voltage==0`，且上游在 `silent_modules` 里 | 0.85 |
| `no_output` | 所有输出口 `isConnected()==false`（`Port.hpp:182`）或峰值全 0 且无输入连接 | 0.9 |
| `load_failed` | moduleId **不在** `live_modules()` 但**在** patch JSON 的 `modules[]` 里 ⇒ 引擎静默丢弃 | **1.0** |

**实现要点**
- ⭐ **`is_bypassed` 是本工具的核心**。没有它，「被 bypass」与「没 bypass 但真没输出」在纯 `/signal` 视角下**一模一样（都是 0V）**，confidence 无法拉开。
- ⭐ **`load_failed` 是 0.9 闭环的接点**：H9 让 `/load` 回传 `lastLoadWarnings`，其 skipped 行直接就是证据源。⚠️ 前提是 H9 的两处修复都做了（override/Engine.cpp 两行 log 恢复 + lastLoadWarnings 字段），只改 handler 读 warningLog 恒为空。
- 增益参数名启发式用 `paramlib.TERMS`（`paramlib.py:734-788`）中英映射 + `resolve_name()`（`:834`）打分定位 pid。
- ⚠️ `/ports` 只回**前 4 通道**（`CardinalCommon.cpp:544` + `PORT_MAX_CHANNELS=16` `Port.hpp:11`）⇒ poly 模块判定要标 `"channels_truncated": true`。

**验收**：单 VCO bypass → `bypassed`/1.0/`source=="isBypassed"`；VCO ← 被 bypass 的 VCO → 上游 `bypassed`/1.0、下游 `upstream_silent`/0.85 且 `fix.ref` 指上游；patch 有引擎无 → `load_failed`/1.0。

## T3. `cardinal_deploy(patch, verify=True)` — 部署并验证

**入参** `{ "patch": "<name>", "verify": true, "timeout": 15.0, "settle_ms": 250 }`

**返回**
```json
{ "sent":true, "load_reply":"ok", "applied":21, "skipped":3,
  "skipped_detail": [ {"reason":"Could not find module Foo/Bar","module_index":7} ],
  "warning_log":"...",
  "verify": { "attempt":3,"waited_ms":700,"file_modules":24,"engine_modules":21,
    "dropped":[ {"id":9,"plugin":"Foo","model":"Bar","reason":"not_in_engine"} ],
    "added":[ {"id":99,"reason":"in_engine_not_in_file"} ], "ok":false },
  "verdict":"loaded_with_drops" }
```

**实现要点**：① `load_patch(name)`（`cardinal_mcp.py:223`）→ 发 `/load` blob（`CardinalCommon.cpp:714-758`）；② ⛔ **禁止 `sleep(4)`**，改为轮询 `live_patch_path()`（`:537`）返回路径的 mtime 直到更新 —— mtime 是启发式可能选错 slot（其 docstring `:541-543`），故还要叠加 `read_live()` 的 `stale` 检查（0.7）；③ `live_modules()`（`:315`）拿引擎实况；④ **双向 diff**（文件有∧引擎无 = 被丢弃；引擎有∧文件无 = 没加载上/残留，结合 `stale` 判断）；⑤ `skipped_detail` 从 `warning_log` 解析（未编译 H9 时退回 ④ 反推）。

**验收**：合法 patch → `verify.ok:true`/`"loaded"`；含 1 个错 slug → `dropped` 精确列出 + `"loaded_with_drops"`，**不是** `"ok"`；第二次调用无 `added` 幽灵项。

## T4. `cardinal_diff(a, b)` — 两份 patch 差异

**入参** `{ "a": "live"|"<name>", "b": "live"|"<name>" }`

**返回**（字段级）
```json
{ "added_modules":[{"id":9,"plugin":"X","model":"Y","pos":[3,0]}],
  "removed_modules":[{"id":12,"plugin":"X","model":"Z"}],
  "moved_modules":[{"id":20,"from":[1,0],"to":[1,2]}],
  "param_changes":[{"id":20,"pid":3,"name":"Cutoff","from":0.2,"to":0.75}],
  "cable_changes":{"added":[{"from":[20,0],"to":[21,2]}],"removed":[{"from":[20,1],"to":[21,3]}]},
  "data_changes":[{"id":20,"keys":["seq","pattern"]}],
  "summary":{"modules":0,"cables":0,"params":2} }
```

**实现要点**：坐标是 **grid 单位**（`.vcv` 的 `pos` 需 `× RACK_GRID_SIZE + RACK_OFFSET`，`app/RackWidget.cpp:330-336`）；参数名填充用 `paramlib.name_of()`（`paramlib.py:801`）；⚠️ 若一侧是 `live`，受 0.7 限制 `param_changes` 会**漏掉所有 OSC 改的参数** ⇒ 必须标 `"params_unreliable_for_live": true`。
**验收**：自身 diff → 四数组全空；改一个参数 → 只 `param_changes` 有 1 项。

## T5. `cardinal_edit(patch, ops[])` — 增量编辑（**绝不丢用户手改**）

**入参** `{ "patch":"<name>", "dry_run": false, "ops":[
  {"op":"add_module","plugin":"Bogaudio-VCO","model":"VCO","pos":[4,0],"params":{"0":0.5}},
  {"op":"remove_module","id":42}, {"op":"add_cable","from":[42,0],"to":[43,1]},
  {"op":"remove_cable","from":[42,1],"to":[43,2]}, {"op":"set_param","id":42,"pid":3,"value":0.75}] }`

**流程（顺序不可变）**：① ⭐ **`read_live()` 出发，不用磁盘 patch** —— 这是「绝不丢用户手改」的唯一保证（用户可能在 GUI 拖过模块、改过参数，`patchio.read_patch()` `patchio.py:53` 是磁盘旧版）；先查 `stale`，太旧则**中止并要求用户先保存**。② 施加 ops（内存 dict）。③ `sanitize`（`_add_sanitize.py:27`）。④ 跑 T1 四审计脚本。⑤ 任一 hard 命中 → 中止（`dry_run` 只报告）。⑥ 写盘 `patchio.write_patch()`（`:104`）。⑦ `load_patch()` 重载。⑧ `live_modules()` 验证。

**实现要点**：⛔ **本工具不做引擎内编辑**，走「改文件 → `/load`」。架构级硬约束：`RackWidget::addModule`（`app/RackWidget.cpp:594-607`）依赖 `APP->scene` ⇒ **headless 下动态加模块不可做**；绕过 `history::ModuleAdd`（`history.hpp:71`）会丢 undo；只动 engine 不动 widget 会 Scene/Engine 不一致；`/load` 是**唯一被完整验证过**的全量写路径。编译后要「运行中原地编辑且可撤销」走 H7 `/batch`，不是本工具。新模块 id 从 `read_live()` 现有最大 id +1 起。

**验收**：用户手改过参数 → `edit` 只加模块 → 手改**仍在**；加越界端口 → 步骤⑤拦截 + `"rejected_by_audit"` + **未写盘**。

## T6. `cardinal_topology(scope)` — 机架拓扑

**入参** `{ "scope":"live"|"<name>", "role_filter":["VCF","ENV"] }`
**返回** `{ "modules":[{"id":42,"plugin":"X","model":"VCO","role":"VCO","pos":[3,0],"params":0,"inputs":3,"outputs":2}], "edges":[{"from":[42,0],"to":[43,1],"channels":1,"from_voltage":0.0,"to_voltage":0.0}], "by_role":{"VCO":[{"id":42}],"VCF":[{"id":43}]}, "source":"osc_cables", "voltage_live":true, "page":{"offset":0,"returned":31,"total":31} }`

**实现要点**：两条数据源 —— `live`+编译后走 H1 `/cables`（零 hook：`Cable` 四字段全 public `Cable.hpp:15-19` + `Engine::getCableIds()` `Engine.hpp:163`）；未编译走 patch 的 `cables[]`。`by_role` 复用 `audit_flow.role()`（`audit_flow.py:126`，查 ROLES 表 `:127`）。`edges` 电压需另调 `/ports` ⇒ **仅对 `voltage_live:true` 的边**，受 0.5 撕裂说明约束。
**验收**：单 VCO→VCF → `edges` 长度 1，`by_role.VCO` 含 42。

## T7. `cardinal_port_semantics(plugin, model)` — 端口语义表

**用途**：知道「这个模块的第 3 个输入是 pitch 还是 gate」，否则无法自动接线。
**入参** `{ "plugin":"Bogaudio-VCO", "model":"VCO" }`
**返回** `{ "plugin":"Bogaudio-VCO","model":"VCO", "inputs":[{"id":0,"name":"V/oct","semantic":"pitch","role":"main"},{"id":1,"name":"FM","semantic":"cv"}], "outputs":[{"id":0,"name":"Sin","semantic":"audio"},{"id":1,"name":"Sin","semantic":"audio"}], "source":"paramlib.modules.json", "confidence":"medium" }`

**实现要点 —— 明确的前置扩展任务（零编译，可与 T1 并行）**
- `paramlib.parse_module()`（`paramlib.py:339-395`）**只抽 param**，specs 写死四项（`:355-356`）：`configParam/knob`、`configParamNoRand/knob`、`configSwitch/switch`、`configButton/button`。
- 但它已在做对的事：`parse_enums()`（`:251`）+ `scan_loops()`（`:309`）已在解析同一 enum 块（文件头注释 `:14` 明说含 "ParamIds / InputIds / OutputIds / …"），**只是把非 ParamId 部分丢弃了**。
- ⇒ **扩展点**：在 `parse_module` 循环加 `configInput` / `configOutput` 两个 fname，产出 `inputs`/`outputs`，复用同一套 `innermost_loop` 展开 + `label_of` 取名。`semantic` 分类用名字启发式（`pitch|v/oct`→pitch，`gate|trig|env`→gate，`audio|out`→audio，其余 cv）。
- ⚠️ 与 T9 的 `reserved` 陷阱同类：`paramlib.py:673-686` 已为 param 生成 `kind:"reserved"` 占位；**input/output 也要同样占位**，否则会误判「这个口不存在」而实际是「有 enum 值但没 configInput」。

**验收**：Bogaudio-VCO → `inputs[0].name=="V/oct"` 且 `semantic=="pitch"`；任何模块 `inputs` 长度 == `configInput` 调用次数（loop 展开后）。

## T8. `cardinal_find_module(timbre|model|tags)` — 模块检索

**入参** `{ "timbre":"warm pad", "model":"VCO", "plugin":"Bogaudio-VCO", "tags":["drone"], "limit":20 }`
**返回** `{ "matches":[{"plugin":"...","model":"...","score":0.82,"route":"Lead → Comp → VCF","why":"matched tags:pad,warm"}], "index_size":1422, "routes":17 }`

**实现要点**：包 `modsearch.py`（`build_index()` `:118` / `load_index()` `:159` / `fmt_mod()` `:170`）；音色速查包 `ROUTES`（`:44`，17 条）；匹配复用 `paramlib.TERMS`（`paramlib.py:734-788`）把「温暖」「pad」翻成英文关键词。
**验收**：`timbre:"warm pad"` 返回非空且每项有 `route`。

## T9. `set_param_by_name(module, name, value)` — 按名字设参数

**入参** `{ "module":"VCO"|42, "name":"起音"|"Attack", "value":0.3, "dry_run":false }`
**返回** `{ "resolved":{"pid":1,"name":"Attack","score":3,"candidates":[[3,1,"Attack"],[1,5,"Decay"]]}, "applied":true, "before":0.02, "after":0.3, "undoable":false }`

**实现要点**：走 `paramlib.resolve_name()`（`paramlib.py:834-861`）打分取最高分（内部已做中文口语展开 `:846-849`）。⛔ **必须拒绝 `kind=="reserved"` 的槽**：`paramlib.py:673-686` 为「enum 里有但无 `configParam`」的槽生成占位（VCF 1 号、Clocked 14 号）—— 设进去不报错但**没有任何效果**，是最难查的哑弹；命中时返回 `{"error":"reserved_slot","pid":N}`，**不回退次高分**（次高分同样是错的）。`resolve_name` 空 → `{"error":"no_match","candidates":[前5个已有 param 名]}` 帮 LLM 换词重试。`undoable:false` 因现有 `/param`（`CardinalCommon.cpp:760-790`）走 `Engine::setParamValue`（`Engine.hpp:186`）**绕过 history**；编译后改用 H7 即为 true。
**验收**：`name:"起音"` → `pid:1 "Attack"`；VCF `name:"1"` → `{"error":"reserved_slot"}`，**不是**静默成功。

## T9b. `cardinal_set_params_batch(patch, sets[])` — 批量设参（✅ 已实现 2026-10-21）

**入参** `{ "patch":"<name>", "sets":[{"module":"VCO","param":"Frequency","value":8.0,"instance":0}], "load_after":false }`
**返回** `{ "ok":true, "written":true, "applied":2, "requested":3, "failed":1, "backup":"<patch>.bak-param", "results":[{ "index":0, "ok":true, "module":"Bogaudio/Bogaudio-VCO", "module_id":..., "param_id":0, "param_name":"Frequency", "value":8.0, "warnings":[...] }] }`

**实现要点**：一次读盘、一次备份、一次写盘（不是循环调 T9）。每条**独立** try/except ⇒ 一条失败不打断其余，失败条目仍回执。复用 T9 的 `reserved` 守门、越界警告（照写不裁剪）、多实例提示。⛔ **全部失败 ⇒ 不写盘**（`written:false`，原文件 mtime 不变）。
**验收**：3 条里 2 成功 1 失败 ⇒ 成功的已落盘、失败条目带 `error`；reserved 槽被拒；全失败时 `written:false`。

## T9c. `cardinal_diff(name, check_params=true)` — 参数级差异（✅ 已实现 2026-10-21，E8 解锁）

**入参** `{ "name":"<name>", "check_params":true }`
**返回** `{ "match":true, "params_match":false, "params_checked":595, "params":{ "params_compared":595, "params_unserialized":0, "params_mismatched":1, "tolerance":0.0001 }, "param_mismatches":[{ "module_id":..., "module":"Bogaudio/Bogaudio-VCO", "param_id":0, "file_value":8.0, "live_value":3.5, "delta":-4.5 }] }`

**实现要点**：**结构层与参数层分开报告**（两者可信度不同，参数层受引擎序列化规则影响）。live 侧取 Cardinal 的 autosave（`Manager::saveAutosave()` 用 `toJson()` ⇒ 必然带 params）。🔴 **三条误报防护**：① 引擎跳过不序列化的无界参数（`!isBounded()`）⇒ 归 `params_unserialized`，**不判错**；② 值比较带容差 `1e-4`（吸收 float32 量化误差 ~6e-9）；③ 模块整体缺失归结构层，不在参数层重复报。
**验收**：改 live 端一个参数 ⇒ `params_match=false` 且恰好 1 条不一致；只改结构 ⇒ `match=false` 而 `params_match=true`。

## T10. `cardinal_audit(patch, checks[])` — 聚合审计

**入参** `{ "patch":"live"|"<name>", "checks":["ports","flow","values","chain"] }`
**返回** `{ "ports":{"hard":[],"count":0}, "flow":{"hard":["..."],"soft":["..."]}, "values":{"hard":["..."],"L2L3":["..."]}, "chain":{"hard":["..."]}, "verdict":"pass"|"reject", "summary":{"hard_total":0} }`

**实现要点**：纯聚合 T1 四脚本（`audit_ports.py:66` / `audit_flow.py:134` / `audit_values.py:282`（末尾 `return sorted(out)` `:448`）/ `audit_chain.py:41`（有 `print`，需容忍 stdout 噪声或重定向））。
**验收**：四个 key 恒存在，无命中也给空数组（不能缺 key）。

## T11. `cardinal_knob_watch(module, params[], interval)` — 旋钮实时监控

**入参** `{ "module":42, "params":["Cutoff","Resonance"]|[3,4], "interval":0.25, "duration":4.0 }`
**返回** `{ "series":[{"t":0.0,"values":{"3":0.2,"4":0.55}},{"t":0.25,"values":{"3":0.21,"4":0.55}}], "changes":[{"pid":3,"from":0.2,"to":0.75,"at_t":1.5}], "final":{"3":0.75,"4":0.55}, "probe_ok":true }`

**实现要点**：底层 `get_param()`（`cardinal_mcp.py:338`）→ `/param-get` → 引擎 `ParamQuantity::getDisplayValue()`（`CardinalCommon.cpp:451`），**拿到的已经是物理显示值**（275ms 而非 0.275）；⛔ **串行**（0.1 无关联 id），`interval` 最小 **≥0.2s**；⚠️ **不要用它监控 CPU**（1s 刷新，见 0.6；CPU 用 H3）；pid 名字解析走 T9，命中 `reserved` 同样拒绝。
**验收**：`duration:1.0, interval:0.25` → `series` 长度 ≈4；不设 `params` 时默认监控全部（先 `paramlib.describe` `:812`）。

---

# 第二部分：Handler 规格（需编译，**一次编译**）

> ⚠️ **本部分不给 C++ 函数签名。** 实现者对着既有范式（`history::ModuleAdd::redo()`、`osc_modules_handler` `CardinalCommon.cpp:395`）自行确定签名与内部结构。反面教材：第一轮曾把 `getMinDisplayValue`/`getValueAsString` 当作存在报给 PM，实际**不存在**（正确名 `getDisplayValueString()` `ParamQuantity.hpp:100` 与 `Quantity::getString()` `Quantity.hpp:74`），险些返工。
> 本部分给的是：**协议契约 + 行为要求 + 注册位置 + 验收标准**。

## 2.0 通用规则

**① 响应**：全部按 0.2 三段式；**所有 assert 分支必须回 err**。
**② 分页**：列表类按 0.3 带 `<returned>/<total>`，`limit` 上限 64。
**③ 注册表抽函数（根治双写，采用此方案）**：现状 thread 版 `lo_server_thread_add_method` 在 `CardinalCommon.cpp:1135-1145`、非 thread 版 `lo_server_add_method` 在 `:1152-1160`；⛔ 只写一处 ⇒ 换构建配置后**静默失效**（不报错、收不到）。**方案**：抽成单一函数（建议名 `CardinalCommon_RegisterOscMethods(lo_server server, Initializer* self)`，实现放在 `osc_fallback_handler` 之前），thread 版 `:1135` 前后调一次、非 thread 版 `:1152` 前后调一次，**以后加 handler 只改一行**。
**④ build-time 条件**：`CARDINAL_WINDOW_CAN_GENERATE_SCREENSHOTS` 被 `#if !(defined(DGL_USE_GLES) || CARDINAL_VARIANT_MINI)` 包住（`override/Window.cpp:45`）⇒ **H4 的注册本身必须在该 `#ifdef` 内**，否则 Mini/GLES 构建编译不过。⇒ 变体矩阵 **2（thread/非thread）× 2（常规/Mini-GLES）= 4 种**；抽函数后只需在函数内一处加 `#ifdef`。
**⑤ RAII contextSet guard（强制行为要求）**：现有 `/param` 有缺陷 —— `DISTRHO_SAFE_ASSERT_RETURN(module != nullptr, 0)`（`CardinalCommon.cpp:788`）在 `contextSet(nullptr)` **之前** return，module 查不到时 thread-local context 泄漏。**要求**：每个新 handler 开头创建 guard，构造时 `contextSet(context)`，析构时 **`contextSet(prev)` 恢复原值（而非置 nullptr）**，保证**所有 return 路径（含 assert 提前 return）自动正确**。不必改现有 `/param`，避免动已验证路径。
**⑥ 诚实语义**：⛔ 不宣称事务原子性（0.9）。
**⑦ 位置**：全部 handler 放在 `CARDINAL-MCP-READ-PROBES-END`（`CardinalCommon.cpp:689`）之后，与现有 5 探针同区块。

---

## H0. `/build-info` — 构建标识与能力协商（**P0，最高优先**）

| 项 | 内容 |
|---|---|
| types / 位置 | `""`（无参）；`CardinalCommon.cpp` 探针区块内（`:689` 之后），注册进 2.0③ 的注册表函数 |
| **行为要求** | **无条件立即回复**，不做任何可能阻塞/失败的查询。这是 MCP 的健康检查心跳。唯一 `err` 条件是 `context` 为空 → `err engine_error\|no context` |
| payload | `version=<Cardinal 版本>,variant=main\|mini,osc_thread=1\|0,built=<__DATE__> <__TIME__>,safeMode=0\|1,modules=<n>,caps=<逗号分隔的已注册路径清单>` |
| ⭐ 必要性 | `CARDINAL_OSC_AUTOSTART` 是**运行期 getenv**（`override/MenuBar.cpp:741`、`CardinalCommon.cpp:1040-1043`），**不是编译期宏**，全仓无 `-D` 定义 ⇒ **OSC 服务是否启动取决于宿主环境变量**。若某 DAW 环境没开，MCP 侧表现为「所有工具超时」，**与「Cardinal 崩了」现象上无法区分** |
| 收益 | ① 环境问题在**第一次调用**就暴露；② MCP 侧有确定健康检查；③ `caps` 让 MCP **自动降级**而不是靠超时试探；④ `variant`/`osc_thread` 让 Python 侧不必猜 |
| 风险 | 无（纯字符串拼接） |
| 验收 | 正常环境先调 `/build-info` → `ok` + `caps` 含全部已注册路径；Mini 构建 → `caps` **不含** `screenshot`（编译期就没注册）；未启动 OSC → 超时（此时才落到超时路径） |

## H1. `/cables` — 线缆拓扑（零 hook，P0）

| 项 | 内容 |
|---|---|
| types | `"h"`（可扩展 `"hi"` = moduleId 过滤）；分页参数见 0.3 |
| 实现 | `getCableIds()`（`Engine.hpp:163`，share-lock）→ 逐个 `getCable(id)`（`:183`）→ 读 `c->inputModule->id`/`inputId`/`outputModule->id`/`outputId`（`Cable.hpp:15-19`，**全 public**） |
| payload | `"<returned>/<total>,<im:II>-<om:OO>,..."` |
| 行为要求 | 遵守 2.0①②；空机架回 `"ok"` + `0/0,`（⛔ 不是 err，也不是空字符串） |
| 风险 | **低**。全 share-lock，无音频线程交互。⚠️ 必须分页：大机架线缆可数千条 |
| 验收 | 单 VCO→VCF → `1/1,42:0-43:1`；200+ 线缆机架 → 不超 MTU、`total` 正确 |

## H2. `/transport` — 走带状态（零 hook，P0，**性价比最高**）

| 项 | 内容 |
|---|---|
| types / 实现 | `""`；读 `CardinalPluginContext`（`include/plugincontext.hpp:81-103`）字段，**全部零 hook**：`playing`(:86)/`bypassed`(:86)/`bar`(:87)/`beat`(:87)/`beatsPerBar`(:87)/`beatType`(:87)/`barStartTick`(:89)/`beatsPerMinute`(:89)/`tick`(:90)/`tickClock`(:90)/`ticksPerBeat`(:90)/`ticksPerFrame`(:90)/`frame`(:88)/`processCounter`(:82)/`sampleRate`(:83)/`bufferSize`(:82) |
| payload | `"playing=1,bar=3,beat=2,bpm=120.00,tick=3840,sr=48000,bufsz=64,proc=12345,sampled=1"` |
| 价值 | ⭐ 判断「跑带机在不在转」的**权威数据**，比 `/light` 猜 RUN 灯准得多。直接支撑 T2 的 `upstream_silent`（上游没跑带 ⇒ 全下游静音） |
| 风险 | 低。⚠️ 字段由 DSP 线程写（`CardinalPlugin.cpp:1288` 自增 `processCounter`），OSC 线程读是**非原子瞬时采样**（0.5）⇒ payload 标 `sampled=1`，MCP 不重试 |
| 验收 | 宿主播放 → `playing=1` 且 `tick` 单调递增；停播 → `playing=0` |

## H3. `/engine-info` — 引擎状态 + CPU meter（零 hook，P0）

| 项 | 内容 |
|---|---|
| types / 实现 | `""`；`getSampleRate()`(`Engine.hpp:50`)/`getFrame()`(:68)/`getBlock()`(:71)/`getBlockTime()`(:77)/`getBlockFrames()`(:80)/`getMeterAverage()`(:87)/`getMeterMax()`(:88)/`getMasterModule()`(:46)/`getNumModules()`(:91)/`getNumCables()`(:153) |
| payload | `"sr=48000,frame=123456,block=9876,blockTime=12.34,cpuAvg=0.184,cpuMax=0.412,cpuAgeMs=340,master=42,modules=24,cables=31"` |
| ⚠️ **必须带 `cpuAgeMs`** | `meterLastAverage` 只在 `startTime - meterLastTime >= 1.0` 时更新（`Engine.cpp:576`）。用 `system::getTime() - meterLastTime` 得 age，让 MCP 判断新鲜度（0.6） |
| 风险 / 验收 | 低（share-lock 或无锁读 double）；连续调 5 次 → 后 4 次 `cpuAvg` 相同且 `cpuAgeMs` 递增 |

## H4. `/screenshot` — GUI 截图（异步两段式，GUI-only，P1）

| 项 | 内容 |
|---|---|
| types | `"b"`（带一个 token blob，原样回传用于配对） |
| 位置 | 实现与**注册都必须在 `#ifdef CARDINAL_WINDOW_CAN_GENERATE_SCREENSHOTS` 内**（2.0④） |
| 实现（发起侧） | 调 `rack::window::generateScreenshot()` —— ⚠️ **声明在 `src/CardinalCommon.hpp:26`，不在 `Rack/include/window/Window.hpp`**（PM 文档已标注此坑）。实现 `override/Window.cpp:906-910`，就一行：`APP->window->internal->generateScreenshotStep = kScreenshotStepStarted;` |
| 实现（回调侧） | base64 落点 `override/Window.cpp:588-592`（`String::asBase64` → `ui->setState("screenshot",...)`）。在 **`:734` 的 `stbi_write_png_to_func` 回调**处多推一条 OSC：`/resp "screenshot" "ok" "<token>|<base64>..."` |
| 时序 | 状态机 `:706-747`，`:722 glReadPixels` 读 GL **前缓冲**。⛔ **异步，需等约 4 帧** ⇒ 必须「请求 → 收推送」两段式，⛔ **不能同步等**（`ask()` 1.5s 不够） |
| ⚠️ **GUI-only** | ① Mini 变体**编译时就没有**（`override/Window.cpp:45`）；② headless 用 `src/custom/RemoteWindow.cpp`，其 `screenshot()`(:111)/`screenshotModules()`(:115) 是**空 stub** |
| 风险 | 中。内存峰值 `winW*winH*4`（`:718`，大窗口约 33MB）+ base64 涨 33% ⇒ 单包必爆 MTU，**必须分块**（每次 1200 字节 + 序号 + 总块数） |
| 价值 / 验收 | 自验证闭环：改完接线截图看线对不对、诊断完截图看 LED 亮不亮。常规 GUI 构建 → PNG 与画面一致（人工目视）；Mini 构建 → `caps` 不含 `screenshot`；headless → `err not_supported_in_this_build` |

## H5. `/undo` `/redo` — 原生撤销（零 hook，P0）

| 项 | 内容 |
|---|---|
| types / 实现 | `""`；`APP->history->undo()`（`history.cpp:260`）/ `redo()`（`:267`），可带 `canUndo()`(:274)/`canRedo()`(:278)/`getUndoName()`(:282)/`getRedoName()`(:288)/`isSaved()`(:298) |
| payload | `"ok,canUndo=1,canRedo=0,name=change parameter"`；无历史时 `err engine_error\|nothing to undo`（⛔ 不是 `"ok,canUndo=0"`，否则被当成功） |
| 风险 | ⚛️ **高 —— 必须在 UI 线程执行**。`history::State` 及其 Action 全是裸指针无锁（`history.hpp:173-194`），且 `ModuleAdd::redo()` 会 `APP->scene->rack->addModule()`。非 thread 构建下 OSC 在 UI 线程 `stepRemoteServer()`（`override/MenuBar.cpp:852`）被 pump，直接调即**竞态**；thread 版可接受（OSC 独立线程） |
| 依赖 | 需 `APP->scene` 非空 ⇒ headless 回 `not_supported_in_this_build` |
| 验收 | `/batch` 加 3 模块后 `/undo` → 3 个全消失；`canUndo=0` 时 `/undo` 回 err |

## H6. `/batch` — 批量操作（P1）

| 项 | 内容 |
|---|---|
| types / 实现 | `"b"`（pax tar + zstd blob，内含 ops）；解包 → 构造 `history::ComplexAction`（`history.hpp:52-60`）→ 逐个 `push(Action*)`（`:58`，实现会**递归** push 子 action）→ `APP->history->push()`（`history.cpp:234`）→ 逐个 `redo()` |
| 现成 Action | `ModuleAdd`(:71)/`ModuleRemove`(:85)/`ModuleMove`(:92)/`ModuleBypass`(:103)/`ModuleChange`(:113)/`ParamChange`(:125)/`CableAdd`(:137)/`CableRemove` |
| ⚠️ **诚实语义** | ⛔ **不要宣称 all-or-nothing**。`ModuleAdd::redo()` 的写法是「`catch` 吞异常 → 继续 `addModule`」；`Engine::fromJson`（`Engine.cpp:1216-1260`）也是循环 + catch + `continue`。⇒ 必须返回 `applied:N skipped:M` + 每个 skipped 的原因。这是**引擎既有语义，不是缺陷** |
| payload | `"applied=5,skipped=2,reason=Could not find module Foo/Bar"`（skipped 多时按 0.3 截断/分块） |
| 风险 | ⚠️ 高。同 H5 线程约束 + `RackWidget::addModule` 依赖 `APP->scene` ⇒ headless 不可用，回 `not_supported_in_this_build` |
| ⭐ 差异化 / 验收 | 「批量生成 patch 后一步撤销」—— 4 个对标宿主里只有 Unity 能做，PM 已定位为宣传点。提交 3 成功 + 2 失败（错 slug）→ `applied=3 skipped=2`；随后一次 `/undo` → 3 个成功项全消失 |

## H7. `/param-set` — 可撤销的设参数（P1，替换现有 `/param`）

| 项 | 内容 |
|---|---|
| types / 实现 | `"hif"`（moduleId, paramId, value）；先读旧值 `getParamValue()`（`Engine.hpp:187`，无锁读 `params[i]`）→ `setParamValue()`（`:186`，**exclusive-lock**）→ 构造 `history::ParamChange{moduleId, paramId, oldValue, newValue}`（`history.hpp:125-134`）→ `APP->history->push()` |
| payload / 越界 | `"ok,old=0.02,new=0.30,undoable=1"`；找不到时 `err no_such_module` / `err no_such_param`（⛔ 不是空 payload） |
| 价值 / 风险 | 现有 `/param`（`CardinalCommon.cpp:760-790`）**绕过 history ⇒ 不可撤销**，这是 T9 返回 `undoable:false` 的根因；低-中风险，exclusive-lock 会短暂阻塞音频线程（同 `resetModule` 量级） |
| 验收 | `/param-set` 后 `/undo` → 参数回旧值、T9 该路径 `undoable:true`；不存在 pid → `err no_such_param` |

## H8. `/plugins` — 已加载插件清单（P0，诊断用）

| 项 | 内容 |
|---|---|
| types / 实现 | `""` 或 `"s"`（slug 过滤），分页见 0.3；遍历 `rack::plugin::plugins`（`plugin.hpp:39` `extern std::vector<Plugin*> plugins`）→ `Plugin::slug` → `models`（`Model::slug` + `getFullName()` `plugin/Model.hpp:73`） |
| payload | 分页 `"<returned>/<total>,<pluginSlug>:<model1>\|<model2>,..."` |
| 价值 | ⭐ **这是「我拼写的 plugin 到底存不存在」的权威答案**。`plugin::modelFromJson`（`plugin.cpp:457-475`）找不到时抛 `"Could not find module %s/%s"`，`Engine::fromJson`（`Engine.cpp:1229-1236`）catch 后 `continue` **静默丢弃**。有了它，MCP 能在生成 patch 前就校验 slug |
| ⚠️ **必须同时暴露** | `settings::safeMode`（`settings.hpp:31`）—— 它为 true 时 `plugin::init()` 在 `plugin.cpp:273-275` 直接 `return`，**一个插件都不加载**。这是「插件全都找不到」的隐藏陷阱，必须带上让上层区分「没装」与「被禁用」。附带 `asset::systemDir` / `plugin::pluginsPath`（`plugin.cpp:256-262`，devMode 下 = `asset::user("plugins")`）⇒ 可直接告诉用户插件该放哪 |
| 风险 / 验收 | 低（纯只读遍历）；safeMode 构建 → `safeMode=1` 且 `total=0`；正常构建 → 查得到 `Bogaudio-VCO/VCO`；查不存在的 slug → 空结果 + `total` 如实，**不是** err |

## H9. `/load` 回传 `warningLog`（P0，**两处修复**，⚠️ 2026-10-19 重写 —— 旧版「≈3 行」判断错误）

**这是整个诊断链路的源头修复，也是 0.9 具名能力的唯一改动点。**

🔴 **本节 2026-10-19 全面重写**。旧版判断「handler 读 `patch->warningLog` 塞进响应 ≈3 行即可」**不成立**，本机 WSL 源码核实（`override/Engine.cpp:1260` 与 `:1289`）：

```
override/Engine.cpp:1260   // APP->patch->log(e.what());    ← 被注释！
override/Engine.cpp:1289   // APP->patch->log(e.what());    ← 被注释
```

`Engine::fromJson` catch 到模块加载错误时本应 `patch->log(...)` 写进 warningLog，但 override 版（**编译生效版**）这两行被注释 ⇒ **warningLog 恒为空**。只改 handler 的 3 行方案读到的永远是空串 —— 假阳性诊断，比没有诊断更糟。

⇒ **正确修法是两处**：

| # | 改动 | 文件 | 为什么必须 |
|---|---|---|---|
| ① | 恢复被注释的两行 `APP->patch->log(e.what());` | `src/override/Engine.cpp:1260` 与 `:1289` | 不恢复则 warningLog 恒空，② 读到空 |
| ② | `Manager` 加持久字段 `lastLoadWarnings`；`fromJson` 末尾（现 `warningLog = ""` 处）先把 warningLog 存进字段再清 | `src/Rack/src/patch.cpp`（`:534` 附近）+ `include/patch.hpp`（`warningLog` 声明旁，`:26`） | `Manager::fromJson` 结尾**清空 warningLog**（本机核实：`patch.cpp` 的 `warningLog = ""` 在 osdialog 之后执行）；`osc_load_handler` 里 `loadAutosave()` 返回后 fromJson 已跑完，读 `warningLog` 恒为空 ⇒ 必须经 `lastLoadWarnings` 取 |

`patch::Manager::fromJson`（`src/Rack/src/patch.cpp:476-535`）现状：
```
:478  warningLog = "";                       // 开头清空
:519  APP->engine->fromJson(rootJ);          // 期间 Engine::fromJson 的 catch 往里写错误
                                             //   ⚠️ 但 override/Engine.cpp:1260/:1289 两行 log 被注释 ⇒ 实际什么都不写
:531-533  if (warningLog != "") osdialog_message(...)   // Cardinal 里被 stub（src/custom/osdialog.cpp:28）
:534  warningLog = "";                       // ★ 结尾清空 ⇒ handler 读不到
```

**行为要求**（不给签名）：`osc_load_handler` 在 `loadAutosave()` 之后读 `context->patch->lastLoadWarnings`（新增字段，**不是** `warningLog`），塞进响应。响应按 0.2 三段式：加载成功但有 skipped → `"ok"` + payload 含 `applied=N skipped=M` + warnings；加载本身失败 → `err patch_load_failed|<首行诊断>`。

**payload**：`"applied=21,skipped=2,warnings=Could not find module Foo/Bar\nCould not find module Baz/Qux"`
**风险/验收**：低；warningLog 可能很长 ⇒ 按 0.3 截断并带 `skippedTotal`。验收：加载含 1 个错 slug 的 patch → 响应含 `Could not find module X/Y` 且 `skipped=1`；**加载一个完全正常的 patch → warnings 为空**（防「恢复注释后把正常路径也搞响」）。

## H10. `/midi-out` — MIDI 输出（P2）

| 项 | 内容 |
|---|---|
| types / 实现 | `"b"`（原始 MIDI 字节 blob + 内嵌 frame/channel）；`CardinalPluginContext::writeMidiMessage(msg, channel)` —— 声明 `include/plugincontext.hpp:100`，实现 `CardinalCommon.cpp:202-235` |
| ⚠️ **两个硬 assert** | `message.frame >= 0`（`:208`）⇒ **必须自己设 frame**（语义见 `include/midi.hpp:19-24`：output 是「生成时的 frame」，-1 表示立即发送）；`size > 0`（`:207`） |
| ⚠️ **bypassed 提前返回** | `if (bypassed) return;`（`:204`）⇒ 响应必须回显 `skipped:bypassed`，否则 MCP 以为发出去了 |
| 状态字节映射 | `:214-235` 按 `bytes[0] & 0xF0` 判 3 字节 / `& 0x0F` 判 SysEx 长度 ⇒ blob 长度须合法 |
| 风险 | 中。音频线程相关，⚠️ 建议在 DSP 回调里排队而非 OSC 线程直发 |
| **MIDI-IN 不做** | `midi::InputQueue::onMessage()`（`midi.hpp:265`）虽是 public virtual，但**没有任何全局注册表能枚举所有 InputQueue**（`Port::driverId/deviceId` 在 `midi.hpp:203-205` 是 private 区）。做 IN 需改 `src/Rack/src/midi.cpp` 加注册表（约 30 行）⇒ 降级 P3 |
| 附带提醒 | **Cardinal 已删 MIDI 面板**（`include/app/` 下只有 `MidiDisplay.hpp`，无 `MidiPanel`；`override/MenuBar.cpp:805` 只剩 "Enable/Reconnect MIDI" 开关）⇒ **「MIDI 映射表读取」不存在，别写进能力矩阵** |

## 2.9 JS 侧承载清单（配合 0.8 一次编译）

以下能力**不写原生 handler**，用 QuickJS 绑定实现（工程量从「改 C++ + 重编」降为「加一段 JS」）：遍历/聚合类（`/modules` 分页、`/plugins` 枚举、`/cables` 拓扑，JS 直接调 `context->engine->getModuleIds()/getCableIds()`）；派生计算类（峰值包络、通道统计、role 归类）。
⛔ 例外，必须原生：碰音频线程或必须零 hook 的 —— H2 `/transport`、H3 `/engine-info`、H4 `/screenshot`、H7 `/param-set`、H9 `/load` warnLog。

QuickJS 现状：已静态链入（`src/Makefile.cardinal.mk:152-154` 链 `libquickjs.a`，含 `quickjs-libc.o` 提供 `os.exec`/`std.getenv` 等），但**引擎侧零使用**，只被 AriaModules Qqqq 当乐谱解析器；**现成 RAII 封装可直接抄**：`plugins/AriaModules/src/javascript.hpp`（85 行，含 `JS_NewRuntime`/`JS_NewContext`/`JS_Eval`/`JS_ToCString`）。⚠️ **绑定必须挂 DSP 回调或入队后预算执行，不要在音频回调里跑任意 JS**；且 `quickjs-libc` 带 `os.exec` ⇒ 绑定暴露给 MCP 等于给了宿主内代码执行，**必须在用户文档显式声明这是有意设计**（用户要的就是 DCC 宿主级脚本能力）。

---

# 第三部分：风险清单与验证方案

## 3.1 每个 handler 的失败模式与降级

| handler | 未编译时 | 运行期失败 | 降级路径 |
|---|---|---|---|
| `/build-info` H0 | 超时（这本身就是结论） | context 空 | `err engine_error` |
| 现有 5 探针 | 超时 → `probe_not_supported`（`cardinal_mcp.py:293-299` 已实现） | assert 分支（改造后回 err） | `PROBE_UNSUPPORTED` |
| `/cables` H1 | 同上 | payload 超 MTU | 分页；`total` 如实上报 |
| `/transport` H2 | 同上 | 字段撕裂（0.5） | 标 `sampled=1`，不重试 |
| `/engine-info` H3 | 同上 | **cpu 值 1s 内不变** | 带 `cpuAgeMs`；MCP 侧缓存（0.6） |
| `/screenshot` H4 | 同上 | ① Mini/headless **编译时就没有** ② 异步超时 ③ base64 超 MTU ④ 33MB 内存峰值 | 全走 `err`+code；⛔ **绝不用同步 `ask()` 等回调** |
| `/undo` `/redo` H5 | 同上 | headless 无 `APP->scene`；无历史 | `not_supported_in_this_build` / `engine_error` |
| `/batch` H6 | 同上 | 同上 + **不保证原子** | 返回 `applied/skipped`，⛔ 不宣称事务 |
| `/param-set` H7 | 同上 | module/param 越界 | `no_such_module` / `no_such_param` |
| `/plugins` H8 | 同上 | **`safeMode=true` ⇒ 零插件** | 响应带 `safeMode`，区分「没装」与「被禁用」 |
| `/load` warnLog H9 | 旧 `/load` 仍可用 | warningLog 为空 | 无 skipped ⇒ T3 退回双集合 diff 反推 |
| `/midi-out` H10 | 同上 | `bypassed` / assert 失败 | 回显 `skipped:bypassed` |

**统一铁律**：⛔ **任何情况下不得返回「成功但数据为空」来表达错误。** 空数据 / 未编译 / 出错 三者必须可区分。

## 3.2 编译后的逐项验证步骤

**第 0 步：确认补丁真的编进去了**（避免假阳性）
```bash
# ✅ 必须用带连字符的串或函数名
strings -a "D:/Cardinal/bin/Cardinal" | grep -c 'param-get'    # 期望 ≥1
strings -a "D:/Cardinal/bin/Cardinal" | grep -c 'build-info'   # H0 编译后
strings -a "D:/Cardinal/bin/Cardinal" | grep -c '/cables'      # H1 编译后
# ⛔ 不要用 grep -c '/modules' —— 会得到 11 次假阳性（全是 JUCE 的 ../../modules/water/... 路径）
```
> 判据：`param-get` 当前实测 = **0**（未编译）；`/modules` 当前 = 11（假阳性）。

**第 1 步：连通性（先做健康检查）**：`python D:/Cardinal/tools/cardinal_mcp.py --call /build-info`
> 端口默认 2228（`src/CardinalRemote.hpp:9`；MCP 侧 `cardinal_mcp.py:83`），`CARDINAL_PORT` 可覆盖。⚠️ 若 `/build-info` 也超时：OSC 服务由**运行期** `getenv("CARDINAL_REMOTE_HOST_PORT")` 决定（`CardinalCommon.cpp:1040-1043`，非编译期宏），宿主环境没开就静默不通 —— **这正是 H0 存在的理由**。

**第 2 步：逐个 handler 实测**（每条独立可跑，⛔ 必须串行）
```bash
python D:/Cardinal/tools/cardinal_mcp.py --selftest     # 覆盖 /hello /modules /param-get /ports /signal /light
python D:/Cardinal/tools/cardinal_mcp.py --call /cables
python D:/Cardinal/tools/cardinal_mcp.py --call /transport
python D:/Cardinal/tools/cardinal_mcp.py --call /engine-info
python D:/Cardinal/tools/cardinal_mcp.py --call /plugins
python D:/Cardinal/tools/cardinal_mcp.py --call /undo --redo
python D:/Cardinal/tools/cardinal_mcp.py --call /load --file D:/Cardinal/patches/bad-slug.vcv
python D:/Cardinal/tools/cardinal_mcp.py --call /screenshot --out D:/Cardinal/shots/x.png
```
> 若 `--call` 子命令不存在，在 `cardinal_mcp.py` 加一个通用 escape-hatch（约 10 行），比给每个 handler 写一次性测试便宜。

**第 3 步：端到端验收**

| 验收项 | 期望 |
|---|---|
| 加载含 1 个错 plugin slug 的 patch | `/load` 回 `ok` **且** payload 含 `Could not find module X/Y` 与 `skipped=1`；`/modules` 少 1 个；T3 `"loaded_with_drops"` |
| ⭐ 闭环：对上一步 patch 跑 T2 | `issue:"load_failed"`, `confidence:1.0`, `evidence.source=="load_warning_log"` |
| 把某模块 bypass | T2 输出 `issue:"bypassed"`, `confidence:1.0`, `source=="isBypassed"` |
| `/batch` 加 3 模块后 `/undo` | 3 个全消失（`ComplexAction` 一次回滚） |
| `/param-set` 后 `/undo` | 参数回旧值，T9 该路径 `undoable:true` |
| `/engine-info` 连续调 5 次 | 后 4 次 `cpuAvg` 相同且 `cpuAgeMs` 递增 |
| `/screenshot` | PNG 与 GUI 当前画面一致（人工目视） |
| 未编译构建下调 `/cables` | `probe_not_supported`，⛔ **不是** 空数组 |
| 对不存在的 moduleId 调 `/ports` | `err no_such_module`，⛔ **不是** 空 payload |
| 超大机架调 `/modules` | 分页返回，`total` 与实际模块数一致，不超 MTU |

## 3.3 并发 / 线程安全显式声明

**读（可能撕裂，瞬时采样，不会崩）**
| 数据 | 写方 | 读方 | 说明 |
|---|---|---|---|
| Port 电压 / channels | 音频线程 `Module::doProcess()`（`Module.cpp:335-370`）**无锁** | OSC/UI | `Engine` 的 `SharedMutex`（`Engine.cpp:227`）**不保护**。Cardinal 既定设计（`PortWidget::step()` 也无锁读） |
| Light 亮度 | 同上 | OSC/UI | 同上。`Light::getBrightness()`（`Light.hpp:20`） |
| `CardinalPluginContext` 字段 | DSP 线程（`CardinalPlugin.cpp:1288` / `CardinalUI.cpp:649`） | OSC | 非原子瞬时采样 |
| `Engine::getParamValue()` | — | — | **无锁**直读 `params[i]`（`Engine.cpp:1067-1069`） |

**写（需要锁）**
| 操作 | 锁 | 阻塞音频？ |
|---|---|---|
| `getModuleIds/getModule/getCableIds/getMeter*` | `SharedLock`（`Engine.cpp:944/918/939`） | 否，可并发 |
| `Engine::setParamValue` | `lock_guard`（`Engine.cpp:1050`） | **是**（短暂） |
| `resetModule/randomizeModule/bypassModule` | `lock_guard`（`:853/862/875`） | **是** |
| `addModule/removeModule/addCable/removeCable/moduleFromJson/fromJson` | `lock_guard` | **是** |

**⛔ UI-only（OSC 线程调用即竞态）**：一切 `APP->scene->...` / `RackWidget::*` / `ModuleWidget::*`（widget 树裸指针无锁，只在 UI 线程 step/draw）；`APP->history->push/undo/redo`（`history.hpp:173-194` 裸指针无锁）；`patch::Manager::load/save`（触发文件 IO + `prepareSave()` 事件）。
⇒ **H5 `/undo` `/redo`、H6 `/batch` 在非 thread 构建下必须转发到 UI 线程队列**，不能在 `stepRemoteServer()`（`override/MenuBar.cpp:852`，UI 线程）里同步执行。

## 3.4 尚未解决的风险（需 team-lead 决策）

1. **OSC 启动依赖运行期环境变量**（`CardinalCommon.cpp:1040-1042` 是 `getenv`，全仓无 `-D`）⇒ H0 `/build-info` 定为 **P0**，把「环境没开」与「Cardinal 崩了」区分开。
2. **`/screenshot` base64 必然超 MTU**，分块协议需 MCP 侧配套（约 60 行），是否第一版就做待决。
3. **MIDI-IN 需改 `src/Rack/src/midi.cpp` 加注册表**（约 30 行），已从 P2 降到 P3，第一版不做。
4. **JS 绑定的安全边界**：`quickjs-libc` 带 `os.exec` ⇒ 绑定即等于给宿主内代码执行。这是**有意设计**，但必须在用户文档显式声明。
5. **两种构建（thread / 非 thread）都要验**：注册表抽函数（2.0③）后仍需各跑一遍第 2 步，确认 `caps` 列表一致。

---

## 附：关键源码坐标速查

| 主题 | 坐标 |
|---|---|
| 探针区块 | `src/CardinalCommon.cpp:357`(BEGIN) / `:689`(END) |
| handler 注册（双写） | `:1135-1145`(thread) / `:1152-1160`(非thread) |
| fallback（未知路径静默丢弃） | `:690-693` |
| `/load` handler（要改的地方） | `override/CardinalCommon.cpp:714-758`，lastLoadWarnings 插入点 `:745` 附近 |
| `/param` 的 contextSet 缺陷 | `:788` |
| `/ports` 4 通道截断注释 | `:544` |
| `/modules` 无上限拼接 | `:395` |
| OSC 端口默认值 / 启动(getenv) / 每帧 pump | `src/CardinalRemote.hpp:9`；`CardinalCommon.cpp:1040-1043`；`override/MenuBar.cpp:741,852` |
| Engine 只读 API | `include/engine/Engine.hpp:46/50/68/71/87/88/91/117/121/163/183/225` |
| Engine 锁 / CPU meter 1s 刷新 | `Engine.cpp:227`；`:576` |
| 静默丢弃模块 | `Engine.cpp:1229-1236`(model) / `:1247-1260`(module) / `:1216-1260`(fromJson) |
| `warningLog` 两次清空 | `src/Rack/src/patch.cpp:478` / `:534`；字段声明 `include/patch.hpp`；⚠️ override/Engine.cpp 两行 log 被注释（:1260/:1289） |
| history 可编程 undo | `src/Rack/src/history.cpp:234/260/267/274/278/282/298` |
| `ComplexAction` / `ParamChange` / Action 范式 | `include/history.hpp:52-60` / `:125-134`；`history.cpp`（`ModuleAdd::redo`/`CableAdd::redo`） |
| `RackWidget::addModule` 依赖 scene | `src/Rack/src/app/RackWidget.cpp:594-607` |
| `Cable` public 字段 / `Module::isBypassed()` | `include/engine/Cable.hpp:15-19`；`Module.hpp:465` → `Module.cpp:286` |
| ParamQuantity 读接口（**注意正确名**） | `ParamQuantity.hpp:82/92/94-97/100/104/105`；`getString()` `Quantity.hpp:74` |
| Port 读接口 | `Port.hpp:50/55/99/110/175/182`（`PORT_MAX_CHANNELS=16` @ `:11`） |
| `CardinalPluginContext` / `writeMidiMessage` | `include/plugincontext.hpp:82-90` / `:100`；实现 `CardinalCommon.cpp:202-235` |
| QuickJS 链入 / 现成封装 | `src/Makefile.cardinal.mk:152-154`；`plugins/AriaModules/src/javascript.hpp`（85 行 RAII） |
| 截图入口/状态机/base64/编译条件 | `src/CardinalCommon.hpp:26`；`override/Window.cpp:906-910` / `:706-747` / `:588-592` / `:45` |
| safeMode 陷阱 / osdialog stub | `plugin.cpp:273-275`；`src/custom/osdialog.cpp:28` |
| MCP 侧 OSC 层 / `read_live()` 局限 | `cardinal_mcp.py:88-166` / `:293-313`；`:561-576` |
| patch I/O / param 名解析 / `reserved` | `patchio.py:53/80/104`；`paramlib.py:801/812/834`；`:673-686` |
| **T7 扩展点** | `paramlib.py:355-356`（specs 只含 4 个 config 函数，需加 `configInput`/`configOutput`） |