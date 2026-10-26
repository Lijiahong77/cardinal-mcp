#include "rack.hpp"

#include "SongRollData.hpp"
#include "Transport.hpp"

#include <algorithm>
#include <mutex>
#include <atomic>

namespace SongRoll {

  // SongRoll = 排歌层：吃各通道的 end-of-pattern 触发，按 sections[] 推进，
  // 输出每通道的 pattern 号（V/Oct 语义，PianoRoll PATTERN_IN 直接吃）。
  //
  // 端口布局（阶段 2；原作者 Rack 1 设计的 CLOCK/PATTERN/RUN/RECORD/VOCT...
  // 已废——那时它想当完整序列器，现在定位是纯段推进器）：
  //   IN  RESET(边沿回第0段) / RUN(边沿翻转) / EOP_INPUT+0..7(各通道 EOP 10V 脉冲)
  //   OUT PATTERN_OUTPUT+0..7(段内各通道 pattern 号) / SECTION_END(段边界脉冲)
  //       SECTION_NUM(当前段号, 1V/段【 Arrange START 语义待核实】) / SONG_END(回卷脉冲)
  struct SongRollModule : rack::Module {
    enum ParamIds {
      NUM_PARAMS
    };
    enum InputIds {
      RESET_INPUT,
      RUN_INPUT,
      EOP_INPUT, EOP_INPUT2, EOP_INPUT3, EOP_INPUT4,
      EOP_INPUT5, EOP_INPUT6, EOP_INPUT7, EOP_INPUT8,
      NUM_INPUTS
    };
    enum OutputIds {
      PATTERN_OUTPUT, PATTERN_OUTPUT2, PATTERN_OUTPUT3, PATTERN_OUTPUT4,
      PATTERN_OUTPUT5, PATTERN_OUTPUT6, PATTERN_OUTPUT7, PATTERN_OUTPUT8,
      SECTION_END_OUTPUT,
      SECTION_NUM_OUTPUT,
      SONG_END_OUTPUT,
      NUM_OUTPUTS
    };
    enum LightIds {
      NUM_LIGHTS
    };

    // All arrangement/runtime readers use this mutex. Never call Engine while held.
    // Recursive for nested helpers and Module::toJson -> dataToJson in UI transactions.
    std::recursive_mutex stateMutex;
    // UI publishes cancellation; only a mutex-owning DSP sample acknowledges it.
    std::atomic<bool> eventCancelPending{false};
    // DSP-owned last event levels, never read or written by UI/JSON/reset.
    bool sectionEndHigh = false;
    bool songEndHigh = false;
    bool runNeedsLow = false;
    bool eopNeedsLow[SONGROLL_CHANNELS] = {};

    rack::dsp::SchmittTrigger resetInputTrigger;
    rack::dsp::SchmittTrigger runInputTrigger;
    rack::dsp::SchmittTrigger eopTrigger[SONGROLL_CHANNELS];
    rack::dsp::PulseGenerator sectionEndPulse;
    rack::dsp::PulseGenerator songEndPulse;

    SongRollData songRollData;
    Transport transport;

    bool running = false;
    int currentSection = 0;
    int repeatsLeft[SONGROLL_CHANNELS];

    SongRollModule();

    void process(const ProcessArgs &args) override;
    void onReset(const ResetEvent &e) override;

    json_t *dataToJson() override;
    void dataFromJson(json_t *rootJ) override;

    void stopFirst();
    void enterSection(int idx);
    void advanceSection();

  private:
    void resetState();
  };

}
