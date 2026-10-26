#pragma once
#include "rack.hpp"

using namespace rack;

namespace SongRoll {

  struct SongRollModule;

  // -- Repeats -- 标签 + −/数字/+ + 模式行（FREE/REPEATS/LIMIT 点击轮换）
  class RepeatControlWidget : public Widget {
  public:
    int repeats = 1;
    int repeats_complete = 0;
    int repeat_mode = 1;
    SongRollModule* module = nullptr;
    int channel = 0;

    RepeatControlWidget();

    void draw(const DrawArgs& args) override;
    void onButton(const event::Button& e) override;
  };

}
