#pragma once
#include "rack.hpp"

using namespace rack;

namespace SongRoll {

  class SongRollModule;

  // 卷帘区：8 个通道 slice 横排（对应 8 个 PATTERN# 输出）
  class RollArea : public Widget {
  public:
    SongRollModule* module;

    RollArea(Rect box, SongRollModule* module);
  };

}
