# 人类操作 → 源码函数 映射

> 调查范围：`/home/lijia/Cardinal`（WSL）。**只读调查，未修改任何源码。**
> 所有路径区分 **override 版**（`src/override/` 或 `src/custom/`，**编译生效**）与 **Rack 版**（`src/Rack/`，可能被替换）。

---

## ⚠️ 零. 编译生效文件对照表（先看这个，否则全白查）

`src/Makefile:42-50` 的 `RACK_FILES` 把同名 Rack 源文件排除（`IGNORED_FILES`）后换成 override 版：

| 文件 | **实际编译的版本** | 依据 |
|---|---|---|
| `src/app/Browser.cpp` | **`src/custom/Browser.cpp`** | `src/Makefile:37`；`custom/Browser.cpp:28` 是 `#include "../src/app/Browser.cpp"` 的颜色 hack 壳 |
| `src/engine/Engine.cpp` | **`src/override/Engine.cpp`** | `src/Makefile:46` |
| `src/plugin/Model.cpp` | **`src/override/Model.cpp`** | `src/Makefile:47` |
| `src/app/ModuleWidget.cpp` | **`src/override/ModuleWidget.cpp`** | `src/Makefile:48` |
| `src/app/Scene.cpp` | **`src/override/Scene.cpp`** | `src/Makefile:50` |
| `src/plugin/plugin.cpp` | **`src/override/plugin.cpp`** | `src/Makefile:45` |
| `src/app/MenuBar.cpp` | **`src/override/MenuBar.cpp`** | 经 `Makefile.cardinal.mk:95` 的 `FILES_UI`，且 `src/Makefile:73` 忽略 Rack 版 |
| `src/window/Window.cpp` | **`src/override/Window.cpp`** | 经 `Makefile.cardinal.mk:96`，且 `src/Makefile:82` 忽略 Rack 版 |
| `src/app/RackWidget.cpp` | ⚠️ **Rack 原版，未被覆盖** | `src/Makefile` 中**没有** `RackWidget.cpp`，也无对应 override 文件 → **引Rack 版行号是安全的** |
| `src/app/ParamWidget.cpp` | ⚠️ **Rack 原版，未被覆盖** | 同上 |
| `src/engine/ParamQuantity.cpp` | ⚠️ **Rack 原版，未被覆盖** | 同上 |
| `src/CardinalCommon.cpp` | Cardinal 自己的（非 Rack） | OSC 层在这里 |

> `src/override/diffs/` 下有 `MenuBar.cpp.diff` / `Window.cpp.diff`，但这两个**不在** `RACK_FILES` 的 42-50 行里，走的是 `Makefile.cardinal.mk` 的 `FILES_UI` 通道。结论不变（override 版生效），但排查时容易漏。

---

## 重点回答：三档可编程性分类

### 🟢 第一档：零编译可做（现有 OSC handler 已足够，一个 Python 进程即可）

关键前提：**`src/CardinalCommon.cpp` 里已经有一套 OSC 只读探针**（代码块标记 `CARDINAL-MCP-READ-PROBES-BEGIN`，注释日期 **2026-10-19**，即今天新增）。注册表在 `src/CardinalCommon.cpp:1135-1145`：

| OSC 路径 | 签名 | Handler | 作用 |
|---|---|---|---|
| `/hello` | `""` | `CardinalCommon.cpp:696` | 连通性测试 |
| `/load` | `"b"` | `CardinalCommon.cpp:714` | **加载 .vcv 整份机架** |
| `/param` | `"hif"` | `CardinalCommon.cpp:760` | 写参数（原始值） |
| `/host-param` | `"if"` | `CardinalCommon.cpp:794` | 写宿主参数 |
| `/modules` | `""` | `CardinalCommon.cpp:395` | **列出所有模块 id + plugin + model** |
| `/param-get` | `"hi"` | `CardinalCommon.cpp:451` | **读回真实显示值**（走 `getDisplayValue`） |
| `/ports` | `"h"` | `CardinalCommon.cpp:505` | 读输入口连接数 + 各通道电压 |
| `/signal` | `""` | `CardinalCommon.cpp:583` | 全机架扫描「此刻真的有电压」的口 |
| `/light` | `"hi"` | `CardinalCommon.cpp:651` | 读 LED 亮度 |
| `/screenshot` | `"b"` | `CardinalCommon.cpp:821` | 截图 |

**⇒ 第一档能完整覆盖的**：
- 读机架现状：`/modules`（不用再爬 manifest）
- 写旋钮：`/param`
- 读旋钮真实物理量：`/param-get`
- 验证音频是否真的在跑：`/signal`、`/ports`
- **一次性搭好整个机架 + 全部连线 + 全部参数 + 音符数据：`/load` 直接灌一份 .vcv blob**

最后一条是本次调查最重要的结论：**你原本的目标（"用代码模拟前端一切操作，而不是每次重新生成文件"）其实已经能做到 90% —— 用 `/load` 灌 patch 文件即可，零编译。**

**第一档做不到的**：在**已加载的运行中机架**上做增量修改（加载会 `clear()` 整个引擎）；写「显示值」而非「原始值」。

### 🟡 第二档：需小改 C++（每个都是几十行的 handler 补全）

