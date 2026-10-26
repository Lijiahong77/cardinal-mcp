// Explicit serial ABI shells: no real UI, plugin registry, engine lifetime or DSP.
#include <jansson.h>
#include <algorithm>
#include <vector>
#include <string>
#include <stdexcept>
#include <iostream>
#include <cassert>
#include <mutex>
#include <thread>
#include <future>
#include <atomic>
#include <condition_variable>
#include <functional>
#include <chrono>
#include <cstdint>
#define INFO(...) ((void)0)
#define GLFW_PRESS 1
#define GLFW_MOUSE_BUTTON_LEFT 0
using std::string;
template<class T>T clamp(T x,T a,T b){return std::max(a,std::min(b,x));}
namespace rack { namespace math {using ::clamp;} }
struct Exception:std::runtime_error { template<class... T> Exception(const char*s,T...):std::runtime_error(s){} };
namespace plugin {struct Plugin{string slug="rcm",version="test";};struct Model{Plugin* plugin;string slug="rcm-songroll";explicit Model(Plugin* p):plugin(p){}}; Plugin p;Model m{&p};string normalizeSlug(string s){return s;} Model* getModelFallback(string a,string b){return a=="rcm"&&b=="rcm-songroll"?&m:nullptr;} Model* modelFromJson(json_t*);}
struct Port {float v=0;int channels=1;std::function<void()> onRead,onWrite;float getVoltage(){if(onRead)onRead();return v;}void setVoltage(float x){if(onWrite)onWrite();v=x;}void setChannels(int n){channels=n;}};
struct Module {struct ProcessArgs{float sampleTime=1.f/48000;};struct ResetEvent{};Port inputs[16],outputs[16];virtual void process(const ProcessArgs&){}virtual void onReset(const ResetEvent&){}long id=42; plugin::Model* model=&plugin::m;struct Internal{bool bypassed=false;} obj,*internal=&obj;struct Exp{long moduleId=-1;}leftExpander,rightExpander;json_t* paramsToJson(){return json_array();}void paramsFromJson(json_t*){}virtual json_t* dataToJson()=0;virtual void dataFromJson(json_t*)=0;json_t* toJson();void fromJson(json_t*);};
namespace engine {using ::Module;}
struct Engine{std::vector<Module*> modules;std::mutex mutex;Module* getModule(long id){for(auto*m:modules)if(m->id==id)return m;return nullptr;}void moduleFromJson(Module* m,json_t* j);};
namespace history {struct ModuleChange{string name;long moduleId;json_t* oldModuleJ=nullptr,*newModuleJ=nullptr;~ModuleChange();void undo();void redo();};using Action = ModuleChange;struct State{std::vector<ModuleChange*> actions;int actionIndex=0,savedIndex=-1;bool canUndo(){return actionIndex>0;}bool canRedo(){return actionIndex<(int)actions.size();}void push(ModuleChange*);void undo();void redo();~State(){for(auto*p:actions)delete p;}};}
struct App{Engine* engine;history::State* history;};App* APP;
struct Vec{float x,y;Vec(float x=0,float y=0):x(x),y(y){}};struct Rect{Vec pos,size;Rect(Vec p={},Vec s={}):pos(p),size(s){}bool contains(Vec v){return v.x>=pos.x&&v.y>=pos.y&&v.x<pos.x+size.x&&v.y<pos.y+size.y;}};
namespace event{struct Button{int action=1,button=0;Vec pos;void consume(void*)const{}};}
struct Widget{Rect box{Vec(),Vec(100,100)};std::vector<Widget*> children;virtual void step(){}void onButton(const event::Button&){}void addChild(Widget*w){children.push_back(w);}virtual ~Widget(){for(auto*p:children)delete p;}};
struct SequentialLayout:Widget{enum{VERTICAL_ORIENTATION,LEFT_ALIGNMENT};int orientation=0,alignment=0;Vec spacing;};
struct PatternHeaderWidget:Widget{int pattern,repeats,repeats_completed;bool active=false;PatternHeaderWidget(int p,int r,int c):pattern(p),repeats(r),repeats_completed(c){}};

namespace rack {using ::Module;}
