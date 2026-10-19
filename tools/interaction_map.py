"""交互寻址：把「人类能做的每个操作」索引成可调用的工具

## 这是什么
李定的核心思路（2026-10-19）：
> 「人类点的是 UI 里的按钮，我应该找到那个按钮的代码路径，然后调它
> —— 而不是改文件重载。这样的思路就是应该面对你整个过程流程里的所有东西。」

**这不是一个工具，是一条判据。** 每当我想「改文件 → 重载」时，
应该先问：**人类在界面上做这件事时，点的是哪里？那段代码在哪？**

## 三条规则
1. **先找 UI 落点，再找背后的函数。** 人类点右键菜单 / 拖旋钮 / 按按钮，
   都有对应的 `MenuItem::onAction` / `Widget::onButton` / 虚函数。
   那才是权威入口 —— 里面已经处理好了所有边界与副作用。
2. **优先走「不弹对话框」的那条分支。** 人类路径常有两条：
   `async_dialog_filebrowser(...)`（人用）vs 直接收参数（程序用）。
   走后者，跳过 GUI 依赖。
3. **只有确实找不到 UI 落点时**，才退到「改文件 + 重载」，
   并且**必须说明为什么找不到**。

## 本文件是什么
它是一份**索引**，列出 Cardinal 里「人类能操作」的全部动作，
以及每个动作背后可编程调用的代码位置和当前状态。

它的作用不是给我自己看的，是**给未来的任务查表用的**：
下次要做某个操作，先来这里查人类点哪里，别又从头翻源码。
"""

from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------- 操作索引
#
# status:
#   "ready"     —— 已做成 MCP 工具，可直接调
#   "partial"   —— 只能改文件重载，没走 UI 路径（原因见 blocker）
#   "planned"   —— 源码已定位，handler 已设计，待编译
#   "blocked"   —— 源码层面就做不到，说明原因

