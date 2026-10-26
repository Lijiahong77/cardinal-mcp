// B1: real process and real UI/JSON methods, fixed lock-owner interleavings.
// Outer recursive lock prolongs the actual read transaction; no DSP/runtime mutation.
static void b1Boundary(SongRollModule& m,bool wrap){
 m.songRollData.sections.resize(2);tick(m);start(m);
 if(wrap)m.enterSection(1);
 setAllEop(m,10);tick(m);
 ck(m.outputs[SongRollModule::SECTION_END_OUTPUT].v==10,"real SECTION_END pulse required");
 ck(m.outputs[SongRollModule::SONG_END_OUTPUT].v==(wrap?10:0),"real SONG_END state required");
}
static void b1FailTick(SongRollModule& m){
 float pattern=m.outputs[0].v,section=m.outputs[SongRollModule::SECTION_NUM_OUTPUT].v;
 auto p=std::async(std::launch::async,[&]{tick(m);});
 bool ready=p.wait_for(std::chrono::seconds(2))==std::future_status::ready;
 // owner stays locked: a blocking process is an immediate failure, not silently released.
 if(!ready)std::abort();p.get();
 ck(m.outputs[0].v==pattern&&m.outputs[SongRollModule::SECTION_NUM_OUTPUT].v==section,"failed samples hold PATTERN and SECTION_NUM, including genuine edits");
}
static void b1Readonly(const string& test,SongRollModule& m,PatternControllerSlice& sl){
 bool wrap=test.find("song")!=string::npos;bool json=test.find("json")!=string::npos;
 b1Boundary(m,wrap);int section=m.currentSection;float remaining=m.sectionEndPulse.remaining;
 float skipped,skippedSong;
 {std::unique_lock<std::recursive_mutex> owner(m.stateMutex);
  if(json){Json saved(m.toJson());ck(saved.j!=nullptr,"real JSON read");}else sl.step();
  int count=test=="b1_readonly_consecutive"?128:1;
  for(int i=0;i<count;++i)b1FailTick(m);
  skipped=m.outputs[SongRollModule::SECTION_END_OUTPUT].v;skippedSong=m.outputs[SongRollModule::SONG_END_OUTPUT].v;
  ck(m.sectionEndPulse.remaining==remaining,"failed samples must not touch protected PulseGenerator");
 }
 tick(m);float resumed=m.outputs[SongRollModule::SECTION_END_OUTPUT].v;
 std::cout<<"SECTION_END sequence=10,"<<skipped<<","<<resumed<<" section="<<section<<"->"<<m.currentSection<<std::endl;
 if(wrap)std::cout<<"SONG_END sequence=10,"<<skippedSong<<","<<m.outputs[SongRollModule::SONG_END_OUTPUT].v<<std::endl;
 ck(skipped==10&&resumed==10,"read-only contention must not split one SECTION_END into two rises");
 if(wrap)ck(skippedSong==10&&m.outputs[SongRollModule::SONG_END_OUTPUT].v==10,"read-only contention preserves SONG_END without duplicate rise");
 ck(m.currentSection==section,"no new boundary during read contention");
 setAllEop(m,0);for(int i=0;i<100;++i)tick(m);
 ck(m.outputs[SongRollModule::SECTION_END_OUTPUT].v==0&&m.outputs[SongRollModule::SONG_END_OUTPUT].v==0,"old pulse eventually expires on successful samples");
}
static void b1(const string& test,SongRollModule& m,PatternControllerSlice& sl){
 if(test.find("b1_readonly_")==0){b1Readonly(test,m,sl);return;}
 b1Boundary(m,true);
 if(test=="b1_cancel_inflight"){
  std::unique_lock<std::recursive_mutex> owner(m.stateMutex);
  std::promise<void> sampled,resume;auto go=resume.get_future();
  m.outputs[SongRollModule::SECTION_END_OUTPUT].onWrite=[&]{sampled.set_value();go.wait();};
  auto dsp=std::async(std::launch::async,[&]{tick(m);});sampled.get_future().wait();
  // Failed DSP already sampled cancel=false. Publish a real edit before its write.
  m.songRollData.sections[0].channels[0].pattern=37;m.stopFirst();resume.set_value();dsp.get();
  m.outputs[SongRollModule::SECTION_END_OUTPUT].onWrite=nullptr;
  // One already in-flight sample may complete with its old high; next must cancel.
  b1FailTick(m);ck(m.outputs[SongRollModule::SECTION_END_OUTPUT].v==0&&m.outputs[SongRollModule::SONG_END_OUTPUT].v==0,"concurrent cancellation not lost by prior failed invocation");
 }else if(test=="b1_writer_before_cancel"){
  std::unique_lock<std::recursive_mutex> owner(m.stateMutex);
  m.songRollData.sections[0].channels[0].pattern=37;
  b1FailTick(m);ck(m.outputs[SongRollModule::SECTION_END_OUTPUT].v==10,"pre-stop transaction skips without false low");
  m.stopFirst();b1FailTick(m);
 }else if(test=="b1_cancel_success"){
  click(sl,0); // no intervening failed sample: cancellation still observed on success
 }else{
  std::unique_lock<std::recursive_mutex> owner(m.stateMutex);
  click(sl,0);float before=m.outputs[SongRollModule::SECTION_END_OUTPUT].v;
  ck(before==10,"UI never writes event outputs");
  b1FailTick(m);ck(m.outputs[SongRollModule::SECTION_END_OUTPUT].v==0&&m.outputs[SongRollModule::SONG_END_OUTPUT].v==0,"edit cancellation clears both events on failed sample");
  for(int i=0;i<64;++i)b1FailTick(m);
  if(test=="b1_cancel_repeated"){m.songRollData.sections[0].channels[0].pattern=41;m.stopFirst();b1FailTick(m);m.stopFirst();}
  if(test=="b1_cancel_reset"){m.onReset(Module::ResetEvent{});b1FailTick(m);}
  if(test=="b1_cancel_json"){Json j(json_loads("{\"songRoll\":{\"sections\":[{\"channels\":[{\"pattern\":37}]}]}}",0,nullptr));m.dataFromJson(j.j);b1FailTick(m);}
 }
 for(int i=0;i<100;++i){tick(m);ck(m.outputs[SongRollModule::SECTION_END_OUTPUT].v==0&&m.outputs[SongRollModule::SONG_END_OUTPUT].v==0,"cancel cannot be lost or resurrect old pulse on next successes");}
 ck(!m.running&&m.currentSection==0,"stop-first transport remains stopped-first");
 int expected=test=="b1_cancel_inflight"||test=="b1_writer_before_cancel"||test=="b1_cancel_json"?37:test=="b1_cancel_repeated"?41:test=="b1_cancel_reset"?1:2;
 ck(m.songRollData.sections[0].channels[0].pattern==expected,"new configuration retained");
 ck(m.outputs[0].v==float(expected-1)/12.f,"new held pattern refreshed by successful DSP");
 start(m);ck(m.running,"fresh RUN after observed low works");setAllEop(m,0);tick(m);setAllEop(m,10);tick(m);
 ck(m.outputs[SongRollModule::SECTION_END_OUTPUT].v==10,"new real boundary emits after cancellation, not permanently muted");
}