| 需求 | 需要加的东西 | 改动量 |
|---|---|---|
| **按显示值写参数**（写 `275ms` 而不是 `0.275`） | 加 `/param-set-display "hid"`，内部调`ParamQuantity::setDisplayValue()` | **极小**，核心函数已存在（见 §3） |
| 运行中加载 patch（不清空机架） | 加 `/merge`，内部调 `Engine::moduleFromJson()`（`override/Engine.cpp:916`，**已存在**） | 小 |
| 运行中新增模块 | 加 `/add-module "ss"`，内部走 `getModelFallback`→`createModule`→`Engine::addModule`（三步**全部已存在**，见 §1） | 小 |
| 移动模块到指定坐标 | 加 `/module-pos "hff"`，内部调 `setModulePosForce()`（`RackWidget.cpp:715`，**已存在**） | 小，但需拿到 `ModuleWidget`（Rack 版 `RackWidget::getModule(int64_t)`，`RackWidget.cpp:639`） |
| 读浏览器那份内存列表 | 加 `/models`，内部遍历 `plugin::plugins` → `model->models`（**数据已在内存**，见 §1） | 小 |

### 🔴 第三档：需较大改动

- **让参数写入走 history（可撤销）**：GUI 路径 `ParamWidget.cpp:46/78/308` 会push `history::ParamChange`；而 `Engine::setParamValue`（`override/Engine.cpp:1080`）**完全不 push**。要让它可撤销得改引擎语义，影响面大。
- **模拟拖拽的"鼠标手感"**（拖动阈值 `minDist`、框选、squeeze 布局）—— 这些是 UI 交互细节，编程复现无意义，应直接调落点函数。
- **QuickJS 绑定**：⚠️ **Cardinal 核心里没有 QuickJS 绑定**。`deps/QuickJS/` 只是 vendored 依赖，实际唯一使用者是 `plugins/AriaModules/src/javascript.hpp`。若要加 JS 绑定，等于从零写 binding 层，**归第三档**。

---

## 0. 速查表

| 人类动作 | 源码位置 | 能否编程调用 | 可撤销 |
|---|---|---|---|
| 右键机架空白→打开浏览器 | `Rack/src/app/RackWidget.cpp:179` `onButton` | 🟡 加 handler 调 `APP->scene->browser->show()` | ❌ |
| 浏览器搜索框打字 | `Rack/src/app/Browser.cpp:856` `onTextEdit` → `browser->search` | 🟡 加 handler 直接调 `modelDb.search()`（`Browser.cpp:751`） | ❌ |
| 点 Tags 筛选 | `Browser.cpp:928-946` `TagButton` 回调 | 🟡 设`browser->tagIds` + `refresh()` | ❌ |
| 点品牌/类型筛选 | `Browser.cpp:912` `hasVisibleModel` / `isModelVisible:623` | 🟡 同上 | ❌ |
| 选中模块（放机架） | `Browser.cpp:78` `chooseModel` | 🟡 三步都已存在，见下 | ✅ 是 |
| 拖动模块 | `override/ModuleWidget.cpp:495` `onDragMove` → `setModulePosForce` | 🟢 直接调 `RackWidget.cpp:715` | ✅ |
| 右键旋钮→菜单 | `Rack/src/app/ParamWidget.cpp:243` `createContextMenu` | 🔴 UI 菜单本身无需复现 | — |
| 旋钮拖动改值 | `ParamWidget.cpp:46/78` → `history::ParamChange` | 🟢 `/param`（但**不撤销**） | ⚠️ OSC 否 |
| 按钮点击 | `Module::configButton` `Module.hpp:165` | 🟢 `/param` 写 1.0 | ⚠️ 同上 |
| 开关切档 | `Module::configSwitch` `Module.hpp:153` | 🟢 `/param` 写 `min+i` | ⚠️ 同上 |
| **写显示值 275ms** | `ParamQuantity::setDisplayValue` `ParamQuantity.cpp:89` | 🟡 **函数已存在，只缺 OSC 入口** | ❌ |
| piano-roll 放音符 | rcm: `PatternData::setStepActive` `PatternData.hpp:28` | 🟡 经 `moduleFromJson` 灌 JSON | ❌ |
| 序列器 播放/停止 | rcm: `sequenceRunning` `PianoRollModule.cpp:30` | 🟡 同上 | ❌ |

---

## 1. 模块浏览器

### 1.1 右键菜单怎么定义

- **机架右键**：`Rack/src/app/RackWidget.cpp:179` `RackWidget::onButton` → 右键按下即 `APP->scene->browser->show()`（`:186`）。
  ⚠️ RackWidget **无 override**，行号有效。
- **模块右键**：`override/ModuleWidget.cpp:1133`调 `appendContextMenu(menu)`；`:1028` 调 `model->appendContextMenu(menu)`。

### 1.2 ⭐「Add module」子菜单怎么构造 —— 答案：**一次性全量枚举**，不是增量过滤

这是个**两套UI** 的设计，别混淆：

