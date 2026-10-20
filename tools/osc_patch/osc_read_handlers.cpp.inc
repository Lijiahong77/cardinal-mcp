// ---------------------------------------------------------------------------
// ★ 2026-10-19 新增：OSC 只读探针（read-only introspection）
//
// 【为什么需要】
// Cardinal 的 OSC 服务器**只能写不能读**（原版只有 /hello /param /host-param /load
// 四个 handler，且全都不回数据）。这让外部工具（我的 MCP）只能"盲写"：
// 设了参数、加载了机架，但**永远无法确认软件现在到底是什么状态**——
// 有没有加载成功、模块在不在、旋钮到底多少、有没有信号在跑。
//
// 【这些 handler 提供什么】
//   /modules          → 列出所有模块 id + 插件 + 模型（机器可读，逗号分隔）
//   /param-get h i    → 读回单个旋钮的**真实显示值**（走 ParamQuantity::getDisplayValue）
//   /ports h          → 读回某模块所有输入口的**连接数 + 各通道电压**  ★核心
//   /signal           → 全机架扫描：哪些模块的音频口**此刻真的有电压**
//   /light h i        → 读回 LED 亮度（判断"运行/录制灯亮没亮"）
//
// 【为什么用 getDisplayValue 而不是 getValue】
// Cardinal 的旋钮绝大多数存归一化值（0..1），但面板上显示的是物理量
// （ADSR 存 0.275 显示 275ms；Bogaudio-VCO 存 6.0 八度显示 220Hz）。
// getValue() 给的是**存储值**，对外部工具毫无意义；
// getDisplayValue() 才是**人能读懂、也能判对错的**值。
//
// 【回复格式】统一 /resp: "tag" "payload"，payload 是逗号分隔的紧凑格式，
//   避免引入 JSON 依赖（Cardinal 这边连 nlohmann 都是条件编译的）。
// ---------------------------------------------------------------------------

// 把 float 变成不含千分位/科学计数歧义的短字符串（ScopedSafeLocale 已在文件里）
static std::string fmtShort(float v)
{
    char buf[32] = {};
    const ScopedSafeLocale cssl;
    std::snprintf(buf, sizeof(buf), "%.4g", (double)v);
    return std::string(buf);
}

// ---------------------------------------------------------------- /modules
// 回复: /resp "modules" "id:plugin/model,id:plugin/model,..."
static int osc_modules_handler(const char*, const char*, lo_arg**, int, const lo_message m, void* const self)
{
    d_debug("osc_modules_handler()");

    const lo_address source = lo_message_get_source(m);
    const lo_server server = static_cast<Initializer*>(self)->oscServer;

    CardinalBasePlugin* const plugin = static_cast<Initializer*>(self)->remotePluginInstance;
    if (plugin == nullptr)
    {
        lo_send_from(source, server, LO_TT_IMMEDIATE, "/resp", "ss", "modules", "");
        return 0;
    }

    CardinalPluginContext* const context = plugin->context;

#ifdef CARDINAL_INIT_OSC_THREAD
    rack::contextSet(context);
#endif

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

        // slug 形如 "Bogaudio-VCO"；Model 直接持有 plugin 指针（Model.hpp:35），
        // 拼出的 "plugin|model" 正好和 .vcv 里的 plugin/model 字段同构
        // ⇒ 外部工具无需再查映射表。
        if (!out.empty())
            out += ",";
        out += std::to_string(id);
        out += ":";
        out += model->plugin != NULL ? model->plugin->slug : std::string("?");
        out += "|";
        out += model->slug;
    }

#ifdef CARDINAL_INIT_OSC_THREAD
    rack::contextSet(nullptr);
#endif

    lo_send_from(source, server, LO_TT_IMMEDIATE, "/resp", "ss", "modules", out.c_str());
    return 0;
}

