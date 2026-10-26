using namespace SongRoll;
struct SongRollModule:Module{SongRollData songRollData;bool running=false;int currentSection=0;int repeatsLeft[8]={};struct Out{float v=0;void setVoltage(float x){v=x;}} outputs[11];enum{PATTERN_OUTPUT=0,SECTION_NUM_OUTPUT=9};void enterSection(int);json_t* dataToJson()override;void dataFromJson(json_t*)override;};
struct PatternControlWidget:Widget{SongRollModule* module=nullptr;int channel=0,pattern=0;PatternControlWidget();void onButton(const event::Button&);};
struct RepeatControlWidget:Widget{SongRollModule* module=nullptr;int channel=0,repeats=1,repeat_mode=1;RepeatControlWidget();void onButton(const event::Button&);};
struct ClockDivControlWidget:Widget{SongRollModule* module=nullptr;int channel=0,clock_div=1;ClockDivControlWidget();void onButton(const event::Button&);};
struct PatternControllerSlice:Widget{SongRollModule* module;int channel,displayedSection=-1;PatternControlWidget*pattern;RepeatControlWidget*repeats;ClockDivControlWidget*clock_div;PatternHeaderWidget*header;SequentialLayout*layout;PatternControllerSlice(int channel,SongRollModule* module);void step()override;};
