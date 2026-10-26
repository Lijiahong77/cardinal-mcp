// Additional real-source behavior and deterministic interleavings.
static void tick(SongRollModule&m){m.process(Module::ProcessArgs{});}
static void setAllEop(SongRollModule&m,float v){for(int c=0;c<8;++c)m.inputs[SongRollModule::EOP_INPUT+c].v=v;}
static void start(SongRollModule&m){m.inputs[SongRollModule::RUN_INPUT].v=0;tick(m);m.inputs[SongRollModule::RUN_INPUT].v=10;tick(m);}
static void extra(const string&test,SongRollModule&m,PatternControllerSlice&sl,history::State&hist){
 if(test=="rollarea_preview"){RollArea preview(Rect(Vec(),Vec(400,200)),nullptr);ck(preview.children.size()==8,"RollArea NULL browser preview safely constructs fixed eight channels");RollArea actual(Rect(Vec(),Vec(400,200)),&m);ck(actual.children.size()==8,"real module RollArea channel count unchanged");
 }else if(test=="load_matrix"){
  for(int savedRun=0;savedRun<2;++savedRun)for(int idx:{-9,0,2,999})for(bool omitted:{false,true}){
   m.songRollData.sections.resize(3);m.currentSection=2;m.running=true;
   Json j(m.toJson());auto*d=json_object_get(j.j,"data");json_object_set_new(d,"running",json_boolean(savedRun));if(omitted)json_object_del(d,"currentSection");else json_object_set_new(d,"currentSection",json_integer(idx));
   m.fromJson(j.j);ck(!m.running&&m.currentSection==0,"full JSON load ignores saved transport");
  }
 }else if(test=="partial_table"){
  m.songRollData.sections.resize(4);m.currentSection=3;m.running=true;
  Json j(json_loads("{\"songRoll\":{\"sections\":[{\"channels\":[{\"pattern\":61,\"repeats\":6,\"repeat_mode\":2,\"clock_div\":0}]}]}}",0,nullptr));m.dataFromJson(j.j);
  ck(m.songRollData.sections.size()==1&&!m.running&&m.currentSection==0&&m.repeatsLeft[0]==6,"partial load returns first with new counts");sl.step();ck(display(sl,0)==61&&display(sl,1)==6&&display(sl,2)==0&&display(sl,3)==2,"partial data not lost");
  m.running=true;m.dataFromJson(nullptr);ck(m.running,"null load remains no-op");
 }else if(test=="run_high_rearm"){
  start(m);ck(m.running,"normal manual RUN works");click(sl,0);ck(!m.running,"edit stops");for(int i=0;i<20;++i)tick(m);ck(!m.running,"held high after edit must not restart");
  m.inputs[SongRollModule::RUN_INPUT].v=0;tick(m);m.inputs[SongRollModule::RUN_INPUT].v=10;tick(m);ck(m.running,"fresh low-rise manually starts");m.inputs[SongRollModule::RUN_INPUT].v=0;tick(m);m.inputs[SongRollModule::RUN_INPUT].v=10;tick(m);ck(!m.running,"normal RUN toggle still stops");
 }else if(test=="high_before_first_process"){
  m.inputs[SongRollModule::RUN_INPUT].v=10;click(sl,1);for(int i=0;i<5;++i)tick(m);ck(!m.running,"high present before first process cannot start");start(m);ck(m.running,"new low-rise works after initial high");
 }else if(test=="eop_old_edge"){
  tick(m);setAllEop(m,10);click(sl,0);start(m);ck(m.running&&m.currentSection==0,"manual start does not consume old EOP highs");for(int c=0;c<8;++c)ck(m.repeatsLeft[c]==1,"no stale repeats consumed");
  setAllEop(m,0);tick(m);setAllEop(m,10);tick(m);ck(m.outputs[SongRollModule::SECTION_END_OUTPUT].v==10,"fresh EOP advances after low-rise");
 }else if(test=="pulse_cleanup"){
  m.songRollData.sections.resize(2);m.currentSection=1;tick(m);start(m);setAllEop(m,10);tick(m);
  ck(m.outputs[SongRollModule::SECTION_END_OUTPUT].v==10&&m.outputs[SongRollModule::SONG_END_OUTPUT].v==10,"real wrap creates both pulses");
  click(sl,3);ck(m.sectionEndPulse.remaining==0&&m.songEndPulse.remaining==0,"edit clears internal old pulses");tick(m);ck(m.outputs[SongRollModule::SECTION_END_OUTPUT].v==0&&m.outputs[SongRollModule::SONG_END_OUTPUT].v==0,"no boundary/song-end leakage");
 }else if(test=="reset_normal"){
  m.songRollData.sections.resize(3);tick(m);start(m);m.enterSection(2);m.inputs[SongRollModule::RESET_INPUT].v=10;tick(m);ck(m.running&&m.currentSection==0,"normal RESET jumps first without stopping running");
 }else if(test=="stopped_output_heal"){
  m.songRollData.sections[0].channels[0].pattern=49;click(sl,1);tick(m);ck(m.outputs[0].v==4&&!m.running,"pattern remains (49-1)/12 while stopped");m.outputs[0].v=0;m.outputs[0].channels=0;tick(m);ck(m.outputs[0].v==4&&m.outputs[0].channels==1,"stopped continuous output self-heals");
 }else if(test=="noop_stops"){
  for(int kind=0;kind<3;++kind){auto&ch=m.songRollData.sections[0].channels[0];if(kind==0)ch.pattern=64;else if(kind==1)ch.repeats=64;else ch.clock_div=64;m.running=true;auto count=hist.actions.size();click(sl,kind);ck(!m.running&&m.currentSection==0&&hist.actions.size()==count+1,"recognized clamp noop retains action and stops");}
 }else if(test=="process_before_writer"){
  tick(m);std::promise<void> reading,release,writerStarting;auto go=release.get_future();
  m.inputs[SongRollModule::RUN_INPUT].onRead=[&]{reading.set_value();go.wait();};
  auto p=std::async(std::launch::async,[&]{tick(m);});reading.get_future().wait();
  bool acquired=m.stateMutex.try_lock();if(acquired)m.stateMutex.unlock();
  Json j(json_loads("{\"songRoll\":{\"sections\":[{\"channels\":[{\"pattern\":37}]}]}}",0,nullptr));
  auto w=std::async(std::launch::async,[&]{writerStarting.set_value();m.dataFromJson(j.j);});writerStarting.get_future().wait();
  bool writerPremature=w.wait_for(std::chrono::milliseconds(40))==std::future_status::ready;
  release.set_value();p.get();w.get();m.inputs[SongRollModule::RUN_INPUT].onRead=nullptr;
  ck(!acquired&&!writerPremature,"old real process owns mutex until entire reader finishes; writer cannot apply");ck(m.songRollData.sections[0].channels[0].pattern==37&&!m.running,"writer applies only after old process returns");
 }else if(test=="ui_no_half_config"||test=="json_no_half_config"){
  std::unique_lock<std::recursive_mutex> lock(m.stateMutex);m.songRollData.sections[0].channels[0].pattern=31;std::promise<void> starting;
  auto r=std::async(std::launch::async,[&]{starting.set_value();if(test=="ui_no_half_config")sl.step();else {Json j(m.toJson());auto*d=json_object_get(j.j,"data");auto*c=json_array_get(json_object_get(json_array_get(json_object_get(json_object_get(d,"songRoll"),"sections"),0),"channels"),0);ck(json_integer_value(json_object_get(c,"repeats"))==23,"JSON sees complete config");}});starting.get_future().wait();
  bool premature=r.wait_for(std::chrono::milliseconds(40))==std::future_status::ready;m.songRollData.sections[0].channels[0].repeats=23;lock.unlock();r.get();ck(!premature,"UI/JSON reader must wait for transaction completion");if(test=="ui_no_half_config")ck(display(sl,0)==31&&display(sl,1)==23,"UI sees complete config");
 }else if(test=="thread_stress"){
  Json j(json_loads("{\"songRoll\":{\"sections\":[{\"channels\":[{\"pattern\":37,\"repeats\":5}]}]}}",0,nullptr));
  std::atomic<bool> go(false);auto dsp=std::async(std::launch::async,[&]{while(!go.load()){}for(int i=0;i<10000;++i)tick(m);});auto writer=std::async(std::launch::async,[&]{while(!go.load()){}for(int i=0;i<500;++i)m.dataFromJson(j.j);});go=true;for(int i=0;i<500;++i){click(sl,i%4);sl.step();Json saved(m.toJson());}dsp.get();writer.get();ck(!m.running&&m.currentSection==0,"concurrent load/read/process final state");
 }else if(test=="mode_semantics"){
  for(auto mode:{ChannelConfig::FREE,ChannelConfig::LIMIT}){m.songRollData.sections[0].channels[0].repeat_mode=mode;m.stopFirst();start(m);setAllEop(m,0);tick(m);setAllEop(m,10);tick(m);ck(m.currentSection==0&&m.repeatsLeft[0]==1,"FREE/LIMIT existing non-REPEATS semantics preserved");m.running=false;}
 }else throw std::runtime_error("unknown extra case");
}
