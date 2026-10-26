#include "PatternControlWidget.hpp"
#include "SongRollModule.hpp"
#include "SongRollData.hpp"
#include "../Consts.hpp"

namespace SongRoll {

  PatternControlWidget::PatternControlWidget() {}

  void PatternControlWidget::draw(const DrawArgs& args) {
    NVGcontext* ctx = args.vg;
    float y = 1;

    nvgBeginPath(ctx);
    nvgFontSize(ctx, 10);
    nvgTextAlign(ctx, NVG_ALIGN_CENTER + NVG_ALIGN_TOP);
    nvgFillColor(ctx, NV_YELLOW);
    nvgText(ctx, box.size.x * 0.5, y, "-- Pattern --", NULL);

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

    char patternBuffer[100];
    snprintf(patternBuffer, sizeof(patternBuffer), "%d", pattern + 1);

    nvgBeginPath(ctx);
    nvgFontSize(ctx, 14);
    nvgTextAlign(ctx, NVG_ALIGN_CENTER + NVG_ALIGN_TOP);
    nvgFillColor(ctx, NV_YELLOW);
    nvgText(ctx, box.size.x * 0.5, y, patternBuffer, NULL);

    y += 14;

    box.size.y = y;
  }

  void PatternControlWidget::onButton(const event::Button& e) {
    if (e.action != GLFW_PRESS || e.button != GLFW_MOUSE_BUTTON_LEFT) {
      Widget::onButton(e);
      return;
    }
    e.consume(this);

    Rect minus(Vec(0, 10), Vec(box.size.x * 0.40, 14));
    Rect plus(Vec(box.size.x * 0.60, 10), Vec(box.size.x * 0.40, 14));

    if (!minus.contains(e.pos) && !plus.contains(e.pos))
      return;
    if (module == nullptr)
      return;

    std::unique_lock<std::recursive_mutex> lock(module->stateMutex);
    SongRollData& data = module->songRollData;
    if (data.sections.empty())
      return;
    int sec = clamp(module->currentSection, 0, int(data.sections.size()) - 1);

    // engine field is 1-based (1..64); widget field is 0-based (0..63)
    int oldPattern = data.sections[sec].channels[channel].pattern;
    int newPattern = oldPattern;
    if (minus.contains(e.pos))
      newPattern = clamp(oldPattern - 1, 1, 64);
    else
      newPattern = clamp(oldPattern + 1, 1, 64);

    json_t* oldModuleJ = module->toJson();
    data.sections[sec].channels[channel].pattern = newPattern;
    pattern = newPattern - 1;   // widget display field 0-based
    module->stopFirst();
    json_t* newModuleJ = module->toJson();
    lock.unlock();

    history::ModuleChange* h = new history::ModuleChange;
    h->name = "change pattern";
    h->moduleId = module->id;
    h->oldModuleJ = oldModuleJ;
    h->newModuleJ = newModuleJ;
    APP->history->push(h);
  }

}
