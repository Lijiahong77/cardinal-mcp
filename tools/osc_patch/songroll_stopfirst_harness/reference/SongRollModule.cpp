#include "SongRollModule.hpp"

using namespace rack;
using namespace SongRoll;

void SongRollModule::resetState() {
  std::lock_guard<std::recursive_mutex> lock(stateMutex);
  transport.reset();
  songRollData.reset();
  stopFirst();
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

void SongRollModule::stopFirst() {
  std::lock_guard<std::recursive_mutex> lock(stateMutex);
  running = false;
  sectionEndPulse.reset();
  songEndPulse.reset();
  eventCancelPending.store(true, std::memory_order_release);
  runInputTrigger.reset();
  runNeedsLow = true;
  for (int c = 0; c < SONGROLL_CHANNELS; ++c) {
    eopTrigger[c].reset();
    eopNeedsLow[c] = true;
  }
  enterSection(0);
}

void SongRollModule::enterSection(int idx) {
  std::lock_guard<std::recursive_mutex> lock(stateMutex);
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
  // Outputs are owned exclusively by process(), including JSON/UI transitions.
}

void SongRollModule::advanceSection() {
  std::lock_guard<std::recursive_mutex> lock(stateMutex);
  sectionEndPulse.trigger();
  int next = currentSection + 1;
  if (next >= int(songRollData.sections.size())) {
    songEndPulse.trigger();
    next = 0;
  }
  enterSection(next);
}

void SongRollModule::process(const ProcessArgs &args) {
  std::unique_lock<std::recursive_mutex> lock(stateMutex, std::try_to_lock);
  if (!lock.owns_lock()) {
    // No arrangement/runtime/trigger/pulse access without the mutex.
    // Read-only contention freezes the last event levels (and pulse time).
    // A real edit cancels them; leave its flag set until success owns the lock.
    if (eventCancelPending.load(std::memory_order_acquire)) {
      sectionEndHigh = false;
      songEndHigh = false;
    }
    outputs[SECTION_END_OUTPUT].setChannels(1);
    outputs[SECTION_END_OUTPUT].setVoltage(sectionEndHigh ? 10.f : 0.f);
    outputs[SONG_END_OUTPUT].setChannels(1);
    outputs[SONG_END_OUTPUT].setVoltage(songEndHigh ? 10.f : 0.f);
    return;
  }
  // Writers hold stateMutex, so no new cancellation can race this acknowledgement.
  // stopFirst already reset the protected pulses; never resurrect a cancelled level.
  if (eventCancelPending.exchange(false, std::memory_order_acq_rel)) {
    sectionEndHigh = false;
    songEndHigh = false;
  }

  const float runVoltage = inputs[RUN_INPUT].getVoltage();
  const bool runEdge = runInputTrigger.process(runVoltage);
  if (runNeedsLow) {
    if (runVoltage <= 0.f)
      runNeedsLow = false;
  }
  else if (runEdge)
    running = !running;

  // Track EOP even while stopped: old highs cannot become fresh start edges.
  bool eopEdge[SONGROLL_CHANNELS];
  for (int c = 0; c < SONGROLL_CHANNELS; ++c) {
    const float voltage = inputs[EOP_INPUT + c].getVoltage();
    const bool edge = eopTrigger[c].process(voltage);
    eopEdge[c] = edge && !eopNeedsLow[c];
    if (voltage <= 0.f)
      eopNeedsLow[c] = false;
  }

  // RESET：边沿回第 0 段（不停 running，照 Hapax）
  if (resetInputTrigger.process(inputs[RESET_INPUT].getVoltage()))
    enterSection(0);

  if (songRollData.sections.empty()) {
    running = false;
    sectionEndHigh = false;
    songEndHigh = false;
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
          eopEdge[c]) {
        repeatsLeft[c] -= 1;
      }
      if (repeatsLeft[c] > 0)
        allDone = false;
    }
    if (allDone)
      advanceSection();
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
  sectionEndHigh = sectionEndPulse.process(args.sampleTime);
  songEndHigh = songEndPulse.process(args.sampleTime);
  outputs[SECTION_END_OUTPUT].setVoltage(sectionEndHigh ? 10.f : 0.f);
  outputs[SONG_END_OUTPUT].setVoltage(songEndHigh ? 10.f : 0.f);
  outputs[SECTION_NUM_OUTPUT].setVoltage(float(currentSection));
}

json_t *SongRollModule::dataToJson() {
  std::lock_guard<std::recursive_mutex> lock(stateMutex);
  json_t *root = json_object();
  json_object_set_new(root, "songRoll", songRollData.toJson());
  json_object_set_new(root, "running", json_boolean(running));
  json_object_set_new(root, "currentSection", json_integer(currentSection));
  return root;
}

void SongRollModule::dataFromJson(json_t *rootJ) {
  if (rootJ == nullptr)
    return;
  // Parse/reclaim private replacement vectors outside the shared-state lock.
  json_t *sr = json_object_get(rootJ, "songRoll");
  const bool replace = sr && json_is_array(json_object_get(sr, "sections"));
  SongRollData incoming;
  if (replace)
    incoming.fromJson(sr);
  {
    std::lock_guard<std::recursive_mutex> lock(stateMutex);
    if (replace)
      songRollData.sections.swap(incoming.sections);
    // Saved running/currentSection deliberately never resume historical playback.
    stopFirst();
  }
}
