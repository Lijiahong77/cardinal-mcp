// Behavior assertions for real extracted methods; no candidate text rewriting.
static void ck(bool b,const char* msg){if(!b)throw std::runtime_error(msg);}
static event::Button button(float x=80,float y=15){event::Button e;e.pos=Vec(x,y);return e;}
static void click(PatternControllerSlice& s,int kind,bool minus=false){auto e=button(minus?10:80,kind==3?35:kind==2&&minus?50:15);if(kind==0)s.pattern->onButton(e);else if(kind==2)s.clock_div->onButton(e);else s.repeats->onButton(e);}
static int value(SongRollModule&m,int kind,int channel=0){auto&c=m.songRollData.sections[m.currentSection].channels[channel];return kind==0?c.pattern:kind==1?c.repeats:kind==2?c.clock_div:int(c.repeat_mode);}
static int display(PatternControllerSlice&s,int kind){return kind==0?s.pattern->pattern+1:kind==1?s.repeats->repeats:kind==2?s.clock_div->clock_div:s.repeats->repeat_mode;}
struct Json {json_t*j;explicit Json(json_t*x):j(x){}~Json(){json_decref(j);}Json(const Json&)=delete;};
int main(int argc,char**argv){string test=argc>1?argv[1]:"";
try{
 SongRollModule m,n;n.id=8675309;Engine eng;eng.modules={&m,&n};history::State hist;App app{&eng,&hist};APP=&app;
 PatternControllerSlice sl(0,&m);sl.step();
 if(test.find("snapshot_")==0||test.find("history_")==0&&test!="history_chain_branch"){
  int kind=test.find("pattern")!=string::npos?0:test.find("repeats")!=string::npos?1:2;
  Json before(m.toJson());click(sl,kind);ck(value(m,kind)==2,"edit applies exactly once; push does not redo");Json after(m.toJson());
  auto*a=hist.actions.back();ck(a->oldModuleJ!=a->newModuleJ,"snapshots own independent new references");
  ck(json_equal(a->oldModuleJ,before.j)&&json_equal(a->newModuleJ,after.j),"history snapshots must be complete Module JSON");
  hist.undo();ck(value(m,kind)==1,"undo restores data");Json undone(m.toJson());ck(json_equal(undone.j,before.j),"undo restores complete Module JSON");
  if(test.find("history_")==0){sl.step();ck(display(sl,kind)==1,"same-section UI stale after undo step");}
  hist.redo();ck(value(m,kind)==2,"redo restores data");sl.step();ck(display(sl,kind)==2,"redo display refresh");
 }else if(test=="same_section_replace"){
  Json j(m.toJson());auto*d=json_object_get(j.j,"data");auto*sr=json_object_get(d,"songRoll");auto*ch=json_array_get(json_object_get(json_array_get(json_object_get(sr,"sections"),0),"channels"),0);
  json_object_set_new(ch,"pattern",json_integer(51));json_object_set_new(ch,"repeats",json_integer(23));json_object_set_new(ch,"repeat_mode",json_integer(ChannelConfig::LIMIT));json_object_set_new(ch,"clock_div",json_integer(0));m.fromJson(j.j);
  sl.step();ck(display(sl,0)==51&&display(sl,1)==23&&display(sl,2)==0&&display(sl,3)==ChannelConfig::LIMIT,"same section replacement must refresh all display caches");ck(sl.header->pattern==51&&sl.header->repeats==23,"header agrees");
 }else if(test.find("nostep_")==0){
  int kind=test=="nostep_repeats"?1:test=="nostep_clock"?2:3;click(sl,kind);hist.undo(); // absolutely no UI step before next click
  click(sl,kind);ck(value(m,kind)==2,"undo then no-step click must read authoritative data");ck(hist.actions.size()==1&&!hist.canRedo(),"click branches history");hist.undo();ck(value(m,kind)==1,"branched action old state");hist.redo();ck(value(m,kind)==2,"branched action new state");
 }else if(test=="repeats_preserve_mode"){
  auto&ch=m.songRollData.sections[0].channels[0];ch.repeat_mode=ChannelConfig::FREE;click(sl,1);ck(ch.repeats==2&&ch.repeat_mode==ChannelConfig::FREE,"count edit must not overwrite authoritative mode with cache");hist.undo();ck(value(m,3)==ChannelConfig::FREE,"mode survives undo");
 }else if(test=="mode_preserve_repeats"){
  m.songRollData.sections[0].channels[0].repeats=29;click(sl,3);ck(value(m,1)==29&&value(m,3)==ChannelConfig::LIMIT,"mode edit must not overwrite authoritative count");hist.undo();ck(value(m,1)==29,"count survives undo");
 }else if(test=="multi_channel_instance"){
  PatternControllerSlice a(7,&m),b(3,&n);a.step();b.step();click(a,0);click(b,1);click(a,2);
  ck(value(m,0,7)==9&&value(n,1,3)==2&&value(m,2,7)==2,"independent controls/channels");
  hist.undo();ck(value(m,2,7)==1&&value(n,1,3)==2,"first undo targets m");hist.undo();ck(value(n,1,3)==1&&value(m,0,7)==9,"second undo targets n by ID");hist.undo();ck(value(m,0,7)==8,"third undo m pattern");hist.redo();hist.redo();hist.redo();a.step();b.step();ck(display(a,0)==9&&display(a,2)==2&&display(b,1)==2,"multiinstance redo/step");ck(value(m,1,0)==1&&value(n,0,0)==1,"other channels untouched");
 }else if(test=="history_chain_branch"){
  click(sl,0);click(sl,1);click(sl,2);for(int i=0;i<3;++i)hist.undo();ck(value(m,0)==1&&value(m,1)==1&&value(m,2)==1,"undo entire chain");for(int i=0;i<3;++i)hist.redo();ck(value(m,0)==2&&value(m,1)==2&&value(m,2)==2,"redo entire chain");hist.undo();hist.undo();click(sl,3);ck(hist.actions.size()==2&&!hist.canRedo(),"new edit truncates redo branch");hist.undo();hist.undo();hist.redo();hist.redo();sl.step();ck(display(sl,0)==2&&display(sl,1)==1&&display(sl,2)==1&&display(sl,3)==2,"new branch authoritative state");
 }else if(test=="preview_null"){
  PatternControllerSlice preview(0,nullptr);preview.step();for(int i=0;i<4;++i)click(preview,i);ck(hist.actions.empty(),"NULL preview never pushes history");
 }else if(test.find("boundary_")==0){
  int kind=test=="boundary_pattern"?0:test=="boundary_repeats"?1:2;auto&ch=m.songRollData.sections[0].channels[0];int&v=kind==0?ch.pattern:kind==1?ch.repeats:ch.clock_div;
  v=64;sl.step();Json before(m.toJson());click(sl,kind);ck(v==64&&hist.actions.size()==1,"existing max no-op still pushes one history action");Json after(m.toJson());ck(json_equal(before.j,after.j),"max clamp preserves data");hist.undo();hist.redo();
  int min=kind==2?0:1;auto&cc=m.songRollData.sections[0].channels[0];if(kind==0)cc.pattern=min;else if(kind==1)cc.repeats=min;else cc.clock_div=min;sl.step();click(sl,kind,true);ck(value(m,kind)==min&&hist.actions.size()==2,"existing min no-op still pushes one action");hist.undo();hist.redo();sl.step();ck(display(sl,kind)==min,"boundary history valid");
 }else if(test=="mode_cycle"){
  ck(ChannelConfig::FREE==0&&ChannelConfig::REPEATS==1&&ChannelConfig::LIMIT==2,"fixture enum actual three states");for(int expected:{2,0,1}){click(sl,3);ck(value(m,3)==expected,"mode cycle uses real enum");}for(int i=0;i<3;++i)hist.undo();ck(value(m,3)==1,"undo mode cycle");for(int i=0;i<3;++i)hist.redo();sl.step();ck(display(sl,3)==1,"redo mode cycle");
 }else if(test=="nonhit_empty"){
  Json before(m.toJson());auto e=button(50,5);sl.pattern->onButton(e);sl.repeats->onButton(e);sl.clock_div->onButton(e);e=button();e.action=0;sl.pattern->onButton(e);sl.repeats->onButton(e);sl.clock_div->onButton(e);e.action=1;e.button=1;sl.pattern->onButton(e);sl.repeats->onButton(e);sl.clock_div->onButton(e);Json after(m.toJson());ck(json_equal(before.j,after.j)&&hist.actions.empty(),"nonhits unchanged");m.songRollData.sections.clear();sl.step();for(int i=0;i<4;++i)click(sl,i);ck(hist.actions.empty(),"empty data guard unchanged");
 }else if(test=="preserve_unrelated"){
  m.songRollData.sections.resize(3);m.currentSection=1;m.running=true;m.internal->bypassed=true;m.leftExpander.moduleId=912;m.rightExpander.moduleId=913;
  for(int s=0;s<3;++s)for(int c=0;c<8;++c){auto&ch=m.songRollData.sections[s].channels[c];ch.pattern=1+s*8+c;ch.repeats=2+s+c;ch.repeat_mode=ChannelConfig::eRepeatMode(c%3);ch.clock_div=(s+c)%5;}
  m.songRollData.sections[2].channels[7].repeats=117;sl.step();
  for(int kind=0;kind<4;++kind){Json old(m.toJson());click(sl,kind);Json edited(m.toJson());Json expected(json_deep_copy(old.j));auto*ch=json_array_get(json_object_get(json_array_get(json_object_get(json_object_get(json_object_get(expected.j,"data"),"songRoll"),"sections"),1),"channels"),0);const char*key=kind==0?"pattern":kind==1?"repeats":kind==2?"clock_div":"repeat_mode";json_object_set_new(ch,key,json_integer(value(m,kind)));ck(json_equal(expected.j,edited.j),"edit only changes selected field; running/section/bypass/expanders/other channels intact");hist.undo();Json restored(m.toJson());ck(json_equal(restored.j,old.j),"undo unrelated data intact");hist.redo();Json redone(m.toJson());ck(json_equal(redone.j,edited.j),"redo unrelated data intact");sl.step();}
 }else if(test=="missing_module"){
  click(sl,0);eng.modules.clear();hist.undo();hist.redo();ck(value(m,0)==2,"history missing module no-op unchanged");
 }else throw std::runtime_error("unknown test");
 std::cout<<"PASS "<<test<<std::endl;return 0;
}catch(std::exception&e){std::cout<<"FAIL "<<test<<": "<<e.what()<<std::endl;return 1;}}
