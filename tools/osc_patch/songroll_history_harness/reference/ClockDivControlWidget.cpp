#include "ClockDivControlWidget.hpp"
#include "SongRollModule.hpp"
#include "SongRollData.hpp"
#include "../Consts.hpp"

namespace SongRoll {

  ClockDivControlWidget::ClockDivControlWidget() {}

  void ClockDivControlWidget::draw(const DrawArgs& args) {
    NVGcontext* ctx = args.vg;
    float y = 1;

    nvgBeginPath(ctx);
    nvgFontSize(ctx, 10);
    nvgTextAlign(ctx, NVG_ALIGN_CENTER + NVG_ALIGN_TOP);
    nvgFillColor(ctx, NV_YELLOW);
    nvgText(ctx, box.size.x * 0.5, y, "-- Clock Div --", NULL);

    y += 10;

    float clockDivHeight = 48;
    float hcenter = box.size.x * 0.5;

    nvgBeginPath(ctx);
    nvgStrokeColor(ctx, NV_YELLOW_H);
    nvgStrokeWidth(ctx, 1.0f);
    nvgRoundedRect(ctx, 8, y, box.size.x - 16, clockDivHeight, 4);
    nvgStroke(ctx);

    nvgBeginPath(ctx);
    nvgStrokeColor(ctx, NV_YELLOW_H);
    nvgStrokeWidth(ctx, 2.0f);
    nvgFillColor(ctx, NV_BLACK);
    nvgRect(ctx, 9, y + (clockDivHeight / 2) - 10, box.size.x - 18, 20);
    nvgFill(ctx);

    nvgBeginPath(ctx);
    nvgStrokeColor(ctx, NV_YELLOW_H);
    nvgStrokeWidth(ctx, 1.0f);
    nvgMoveTo(ctx, 8, y + (clockDivHeight / 2) - 10);
    nvgLineTo(ctx, 8 + box.size.x - 16, y + (clockDivHeight / 2) - 10);
    nvgStroke(ctx);

    nvgBeginPath(ctx);
    nvgStrokeColor(ctx, NV_YELLOW_H);
    nvgStrokeWidth(ctx, 1.0f);
    nvgMoveTo(ctx, 8, y + (clockDivHeight / 2) - 10 + 20);
    nvgLineTo(ctx, 8 + box.size.x - 16, y + (clockDivHeight / 2) - 10 + 20);
    nvgStroke(ctx);

    nvgBeginPath(ctx);
    nvgStrokeColor(ctx, NV_YELLOW_H);
    nvgStrokeWidth(ctx, 3.0f);
    nvgMoveTo(ctx, hcenter - 8, y + 10);
    nvgLineTo(ctx, hcenter, y + 4);
    nvgLineTo(ctx, hcenter + 8, y + 10);
    nvgStroke(ctx);

    nvgBeginPath(ctx);
    nvgStrokeColor(ctx, NV_YELLOW_H);
    nvgStrokeWidth(ctx, 3.0f);
    nvgMoveTo(ctx, hcenter - 8, y + clockDivHeight - 10);
    nvgLineTo(ctx, hcenter, y + clockDivHeight - 4);
    nvgLineTo(ctx, hcenter + 8, y + clockDivHeight - 10);
    nvgStroke(ctx);


    char clockDivBuffer[100];
    if (clock_div > 0) {
      snprintf(clockDivBuffer, sizeof(clockDivBuffer), "/ %d", clock_div);
    } else {
      snprintf(clockDivBuffer, sizeof(clockDivBuffer), "off");
    }

    nvgBeginPath(ctx);
    nvgFontSize(ctx, 12);
    nvgTextAlign(ctx, NVG_ALIGN_CENTER + NVG_ALIGN_MIDDLE);
    nvgFillColor(ctx, NV_YELLOW);
    nvgText(ctx, hcenter, y + (clockDivHeight / 2), clockDivBuffer, NULL);

    y += clockDivHeight;

    box.size.y = y;
  }

  void ClockDivControlWidget::onButton(const event::Button& e) {
    if (e.action != GLFW_PRESS || e.button != GLFW_MOUSE_BUTTON_LEFT) {
      Widget::onButton(e);
      return;
    }
    e.consume(this);

    Rect minus(Vec(0, 44), Vec(box.size.x, 20));
    Rect plus(Vec(0, 10), Vec(box.size.x, 20));

    if (!minus.contains(e.pos) && !plus.contains(e.pos))
      return;
    if (module == nullptr)
      return;

    SongRollData& data = module->songRollData;
    if (data.sections.empty())
      return;
    int sec = clamp(module->currentSection, 0, int(data.sections.size()) - 1);

    // undo/redo may happen before another UI step; data is authoritative.
    clock_div = data.sections[sec].channels[channel].clock_div;
    json_t* oldModuleJ = module->toJson();
    if (minus.contains(e.pos))
      clock_div = clamp(clock_div - 1, 0, 64);
    else if (plus.contains(e.pos))
      clock_div = clamp(clock_div + 1, 0, 64);
    data.sections[sec].channels[channel].clock_div = clock_div;
    json_t* newModuleJ = module->toJson();

    history::ModuleChange* h = new history::ModuleChange;
    h->name = "change clock div";
    h->moduleId = module->id;
    h->oldModuleJ = oldModuleJ;
    h->newModuleJ = newModuleJ;
    APP->history->push(h);
  }

}