| 入口 | 实现 | 枚举方式 |
|---|---|---|
| 右键菜单里的 "Add module" | `override/Model.cpp:125` `Model::appendContextMenu(ui::Menu*, bool inBrowser)` | 展示单个模型的详情（Plugin/Version/Author/Tags/Manual/Donate/Favorite…），**Tags 展示在 `:152-157`** |
| 真正的浏览器面板 | `Rack/src/app/Browser.cpp`（经 `custom/Browser.cpp` 编译） | **全量枚举 + 客户端过滤** |

浏览器面板里，每个模型在 `modelDbInit()`（`Browser.cpp:46`）就被**全部塞进内存索引**：

```cpp
// Browser.cpp:46-75
static void modelDbInit() {
    modelDb = fuzzysearch::Database<plugin::Model*>();
    modelDb.setWeights({0.9f, 0.75f, 1.0f, 0.8f, 0.9f});   // brand,pluginName,name,desc,tagStr
    modelDb.setThreshold(0.5f);
    for (plugin::Plugin* plugin : plugin::plugins)          // 全量遍历
        for (plugin::Model* model : plugin->models) {
            std::string tagStr; // 拼接 tag::tagAliases[tagId]...
            std::vector<std::string> fields = {
                model->plugin->brand, model->plugin->name,
                model->name, model->description, tagStr,
            };
            modelDb.addEntry(model, fields);
        }
}
```

**⇒ 是一次性把所有模块枚举进内存**（不是按需增量）。

### 1.3 搜索过滤逻辑

- **搜索框事件**：`Browser.cpp:856` — `browser->search = string::trim(text)`。
- **实际检索**：`Browser.cpp:751` `modelDb.search(search)`（fuzzysearch）。
- **匹配字段**（权重顺序，`Browser.cpp:48`）：
  `0.9` **brand**、`0.75` **plugin name**、`1.0` **model name**、`0.8` **description**、`0.9` **tags 及其所有别名**
- 注意：**不匹配 slug**。想按 slug 搜外部得自己比对。
- 结果写进 `prefilteredModelScores`（`Browser.cpp:754`），空搜索时全部记 1 分（`Browser.cpp:695`）。

### 1.4 Tags 筛选 + tags 数据来源

**数据链路**（manifest → 内存，已逐跳确认）：

1. plugin manifest `plugin.json` 的 `"tags": [...]` 数组
2. → `override/Model.cpp:63` `json_object_get(rootJ, "tags")`
3. → `:69` `tag::findId(tag)` 把字符串 tag 映射成整数 id
4. → `:72-77` 去重后 `tagIds.push_back(tagId)`
5. → 存在 `plugin::Model::tagIds`（`Model.hpp`，`std::vector<int>`）
6. → 搜索索引与筛选都读它：`Browser.cpp:57`（索引）、`Browser.cpp:651`（筛选）

**筛选实现**：`Browser.cpp:623` `Browser::isModelVisible(plugin::Model*, const std::string& brand, std::set<int> tagIds, bool favorite)`

判定顺序（**注意每一条都是"否决"**）：
- `:625` `model->hidden` → 隐藏
- `:629` `settings::ModuleInfo::enabled == false` → 用户禁用了
- `:634` `!settings::isModuleWhitelisted(...)` → 库白名单外
- `:637-641` favorite 模式：`mi->favorite` 不成立
- `:643-647` **brand** 精确相等
- `:649-655` **tag**：要求 `model->tagIds` **包含全部** 选中 tag（AND，非 OR）

「该brand/tag 下还有没有可见项」：`Browser.cpp:660` `hasVisibleModel`（用于把无结果的筛选项置灰，调用点 `:912`）。
状态字段：`Browser.cpp:471` `search`、`:473` `tagIds`、`:478` `prefilteredModelScores`、`:479` `modelOrders`。
重算入口：`Browser.cpp:678` `refresh()`。

**没有** `browser::model` 这种独立数据结构—— `browser` 只是个 namespace（`Browser.cpp:40`），数据实体是 `plugin::Model`。

### 1.5 模块详情预览面板

`Browser.cpp:300-313`（ModelBox 的 tooltip/详情文本）：
- `:300` `model->name`、`:302` `model->plugin->brand`
- `:304-305` `model->description`
- `:309-313` `tag::getTag(tagId)` 逐个列出 tags

菜单版详情走 `Browser.cpp:336-338`：标签 + `model->appendContextMenu(menu, true)`（第二个参数 `inBrowser=true`，影响 Favorite 项的快捷键提示，见 `override/Model.cpp:199`）。

**⇒ 确实要读 manifest（description/tags）+ Model 自身字段，不需要读 param/port 定义。**

### 1.6 ⭐ 落点：选中模块后如何创建并放进机架

完整链条，每一跳都已核对：

```
Browser.cpp:261     ModelBox 点击 → chooseModel(model)
Browser.cpp:78      chooseModel()
  ├─ :88model->createModule()
  ├─ :89            APP->engine->addModule(module)          → override/Engine.cpp:737
  ├─ :93            model->createModuleWidget(module)
  ├─ :95-96         updateModuleOldPositions() → addModuleAtMouse()
  │                              → RackWidget.cpp:609
  │                                └─ setModulePosSqueeze/Nearest → setModulePosForce(:715)
  │                                   RackWidget.cpp:594addModule()
  ├─ :97            h->push(APP->scene->rack->getModuleDragAction())
  ├─ :100           moduleWidget->loadTemplate()
  ├─ :103-106       history::ModuleAdd（序列化以便 redo）
  ├─ :108           APP->history->push(h)                    ← 唯一真正可撤销的一步
  └─ :111           APP->scene->browser->hide()
```

