// ---------------------------------------------------------------------------
// ★ 2026-10-20 新增：QuickJS 绑定 —— Cardinal 进程内 JS 执行
//
// 【为什么】（10-19 战略对标结论）
//   Unity / UE / Blender / Godot 的 MCP **10/10 都有「宿主内执行任意代码」工具**
//   （Roslyn 内存编译 / execute_blender_code / editor_run_python / execute_script）。
//   探针是「一次性清单」会过时，JS 是「无限能力」会生长——这是行业标配。
//   且 liblo 的 string 接收通路不可靠（B5 教训），任意文本类输入（JS 源码、
//   模块 JSON）走 OSC 参数是死路 ⇒ JS 绑定同时是协议短板的解药。
//
// 【安全模型】（lethal trifecta：私数据 + 不可信内容 + 外发能力 = 窃盗条件）
//   1. **默认 off**：env CARDINAL_JS_MODE=off|read|write，默认 off。off 时端点
//      直接拒绝并提示。李不显式开启就没有这个能力。
//   2. **绝不初始化 quickjs-libc**（JS_NewContext 裸上下文，不调 js_std_loop/
//      js_init_module_os）⇒ JS 里**没有 std/os/script 模块** ⇒ 没有
//      exec/waitpid/kill/pipe ⇒ **任意命令执行这条路从根上不存在**。
//   3. **指令预算**：JS_SetInterruptHandler 计数，超 2000 万指令中断
//      （防死循环卡 UI 线程；handler 在 UI 线程同步跑，预算=界面冻结预算）。
//   4. **API 分级**：read 模式只读（modules/getParam/ports/signal/cables/
//      transport/moduleJson）；write 模式才追加 setParam/setDisplayValue/
//      moduleFromJson/addModule/cableAdd/undo/redo。
//   5. **无文件/网络 API**：不给 JS 任何 fs/net 能力（ Cardinal 数据全走 API）。
//
// 【源码依据】（2026-10-20 WSL 树实测）
//   链接：src/Makefile.cardinal.mk:153 RACK_EXTRA_LIBS += libquickjs.a
//   头文件：src/Rack/dep/include/quickjs.h（相对 src/ 的稳 include 路径）
//   RAII 范本：plugins/AriaModules/src/javascript.hpp（WTFPL，可抄）
//   惯例：每次 eval 新建 runtime（AriaModules 注释："basically instant"，
//         无状态污染）——本实现沿用，budget 挂在 runtime 上。
//
// 【调用约定】
//   /osc-js-run "i" = 脚本索引（1-based，先用 /osc-js-list 查）。
//   脚本被包成 `globalThis.result = (function(){ <脚本> })();`，所以脚本用
//   `return` 交结果（不要自己赋 globalThis.result——会被 undefined 覆盖）。
//   墙钟超预算如实回 `budget-exceeded ms=N`；其余异常回 `error: ...`。
// ---------------------------------------------------------------------------

// 相对 src/ 的稳路径（ CardinalCommon.cpp 在 src/ 下；勿用尖括号——include
// 路径里没有 quickjs.h 的保证，相对路径一定找得到）
#include "Rack/dep/include/quickjs.h"
#include <dirent.h>
#include <stdio.h>
#include <time.h>
// ⚠️ 不用 <fstream>/<sstream>：实测在本 inc 的插入位置（CardinalCommon.cpp
// 中部）会炸 ios_base 未声明（mingw C++ 库内部前置状态问题）；FILE* 零风险。

// JS API 回调拿 self（Initializer*）的通道：JS C 函数签名里没有 self 参数。
// OSC handler 在 GUI 版是 UI 线程串行执行的 ⇒ eval 期间独占，前后置空即安全。
static void* g_osc_js_self = NULL;

