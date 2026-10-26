#include "../SongRoll/SongRollData.hpp"

using namespace SongRoll;

Section::Section() {
  channels.resize(SONGROLL_CHANNELS);
}

SongRollData::SongRollData() {
  reset();
}

void SongRollData::reset() {
  sections.clear();
  Section sec;
  for (int c = 0; c < SONGROLL_CHANNELS; ++c) {
    sec.channels[c].pattern = c + 1;
    sec.channels[c].repeats = 1;
    sec.channels[c].repeat_mode = ChannelConfig::REPEATS;
    sec.channels[c].clock_div = 1;
  }
  sections.push_back(sec);
}

json_t *SongRollData::toJson() {
  json_t *root = json_object();
  json_t *arr = json_array();
  for (const Section &sec : sections) {
    json_t *so = json_object();
    json_t *chs = json_array();
    for (const ChannelConfig &ch : sec.channels) {
      json_t *co = json_object();
      json_object_set_new(co, "pattern", json_integer(ch.pattern));
      json_object_set_new(co, "repeats", json_integer(ch.repeats));
      json_object_set_new(co, "repeat_mode", json_integer(int(ch.repeat_mode)));
      json_object_set_new(co, "clock_div", json_integer(ch.clock_div));
      json_array_append_new(chs, co);
    }
    json_object_set_new(so, "channels", chs);
    json_array_append_new(arr, so);
  }
  json_object_set_new(root, "sections", arr);
  return root;
}

void SongRollData::fromJson(json_t *rootJ) {
  if (rootJ == nullptr)
    return;
  json_t *arr = json_object_get(rootJ, "sections");
  if (arr == nullptr || !json_is_array(arr))
    return;
  sections.clear();
  size_t n = json_array_size(arr);
  for (size_t i = 0; i < n; ++i) {
    json_t *so = json_array_get(arr, i);
    if (so == nullptr)
      continue;
    Section sec;
    json_t *chs = json_object_get(so, "channels");
    if (chs != nullptr && json_is_array(chs)) {
      size_t m = json_array_size(chs);
      for (size_t c = 0; c < sec.channels.size() && c < m; ++c) {
        json_t *co = json_array_get(chs, c);
        if (co == nullptr)
          continue;
        json_t *j;
        if ((j = json_object_get(co, "pattern")) != nullptr)
          sec.channels[c].pattern = rack::math::clamp(int(json_integer_value(j)), 1, 64);
        if ((j = json_object_get(co, "repeats")) != nullptr)
          sec.channels[c].repeats = int(json_integer_value(j));
        if ((j = json_object_get(co, "repeat_mode")) != nullptr) {
          // clamp 到合法枚举范围：json 里的脏值（如 99）转 eRepeatMode 是 UB
          const int rm = rack::math::clamp(int(json_integer_value(j)), 0, 2);
          sec.channels[c].repeat_mode = ChannelConfig::eRepeatMode(rm);
        }
        if ((j = json_object_get(co, "clock_div")) != nullptr)
          sec.channels[c].clock_div = int(json_integer_value(j));
      }
    }
    sections.push_back(sec);
  }
  if (sections.empty())
    reset();
}
