// ---------------------------------------------------------------------------
// ★ 2026-10-20 新增：C 组 handler —— 模拟人类操作（李定的核心方向）
//   全部走 history API（可 undo），与「人类点 UI」等价：
//     C1 /param-set-by-display h i f   右键旋钮输数值（setDisplayValue）
//     C2 /module-add       s i i       右键 Add module（Plugin 菜单）
//     C3 /cable-add h i h i            从输出口拖线到输入口（查重：挤掉旧线）
//        /cable-remove     h           选中线按 Delete
//     C4 /undo  /redo                  Ctrl+Z / Ctrl+Shift+Z
//     C6r /module-json      h          读模块 data（toJson；回复方向 string 可靠）
//     C7 /module-remove     h          右键 Remove
//     C8 /module-move h i i            拖动模块（ModuleMove history，可 undo）
//     C9 /midi-out i i i i             在 DAW 里弹 MIDI（channel+3 字节，数值参数）
//     /osc-echo-string     s           string 接收探针（验证 liblo string 通路）
//
// 【源码依据】（全部 2026-10-20 在 WSL 树 /home/lijia/Cardinal 实测核实）
//   C1  ParamQuantity::setDisplayValue：src/Rack/include/engine/ParamQuantity.hpp:99
//       ParamChange{moduleId,paramId,oldValue,newValue}：src/Rack/include/history.hpp
//   C2  ModuleAdd{model,pos,moduleJ}：history.hpp:71；Plugin::getModel：plugin/Plugin.hpp
//       ::rack::plugin::getPlugin：src/Rack/src/plugin.cpp:373
//   C3  CableAdd{cableId,inputModuleId,inputId,outputModuleId,outputId,color}：history.hpp:137
//       CableAdd::redo 自建 Cable（不需 widget）：src/Rack/src/history.cpp:171
//       CableRemove：history.hpp:153（InverseAction<CableAdd>）
//   C4  State::undo/redo/canUndo/canRedo/getUndoName/getRedoName：history.hpp:183+
//       APP->history 已在 CardinalCommon.cpp:1604 使用（include 链通）
//   C6r Module::toJson()：src/Rack/include/engine/Module.hpp:347
//   C7  ModuleRemove：history.hpp:85
//   C8  ModuleMove{moduleId,oldPos,newPos}：history.hpp（push 时 redo 填 oldPos）
//   C9  midi::Message{bytes,frame=-1}：src/Rack/include/midi.hpp:16-24；
//       writeMidiMessage：include/plugincontext.hpp:100；bypassed 提前 return 要回显
//
// ⚠️ liblo string 接收：lo_arg.s 声明为 char，官方约定 &argv[n]->s 取指针
//   （lo_osc_types.h 注释原话 "strings must be read with &argv[n]->t"）。
//   B5 曾因此止损下线单查（首版 oscArgStr 读错偏移写了 *(char**)a，联合起始
//   8 字节是 i/i32 地盘；修正版 *(char**)&a->s 当时未验证）。本批带
//   /osc-echo-string 探针重新验证——通则 C2 等 string 端点转正。
// ---------------------------------------------------------------------------

// 数字 → 短字符串（独立命名，避免与 B 组的 fmtB 重定义——同一 TU！）
static std::string fmtC(double v)
{
    char buf[40] = {};
    const ScopedSafeLocale cssl;
    std::snprintf(buf, sizeof(buf), "%.6g", v);
    return std::string(buf);
}

// liblo string 参数取值：取 s 成员地址转型（s 在联合内偏移约 40，不是 0）
static const char* oscArgStrC(const lo_arg* a)
{
    return *(char**)&a->s;
}

static std::string oscJsonDumpsCompact(json_t* j)
{
    if (j == NULL)
        return std::string("null");
    char* s = json_dumps(j, JSON_COMPACT);
    std::string out = s ? s : "";
    if (s)
        free(s);
    return out;
}

