#include "RollArea.hpp"
#include "PatternControllerSlice.hpp"
#include "SongRollModule.hpp"
#include "SongRollData.hpp"

namespace SongRoll {

  RollArea::RollArea(Rect box, SongRollModule* module) : module(module) {
    this->box = box;

    int numChannels = SONGROLL_CHANNELS;
    if (module) {
      std::lock_guard<std::recursive_mutex> lock(module->stateMutex);
      if (module->songRollData.sections.empty())
        return;
      numChannels = int(module->songRollData.sections[0].channels.size());
    }
    const float channelWidth = box.size.x / numChannels;
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