注意：**GUI 路径并不经过 `getModelFallback`**。`plugin::getModelFallback`（`override/plugin.cpp:134`）只在 **JSON 加载路径**里用（`override/plugin.cpp:178` `modelFromJson` ← `override/Engine.cpp:1256`）。

**⇒ 编程新增模块的正确做法**（无需碰 GUI）：
```
plugin::getModelFallback(pluginSlug, modelSlug)   // override/plugin.cpp:134
  → model->createModule()
  → engine->addModule(module)                      // override/Engine.cpp:737（自动分配 id）
```
`Engine::addModule` 会自动生成 id（`override/Engine.cpp:746-750`），并派发 `AddEvent` / `SampleRateChangeEvent`。

### 1.7 ⭐⭐ 关键问题：模块列表是否已在内存？外部能否直接拿到？

**答：全部已在内存，且有两条现成路径。**

**证据 1** —— 全局静态索引：
```cpp
// Rack/src/app/Browser.cpp:43
static fuzzysearch::Database<plugin::Model*> modelDb;
```
`modelDbInit()`（`:46`）在启动时把 `plugin::plugins` × `plugin::models` 全部建成倒排索引，每条 entry 的 5 个字段就是 brand / pluginName / name / description / tags。**注意 `modelDb` 是 `static`，作用域仅限 Browser.cpp 内部，外部拿不到** —— 但底层数据 `plugin::plugins` / `plugin::models` 是全局的（`override/plugin.cpp`），**可以遍历**。

**证据 2** —— OSC 已暴露运行中机架：
`/modules`（`CardinalCommon.cpp:395`）已经在遍历 `context->engine->getModuleIds()` 并输出 `id:plugin|model`（`:425-436`），**注释里明确写了这正好和 .vcv 的 `plugin`/`model` 字段同构，外部无需再查映射表**。

**⇒ 结论**：
- 想拿「**已加载**的模块列表」→ **直接 `/modules`，零编译，已可用**。
- 想拿「**全部可安装**模块的完整清单（含 description/tags）」→ 现有 OSC **没有这个 handler**，但数据已在内存（`plugin::plugins`），**只需加一个几十行的 `/models` handler**，**不需要爬 manifest**。

---

## 2. 拖放与摆放

⚠️ `RackWidget.cpp` 与 `override/ModuleWidget.cpp` 的行号都有效（前者无override）。

### 2.1 拖放回调

| 函数 | 位置 | 作用 |
|---|---|---|
| `RackWidget::onButton` | `RackWidget.cpp:179` | 右键 → 打开浏览器 |
| `RackWidget::onDragStart` | `RackWidget.cpp:192` | 左键按下 → 开始**框选**（不是拖模块） |
| `RackWidget::onDragEnd` | `RackWidget.cpp:202` | 结束框选 |
| `RackWidget::onDragHover` | `RackWidget.cpp:207` | 更新 `internal->mousePos`、框选矩形 |
| `ModuleWidget::onDragStart` | `override/ModuleWidget.cpp:467` | 模块拖动起点 |
| `ModuleWidget::onDragEnd` | `override/ModuleWidget.cpp:480` | 结束，`:487` push `getModuleDragAction()` |
| `ModuleWidget::onDragMove` | `override/ModuleWidget.cpp:495` | **实际移动逻辑** |

`onDragMove` 关键细节（`:495-533`）：
- `:501-506` 有**拖动阈值** `minDist = RACK_GRID_WIDTH`，移动超过一格宽才开始拖（防误触）
- `:512-515` `pos.y -= RACK_GRID_HEIGHT / 2`（对齐机架行）
- `:518-521` 若模块被选中 → 整组选中模块一起动（`setSelectionPosNearest`）
- `:525-530` 三选一：`squeezeModules` 开关 → `setModulePosSqueeze`；按住 Ctrl → `setModulePosForce`；否则 `setModulePosNearest`

**⇒ 这些"鼠标手感"不该被编程复现，直接调落点函数即可。**

### 2.2 三个落点函数

| 函数 | 位置 | 语义 |
|---|---|---|
| `requestModulePos` | `RackWidget.cpp:668` | 尝试放到 `pos`，**若与任何模块相交则返回 false 且不放置** |
| `setModulePosNearest` | `RackWidget.cpp:702` | 用 `eachNearestGridPos`（`:684`）螺旋搜索最近的不冲突格 |
| `setModulePosForce` | `RackWidget.cpp:715` | **强制**放置：按 grid 重算，收集左右模块并让位（`:718-736`），无视冲突 |
| `addModuleAtMouse` | `RackWidget.cpp:609` | 以鼠标位置为中心落位（依赖 `internal->mousePos`，**编程时不可用**） |
| `addModule` | `RackWidget.cpp:594` | 真正挂到 `moduleContainer`，校验尺寸（≥0.5HP 宽、必须 3U 高） |
| `updateModuleOldPositions` | `RackWidget.cpp:890` | 记录旧位置，供 drag action 撤销 |
| `getModuleDragAction` | `RackWidget.cpp:897` | 生成可撤销的移动 action |

