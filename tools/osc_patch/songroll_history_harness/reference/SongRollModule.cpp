#include "SongRollModule.hpp"

using namespace rack;
using namespace SongRoll;

void SongRollModule::resetState() {
  transport.reset();
  songRollData.reset();
  running = false;
  enterSection(0);
}

SongRollModule::SongRollModule() : Module(NUM_PARAMS, NUM_INPUTS, NUM_OUTPUTS, NUM_LIGHTS), transport(&songRollData) {
  // Port names + descriptions. These are what PortTooltip shows on hover.
  configInput(RESET_INPUT, "Reset")->description = "Trigger jumps back to section 1";
  configInput(RUN_INPUT, "Run")->description = "Trigger toggles run / stop";
  for (int c = 0; c < SONGROLL_CHANNELS; ++c) {
    configInput(EOP_INPUT + c, string::f("EOP %d", c + 1))
        ->description = string::f("End-of-pattern trigger from channel %d (PianoRoll EOP out)", c + 1);
  }
  for (int c = 0; c < SONGROLL_CHANNELS; ++c) {
    configOutput(PATTERN_OUTPUT + c, string::f("Pattern %d", c + 1))
        ->description = string::f("Pattern number for channel %d, 1/12V per pattern (0V = pattern 1, 1/12V = pattern 2 ...)", c + 1);
  }
  configOutput(SECTION_END_OUTPUT, "Section end")->description = "10V pulse at every section boundary";
  configOutput(SECTION_NUM_OUTPUT, "Section num")->description = "Current section number (1V per section)";
  configOutput(SONG_END_OUTPUT, "Song end")->description = "10V pulse when the song wraps back to section 1";

  resetState();
}

void SongRollModule::onReset(const ResetEvent &e) {
  resetState();
}

void SongRollModule::enterSection(int idx) {
  if (songRollData.sections.empty()) {
    currentSection = 0;
    for (int c = 0; c < SONGROLL_CHANNELS; ++c)
      repeatsLeft[c] = 1;
    return;
  }
  currentSection = clamp(idx, 0, int(songRollData.sections.size()) - 1);
  const Section &sec = songRollData.sections[currentSection];
  for (int c = 0; c < SONGROLL_CHANNELS; ++c)
    repeatsLeft[c] = std::max(1, sec.channels[c].repeats);
  // 切段当帧刷新输出（PianoRoll 下一帧就吃到新 pattern 号）
  for (int c = 0; c < SONGROLL_CHANNELS; ++c)
    // PATTERN_OUTPUT 走 PianoRoll 的 PATTERN_INPUT 语义：
        //   quantizePitch(v) - 48 == round(v*12)  =>  0V = pattern 0（1-based 的 pattern 1）
        //   每 1/12 V 递增一个 pattern；不能加 48/12 的 C4 偏移，否则 pattern 号整体 +48
        outputs[PATTERN_OUTPUT + c].setVoltage(float(sec.channels[c].pattern - 1) / 12.f);
  outputs[SECTION_NUM_OUTPUT].setVoltage(float(currentSection));
}

void SongRollModule::advanceSection() {
  sectionEndPulse.trigger();
  int next = currentSection + 1;
  if (next >= int(songRollData.sections.size())) {
    songEndPulse.trigger();
    next = 0;
  }
  enterSection(next);
}

void SongRollModule::process(const ProcessArgs &args) {
  // RUN：边沿翻转（照 PianoRoll transport.toggleRun）
  if (runInputTrigger.process(inputs[RUN_INPUT].getVoltage()))
    running = !running;

  // RESET：边沿回第 0 段（不停 running，照 Hapax）
  if (resetInputTrigger.process(inputs[RESET_INPUT].getVoltage()))
    enterSection(0);

  if (songRollData.sections.empty()) {
    running = false;
    for (int c = 0; c < SONGROLL_CHANNELS; ++c) {
      outputs[PATTERN_OUTPUT + c].setChannels(1);
      outputs[PATTERN_OUTPUT + c].setVoltage(0.f);
    }
    outputs[SECTION_END_OUTPUT].setChannels(1);
    outputs[SECTION_END_OUTPUT].setVoltage(0.f);
    outputs[SONG_END_OUTPUT].setChannels(1);
    outputs[SONG_END_OUTPUT].setVoltage(0.f);
    outputs[SECTION_NUM_OUTPUT].setChannels(1);
    outputs[SECTION_NUM_OUTPUT].setVoltage(0.f);
    return;
  }

  // 每帧刷新 PATTERN 输出：Rack 的 Engine_updateConnected() 会在任何 cable
  // 增删时把「未接线的端口」电压全部清零（Port_setDisconnected），而切段
  // 之间不会有 enterSection() 来重设，输出就会永久停在 0V。每帧重写可自愈。
  {
    const Section &sec = songRollData.sections[currentSection];
    for (int c = 0; c < SONGROLL_CHANNELS; ++c) {
      outputs[PATTERN_OUTPUT + c].setChannels(1);
      // PATTERN_OUTPUT 走 PianoRoll 的 PATTERN_INPUT 语义：
        //   quantizePitch(v) - 48 == round(v*12)  =>  0V = pattern 0（1-based 的 pattern 1）
        //   每 1/12 V 递增一个 pattern；不能加 48/12 的 C4 偏移，否则 pattern 号整体 +48
        outputs[PATTERN_OUTPUT + c].setVoltage(float(sec.channels[c].pattern - 1) / 12.f);
    }
  }
  outputs[SECTION_END_OUTPUT].setChannels(1);
  outputs[SECTION_NUM_OUTPUT].setChannels(1);
  outputs[SONG_END_OUTPUT].setChannels(1);

  if (running) {
    Section &sec = songRollData.sections[currentSection];
    bool allDone = true;
    for (int c = 0; c < SONGROLL_CHANNELS; ++c) {
      ChannelConfig &ch = sec.channels[c];
      // FREE 模式：该通道不自行完成（段挂起等手动推进）——阶段 3 补 LIMIT 完整语义
      if (ch.repeat_mode == ChannelConfig::REPEATS &&
          eopTrigger[c].process(inputs[EOP_INPUT + c].getVoltage())) {
        repeatsLeft[c] -= 1;
      }
      if (repeatsLeft[c] > 0)
        allDone = false;
    }
    if (allDone)
      advanceSection();
  }

  outputs[SECTION_END_OUTPUT].setVoltage(sectionEndPulse.process(args.sampleTime) ? 10.f : 0.f);
  outputs[SONG_END_OUTPUT].setVoltage(songEndPulse.process(args.sampleTime) ? 10.f : 0.f);
  outputs[SECTION_NUM_OUTPUT].setVoltage(float(currentSection));
}

json_t *SongRollModule::dataToJson() {
  json_t *root = json_object();
  json_object_set_new(root, "songRoll", songRollData.toJson());
  json_object_set_new(root, "running", json_boolean(running));
  json_object_set_new(root, "currentSection", json_integer(currentSection));
  return root;
}

void SongRollModule::dataFromJson(json_t *rootJ) {
  if (rootJ == nullptr)
    return;
  json_t *sr = json_object_get(rootJ, "songRoll");
  if (sr != nullptr)
    songRollData.fromJson(sr);
  json_t *j = json_object_get(rootJ, "running");
  if (j != nullptr)
    running = json_is_true(j);
  j = json_object_get(rootJ, "currentSection");
  if (j != nullptr)
    enterSection(int(json_integer_value(j)));
}
