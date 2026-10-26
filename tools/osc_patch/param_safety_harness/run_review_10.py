
from pathlib import Path
import re,subprocess,json,sys
C=Path(sys.argv[1]).resolve();L=Path(__file__).parent/'reference';W=Path(__file__).parent;D=Path(sys.argv[2]).resolve()
assert D != C and C not in D.parents, 'output must be separate from source'
D.mkdir(parents=True,exist_ok=False)
def ext(p,s):
 t=p.read_text();a=t.index(s);b=t.index('{',a);i=b+1;n=1
 while n:n+=(t[i]=='{')-(t[i]=='}');i+=1
 return t[a:i]
h=(W/'cpp_param_harness.cpp').read_text().split('int main(')[0]
a=h.index('struct SharedMutex {');b=h.index('template<class M>',a)
real=ext(C/'src/Rack/include/mutex.hpp','struct SharedMutex {')+';'
real=real.replace('struct SharedMutex','struct RackSharedMutex')
# Constructor/destructor names must follow the extracted test-local class rename.
real=real.replace('SharedMutex()', 'RackSharedMutex()')
h=h[:a]+'using Exception=std::runtime_error;\n'+real+'\nstruct SharedMutex:RackSharedMutex {static thread_local int held;void lock(){RackSharedMutex::lock();++held;}void unlock(){--held;RackSharedMutex::unlock();}void lock_shared(){RackSharedMutex::lock_shared();++held;}void unlock_shared(){--held;RackSharedMutex::unlock_shared();}};\nthread_local int SharedMutex::held=0;\n'+h[b:]
h='#include <pthread.h>\n#include <stdexcept>\n'+h
h=h.replace('float getValue();void setImmediateValue(float);virtual void setDisplayValue(float);','virtual float getValue();void setValue(float);void setImmediateValue(float);virtual void setDisplayValue(float);')
h=h.replace('struct Module {int64_t','struct Module {virtual ~Module()=default;int64_t')
h=h.replace('virtual float getValue();','virtual float getDisplayValue(){return getValue();}virtual float getValue();')
h=h.replace('float oldValue,newValue;};','float oldValue,newValue;void undo();void redo();};')
engine=C/'src/override/Engine.cpp';pq=C/'src/Rack/src/engine/ParamQuantity.cpp';common=C/'src/CardinalCommon.cpp'
fns=['static bool Engine_isValidParam(','Module* Engine::getModule(','Module* Engine::getModule_NoLock(','void Engine::setParamValue(','float Engine::getParamValue(','void Engine::setParamSmoothValue(','float Engine::getParamSmoothValue(','ParamWriteResult Engine_writeParamById(']
prod='namespace rack {namespace engine {\n'+'\n'.join(ext(engine,s) for s in fns)+'\n'+'\n'.join(ext(pq,s) for s in ['float ParamQuantity::getValue(','void ParamQuantity::setValue(','void ParamQuantity::setImmediateValue(','void ParamQuantity::setDisplayValue('])+'\n}}\n'+'\n'.join(ext(common,s) for s in ['static int osc_param_handler(','static int osc_param_set_display_handler(','static JSValue jsApiSetDisplayValue('])
prod+='\nnamespace rack {namespace history {\n'+ '\n'.join(ext(L/'src/Rack/src/history.cpp',s) for s in ['void ParamChange::undo()','void ParamChange::redo()'])+'\n}}\n'
(D/'production.inc').write_text(prod);(D/'safety-declarations.inc').write_text((C/'src/ParamWriteSafety.hpp').read_text());t=(C/'src/Rack/include/engine/Param.hpp').read_text();(D/'param.inc').write_text(t[t.index('struct Param {'):t.index('} // namespace engine')])
steps=ext(L/'plugins/BogaudioModules/src/AddrSeq.hpp','struct StepsParamQuantity : ParamQuantity')+';'
h+='\nusing namespace rack::engine;using SpinLock=std::mutex;float clamp(float v,float a,float b){return rack::math::clampSafe(v,a,b);}\nstruct AddrSeq:Module {std::mutex _elementsLock;std::vector<int>_elements;'+steps+'};\n'
h+=r'''
struct VirtualPQ:ParamQuantity {bool entered=false;float getValue() override{return ParamQuantity::getValue()+100;}void setDisplayValue(float v)override{assert(SharedMutex::held==1);entered=true;ParamQuantity::setDisplayValue(v);}};
int main(){
 Engine::Internal in;Engine e{&in};Module m;m.params.resize(3);ParamQuantity pq[3];for(int i=0;i<3;i++){pq[i].module=&m;pq[i].paramId=i;m.paramQuantities.push_back(&pq[i]);}in.modulesCache[7]=&m;
 rack::History hist;rack::App app;app.engine=&e;app.history=&hist;rack::app=&app;
 auto check=[](const char*name){assert(SharedMutex::held==0);std::cout<<"PASS "<<name<<"\n";};
 pq[1].displayMultiplier=1000;auto r=Engine_writeParamById(&e,7,1,275,true);assert(std::abs(r.newValue-.275f)<1e-6);check("milliseconds");
 rack::history::ParamChange action;action.moduleId=7;action.paramId=1;action.oldValue=r.oldValue;action.newValue=r.newValue;action.undo();assert(e.getParamValue(&m,1)==r.oldValue);action.redo();assert(e.getParamValue(&m,1)==r.newValue);check("real-history-undo-redo");
 pq[1].displayMultiplier=261.625565f;pq[1].displayBase=2;r=Engine_writeParamById(&e,7,1,440,true);assert(std::abs(r.newValue-std::log2(440/261.625565f))<1e-6);check("exponential-frequency");
 pq[1].displayMultiplier=20;pq[1].displayBase=-10;r=Engine_writeParamById(&e,7,1,0,true);assert(r.newValue==1);check("logarithmic-decibels");
 pq[1].displayMultiplier=1;pq[1].displayBase=0;pq[1].snapEnabled=true;r=Engine_writeParamById(&e,7,1,.6,true);assert(r.newValue==1);pq[1].snapEnabled=false;check("snap");
 e.setParamSmoothValue(&m,1,6);r=Engine_writeParamById(&e,7,1,2,true);assert(r.oldValue==6&&r.newValue==2&&in.smoothModule==nullptr);check("smoothing-target-and-cancel");
 m.paramQuantities[1]=nullptr;r=Engine_writeParamById(&e,7,1,2,true);assert(r.status==ParamWriteStatus::BadParam);m.paramQuantities.resize(1);r=Engine_writeParamById(&e,7,1,2,true);assert(r.status==ParamWriteStatus::BadParam);check("null-and-short-quantities");
 r=Engine_writeParamById(nullptr,7,0,2,false);assert(r.status==ParamWriteStatus::NoModule);r=Engine_writeParamById(&e,999,0,2,false);assert(r.status==ParamWriteStatus::NoModule);r=Engine_writeParamById(&e,7,-1,2,false);assert(r.status==ParamWriteStatus::BadParam);check("missing-and-negative");
 VirtualPQ vp;vp.module=&m;vp.paramId=0;m.paramQuantities[0]=&vp;e.setParamValue(&m,0,3);r=Engine_writeParamById(&e,7,0,4,true);assert(vp.entered&&r.oldValue==103&&r.newValue==104);check("virtual-get-and-set");
 AddrSeq am;am.id=8;am.params.resize(1);am._elements.resize(16);AddrSeq::StepsParamQuantity sp;sp.module=&am;sp.paramId=0;sp.minValue=1;sp.maxValue=8;am.paramQuantities.push_back(&sp);in.modulesCache[8]=&am;r=Engine_writeParamById(&e,8,0,16,true);assert(r.status==ParamWriteStatus::Ok&&r.newValue==8);check("real-addrseq-nested-module-lock");
}
'''
(D/'harness.cpp').write_text(h)
p=subprocess.run(['g++','-std=c++17','-g','-O1','-fsanitize=address,undefined','-fno-sanitize-recover=all','-pthread',str(D/'harness.cpp'),'-o',str(D/'harness')],capture_output=True,timeout=120);print('COMPILE',p.returncode);print(p.stderr.decode());assert p.returncode==0
p=subprocess.run([str(D/'harness')],capture_output=True,timeout=20);print('RUN',p.returncode);print(p.stdout.decode());print(p.stderr.decode());(D/'result.json').write_text(json.dumps({'rc':p.returncode,'stdout':p.stdout.decode(),'stderr':p.stderr.decode()},indent=2));assert p.returncode==0