ACTIONS: list[dict[str, Any]] = [
    # ---------- 浏览器 / 检索 ----------
    {
        "id": "browse-modules",
        "human": "右键 → Add module → 搜索框打字 / 按 Tags、品牌筛选",
        "ui_entry": "Rack/src/app/Browser.cpp:43 static modelDb（启动时全量建索引）",
        "backend_fn": "plugin::getModelFallback() → Model::createModule()",
        "programmable": "数据在内存但 modelDb 是 static；我改读本机 PluginManifests",
        "status": "ready",
        "tools": ["cardinal_module_search", "cardinal_module_tags",
                  "cardinal_module_brands", "cardinal_module_detail"],
        "note": "与人类右键菜单同一份数据（1407 模块 / 85 品牌 / 104 标签）。",
    },
    {
        "id": "add-module",
        "human": "右键 → Add module → 选中 → 拖进机架",
        "ui_entry": "RackWidget::appendContextMenu（浏览器菜单）",
        "backend_fn": "history::ModuleAdd::redo()（现成的完整范式）"
                      " → Model::createModule → Engine::addModule → RackWidget::addModule",
        "programmable": "需要新 C++ handler",
        "status": "planned",
        "blocker": "RackWidget::addModule 依赖 APP->scene；需编译；"
                   "GUI 版 OSC 每帧在 UI 线程 pump（MenuBar.cpp:852）⇒ handler 里调 widget 安全",
    },
    {
        "id": "remove-module",
        "human": "右键模块 → Remove",
        "ui_entry": "ModuleWidget::appendContextMenu",
        "backend_fn": "history::ModuleRemove::redo()",
        "programmable": "需要新 C++ handler",
        "status": "planned",
        "blocker": "同上；history::ModuleRemove 已有现成 Action",
    },
    {
        "id": "move-module",
        "human": "拖动模块改变位置",
        "ui_entry": "RackWidget 拖放处理（onDragMove 等）",
        "backend_fn": "RackWidget::requestModulePos / setModulePosForce",
        "programmable": "需要新 C++ handler",
        "status": "planned",
    },

    # ---------- 接线 ----------
    {
        "id": "add-cable",
        "human": "从模块输出口拖一条线到另一个输入口",
        "ui_entry": "RackWidget 拖放 / ModuleWidget::onPortMouse",
        "backend_fn": "history::CableAdd::redo()（现成范式：new Cable → Engine::addCable"
                      " → new CableWidget → RackWidget::addCable）",
        "programmable": "需要新 C++ handler",
        "status": "planned",
        "note": "⚠️ 同一输入口只能接一根线，后一根挤掉前一根 ⇒ handler 必须查重",
    },
    {
        "id": "remove-cable",
        "human": "右键连线 → 删除",
        "ui_entry": "CableWidget 右键菜单",
        "backend_fn": "history::CableRemove::redo()",
        "programmable": "需要新 C++ handler",
        "status": "planned",
    },

    # ---------- 参数 ----------
    {
        "id": "turn-knob",
        "human": "拖动旋钮改值",
        "ui_entry": "ParamWidget::onDrag / ParamHandle",
        "backend_fn": "Engine::setParamValue（会走 history 之外的直写）",
        "programmable": "✅ 已能做（按整数 param index）",
        "status": "ready",
        "tools": ["cardinal_set_param"],
        "limitation": "只能按编号，不知道旋钮叫什么；且不可撤销",
    },
    {
        "id": "knob-rightclick-enter-value",
        "human": "右键旋钮 → 输入数值",
        "ui_entry": "ParamWidget::onButton → 弹出输入菜单",
        "backend_fn": "⭐ ParamQuantity::setDisplayValue(float)"
                      "（Rack/src/engine/ParamQuantity.cpp:91）"
                      " / setDisplayValueString(:133)",
        "programmable": "需要新 C++ handler",
        "status": "planned",
        "value": "高",
        "note": "⭐ 这一条极重要：Cardinal 存的是归一化值/八度值，"
                "但人能读懂的是显示值（ADSR 存 0.275 = 275ms）。"
                "有 setDisplayValue 才能说「把起音设成 275ms」，"
                "否则只能说「设成 0.275」—— 量纲知识被迫外泄给调用方。",
    },
    {
        "id": "press-button",
        "human": "点击面板上的按钮（configButton）",
        "ui_entry": "ButtonWidget::onButton → configButton 回调",
        "backend_fn": "Module 里的 button 回调（插件自定义）",
        "programmable": "通用做法：走 data JSON（见 sample/seq 工具）",
        "status": "partial",
        "note": "各插件的按钮语义不同，通用做法是改 data 字段。"
                "部分按钮直接触发动作（不可从外部调），需逐插件查。",
    },
    {
        "id": "toggle-switch",
        "human": "拨开关切档（configSwitch）",
        "ui_entry": "SwitchWidget / ParamWidget",
        "backend_fn": "ParamQuantity::enumValue 相关 / setDisplayValueString",
        "programmable": "✅ 已能做（set_param 写值）",
        "status": "ready",
        "tools": ["cardinal_set_param"],
        "warning": "⚠️ configSwitch 常见 {0=Unmuted,1=Muted,2=Soloed} —— 0 才是开。"
                   "samplerx8 的 MUTE 编号尚未实测，未硬写。",
    },

    # ---------- 采样 ----------
    {
        "id": "load-sample",
        "human": "右键 sampler → Load sample → 选文件",
        "ui_entry": "plugins/voxglitch/src/SamplerX8/SamplerX8LoadSample.hpp"
                    "（全文 34 行，struct SamplerX8LoadSample : MenuItem）",
        "backend_fn": "SamplerX8LoadSample::fileSelected(module, n, filename)"
                      " → sample_players[n].loadSample(filename) + setRoot(filename)",
        "programmable": "✅ 已做（走「直接收文件名」那条分支，不弹框）",
        "status": "ready",
        "tools": ["cardinal_samples_list", "cardinal_sample_inspect",
                  "cardinal_sample_load", "cardinal_sample_clear"],
        "note": "存盘形态：data.loaded_sample_path_1..8（1 起）+ samples_root_dir；"
                "相对路径风格必须与该模块已有条目一致，否则旧槽静默解析不到。",
    },

    # ---------- 序列器 ----------
    {
        "id": "pianoroll-write-note",
        "human": "在 piano-roll 上点格子放音符 / 拖动改音高 / 拉长改时值",
        "ui_entry": "Rack UI 编辑器（走 ModuleWidget 的 step 回调）",
        "backend_fn": "PatternData::steps[] → dataToJson 时 key 是 `notes`"
                      "（plugins/rcm-modules/src/PianoRoll/PatternData.cpp:235）",
        "programmable": "✅ 已做（改 data JSON）",
        "status": "ready",
        "tools": ["cardinal_seq_read", "cardinal_seq_edit_note"],
        "limitation": "只改文件。运行中改需要编译后的 /module-json handler"
                      "（Engine::moduleFromJson 是现成 public API）",
    },
    {
        "id": "sequencer-run",
        "human": "点 RUN 按钮",
        "ui_entry": "面板上的 RUN 按钮",
        "backend_fn": "data.sequenceRunning（rcm）/ data.running（Starsea）",
        "programmable": "✅ 已做",
        "status": "ready",
        "tools": ["cardinal_seq_set_running"],
        "note": "🔴 加载后不自动开播是李的宪法 ⇒ 默认仍写 false，工具不擅自改。",
    },

    # ---------- 走带 / MIDI ----------
    {
        "id": "transport",
        "human": "看/控走带（小节、拍、BPM、跑带状态）",
        "ui_entry": "面板上的走带显示",
        "backend_fn": "CardinalPluginContext（include/plugincontext.hpp:82-90）"
                      "已有 playing/bar/beat/bpm/tick/tickClock ⇒ 零 hook",
        "programmable": "需要新 C++ handler（数据现成，只差 OSC 入口）",
        "status": "planned",
        "value": "高",
    },
    {
        "id": "midi-out",
        "human": "在 DAW 里弹 MIDI 键盘",
        "ui_entry": "（宿主侧）",
        "backend_fn": "CardinalPluginContext::writeMidiMessage(msg, channel)"
                      "（plugincontext.hpp:100，实现 CardinalCommon.cpp:202-235）",
        "programmable": "需要新 C++ handler",
        "status": "planned",
        "warning": "⚠️ 必须自己设 message.frame >= 0（:208 的 assert）；"
                   "⚠️ bypassed 时提前 return（:204）⇒ 响应要回显 skipped:bypassed",
    },
    {
        "id": "midi-in",
        "human": "（宿主注入 MIDI）",
        "backend_fn": "midi::InputQueue::onMessage 是 public virtual，"
                      "但没有全局注册表能枚举所有 InputQueue",
        "programmable": "需改 src/Rack/src/midi.cpp 加注册表（约 30 行）",
        "status": "blocked",
        "blocker": "Port::driverId/deviceId 在 midi.hpp:203-205 是 private 区",
    },

    # ---------- 看 / 诊断 ----------
    {
        "id": "see-wiring",
        "human": "看着机架理清链路",
        "ui_entry": "（眼睛）",
        "backend_fn": "读 .vcv 的 cables + Cable 字段",
        "programmable": "✅ 已做",
        "status": "ready",
        "tools": ["cardinal_topology"],
    },
    {
        "id": "read-knob-value",
        "human": "看旋钮现在是多少",
        "ui_entry": "面板数字",
        "backend_fn": "ParamQuantity::getDisplayValue()（人眼可读）"
                      " vs getValue()（存储值，不可读）",
        "programmable": "探针已注入源码，未编译",
        "status": "partial",
        "tools": ["cardinal_get_param"],
        "blocker": "需要编译；未编译时返回 probe_not_supported（不假装成功）",
    },
    {
        "id": "see-live-signal",
        "human": "看 LED 亮不亮 / 输出有没有信号",
        "ui_entry": "（眼睛）",
        "backend_fn": "Port::getVoltage / Light::getBrightness（均现成，零 hook）",
        "programmable": "探针已注入源码，未编译",
        "status": "partial",
        "tools": ["cardinal_module_ports", "cardinal_scan_signal", "cardinal_get_light"],
        "blocker": "需要编译",
    },
    {
        "id": "screenshot",
        "human": "看一眼屏幕",
        "ui_entry": "rack::window::generateScreenshot()"
                    "（声明 src/CardinalCommon.hpp:26，实现 override/Window.cpp:906-910）",
        "programmable": "需新 handler；GUI-only（Mini/headless 编译时就没有）",
        "status": "planned",
        "note": "状态机 override/Window.cpp:706-747，:722 glReadPixels，"
                "base64 回调 :588-592；异步约 4 帧，须分块（base64 必超 MTU）",
    },
    {
        "id": "load-patch",
        "human": "File → Load",
        "ui_entry": "patch::Manager::load",
        "programmable": "✅ 已做（收 pax tar + zstd blob）",
        "status": "ready",
        "tools": ["cardinal_load_patch", "cardinal_read_live", "cardinal_save_live"],
        "limitation": "整体替换 ⇒ 抹掉 GUI 未保存的手改，且打断音频。"
                      "运行中增量改要走 add-cable / add-module 那几项。",
    },
    {
        "id": "undo",
        "human": "Ctrl+Z",
        "ui_entry": "history::State::undo",
        "backend_fn": "history::State::undo()（history.cpp:260，public）"
                      " / redo()(:267) / push()(:234) / ComplexAction(history.hpp:52)",
        "programmable": "需要新 C++ handler",
        "status": "planned",
        "value": "高",
        "note": "⚠️ 必须 UI 线程（history 是裸指针无锁）；"
                "GUI 版 OSC 本来就在 UI 线程 pump ⇒ 可直接调。"
                "⚠️ 现有 /param 绕过 history ⇒ 写参数不可撤销，改走 ParamChange 才可撤。",
    },
    {
        "id": "select-module",
        "human": "点选模块",
        "ui_entry": "RackWidget::getSelected()（RackWidget.hpp:92）",
        "programmable": "可读但无意义（AI 不需要「看哪里」）",
        "status": "blocked",
        "blocker": "人类操作用鼠标；AI 的等价物是按 plugin|model 定位，不该模拟选中态",
    },
]

