// ---------------------------------------------------------------------------
// ★ 2026-10-20 新增：B 组读数 handler（build-info / cables / transport /
//   engine-info / plugins）。与 A 组（osc_read_handlers.cpp.inc）共用同一套
//   回复契约：/resp "tag" "payload"，payload 内部用 | 分字段、逗号分列表。
//
// 【源码依据】（全部 2026-10-20 在 WSL 树 /home/lijia/Cardinal 实测核实，
//   不照抄旧档行号——A5 的教训：行号会指错文件）
//   B2  Cable 字段：src/Rack/include/engine/Cable.hpp
//       （id / inputModule / inputId / outputModule / outputId 全 public）
//       getCableIds()：engine/Engine.hpp:163；getCable(id)：:183
//   B3  transport：include/plugincontext.hpp:86-90
//       （CardinalPluginContext : rack::Context，playing/bar/beat/beatsPerBar/
//        beatType/barStartTick/beatsPerMinute/tick/tickClock/ticksPerBeat 全现成）
//   B4  meter：engine/Engine.hpp:87-88（getMeterAverage/getMeterMax）；
//       ⚠️ CPU 值每 1 秒才刷新（engine/Engine.cpp:576 meterUpdateDuration=1.0，
//       meterLastTime 是 Engine 私有成员，外部拿不到精确 age）
//       ⇒ 诚实处理：回常量 cpuRefreshMs=1000，不假装知道精确 age
//   B5  getPlugin：src/Rack/src/plugin.cpp:373（非 static，但 Plugin.hpp 未导出声明
//       ⇒ 注入器把前置声明插到 CardinalCommon.cpp 顶部全局作用域）；
//       safeMode：src/Rack/include/settings.hpp:31（在 namespace rack 内 ⇒ 写 rack::settings）
//
// ⚠️ liblo 的 method 匹配是 types 精确匹配（同 path 不同 types 要分开注册）：
//   /cables 无参（全量）与 /cables "h"（单模块过滤）是两个 handler。
//   /plugins 只做无参列表——单查（"s"）已下线：该 liblo 的 string 接收路径
//   不可靠（2026-10-20 实测静默无回复），单查需求由 MCP 侧读 PluginManifests
//   承担（磁盘事实 vs 运行事实分层，见 TODO-BACKLOG B5）。
// ⚠️ liblo string 参数必须 *(char**)&argv[n]->s 取——本 Cardinal 版的 lo_arg.s
//   声明为 char，实际存 char*（lo_osc_types.h 官方注释原话：
//   "strings must be read with &argv[n]->t"）。直接 argv[n]->s 会按 char 解析报错。
//
// 【为什么 B1 重要】（TODO-BACKLOG 标 P0）
//   OSC 开不开由运行期 getenv 决定（override/MenuBar.cpp:741），没开时所有工具
//   超时——现象与「Cardinal 崩了」无法区分。/build-info 让客户端一发拿到构建
//   指纹；MCP 侧配合进程探测即可区分「没开 OSC」与「崩了」。
// ---------------------------------------------------------------------------

// 数字 → 短字符串（与 A 组 fmtShort 独立命名，避免重定义；ScopedSafeLocale
// 来自 CardinalCommon.cpp 既有 include 链，A 组已实证可用）
static std::string fmtB(double v)
{
    char buf[40] = {};
    const ScopedSafeLocale cssl;
    std::snprintf(buf, sizeof(buf), "%.6g", v);
    return std::string(buf);
}

// liblo string 参数取值（见文件头：必须取 s 成员地址转型——联合起始 8 字节
// 是 i/i32 的地盘，读 (char**)a 会拿到垃圾指针，2026-10-20 实测栽过）
static const char* oscArgStr(const lo_arg* a)
{
    return *(char**)&a->s;
}

static const char* cardinalVariantName(CardinalVariant v)
{
    switch (v)
    {
    case kCardinalVariantMain:   return "main";
    case kCardinalVariantMini:   return "mini";
    case kCardinalVariantFX:     return "fx";
    case kCardinalVariantNative: return "native";
    case kCardinalVariantSynth:  return "synth";
    default:                     return "?";
    }
}

