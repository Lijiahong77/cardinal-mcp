#pragma once
#include "rack.hpp"
#include "../BaseWidget.hpp"

using namespace rack;

namespace SongRoll {

  struct SongRollModule;

  struct SongRollWidget : BaseWidget {
    SongRollModule* module;

    SongRollWidget(SongRollModule* module);

    Rect getRollArea();

    void drawBackgroundColour(NVGcontext* vg);
    void drawPatternEditors(NVGcontext* vg);

    void appendContextMenu(Menu* menu) override;
    void draw(const DrawArgs& args) override;
  };

}
