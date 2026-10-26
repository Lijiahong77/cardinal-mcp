struct PatternControlWidget:Widget{SongRollModule* module=nullptr;int channel=0,pattern=0;PatternControlWidget();void onButton(const event::Button&);};
struct RepeatControlWidget:Widget{SongRollModule* module=nullptr;int channel=0,repeats=1,repeat_mode=1;RepeatControlWidget();void onButton(const event::Button&);};
struct ClockDivControlWidget:Widget{SongRollModule* module=nullptr;int channel=0,clock_div=1;ClockDivControlWidget();void onButton(const event::Button&);};
struct PatternControllerSlice:Widget{SongRollModule* module;int channel,displayedSection=-1;PatternControlWidget*pattern;RepeatControlWidget*repeats;ClockDivControlWidget*clock_div;PatternHeaderWidget*header;SequentialLayout*layout;PatternControllerSlice(int channel,SongRollModule* module);void step()override;};

struct RollArea:Widget {SongRollModule*module;RollArea(Rect,SongRollModule*);};