// ------------------------------------------------------------ /param-get
// 入参: "hi" = moduleId, paramId
// 回复: /resp "param" "<displayValue>"   （字符串，方便显示真实物理量）
static int osc_param_get_handler(const char*, const char* types, lo_arg** argv, int argc, const lo_message m, void* const self)
{
    d_debug("osc_param_get_handler()");
    DISTRHO_SAFE_ASSERT_RETURN(argc == 2, 0);

    const lo_address source = lo_message_get_source(m);
    const lo_server server = static_cast<Initializer*>(self)->oscServer;

    CardinalBasePlugin* const plugin = static_cast<Initializer*>(self)->remotePluginInstance;
    if (plugin == NULL)
    {
        lo_send_from(source, server, LO_TT_IMMEDIATE, "/resp", "ss", "param", "");
        return 0;
    }

    CardinalPluginContext* const context = plugin->context;
    const int64_t moduleId = argv[0]->h;
    const int paramId = argv[1]->i;

#ifdef CARDINAL_INIT_OSC_THREAD
    rack::contextSet(context);
#endif

    std::string result;
    rack::engine::Module* const module = context->engine->getModule(moduleId);

    if (module != NULL && paramId >= 0 && paramId < module->getNumParams())
    {
        // ★ 关键：用 getDisplayValue 而非 getValue。
        //   存 0.275 的 ADSR.Attack，getValue 给 0.275（无意义），
        //   getDisplayValue 给 275（= 275 ms，这才是能判对错的值）。
        rack::engine::ParamQuantity* const pq = module->getParamQuantity(paramId);
        if (pq != NULL)
            result = fmtShort(pq->getDisplayValue());
    }

#ifdef CARDINAL_INIT_OSC_THREAD
    rack::contextSet(nullptr);
#endif

    lo_send_from(source, server, LO_TT_IMMEDIATE, "/resp", "ss", "param", result.c_str());
    return 0;
}

// ---------------------------------------------------------------- /ports
// 入参: "h" = moduleId
// 回复: /resp "ports" "in:conn:ch0vol:ch1vol|in:...|out:conn:ch0vol:ch1vol|out:..."
//
// ★ 这是本补丁最重要的一个：它回答"这个模块的口上，现在有没有信号"。
//   conn = getChannels()，0 表示**根本没接线**（⇒ 静态死模块，永远不工作）
//   vol  = 该通道电压（音频 ±5V / 音高 CV / 门信号）
//   ⇒ 外部工具由此能区分三种情况：
//       未接线(conn=0) / 接了但此刻无电压(vol=0) / 接了且此刻有信号(vol≠0)
static int osc_ports_handler(const char*, const char* types, lo_arg** argv, int argc, const lo_message m, void* const self)
{
    d_debug("osc_ports_handler()");
    DISTRHO_SAFE_ASSERT_RETURN(argc == 1, 0);

    const lo_address source = lo_message_get_source(m);
    const lo_server server = static_cast<Initializer*>(self)->oscServer;

    CardinalBasePlugin* const plugin = static_cast<Initializer*>(self)->remotePluginInstance;
    if (plugin == NULL)
    {
        lo_send_from(source, server, LO_TT_IMMEDIATE, "/resp", "ss", "ports", "");
        return 0;
    }

    CardinalPluginContext* const context = plugin->context;
    const int64_t moduleId = argv[0]->h;

#ifdef CARDINAL_INIT_OSC_THREAD
    rack::contextSet(context);
#endif

    std::string out;
    rack::engine::Module* const module = context->engine->getModule(moduleId);

    if (module != NULL)
    {
        // ---- 输入口 ----
        for (int i = 0; i < module->getNumInputs(); ++i)
        {
            rack::engine::Input& port = module->inputs[i];
            const int conn = port.getChannels();

            if (!out.empty())
                out += "|";
            out += "in:" + std::to_string(i);
            out += ":" + std::to_string(conn);

            // 只回前 4 个通道：立体声够用，poly 到 16 通道会让 payload 爆掉
            for (int ch = 0; ch < 4; ++ch)
            {
                out += ":" + fmtShort(port.getPolyVoltage(ch));
            }
        }

        // ---- 输出口 ----
        for (int i = 0; i < module->getNumOutputs(); ++i)
        {
            rack::engine::Output& port = module->outputs[i];
            const int conn = port.getChannels();

            if (!out.empty())
                out += "|";
            out += "out:" + std::to_string(i);
            out += ":" + std::to_string(conn);

            for (int ch = 0; ch < 4; ++ch)
            {
                out += ":" + fmtShort(port.getPolyVoltage(ch));
            }
        }
    }

#ifdef CARDINAL_INIT_OSC_THREAD
    rack::contextSet(nullptr);
#endif

    lo_send_from(source, server, LO_TT_IMMEDIATE, "/resp", "ss", "ports", out.c_str());
    return 0;
}

