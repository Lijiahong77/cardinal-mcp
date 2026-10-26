"""C++11 real-source serial/thread regression. No Rack window, audio device or sockets. DSP process is extracted verbatim; Port ABI and per-read barrier hook are shells. Actual std::recursive_mutex is unchanged.

Verbatim DSP process/reset/advance/stopFirst/enterSection and actual class header plus actual Rack float SchmittTrigger/PulseGenerator. Constructor substitutes config-only setup with resetState. Verbatim methods: 4 controls' constructors/onButton/step, SongRoll data serialization,
Rack Module serialization, modelFromJson, history ModuleChange destructor/undo/redo,
State push/undo/redo and Engine moduleFromJson. Only Engine mutex ABI is substituted.
Shells: Widget geometry/event/layout/ownership, registry, empty params and output ports,
Engine module lookup and std::mutex. Real Jansson runtime and header, not JSON mocks.
--reference must contain actual saved source files; never synthesize a candidate here.
"""
import argparse,json,pathlib,subprocess,hashlib,os
HERE=pathlib.Path(__file__).resolve().parent
EXTRA=['rollarea_preview','load_matrix','partial_table','run_high_rearm','high_before_first_process','eop_old_edge','pulse_cleanup','reset_normal','stopped_output_heal','noop_stops','process_before_writer','ui_no_half_config','json_no_half_config','thread_stress','mode_semantics']
B1=['b1_cancel_inflight','b1_readonly_ui_section','b1_readonly_ui_song','b1_readonly_json_section','b1_readonly_json_song','b1_readonly_consecutive','b1_writer_before_cancel','b1_cancel_success','b1_cancel_fail','b1_cancel_repeated','b1_cancel_reset','b1_cancel_json']
CASES=B1+EXTRA+['process_contention','stopfirst_edits','stopfirst_load','snapshot_pattern','snapshot_repeats','snapshot_clock','history_pattern','history_repeats','history_clock','same_section_replace','nostep_repeats','nostep_clock','nostep_mode','repeats_preserve_mode','mode_preserve_repeats','multi_channel_instance','history_chain_branch','preview_null','boundary_pattern','boundary_repeats','boundary_clock','mode_cycle','nonhit_empty','preserve_unrelated','missing_module']
def extract(text,sig):
 start=text.index(sig);a=text.index('{',start);depth=1;i=a+1
 while depth:
  if text[i]=='{':depth+=1
  elif text[i]=='}':depth-=1
  i+=1
 return text[start:i]