// ---------------------------------------------------------------- C1 /param-set-by-display
// 入参 "hif" = moduleId, paramId, displayValue
// 回复 "param-set" "ok old=.. new=.."（存储值前后）/ 错误原因
static int osc_param_set_display_handler(const char*, const char* types, lo_arg** argv, int argc, const lo_message m, void* const self)
{
    d_debug("osc_param_set_display_handler()");
    DISTRHO_SAFE_ASSERT_RETURN(argc == 3, 0);

    const lo_address source = lo_message_get_source(m);
    const lo_server server = static_cast<Initializer*>(self)->oscServer;

    CardinalBasePlugin* const plugin = static_cast<Initializer*>(self)->remotePluginInstance;
    if (plugin == nullptr)
    {
        lo_send_from(source, server, LO_TT_IMMEDIATE, "/resp", "ss", "param-set", "no-plugin");
        return 0;
    }
    CardinalPluginContext* const context = plugin->context;
    const int64_t moduleId = argv[0]->h;
    const int paramId = argv[1]->i;
    const float displayValue = argv[2]->f;

   #ifdef CARDINAL_INIT_OSC_THREAD
    rack::contextSet(context);
   #endif

    std::string payload;
    rack::engine::Module* const module = context->engine->getModule(moduleId);
    rack::engine::ParamQuantity* const pq = module != NULL
        ? module->getParamQuantity(paramId) : NULL;
    if (pq != NULL)
    {
        const float oldValue = pq->getValue();
        pq->setDisplayValue(displayValue);   // 引擎按量纲换算存储值（275ms→0.275）
        const float newValue = pq->getValue();
        rack::history::ParamChange* a = new rack::history::ParamChange;
        a->moduleId = moduleId;
        a->paramId = paramId;
        a->oldValue = oldValue;
        a->newValue = newValue;
        APP->history->push(a);
        payload = std::string("ok old=") + fmtC(oldValue) + " new=" + fmtC(newValue);
    }
    else
    {
        payload = module == NULL ? "no-module" : "bad-param";
    }

   #ifdef CARDINAL_INIT_OSC_THREAD
    rack::contextSet(nullptr);
   #endif

    lo_send_from(source, server, LO_TT_IMMEDIATE, "/resp", "ss", "param-set", payload.c_str());
    return 0;
}

// ---------------------------------------------------------------- C3 /cable-add
// 入参 "hihi" = outputModuleId, outputId, inputModuleId, inputId
// 人类等价：从输出口拖一条线到输入口。同一输入口只能接一根线 ⇒ 旧线被挤掉
// （Rack 的 GUI 行为），这里显式查重并先 remove，回复报告 replaced 数。
static int osc_cable_add_handler(const char*, const char* types, lo_arg** argv, int argc, const lo_message m, void* const self)
{
    d_debug("osc_cable_add_handler()");
    DISTRHO_SAFE_ASSERT_RETURN(argc == 4, 0);

    const lo_address source = lo_message_get_source(m);
    const lo_server server = static_cast<Initializer*>(self)->oscServer;

    CardinalBasePlugin* const plugin = static_cast<Initializer*>(self)->remotePluginInstance;
    if (plugin == nullptr)
    {
        lo_send_from(source, server, LO_TT_IMMEDIATE, "/resp", "ss", "cable-add", "no-plugin");
        return 0;
    }
    CardinalPluginContext* const context = plugin->context;
    const int64_t outMod = argv[0]->h;
    const int outPort = argv[1]->i;
    const int64_t inMod = argv[2]->h;
    const int inPort = argv[3]->i;

   #ifdef CARDINAL_INIT_OSC_THREAD
    rack::contextSet(context);
   #endif

    std::string payload;
    rack::engine::Module* const outM = context->engine->getModule(outMod);
    rack::engine::Module* const inM = context->engine->getModule(inMod);
    if (outM == NULL || inM == NULL)
    {
        payload = "no-module";
    }
    else if (outPort < 0 || outPort >= outM->getNumOutputs()
             || inPort < 0 || inPort >= inM->getNumInputs())
    {
        payload = "bad-port";
    }
    else
    {
        int replaced = 0;
        // 查重：同一输入口已接的线，先 remove（模仿人类拖线挤掉）
        std::vector<int64_t> ids = context->engine->getCableIds();
        for (int64_t id : ids)
        {
            rack::engine::Cable* const c = context->engine->getCable(id);
            if (c == NULL)
                continue;
            if (c->inputModule == inM && c->inputId == inPort)
            {
                rack::history::CableRemove* r = new rack::history::CableRemove;
                r->cableId = id;
                APP->history->push(r);
                ++replaced;
            }
        }
        rack::history::CableAdd* a = new rack::history::CableAdd;
        a->cableId = -1;   // 加入引擎时分配新 id
        a->inputModuleId = inMod;
        a->inputId = inPort;
        a->outputModuleId = outMod;
        a->outputId = outPort;
        APP->history->push(a);
        payload = std::string("ok replaced=") + std::to_string(replaced);
    }

   #ifdef CARDINAL_INIT_OSC_THREAD
    rack::contextSet(nullptr);
   #endif

    lo_send_from(source, server, LO_TT_IMMEDIATE, "/resp", "ss", "cable-add", payload.c_str());
    return 0;
}