### 2.3 ⭐「把某模块移到 (x,y)」的可编程入口

**有，但没有现成对外接口。** 最干净的是 `setModulePosForce`：

```cpp
// Rack/src/app/RackWidget.cpp:715
void RackWidget::setModulePosForce(ModuleWidget* mw, math::Vec pos)
```
- `pos` 是**像素坐标**（内部会 `(pos - RACK_OFFSET) / RACK_GRID_SIZE` 取整，`:717`）
- 取 module widget：`RackWidget::getModule(int64_t moduleId)`，`RackWidget.cpp:639`（遍历 `moduleContainer` 比对 `mw->module->id`）

现成用例：`Engine::fromJson` 加载 .vcv 时就是这么摆的（`override/Engine.cpp:342`，`pos = pos.mult(RACK_GRID_SIZE).plus(RACK_OFFSET)`）。

**⇒ 需要新增一个 OSC handler（第二档）。注意 `APP->scene->rack` 是 UI 线程对象，跨线程调用需 `rack::contextSet()` 保护，参照 `CardinalCommon.cpp:411-415` 的写法。**

---

## 3. 旋钮 / 按钮 / 开关

⚠️ `ParamWidget.cpp` 与 `ParamQuantity.cpp` **均无 override**，Rack 版行号有效。

### 3.1 参数右键菜单

`ParamWidget::createContextMenu` — `Rack/src/app/ParamWidget.cpp:243`：
- `:251-252` `ParamLabel`（显示当前值）
- **开关分支** `:254-267`：按 `switchQuantity->labels` 逐档生成 `ParamValueItem`，带 CHECKMARK，`:261` 设 `value = minValue + i`
- **连续量分支** `:268-273`：`ParamField` 文本框（就是让你**输入数字**的那个）
- `:276-280` "Initialize" → `resetAction()`
- `:283-285` "Fine adjust"（Ctrl+drag）
- `:288-292` "Unmap"
- `:295` `appendContextMenu(menu)`（虚函数，`ParamWidget.hpp:45`）

`onButton` 在 `ParamWidget.cpp:208`。`resetAction()` 在 `:299`，`:308` push `history::ParamChange`。

### 3.2 参数值怎么写 —— ⚠️ 有两条路，语义不同

**GUI 路（走 history，可撤销）**：
`ParamWidget.cpp:46` / `:78` / `:308` → `history::ParamChange` → `APP->history->push(...)`

**引擎路（不走 history，不可撤销）**：
```cpp
// override/Engine.cpp:1080
void Engine::setParamValue(Module* module, int paramId, float value) {
    if (internal->smoothModule == module && internal->smoothParamId == paramId) {
        internal->smoothModule = NULL;   // 取消正在进行的平滑
        internal->smoothParamId = 0;
    }
    if (internal->remoteDetails != nullptr && internal->remoteDetails->connected)
        sendParamChangeToRemote(...);
    module->params[paramId].setValue(value);   // ← 直接写，无 history
}
```
`/param` OSC handler 走的就是这条（`CardinalCommon.cpp:785` `context->engine->setParamValue(...)`）。

**⇒ OSC 写参数不可撤销。** 要撤销得自己 push `history::ParamChange`，或走 `/load` 重载。

### 3.3 按钮（ButtonWidget / configButton）

`configButton` **不在** ParamWidget，而在 `Module` 上：
```cpp
// Rack/include/engine/Module.hpp:165
template <class TSwitchQuantity = SwitchQuantity>
TSwitchQuantity* configButton(int paramId, std::string name = "") {
    TSwitchQuantity* sq = configParam<TSwitchQuantity>(paramId, 0.f, 1.f, 0.f, name);
    sq->ParamQuantity::snapEnabled = true;
    sq->ParamQuantity::smoothEnabled = false;
    sq->ParamQuantity::randomizeEnabled = false;
    return sq;
}
```
**⇒ 按钮就是一个 0/1 的 param。外部直接 `/param` 写 `1.0` 即可，无需调用虚函数。**
「点击触发的是哪个虚函数」——**没有专门的虚函数**。按下动作最终也是写 param 值；变化被模块的 `onParamChange` 捕获。

### 3.4 开关（configSwitch）档位切换

```cpp
// Rack/include/engine/Module.hpp:153
template <class TSwitchQuantity = SwitchQuantity>
TSwitchQuantity* configSwitch(int paramId, float minValue, float maxValue,
                              float defaultValue, std::string name = "",
                              std::vector<std::string> labels = {}) { ... }
```
`SwitchQuantity` 定义在 `Rack/include/engine/ParamQuantity.hpp:121-125`（**不是独立文件**）：
```cpp
struct SwitchQuantity : ParamQuantity {
    std::vector<std::string> labels;
    std::string getDisplayValueString() override;
    void setDisplayValueString(std::string s) override;
};
```

⚠️ **没有 `enumValue` 这个函数**（你猜的名字）。实际有两个：

