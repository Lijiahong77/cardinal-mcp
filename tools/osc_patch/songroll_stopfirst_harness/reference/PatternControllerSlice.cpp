#include "PatternControllerSlice.hpp"
#include "PatternHeaderWidget.hpp"
#include "PatternControlWidget.hpp"
#include "RepeatControlWidget.hpp"
#include "ClockDivControlWidget.hpp"
#include "SongRollModule.hpp"
#include "SongRollData.hpp"

namespace SongRoll {

  PatternControllerSlice::PatternControllerSlice(int channel, SongRollModule* module) : channel(channel), module(module) {
    layout = new SequentialLayout;
    layout->orientation = SequentialLayout::VERTICAL_ORIENTATION;
    layout->alignment = SequentialLayout::LEFT_ALIGNMENT;
    layout->spacing = Vec(0, 10);

    header = new PatternHeaderWidget(1, 0, 0);
    layout->addChild(header);

    pattern = new PatternControlWidget;
    pattern->module = module;
    pattern->channel = channel;
    layout->addChild(pattern);

    repeats = new RepeatControlWidget;
    repeats->module = module;
    repeats->channel = channel;
    layout->addChild(repeats);

    clock_div = new ClockDivControlWidget;
    clock_div->module = module;
    clock_div->channel = channel;
    layout->addChild(clock_div);

    addChild(layout);
  }

  void PatternControllerSlice::step() {
    if (module == nullptr) {
      Widget::step();
      return;
    }
    std::unique_lock<std::recursive_mutex> lock(module->stateMutex);
    SongRollData& data = module->songRollData;
    if (data.sections.empty()) {
      lock.unlock();
      Widget::step();
      return;
    }
    int sec = clamp(module->currentSection, 0, int(data.sections.size()) - 1);

    // 每帧单向从 data 刷新显示；同段 undo/redo 或 JSON 替换也会改值。
    {
      displayedSection = sec;
      const ChannelConfig& ch = data.sections[sec].channels[channel];
      pattern->pattern = ch.pattern - 1;   // engine 1-based -> widget 0-based
      repeats->repeats = ch.repeats;
      repeats->repeat_mode = int(ch.repeat_mode);
      clock_div->clock_div = ch.clock_div;
    }

    // header 每帧刷新（显示当前段的 pattern 号与 repeats 进度）
    const ChannelConfig& ch = data.sections[sec].channels[channel];
    header->pattern = ch.pattern;
    header->repeats = std::max(1, ch.repeats);
    header->repeats_completed = std::max(0, ch.repeats - module->repeatsLeft[channel]);
    header->active = true;
    lock.unlock(); // No module references escape into layout/child steps.

    for (auto* widget : layout->children) {
      widget->box.size.x = box.size.x;
    }
    layout->box.size.y = box.size.y;

    Widget::step();
  }

  void PatternControllerSlice::draw(const DrawArgs& args) {
    Widget::draw(args);
  }

}
