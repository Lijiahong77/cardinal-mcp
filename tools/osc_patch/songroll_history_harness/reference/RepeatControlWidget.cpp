#include "RepeatControlWidget.hpp"
#include "SongRollModule.hpp"
#include "SongRollData.hpp"
#include "../Consts.hpp"

namespace SongRoll {

  RepeatControlWidget::RepeatControlWidget() {}

  void RepeatControlWidget::draw(const DrawArgs& args) {
    NVGcontext* ctx = args.vg;
    float y = 1;

    nvgBeginPath(ctx);
    nvgFontSize(ctx, 10);
    nvgTextAlign(ctx, NVG_ALIGN_CENTER + NVG_ALIGN_TOP);
    nvgFillColor(ctx, NV_YELLOW);
    nvgText(ctx, box.size.x * 0.5, y, "-- Repeats --", NULL);

    y += 10;

    nvgBeginPath(ctx);
    nvgFontSize(ctx, 14);
    nvgTextAlign(ctx, NVG_ALIGN_CENTER + NVG_ALIGN_TOP);
    nvgFillColor(ctx, NV_YELLOW);
    nvgText(ctx, box.size.x * 0.25, y, "\xe2", NULL);

    nvgBeginPath(ctx);
    nvgFontSize(ctx, 14);
    nvgTextAlign(ctx, NVG_ALIGN_CENTER + NVG_ALIGN_TOP);
    nvgFillColor(ctx, NV_YELLOW);
    nvgText(ctx, box.size.x * 0.75, y, "+", NULL);

    char repeatBuffer[100];
    snprintf(repeatBuffer, sizeof(repeatBuffer), "%d", repeats);

    nvgBeginPath(ctx);
    nvgFontSize(ctx, 14);
    nvgTextAlign(ctx, NVG_ALIGN_CENTER + NVG_ALIGN_TOP);
    nvgFillColor(ctx, NV_YELLOW);
    nvgText(ctx, box.size.x * 0.5, y, repeatBuffer, NULL);

    y += 16;

    nvgBeginPath(ctx);
    nvgFontSize(ctx, 12);
    nvgTextAlign(ctx, NVG_ALIGN_CENTER + NVG_ALIGN_TOP);
    nvgFillColor(ctx, NV_YELLOW);
    switch (repeat_mode) {
      case ChannelConfig::FREE:
        nvgText(ctx, box.size.x * 0.5, y, "no limit", NULL);
        break;
      case ChannelConfig::REPEATS:
        nvgText(ctx, box.size.x * 0.5, y, "at least", NULL);
        break;
      case ChannelConfig::LIMIT:
        nvgText(ctx, box.size.x * 0.5, y, "at most", NULL);
        break;
    }

    nvgBeginPath(ctx);
    nvgStrokeColor(ctx, NV_YELLOW_H);
    nvgRoundedRect(ctx, 8, y, box.size.x - 16, 12, 2);
    nvgStroke(ctx);

    y += 14;
    box.size.y = y;
  }

  void RepeatControlWidget::onButton(const event::Button& e) {
    if (e.action != GLFW_PRESS || e.button != GLFW_MOUSE_BUTTON_LEFT) {
      Widget::onButton(e);
      return;
    }
    e.consume(this);

    Rect minus(Vec(0, 10), Vec(box.size.x * 0.40, 14));
    Rect plus(Vec(box.size.x * 0.60, 10), Vec(box.size.x * 0.40, 14));
    Rect mode(Vec(0, 26), Vec(box.size.x, 26));

    if (!minus.contains(e.pos) && !plus.contains(e.pos) && !mode.contains(e.pos))
      return;
    if (module == nullptr)
      return;

    SongRollData& data = module->songRollData;
    if (data.sections.empty())
      return;
    int sec = clamp(module->currentSection, 0, int(data.sections.size()) - 1);

    // undo/redo may happen before another UI step; data is authoritative.
    repeats = data.sections[sec].channels[channel].repeats;
    repeat_mode = int(data.sections[sec].channels[channel].repeat_mode);
    json_t* oldModuleJ = module->toJson();
    if (minus.contains(e.pos))
      repeats = clamp(repeats - 1, 1, 64);
    else if (plus.contains(e.pos))
      repeats = clamp(repeats + 1, 1, 64);
    else if (mode.contains(e.pos))
      repeat_mode = (repeat_mode + 1) % 3;
    data.sections[sec].channels[channel].repeats = repeats;
    data.sections[sec].channels[channel].repeat_mode = ChannelConfig::eRepeatMode(repeat_mode);
    json_t* newModuleJ = module->toJson();

    history::ModuleChange* h = new history::ModuleChange;
    h->name = "change repeats";
    h->moduleId = module->id;
    h->oldModuleJ = oldModuleJ;
    h->newModuleJ = newModuleJ;
    APP->history->push(h);
  }

}