```cpp
// Rack/src/engine/ParamQuantity.cpp:212
void SwitchQuantity::setDisplayValueString(std::string s) {
    auto it = std::find_if(labels.begin(), labels.end(), [&](const std::string& a) {
        return string::lowercase(a) == string::lowercase(s);
    });
    if (it == labels.end()) return;
    int index = std::distance(labels.begin(), it);
    setImmediateValue(getMinValue() + index);
}
```
按**档位名**（大小写不敏感）切档。**这是编程侧最干净的开关入口。**

### 3.5 ⭐⭐ getDisplayValue / 换算 —— 函数名是 `setDisplayValue`，不是 `fromDisplayValue`

**全仓库 grep `fromDisplayValue` 结果为空 —— 该函数不存在。** 实际是这对：

```cpp
// Rack/src/engine/ParamQuantity.cpp:73   存储值 → 显示值
float ParamQuantity::getDisplayValue() {
    float v = getValue();
    if (displayBase == 0.f)      { /* Linear   */ }
    else if (displayBase < 0.f)  { v = std::log(v) / std::log(-displayBase); }  // Log
    else                         { v = std::pow(displayBase, v); }              // Exp
    return v * displayMultiplier + displayOffset;
}

// Rack/src/engine/ParamQuantity.cpp:89   显示值 → 存储值  ★你要的就是这个
void ParamQuantity::setDisplayValue(float displayValue) {
    float v = displayValue - displayOffset;
    if (displayMultiplier == 0.f) v = 0.f; else v /= displayMultiplier;
    if (displayBase == 0.f)      { }
    else if (displayBase < 0.f)  { v = std::pow(-displayBase, v); }
    else                         { v = std::log(v) / std::log(displayBase); }
    if (std::isnan(v)) return;
    setImmediateValue(v);      // 注意：是 setImmediate，不走平滑
}
```
声明在 `Rack/include/engine/ParamQuantity.hpp:97`（`getDisplayValue`）与 `.cpp:89`。

**⇒ 「把 275ms 写进去」的能力已经完全具备，只差一个 OSC 入口。**
新增 `/param-set-display "hid"` → `module->params[paramId].getParamQuantity()->setDisplayValue(v)`，**第二档，改动极小**。
（`/param-get` 已经用 `getDisplayValue` 了，见 `CardinalCommon.cpp:451` handler。）

---

## 4. 序列器 / 音符编辑

### 4.1 机架里带音符的模块（实测 `grep -l 'notes' plugins/*/plugin.json`）

含 `notes` 字样的 plugin.json：`BaconPlugs`、`Cardinal`、`DHE-Modules`、`EnigmaCurry`、`GlueTheGiant`、`GrandeModular`、`ML_modules`、`Venom`、`stoermelder-packone`。
本次按要求深入分析其中 2 个：`rcm-modules`（pianoroll）与 `Starsea`（MiniArranger）。
（`Cardinal/Notes`、`Cardinal/HostMIDI` 未在 `plugins/Cardinal/plugin.json` 的 slug 列表中见到—— 该列表含 `HostMIDI`、`HostMIDIGate` 等，**`Notes` 未找到**。）

### 4.2 rcm-pianoroll

⚠️ **你猜的结构是错的**：不是 `notes[]`，是 **`steps[]`**，且**没有 length 字段**（音符恒定 1 格）。

**C++ 结构**（`plugins/rcm-modules/src/PianoRoll/PatternData.hpp:51-68`）：
```cpp
struct Step {                  // :51
  int   pitch    = 0;
  float velocity = 0.f;
  bool  retrigger= false;
  bool  active   = false;
};
struct Measure {               // :58
  std::vector<Step> steps;     // ⚠️ 数组下标 == step 号
};
struct Pattern {               // :62
  std::vector<Measure> measures;
  int numberOfMeasures = 1;
  int beatsPerMeasure  = 4;
  int divisionsPerBeat = 4;    // :67
};
std::vector<Pattern> patterns; // :70
```

**⚠️ JSON 键名与 C++ 字段名不一致 —— 这是最容易踩的坑**：
序列化时数组键叫 **`"notes"`**，读的却是 `steps`：
```cpp
// plugins/rcm-modules/src/PianoRoll/PatternData.cpp:193 dataToJson
json_object_set_new(patternJ, "numberOfMeasures", ...);   // :215
json_object_set_new(patternJ, "beatsPerMeasure", ...);    // :216
json_object_set_new(patternJ, "divisionsPerBeat", ...);   // :217
json_t *measuresJ = json_array();                          // :219
for (const auto& measure : pattern.measures) {
    json_t *notesJ = json_array();                         // :222  ← 键名 notes
    for (const auto& step : measure.steps) {
        json_object_set_new(noteJ, "pitch",     json_integer(step.pitch));      // :227
        json_object_set_new(noteJ, "velocity",  json_real(step.velocity));       // :228
        json_object_set_new(noteJ, "retrigger", json_boolean(step.retrigger));   // :229
        json_object_set_new(noteJ, "active",    json_boolean(step.active));      // :230
        json_array_append_new(notesJ, noteJ);
    }
    json_object_set_new(measureJ, "notes", notesJ);       // :235
}
```
反序列化 `PatternData::dataFromJson`（`PatternData.cpp:246`）读 `"measures"`（`:271`）→ `"notes"`（`:281`）。

