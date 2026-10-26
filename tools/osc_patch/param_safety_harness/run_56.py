"""Extract real C++ function bodies and execute isolated ASan+UBSan scenarios."""
import pathlib,subprocess,json,hashlib,os,re,sys,collections
L=pathlib.Path(sys.argv[1]).resolve();A=pathlib.Path(sys.argv[2]).resolve()
assert A != L and L not in A.parents, 'output must be separate from source'
A.mkdir(parents=True,exist_ok=False);phase='green';D=A/'generated';D.mkdir()
records=[]
def extract(path,signature):
 text=path.read_text();start=text.index(signature);begin=text.index('{',start);depth=1;i=begin+1
 while depth:
  if text[i]=='{':depth+=1
  elif text[i]=='}':depth-=1
  i+=1
 result=text[start:i];records.append({'path':str(path),'signature':signature,'sha256':hashlib.sha256(result.encode()).hexdigest(),'bytes':len(result.encode())});return result
engine=L/'src/override/Engine.cpp';common=L/'src/CardinalCommon.cpp';pq=L/'src/Rack/src/engine/ParamQuantity.cpp'
fns=['Module* Engine::getModule(','Module* Engine::getModule_NoLock(','void Engine::setParamValue(','float Engine::getParamValue(','void Engine::setParamSmoothValue(','float Engine::getParamSmoothValue(']
if (L/'src/ParamWriteSafety.hpp').exists():fns=['static bool Engine_isValidParam(']+fns+['ParamWriteResult Engine_writeParamById(']
parts=[extract(engine,s) for s in fns]+[extract(pq,s) for s in ['float ParamQuantity::getValue(','void ParamQuantity::setImmediateValue(','void ParamQuantity::setDisplayValue(']]
cpp='namespace rack {namespace engine {\n'+'\n\n'.join(parts)+'\n}}\n'+'\n\n'.join(extract(common,s) for s in ['static int osc_param_handler(','static int osc_param_set_display_handler(','static JSValue jsApiSetDisplayValue('])
(D/'production.inc').write_text(cpp);header=L/'src/ParamWriteSafety.hpp';(D/'safety-declarations.inc').write_text(header.read_text().replace('#pragma once','').replace('#include <cstdint>','') if header.exists() else '')
param=(L/'src/Rack/include/engine/Param.hpp').read_text();(D/'param.inc').write_text(param[param.index('struct Param {'):param.index('} // namespace engine')]);(D/'harness.cpp').write_bytes((pathlib.Path(__file__).parent/'cpp_param_harness.cpp').read_bytes())
(A/('cpp-param-safety-'+phase+'-extractions.json')).write_text(json.dumps(records,indent=2))
cmd=['g++','-std=c++17','-g','-O1','-fno-omit-frame-pointer','-fsanitize=address,undefined','-fno-sanitize-recover=all','-pthread',str(D/'harness.cpp'),'-o',str(D/'harness')]
p=subprocess.run(cmd,capture_output=True,timeout=120);(A/('cpp-param-safety-'+phase+'-compile.log')).write_bytes(p.stdout+p.stderr);assert not p.returncode,p.stderr.decode()
scenarios=[]
for mode in ['raw','direct','smooth','display','js']:
 for pid in ['-1','3','2147483647']:scenarios.append([mode,pid,'440','7'])
 scenarios += [[mode,'1','440','-1'],[mode,'1','440','9223372036854775807']]
 for val in ['440','-12.5','0.275','nan','inf','-inf']:scenarios.append([mode,'1',val,'7'])
scenarios.append(['lifetime','1','440','7'])
out=[]
for n,args in enumerate(scenarios):
 env=dict(os.environ,ASAN_OPTIONS='detect_leaks=1:abort_on_error=1',UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1')
 p=subprocess.run([str(D/'harness'),*args],capture_output=True,timeout=10,env=env)
 r={'id':'/'.join(args),'args':args,'rc':p.returncode,'stdout':p.stdout.decode('utf8','replace'),'stderr':p.stderr.decode('utf8','replace')};out.append(r)
 with (A/('cpp-param-safety-'+phase+'-cases.jsonl')).open('a') as f:f.write(json.dumps(r)+'\n')
summary={'phase':phase,'binary':str(D/'harness'),'scenarios':len(out),'unique':len(set(r['id'] for r in out)),'passed':sum(r['rc']==0 for r in out),'failed':sum(r['rc']!=0 for r in out),'failed_ids':[r['id'] for r in out if r['rc']!=0],'sources':'verbatim extraction; Rack and protocol ownership shells explicitly stubbed, real Param and ParamQuantity conversion bodies','compiler':subprocess.check_output(['g++','--version']).decode()}
(A/('cpp-param-safety-'+phase+'-summary.json')).write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))
if phase.startswith('green'):assert all(r['rc']==0 for r in out),summary
else:assert any(r['rc']!=0 and ('AddressSanitizer' in r['stderr'] or 'Assertion' in r['stderr']) for r in out)