// ---------------------------------------------------------------- B1 /build-info
// 无入参。回复 /resp "build-info" "variant=..|mode=..|build=..|safeMode=..|caps=.."
static int osc_build_info_handler(const char*, const char*, lo_arg**, int, const lo_message m, void* const self)
{
    d_debug("osc_build_info_handler()");

    const lo_address source = lo_message_get_source(m);
    const lo_server server = static_cast<Initializer*>(self)->oscServer;

    const char* variant = "?";
    CardinalBasePlugin* const plugin = static_cast<Initializer*>(self)->remotePluginInstance;
    if (plugin != nullptr && plugin->context != nullptr)
        variant = cardinalVariantName(plugin->context->variant);

    std::string mode =
       #ifdef CARDINAL_INIT_OSC_THREAD
        "thread";
       #else
        "gui";
       #endif

    // caps 清单 = 当前构建实际注入的全部 OSC 端点（加新端点时同步更新这里！）
    std::string caps = "modules,param-get,ports,signal,light,"
                       "build-info,cables,transport,engine-info,plugins";

    std::string payload = std::string("variant=") + variant
        + "|mode=" + mode
        + "|build=" + __DATE__ " " __TIME__
        + "|safeMode=" + (rack::settings::safeMode ? "1" : "0")
        + "|caps=" + caps;

    lo_send_from(source, server, LO_TT_IMMEDIATE, "/resp", "ss", "build-info", payload.c_str());
    return 0;
}

// ---------------------------------------------------------------- B2 /cables
// /cables        无参 → 全机架所有线
// /cables "h"    带 moduleId → 只回涉及该模块的线
// 回复 /resp "cables" "id:inMod:inId:outMod:outId,..."（无线 = "none"）
static int osc_cables_handler_impl(const lo_message m, void* const self, bool filter, int64_t filterId)
{
    const lo_address source = lo_message_get_source(m);
    const lo_server server = static_cast<Initializer*>(self)->oscServer;

    CardinalBasePlugin* const plugin = static_cast<Initializer*>(self)->remotePluginInstance;
    if (plugin == nullptr)
    {
        lo_send_from(source, server, LO_TT_IMMEDIATE, "/resp", "ss", "cables", "");
        return 0;
    }

    CardinalPluginContext* const context = plugin->context;

   #ifdef CARDINAL_INIT_OSC_THREAD
    rack::contextSet(context);
   #endif

    std::string out;
    const std::vector<int64_t> ids = context->engine->getCableIds();
    for (int64_t id : ids)
    {
        rack::engine::Cable* const c = context->engine->getCable(id);
        if (c == NULL)
            continue;
        const int64_t inMod  = c->inputModule  != NULL ? c->inputModule->id  : -1;
        const int64_t outMod = c->outputModule != NULL ? c->outputModule->id : -1;
        if (filter && inMod != filterId && outMod != filterId)
            continue;
        if (!out.empty())
            out += ",";
        out += std::to_string(id) + ":" + std::to_string(inMod) + ":"
             + std::to_string(c->inputId) + ":" + std::to_string(outMod) + ":"
             + std::to_string(c->outputId);
    }

   #ifdef CARDINAL_INIT_OSC_THREAD
    rack::contextSet(nullptr);
   #endif

    if (out.empty())
        out = "none";
    lo_send_from(source, server, LO_TT_IMMEDIATE, "/resp", "ss", "cables", out.c_str());
    return 0;
}

static int osc_cables_all_handler(const char*, const char*, lo_arg**, int, const lo_message m, void* const self)
{
    d_debug("osc_cables_all_handler()");
    return osc_cables_handler_impl(m, self, false, 0);
}

static int osc_cables_one_handler(const char*, const char* types, lo_arg** argv, int argc, const lo_message m, void* const self)
{
    d_debug("osc_cables_one_handler()");
    DISTRHO_SAFE_ASSERT_RETURN(argc == 1, 0);  // types 匹配由 liblo 注册侧保证
    return osc_cables_handler_impl(m, self, true, argv[0]->h);
}

// ---------------------------------------------------------------- B3 /transport
// 无入参。回复 /resp "transport" "playing=..|bar=..|beat=..|bpb=..|beatType=..|bpm=..|tick=..|ticksPerBeat=..|bypassed=.."
static int osc_transport_handler(const char*, const char*, lo_arg**, int, const lo_message m, void* const self)
{
    d_debug("osc_transport_handler()");

    const lo_address source = lo_message_get_source(m);
    const lo_server server = static_cast<Initializer*>(self)->oscServer;

    CardinalBasePlugin* const plugin = static_cast<Initializer*>(self)->remotePluginInstance;
    if (plugin == nullptr || plugin->context == nullptr)
    {
        lo_send_from(source, server, LO_TT_IMMEDIATE, "/resp", "ss", "transport", "");
        return 0;
    }

    const CardinalPluginContext* const context = plugin->context;
    std::string payload = std::string("playing=") + (context->playing ? "1" : "0")
        + "|bar=" + std::to_string(context->bar)
        + "|beat=" + std::to_string(context->beat)
        + "|bpb=" + std::to_string(context->beatsPerBar)
        + "|beatType=" + std::to_string(context->beatType)
        + "|bpm=" + fmtB(context->beatsPerMinute)
        + "|tick=" + fmtB(context->tick)
        + "|ticksPerBeat=" + fmtB(context->ticksPerBeat)
        + "|bypassed=" + (context->bypassed ? "1" : "0");

    lo_send_from(source, server, LO_TT_IMMEDIATE, "/resp", "ss", "transport", payload.c_str());
    return 0;
}

