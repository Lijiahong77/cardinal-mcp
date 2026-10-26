// Offline harness. Production functions are extracted verbatim into production.inc.
// Stubs: Rack ownership shell, Engine::Internal subset, liblo/QuickJS/history.
// Real Param and ParamQuantity conversion bodies are not replaced with mock logic.
#include <cassert>
#include <cmath>
#include <climits>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <vector>
#include <unordered_map>
#include <shared_mutex>
#include <mutex>
#include <string>
#include <atomic>
#include <thread>
#include <chrono>
#include <condition_variable>
#define DISTRHO_SAFE_ASSERT_RETURN(c,r) do {if(!(c)) return r;}while(0)
#define d_debug(...) ((void)0)
#define CARDINAL_INIT_OSC_THREAD
struct SharedMutex {
 std::shared_mutex m; static thread_local int held;
 void lock(){m.lock();++held;} void unlock(){--held;m.unlock();}
 void lock_shared(){m.lock_shared();++held;} void unlock_shared(){--held;m.unlock_shared();}
};
thread_local int SharedMutex::held=0;
template<class M>using SharedLock=std::shared_lock<M>;
int sends=0;bool sendLocked=false;
namespace remoteUtils { struct RemoteDetails {bool connected=true;}; }
void sendParamChangeToRemote(remoteUtils::RemoteDetails*,int64_t,int,float){++sends;sendLocked=SharedMutex::held>0;}
namespace rack {namespace math {float clampSafe(float x,float a,float b){return std::fmax(std::fmin(x,b),a);}}
namespace engine {
#include "param.inc"
struct Module;
struct ParamQuantity {
 Module* module=nullptr;int paramId=0;bool snapEnabled=false,smoothEnabled=false;
 float minValue=-10000,maxValue=10000,displayBase=0,displayMultiplier=1,displayOffset=0;
 virtual ~ParamQuantity()=default;
 float getMinValue(){return minValue;} float getMaxValue(){return maxValue;}
 float getValue();void setImmediateValue(float);virtual void setDisplayValue(float);
};
struct Module {int64_t id=7;std::vector<Param>params;std::vector<ParamQuantity*>paramQuantities;
 ParamQuantity* getParamQuantity(int index){return paramQuantities[index];}
};
struct Engine {
 struct Internal {SharedMutex mutex; std::unordered_map<int64_t,Module*>modulesCache;Module*smoothModule=nullptr;int smoothParamId=0;float smoothValue=0;remoteUtils::RemoteDetails*remoteDetails=nullptr;}*internal;
 Module*getModule(int64_t);Module*getModule_NoLock(int64_t);
 void setParamValue(Module*,int,float);float getParamValue(Module*,int);
 void setParamSmoothValue(Module*,int,float);float getParamSmoothValue(Module*,int);
};
}
struct Context {engine::Engine* engine;};
Context*current=nullptr;void contextSet(Context*c){current=c;}
namespace history {struct ParamChange{int64_t moduleId;int paramId;float oldValue,newValue;};}
struct History {int count=0;void push(history::ParamChange*p){++count;delete p;}};
struct App:Context {History*history;};App*app;
}
#define APP rack::app
using CardinalPluginContext=rack::Context;
struct CardinalBasePlugin {CardinalPluginContext*context;};
struct Initializer {CardinalBasePlugin*remotePluginInstance;void*oscServer=nullptr;};
using lo_address=void*;using lo_server=void*;using lo_message=void*;
union lo_arg{int64_t h;int32_t i;float f;};
void*lo_message_get_source(void*){return nullptr;}
std::string replyStatus,replyPayload;
void cardinalOscReply(void*,void*,const char*,const std::string&p,const char*s){replyStatus=s;replyPayload=p;}
std::string fmtC(float v){return std::to_string(v);}
std::string fmtB(double v){return std::to_string(v);}
using JSValue=double;using JSValueConst=double;struct JSContext{};
void*g_osc_js_self=nullptr;
int JS_ToInt64(JSContext*,int64_t*p,JSValue v){*p=(int64_t)v;return 0;}
int JS_ToInt32(JSContext*,int32_t*p,JSValue v){*p=(int32_t)v;return 0;}
int JS_ToFloat64(JSContext*,double*p,JSValue v){*p=v;return 0;}
JSValue JS_ThrowTypeError(JSContext*,const char*){return -101;}
JSValue JS_ThrowInternalError(JSContext*,const char*){return -102;}
JSValue JS_NewFloat64(JSContext*,double v){return v;}
JSValue JS_NewStringLen(JSContext*,const char*,size_t){return 1;}
#define JS_UNDEFINED 0
#include "safety-declarations.inc"
#include "production.inc"
struct BlockingPQ:rack::engine::ParamQuantity {
 std::mutex mutex;std::condition_variable cv;bool entered=false,release=false;bool held=false;
 void setDisplayValue(float v)override{
  {std::unique_lock<std::mutex> l(mutex);held=SharedMutex::held>0;entered=true;cv.notify_all();cv.wait(l,[&]{return release;});}
  rack::engine::ParamQuantity::setDisplayValue(v);
 }
};
int main(int argc,char**argv){
 assert(argc==5);std::string mode=argv[1];int pid=std::stoi(argv[2]);float val=std::strtof(argv[3],nullptr);int64_t mid=std::stoll(argv[4]);
 using namespace rack::engine;
 Engine::Internal in;Engine engine{&in};Module mod;mod.params.resize(3);for(int i=0;i<3;++i)mod.params[i].value=11*(i+1);
 ParamQuantity pq[3];for(int i=0;i<3;++i){pq[i].module=&mod;pq[i].paramId=i;mod.paramQuantities.push_back(&pq[i]);}
 in.modulesCache.emplace(mod.id,&mod);remoteUtils::RemoteDetails remote;in.remoteDetails=&remote;
 CardinalPluginContext context{&engine};CardinalBasePlugin plugin{&context};Initializer init{&plugin};rack::History hist;rack::App app;app.engine=&engine;app.history=&hist;rack::app=&app;g_osc_js_self=&init;
 bool invalid=mid!=7||pid<0||pid>=3;
 if(mode=="raw"){
  lo_arg a,b,c;a.h=mid;b.i=pid;c.f=val;lo_arg*args[]={&a,&b,&c};osc_param_handler(nullptr,"hif",args,3,nullptr,&init);assert(rack::current==nullptr);
 }else if(mode=="direct")engine.setParamValue(mid==7?&mod:nullptr,pid,val);
 else if(mode=="smooth"){
  in.smoothModule=&mod;in.smoothParamId=0;in.smoothValue=17;
  engine.setParamSmoothValue(mid==7?&mod:nullptr,pid,val);
  if(invalid){assert(in.smoothModule==&mod&&in.smoothParamId==0&&in.smoothValue==17);}
  else {assert(in.smoothModule==&mod&&in.smoothParamId==pid);assert((std::isnan(val)&&std::isnan(in.smoothValue))||in.smoothValue==val);if(pid!=0)assert(mod.params[0].value==17);}
 }else if(mode=="display"||mode=="js"){
  if(mode=="display") {lo_arg a,b,c;a.h=mid;b.i=pid;c.f=val;lo_arg*args[]={&a,&b,&c};osc_param_set_display_handler(nullptr,"hif",args,3,nullptr,&init);assert(rack::current==nullptr);if(invalid)assert(replyStatus== (mid!=7?"err:E_NO_MODULE":"err:E_BAD_PARAM"));else assert(replyStatus=="ok");}
  else {JSContext ctx;JSValue args[]={(double)mid,(double)pid,val};auto r=jsApiSetDisplayValue(&ctx,0,3,args);if(invalid)assert(r==-102);}
 }else if(mode=="lifetime"){
  BlockingPQ block;block.module=&mod;block.paramId=1;mod.paramQuantities[1]=&block;
  std::thread writer([&]{lo_arg a,b,c;a.h=7;b.i=1;c.f=val;lo_arg*args[]={&a,&b,&c};osc_param_set_display_handler(nullptr,"hif",args,3,nullptr,&init);});
  {std::unique_lock<std::mutex>l(block.mutex);block.cv.wait(l,[&]{return block.entered;});}
  std::atomic<bool>attempt{false},removed{false};std::thread remover([&]{attempt=true;std::lock_guard<SharedMutex>lock(in.mutex);in.modulesCache.erase(7);removed=true;});
  while(!attempt.load())std::this_thread::yield();std::this_thread::sleep_for(std::chrono::milliseconds(20));
  assert(block.held&&!removed.load());
  {std::lock_guard<std::mutex>l(block.mutex);block.release=true;block.cv.notify_all();}writer.join();remover.join();assert(removed);std::cout<<"PASS lifetime lock excludes removal\n";return 0;
 }else return 9;
 if(invalid){for(int i=0;i<3;++i)assert(mod.params[i].value==11*(i+1));assert(sends==0&&hist.count==0);}
 else if(mode=="raw"||mode=="direct"){
  assert((std::isnan(val)&&std::isnan(mod.params[pid].value))||mod.params[pid].value==val);assert(sends==1);if(mode=="raw")assert(sendLocked);
 }else if(mode=="display"||mode=="js"){
  float expected=std::isnan(val)?11*(pid+1):rack::math::clampSafe(val,-10000,10000);assert(mod.params[pid].value==expected);assert(hist.count==1);
  // Real ParamQuantity::setDisplayValue returns before any setter for NaN.
  // Preserve that existing no-op; there must be no remote send to lock-check.
  if(std::isnan(val))assert(sends==0);else assert(sendLocked);
 }
 for(int i=0;i<3;++i)if(i!=pid&&!(mode=="smooth"&&!invalid&&i==0))assert(mod.params[i].value==11*(i+1));
 assert(SharedMutex::held==0);std::cout<<"PASS "<<mode<<" "<<pid<<" "<<argv[3]<<" "<<mid<<"\n";
}