// 执行预算：挂在 JSRuntime 上，超限中断（返回 1 = 中断）。
//
// 【血泪·为什么用墙钟而不是指令数】2026-10-20 运行级实测：原先只数指令、
// 上限 2000 万，结果死循环脚本 40 秒没被打断、UI 线程被永久卡死。根因是
// 数量级错得离谱——quickjs 只在 `interrupt_counter`（JS_INTERRUPT_COUNTER_INIT
// = 10000，见 deps/QuickJS/quickjs.c:316）递减到 0 时才调一次 handler，即
// handler 每 ~10000 条指令才被调一次；2000 万次 handler 调用 ≈ 2000 亿条指令。
//
// 【更根本的问题：单位错了】安全目标是「不能卡死 UI 线程」，量纲必须是时间。
// 同一个指令数在真机（原生 Windows）和 WINE+xvfb 下时间含义差几个数量级，
// 按指令数定阈值等于把「快机器更早被打断」和「慢机器可能卡很久」都留给了运气。
// ⇒ 主判据用墙钟毫秒（env CARDINAL_JS_BUDGET_MS 覆盖），指令数只留作兜底。
struct OscJsBudget {
    clock_t start;    // 起跑时刻
    double limitMs;   // 墙钟上限（毫秒）
    long counter;     // handler 调用次数（兜底判据）
    long counterLimit;
};

static int oscJsInterrupt(JSRuntime* rt, void* opaque)
{
    (void) rt;
    OscJsBudget* const b = static_cast<OscJsBudget*>(opaque);
    const double elapsedMs = (double)(clock() - b->start) * 1000.0 / (double) CLOCKS_PER_SEC;
    if (elapsedMs > b->limitMs)
        return 1;
    if (++b->counter > b->counterLimit)   // 兜底：时钟异常时的硬上限
        return 1;
    return 0;
}

// ---- JS 侧 API 的 C 实现 ---------------------------------------------------
// 约定：每个 C 函数从 this_val 之后的 argv 取参，返回 JSValue。
// 出错返回 JS_EXCEPTION（会冒泡成 JS 异常，如实回传）。

static JSValue jsApiModules(JSContext* ctx, JSValueConst this_val, int argc, JSValueConst* argv)
{
    (void) this_val; (void) argc; (void) argv;
    CardinalBasePlugin* const plugin = static_cast<Initializer*>(g_osc_js_self)->remotePluginInstance;
    if (plugin == nullptr)
        return JS_ThrowInternalError(ctx, "no plugin");
    CardinalPluginContext* const context = plugin->context;
    std::string out;
    const std::vector<int64_t> ids = context->engine->getModuleIds();
    for (int64_t id : ids)
    {
        rack::engine::Module* const module = context->engine->getModule(id);
        if (module == NULL)
            continue;
        rack::plugin::Model* const model = module->getModel();
        if (model == NULL)
            continue;
        if (!out.empty())
            out += ",";
        out += std::to_string(id) + ":" +
               (model->plugin != NULL ? model->plugin->slug : std::string("?")) + "|" + model->slug;
    }
    return JS_NewStringLen(ctx, out.c_str(), out.size());
}

static JSValue jsApiGetParam(JSContext* ctx, JSValueConst this_val, int argc, JSValueConst* argv)
{
    (void) this_val;
    if (argc < 2)
        return JS_ThrowTypeError(ctx, "getParam(id, param) needs 2 args");
    int64_t mid = 0;
    int32_t pid = 0;
    if (JS_ToInt64(ctx, &mid, argv[0]) != 0 || JS_ToInt32(ctx, &pid, argv[1]) != 0)
        return JS_ThrowTypeError(ctx, "getParam: bad number args");
    CardinalBasePlugin* const plugin = static_cast<Initializer*>(g_osc_js_self)->remotePluginInstance;
    if (plugin == nullptr)
        return JS_ThrowInternalError(ctx, "no plugin");
    rack::engine::Module* const module = plugin->context->engine->getModule(mid);
    if (module == NULL)
        return JS_ThrowInternalError(ctx, "no module");
    rack::engine::ParamQuantity* const pq = module->getParamQuantity(pid);
    if (pq == NULL)
        return JS_ThrowInternalError(ctx, "no param");
    const std::string s = fmtB((double) pq->getDisplayValue());
    return JS_NewStringLen(ctx, s.c_str(), s.size());
}

