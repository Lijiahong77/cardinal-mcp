#pragma once
#include <vector>

#include "rack.hpp"

// 通道数（原作者 Section 构造即 resize(8)；对应 MiniArranger 的 4+4 轨）
#define SONGROLL_CHANNELS 8

namespace SongRoll {


  class ChannelConfig {
  public:
    enum eRepeatMode {
      FREE,
      REPEATS,
      LIMIT
    };

    int pattern = 1;
    int repeats = 1;
    eRepeatMode repeat_mode = eRepeatMode::REPEATS;
    int clock_div = 1;
  };

  class Section {
  public:
    std::vector<ChannelConfig> channels;
    Section();
  };

  class SongRollData {
  public:
    std::vector<Section> sections;
    SongRollData();
    void reset();
    json_t *toJson();
    void fromJson(json_t *rootJ);
  };

}
