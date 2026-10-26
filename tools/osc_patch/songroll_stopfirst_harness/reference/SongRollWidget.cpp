#include "rack.hpp"
#include "window.hpp"
#include "helpers.hpp"

#include "../plugin.hpp"
#include "SongRollWidget.hpp"
#include "SongRollModule.hpp"
#include "RollArea.hpp"
#include "../Consts.hpp"

using namespace rack;
using namespace SongRoll;

extern Plugin* plugin;

// standalone module for the module browser
// ModelBox::createPreview() 会调 createModuleWidget(NULL)，module 为 NULL 时
// 若直接传给 RollArea 会解引用 NULL 崩溃（浏览器一搜索就崩的根因）。
// static 避免与 PianoRollWidget.cpp 里同名的全局 browserModule 冲突。
static SongRollModule browserModule;

SongRollWidget::SongRollWidget(SongRollModule* module) {
  setModule(module);
  SongRollModule* originalmodule = module;
  module = this->module = module == NULL ? &browserModule : module;

  // 背景色写基类 colourData：BaseWidget::draw() 用的就是它，
  // 若用子类同名成员会导致「同属性画两遍、颜色还不一致」。
  colourData.backgroundHue = 0.33f;
  colourData.backgroundSaturation = 1.f;
  colourData.backgroundLuminosity = 0.25f;

  setPanel(APP->window->loadSvg(asset::plugin(pluginInstance, "res/SongRoll.svg")));

  // 输入：左区 2 列 x 5 行（RESET/RUN/EOP1-3 在 x=16，EOP4-8 在 x=52）
  addInput(createInput<PJ301MPort>(Vec(16, 45),  originalmodule, SongRollModule::RESET_INPUT));
  addInput(createInput<PJ301MPort>(Vec(16, 100), originalmodule, SongRollModule::RUN_INPUT));
  addInput(createInput<PJ301MPort>(Vec(16, 155), originalmodule, SongRollModule::EOP_INPUT + 0));
  addInput(createInput<PJ301MPort>(Vec(16, 210), originalmodule, SongRollModule::EOP_INPUT + 1));
  addInput(createInput<PJ301MPort>(Vec(16, 265), originalmodule, SongRollModule::EOP_INPUT + 2));
  addInput(createInput<PJ301MPort>(Vec(52, 45),  originalmodule, SongRollModule::EOP_INPUT + 3));
  addInput(createInput<PJ301MPort>(Vec(52, 100), originalmodule, SongRollModule::EOP_INPUT + 4));
  addInput(createInput<PJ301MPort>(Vec(52, 155), originalmodule, SongRollModule::EOP_INPUT + 5));
  addInput(createInput<PJ301MPort>(Vec(52, 210), originalmodule, SongRollModule::EOP_INPUT + 6));
  addInput(createInput<PJ301MPort>(Vec(52, 265), originalmodule, SongRollModule::EOP_INPUT + 7));

  // 输出：右区 2 列 x 6 行（P1-6 在 x=530，P7/P8/SEC_END/SEC_NUM/SONG_END 在 x=570）
  addOutput(createOutput<PJ301MPort>(Vec(530, 40),  originalmodule, SongRollModule::PATTERN_OUTPUT + 0));
  addOutput(createOutput<PJ301MPort>(Vec(530, 84),  originalmodule, SongRollModule::PATTERN_OUTPUT + 1));
  addOutput(createOutput<PJ301MPort>(Vec(530, 128), originalmodule, SongRollModule::PATTERN_OUTPUT + 2));
  addOutput(createOutput<PJ301MPort>(Vec(530, 172), originalmodule, SongRollModule::PATTERN_OUTPUT + 3));
  addOutput(createOutput<PJ301MPort>(Vec(530, 216), originalmodule, SongRollModule::PATTERN_OUTPUT + 4));
  addOutput(createOutput<PJ301MPort>(Vec(530, 260), originalmodule, SongRollModule::PATTERN_OUTPUT + 5));
  addOutput(createOutput<PJ301MPort>(Vec(570, 40),  originalmodule, SongRollModule::PATTERN_OUTPUT + 6));
  addOutput(createOutput<PJ301MPort>(Vec(570, 84),  originalmodule, SongRollModule::PATTERN_OUTPUT + 7));
  addOutput(createOutput<PJ301MPort>(Vec(570, 128), originalmodule, SongRollModule::SECTION_END_OUTPUT));
  addOutput(createOutput<PJ301MPort>(Vec(570, 172), originalmodule, SongRollModule::SECTION_NUM_OUTPUT));
  addOutput(createOutput<PJ301MPort>(Vec(570, 216), originalmodule, SongRollModule::SONG_END_OUTPUT));

  auto* rollArea = new RollArea(getRollArea(), module);
  addChild(rollArea);
}

void SongRollWidget::appendContextMenu(Menu* menu) {
}

Rect SongRollWidget::getRollArea() {
  return Rect(Vec(74, 30), Vec(434, 270));
}

void SongRollWidget::drawBackgroundColour(NVGcontext* ctx) {
  nvgBeginPath(ctx);
  nvgFillColor(ctx, nvgHSL(colourData.backgroundHue, colourData.backgroundSaturation,
                            colourData.backgroundLuminosity));
  nvgRect(ctx, 0, 0, box.size.x, box.size.y);
  nvgFill(ctx);
}

void SongRollWidget::drawPatternEditors(NVGcontext* ctx) {
  Rect rollArea = getRollArea();
  static const float PATTERN_AREA_HEIGHT = 1;
  static const float leftMargin = 0;
  Rect patternArea(Vec(rollArea.pos.x + leftMargin, rollArea.pos.y + rollArea.size.y - (rollArea.size.y * PATTERN_AREA_HEIGHT)), Vec(rollArea.size.x - leftMargin, rollArea.size.y * PATTERN_AREA_HEIGHT));

  nvgBeginPath(ctx);
  nvgFillColor(ctx, nvgRGBA(1, 1, 1, 1));
  nvgRect(ctx, rollArea.pos.x, rollArea.pos.y, rollArea.size.x, rollArea.size.y);
  nvgFill(ctx);

  float channelWidth = patternArea.size.x / SONGROLL_CHANNELS;

  nvgSave(ctx);
  nvgScissor(ctx, patternArea.pos.x, patternArea.pos.y, patternArea.size.x, patternArea.size.y);

  for (int i = 1; i < SONGROLL_CHANNELS; i++) {
    nvgBeginPath(ctx);
    nvgMoveTo(ctx, patternArea.pos.x + (channelWidth * i), patternArea.pos.y);
    nvgLineTo(ctx, patternArea.pos.x + (channelWidth * i), patternArea.pos.y + patternArea.size.y);
    nvgStrokeWidth(ctx, 1.f);
    nvgStrokeColor(ctx, NV_YELLOW_H);
    nvgStroke(ctx);
  }

  nvgRestore(ctx);
}

void SongRollWidget::draw(const DrawArgs& args) {
  drawBackgroundColour(args.vg);

  BaseWidget::draw(args);

  drawPatternEditors(args.vg);
}