**⇒ JSON 实际路径：`patterns[i].measures[j].notes[k]`，其中 `k` 就是 step 号，且 `notes` 数组长度 = 每小节格数。**

**小节/拍/步换算**：
- 每小节格数 = `getStepsPerMeasure(pattern)` = `beatsPerMeasure * divisionsPerBeat`（`PatternData.cpp:60`）
- 默认 4 拍 × 4 分 = **每小节 16 格**
- `PatternData.hpp:66` `divisionsPerBeat = 4`
- **没有跨 pattern 的绝对 step 索引**，必须 (pattern, measure, step) 三元组定位

**播放开关字段**（`plugins/rcm-modules/src/PianoRoll/PianoRollModule.cpp`）：
```cpp
json_object_set_new(rootJ, "sequenceRunning", json_boolean(transport.isRunning()));  // :30
```
其他顶层字段：`"patterns"`(:26)、`"currentPattern"`(:27)、`"currentStep"`(:28)、`"clockDelay"`(:29)、`"lowestDisplayNote"`(:31)、`"notesToShow"`(:32)、`"currentMeasure"`(:33)、`"driverMode"`(:34)。
读回：`sequenceRunning` → `transport.setRun()`（`:62-64`）。

**⭐ 有现成的可编程方法**（不用只改 JSON）——`PatternData.hpp:27-40`：
```
toggleStepActive(pattern, measure, step)          :27
setStepActive(pattern, measure, step, active)     :28
setStepPitch(pattern, measure, step, pitch)       :29
toggleStepRetrigger / setStepRetrigger           :30-31
setStepVelocity / increaseStepVelocityTo         :32-33
isStepActive / isStepRetriggered                 :35-36
getStepVelocity / getStepPitch                   :37-38
adjustVelocity(pattern, measure, step, delta)    :40
```
且**自带撤销**：`PatternData::PatternAction`（`PatternData.hpp:81`，继承 `rack::history::ModuleAction`），实现在 `PatternData.cpp:14-45`（`copyPatternData` 做快照）。
**改一个音符 = 只改 `step` 的 `active`/`pitch`/`velocity`/`retrigger` 四个字段之一**（长度不可改）。

### 4.3 Starsea-MiniArranger

⚠️ 结构与 rcm **完全不同**，且它是 Cardinal 自研的（`ArrangerData.hpp:1-20` 有中文设计说明，日期 2026-09-21）。

**C++ 结构**（`plugins/Starsea/src/ArrangerData.hpp`）：
```cpp
struct MaNote {              // :54
  int   step     = 0;        // :57  起始格
  int   length   = 1;        // :58  ★有length！rcm 缺的就是这个
  int   pitch    = 60;       // :59  MIDI 0..127，输出转 V/Oct：(pitch-60)/12
  float velocity = 0.8f;     // :60  0..1
};
struct MaTrack {             // :112
  std::string         label;      // :113
  bool                mute = false;  // :114
  int                 measures = 4;    // :116  本轨小节数（整数，不是数组！）
  std::vector<MaNote> notes;          // :117  始终按 step 排序
};
```
**⇒ JSON 路径是 `tracks[].notes[]`，`measures` 是个整数标量 —— 不是 `patterns[0].measures[].notes[]`。**

序列化（`ArrangerData.hpp:83-88` `MaNote::toJson`）：`"step"`、`"length"`、`"pitch"`、`"velocity"`。
反序列化：`:90-105` `MaNote::fromJson`，末尾 `:104` 调 `clampValues()`（`:67-76`）。
轨道级（`:186-192`）：`"measures"` 整数(`:187`)、`"notes"` 数组(`:192`)。

**步单位换算**（常量 `:35-41`）：
```
MA_STEPS_PER_MEASURE = 16   // 4/4 下 16 格 = 4 拍 × 4 格   :37
MA_MAX_MEASURES      = 64   // 每轨最长小节数                :36
MA_MAX_LENGTH        = 16   // 单音符最长 16 格              :38
MA_TRACKS            = 4    // 主模块自带轨数                :35
MA_PITCH_MIN/MAX     = 12 / 108                            :39-40
```
每四分音符格数：`ArrangerData.hpp:227` `float stepsPerQuarter = 4.f;`（16分=4格），`:238` 同样默认 4.f。

**排序/发声判定**：
- `:62-67` `operator<` — 先按 `step`，再按 `pitch`
- `:78-80` `soundingAt(s)` → `(s >= step) && (s < step + length)`
- `:129` `notes` 插入后 `std::stable_sort`
- `:137-138` / `:149-151` `indexSounding` 反查

**播放/运行开关字段**：⚠️ **在 `ArrangerData.hpp` 里未找到 `sequenceRunning` / `playing`**（该文件只管数据模型，传输状态在 `MiniArranger.cpp` / `Transport.hpp`）。**未找到确切字段名，不猜。**

**⭐ 有现成的可编程方法**（比 rcm 更完整）：
- `:160-166` 新增音符（`addNote`，含 `defaultPitch`）
- `:168-172` 查/改指定 step 的音符
- `:176-180` 直接 `notes.push_back(note)`
- `:135-152` `removeNote` / 批量清除某step 发声音符
- `:116-133` 小节数设置与重排

