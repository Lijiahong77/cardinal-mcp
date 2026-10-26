#pragma once
#include "rack.hpp"

using namespace rack;

namespace SongRoll {

  struct SongRollModule;

  // -- Clock Div -- 上下箭头 + /N 显示（0 = off）
  class ClockDivControlWidget : public Widget {
  public:
    int clock_div = 1;
    SongRollModule* module = nullptr;
    int channel = 0;

    ClockDivControlWidget();

    void draw(const DrawArgs& args) override;
    void onButton(const event::Button& e) override;
  };

}
