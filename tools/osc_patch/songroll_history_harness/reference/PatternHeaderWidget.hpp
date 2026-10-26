#pragma once
#include "rack.hpp"

using namespace rack;

namespace SongRoll {

  // 圆弧头：亮几段 = repeats 进度，中间数字 = pattern 号
  class PatternHeaderWidget : public Widget {
  public:
    int repeats = 1;
    int repeats_completed = 0;
    int pattern = 0;
    bool active = true;

    PatternHeaderWidget(int repeats, int repeats_completed, int pattern);

    void draw(const DrawArgs& args) override;
  };

}