// ---------------------------------------------------------------- C3 /cable-remove
// 入参 "h" = cableId
static int osc_cable_remove_handler(const char*, const char* types, lo_arg** argv, int argc, const lo_message m, void* const self)
{
    d_debug("osc_cable_remove_handler()");
    DISTRHO_SAFE_ASSERT_RETURN(argc == 1, 0);

    const lo_address source = lo_message_get_source(m);
    const lo_server server = static_cast<Initializer*>(self)->oscServer;

    CardinalBasePlugin* const plugin = static_cast<Initializer*>(self)->remotePluginInstance;
    if (plugin == nullptr)
    {
        lo_send_from(source, server, LO_TT_IMMEDIATE, "/resp", "ss", "cable-remove", "no-plugin");
        return 0;
    }
    CardinalPluginContext* const context = plugin->context;
    const int64_t cableId = argv[0]->h;

   #ifdef CARDINAL_INIT_OSC_THREAD
    rack::contextSet(context);
   #endif

    std::string payload;
    if (context->engine->getCable(cableId) != NULL)
    {
        rack::history::CableRemove* a = new rack::history::CableRemove;
        a->cableId = cableId;
        APP->history->push(a);
        payload = "ok";
    }
    else
    {
        payload = "no-cable";
    }

   #ifdef CARDINAL_INIT_OSC_THREAD
    rack::contextSet(nullptr);
   #endif

    lo_send_from(source, server, LO_TT_IMMEDIATE, "/resp", "ss", "cable-remove", payload.c_str());
    return 0;
}

// ---------------------------------------------------------------- C4 /undo /redo
static int osc_undo_handler(const char*, const char*, lo_arg**, int, const lo_message m, void* const self)
{
    d_debug("osc_undo_handler()");
    const lo_address source = lo_message_get_source(m);
    const lo_server server = static_cast<Initializer*>(self)->oscServer;
    std::string payload;
    if (APP->history->canUndo())
    {
        payload = APP->history->getUndoName();
        APP->history->undo();
    }
    else
    {
        payload = "nothing";
    }
    lo_send_from(source, server, LO_TT_IMMEDIATE, "/resp", "ss", "undo", payload.c_str());
    return 0;
}

static int osc_redo_handler(const char*, const char*, lo_arg**, int, const lo_message m, void* const self)
{
    d_debug("osc_redo_handler()");
    const lo_address source = lo_message_get_source(m);
    const lo_server server = static_cast<Initializer*>(self)->oscServer;
    std::string payload;
    if (APP->history->canRedo())
    {
        payload = APP->history->getRedoName();
        APP->history->redo();
    }
    else
    {
        payload = "nothing";
    }
    lo_send_from(source, server, LO_TT_IMMEDIATE, "/resp", "ss", "redo", payload.c_str());
    return 0;
}

// ---------------------------------------------------------------- C6r /module-json
// 入参 "h" = moduleId。回复 "module-json" "<compact json>"（截断保护：OSC UDP 上限）
static int osc_module_json_handler(const char*, const char* types, lo_arg** argv, int argc, const lo_message m, void* const self)
{
    d_debug("osc_module_json_handler()");
    DISTRHO_SAFE_ASSERT_RETURN(argc == 1, 0);

    const lo_address source = lo_message_get_source(m);
    const lo_server server = static_cast<Initializer*>(self)->oscServer;

    CardinalBasePlugin* const plugin = static_cast<Initializer*>(self)->remotePluginInstance;
    if (plugin == nullptr)
    {
        lo_send_from(source, server, LO_TT_IMMEDIATE, "/resp", "ss", "module-json", "no-plugin");
        return 0;
    }
    CardinalPluginContext* const context = plugin->context;
    const int64_t moduleId = argv[0]->h;

   #ifdef CARDINAL_INIT_OSC_THREAD
    rack::contextSet(context);
   #endif

    std::string payload;
    rack::engine::Module* const module = context->engine->getModule(moduleId);
    if (module == NULL)
    {
        payload = "no-module";
    }
    else
    {
        json_t* const j = module->toJson();
        std::string s = oscJsonDumpsCompact(j);
        if (j != NULL)
            json_decref(j);
        if (s.size() > 60000)
        {
            s.resize(60000);
            s += "...TRUNCATED";
        }
        payload = s;
    }

   #ifdef CARDINAL_INIT_OSC_THREAD
    rack::contextSet(nullptr);
   #endif

    lo_send_from(source, server, LO_TT_IMMEDIATE, "/resp", "ss", "module-json", payload.c_str());
    return 0;
}