// -------------------------------------------------------------- /signal
// 无入参。扫全机架所有模块的**音频输出口**，报告此刻真的有电压的模块。
// 回复: /resp "signal" "id:volt,id:volt,..."  （只含电压非零的模块）
//
// ★ 这是「静音盲区」的正解：不需要离线渲染，直接问引擎"现在哪些口上有信号"。
//   一个模块所有输出口都是 0V ⇒ 它此刻不产生任何声音。
static int osc_signal_handler(const char*, const char*, lo_arg**, int, const lo_message m, void* const self)
{
    d_debug("osc_signal_handler()");

    const lo_address source = lo_message_get_source(m);
    const lo_server server = static_cast<Initializer*>(self)->oscServer;

    CardinalBasePlugin* const plugin = static_cast<Initializer*>(self)->remotePluginInstance;
    if (plugin == NULL)
    {
        lo_send_from(source, server, LO_TT_IMMEDIATE, "/resp", "ss", "signal", "");
        return 0;
    }

    CardinalPluginContext* const context = plugin->context;

#ifdef CARDINAL_INIT_OSC_THREAD
    rack::contextSet(context);
#endif

    std::string out;
    const std::vector<int64_t> ids = context->engine->getModuleIds();

    for (int64_t id : ids)
    {
        rack::engine::Module* const module = context->engine->getModule(id);
        if (module == NULL)
            continue;

        // 取该模块所有输出口的最大绝对电压
        float peak = 0.0f;
        for (int i = 0; i < module->getNumOutputs(); ++i)
        {
            rack::engine::Output& port = module->outputs[i];
            if (!port.isConnected())
                continue;

            for (int ch = 0; ch < 4; ++ch)
            {
                const float v = port.getPolyVoltage(ch);
                const float a = v < 0.0f ? -v : v;
                if (a > peak)
                    peak = a;
            }
        }

        // 阈值 1e-4 V：低于此在音频里等同静音（-80 dBFS 附近）
        if (peak > 1e-4f)
        {
            if (!out.empty())
                out += ",";
            out += std::to_string(id);
            out += ":" + fmtShort(peak);
        }
    }

#ifdef CARDINAL_INIT_OSC_THREAD
    rack::contextSet(nullptr);
#endif

    lo_send_from(source, server, LO_TT_IMMEDIATE, "/resp", "ss", "signal", out.c_str());
    return 0;
}

// ---------------------------------------------------------------- /light
// 入参: "hi" = moduleId, lightId
// 回复: /resp "light" "<brightness 0..1>"
// 用途：判断 Clocked 的 RUN 灯、录音灯是否亮（机架是否在跑）
static int osc_light_handler(const char*, const char* types, lo_arg** argv, int argc, const lo_message m, void* const self)
{
    d_debug("osc_light_handler()");
    DISTRHO_SAFE_ASSERT_RETURN(argc == 2, 0);

    const lo_address source = lo_message_get_source(m);
    const lo_server server = static_cast<Initializer*>(self)->oscServer;

    CardinalBasePlugin* const plugin = static_cast<Initializer*>(self)->remotePluginInstance;
    if (plugin == NULL)
    {
        lo_send_from(source, server, LO_TT_IMMEDIATE, "/resp", "ss", "light", "");
        return 0;
    }

    CardinalPluginContext* const context = plugin->context;
    const int64_t moduleId = argv[0]->h;
    const int lightId = argv[1]->i;

#ifdef CARDINAL_INIT_OSC_THREAD
    rack::contextSet(context);
#endif

    std::string result;
    rack::engine::Module* const module = context->engine->getModule(moduleId);

    if (module != NULL && lightId >= 0 && lightId < module->getNumLights())
        result = fmtShort(module->lights[lightId].getBrightness());

#ifdef CARDINAL_INIT_OSC_THREAD
    rack::contextSet(nullptr);
#endif

    lo_send_from(source, server, LO_TT_IMMEDIATE, "/resp", "ss", "light", result.c_str());
    return 0;
}