static JSValue jsApiPorts(JSContext* ctx, JSValueConst this_val, int argc, JSValueConst* argv)
{
    (void) this_val;
    if (argc < 1)
        return JS_ThrowTypeError(ctx, "ports(id) needs 1 arg");
    int64_t mid = 0;
    if (JS_ToInt64(ctx, &mid, argv[0]) != 0)
        return JS_ThrowTypeError(ctx, "ports: bad id");
    CardinalBasePlugin* const plugin = static_cast<Initializer*>(g_osc_js_self)->remotePluginInstance;
    if (plugin == nullptr)
        return JS_ThrowInternalError(ctx, "no plugin");
    rack::engine::Module* const module = plugin->context->engine->getModule(mid);
    if (module == NULL)
        return JS_ThrowInternalError(ctx, "no module");
    std::string out;
    for (int i = 0; i < module->getNumInputs(); ++i)
    {
        rack::engine::Input& port = module->inputs[i];
        if (!out.empty()) out += "|";
        out += "in:" + std::to_string(i) + ":" + std::to_string(port.getChannels());
        for (int ch = 0; ch < 4; ++ch)
            out += ":" + fmtB(port.getPolyVoltage(ch));
    }
    for (int i = 0; i < module->getNumOutputs(); ++i)
    {
        rack::engine::Output& port = module->outputs[i];
        if (!out.empty()) out += "|";
        out += "out:" + std::to_string(i) + ":" + std::to_string(port.getChannels());
        for (int ch = 0; ch < 4; ++ch)
            out += ":" + fmtB(port.getPolyVoltage(ch));
    }
    return JS_NewStringLen(ctx, out.c_str(), out.size());
}

static JSValue jsApiCables(JSContext* ctx, JSValueConst this_val, int argc, JSValueConst* argv)
{
    (void) this_val; (void) argc; (void) argv;
    CardinalBasePlugin* const plugin = static_cast<Initializer*>(g_osc_js_self)->remotePluginInstance;
    if (plugin == nullptr)
        return JS_ThrowInternalError(ctx, "no plugin");
    std::string out;
    const std::vector<int64_t> ids = plugin->context->engine->getCableIds();
    for (int64_t id : ids)
    {
        rack::engine::Cable* const c = plugin->context->engine->getCable(id);
        if (c == NULL) continue;
        if (!out.empty()) out += ",";
        out += std::to_string(id) + ":"
             + std::to_string(c->inputModule != NULL ? c->inputModule->id : -1) + ":"
             + std::to_string(c->inputId) + ":"
             + std::to_string(c->outputModule != NULL ? c->outputModule->id : -1) + ":"
             + std::to_string(c->outputId);
    }
    if (out.empty()) out = "none";
    return JS_NewStringLen(ctx, out.c_str(), out.size());
}

static JSValue jsApiTransport(JSContext* ctx, JSValueConst this_val, int argc, JSValueConst* argv)
{
    (void) this_val; (void) argc; (void) argv;
    CardinalBasePlugin* const plugin = static_cast<Initializer*>(g_osc_js_self)->remotePluginInstance;
    if (plugin == nullptr || plugin->context == nullptr)
        return JS_ThrowInternalError(ctx, "no plugin");
    const CardinalPluginContext* const context = plugin->context;
    std::string payload = std::string("playing=") + (context->playing ? "1" : "0")
        + "|bar=" + std::to_string(context->bar)
        + "|beat=" + std::to_string(context->beat)
        + "|bpm=" + fmtB(context->beatsPerMinute)
        + "|tick=" + fmtB(context->tick)
        + "|bypassed=" + (context->bypassed ? "1" : "0");
    return JS_NewStringLen(ctx, payload.c_str(), payload.size());
}

static JSValue jsApiModuleJson(JSContext* ctx, JSValueConst this_val, int argc, JSValueConst* argv)
{
    (void) this_val;
    if (argc < 1)
        return JS_ThrowTypeError(ctx, "moduleJson(id) needs 1 arg");
    int64_t mid = 0;
    if (JS_ToInt64(ctx, &mid, argv[0]) != 0)
        return JS_ThrowTypeError(ctx, "moduleJson: bad id");
    CardinalBasePlugin* const plugin = static_cast<Initializer*>(g_osc_js_self)->remotePluginInstance;
    if (plugin == nullptr)
        return JS_ThrowInternalError(ctx, "no plugin");
    rack::engine::Module* const module = plugin->context->engine->getModule(mid);
    if (module == NULL)
        return JS_ThrowInternalError(ctx, "no module");
    std::string s = oscJsonDumpsCompact(module->toJson());
    return JS_NewStringLen(ctx, s.c_str(), s.size());
}