**编辑一个音符需动的字段**：`step`（起始格）、`length`（时值）、`pitch`、`velocity`。

### 4.4 ⭐ 结论：编程改音符的两条路

| 方式 | 路径 | 优点 | 缺点 |
|---|---|---|---|
| **A. 灌 JSON**（推荐，跨模块通用） | `Engine::moduleFromJson(Module*, json_t*)` — **`override/Engine.cpp:916`（已存在）**；整机架用 `Engine::fromJson` `override/Engine.cpp:1241` | 不需要认识任何 C++ 类；`/load` OSC **今天就能用**（整机架）；两个模块格式不同也能分别处理 | 覆盖式（会先 `reset()` 整个 pattern，见 `PatternData.cpp:248`）；不撤销 |
| **B. 调C++ 类方法** | rcm: `setStepActive/setStepPitch/...`（`PatternData.hpp:28-33`）；Starsea: `addNote`（`ArrangerData.hpp:161`） | 精确、可撤销（rcm 有 `PatternAction`） | **需要新写 C++ handler**（第二/三档），因为 OSC 层没有任何 module-specific 入口 |

**⇒ 综合建议：用 A。** `moduleFromJson` 已是 public 引擎 API，加一个 `/module-json "hb"`（传 moduleId + json blob，内部 `moduleToJson` 取出旧 JSON → 改音符 → `moduleFromJson` 写回）即可**通用地**编辑任意模块的音符，无需为每个插件写专用代码。这是性价比最高的一条路。

---

## 5. 明确不可编程模拟的操作

| 操作 | 原因 |
|---|---|
| **真正的鼠标拖拽手感** | `override/ModuleWidget.cpp:501-506` 的拖动阈值、框选、Ctrl 多选整组移动 —— 是交互细节，编程应直接调 `setModulePosForce`（`RackWidget.cpp:715`） |
| **浏览器 UI 的实时打字/滚动** | `Browser.cpp:856` `onTextEdit` 绑定的是 `TextField` 事件；编程只需设 `browser->search` 再 `refresh()`（`:678`） |
| **旋钮右键菜单的弹出与点击** | `ParamWidget.cpp:243` 产出的是 `ui::Menu` 控件树，脱离 `Widget` 事件循环无意义。**改为直接调底层 `ParamQuantity` 方法** |
| **QuickJS 脚本层** | ⚠️ **Cardinal 核心无QuickJS 绑定**。`deps/QuickJS/` 是 vendored 依赖，唯一使用者是 `plugins/AriaModules/src/javascript.hpp`。从零加绑定 = 第三档 |
| **参数写入的撤销** | `Engine::setParamValue`（`override/Engine.cpp:1080`）**不 push history**，OSC `/param` 因此不可撤销。要撤销只能重载 `/load` |

---

## 附：本次调查的 5 条最重要发现

1. **浏览器全量数据已在内存**：`Browser.cpp:43` 的 `static modelDb`（`modelDbInit()` `:46`）在启动时把 `plugin::plugins` × `plugin->models` 全部建成 5 字段模糊索引。**不需要爬 manifest**，加一个 `/models` handler 即可全量导出。但 `modelDb` 是 `static`，外部只能遍历 `plugin::plugins`。

2. **「写 275ms」的能力已经存在，只差 OSC 入口**：函数真名是 **`ParamQuantity::setDisplayValue`**（`Rack/src/engine/ParamQuantity.cpp:89`），**不是 `fromDisplayValue`**（全仓库不存在该名字）。`getDisplayValue` 在 `:73`。

3. **你猜的两个结构都错了**：
   - rcm-pianoroll 是 `patterns[].measures[].notes[]` 但 C++ 侧叫 **`steps[]`**，`notes` 数组**下标即 step 号**，且**没有 length 字段**（`PatternData.hpp:51-56`）。
   - Starsea 是 **`tracks[].notes[]`**（多轨），`measures` 是**整数标量**（`ArrangerData.hpp:116`），**有** `length` 字段（`:58`）。

4. **`override/` 之外还有第三个替换点**：`src/custom/Browser.cpp:28` 通过 `#include "../src/app/Browser.cpp"` 把 Rack 的浏览器整个换掉。排查时只看 `override/` 会漏掉它。另外 `MenuBar.cpp`/`Window.cpp` 走 `Makefile.cardinal.mk:95-96` 的 `FILES_UI` 通道，不在 `RACK_FILES` 里。而 **`RackWidget.cpp` / `ParamWidget.cpp` / `ParamQuantity.cpp` 完全没有 override** —— 这三个引 Rack 版行号是安全的。

5. **`Engine::moduleFromJson`（`override/Engine.cpp:916`）是编辑音符的通用捷径**：它已存在且是 public API，配合 `/load` 可以**不加任何 C++ 代码**就完成「搭机架 + 放音符」；若要运行中增量改，加一个 `/module-json` handler 即可**通用支持任意插件**的音符/参数/端口数据，不必为每个插件写专用绑定。

---

*调查完成，未修改任何源码文件。*