def generate(ref):
 files={p.name:p.read_text(encoding='utf8') for p in ref.iterdir() if p.suffix in ('.cpp','.hpp')}
 pre=(HERE/'shell.cpp').read_text();datahpp=files['SongRollData.hpp'].replace('#pragma once','').replace('#include "rack.hpp"','')
 classes=(HERE/'classes.cpp').read_text()
 parts=[pre,extract(files['plugin.cpp'],'Model* modelFromJson').replace('Model* modelFromJson','plugin::Model* plugin::modelFromJson'),extract(files['Module.cpp'],'json_t* Module::toJson'),extract(files['Module.cpp'],'void Module::fromJson'),datahpp, 'namespace rack { namespace dsp { template<typename T=float>struct TSchmittTrigger; template<> '+extract(files['digital.hpp'],'struct TSchmittTrigger<float>')+'; typedef TSchmittTrigger<> SchmittTrigger; '+extract(files['digital.hpp'],'struct PulseGenerator')+'; }}', files['Transport.hpp'], '\n'.join(l for l in files['SongRollModule.hpp'].splitlines() if not l.startswith('#include')), 'using namespace SongRoll;', classes, 'SongRollModule::SongRollModule():transport(&songRollData){resetState();}', extract(files['Transport.cpp'],'Transport::Transport'), extract(files['Transport.cpp'],'void Transport::reset')]
 parts.append(extract(files['Engine.cpp'],'void Engine::moduleFromJson').replace('std::lock_guard<SharedMutex> lock(internal->mutex);','std::lock_guard<std::mutex> lock(mutex);'))
 for sig in ['ModuleChange::~ModuleChange','void ModuleChange::undo','void ModuleChange::redo','void State::push','void State::undo','void State::redo']:parts.append('namespace history { '+extract(files['history.cpp'],sig)+' }')
 parts.append(files['SongRollData.cpp'].replace('#include "../SongRoll/SongRollData.hpp"',''))
 for sig in ['void SongRollModule::resetState','void SongRollModule::onReset','void SongRollModule::advanceSection','void SongRollModule::process','void SongRollModule::stopFirst','void SongRollModule::enterSection','json_t *SongRollModule::dataToJson','void SongRollModule::dataFromJson']:parts.append(extract(files['SongRollModule.cpp'],sig))
 for f,c in [('PatternControlWidget.cpp','PatternControlWidget'),('RepeatControlWidget.cpp','RepeatControlWidget'),('ClockDivControlWidget.cpp','ClockDivControlWidget')]:
  parts.extend([extract(files[f],c+'::'+c+'()'),extract(files[f],'void '+c+'::onButton')])
 parts.append(extract(files['RollArea.cpp'],'RollArea::RollArea('))
 parts.extend([extract(files['PatternControllerSlice.cpp'],'PatternControllerSlice::PatternControllerSlice('),extract(files['PatternControllerSlice.cpp'],'void PatternControllerSlice::step'),(HERE/'tests.cpp').read_text().replace('int main(int argc,char**argv)',(HERE/'extra.cpp').read_text().replace('static void extra(', (HERE/'b1.cpp').read_text()+'\nstatic void extra(').replace(' if(test=="rollarea_preview")',' if(test.find("b1_")==0){b1(test,m,sl);return;}\n if(test=="rollarea_preview")')+'\nint main(int argc,char**argv)')])
 return '\n'.join(parts),{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in ref.iterdir() if p.is_file()}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--reference',type=pathlib.Path,default=HERE/'reference');ap.add_argument('--out',type=pathlib.Path,required=True);ap.add_argument('--case',action='append',choices=CASES);ap.add_argument('--jansson-include-dir','--jansson-include',dest='jansson_include',default=os.environ.get('JANSSON_INCLUDE_DIR'),help='Linux directory containing jansson.h and jansson_config.h (or JANSSON_INCLUDE_DIR)');a=ap.parse_args()
 if not a.jansson_include or not pathlib.Path(a.jansson_include).is_absolute() or not all((pathlib.Path(a.jansson_include)/h).is_file() for h in ('jansson.h','jansson_config.h')):
  ap.error('Jansson headers required: set --jansson-include-dir or JANSSON_INCLUDE_DIR to an absolute Linux directory containing jansson.h and jansson_config.h; got '+repr(a.jansson_include))
 a.out.mkdir(parents=True,exist_ok=True);src,hashes=generate(a.reference);(a.out/'generated.cpp').write_text(src);(a.out/'sourcehashes.json').write_text(json.dumps(hashes,indent=2))
 command=['g++','-std=c++11','-O0','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer','-pthread','-H','-I',a.jansson_include,str(a.out/'generated.cpp'),'-l:libjansson.so.4','-o',str(a.out/'harness')]
 r=subprocess.run(command,capture_output=True,text=True);(a.out/'compile.log').write_text(r.stdout+r.stderr)
 results={'compile':{'command':command,'rc':r.returncode,'jansson_include_dir':a.jansson_include,'include_trace':[line for line in r.stderr.splitlines() if 'jansson.h' in line or 'jansson_config.h' in line]},'scope':__doc__,'cases':[]}
 if r.returncode==0:
  for case in a.case or CASES:
   p=subprocess.run([str(a.out/'harness'),case],capture_output=True,text=True,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=1'));results['cases'].append(dict(id=case,rc=p.returncode,stdout=p.stdout,stderr=p.stderr))
 (a.out/'results.json').write_text(json.dumps(results,indent=2));print(json.dumps(results,indent=2))
 return 0 if r.returncode==0 and all(c['rc']==0 for c in results['cases']) else 1
if __name__=='__main__':raise SystemExit(main())