// ---------------------------------------------------------------- B4 /engine-info
// 无入参。回复 /resp "engine-info" "sampleRate=..|bufferSize=..|cpuAvg=..|cpuMax=..|cpuRefreshMs=1000"
// ⚠️ CPU 负载每 1 秒刷新（Engine.cpp:576），meterLastTime 私有拿不到 ⇒ 回常量
static int osc_engine_info_handler(const char*, const char*, lo_arg**, int, const lo_message m, void* const self)
{
    d_debug("osc_engine_info_handler()");

    const lo_address source = lo_message_get_source(m);
    const lo_server server = static_cast<Initializer*>(self)->oscServer;

    CardinalBasePlugin* const plugin = static_cast<Initializer*>(self)->remotePluginInstance;
    if (plugin == nullptr || plugin->context == nullptr)
    {
        lo_send_from(source, server, LO_TT_IMMEDIATE, "/resp", "ss", "engine-info", "");
        return 0;
    }

    const CardinalPluginContext* const context = plugin->context;
    std::string payload = std::string("sampleRate=") + fmtB(context->sampleRate)
        + "|bufferSize=" + std::to_string(context->bufferSize)
        + "|cpuAvg=" + fmtB(context->engine->getMeterAverage())
        + "|cpuMax=" + fmtB(context->engine->getMeterMax())
        + "|cpuRefreshMs=1000";

    lo_send_from(source, server, LO_TT_IMMEDIATE, "/resp", "ss", "engine-info", payload.c_str());
    return 0;
}

// ---------------------------------------------------------------- B5 /plugins
// /plugins        无参 → 当前机架里出现过的 plugin slug 列表（引擎真实数据，去重）
// 带 safeMode 标志（true 时插件根本没加载——「拼写正确却找不到」的第一嫌疑）
// 单查（"s"）已下线：liblo string 接收不可靠，单查由 MCP 侧读 PluginManifests 承担
// 回复 /resp "plugins" "safeMode=..|plugins=.."
static int osc_plugins_list_handler(const char*, const char*, lo_arg**, int, const lo_message m, void* const self)
{
    d_debug("osc_plugins_list_handler()");

    const lo_address source = lo_message_get_source(m);
    const lo_server server = static_cast<Initializer*>(self)->oscServer;

    std::string payload = std::string("safeMode=") + (rack::settings::safeMode ? "1" : "0");

    std::string list;
    CardinalBasePlugin* const plugin = static_cast<Initializer*>(self)->remotePluginInstance;
    if (plugin != nullptr && plugin->context != nullptr)
    {
       #ifdef CARDINAL_INIT_OSC_THREAD
        rack::contextSet(plugin->context);
       #endif
        std::vector<std::string> seen;   // 量小（<100），线性查重，避免依赖 <set>
        const std::vector<int64_t> ids = plugin->context->engine->getModuleIds();
        for (int64_t id : ids)
        {
            rack::engine::Module* const module = plugin->context->engine->getModule(id);
            if (module == NULL)
                continue;
            rack::plugin::Model* const model = module->getModel();
            if (model == NULL || model->plugin == NULL)
                continue;
            const std::string slug = model->plugin->slug;
            bool dup = false;
            for (const std::string& s : seen)
                if (s == slug) { dup = true; break; }
            if (!dup)
            {
                seen.push_back(slug);
                if (!list.empty())
                    list += ",";
                list += slug;
            }
        }
       #ifdef CARDINAL_INIT_OSC_THREAD
        rack::contextSet(nullptr);
       #endif
    }
    payload += "|plugins=" + (list.empty() ? std::string("none") : list);

    lo_send_from(source, server, LO_TT_IMMEDIATE, "/resp", "ss", "plugins", payload.c_str());
    return 0;
}
