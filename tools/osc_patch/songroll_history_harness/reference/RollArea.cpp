#include "RollArea.hpp"
#include "PatternControllerSlice.hpp"
#include "SongRollModule.hpp"
#include "SongRollData.hpp"

namespace SongRoll {

  RollArea::RollArea(Rect box, SongRollModule* module) : module(module) {
    this->box = box;

    SongRollData& data = module->songRollData;
    if (data.sections.empty())
      return;

    const int numChannels = (int)data.sections[0].channels.size();
    const float channelWidth = box.size.x / data.sections[0].channels.size();
    for (int i = 0; i < numChannels; i++) {
      auto* slice = new PatternControllerSlice(i, module);
      slice->box.pos.x = (channelWidth * i);
      slice->box.pos.y = 0;
      slice->box.size.x = channelWidth;
      slice->box.size.y = box.size.y;

      addChild(slice);
    }
  }

}
