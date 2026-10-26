#pragma once
#include "rack.hpp"

using namespace rack;

namespace SongRoll {

  struct SongRollModule;

  // -- Pattern -- 标签 + −/数字/+（点按直接改 data 并 push undo）
  class PatternControlWidget : public Widget {
  public:
    int pattern = 0;
    SongRollModule* module = nullptr;
    int channel = 0;

    PatternControlWidget();

    void draw(const DrawArgs& args) override;
    void onButton(const event::Button& e) override;
  };

}