// ---------------------------------------------------------------- C7 /module-remove
// 入参 "h" = moduleId
static int osc_module_remove_handler(const char*, const char* types, lo_arg** argv, int argc, const lo_message m, void* const self)
{
    d_debug("osc_module_remove_handler()");
    DISTRHO_SAFE_ASSERT_RETURN(argc == 1, 0);

    const lo_address source = lo_message_get_source(m);
    const lo_server server = static_cast<Initializer*>(self)->oscServer;

    CardinalBasePlugin* const plugin = static_cast<Initializer*>(self)->remotePluginInstance;
    if (plugin == nullptr)
    {
        lo_send_from(source, server, LO_TT_IMMEDIATE, "/resp", "ss", "module-remove", "no-plugin");
        return 0;
    }
    CardinalPluginContext* const context = plugin->context;
    const int64_t moduleId = argv[0]->h;

   #ifdef CARDINAL_INIT_OSC_THREAD
    rack::contextSet(context);
   #endif

    std::string payload;
    if (context->engine->getModule(moduleId) != NULL)
    {
        rack::history::ModuleRemove* a = new rack::history::ModuleRemove;
        a->moduleId = moduleId;
        APP->history->push(a);
        payload = "ok";
    }
    else
    {
        payload = "no-module";
    }

   #ifdef CARDINAL_INIT_OSC_THREAD
    rack::contextSet(nullptr);
   #endif

    lo_send_from(source, server, LO_TT_IMMEDIATE, "/resp", "ss", "module-remove", payload.c_str());
    return 0;
}

// ---------------------------------------------------------------- C8 /module-move
// 入参 "hii" = moduleId, x, y（格坐标）。走 ModuleMove history ⇒ 可 undo
static int osc_module_move_handler(const char*, const char* types, lo_arg** argv, int argc, const lo_message m, void* const self)
{
    d_debug("osc_module_move_handler()");
    DISTRHO_SAFE_ASSERT_RETURN(argc == 3, 0);

    const lo_address source = lo_message_get_source(m);
    const lo_server server = static_cast<Initializer*>(self)->oscServer;

    CardinalBasePlugin* const plugin = static_cast<Initializer*>(self)->remotePluginInstance;
    if (plugin == nullptr)
    {
        lo_send_from(source, server, LO_TT_IMMEDIATE, "/resp", "ss", "module-move", "no-plugin");
        return 0;
    }
    CardinalPluginContext* const context = plugin->context;
    const int64_t moduleId = argv[0]->h;
    const float px = argv[1]->i;
    const float py = argv[2]->i;

   #ifdef CARDINAL_INIT_OSC_THREAD
    rack::contextSet(context);
   #endif

    std::string payload;
    if (context->engine->getModule(moduleId) != NULL)
    {
        rack::history::ModuleMove* a = new rack::history::ModuleMove;
        a->moduleId = moduleId;
        a->newPos = rack::math::Vec(px, py);
        APP->history->push(a);
        payload = std::string("ok ") + std::to_string((int)px) + ":" + std::to_string((int)py);
    }
    else
    {
        payload = "no-module";
    }

   #ifdef CARDINAL_INIT_OSC_THREAD
    rack::contextSet(nullptr);
   #endif

    lo_send_from(source, server, LO_TT_IMMEDIATE, "/resp", "ss", "module-move", payload.c_str());
    return 0;
}

// ---------------------------------------------------------------- C9 /midi-out
// 入参 "iiii" = channel, byte0, byte1, byte2（数值参数，避开 string/blob 通路）
// ⚠️ frame 必须 >= 0（TODO: plugincontext.hpp:208 assert）⇒ 用 context->frame
// ⚠️ bypassed 时引擎提前 return ⇒ 回显 skipped:bypassed，不假装发成功
static int osc_midi_out_handler(const char*, const char* types, lo_arg** argv, int argc, const lo_message m, void* const self)
{
    d_debug("osc_midi_out_handler()");
    DISTRHO_SAFE_ASSERT_RETURN(argc == 4, 0);

    const lo_address source = lo_message_get_source(m);
    const lo_server server = static_cast<Initializer*>(self)->oscServer;

    CardinalBasePlugin* const plugin = static_cast<Initializer*>(self)->remotePluginInstance;
    if (plugin == nullptr)
    {
        lo_send_from(source, server, LO_TT_IMMEDIATE, "/resp", "ss", "midi-out", "no-plugin");
        return 0;
    }
    CardinalPluginContext* const context = plugin->context;

    std::string payload;
    if (context->bypassed)
    {
        payload = "skipped:bypassed";
    }
    else
    {
        rack::midi::Message msg;
        msg.bytes.push_back((uint8_t) argv[1]->i);
        msg.bytes.push_back((uint8_t) argv[2]->i);
        msg.bytes.push_back((uint8_t) argv[3]->i);
        msg.frame = (int64_t) context->frame;
        context->writeMidiMessage(msg, (uint8_t) argv[0]->i);
        payload = "sent";
    }

    lo_send_from(source, server, LO_TT_IMMEDIATE, "/resp", "ss", "midi-out", payload.c_str());
    return 0;
}
