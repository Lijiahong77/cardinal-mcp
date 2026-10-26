#pragma once
#include "rack.hpp"

using namespace rack;

namespace SongRoll {

  struct SongRollModule;
  class PatternHeaderWidget;
  class PatternControlWidget;
  class RepeatControlWidget;
  class ClockDivControlWidget;

  // 每通道一条纵向 slice：圆弧头 + Pattern + Repeats + ClockDiv。
  // 编辑器跟随 engine 的 currentSection（改的就是正在播的那段）。
  class PatternControllerSlice : public Widget {
  public:
    const int channel;
    SongRollModule* module;
    SequentialLayout* layout;
    PatternHeaderWidget* header;
    PatternControlWidget* pattern;
    RepeatControlWidget* repeats;
    ClockDivControlWidget* clock_div;

    PatternControllerSlice(int channel, SongRollModule* module);

    void step() override;
    void draw(const DrawArgs& args) override;

  private:
    int displayedSection = -1;
  };

}