// ---- write 模式 API ----

static JSValue jsApiSetDisplayValue(JSContext* ctx, JSValueConst this_val, int argc, JSValueConst* argv)
{
    (void) this_val;
    if (argc < 3)
        return JS_ThrowTypeError(ctx, "setDisplayValue(id, param, value) needs 3 args");
    int64_t mid = 0; int32_t pid = 0; double dv = 0;
    if (JS_ToInt64(ctx, &mid, argv[0]) != 0 || JS_ToInt32(ctx, &pid, argv[1]) != 0
        || JS_ToFloat64(ctx, &dv, argv[2]) != 0)
        return JS_ThrowTypeError(ctx, "setDisplayValue: bad args");
    CardinalBasePlugin* const plugin = static_cast<Initializer*>(g_osc_js_self)->remotePluginInstance;
    if (plugin == nullptr)
        return JS_ThrowInternalError(ctx, "no plugin");
    rack::engine::Module* const module = plugin->context->engine->getModule(mid);
    rack::engine::ParamQuantity* const pq = module != NULL ? module->getParamQuantity(pid) : NULL;
    if (pq == NULL)
        return JS_ThrowInternalError(ctx, "no module/param");
    const float oldValue = pq->getValue();
    pq->setDisplayValue((float) dv);
    const float newValue = pq->getValue();
    rack::history::ParamChange* a = new rack::history::ParamChange;
    a->moduleId = mid; a->paramId = pid; a->oldValue = oldValue; a->newValue = newValue;
    APP->history->push(a);
    const std::string s = std::string("old=") + fmtB(oldValue) + " new=" + fmtB(newValue);
    return JS_NewStringLen(ctx, s.c_str(), s.size());
}

static JSValue jsApiModuleFromJson(JSContext* ctx, JSValueConst this_val, int argc, JSValueConst* argv)
{
    (void) this_val;
    if (argc < 2)
        return JS_ThrowTypeError(ctx, "moduleFromJson(id, json) needs 2 args");
    int64_t mid = 0;
    if (JS_ToInt64(ctx, &mid, argv[0]) != 0)
        return JS_ThrowTypeError(ctx, "moduleFromJson: bad id");
    const char* js = JS_ToCString(ctx, argv[1]);
    if (js == NULL)
        return JS_ThrowTypeError(ctx, "moduleFromJson: bad json string");
    const std::string jsonStr(js);
    JS_FreeCString(ctx, js);
    CardinalBasePlugin* const plugin = static_cast<Initializer*>(g_osc_js_self)->remotePluginInstance;
    if (plugin == nullptr)
        return JS_ThrowInternalError(ctx, "no plugin");
    rack::engine::Module* const module = plugin->context->engine->getModule(mid);
    if (module == NULL)
        return JS_ThrowInternalError(ctx, "no module");
    json_error_t err;
    json_t* rootJ = json_loads(jsonStr.c_str(), 0, &err);
    if (rootJ == NULL)
        return JS_ThrowInternalError(ctx, "json parse failed");
    APP->engine->moduleFromJson(module, rootJ);
    json_decref(rootJ);
    return JS_NewStringLen(ctx, "ok", 2);
}

static JSValue jsApiAddModule(JSContext* ctx, JSValueConst this_val, int argc, JSValueConst* argv)
{
    (void) this_val;
    if (argc < 3)
        return JS_ThrowTypeError(ctx, "addModule('plugin|model', x, y) needs 3 args");
    const char* slugC = JS_ToCString(ctx, argv[0]);
    if (slugC == NULL)
        return JS_ThrowTypeError(ctx, "addModule: bad slug");
    const std::string slugPair(slugC);
    JS_FreeCString(ctx, slugC);
    int32_t px = 0, py = 0;
    if (JS_ToInt32(ctx, &px, argv[1]) != 0 || JS_ToInt32(ctx, &py, argv[2]) != 0)
        return JS_ThrowTypeError(ctx, "addModule: bad coords");
    std::string pluginSlug, modelSlug;
    const size_t bar = slugPair.find('|');
    if (bar != std::string::npos)
    {
        pluginSlug = slugPair.substr(0, bar);
        modelSlug = slugPair.substr(bar + 1);
    }
    rack::plugin::Model* model = NULL;
    if (!pluginSlug.empty())
    {
        rack::plugin::Plugin* const p = ::rack::plugin::getPlugin(pluginSlug);
        model = p != NULL ? p->getModel(modelSlug) : NULL;
    }
    if (model == NULL)
        return JS_ThrowInternalError(ctx, "no model (need plugin|model full slug)");
    rack::history::ModuleAdd* a = new rack::history::ModuleAdd;
    a->model = model;
    a->pos = rack::math::Vec(px, py);
    APP->history->push(a);
    return JS_NewStringLen(ctx, "ok", 2);
}