BY_ID = {a["id"]: a for a in ACTIONS}


# ---------------------------------------------------------------- 查询

def list_actions(status: str | None = None, group: str = "") -> dict[str, Any]:
    """列出人类可做的操作，以及每个背后能不能编程调用。"""
    out = []
    for a in ACTIONS:
        if status and a.get("status") != status:
            continue
        out.append({
            "id": a["id"],
            "human": a["human"],
            "ui_entry": a.get("ui_entry", ""),
            "status": a["status"],
            "tools": a.get("tools", []),
            "value": a.get("value", ""),
        })
    counts: dict[str, int] = {}
    for a in ACTIONS:
        counts[a["status"]] = counts.get(a["status"], 0) + 1
    return {
        "total": len(ACTIONS),
        "by_status": counts,
        "actions": out,
        "status_meaning": {
            "ready": "已做成 MCP 工具，可直接调",
            "partial": "只能改文件重载，或依赖未编译的探针（原因见 blocker）",
            "planned": "源码已定位，handler 设计好了，待编译",
            "blocked": "源码层面做不到（原因见 blocker）",
        },
        "principle": (
            "人类在界面上做每件事都有对应的代码落点。"
            "要模拟人类操作，先找那个落点，走它背后那条『不弹对话框』的分支 —— "
            "而不是生成新文件再重载。"
        ),
    }


def detail(action_id: str) -> dict[str, Any]:
    a = BY_ID.get(action_id)
    if not a:
        return {
            "error": f"没有 id={action_id} 这个操作",
            "available": sorted(BY_ID),
        }
    return a


def find_ready() -> dict[str, Any]:
    """只列已经能直接调的 —— 想知道『我现在能干什么』时看这个。"""
    return {
        "ready_actions": [
            {"id": a["id"], "human": a["human"], "tools": a.get("tools", [])}
            for a in ACTIONS if a["status"] == "ready"
        ],
        "count": sum(1 for a in ACTIONS if a["status"] == "ready"),
    }


if __name__ == "__main__":
    import json
    import sys

    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    if cmd == "list":
        print(json.dumps(list_actions(), ensure_ascii=False, indent=2))
    elif cmd == "ready":
        print(json.dumps(find_ready(), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(detail(cmd), ensure_ascii=False, indent=2))