static JSValue jsApiCableAdd(JSContext* ctx, JSValueConst this_val, int argc, JSValueConst* argv)
{
    (void) this_val;
    if (argc < 4)
        return JS_ThrowTypeError(ctx, "cableAdd(outMod, outPort, inMod, inPort) needs 4 args");
    int64_t om = 0, im = 0; int32_t op = 0, ip = 0;
    if (JS_ToInt64(ctx, &om, argv[0]) != 0 || JS_ToInt32(ctx, &op, argv[1]) != 0
        || JS_ToInt64(ctx, &im, argv[2]) != 0 || JS_ToInt32(ctx, &ip, argv[3]) != 0)
        return JS_ThrowTypeError(ctx, "cableAdd: bad args");
    CardinalBasePlugin* const plugin = static_cast<Initializer*>(g_osc_js_self)->remotePluginInstance;
    if (plugin == nullptr)
        return JS_ThrowInternalError(ctx, "no plugin");
    CardinalPluginContext* const context = plugin->context;
    rack::engine::Module* const inM = context->engine->getModule(im);
    if (inM == NULL)
        return JS_ThrowInternalError(ctx, "no input module");
    int replaced = 0;
    const std::vector<int64_t> ids = context->engine->getCableIds();
    for (int64_t id : ids)
    {
        rack::engine::Cable* const c = context->engine->getCable(id);
        if (c != NULL && c->inputModule == inM && c->inputId == ip)
        {
            rack::history::CableRemove* r = new rack::history::CableRemove;
            r->cableId = id;
            APP->history->push(r);
            ++replaced;
        }
    }
    rack::history::CableAdd* a = new rack::history::CableAdd;
    a->cableId = -1;
    a->inputModuleId = im;
    a->inputId = ip;
    a->outputModuleId = om;
    a->outputId = op;
    APP->history->push(a);
    const std::string s = std::string("ok replaced=") + std::to_string(replaced);
    return JS_NewStringLen(ctx, s.c_str(), s.size());
}

static JSValue jsApiUndo(JSContext* ctx, JSValueConst this_val, int argc, JSValueConst* argv)
{
    (void) this_val; (void) argc; (void) argv;
    const std::string s = APP->history->canUndo() ? APP->history->getUndoName() : std::string("nothing");
    if (s != "nothing")
        APP->history->undo();
    return JS_NewStringLen(ctx, s.c_str(), s.size());
}

static JSValue jsApiRedo(JSContext* ctx, JSValueConst this_val, int argc, JSValueConst* argv)
{
    (void) this_val; (void) argc; (void) argv;
    const std::string s = APP->history->canRedo() ? APP->history->getRedoName() : std::string("nothing");
    if (s != "nothing")
        APP->history->redo();
    return JS_NewStringLen(ctx, s.c_str(), s.size());
}

// ---- 注册表 ----

typedef JSValue (*OscJsFn)(JSContext*, JSValueConst, int, JSValueConst*);

static void oscJsRegisterApi(JSContext* ctx, bool writeMode)
{
    JSValue global = JS_GetGlobalObject(ctx);
    JSValue api = JS_NewObject(ctx);

    struct { const char* name; OscJsFn fn; } readFns[] = {
        {"modules", jsApiModules},
        {"getParam", jsApiGetParam},
        {"ports", jsApiPorts},
        {"cables", jsApiCables},
        {"transport", jsApiTransport},
        {"moduleJson", jsApiModuleJson},
    };
    for (const auto& e : readFns)
        JS_SetPropertyStr(ctx, api, e.name, JS_NewCFunction(ctx, e.fn, e.name, 8));

    if (writeMode)
    {
        struct { const char* name; OscJsFn fn; } writeFns[] = {
            {"setDisplayValue", jsApiSetDisplayValue},
            {"moduleFromJson", jsApiModuleFromJson},
            {"addModule", jsApiAddModule},
            {"cableAdd", jsApiCableAdd},
            {"undo", jsApiUndo},
            {"redo", jsApiRedo},
        };
        for (const auto& e : writeFns)
            JS_SetPropertyStr(ctx, api, e.name, JS_NewCFunction(ctx, e.fn, e.name, 8));
    }

    JS_SetPropertyStr(ctx, global, "cardinal", api);
    JS_FreeValue(ctx, global);
}

// ---- 脚本目录与输入 ----
// ⚠️ liblo string 接收在本 Cardinal 版上确认不通（2026-10-20 实测：echo /
//   module-add / js-eval 三个 string 输入端点全部无回复，oscArgStrC 两种偏移
//   读法都救不回——B5 止损案的根因坐实）。⇒ JS 源码改走「脚本文件 + 索引」：
//   纯数值参数（i），脚本放 CARDINAL_JS_DIR（默认仓库根 js/），可 git 管理
//   ——比每次传字符串更工程化，李的 Cardinal 工作流本来就是 git diff 资产。
static std::string oscJsScriptDir()
{
    const char* const env = std::getenv("CARDINAL_JS_DIR");
    if (env != nullptr && env[0] != '\0')
        return std::string(env);
    // 默认：仓库根下的 js/（本文件所在仓库的约定目录）
    return std::string("D:/Cardinal/js");
}

static std::vector<std::string> oscJsListFiles()
{
    std::vector<std::string> files;
    const std::string dir = oscJsScriptDir();
    DIR* d = opendir(dir.c_str());
    if (d == NULL)
        return files;
    struct dirent* e;
    while ((e = readdir(d)) != NULL)
    {
        const std::string name(e->d_name);
        if (name.size() > 3 && name.substr(name.size() - 3) == ".js")
            files.push_back(name);
    }
    closedir(d);
    std::sort(files.begin(), files.end());
    return files;
}

static bool oscJsReadScript(int index1Based, std::string& out)
{
    const std::vector<std::string> files = oscJsListFiles();
    if (index1Based < 1 || index1Based > (int) files.size())
        return false;
    FILE* f = fopen((oscJsScriptDir() + "/" + files[index1Based - 1]).c_str(), "rb");
    if (f == NULL)
        return false;
    char buf[8192];
    size_t n;
    while ((n = fread(buf, 1, sizeof(buf), f)) > 0)
        out.append(buf, n);
    fclose(f);
    return true;
}

// /osc-js-run "i" = 脚本索引（1-based，见 /osc-js-list）。源码里把结果赋给
// globalThis.result；eval 后把 result 字符串化回传。
static int osc_js_run_handler(const char*, const char* types, lo_arg** argv, int argc, const lo_message m, void* const self)
{
    d_debug("osc_js_run_handler()");
    DISTRHO_SAFE_ASSERT_RETURN(argc == 1, 0);

    const lo_address source = lo_message_get_source(m);
    const lo_server server = static_cast<Initializer*>(self)->oscServer;

    // ---- 模式门禁（默认 off；三级 env）----
    const char* const modeEnv = std::getenv("CARDINAL_JS_MODE");
    const std::string mode = modeEnv != nullptr ? std::string(modeEnv) : std::string("off");
    if (mode != "read" && mode != "write")
    {
        cardinalOscReply(source, server, "js",
                         "disabled: set CARDINAL_JS_MODE=read or =write to enable",
                         "err:E_DISABLED");
        return 0;
    }

    // ---- 读脚本文件（索引制，避开 liblo string 通路）----
    std::string src;
    if (!oscJsReadScript(argv[0]->i, src))
    {
        cardinalOscReply(source, server, "js",
                         "no-script: bad index (see /osc-js-list)",
                         "err:E_BAD_ARGS");
        return 0;
    }

    // ---- 诊断回显（定位期临时；通了即删）----
    {
        const std::string diag = "mode=" + mode
            + " src_len=" + std::to_string(src.size())
            + " src_head=" + src.substr(0, 48);
        cardinalOscReply(source, server, "js-diag", diag, "ok");
    }

    // ---- runtime（不初始化 libc ⇒ 无 std/os）+ 墙钟执行预算 ----
    JSRuntime* const rt = JS_NewRuntime();
    JSContext* const ctx = JS_NewContext(rt);
    if (rt == NULL || ctx == NULL)
    {
        cardinalOscReply(source, server, "js", "runtime-failed", "err:E_INTERNAL");
        if (ctx) JS_FreeContext(ctx);
        if (rt) JS_FreeRuntime(rt);
        return 0;
    }
    // 墙钟上限默认 2000ms（CARDINAL_JS_BUDGET_MS 可覆盖）；兜底 counter 上限
    // 100 万次 handler 调用 ≈ 100 亿条指令，正常路径永远碰不到。
    double budgetMs = 2000.0;
    if (const char* const envMs = std::getenv("CARDINAL_JS_BUDGET_MS"))
    {
        const double v = std::atof(envMs);
        if (v > 0.0)
            budgetMs = v;
    }
    OscJsBudget budget = {clock(), budgetMs, 0, 1000000};
    JS_SetInterruptHandler(rt, oscJsInterrupt, &budget);

    g_osc_js_self = self;
    oscJsRegisterApi(ctx, mode == "write");

    // ---- eval（包 IIFE，结果落 globalThis.result）----
    const std::string wrapped = std::string("globalThis.result = (function() {\n")
        + src + "\n})();";
    std::string payload;
    JSValue r = JS_Eval(ctx, wrapped.c_str(), wrapped.size(), "<osc-js>", JS_EVAL_TYPE_GLOBAL);
    const double elapsedMs = (double)(clock() - budget.start) * 1000.0 / (double) CLOCKS_PER_SEC;
    if (JS_IsException(r))
    {
        JSValue exc = JS_GetException(ctx);
        const char* msg = JS_ToCString(ctx, exc);
        // 预算打满的异常在 quickjs 里是 "interrupted"；如实标成 budget-exceeded
        // 并附实测耗时，让调用方一眼分得清「脚本写错」和「脚本跑太久」。
        const bool overBudget = elapsedMs >= budget.limitMs;
        payload = std::string(overBudget ? "budget-exceeded ms=" : "error: ");
        if (!overBudget)
            payload += msg != nullptr ? msg : "(unknown)";
        else
        {
            char b[32] = {};
            std::snprintf(b, sizeof(b), "%.0f", elapsedMs);
            payload += b;
        }
        if (msg != nullptr)
            JS_FreeCString(ctx, msg);
        JS_FreeValue(ctx, exc);
    }
    else
    {
        JS_FreeValue(ctx, r);
        JSValue global = JS_GetGlobalObject(ctx);
        JSValue res = JS_GetPropertyStr(ctx, global, "result");
        const char* s = JS_ToCString(ctx, res);
        payload = s != nullptr ? std::string(s) : std::string("undefined");
        if (s != nullptr)
            JS_FreeCString(ctx, s);
        JS_FreeValue(ctx, res);
        JS_FreeValue(ctx, global);
    }

    g_osc_js_self = NULL;
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);

    cardinalOscReply(source, server, "js", payload, "ok");
    return 0;
}

// /osc-js-list 无参 —— 列脚本目录（索引 1-based，按文件名排序）
static int osc_js_list_handler(const char*, const char*, lo_arg**, int, const lo_message m, void* const self)
{
    const lo_address source = lo_message_get_source(m);
    const lo_server server = static_cast<Initializer*>(self)->oscServer;

    std::string out;
    const std::vector<std::string> files = oscJsListFiles();
    for (size_t i = 0; i < files.size(); ++i)
    {
        if (!out.empty())
            out += ",";
        out += std::to_string(i + 1) + ":" + files[i];
    }
    if (out.empty())
        out = "none";

    cardinalOscReply(source, server, "js-list", out, "ok");
    return 0;
}
